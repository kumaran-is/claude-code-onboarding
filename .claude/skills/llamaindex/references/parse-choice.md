# Parser choice — built-in readers, LiteParse, LlamaParse

Official: [Loading](https://developers.llamaindex.ai/python/framework/module_guides/loading/), [LiteParse getting started](https://developers.llamaindex.ai/liteparse/getting_started/), [LlamaParse getting started](https://developers.llamaindex.ai/llamaparse/parse/getting_started/).

Do not enable hosted LlamaParse in scaffolded code until the user approves (1) sending documents to LlamaCloud, (2) storing `LLAMA_CLOUD_API_KEY`, (3) usage cost.

## Decision

```
ordinary markdown/html/text → SimpleDirectoryReader / built-in readers
digital PDF or Office, local/offline, or data-must-stay-local → LiteParse
scans, handwriting, dense tables, charts, schema extract → LlamaParse
                                            └── no approval → LiteParse + record the quality risk
```

The selector encodes this: `select_rag_framework.py` `parser` field.

## Built-in readers

```python
from llama_index.core import SimpleDirectoryReader

docs = SimpleDirectoryReader(
    "./data",
    filename_as_id=True,  # still stamp tenant/ACL from the source register
).load_data()
```

Use for markdown, HTML, plain text, and simple digital PDFs where layout does not carry meaning. Not for table-heavy or scanned files (`rag-review` check 1.1).

## LiteParse (local, no API key)

Install in the **product** project (`uv add liteparse`), never globally on the toolkit machine.

```python
from liteparse import LiteParse
from llama_index.core import Document

parser = LiteParse(output_format="markdown")  # "text" | "json" | "markdown"
result = parser.parse("policy.pdf")  # path or bytes
doc = Document(
    text=result.text,
    doc_id=stable_doc_id,
    metadata={"parser": "liteparse", "parser_version": "liteparse", "pages": result.total_pages},
)
```

Office formats need LibreOffice on the host. Images use native conversion (v2.8+). Optional OCR: `LiteParse(ocr_enabled=True, ...)` — still local.

Start here for latency-sensitive and air-gapped corpora. If evals show tables/scans failing, escalate to LlamaParse with approval — do not silently switch.

## LlamaParse (hosted, approval-gated)

Deprecated: `pip install llama-parse` / `from llama_parse import LlamaParse` / `llama-cloud-services`.

Current (https://developers.llamaindex.ai/llamaparse/parse/getting_started/):

```python
from llama_cloud import LlamaCloud
from llama_index.core import Document

# BLOCK unless llamaparse_approved=true in the ADR and LLAMA_CLOUD_API_KEY is provisioned
client = LlamaCloud()  # reads LLAMA_CLOUD_API_KEY
uploaded = client.files.create(file="./scan.pdf", purpose="parse")
parsed = client.parsing.parse(
    file_id=uploaded.id,
    tier="agentic",
    version="latest",
    expand=["markdown"],
)
text = "\n\n".join(page.markdown for page in parsed.markdown.pages)
doc = Document(text=text, doc_id=stable_doc_id, metadata={"parser": "llamaparse"})
```

Never hard-code the API key. Never parse tenant documents in a shared cloud project without a tenancy story. Treat parse output as untrusted (prompt injection in PDFs).

## Mapping onto the shared ingest checklist

After any parser, the rest of ingestion is framework-neutral: sanitize, envelope, hash, embed (`vector-database/references/rag-ingest-checklist.md`). LlamaIndex `IngestionPipeline` is the place those transformations run (`ingestion-and-retrieval.md`).
