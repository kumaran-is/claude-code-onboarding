# RAG Ingest Pipeline Checklist

Load this file BEFORE writing any agent or worker that ingests text into a Weaviate collection or pgvector table for retrieval. It is the PR checklist; the update/versioning/deletion procedures live in `rag-architect/references/incremental-ingestion-guide.md` and `versioning-and-freshness.md` (canonical), and permission-aware retrieval in `rag-security-reviewer` §1–2.

## When this applies

- Any agent/worker that takes text → produces a vector → writes to a vector store
- Examples: document ingestion workers, knowledge-base seeding scripts, batch backfill jobs
- **Does NOT apply** to query-time embedding (user question → embed → search). Queries go through the same embedding chokepoint with the query task type, without storage redaction (redaction would hurt recall); say so in a comment at the call site.

## Checklist (copy into your ingest PR)

### S. Source register entry (ADAPT; the canonical source register)
No content enters an index without a source register entry. Keep it as a reviewed config file next to the pipeline (one entry per corpus/source):

```yaml
source_id: <stable id>
owner: <named accountable person>
approved_use: [<capability ids allowed to retrieve it>]
data_classification: <public | internal | confidential | restricted>
acl_source: <source-system ACL | org membership | role map>
acl_sync_sla: 15m            # ADAPT default ≤ 15 min; ratify
isolation_boundary: <tenant | org | business unit | user>
pii_policy: [<PII classes allowed after sanitization>]
retention: <duration>; legal_hold: <rule>
deletion_sla: 24h            # ADAPT default ≤ 24 h; ratify
trust_level: <trusted-internal | partner | user-generated | external-web>
refresh_mode: <event-driven | scheduled | manual>
embedding_profile: {model: <id>, version: <v>, dimensions: <n>, chunking_version: <v>}
```

- [ ] The ingest job refuses a `source_id` without a register entry, and stamps `trust_level`, `data_classification` and `embedding_profile` from it (never from the document).
- [ ] `user-generated` / `external-web` sources pass the poisoning controls in §P before entering a shared corpus.

### I. Ingestion stages (in order; each is a checklist item)

| # | Stage | Requirement |
|---|---|---|
| 1 | Fetch | Connector authenticates as a least-privilege service identity; records the source version / etag |
| 2 | Parse | Layout-aware: headings, lists and tables extracted separately, page numbers retained; OCR only for image-only content, with confidence recorded (`rag-architect/references/advanced-chunking-guide.md` §3) |
| 3 | Clean | Dehyphenate, normalize whitespace and encoding, strip boilerplate (headers, footers, navigation), fix OCR artifacts |
| 4 | Sanitize | Remove secrets; redact PII beyond `pii_policy`; flag detectable instruction-like text (§P) |
| 5 | Chunk | Per `rag-architect/references/advanced-chunking-guide.md` §0; chunking strategy versioned |
| 6 | Summarize (optional) | One summary chunk per long document, marked `chunk_type=summary` |
| 7 | Enrich | Attach the chunk envelope (§B) |
| 8 | Embed | Through the shared embedding helper only (G13); model/version stamped (§A) |
| 9 | Write | Idempotent (§B) |
| 10 | Emit event | Invalidate caches, schedule eval refresh, update freshness metrics |

### A0. Validate before parsing
- [ ] Source location is allowlisted (bucket/prefix re-validated server-side, not trusted from the message).
- [ ] File type checked by magic bytes, not extension; size and page caps (`MAX_BYTES`, `MAX_PAGES`) enforced; encrypted files and archive bombs rejected.
- [ ] All of the above happens before any paid OCR or embedding call.

### A. Embedding through one chokepoint
- [ ] Ingest calls the storage entry of the embedding chokepoint (redact → length cap → embed with the document task type → `len(vector) == DIMS` → cost log). No direct provider SDK calls in ingest code.
- [ ] Model, dims and task type come from config; every stored vector carries `embedding_model` (and dims/task type/version) — see `rag-pipeline-patterns.md` §Embedding Pipeline.
- [ ] Text is normalized (Unicode NFKC, whitespace, dehyphenation) before hashing AND embedding; the normalizer is versioned.

### A2. Chunking
- [ ] Overlap per the canonical rule in `rag-architect/SKILL.md`: ~10–15% for size-based splitters; 0 allowed on natural boundaries with parent/neighbour expansion.
- [ ] Final chunk ≤ reranker input limit minus the longest expected query (often 512 tokens total — check your reranker), applied after overlap; a unit test runs the chunker over the largest fixture document and asserts the cap.
- [ ] Chunk ids are stable: hash(doc_id, section path, local ordinal) — never a document-global index; Weaviate object uuid = `generate_uuid5(chunk_id)` so retries overwrite.
- [ ] `chunking_method`, `extraction_method` (text layer / OCR tier), parser/chunker/normalizer versions stored per chunk.

### A3. Schema decided at create time
- [ ] Tenancy model chosen deliberately: many small tenants → Weaviate native multi-tenancy (one shard per tenant); few large tenants or cross-tenant analytics → shared collection/table with a mandatory server-side tenant filter (+ RLS or partitions in PostgreSQL). Either way the tenant id comes only from the verified auth context.
- [ ] If `auto_tenant_creation=True`: a write with a forged or mistyped tenant id silently creates a tenant, and read/delete on a never-written tenant raises. Non-write paths use the shared `tenants.exists()` guard (`weaviate-collection-patterns.md` §Multi-Tenancy). Prefer explicit tenant creation at onboarding.
- [ ] Weaviate create uses `vector_config=Configure.Vectors.*` (deprecated `vectorizer_config`/`vector_index_config` arguments are a review finding); create-only settings (`multi_tenancy`, `inverted_index_config(index_null_state=...)`, tokenization) are decided now.
- [ ] pgvector: dimension ≤ 2000 for an HNSW/IVFFlat index; `embedding_model` set by the writer, no column `DEFAULT`.

### B. Persistence
- [ ] **Redact at the storage boundary, not only in logs:** the persisted chunk text and its vector are both produced from already-redacted text; there is no "raw text plus a flag" row to leak. Redaction is one-way and recorded as counts per class (`pii_redactions: {email: 2}`), never values; each redaction pattern has a paired test (a positive that must be redacted and a near-miss negative that must survive).
- [ ] Secrets (credentials, keys, tokens, access codes) are removed before embedding, through the same shared redaction service used for logs and model egress. A secret found after indexing is an incident: purge chunk, vector and caches, then rotate the secret.
- [ ] The chunk envelope is schema-validated at write time; required fields: `chunk_id`, `source_id`, `scope_id` (the isolation key), `acl` (principals/roles), `data_classification`, `trust_level`, `doc_version`, `is_current`, `source_updated_at`, `language`, `chunking_version`, `embedding_model`, `embedding_version`, `ingested_at`, `content_hash`; optional `parent_id`, `effective_from`, `superseded_at`, `chunk_type`, `section_path`, `page`, `pii_redactions`. A write missing a required field fails.
- [ ] Idempotency: re-running ingestion on the same source never duplicates chunks. One mechanism per corpus:

  | Mechanism | How | Choose when |
  |---|---|---|
  | Version-supersede | Mark the prior generation `is_current=false, superseded_at=now`, then write the new generation | Documents are versioned; history must stay queryable; store lacks unique constraints |
  | Content-hash upsert | Unique key on `(scope_id, source_id, chunk_hash)` | Store enforces uniqueness cheaply; history not needed |

  A failed ingest retries the **whole** sequence and converges. The swap between generations is atomic or filtered, so two "current" generations never answer the same query.
- [ ] Ingestion emits an event on success (cache invalidation via `index_version`, eval refresh, freshness metric).
- [ ] Batch both embedding calls and store writes. Weaviate: read `collection.batch.failed_objects` after EACH `with batch` block; pgvector: one transaction per batch.

### C. Failure handling
- [ ] Per-chunk embedding failures are isolated: counted, logged with ids, skipped — and the run FAILS below a success-rate floor. Transient errors (429/503/timeouts) are retried with capped backoff inside the chokepoint.
- [ ] Store-level failures (store unreachable, schema missing) are fatal and surface as a pipeline error.
- [ ] Re-ingest writes the new generation first, then retires the old one (supersede or chunk diff — one strategy per source type). No delete-then-insert window. A failed retire is an error to surface, not "acceptable stale data".
- [ ] Log errors with `log_exception(logger, event, exc, **ids)` (`deployment-ci-cd/reference/python-observability.md` §2) — never `str(e)` of request-derived errors.

### D. Observability
- [ ] Per-call cost/latency log from the chokepoint; per-run summary (`chunks_added/updated/retired/failed`, tokens, estimated cost, duration) with document and tenant ids.
- [ ] Ingestion trace correlates with the request/job id.

### E. Tenant and permission scope
- [ ] Upstream fetches (object store, connectors) run under the same tenant scope as the write; the vector store does not enforce your ACLs by itself.
- [ ] ACL labels (role/group ids) stored per chunk so retrieval can filter in the same call; an ACL change is a metadata update plus cache invalidation, not a re-embed.
- [ ] ACLs are copied from the source of record and re-synced within `acl_sync_sla`; a test revokes a grant at the source and asserts the chunk stops being retrieved within the SLA.
- [ ] Derived artifacts (summaries, compiled profiles, cached answers) inherit the **most restrictive** ACL of their inputs.
- [ ] Role visibility within a scope (internal notes vs customer-visible text) is a chunk attribute, filtered like any other ACL. Filter values at query time come from the server-side auth context, never from client input or model output (`rag-security-reviewer` §2).

### P. Poisoning and injection controls at ingestion
- [ ] Instruction-like text ("ignore previous instructions…") is detected and flagged at ingestion; flagged chunks are reviewed or quarantined, never silently dropped.
- [ ] Untrusted contributors cannot write into a shared corpus without review; `trust_level` is stored per chunk and usable as a retrieval filter or ranking signal.
- [ ] Monitor new chunks that become nearest neighbours of many high-value queries, and chunks with abnormal retrieval frequency; cap one source's share of the final context.
- [ ] Vectors are treated as sensitive as their source text (same access control, encryption and residency).
- [ ] Red-team coverage for indirect injection and poisoning exists for every corpus below `trusted-internal` (procedures: `eval-guide/reference/red-teaming.md`, query-time controls: `rag-security-reviewer`).

### F. Tests
- [ ] Oversized input rejected before any paid call.
- [ ] PII in a sample chunk is redacted in stored text (assert the original string is absent).
- [ ] Chunk-cap test (A2) and a stable-id test (re-ingesting the same document yields the same ids).
- [ ] Golden set includes a document with PII and an edited-document case.

## Anti-patterns to refuse at code review

```python
# ✗ — bypasses redaction, the length cap, the dimension check and the cost log
vec = provider_client.embeddings.create(input=chunk_text, model="some-model")

# ✗ — vector is from redacted text but the stored text still holds raw PII
vec = await embedder.embed([redact_pii(text)], "RETRIEVAL_DOCUMENT")
store.insert(text=text, vector=vec[0])

# ✗ — one bad chunk aborts the whole document (no isolation), or the opposite:
#     every chunk fails and the run still reports success (no success-rate floor)
for chunk in chunks:
    vectors.append(await embedder.embed([chunk.text], "RETRIEVAL_DOCUMENT"))
```

## G. Multi-agent ingest pipelines — persist state through the framework

**Symptom:** the pipeline reports `chunks_written: 0` although chunks landed in the store.

- [ ] Google ADK: a `BaseAgent` sub-agent whose state is read by the request handler AFTER `runner.run_async` finishes must carry the change on a yielded event: write through the delta-aware `ctx.state[k] = v` (ADK records it in `state_delta`) or set `EventActions(state_delta={...})` explicitly. Mutating `ctx.session.state[k]` directly bypasses the delta: later sub-agents in the same run may see it, but it is not persisted, so a handler that re-reads the session via `session_service.get_session(...)` sees the old value. Apply it to every key read after the run (`ingestion_result`, `pipeline_error`, `chunking_method`, …) on both the success and the error event.
- [ ] LangGraph: return the update from the node; never mutate the state object in place.

```python
# ✗ — bypasses the delta; the handler re-reads the session and finds no ingestion_result
ctx.session.state["ingestion_result"] = result
yield Event(author=self.name, content=content)

# ✓ — state_delta persists the change when the runner appends the event (ADK docs: sessions/state)
from google.adk.events import Event, EventActions
yield Event(
    author=self.name,
    actions=EventActions(state_delta={"ingestion_result": result}),
    content=content,
)
```

## H. Live verification gate

Before merging an ingest change, attach evidence from a real run against a dev store:

1. Count chunks for the test document directly in the store, under the test tenant (Weaviate: `collection.with_tenant(t).aggregate.over_all(filters=Filter.by_property("doc_id").equal(d), total_count=True)`; pgvector: `SELECT count(*) … WHERE tenant_id = $1 AND document_id = $2`) — expect ≥ the chunker's output count.
2. Assert no raw PII in stored text (search the store for the seeded email/ID strings).
3. Run a recall smoke query whose answer is in the test document and check its chunk id is in the top-k.
4. Paste the commands and their output in the PR. A check you did not run is NOT RUN, not PASS.

## Reference

- `rag-pipeline-patterns.md` — embedding chokepoint, scoped retrieval, Path A vs B
- `weaviate-collection-patterns.md` — current v4 create API, tenant guard, batch failure accounting
- `rag-architect/references/incremental-ingestion-guide.md` — hash-gated updates (canonical update path)
- `rag-architect/references/versioning-and-freshness.md` — supersession and erasure
