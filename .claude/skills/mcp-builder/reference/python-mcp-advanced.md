# Python MCP Server — Context, Progress, Cancellation, Resources, Prompts, Lifespan, Protocol Eras

`mcp==2.3.0` (SDK v2). Setup: [python-mcp-setup.md](python-mcp-setup.md) · errors/pagination/complete example: [python-mcp-patterns.md](python-mcp-patterns.md). Every `python` block here compiles under CPython 3.14 (`py_compile`); API names were checked against the installed package.

---

## The Context

Add a parameter annotated `Context` (from `mcp.server.mcpserver`) to any tool, resource or prompt; the SDK injects a fresh one per request and leaves it out of the input schema.

| Member | Use |
|---|---|
| `ctx.request_id` | correlate logs |
| `await ctx.report_progress(progress, total, message)` | progress; a no-op when the caller did not ask for it |
| `await ctx.read_resource(uri)` | read one of this server's own resources |
| `ctx.request_context.lifespan_context` | the object your lifespan yielded (pools, clients) |
| `ctx.headers` | HTTP request headers, `None` on stdio — client-supplied input, **never identity** |
| `await ctx.notify_tools_changed()` / `notify_resource_updated(uri)` | change notifications for 2026-07-28 subscribers (`subscriptions/listen`) |

`ctx.elicit(...)`, sampling and roots are 2025-era push features (see [Protocol eras](#protocol-eras-and-backward-compatibility)); `ctx.info()`/`ctx.debug()` protocol logging is Deprecated as of 2026-07-28 (SEP-2577) — log with the `logging` module to stderr and use OpenTelemetry for traces.

## Progress and cancellation

```python
from typing import Annotated

import anyio
from pydantic import Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

mcp = MCPServer("orders_mcp")
holds: set[str] = set()


async def export_batch(index: int) -> None:
    await anyio.sleep(0.05)


async def release_holds() -> None:
    holds.clear()


@mcp.tool()
async def orders_export(batches: Annotated[int, Field(ge=1, le=100)], ctx: Context) -> str:
    """Export orders in batches and report progress. Stops when the caller cancels."""
    holds.add("export")
    try:
        for i in range(batches):
            await export_batch(i)  # a cancelled call raises here; nothing it returns is sent
            await ctx.report_progress(i + 1, total=batches, message=f"batch {i + 1}/{batches}")
        return f"Exported {batches} batches"
    finally:
        # cleanup that awaits must be shielded (every await in a cancelled task raises) and time-bounded
        with anyio.move_on_after(5, shield=True):
            await release_holds()
```

- Cancellation in v2 cancels the handler task: the pending `await` raises, `finally` runs. Use `finally`, not `except`, so the cancellation keeps propagating.
- A plain `def` tool runs in a worker thread and cannot be interrupted: call `anyio.from_thread.check_cancelled()` between units of work.
- Progress must increase; treat it as advisory (the final update can race the result).

## Resources and prompts

```python
import json

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.mcpserver.prompts.base import Message, UserMessage
from mcp.types import INVALID_PARAMS

mcp = MCPServer("orders_mcp")
ORDERS = {"ord_001": 1250, "ord_002": 1500}


@mcp.resource("orders://schema", mime_type="application/schema+json")
def order_schema() -> str:
    """JSON schema of an order record."""
    return json.dumps({"type": "object", "properties": {"id": {"type": "string"}}})


@mcp.resource("orders://{order_id}", mime_type="application/json")
def order_by_id(order_id: str) -> str:
    """One order as JSON."""
    if order_id not in ORDERS:
        raise MCPError(code=INVALID_PARAMS, message=f"Unknown order {order_id!r}")
    return json.dumps({"id": order_id, "total_cents": ORDERS[order_id]})


@mcp.prompt()
def orders_summarize(order_id: str) -> list[Message]:
    """Draft a support-agent summary of one order."""
    return [UserMessage(f"Summarize order {order_id} for a support agent.")]
```

- A URI with `{placeholders}` is a template; the placeholders become function parameters.
- Unknown resource → protocol error (`MCPError`, `-32602` in 2026-07-28, which replaced `-32002`). Do not return empty content for a miss.
- A URI is not an authorization check: verify the caller may read `order_id`.

## Lifespan: shared clients and pools

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx2

from mcp.server import MCPServer
from mcp.server.mcpserver import Context


@dataclass
class AppContext:
    http: httpx2.AsyncClient


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    async with httpx2.AsyncClient(base_url="https://api.example.com", timeout=10.0) as http:
        yield AppContext(http=http)


mcp = MCPServer("orders_mcp", lifespan=lifespan)


@mcp.tool()
async def orders_ping(ctx: Context[AppContext]) -> str:
    """Check that the orders API answers. Read-only."""
    response = await ctx.request_context.lifespan_context.http.get("/health")
    return f"orders API status {response.status_code}"
```

Validate required environment variables before `yield` and raise — fail fast, never fall back to defaults.

---

## Protocol eras and backward compatibility

| | 2026-07-28 ("modern") | ≤ 2025-11-25 ("legacy") |
|---|---|---|
| Opening | none; every request carries version/capabilities/client info in `_meta`; servers implement `server/discover` | `initialize` handshake |
| Sessions | none (no `Mcp-Session-Id`); cross-call state via explicit handles in tool arguments | optional HTTP sessions |
| Asking the user / an LLM mid-call | handler returns an `InputRequiredResult` (Multi Round-Trip Requests); v2 also offers `Resolve(fn)` parameters that `Elicit(...)` | server pushes `elicitation/create`, `sampling/createMessage`, `roots/list` (`ctx.elicit()`) |
| Change notifications | only on a `subscriptions/listen` stream | unsolicited on the session |
| Stream resumability | removed | `Last-Event-ID` + `event_store` |

- `MCPServer` serves both eras on every transport; there is **no option to reject legacy clients** in the Python SDK.
- HTTP legacy leg: default is sessionful (sticky routing needed across workers). `streamable_http_app(stateless_http=True)` makes it per-request and freely load-balanced, but on that leg server-to-client requests raise `NoBackChannelError` and notifications (including progress) are dropped. The modern leg is sessionless either way.
- Python `Client` defaults to `mode="auto"` (probe with `server/discover`, fall back to `initialize`); verified to land on `2026-07-28` against a v2 server over stdio. Use `mode="legacy"` only to test the 2025 path.
- Sampling and Roots are Deprecated (SEP-2577, earliest removal in the first revision on or after 2027-07-28): call your LLM provider directly; pass paths as tool arguments or configuration.

Details: https://py.sdk.modelcontextprotocol.io/protocol-versions/ and https://py.sdk.modelcontextprotocol.io/run/legacy-clients/

---

## Quality checklist

- [ ] `mcp==2.x` pinned; imports from `mcp.server` / `mcp.server.mcpserver`, no `mcp.server.fastmcp`
- [ ] Flat, `Annotated`-constrained tool parameters; bounded strings, numbers, lists
- [ ] Return types are models/TypedDicts so `output_schema` + `structured_content` are generated
- [ ] Expected failures raise `ToolError` with a next step; host-facing failures raise `MCPError`; no `return "Error: ..."`, no bare `except:`
- [ ] Shared clients created in the lifespan; required env validated before `yield`
- [ ] Long tools are `async`, cancellation-safe (`finally` + shielded, time-bounded cleanup)
- [ ] Logging via `logging` to stderr; no `print()`; no protocol logging in new code
- [ ] HTTP: `transport_security` allow-list for real hostnames; auth in front ([security-core.md](security-core.md)); decided sessionful vs `stateless_http` for the legacy leg
- [ ] Tests drive the server through `mcp.Client` in memory and over stdio; one negative control per gate
- [ ] `uv run mcp dev server.py` / Inspector CLI smoke before publishing
