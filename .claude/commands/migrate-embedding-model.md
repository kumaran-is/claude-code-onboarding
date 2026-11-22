---
description: Plan and generate an embedding model migration — switches embedding model across pgvector tables or Weaviate collections. Produces affected table/collection list, API cost estimate, reversible expand-deploy-contract SQL migrations, and re-embedding script. Safe to run on production — uses expand-then-contract pattern.
argument-hint: "[from model] [to model] [table or collection name(s)]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
disable-model-invocation: true
---

# Migrate Embedding Model

Plan and generate a safe embedding model migration using expand-deploy-contract.

**Input:** $ARGUMENTS (e.g., "text-embedding-3-small text-embedding-3-large documents support_cases")

## Steps

1. **Load the `vector-database` skill** — read `SKILL.md` and `references/embedding-migration-guide.md` for the full procedure.

2. **Gather requirements** — Extract from `$ARGUMENTS` or ask:
   - From model (current)
   - To model (new)
   - Tables/collections to migrate
   - Migration format (Flyway SQL / Alembic Python / Weaviate Python)

3. **Discover affected code** — Grep the codebase for:
   ```bash
   grep -rn "{from_model}" --include="*.py" --include="*.sql" --include="*.ts"
   grep -rn "embedding_model" --include="*.py" --include="*.sql"
   ```
   Report all files referencing the old model that will need updates.

4. **Estimate cost**:
   - For each table: `SELECT COUNT(*), AVG(LENGTH({text_col})) FROM {table}`
   - Calculate: `total_tokens = row_count × avg_chars / 4`
   - Cost at the to-model's current price (read it from the provider's pricing page; never hard-code)
   - New dimension > 2000 with an HNSW/IVFFlat index → stop and choose reduced dimensions or a `halfvec` expression index
   - Report: "Estimated cost: $X.XX for {from_model} → {to_model}"

5. **Generate migration artifacts**:

   ### Phase 1 — Expand migration (safe, reversible)
   ```
   V{N}__expand_embedding_{table}_{new_model_slug}.sql
   ```
   - Adds `embedding_v2 vector({new_dims})` column
   - Adds `embedding_model_v2 varchar(100)` column (stamped by the re-embed writer, no `DEFAULT`)
   - Creates HNSW index on `embedding_v2` with `CREATE INDEX CONCURRENTLY` outside the migration transaction
   - Adds `reembedding_status varchar(20) DEFAULT 'pending'`

   ### Re-embedding script
   ```
   scripts/re_embed_{table}.py
   ```
   - Pattern: `references/embedding-migration-guide.md` §Re-Embedding Script (keyset pagination, one transaction per batch, `asyncio.sleep` not `time.sleep`, structured logging not `print`)
   - Embeds through the embedding chokepoint with the new model and document task type (dimension asserted)
   - Reads from `{text_col}`, writes to `embedding_v2` and stamps `embedding_model_v2`
   - Idempotent and resumable: `WHERE embedding_v2 IS NULL AND id > last_id`
   - Dry-run mode: `--dry-run` flag to preview without writing

   ### Verification queries
   ```
   scripts/verify_reembedding_{table}.sql
   ```
   - Count pending vs done
   - Recall gate on the golden set: Recall@k (new) ≥ Recall@k (old) − 0.02, per query slice — similarity scores across two models are not comparable
   - While both columns are live, every query filters on the model that matches the column it searches

   ### Phase 3 — Contract migration
   ```
   V{N+1}__contract_embedding_{table}.sql
   ```
   - Drops old `embedding` and `embedding_model` columns
   - Renames `embedding_v2` → `embedding`
   - Renames index
   - Down section with data-loss warning

6. **Update application code references** — List every file that hardcodes the old model name. Provide sed command:
   ```bash
   sed -i 's/{from_model}/{to_model}/g' {file_list}
   ```

7. **Run `pgvector-schema-reviewer` agent** on Phase 1 and Phase 3 migrations.

8. **Save all files** and report the complete migration runbook:

```
## Migration Runbook: {from_model} → {to_model}

### Pre-migration
- [ ] Take database backup
- [ ] Estimated cost: $X.XX
- [ ] Test re_embed script on 100 rows: python scripts/re_embed_{table}.py --limit 100 --dry-run

### Phase 1: Expand (safe, reversible)
- [ ] Deploy: V{N}__expand_embedding_{table}.sql
- [ ] Verify: psql -c "SELECT COUNT(*) FROM {table} WHERE embedding_v2 IS NULL"

### Phase 2: Re-embed (run during low traffic)
- [ ] Run: python scripts/re_embed_{table}.py
- [ ] Verify: psql -f scripts/verify_reembedding_{table}.sql
- [ ] Recall gate passed on the golden set (command + output attached; otherwise NOT RUN)

### Phase 3: Contract (irreversible after this point)
- [ ] Deploy: V{N+1}__contract_embedding_{table}.sql
- [ ] Update application model references
- [ ] Run: /review-code src/ (verify no references to old model)
```

$ARGUMENTS
