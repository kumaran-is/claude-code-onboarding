# Table Chunking Strategy

Reference for chunking tabular data in RAG pipelines. Standard text chunking destroys tables — this guide covers the correct approaches (§6 of the production RAG pipeline).

---

## 1. The Problem — Why Text Chunking Fails on Tables

Standard character/token chunking splits mid-row, losing the relationship between headers and values:

### ❌ Bad Split (Do Not Do This)

Original table:
```
| Service       | Response Time | Cost     |
|---------------|---------------|----------|
| Basic Support | 48 hours      | Included |
| Premium       | 4 hours       | $199/mo  |
| Enterprise    | 1 hour        | Custom   |
```

After naive 150-token chunking:
```
# Chunk A (ends mid-table)
| Service       | Response Time | Cost     |
|---------------|---------------|----------|
| Basic Support | 48 hours      | Included |

# Chunk B (no headers — unreadable without context)
| Premium       | 4 hours       | $199/mo  |
| Enterprise    | 1 hour        | Custom   |
```

Chunk B is **meaningless without the headers**. A model retrieving chunk B cannot answer "what is the Enterprise response time?" correctly — it has no column labels.

---

## 2. Strategy by Table Size

| Table Size | Strategy |
|---|---|
| Small (≤ 20 rows) | Single chunk — keep entire table together |
| Medium (21–100 rows) | Row-group chunking — N rows per chunk, header always repeated |
| Large (> 100 rows) | Structured summary + row-group chunks + JSON representation |

---

## 3. Small Tables — Single Chunk

Keep the entire table in one chunk. Include surrounding section heading as context.
```python
def chunk_small_table(table_text: str, section_heading: str) -> str:
    return f"Section: {section_heading}\n\n{table_text}"
```

**Metadata:** `content_type: table`, `table_row_count: N`, `table_row_range: "1-N"`

---

## 4. Row-Group Chunking (Medium Tables)

Split into groups of N rows. **Always repeat the header row** at the top of every chunk.

### ✅ Good Row-Group Chunk
```
# Chunk 1 — rows 1–10 (header repeated)
| Service       | Response Time | Cost     |
|---------------|---------------|----------|
| Basic Support | 48 hours      | Included |
| Premium       | 4 hours       | $199/mo  |
...

# Chunk 2 — rows 11–20 (header repeated — critical)
| Service       | Response Time | Cost     |
|---------------|---------------|----------|
| Enterprise    | 1 hour        | Custom   |
...
```

### Implementation
```python
def chunk_table_by_rows(
    headers: list[str],
    rows: list[list[str]],
    rows_per_chunk: int = 10,
    section_heading: str = "",
) -> list[str]:
    chunks = []
    header_row = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"

    for i in range(0, len(rows), rows_per_chunk):
        group = rows[i : i + rows_per_chunk]
        row_lines = ["| " + " | ".join(str(c) for c in row) + " |" for row in group]
        chunk_text = "\n".join([
            f"Section: {section_heading}" if section_heading else "",
            f"Rows {i+1}–{i+len(group)}:",
            header_row,
            separator,
            *row_lines,
        ])
        chunks.append(chunk_text.strip())
    return chunks
```

### Chunk Size Guidance
- 10 rows/chunk for tables with long cell values (descriptions, notes)
- 25 rows/chunk for tables with short cell values (numbers, codes, dates)
- Measure chunk token count; keep under embedding model limit

---

## 5. Multiple Representations (Large or Complex Tables)

For tables that serve both semantic search and structured lookup, store multiple representations:

```python
def store_table_multi_representation(table, metadata: dict) -> list[dict]:
    chunks = []

    # Representation 1: Plain text (semantic search)
    plain = table_to_plain_text(table)  # "Service: Basic Support, Response: 48h, Cost: Included"
    chunks.append({
        "text": plain,
        "content_type": "table_plain",
        **metadata,
    })

    # Representation 2: Markdown (display / citation)
    markdown = table_to_markdown(table)
    chunks.append({
        "text": markdown,
        "content_type": "table_markdown",
        **metadata,
    })

    # Representation 3: JSON (structured lookup)
    json_rows = [dict(zip(table.headers, row)) for row in table.rows]
    chunks.append({
        "text": json.dumps(json_rows, indent=2),
        "content_type": "table_json",
        **metadata,
    })

    return chunks
```

### When to Use Each Representation at Retrieval Time

| Query Type | Representation to Prefer |
|---|---|
| Semantic / conceptual ("what does X cover?") | `table_plain` |
| Display / citation ("show me the table") | `table_markdown` |
| Structured lookup ("what is the cost for Plan B?") | `table_json` or SQL |
| Comparison ("compare A and B") | `table_markdown` → LLM formats |

Filter at query time using `content_type` metadata:
```python
# For semantic questions, retrieve only plain text representations
filters = {"content_type": "table_plain", **tenant_filters}
results = retrieve(query, metadata_filter=filters)
```

---

## 6. Metadata Schema for Table Chunks

Extend the standard chunk metadata schema with table-specific fields:

| Field | Value | Purpose |
|---|---|---|
| `content_type` | `table`, `table_plain`, `table_markdown`, `table_json` | Representation filter at retrieval |
| `table_row_range` | `"1-10"`, `"11-20"` | Context for partial chunks |
| `table_row_count` | integer | Total rows in original table |
| `table_column_count` | integer | Column count |
| `table_headers` | `["Service", "Cost", "SLA"]` | Headers as JSON array |
| `parent_table_id` | uuid | Groups all chunks from one table |

---

## 7. Parsing Tables from Source Documents

### From PDF (LiteParse local, LlamaParse hosted)
Digital tables: try **LiteParse** first (local, no API key). Scans / merged cells / structured extract: **LlamaParse** (`llama-cloud>=2.8`) only after explicit approval for data processing, credentials, and cost. Deprecated: `from llama_parse import LlamaParse`. Fallback: Camelot or pdfplumber for simpler tables. Full decision: `llamaindex/references/parse-choice.md`.

```python
# Local default
from liteparse import LiteParse
from llama_index.core import Document

local = LiteParse(output_format="markdown")
parsed = local.parse("document.pdf")
documents = [Document(text=parsed.text, doc_id=stable_id)]

# Hosted — BLOCK without approval
# from llama_cloud import LlamaCloud
# client = LlamaCloud()  # LLAMA_CLOUD_API_KEY
# file = client.files.create(file="document.pdf", purpose="parse")
# result = client.parsing.parse(file_id=file.id, tier="agentic", version="latest", expand=["markdown"])
```

### From Markdown
```python
import re

def extract_tables_from_markdown(text: str) -> list[str]:
    # Match markdown table blocks
    pattern = r'(\|.+\|\n\|[-|: ]+\|\n(?:\|.+\|\n)*)'
    return re.findall(pattern, text)
```

### From HTML
```python
from bs4 import BeautifulSoup
import pandas as pd

def extract_tables_from_html(html: str) -> list[pd.DataFrame]:
    return pd.read_html(html)  # returns list of DataFrames
```

---

## 8. Common Mistakes

| Mistake | Why It's Wrong | Fix |
|---|---|---|
| Splitting table at token boundary | Headers lost from subsequent chunks | Use row-group strategy with header repeat |
| Storing only markdown representation | Semantic search misses cells that don't match query | Store plain text variant too |
| Using auto-increment chunk IDs for table rows | IDs change on re-ingest; golden set breaks | Use `{doc_id}-table{table_idx}-rows{start}-{end}` |
| Ignoring `content_type` at retrieval | JSON representation retrieved for semantic questions | Filter by `content_type` per query class |
| Not including section heading in table chunk | "What is the Premium SLA?" → retriever finds chunk but no context for what table it describes | Always prepend section heading |
