# MCP Server Setup

> **When to use**: Adding an MCP (Model Context Protocol) server to the workspace, or building a custom MCP server for a new integration
> **Time estimate**: 30 min to configure an existing server; 2–4 hours to build a custom one
> **Prerequisites**: Claude Code installed; MCP server package or source available; Node 26 LTS (TypeScript servers) or Python 3.14 + uv (Python servers)

## Overview

Configuring MCP servers for Claude Code, and building custom servers with the official SDKs: TypeScript SDK v2 (`@modelcontextprotocol/server`) or Python SDK v2 (`mcp`, `MCPServer`). Protocol revision 2026-07-28; transports are **stdio** (local) and **Streamable HTTP** (remote). The 2024-11-05 HTTP+SSE transport is deprecated: never use it for new servers. Patterns, security and production guidance live in the `mcp-builder` skill.

Verified 2026-11-23 against `@modelcontextprotocol/server@2.4.0`, `@modelcontextprotocol/client@2.4.0`, `@modelcontextprotocol/node@2.1.2`, `@modelcontextprotocol/fastify@2.0.1`, Node 26.13.1, TypeScript 6.0.3 and Claude Code 2.1.331 (`claude mcp add --help`).

---

## Current MCP Servers (this workspace)

Project-scoped servers are defined in `.mcp.json` at the repo root (shared through git). Each one is reviewed before use: see `.claude/rules/skill-triggers.md` §P0 for the trust table.

| MCP Server | Purpose | When Used |
|-----------|---------|----------|
| `context7` | Library documentation lookup | Before writing any code — resolve library ID + query docs |
| `angular-cli` | Angular 22.x patterns, best practices (`get_best_practices` with `workspacePath`), docs (`search_documentation` version 22), project discovery | Before writing Angular code |
| `dart-mcp-server` | Flutter/Dart tooling, device lists, test runner | Before writing Flutter code |
| `firebase` | Firebase project, rules, SDK config | Firebase integration |
| `chrome-devtools` | Browser inspection, performance, network | Web (Angular/React) browser testing |
| `xcodebuild` | iOS build, simulator, test runner | iOS release workflow |
| `weaviate-docs` | Weaviate documentation search | Weaviate collection/RAG work |
| `langchain-docs` | LangChain documentation | Agentic AI work |

The full list is in `.mcp.json`.

---

## Phases

### Phase 1 — Configure an Existing MCP Server

Add it with the CLI (`-s project` writes `.mcp.json`; the default `local` scope keeps it private to you):

```bash
# stdio server, exact version pinned
claude mcp add -s project my-server -e API_KEY='${MY_API_KEY}' -- npx -y @scope/my-mcp-server@1.4.2

# remote Streamable HTTP server
claude mcp add -s project --transport http my-remote https://mcp.example.com/mcp

claude mcp list            # configured servers and connection status
claude mcp get my-server   # one server's config
```

Or edit `.mcp.json` directly:

```json
{
  "mcpServers": {
    "my-new-server": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@scope/my-mcp-server@1.4.2"],
      "env": { "API_KEY": "${MY_API_KEY}" }
    },
    "my-remote": {
      "type": "http",
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

- Pin an exact version (`@1.4.2`), never `@latest`: an unpinned package can change under you between sessions.
- Secrets come from the environment (`${VAR}`), never literal values in `args`, `env` or `headers`.
- Run the §P0 security scan from `skill-triggers.md` before trusting a new server, and add it to the trust table.

---

### Phase 2 — Build a Custom MCP Server

**Skill**: load `mcp-builder` (`.claude/skills/mcp-builder/SKILL.md`) first. Build one when your team has an internal API, data source or catalog that Claude Code should query and no maintained server exists.

**Python** (`mcp` SDK v2, `from mcp.server import MCPServer`): follow [python-mcp-setup.md](../../.claude/skills/mcp-builder/reference/python-mcp-setup.md) and [python-mcp-patterns.md](../../.claude/skills/mcp-builder/reference/python-mcp-patterns.md). The standalone `fastmcp` package is a different project; use the official SDK.

**TypeScript** (SDK v2). Exact pins, `"type": "module"`:

```bash
npm i -E @modelcontextprotocol/server@2.4.0 zod@4.6.7 pino@10.4.0
npm i -E -D typescript@6.0.3 @types/node@26.6.6 @modelcontextprotocol/client@2.4.0 vitest@5.1.1
```

One tool registry, used by every transport:

```typescript
// src/tools.ts
import { setTimeout as delay } from 'node:timers/promises';
import type { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

export function registerTools(server: McpServer): McpServer {
  server.registerTool(
    'orders_total',
    {
      description: 'Sum order totals in cents',
      inputSchema: z.object({ cents: z.array(z.number().int().nonnegative()).max(100) }),
      outputSchema: z.object({ total: z.number().int() }),
      annotations: { readOnlyHint: true, idempotentHint: true },
    },
    ({ cents }) => {
      const output = { total: cents.reduce((a, b) => a + b, 0) };
      return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
    },
  );
  server.registerTool(
    'slow_report',
    {
      description: 'Long-running report; stops when the caller cancels',
      inputSchema: z.object({ ms: z.number().int().min(0).max(30_000) }),
      annotations: { readOnlyHint: true },
    },
    async ({ ms }, ctx) => {
      await delay(ms, undefined, { signal: ctx.mcpReq.signal }); // forward the signal to every await
      return { content: [{ type: 'text', text: `done after ${ms} ms` }] };
    },
  );
  return server;
}
```

stdio entry point (what Claude Code spawns):

```typescript
// src/server-stdio.ts
import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { pino } from 'pino';
import { registerTools } from './tools.js';

// stdout carries the protocol: every log line goes to stderr (fd 2). Never console.log.
const logger = pino({}, pino.destination(2));
const handle = serveStdio(() => registerTools(new McpServer({ name: 'orders-mcp', version: '1.0.0' })));
logger.info('listening on stdio');

for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  process.once(signal, () => {
    handle
      .close()
      .then(() => process.exit(0))
      .catch((err: unknown) => {
        logger.error({ err }, 'stdio_shutdown_failed');
        process.exit(1);
      });
  });
}
```

Verified with a real SDK `Client` over stdio: tools listed and called, a client cancel aborted `slow_report`, and closing stdin mid-call aborted the in-flight handler and the process exited.

**Remote (Streamable HTTP)**: the same `registerTools` behind `createMcpHandler`, on `node:http` or Fastify, with Host/Origin allow-lists, a body limit, authentication and graceful shutdown. Code and test results: [node-mcp-advanced.md](../../.claude/skills/mcp-builder/reference/node-mcp-advanced.md#streamable-http-on-fastify) and [production-runtime-shutdown-health.md](../../.claude/skills/mcp-builder/reference/production-runtime-shutdown-health.md). Authorization: [security-core.md](../../.claude/skills/mcp-builder/reference/security-core.md).

**Do not** start new code on the v1 package (`@modelcontextprotocol/sdk`, `new Server(...)` + `setRequestHandler(ListToolsRequestSchema, ...)`, `server.tool(...)`, `SSEServerTransport`): v1 is in maintenance. Migration notes: [node-mcp-setup.md](../../.claude/skills/mcp-builder/reference/node-mcp-setup.md).

---

### Phase 3 — Test Before Registering

```bash
npx tsc -p tsconfig.json                     # strict, exit 0
npx vitest run                               # tests through a real Client (see node-mcp-advanced.md "Testing")
npx @modelcontextprotocol/inspector@2.16.0 --cli node dist/server-stdio.js --method tools/list
```

---

### Phase 4 — Register in Claude Code

```bash
claude mcp add -s project orders -- node /abs/path/to/orders-mcp/dist/server-stdio.js
claude mcp get orders
```

Restart Claude Code; the server's tools then appear in the session's tool list (`/mcp` shows status).

---

### Phase 5 — Update the Skill Mapping

After adding a new MCP server, tell Claude when to use it: add it to the relevant skill's `SKILL.md` MCP lookup order and, if it is cross-cutting, to `CLAUDE.md`.

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
| Add existing MCP | `claude mcp add -s project …` (pinned version) | `.mcp.json` |
| Build Python MCP | SDK v2 `MCPServer` + `@mcp.tool()` | New Python project |
| Build TypeScript MCP | SDK v2 `McpServer.registerTool` + `serveStdio` / `createMcpHandler` | New TS project |
| Register custom MCP | `claude mcp add` with an absolute path | `.mcp.json` |
| Document the MCP | Update skill SKILL.md + CLAUDE.md | Relevant skill file |

---

## Common Pitfalls

- **Secrets in `.mcp.json`** — use `${ENV_VAR}` expansion, never literal keys in `args`, `env` or `headers`
- **`@latest` or unpinned packages** — pin the exact version
- **Logging to stdout in a stdio server** — it corrupts the protocol stream; log to stderr
- **Throwing generic errors from tools** — return `isError: true` results with a recovery hint the model can act on (`mcp-builder` error taxonomy)
- **Remote server without Host/Origin validation and auth** — DNS-rebinding and unauthenticated access; see the security references
- **Not updating skills** — an MCP the skills never mention is rarely used
- **Too many tools in one server** — keep tools intent-based and split by domain

## Related Workflows

- [`new-skill-creation.md`](new-skill-creation.md) — skills reference MCP servers
- [`developer-onboarding.md`](developer-onboarding.md) — new developers configure MCP servers during onboarding
