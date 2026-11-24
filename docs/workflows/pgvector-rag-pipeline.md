# pgvector RAG Pipeline

> **When to use**: Building a semantic search or RAG pipeline backed by PostgreSQL + pgvector
> **Time estimate**: 2–4 hours for initial pipeline; 1 hour per additional retrieval stage
> **Prerequisites**: PostgreSQL database accessible, embedding model selected, pgvector extension installed

## Overview

End-to-end pgvector RAG pipeline: schema design → pipeline scaffold → index tuning → review. Covers the IVFFlat vs HNSW decision, embedding model pinning, null guards, reranking, and production-ready error handling.

---

## Phases

### Phase 1 — Load Skill and Make Key Decisions

**Action**: Load `vector-database` skill (`skills/vector-database/SKILL.md`)
**Iron Law** (from `skills/vector-database/SKILL.md:15-18`): Pin dimensions at model selection — changing models later requires full re-embedding

**pgvector vs Weaviate decision** (from `skills/vector-database/SKILL.md:37-42`):

| Choose pgvector when | Choose Weaviate when |
|---------------------|---------------------|
| Data already in PostgreSQL | Need built-in vectorizer (no separate embedding service) |
| Simple single-stage retrieval | Need multi-modal search |
| Full SQL control required | Need managed vector DB with minimal ops |
| <1M vectors with predictable growth | Need native generative RAG API |

**MCP**: Context7 for current pgvector syntax (pgvector version matters)

---

### Phase 2 — Schema Design

**Command**: `/design-vector-schema [table-name] [embedding-model] [row-count-estimate]`
**Source**: `commands/design-vector-schema.md`
**Skill**: `vector-database` with pgvector-patterns reference
**Agent**: `pgvector-schema-reviewer` (after generation)

**7-step process** (from `commands/design-vector-schema.md`):
1. Load vector-database skill
2. Gather requirements: table name, embedding model, row count, distance metric, format
3. Select index type based on row count:

| Row count | Index type | Reason |
|-----------|-----------|--------|
| < 100K | IVFFlat | Lower build time, sufficient recall |
| >= 100K | HNSW | Better recall, faster queries at scale |

4. Generate migration with:
   - `vector(<dim>)` column with correct dimension for the model
   - `embedding_model` metadata column (records which model generated embeddings)
   - NULL guard (partial index: `WHERE embedding IS NOT NULL`)
   - `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
   - Index with correct operator class for distance metric

5. Run `pgvector-schema-reviewer` agent
6. Save file to migration directory
7. Report generated files and findings

**Distance metric → operator class mapping**:

| Metric | Operator | IVFFlat ops class | HNSW ops class |
|--------|----------|-------------------|----------------|
| Cosine | `<=>` | `vector_cosine_ops` | `vector_cosine_ops` |
| L2 | `<->` | `vector_l2_ops` | `vector_l2_ops` |
| Inner product | `<#>` | `vector_ip_ops` | `vector_ip_ops` |

**Critical**: Operator in queries MUST match operator class in index — mismatch = full table scan

**Produces**: Reversible Flyway/Alembic migration with correct index, metadata column, null guard
**Gate**: `pgvector-schema-reviewer` agent passes; migration is reversible

---

### Phase 3 — Pipeline Scaffold

**Command**: `/scaffold-rag-pipeline [pipeline-name] pgvector [use-case]`
**Source**: `commands/scaffold-rag-pipeline.md`
**Skill**: `vector-database` with RAG pipeline reference
**Agent**: `rag-implementation-reviewer` (after generation)

**Generated files** (from `commands/scaffold-rag-pipeline.md`):
```
src/<pipeline-name>/
├── embedding_service.py    # Calls embedding API, batches requests
├── chunking.py             # Text splitting strategy
├── retriever.py            # pgvector query with filters
├── reranker.py             # Cross-encoder reranking (optional)
├── pipeline.py             # Orchestrates all stages
└── tests/
    ├── test_embedding.py
    ├── test_retriever.py
    └── test_pipeline.py
```

**Chunking strategies** (from skill reference):

| Strategy | When to use |
|----------|------------|
| Fixed size (512 tokens) | General text, no structure |
| Sentence-based | Prose, articles |
| Recursive character | Mixed content |
| Semantic | High-value content, needs coherence |
| Document-aware | PDFs, markdown with headers |

**Reranking**: Always include for production — retrieval recall alone is insufficient
**Embedding API**: Always batch requests — never embed one at a time in a loop

**Produces**: Complete RAG pipeline with all components
**Gate**: `rag-implementation-reviewer` agent passes; tests pass

---

### Phase 4 — Index Tuning

**Command**: `/tune-vector-index [table-name] [row-count] [target-latency-ms] [current-index-type]`
**Source**: `commands/tune-vector-index.md`
**9-step process**:
1. Load vector-database skill
2. Gather requirements
3. Query current index state
4. Select and tune based on row count and latency target

**HNSW parameters** (from skill):

| Parameter | Default | Tuning guidance |
|-----------|---------|----------------|
| `m` | 16 | Higher = better recall, more memory. Range: 4–64 |
| `ef_construction` | 64 | Higher = better recall at build time. Range: 32–400 |
| `ef_search` | 40 | Higher = better recall at query time. Set with `SET LOCAL` per transaction (a plain `SET` leaks to the next request on a pooled connection) |

**IVFFlat parameters**:

| Parameter | Guidance |
|-----------|---------|
| `lists` | `sqrt(row_count)` for balanced perf/recall |
| `probes` | start near `sqrt(lists)`; increase for recall |

**Filtered queries** (tenant, category): on pgvector ≥ 0.8.0 add `SET LOCAL hnsw.iterative_scan = relaxed_order` (IVFFlat: `ivfflat.iterative_scan = relaxed_order`). Verified on PostgreSQL 18.7 + pgvector 0.8.7: a 1%-selective filter returned 0–1 of 10 rows without it and 10 of 10 with it. See `vector-database/references/ann-vs-knn.md` §Filtered ANN.

5. Generate SQL: `DROP INDEX CONCURRENTLY` + `CREATE INDEX CONCURRENTLY` (non-blocking)
6. Generate `EXPLAIN ANALYZE` template
7. Generate query-time settings inside the query transaction (`SET LOCAL ivfflat.probes = N` / `SET LOCAL hnsw.ef_search = N` / `SET LOCAL hnsw.iterative_scan = relaxed_order`)
8. Provide monitoring queries (index size, query times)
9. Report recommendation

**Produces**: Index tuning recommendation with SQL and monitoring queries
**Gate**: EXPLAIN ANALYZE shows index scan; p95 query latency meets target

---

### Phase 5 — Pipeline Review

**Agent 1**: `pgvector-schema-reviewer`
- Vibe: *"Operator-index mismatch is a silent full-table scan — caught here, not in prod"*
- Checks: operator-index alignment, dimension vs model match, null guard presence, `embedding_model` metadata column, migration reversibility

**Agent 2**: `rag-implementation-reviewer`
- Checks: embedding model pinned (not `latest`), chunking strategy justified, hybrid vs pure-vector documented, reranking present, null guards on retrieval results, error handling on embedding API calls

**Gate**: Both agents pass; zero CRITICAL findings

---

## Quick Reference

| Phase | Command/Agent | Produces | Gate |
|-------|--------------|----------|------|
| 1 — Decide | Load `vector-database` skill | Key decisions made | pgvector vs Weaviate decided |
| 2 — Schema | `/design-vector-schema` + `pgvector-schema-reviewer` | Migration file | Agent passes |
| 3 — Pipeline | `/scaffold-rag-pipeline pgvector` + `rag-implementation-reviewer` | Pipeline files | Agent passes + tests pass |
| 4 — Index tuning | `/tune-vector-index` | Tuned index SQL | p95 latency target met |
| 5 — Review | `pgvector-schema-reviewer` + `rag-implementation-reviewer` | Findings | Zero CRITICAL |

---

## Common Pitfalls

- **Operator-index mismatch** — using `<=>` (cosine) query with `vector_l2_ops` index = full table scan; always match
- **No `embedding_model` column** — when you switch models, you can't tell which rows need re-embedding
- **Embedding `latest` model** — OpenAI/Cohere change `latest`; pin to `text-embedding-3-small` not `latest`
- **Embedding one at a time** — always batch; single-item loops are 10–50x slower
- **No null guard** — NULL embeddings cause index issues; partial index `WHERE embedding IS NOT NULL`
- **No reranking** — retrieval recall alone is 60–70%; reranking brings it to 85–90%

## Related Workflows

- [`database-schema-design.md`](database-schema-design.md) — base table design before vector column
- [`weaviate-collection-pipeline.md`](weaviate-collection-pipeline.md) — Weaviate alternative
- [`embedding-model-migration.md`](embedding-model-migration.md) — migrating to a new embedding model
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — plugging the pipeline into a LangGraph agent
