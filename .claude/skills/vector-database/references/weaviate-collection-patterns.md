# Weaviate Collection Patterns

Python client v4 current API: weaviate-client 4.24.1 against a Weaviate 1.40.7 server, run with `python -W error::DeprecationWarning` (self-provided vectors + HNSW cosine create, multi-tenancy, batch insert, hybrid with `vector=`, filtered `near_vector`, tenant isolation, `delete_many`: executed; named vectors, PQ/RQ compression and server-side vectorizers below are checked against signatures only). The 4.24 client refuses servers older than 1.27.0. weaviate-client 4.24.1 caps `grpcio<1.80` (resolves 1.78.2, which has no cp315 wheel); this is one of the blockers for Python 3.15, so Weaviate services stay on 3.14.

## Table of Contents
1. [Client Setup](#client-setup)
2. [Basic Collection](#basic-collection)
3. [Named Vectors (Multi-Vector)](#named-vectors-multi-vector)
4. [Multi-Tenancy](#multi-tenancy)
5. [Query Patterns](#query-patterns)
6. [Batch Ingestion](#batch-ingestion)
7. [Collection Introspection](#collection-introspection)

---

## Client Setup

```python
import os
import weaviate
from weaviate.classes.init import Auth

# Weaviate Cloud
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=os.environ["WEAVIATE_URL"],        # from env — never hardcode
    auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
    headers={
        "X-OpenAI-Api-Key": os.environ["OPENAI_API_KEY"],  # only if using a server-side text2vec_openai vectorizer
    },
)

# Local / Docker. Pin the server image by digest, e.g.
#   semitechnologies/weaviate:1.40.7@sha256:1373d227ef808c95601b79be75d5e613c04c5ad33a1a2e91ed91a5e6c2748144
# (resolved 2026-11-23 with `docker buildx imagetools inspect`; re-resolve when you bump the tag)
client = weaviate.connect_to_local()               # host/port/grpc_port args when not 8080/50051

# Always close the connection (or use `with weaviate.connect_to_local() as client:`)
try:
    ...
finally:
    client.close()
```

---

## Basic Collection

Two ways to produce vectors:
- **Self-provided** (`Configure.Vectors.self_provided`) — you embed in app code through one embedding chokepoint (redaction before embedding, cost logging, one model for every store). Recommended for RAG ingest.
- **Server-side vectorizer** (`Configure.Vectors.text2vec_<provider>`) — Weaviate calls the embedding API; raw text leaves your service.

```python
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

client.collections.create(
    name="ProductReview",
    vector_config=Configure.Vectors.self_provided(
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,   # explicit; defaults change between versions
            ef_construction=128,
            max_connections=64,                       # document non-default values
        ),
    ),
    # Create-only settings: decide now (changing them = recreate + reindex)
    multi_tenancy_config=Configure.multi_tenancy(enabled=False),
    inverted_index_config=Configure.inverted_index(index_null_state=True),  # needed to filter is_none on e.g. superseded_at
    properties=[
        Property(name="text",            data_type=DataType.TEXT),
        Property(name="source",          data_type=DataType.TEXT),
        Property(name="product_id",      data_type=DataType.TEXT),
        Property(name="rating",          data_type=DataType.NUMBER),
        Property(name="scraped_at",      data_type=DataType.DATE),
        Property(name="superseded_at",   data_type=DataType.DATE),
        Property(name="embedding_model", data_type=DataType.TEXT),   # version stamp on every object
    ],
)
```

**Deprecated (weaviate-client 4.24.1 emits Dep024/Dep025 on create):** `vectorizer_config=Configure.Vectorizer.*` and `vector_index_config=` as create arguments, and `Configure.NamedVectors.*` (only accepted through the deprecated `vectorizer_config=`; Dep026 in `add_vector`). New properties can be added later with `collection.config.add_property(...)`; multi-tenancy, `index_null_state` and tokenization cannot be changed after create — detect drift at startup and log an error naming "recreate + reindex".

---

## Named Vectors (Multi-Vector)

Use when different properties need different embedding strategies. Pass a list of `Configure.Vectors.*(name=...)`.

```python
client.collections.create(
    name="ContractPDF",
    vector_config=[
        Configure.Vectors.text2vec_openai(
            name="summary_vec",
            source_properties=["summary"],            # never rely on the all-properties default
            model="text-embedding-3-small",
        ),
        Configure.Vectors.self_provided(name="full_text_vec"),   # embedded in app code
    ],
    properties=[
        Property(name="summary",     data_type=DataType.TEXT),
        Property(name="full_text",   data_type=DataType.TEXT),
        Property(name="contract_id", data_type=DataType.TEXT),
    ],
)

contracts = client.collections.use("ContractPDF")
result = contracts.query.near_text(          # works: summary_vec has a server vectorizer
    query="early termination clause",
    target_vector="summary_vec",
    limit=5,
)
result = contracts.query.near_vector(        # self-provided vector space: pass the query vector
    near_vector=embed_query("early termination clause"),
    target_vector="full_text_vec",
    limit=5,
)
```

---

## Multi-Tenancy

**Set `enabled=True` at collection creation — this cannot be changed later.** One shard per tenant gives structural isolation; the per-user/role permission filter still goes in `filters=` (canonical rules: `rag-security-reviewer` §1–2).

```python
from weaviate.classes.query import Filter
from weaviate.classes.tenants import Tenant

client.collections.create(
    name="TenantDocument",
    vector_config=Configure.Vectors.self_provided(
        vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE),
    ),
    multi_tenancy_config=Configure.multi_tenancy(
        enabled=True,
        auto_tenant_creation=False,   # explicit tenant lifecycle (see caveats below)
    ),
    properties=[
        Property(name="content",  data_type=DataType.TEXT),
        Property(name="doc_id",   data_type=DataType.TEXT),
        Property(name="doc_type", data_type=DataType.TEXT),
    ],
)

documents = client.collections.use("TenantDocument")
documents.tenants.create([Tenant(name="org_123"), Tenant(name="org_456")])   # at org onboarding


def scoped(tenant_id: str):
    """The only way to touch a multi-tenant collection. tenant_id comes from the verified auth context."""
    if not tenant_id:
        raise PermissionError("tenant scope required")
    return documents.with_tenant(tenant_id)


scoped(ctx.tenant_id).data.insert(
    properties={"content": "Service agreement for account 4B", "doc_id": "doc-77", "doc_type": "contract"},
    vector=embed_document("Service agreement for account 4B"),
)
result = scoped(ctx.tenant_id).query.near_vector(near_vector=embed_query("late payment clause"), limit=5)
```

### `auto_tenant_creation=True` caveats

- A **write** with a forged or mistyped tenant id silently **creates** a tenant. Never take the tenant id from the request body, tool arguments or model output.
- The tenant exists only after its first write. Query, delete or supersede on a never-written tenant **raises**. Guard non-write paths with the typed check, once, in a shared helper:

```python
def delete_by_doc(tenant_id: str, doc_id: str) -> int:
    if not documents.tenants.exists(tenant_id):   # lazily created on first write
        return 0                                  # typed check — never match error text
    res = scoped(tenant_id).data.delete_many(where=Filter.by_property("doc_id").equal(doc_id))
    return res.successful
```

Matching exception text ("tenant not found") also swallows auth, network and filter errors — do not.

**Tenant lifecycle:** cold tenants can be deactivated or offloaded (`documents.tenants.deactivate(...)`, `.offload(...)`, `.activate(...)`) to cut memory. Choose native multi-tenancy for many small tenants; for few large tenants or cross-tenant analytics, a shared collection with a mandatory server-side filter may fit better.

---

## Query Patterns

Every call below runs on `scoped(ctx.tenant_id)` when the collection is multi-tenant.

### Vector search
```python
from weaviate.classes.query import Filter, HybridFusion, MetadataQuery

reviews = client.collections.use("ProductReview")
qvec = embed_query("battery drains overnight")      # same model + query task type as stored vectors

result = reviews.query.near_vector(
    near_vector=qvec,
    limit=10,
    return_metadata=MetadataQuery(distance=True),
    filters=Filter.by_property("rating").greater_than(3.5)
            & Filter.by_property("embedding_model").equal(settings.embedding_model),
)
```
`near_text` requires a server-side vectorizer for the target vector; on self-provided vectors use `near_vector`.

### Hybrid Search
```python
result = reviews.query.hybrid(
    query="battery drains overnight model X200",
    vector=qvec,                             # REQUIRED on self-provided vectors — without it the
                                             # vector leg is empty and ranking is keyword-only, no error
    alpha=0.5,                               # 0 = BM25 only, 1 = vector only; tune per query class
    fusion_type=HybridFusion.RELATIVE_SCORE, # or HybridFusion.RANKED
    limit=40,                                # over-fetch for the reranker
    return_metadata=MetadataQuery(score=True, explain_score=True),
)
```

**Fusion algorithm choice** (`HybridFusion` has exactly two members):
| Algorithm | When to Use |
|-----------|-------------|
| `HybridFusion.RANKED` | Rank-based merge; stable when score scales differ |
| `HybridFusion.RELATIVE_SCORE` | Score-normalized merge; keeps score magnitude |

Test: a golden paraphrase query sharing no keywords with its answer chunk must appear in the top-k — it fails if `vector=` is missing.

### BM25 (keyword only)
```python
result = reviews.query.bm25(query="X200", query_properties=["text", "source"], limit=10)
```

### Generative (server-side RAG)
`collection.generate.*` sends retrieved objects to a model configured on the collection. Use it for prototypes; production RAG usually needs the citation validation and abstention in `rag-architect/references/rag-response-contract.md` §10, which you implement in app code.

---

## Batch Ingestion

```python
import logging
from weaviate.util import generate_uuid5

logger = logging.getLogger(__name__)
reviews = client.collections.use("ProductReview")   # multi-tenant: scoped(tenant_id)

with reviews.batch.fixed_size(batch_size=200) as batch:
    for item in items_to_insert:
        batch.add_object(
            properties={"text": item["text"], "source": item["source"],
                        "product_id": item["product_id"], "rating": item["rating"],
                        "embedding_model": settings.embedding_model},
            vector=item["vector"],                           # from the embedding chokepoint
            uuid=generate_uuid5(item["chunk_id"]),           # stable chunk id → retries overwrite
        )

# Read failures after EACH batch context exits (4.24.1 clears batch data per batch context)
failed = reviews.batch.failed_objects
if failed:
    logger.error("weaviate_batch_failed", extra={"failed": len(failed), "total": len(items_to_insert),
                                                 "first_uuid": str(failed[0].object_.uuid)})
    if len(failed) / max(len(items_to_insert), 1) > settings.max_ingest_failure_rate:
        raise RuntimeError("ingest failure rate above threshold")
```
Log ids and counts, not object text or raw error messages that may echo content.

---

## Collection Introspection

```python
exists = client.collections.exists("ProductReview")      # check before create — never recreate blindly

config = client.collections.use("ProductReview").config.get()
logger.info("collection_config", extra={
    "vector_config": str(config.vector_config),            # reading config is fine
    "multi_tenancy": config.multi_tenancy_config.enabled,
    "index_null_state": config.inverted_index_config.index_null_state,
})

for name in client.collections.list_all():
    logger.info("collection", extra={"name": name})

client.collections.delete("ProductReview")   # irreversible — gate behind an explicit confirmation
```
