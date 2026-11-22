---
description: Design a Weaviate collection using Python client v4. Captures vectorizer selection, named vectors, multi-tenancy flag, and property definitions → generates Python collection creation code with correct distance metric, connection handling, and batch ingestion helper.
argument-hint: "[collection name] [use case description]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Design Weaviate Collection

Generate production-ready Weaviate Python client v4 collection code.

**Input:** $ARGUMENTS

## Steps

1. **Load the `vector-database` skill** — read `SKILL.md` and `references/weaviate-collection-patterns.md` for templates and anti-patterns.

2. **Gather requirements** — Extract from `$ARGUMENTS` or ask:
   - Collection name (PascalCase)
   - Use case (determines property types and vectorizer choice)
   - Embedding model / vectorizer (from skill model table)
   - Distance metric (cosine default; L2 or dot-product if specified)
   - Multi-tenancy: required? (set now — CANNOT change post-creation)
   - Named vectors: multiple embedding spaces needed?
   - Generative RAG: will this collection use `.generate.*` queries?

3. **Generate collection code** including:
   - Correct `weaviate.connect_to_*()` (v4 API, NOT deprecated `weaviate.Client()`)
   - API keys from `os.environ["..."]` — NEVER hardcoded
   - `client.close()` in `finally` block
   - `vector_config=Configure.Vectors.self_provided(...)` (app-side embedding) or `Configure.Vectors.text2vec_<provider>(...)` — NOT the deprecated `vectorizer_config=` / `vector_index_config=` create arguments or `Configure.NamedVectors` (Dep024/025/026 in weaviate-client 4.24.1)
   - `Configure.multi_tenancy(enabled=True/False)` — explicitly declared; if `auto_tenant_creation=True`, also generate the shared `tenants.exists()` guard for read/delete paths
   - `Configure.VectorIndex.hnsw(distance_metric=...)` inside `vector_config` — explicit, not default
   - Create-only settings decided now: `inverted_index_config=Configure.inverted_index(index_null_state=True)` if any query filters on null (e.g. `superseded_at`), tokenization per property
   - `embedding_model` property on every object
   - All properties with explicit `DataType`
   - `generate_uuid5(stable_id)` for batch inserts (idempotent)
   - `collection.batch.failed_objects` read after each batch context, logged by id/count, failing the run above a failure-rate threshold

4. **Generate helper functions**:
   - `create_collection_if_not_exists()` — checks existence before creating
   - `batch_insert(items)` — with error checking
   - `scoped(tenant_id)` helper (multi-tenant collections) — every call goes through `.with_tenant(tenant_id)`, tenant from the auth context
   - Query example matching the use case. Self-provided vectors: `near_vector` or `hybrid(query=..., vector=...)` — `hybrid` without `vector=` silently degrades to keyword-only; fusion enum `HybridFusion.RANKED` / `RELATIVE_SCORE`

5. **Run `weaviate-schema-reviewer` agent** on the generated code before presenting.

6. **Save file** to appropriate location (infer from project structure or use `src/vector/` as default).

7. **Report** generated files and any reviewer findings.

$ARGUMENTS
