# ANN vs KNN in RAG — Quick Reference

A practical guide to choosing between exact and approximate nearest-neighbor search for vector retrieval.

---

## The Core Tradeoff

| Item | Meaning | Strength | Weakness |
|------|---------|---------|---------|
| **KNN / Exact search** | Finds the true top-k closest vectors by comparing against all candidates | Highest recall / most accurate | Slower and expensive as data grows |
| **ANN / Approximate search** | Finds "almost nearest" vectors using indexes like **HNSW** or **IVFFlat** | Much faster at scale | Slight recall tradeoff |

**Simple rule:** KNN = accuracy baseline. ANN/HNSW = production scale.

---

## 1. KNN (Exact / Brute-Force Search)

**How it works:** Compares the query vector against *every* vector in the database, returning the true top-k closest.
**Complexity:** O(N) per query — scales linearly with dataset size.

**When to use:**
- Small datasets (< ~50k vectors)
- Local dev and golden-dataset testing
- Measuring "true recall" as a baseline to evaluate ANN against
- Offline batch jobs where latency doesn't matter
- Scoped verification within a narrow metadata filter (one document, one user, one tenant)

**Why it matters:** It's the only way to know what *perfect* retrieval looks like for your data. You can't measure ANN's recall loss without it.

---

## 2. ANN (Approximate Nearest Neighbor)

**How it works:** Uses a pre-built index structure to skip most comparisons, finding *probably* the top-k closest vectors much faster than brute force.

**Complexity:** HNSW usually gives logarithmic-like / sublinear search behavior in practice, but latency depends on index parameters, vector dimensions, metadata filters, and dataset shape — it is not a guaranteed `O(log N)` for every query/data shape.

**Common index types:**

| Index | Strength | Weakness |
|-------|---------|---------|
| **HNSW** | Excellent recall/speed tradeoff for large datasets; scales very far with proper infrastructure | Higher memory footprint (stores graph links), slower build time |
| **IVFFlat** | Lower memory, faster to build | Lower recall than HNSW at same speed; needs training/re-clustering (`lists` rebuild) as data shifts — use for very large, memory-bound, mostly static corpora |
| **Flat** | Exact (technically not ANN) — brute force | Slow at scale |

**When to use ANN:** Production retrieval on any non-trivial dataset (> ~50k vectors).

### A third axis: Quantization

Beyond choosing an index type, **vector quantization** (PQ — Product Quantization, SQ — Scalar Quantization) compresses the vectors themselves to trade accuracy for memory and speed. It composes with HNSW/IVFFlat — e.g. HNSW+PQ is a common large-scale config. Worth considering when memory becomes the bottleneck before latency does; rerank the candidates with full-precision vectors to recover recall.

---

## Recall Tradeoff in Practice

ANN doesn't mean "bad recall" — **well-tuned HNSW can often reach 95–99% recall**, but this must be measured against exact KNN on *your own* golden dataset. Tuning knobs:

- **HNSW `ef_search`** (query-time) — higher = better recall, slower queries
- **HNSW `ef_construction`** (build-time) — higher = better-quality graph, slower index build
- **HNSW `M`** (build-time) — higher = better recall, more memory
- **IVFFlat `probes`** (query-time, `ivfflat.probes`) — higher = better recall, slower queries; start near `sqrt(lists)`

**The golden workflow:** Measure recall of your ANN config against KNN ground truth on a sample, then tune until ANN-vs-exact overlap@k meets the ratified floor (ADAPT default **≥ 0.95 of exact**). If exact KNN also misses the right chunk, the problem is chunking or embeddings, not the index. (This index-quality measure — the share of the exact top-k that ANN also returns — is distinct from retrieval Recall@K against labeled relevant chunks; metric formulas live in the `llm-evaluation` skill.)

Set query-time knobs with `SET LOCAL` inside the request transaction. A plain `SET` on a pooled connection persists into the next request (verified on PG16 and again on PostgreSQL 18.7 + pgvector 0.8.7: `SET LOCAL hnsw.ef_search = 200` reverts to 40 after commit; a session `SET` stays 200).

---

## Filtered ANN — isolation holds, recall does not

pgvector applies the `WHERE` clause **after** the HNSW/IVFFlat index produces its candidate list (`hnsw.ef_search`, default 40). With a selective filter — a small tenant, a rare category, `is_current` on a mostly-superseded corpus — the query can return fewer than `LIMIT` rows or none. Unauthorized rows are still excluded (isolation is fine); the right rows are simply never reached.

**Reproduced on PostgreSQL 18.7 + pgvector 0.8.7** (20,000 rows, `vector(8)`, HNSW `m=16, ef_construction=64`, an unindexed filter matching 1% of rows, `LIMIT 10`, SQLAlchemy 2.1.9 + asyncpg; executed test with a negative control):

| Plan | Rows returned | Overlap with exact top-10 |
|---|---|---|
| HNSW, default (`hnsw.iterative_scan = off`, `ef_search = 40`) | **0–1** (two runs) | 0.0–0.1 |
| HNSW, `SET LOCAL hnsw.iterative_scan = strict_order` | 10 | 1.0 |
| HNSW, `SET LOCAL hnsw.iterative_scan = relaxed_order` | 10 | 1.0 |
| Negative control: `ALTER DATABASE ... SET hnsw.iterative_scan = relaxed_order` | 10 for the "default" query too, so the test's "default loses rows" assertion failed as intended | - |

**Planner note (pgvector >= 0.8.0 cost estimation):** when the filter column has its own selective B-tree index (`tenant_id = 150`, 30 rows), the planner chose `Index Scan using ix_chunks_tenant` + sort, i.e. an exact search with full recall, and did not touch HNSW. The recall loss appears when the filter is unindexed or not selective enough for the B-tree path. Always read `EXPLAIN` for your real filter before deciding which fix you need.

Earlier reproduction on PostgreSQL 16 + pgvector 0.6.2 (tenant 1 = 1% of rows; this version has no iterative scans):

| Plan | Rows returned |
|---|---|
| HNSW, default `ef_search = 40` | **0** |
| HNSW, `SET LOCAL hnsw.ef_search = 400` | 3–6 (two seeded fixtures) |
| Exact scan (`SET LOCAL enable_indexscan = off`) | 10 |
| Partial HNSW index `WHERE tenant_id = 1`, tenant bound as `$2` (asyncpg), 7 calls on one connection | `[10, 10, 0, 0, 0, 0, 0]` — see the generic-plan trap below |
| Same, `SET LOCAL plan_cache_mode = force_custom_plan` in the transaction | `[10] × 7` |
| Same, tenant written as a literal (`tenant_id = 1`) | 10 |

Fixes, in order of preference:

| Fix | When | Notes |
|---|---|---|
| Iterative index scans | pgvector ≥ 0.8.0 | `SET LOCAL hnsw.iterative_scan = relaxed_order` (or `strict_order`; IVFFlat accepts only `off`/`relaxed_order`, executed); bounded by `hnsw.max_scan_tuples` (default 20000), `hnsw.scan_mem_multiplier` (default 1) / `ivfflat.max_probes`. Executed on 0.8.7: 0–1 → 10 rows (table above). `relaxed_order` may return results slightly out of distance order: re-sort in an outer query when order matters |
| Partial index per hot filter value | Few, stable filter values (e.g. `is_current`, a large tenant) | `CREATE INDEX … USING hnsw (embedding vector_cosine_ops) WHERE is_current`. If the predicate's value is a bind parameter (`tenant_id = $2`), you MUST also `SET LOCAL plan_cache_mode = force_custom_plan` (generic-plan trap below) |
| Partition by tenant (or list/range key) | Many tenants, tenant-scoped queries | Each partition has its own index; the planner prunes |
| Exact scan for small scopes | Tenant below a row threshold | Exact search over a few thousand rows is cheap and has perfect recall |
| Raise `ef_search` | Stopgap only | Helps, does not guarantee `LIMIT` rows (3–6 of 10 above) |

```sql
BEGIN;
SET LOCAL hnsw.iterative_scan = relaxed_order;   -- pgvector >= 0.8.0
SET LOCAL hnsw.ef_search = 100;
SELECT id FROM doc_chunks
WHERE tenant_id = $1 AND embedding_model = $2 AND is_current
ORDER BY embedding <=> $3 LIMIT 10;
COMMIT;
```

**Generic-plan trap (partial indexes with bound parameters).** Drivers that use server-side prepared statements (asyncpg always; SQLAlchemy's asyncpg dialect; psycopg 3 once a query reaches its `prepare_threshold`) let PostgreSQL switch a statement to a **generic plan**: under the default `plan_cache_mode = auto` the first five executions get custom plans, after which the planner may keep a generic plan built without the parameter values. A generic plan cannot prove `tenant_id = $2` implies the partial index's `WHERE tenant_id = 1`, so it falls back to the full HNSW index and the hot tenant gets 0 rows again — silently, from the 6th call onward on that connection. Executed above: `pg_prepared_statements.custom_plans` stopped at 5 while `generic_plans` grew. Pick one:

- `SET LOCAL plan_cache_mode = force_custom_plan` in the same transaction as the query (executed: `[10] × 7`). Costs one planning step per call; measure it on your query.
- Inline the filter value as a literal, taken from a server-side allowlist of hot values (never from request input), so the predicate is visible to the planner.
- Use the exact-scan path for the scope (`SET LOCAL enable_indexscan = off`), which does not depend on plan choice.

Literal predicates in the query text (`AND is_current`, `AND embedding IS NOT NULL`) are not affected: the generic plan still sees them.

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;   -- partial index on a bound tenant_id
SELECT id FROM doc_chunks
WHERE tenant_id = $1 AND embedding_model = $2 AND is_current
ORDER BY embedding <=> $3 LIMIT 10;
COMMIT;
```

**`iterative_scan` on pgvector < 0.8 can be a silent no-op.** (On 0.8.7 an invalid value fails: `Available values: off, relaxed_order, strict_order`.) On pgvector 0.6.2, `SET LOCAL hnsw.iterative_scan = relaxed_order` was **accepted without error** in a backend where the vector library was not yet loaded (PostgreSQL stores it as a placeholder setting); it errored ("reserved prefix") only once the library was loaded. So the setting is not proof that iterative scans are active. Check the version at startup and fail closed: `SELECT extversion FROM pg_extension WHERE extname = 'vector'` must be ≥ `0.8.0` before you rely on fix #1.

**Required test:** a fixture with a filter matching ≤ 1% of rows asserts `count == LIMIT` (and equals the exact-scan ids, modulo relaxed ordering). Run the query **more than 5 times on one pooled connection** with the production driver, so a generic-plan switch is caught. Weaviate multi-tenancy avoids this structurally (one shard per tenant); Weaviate property filters inside a shared collection are applied during the HNSW search, but still measure with the same test.

---

## Vector DB Support

**pgvector (Postgres)**
Exact search is the default and gives perfect recall. Adding **HNSW** or **IVFFlat** indexes enables approximate search for speed at scale.

**Weaviate**
Supports **HNSW** (scales well for large datasets), **Flat** (brute force, good for small datasets), **Dynamic** (auto-switches), and **HFresh**.

**Other engines** (Pinecone, Qdrant, Milvus, FAISS): support ANN-style indexing, often including HNSW or similar high-performance vector indexes, but **defaults vary by product and deployment mode**. FAISS in particular is a library with many index families; Pinecone abstracts internals. Always check the specific version and deployment.

---

## Recommended Pattern

### Broad production search

Use **ANN with HNSW** for production retrieval, paired with hybrid search and a reranker:

```text
User query
  ↓
Hybrid retrieval: BM25 + vector ANN/HNSW
  ↓
Retrieve top 50–100 chunks (over-retrieve on purpose)
  ↓
Rerank with your preferred reranker (e.g. Vertex AI Ranking, Cohere Rerank, cross-encoder)
  ↓
Keep top 5–10 chunks
  ↓
Generate grounded answer with citations
  ↓
Evaluate Recall@k + Faithfulness
```

**Why over-retrieve then rerank?** ANN gives fast, broad recall. The reranker cleans up ordering and relevance. This combo beats either alone — and compensates for ANN's small recall loss by widening the candidate pool.

### High-risk scoped verification

For high-risk answers — contractual clauses, financial terms, legal-like explanations — combine ANN with a scoped exact-KNN fallback:

```text
Broad production search:
  ANN/HNSW + hybrid retrieval + reranker

High-risk scoped verification:
  metadata filter (one document / one user / one tenant)
  → smaller candidate set
  → exact KNN or strong rerank
  → citation-required answer
```

This gives the best of both worlds: ANN handles scale, exact KNN handles the narrow, high-stakes cases where you can't afford to miss a clause.

---

## Recommendation Matrix

| Environment | Recommendation |
|-------------|---------------|
| **Small local dev / golden dataset testing** | Use **Exact KNN / Flat** to measure true recall baseline |
| **Production RAG** | Use **ANN / HNSW** for speed + scale |
| **High-risk answers** (contracts, financial terms, compliance) | Narrow with metadata filter → exact KNN or strong rerank → citation required |
| **Postgres pgvector** | Use HNSW when vector data grows beyond ~50k rows |
| **Weaviate** | Use HNSW as main vector index |

---

## Diagnostic Cues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Production retrieval slow at scale | Using exact KNN on large dataset | Switch to HNSW |
| ANN recall noticeably worse than KNN baseline | `ef_search` / `probes` too low | Increase ANN search params, re-measure |
| Small tenant or rare filter returns 0–few rows | Filter applied after the ANN candidate list | See §Filtered ANN |
| High latency even with HNSW | `ef_search` set too high, or k too large | Tune down, or add reranker on smaller top-k |
| Right chunks exist but never retrieved | Embedding model mismatch, not an ANN issue | Validate with KNN — if KNN also misses, fix embeddings/chunking |
| Memory pressure on vector DB | HNSW graph links + high `M` value | Lower `M`, or shard the index |

---

## Final Rule

> **Use exact KNN / Flat as the truth baseline. Use ANN/HNSW for production scale.**
> **For production: ANN/HNSW + hybrid search + reranker + Recall@k evaluation against KNN. For high-risk answers, add scoped verification and citation enforcement.**

---

## References

- [pgvector — GitHub](https://github.com/pgvector/pgvector)
- [Weaviate — Indexing Concepts](https://docs.weaviate.io/weaviate/concepts/indexing)
- [HNSW Paper — Malkov & Yashunin](https://arxiv.org/abs/1603.09320)
