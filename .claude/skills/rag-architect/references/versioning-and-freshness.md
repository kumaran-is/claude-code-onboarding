# Versioning and Freshness

Reference for managing evolving documents in a RAG pipeline — policies, contracts, pricing, and any corpus where content changes over time and historical queries matter (§13 of the production RAG pipeline).

---

## 1. The Problem

Static ingestion assumes documents don't change. Real corpora have:
- **Policy updates** — new version supersedes old; users still ask "what was the rule in March?"
- **Contract amendments** — original + amendments coexist; need to return the version in effect at a given date
- **Pricing changes** — yesterday's price is stale; but billing disputes require historical accuracy
- **Regulatory changes** — "what did the regulation say before the 2024 amendment?"

Without versioning, re-ingesting a new document silently overwrites old chunks — breaking historical queries and destroying the audit trail.

---

## 2. Versioning Model (§13.1)

Add four fields to every chunk's metadata:

| Field | Type | Description |
|---|---|---|
| `document_version` | int | Monotonically increasing per document (1, 2, 3…) |
| `effective_from` | date | Date this version became active |
| `effective_to` | date \| null | Date this version was superseded (null = still current) |
| `superseded_at` | timestamp \| null | When this chunk was replaced (null = current) |

### Stable Chunk ID Scheme with Versioning
```
chunk_id = f"{document_id}-v{document_version}-{chunk_index:04d}"
# Example: "policy-terms-of-service-v3-0007"
```

Never reuse a chunk ID across versions. Old IDs must remain in the database for historical queries and audit logs.

---

## 3. Default Retrieval Filter — Current Versions Only (§13.2)

**Always** filter to current chunks unless the query explicitly asks for historical content.

```python
# Default filter — applied at the pre-filter chokepoint
DEFAULT_VERSION_FILTER = {
    "superseded_at": None,  # null = still current
    "effective_to": None,   # null = no end date = still active
}

# Merge with tenant filter
def build_filters(tenant_id: str, as_of_date: date | None = None) -> dict:
    if as_of_date:
        # Historical query — return version in effect at that date
        return {
            "tenant_id": tenant_id,
            "effective_from": {"$lte": as_of_date},
            "$or": [
                {"effective_to": None},
                {"effective_to": {"$gte": as_of_date}},
            ]
        }
    # Default — current only
    return {
        "tenant_id": tenant_id,
        "superseded_at": None,
    }
```

### SQL Equivalent (pgvector)
```sql
-- Current version filter (default)
WHERE tenant_id = $1
  AND superseded_at IS NULL

-- Historical version filter (as_of_date query)
WHERE tenant_id = $1
  AND effective_from <= $2
  AND (effective_to IS NULL OR effective_to >= $2)
```

---

## 4. Historical Queries (§13.3)

Detect when a user is asking about a past state, not the current state.

### Temporal Intent Detection
```python
HISTORICAL_KEYWORDS = [
    "used to", "previously", "in [year]", "before the change",
    "at the time", "last year", "as of [month]", "original",
    "prior to", "when it was", "the old", "back when",
]

def detect_temporal_intent(query: str) -> date | None:
    # Pattern 1: explicit year ("in 2023", "before 2024")
    year_match = re.search(r'\b(20\d{2})\b', query)
    if year_match:
        return date(int(year_match.group(1)), 12, 31)  # end of that year

    # Pattern 2: relative keywords ("last year", "previously")
    for kw in HISTORICAL_KEYWORDS:
        if kw.lower() in query.lower():
            return date.today() - timedelta(days=365)  # approximate

    return None  # no temporal intent — use current filter
```

### Application
```python
as_of_date = detect_temporal_intent(query)
filters = build_filters(tenant_id=tenant_id, as_of_date=as_of_date)
results = retrieve(query, metadata_filter=filters)

# Inject version context into generation prompt
if as_of_date:
    prompt_prefix = f"Answer based on the version in effect as of {as_of_date}. "
    prompt_prefix += "If the current version differs, note that too."
```

---

## 5. Ingesting a New Version — Atomic Transaction (§13.4)

When a document is updated, the old and new versions must be swapped atomically. A non-atomic swap creates a window where no valid version exists (all superseded) or both versions are returned (duplicate answers).

### Required Pattern
```python
async def ingest_new_version(
    document_id: str,
    new_content: bytes,
    effective_from: date,
    db: AsyncConnection,
) -> None:
    async with db.transaction():
        # Step 1: Supersede ALL current chunks for this document
        await db.execute("""
            UPDATE rag_chunks
            SET superseded_at = NOW(),
                effective_to = $1
            WHERE document_id = $2
              AND superseded_at IS NULL
        """, effective_from, document_id)

        # Step 2: Get new document version number
        new_version = await db.fetchval("""
            SELECT COALESCE(MAX(document_version), 0) + 1
            FROM rag_chunks WHERE document_id = $1
        """, document_id)

        # Step 3: Insert new chunks (same transaction)
        new_chunks = chunk_document(new_content)
        for idx, chunk in enumerate(new_chunks):
            chunk_id = f"{document_id}-v{new_version}-{idx:04d}"
            await db.execute("""
                INSERT INTO rag_chunks
                  (chunk_id, document_id, document_version, text, embedding,
                   effective_from, effective_to, superseded_at, ...)
                VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL, ...)
            """, chunk_id, document_id, new_version, chunk.text, chunk.embedding,
                effective_from)

    # Transaction commits both steps atomically — no window of inconsistency
```

### What Happens on Rollback
If the transaction fails, no changes are applied — old chunks remain current and unsuperseded. Safe to retry.

---

## 6. Effective Date in Generation

Include the effective date in retrieved chunk metadata and instruct the model to cite it.

### Context Packing with Version Info
```python
context_parts = []
for i, chunk in enumerate(packed_chunks):
    version_note = ""
    if chunk.metadata.get("effective_from"):
        version_note = f" [effective {chunk.metadata['effective_from']}]"
    context_parts.append(
        f"[{i+1}]{version_note} {chunk.text}\n(Source: {chunk.metadata['source_uri']})"
    )
```

### Generation Prompt Addition
```
When citing a fact, include the version date if the source has one:
"According to the [Month Year] version of [Document Name]..."
If the user asked about a specific time period and the retrieved content
is from a different period, note the discrepancy.
```

---

## 7. Schema — pgvector Table with Versioning

```sql
CREATE TABLE rag_chunks (
    chunk_id          varchar(200) PRIMARY KEY,
    document_id       uuid NOT NULL,
    document_version  int  NOT NULL DEFAULT 1,
    tenant_id         varchar(100) NOT NULL,
    text              text NOT NULL,
    embedding         vector(1536),
    embedding_model   varchar(100) NOT NULL,
    effective_from    date,
    effective_to      date,          -- NULL = no end date / still active
    superseded_at     timestamptz,   -- NULL = current version
    content_hash      varchar(64),
    source_uri        varchar(500),
    created_at        timestamptz DEFAULT NOW()
);

-- Indexes for common filter patterns
CREATE INDEX rag_chunks_current_idx
    ON rag_chunks (tenant_id, document_id)
    WHERE superseded_at IS NULL;

CREATE INDEX rag_chunks_historical_idx
    ON rag_chunks (tenant_id, effective_from, effective_to)
    WHERE effective_from IS NOT NULL;

-- RLS: tenants only see their own chunks
ALTER TABLE rag_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_chunks FORCE ROW LEVEL SECURITY;          -- applies to the table owner too
CREATE POLICY tenant_isolation ON rag_chunks
    USING      (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
-- Per request, inside the transaction:  SELECT set_config('app.tenant_id', $1, true);
```

The application role must not own the table and must not have `BYPASSRLS` (superusers always bypass). Test both failure modes: no tenant set → zero rows (too strict, visible) and a wrong tenant → zero rows, plus the system-job path that legitimately runs without RLS. Cast the setting (`::uuid`) when `tenant_id` is a `uuid` column. Verified on PG16: app role without a tenant sees 0 rows, as `t1` sees only `t1` rows, and the transaction-local setting is empty after commit. Rule detail: `postgres-best-practices/rules/security-rls-basics.md`.

---

## 8. GDPR / Right-to-Be-Forgotten with Versioning

Erasure is **not** supersession: superseded versions still hold the text. An erasure request hard-deletes every version, scoped to the requesting tenant, and propagates to every derived store.

### Step 1 — one database transaction: tombstone, delete, outbox, audit
```sql
-- $1 = tenant_id (from the verified auth context), $2 = document_id
WITH tomb AS (
    INSERT INTO erasure_tombstones (tenant_id, document_id) VALUES ($1, $2)
    ON CONFLICT DO NOTHING                       -- ingestion skips tombstoned ids
), gone AS (
    DELETE FROM rag_chunks WHERE tenant_id = $1 AND document_id = $2   -- every version
    RETURNING chunk_id
), outbox AS (
    INSERT INTO erasure_outbox (tenant_id, document_id, chunk_ids)
    SELECT $1, $2, coalesce(array_agg(chunk_id), '{}') FROM gone
)
INSERT INTO deletion_audit_log (tenant_id, document_id, deleted_chunk_count, reason)
SELECT $1, $2, count(*), 'erasure_request' FROM gone
RETURNING deleted_chunk_count;
```
`DELETE … RETURNING COUNT(*)` is invalid ("aggregate functions are not allowed in RETURNING") — count rows from a CTE instead. Verified on PG16 with RLS forced and a non-owner role: 3 of 3 `t1` rows deleted across versions, the other tenant's row with the same `document_id` untouched, outbox row created with the 3 chunk ids. The audit row stores ids and counts only — never the erased text.

### Step 2 — a retryable worker drains the outbox
External stores are not inside the database transaction. A worker (idempotent, retried with backoff, alert on age) for each outbox row:
1. Deletes the chunk ids from every external index: vector store (Weaviate: `with_tenant(t).data.delete_many(where=Filter.by_property("doc_id").equal(d))`, guarded by `tenants.exists(t)`), BM25/FTS index, object store (original file and extracted text).
2. Purges caches: bump the corpus `index_version` (retrieval/answer keys miss) and delete entries referencing the chunk ids (`rag-operations-guide.md` §1).
3. Removes derived artifacts: summaries, extracted entities/graph nodes, eval fixtures and golden cases built from the document.
4. Verifies zero remaining objects per store by count, then marks the row `done`. A non-zero count is an error to surface, not "acceptable stale data".

**Important:** Fine-tuned models trained on deleted content cannot be "un-trained". Deletion applies to retrieval only — disclose this limitation when accepting GDPR requests if any model fine-tuning has occurred.
