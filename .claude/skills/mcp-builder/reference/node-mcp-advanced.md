# Node/TypeScript MCP Server — Resources, Prompts, User Input, Transports, Protocol Versions, Testing

SDK v2 (`@modelcontextprotocol/server@2.4.0`, `@modelcontextprotocol/client@2.4.0`). Every `typescript` block type-checks under `strict`; behaviours marked *verified* were exercised with a real SDK `Client`. Setup: [node-mcp-setup.md](node-mcp-setup.md) · tools: [node-mcp-patterns.md](node-mcp-patterns.md) · pagination/progress/cancellation: [node-mcp-patterns-advanced.md](node-mcp-patterns-advanced.md).

---

## Primitives and who controls them

| Primitive | Controlled by | Use for | Error channel |
|---|---|---|---|
| Tool | the **model** decides to call | actions, queries with logic or side effects | `isError: true` result (model reads it) |
| Resource | the **application** decides to read | read-only data addressed by URI | JSON-RPC error (`ProtocolError`) |
| Prompt | the **user** picks it (slash command, menu) | reusable message templates | JSON-RPC error |

---

## Resources

```typescript
import { McpServer, ResourceNotFoundError, ResourceTemplate } from '@modelcontextprotocol/server';

declare function loadOrder(id: string): Promise<{ id: string; status: string } | undefined>;
declare function recentOrderIds(): Promise<string[]>;

export function registerOrderResources(server: McpServer): void {
  // Static resource: fixed URI.
  server.registerResource(
    'orders-schema',
    'orders://schema',
    { title: 'Order JSON schema', description: 'Shape of an order record', mimeType: 'application/schema+json' },
    async (uri) => ({ contents: [{ uri: uri.href, mimeType: 'application/schema+json', text: '{"type":"object"}' }] }),
  );

  // Template: orders://{id}. The list callback makes concrete URIs appear in resources/list;
  // use { list: undefined } when the set is not enumerable.
  server.registerResource(
    'order',
    new ResourceTemplate('orders://{id}', {
      list: async () => ({
        resources: (await recentOrderIds()).map((id) => ({ uri: `orders://${id}`, name: id, mimeType: 'application/json' })),
      }),
    }),
    { description: 'One order as JSON', mimeType: 'application/json' },
    async (uri, { id }) => {
      const order = await loadOrder(String(id));
      if (order === undefined) throw new ResourceNotFoundError(uri.href);
      return { contents: [{ uri: uri.href, mimeType: 'application/json', text: JSON.stringify(order) }] };
    },
  );
}
```

- A missing resource is `ResourceNotFoundError` → JSON-RPC `-32602` with `data.uri`. The 2026-07-28 spec moved this from `-32002` to `-32602` (SEP-2164); the SDK only *receives* `-32002` for old peers. Verified: reading `orders://nope` rejects with `ProtocolError` on stdio and HTTP.
- Any other exception from a resource callback becomes `-32603` Internal Error — validate template variables and throw `ProtocolError(ProtocolErrorCode.InvalidParams, …)` for malformed ids.
- Resource URIs are not authorization: check the caller's access to `id` inside the callback ([security-core.md](security-core.md)).
- Subscriptions: in 2026-07-28 clients subscribe to `resourceSubscriptions` on a `subscriptions/listen` stream (`resources/subscribe` / `unsubscribe` were removed); publish with `handler.notify.resourceUpdated(uri)` — see [node-mcp-patterns-advanced.md](node-mcp-patterns-advanced.md#change-notifications).

## Prompts

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

export function registerOrderPrompts(server: McpServer): void {
  server.registerPrompt(
    'orders_summarize',
    {
      title: 'Summarize an order',
      description: 'Draft a support-agent summary of one order',
      argsSchema: z.object({
        order_id: z.string().describe('Order id, e.g. ord_001'),
        tone: z.enum(['brief', 'detailed']).optional(),
      }),
    },
    ({ order_id, tone }) => ({
      messages: [
        {
          role: 'user' as const,
          content: { type: 'text' as const, text: `Summarize order ${order_id} for a support agent (${tone ?? 'brief'}).` },
        },
      ],
    }),
  );
}
```

`argsSchema` is a Zod object; prompt arguments arrive as strings on the wire.

---

## Asking the user mid-call (elicitation via Multi Round-Trip Requests)

In 2026-07-28 a server never sends its own request to the client. A `tools/call`, `prompts/get` or `resources/read` handler **returns** `inputRequired(...)` (`resultType: "input_required"`); the client gathers the answer and **retries the same call** with `inputResponses` (SEP-2322). The 2025-era push APIs (`ctx.mcpReq.elicitInput`, `requestSampling`) throw on a 2026-07-28 request.

```typescript
import { acceptedContent, inputRequired, inputResponse, McpServer, type CallToolResult, type InputRequiredResult } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const Confirm = z.object({ confirm: z.boolean() });
declare function cancelOrder(id: string): Promise<void>;

export function registerCancel(server: McpServer): void {
  server.registerTool(
    'orders_cancel',
    {
      description: 'Cancel an order. Asks the user to confirm before cancelling.',
      inputSchema: z.object({ order_id: z.string() }),
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
    },
    async ({ order_id }, ctx): Promise<CallToolResult | InputRequiredResult> => {
      // 1. A declined or cancelled prompt ends the call. Without this check the client re-asks until maxRounds.
      const view = inputResponse(ctx.mcpReq.inputResponses, 'confirm');
      if (view.kind === 'elicit' && view.action !== 'accept') {
        return { isError: true, content: [{ type: 'text', text: `User did not confirm; ${order_id} was not cancelled.` }] };
      }
      // 2. inputResponses come from the client: validate them with the same schema.
      const answer = acceptedContent(ctx.mcpReq.inputResponses, 'confirm', Confirm);
      if (answer === undefined) {
        return inputRequired({ inputRequests: { confirm: inputRequired.elicit({ message: `Cancel order ${order_id}?`, requestedSchema: Confirm }) } });
      }
      if (!answer.confirm) {
        return { isError: true, content: [{ type: 'text', text: `User said no; ${order_id} was not cancelled.` }] };
      }
      await cancelOrder(order_id);
      return { content: [{ type: 'text', text: `Cancelled ${order_id}` }] };
    },
  );
}
```

Verified (client declares `capabilities: { elicitation: { form: {} } }` and handles `elicitation/create`):

| Connection | Accept + yes | Decline |
|---|---|---|
| modern, stdio and HTTP | asked once, action ran | asked once, `isError` result |
| legacy, stdio | SDK bridged the input request to a 2025 `elicitation/create` push; action ran | — |
| legacy, **stateless HTTP** (`createMcpHandler`) | **not asked**; `isError`: "per-request legacy serving cannot receive server-to-client requests" | — |
| modern, handler **without** the decline check (negative control) | — | asked 10 times, then `SdkError … still required input after 10 rounds` |

Rules: the handler re-runs from the top on every round, so everything before the `inputRequired` return must be side-effect free; carry server state between rounds in `requestState` (opaque, integrity-protect it), never in memory; elicitation is for user decisions, never for secrets (use URL-mode elicitation for credentials — see security files). **Sampling** and **Roots** are Deprecated in 2026-07-28 (SEP-2577): call your LLM provider directly instead of sampling; pass paths as tool arguments or configuration instead of roots.

---

## Transports and protocol eras

**Two transports only for new work: stdio and Streamable HTTP.** The 2024-11-05 HTTP+SSE transport (separate `GET /sse` + `POST /messages`) is Deprecated (since 2025-03-26; formally under SEP-2596); keep it only behind a migration shim (`@modelcontextprotocol/server-legacy`), never in new code.

| | 2026-07-28 ("modern") | 2025-03-26 … 2025-11-25 ("legacy") |
|---|---|---|
| Opening | none — every request carries `_meta`: `io.modelcontextprotocol/protocolVersion`, `clientCapabilities`, `clientInfo` | `initialize` / `notifications/initialized` handshake |
| Discovery | `server/discover` (servers **MUST** implement) | `initialize` result |
| Version mismatch | `400` + `UnsupportedProtocolVersionError` `-32022` with `data.supported` | server answers `initialize` with a version it supports |
| HTTP headers | `MCP-Protocol-Version` (must equal `_meta`), `Mcp-Method`, `Mcp-Name` (tools/call, resources/read, prompts/get); mismatch → `400` `HeaderMismatch` `-32020` | `MCP-Protocol-Version` (2025-06-18+), `Mcp-Session-Id` |
| Sessions | **none** — no `Mcp-Session-Id`; cross-call state uses explicit handles | optional, server-minted `Mcp-Session-Id`, ended with `DELETE` |
| Server → client notifications | per-request SSE stream (progress), `subscriptions/listen` stream (changes) | per-request stream + standalone `GET` SSE stream |
| Server → client requests | none — `input_required` results (MRTR) | sampling/elicitation/roots pushed on SSE |
| Resumability | **removed** — a broken stream loses the request; re-issue with a new id | `Last-Event-ID` replay with an `EventStore` |
| HTTP cancellation | close the request's SSE stream | `notifications/cancelled` POST |
| `ping`, `logging/setLevel` | removed | present |

Verified on the wire (raw `fetch` to a `createMcpHandler` endpoint): unsupported version `1900-01-01` → `400` + `-32022` with `supported` containing `2026-07-28`; header `2025-11-25` vs `_meta` `2026-07-28` → `400` + `-32020`; `server/discover` → `200`, `resultType: "complete"`; a legacy `initialize` asking for `1900-01-01` → `200` with a supported dated version.

### Serving both eras

`serveStdio(factory)` and `createMcpHandler(factory)` serve modern requests and, by default, 2025-era clients (`legacy: 'stateless'` on HTTP). Pass `{ legacy: 'reject' }` to refuse 2025 openings (verified: a default client's `connect()` rejected; an `auto` client still connected as `modern`). Legacy-stateless HTTP has two limits you must design around (both verified): **no cancellation** reaches the handler, and **no elicitation/sampling** is possible. If 2025-era HTTP clients need those, keep a sessionful `NodeStreamableHTTPServerTransport` for them and route with `isLegacyRequest` in front of `createMcpHandler(factory, { legacy: 'reject' })` (SDK migration guide, *Serving the 2026-07-28 revision*).

### Clients: choosing the era

```typescript
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const client = new Client(
  { name: 'orders-agent', version: '1.0.0' },
  { versionNegotiation: { mode: 'auto', probe: { timeoutMs: 5_000 } } },
);
await client.connect(new StreamableHTTPClientTransport(new URL('https://mcp.example.com/mcp')));
const era = client.getProtocolEra(); // 'modern' | 'legacy'
```

- TypeScript `Client` **defaults to legacy** (`initialize`, no probe). `mode: 'auto'` probes with `server/discover` and falls back; `mode: { pin: '2026-07-28' }` never falls back (verified: rejected with `SdkError` `ERA_NEGOTIATION_FAILED` against a legacy-only server).
- The Python SDK v2 `Client` negotiated `2026-07-28` by default against a v2 server (verified).
- Do not default a spawn-per-invocation CLI to `auto` on stdio: a legacy server that ignores unknown pre-`initialize` requests stalls for the whole probe timeout.
- Cache the era per server origin/process; re-probe when a cached assumption fails.

### Legacy sessions (2025-era only)

Only if you must keep a sessionful 2025 deployment: `NodeStreamableHTTPServerTransport({ sessionIdGenerator: () => randomUUID(), eventStore })`, one transport per session in a map, `404` for unknown session ids, idle timeout and a cap on open sessions, shared `eventStore` (and sticky routing) across replicas. None of this exists in 2026-07-28; plan the migration rather than extending it. Recipe: https://ts.sdk.modelcontextprotocol.io/v2/serving/sessions-state-scaling.md

---

## Testing and conformance

### In-process tests through a real Client (no port, no mocks)

```typescript
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import { describe, expect, test } from 'vitest';
import * as z from 'zod/v4';

function createServer(): McpServer {
  const server = new McpServer({ name: 'orders-mcp-server', version: '1.0.0' });
  server.registerTool(
    'orders_total',
    {
      description: 'Sum order totals in cents',
      inputSchema: z.object({ cents: z.array(z.number().int().nonnegative()).max(100) }),
      outputSchema: z.object({ total: z.number().int() }),
    },
    async ({ cents }) => {
      const output = { total: cents.reduce((a, b) => a + b, 0) };
      return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
    },
  );
  return server;
}

for (const era of ['modern', 'legacy'] as const) {
  describe(`orders_total (${era})`, () => {
    async function connect(): Promise<Client> {
      const handler = createMcpHandler(createServer);
      const client = new Client({ name: 'test', version: '1.0.0' }, era === 'modern' ? { versionNegotiation: { mode: 'auto' } } : {});
      await client.connect(
        new StreamableHTTPClientTransport(new URL('http://test.invalid/mcp'), {
          fetch: (input, init) => handler.fetch(new Request(input, init)),
        }),
      );
      return client;
    }

    test('happy path returns structuredContent', async () => {
      const client = await connect();
      const res = await client.callTool({ name: 'orders_total', arguments: { cents: [100, 250] } });
      expect(res.isError).not.toBe(true);
      expect(res.structuredContent).toEqual({ total: 350 });
      await client.close();
    });

    test('schema violation is a tool error the model can read', async () => {
      const client = await connect();
      const res = await client.callTool({ name: 'orders_total', arguments: { cents: [-1] } });
      expect(res.isError).toBe(true);
      await client.close();
    });
  });
}
```

Run every behaviour test in **both eras** and over **both transports** for anything transport-sensitive (cancellation, elicitation, notifications): the sandbox found era/transport-specific differences that a single-era test would have hidden. Add a negative control for each gate (break the handler, see the test fail).

### Inspector CLI (smoke, scriptable)

```bash
npx @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/list
npx @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/call --tool-name orders_list --tool-arg limit=2
npx @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:3000/mcp --method tools/list
```

Exit code is non-zero when a call returns `isError: true` (verified: exit 5 for an out-of-range argument).

### Official conformance suite

`@modelcontextprotocol/conformance@0.1.16` (`npx @modelcontextprotocol/conformance@0.1.16 list`) has server scenarios for protocol versions **2025-06-18 and 2025-11-25 only** — no 2026-07-28 scenarios in the stable release (a `0.2.0-alpha` line exists; not evaluated). Useful today against an HTTP server:

```bash
npx @modelcontextprotocol/conformance@0.1.16 server --url http://127.0.0.1:3000/mcp --scenario server-initialize
npx @modelcontextprotocol/conformance@0.1.16 server --url http://127.0.0.1:3000/mcp --scenario tools-list
npx @modelcontextprotocol/conformance@0.1.16 server --url http://127.0.0.1:3000/mcp --scenario dns-rebinding-protection
```

Verified: all three pass against the guarded `createMcpHandler` server; with the Host/Origin guards removed `dns-rebinding-protection` fails (exit 1). Most `tools-call-*`, `resources-*` and `prompts-*` scenarios expect fixture tools (for example `test_error_handling`) and fail against a normal server — run them against a conformance fixture build, or keep an expected-failures baseline (`--expected-failures`).

---

## Quality checklist

- [ ] SDK v2 packages pinned exactly; no `@modelcontextprotocol/sdk` deep imports in new code
- [ ] One `createServer()` factory, cheap and side-effect free; `serveStdio` / `createMcpHandler` entry points
- [ ] Logs to stderr only; no `console.log`
- [ ] HTTP: Host/Origin validation and authentication in front of `createMcpHandler`; localhost bind unless an allow-list is configured
- [ ] Every tool: bounded Zod `inputSchema`, `outputSchema` + `structuredContent` + `content`, honest annotations (hints only), recovery hint in error text
- [ ] Resource/prompt callbacks throw `ProtocolError` subclasses, never return empty data on failure
- [ ] Long tools honour `ctx.mcpReq.signal` after every await and forward it to I/O
- [ ] Destructive tools confirm via `inputRequired` and handle decline
- [ ] No reliance on protocol sessions; cross-call state via explicit, authorized, expiring handles
- [ ] Decided and documented which eras you serve (`legacy` option) and the legacy-HTTP limits
- [ ] Tests through a real `Client` in both eras; Inspector CLI smoke; conformance `server-initialize`, `tools-list`, `dns-rebinding-protection`
- [ ] House conventions from the main skill: `next_actions` / `suggestion`, error taxonomy, ≤ 25 intent-based tools
