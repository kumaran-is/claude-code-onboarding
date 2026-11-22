# Embedding Model Migration

> **When to use**: Migrating from one embedding model to another — changing dimensions, provider, or model version
> **Time estimate**: 2–4 hours for planning; hours to days for re-embedding depending on data volume
> **Prerequisites**: Existing vector database (pgvector or Weaviate) with embeddings; new model selected and validated

## Overview

Safe migration from one embedding model to another using the `/migrate-embedding-model` command. Covers dimension mismatch handling, zero-downtime strategy (dual-write → backfill → cutover), pgvector schema migration, and Weaviate collection recreation. Uses `pgvector-schema-reviewer` and `rag-implementation-reviewer` agents for validation.

---

## Iron Law (from `skills/vector-database/SKILL.md`)

> **PIN DIMENSIONS AT MODEL SELECTION — CHANGING MODELS LATER REQUIRES FULL RE-EMBEDDING**
> Old embeddings are incompatible with a new model — mixing them produces semantically meaningless search results.

---

## Why Model Migrations Are Hard

| Issue | Impact |
|-------|--------|
| Different dimensions | `text-embedding-3-small` = 1536, `text-embedding-ada-002` = 1536, Cohere multilingual = 768 — new column or collection needed |
| Different vector spaces | Cosine similarity between old and new model vectors is meaningless |
| No incremental migration | You cannot partially migrate — mixed embeddings = broken search |
| Re-embedding cost | Large datasets can take hours and significant API cost |

---

## Phases

### Phase 1 — Validate New Model

**Command**: `/migrate-embedding-model [from-model] [to-model]`
**Skill**: `vector-database`

**Before any migration**:
1. Evaluate the new model on your domain's data
2. Run semantic search with both models on the same queries
3. Compare recall quality (not just marketing claims)
4. Check dimension compatibility

**Dimension check**:
```python
import openai

# Test new model dimensions
response = openai.embeddings.create(
    model="text-embedding-3-large",  # New model
    input="test sentence"
)
print(len(response.data[0].embedding))  # 3072 for text-embedding-3-large
```

**Gate**: New model produces better or equivalent search quality on domain test queries.

---

### Phase 2 — pgvector Migration Strategy

**Strategy**: Expand-Contract (zero downtime)

**Step 1 — Expand: Add new embedding column**:
```sql
-- V12__add_new_embedding_column.sql
ALTER TABLE documents
ADD COLUMN embedding_v2 vector(3072),           -- New dimensions
ADD COLUMN embedding_model VARCHAR(100);         -- Track which model

-- Update existing column to track its model
UPDATE documents SET embedding_model = 'text-embedding-ada-002';

-- Index for the new column (non-blocking)
CREATE INDEX CONCURRENTLY idx_documents_embedding_v2_hnsw
ON documents USING hnsw (embedding_v2 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Step 2 — Dual-write: Write to both columns during migration**:
```python
# During backfill period: new documents get both embeddings
async def insert_document(text: str, content: str):
    old_embedding = await embed(text, model="text-embedding-ada-002")
    new_embedding = await embed(text, model="text-embedding-3-large")

    await db.execute(
        "INSERT INTO documents (content, embedding, embedding_v2, embedding_model) "
        "VALUES ($1, $2, $3, $4)",
        content, old_embedding, new_embedding, "text-embedding-3-large"
    )
```

**Step 3 — Backfill: Re-embed existing records**:
```python
# Backfill script — batch to avoid API rate limits and cost spikes
async def backfill_embeddings(batch_size: int = 100):
    offset = 0
    while True:
        rows = await db.fetch(
            "SELECT id, content FROM documents "
            "WHERE embedding_v2 IS NULL "
            "ORDER BY id LIMIT $1 OFFSET $2",
            batch_size, offset
        )
        if not rows:
            break

        # Batch embed (never one at a time)
        texts = [row['content'] for row in rows]
        embeddings = await embed_batch(texts, model="text-embedding-3-large")

        await db.executemany(
            "UPDATE documents SET embedding_v2 = $1, embedding_model = 'text-embedding-3-large' WHERE id = $2",
            [(emb, row['id']) for emb, row in zip(embeddings, rows)]
        )

        offset += batch_size
        logger.info(f"Backfilled {offset} records")
```

**Step 4 — Validate: Confirm search quality**:
```sql
-- Verify backfill progress
SELECT
  COUNT(*) FILTER (WHERE embedding_v2 IS NOT NULL) AS migrated,
  COUNT(*) FILTER (WHERE embedding_v2 IS NULL) AS pending,
  COUNT(*) AS total
FROM documents;

-- Run EXPLAIN ANALYZE on new column
EXPLAIN ANALYZE
SELECT id, content
FROM documents
ORDER BY embedding_v2 <=> $1::vector
LIMIT 10;
```

**Step 5 — Contract: Cut over to new column**:
```sql
-- V13__cutover_to_new_embedding.sql
-- Only after ALL embedding_v2 are populated
ALTER TABLE documents
RENAME COLUMN embedding TO embedding_v1_deprecated,
RENAME COLUMN embedding_v2 TO embedding;

-- Drop old index (non-blocking)
DROP INDEX CONCURRENTLY idx_documents_embedding_hnsw;
```

**Step 6 — Cleanup (after validation period)**:
```sql
-- V14__remove_old_embedding.sql
-- After confirming new model works in production for 1 week
ALTER TABLE documents DROP COLUMN embedding_v1_deprecated;
```

---

### Phase 3 — Weaviate Collection Migration

Weaviate does not support in-place vectorizer changes — must create new collection:

**Step 1 — Create new collection with new vectorizer**:
```python
# Use weaviate-schema-reviewer agent on this code before running
from weaviate.classes.config import Configure, DataType, Property

client.collections.create(
    name="DocumentsV2",
    vector_config=Configure.Vectors.text2vec_openai(
        model="text-embedding-3-large",   # New model
        source_properties=["content"],    # never rely on the all-properties default
    ),
    properties=[
        Property(name="content", data_type=DataType.TEXT),
        Property(name="embedding_model", data_type=DataType.TEXT),
    ],
)
```

`vectorizer_config=Configure.Vectorizer.*` is deprecated (weaviate-client 4.24.1 emits Dep024 on `create()`); see `.claude/skills/vector-database/references/weaviate-collection-patterns.md`.

**Step 2 — Backfill new collection**:
```python
# Export from old, import to new
old_collection = client.collections.get("Documents")
new_collection = client.collections.get("DocumentsV2")

with new_collection.batch.dynamic() as batch:
    for obj in old_collection.iterator():
        batch.add_object({
            "content": obj.properties["content"],
            "embedding_model": "text-embedding-3-large",
        })
        # Weaviate will re-embed using the new vectorizer
```

**Step 3 — Validate then rename**:
- Run search quality tests on `DocumentsV2`
- After validation: delete `Documents`, rename `DocumentsV2` → `Documents`
- Or: keep both with traffic routing

---

### Phase 4 — Agents

**`pgvector-schema-reviewer`** — review the migration SQL:
- Correct dimensions for new model
- Operator class matches new distance metric
- NULL guard on new column
- `embedding_model` metadata column
- Migration is reversible

**`rag-implementation-reviewer`** — review the updated pipeline:
- Model name is pinned (not `latest`)
- Chunking strategy unchanged or documented reason for change
- Reranking still present
- Error handling on new embedding API calls

---

## Quick Reference

| Phase | Action | Gate |
|-------|--------|------|
| 1 — Validate | Test new model search quality | Better or equal recall vs old model |
| 2a — Expand | Add `embedding_v2` column + index | Migration SQL reviewed by `pgvector-schema-reviewer` |
| 2b — Dual-write | New inserts write both columns | No data without new embedding |
| 2c — Backfill | Re-embed all existing rows in batches | 100% rows have `embedding_v2` |
| 2d — Validate | EXPLAIN ANALYZE + search quality check | Index scan used, quality confirmed |
| 2e — Contract | Rename columns, drop old index | Done only after validation period |
| 3 — Weaviate | Create new collection, backfill, validate | `weaviate-schema-reviewer` passes |

---

## Common Pitfalls

- **Mixing old and new embeddings** — even one old embedding in a new-model search index produces wrong results
- **No quality validation** — switching models without testing on domain data; model claims don't equal actual domain performance
- **Re-embedding one at a time** — always batch; single-item loops are 10–50x slower and hit rate limits
- **Skipping `embedding_model` column** — when you've migrated, you need to know which rows used which model; without this column you must re-embed everything to be safe
- **Dropping old column immediately** — keep the old column for at least 1 week after cutover for rollback safety

## Related Workflows

- [`pgvector-rag-pipeline.md`](pgvector-rag-pipeline.md) — original pgvector pipeline setup
- [`weaviate-collection-pipeline.md`](weaviate-collection-pipeline.md) — Weaviate collection management
- [`database-schema-design.md`](database-schema-design.md) — schema migration patterns (expand-contract)
