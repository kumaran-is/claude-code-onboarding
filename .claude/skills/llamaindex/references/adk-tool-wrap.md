# Expose LlamaIndex (or LangChain) retrieval to Google ADK

Only when the user **explicitly** asks. Default: one framework owns retrieve **and** generate.

Official ADK constraints (`google-adk/SKILL.md`):

- Model-chosen tools must not open HTTP/DB/vector stores from a `FunctionTool` — that is `McpToolset`.
- Deterministic graph steps **may** call the retriever from a `FunctionNode`.
- Never interpolate retrieved text into `instruction` (`adk-gemini-prompt-templates.md` §2).
- Retrieved ids are the only legal citations; empty retrieve → `INSUFFICIENT_EVIDENCE` without a model call when the graph is retrieve-then-generate.

## Forbidden: two synthesizers

```python
# WRONG — LlamaIndex writes an answer AND ADK writes an answer
answer = index.as_query_engine().query(user_text)
# plus LlmAgent(instruction=GEMINI_RAG_INSTRUCTION, tools=[...])
```

One owner. If ADK is the agent, LlamaIndex stops at `retriever.retrieve()`.

## Pattern A — deterministic retrieve (preferred for "every answer is grounded")

Graph: `FunctionNode(retrieve)` → evidence gate → `LlmAgent` generate.

```python
from google.adk.workflow import FunctionNode

def retrieve_nodes(node_input: str, tenant_id: str) -> dict:
    """ACL-filtered LlamaIndex retrieve. tenant_id is bound from session/auth state."""
    if not tenant_id:
        raise PermissionError("tenant_id required")
    nodes = retriever.retrieve(node_input)  # retriever already has MetadataFilters
    packed = []
    for node in nodes:
        meta = dict(node.metadata or {})
        if meta.get("tenant_id") != tenant_id or meta.get("acl") != tenant_id:
            continue
        packed.append(
            {
                "id": node.node_id,
                "ref_doc_id": node.ref_doc_id,
                "text": node.get_content(),
            }
        )
    if not packed:
        return {"ok": True, "error_code": None, "status": "INSUFFICIENT_EVIDENCE", "nodes": []}
    return {"ok": True, "error_code": None, "status": "OK", "nodes": packed}


retrieve_step = FunctionNode(func=retrieve_nodes, name="retrieve_nodes", timeout=10.0)
```

The generate agent sees tool/state **data**, not an instruction template filled with chunk text. After the run, validate citations ⊂ returned ids (`response_contract.py`).

## Pattern B — model-chosen retrieve

Wrap the same chokepoint as an **MCP tool** and attach `McpToolset(tool_filter=...)`. The tool args include the query only; tenant/ACL are injected server-side from the authenticated session, never from the model.

A `FunctionTool` is allowed only when it reads nodes **already** written to `tool_context.state` by an MCP tool or a `FunctionNode` (pure/session logic). It must not import a vector client.

## Pattern C — LangChain retriever, same wrap

Replace `retriever.retrieve` with the LangChain retriever `invoke(query, org_id=...)` from `agentic-templates-rag.md`. Same JSON contract: `{ok, error_code, status, nodes:[{id,text}]}`. Still one generator (ADK).

## Tests

Isolated fixtures: `rag-architect/scripts/run_rag_framework_fixtures.py` (LlamaIndex retrieve + ADK tool payload, no live Gemini). Live-provider generate is NOT RUN unless the product supplies credentials.
