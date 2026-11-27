# LlamaIndex ingestion, index, retrieval

Official: [IngestionPipeline](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/), [Querying](https://developers.llamaindex.ai/python/framework/module_guides/querying/), [Observability](https://developers.llamaindex.ai/python/framework/module_guides/observability/).

Chunk sizes, overlap, hybrid/RRF, and ACL rules are **not** redefined here — `rag-architect` + `rag-security-reviewer` + `vector-database`.

## Transformations (do not invent a parallel pipeline)

`IngestionPipeline` applies a list of `Transformations` (node parsers, extractors, embedding models). Each node+transformation pair is hashed and cached.

```python
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline, IngestionCache
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore

pipeline = IngestionPipeline(
    transformations=[
        SentenceSplitter(chunk_size=512, chunk_overlap=64),
        embed_model,  # mandatory when vector_store= is set
    ],
    vector_store=vector_store,
    cache=IngestionCache(),
    docstore=SimpleDocumentStore(),
)
nodes = pipeline.run(documents=documents)           # sync
nodes = await pipeline.arun(documents=documents)    # async
pipeline.persist("./pipeline_storage")              # local cache + docstore
pipeline.run(documents=documents, num_workers=4)    # multiprocessing; measure before using
```

Remote cache backends documented by LlamaIndex: `RedisCache`, `MongoDBCache`, `FirestoreCache` via `IngestionCache(cache=...)`. Prefer the product's existing Redis/Postgres — do not add a new cache product for ingest.

## Document management (idempotent upsert)

Attach a `docstore`. LlamaIndex maps `doc_id` → content hash:

- Same `doc_id`, same hash → skip
- Same `doc_id`, different hash, `vector_store` attached → re-process and upsert
- Deletes: remove from docstore **and** vector store, then probe-retrieve (`versioning-and-freshness.md` §8). Soft-delete with `is_active=false` plus a retrieval filter is the shared default.

Set `Document.doc_id` yourself. Random ids per run duplicate vectors.

## Indexes and stores

```python
from llama_index.core import VectorStoreIndex

index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
```

pgvector / Weaviate: use the official LlamaIndex vector-store integrations **and** the kit schema rules (dims, `embedding_model` stamp, tenant column / Weaviate tenant, null guard). Do not create a second embedding chokepoint — wrap the LlamaIndex embedding model around `vector-database` `EmbeddingService`, or implement `BaseEmbedding` as an adapter over that service.

`VectorStoreIndex.from_documents` is fine for tests (`MockEmbedding`). Production ingest goes through `IngestionPipeline` so cache and docstore work.

## Retrieval, filters, postprocessors

```python
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters
from llama_index.core.postprocessor import SimilarityPostprocessor

filters = MetadataFilters(
    filters=[
        MetadataFilter(key="tenant_id", value=ctx.tenant_id, operator=FilterOperator.EQ),
        MetadataFilter(key="is_active", value=True, operator=FilterOperator.EQ),
    ],
)
retriever = index.as_retriever(similarity_top_k=50, filters=filters)
nodes = retriever.retrieve(query)
# optional: SimilarityPostprocessor / a pinned cross-encoder rerank on the ORIGINAL query
```

If the store's metadata filter is not applied as a pre-filter (some simple stores filter in process), that is a **review finding** for production. Tests may still assert a chokepoint that drops mismatched `tenant_id`.

Source provenance: keep `node.node_id`, `node.ref_doc_id`, score, and metadata on the packed context. Citation validation uses those ids (`response_contract.py`).

## Query engine vs retriever

| Product shape | API | Generation owner |
|---|---|---|
| LlamaIndex service | `index.as_query_engine(...)` | LlamaIndex response synthesizer |
| ADK agent | `index.as_retriever(...)` only | ADK `LlmAgent` |
| LangGraph pipeline | retriever → evidence gate → `llm.invoke` | LangGraph node |

Empty nodes → abstain in **code**. Do not ask a synthesizer to "say you don't know".

## Observability

Attach the existing OpenTelemetry tracer. LlamaIndex `llama_index.core.instrumentation.get_dispatcher()` can emit spans for ingest, retrieve, postprocess, and synthesize. Span names must stay bounded (`ai-observability.md`). Do not log raw chunk text at info in production.

Evals stay `/rag-eval-init` / RAGAS / DeepEval. A LlamaIndex eval helper is optional glue, not a second golden-set format.
