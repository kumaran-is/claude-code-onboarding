# Node/TypeScript MCP Server — Pagination, Response Size, Progress, Cancellation, Notifications

SDK v2 (`@modelcontextprotocol/server@2.4.0`). Every `typescript` block type-checks under `strict`; the behaviours marked *verified* were run against a real `Client` over stdio and Streamable HTTP in both protocol eras (2026-07-28 "modern", 2025-11-25 "legacy").

---

## Two kinds of pagination

| | Protocol pagination | Tool-level pagination |
|---|---|---|
| Applies to | `tools/list`, `prompts/list`, `resources/list`, `resources/templates/list` | your tool's own result set (`orders_list`) |
| Fields | request `params.cursor`, result `nextCursor` | a `cursor` argument and a `next_cursor` (or `nextCursor`) output field you define |
| Client behaviour (SDK v2) | `client.listTools()` with no cursor **walks every page** and returns one aggregate (cap `listMaxPages`, default 64, then `SdkError` `LIST_PAGINATION_EXCEEDED`); `listTools({ cursor })` returns one raw page | the model passes the cursor back on the next call |
| Rules (spec) | cursor is **opaque**; page size is the server's choice; missing `nextCursor` = end; invalid cursor → `-32602` | same discipline: opaque, stable, bounded page size, clear error on a bad cursor |

### Tool-level cursor pagination (verified: 23 items walked in 10-item pages with no gaps or duplicates)

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const encodeCursor = (offset: number): string => Buffer.from(String(offset)).toString('base64url');
const decodeCursor = (cursor: string): number | undefined => {
  const offset = Number.parseInt(Buffer.from(cursor, 'base64url').toString('utf8'), 10);
  return Number.isInteger(offset) && offset >= 0 ? offset : undefined;
};

declare function queryOrders(offset: number, limit: number, signal: AbortSignal): Promise<{ items: { id: string }[]; total: number }>;

export function registerOrdersList(server: McpServer): void {
  server.registerTool(
    'orders_list',
    {
      description:
        'List orders newest first, one page at a time. Returns next_cursor when more pages exist; pass it back unchanged as cursor to continue.',
      inputSchema: z.object({
        limit: z.number().int().min(1).max(50).default(20),
        cursor: z.string().max(128).optional().describe('Opaque next_cursor from the previous page'),
      }),
      outputSchema: z.object({
        items: z.array(z.object({ id: z.string() })),
        total: z.number().int(),
        next_cursor: z.string().optional(),
      }),
      annotations: { readOnlyHint: true },
    },
    async ({ limit, cursor }, ctx) => {
      const offset = cursor === undefined ? 0 : decodeCursor(cursor);
      if (offset === undefined) {
        return { isError: true, content: [{ type: 'text', text: 'Invalid cursor. Call orders_list without cursor to restart.' }] };
      }
      const page = await queryOrders(offset, limit, ctx.mcpReq.signal);
      const next = offset + page.items.length < page.total ? encodeCursor(offset + page.items.length) : undefined;
      const output = { items: page.items, total: page.total, ...(next === undefined ? {} : { next_cursor: next }) };
      return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
    },
  );
}
```

A base64 offset is fine for a stable, append-only list. For data that changes between calls, encode a keyset position (last seen sort key + id) and sign it (HMAC) so a model cannot forge a cursor into another tenant's range.

### Protocol pagination of list results (verified, both eras)

`McpServer` lists everything in one page. To paginate `resources/list` (large catalogs) drop to the low-level `Server` it wraps:

```typescript
import { McpServer, ProtocolError, ProtocolErrorCode } from '@modelcontextprotocol/server';

declare const catalog: { uri: string; name: string }[];
const PAGE_SIZE = 100;

export function createCatalogServer(): McpServer {
  const mcp = new McpServer({ name: 'catalog-mcp-server', version: '1.0.0' }, { capabilities: { resources: {} } });
  mcp.server.setRequestHandler('resources/list', async (request) => {
    const cursor = request.params?.cursor;
    const start = cursor === undefined ? 0 : Number.parseInt(Buffer.from(cursor, 'base64url').toString('utf8'), 10);
    if (!Number.isInteger(start) || start < 0 || start > catalog.length) {
      throw new ProtocolError(ProtocolErrorCode.InvalidParams, 'Invalid cursor');
    }
    const end = start + PAGE_SIZE;
    return {
      resources: catalog.slice(start, end),
      ...(end < catalog.length ? { nextCursor: Buffer.from(String(end)).toString('base64url') } : {}),
    };
  });
  return mcp;
}
```

Observed: `client.listResources()` returned all 7 of 7 items across 3 pages with no `nextCursor`; `listResources({ cursor })` returned one 3-item page; a garbage cursor rejected with `ProtocolError` code `-32602`.

### Caching hints on list results (2026-07-28)

`tools/list`, `prompts/list`, `resources/list`, `resources/read`, `resources/templates/list` and `server/discover` results carry `ttlMs` and `cacheScope` (`public` | `private`, SEP-2549). With no input from you the SDK emitted `ttlMs: 0, cacheScope: "private"` on both `tools/list` and a hand-written `resources/list` (observed on the wire), i.e. "do not cache, do not share". Raise `ttlMs` only for lists that really are static, and never mark per-user lists `public`.

---

## Response size

- Default to concise output; offer `response_format: 'markdown' | 'json'` when both people and programs consume the tool.
- Bound every page (`limit` max) **and** the serialized size. Truncate by items, never mid-JSON, and say so:

```typescript
export const CHARACTER_LIMIT = 25_000;

export function fitToLimit<T>(items: T[], render: (subset: T[]) => string): { text: string; shown: number; truncated: boolean } {
  let shown = items.length;
  let text = render(items);
  while (text.length > CHARACTER_LIMIT && shown > 1) {
    shown = Math.max(1, Math.floor(shown / 2));
    text = render(items.slice(0, shown));
  }
  const truncated = shown < items.length;
  return {
    text: truncated ? `${text}\n\n[Truncated: showing ${shown} of ${items.length}. Narrow the query or page with cursor.]` : text,
    shown,
    truncated,
  };
}
```

Context-budget guidance: [mcp-design-context-efficiency.md](mcp-design-context-efficiency.md).

---

## Progress and cancellation

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { pino } from 'pino';

const logger = pino({}, pino.destination(2));
declare function exportBatch(index: number, signal: AbortSignal): Promise<void>;

export function registerExport(server: McpServer): void {
  server.registerTool(
    'orders_export',
    {
      description: 'Export orders in batches and report progress. Stops when the caller cancels.',
      inputSchema: z.object({ batches: z.number().int().min(1).max(100) }),
      annotations: { readOnlyHint: true },
    },
    async ({ batches }, ctx) => {
      const { signal } = ctx.mcpReq;
      const progressToken = ctx.mcpReq._meta?.progressToken;
      let done = 0;
      for (let i = 0; i < batches; i++) {
        await exportBatch(i, signal); // forward the signal into I/O
        if (signal.aborted) {
          // re-check after every await: on HTTP the stream may have closed while we waited
          logger.info({ done, batches, reason: String(signal.reason) }, 'orders_export cancelled');
          break;
        }
        done++;
        if (progressToken !== undefined) {
          await ctx.mcpReq.notify({
            method: 'notifications/progress',
            params: { progressToken, progress: done, total: batches, message: `batch ${done}/${batches}` },
          });
        }
      }
      return { content: [{ type: 'text', text: `Exported ${done} of ${batches} batches` }] };
    },
  );
}
```

**Progress** (verified): the client asks by passing `onprogress` to `callTool`, which puts a `progressToken` in `_meta`; send `notifications/progress` only when a token is present; `progress` must increase. Progress flows on the **response stream of that request** (Streamable HTTP upgrades the reply to SSE when a handler notifies before returning). Treat progress as advisory: in 1 of 5 full sandbox runs the final update arrived after the result on a stdio/legacy connection, so never make correctness depend on the last progress event.

**Cancellation — what actually reaches your handler** (verified with server-side logs):

| Transport / era | Client action | Server effect |
|---|---|---|
| stdio, modern or legacy | `AbortController.abort()` on `callTool({…}, { signal })` | client sends `notifications/cancelled`; `ctx.mcpReq.signal` aborts; handler stopped early (well under 40 of 40 batches) |
| Streamable HTTP, modern (2026-07-28) | same | client closes the request's SSE stream — that **is** the cancellation; signal aborts with reason `Connection closed`; handler stopped at 2 of 40 batches |
| Streamable HTTP, legacy client on a stateless `createMcpHandler` | same | **handler ran to completion (40/40)** — the `notifications/cancelled` POST cannot reach the per-request instance |

Consequences:

1. Check `signal.aborted` **after every `await`**, before sending more notifications: after an HTTP stream closes, a further `notify` throws.
2. Pass `signal` to `fetch`, DB drivers, and child work so the upstream call is cancelled too.
3. If long-running tools must be cancellable for 2025-era HTTP clients, either serve them with a sessionful `NodeStreamableHTTPServerTransport` (legacy only) or `legacy: 'reject'` and require 2026-07-28 clients. A cancelled request gets no response; whatever the handler returns afterwards is discarded.

For work that outlives one request, use the official **Tasks extension** (`io.modelcontextprotocol/tasks`, moved out of core in 2026-07-28: poll with `tasks/get`) rather than holding a stream open.

---

## Change notifications

| Era | How a change reaches the client |
|---|---|
| 2026-07-28 | Only on a `subscriptions/listen` stream the client opened and opted into (`toolsListChanged`, `promptsListChanged`, `resourcesListChanged`, `resourceSubscriptions`). Behind `createMcpHandler`, publish with `handler.notify.toolsChanged()` / `promptsChanged()` / `resourcesChanged()` / `resourceUpdated(uri)`. |
| 2025-era | unsolicited `notifications/*/list_changed` and `notifications/resources/updated` (after `resources/subscribe`) on the session. |

`McpServer` advertises `listChanged` automatically and sends it when you `update()`, `enable()`, `disable()` or `remove()` a registration handle; on stdio, `serveStdio` routes those onto the open listen stream. Verified: `handler.notify.toolsChanged()` delivered exactly one `notifications/tools/list_changed` to a modern client listening with `{ toolsListChanged: true }`. The default event bus is in-process — with several replicas, pass the same custom `ServerEventBus` (Redis/NATS pub/sub) to every `createMcpHandler(factory, { bus })`.

---

## Logging to the client (deprecated)

MCP protocol logging (`notifications/message`, `logging/setLevel`) is **Deprecated as of 2026-07-28** (SEP-2577; earliest removal: first revision on or after 2027-07-28). In 2026-07-28 the level travels per request in `_meta` (`io.modelcontextprotocol/logLevel`), and a server must not emit log notifications for requests without it. New servers: log to stderr (stdio) and use OpenTelemetry for distributed traces ([observability-tracing.md](observability-tracing.md)). The SDK's `logger` option on `McpServer`/`createMcpHandler` routes the SDK's own diagnostics and sends nothing over the wire.
