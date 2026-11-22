---
title: Use Advisory Locks for Application-Level Locking
impact: MEDIUM
impactDescription: Efficient coordination without row-level lock overhead
tags: advisory-locks, coordination, application-locks
---

## Use Advisory Locks for Application-Level Locking

Advisory locks provide application-level coordination without requiring database rows to lock.

**Incorrect (creating rows just for locking):**

```sql
-- Creating dummy rows to lock on
create table resource_locks (
  resource_name text primary key
);

insert into resource_locks values ('report_generator');

-- Lock by selecting the row
select * from resource_locks where resource_name = 'report_generator' for update;
```

**Correct (transaction-scoped advisory lock):**

```sql
-- Released automatically at COMMIT or ROLLBACK, on whichever connection holds it
begin;
select pg_advisory_xact_lock(hashtext('daily_report'));
-- ... do work ...
commit;

-- Non-blocking variant: returns true/false immediately, still released at transaction end
select pg_try_advisory_xact_lock(hashtext('daily_report'));
```

**Incorrect (session-level lock through an application pool):**

```sql
select pg_advisory_lock(hashtext('report_generator'));
-- ... work ...
select pg_advisory_unlock(hashtext('report_generator'));   -- may run on a DIFFERENT pooled connection
```

A session-level lock belongs to the connection, and a pool hands out connections. Verified on PostgreSQL 16 with two pooled connections:
the unlock on the other connection returned `false`, the lock stayed held after both connections went back to the pool, and it was
freed only when the owning connection was closed. Use `pg_advisory_lock` / `pg_try_advisory_lock` only on a connection you own for its whole life
(never behind a transaction-mode pooler).

Rules:

- Use one helper that builds keys from canonical ids (parse UUIDs, then format); two spellings of one id are two locks.
- Fix one global lock order: advisory lock first, then row locks (`order by id for update`).
- Where a unique constraint can express the invariant, use the constraint (it arbitrates races without a lock). Use an advisory lock only
  for invariants a constraint cannot express (e.g. "at most one active X per account").
- Where a decision depends on counters another session updates, lock the parent row `for update` and prove it with a contention test
  (holder keeps the lock, contender runs with `set local lock_timeout = '500ms'` and must fail with SQLSTATE `55P03`).
- Python usage and pool pitfalls: `python-dev/reference/reliability-idempotency-retries-outbox.md` section 2.

Reference: [Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS)
