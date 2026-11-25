# NestJS MCP: `@nestjs/mcp` (an MCP server inside a Nest app) and the Observe MCP server

The MCP section of the official docs (docs.nestjs.com/mcp/overview, /primitives, /transports, /testing, /migration)
documents **`@nestjs/mcp`**, a package that turns a Nest application into a Model Context Protocol server. It is not
a documentation server for coding agents: NestJS publishes no docs MCP server. Consult NestJS docs through Context7,
then docs.nestjs.com (see `SKILL.md` → Documentation Sources).

| Option | Status here | Why |
|---|---|---|
| `@nestjs/mcp` 0.0.4 + `@modelcontextprotocol/server` 2.4.0 | OPTIONAL (pre-1.0) | Official, MIT, peers `@nestjs/core ^12` and SDK v2 `^2.4.0` (the toolkit's MCP line); first published 2026-11-04. Use it to expose tools from an **existing** Nest 12 service so they reuse its providers, guards and interceptors. A standalone MCP server stays on `/scaffold-mcp-server` (`mcp-builder`). |
| `@rekog/mcp-nest` (community) | Do not use for new code | The docs' migration page moves it to `@nestjs/mcp` |
| NestJS Observe MCP server (`https://observe-api.nestjs.com/mcp`) | DEFER | Reads Observe data (traces, errors, regressions), not docs; included only in paid plans (Pro and above); needs an Observe account and a personal `omcp_` token. Same decision as `@nestjs/observe` |

Verified 2026-11-24 on NestJS 12.6.0 + Fastify 5.12.8 + Zod 4.6.7, Node 26.13.1. The test below passed 5/5:
- tools/list returns an object `inputSchema` and `readOnlyHint`;
- a call returns `structuredContent`;
- `NotFoundException` comes back as `isError` with its message;
- a smuggled argument on a `z.strictObject` is rejected;
- a foreign `Host` header gets a 4xx.

Planted bug: `strictObject` → `object` failed the smuggled-argument test.

## Install

```bash
npm i -E @nestjs/mcp@0.0.4 @modelcontextprotocol/server@2.4.0
npm i -D -E @modelcontextprotocol/client@2.4.0   # connectMcpClient in tests
```

Zod 4.2+ (the project's `zod` 4.6.7); Zod 3 schemas are refused at startup. The package is ESM (`"type": "module"`),
which matches a NestJS 12 project.

## Tools on existing providers

```typescript
// src/orders/order.tools.ts
import { Injectable, NotFoundException } from '@nestjs/common';
import { Tool } from '@nestjs/mcp';
import { z } from 'zod';
import { OrdersService } from './orders.service.js';

const OrderSchema = z.object({ id: z.string(), status: z.enum(['open', 'shipped']) });

@Injectable()
export class OrderTools {
  constructor(private readonly orders: OrdersService) {}

  @Tool({
    name: 'find-order', // [A-Za-z0-9_.-]{1,128}, unique: duplicates fail at startup
    description: 'Find one order by id', // written for the model: it picks the tool by this text
    inputSchema: z.strictObject({ orderId: z.string().min(1).describe('The order id') }),
    outputSchema: OrderSchema,
    annotations: { readOnlyHint: true }, // a hint to the client, never authorization
  })
  async find({ orderId }: { orderId: string }) {
    const order = await this.orders.findById(orderId);
    // An HttpException message reaches the model as isError: true; other errors become "Internal server error".
    if (order === null) throw new NotFoundException(`order ${orderId} not found`);
    return order;
  }
}
```

```typescript
// src/app.module.ts (excerpt): McpModule is imported once, in the root module
McpModule.forRoot({
  name: 'orders',
  version: '1.0.0',
  instructions: 'Look up orders with find-order.',
  // Streamable HTTP at /mcp on the existing Fastify app; refuse other Host headers (DNS rebinding).
  http: { allowedHosts: ['localhost', '127.0.0.1'] },
}),
```

The tool class is a normal provider: list it in its feature module's `providers`. Request-scoped providers are refused
at startup.

## Security

- Tool arguments are external input. Each tool declares an `inputSchema`, a `z.strictObject` for objects, and
  derives tenant and user from the verified auth context, never from arguments.
- Remote exposure needs authentication: `McpModule.forRoot({ auth: { verifier, resource, authorizationServers } })`
  (OAuth 2.1 resource server with an `McpTokenVerifier`). `scopes` on a primitive without `auth` fails at startup.
  The auth path is documented upstream but was NOT RUN here: test it before relying on it.
- Set `http.allowedHosts` (and `allowedOrigins` for browser clients) for every deployment, not only for localhost.
- Side-effecting tools need human approval in this toolkit (`typescript-node-backend.md` → MCP servers).
- stdio: run a standalone application context with `McpStdioServer` and log through `McpStdioLogger` to stderr, since
  stdout carries the protocol. This mode is documented upstream but NOT RUN here.

## Test

```typescript
// test/mcp.e2e-spec.ts (excerpt; the verified run used an in-file module with the same tool)
import type { AddressInfo } from 'node:net';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { connectMcpClient } from '@nestjs/mcp/testing';
import type { Client } from '@modelcontextprotocol/client';

let app: NestFastifyApplication;
let client: Client;
beforeAll(async () => {
  const moduleRef = await Test.createTestingModule({ imports: [McpAppModule] }).compile();
  app = moduleRef.createNestApplication<NestFastifyApplication>(new FastifyAdapter(), { logger: false });
  await app.listen(0, '127.0.0.1');
  client = await connectMcpClient(app);
});
afterAll(async () => {
  await client.close();
  await app.close();
});

it('calls the tool and returns structured content', async () => {
  const res = await client.callTool({ name: 'find-order', arguments: { orderId: 'o-1' } });
  expect(res.structuredContent).toEqual({ id: 'o-1', status: 'open' });
});
it('rejects arguments that break the input schema', async () => {
  const res = await client
    .callTool({ name: 'find-order', arguments: { orderId: 'o-1', tenantId: 'x' } })
    .catch((e: unknown) => ({ isError: true, content: String(e) }));
  expect(res.isError).toBe(true);
});
it('refuses a foreign Host header (DNS rebinding)', async () => {
  const res = await app.inject({
    method: 'POST',
    url: '/mcp',
    headers: { host: 'evil.example', 'content-type': 'application/json', accept: 'application/json, text/event-stream' },
    payload: { jsonrpc: '2.0', id: 1, method: 'tools/list' },
  });
  expect(res.statusCode).toBeGreaterThanOrEqual(400);
});
```

`/verify full` also runs its MCP gate on a NestJS package that depends on `@modelcontextprotocol/server` (`nest+mcp`).
Set `MCP_SERVER_URL=http://127.0.0.1:3000/mcp` while the app is running.

## Observe MCP server (DEFER)

If an approved paid Observe account exists, the server is added with
`claude mcp add observe --transport http https://observe-api.nestjs.com/mcp` and OAuth through `/mcp`. Do not
add it to `.mcp.json` without the skill/MCP security scan, the allowlist and checksum update
(`.claude/rules/skill-triggers.md`) and explicit approval. Never put an `omcp_` token in an argument or a committed
file.
