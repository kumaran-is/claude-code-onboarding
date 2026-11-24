# Resilience: Rate Limiting, Retry Rules, Caching, Loop Guard

Small guards that sit next to the policies in [resilience-core.md](resilience-core.md): a token bucket for an upstream's quota, a tenant-keyed read-through TTL cache with request coalescing, an optional Redis cache shared across replicas, and a per-caller loop detector. Verified 2026-11-23 against `lru-cache@11.5.3`, `ioredis@6.1.0`, `zod@4.6.7`, `@opentelemetry/api@1.10.0`, `@modelcontextprotocol/server@2.4.0` on Node 26.13.1 + TypeScript 6.0.3 strict (`nodenext`): `tsc` exit 0, Vitest 15/15. Planted defects (caching a failure, no coalescing, a tenant-blind key, an unbranded string key, unsorted fingerprint keys, a detector not scoped per caller) each made a test or `tsc` fail.

## 1. Code

```typescript
import { createHash } from "node:crypto";
import { metrics } from "@opentelemetry/api";
import { LRUCache } from "lru-cache";

const meter = metrics.getMeter("orders-mcp");
// Totals are Counters (monotonic). A Gauge for a running total loses increments between exports.
const cacheLookups = meter.createCounter("app.cache.lookups", { description: "Cache lookups by result (hit|miss)" });
const loopsBlocked = meter.createCounter("app.mcp.tool_loops_blocked", { description: "Tool calls refused as repeated loops" });

/** Stable JSON: object keys sorted, so {a,b} and {b,a} produce the same fingerprint. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return value === undefined ? "undefined" : JSON.stringify(value);
}

/** SHA-256 of the canonical args: keys never hold raw argument values (PII) in memory or logs. */
export function fingerprint(tool: string, args: unknown): string {
  return createHash("sha256").update(`${tool}\0${canonical(args)}`).digest("hex");
}

/** A cache key can only be built with a tenant, so a tenant-blind key does not type-check. */
export type CacheKey = string & { readonly __brand: "CacheKey" };
export function cacheKey(tenantId: string, resource: string, args: unknown): CacheKey {
  if (tenantId === "") throw new Error("cacheKey: tenantId is required");
  return `${tenantId}\0${resource}\0${fingerprint(resource, args)}` as CacheKey;
}

type Load<V> = (signal: AbortSignal) => Promise<V>;

/** Read-through cache for successful upstream reads. Errors are never cached; concurrent misses share one load. */
export class TtlCache<V extends string | number | boolean | object> {
  readonly #cache: LRUCache<CacheKey, V, Load<V>>;
  constructor(readonly name: string, max: number, ttlMs: number) {
    this.#cache = new LRUCache<CacheKey, V, Load<V>>({
      max,
      ttl: ttlMs,
      // One in-flight load per key: callers that miss while it runs await the same promise.
      fetchMethod: (_key, _stale, { signal, context }) => context(signal),
    });
  }
  async getOrLoad(key: CacheKey, load: Load<V>): Promise<{ value: V; hit: boolean }> {
    const hit = this.#cache.has(key); // false for an expired entry or a load still in flight
    cacheLookups.add(1, { "app.cache.name": this.name, "app.cache.result": hit ? "hit" : "miss" });
    // forceFetch rejects when the load rejects; the failed entry is removed, so the next call retries.
    const value = await this.#cache.forceFetch(key, { context: load });
    return { value, hit };
  }
  /** Call after any write that changes what `key` would return. Aborts an in-flight load for it. */
  invalidate(key: CacheKey): void {
    this.#cache.delete(key);
  }
  get size(): number {
    return this.#cache.size;
  }
}

/**
 * Refuses the same tool + same arguments more than `threshold` times inside `windowMs` for one caller scope
 * (principal id, or session id on a sessionful transport). Bounded: at most `maxKeys` fingerprints are tracked.
 */
export class ToolCallLoopDetector {
  readonly #calls: LRUCache<string, number[]>;
  constructor(private readonly threshold = 3, private readonly windowMs = 60_000, maxKeys = 10_000) {
    this.#calls = new LRUCache<string, number[]>({ max: maxKeys, ttl: windowMs });
  }
  /** Returns true when this call should be refused. */
  isLoop(scope: string, tool: string, args: unknown, now = Date.now()): boolean {
    const key = `${scope}\0${fingerprint(tool, args)}`;
    const recent = (this.#calls.get(key) ?? []).filter((t) => now - t < this.windowMs);
    recent.push(now);
    this.#calls.set(key, recent);
    const loop = recent.length > this.threshold;
    if (loop) loopsBlocked.add(1, { "gen_ai.tool.name": tool });
    return loop;
  }
}

/** Token bucket for an upstream's quota. `tryTake` never waits: callers reject or queue explicitly. */
export class TokenBucket {
  #tokens: number;
  #last: number;
  constructor(private readonly capacity: number, private readonly refillPerSecond: number, now = Date.now()) {
    this.#tokens = capacity;
    this.#last = now;
  }
  tryTake(now = Date.now()): boolean {
    this.#tokens = Math.min(this.capacity, this.#tokens + ((now - this.#last) / 1000) * this.refillPerSecond);
    this.#last = now;
    if (this.#tokens < 1) return false;
    this.#tokens -= 1;
    return true;
  }
}
```

## 2. Rate limiting an upstream (token bucket)

- `capacity` is the burst; `refillPerSecond` is the sustained rate the vendor allows divided by your replica count. *Executed:* `TokenBucket(2, 1)` allowed 2 immediate calls, refused the 3rd, refused again at 999 ms and allowed at 1000 ms.
- `tryTake` never sleeps. When it returns false, return a tool error (`"rate limit reached for orders API, retry in a few seconds"`) or put the call in the bulkhead queue. Sleeping inside a handler holds a slot and a socket while doing nothing.
- An in-process bucket limits one replica. For a vendor quota shared by all replicas, keep the counter in a shared store (Redis `INCR` + expiry, or the vendor's quota headers) and treat 429 as authoritative.
- Inbound rate limiting per client/tenant (protecting **your** server) is a different control: [security-middleware-attacks.md](security-middleware-attacks.md) and [production-runtime-multi-tenant.md](production-runtime-multi-tenant.md).

## 3. Retry

Retry rules, idempotency and backoff with jitter are in resilience-core.md §1, §2 and §5; use that policy and do not write a second retry loop. Summary: idempotent operations only, transient outcomes only, ≤ 2 retries with jittered exponential backoff, one retrying layer, never while the breaker is open.

## 4. Read-through cache

Cache the upstream **response** for stable reads (profiles, catalogue entries, reference data), not the MCP tool result.

```typescript
const customers = new TtlCache<Customer>("customers", 5_000, 60_000);
const { value } = await customers.getOrLoad(
  cacheKey(principal.tenantId, "customer", { id: args.customerId }),
  (signal) => crm.getCustomer(args.customerId, { signal: AbortSignal.any([signal, ctx.mcpReq.signal]) }),
);
```

- **Key design.** `cacheKey(tenant, resource, args)` = tenant + resource + SHA-256 of the canonical args, so the key holds no raw argument values and `{a, b}` equals `{b, a}`. Add every input that changes the response (locale, API version, the caller's role when the upstream filters by it).
- **Tenant isolation.** The branded `CacheKey` type means a plain string such as `"customer:42"` does not compile, and an empty tenant throws. *Executed:* the same resource and args for `tenant-a` and `tenant-b` are separate entries; dropping the tenant from the key made that test fail; passing a plain string made `tsc` exit 2.
- **Stampede.** `lru-cache` 11's `fetchMethod` + `forceFetch` share one in-flight load per key. *Executed:* 50 concurrent misses called the upstream once; 5 concurrent waiters on a failing load all rejected after one call and nothing was cached. Without the shared load the stampede test failed.
- **Failures are not cached.** `forceFetch` rejects when the load rejects and removes the entry, so the next call reaches the upstream again. A cached error turns a 2-second blip into a TTL-long outage.
- **Bounds and invalidation.** Bounded by entries (`max`) and age (`ttl`); choose TTL per resource type (seconds for prices or availability, minutes for profiles). `invalidate` after a write forces a reload and aborts the `signal` of a load still in flight for that key (*executed*).
- **lru-cache 11 notes.** Named export `LRUCache`; the third type parameter is the `fetchMethod` context type; `has()` is false while a fetch is pending, which is why the in-flight case counts as a miss.
- `app.cache.lookups` is a Counter with `result=hit|miss`; the hit ratio is computed in the backend. Totals are counters, never gauges (observability-metrics.md §2).

### Shared cache across replicas (optional: ioredis 6)

Each replica holds its own in-process cache. Add Redis only when replicas must agree, or another service invalidates entries. It is not part of a generic MCP scaffold.

```typescript
import { Redis } from "ioredis";
import type { z } from "zod";

/** ioredis 6 speaks RESP3 by default (Redis >= 6); protocol: 2 keeps the v5 wire format. */
export function createRedis(url: string): Redis {
  return new Redis(url, { lazyConnect: true, maxRetriesPerRequest: 2, enableOfflineQueue: false });
}

/** Values are re-validated on read: the shared cache is outside this process's trust boundary. */
export async function redisGetOrLoad<S extends z.ZodType>(
  redis: Redis, key: CacheKey, schema: S, ttlMs: number, load: () => Promise<z.output<S>>,
): Promise<z.output<S>> {
  const redisKey = `cache:${key}`;
  const raw = await redis.get(redisKey); // rejects fast while Redis is down; the caller decides to fail or bypass
  if (raw !== null) {
    const parsed = schema.safeParse(JSON.parse(raw));
    if (parsed.success) return parsed.data;
    await redis.del(redisKey); // shape changed after a deploy: drop it and reload
  }
  const value = await load();
  await redis.set(redisKey, JSON.stringify(value), "PX", ttlMs);
  return value;
}
```

- **ioredis 6.0.0 breaking changes** (CHANGELOG): Node >= 20; RESP3 is the default protocol (set `protocol: 2` for Redis < 6 or proxies that only speak RESP2); `replyMapping` defaults to `"legacy"`, so reply shapes match v5. *Executed:* `options.protocol` is 3 by default and 2 with the opt-out.
- `enableOfflineQueue: false` fails a command at once while disconnected instead of buffering it. *Executed:* a read against an unreachable Redis rejected in < 500 ms. With `lazyConnect`, call `connect()` at startup so a bad URL fails the readiness probe.
- This helper does not coalesce across replicas. Front it with the in-process `TtlCache` (per-replica coalescing), or use a short `SET NX PX` lock when a cold key must reach the upstream once cluster-wide.
- `tsc` with `skipLibCheck: false` reports 2 errors inside ioredis 6.1.0's own `.d.ts` (it imports the untyped `redis-errors`); keep `skipLibCheck: true` or add a local declaration. Live Redis behaviour was not run (no server in the verification sandbox).

## 5. Tool-call loop guard

An agent that calls the same tool with the same arguments again and again (weak instructions, an ambiguous tool result) burns tokens and upstream quota. The server can refuse the repeat and tell the agent what to do instead.

```typescript
const loops = new ToolCallLoopDetector(3, 60_000);

mcp.registerTool("search_orders", { description: "Search orders", inputSchema: z.object({ q: z.string().max(200) }) }, (args, ctx) => {
  // principalFrom(): fail-closed principal from the verified token (production-runtime-multi-tenant.md)
  const principal = principalFrom(ctx.http?.authInfo);
  if (loops.isLoop(`${principal.tenantId}:${principal.subject}`, "search_orders", args)) {
    return {
      isError: true,
      content: [{ type: "text", text: "Same search repeated 4 times in 60 s with identical arguments. Change the query or ask the user what they need." }],
    };
  }
  return searchOrders(principal, args, ctx.mcpReq.signal);
});
```

- **Scope per caller.** The old version tracked fingerprints in one global map, so two users asking the same question tripped each other's limit. *Executed:* the 4th identical call from `user-a` was refused while the same call from `user-b` was allowed. Use the authenticated principal; with stateless `createMcpHandler` there is no session id.
- **Canonical fingerprint.** `JSON.stringify` depends on key order, so `{q, page}` and `{page, q}` looked different. The detector sorts keys and hashes the result, so raw argument values (which may be PII) are not kept in memory as map keys.
- **Bounded memory.** Fingerprints live in an LRU with `max` keys and a TTL equal to the window. The old map grew without limit.
- Return a tool result with `isError: true` and a next step, not a protocol error: the agent can read it and change course.
