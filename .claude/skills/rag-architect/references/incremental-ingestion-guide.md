# Incremental Ingestion Guide

Reference for keeping a RAG corpus fresh without re-embedding unchanged content. Apply when implementing or debugging the document ingestion pipeline.

**Cross-references:** For ingestion strategy selection (full re-ingest vs document-level diff vs append-only), see `advanced-chunking-guide.md §5.3`. For versioning fields (effective_from, superseded_at), see `versioning-and-freshness.md §2`.

---

## 1. Two-Level Hash Gate

Use both a document-level hash and a chunk-level hash. They serve different purposes.

| Hash Level | Purpose | What It Prevents |
|---|---|---|
| **Document hash** | Fast skip — if the whole document is unchanged, skip immediately | Unnecessary chunking and parsing on every ingestion run |
| **Chunk hash** | Exact diff — find exactly which chunks changed, added, or were removed | Re-embedding unchanged chunks when only one paragraph changed |

**Why both are required:**
- Document hash alone tells you the document changed, but not which part. Without chunk hashing, you must delete and re-embed the entire document on every edit.
- Chunk hash alone means parsing and chunking every document on every run — expensive at scale.

```
Ingestion run
  ↓
Compute document hash
  ↓
Document hash unchanged? → SKIP (no parse, no chunk, no embed)
  ↓
Document hash changed?
  ↓
Parse + chunk
  ↓
Compute chunk hash per chunk
  ↓
Compare chunk hashes → embed only changed/new, soft-delete removed
```

---

## 2. Normalize Before Hashing

Always normalize text before computing the content hash. Raw text contains formatting noise — whitespace differences, trailing newlines, OCR artifacts — that cause false re-embeds when content has not meaningfully changed.

```python
import hashlib
import re

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)   # collapse all whitespace
    return text.strip()

def content_hash(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

**What to normalize out before hashing:**
- Extra spaces, tabs, newlines
- Repeated whitespace from PDF extraction
- Page numbers and headers/footers
- Generated timestamps in document metadata
- OCR artifacts when detectable (low-confidence characters)

**What NOT to normalize out:**
- Meaningful punctuation (changes sentence meaning)
- Numbers and amounts (a fee change from $50 to $75 must be detected)
- Section titles (they anchor chunk identity)

---

## 3. Chunk-Level Diff Algorithm

### 14-Step Algorithm

```
1.  Load latest document
2.  Parse document into text
3.  Normalize full document text
4.  Compute document hash
5.  If document hash is unchanged → skip document entirely
6.  If document hash changed → split into chunks using stable chunking
7.  Compute chunk hash for each chunk
8.  Load previous chunk records for this doc_id from metadata store
9.  Build lookup: old_chunks_by_id = {chunk.chunk_id: chunk for chunk in old_chunks}
10. For each new chunk:
      If old chunk exists AND chunk hashes match → skip (keep existing vector)
      If old chunk exists AND chunk hashes differ → re-embed and upsert
      If no old chunk exists → embed and insert
11. For each old chunk not present in new chunk set → soft-delete
12. Update document record with new doc_hash and doc_version
13. Run retrieval smoke test on changed document (see §7)
14. Log ingestion trace
```

### Python Implementation

```python
def ingest_document(doc_id: str, raw_content: str, metadata: dict) -> str:
    parsed_text = parse_document(raw_content)
    normalized_doc = normalize_text(parsed_text)
    new_doc_hash = content_hash(normalized_doc)

    old_doc = get_document_record(doc_id)
    if old_doc and old_doc.doc_hash == new_doc_hash:
        return "skipped: document unchanged"

    new_chunks = chunk_document(normalized_doc, doc_id=doc_id)
    old_chunks = get_existing_chunks(doc_id)
    old_by_chunk_id = {c.chunk_id: c for c in old_chunks}
    new_chunk_ids = set()

    for chunk in new_chunks:
        chunk_hash_val = content_hash(chunk.text)
        new_chunk_ids.add(chunk.chunk_id)

        old_chunk = old_by_chunk_id.get(chunk.chunk_id)
        if old_chunk and old_chunk.chunk_hash == chunk_hash_val:
            continue  # unchanged — keep existing vector

        embedding = embed(chunk.text)
        upsert_vector(
            chunk_id=chunk.chunk_id,
            doc_id=doc_id,
            text=chunk.text,
            embedding=embedding,
            chunk_hash=chunk_hash_val,
            is_active=True,
            **metadata,
        )

    # Soft-delete chunks that no longer exist
    for old_chunk in old_chunks:
        if old_chunk.chunk_id not in new_chunk_ids:
            soft_delete_chunk(old_chunk.chunk_id)

    update_document_record(
        doc_id=doc_id,
        doc_hash=new_doc_hash,
        doc_version=metadata.get("doc_version"),
    )
    return "ingestion complete"
```

---

## 4. Hard Delete vs Soft Delete

When a chunk is removed from a new document version, choose one of two behaviors:

| Approach | Mechanism | When to Use |
|---|---|---|
| **Hard delete** | Remove row and vector from vector DB | No historical retrieval needed; old policy text must never be returned; storage cleanup matters |
| **Soft delete** | Set `is_active = false`, keep row | Audit trail required; rollback possible; document version comparison needed |

**Production recommendation:** Use soft delete for content *updates* (auditability, rollback). It is never an erasure: an erasure/RTBF request is a tenant-scoped hard delete of every version plus a tombstone (`versioning-and-freshness.md` §8).

**One update strategy per source type:** content-hash chunk diff (this guide — frequently edited knowledge bases) OR version supersession (`versioning-and-freshness.md` §5 — legally versioned documents). Never mix both on one source type. Write the new generation before retiring the old one (no delete-then-insert window), and after a diff ingest run the recall smoke test plus a golden case for the edited document. A failed stale-chunk retire is an error to surface, not acceptable stale data.

```python
def soft_delete_chunk(chunk_id: str) -> None:
    update_chunk_metadata(
        chunk_id=chunk_id,
        is_active=False,
        deleted_at=datetime.now(UTC).isoformat(),   # from datetime import UTC, datetime
    )
```

### Mandatory Retrieval Filter

Always filter to active chunks at retrieval time. Without this, soft-deleted chunks from old versions contaminate answers.

```python
# Applied inside the scoped retrieval chokepoint (rag-security-reviewer §2) — never skip
base_filter = {
    "tenant_id": tenant_id,
    "is_active": True,
}
```

```sql
-- pgvector equivalent
WHERE tenant_id = $1
  AND is_active = true
```

---

## 5. Version Fields That Force Full Re-embed

When any of these change, chunk hashes will no longer match vectors in the index. A full re-ingest is required — chunk-level diff cannot be used safely.

| Field Changed | Full Re-embed Required? | Reason |
|---|---|---|
| `embedding_model` | **Yes** | Different model = different vector space; old vectors are incompatible |
| `embedding_dimensions` | **Yes** | Index dimension mismatch; queries will fail or return garbage |
| `chunker_version` | **Usually yes** | Chunk boundaries shift; old chunk IDs no longer align to new chunk IDs |
| `parser_version` (significant change) | **Usually yes** | Extracted text changes; hashes change for all chunks even if source unchanged |
| `normalizer_version` | **Maybe** | If normalization behavior changes, hashes change; test on a sample first |
| One paragraph changed | No | Chunk-level diff handles this |
| New section added | No | New chunks added, unchanged chunks kept |
| Section deleted | No | Removed chunks soft-deleted |
| Metadata-only change | No | Update metadata row; no re-embedding needed |
| ACL / permission changed | No | Update metadata; no re-embedding needed — but invalidate retrieval/answer caches built under the old ACL (`rag-operations-guide.md` §1) |

**Store these version fields on every chunk** so you can detect when a full re-embed is needed:

```json
{
  "embedding_model": "<provider-model-id>",
  "embedding_dimensions": 768,
  "embedding_task_type": "RETRIEVAL_DOCUMENT",
  "chunker_version": "v2",
  "parser_version": "v1",
  "normalizer_version": "v1"
}
```

See `advanced-chunking-guide.md §4` for the full 16-field metadata schema.

---

## 6. Common Failure Modes

| Failure | Cause | Fix |
|---|---|---|
| Old policy text appears in answers | Soft-deleted chunks not filtered at retrieval | Add `is_active = true` to retrieval pre-filter |
| Duplicate chunks retrieved | Upsert not using stable chunk ID — creates new row instead of updating | Enforce stable `chunk_id` = `doc_id:section_path:chunk_index` |
| Too many unnecessary re-embeds | Hashing raw text before normalization — whitespace diffs cause false mismatches | Normalize before hashing (§2) |
| Changed paragraph not detected | Chunk IDs are unstable (based on offset, not section path) — boundaries shift | Switch to section-aware, stable chunk IDs |
| All chunks flagged as changed after small edit | Chunking strategy too fragile — small edit shifts all downstream chunk boundaries | Use document-aware chunking on headings/sections, not sliding windows |
| Document embedded multiple times | Missing `doc_id` uniqueness enforcement — same document ingested under different IDs | Enforce stable `doc_id` derived from source URI |
| Correct chunk not retrieved after update | `is_active` set correctly but retrieval filter missing the field | Audit retrieval pre-filter; confirm `is_active = true` is enforced |

---

## 7. Post-Ingestion Smoke Test

After every ingestion run that changed at least one chunk, run a retrieval smoke test before considering the ingestion complete.

```python
def post_ingestion_smoke_test(doc_id: str, sample_queries: list[str]) -> bool:
    for query in sample_queries:
        results = retrieve(query, filters={"doc_id": doc_id, "is_active": True})
        if not results:
            log.warning("smoke_test_failed", doc_id=doc_id, query=query)
            return False
    return True
```

**What to check:**
- At least one relevant chunk is returned for each test query
- No soft-deleted chunks appear in results
- Chunk metadata (version, source_uri) reflects the new ingestion

**Golden set hygiene:** When a document changes and is re-ingested, add the changed section as a new test case in the golden set. This catches regressions if the ingestion pipeline breaks for that document type in future.

**Ingestion trace logging** (one structured log per run):
```json
{
  "doc_id": "company-policy-001",
  "doc_version": "2026-05-25",
  "chunks_unchanged": 12,
  "chunks_updated": 1,
  "chunks_added": 2,
  "chunks_deleted": 1,
  "embedding_model": "<provider-model-id>",
  "duration_ms": 1240,
  "smoke_test_passed": true
}
```
