---
title: Keep Transactions Short to Reduce Lock Contention
impact: MEDIUM-HIGH
impactDescription: 3-5x throughput improvement, fewer deadlocks
tags: transactions, locking, contention, performance
---

## Keep Transactions Short to Reduce Lock Contention

Long-running transactions hold locks that block other queries. Keep transactions as short as possible.

**Incorrect (long transaction with external calls):**

```sql
begin;
select * from orders where id = 1 for update;  -- Lock acquired

-- Application makes HTTP call to payment API (2-5 seconds)
-- Other queries on this row are blocked!

update orders set status = 'paid' where id = 1;
commit;  -- Lock held for entire duration
```

**Correct (minimal transaction scope):**

```sql
-- Validate data and call APIs outside transaction
-- Application: response = await paymentAPI.charge(...)

-- Only hold lock for the actual update
begin;
update orders
set status = 'paid', payment_id = $1
where id = $2 and status = 'pending'
returning *;
commit;  -- Lock held for milliseconds
```

Use `statement_timeout` to prevent runaway transactions:

```sql
-- Abort queries running longer than 30 seconds
set statement_timeout = '30s';

-- Or per-session
set local statement_timeout = '5s';
```

Fail fast instead of queueing behind a lock held by a sweep or a long transaction:

```sql
begin;
set local lock_timeout = '500ms';   -- reverts at COMMIT/ROLLBACK; the statement fails with SQLSTATE 55P03
select * from orders where id = 1 for update;
commit;
```

Surface the failure to the caller as a retryable error (503/409), never swallow it. `set local` resets itself; do not restore a hard-coded value by hand.
Verified on PostgreSQL 16: a contender with `lock_timeout = '300ms'` failed with `canceling statement due to lock timeout` (asyncpg raises it as a bare `DBAPIError`, check `orig.sqlstate`).
Do not hold a pooled session open across an HTTP call: compute first, then open the session, write, commit.

Reference: [Transaction Management](https://www.postgresql.org/docs/current/tutorial-transactions.html)
