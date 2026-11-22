---
title: Use Connection Pooling for All Applications
impact: CRITICAL
impactDescription: Handle 10-100x more concurrent users
tags: connection-pooling, pgbouncer, performance, scalability
---

## Use Connection Pooling for All Applications

Postgres connections are expensive (1-3MB RAM each). Without pooling, applications exhaust connections under load.

**Incorrect (new connection per request):**

```sql
-- Each request creates a new connection
-- Application code: db.connect() per request
-- Result: 500 concurrent users = 500 connections = crashed database

-- Check current connections
select count(*) from pg_stat_activity;  -- 487 connections!
```

**Correct (connection pooling):**

```sql
-- Use a pooler like PgBouncer between app and database
-- Application connects to pooler, pooler reuses a small pool to Postgres

-- Size the POOLER's server-side connections from the database (roughly (CPU cores * 2) + spindles for active work).
-- That heuristic is about concurrently active backends, not an application pool: size each app pool from a connection budget (below).

-- Result: 500 concurrent users share 10 actual connections
select count(*) from pg_stat_activity;  -- 10 connections
```

Pool modes:

- **Transaction mode**: connection returned after each transaction (best for most apps)
- **Session mode**: connection held for entire session (needed for prepared statements, temp tables)

Application pool (SQLAlchemy async) from a connection budget:

```python
engine = create_async_engine(url, pool_size=5, max_overflow=5, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800)
# budget: instances x (pool_size + max_overflow), summed over all services and workers,
#         <= ~80% of max_connections minus a reserve for migrations/admin. Over budget -> add a pooler.
```

`pool_timeout` small: exhaustion raises `sqlalchemy.exc.TimeoutError` (verified: after 0.5 s with `pool_timeout=0.5`); map it to 503, do not queue for 30 s.
`pool_recycle` below any proxy/server idle limit. Details: `python-dev/reference/sqlalchemy-async-sessions-and-transactions.md` section 8.
Session-level state (`set`, advisory locks, temp tables) is unsafe behind a transaction-mode pooler.

Reference: [Connection Pooling](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooler)
