---
name: llamaindex
description: "Use when implementing LlamaIndex RAG with document loading, IngestionPipeline, VectorStoreIndex, node parsers, LiteParse, or LlamaParse. Official ingest, index, and retrieve APIs. Triggers: LlamaIndex, IngestionPipeline, VectorStoreIndex, LlamaParse, LiteParse, SimpleDirectoryReader, SentenceSplitter, Node parser."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
last-reviewed: "2026-11-27"
metadata:
  triggers: LlamaIndex, IngestionPipeline, VectorStoreIndex, LlamaParse, LiteParse, SimpleDirectoryReader, SentenceSplitter, Node parser
  related-skills: rag-architect, vector-database, rag-security-reviewer, google-adk, agentic-ai-dev
---

# LlamaIndex RAG

## Iron Law

**Verify every LlamaIndex API against https://developers.llamaindex.ai/python/framework/ (or `llms.txt` / `/api/`). Never enable hosted LlamaParse without explicit approval for data processing, credentials, and cost. When ADK generates the answer, use the LlamaIndex retriever only — never `as_query_engine()` plus an ADK `LlmAgent`.**

Shared lifecycle (chunking numbers, ACL, citations, abstention, evals): `rag-architect`. This skill is **framework APIs only**. Selection: `rag-architect/references/framework-selection.md` and `scripts/select_rag_framework.py`.

## Versions (2026-11-27)

| Package | Pin / constraint | Notes |
|---|---|---|
| `llama-index-core` | 0.14.x (`>=3.11,<4.0`; 3.14 OK) | `Document`, `Node`, `IngestionPipeline`, `VectorStoreIndex` |
| `liteparse` | local parser, no API key | Default for on-machine PDF/Office |
| `llama-cloud` | `>=2.8` | Hosted LlamaParse. **Approval required.** |
| Vector stores | `llama-index-vector-stores-postgres`, `llama-index-vector-stores-weaviate` | Align dims with `vector-database` |

Deprecated: `llama-parse`, `llama-cloud-services`, `from llama_parse import LlamaParse`.

Docs: https://developers.llamaindex.ai/home/ · loading · ingestion_pipeline · querying · observability. Do not add a LlamaIndex MCP server to this toolkit; ask the user if they want `https://developers.llamaindex.ai/mcp` in a **product** repo.

## Load order

1. `rag-architect/SKILL.md` (contract) + `references/framework-selection.md` if `framework=` is unset.
2. This file.
3. Deep refs as needed: `references/parse-choice.md`, `references/ingestion-and-retrieval.md`, `references/adk-tool-wrap.md`.
4. Store/ACL: `vector-database`, `rag-security-reviewer`.

## Decision tree

```
framework=llamaindex (or auto selected it)?
  NO  → stop; use google-adk or agentic-ai-dev
  YES → parser (parse-choice.md)
        ordinary digital text → SimpleDirectoryReader / built-in readers
        local PDF/Office / data-must-stay-local → LiteParse
        scans, dense tables, structured extract → LlamaParse ONLY after approval
      → IngestionPipeline (transformations, cache, docstore, vector_store)
      → VectorStoreIndex.from_vector_store
      → retriever + MetadataFilters from auth context
      → generate: query engine (LlamaIndex-only) OR ADK/LangChain wrap (retriever only)
```

## Official loading

```python
from llama_index.core import Document, SimpleDirectoryReader

docs = SimpleDirectoryReader("./data").load_data()
doc = Document(
    text=page_text,
    doc_id="policy:refunds:v3",  # stable; never a random uuid per ingest
    metadata={
        "tenant_id": tenant_id,  # from source register, not the file name alone
        "acl": tenant_id,
        "document_id": "policy:refunds",
        "document_version": "3",
        "is_active": True,
        "embedding_model": embed_model.model_name,
    },
)
```

LiteParse / LlamaParse → `Document(text=...)`: `references/parse-choice.md`.

## Official ingestion

https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/

```python
from llama_index.core.embeddings.mock_embed_model import MockEmbedding  # tests only
from llama_index.core.ingestion import IngestionPipeline, IngestionCache
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore

pipeline = IngestionPipeline(
    transformations=[
        SentenceSplitter(chunk_size=512, chunk_overlap=64),  # cap: rag-architect overlap rule
        embed_model,  # required if vector_store= is set
    ],
    vector_store=vector_store,
    cache=IngestionCache(),
    docstore=SimpleDocumentStore(),  # doc_id + hash upsert / skip
)
nodes = pipeline.run(documents=docs)
# async: nodes = await pipeline.arun(documents=docs)
# persist cache: pipeline.persist("./pipeline_storage")
```

Chunk size still obeys `rag-architect` (final chunk ≤ reranker window minus query). `TitleExtractor` and other LLM extractors need a live model — do not add them in tests; skip unless the product approved the extra LLM cost.

## Official retrieval (not a second ACL story)

```python
from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import (
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)

index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
filters = MetadataFilters(
    filters=[
        MetadataFilter(key="tenant_id", value=ctx.tenant_id, operator=FilterOperator.EQ),
        MetadataFilter(key="is_active", value=True, operator=FilterOperator.EQ),
        MetadataFilter(key="embedding_model", value=embed_model.model_name, operator=FilterOperator.EQ),
    ],
)
retriever = index.as_retriever(similarity_top_k=50, filters=filters)
nodes = retriever.retrieve(query)
```

`ctx.tenant_id` comes from the verified principal (`rag-security-reviewer`). Never from the user message or tool args. pgvector filtered-ANN caveat still applies.

Hybrid / rerank: use LlamaIndex retrievers + node postprocessors when the store supports them; otherwise the same hybrid/RRF chokepoint as `vector-database/references/rag-pipeline-patterns.md`. Provenance: cite `node.node_id` / `node.ref_doc_id` only.

## Grounded generation

**LlamaIndex-only service:** `index.as_query_engine(...)` (response synthesizer) + runtime citation check (`rag-architect/scripts/response_contract.py`). Empty retrieval → do not call the synthesizer; return `NOT_FOUND` / `INSUFFICIENT_EVIDENCE`.

**ADK or LangChain owns generation:** `as_retriever` only. Wrap: `references/adk-tool-wrap.md`.

Retrieved text is untrusted data. Do not interpolate it into an ADK `instruction`.

## Observability and evals

Reuse Langfuse / OpenTelemetry / RAGAS / DeepEval from `eval-guide` and `deployment-ci-cd/reference/ai-observability.md`. LlamaIndex instrumentation (`llama_index.core.instrumentation`) may attach to the same tracer; do not stand up a second eval stack. Golden sets: `/rag-eval-init`.

## Reviewer checks (no new agent)

`rag-implementation-reviewer` plus:

- [ ] `framework=` is `llamaindex` (or auto-selected with recorded reasons)
- [ ] No `from llama_parse import LlamaParse`
- [ ] LlamaParse / `LlamaCloud` behind an approval record
- [ ] `IngestionPipeline` transformations, not a one-off split/embed loop (unless compatibility)
- [ ] `MetadataFilters` (or store-native equivalent) from auth context
- [ ] One generation path
- [ ] Tests distinguish STATIC / MOCKED / INTEGRATION / LIVE-PROVIDER

## Reference files

| File | When |
|---|---|
| `references/parse-choice.md` | LiteParse vs LlamaParse vs built-in readers |
| `references/ingestion-and-retrieval.md` | Pipeline, indexes, filters, postprocessors, deletes |
| `references/adk-tool-wrap.md` | Expose this retriever to Google ADK without dual generation |
