# RAG Operations Guide

Reference for operating a production RAG system: caching, cost management, observability, and optimization (§36 of the production RAG playbook).

---

## 1. Caching Strategies (§36.3)

Six cache layers, applied independently. Choose based on hit rate vs staleness tolerance.

> **Canonical home for RAG cache-key scoping.** `rag-review` 5.7 and the reviewer agents link here.

| Cache Layer | What Gets Cached | Key | TTL | Tenant-Scoped? | Risk if Wrong |
|---|---|---|---|---|---|
| **Chunk embedding** | Embeddings for stored chunks | `content_hash` + model + dims + task type + normalizer version | Until doc update | No — stored rows carry tenant; the vector itself is not scoped | Low — stale embedding = retrieval miss |
| **Query embedding** | Embedding of the user query | `hash(norm(query), model, dims, task_type)` | 1–24h | Optional — the vector does not depend on the tenant; store the hash, not raw query text | Low |
| **Retrieval result** | Top-k chunk ids for a query | `hash(tenant, perm_fp, index_version, model, norm(query), filters)` | 5–15 min | **YES** | **Critical** — cross-tenant/cross-role leak |
| **Exact-match answer** | Full pipeline result for identical queries | `hash(retrieval_key, prompt_version, generation_model)` | 15–60 min | **YES** (via retrieval key) | **Critical** |
| **Semantic answer** | Result for similar (not identical) queries | nearest neighbour on query embedding **within** the same tenant + `perm_fp` + `index_version` partition | 15–30 min | **YES** | **High** — similar wording ≠ same answer |

`perm_fp` = hash of the sorted role and group ids that the retrieval filter used. `index_version` is bumped on every ingest, update or delete in the corpus, so old entries become unreachable (also the cheapest way to honour an erasure request across caches).

### Critical Rule — Retrieval and Answer Keys Carry the Full Scope
```python
# ❌ WRONG — leaks across tenants, roles and corpus versions
cache_key = sha256(query_text)

# ✅ CORRECT
def retrieval_key(tenant: str, perm_fp: str, index_ver: str, model: str, q: str, filters: str) -> str:
    if not tenant:
        raise ValueError("tenant required")     # scope ambiguity fails closed: skip the cache
    return _h(tenant, perm_fp, index_ver, model, norm(q), filters)

def answer_key(retr_key: str, prompt_ver: str, gen_model: str) -> str:
    return _h(retr_key, prompt_ver, gen_model)
```
(`_h` = sha256 over NUL-joined parts; `norm` = NFKC + lowercase + collapsed whitespace. Verified: 5 pytest cases — tenant, permission and index-version changes miss; group order and whitespace do not; empty tenant fails closed.)

Forgetting tenant or permissions in a retrieval/answer key is a **Sev-1 security incident**. Cache *errors* fail open (log with `log_exception`, treat as a miss); scope *ambiguity* fails closed (do not read or write the cache).

### Cache Invalidation Triggers
- Document added/updated/deleted → bump the corpus `index_version`
- ACL or group membership change → new `perm_fp` misses automatically; also purge entries for removed grants if TTL is long
- Prompt or generation-model version change → answer keys change automatically
- Embedding model change → invalidate query- and chunk-embedding caches
- Erasure request → bump `index_version` and purge entries that reference the erased chunk ids

---

## 2. Cost Hierarchy (§36.1)

Typical cost breakdown for a production RAG query (varies by scale and model choice):

| Component | % of Total Cost | Primary Driver |
|---|---|---|
| Vector DB (retrieval + indexing) | 30–50% | Query volume × index size |
| LLM (generation) | 25–40% | Context length × output tokens |
| Reranker (cross-encoder) | 10–20% | Candidate pool size × batch frequency |
| Embeddings (query + ingestion) | 5–15% | Query volume + ingestion frequency |
| Ingestion pipeline (parsing, chunking) | 5–10% | Document update frequency |

### Cost Optimization Techniques (§36.2)

| Technique | Reduces | Impact | Tradeoff |
|---|---|---|---|
| **Quantization (PQ/SQ)** | Vector DB storage 4–16× | High | Small recall loss (~1–3%) |
| **Matryoshka truncation** | Embedding cost + storage | Medium | Recall loss at small dims; test first |
| **Prompt caching** | LLM cost | High for repeated system prompts | API support required (Claude, GPT-4o) |
| **Context compression** | LLM input tokens | Medium | Compressor adds latency |
| **Selective reranking** | Reranker cost | High | Apply only when top-k from fusion diverges |
| **Embedding cache** | Embedding API calls | High for repeated queries | Staleness risk on model updates |
| **Content-hash diff ingestion** | Ingestion cost | High for stable corpora | Implementation overhead |
| **Over-retrieve then filter** | LLM cost | Medium | Retrieve 50–100; rerank to 5–10 instead of always sending 50 to LLM |

---

## 3. Observability — Five Dashboards (§36.4)

Build these before going to production. Each has a primary alert threshold.

### Dashboard 1: Health
| Metric | Alert Threshold |
|---|---|
| RAG pipeline p95 latency | > 2s |
| Retrieval step p95 latency | > 500ms |
| Reranker p95 latency | > 300ms |
| LLM generation p95 latency | > 1.5s |
| Error rate (all stages) | > 1% |
| Ingestion queue depth | > 1000 pending |

### Dashboard 2: Quality
| Metric | Alert Threshold |
|---|---|
| Recall@5 (from eval CI run) | < baseline − 0.05 |
| Faithfulness score (LLM judge) | < 0.85 |
| Abstention rate | > 20% (investigate why; > 5% sudden spike = alert) |
| Citation accuracy | < 0.90 |
| Zero-result rate (no chunks retrieved) | > 5% |

### Dashboard 3: Cost
| Metric | Alert Threshold |
|---|---|
| Cost per query (blended) | > $0.05 (tune to your target) |
| LLM token usage per query | > 3000 input + 500 output tokens (investigate packing) |
| Reranker calls per query | > 150 candidates (over-retrieving) |
| Cache hit rate | < 20% (investigate query diversity or TTL) |

### Dashboard 4: Ingestion
| Metric | Alert Threshold |
|---|---|
| Documents ingested per hour | Drops > 50% vs baseline |
| Failed ingestions | > 1% |
| Avg chunk quality score | < 0.6 |
| Low-quality chunks rejected | > 10% of total (investigate parser) |
| Embedding model mismatch detected | Any → Sev-1 |

### Dashboard 5: Security
| Metric | Alert Threshold |
|---|---|
| Cross-tenant filter bypass attempts | Any → **Sev-1 page** |
| ACL policy violation (post-filter access) | Any → **Sev-1 page** |
| Audit log gap (response without log entry) | Any → **Sev-1 page** |
| Prompt injection pattern detected | > 0/day → investigate |
| PII detected in LLM output | Any → **Sev-1 page** |

### Logging — Required Per-Request Fields
Every request must produce one log line with:
```json
{
  "response_id": "uuid",
  "timestamp": "ISO-8601",
  "user_id": "...",
  "tenant_id": "...",
  "query_hash": "sha256(query)",
  "filters_applied": {"tenant_id": "...", "access_level": "..."},
  "chunks_used": ["chunk_id_1", "chunk_id_2"],
  "retriever_scores": [0.92, 0.87],
  "reranker_scores": [0.95, 0.83],
  "model": "gemini-1.5-pro",
  "prompt_version": "v4",
  "latency_ms": {"retrieval": 120, "rerank": 45, "generation": 890},
  "abstained": false,
  "cost_usd": 0.018
}
```

---

## 4. Latency Budget (§36)

Target p95 latency per stage for a 2s end-to-end SLA:

| Stage | Target p95 |
|---|---|
| Query embedding | 50ms |
| ANN retrieval (vector DB) | 100–200ms |
| BM25 retrieval | 30–80ms |
| RRF fusion | < 5ms |
| Reranker (cross-encoder) | 100–250ms |
| Context packing | < 10ms |
| LLM generation (streaming) | 500ms to first token |
| **Total p95** | **< 2s** |

If you're over budget: add reranker caching, reduce candidate pool size, or move to a faster cross-encoder.

---

## 5. Environment-Aware Reranker Configuration (§2)

Use a lighter reranker locally (no Vertex AI auth overhead) and the full production reranker in staging/prod. Switching via environment variable avoids hardcoded model names in code.

### Reranker by Environment

| Environment | Provider | Model | Why |
|---|---|---|---|
| **Local / Docker** | Gemini-as-reranker | `gemini-2.5-flash` | Works with Google AI Studio key; no GCP project required |
| **Staging** | Vertex AI Ranking API | `semantic-ranker-default-004` | Closer to production quality; tests auth path |
| **Production** | Vertex AI Ranking API | `semantic-ranker-default-004` | Lowest latency, production-grade auth and monitoring |

### `.env.example`
```env
# Environment: local | staging | production
APP_ENV=local

# Reranker provider: gemini_llm | vertex_ai_ranking
# local → gemini_llm
# staging/production → vertex_ai_ranking
RERANKER_PROVIDER=gemini_llm

# Local Gemini reranker (Google AI Studio key)
GEMINI_API_KEY=your_google_ai_studio_api_key
RERANKER_MODEL=gemini-2.5-flash

# Staging / Production — Vertex AI Ranking API
VERTEX_PROJECT_ID=your-gcp-project-id
VERTEX_LOCATION=global
VERTEX_RANKING_MODEL=semantic-ranker-default-004
```

### Python Router Pattern
```python
import os

def get_reranker():
    provider = os.environ.get("RERANKER_PROVIDER", "gemini_llm")
    if provider == "vertex_ai_ranking":
        return VertexAIRankingReranker(
            project_id=os.environ["VERTEX_PROJECT_ID"],
            location=os.environ["VERTEX_LOCATION"],
            model=os.environ["VERTEX_RANKING_MODEL"],
        )
    # Default: Gemini-as-reranker (local dev)
    return GeminiReranker(
        api_key=os.environ["GEMINI_API_KEY"],
        model=os.environ.get("RERANKER_MODEL", "gemini-2.5-flash"),
    )

# Usage — same interface regardless of environment
reranker = get_reranker()
ranked = await reranker.rerank(query=query, documents=candidates, top_n=10)
```

### CI / CD Note
- Local: `.env.local` with `RERANKER_PROVIDER=gemini_llm`
- Staging: Secret Manager or CI env vars with `RERANKER_PROVIDER=vertex_ai_ranking`
- Production: Workload Identity Federation — no API key in env; `VERTEX_PROJECT_ID` only

---

## 6. Recommended Starting Defaults (§10)

Concrete numbers to start with before golden-set tuning. These are starting points — measure and adjust.

### Retrieval Pipeline Defaults

| Stage | Default | Notes |
|---|---|---|
| ANN candidate retrieval (`top_k`) | **80** | Dense + BM25 top-40 each → RRF → 80 deduplicated candidates |
| Post-dedup candidates into reranker | **40–60** | After MMR/dedup; reranking 80 without dedup wastes cost |
| Final context chunks (after reranking) | **5–10** | Send to generation; lower = cheaper + less distraction |

**Per-request budgets, enforced in code** (not by prompt): max derived sub-queries (3–6), max rerank candidates, max rerank calls, and one hard deadline for the whole retrieval stage. On breach, return the partial result with a degradation flag and log it — never an unbounded fan-out.

### Chunk Size Defaults by Document Density

| Document Type | Chunk Size | Why |
|---|---|---|
| General knowledge / prose | 500–800 tokens | Enough context; stays within embedding model limits |
| Structured / procedure docs (SOPs, guides) | 300–600 tokens | Denser information per sentence; smaller chunks = more precise retrieval |
| Tables | Full table or row-groups | See `table-chunking-strategy.md` — never split mid-row |
| Event-based records (support messages, logs) | One event per chunk | Natural unit; splitting one event across chunks loses context |

### Query Strategy Defaults

```
Always rewrite conversational follow-up queries (resolve pronouns, standalone query)
Apply domain synonym expansion when corpus has known vocabulary gaps
Split multi-part questions before retrieval
Use HyDE only as a fallback for low-confidence retrieval — never on exact facts or legal/contractual content
```

**Tuning discipline:** establish a golden set of ≥50 queries first, measure Recall@5 per query type, then adjust `top_k`, chunk size, and overlap based on where recall falls short — not before.

---

## 9. Corpus Hygiene at Scale

At small corpus size (< 10k docs), duplicate and stale documents are a nuisance. At large corpus size (> 100k docs), they become a retrieval accuracy problem — they crowd the embedding space with near-identical vectors, causing the retriever to return plausible-but-wrong results instead of the canonical answer.

### Hard-Negative Pollution Signal

When the same chunk appears in the top-K for many semantically different queries, it is likely a near-duplicate or an overly generic chunk that has become a hard negative attractor. Diagnose with:

```python
# Find chunks retrieved too frequently across diverse queries
chunk_retrieval_counts = Counter(
    chunk_id for result in eval_run for chunk_id in result.retrieved_doc_ids
)
# Chunks appearing in > 20% of queries are candidates for review
hot_chunks = [cid for cid, count in chunk_retrieval_counts.items()
              if count / len(eval_run) > 0.20]
```

Investigate hot chunks: are they duplicates? generic boilerplate? navigation text? Remove or de-weight them.

### Corpus Hygiene Checklist

| Problem | Detection | Fix |
|---|---|---|
| **Near-duplicate documents** | Canonical dedup rule: exact dup = same `content_hash`; near dup = MinHash Jaccard ≥ 0.9 on shingles OR embedding cosine ≥ 0.95 across different doc IDs — never compare a Jaccard score to a cosine threshold; tune on a labelled sample | Keep canonical version; soft-delete or exclude duplicates from index |
| **Draft + final versions both indexed** | `doc_version` field present but no `superseded_at` filter applied | Apply `superseded_at IS NULL` filter; see `versioning-and-freshness.md §3` |
| **Outdated policy docs** | `effective_to` date in the past but `is_active = true` | Run periodic sweep: mark expired docs inactive |
| **Copied content across folders** | Same `content_hash` under different `source_uri` | Dedup on `content_hash` at ingestion; keep highest-authority source |
| **Generic boilerplate chunks** | High retrieval frequency across unrelated queries | Tag with `is_boilerplate = true`; exclude from retrieval or downweight in reranker |

### Source-of-Truth Tagging

For corpora with authoritative and non-authoritative versions of the same content, add an `is_canonical` field to chunk metadata:

```json
{
  "is_canonical": true,
  "authority_tier": 1,
  "supersedes": ["doc-id-v1", "doc-id-v2"]
}
```

Use `authority_tier` as a reranker signal — boost canonical sources over draft/copied versions when rerank scores are close. See `context-packing-patterns.md §8` for authority boost at packing time.

### When to Run Hygiene

- After any bulk ingestion of a new document corpus
- When Recall@K drops in a specific corpus segment (see `rag-evaluator/SKILL.md` Eval Breakdown)
- On a scheduled basis for corpora with high update frequency (weekly for policy docs)
