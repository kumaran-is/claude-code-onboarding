# PostgreSQL Review Checklist

## 1. Query Performance (CRITICAL)

- All WHERE/JOIN columns have appropriate indexes
- Correct index type chosen (B-tree for equality/range, GIN for JSONB/arrays/full-text, BRIN for time-series)
- Composite indexes have correct column order (equality columns first, then range)
- No N+1 query patterns — use JOINs or `ANY(ARRAY[...])` instead
- No `SELECT *` in production code
- Cursor-based pagination instead of OFFSET on large tables
- Batch inserts instead of individual inserts for bulk operations
- EXPLAIN ANALYZE run on complex queries; no unexpected Seq Scans on large tables
- Covering indexes (INCLUDE) used where beneficial
- Partial indexes for commonly filtered subsets (soft deletes, status filters)

## 2. Schema Design (HIGH)

- `bigint` for IDs (not `int`), or UUIDv7 for distributed systems (not random UUIDs)
- `text` for strings (not `varchar(n)` unless constraint needed)
- `timestamptz` for timestamps (not `timestamp`)
- `numeric` for money (not `float`)
- `boolean` for flags (not `varchar`)
- Primary keys defined on all tables
- Foreign keys with appropriate ON DELETE behavior
- NOT NULL where appropriate, CHECK constraints for validation
- `lowercase_snake_case` identifiers (no quoted mixed-case)
- Partitioning considered for tables > 100M rows or time-series data

## 3. Security & RLS (CRITICAL)

- RLS enabled and forced on multi-tenant tables
- RLS policies use `(SELECT auth.uid())` pattern (not bare function call per row)
- RLS policy columns are indexed
- Least privilege: no `GRANT ALL` to application users
- Public schema permissions revoked; roles scoped to needed operations
- Sensitive data encrypted; PII access logged
- All queries parameterized (no SQL injection risk)

> For application-level security beyond database (OWASP Top 10, secrets detection, auth bypasses, XSS, SSRF), delegate to the `security-reviewer` agent.

## 4. Concurrency & Connections (MEDIUM)

- Transactions kept short; no external API calls while holding locks
- Consistent lock ordering to prevent deadlocks
- SKIP LOCKED used for queue/worker patterns
- Connection pooling configured (transaction mode for most apps)
- Idle timeouts set (`idle_in_transaction_session_timeout`, `idle_session_timeout`)
- UPSERT (`ON CONFLICT`) used instead of check-then-insert patterns
- No session-level advisory locks through an app pool (`pg_advisory_xact_lock` only); advisory-then-row lock order
- Every uniqueness invariant has a DB constraint; races resolved by the constraint (rollback, return the winner), not by a pre-check
- User-facing statements that can meet sweep-held rows use `SET LOCAL lock_timeout`
- Claim queues (`SKIP LOCKED`) have `ORDER BY`, an attempts cap and a lease; outbox rows have attempts + backoff + an exhausted state
- SQLAlchemy `text()` raw SQL uses `CAST(:p AS type)`, not `:p::type`; partial-index upserts repeat the predicate

## 4b. Migration Safety (HIGH for live tables)

Tool-neutral checks; Alembic specifics in `python-dev/reference/alembic-migration-safety.md`.

- Runner sets `lock_timeout`; each revision/transaction takes its own lock only for as long as needed (`transaction_per_migration` in Alembic)
- Indexes on populated tables built `CONCURRENTLY` outside a transaction (Alembic `autocommit_block()`, Flyway `executeInTransaction=false`), `DROP INDEX CONCURRENTLY IF EXISTS` first
- CHECK / FK on populated tables added `NOT VALID`, then `VALIDATE CONSTRAINT`; unique builds have a duplicate preflight
- Enum values added outside the transaction that uses them; downgrade of an enum add is a documented no-op
- Backfills are keyset-paginated, committed per batch, finished with a verification count (never "re-select WHERE new IS NULL")
- Exactly one Alembic head (`alembic heads`); upgrade -> downgrade -1 -> upgrade passes on an empty database
- Drops and renames only in a contract phase with human approval; the downgrade states what data it loses
- CHECK constraints and enum values written by hand (autogenerate does not emit them); false drops of extension/partition objects filtered, not accepted

## 5. Monitoring & Maintenance

- `pg_stat_statements` enabled for query analysis
- Autovacuum tuned for high-churn tables
- Statistics kept current (`ANALYZE` run regularly)

## Anti-Patterns to Always Flag

- `SELECT *` in production code
- Missing indexes on foreign keys
- OFFSET pagination on large tables
- N+1 query patterns
- `int` IDs, `varchar(255)`, `timestamp` (no tz), `timetz`, `char(n)`, `money`, `serial`, `float` for money
- `GRANT ALL` to application users
- RLS policies with bare `auth.uid()` (not wrapped in SELECT)
- Locks held during external calls
- Session-level advisory locks used through a connection pool
- `CREATE INDEX CONCURRENTLY` inside a transaction block, or plain `CREATE INDEX` on a populated table without a stated reason
- Unparameterized queries

## Output Format

Report findings grouped by severity (CRITICAL > HIGH > MEDIUM > LOW) with file location, issue description, and recommended fix. Include the review checklist with pass/fail status.
