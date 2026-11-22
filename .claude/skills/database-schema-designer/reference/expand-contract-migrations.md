# Expand-Contract Migration Pattern

Zero-downtime schema migrations using the Expand-Contract strategy for PostgreSQL + Flyway (Java) and Prisma (NestJS).
For Alembic (Python) the same phases apply; runner settings, `autocommit_block`, `NOT VALID`, single-head gate: `python-dev/reference/alembic-migration-safety.md`.

---

## The 3 Phases

| Phase | What Happens | Code State | Safe to Deploy? |
|-------|-------------|------------|-----------------|
| **EXPAND** | Add new nullable column/table; write to BOTH old + new; read from OLD | Old + New code deployed | YES |
| **MIGRATE** | Backfill historical rows; switch reads to NEW column | New code reads new, old code ignores | YES |
| **CONTRACT** | Drop old column/constraint; clean up | New code only | YES (after N deploys) |

**Rule:** Never collapse phases into a single migration. Each phase must survive independently in production.

---

## PostgreSQL CONCURRENTLY Patterns

### CREATE INDEX CONCURRENTLY

Builds the index without holding a table-level lock — reads and writes continue uninterrupted during index creation.

```sql
-- Expand phase: add index on new column without blocking queries
CREATE INDEX CONCURRENTLY idx_users_email_v2 ON users(email_v2);
```

**Constraint:** Cannot run inside a transaction block. Flyway wraps migrations in transactions by default — disable this per-file:

```sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY idx_users_email_v2 ON users(email_v2);
```

### DROP INDEX CONCURRENTLY

Safe to use during the contract phase — does not block reads or writes.

```sql
-- Contract phase: remove old index without locking
DROP INDEX CONCURRENTLY idx_users_email_old;
```

---

## Batched Backfill (keyset)

Never backfill millions of rows in a single `UPDATE` — it holds a long-running lock and causes replication lag.

**Pattern:** walk the primary key in fixed windows, one short transaction per window (application code or a separate job, never inside one long migration transaction).

```sql
-- Run for consecutive windows: :last = 0, 1000, 2000, ... up to max(id)
UPDATE users
SET    new_email = old_email
WHERE  id > :last AND id <= :last + 1000
  AND  new_email IS NULL AND old_email IS NOT NULL;

-- Finish with a check that must return 0
SELECT count(*) FROM users WHERE new_email IS NULL AND old_email IS NOT NULL;
```

**Why not "re-select `WHERE new_email IS NULL LIMIT 1000` until 0 rows":** rows whose source value is NULL are written back as NULL and match again, so the loop never ends
(verified on PostgreSQL 16: 45 of 450 rows kept matching on every round). A `FOR UPDATE SKIP LOCKED` batch can also skip rows another transaction holds and end early,
so always finish with the verification count. Keyset windows are finite and each commit is short; measure the batch duration on your data and tune the window.

---

## Prisma Expand-Contract Workaround

**Problem:** Prisma generates `CREATE INDEX` statements and wraps `prisma migrate dev` in a transaction. `CREATE INDEX CONCURRENTLY` cannot run inside a transaction — Prisma will error.

**Solution:** Use `--create-only` to generate the SQL file without applying it, then edit the SQL manually before deploying.

```bash
# 1. Generate migration SQL without applying it
npx prisma migrate dev --create-only --name add_new_email_idx

# 2. Edit migrations/xxx_add_new_email_idx/migration.sql
# Change: CREATE INDEX ...
# To:     CREATE INDEX CONCURRENTLY ...

# 3. Apply manually (Prisma won't wrap in transaction)
npx prisma migrate deploy
```

**Warning:** Never use `prisma migrate dev` (without `--create-only`) for `CONCURRENTLY` operations — it runs inside a transaction and will fail with:

```
ERROR: CREATE INDEX CONCURRENTLY cannot run inside a transaction block
```

---

## Flyway Expand-Contract Example

Expand phase migration that adds a new column and a concurrent index, with transaction isolation disabled:

```sql
-- flyway:executeInTransaction=false
-- V2__expand_add_email_v2.sql

ALTER TABLE users ADD COLUMN email_v2 TEXT;
CREATE INDEX CONCURRENTLY idx_users_email_v2 ON users(email_v2);
```

Contract phase (separate migration file, separate deploy):

```sql
-- flyway:executeInTransaction=false
-- V4__contract_drop_email_old.sql

DROP INDEX CONCURRENTLY idx_users_email;
ALTER TABLE users DROP COLUMN email;
```

---

## Anti-Patterns

| Anti-pattern | Problem | Fix |
|-------------|---------|-----|
| Renaming a column in one migration | Running app reads old name → crashes | Expand-Contract: add new column, backfill, switch reads, drop old |
| `CREATE INDEX` without CONCURRENTLY on a populated table | Blocks writes for the whole build | Use `CREATE INDEX CONCURRENTLY` (plain is fine on a new or tiny table; say why) |
| Running CONTRACT phase in the same deploy as EXPAND | Old code still deployed reads the dropped column → 500 errors | Wait at least N deploys (all old instances drained) before contracting |
| Single-statement backfill on large table | Lock timeout, replication lag, OOM risk | Keyset batches, 1000 rows per window, commit per batch |
| Plain `ADD CONSTRAINT CHECK` on a large table | Scans every row under ACCESS EXCLUSIVE; fails on legacy rows | `ADD CONSTRAINT ... NOT VALID`, fix data, then `VALIDATE CONSTRAINT` |
| DDL without `lock_timeout` | The DDL queues behind a long transaction and blocks every later query | `SET lock_timeout = '5s'` (runner) or `SET LOCAL` in the revision; retry the deploy |
| Failed `CREATE INDEX CONCURRENTLY` | Leaves an INVALID index; a retry fails with "already exists" | `DROP INDEX CONCURRENTLY IF EXISTS` first |
