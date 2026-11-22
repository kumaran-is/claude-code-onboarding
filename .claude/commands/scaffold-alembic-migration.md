---
description: Generate a new Alembic database migration with full design-first workflow
argument-hint: "<description> (e.g. add_user_table, add_embedding_column)"
allowed-tools: Bash, Read, Write, Edit
---

# /scaffold-alembic-migration

Generate a new Alembic database migration following the design-first workflow.

## Usage

```
/scaffold-alembic-migration <description>
```

Example: `/scaffold-alembic-migration add_user_table`

## Prerequisites

Before running, identify the project's Alembic configuration:
- Alembic config file location (typically `alembic.ini` under the shared services directory)
- SQLAlchemy models directory
- Pydantic schemas directory

Check the project's `CLAUDE.md` for the canonical paths.

## Full Workflow

Reference for every rule below (with executed examples): `.claude/skills/python-dev/reference/alembic-migration-safety.md`.

### Step 0 — Runner Check (once per project, before the first revision)

Read `env.py` and confirm: a session `lock_timeout` is set (and committed), `transaction_per_migration=True`, `compare_type=True`,
`NullPool` for the migration engine, and EVERY model module is imported (a missing import makes autogenerate skip the table).
Fix gaps with the template in the reference before generating anything.

### Step 1 — Design Doc Update (human reviews before code)

Update the design docs to reflect the planned change:

```bash
# Read current schema docs (adjust paths to your project)
cat docs/database/entity-model.md
cat docs/database/entity-erd.md
```

- Add/modify the entity definition in the schema docs
- Add/modify the Mermaid ERD
- **Present the doc diff to the human** — do NOT proceed until approved

### Step 2 — Update SQLAlchemy Model (source of truth)

Locate the shared models directory for this project and update the relevant model file.

Rules:
- Use `Mapped[]` type annotations (SQLAlchemy 2.0+ async)
- Import and extend the project's `Base` and any shared mixins (e.g. `TimestampMixin`, `UUIDMixin`)
- Add proper foreign keys with `ForeignKey()` constraints
- Add relationship back-references where needed
- Export the new model in the models `__init__.py`

### Step 3 — Update Pydantic Schemas

Locate the shared schemas directory and update the relevant schema file:

- Create/update request and response schemas matching the model
- Export in `schemas/__init__.py`

### Step 4 — Generate Migration (autogenerate)

```bash
# Adjust the -c path to match the project's alembic.ini location
uv run alembic -c <path/to/alembic.ini> revision --autogenerate -m "$ARGUMENTS"
```

### Step 4b — Single-Head Gate

```bash
uv run alembic -c <path/to/alembic.ini> heads    # must list exactly one head
```

Run after every merge of the base branch, migration or not. Ask Alembic; never regex-parse `down_revision`.
Two heads: re-parent your unapplied revision onto the base head; if neither side is yours or one is applied, `alembic merge`.

### Step 5 — Self-Review Migration (AI blind spot check)

Read the generated migration file and check for these known autogenerate problems:

| Problem | Detection | Fix |
|---------|-----------|-----|
| Column rename → shows as drop+add | `op.drop_column` + `op.add_column` for same data | Rewrite as `op.alter_column(table, old_name, new_column_name=new_name)` |
| Enum value addition | PostgreSQL enums need `ALTER TYPE ... ADD VALUE` | Wrap in `with op.get_context().autocommit_block():` + `ADD VALUE IF NOT EXISTS`; the value is unusable in the same transaction; downgrade is a documented no-op |
| CHECK constraint in `__table_args__` | Not emitted by autogenerate by default | Hand-write `op.create_check_constraint(...)` and drop it in `downgrade()`; on a populated table add `NOT VALID`, then `VALIDATE CONSTRAINT` |
| Extension / partition / ANN-index drops | False positives | Filter once with `include_object` in `env.py`; never accept the drop |
| Plain `op.create_index` on a populated table | Blocks writes for the whole build | `CREATE INDEX CONCURRENTLY` in `autocommit_block()`, `DROP INDEX CONCURRENTLY IF EXISTS` first; plain is fine on a new/tiny table (say why) |
| Unique constraint on existing data | Build fails on duplicates | Run a duplicate preflight query first; dedupe only under an approved keep-one rule |
| Backfill inside the revision | Long transaction; "re-select NULLs" loops forever | Keyset-paginated batches in a separate job, finish with a verification count |
| Missing `lock_timeout` on ALTER of a live table | DDL queues behind long transactions | `op.execute("SET LOCAL lock_timeout = '3s'")` unless the runner already guarantees it |
| Enum value removal | Autogenerate ignores this entirely | Write manual migration — PostgreSQL can't remove enum values in-place |
| Data loss risk | Any `op.drop_column` or `op.drop_table` | Flag with `# WARNING: DATA LOSS — requires human approval` comment |
| Missing index | New FK column without index | Add `op.create_index()` for expected query patterns |
| pgvector column | Vector columns need special handling | Ensure `from pgvector.sqlalchemy import Vector` is imported |
| Nullable mismatch | Default nullable doesn't match model intent | Verify `nullable=True/False` matches `Optional[]` in model |

If ANY issue is found, fix the migration file before proceeding.

### Step 6 — Round-Trip Test (mandatory, all 3 must pass)

```bash
# Apply migration
uv run alembic -c <path/to/alembic.ini> upgrade head

# Verify rollback works
uv run alembic -c <path/to/alembic.ini> downgrade -1

# Verify re-apply works
uv run alembic -c <path/to/alembic.ini> upgrade head
```

If any step fails → fix the migration, do NOT commit.

### Step 7 — Dispatch Reviewer

Run the `postgresql-database-reviewer` agent on the migration file.
The verdict must be **SAFE TO APPLY** before opening a PR.

## Report

After completion, present the 3-file summary for human review:

```
SCHEMA CHANGE: $ARGUMENTS

1. DESIGN DOC DIFF:
   - docs/database/entity-model.md: [what changed]
   - docs/database/entity-erd.md: [what changed]

2. MODEL CHANGES:
   - <models path>/<file>: [what changed]
   - <schemas path>/<file>: [what changed]

3. MIGRATION FILE:
   - <alembic versions path>/<file>
   - upgrade(): [summary of operations]
   - downgrade(): [summary of reversal]
   - Round-trip test: PASS / FAIL (and `alembic heads` count: 1)
   - Downgrade loses: [data/behaviour the downgrade drops, or "nothing"]; refuses when data no longer fits: yes/no
   - Blind spot check: [issues found and fixed, or "clean"]

POTENTIAL CONCERNS:
- [data loss risks, enum changes, index gaps, etc.]
```

## Hard Rules

- **NEVER run DDL directly on PostgreSQL** — no ALTER TABLE outside Alembic
- **NEVER modify an applied migration** — create a new revision instead. Amending an UNPUSHED one you applied locally: `alembic downgrade -1` BEFORE editing (editing first leaves the database stamped at head with the old schema; repair with `downgrade <old-parent>`, then `upgrade head`)
- **NEVER skip the round-trip test** — upgrade → downgrade → upgrade must all pass
- **NEVER skip the design doc update** — the schema docs are the RFC
- **Single-writer rule** — only one agent/session modifies models at a time
- **Always commit model + migration + schema docs in the same PR**

$ARGUMENTS
