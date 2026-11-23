# Python MCP Server — Setup, Tools and Validation

Python servers on the **official MCP Python SDK v2** (`mcp` on PyPI). v2 is the stable line (`pip install mcp` installs 2.x), speaks protocol revision **2026-07-28** and still serves 2025-era clients.

> Verified 2026-11-23 with `mcp==2.3.0` on CPython 3.14.5 via `uv`: every `python` block in the `python-mcp-*` files imports and runs, the server snippets were driven through `mcp.Client`, and the complete example in [python-mcp-patterns.md](python-mcp-patterns.md) was run through the SDK `Client` in-memory and over stdio with pytest (plus a negative control). Check `uv pip index versions mcp` / PyPI before you pin.

---

## v1 → v2: what changed for a server author

| v1 (`mcp` 1.x) | v2 (`mcp` 2.x) |
|---|---|
| `from mcp.server.fastmcp import FastMCP` | `from mcp.server import MCPServer` (old path removed, not deprecated) |
| `FastMCP("name")` | `MCPServer("name")` |
| `from mcp.server.fastmcp import Context` | `from mcp.server.mcpserver import Context` |
| `ToolError` in `mcp.server.fastmcp.exceptions` | `from mcp.server.mcpserver.exceptions import ToolError` |
| `McpError` | `from mcp import MCPError` |
| wire types camelCase (`inputSchema`, `isError`) | snake_case (`input_schema`, `is_error`, `structured_content`); wire types live in `mcp-types` |
| `ClientSession` + transport context manager + `initialize()` | one `mcp.Client(...)` (URL, `StdioServerParameters`, transport, or the server object for in-memory tests) |
| low-level `@server.list_tools()` decorators | `Server(name, on_list_tools=..., on_call_tool=...)`; arguments are **not** validated for you there |

Migration guide: https://py.sdk.modelcontextprotocol.io/migration/

---

## Install (pinned)

```bash
uv init orders-mcp && cd orders-mcp
uv add "mcp[cli]==2.3.0"           # [cli] adds `mcp dev` / `mcp run`
uv add --dev pytest==9.0.1 anyio==4.12.0
```

`requires-python = ">=3.14"` for this workspace (the SDK itself supports 3.10+).

## Naming

- Server name: `{service}_mcp` (e.g. `orders_mcp`); no versions or dates.
- Tool names: `snake_case`, service-prefixed, verb-led (`orders_list`, `orders_cancel`). The function name is the tool name unless you pass `name=`.

---

## Tool structure

The function signature **is** the contract: type hints become the JSON Schema (2020-12), the docstring becomes the description, and the SDK rejects bad arguments before your function runs. Constrain arguments with `Annotated[..., Field(...)]`; return a Pydantic model (or `TypedDict`, dataclass, primitive) to get an `output_schema` and `structured_content` automatically.

```python
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer("orders_mcp")


class OrderSummary(BaseModel):
    id: str
    status: Literal["pending", "shipped", "delivered"]
    total_cents: int


@mcp.tool(
    title="Get one order",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
)
async def orders_get(
    order_id: Annotated[str, Field(pattern=r"^ord_\d{3,}$", description="Order id from orders_list, e.g. ord_001")],
) -> OrderSummary:
    """Fetch one order by id with its status and total in cents. Use after orders_list. Read-only."""
    return OrderSummary(id=order_id, status="pending", total_cents=1250)
```

- **Flat, annotated parameters**, not one `params: InputModel` argument: a single model parameter nests every field under `params` in the advertised schema and makes the model's job harder.
- Bound everything: `max_length` on strings, `le` on numbers, `max_length` on lists.
- Annotations are **hints for the host's UI** (auto-approve read-only, confirm destructive). Clients must treat them as untrusted; they never enforce anything. Enforce authorization in the tool.
- The return annotation drives `structured_content`: `-> OrderSummary` produced `{"id": "ord_002", "total_cents": 1500, ...}` in the sandbox; `-> str` yields `{"result": "..."}`.

### Pydantic v2 reminders

`model_config = ConfigDict(...)` (not `class Config`), `@field_validator` + `@classmethod` (not `@validator`), `model_dump()` (not `.dict()`), `Field(max_length=...)` on lists (not `max_items`).

```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CreateUser(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("name")
    @classmethod
    def no_control_chars(cls, value: str) -> str:
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("name must not contain control characters")
        return value
```

(`EmailStr` needs `uv add email-validator==2.4.0`.)

---

## Running it

```python
from mcp.server import MCPServer

mcp = MCPServer("orders_mcp")

if __name__ == "__main__":
    mcp.run()  # stdio by default
```

| Transport | How | Notes |
|---|---|---|
| stdio | `mcp.run()` | default; stdout is the protocol — log to stderr (the `logging` module's default stream) |
| Streamable HTTP | `mcp.run(transport="streamable-http", port=3001)` or mount `mcp.streamable_http_app()` in an ASGI app | serves `/mcp`; transport options go to `run()`/`streamable_http_app()`, never to `MCPServer(...)` |
| SSE (`transport="sse"`) | **do not use** | the 2024-11-05 HTTP+SSE transport is Deprecated; migration only |

- `streamable_http_app()` enables DNS-rebinding protection for localhost by default. Behind a real hostname pass `transport_security=TransportSecuritySettings(allowed_hosts=["mcp.example.com", "mcp.example.com:*"], ...)` from `mcp.server.transport_security`. A non-localhost `host=` alone **turns the protection off** rather than allow-listing.
- HTTP options that only matter for 2025-era clients: `stateless_http=True` (no legacy sessions), `json_response=True` (no SSE; a tool that elicits then fails with `NoBackChannelError`), `session_idle_timeout`, `max_sessions`, `event_store`. Request bodies over 4 MiB get HTTP 413 (`max_request_body_size`).
- Authentication is not on by default: see [security-core.md](security-core.md).

### Inspector and CLI

```bash
uv run mcp dev server.py                       # MCP Inspector UI (needs npx)
uv run mcp run server.py --transport streamable-http
npx @modelcontextprotocol/inspector@2.16.0 --cli uv run python server.py --method tools/list
```

Next: error handling, pagination, the complete tested example → [python-mcp-patterns.md](python-mcp-patterns.md); context, progress, cancellation, resources, prompts, lifespan, protocol eras → [python-mcp-advanced.md](python-mcp-advanced.md).
