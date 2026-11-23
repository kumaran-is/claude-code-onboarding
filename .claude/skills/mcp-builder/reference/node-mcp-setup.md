# Node/TypeScript MCP Server — Setup and Configuration

Project setup for MCP servers on the **official MCP TypeScript SDK v2** (stable line, implements spec revision **2026-07-28** and still serves 2025-era clients). Covers packages, pinned versions, project layout, the two entry points (stdio and Streamable HTTP) and build/run.

> Verified 2026-11-23 against `@modelcontextprotocol/server@2.4.0`, `@modelcontextprotocol/client@2.4.0`, `@modelcontextprotocol/node@2.1.2`, `zod@4.6.7`, TypeScript 5.9.3 strict, Node 24. Every `typescript` block in the `node-mcp-*` files was type-checked in a disposable project, and the behaviours described were exercised with a real SDK `Client` over stdio and Streamable HTTP. Re-check versions with `npm view <pkg> version` before you start.

---

## SDK v1 vs v2 — which package

| | v2 (use for new work) | v1 (maintenance only) |
|---|---|---|
| Packages | `@modelcontextprotocol/server`, `@modelcontextprotocol/client` (+ optional `@modelcontextprotocol/node` / `express` / `fastify` / `hono` adapters) | single `@modelcontextprotocol/sdk` (1.32.x) |
| Protocol | 2026-07-28 ("modern") **and** 2024-10-07 … 2025-11-25 ("legacy") from one entry point | legacy only (`LATEST_PROTOCOL_VERSION` = `2025-11-25`) |
| Imports | package roots + subpaths (`@modelcontextprotocol/server/stdio`) | deep paths (`@modelcontextprotocol/sdk/server/mcp.js`) |
| Errors | `ProtocolError` / `ProtocolErrorCode` | `McpError` / `ErrorCode` |
| Tools | `registerTool(name, { inputSchema: z.object(...) }, handler)` | `registerTool` (the older `server.tool()` is `@deprecated`) |

Migrating v1 code: run `npx @modelcontextprotocol/codemod@2.4.0 v1-to-v2 .` at the package root, then `grep -rn '@mcp-codemod-error' .` and `tsc --noEmit`. Guide: https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2.md

---

## Install (pinned)

```bash
npm pkg set type=module
npm i -E @modelcontextprotocol/server@2.4.0 zod@4.6.7 pino@10.4.0
npm i -E @modelcontextprotocol/node@2.1.2            # only if you serve HTTP on node:http
npm i -E -D typescript@5.9.3 tsx@4.23.15 @types/node@24.19.2 vitest@5.1.1
npm i -E -D @modelcontextprotocol/client@2.4.0       # tests drive the server through a real Client
```

- Import Zod as `import * as z from 'zod/v4'` — that is the form the SDK documents and the one these files were checked with.
- TypeScript ≥ 6 no longer auto-includes `@types/*`: keep `"types": ["node"]` in `tsconfig.json` (harmless on 5.9).

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "types": ["node"],
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "outDir": "dist",
    "rootDir": "src",
    "sourceMap": true
  },
  "include": ["src/**/*.ts"]
}
```

### package.json scripts

```json
{
  "type": "module",
  "engines": { "node": ">=24" },
  "scripts": {
    "build": "tsc -p .",
    "typecheck": "tsc -p . --noEmit",
    "start:stdio": "node dist/stdio.js",
    "start:http": "node dist/http.js",
    "test": "vitest run"
  }
}
```

---

## Naming

- Server name: `{service}-mcp-server` (lowercase, hyphens, no version or date) — e.g. `orders-mcp-server`.
- Tool names: `snake_case`, prefixed with the service (`orders_list`, not `list`) so they do not collide when a host loads several servers. Tool names are case-sensitive and should stay within `A-Z a-z 0-9 _ - .` (spec 2026-07-28, *Tools → Tool names*).

---

## Project layout

```
orders-mcp-server/
├── src/
│   ├── server.ts        # createServer(): McpServer — registers tools/resources/prompts (no transport code)
│   ├── stdio.ts         # entry: serveStdio(createServer)
│   ├── http.ts          # entry: createMcpHandler(createServer) behind Host/Origin guards (+ auth, see security-core.md)
│   ├── tools/           # one file per domain; each exports register<Domain>Tools(server, deps)
│   ├── clients/         # typed upstream API clients (fetch + AbortSignal)
│   ├── config.ts        # zod-validated env, read once at startup — fail fast
│   └── logger.ts        # pino to stderr
├── test/                # vitest: drive createServer() through a real Client
└── tsconfig.json
```

Keep **one factory** (`createServer`) and two thin entry files. The factory must be cheap and side-effect free: v2 calls it once per stdio connection and **once per HTTP request**. Create pools, caches and API clients once at module scope and close over them.

For the 3-layer production layout (transport / protocol / business) see [production-deployment-structure.md](production-deployment-structure.md).

---

## Logger (stderr only)

On stdio, **stdout is the JSON-RPC channel** — a single stray `console.log` corrupts the stream. Log to stderr (fd 2) everywhere so the same code is safe on both transports.

```typescript
import { pino } from 'pino';

export const logger = pino({ level: process.env.LOG_LEVEL ?? 'info' }, pino.destination(2));
```

---

## Server factory

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

export function createServer(): McpServer {
  const server = new McpServer({ name: 'orders-mcp-server', version: '1.0.0' });

  server.registerTool(
    'orders_get_status',
    {
      title: 'Get order status',
      description: 'Return the fulfilment status of one order. Use when the user asks where an order is.',
      inputSchema: z.object({ order_id: z.string().regex(/^ord_\d{3,}$/).describe('Order id, e.g. ord_001') }),
      outputSchema: z.object({ order_id: z.string(), status: z.enum(['pending', 'shipped', 'delivered']) }),
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async ({ order_id }) => {
      const output = { order_id, status: 'pending' as const };
      return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
    },
  );

  return server;
}
```

`registerTool` / `registerResource` / `registerPrompt` are the only registration APIs to use. The low-level `Server` + `setRequestHandler('tools/list', …)` is for protocol-level work only (custom pagination of list results, custom methods) — see [node-mcp-patterns-advanced.md](node-mcp-patterns-advanced.md).

---

## Entry point: stdio (local, host-launched)

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { pino } from 'pino';

const logger = pino({}, pino.destination(2));

function createServer(): McpServer {
  return new McpServer({ name: 'orders-mcp-server', version: '1.0.0' });
}

const handle = serveStdio(createServer); // serves 2026-07-28 and 2025-era clients; pass { legacy: 'reject' } to refuse 2025 openings
logger.info('orders-mcp-server listening on stdio');

process.on('SIGTERM', () => {
  handle.close().catch((err: unknown) => {
    logger.error({ err }, 'stdio shutdown failed');
    process.exitCode = 1;
  });
});
```

When the host closes stdin the transport closes itself; in-flight requests are aborted.

## Entry point: Streamable HTTP (remote, many clients)

```typescript
import { createServer as createHttpServer } from 'node:http';
import { localhostHostValidation, localhostOriginValidation, toNodeHandler } from '@modelcontextprotocol/node';
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import { pino } from 'pino';

const logger = pino({}, pino.destination(2));
const port = Number(process.env.PORT ?? '3000');

function createServer(): McpServer {
  return new McpServer({ name: 'orders-mcp-server', version: '1.0.0' });
}

// One fresh McpServer per HTTP request; nothing is held between requests (no sessions).
const handler = createMcpHandler(createServer);
const nodeHandler = toNodeHandler(handler);
const validateHost = localhostHostValidation();
const validateOrigin = localhostOriginValidation();

const httpServer = createHttpServer((req, res) => {
  // createMcpHandler validates no Host/Origin and verifies no token: put both in front of it.
  if (!validateHost(req, res) || !validateOrigin(req, res)) return;
  if (req.url !== '/mcp') {
    res.writeHead(404).end();
    return;
  }
  void nodeHandler(req, res);
}).listen(port, '127.0.0.1', () => logger.info({ port }, 'listening on /mcp'));

process.on('SIGTERM', () => {
  handler
    .close()
    .then(() => httpServer.close())
    .catch((err: unknown) => {
      logger.error({ err }, 'http shutdown failed');
      process.exitCode = 1;
    });
});
```

- Bind `127.0.0.1` locally. Behind a load balancer bind `0.0.0.0` **and** pass an explicit allow-list (`hostHeaderValidation([...])` / `originValidation([...])`, or `createMcpFastifyApp({ host: '0.0.0.0', allowedHosts: [...] })`). The spec requires servers to validate `Origin` and answer an invalid one with `403`.
- Authentication (bearer verification, protected-resource metadata, scopes) is **not** done by `createMcpHandler`: see [security-core.md](security-core.md).
- Fastify instead of `node:http`: `createMcpFastifyApp()` from `@modelcontextprotocol/fastify@2.0.1` arms the Host/Origin checks by default; mount with `app.all('/mcp', (req, reply) => node(req.raw, reply.raw, req.body))`.

---

## Build, run, inspect

```bash
npm run typecheck && npm run build
npx @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/list
npx @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/call --tool-name orders_get_status --tool-arg order_id=ord_001
npx @modelcontextprotocol/inspector@2.16.0 node dist/stdio.js      # web UI
```

The Inspector CLI exits non-zero when a call returns `isError: true` (verified: exit 5), so it can gate a smoke step in CI. Full testing guidance: [node-mcp-advanced.md](node-mcp-advanced.md#testing-and-conformance).
