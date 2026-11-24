# pgvector Migration Templates

## Table of Contents
1. [Standard Migration (up + down)](#standard-migration)
2. [HNSW Index](#hnsw-index)
3. [IVFFlat Index](#ivfflat-index)
4. [Null Guard Pattern](#null-guard)
5. [Reversible Model Migration](#reversible-model-migration)

---

## Standard Migration

Verified server: PostgreSQL 18.7 + pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg18-trixie@sha256:ab49524d18df7200b74ac9a475e1db6297fc1eb57da4c214c63d10ecc4b754fa`, resolved 2026-11-23 with `docker buildx imagetools inspect`). Pin the extension version in the image tag, never a floating `pg18` tag, and check `SELECT extversion FROM pg_extension WHERE extname = 'vector'` in CI.

Every pgvector migration must:
- `CREATE EXTENSION IF NOT EXISTS vector` in `up()`
- Declare dimension matching the model exactly
- Add `embedding_model varchar(100)` alongside the vector column — set by the writer, never a `DEFAULT` (a default lies after a model migration and on NULL vectors)
- Keep the dimension ≤ 2000 if the column will get an HNSW/IVFFlat index (use reduced dims or a `halfvec` expression index above that)
- Include a reversible `down()`

```sql
-- V{N}__add_vector_search_{table}.sql

-- up
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE {table}
  ADD COLUMN embedding         vector({dims}),
  ADD COLUMN embedding_model   varchar(100),
  ADD COLUMN embedded_at       timestamptz,
  ADD CONSTRAINT {table}_embedding_model_stamped
      CHECK (embedding IS NULL OR embedding_model IS NOT NULL);

COMMENT ON COLUMN {table}.embedding IS
  'Semantic embedding. Dimension={dims}. Model stored in embedding_model column.';

-- down
ALTER TABLE {table}
  DROP CONSTRAINT IF EXISTS {table}_embedding_model_stamped,
  DROP COLUMN IF EXISTS embedding,
  DROP COLUMN IF EXISTS embedding_model,
  DROP COLUMN IF EXISTS embedded_at;
```

### Real Examples by Model

**text-embedding-3-small (1536 dims)**
```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE documents
  ADD COLUMN embedding         vector(1536),
  ADD COLUMN embedding_model   varchar(100),          -- writer sets 'text-embedding-3-small'
  ADD COLUMN embedded_at       timestamptz;
```

**nomic-embed-text local (768 dims)**
```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE support_cases
  ADD COLUMN embedding         vector(768),
  ADD COLUMN embedding_model   varchar(100),          -- writer sets 'nomic-embed-text'
  ADD COLUMN embedded_at       timestamptz;
```

---

## HNSW Index

Production default. No training step: it can be built on an empty table and stays valid as rows are inserted. Build large indexes with `CREATE INDEX CONCURRENTLY` outside the migration transaction, with `maintenance_work_mem` sized for the graph; strip Alembic autogenerate's drop/create churn on ANN indexes (`python-dev/reference/alembic-migration-safety.md`).

```sql
-- Cosine similarity (most common)
CREATE INDEX {table}_embedding_hnsw_idx
  ON {table} USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- L2 similarity
CREATE INDEX {table}_embedding_hnsw_l2_idx
  ON {table} USING hnsw (embedding vector_l2_ops)
  WITH (m = 16, ef_construction = 64);

-- Inner product (for dot-product similarity)
CREATE INDEX {table}_embedding_hnsw_ip_idx
  ON {table} USING hnsw (embedding vector_ip_ops)
  WITH (m = 16, ef_construction = 64);
```

**Parameter tuning:**
| Parameter | Default | Increase when |
|-----------|---------|---------------|
| `m` | 16 | Higher recall needed (try 32, 64) |
| `ef_construction` | 64 | Higher quality index needed (try 128) |
| `ef_search` (query time) | 40 | Recall < 0.95 at query time |

Set `ef_search` at query time, transaction-scoped:
```sql
BEGIN;
SET LOCAL hnsw.ef_search = 100;   -- SET LOCAL: a plain SET leaks to the next request on a pooled connection
SELECT id FROM documents WHERE tenant_id = $2 AND embedding_model = $3
ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;
```
Selective `WHERE` filters run after the index scan and can return fewer than `LIMIT` rows — see `ann-vs-knn.md` §Filtered ANN. Iterative scans need pgvector ≥ 0.8.0 (executed on 0.8.7: 0–1 → 10 of 10 rows); use `SET LOCAL hnsw.iterative_scan = relaxed_order` in the same transaction.

---

## IVFFlat Index

Use for fast builds, memory-constrained hosts or mostly-static data. Build it AFTER the data is loaded — the lists (k-means centroids) are computed from the rows present at build time.

```sql
-- MUST have representative data before creating the IVFFlat index
-- 250k rows → lists = 250 (rows / 1000)
CREATE INDEX CONCURRENTLY {table}_embedding_ivfflat_idx
  ON {table} USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 250);

-- After a large change in data distribution (bulk load, new corpus), rebuild the lists:
REINDEX INDEX CONCURRENTLY {table}_embedding_ivfflat_idx;
-- ANALYZE only refreshes planner statistics; it does not re-cluster the lists.
```

**Probe tuning at query time:**
```sql
BEGIN;
SET LOCAL ivfflat.probes = 16;  -- start near sqrt(lists); higher = better recall, slower
SELECT id FROM documents ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;
```

**lists formula** (pgvector README):
- ≤ 1M rows: `lists = row_count / 1000`
- > 1M rows: `lists = sqrt(row_count)`
- `probes` starting point: `sqrt(lists)`

---

## Null Guard

NULL vectors (and zero vectors under cosine) are not indexed. Filter them explicitly so exact-scan fallbacks and partial indexes behave the same as the ANN path, and so un-embedded rows are visible as a backlog metric.

```sql
-- Add partial index for non-null embeddings
CREATE INDEX {table}_embedding_notnull_idx
  ON {table} USING hnsw (embedding vector_cosine_ops)
  WHERE embedding IS NOT NULL;

-- Query guard
SELECT id, name,
       1 - (embedding <=> $1::vector) AS similarity
FROM {table}
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT $2;
```

---

## Reversible Model Migration

When switching embedding models, use expand-deploy-contract:

```sql
-- Phase 1: Expand (add new column, keep old)
-- V{N}__expand_embedding_{table}_v2.sql

ALTER TABLE {table}
  ADD COLUMN embedding_v2        vector({new_dims}),
  ADD COLUMN embedding_model_v2  varchar(100);       -- the re-embed writer stamps it

CREATE INDEX CONCURRENTLY {table}_embedding_v2_hnsw_idx
  ON {table} USING hnsw (embedding_v2 vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);


-- Phase 2: Deploy re-embedding script (see embedding-migration-guide.md)
-- Run: python scripts/re_embed.py --table {table} --from-col embedding --to-col embedding_v2


-- Phase 3: Contract (swap columns, drop old)
-- V{N+1}__contract_embedding_{table}_v2.sql

ALTER TABLE {table}
  DROP COLUMN embedding,
  DROP COLUMN embedding_model;

ALTER TABLE {table}
  RENAME COLUMN embedding_v2 TO embedding;

ALTER TABLE {table}
  RENAME COLUMN embedding_model_v2 TO embedding_model;

-- Down (revert contract — restore the two-column structure)
-- NOTE: the old vectors are gone after contract; the restored column is empty until
-- re-embedded or restored from backup. Contract only after the recall gate passed.
ALTER TABLE {table} RENAME COLUMN embedding TO embedding_v2;
ALTER TABLE {table} RENAME COLUMN embedding_model TO embedding_model_v2;
ALTER TABLE {table}
  ADD COLUMN embedding        vector({old_dims}),
  ADD COLUMN embedding_model  varchar(100);
```
(Verified on PG16 + pgvector 0.6.2 and again on PostgreSQL 18.7 + pgvector 0.8.7 with 2,000 rows: expand → `CREATE INDEX CONCURRENTLY` → backfill → contract → down round-trips without error and keeps the 2,000 re-embedded vectors. The previous down added `embedding_v2` before renaming onto the same name and failed.)

---

## Operator-Index Alignment Table

**This is the most common pgvector bug.** Always verify before deploy.

| Query Operator | Index ops | What it computes |
|----------------|-----------|-----------------|
| `<=>` | `vector_cosine_ops` | Cosine distance |
| `<->` | `vector_l2_ops` | L2 (Euclidean) distance |
| `<#>` | `vector_ip_ops` | Negative inner product |

Mismatch: the planner cannot use the index and falls back to a sequential scan — no error, only latency (verified with EXPLAIN on PostgreSQL 18.7 + pgvector 0.8.7: `<->` on a `vector_cosine_ops` index → Seq Scan + Sort; `<=>` → `Index Scan using ...`).
