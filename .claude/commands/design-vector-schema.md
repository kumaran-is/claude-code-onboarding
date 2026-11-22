---
description: Design a pgvector migration SQL file. Captures model + dimension + distance metric + row count → generates reversible Flyway/Alembic migration with correct index type, metadata columns, and null guards.
argument-hint: "[table name] [embedding model] [row count estimate]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Design Vector Schema

Generate a production-ready pgvector migration for the following:

**Input:** $ARGUMENTS

## Steps

1. **Load the `vector-database` skill** — read `SKILL.md` and `references/pgvector-migration-template.md` for templates and operator-index alignment rules.

2. **Gather requirements** — Extract from `$ARGUMENTS` or ask:
   - Table name (existing or new)
   - Embedding model (from skill's model table — `text-embedding-3-small`, `text-embedding-3-large`, `embed-english-v3.0`, `voyage-3-large`, `nomic-embed-text`)
   - Estimated row count (determines HNSW vs IVFFlat)
   - Distance metric (cosine / L2 / inner product)
   - Migration format (Flyway `V{N}__*.sql` or Alembic `{revision}_.py`)

3. **Select index type**:
   - Default: HNSW (no training step; works on an empty table)
   - IVFFlat only for fast builds / memory-constrained / mostly-static data, built after the data load with `lists` = rows/1000 (≤ 1M rows) or sqrt(rows) (> 1M); note `REINDEX INDEX CONCURRENTLY` after large distribution changes (`ANALYZE` does not re-cluster)
   - Dimension > 2000 → stop: HNSW/IVFFlat on `vector` cannot index it; propose reduced dimensions or a `halfvec` expression index (pgvector ≥ 0.7)
   - Table queried with a selective filter (tenant, category) → add the filtered-ANN mitigation (partial index, partition, or iterative scan on pgvector ≥ 0.8) per `references/ann-vs-knn.md` §Filtered ANN. A partial index whose predicate value is a bind parameter (`tenant_id = $2`) must ship with `SET LOCAL plan_cache_mode = force_custom_plan` in the query transaction (generic-plan trap)

4. **Generate migration file** with:
   - `CREATE EXTENSION IF NOT EXISTS vector;` at top of `up()`
   - `vector({dims})` column — dimension from model table
   - `embedding_model varchar(100)` — set by the writer, no `DEFAULT`; plus `CHECK (embedding IS NULL OR embedding_model IS NOT NULL)`
   - `embedded_at timestamptz`
   - Correct index with matching ops class, created with `CREATE INDEX CONCURRENTLY` outside the migration transaction (Alembic: `op.get_context().autocommit_block()`)
   - Null guard partial index (`WHERE embedding IS NOT NULL`) for tables > 50K rows
   - Reversible `down()` section
   - Comment block: model, dims, distance metric, index params reasoning

5. **Run `pgvector-schema-reviewer` agent** on the generated file before presenting to user. If you have a disposable database, apply up → down → up and report the commands and output; otherwise mark the round-trip NOT RUN.

6. **Save file** to `src/main/resources/db/migration/` (Flyway) or `alembic/versions/` (Alembic) depending on project structure. If neither exists, save to current directory with correct naming convention.

7. **Report** what was generated and any reviewer findings.

$ARGUMENTS
