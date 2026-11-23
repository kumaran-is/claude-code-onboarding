# Python MCP Server — Errors, Pagination, Upstream Calls, Complete Example

`mcp==2.3.0` (SDK v2). Setup and tool basics: [python-mcp-setup.md](python-mcp-setup.md).

---

## Errors: three outcomes

| You raise / return | The client gets | Who reads it |
|---|---|---|
| `raise ToolError("...")` (`mcp.server.mcpserver.exceptions`) | a result with `is_error=True` and your message | the **model** — it can correct itself |
| arguments fail the signature's validation | `is_error=True` result, your function never runs | the model |
| `raise MCPError(code=INVALID_PARAMS, message=...)` (`from mcp import MCPError`) | a JSON-RPC error, no result | the **host code** |
| any other exception | a failed call; the model learns only that it failed; your log gets the traceback | nobody useful — avoid |

Rules:

- Expected failures (not found, upstream 429/5xx, business rule) → `ToolError` with a sentence that names the next step. Never `return "Error: ..."`: a returned string has `is_error=False`, so the model treats it as success.
- `MCPError` only when the request itself is wrong for the host (unknown resource, malformed params).
- Log the full exception server-side with context before raising `ToolError` — never put stack traces or secrets in the message.

## Upstream client (httpx2, one pooled client)

```python
import logging

import httpx2

from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger("orders_mcp")


def to_tool_error(exc: Exception, action: str) -> ToolError:
    """Map an upstream failure to a model-readable ToolError, after logging the detail."""
    logger.error("%s failed", action, exc_info=exc)
    if isinstance(exc, httpx2.HTTPStatusError):
        status = exc.response.status_code
        if status == 404:
            return ToolError("Not found. Check the id with the matching *_list tool.")
        if status == 403:
            return ToolError("Permission denied for this account. Do not retry; tell the user.")
        if status == 429 or status >= 500:
            return ToolError(f"Upstream temporarily unavailable (HTTP {status}). Retry once after a short wait.")
        return ToolError(f"Upstream rejected the request (HTTP {status}). Check the arguments.")
    if isinstance(exc, httpx2.TimeoutException):
        return ToolError("Upstream timed out. Retry once with a narrower query.")
    return ToolError("Unexpected failure. Do not retry; report it.")


async def get_json(client: httpx2.AsyncClient, path: str, params: dict[str, str | int]) -> dict[str, object]:
    response = await client.get(path, params=params, timeout=10.0)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"expected a JSON object from {path}")
    return body
```

Create the `httpx2.AsyncClient` once in the server lifespan ([python-mcp-advanced.md](python-mcp-advanced.md#lifespan-shared-clients-and-pools)), not per call. Use `async def` tools for I/O; a blocking call inside `async def` stalls every other request.

## Pagination

Tool-level pagination: an opaque `cursor` argument in, a `next_cursor` field out. Bound the page size; reject a bad cursor with a `ToolError` that says how to restart.

```python
import base64
from typing import Annotated

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("orders_mcp")
ORDERS = [f"ord_{i:03d}" for i in range(1, 24)]


class OrderPage(BaseModel):
    items: list[str]
    total: int
    next_cursor: str | None = None


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode(cursor: str) -> int:
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ToolError("Invalid cursor. Call orders_list without cursor to restart.") from exc
    if offset < 0:
        raise ToolError("Invalid cursor. Call orders_list without cursor to restart.")
    return offset


@mcp.tool()
async def orders_list(
    limit: Annotated[int, Field(ge=1, le=50, description="Page size, 1-50")] = 20,
    cursor: Annotated[str | None, Field(max_length=128, description="Opaque next_cursor from the previous page")] = None,
) -> OrderPage:
    """List order ids one page at a time. Pass next_cursor back unchanged as cursor to get the next page."""
    start = 0 if cursor is None else _decode(cursor)
    items = ORDERS[start : start + limit]
    end = start + len(items)
    return OrderPage(items=items, total=len(ORDERS), next_cursor=_encode(end) if end < len(ORDERS) else None)
```

Protocol-level pagination of `tools/list` / `resources/list` (a `cursor` param and `nextCursor` result on the list call itself) is only needed for very large catalogs and is done on the low-level `Server` (`on_list_resources=...` receiving `PaginatedRequestParams`). Cursors are opaque; page size is the server's choice; a missing `next_cursor` ends the walk.

---

## Complete example (tested)

`src/server.py`:

```python
"""Orders demo MCP server (Python SDK v2)."""

import json
import logging
from typing import Annotated

from pydantic import BaseModel, Field

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import INVALID_PARAMS

logger = logging.getLogger("orders-demo")

mcp = MCPServer("orders-demo")

ORDERS = {f"ord_{i:03d}": 1000 + i * 250 for i in range(1, 24)}


class OrderTotal(BaseModel):
    id: str
    total_cents: int


@mcp.tool()
async def order_total(
    order_id: Annotated[str, Field(pattern=r"^ord_\d{3}$", description="Order id, e.g. ord_001")],
    ctx: Context,
) -> OrderTotal:
    """Return the total of one order in cents. Use when the user asks what an order cost."""
    await ctx.report_progress(1, 1, "looked up order")
    if order_id not in ORDERS:
        logger.info("order not found", extra={"order_id": order_id})
        raise ToolError(f"No order {order_id!r}. Call order_total with an id like ord_001.")
    return OrderTotal(id=order_id, total_cents=ORDERS[order_id])


@mcp.resource("orders://{order_id}")
def order_resource(order_id: str) -> str:
    """One order as JSON text."""
    if order_id not in ORDERS:
        raise MCPError(code=INVALID_PARAMS, message=f"Unknown order {order_id!r}")
    return json.dumps({"id": order_id, "total_cents": ORDERS[order_id]})


if __name__ == "__main__":
    mcp.run()
```

`tests/test_server.py` — drives the server through the real `Client`, in memory and as a stdio subprocess:

```python
import sys
from pathlib import Path

import pytest

from mcp import Client, MCPError, StdioServerParameters

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from server import mcp  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_in_memory_structured_output_and_errors() -> None:
    async with Client(mcp) as client:
        tools = (await client.list_tools()).tools
        tool = next(t for t in tools if t.name == "order_total")
        assert tool.output_schema is not None
        ok = await client.call_tool("order_total", {"order_id": "ord_002"})
        assert ok.is_error is False
        assert ok.structured_content == {"id": "ord_002", "total_cents": 1500}
        missing = await client.call_tool("order_total", {"order_id": "ord_999"})
        assert missing.is_error is True
        bad = await client.call_tool("order_total", {"order_id": "DROP TABLE"})
        assert bad.is_error is True


async def test_resource_read_and_unknown_id_is_protocol_error() -> None:
    async with Client(mcp) as client:
        found = await client.read_resource("orders://ord_003")
        assert "ord_003" in str(found.contents[0])
        with pytest.raises(MCPError):
            await client.read_resource("orders://ord_999")


async def test_stdio_subprocess() -> None:
    server = Path(__file__).resolve().parents[1] / "src" / "server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(server)])
    async with Client(params) as client:
        assert client.protocol_version is not None
        res = await client.call_tool("order_total", {"order_id": "ord_001"})
        assert res.structured_content == {"id": "ord_001", "total_cents": 1250}
```

Observed: `uv run pytest -q` → `3 passed`; `client.protocol_version` on stdio was `2026-07-28`. Negative control: changing the not-found branch to return a zero total instead of raising made `test_in_memory_structured_output_and_errors` fail (`assert False is True`, exit 1).

Production hardening on top of this example: add authorization per call ([security-core.md](security-core.md)); add the house `next_actions` / `suggestion` fields ([agent-design-patterns.md](agent-design-patterns.md)).
