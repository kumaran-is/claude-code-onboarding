# PostgreSQL Connection & Concurrency Setup

> **When to use**: Configuring connection pooling for a new service, diagnosing connection exhaustion, implementing a job queue, or resolving deadlocks in a multi-writer workload.
> **Applies to**: Python/FastAPI (asyncpg), NestJS (Prisma), Java/Spring Boot (R2DBC)
> **Prerequisites**: PostgreSQL database running; access to `pg_stat_activity` and `pg_stat_statements`

## Overview

Structured workflow for production-safe connection management and concurrency patterns. Covers pooling configuration, connection limits, idle timeouts, SKIP LOCKED queues, and deadlock prevention.

## Phases

### Phase 1 — Assess Current Connection State

**Trigger**: New service deployment, connection errors, or `too many connections` failures

```sql
-- Check current connections by state and application
SELECT state, application_name, COUNT(*)
FROM pg_stat_activity
GROUP BY state, application_name
ORDER BY count DESC;

-- Check max_connections setting
SHOW max_connections;

-- Recommended ceiling: max_connections = (RAM_GB * 25) or explicit formula
-- pool_size = (CPU_cores * 2) + disk_spindles
-- Leave 10-20 connections reserved for admin/monitoring
```

**Skill**: `postgres-best-practices` — read `rules/conn-limits.md` and `rules/conn-pooling.md`

**Gate**: Current connection count documented; pool size target calculated

---

### Phase 2 — Configure Connection Pooling

**Trigger**: Service connects directly to PostgreSQL without a pooler

**Stack-specific configuration:**

**Python / SQLAlchemy 2.1 + asyncpg** (engine built once in the FastAPI lifespan; full pattern in `python-dev/reference/sqlalchemy-async-sessions-and-transactions.md` sections 2 and 8):
```python
# pool_size + max_overflow per instance comes from the connection budget:
# instances x (pool_size + max_overflow), summed over all services, < ~80% of max_connections
engine = create_async_engine(
    settings.database_url.get_secret_value(),   # postgresql+asyncpg://... (always name the driver)
    pool_size=5, max_overflow=5,
    pool_timeout=10,       # fail fast -> 503, do not queue for 30 s
    pool_pre_ping=True,
    pool_recycle=1800,     # below any proxy/server idle limit
)
```
`(CPU_cores * 2) + spindles` sizes the server's active connections (a pooler's server pool), not each application pool.
Behind a transaction-mode pooler, disable asyncpg prepared statements (section 8 of the sessions reference).

**NestJS / Prisma:**
```
# In DATABASE_URL — add connection_limit and pool_timeout
DATABASE_URL="postgresql://user:pass@host/db?connection_limit=10&pool_timeout=20&pgbouncer=true"
# pgbouncer=true disables prepared statements (required for transaction mode)
```

**Java / Spring Boot WebFlux (R2DBC):**
```yaml
# In application.yml
spring:
  r2dbc:
    url: r2dbc:postgresql://host/db
    pool:
      initial-size: 2
      max-size: 10
      max-idle-time: 5m
```

**Skill**: `postgres-best-practices` — `rules/conn-pooling.md`, `rules/conn-idle-timeout.md`

**Gate**: Pool configured; connection count under control

---

### Phase 3 — Resolve Prepared Statement Conflicts (transaction-mode pooling)

**Trigger**: Errors like `prepared statement "s0" already exists` with PgBouncer in transaction mode

**Problem**: Prisma and some ORMs use named prepared statements. Transaction-mode poolers don't maintain session state between transactions.

```sql
-- Check for stale prepared statements
SELECT name, statement FROM pg_prepared_statements;

-- Deallocate all (emergency fix)
DEALLOCATE ALL;
```

**Fix options (in order of preference):**
1. Add `pgbouncer=true` to Prisma `DATABASE_URL` — disables named prepared statements
2. Switch PgBouncer to session mode (loses connection multiplexing benefit)
3. Use `DEALLOCATE ALL` at connection return (overhead)

**Skill**: `postgres-best-practices` — `rules/conn-prepared-statements.md`

**Gate**: No prepared statement errors in logs

---

### Phase 4 — Implement SKIP LOCKED Job Queue

**Trigger**: Building a background job processor with multiple concurrent workers

```sql
-- Create jobs table
CREATE TABLE jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    payload JSONB NOT NULL,
    worker_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_jobs_pending ON jobs(created_at) WHERE status = 'pending';

-- Atomic claim-and-update (no race condition, no blocking)
UPDATE jobs
SET status = 'processing',
    worker_id = $1,
    started_at = now()
WHERE id = (
    SELECT id FROM jobs
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

**Skill**: `postgres-best-practices` — `rules/lock-skip-locked.md`

**Gate**: Workers process concurrently without blocking each other

---

### Phase 5 — Prevent Deadlocks in Multi-Writer Workloads

**Trigger**: Deadlock errors in logs (`ERROR: deadlock detected`)

**Root cause pattern:**
```sql
-- Transaction A: locks user 1, then order 1
-- Transaction B: locks order 1, then user 1 → DEADLOCK

-- Fix: always acquire locks in the same order across all transactions
-- By primary key, ascending

-- Bad (inconsistent order):
-- TX A: UPDATE users WHERE id=1; UPDATE orders WHERE id=100;
-- TX B: UPDATE orders WHERE id=100; UPDATE users WHERE id=1;

-- Good (consistent ascending order by ID):
BEGIN;
-- Always lock the lower ID first
UPDATE accounts SET balance = balance - 100 WHERE id = LEAST($1, $2);
UPDATE accounts SET balance = balance + 100 WHERE id = GREATEST($1, $2);
COMMIT;
```

**Skill**: `postgres-best-practices` — `rules/lock-deadlock-prevention.md`, `rules/lock-short-transactions.md`

**Gate**: Zero deadlock errors in 24-hour monitoring window after fix

---

### Phase 6 — Review Configuration

**Trigger**: Configuration changes ready for staging

**Agent**: `postgresql-database-reviewer`

The agent will:
1. Check connection pool sizing against hardware
2. Verify lock ordering patterns are consistent
3. Flag any configuration that could cause connection exhaustion
4. Verify idle timeout is set

**Verdict required**: `✅ SAFE TO APPLY` before deploying to production

---

## Common Pitfalls

- Setting `max_connections` too high — each connection uses 5-10MB RAM; 500 connections on a 2GB instance = OOM
- Using session mode pooling with microservices — each service holds connections permanently
- Not setting `idle_in_transaction_session_timeout` — hung transactions hold locks indefinitely
- Prisma without `pgbouncer=true` in transaction mode — causes intermittent prepared statement errors
- Missing partial index on job queue `WHERE status = 'pending'` — full table scan as queue grows

## Related Skills

- `postgres-best-practices` — All connection and locking rule files
- `postgresql` — PostgreSQL-specific configuration parameters and table design
- `database-schema-designer` — Schema design for the jobs table and related entities
- `sql-optimization-patterns` — Query optimization if job processing queries are slow

## Related Agents

- `postgresql-database-reviewer` — Reviews connection configuration and locking patterns
