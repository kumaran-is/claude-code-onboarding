# Agentic AI Tool Patterns (LangChain v1)

How to write tools for `create_agent` / LangGraph. Safety rules (authority tiers, scope injection, allowlists, evidence gate, idempotency, budgets, approvals, durable resume) are canonical in `tool-execution-safety.md`; this file is the implementation template.

Executed (Python 3.14, langchain 1.2.8, `ruff` + `mypy --strict` clean): scripted fake model, `httpx.MockTransport` backend, 4 tests listed under the template.

REMOVED from the previous version: tools returning `f"... failed: {e}"` and logging `error=str(e)` (exception text reached the model and logs), a generic `call_external_api(endpoint, method, payload)` tool (model-chosen URL = SSRF), a `query_database(table, filters, columns)` tool (model-chosen table/columns), and a hand-rolled retry decorator that retried every exception and returned the last error as text.

## Template: typed, scoped, bounded read tool

**File:** `src/<service>/agents/tools/knowledge.py`

```python
@dataclass(frozen=True)
class RequestCtx:
    org_id: str
    user_id: str


DOC_FIELDS = frozenset({"doc_id", "title", "snippet", "updated_at"})


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="What to look for")
    limit: int = Field(default=5, ge=1, le=20)


@tool(args_schema=SearchArgs)
async def search_knowledge_base(query: str, runtime: ToolRuntime[RequestCtx], limit: int = 5) -> ToolResult:
    """Search the caller's organization knowledge base. Returns up to `limit` documents.

    Fallback: if unavailable, answer INSUFFICIENT_EVIDENCE; do not answer from memory.
    """
    org_id = runtime.context.org_id                      # verified scope, never a model argument
    try:
        async with asyncio.timeout(settings.tool_timeout_s):
            rows = await kb.search(org_id=org_id, query=query, limit=limit)   # service re-authorizes
    except (TimeoutError, httpx.TransportError, httpx.HTTPStatusError) as exc:
        log_exception(logger, "tool_search_failed", exc, level="warning", org_id=org_id)
        return fail("TOOL_UNAVAILABLE")
    if not rows:
        return fail("NOT_FOUND")
    return ok({"documents": [project(r, DOC_FIELDS) for r in rows]})
```

`ToolResult`, `ok`, `fail`, `project`: `tool-execution-safety.md` §1. `log_exception`: `deployment-ci-cd/reference/python-observability.md` §2. Wire with `create_agent(model, tools=[...], context_schema=RequestCtx)` and `ainvoke(..., context=RequestCtx(...))` (`agentic-templates-core.md`).

Executed assertions:
- The model-visible schema has only `query` and `limit` (`runtime` is injected).
- A model-sent `org_id="org-b"` was ignored; the backend received the context's `org-a`.
- The backend record's `owner_email` was dropped by projection.
- A backend `ConnectError` whose message contained a hostname and an id produced exactly `{"ok": false, "error_code": "TOOL_UNAVAILABLE", "data": null}`; the log line carried `error_type=ConnectError` and the org id only.
- Arguments failing `args_schema` came back to the model as an error `ToolMessage` naming the field ("String should have at least 2 characters"), so the model can correct itself. That text goes to the model, not the client.

Catch only the exceptions you can classify. Anything else propagates to the route's boundary handler (typed 503, `agentic-error-handling.md`), which is better than pretending to the model that a programming error is "unavailable".

## Write tools

Write tools follow the authority tiers in `tool-execution-safety.md` §2: a controlled write takes an idempotency key and goes through `run_once` (§6); a high-consequence write is a **propose** tool plus approval (`agentic-streaming-hitl.md`). The scope comes from `runtime.context`, the key from run state, never from model arguments.

## External APIs

- One tool per business operation (`get_shipment_status(shipment_id)`), backed by a typed client with a **fixed base URL** from settings. The model never chooses the host, path, method or headers.
- Timeouts on every call (`httpx.AsyncClient(timeout=...)` plus the tool's own `asyncio.timeout`), inside the run deadline.
- Don't return raw response bodies: parse, project, return `ToolResult`.
- Any URL that originates from content (a link in a document, a user-supplied URL) is fetched only through an allow-listed fetcher (scheme, host allowlist, resolved IP not private, size cap).

## Database access

No generic "query any table" tool. Write one tool per question the agent may ask, implemented with parameterized queries and the org filter applied in code (or row-level security). Text-to-SQL is a separate, high-risk design: read-only role, statement allowlist, row/time limits, and its own security review.

## Retries

Prefer no tool-level retry: the agent can call again, and the model/run layer has its own budget. When a read tool has a known transient failure mode, use `ToolRetryMiddleware` with explicit settings:

```python
ToolRetryMiddleware(
    tools=["search_knowledge_base"],          # read-only / idempotent tools only
    retry_on=(httpx.TransportError,),         # transient classes, not Exception
    max_retries=2,
    on_failure="error",                       # see trap below
)
```

**Trap (executed):** the default `on_failure="continue"` turns the final exception into the `ToolMessage` text: `"Tool 'flaky' failed after 3 attempts with ConnectionError: db-host-7 password=..."`, which the model can then repeat to the user. Use `"error"` (the exception propagates to your boundary handler), or a callable `on_failure=lambda exc: json.dumps(fail("TOOL_UNAVAILABLE"))` that returns a fixed, typed payload. Also the default `retry_on=(Exception,)` retries programming errors and non-idempotent writes.

Never retry write tools unless they are idempotency-keyed.

## MCP tools

- Building an MCP server: `mcp-builder` skill.
- Consuming MCP tools in an agent: treat every MCP tool as third-party code. Resolve the agent's allowlist against the server's tool list at startup (fail on unknown names, `tool-execution-safety.md` §4), pin the tool surface hash, inject scope in the gateway/adapter (the MCP server must not trust a model-supplied tenant id), and treat results as untrusted data. Verify the adapter package's current API (e.g. `langchain-mcp-adapters`) with Context7 before use; it is not covered by the executed tests here.

## Tool registration

```python
TOOL_REGISTRY: dict[str, BaseTool] = {t.name: t for t in (search_knowledge_base, get_shipment_status, propose_refund)}

# per agent, explicit and validated at construction
support_tools = resolve_allowlist(TOOL_REGISTRY, settings.support_agent_tools)
```

## Key Rules

| Rule | Standard |
|------|----------|
| Docstrings | Every tool: when to use it, what it returns, degradation mode |
| Arguments | `args_schema` with bounds; no scope params; no host/path/table chosen by the model |
| Scope | `ToolRuntime[Ctx]` (or the gateway's `bind_scope`) |
| Return type | `ToolResult` (`ok`/`error_code`/`data`), projected fields only |
| Errors | Catch classified exceptions → typed code; log via `log_exception`; no exception text to the model |
| Timeouts | Every I/O call, inside the run deadline |
| Retries | Read-only tools only; transient classes; `on_failure` never `"continue"` |
| Side effects | Idempotency key; high-consequence = propose + approval |
| Tests | Schema has no scope params; forged scope ignored; failure payload has no exception text |
