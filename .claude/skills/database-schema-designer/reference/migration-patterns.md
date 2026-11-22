# Migration Patterns

Evolve database schemas safely with reversible, backward-compatible, zero-downtime migrations.

---

## Migration Best Practices

| Practice | Why |
|----------|-----|
| Always reversible | Need to rollback on failure |
| Backward compatible | Zero-downtime deploys require old and new code to coexist |
| Schema before data | Separate structural changes from data transformations |
| Test on staging | Catch issues before production |
| Small incremental changes | Easier to debug and rollback |

---

## Adding a Column (Zero-Downtime)

Never add a NOT NULL column without a default in a single step. Use a multi-step process:

```sql
-- Step 1: Add nullable column
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Step 2: Deploy code that writes to new column

-- Step 3: Backfill existing rows
UPDATE users SET phone = '' WHERE phone IS NULL;

-- Step 4: Make required (if needed)
ALTER TABLE users MODIFY phone VARCHAR(20) NOT NULL;
```

### Why Multi-Step?

- Step 1 is backward compatible (old code ignores the new column)
- Step 2 ensures new rows get the value
- Step 3 fills historical data
- Step 4 enforces the constraint only after all data is clean

---

## Renaming a Column (Zero-Downtime)

Never use `ALTER TABLE RENAME COLUMN` in a single step with live traffic. Use expand-contract pattern:

```sql
-- Step 1: Add new column
ALTER TABLE users ADD COLUMN email_address VARCHAR(255);

-- Step 2: Copy data
UPDATE users SET email_address = email;

-- Step 3: Deploy code reading from BOTH columns (dual-read)

-- Step 4: Deploy code writing to BOTH columns (dual-write)

-- Step 5: Deploy code reading/writing only new column

-- Step 6: Drop old column (after confirming no code references it)
ALTER TABLE users DROP COLUMN email;
```

---

## Removing a Column (Zero-Downtime)

```sql
-- Step 1: Stop writing to the column (deploy code change)
-- Step 2: Stop reading from the column (deploy code change)
-- Step 3: Drop the column
ALTER TABLE users DROP COLUMN legacy_field;
```

**Rule:** Never drop a column that live code still reads or writes.

---

## Adding an Index (Zero-Downtime)

```sql
-- PostgreSQL: CONCURRENTLY avoids table lock
CREATE INDEX CONCURRENTLY idx_orders_status ON orders(status);

-- MySQL: ALGORITHM=INPLACE avoids table copy
ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE;
```

**Warning:** Standard CREATE INDEX blocks writes for the whole build. On a populated table use CONCURRENTLY (PostgreSQL) or ALGORITHM=INPLACE (MySQL); a plain build is acceptable on a new or tiny table (say why in the migration). CONCURRENTLY cannot run in a transaction: Flyway `executeInTransaction=false`, Alembic `autocommit_block()` (`python-dev/reference/alembic-migration-safety.md`).

---

## Changing a Data Type

```sql
-- Step 1: Add new column with new type
ALTER TABLE products ADD COLUMN price_decimal DECIMAL(10,2);

-- Step 2: Backfill
UPDATE products SET price_decimal = CAST(price_float AS DECIMAL(10,2));

-- Step 3: Deploy dual-write code
-- Step 4: Switch reads to new column
-- Step 5: Drop old column
ALTER TABLE products DROP COLUMN price_float;
```

---

## Migration Template

```sql
-- Migration: YYYYMMDDHHMMSS_description.sql

-- UP
BEGIN;
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
CREATE INDEX idx_users_phone ON users(phone);
COMMIT;

-- DOWN
BEGIN;
DROP INDEX idx_users_phone ON users;
ALTER TABLE users DROP COLUMN phone;
COMMIT;
```

### Template Rules

1. **Always include UP and DOWN** -- every migration must be reversible
2. **Wrap in transaction** -- atomic success or failure
3. **Descriptive filename** -- `20250115120000_add_phone_to_users.sql`
4. **Comment the purpose** -- what and why
5. **Estimate impact** -- time, rows affected, downtime requirement

---

## Rollback Strategies

| Scenario | Strategy |
|----------|----------|
| Schema change failed | Run DOWN migration |
| Data migration failed | Restore from backup + re-run |
| Performance degradation | Drop new indexes, revert schema |
| Application error after migration | Deploy old code (schema must be backward compatible) |

### Safe Rollback Checklist

- [ ] DOWN migration tested before deploying UP
- [ ] Backup taken before migration
- [ ] Old application code works with new schema
- [ ] New application code works with old schema (during transition)
- [ ] Monitoring in place to detect issues quickly

---

## Migration Tools

| Stack | Tool | Notes |
|-------|------|-------|
| Spring Boot | Flyway | SQL-based, versioned migrations |
| Spring Boot | Liquibase | XML/YAML/SQL, more features |
| Node.js | Knex.js | JavaScript migrations |
| Node.js | Prisma Migrate | Schema-driven migrations |
| Python | Alembic | SQLAlchemy integration |
| Django | Django Migrations | Built-in, auto-generated |
| Rails | ActiveRecord Migrations | Built-in, Ruby DSL |

Run migrations once, as a gated one-shot job before rollout (fail-fast, no retries, a task timeout, same image as local) rather than from every service entrypoint, where N instances race for the same lock.
Set a `lock_timeout` in the runner so a blocked DDL fails the deploy instead of queueing every other query behind it.

---

## Large Table Migrations

For tables with millions of rows, special care is required:

1. **Batch updates** -- process in chunks of 1000-10000 rows
2. **Throttle** -- add sleep between batches to reduce load
3. **Use pt-online-schema-change** (MySQL) or pg_repack (PostgreSQL) for ALTER TABLE on large tables
4. **Monitor replication lag** -- large migrations can cause replica delays
5. **Schedule during low traffic** -- even with zero-downtime patterns

```sql
-- Batch update example
UPDATE users SET phone = ''
WHERE phone IS NULL
AND id BETWEEN 1 AND 10000;

-- Repeat with next batch: id BETWEEN 10001 AND 20000
```
