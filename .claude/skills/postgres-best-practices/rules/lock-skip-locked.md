---
title: Use SKIP LOCKED for Non-Blocking Queue Processing
impact: MEDIUM-HIGH
impactDescription: 10x throughput for worker queues
tags: skip-locked, queue, workers, concurrency
---

## Use SKIP LOCKED for Non-Blocking Queue Processing

When multiple workers process a queue, SKIP LOCKED allows workers to process different rows without waiting.

**Incorrect (workers block each other):**

```sql
-- Worker 1 and Worker 2 both try to get next job
begin;
select * from jobs where status = 'pending' order by created_at limit 1 for update;
-- Worker 2 waits for Worker 1's lock to release!
```

**Correct (SKIP LOCKED for parallel processing):**

```sql
-- Each worker skips locked rows and gets the next available
begin;
select * from jobs
where status = 'pending'
order by created_at
limit 1
for update skip locked;

-- Worker 1 gets job 1, Worker 2 gets job 2 (no waiting)

update jobs set status = 'processing' where id = $1;
commit;
```

**Gap:** if the worker crashes after the flip, the row stays `processing` forever. Claim with a lease and an attempts cap (next block).

Complete queue pattern:

```sql
-- Atomic claim-and-update in one statement
update jobs
set status = 'processing', worker_id = $1, started_at = now()
where id = (
  select id from jobs
  where status = 'pending'
  order by created_at
  limit 1
  for update skip locked
)
returning *;
```

Lease + attempts (reclaims crashed claims, stops poison rows; verified on PostgreSQL 16: claim, claim during lease returned nothing, re-claim after expiry, none after the cap):

```sql
update jobs
set status = 'running', attempts = attempts + 1, locked_until = now() + interval '5 minutes'
where id in (
  select id from jobs
  where attempts < 5
    and (status = 'pending' or (status = 'running' and locked_until < now()))
  order by created_at
  limit 10
  for update skip locked
)
returning id, attempts;
```

`order by` is mandatory for fairness. Completion: `update jobs set status = 'done' where id = $1 and status = 'running'`.
Consumers must be idempotent (a lease that expires while the worker is merely slow gives two workers the same row).
Full outbox variant with backoff: `python-dev/reference/reliability-idempotency-retries-outbox.md` section 4.

Reference: [SELECT FOR UPDATE SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)
