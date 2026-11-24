# ADK Tools — Basic Patterns

## 1. Plain Function Tool (auto-schema)

ADK auto-wraps plain Python functions as tools. The docstring — including `Args` and
`Returns` sections — is used to generate the tool schema that the model sees.

```python
def get_weather(city: str, unit: str = "celsius") -> dict:
    """Get current weather for a city.

    Args:
        city: The name of the city to look up.
        unit: Temperature unit, either 'celsius' or 'fahrenheit'.

    Returns:
        A dict with keys 'temperature' (float), 'condition' (str),
        and 'humidity' (int).
    """
    # implementation
    return {"temperature": 22.5, "condition": "sunny", "humidity": 60}
```

Pass the function directly to `Agent(tools=[get_weather])` — no wrapper required.

**Return contract (all stacks):** return a small JSON-serializable dict with an explicit error
field, e.g. `{"ok": bool, "error_code": str | None, "data": ...}`, never raw backend bodies or
exception text. The canonical rule lives in `agentic-ai-coding-standard`; the route inspects
`ok`/`error_code` after the run (`agentic-ai-dev/reference/tool-execution-safety.md`).

---

## 2. Tool with ToolContext (State Access)

Add a `tool_context: ToolContext` parameter to any tool function. ADK injects it
automatically at call time — callers never pass it.

```python
from google.adk.tools import ToolContext

def remember_preference(key: str, value: str, tool_context: ToolContext) -> dict:
    """Store a user preference in session state.

    Args:
        key: Preference name to store.
        value: Value to associate with the key.
        tool_context: Injected by ADK — do not pass manually.

    Returns:
        A dict with 'stored' bool and 'key' str.
    """
    existing = tool_context.state.get(key, None)
    tool_context.state[key] = value
    return {"stored": True, "key": key, "previous": existing}
```

Read: `tool_context.state.get("key", default)`
Write: `tool_context.state["key"] = value`

---

## 3. Async Tool

Use `async def` for tools that perform I/O. ADK awaits them automatically.

```python
import asyncio
from google.adk.tools import ToolContext

async def fetch_report(report_id: str, tool_context: ToolContext) -> dict:
    """Fetch a report from the external reporting service.

    Args:
        report_id: The unique ID of the report to fetch.
        tool_context: Injected by ADK — do not pass manually.

    Returns:
        A dict with 'report_id' str and 'data' dict.
    """
    await asyncio.sleep(0.1)  # simulates async I/O
    cached = tool_context.state.get(f"report:{report_id}")
    if cached:
        return {"report_id": report_id, "data": cached, "source": "cache"}
    # ... real fetch here
    return {"report_id": report_id, "data": {}, "source": "api"}
```

**Enum parameters (2.14+):** an `enum.Enum`-typed argument now arrives as the enum member, not its raw string (executed on 2.15). With a plain `Enum` (not `StrEnum`), 1.x code that compares the argument with `== "value"` silently stops matching; compare with the member or use `Literal[...]`.

---

## 4. Pydantic Input Tool

For structured inputs, define a `BaseModel` and use it as the parameter type.
ADK extracts the schema from the model for the tool definition.

```python
from pydantic import BaseModel
from google.adk.tools import ToolContext

class OrderRequest(BaseModel):
    product_id: str
    quantity: int
    shipping_address: str

def place_order(order: OrderRequest, tool_context: ToolContext) -> dict:
    """Place a product order.

    Args:
        order: The order details including product, quantity, and address.
        tool_context: Injected by ADK — do not pass manually.

    Returns:
        A dict with 'order_id' str and 'status' str.
    """
    tool_context.state["last_order"] = order.model_dump()
    return {"order_id": "ORD-001", "status": "confirmed"}
```

---

## 5. FunctionTool with Confirmation (human approval)

`FunctionTool(func, require_confirmation=True)` pauses before the tool runs. Confirmation is
not authorization: the tool still checks scope and an allowlist itself, and side effects
take an idempotency key (`agentic-ai-dev/reference/tool-execution-safety.md`).

```python
from google.adk.tools import FunctionTool, ToolContext


def archive_document(document_id: str, tool_context: ToolContext) -> dict:
    """Archive one document owned by the caller's organization.

    Args:
        document_id: Id of the document to archive.

    Returns:
        {"ok": bool, "error_code": str | None, "data": {"document_id": str} | None}
    """
    org_id = tool_context.state.get("org_id")  # server-set scope, never a model argument
    if not org_id:
        return {"ok": False, "error_code": "UNAUTHORIZED", "data": None}
    # documents.archive(org_id=org_id, document_id=document_id, idempotency_key=...)
    # must authorize the record itself and be idempotent
    return {"ok": True, "error_code": None, "data": {"document_id": document_id}}


archive_tool = FunctionTool(archive_document, require_confirmation=True)
```

Round trip (executed on 1.29 and 2.15 with a scripted model): the first run does **not** execute the
tool; it emits a function call named `adk_request_confirmation` (args `originalFunctionCall`,
`toolConfirmation`). Show it to the user, then send the decision as the next message:

```python
decision = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
    id=confirmation_call.id, name="adk_request_confirmation", response={"confirmed": True},
))])
async for event in runner.run_async(user_id=principal.user_id, session_id=session.id, new_message=decision):
    ...
```

The decision must come from an authenticated endpoint for the session's owner, never from
model text. `require_confirmation` may also be a callable `(**tool_args) -> bool` to confirm
only risky argument values.

---

## 6. Built-in Tools Reference Table

| Tool | Import | Purpose |
|------|--------|---------|
| `google_search` | `from google.adk.tools import google_search` | Web search via Google |
| `load_memory` | `from google.adk.tools import load_memory` | Load from memory service |
| `preload_memory` | `from google.adk.tools import preload_memory` | Preload memories into context |
| `exit_loop` | `from google.adk.tools import exit_loop` | Exit LoopAgent iteration |
| `transfer_to_agent` | injected automatically when `sub_agents` is set — do not list it in `tools=` | Hand off to sub-agent |
| `AgentTool` | `from google.adk.tools import AgentTool` | Call another agent as a tool (parent keeps control) |
| `get_user_choice` | `from google.adk.tools import get_user_choice` | Get user selection |
| `VertexAiSearchTool` | `from google.adk.tools import VertexAiSearchTool` | Enterprise search via Vertex AI |

---

## 7. McpToolset

`McpToolset` connects an ADK agent to an MCP server. Always call `await runner.close()`
on shutdown — MCP sessions hold open connections.

**`tool_filter` is an allowlist you must enforce yourself.** ADK treats `None` AND an empty
list as "expose every tool" (`base_toolset.py` `_is_tool_selected`: `if not self.tool_filter:
return True`; `McpToolset(..., tool_filter=[])` constructs without error — executed on 1.29 and 2.15; 2.x needs the `google-adk[mcp]` extra to import `McpToolset`).
Build toolsets through one project factory that raises on a missing/empty filter, and add a
startup or CI check that every allowlisted name exists on the server (a typo silently leaves
the agent with fewer tools).

```python
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters


def mcp_toolset(connection_params, tool_filter: list[str]) -> McpToolset:
    if not tool_filter:
        raise ValueError("tool_filter must be a non-empty allowlist")  # ADK would expose ALL tools
    return McpToolset(connection_params=connection_params, tool_filter=tool_filter)


# stdio (subprocess). StdioConnectionParams takes server_params=, not command=/args=
docs_tools = mcp_toolset(
    StdioConnectionParams(
        server_params=StdioServerParameters(command="npx", args=["-y", "<pinned-server-package>@<version>"]),
        timeout=30,
    ),
    tool_filter=["search_documents", "get_document"],
)

# Streamable HTTP (preferred for remote servers; SseConnectionParams is the older transport)
orders_tools = mcp_toolset(
    StreamableHTTPConnectionParams(url=settings.orders_mcp_url, timeout=60),
    tool_filter=["get_order"],
)
```

Pin the MCP server package version; never `npx -y <package>` unpinned in production.
