# Hybrid Search

Combines vector similarity and keyword (BM25) matching for balanced search results on a single collection.

> **Self-provided vectors:** this script sends only the query text. On a collection created with `Configure.Vectors.self_provided()` (no server vectorizer) the vector leg has nothing to search and results are keyword-only, with no error. Use it on collections with a server-side vectorizer; for self-provided vectors call `collection.query.hybrid(query=q, vector=embed_query(q))` from application code. Multi-tenant collections also need `.with_tenant(...)`, which this script does not set.

## Usage

```bash
uv run scripts/hybrid_search.py --query "USER_QUERY" --collection "CollectionName" [--alpha 0.7] [--limit 10] [--properties "prop1,prop2"] [--target-vector "vector_name"] [--json]
```

## Parameters

| Parameter | Flag | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--query` | `-q` | Yes | — | Search query text |
| `--collection` | `-c` | Yes | — | Collection name |
| `--alpha` | `-a` | No | `0.7` | Balance between vector (1.0) and keyword (0.0) |
| `--limit` | `-l` | No | `10` | Maximum number of results |
| `--properties` | `-p` | No | all | Comma-separated properties to search |
| `--target-vector` | `-t` | No | — | Target vector name for named vector collections |
| `--json` | — | No | `false` | Output in JSON format |

## Output

- **Default**: Markdown table with object properties and score
- **JSON**: Array of objects with properties and search metadata

## Examples

Basic hybrid search:

```bash
uv run scripts/hybrid_search.py --query "climate change effects" --collection "Articles"
```

Keyword-heavy search (lower alpha):

```bash
uv run scripts/hybrid_search.py --query "product SKU-1234" --collection "Products" --alpha 0.3
```

Search specific properties with named vector:

```bash
uv run scripts/hybrid_search.py --query "renewable energy" --collection "Papers" --properties "title,abstract" --target-vector "title_vector"
```

