---
name: weaviate
description: "Search, query, and manage Weaviate vector database collections. Use when running semantic search, hybrid search, keyword search, natural language Q&A with source citations, collection schema inspection, data exploration, filtered fetching, bulk imports, or creating example data. Triggers: 'Weaviate', 'vector search', 'hybrid search', 'semantic search', 'Query Agent', 'collection management', 'import data', 'explore collection'."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: Weaviate, vector search, hybrid search, semantic search, Query Agent, collection management, data import, explore collection, keyword search
  related-skills: vector-database, weaviate-cookbooks, agentic-ai-dev
  domain: backend
  role: specialist
  scope: query
  output-format: results
last-reviewed: "2026-03-15"
---

# Weaviate Database Operations

## Iron Law

**ALWAYS LIST COLLECTIONS FIRST — never assume collection names or schemas exist.**

Running any search or import against a non-existent collection returns a cryptic error. `list_collections.py` takes under 1 second and prevents every "collection not found" failure.

## Process

1. **List collections** — discover what exists before any operation
2. **Ask user** — confirm which collection(s) to target, or offer example data if empty
3. **Get collection details** — inspect schema, vectorizer, multi-tenancy status
4. **Explore collection** — check data distribution and sample objects
5. **Run operation** — search, import, fetch, or ask

## Script Index

| Script | Command | When to Use |
|--------|---------|-------------|
| `ask.py` | `uv run scripts/ask.py` | AI-generated answer with source citations across collections |
| `query_search.py` | `uv run scripts/query_search.py` | Browse raw objects across collections (no synthesis) |
| `hybrid_search.py` | `uv run scripts/hybrid_search.py` | **Default search** — BM25 + vector, balanced recall |
| `semantic_search.py` | `uv run scripts/semantic_search.py` | Conceptual similarity, intent matters more than keywords |
| `keyword_search.py` | `uv run scripts/keyword_search.py` | Exact terms, IDs, SKUs, specific text patterns |
| `list_collections.py` | `uv run scripts/list_collections.py` | Discover all collections in the instance |
| `get_collection.py` | `uv run scripts/get_collection.py --name NAME` | Schema, vectorizer config, multi-tenancy status |
| `explore_collection.py` | `uv run scripts/explore_collection.py NAME` | Data distribution, top values, sample objects |
| `create_collection.py` | `uv run scripts/create_collection.py` | Create collection with custom schema |
| `fetch_filter.py` | `uv run scripts/fetch_filter.py` | Retrieve by ID or structured filter criteria |
| `import.py` | `uv run scripts/import.py data.csv --collection NAME` | Bulk import from CSV, JSON, or JSONL |
| `example_data.py` | `uv run scripts/example_data.py` | Load toy data when no real data exists |

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `references/ask.md` | Query Agent ask mode — answer synthesis, source citation format | Building Q&A interfaces |
| `references/query_search.md` | Query Agent search mode — raw object retrieval | Browsing/exploring objects |
| `references/hybrid_search.md` | Hybrid BM25 + vector, alpha tuning, fusion types | General-purpose search |
| `references/semantic_search.md` | nearText query patterns, distance thresholds | Conceptual/intent-based search |
| `references/keyword_search.md` | BM25 patterns, tokenization, exact match | Keyword/ID/SKU lookup |
| `references/list_collections.md` | Collection discovery, schema overview | Discovery step |
| `references/get_collection.md` | Schema inspection, vectorizer config, properties | Pre-query schema check |
| `references/explore_collection.md` | Data stats, value distribution, sample objects | Understanding data shape |
| `references/create_collection.md` | Collection creation, properties, vectorizer config | Schema design |
| `references/fetch_filter.md` | ID fetch, `where` filter, structured retrieval | Precise data retrieval |
| `references/import_data.md` | Batch import, error handling, UUID strategy | Data ingestion |
| `references/example_data.md` | Pre-built toy datasets | Demos, testing |
| `references/environment_requirements.md` | All env vars and provider keys | Environment setup |

## Environment Variables

**Required:**
- `WEAVIATE_URL` — Weaviate Cloud cluster URL
- `WEAVIATE_API_KEY` — Weaviate API key

**External provider keys** (set only what your collections use):
→ See `references/environment_requirements.md` for the full list.

If the user has no Weaviate instance, direct them to [Weaviate Cloud](https://console.weaviate.cloud/) to create a free sandbox, then run `/weaviate:quickstart`.

## Documentation Sources

Before generating code, consult these sources for current APIs:

| Source | Tool | Purpose |
|--------|------|---------|
| Weaviate Python v4 | `weaviate-docs` MCP | Collection creation, query APIs, vectorizer config |
| Weaviate general docs | `weaviate-docs` MCP | Best practices, multi-tenancy, named vectors |
| Python client fallback | `Context7` MCP | `weaviate-client` package, async patterns |

## Output Formats

All scripts support `--json` flag. Default output is markdown tables.

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `WEAVIATE_URL not set` | Missing env var | Export env var in terminal |
| `Collection not found` | Wrong name or not yet created | Run `list_collections.py` first |
| `Authentication error` | Bad API key | Check both Weaviate key and vectorizer provider key |
| `Dimension mismatch` | Collection vectorizer ≠ query vectorizer | Match vectorizer on import and query |

## Post-Code Review

After writing Weaviate code, dispatch:
- `weaviate-schema-reviewer` — collection schema, v4 API, multi-tenancy, distance metric
- `rag-implementation-reviewer` — if building a retrieval pipeline
