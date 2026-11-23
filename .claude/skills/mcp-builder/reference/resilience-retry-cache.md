# Resilience: Rate Limiting, Retry Rules, Caching, Loop Guard

Small guards that sit next to the policies in [resilience-core.md](resilience-core.md): a token bucket for an upstream's quota, a read-through TTL cache, and a per-caller loop detector. Verified 2026-11-23 with `lru-cache@11.5.3`, `@opentelemetry/api@1.10.0`, Node 24.13.1, TypeScript 5.9.3 strict + ESLint `strictTypeChecked`. 6 tests; 3 planted defects (caching a failure, unsorted fingerprint keys, a detector not scoped per caller) each made a test fail.

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

/** Read-through cache for successful upstream reads. Errors are never cached. */
export class TtlCache<V extends string | number | boolean | object> {
  readonly #cache: LRUCache<string, V>;
  constructor(readonly name: string, max: number, ttlMs: number) {
    this.#cache = new LRUCache<string, V>({ max, ttl: ttlMs });
  }
  async getOrLoad(key: string, load: () => Promise<V>): Promise<{ value: V; hit: boolean }> {
    const cached = this.#cache.get(key);
    cacheLookups.add(1, { "app.cache.name": this.name, "app.cache.result": cached === undefined ? "miss" : "hit" });
    if (cached !== undefined) return { value: cached, hit: true };
    const value = await load(); // a rejection propagates and nothing is stored
    this.#cache.set(key, value);
    return { value, hit: false };
  }
  /** Call after any write that changes what `key` would return. */
  invalidate(key: string): void {
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

- Bounded by entries (`max`) and age (`ttl`); choose TTL per resource type from how stale the data may be: seconds for prices or availability, minutes for profiles.
- *Executed:* a failed load stores nothing (next call reaches the upstream again); a hit skips the loader; `invalidate` after a write forces a reload; an entry older than the TTL is reloaded.
- Key on the inputs that determine the response, including the tenant/principal whenever the response is tenant-specific. A key without the tenant serves one tenant's data to another.
- `app.cache.lookups` is a Counter with `result=hit|miss`; the hit ratio is computed in the backend. The previous version kept hit/miss totals as gauges; totals must be counters (observability-metrics.md §2).
- Concurrent misses for the same key each call the upstream (no request coalescing). If that matters, share the in-flight promise per key, or use `lru-cache`'s `fetchMethod` (not executed here).
- Multiple replicas each hold their own cache; use Redis when consistency across replicas or invalidation from another service matters.

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
