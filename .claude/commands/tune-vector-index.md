---
description: Recommend and generate optimized HNSW or IVFFlat index configuration given row count and query latency target. Outputs DROP + CREATE INDEX SQL with tuned parameters, EXPLAIN ANALYZE template, and pgvector-specific query-time settings (ef_search, probes).
argument-hint: "[table name] [current row count] [target latency ms] [current index type if any]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Tune Vector Index

Recommend and generate an optimized pgvector index configuration.

**Input:** $ARGUMENTS (e.g., "documents 250000 50ms IVFFlat")

## Steps

1. **Load the `vector-database` skill** — read `SKILL.md` and `references/pgvector-migration-template.md` for index parameter guidance.

2. **Gather requirements** — Extract from `$ARGUMENTS` or ask:
   - Table name
   - Current row count (or estimate)
   - Target query latency (e.g., 50ms p95)
   - Current index type (IVFFlat / HNSW / none)
   - Distance metric (cosine / L2 / inner product)
   - Recall requirement (0.95 / 0.99 / best-effort)

3. **Query current index state** if project has a database connection:
   ```sql
   SELECT indexname, indexdef, pg_size_pretty(pg_relation_size(indexname::regclass))
   FROM pg_indexes
   WHERE tablename = '{table}' AND indexdef ILIKE '%vector%';
   ```

4. **Select and tune index** based on row count and latency target:

   ### Decision logic:
   ```
   row_count < 100K AND latency_ok_with_IVFFlat → IVFFlat (lower memory)
   row_count >= 100K OR recall >= 0.99 → HNSW
   Production (SLA < 100ms) → HNSW always
   ```

   ### HNSW parameter tuning:
   | Target | m | ef_construction | ef_search |
   |--------|---|-----------------|-----------|
   | Fast (>100ms OK) | 8 | 32 | 20 |
   | Balanced (50-100ms) | 16 | 64 | 40 |
   | High recall (<50ms, recall>0.99) | 32 | 128 | 80 |

   ### IVFFlat parameter tuning:
   | Row count | lists | probes (start) |
   |-----------|-------|--------|
   | ≤ 1M | row_count / 1000 | sqrt(lists) |
   | > 1M | sqrt(row_count) | sqrt(lists) |

   (pgvector README formula. Build IVFFlat only after the data is loaded.)

   ### Dimension limit
   HNSW/IVFFlat on `vector` support ≤ 2000 dims. Above that: reduced dimensions or a `halfvec` expression index (≤ 4000 dims, pgvector ≥ 0.7).

   ### Filtered queries
   If the table is queried with a selective `WHERE` (tenant, category, `is_current`), the filter runs after the index scan and can return fewer than `LIMIT` rows. Recommend iterative scans (`hnsw.iterative_scan` / `ivfflat.iterative_scan`, pgvector ≥ 0.8), a partial index per hot value, partitioning, or exact scan for small scopes — `vector-database/references/ann-vs-knn.md` §Filtered ANN. When recommending a partial index: a partial index on a bound parameter (`tenant_id = $2`) needs `SET LOCAL plan_cache_mode = force_custom_plan`, or it silently stops being used after 5 prepared executions. Check the server's pgvector version (`SELECT extversion FROM pg_extension WHERE extname = 'vector'`) before emitting iterative-scan settings: below 0.8 the `SET` can be accepted silently and do nothing.

5. **Generate SQL**:

   ```sql
   -- Drop existing index (if replacing)
   DROP INDEX CONCURRENTLY IF EXISTS {table}_embedding_idx;

   -- Create optimized index
   CREATE INDEX CONCURRENTLY {table}_embedding_{type}_idx
     ON {table} USING {hnsw|ivfflat} (embedding {ops_class})
     WITH ({params});

   -- Refresh planner statistics
   ANALYZE {table};

   -- IVFFlat only: after a large change in data distribution, rebuild the lists.
   -- ANALYZE does not re-cluster an IVFFlat index.
   REINDEX INDEX CONCURRENTLY {table}_embedding_ivfflat_idx;
   ```

   Note: `CONCURRENTLY` avoids blocking writes but cannot run inside a transaction block — run these statements outside the migration transaction (Alembic: autocommit block; see `python-dev/reference/alembic-migration-safety.md`). Size `maintenance_work_mem` for the build.

6. **Generate EXPLAIN ANALYZE template**:
   ```sql
   -- Run this to verify index is being used
   BEGIN;
   SET LOCAL enable_seqscan = off;              -- force index for testing only
   SET LOCAL hnsw.ef_search = {ef_search};      -- or ivfflat.probes = {probes}

   EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
   SELECT id, 1 - (embedding <=> '{sample_vec}'::vector) AS similarity
   FROM {table}
   WHERE embedding IS NOT NULL
   ORDER BY embedding <=> '{sample_vec}'::vector
   LIMIT 10;
   ROLLBACK;
   ```
   Also compare the index result for a ≤ 1%-selective filter against an exact scan (`SET LOCAL enable_indexscan = off`) and report both row counts.
   ```

7. **Generate query-time settings snippet** for application code:
   ```python
   # Per request, transaction-scoped. A plain SET on a pooled connection
   # persists into the next request that borrows it.
   async with pool.acquire() as conn, conn.transaction():
       await conn.execute("SET LOCAL hnsw.ef_search = {ef_search}")
       rows = await conn.fetch(SEARCH_SQL, query_vec, ctx.tenant_id, active_model, limit)
   ```

8. **Provide monitoring queries**:
   ```sql
   -- Check index usage (should be > 0 after queries)
   SELECT idx_scan, idx_tup_read, idx_tup_fetch
   FROM pg_stat_user_indexes
   WHERE indexrelname = '{table}_embedding_{type}_idx';

   -- Check index size
   SELECT pg_size_pretty(pg_relation_size('{table}_embedding_{type}_idx'));
   ```

9. **Report**:
```
## Vector Index Recommendation: {table}

Input:
- Row count: {N}
- Target latency: {ms}ms
- Distance metric: {metric}

Recommendation: {HNSW|IVFFlat}
Rationale: {reason}

Index parameters:
- {param}: {value} — {reasoning}

Estimated memory overhead: ~{N}MB
Expected recall at tuned settings: ~{pct}%

Migration files generated:
- [path/to/migration.sql]

Next: Run EXPLAIN ANALYZE template to verify index is used before deploying.
```

$ARGUMENTS
