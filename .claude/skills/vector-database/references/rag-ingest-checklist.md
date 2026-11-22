# RAG Ingest Pipeline Checklist

Load this file BEFORE writing any agent or worker that ingests text into a Weaviate collection or pgvector table for retrieval. It is the PR checklist; the update/versioning/deletion procedures live in `rag-architect/references/incremental-ingestion-guide.md` and `versioning-and-freshness.md` (canonical), and permission-aware retrieval in `rag-security-reviewer` §1–2.

## When this applies

- Any agent/worker that takes text → produces a vector → writes to a vector store
- Examples: document ingestion workers, knowledge-base seeding scripts, batch backfill jobs
- **Does NOT apply** to query-time embedding (user question → embed → search). Queries go through the same embedding chokepoint with the query task type, without storage redaction (redaction would hurt recall); say so in a comment at the call site.

## Checklist (copy into your ingest PR)

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
- [ ] Store only the redacted text next to the vector; attach redaction counts (not values) as metadata.
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
