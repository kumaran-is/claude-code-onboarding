# Tier 1 vs Tier 2 — Vector Store Selection

Load this file BEFORE specifying where any new vector data should live —
adding embeddings to a service, designing a schema with a `vector(N)`
column, creating a new Weaviate collection, or reviewing a PR that does
either. Picking the wrong tier is expensive to undo because schemas and
indexes are immutable in production.

## The split

```
┌────────────────────────────────────────┐  ┌────────────────────────────────────────┐
│  TIER 1 — pgvector (PostgreSQL)        │  │  TIER 2 — Weaviate Cloud               │
│                                        │  │                                        │
│  • Entity profile embeddings           │  │  • Document / clause chunks            │
│  • Rule / policy embeddings            │  │  • FAQ corpus                          │
│                                        │  │                                        │
│  • Hot path / low latency              │  │  • Cold path / batch RAG               │
│  • Joins with relational data          │  │  • Pure semantic search                │
│  • Strong consistency                  │  │  • Eventual consistency OK             │
│  • <50ms p99 query                     │  │  • <500ms p99 query                    │
└────────────────────────────────────────┘  └────────────────────────────────────────┘
        Entity matching, rule lookup              QA agents, FAQ search
```

## Step 0 — use the platform you already run (collocated vs dedicated)

Ask first **where the data naturally lives**. Before the tier rule below:

- If the service has no dedicated vector/search engine yet, start **collocated** (pgvector in the system-of-record PostgreSQL). Adding a dedicated store (or a managed retrieval service) needs an architecture review (ADR) showing the existing platform cannot meet a measured need: corpus size, native hybrid search, physical multi-tenancy, or content that lives outside the relational store (guardrail G13).
- Require a cost estimate at current and 10× volume, including **idle cost**: some managed vector services bill a minimum footprint at zero traffic.
- Check these criteria for the candidate store: filtered-ANN recall under selective filters, native hybrid search, multi-tenancy limits, hard-delete latency and tombstone compaction, read-after-write consistency, index types (HNSW, IVF, flat, quantization), backup/restore, encryption at rest, private networking, region pinning.
- A managed retrieval service is acceptable for a small team doing standard document Q&A only after its ACL and deletion semantics are checked against the chunk envelope and ACL sync rules (`rag-ingest-checklist.md` §B, §E) and the deletion propagation path (`rag-architect/references/versioning-and-freshness.md` §8); it trades control over chunking, ranking and metadata for less to operate.
- **Do not dual-write the same content to two stores as two sources of truth**; they drift. When both relational and semantic filtering are needed, use two-stage retrieval (filter in one, rank in the other).

The tier rule below applies when both tiers are already on the platform (as in this toolkit's reference stack).

## The decision rule (binary, mandatory)

Answer this question before adding ANY vector data:

> **"Does the query need SQL JOIN, PostGIS, or relational filters alongside vector similarity?"**

| Answer | Tier | Rationale |
|---|---|---|
| **YES** | **Tier 1 — pgvector** | Vector lives next to the relational data so one SQL transaction does everything. Weaviate cannot JOIN with Postgres tables — denormalising to keep them in sync introduces eventual-consistency bugs. |
| **NO — pure semantic / hybrid text search** | **Tier 2 — Weaviate** | Weaviate's native `hybrid()`, physical multi-tenancy, and reranker plug-ins are purpose-built for this. pgvector's BM25 is weaker; pgvector multi-tenancy is filter-only. |
| **Both?** | **Two-stage retrieval** | Tier 1 returns candidates with relational filters → pass IDs to Tier 2 for semantic re-rank. See `rag-pipeline-patterns.md` "Two-Stage Retrieval" section. |

## Decision criteria checklist

Tick what applies to your data. Mostly Tier 1 column? → pgvector. Mostly Tier 2 column? → Weaviate.

| Criterion | Tier 1 (pgvector) | Tier 2 (Weaviate) |
|---|---|---|
| Joined with relational data? | ✓ Yes — entity profiles / rules JOIN other tables | ✗ No — pure text content |
| Filtered by SQL aggregates / PostGIS / multi-table predicates? | ✓ Yes (`ST_Within`, multi-table joins) — mind filtered-ANN recall (`ann-vs-knn.md`) | ✗ Mostly tenant + a few metadata filters |
| Strong consistency required? | ✓ Yes — new entity row → MUST match instantly | ✗ No — chunk indexed → readable in seconds is fine |
| Hybrid search required? (BM25 + vector) | Possible in SQL (vector CTE + `tsvector` CTE + RRF — `rag-pipeline-patterns.md`) | ✓ Native `hybrid()` — exact phrases ("Section 5.3", "$2,400") matter |
| Reranking required? | Decide by eval, not by store | Decide by eval, not by store |
| Scale per tenant | Thousands → low millions of rows | Millions → billions of chunks |
| User-blocking latency budget | <50ms (results page) | <500ms (chat response, can stream) |
| Schema flexibility | Stable — Alembic migration per change | Flexible — chunks vary per document |
| Multi-tenancy isolation | `WHERE tenant_id` + RLS (`FORCE ROW LEVEL SECURITY`) or partitions | Native tenant shards (`with_tenant()`) |

If your data hits ≥4 left-column boxes → **Tier 1**. If it hits ≥4 right-column boxes → **Tier 2**. If it splits roughly 50/50, your data may be in the wrong shape — re-think before adding it.

## Why split at all (and not just one store)?

### "Why not put everything in Weaviate?"

- Weaviate doesn't `JOIN` with Postgres. Entity matching like `providers JOIN coverage_areas` + `ST_Within` (PostGIS) would force denormalisation and two-database write consistency.
- Weaviate has no PostGIS polygon predicates. Geo filtering on coverage areas would happen client-side after pulling candidates.
- A second managed store adds cost and operations; pgvector sits inside your existing PostgreSQL (compare current pricing for your sizes).
- Transactional freshness — a row committed at T is visible to the next query in the same database.

### "Why not put everything in pgvector?"

- Very large chunk corpora strain one PostgreSQL instance (HNSW build memory, index size, vacuum); measure index build time and p95 latency at your projected size before committing — there is no fixed row limit.
- pgvector hybrid search needs hand-written SQL (a vector CTE and a `ts_rank_cd` CTE fused with RRF — verified example in `rag-pipeline-patterns.md`); Weaviate's `hybrid()` is one call. Note `ts_rank_cd` is not BM25.
- pgvector tenant isolation is a filter (+ RLS or partitions), and selective tenant filters lose ANN recall unless mitigated. Weaviate's native multi-tenancy gives one shard per tenant — useful when many small tenants need structural isolation.
- Weaviate's reranker integration (Cohere, Voyage, BGE modules) is plug-and-play; in pgvector you build it yourself.

## Canonical placement examples (adapt to your domain)

| Vector data | Tier | Reason |
|---|---|---|
| **Entity profile embeddings** (e.g. suppliers, providers) | Tier 1 | JOIN with entity tables, geo filters, ratings |
| **Policy / rule embeddings** | Tier 1 | JOIN with rules tables; compliance flag filters required |
| **Location / coverage embeddings** | Tier 1 | JOIN with location data + PostGIS coverage |
| **Document clause chunks** (e.g. contracts, policies) | Tier 2 | Document ingestion path; QA agent retrieval |
| **FAQ corpus chunks** | Tier 2 | Same retrieval profile as documents |
| **Unstructured review / feedback chunks** | Tier 2 | Pure unstructured text; QA agent retrieval |
| **Agent few-shot examples** (if vectorised) | Neither — keep in code | Fewer than 100 examples; no scale need |

When you encounter a vector data type NOT in this list:

1. Run the decision rule above
2. State the placement + your reasoning in the schema PR description
3. Dispatch `pgvector-schema-reviewer` (Tier 1) or `weaviate-schema-reviewer` (Tier 2)
4. If reviewer flags a tier mismatch, swap to the other tier before merging

## Real-world example — one user request, both tiers

```
1. User submits a request (no vector store yet — triage classifies it)
   ↓
2. Retrieval agent looks up matching entities:
   ┌─────────────────────────────────────────────┐
   │ TIER 1 query (pgvector)                     │
   │ "find matches within criteria,              │
   │  embedding similar to request,              │
   │  active, rating ≥ 4.0, scope=owner_X"       │
   │ → 20 candidates in 30ms                     │
   └─────────────────────────────────────────────┘
   ↓
3. Reranker picks top 3
   ↓
4. User asks a document question ("what does my contract say about X?")
   ↓
5. QA agent retrieves document clauses:
   ┌─────────────────────────────────────────────┐
   │ TIER 2 query (Weaviate)                     │
   │ "hybrid search 'X'                          │
   │  in document_Y, tenant=owner_X"             │
   │ → 5 chunks in 200ms                         │
   │ + reranker → top 3 → LLM answer             │
   └─────────────────────────────────────────────┘
```

## Hard rules (violation = STOP and revert)

- **NEVER** add vector data to pgvector if the answer to the JOIN/PostGIS/aggregate question is "no" AND the corpus is unstructured text AND a Tier 2 store already runs on the platform — that data belongs in Tier 2. Without a Tier 2 store, Step 0 applies.
- **NEVER** add vector data to Weaviate if it needs `JOIN`, PostGIS, or multi-table aggregate filters at query time — that data belongs in Tier 1. Denormalisation is not the fix; denormalisation creates 2-database consistency bugs that surface as silent retrieval misses.
- **NEVER** sync Postgres rows to Weaviate to "have both" — dual-writes drift in production. If you genuinely need both, use two-stage retrieval (Tier 1 candidate → Tier 2 rerank), not synchronisation.
- **NEVER** put a new vector column or collection in a service WITHOUT stating the tier decision in the PR description (dispatch `pgvector-schema-reviewer` or `weaviate-schema-reviewer` to enforce).

## TL;DR

| | **Tier 1 — pgvector** | **Tier 2 — Weaviate** |
|---|---|---|
| **Mental model** | "Vector as a column in your database" | "Database designed entirely around vector search" |
| **Job** | Vectors that live alongside relational data | Vectors for pure unstructured text RAG |
| **Typical uses** | Entity profiles, policy rule embeddings | Document clause chunks, FAQ corpus |
| **Query style** | Mixed — SQL JOIN + WHERE + vector | Pure semantic + hybrid BM25 |
| **Optimal for** | Transactional matching | Long-document QA |
| **Latency** | <50ms (user-blocking) | <500ms (streamable) |
| **Scale** | Millions per tenant | Billions across tenants |
| **Consistency** | ACID with PostgreSQL | Eventual (writes → readable in seconds) |
| **Multi-tenancy** | Logical (`WHERE`) | Physical (`with_tenant()`) |
| **Hybrid search** | DIY | Native `hybrid()` |

**Pick by query characteristics, not by data size.** Most production RAG systems run both — that's expected, not a smell.

## Cross-references

- `.claude/skills/vector-database/SKILL.md` (decision tree)
- `.claude/skills/vector-database/references/pgvector-migration-template.md` (Tier 1 schema design)
- `.claude/skills/vector-database/references/weaviate-collection-patterns.md` (Tier 2 schema design)
- `.claude/skills/vector-database/references/rag-pipeline-patterns.md` "Two-Stage Retrieval" (when both tiers are needed in one query)
- `.claude/agents/pgvector-schema-reviewer.md` (Tier 1 schema review)
- `.claude/agents/weaviate-schema-reviewer.md` (Tier 2 schema review + tier-mismatch flag)
