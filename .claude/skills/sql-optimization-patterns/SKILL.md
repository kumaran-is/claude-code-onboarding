---
name: sql-optimization-patterns
description: "Transforms slow PostgreSQL queries into fast operations through systematic EXPLAIN ANALYZE, indexing strategies, N+1 elimination, cursor pagination, and materialized views. Use when diagnosing slow queries, optimizing database performance, or designing index strategies — always profile before optimizing."
argument-hint: "[slow query, table name, or optimization goal]"
allowed-tools: Read
context: fork
metadata:
  triggers: slow query, query optimization, EXPLAIN ANALYZE, N+1 query, index strategy, cursor pagination, missing index, seq scan, query performance, database performance, slow endpoint, database slow, optimize SQL, PostgreSQL optimization, batch operations, materialized view, table partitioning, pg_stat_statements
  related-skills: database-schema-designer, sql-pro, python-dev, java-spring-api, nestjs-api, vector-database
  domain: infrastructure
  role: optimizer
  scope: implementation
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law
PROFILE BEFORE OPTIMIZING — RUN `EXPLAIN (ANALYZE, BUFFERS)` ON THE ACTUAL SLOW QUERY BEFORE WRITING A SINGLE INDEX

## When to Use This Skill

- Debugging slow-running queries in PostgreSQL
- Endpoint response times exceeding target SLA
- Designing performant database schemas for high-traffic tables
- Reducing database load and infrastructure costs
- Resolving N+1 query problems from ORM usage (SQLAlchemy, Prisma, R2DBC)
- Analyzing EXPLAIN query plans from production
- Implementing efficient composite and partial indexes
- Migrating from OFFSET pagination to cursor-based pagination

## Do Not Use This Skill When

- You need cloud-native SQL or analytics platforms (BigQuery, Snowflake) — use `sql-pro`
- You need schema migration design — use `database-schema-designer`
- The database is not PostgreSQL (patterns are PostgreSQL-specific)

## Quick Reference

| Problem | Diagnosis | Fix |
|---------|-----------|-----|
| Slow endpoint | `EXPLAIN (ANALYZE, BUFFERS)` — look for Seq Scan | Add index on WHERE/JOIN columns |
| N+1 queries | Count DB calls per request > 1 | JOIN + eager load or batch query |
| Slow pagination | `OFFSET` on large table | Cursor-based pagination |
| Slow aggregation | GROUP BY without index | Partial index + filter before GROUP BY |
| Slow COUNT(*) | Full table count | `pg_class.reltuples` estimate or index-only count |
| Repeated expensive query | Same query hits DB repeatedly | Materialized view + scheduled refresh |
| Large table slow scans | Millions of rows, date filter | Table partitioning by date range |

## Process

### Step 1 — Identify the Slow Query
```sql
-- Find the top-10 slowest queries by mean execution time
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

No `pg_stat_statements`? Turn on the slow-query log server-wide. A session `SET` only logs your own
session, and the parameter needs superuser (or `GRANT SET`/`ALTER SYSTEM ON PARAMETER`):
```sql
ALTER SYSTEM SET log_min_duration_statement = '100ms';  -- persisted to postgresql.auto.conf
SELECT pg_reload_conf();                                 -- applies without a restart
-- revert: ALTER SYSTEM RESET log_min_duration_statement; SELECT pg_reload_conf();
```
Cloud SQL: set the database flag instead (`gcloud sql instances patch INSTANCE --database-flags=log_min_duration_statement=100`;
the call replaces **all** existing flags, so list every flag you keep).

### Step 2 — Profile with EXPLAIN
```sql
-- Always use ANALYZE + BUFFERS for real data
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT u.id, u.email, COUNT(o.id) AS order_count
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.created_at > NOW() - INTERVAL '30 days'
GROUP BY u.id, u.email;
```

**Key nodes to watch:**
- `Seq Scan` on large table → add index
- `Index Scan` → good; `Index Only Scan` → best
- `Nested Loop` on large tables → may need Hash Join
- `Hash Batches > 1` → memory spill, increase `work_mem`
- `Rows` estimate far from `Actual Rows` → run `ANALYZE <table>`

### Step 3 — Apply the Right Fix
See `resources/implementation-playbook.md` for SQL code for each pattern.

### Step 4 — Verify Improvement
```sql
-- Re-run EXPLAIN ANALYZE after index/change
-- Compare: Execution Time before vs after
-- Compare: Seq Scan → Index Only Scan
```

## Optimization Patterns (Summary)

Load `resources/implementation-playbook.md` for full SQL code examples.

| Pattern | When | Speedup |
|---------|------|---------|
| Composite index | Multi-column WHERE/ORDER BY | 10x–100x |
| Partial index | Filtered subset (e.g., active users) | 5x–50x |
| Covering index | Avoid table heap access | 2x–10x |
| Cursor pagination | Replace `OFFSET 100000` | 100x+ |
| N+1 elimination | ORM loop → single JOIN | N× → 1 query |
| Materialized view | Repeated expensive aggregation | 100x+ |
| Batch operations | Individual inserts/updates in loop | 10x–50x |
| Table partitioning | Time-series or date-range tables >10M rows | 5x–20x |

## Stack Integration

### Python / FastAPI (asyncpg + SQLAlchemy)
- N+1 → use `selectinload` or `joinedload` in SQLAlchemy async; make accidental lazy loads fail with `lazy="raise"` (see `python-dev/reference/sqlalchemy-async-sessions-and-transactions.md` section 6)
- Batch insert → `await session.execute(insert(Model), list_of_dicts)` (SQLAlchemy 2.x batches it) or asyncpg `Connection.executemany` / `copy_records_to_table` (there is no `execute_many`)
- Raw SQL in `text()`: write `CAST(:p AS uuid)`, never `:p::uuid` (the `::` form loses the bind and fails with a syntax error); verify by running it through the real session, not by EXPLAIN on a hand-substituted copy
- Slow query → enable `echo=True` on engine to capture SQL, then EXPLAIN

### NestJS / Prisma
- N+1 → use Prisma `include: { orders: true }` instead of loop queries
- Raw SQL → `prisma.$queryRaw` for complex optimized queries
- Slow endpoint → enable Prisma query logging, identify the statement

### Java / Spring Boot WebFlux (R2DBC)
- N+1 → use `DatabaseClient` with JOIN query instead of reactive loop
- Batch → R2DBC `executeBatch()` method
- Slow query → enable R2DBC logging, capture SQL for EXPLAIN

## Anti-Patterns

- Creating indexes without running `EXPLAIN ANALYZE` first
- Function in WHERE clause preventing index use: `WHERE LOWER(email) = ?` — use expression index
- `LIKE '%term'` with leading wildcard — cannot use B-Tree index; use GIN + `pg_trgm`
- Over-indexing: each index slows INSERT/UPDATE/DELETE — only index proven slow paths
- `OFFSET 100000` pagination on large tables — always replace with cursor
- Individual row inserts in a loop — always batch

## Documentation Sources

- PostgreSQL EXPLAIN: Query MCP context7 with library ID `/postgresql/postgresql`
- `pg_stat_statements`: Query MCP context7

## Reference Files

- `resources/implementation-playbook.md` — Full SQL code for all 8 optimization patterns, EXPLAIN annotation guide, monitoring queries

## Related Skills

- `sql-pro` — Cloud analytics, HTAP, dimensional modeling, BigQuery/Snowflake
- `database-schema-designer` — Schema design, migration patterns, FK/index rules
- `vector-database` — pgvector HNSW/IVFFlat index alignment
- `python-dev` — SQLAlchemy async, asyncpg patterns
- `java-spring-api` — R2DBC reactive database access
- `nestjs-api` — Prisma ORM, raw query patterns
