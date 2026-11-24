# Weaviate Collection + RAG Pipeline

> **When to use**: Building semantic search or RAG with Weaviate as the vector database
> **Time estimate**: 2–4 hours for initial collection + pipeline; 30 min per additional collection
> **Prerequisites**: Weaviate Cloud account (or local instance), Python environment with `uv`

## Overview

End-to-end Weaviate workflow from quickstart onboarding through collection design, RAG pipeline scaffolding, review, and ongoing operations. Covers vectorizer selection, multi-tenancy, named vectors, and the 8 cookbook types for production AI applications.

---

## Phases

### Phase 1 — Quickstart / Onboarding

**Command**: `/weaviate:quickstart`
**Source**: `commands/weaviate/quickstart.md`
**Iron Law** (from `skills/weaviate/SKILL.md:16-19`): `ALWAYS LIST COLLECTIONS FIRST` before any operation

**6-step onboarding** (from `commands/weaviate/quickstart.md`):
1. Welcome & orientation — understand available commands
2. Sign up for Weaviate Cloud (if needed)
3. Verify prerequisites: Python, `uv` installed
4. Load data — choose: sample data, import own, empty collection, or skip
5. Test drive key commands: list, explore, search, ask
6. Plan next steps

**Configure credentials**:
```bash
export WEAVIATE_URL="https://<cluster>.weaviate.network"
export WEAVIATE_API_KEY="..."
export OPENAI_API_KEY="..."  # or COHERE_API_KEY, ANTHROPIC_API_KEY
```

**Gate**: `/weaviate:collections` returns list without error

---

### Phase 2 — Collection Design

**Command**: `/design-weaviate-collection [collection-name] [use-case]`
**Source**: `commands/design-weaviate-collection.md`
**Skill**: `vector-database` with Weaviate patterns reference
**Agent**: `weaviate-schema-reviewer` (after generation)

**7-step process** (from `commands/design-weaviate-collection.md`):
1. Load vector-database skill
2. Gather requirements:
   - Collection name (PascalCase)
   - Use case (determines vectorizer)
   - Distance metric (`cosine` / `l2-squared` / `dot`)
   - Multi-tenancy? (enables tenant isolation)
   - Named vectors? (multiple vector spaces per object)
   - Generative RAG? (requires generative module config)
3. Generate collection code with:
   - Python client v4 API (`import weaviate`)
   - API keys from env vars — never hardcoded
   - `client.close()` in `finally` block
   - Explicit property definitions with data types
4. Generate helper functions:
   - `create_if_not_exists()` — idempotent creation
   - `batch_insert()` — efficient bulk ingestion
   - Query examples (semantic, hybrid, BM25)
5. Run `weaviate-schema-reviewer` agent
6. Save to appropriate location
7. Report generated files and findings

**Vectorizer selection guide**:

| Vectorizer | When to use |
|-----------|------------|
| `text2vec-openai` | General text, high quality |
| `text2vec-cohere` | Multilingual, cost-effective |
| `text2vec-transformers` | Self-hosted, no API cost |
| `multi2vec-clip` | Images + text |
| `none` | Bring your own vectors |

**Named vectors** (when to use): When objects need multiple semantic representations (e.g., `title_vector` + `body_vector` searched independently)

**Multi-tenancy**: Enable from creation if data is tenant-scoped — cannot be added after collection exists

**Produces**: Python collection creation code with helpers
**Gate**: `weaviate-schema-reviewer` passes; collection creates without error

---

### Phase 3 — RAG Pipeline Scaffold

**Command**: `/scaffold-rag-pipeline [pipeline-name] weaviate [use-case]`
**Source**: `commands/scaffold-rag-pipeline.md`
**Skill**: `vector-database` + `weaviate-cookbooks`
**Agent**: `rag-implementation-reviewer`

**Select cookbook type** (from `skills/weaviate-cookbooks/SKILL.md`):

| Cookbook | Use case |
|----------|---------|
| Query Agent chatbot | Conversational search over collections |
| Data explorer | Browse and explore collection data |
| Multimodal PDF RAG | PDF documents with images |
| Basic RAG | Simple retrieval-augmented generation |
| Advanced RAG | Multi-stage retrieval with reranking |
| Agentic RAG | LangChain/LangGraph + Weaviate retrieval |
| DSPy tool-calling | DSPy-optimized prompts + Weaviate tools |
| Hybrid search | BM25 + vector combined |

**Iron Law** (from `skills/weaviate-cookbooks/SKILL.md:16-19`): `READ setup.md AND environment_requirements.md BEFORE GENERATING CODE`

**Generated pipeline files**:
```
src/<pipeline-name>/
├── collection.py           # Collection creation and management
├── ingestion.py            # Batch ingestion with vectorizer
├── retriever.py            # Semantic/hybrid/BM25 search
├── generator.py            # Generative RAG (if applicable)
├── pipeline.py             # Orchestration
└── tests/
```

**Produces**: Complete Weaviate-backed RAG pipeline
**Gate**: `rag-implementation-reviewer` passes; end-to-end pipeline test succeeds

---

### Phase 4 — Schema Review

**Agent 1**: `weaviate-schema-reviewer` (sonnet)
- Vibe: *"Multi-tenancy and vectorizer mismatches corrupt collections — caught here first"*
- Checks: vectorizer validity, multi-tenancy flag, distance metric correctness, no hardcoded API keys, named vector consistency, Python client v4 API correctness

**Agent 2**: `rag-implementation-reviewer`
- Checks: embedding model pinned, chunking strategy justified, reranking present for production, null guards on retrieval, error handling on Weaviate API calls

**Gate**: Both agents pass; zero CRITICAL findings

---

### Phase 5 — Operations

**List collections**:
```
/weaviate:collections
```
Returns: collection names, object counts, vectorizer config

**Explore a collection**:
```
/weaviate:explore [collection-name] limit 20
```
Returns: object count, property statistics, sample objects

**Semantic search**:
```
/weaviate:search query "your search text" collection "CollectionName" type semantic
```

**Hybrid search** (BM25 + vector):
```
/weaviate:search query "your search text" collection "CollectionName" type hybrid alpha 0.5
```
`alpha=1.0` = pure vector, `alpha=0.0` = pure BM25, `alpha=0.5` = balanced

**Natural language Q&A** (requires generative module):
```
/weaviate:ask query "What is the main theme?" collections "CollectionName"
```
Returns: AI-generated answer with source citations

**Filter and fetch**:
```
/weaviate:fetch collection "CollectionName" filters '{"path":["category"],"operator":"Equal","valueText":"news"}' limit 10
```

**Query Agent** (multi-collection natural language):
```
/weaviate:query query "find recent articles about AI" collections "Articles,News" limit 5
```

---

## Quick Reference

| Phase | Command/Agent | Produces | Gate |
|-------|--------------|----------|------|
| 1 — Onboarding | `/weaviate:quickstart` | Connected instance | Collections list succeeds |
| 2 — Design | `/design-weaviate-collection` + `weaviate-schema-reviewer` | Collection code | Agent passes |
| 3 — Pipeline | `/scaffold-rag-pipeline weaviate` + `rag-implementation-reviewer` | Pipeline files | Agent passes + tests pass |
| 4 — Review | `weaviate-schema-reviewer` + `rag-implementation-reviewer` | Findings | Zero CRITICAL |
| 5 — Operations | `/weaviate:search`, `/weaviate:ask`, `/weaviate:explore` | Query results | Live data returned |

---

## Common Pitfalls

- **Hardcoded API keys** — `weaviate-schema-reviewer` blocks this; always `os.getenv()`
- **Multi-tenancy after creation** — cannot be added retroactively; decide before creating collection
- **Vectorizer mismatch between index time and query time** — use same vectorizer for both ingestion and queries
- **Missing `client.close()`** — Weaviate v4 client holds connections; always close in `finally`
- **Using v3 client syntax with v4** — `weaviate.connect_to_weaviate_cloud()` / `connect_to_local()`, not `weaviate.Client()` (v3) or the deprecated `connect_to_wcs()`; run new code under `python -W error::DeprecationWarning` once to surface Dep0xx warnings
- **No error handling on `generate` calls** — generative module calls can fail; wrap in try/except with logging

## Related Workflows

- [`pgvector-rag-pipeline.md`](pgvector-rag-pipeline.md) — pgvector alternative
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — LangGraph agents with Weaviate retrieval
- [`embedding-model-migration.md`](embedding-model-migration.md) — migrate to new embedding model
- [`weaviate-operations.md`](weaviate-operations.md) — day-to-day Weaviate operations
