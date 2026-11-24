# Alembic Migration Safety (PostgreSQL)

> For Python services that use Alembic. Java/Flyway and Node/Prisma equivalents live in
> `database-schema-designer/reference/expand-contract-migrations.md`; the phase model (expand, migrate, contract) is shared.
> Snippets were run against PostgreSQL 16 (sections 2-8) and re-run on PostgreSQL 18.7 + pgvector 0.8.7 with Alembic 1.20.1,
> SQLAlchemy 2.1.9, asyncpg 0.32.0 on Python 3.14.10 (runner, `CONCURRENTLY` HNSW build, expand revision with backfill, and the section 7 round trip
> with rows preserved). Pin `alembic==1.20.1` or later with SQLAlchemy 2.1: 1.20.1 fixed autogenerate emitting a duplicate CHECK for
> `Enum`/`Boolean(create_constraint=True)` (duplicate-constraint error at upgrade) and false "Computed default cannot be modified" warnings.

---

## 1. Runner: `migrations/env.py`

```python
import asyncio
import os

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Import EVERY model module before reading Base.metadata: a missing one makes autogenerate skip it.
# from myapp.db import Base; target_metadata = Base.metadata
target_metadata = None
# fail fast instead of queueing behind a long transaction
LOCK_TIMEOUT = os.environ.get("MIGRATION_LOCK_TIMEOUT", "5s")


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
    # session-level SET must outlive the per-revision transactions
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


asyncio.run(run_async_migrations())
```

| Setting | Why | Evidence |
|---------|-----|----------|
| `lock_timeout` (5 s) | A DDL waiting for a lock queues every later reader and writer behind it. Fail the deploy instead | Executed: with an open transaction on the table and `MIGRATION_LOCK_TIMEOUT=1s`, `ADD COLUMN` failed after ~1 s |
| `transaction_per_migration=True` | A lock lives only as long as its revision; a failed run leaves earlier revisions applied and resumes | Executed: r6 failed on lock timeout, `alembic current` stayed `r5`, a re-run applied r6 |
| `NullPool` | One short-lived connection; no pooled-session state leaks into DDL | - |
| `compare_type=True` | Autogenerate notices type changes | - |
| Online (async) only here | Keep one runner; add an offline branch only if you emit SQL files | - |

Run migrations once, as a gated one-shot job BEFORE rolling out new code (fail-fast, no retries, a task timeout, same image as local),
not from every service entrypoint (N instances race for the same lock). Rebuild the migrate image after adding a revision or it fails with `Can't locate revision`.

---

## 2. Rules that need a decision per revision

| Operation on a live table | Do | Do not |
|---------------------------|----|--------|
| Add nullable column, no default | Plain `op.add_column` (catalog-only) | - |
| Add `NOT NULL` column | Add nullable, backfill (section 5), then `SET NOT NULL` in a later revision. `SET NOT NULL` scans under ACCESS EXCLUSIVE; PostgreSQL 12+ skips the scan when a validated `CHECK (col IS NOT NULL)` exists (documented, not executed here) | One-step `NOT NULL` with a volatile default (`now()`, `gen_random_uuid()`): rewrites the table |
| Build an index | `CONCURRENTLY` in `autocommit_block` (section 3) | Plain `CREATE INDEX` on a populated table (blocks writes). Plain is fine on a new or tiny table: say so in the docstring |
| Add CHECK | `NOT VALID` then `VALIDATE CONSTRAINT` (section 4) | Plain `ADD CONSTRAINT` (scans under ACCESS EXCLUSIVE) |
| Add UNIQUE | Duplicate preflight, then build | Build blind: it FAILS on duplicates |
| Add enum value | `autocommit_block` (section 6) | Using the new value in the same transaction |
| Drop column / table | Contract phase only, after no code reads it; `# WARNING: DATA LOSS` comment and human approval | Dropping in the same deploy as the expand |
| Rename column | Expand-contract (add, dual-write, backfill, switch reads, drop) | `op.alter_column(new_column_name=...)` while old code runs |

Each revision on an existing busy table starts with `op.execute("SET LOCAL lock_timeout = '3s'")` if it takes a stronger lock than the runner assumed.

---

## 3. Build indexes without blocking writers

```python
def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction
    with op.get_context().autocommit_block():
        # waiting here blocks no writer; the runner's 5s would fail the deploy
        op.execute("SET lock_timeout = '15min'")
        # clears an INVALID leftover of a failed build
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_open")
        op.execute(
            "CREATE INDEX CONCURRENTLY ix_orders_open ON orders (created_at) WHERE status = 'open'"
        )
        op.execute("SET lock_timeout = '5s'")  # restore the runner value


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_open")
```

Executed facts:
- `CREATE INDEX CONCURRENTLY` inside a transaction: `ActiveSQLTransactionError`.
- A failed concurrent unique build leaves the index with `indisvalid = false`; a retry without the `DROP ... IF EXISTS` fails with `already exists`.
- Build the new index before dropping the old one when replacing an index.
- After a failed build, check `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid`.

---

## 4. Constraints: `NOT VALID`, then `VALIDATE`

```python
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    # new rows enforced now
    op.execute("ALTER TABLE orders ADD CONSTRAINT ck_orders_total CHECK (total >= 0) NOT VALID")
    # fix legacy rows here (human-approved), then:
    # scan, weaker lock
    op.execute("ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_total")
```

Executed on a table with a legacy bad row: plain `ADD CONSTRAINT` fails (`CheckViolationError`); `NOT VALID` succeeds and still rejects new bad rows;
`VALIDATE` fails until the legacy row is fixed. Split the fix and the `VALIDATE` into a later revision (or batch job) when the table is large.
The same two-step form exists for foreign keys (`ADD FOREIGN KEY ... NOT VALID` then `VALIDATE`; PostgreSQL documented behaviour, not executed here).

Unique build preflight (the build fails on duplicates; do not auto-delete without an approved keep-one rule):

```sql
SELECT ref, count(*) FROM invoices WHERE ref IS NOT NULL GROUP BY ref HAVING count(*) > 1;
```

Create tables that carry foreign keys last in a revision so the parent-table lock is short.

---

## 5. Backfill

Never one `UPDATE` over a large table in a revision transaction. Run it as a separate job (or commit per batch), keyset-paginated:

```python
KEYSET = text("""
    UPDATE orders SET new_col = lower(old_col)
    WHERE id > :last AND id <= :last + :step AND new_col IS NULL AND old_col IS NOT NULL
""")

last, max_id = 0, await session.scalar(text("SELECT max(id) FROM orders")) or 0
while last < max_id:
    await session.execute(KEYSET, {"last": last, "step": 1000})
    await session.commit()                       # one short transaction per batch
    last += 1000
# finish with a check that must return 0:
# SELECT count(*) FROM orders WHERE new_col IS NULL AND old_col IS NOT NULL
```

WRONG (`expand-contract-migrations.md` loop form): repeat `UPDATE ... WHERE new_col IS NULL LIMIT 1000` until 0 rows. Executed: rows whose source value is
NULL are rewritten to NULL and match again, so the loop never ends (45 of 450 rows kept matching for 10 rounds). Keyset windows are finite.
`FOR UPDATE SKIP LOCKED` inside a backfill can skip rows another transaction holds and end the loop early: always finish with the verification count.

---

## 6. Enums

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE order_kind ADD VALUE IF NOT EXISTS 'c'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value in place; this no-op is deliberate and must be documented
    pass
```

Executed: adding a value and using it in the same transaction fails (`UnsafeNewEnumValueUsageError: unsafe use of new value`).
Use the value only in a later revision.

---

## 7. One head, always

Two branches that each add a revision create two heads; `alembic upgrade head` then fails at deploy time
(`Multiple head revisions are present`). Gate it in CI and after every merge of the base branch, migration or not:

```bash
#!/usr/bin/env bash
# Migration gate: one head, then upgrade -> downgrade -1 -> upgrade on an EMPTY database.
set -euo pipefail
ALEMBIC="${ALEMBIC:-alembic}"
heads="$($ALEMBIC heads | grep -c . || true)"   # `|| true`: grep -c exits 1 on zero heads; report it below instead of dying silently
if [ "$heads" != "1" ]; then echo "FAIL: expected 1 alembic head, found $heads" >&2; exit 1; fi
# One command per line. `a && b && c` under `set -e` ignores a failure in b: a broken downgrade then printed PASS (executed, exit 0).
$ALEMBIC upgrade head
$ALEMBIC downgrade -1
$ALEMBIC upgrade head
echo "PASS: single head, round trip"
```

Executed against fake `alembic` wrappers (negative controls): healthy wrapper -> PASS, exit 0; wrapper whose `downgrade` exits 1 -> prints the failure, no PASS, exit 1;
wrapper printing zero heads -> `FAIL: expected 1 alembic head, found 0`, exit 1; two heads -> exit 1. Keep a control like this beside any gate script you write. Ask Alembic (`alembic heads`); never regex-parse `down_revision`
(a regex over-counts when a file mentions another revision id). After renaming a revision file delete the stale `__pycache__`.
Fix a fork by re-parenting your unapplied revision onto the base head; if neither side is yours or one is already applied, `alembic merge`.

Amending an UNPUSHED revision you already applied locally: `alembic downgrade -1` BEFORE editing. If you edited first, the database is stamped
at head with the old schema; repair with `alembic downgrade <old-parent>` (or `alembic stamp --purge <old-parent>` after fixing the schema by hand), then `upgrade head`.
Never edit a revision that is pushed or applied elsewhere: write a new one.

---

## 8. Autogenerate blind spots

| Model change | What autogenerate does | You do |
|--------------|------------------------|--------|
| Column rename | `drop_column` + `add_column` (data loss) | Rewrite as expand-contract |
| CHECK constraint in `__table_args__` | Not detected by default (Alembic >= 1.19.2: opt-in plugin `alembic.ext.checkconstraint_byname`, needs every CHECK named, never sees expression changes) | Hand-write `op.create_check_constraint(...)` and its `downgrade` (mind naming conventions: next paragraph) |
| Enum value added/removed | Not detected | Hand-write (section 6); removal needs a new type |
| Extension tables, partition children, ANN indexes | False `drop_*` | Filter once in `env.py` with `include_object`; never accept the drop |
| Server defaults, partial-index predicates | Often missed | Review the diff against the model |
| `Computed(...)` without `persisted=True` (SQLAlchemy 2.1) | Renders a VIRTUAL generated column; on PostgreSQL 18 an index on it fails (`indexes on virtual generated columns are not supported`, executed) | `persisted=True` for every indexed generated column (`tsvector` for hybrid search) |
| Unnamed constraint dropped in `downgrade()` | 1.20 adds a warning comment above `op.drop_constraint(None, ...)` | Name every constraint (naming convention); never ship a `None` drop |

Naming-convention trap: with `MetaData(naming_convention={"ck": "ck_%(table_name)s_%(constraint_name)s"})`, Alembic applies the convention to names you pass to `op.*`.
Passing the already-expanded name doubles it (`op.drop_constraint("ck_documents_positive_version", ...)` emitted `DROP CONSTRAINT ck_documents_ck_documents_positive_version`,
which fails in `downgrade`). Pass the short name (`"positive_version"`) or wrap the full one: `op.f("ck_documents_positive_version")` (both emit the intended name; executed offline with `as_sql`).
Always run the round trip (section 7) so a broken downgrade is caught.

Assess a generated draft by operation count: if it is mostly `drop_*`, the models are not fully imported or the filter is missing. Rewrite it, do not trim it.

---

## 9. Downgrade honesty

- State in the docstring what a downgrade loses (a dropped column's data, a lifted hold) and what to snapshot or pause first.
- Make the downgrade refuse (`RAISE`/exception) when data no longer fits the old schema instead of truncating silently.
- "Always reversible" means the round trip passes on an empty database; it does not make a data-losing downgrade safe in a shared environment.

---

## 10. Review checklist (used by `postgresql-database-reviewer`)

- [ ] Runner sets `lock_timeout`, `transaction_per_migration=True`; all models imported
- [ ] Indexes on populated tables: `CONCURRENTLY` in `autocommit_block`, `DROP ... IF EXISTS` first
- [ ] CHECK/FK added `NOT VALID` then validated; unique builds have a duplicate preflight
- [ ] Enum values in `autocommit_block`, not used in the same revision; downgrade documented
- [ ] Backfill keyset-paginated, batched commits, verification count
- [ ] Exactly one head; round trip passes on an empty database; no edit to an applied revision
- [ ] Drop/rename only in a contract phase with approval; downgrade loss stated
