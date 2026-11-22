---
title: Use UPSERT for Insert-or-Update Operations
impact: MEDIUM
impactDescription: Atomic operation, eliminates race conditions
tags: upsert, on-conflict, insert, update
---

## Use UPSERT for Insert-or-Update Operations

Using separate SELECT-then-INSERT/UPDATE creates race conditions. Use INSERT ... ON CONFLICT for atomic upserts.

**Incorrect (check-then-insert race condition):**

```sql
-- Race condition: two requests check simultaneously
select * from settings where user_id = 123 and key = 'theme';
-- Both find nothing

-- Both try to insert
insert into settings (user_id, key, value) values (123, 'theme', 'dark');
-- One succeeds, one fails with duplicate key error!
```

**Correct (atomic UPSERT):**

```sql
-- Single atomic operation
insert into settings (user_id, key, value)
values (123, 'theme', 'dark')
on conflict (user_id, key)
do update set value = excluded.value, updated_at = now();

-- Returns the inserted/updated row
insert into settings (user_id, key, value)
values (123, 'theme', 'dark')
on conflict (user_id, key)
do update set value = excluded.value
returning *;
```

Insert-or-ignore pattern:

```sql
-- Insert only if not exists (no update)
insert into page_views (page_id, user_id)
values (1, 123)
on conflict (page_id, user_id) do nothing;
```

Partial unique index: repeat the index predicate in the conflict target, or Postgres reports
"no unique or exclusion constraint matching the ON CONFLICT specification" (verified on PostgreSQL 16):

```sql
create unique index uq_pu on pu (k) where live;
insert into pu (k, live, v) values ('x', true, 1)
on conflict (k) where live do update set v = excluded.v;   -- SQLAlchemy: index_where=pu.c.live
```

`do update set` changes only the columns it names: ORM `onupdate` defaults do not run (set `updated_at` yourself) and an omitted column keeps its old value.

ORM flow when you need the winner's row (insert first; the unique constraint decides):

```python
session.add(Reservation(user_id=u, slot_id=s))
try:
    await session.flush()                      # the unique constraint picks the winner
except IntegrityError:
    await session.rollback()                   # also drops this attempt's other staged work
    return await get_existing(session, u, s)   # idempotent: return the winner, do not 500
```

A pre-check `select` before the insert is a fast path, never the guard. Classify the violated constraint by name before treating it as "already exists":
`python-dev/reference/sqlalchemy-async-sessions-and-transactions.md` section 7. Keys and replays: `reliability-idempotency-retries-outbox.md` section 1.

Reference: [INSERT ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT)
