# Resilience in Production: Connection Pools and Composition

How the pieces fit in a running server: one HTTP connection pool per upstream with explicit timeouts, one policy set per upstream ([resilience-core.md](resilience-core.md)), guards from [resilience-retry-cache.md](resilience-retry-cache.md), and a shutdown that closes them in order ([production-runtime-shutdown-health.md](production-runtime-shutdown-health.md)). Verified 2026-11-23 with `undici@8.13.1`, Node 24.13.1, TypeScript 5.9.3 strict.

## 1. Connection pool per upstream (undici)

```typescript
import { Pool } from "undici";
import { UpstreamHttpError } from "../resilience.js";

/**
 * One pool per upstream origin, created at startup and closed during graceful shutdown.
 * Every timeout is explicit: undici's defaults (headers/body 300 s) are far above any tool budget.
 */
export function createUpstreamPool(origin: string): Pool {
  return new Pool(origin, {
    connections: 20, // = the bulkhead's maxConcurrent for this upstream
    pipelining: 1, // no HTTP/1.1 pipelining: a stalled response would block the requests queued behind it
    connectTimeout: 2_000,
    headersTimeout: 2_000,
    bodyTimeout: 5_000,
    keepAliveTimeout: 4_000, // below the upstream server's own keep-alive timeout
  });
}

export async function getJson(pool: Pool, path: string, signal: AbortSignal): Promise<unknown> {
  const res = await pool.request({ method: "GET", path, signal, headers: { accept: "application/json" } });
  if (res.statusCode >= 400) {
    await res.body.dump(); // release the connection back to the pool
    throw new UpstreamHttpError(res.statusCode);
  }
  return res.body.json();
}
```

- *Executed:* 200 → JSON; 404 → `UpstreamHttpError` (body drained so the socket is reused); a response that sent no headers for 3 s failed with `UND_ERR_HEADERS_TIMEOUT` after ~2 s. With `headersTimeout` removed (undici default 300 s), the same call waited the full 3 s and returned: the test failed.
- `pipelining: 1` (the default). The old example on this page exposed a `pipelining` option; HTTP/1.1 pipelining sends several requests on one socket, so a slow response delays every request behind it, and a non-idempotent request may be replayed on a reset.
- `connections` equals the bulkhead size for that upstream, so the pool never queues more than the bulkhead allows.
- `keepAliveTimeout` below the upstream server's idle timeout avoids reusing a socket the server is closing (`ECONNRESET` on the first write). The same rule, reversed, applies to your own server behind a load balancer (production-runtime-shutdown-health.md §3).
- Global `fetch` in Node 24.13.1 uses a bundled undici (7.18.2 there, from `process.versions.undici`), not the `undici` package you install. Timeouts set on an installed `undici` `Pool`/`Agent` do not affect global `fetch` unless you pass that dispatcher explicitly. Pick one client per upstream and set its timeouts there. With global `fetch`, the per-attempt `AbortSignal` (resilience-core.md §2) is your timeout.
- Database pools follow the same rules: one pool per process, bounded size (`replicas × pool size ≤ database max_connections − headroom`), statement/query timeout set, closed during shutdown. Prisma 7 with `@prisma/adapter-pg`: size the pool on the adapter (`new PrismaPg({ connectionString, max: 10 })`, see `nestjs-api` `reference/nestjs-config-prisma7.md`) and call `$disconnect()` in shutdown.

## 2. Composition per upstream

```
tool handler
 ├─ loop guard (per caller)                         resilience-retry-cache.md §5
 ├─ cache.getOrLoad(key) ── hit → return            resilience-retry-cache.md §4
 └─ miss → token bucket.tryTake() ── false → tool error "rate limited"
           └─ policy.execute({ idempotent }, signal)  bulkhead → breaker → retry → timeout
                └─ pool.request({ signal })            explicit connect/headers/body timeouts
```

- Cache before the policy: a hit should not consume a bulkhead slot or a rate-limit token.
- Rate limit before the policy: a refused call is not an upstream failure and must not reach the breaker.
- Create every piece once at startup in a small per-upstream module (`clients/orders.ts`), export plain functions (`getOrder`, `createRefund`), and keep the policy objects out of tool handlers.
- Map fail-fast errors to clear tool results:

| Error | Tool result text (example) | Log level |
|-------|---------------------------|-----------|
| `BrokenCircuitError` | "Orders service is unavailable. Try again in a minute." | warn (once per state change via `breaker.onBreak`) |
| `BulkheadRejectedError` / bucket empty | "Orders service is busy. Try again shortly." | warn |
| `TaskCancelledError` | "Orders service did not respond in time." | warn |
| `UpstreamHttpError` 404 | "No order with that id." | info |
| `UpstreamHttpError` 5xx after retries | "Orders service failed. Try again later." | error |

## 3. Fault injection

Test the composition by making the dependency misbehave, not by mocking the policy:

- **In-process** (what the tests here do): a local `node:http` upstream that answers 5xx, 429, 404, hangs before headers, or drops the connection, plus the server under test calling it. Assert call counts, breaker state transitions and tool results.
- **Network level** (NOT RUN here): Toxiproxy (latency, bandwidth, `reset_peer`, timeout toxics) between the service and a real dependency in docker-compose; or `tc netem` in a test container.
- **Load + faults** (autocannon/k6, node-ci-and-observability.md and §4 below): run a steady load, inject a fault mid-run, and check that p99 of unaffected tools stays inside budget (bulkhead isolation) and that the error rate returns to baseline within `halfOpenAfter` after the fault clears.

## 4. Load and concurrency testing

```javascript
// Load/concurrency smoke against a stateless (SDK v2 createMcpHandler) server: N connections calling tools/call.
// usage: node scripts/load.mjs <baseUrl> [connections] [seconds] [p99BudgetMs]
import autocannon from "autocannon";

const [base, conns = "20", secs = "5", p99Budget = "250"] = process.argv.slice(2);
const result = await autocannon({
  url: `${base}/mcp`, method: "POST", connections: Number(conns), duration: Number(secs),
  headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "echo", arguments: { text: "x" } } }),
  verifyBody: (body) => body.includes('"text":"x"') && !body.includes('"isError":true'),
});
const summary = { requests: result.requests.total, non2xx: result.non2xx, errors: result.errors, timeouts: result.timeouts, mismatches: result.mismatches, p50: result.latency.p50, p99: result.latency.p99, rps: result.requests.average };
process.stdout.write(`${JSON.stringify(summary)}\n`);
const failed = summary.non2xx + summary.errors + summary.timeouts + summary.mismatches > 0 || summary.p99 > Number(p99Budget) || summary.requests === 0;
process.exit(failed ? 1 : 0);
```

- *Executed* against the stateless SDK v2 server (OTel off, 20 connections, 5 s, on a laptop): 46,639 requests, 0 non-2xx, 0 errors, 0 mismatched bodies, p50 1 ms, p99 7 ms, exit 0. The same run with a p99 budget of 0 ms exited 1; a run expecting a different body exited 1 (every response counted as a mismatch). Absolute numbers depend on the machine; compare runs on the same runner only.
- `verifyBody` matters: a server that returns 200 with a JSON-RPC error or `isError: true` passes a status-only check.
- For shaped scenarios (ramping arrival rate, thresholds as pass/fail, multi-step sessions) use k6 (v2.4.0 latest at the time of writing; NOT RUN here: not installed). Keep load tests out of the per-PR CI job; run them on a schedule or before a release against a staging deployment, with the budget as the exit code.
- Measure with OTel on as well: the exporter's CPU cost is part of production latency.
