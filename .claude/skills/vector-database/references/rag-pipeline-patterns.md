# RAG Pipeline Patterns

Framework-neutral core first (plain Python + SQL), optional extensions after. Snippets marked *verified* were executed this cycle against PostgreSQL 16 + pgvector 0.6.2 or with scripted fakes — no live model or Weaviate server.

## Table of Contents
1. [Chunking Strategies](#chunking-strategies)
2. [Embedding Pipeline](#embedding-pipeline)
3. [pgvector Retrieval](#pgvector-retrieval)
4. [Weaviate Retrieval](#weaviate-retrieval)
5. [Reranking](#reranking)
6. [LangChain Integration](#langchain-integration)
7. [Two-Stage Retrieval](#two-stage-retrieval)
8. [Model-Specific Embedding Patterns](#model-specific-embedding-patterns)
9. [Server-Side Vectorizer vs Pre-Computed Vectors](#server-side-vectorizer-vs-pre-computed-vectors-path-a-vs-path-b)
10. [Retrieval Stack and Eval Gates](#retrieval-stack-and-eval-gates)

---

## Chunking Strategies

Choose chunking before writing any pipeline code. Canonical overlap and cap rule: `rag-architect/SKILL.md` — size-based splitters ~10–15% overlap; natural boundaries may use 0 with parent/neighbour expansion; **final chunk ≤ reranker input limit minus the longest query** (often 512 tokens total — check your reranker), unit-tested over the largest fixture document.

| Strategy | Chunk Size | Overlap | Use When |
|----------|-----------|---------|---------|
| Fixed token | 400–512 tokens | 10–15% | General text, uniform docs |
| Sentence | 3-5 sentences | 1 sentence | Conversational text, Q&A |
| Paragraph / section | 1 paragraph or section | 0 (+ neighbour expansion) | Structured docs, reports |
| Semantic | Variable | N/A | When chunk coherence matters most |
| Recursive | ~1500–2000 chars → split at `\n\n` → `\n` → ` ` | 10–15% | Unstructured text (default for most RAG) |

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter   # LangChain v1 package

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1800,            # characters; derive from the reranker token cap, then test
    chunk_overlap=220,          # ~12%
    separators=["\n\n", "\n", ". ", " ", ""],
)
chunks = splitter.split_text(document_text)
assert max(count_tokens(c) for c in chunks) <= RERANK_MAX_TOKENS - MAX_QUERY_TOKENS
```

---

## Embedding Pipeline

One chokepoint owns model, dims and task type (from config), batches, asserts every vector's length, and retries only transient errors with capped backoff. Raw provider embed calls elsewhere are a review finding. *Verified with a scripted provider: batching, task type pass-through, wrong-dimension → raise, transient retried then raised, auth error not retried (4 pytest cases; `ruff`, `mypy --strict` clean).*

```python
TaskType = Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]

class TransientEmbeddingError(Exception):
    """429 / 503 / timeout — map provider exceptions to this in the adapter."""

class EmbeddingService:
    def __init__(self, call: ProviderCall, model: str, dims: int,
                 batch_size: int = 100, max_attempts: int = 4) -> None:
        self._call, self.model, self.dims = call, model, dims          # from settings, not literals
        self._batch_size, self._max_attempts = batch_size, max_attempts

    async def _call_with_retry(self, texts: Sequence[str], task: TaskType) -> list[list[float]]:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._call(texts, self.model, self.dims, task)
            except TransientEmbeddingError:
                if attempt == self._max_attempts:
                    raise                                            # bounded; never return []
                await asyncio.sleep(min(8.0, 0.5 * 2 ** (attempt - 1)) * (0.5 + random.random()))
        raise AssertionError("unreachable")

    async def embed(self, texts: Sequence[str], task: TaskType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            out = await self._call_with_retry(batch, task)
            if len(out) != len(batch) or any(len(v) != self.dims for v in out):
                raise EmbeddingDimensionError(f"expected {len(batch)} x {self.dims}")   # never store
            vectors.extend(out)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed([text], "RETRIEVAL_QUERY"))[0]
```

- The adapter maps the provider's query/document modes (`task_type`, `input_type`, BGE/E5 prefixes — see §8) onto `TaskType`; store the task type and model on every vector.
- Ingest isolates per-chunk failures: count, log ids, and fail the run below a success-rate floor. An unreachable vector store is fatal. Log errors with `log_exception(logger, event, exc, **ids)` (`deployment-ci-cd/reference/python-observability.md` §2).

---

## pgvector Retrieval

asyncpg needs the vector codec registered on every connection. Query-time knobs are transaction-scoped. *Verified: returns only the caller's tenant and the active model; `ef_search` is back to 40 after the transaction.*

```python
import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

pool = await asyncpg.create_pool(dsn, init=register_vector)

SEARCH_SQL = """
SELECT id, title, 1 - (embedding <=> $1) AS similarity
FROM documents
WHERE tenant_id = $2 AND embedding_model = $3 AND is_current AND embedding IS NOT NULL
ORDER BY embedding <=> $1
LIMIT $4
"""

async def search_documents(pool: asyncpg.Pool, query_vec: list[float], ctx: AuthContext,
                           limit: int = 10) -> list[dict[str, object]]:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL hnsw.ef_search = 100")      # never a session-level SET
        rows = await conn.fetch(SEARCH_SQL, np.asarray(query_vec, dtype=np.float32),
                                ctx.tenant_id, settings.embedding_model, limit)
    return [dict(r) for r in rows]
```

Dynamic filters: build the `WHERE` from a fixed allowlist of column names and bind every value as a parameter — never interpolate request values. Selective filters can return fewer than `limit` rows on HNSW/IVFFlat: see `ann-vs-knn.md` §Filtered ANN. SQLAlchemy version: `vector-database/SKILL.md`.

### Hybrid in SQL — vector + full-text fused with RRF

Both legs carry the same scope filters. *Verified on a fixture: an identifier query (`INV-20931`) is found by the full-text leg, a zero-overlap paraphrase by the vector leg; rows from another tenant and an old embedding model never appear.*

```sql
-- tsv: tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED, with a GIN index
WITH vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> $1) AS rnk
  FROM doc_chunks WHERE tenant_id = $2 AND embedding_model = $3 AND is_current
  ORDER BY embedding <=> $1 LIMIT $5
), fts AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS rnk
  FROM doc_chunks, websearch_to_tsquery('english', $4) q
  WHERE tenant_id = $2 AND embedding_model = $3 AND is_current AND tsv @@ q
  ORDER BY ts_rank_cd(tsv, q) DESC LIMIT $5
)
SELECT id, sum(1.0 / (60 + rnk)) AS rrf          -- RRF, k = 60
FROM (SELECT * FROM vec UNION ALL SELECT * FROM fts) legs
GROUP BY id ORDER BY rrf DESC LIMIT $5;
```

---

## Weaviate Retrieval

```python
from weaviate.classes.query import Filter, HybridFusion, MetadataQuery

def retrieve_chunks(client: weaviate.WeaviateClient, embedder: EmbeddingService,
                    query: str, query_vec: list[float], ctx: AuthContext,
                    alpha: float = 0.5, limit: int = 40) -> list[dict[str, object]]:
    """Hybrid search on a multi-tenant, self-provided-vector collection."""
    chunks = client.collections.use("DocChunk").with_tenant(ctx.tenant_id)   # scope from auth, never args
    result = chunks.query.hybrid(
        query=query,
        vector=query_vec,                     # REQUIRED: no server vectorizer → without it, keyword-only
        alpha=alpha,                          # tune per query class on the golden set
        fusion_type=HybridFusion.RELATIVE_SCORE,
        filters=Filter.by_property("embedding_model").equal(embedder.model)
                & Filter.by_property("allowed_groups").contains_any(list(ctx.group_ids)),
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )
    return [{"id": str(o.uuid), "text": o.properties["text"], "score": o.metadata.score}
            for o in result.objects]
```

If the query embedding fails, a BM25-only fallback is allowed only as a **signalled** degradation: log it and pass `retrieval_mode="keyword_fallback"` to the generator so it lowers confidence. Collection creation and the lazy-tenant guard: `weaviate-collection-patterns.md`.

---

## Reranking

Initial retrieval optimizes recall; reranking optimizes precision. Rules:
- Rerank against the **original** user query, never a rewritten/HyDE/sub-query text.
- Over-fetch 3–10× the final count; respect the reranker's max input (chunk + query) — longer chunks are truncated and scored on their head only.
- Reranking is **eval-gated**: keep it when the golden set shows a gain on your corpus; otherwise document why it is omitted.

```python
async def retrieve_and_rerank(query: str, ctx: AuthContext, top_k_retrieve: int = 40,
                              top_k_final: int = 5) -> list[Chunk]:
    query_vec = await embedder.embed_query(query)
    candidates = await secure_retrieve(query, query_vec, ctx, limit=top_k_retrieve)
    if not candidates:
        return []                                          # caller logs + abstains (no_retrieval)
    ranked = await reranker.rerank(query=query, documents=[c.text for c in candidates],
                                   top_n=top_k_final)      # provider SDK or local cross-encoder
    return [candidates[r.index] for r in ranked]
```
Provider rerank APIs (Cohere, Voyage, Vertex AI Ranking) and local cross-encoders (BGE reranker) all fit this shape; check the provider's current model ids and token limits before pinning.

---

## LangChain Integration

Optional. Use `langchain-postgres` (`from langchain_postgres import PGEngine, PGVectorStore`) — not the older `langchain_community` PGVector. Match the distance strategy to the index ops class, keep the tenant/permission filter in the store call, and route embeddings through the same chokepoint. Full LangGraph RAG patterns: `agentic-ai-dev` skill.

---

## Two-Stage Retrieval

Pattern: pgvector (structured DB data) → Weaviate (external docs) → merge → rerank.

- Retrieve `N×3` candidates from each stage, rerank down to `N` final
- Both stages go through the scoped chokepoint with the same `ctx`
- Tag each result with `"source": "internal"` or `"source": "external"` before merging; dedupe by stable chunk id
- Run one rerank across the merged list — not separately per stage
- Each stage fails independently and visibly (log + degradation flag), never as a silent empty list
- Log `pg_candidates` and `weaviate_candidates` counts for observability

Generate with `/scaffold-rag-pipeline --storage=both`.

---

## Model-Specific Embedding Patterns

Query/document asymmetry is part of the model contract. Mixing modes depresses recall with no error.

| Model family | Query | Document |
|---|---|---|
| Gemini / Vertex embeddings | `task_type="RETRIEVAL_QUERY"` | `task_type="RETRIEVAL_DOCUMENT"` |
| Cohere, Voyage | `input_type="search_query"` / `"query"` | `"search_document"` / `"document"` |
| BGE (`bge-large-en-v1.5`) | prefix `"Represent this sentence for searching relevant passages: "` | no prefix |
| E5 (`multilingual-e5-large`) | prefix `"query: "` | prefix `"passage: "` |
| OpenAI `text-embedding-3-*` | no mode parameter | — |

Check each provider's docs for the current parameter names before pinning.

```python
from sentence_transformers import SentenceTransformer

class BGEAdapter:
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5") -> None:
        self.model = SentenceTransformer(model_name)

    async def __call__(self, texts: Sequence[str], model: str, dims: int,
                       task: TaskType) -> list[list[float]]:
        if task == "RETRIEVAL_QUERY":
            texts = [f"{self.QUERY_PREFIX}{t}" for t in texts]
        vecs = await asyncio.to_thread(self.model.encode, list(texts), normalize_embeddings=True, batch_size=32)
        return vecs.tolist()

embedder = EmbeddingService(BGEAdapter(), model="BAAI/bge-large-en-v1.5", dims=1024)
```

The adapter plugs into the chokepoint above, so the dimension check and logging still apply. In LangGraph, call it from an **async** node (`async def retrieval_node(state): ...`); for Google ADK tool wiring see the `google-adk` skill.

### Reduced dimensions (Matryoshka)

`text-embedding-3-*` accepts `dimensions=`; Gemini embeddings accept `output_dimensionality`. Rules:
- One fixed dimension per index; the column is `vector(<that dim>)`, ≤ 2000 for an HNSW/IVFFlat index.
- If the provider returns un-normalized truncated vectors and you use inner product (`<#>`), L2-normalize them first; cosine (`<=>`) is scale-invariant.
- Measure recall at the reduced dimension against full dimension on your golden set before adopting; provider-published quality deltas are not your corpus.

---

## Server-Side Vectorizer vs Pre-Computed Vectors (Path A vs Path B)

| | Path A — Server vectorizer | Path B — Pre-computed (`Configure.Vectors.self_provided()`) |
|---|---|---|
| **Setup** | Schema declares `Configure.Vectors.text2vec_*`; you write text; the store calls the embedding API | You embed in app code and pass the vector |
| **PII control** | Raw text leaves your service | Redact → embed → store, all in your code |
| **Cost tracking** | Inside the vector DB invoice | Logged once by the chokepoint |
| **Local dev** | Needs the embedding module loaded | Works with vanilla Weaviate |
| **Model migration** | Re-config the store | Update config, re-embed through the chokepoint |
| **Multi-store RAG** | Each store owns its own pipeline | One embed function feeds all stores |
| **Query side** | `near_text` / `hybrid(query=...)` work directly | Always pass the query vector (`near_vector`, `hybrid(vector=...)`) |

**Recommendation:** Path B for RAG ingest when you need redaction before embedding, one cost ledger or several stores. Path A is fine for prototypes and single-store corpora without PII. Pinecone, Qdrant and pgvector only support Path B.

```python
from weaviate.classes.config import Configure, DataType, Property

client.collections.create(
    name="PolicyClauses",
    vector_config=Configure.Vectors.self_provided(),
    multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=False),
    properties=[
        Property(name="text", data_type=DataType.TEXT),
        Property(name="embedding_model", data_type=DataType.TEXT),   # version stamp
    ],
)

# Write path: redact → embed → write (tenant from the verified auth context)
redacted = redact_pii(chunk.text)
[vec] = await embedder.embed([redacted], "RETRIEVAL_DOCUMENT")
client.collections.use("PolicyClauses").with_tenant(ctx.tenant_id).data.insert(
    properties={"text": redacted, "embedding_model": embedder.model}, vector=vec)
```

Store choice (pgvector vs Weaviate vs both): `tier-1-tier-2-decision.md`. Choose by query shape — JOIN/geo/ACID filters → pgvector; large unstructured corpus needing native hybrid or many small isolated tenants → dedicated vector DB; both → two-stage. Never dual-write the same rows.

---

## Retrieval Stack and Eval Gates

Starting point for text corpora; each layer stays only if the golden set shows it helps:

1. **Hybrid (BM25 + vector).** Vector search misses exact strings (`$2,400`, `Section 5.3`, SKUs, names); BM25 misses paraphrase. Tune `alpha` per query class on the golden set (`alpha=0` pure BM25, `1` pure vector; 0.5 is a starting point).
2. **Rerank** top 20–50 → top 5 against the original query (see §5).
3. **Contextual chunking** — two different techniques; say which one you use:
   - *Deterministic header* (cheap): prepend `[document title › section path]` to the text that is embedded; keep the stored/cited text verbatim.
   - *LLM-generated chunk context* ([Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)): one LLM call per chunk writes a short situating context before embedding/BM25 indexing. Anthropic reports a large reduction in retrieval failures on its benchmarks; measure on yours, and budget the per-chunk LLM cost and re-ingest cost.

```python
header = f"[{doc.title} › {' › '.join(section.path)}]"
[vec] = await embedder.embed([f"{header}\n{redacted_body}"], "RETRIEVAL_DOCUMENT")
store_chunk(text=redacted_body, context_header=header, vector=vec)   # cite the body, verbatim
```

### Eval gates for retrieval (before production)

Golden set `tests/golden/rag/<corpus>/` with ≥ 30 cases (≥ 50 recommended): `query`, `expected_chunk_ids`, `expected_section`, `expected_answer_contains`, plus paraphrase cases with zero keyword overlap and identifier cases.

| Metric | Example threshold | Definition |
|---|---|---|
| `Recall@5` | ≥ 0.85 | relevant chunks in top 5 ÷ all relevant chunks for the query (coverage) |
| `Hit@5` | ≥ 0.95 | 1 if ≥ 1 relevant chunk is in top 5, else 0 — not the same as Recall@5 |
| `MRR@5` | ≥ 0.75 | mean of 1 / rank of the first relevant chunk (0 if none in top 5) |
| Faithfulness / groundedness | ≥ 0.9 (higher = better) | share of answer claims supported by the cited chunks (judge-based; calibrate) |

Thresholds name the exact metric; formulas and worked examples live in the `llm-evaluation` skill (canonical), and the gate values your project enforces live in one place, `eval-guide/reference/per-agent-thresholds.md` (these example values match it). If ADK's `hallucinations_v1` is used, it is a 0–1 score where **higher is better** and the threshold is a minimum — never gate it as `≤ 0.05`. Gate per query class/slice, not only on the aggregate. If a threshold fails, the fix is chosen by the failing slice (alpha, reranking, chunking, contextual headers), not by adding layers blindly.

---

## Cross-References

- `rag-security-reviewer/SKILL.md` §1–2 — canonical permission-aware / tenant-scoped retrieval
- `ann-vs-knn.md` §Filtered ANN — pgvector filter-after-index recall loss and fixes
- `rag-ingest-checklist.md` — ingestion PR checklist and post-ingest live verification
- `rag-architect/references/rag-response-contract.md` §10 — runtime citation validation
- `google-adk` skill — ADK state propagation for multi-agent ingest pipelines
