---
name: postgres-best-practices
description: Supabase PostgreSQL best practices library — 33 impact-rated rules (CRITICAL→LOW) covering connection pooling, RLS, locking, VACUUM, full-text search, and JSONB indexing. Use when writing, reviewing, or optimizing PostgreSQL queries, schema, or configuration.
argument-hint: "[category or specific rule name]"
allowed-tools: Read
context: fork
metadata:
  triggers: connection pooling, pgbouncer, RLS row level security, SKIP LOCKED, queue workers, deadlock, advisory lock, VACUUM ANALYZE, full-text search tsvector, JSONB GIN index, pg_stat_statements, connection limits, max_connections, idle timeout, prepared statements, transaction mode pooling
  related-skills: database-schema-designer, sql-optimization-patterns, postgresql, sql-pro, vector-database
  domain: infrastructure
  role: optimizer
  scope: implementation
  output-format: document
last-reviewed: "2026-03-15"
---

## Iron Law
NEVER TUNE WHAT YOU HAVEN'T MEASURED — CHECK `pg_stat_statements` AND `pg_stat_activity` BEFORE CHANGING CONFIGURATION OR ADDING INDEXES

## When to Use This Skill

- Configuring connection pooling (PgBouncer, Prisma pool, asyncpg pool, R2DBC pool)
- Implementing Row Level Security (RLS) for multi-tenant data isolation
- Designing worker queues with `SKIP LOCKED` and advisory locks
- Preventing deadlocks in concurrent write workloads
- Configuring VACUUM/ANALYZE and autovacuum tuning
- Adding full-text search with `tsvector`/`tsquery`
- Indexing JSONB columns (`jsonb_ops` vs `jsonb_path_ops`)
- Reviewing any PostgreSQL schema or query against the 8-category rule library

## Do Not Use This Skill When

- You need query EXPLAIN analysis and index pattern SQL (use `sql-optimization-patterns`)
- You need schema migration design or ERDs (use `database-schema-designer`)
- You need cloud analytics or HTAP (use `sql-pro`)

## Rule Categories by Priority

| Priority | Category | Impact | Rules |
|----------|----------|--------|-------|
| 1 | Query Performance | CRITICAL | `rules/query-*.md` (5 rules) |
| 2 | Connection Management | CRITICAL | `rules/conn-*.md` (4 rules) |
| 3 | Security & RLS | CRITICAL | `rules/security-*.md` (3 rules) |
| 4 | Schema Design | HIGH | `rules/schema-*.md` (6 rules) |
| 5 | Concurrency & Locking | MEDIUM-HIGH | `rules/lock-*.md` (4 rules) |
| 6 | Data Access Patterns | MEDIUM | `rules/data-*.md` (4 rules) |
| 7 | Monitoring & Diagnostics | LOW-MEDIUM | `rules/monitor-*.md` (3 rules) |
| 8 | Advanced Features | LOW | `rules/advanced-*.md` (2 rules) |

## Quick Rule Index

### Connection Management (NEW — not in other skills)
- `rules/conn-pooling.md` — PgBouncer setup, pool size formula `(cores × 2) + spindles`, transaction vs session mode
- `rules/conn-limits.md` — `max_connections` calculation, prevent database OOM crash
- `rules/conn-idle-timeout.md` — Reclaim 30-50% idle connection slots
- `rules/conn-prepared-statements.md` — Prepared statement conflicts in transaction-mode pooling

### Concurrency & Locking (NEW — not in other skills)
- `rules/lock-skip-locked.md` — Atomic claim-and-update queue pattern, 10x worker throughput
- `rules/lock-deadlock-prevention.md` — Consistent lock ordering, deadlock prevention patterns
- `rules/lock-short-transactions.md` — Minimize transaction duration, 3-5x throughput
- `rules/lock-advisory.md` — Transaction-scoped advisory locks (session-level locks leak across pooled connections)

### Security & RLS (NEW depth — not in other skills)
- `rules/security-rls-basics.md` — `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + policy patterns
- `rules/security-rls-performance.md` — `SECURITY DEFINER` functions, 5-10x faster RLS queries
- `rules/security-privileges.md` — Principle of least privilege, specific GRANT patterns

### Monitoring & Maintenance (NEW — not in other skills)
- `rules/monitor-vacuum-analyze.md` — VACUUM/ANALYZE patterns, autovacuum tuning
- `rules/monitor-pg-stat-statements.md` — Enable and query `pg_stat_statements`
- `rules/monitor-explain-analyze.md` — EXPLAIN ANALYZE usage guide

### Advanced Features (NEW — not in other skills)
- `rules/advanced-full-text-search.md` — `tsvector`, `ts_rank`, GIN full-text index, 100x vs LIKE
- `rules/advanced-jsonb-indexing.md` — GIN index, `jsonb_ops` vs `jsonb_path_ops` trade-off

### Query Performance (complementary to sql-optimization-patterns)
- `rules/query-missing-indexes.md` — EXPLAIN Seq Scan detection
- `rules/query-index-types.md` — B-tree/GIN/BRIN/Hash selection
- `rules/query-composite-indexes.md` — Leftmost prefix rule
- `rules/query-covering-indexes.md` — INCLUDE columns for Index Only Scan
- `rules/query-partial-indexes.md` — Filtered index subsets

### Schema Design (complementary to database-schema-designer)
- `rules/schema-primary-keys.md` — IDENTITY vs UUID vs UUIDv7
- `rules/schema-data-types.md` — Forbidden types, correct alternatives
- `rules/schema-foreign-key-indexes.md` — Diagnostic SQL to find all missing FK indexes
- `rules/schema-lowercase-identifiers.md` — snake_case, no quoted identifiers
- `rules/schema-partitioning.md` — Range partitioning patterns
- `rules/schema-foreign-key-indexes.md` — FK index enforcement

## Stack Integration

### Python / FastAPI (asyncpg + SQLAlchemy)
- Connection pooling: asyncpg pool `min_size`/`max_size` configuration (see `rules/conn-pooling.md`)
- RLS: set `app.current_user_id` session variable before queries (transaction-local: `set_config(..., true)`; session-level state leaks across pooled connections)
- SKIP LOCKED: use in background task workers, with a lease and attempts cap (`rules/lock-skip-locked.md`)
- Session/transaction ownership, pool sizing, `IntegrityError` handling: `python-dev/reference/sqlalchemy-async-sessions-and-transactions.md`
- Idempotency keys, advisory locks, outbox, retries: `python-dev/reference/reliability-idempotency-retries-outbox.md`

### NestJS / Prisma
- Connection pooling: `DATABASE_URL=...?connection_limit=10&pool_timeout=20` (see `rules/conn-pooling.md`)
- Prepared statements: Prisma uses prepared statements — use session mode or `pgbouncer=true` parameter
- SKIP LOCKED: use `prisma.$queryRaw` for queue worker queries

### Java / Spring Boot WebFlux (R2DBC)
- Connection pooling: `r2dbc.pool.max-size`, `r2dbc.pool.initial-size` (see `rules/conn-pooling.md`)
- RLS: use `ConnectionFactory` with per-request session variable injection

## Related Skills

- `database-schema-designer` — Schema design, migrations (Alembic for Python, Flyway for Java), normalization
- `sql-optimization-patterns` — EXPLAIN analysis, N+1, cursor pagination, batch ops
- `postgresql` — PostgreSQL-specific types, gotchas, extensions, JSONB depth
- `sql-pro` — Cloud analytics, HTAP, BigQuery/Snowflake
- `vector-database` — pgvector HNSW/IVFFlat alignment
