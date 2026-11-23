"""MCP client connections for the evaluation harness (MCP Python SDK v2, `mcp==2.3.0`).

Two transports only: stdio and Streamable HTTP. The 2024-11-05 HTTP+SSE transport is
deprecated and intentionally not offered. `mcp.Client` negotiates the protocol era itself
(`server/discover` for 2026-07-28 servers, falling back to `initialize` for older ones).
"""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Self

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


class MCPConnection:
    """One MCP server connection, used as `async with create_connection(...) as conn`."""

    def __init__(self, target: StdioServerParameters | str, headers: dict[str, str] | None = None) -> None:
        self._target = target
        self._headers = headers or {}
        self._stack: AsyncExitStack | None = None
        self._client: Client | None = None

    async def __aenter__(self) -> Self:
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            if isinstance(self._target, str) and self._headers:
                # Headers (e.g. Authorization) live on the HTTP client in SDK v2.
                http_client = await stack.enter_async_context(
                    httpx2.AsyncClient(headers=self._headers, timeout=httpx2.Timeout(30, read=300))
                )
                server: Any = streamable_http_client(self._target, http_client=http_client)
            else:
                server = self._target
            self._client = await stack.enter_async_context(Client(server))
        except BaseException:
            await stack.__aexit__(None, None, None)
            raise
        self._stack = stack
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc, tb)
        self._stack = None
        self._client = None

    def _require_client(self) -> Client:
        if self._client is None:
            raise RuntimeError("MCPConnection used outside `async with`")
        return self._client

    @property
    def protocol_version(self) -> str | None:
        return self._require_client().protocol_version

    async def list_tools(self) -> list[dict[str, Any]]:
        """All tools (the client walks every page), shaped as Claude API tool definitions."""
        result = await self._require_client().list_tools()
        return [
            {"name": tool.name, "description": tool.description or "", "input_schema": tool.input_schema}
            for tool in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool. Returns a JSON-serialisable dict that keeps the tool-level `is_error` flag."""
        result = await self._require_client().call_tool(tool_name, arguments)
        return {
            "is_error": bool(result.is_error),
            "content": [block.model_dump(mode="json", exclude_none=True) for block in result.content],
            "structured_content": result.structured_content,
        }


def create_connection(
    transport: str,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> MCPConnection:
    """Build a connection for transport "stdio" or "http" (Streamable HTTP)."""
    transport = transport.lower()
    if transport == "stdio":
        if not command:
            raise ValueError("Command is required for stdio transport")
        return MCPConnection(StdioServerParameters(command=command, args=args or [], env=env))
    if transport in ("http", "streamable-http", "streamable_http"):
        if not url:
            raise ValueError("URL is required for http transport")
        return MCPConnection(url, headers=headers)
    if transport == "sse":
        raise ValueError(
            "The HTTP+SSE transport is deprecated; serve the MCP server over Streamable HTTP and use '-t http'"
        )
    raise ValueError(f"Unsupported transport type: {transport}. Use 'stdio' or 'http'")
