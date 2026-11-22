---
name: vector-database
description: "Use for all vector database work — pgvector schema design, Weaviate collection creation, RAG pipeline scaffolding, embedding model selection, index tuning (HNSW vs IVFFlat), and embedding model migration. Triggers on: 'vector search', 'pgvector', 'weaviate', 'embedding', 'RAG pipeline', 'semantic search', 'hybrid search', 'nearest neighbor', 'vector index', 're-embedding', 'ANN index'. Use whenever vectors, embeddings, or similarity search are involved, even if not explicitly named."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: pgvector, weaviate, embedding, vector search, RAG pipeline, semantic search, hybrid search, vector index, re-embedding, ANN index, HNSW, IVFFlat, quantization, INT8, product quantization, binary quantization, HNSW benchmark, vector memory, index benchmarking
  related-skills: weaviate, weaviate-cookbooks, agentic-ai-dev, database-schema-designer
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

# Vector Database Skill

## Iron Law

**Pin dimensions at model selection.** The embedding dimension must match the model exactly and is set once — changing models requires a full re-embedding migration. Store `embedding_model varchar(100)` alongside every vector column, set by the writer (never a column `DEFAULT`), and filter every query on the active model.

---

## Embedding Model Selection

Choose model before writing any schema. Dimension determines index shape. Model names and dims change — confirm on the provider's model page before pinning.

| Model (example, verify) | Dims | Notes |
|-------|------|-------|
| `text-embedding-3-small` (OpenAI) | 1536 | Good cost/quality default |
| `text-embedding-3-large` (OpenAI) | 3072 | ⚠️ Above pgvector's 2000-dim index limit — request reduced `dimensions`, or use a `halfvec` expression index (≤ 4000 dims, pgvector ≥ 0.7) |
| `embed-english-v3.0` (Cohere) | 1024 | Uses `input_type` query/document modes |
| `voyage-3-large` (Voyage AI) | 1024 | Uses `input_type` query/document modes |
| `nomic-embed-text` (local) | 768 | On-prem, no API call; uses task prefixes |

**Rules:**
- Once a dimension is written into schema, it cannot change without `/migrate-embedding-model`.
- pgvector HNSW and IVFFlat indexes on `vector` support at most **2000 dims** (verified: `column cannot have more than 2000 dimensions for hnsw index` on a 3072-dim column). Decide reduced dims or `halfvec` at model selection.
- Reduced (Matryoshka) dimensions: one fixed dim per index; L2-normalize truncated vectors if you use inner product; measure recall against full dims before adopting.
- Use the model's query/document asymmetry (task type, `input_type`, BGE/E5 prefixes) and record it per vector. One embedding chokepoint owns model, dims, task type, a `len(vector) == DIMS` assertion and bounded retry of transient errors.

---

## pgvector

### When to Use
- Data lives in PostgreSQL (documents, orders, support cases, account records)
- You need vector search + relational JOINs in a single query
- Filtering on structured columns (region, category, rating) alongside semantic search

### Vector Column Declaration

```sql
-- ALWAYS enable extension in migration up
CREATE EXTENSION IF NOT EXISTS vector;

-- Column: dimension must match model exactly
ALTER TABLE documents ADD COLUMN embedding vector(1536);
ALTER TABLE documents ADD COLUMN embedding_model varchar(100);   -- set by the writer; no DEFAULT
ALTER TABLE documents ADD CONSTRAINT documents_embedding_model_stamped
    CHECK (embedding IS NULL OR embedding_model IS NOT NULL);
```

### Distance Operators

| Operator | Distance Type | Index ops class | Notes |
|----------|--------------|-----------------|-------|
| `<->` | L2 (Euclidean) | `vector_l2_ops` | Works on any vectors; normalization not required |
| `<#>` | Negative inner product | `vector_ip_ops` | Equals cosine ranking only for unit-length vectors |
| `<=>` | Cosine | `vector_cosine_ops` | Works unnormalized; zero vectors are not indexed |

**Critical:** the query operator MUST match the index ops class. Mismatch → the index is not used and the planner falls back to a sequential scan (verified with EXPLAIN: `<->` against a `vector_cosine_ops` index → Seq Scan). NULL vectors are not indexed.

### Index Selection

| | HNSW | IVFFlat |
|--|------|---------|
| **Build** | Slower, more memory; can be built on an empty table | Fast; build AFTER data is loaded (centroids come from existing rows) |
| **Query recall** | Higher at the same speed | Tunable via `ivfflat.probes` |
| **Use when** | Production default | Fast builds, memory-constrained, mostly-static data |
| **Params** | `m`, `ef_construction`; query `hnsw.ef_search` (default 40) | `lists` = rows/1000 up to 1M rows, `sqrt(rows)` above; query `probes` ≈ `sqrt(lists)` |
| **After big data shifts** | No rebuild needed | `REINDEX INDEX CONCURRENTLY` — `ANALYZE` only refreshes planner stats, it does not re-cluster lists |

```sql
-- HNSW (production default); CONCURRENTLY must run outside a transaction block
CREATE INDEX CONCURRENTLY documents_embedding_hnsw ON documents
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- IVFFlat: after the data load; 250k rows → lists = 250
CREATE INDEX CONCURRENTLY documents_embedding_ivf ON documents
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 250);
```

### Query Pattern — scoped, active model, transaction-local knobs

```sql
BEGIN;
SET LOCAL hnsw.ef_search = 100;          -- SET LOCAL: a plain SET leaks to the next request on a pooled connection
SELECT d.id, d.title, 1 - (d.embedding <=> $1::vector) AS similarity
FROM documents d
WHERE d.tenant_id = $2                   -- from the verified auth context
  AND d.embedding_model = $3             -- active model only; never compare across models
  AND d.is_current
  AND d.embedding IS NOT NULL
ORDER BY d.embedding <=> $1::vector
LIMIT 10;
COMMIT;
```

**Filtered ANN returns fewer rows than `LIMIT`.** pgvector applies `WHERE` after the index produces its candidates, so a selective filter (small tenant, rare category) can return few rows or none. Reproduced on pgvector 0.6.2 with a 1%-selective tenant filter: HNSW → 0 of 10 rows, `ef_search = 400` → 3–6, exact scan → 10, partial index → 10 for the first 5 calls, then 0 once PostgreSQL switches the prepared statement to a generic plan (fix: `SET LOCAL plan_cache_mode = force_custom_plan`). Fixes, details and the required test: `references/ann-vs-knn.md` §Filtered ANN.

SQLAlchemy + `pgvector-python` (verified on SQLAlchemy 2.0.58 and 2.1.9):
```python
from pgvector.sqlalchemy import Vector

class Chunk(Base):
    __tablename__ = "doc_chunks"
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (Index("ix_doc_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
                            postgresql_with={"m": 16, "ef_construction": 64},
                            postgresql_ops={"embedding": "vector_cosine_ops"}),)

stmt = (select(Chunk.id, Chunk.text)
        .where(Chunk.tenant_id == ctx.tenant_id, Chunk.embedding_model == settings.embedding_model,
               Chunk.is_current.is_(True), Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(query_vec))     # <=> ↔ vector_cosine_ops
        .limit(k))
```
With raw asyncpg, call `pgvector.asyncpg.register_vector(conn)` (e.g. in the pool `init`) before passing vectors as parameters.

For full migration template → see `references/pgvector-migration-template.md`

---

## Weaviate

### When to Use
- Data lives outside PostgreSQL (scraped text, PDFs, docs, external reviews)
- You need native hybrid search (BM25 + vector) with fusion control
- Many small tenants that need structural isolation (one shard per tenant)

### Collection Schema Essentials (client v4 current API)

```python
import os
import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.init import Auth

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=os.environ["WEAVIATE_URL"],
    auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
)

# Multi-tenancy, index_null_state and tokenization are fixed at creation
client.collections.create(
    name="DocChunk",
    vector_config=Configure.Vectors.self_provided(          # you embed in app code (one chokepoint)
        vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE),
    ),
    multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=False),
    properties=[
        Property(name="text", data_type=DataType.TEXT),
        Property(name="doc_id", data_type=DataType.TEXT),
        Property(name="embedding_model", data_type=DataType.TEXT),
    ],
)
```

`vectorizer_config=`, `vector_index_config=` (create arguments) and `Configure.NamedVectors` are deprecated: weaviate-client 4.24.1 emits Dep024/Dep025 when they are passed to `create()`, and the current form above emits none (checked with an unconnected client and `warnings.catch_warnings`). For a server-side vectorizer use `Configure.Vectors.text2vec_<provider>(...)`; for several named vectors pass a list of `Configure.Vectors.*(name=...)`.

### Query Patterns

```python
from weaviate.classes.query import Filter, HybridFusion

docs = client.collections.use("DocChunk").with_tenant(ctx.tenant_id)   # every call on a multi-tenant collection

# Self-provided vectors: there is no server vectorizer, so ALWAYS pass the query vector
qvec = embed_query(q)                    # same model + query task type as the stored vectors
result = docs.query.hybrid(
    query=q,
    vector=qvec,                         # without it the vector leg is empty → keyword-only, no error
    alpha=0.5,                           # 1.0 = pure vector, 0.0 = pure BM25; tune per query class on the golden set
    fusion_type=HybridFusion.RELATIVE_SCORE,
    filters=Filter.by_property("embedding_model").equal(settings.embedding_model),
    limit=40,                            # over-fetch for the reranker
)
result = docs.query.near_vector(near_vector=qvec, limit=10)   # pure vector
```

**Fusion enum** (`weaviate.classes.query.HybridFusion`): `RANKED` (rank-based) and `RELATIVE_SCORE` (score-normalized). `RANKED_FUSION` / `RELATIVE_SCORE_FUSION` do not exist.

For named vectors, tenant lifecycle and the lazy-tenant guard → see `references/weaviate-collection-patterns.md`

---

## Two-Tier Architecture Decision

When building a system with both structured and unstructured data:

| Tier | Store | Use For |
|------|-------|---------|
| 1 | pgvector (managed PostgreSQL) | Data with a DB row — documents, orders, support cases, account records |
| 2 | Weaviate | Data outside the DB — scraped reviews, PDFs in object storage, external docs |

**Rule:** Keep data in the tier where it originates. Don't sync Postgres rows to Weaviate at MVP — async sync lag introduces consistency bugs. Move to Weaviate only when matching against external documents. Never dual-write the same rows to both.

---

## Slash Commands

- `/design-vector-schema` — pgvector migration SQL from model + row count + metric
- `/design-weaviate-collection` — Weaviate Python collection from vectorizer + schema
- `/scaffold-rag-pipeline` — Full RAG pipeline: chunk → embed → store → retrieve → rerank
- `/migrate-embedding-model` — Re-embedding migration plan + reversible SQL
- `/tune-vector-index` — HNSW vs IVFFlat recommendation + tuned params

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `references/pgvector-migration-template.md` | Full migration SQL with up/down, index, metadata column | pgvector schema design |
| `references/weaviate-collection-patterns.md` | Named vectors, multi-tenancy, advanced queries | Weaviate collection design |
| `references/rag-pipeline-patterns.md` | Chunking strategies, retrieval, reranking, LangChain wiring | Building RAG pipelines |
| `references/embedding-migration-guide.md` | Step-by-step model switching procedure | Re-embedding migrations |
| `references/vector-index-tuning-playbook.md` | Quantization strategies, HNSW benchmarking, memory estimation, Qdrant config | Index tuning and performance optimization |
| `references/ann-vs-knn.md` | KNN vs ANN tradeoffs, HNSW/IVFFlat tuning, recall measurement, high-risk scoped verification pattern | Choosing and tuning retrieval index strategy |
| `references/rag-ingest-checklist.md` | Production ingestion checklist: embeddings, chunking, null guards, multi-tenancy | Safe data ingestion into vector stores |
| `references/tier-1-tier-2-decision.md` | Decision framework: pgvector (hot path, SQL joins) vs Weaviate (cold path, pure semantic) | Choosing the right vector store for a use case |

## Documentation Sources

Before generating code, consult these sources for current APIs:

| Source | Tool | Purpose |
|--------|------|---------|
| pgvector | `Context7` MCP (`/pgvector/pgvector`) | Vector operators, index syntax, iterative scans, limits |
| pgvector-python | `Context7` MCP (`/pgvector/pgvector-python`) | SQLAlchemy `Vector` type, asyncpg/psycopg registration |
| Weaviate Python v4 | `weaviate-docs` MCP | Collection API, query patterns, named vectors |
| OpenAI Embeddings | `Context7` MCP (`openai` library) | text-embedding-3-small/large, dimensions, pricing |
| Cohere Embed | `Context7` MCP (`cohere` library) | embed-english-v3.0, batch embedding |

## Post-Code Review

After writing vector database code, dispatch:
- `pgvector-schema-reviewer` — operator/index alignment, dimension match, null guards, reversible migrations
- `weaviate-schema-reviewer` — current v4 create API, `with_tenant` on every call, hybrid `vector=`, multi-tenancy declaration
- `rag-implementation-reviewer` — embedding chokepoint, dimension check, batch embedding, silent retrieval fallback, permission-aware retrieval, citations, erasure (canonical RAG review)
- `postgresql-database-reviewer` — for the broader migration (indexes, constraints, performance)
