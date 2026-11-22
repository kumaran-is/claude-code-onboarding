---
title: Use Prepared Statements Correctly with Pooling
impact: HIGH
impactDescription: Avoid prepared statement conflicts in pooled environments
tags: prepared-statements, connection-pooling, transaction-mode
---

## Use Prepared Statements Correctly with Pooling

Prepared statements are tied to individual database connections. In transaction-mode pooling, connections are shared, causing conflicts.

**Incorrect (named prepared statements with transaction pooling):**

```sql
-- Named prepared statement
prepare get_user as select * from users where id = $1;

-- In transaction mode pooling, next request may get different connection
execute get_user(123);
-- ERROR: prepared statement "get_user" does not exist
```

**Correct (use unnamed statements or session mode):**

```sql
-- Option 1: Use unnamed prepared statements (most ORMs do this automatically)
-- The query is prepared and executed in a single protocol message

-- Option 2: Deallocate after use in transaction mode
prepare get_user as select * from users where id = $1;
execute get_user(123);
deallocate get_user;

-- Option 3: Use session mode pooling (port 5432 vs 6543)
-- Connection is held for entire session, prepared statements persist
```

Check your driver settings:

```sql
-- Many drivers use prepared statements by default
-- Node.js pg: { prepare: false } to disable
-- JDBC: prepareThreshold=0 to disable
```

SQLAlchemy + asyncpg behind a transaction-mode pooler (options accepted by the dialect on SQLAlchemy 2.1.9; not tested against a live pooler):

```python
# disable the statement caches
create_async_engine("postgresql+asyncpg://.../db?prepared_statement_cache_size=0",
                    connect_args={"statement_cache_size": 0})
# or: unique statement names + NullPool, and have the pooler run DISCARD on return (SQLAlchemy dialect docs)
create_async_engine(url, poolclass=NullPool,
                    connect_args={"prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__"})
```

`pool_pre_ping=True` is safe with such a pooler on current SQLAlchemy 2.x (the ping runs inside an explicit transaction).

Reference: [Prepared Statements with Pooling](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pool-modes)
