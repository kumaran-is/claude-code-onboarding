---
description: Scaffold a full RAG pipeline — chunking → embedding → storage (pgvector or Weaviate) → retrieval → reranking → LangChain or custom Python. Generates production-ready pipeline with pinned model, batch embedding, null guards, error handling, and optional reranker.
argument-hint: "[pipeline name] [storage: pgvector|weaviate|both] [use case description]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold RAG Pipeline

Generate a complete retrieval-augmented generation pipeline.

**Input:** $ARGUMENTS

## Steps

1. **Load the `vector-database` skill** — read `SKILL.md` and `references/rag-pipeline-patterns.md` for templates and anti-patterns.

2. **Gather requirements** — Extract from `$ARGUMENTS` or ask:
   - Pipeline name (snake_case, e.g., `kb_rag`)
   - Vector store: `pgvector`, `weaviate`, or `both` (two-stage)
   - Embedding model (from skill model table)
   - Chunking strategy (recursive / sentence / paragraph / fixed) + chunk size
   - Reranking: provider API / local cross-encoder / none (production "none" needs an eval result)
   - Tenancy and permissions: tenant source (auth context) and ACL fields used in retrieval filters
   - Framework: LangChain integration or custom Python
   - Use case (determines retrieval filters and query patterns)

3. **Generate pipeline files**:

   ### `embedding_service.py`
   - One chokepoint: model, dims and task type from settings (not per-call strings)
   - `EmbeddingService.embed(texts, task)` + `embed_query(text)`; query vs document task modes
   - `len(vector) == DIMS` assertion on every response — raise, never store
   - Retry only transient errors (429/503/timeouts) with capped backoff, then raise; non-transient errors raise immediately
   - Pattern: `references/rag-pipeline-patterns.md` §Embedding Pipeline

   ### `chunking.py`
   - Chunking function with strategy from requirements
   - `langchain_text_splitters.RecursiveCharacterTextSplitter` (or a plain splitter) with overlap per the canonical rule in `rag-architect/SKILL.md`
   - Final chunk capped at the reranker input limit minus the longest query; stable chunk ids
   - Returns `List[{"text": str, "metadata": dict}]`

   ### `{storage}_retriever.py` (pgvector and/or weaviate)
   - One scoped entry `secure_retrieve(query, query_vec, ctx, limit)`: tenant + ACL from `ctx` (auth context), active `embedding_model`, `is_current`, null guard — no optional tenant parameter
   - pgvector: `register_vector` on the pool, `SET LOCAL` query knobs, filtered-ANN mitigation for selective filters; optional SQL hybrid (vector + FTS with RRF)
   - Weaviate: current v4 API, `.with_tenant(ctx.tenant_id)`, `hybrid(..., vector=query_vec)`
   - Structured filters from an allowlist of columns, values bound as parameters
   - `top_k` parameter → retrieves 3–10× final count for reranking room

   ### `reranker.py` (if not "none")
   - Provider rerank wrapper or local cross-encoder; reranks against the ORIGINAL query
   - Accepts merged candidates from both retrieval stages if two-stage

   ### `pipeline.py`
   - Orchestrates: query → embed query → retrieve → rerank → format context
   - Score threshold filter (configurable, calibrated on the golden set)
   - Embed failure → keyword fallback only as a flagged degradation (`retrieval_mode`), logged
   - Per-request budgets: max derived queries, max rerank candidates, one deadline
   - Runtime citation validation hook (`rag-architect/references/rag-response-contract.md` §10) when the pipeline generates answers
   - Logging of retrieval counts and latency (`log_exception` for errors, never `str(e)`)
   - Returns `{"results": [...], "context": str, "metadata": {...}}`

   ### `tests/test_{pipeline_name}.py`
   - Unit test: embedding service raises on wrong dimension; retries transient errors then raises (scripted provider)
   - Unit test: no chunk exceeds the cap; ids are stable across re-ingest
   - Integration test (real PostgreSQL/Weaviate fixture): tenant A never sees tenant B; a ≤ 1%-selective filter returns `LIMIT` rows; old-model rows excluded
   - Golden paraphrase case (zero keyword overlap) hits — catches hybrid without query vector

4. **Run the `rag-implementation-reviewer` agent** on all generated files. Run the generated tests and report the command and output; anything not run is NOT RUN.

5. **Save files** to `src/{pipeline_name}/` or infer from project structure.

6. **Report** generated files, reviewer findings, and how to run the pipeline.

$ARGUMENTS
