# Weaviate Operations

> **When to use**: Day-to-day Weaviate operations — listing collections, searching, exploring data, running Q&A queries
> **Time estimate**: Minutes per operation
> **Prerequisites**: Weaviate instance accessible; `WEAVIATE_URL` and `WEAVIATE_API_KEY` configured

## Overview

Weaviate day-to-day operations using the `weaviate` skill and the Weaviate slash command suite. Covers collection management, semantic search, hybrid search, natural language Q&A, and filtered fetching.

---

## Iron Law (from `skills/weaviate/SKILL.md`)

> **ALWAYS LIST COLLECTIONS FIRST** before any operation — confirm the target collection exists and check its vectorizer config before querying or modifying it.

---

## Environment Setup

```bash
export WEAVIATE_URL="https://<cluster>.weaviate.network"
export WEAVIATE_API_KEY="..."
export OPENAI_API_KEY="..."    # or COHERE_API_KEY, ANTHROPIC_API_KEY
```

---

## Operation Reference

### List Collections
```
/weaviate:collections
```
Returns: collection names, object counts, vectorizer config for each.

**Gate**: Run this first, every time. Confirms connection and shows what's available.

```
Example output:
Collections (3):
- Articles (12,450 objects) — text2vec-openai
- Products (8,200 objects) — text2vec-cohere
- Documents (3,100 objects) — text2vec-transformers
```

---

### Explore a Collection
```
/weaviate:explore [collection-name] limit 20
```
Returns: object count, property statistics, sample objects.

**When to use**: Before searching — understand the data shape and what properties are available.

```
/weaviate:explore Articles limit 5
```

---

### Semantic Search (Vector)
```
/weaviate:search query "your search text" collection "CollectionName" type semantic
```

**Example**:
```
/weaviate:search query "electric vehicle charging infrastructure" collection "Articles" type semantic
```

Returns: Top results ranked by vector similarity with distance scores.

**Under the hood** (from `weaviate` skill):
```python
collection = client.collections.get("Articles")
results = collection.query.near_text(
    query="electric vehicle charging infrastructure",
    limit=10,
    return_metadata=MetadataQuery(distance=True)
)
```

---

### Hybrid Search (BM25 + Vector)
```
/weaviate:search query "your search text" collection "CollectionName" type hybrid alpha 0.5
```

**Alpha parameter**:
- `alpha=1.0` = pure vector search
- `alpha=0.0` = pure BM25 keyword search
- `alpha=0.5` = balanced hybrid (recommended starting point)

**When to use hybrid**:
- Domain-specific terminology (product codes, proper nouns) that benefits from exact keyword matching
- Queries that mix semantic intent with specific terms

```
/weaviate:search query "Model 3 range per charge" collection "Products" type hybrid alpha 0.7
```

---

### BM25 Keyword Search
```
/weaviate:search query "exact term or phrase" collection "CollectionName" type keyword
```

**When to use**: When exact term matching is more important than semantic similarity (e.g., serial numbers, codes).

---

### Natural Language Q&A (Generative RAG)
```
/weaviate:ask query "What is the main theme?" collections "CollectionName"
```

**Requirements**: Collection must have a generative module configured (e.g., `generative-openai`).

Returns: AI-generated answer with source citations.

```
/weaviate:ask query "What are the key differences between IVFFlat and HNSW?" collections "Articles"
```

**Under the hood**:
```python
response = collection.generate.near_text(
    query="IVFFlat vs HNSW differences",
    grouped_task="Summarize the key differences based on the retrieved documents",
    limit=5
)
print(response.generated)  # AI answer
for obj in response.objects:
    print(obj.properties["title"])  # Source documents
```

---

### Filter and Fetch
```
/weaviate:fetch collection "CollectionName" filters '{"path":["category"],"operator":"Equal","valueText":"news"}' limit 10
```

**Filter operators**: `Equal`, `NotEqual`, `GreaterThan`, `LessThan`, `Like`, `ContainsAny`, `ContainsAll`

**Example — fetch recent articles**:
```
/weaviate:fetch collection "Articles" filters '{"path":["publishedAt"],"operator":"GreaterThan","valueDate":"2026-01-01T00:00:00Z"}' limit 20
```

---

### Query Agent (Multi-Collection)
```
/weaviate:query query "find recent articles about AI safety" collections "Articles,News" limit 5
```

The Query Agent:
- Understands natural language queries
- Can search across multiple collections
- Handles complex multi-step queries
- Returns results with explanations

**When to use**: Complex queries that span collections or need reasoning about which collection to search.

---

## Python Client Operations (Direct)

For operations not covered by slash commands:

```python
import weaviate
import weaviate.classes as wvc
import os

# Connect (v4 client: connect_to_weaviate_cloud; connect_to_wcs is deprecated since 4.6.2, weaviate.Client() is v3)
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=os.environ["WEAVIATE_URL"],
    auth_credentials=wvc.init.Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
)

try:
    # List collections
    collections = client.collections.list_all()
    print([c.name for c in collections.values()])

    # Delete a collection (DESTRUCTIVE — confirm first)
    client.collections.delete("OldCollection")

    # Get collection stats
    collection = client.collections.get("Articles")
    agg = collection.aggregate.over_all(total_count=True)
    print(f"Total objects: {agg.total_count}")

finally:
    client.close()  # Always close — v4 client holds connections
```

---

## Quick Reference

| Operation | Command | Notes |
|-----------|---------|-------|
| List collections | `/weaviate:collections` | Always run first |
| Explore data | `/weaviate:explore [name] limit N` | Check schema before searching |
| Semantic search | `/weaviate:search ... type semantic` | Vector similarity |
| Hybrid search | `/weaviate:search ... type hybrid alpha 0.5` | BM25 + vector |
| Keyword search | `/weaviate:search ... type keyword` | Exact term matching |
| Q&A | `/weaviate:ask query "..." collections "..."` | Requires generative module |
| Filtered fetch | `/weaviate:fetch collection "..." filters '...'` | Structured retrieval |
| Multi-collection | `/weaviate:query query "..." collections "A,B"` | Cross-collection agent |

---

## Common Pitfalls

- **Not listing collections first** — searching a non-existent collection returns a confusing error
- **Alpha=1.0 (pure vector) for keyword-heavy queries** — product codes and serial numbers match better with BM25; use hybrid
- **Missing generative module** — `/weaviate:ask` requires the collection to have `generative-openai` or equivalent configured at creation
- **Using v3 or deprecated v4 connect calls** — `weaviate.Client()` is v3 and `weaviate.connect_to_wcs()` is deprecated; use `weaviate.connect_to_weaviate_cloud()` / `connect_to_local()` (weaviate-client 4.24.1, server ≥ 1.27.0). `graphql_raw_query()` is deprecated (Dep031): use the typed `query.*` API
- **Forgetting `client.close()`** — v4 client holds gRPC connections; always close in `finally`

## Related Workflows

- [`weaviate-collection-pipeline.md`](weaviate-collection-pipeline.md) — creating collections and RAG pipelines
- [`embedding-model-migration.md`](embedding-model-migration.md) — migrating collection to new model
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — integrating Weaviate retrieval with LangGraph
