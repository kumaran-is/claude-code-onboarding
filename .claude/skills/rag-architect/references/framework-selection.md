# RAG framework selection — three choices, one lifecycle

Canonical selector for this toolkit. The RAG **contract** (ACL-in-query, citations, abstention, versioned ingestion, evals, traces) lives in `rag-architect/SKILL.md`. This file only chooses **which official APIs implement that contract**.

Selectable values: `framework=auto|google-adk|llamaindex|langchain`.

There is **no fourth selectable framework**. Existing plain-Python / SQL pipelines stay as a **compatibility path** when a repo already has them; `/scaffold-rag-pipeline` does not offer "custom Python" as a new choice.

Run the deterministic scorer:

```bash
python3 .claude/skills/rag-architect/scripts/select_rag_framework.py --selftest
python3 .claude/skills/rag-architect/scripts/select_rag_framework.py --requirements req.json
```

## Official sources (verify before coding)

| Framework | Docs | Kit pin / compatibility |
|---|---|---|
| Google ADK | https://google.github.io/adk-docs/ | `google-adk==2.15.1`, `google-genai==2.34.x` (own lock) |
| LlamaIndex | https://developers.llamaindex.ai/python/framework/ (`llms.txt`, REST `/api/`) | `llama-index-core` 0.14.x, Python `>=3.11,<4.0` (3.14 OK) |
| LangChain | https://docs.langchain.com/ | LangChain v1.5.2, LangGraph v1.2.24 |

Do not invent APIs. Do not copy deprecated `from llama_parse import LlamaParse` (`llama-parse` / `llama-cloud-services` are deprecated). Hosted parse: `llama-cloud>=2.8`, `from llama_cloud import LlamaCloud`.

## Shared contract (every framework)

All three must implement, with their own APIs:

1. Tenant/ACL filter **inside** the retrieval call from the verified auth context (`rag-security-reviewer` §1–2).
2. Stable document/chunk ids; content-hash ingest; deletes that stop retrieval.
3. Retrieved text is **data**, never instructions or tool authority.
4. Citations ⊂ retrieved ids; insufficient evidence → abstain (`rag-response-contract.md`).
5. One generation path (no LlamaIndex query-engine synthesize **and** ADK `LlmAgent` answer).
6. Golden-set evals + traces (Langfuse / OpenTelemetry already in `eval-guide` and `ai-observability.md`).

## When `auto` (evidence, then recommend)

Score the corpus and the runtime. Explicit `framework=` always wins.

| Signal | Prefer | Why |
|---|---|---|
| Existing Google ADK service; multi-step tools + SQL/API + optional retrieve | `google-adk` | Agent-first. Retrieve is a graph `FunctionNode` (deterministic) or an MCP tool (model-chosen). |
| Complex PDFs, tables, scans, OCR, many readers, advanced indexes, ingestion cache | `llamaindex` | Document-centric. Official `Document`/`Node`, `IngestionPipeline`, `VectorStoreIndex`. |
| Existing LangChain/LangGraph service; composable LCEL/graph retrieve→gate→generate | `langchain` | Pipeline-first. Patterns: `agentic-templates-rag.md`, `rag-pipeline-patterns.md` §6. |
| Greenfield, ordinary docs, no agent runtime yet | `llamaindex` | Fastest path to production ingestion + retrieval. |
| Greenfield, the product **is** an agent that sometimes retrieves | `google-adk` | Do not add a second orchestrator. |

Tie-break: `agentic_workflows=true` → `google-adk`; `document_complexity` in `{tables,scans,multimodal}` → `llamaindex`; else existing stack wins; else `llamaindex`.

Record the choice and rejected alternatives in the RAG ADR (`/rag-design`).

## Nested parse choice (LlamaIndex only)

After `llamaindex` is selected, choose a parser (`llamaindex/references/parse-choice.md`):

| Parser | When | Gate |
|---|---|---|
| Built-in readers (`SimpleDirectoryReader`, text/markdown/html) | Ordinary digital text | Default |
| **LiteParse** (`liteparse`, local, no API key) | Local/offline PDF/Office; latency-sensitive; data must not leave the machine | Default for PDFs that are text-heavy |
| **LlamaParse** (`llama-cloud`, hosted) | Scans, OCR, dense tables, structured extract | **BLOCK** until the user approves data processing, credentials, and cost |

## ADK wrap of LlamaIndex / LangChain retrieval

Only when the user **explicitly** asks to expose an existing retriever to an ADK agent. Canonical: `llamaindex/references/adk-tool-wrap.md`.

- Deterministic retrieve → ADK graph `FunctionNode` (vector I/O allowed here).
- Model-chosen retrieve → **MCP tool** (`McpToolset`). A `FunctionTool` must **not** open the vector DB (`google-adk` Iron Law).
- ADK `LlmAgent` generates. The LlamaIndex **retriever** (not `as_query_engine()`) or LangChain retriever returns nodes. Never two synthesizers.

## Implementation homes (do not duplicate)

| Concern | Home |
|---|---|
| Is RAG the right tool, chunking, hybrid, abstention | `rag-architect/SKILL.md` |
| Store, embeddings, pgvector/Weaviate SQL | `vector-database` |
| LangChain/LangGraph retrieve→gate→generate | `agentic-ai-dev/reference/agentic-templates-rag.md` |
| ADK tools, instruction, no interpolation | `google-adk`, `adk-gemini-prompt-templates.md` §2 |
| LlamaIndex APIs | `llamaindex` skill |
| Security ACL | `rag-security-reviewer` |
| Eval / golden set | `rag-evaluator`, `/rag-eval-init` |
| Review | `rag-review`, `rag-implementation-reviewer` |
