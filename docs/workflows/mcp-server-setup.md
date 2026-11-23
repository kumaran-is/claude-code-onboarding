# MCP Server Setup

> **When to use**: Adding a new MCP (Model Context Protocol) server to the workspace, or building a custom MCP server for a new integration
> **Time estimate**: 30 min to configure an existing server; 2–4 hours to build a custom one
> **Prerequisites**: Claude Code installed; MCP server package or source available

## Overview

MCP (Model Context Protocol) server configuration and custom MCP server development. Covers configuring MCP servers in Claude Code settings, building custom servers with FastMCP (Python) or the TypeScript SDK, and the `mcp-builder` skill patterns.

---

## Current MCP Servers (this workspace)

From `.claude/settings.json`:

| MCP Server | Purpose | When Used |
|-----------|---------|----------|
| `context7` | Library documentation lookup | Before writing any code — resolve library ID + query docs |
| `angular-cli` | Angular 22.x patterns, best practices (`get_best_practices` with `workspacePath`), docs (`search_documentation` version 22), project discovery | Before writing Angular code |
| `dart-mcp-server` | Flutter/Dart tooling, device lists, test runner | Before writing Flutter code |
| `firebase` | Firebase project, rules, SDK config | Firebase integration |
| `chrome-devtools` | Browser inspection, performance, network | Browser E2E testing |
| `xcodebuild` | iOS build, simulator, test runner | iOS release workflow |
| `weaviate-docs` | Weaviate documentation search | Weaviate collection/RAG work |
| `langchain-docs` | LangChain documentation | Agentic AI work |
| `youtube-transcript` | Video transcript extraction | Learning and documentation |

---

## Phases

### Phase 1 — Configure an Existing MCP Server

**Settings file**: `.claude/settings.json`

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"],
      "env": {}
    },
    "my-new-server": {
      "command": "uvx",
      "args": ["my-mcp-server@latest"],
      "env": {
        "API_KEY": "${MY_API_KEY}"
      }
    }
  }
}
```

**Or local server**:
```json
{
  "mcpServers": {
    "my-local-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "cwd": "/path/to/server",
      "env": {
        "DATABASE_URL": "${DATABASE_URL}"
      }
    }
  }
}
```

**Verify the server starts**:
```bash
claude mcp list            # List configured servers
claude mcp get my-server   # Check server status
```

---

### Phase 2 — Build a Custom MCP Server (Python/FastMCP)

**Skill**: Load `mcp-builder` (`.claude/skills/mcp-builder/SKILL.md`)

**When to build a custom MCP**:
- Your team has an internal API Claude Code should be able to query
- A third-party service doesn't have an MCP but you need documentation or data from it
- You want to expose company-specific data (internal wikis, design systems, API catalogs)

**FastMCP (Python) — fastest path**:
```python
# server.py
from fastmcp import FastMCP, Context
import httpx

mcp = FastMCP("my-internal-api")

@mcp.tool()
async def search_internal_docs(query: str, ctx: Context) -> str:
    """Search the internal documentation wiki.

    Args:
        query: Search query string
    Returns:
        Matching documentation snippets
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://wiki.internal/api/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {os.environ['WIKI_API_KEY']}"},
        )
        response.raise_for_status()
        results = response.json()
        return "\n\n".join([r["content"] for r in results["hits"][:5]])

@mcp.resource("docs://catalog")
async def list_doc_categories() -> str:
    """List all documentation categories."""
    # Return available categories as a resource
    return "Engineering, Design, Product, Operations"

if __name__ == "__main__":
    mcp.run()
```

**Install and run**:
```bash
uv init my-mcp-server
uv add fastmcp httpx
uv run python server.py
```

---

### Phase 3 — Build a Custom MCP Server (TypeScript)

```typescript
// server.ts — TypeScript MCP SDK
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({
  name: "my-ts-mcp",
  version: "1.0.0",
}, {
  capabilities: { tools: {} },
});

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "search_api_catalog",
    description: "Search the internal API catalog for endpoint documentation",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
      },
      required: ["query"],
    },
  }],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name === "search_api_catalog") {
    const { query } = request.params.arguments as { query: string };
    // Call your internal API
    const results = await fetchApiCatalog(query);
    return { content: [{ type: "text", text: JSON.stringify(results) }] };
  }
  throw new Error(`Unknown tool: ${request.params.name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

---

### Phase 4 — Register in Claude Code Settings

After building:

```json
{
  "mcpServers": {
    "my-new-server": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/my-mcp-server",
      "env": {
        "WIKI_API_KEY": "${WIKI_API_KEY}"
      }
    }
  }
}
```

**Test**:
```bash
# Restart Claude Code
# Then verify the tool is available
# It should appear in the available-deferred-tools list
```

---

### Phase 5 — Update CLAUDE.md Skill Mapping

After adding a new MCP server, update CLAUDE.md to tell Claude when to use it:

```markdown
# In CLAUDE.md — Documentation First section
- **`my-new-server`** MCP for [internal API name] — query before working with [domain]
```

And update the relevant skill's `SKILL.md` to reference the new MCP:

```markdown
# In skills/my-domain/SKILL.md
## MCP Servers
1. `my-new-server` — search internal docs before implementing
2. `context7` — fallback for external library docs
```

---

## Quick Reference

| Task | Action | File |
|------|--------|------|
| Add existing MCP | Add to `mcpServers` block | `.claude/settings.json` |
| Build Python MCP | FastMCP with `@mcp.tool()` | New Python project |
| Build TypeScript MCP | MCP SDK with `server.setRequestHandler` | New TS project |
| Register custom MCP | Add `command` + `cwd` + `env` | `.claude/settings.json` |
| Document the MCP | Update skill SKILL.md + CLAUDE.md | Relevant skill file |

---

## Common Pitfalls

- **Secrets in settings.json** — use `${ENV_VAR}` interpolation, never hardcode API keys
- **No `cwd` for local servers** — local servers need `cwd` set to the server directory
- **No error handling in custom server** — if your MCP tool throws, Claude gets an unhelpful error; wrap in try/catch with descriptive messages
- **Not updating skills** — adding an MCP without updating the skill's MCP lookup order means it won't be used
- **Too many tools in one server** — 10+ tools in one MCP makes it hard for Claude to find the right one; split by domain

## Related Workflows

- [`new-skill-creation.md`](new-skill-creation.md) — skills reference MCP servers
- [`developer-onboarding.md`](developer-onboarding.md) — new developers configure MCP servers during onboarding
