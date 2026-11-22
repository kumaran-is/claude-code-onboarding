# Embedding Model Migration Guide

Switching embedding models requires a full re-embedding migration.
Dimensions change; old and new vectors are incompatible.

## Table of Contents
1. [Pre-Migration Checklist](#pre-migration-checklist)
2. [Migration Plan (pgvector)](#migration-plan-pgvector)
3. [Migration Plan (Weaviate)](#migration-plan-weaviate)
4. [Re-Embedding Script](#re-embedding-script)
5. [Rollback Procedure](#rollback-procedure)
6. [Cost Estimation](#cost-estimation)

---

## Pre-Migration Checklist

Before starting any migration:

- [ ] Know the current model name and dimension (query `embedding_model` column)
- [ ] Know the new model name and dimension
- [ ] Estimate token count → calculate API cost (see Cost Estimation)
- [ ] Take a database backup
- [ ] Test re-embedding script on 100-row sample first
- [ ] Confirm index type for new dimension (HNSW for >100K rows)
- [ ] Schedule during low-traffic window (re-embedding can take hours)

---

## Migration Plan (pgvector)

### Phase 1 — Expand (add new column, keep old)

```sql
-- V{N}__expand_embedding_{table}_{new_model_safe_name}.sql

-- up
ALTER TABLE {table}
  ADD COLUMN embedding_v2        vector({new_dims}),
  ADD COLUMN embedding_model_v2  varchar(100) DEFAULT '{new_model}';

CREATE INDEX {table}_embedding_v2_hnsw_idx
  ON {table} USING hnsw (embedding_v2 vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- down
DROP INDEX IF EXISTS {table}_embedding_v2_hnsw_idx;
ALTER TABLE {table}
  DROP COLUMN IF EXISTS embedding_v2,
  DROP COLUMN IF EXISTS embedding_model_v2;
```

### Phase 2 — Re-embed (run script, see below)

Track progress in a migration state column:

```sql
ALTER TABLE {table}
  ADD COLUMN IF NOT EXISTS reembedding_status varchar(20) DEFAULT 'pending';
-- Values: pending | in_progress | complete | failed
```

### Phase 3 — Verify (before swapping)

```sql
-- Verify all rows have new embedding
SELECT
  COUNT(*) FILTER (WHERE embedding_v2 IS NOT NULL) AS done,
  COUNT(*) FILTER (WHERE embedding_v2 IS NULL)     AS pending,
  COUNT(*)                                          AS total
FROM {table};

-- Spot-check recall quality
SELECT id, name,
  1 - (embedding    <=> query_vec::vector) AS old_sim,
  1 - (embedding_v2 <=> query_vec::vector) AS new_sim
FROM {table}
WHERE embedding IS NOT NULL AND embedding_v2 IS NOT NULL
LIMIT 20;
```

### Phase 4 — Contract (swap, drop old)

```sql
-- V{N+1}__contract_embedding_{table}.sql

-- up
-- Drop old index first
DROP INDEX IF EXISTS {table}_embedding_hnsw_idx;

ALTER TABLE {table}
  DROP COLUMN embedding,
  DROP COLUMN embedding_model,
  DROP COLUMN IF EXISTS reembedding_status;

ALTER TABLE {table}
  RENAME COLUMN embedding_v2 TO embedding;

ALTER TABLE {table}
  RENAME COLUMN embedding_model_v2 TO embedding_model;

-- Also rename the index for clarity
ALTER INDEX {table}_embedding_v2_hnsw_idx
  RENAME TO {table}_embedding_hnsw_idx;

-- down (data loss warning — restore from backup)
ALTER TABLE {table}
  ADD COLUMN embedding_legacy vector({old_dims}),
  ADD COLUMN embedding_model_legacy varchar(100);
-- NOTE: old vector data is gone after contract phase. Restore from pre-migration backup.
```

---

## Migration Plan (Weaviate)

Weaviate does not support in-place dimension changes. Create a new collection.

```python
from weaviate.classes.config import Configure, VectorDistances

# Step 1: Create the new collection (current v4 API; copy multi-tenancy and inverted-index settings)
client.collections.create(
    name="{CollectionName}_v2",
    vector_config=Configure.Vectors.self_provided(          # or Configure.Vectors.text2vec_<provider>(model=...)
        vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE),
    ),
    multi_tenancy_config=Configure.multi_tenancy(           # same tenancy model as the original
        enabled=old_config.multi_tenancy_config.enabled,
        auto_tenant_creation=old_config.multi_tenancy_config.auto_tenant_creation,
    ),
    properties=[...],                                       # same properties as the original
)

# Step 2: Re-ingest every object (per tenant) through the embedding chokepoint, stable uuid5 ids
# Step 3: Recall gate on the golden set (shadow Recall@k >= baseline - 0.02), then switch reads via config/alias
# Step 4: Delete the old collection only after the rollback window
client.collections.delete("{CollectionName}")
```
`old_config = client.collections.use("{CollectionName}").config.get()`. Collection aliases (`client.alias.create(alias_name=..., target_collection=...)` / `client.alias.update(alias_name=..., new_target_collection=...)` in weaviate-client 4.24.1; the server must support aliases — check your version) let the application keep one name across the switch; otherwise switch the collection name in configuration.

---

## Re-Embedding Script

Resumable, keyset-paginated, one transaction per batch, embeddings through the chokepoint (which asserts dimensions), model stamped on every row, identifiers validated. *Verified on PG16 + pgvector 0.6.2 with a scripted embedder: 250 rows, one pre-filled row skipped on resume, 0 remaining, all rows stamped; an injected table name is rejected.*

```python
"""Resumable re-embed backfill into the shadow column (run AFTER the expand migration)."""
import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

import asyncpg
from pgvector import Vector

logger = logging.getLogger("re_embed")
EmbedDocs = Callable[[Sequence[str]], Awaitable[list[list[float]]]]   # EmbeddingService(...).embed(..., "RETRIEVAL_DOCUMENT")


def ident(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"bad identifier: {name!r}")
    return f'"{name}"'


async def re_embed(pool: asyncpg.Pool, embed_docs: EmbedDocs, table: str, text_col: str,
                   to_col: str, model_col: str, model: str, batch_size: int = 100,
                   pause_s: float = 0.1) -> int:
    t, txt, dst, mdl = map(ident, (table, text_col, to_col, model_col))
    select_sql = (f"SELECT id, {txt} AS body FROM {t} WHERE {dst} IS NULL AND {txt} IS NOT NULL "
                  f"AND id > $1 ORDER BY id LIMIT $2")
    update_sql = (f"UPDATE {t} AS d SET {dst} = v.e, {mdl} = $3 "
                  f"FROM unnest($1::bigint[], $2::vector[]) AS v(id, e) WHERE d.id = v.id")
    last_id, done = 0, 0
    while True:
        rows = await pool.fetch(select_sql, last_id, batch_size)       # keyset: resumable, no OFFSET
        if not rows:
            break
        vectors = await embed_docs([r["body"] for r in rows])
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(update_sql, [r["id"] for r in rows], [Vector(v) for v in vectors], model)
        last_id, done = rows[-1]["id"], done + len(rows)
        logger.info("re_embed_progress", extra={"table": table, "done": done, "last_id": last_id})
        await asyncio.sleep(pause_s)                                    # never time.sleep in async code
    return done

# Wiring: pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], init=pgvector.asyncpg.register_vector)
```

Run one worker per table (or shard by id range); transient embed errors are retried inside the chokepoint and anything else stops the run, which resumes from the last committed batch. Never `UPDATE` the live column in place while serving.

---

## Rollback Procedure

If migration fails during Phase 2 (re-embedding), rollback is safe:

```sql
-- Safe rollback: just drop the v2 column (no data lost from original)
DROP INDEX IF EXISTS {table}_embedding_v2_hnsw_idx;
ALTER TABLE {table}
  DROP COLUMN IF EXISTS embedding_v2,
  DROP COLUMN IF EXISTS embedding_model_v2,
  DROP COLUMN IF EXISTS reembedding_status;
```

If migration fails during Phase 4 (contract), restore from pre-migration backup — old vector data was dropped.

---

## Cost Estimation

```
tokens_per_row = avg_chars / 4  (rough approximation)
total_tokens = tokens_per_row * row_count

# price_per_1m = current price from the provider's pricing page (prices change — do not hard-code)
cost = (total_tokens / 1_000_000) * price_per_1m
```

**Example:** 100K product descriptions, avg 200 chars → `total_tokens` ≈ 100,000 × 50 = 5M tokens → cost = 5 × `price_per_1m`. Add the cost of re-embedding queries in any shadow/dual-read period.

---

## Migration Strategies (§38)

Choose based on risk tolerance and corpus size.

### Strategy A — Hard Cutover (Default for Low-Risk)
Use the Expand → Re-embed → Swap → Contract pattern documented above.
- Suitable when: dev/staging migration, non-critical corpora, small teams
- Risk: brief window where old and new index coexist; rollback is clean via column drop

### Strategy B — Shadow Index (High-Stakes Pipelines)
Write embeddings to both old and new columns. Read from old. Compare recall divergence before cutting over.
```python
# Dual-write at ingestion (both models run in parallel)
async def embed_dual(text: str) -> tuple:
    old_emb, new_emb = await asyncio.gather(
        embed(text, model=OLD_MODEL),
        embed(text, model=NEW_MODEL),
    )
    return old_emb, new_emb

# At query time: run both retrievers, compare top-k overlap
old_results = retrieve(query_emb_old, index="embedding")
new_results = retrieve(query_emb_new, index="embedding_v2")
overlap = len(set(old_results) & set(new_results)) / k
# Proceed with cutover only when overlap >= 0.90 on golden set
```
- Suitable when: production corpus, high query volume, no tolerance for recall regression
- Cost: 2× embedding API calls during transition period
- Cutover gate: shadow recall@k ≥ baseline − 0.02 on golden set

### Strategy C — A/B at Query Time
Route X% of live traffic to the new embedding; measure production metrics before full cutover.
```python
def get_retriever(user_id: str, rollout_pct: float = 0.05):
    # Deterministic assignment — same user always gets same model
    bucket = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
    if bucket < rollout_pct * 100:
        return retriever_v2  # new model
    return retriever_v1      # old model
```
- Suitable when: you want production recall signal before full cutover
- Requires: A/B metric tracking (Recall@k by group, user satisfaction, abstention rate)
- Cutover gate: new model group shows Recall@k ≥ old model group after 1000+ queries

### Strategy Selection Guide

| Condition | Strategy |
|---|---|
| Dev / non-critical / small corpus | A — Hard Cutover |
| Production, high stakes, can afford 2× embedding cost | B — Shadow Index |
| Production, want real-user signal, low risk tolerance | C — A/B at Query Time |
| Need to minimize downtime window | B or C (never hard cutover during peak) |
