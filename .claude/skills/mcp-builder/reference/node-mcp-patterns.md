# Node/TypeScript MCP Server — Tool Implementation Patterns

Tools on SDK v2 (`@modelcontextprotocol/server@2.4.0`, `zod@4.6.7`). Every block below type-checks under `strict` + `noUncheckedIndexedAccess`; the runtime behaviours stated were observed with a real `Client` (stdio and Streamable HTTP, both protocol eras). Setup: [node-mcp-setup.md](node-mcp-setup.md).

---

## Naming

- `snake_case`, service-prefixed, verb-led: `orders_list`, `orders_cancel`, `slack_send_message`.
- 1–128 characters from `A-Z a-z 0-9 _ - .`; unique within the server; case-sensitive (spec 2026-07-28 *Tools → Tool names*).
- Name by user intent, not by endpoint (see [mcp-design-principles.md](mcp-design-principles.md)).

## What `registerTool` gives you

From the one Zod `inputSchema` the SDK (a) derives the JSON Schema advertised in `tools/list`, (b) validates every call **before** your handler runs, and (c) types the handler's arguments. `.describe()` text becomes the property `description` — the only per-argument documentation the model sees.

| Situation | What the client receives | Who sees it |
|---|---|---|
| Arguments fail `inputSchema` | result `isError: true`, text `Input validation error: …` — handler never runs | model (can self-correct) |
| Handler returns `isError: true` | that result | model |
| Handler **throws** (any error, even `ProtocolError`) | result `isError: true` with the error's `message` | model |
| `structuredContent` fails `outputSchema` | result `isError: true` (runtime check before it leaves the server) | model |
| Unknown tool name | JSON-RPC error (`ProtocolError`) | host code, not the model |

Verified in the sandbox: `limit: 999` against `.max(10)` → `isError: true` on stdio and HTTP; a planted `structuredContent` that violated `outputSchema` turned every call into `isError: true`.

> **Compile-time output check is not a gate.** The SDK docs say a handler whose `structuredContent` does not match `outputSchema` is a compile error. With 2.4.0 + TypeScript 5.9.3 a planted mismatch (`structuredContent: { total: 'NaN' }` against `z.object({ total: z.number() })`) compiled cleanly (exit 0): the result type is an open record. Rely on the runtime validation and on tests that assert `structuredContent`.

---

## A complete read tool

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const Order = z.object({
  id: z.string(),
  status: z.enum(['pending', 'shipped', 'delivered']),
  total_cents: z.number().int().nonnegative(),
});
type Order = z.infer<typeof Order>;

/** Upstream lookup; returns undefined when the order does not exist. */
declare function findOrder(id: string, signal: AbortSignal): Promise<Order | undefined>;

export function registerOrderTools(server: McpServer): void {
  server.registerTool(
    'orders_get',
    {
      title: 'Get one order',
      description:
        'Fetch one order by id, including status and total in cents. Use after orders_list when you need the details of a single order. Read-only.',
      inputSchema: z.object({
        order_id: z.string().regex(/^ord_[0-9]{3,}$/).describe('Order id as returned by orders_list, e.g. ord_001'),
      }),
      outputSchema: Order,
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    },
    async ({ order_id }, ctx) => {
      const order = await findOrder(order_id, ctx.mcpReq.signal);
      if (order === undefined) {
        return {
          isError: true,
          content: [{ type: 'text', text: `No order ${order_id}. Call orders_list to find valid ids.` }],
        };
      }
      return { content: [{ type: 'text', text: JSON.stringify(order) }], structuredContent: order };
    },
  );
}
```

Rules this example follows:

- **`outputSchema` + `structuredContent` + `content` together.** Always return `content` too (the JSON as text): clients that ignore `structuredContent` still get the data, and in 2.4.0 the handler's return type requires `content` (omitting it is a compile error, verified). Since 2026-07-28 `outputSchema` may be any JSON Schema 2020-12 and `structuredContent` any JSON value (SEP-2106).
- **Recovery hint in the error text.** The model only reads `content`; name the fix ("call orders_list").
- **Pass `ctx.mcpReq.signal` to every I/O call** so a cancelled request stops upstream work ([node-mcp-patterns-advanced.md](node-mcp-patterns-advanced.md#progress-and-cancellation)).
- **No `as any`, no `: any`.** Upstream JSON is `unknown` until a Zod `parse` narrows it.

## Annotations are hints, not security

`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` tell a **host** how to present the tool (auto-approve read-only, confirm destructive). The SDK never changes execution because of them, and the spec says clients **MUST** treat annotations as untrusted unless the server is trusted. Never rely on an annotation to block an action — enforce authorization and confirmation server-side ([security-core.md](security-core.md)).

| Hint | Default when omitted | Set it when |
|---|---|---|
| `readOnlyHint` | `false` | the tool changes nothing |
| `destructiveHint` | `true` (only meaningful when not read-only) | the change deletes or overwrites |
| `idempotentHint` | `false` (only meaningful when not read-only) | repeating the call with the same args has no extra effect |
| `openWorldHint` | `true` | the tool talks to systems outside your control (web, third-party APIs) |

## Write tools: idempotency and explicit handles

MCP has no protocol session (2026-07-28 removed `Mcp-Session-Id`). Cross-call state uses a **server-minted handle** returned by a creation tool and passed back as an ordinary argument (spec *Tools → Stateful tools*, non-normative). Authorize the caller against the handle on every call; make handles opaque, high-entropy and time-bounded; state the lifetime in the creation tool's description; and return a tool error for an expired handle.

```typescript
import { randomUUID } from 'node:crypto';
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const baskets = new Map<string, { owner: string; skus: string[]; expiresAt: number }>();
const TTL_MS = 24 * 60 * 60 * 1000;

export function registerBasketTools(server: McpServer, callerId: () => string): void {
  server.registerTool(
    'shop_create_basket',
    {
      description: 'Create an empty basket and return its basket_id. Baskets expire after 24 hours of inactivity.',
      outputSchema: z.object({ basket_id: z.string() }),
      annotations: { readOnlyHint: false, destructiveHint: false },
    },
    async () => {
      const basket_id = `bsk_${randomUUID()}`;
      baskets.set(basket_id, { owner: callerId(), skus: [], expiresAt: Date.now() + TTL_MS });
      return { content: [{ type: 'text', text: basket_id }], structuredContent: { basket_id } };
    },
  );

  server.registerTool(
    'shop_add_item',
    {
      description: 'Add one SKU to a basket created by shop_create_basket. Adding the same SKU twice keeps one line.',
      inputSchema: z.object({ basket_id: z.string(), sku: z.string().min(1).max(64) }),
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
    },
    async ({ basket_id, sku }) => {
      const basket = baskets.get(basket_id);
      if (basket === undefined || basket.expiresAt < Date.now() || basket.owner !== callerId()) {
        return { isError: true, content: [{ type: 'text', text: 'Unknown or expired basket. Call shop_create_basket.' }] };
      }
      if (!basket.skus.includes(sku)) basket.skus.push(sku);
      basket.expiresAt = Date.now() + TTL_MS;
      return { content: [{ type: 'text', text: `Basket has ${basket.skus.length} item(s).` }] };
    },
  );
}
```

The in-memory `Map` is single-process; on more than one replica keep handles in shared storage.

---

## Zod v4 schema patterns

```typescript
import * as z from 'zod/v4';

export const ResponseFormat = z.enum(['markdown', 'json']);

export const ListInput = z.object({
  query: z.string().trim().min(2).max(200).describe('Text to match against names and emails'),
  limit: z.number().int().min(1).max(50).default(20).describe('Page size, 1-50'),
  cursor: z.string().max(512).optional().describe('Opaque next_cursor from the previous page; omit for page 1'),
  response_format: ResponseFormat.default('markdown').describe("'markdown' for people, 'json' for programs"),
});
export type ListInput = z.infer<typeof ListInput>;

export const CreateUser = z.strictObject({
  name: z.string().min(1).max(100),
  email: z.email(),
  age: z.number().int().min(0).max(150),
});
```

- Bound every string, number and array (`max`), so a model cannot push a 10 MB argument. `McpServer` also accepts `{ maxToolInputElements: n }` (off by default) to cap total array elements + object members per call; the HTTP transport caps the body at 4 MiB by default.
- `z.strictObject` rejects unknown keys (Zod v4 form of `.strict()`); `z.email()` is the v4 top-level format.
- Use `z.enum([...])`, not TypeScript `enum` + `z.nativeEnum` (v3 idiom).
- A field with `.default()` must still be **returned** if it appears in `outputSchema` — the SDK validates the value you return, not a parsed copy.

---

## Typed upstream client (fetch + AbortSignal)

No axios needed on Node 24. Cancellation and a deadline compose with `AbortSignal.any`.

```typescript
import * as z from 'zod/v4';

export class UpstreamError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'UpstreamError';
  }
}

export async function getJson<T>(url: URL, schema: z.ZodType<T>, signal: AbortSignal, timeoutMs = 10_000): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
  });
  if (!res.ok) {
    throw new UpstreamError(`upstream ${url.pathname} returned ${res.status}`, res.status, res.status === 429 || res.status >= 500);
  }
  const body: unknown = await res.json();
  return schema.parse(body);
}

/** Map an upstream failure to model-readable text that names the next step. */
export function toToolErrorText(err: unknown): string {
  if (err instanceof UpstreamError) {
    if (err.status === 404) return 'Not found. Check the id with the matching *_list tool.';
    if (err.status === 403) return 'Permission denied for this account. Do not retry; tell the user.';
    if (err.retryable) return `Upstream temporarily unavailable (HTTP ${err.status}). Retry once after a short wait.`;
    return `Upstream rejected the request (HTTP ${err.status}). Check the arguments.`;
  }
  if (err instanceof Error && err.name === 'TimeoutError') return 'Upstream timed out. Retry once with a narrower query.';
  if (err instanceof z.ZodError) return 'Upstream returned an unexpected shape. Do not retry; report it.';
  return 'Unexpected failure. Do not retry; report it.';
}
```

Use it inside a handler as `try { … } catch (err) { logger.error({ err, tool }, 'orders_get failed'); return { isError: true, content: [{ type: 'text', text: toToolErrorText(err) }] }; }` — log the full error server-side, give the model the actionable sentence, never the stack. House error codes and recovery fields: [error-taxonomy.md](error-taxonomy.md).

---

## Composability

- One `register<Domain>Tools(server, deps)` per domain; `createServer()` calls them all. Dependencies (API clients, pools, logger) come in as arguments, created once at module scope.
- Shared helpers (pagination cursor codec, error mapping, response formatting) live in one module — never copied into each tool.
- Return tools from `tools/list` in a deterministic order (registration order is preserved); the 2026-07-28 spec asks for it to help client caching.
