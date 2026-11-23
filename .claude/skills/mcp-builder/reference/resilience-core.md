# Resilience Core: Timeouts, Circuit Breaker, Bulkhead, Retry Gate

One policy set per upstream dependency that an MCP tool calls: a per-attempt timeout, retries only for idempotent calls, a circuit breaker shared by every caller, and a bulkhead that bounds concurrency. Built on `cockatiel@4.0.0` (2026-05-26; typings read, behaviour executed). `opossum@10.0.0` is the alternative (§6).

Verified 2026-11-23 on Node 24.13.1, TypeScript 5.9.3 strict: 10 tests, and 4 planted defects (retry on a non-idempotent call, breaker threshold off by one, retry wrapped outside the breaker, 4xx opening the breaker) each made a test fail.

## 1. Classify errors by type, not by message

The previous version of this page decided "retryable" with a regex over the error message. `'500'` matched `HTTP 404: order 1500 not found`, and the 5xx pattern matched `HTTP 400: price 5029` (both *executed* against the old code). Throw a typed error from the client and classify on its fields:

| Outcome | Breaker counts it? | Retry it? (idempotent calls only) |
|---------|--------------------|-----------------------------------|
| 5xx | yes | 502, 503, 504 only |
| 429 | yes | yes, honouring `Retry-After` if you implement it |
| other 4xx (400, 401, 403, 404, 409, 422) | **no**: the upstream is alive and rejected *this* request | no |
| timeout (our per-attempt timeout) | yes | yes |
| `ECONNRESET`, `ETIMEDOUT`, `ECONNREFUSED`, `EAI_AGAIN` | yes | yes |
| `BrokenCircuitError`, `BulkheadRejectedError` (our own fail-fast) | no | no |

A 4xx that opens a breaker shared by all callers turns one client's bad input into an outage for everyone (SOURCE-PROVEN rule from a production MCP server; *executed*: 10 × 422 left the breaker closed; the mutant counting 4xx opened it).

## 2. The policy

```typescript
import {
  BrokenCircuitError,
  BulkheadRejectedError,
  ConsecutiveBreaker,
  ExponentialBackoff,
  TaskCancelledError,
  TimeoutStrategy,
  bulkhead,
  circuitBreaker,
  handleWhen,
  retry,
  timeout,
  wrap,
  type CircuitBreakerPolicy,
} from "cockatiel";

/** Thrown by upstream clients so policies can classify by status, not by message regex. */
export class UpstreamHttpError extends Error {
  override readonly name = "UpstreamHttpError";
  constructor(readonly status: number) {
    super(`upstream responded ${status}`);
  }
}

/**
 * Did the DEPENDENCY fail? A 4xx (except 429) means the upstream is alive and rejected the
 * caller's request: it must not open a breaker shared by every caller.
 */
export function isDependencyFailure(err: unknown): boolean {
  if (err instanceof UpstreamHttpError) return err.status >= 500 || err.status === 429;
  // Our own fail-fast rejections are not new evidence about the upstream.
  if (err instanceof BrokenCircuitError || err instanceof BulkheadRejectedError) return false;
  return true; // network error, timeout, unknown: count it
}

/** Transient AND worth another attempt: 429, 502, 503, 504, our own timeout, connection resets. */
export function isTransient(err: unknown): boolean {
  if (err instanceof UpstreamHttpError) return [429, 502, 503, 504].includes(err.status);
  if (err instanceof TaskCancelledError) return true;
  const code = (err as { code?: unknown } | null)?.code;
  return typeof code === "string" && ["ECONNRESET", "ETIMEDOUT", "ECONNREFUSED", "EAI_AGAIN"].includes(code);
}

export interface UpstreamPolicyOptions {
  timeoutMs: number;          // per attempt
  maxRetries: number;         // retries AFTER the first attempt; idempotent calls only
  breakAfter: number;         // consecutive dependency failures that open the breaker
  halfOpenAfterMs: number;    // open -> half-open probe delay
  maxConcurrent: number;      // bulkhead slots
  maxQueued: number;          // bulkhead queue
}

export interface Operation {
  /** GET/HEAD/PUT/DELETE, or a POST carrying an idempotency key the upstream honours. */
  idempotent: boolean;
}

/**
 * One policy set per upstream, shared by every caller (a breaker per call never opens).
 * Order, outermost first: bulkhead -> breaker -> retry -> per-attempt timeout.
 * The breaker sees one result per logical call, so N retries do not count as N failures.
 */
export function createUpstreamPolicy(opts: UpstreamPolicyOptions) {
  const breaker: CircuitBreakerPolicy = circuitBreaker(handleWhen(isDependencyFailure), {
    halfOpenAfter: opts.halfOpenAfterMs,
    breaker: new ConsecutiveBreaker(opts.breakAfter),
  });
  const limiter = bulkhead(opts.maxConcurrent, opts.maxQueued);
  const attemptTimeout = timeout(opts.timeoutMs, TimeoutStrategy.Aggressive);
  // ExponentialBackoff defaults to decorrelated jitter (cockatiel 4 typings).
  const retrying = retry(handleWhen(isTransient), {
    maxAttempts: opts.maxRetries,
    backoff: new ExponentialBackoff({ initialDelay: 50, maxDelay: 2_000 }),
  });
  const withRetry = wrap(limiter, breaker, retrying, attemptTimeout);
  const noRetry = wrap(limiter, breaker, attemptTimeout);

  return {
    breaker,
    limiter,
    retrying,
    /** `fn` receives the per-attempt AbortSignal: pass it to fetch() so a timeout cancels the I/O. */
    execute<T>(op: Operation, fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
      const policy = op.idempotent ? withRetry : noRetry;
      return policy.execute(({ signal }) => fn(signal));
    },
  };
}
```

Use it in an upstream client (the tool passes its own cancellation signal, `ctx.mcpReq.signal`):

```typescript
import * as z from "zod/v4";
import { UpstreamHttpError, createUpstreamPolicy } from "../resilience.js";

const baseUrl = process.env["ORDERS_API_URL"] ?? "http://127.0.0.1:8080";
const Order = z.object({ id: z.string(), status: z.enum(["pending", "shipped", "delivered"]) });
type Order = z.infer<typeof Order>;
const Refund = z.object({ id: z.string(), amount_cents: z.number().int() });
type Refund = z.infer<typeof Refund>;
interface RefundRequest { order_id: string; amount_cents: number }

// Once per upstream, at module load.
const ordersPolicy = createUpstreamPolicy({
  timeoutMs: 2_000, maxRetries: 2, breakAfter: 5, halfOpenAfterMs: 10_000, maxConcurrent: 20, maxQueued: 50,
});

export function getOrder(id: string, cancel: AbortSignal): Promise<Order> {
  return ordersPolicy.execute({ idempotent: true }, async (attempt) => {
    const res = await fetch(`${baseUrl}/orders/${encodeURIComponent(id)}`, { signal: AbortSignal.any([cancel, attempt]) });
    if (!res.ok) throw new UpstreamHttpError(res.status);
    return Order.parse(await res.json());
  });
}

export function createRefund(body: RefundRequest, cancel: AbortSignal): Promise<Refund> {
  // POST without an idempotency key: one attempt, never retried.
  return ordersPolicy.execute({ idempotent: false }, async (attempt) => {
    const res = await fetch(`${baseUrl}/refunds`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.any([cancel, attempt]),
    });
    if (!res.ok) throw new UpstreamHttpError(res.status);
    return Refund.parse(await res.json());
  });
}
```

Executed behaviour (each with its control):

| Behaviour | Result | Control |
|-----------|--------|---------|
| Breaker opens after `breakAfter` consecutive dependency failures | 3 × 500 → `Open`; 4th call rejected with `BrokenCircuitError`, upstream call count stayed 3 | 2 × 503 → still `Closed` |
| Half-open after `halfOpenAfter` | state sequence `Open → HalfOpen → Open` (failed probe) `→ HalfOpen → Closed` (successful probe) | |
| One failure per logical call | 2 calls × 3 attempts = 6 upstream calls, breaker still `Closed` (2 < 3) | mutant with retry outside the breaker: test failed |
| Retry only when idempotent | `idempotent: true` + two 503s → 3 calls, success | `idempotent: false` + 503 → exactly 1 call, error surfaced |
| No retry for a non-transient error | 404 on an idempotent call → 1 call | |
| Timeout cancels the I/O | the attempt's `AbortSignal` fired, `TaskCancelledError` thrown | |
| Bulkhead bounds concurrency | 3rd concurrent call with `maxConcurrent: 2, maxQueued: 0` → `BulkheadRejectedError`; breaker stayed `Closed` | first two completed |

- `wrap(a, b, c)` runs `a` outermost (*executed*). The order above (bulkhead → breaker → retry → timeout) means a rejected or broken call does not occupy a retry loop, and the breaker sees the final outcome of all attempts.
- Create the policy **once per upstream** at module load. A policy created per request never accumulates failures and never opens.
- In half-open, cockatiel sends **one** probe; concurrent callers wait for its outcome (*executed*: 3 concurrent calls started at 0/52/52 ms when the probe succeeded; with a failing probe only 1 reached the upstream and the other 2 got `BrokenCircuitError`). The previous hand-written breaker on this page let every concurrent call through in half-open.
- Map `BrokenCircuitError`/`BulkheadRejectedError`/`TaskCancelledError` to a tool error the agent can act on ("orders service unavailable, retry later"), not to a generic 500 and not to an empty result.

## 3. Timeout budgets

Timeouts nest. Each inner timeout must be shorter than the one outside it, or the outer one fires first and the inner work keeps running.

```
client/agent tool-call timeout          e.g. 60 s (MCP client RequestOptions.timeout)
└─ server requestTimeout                30 s (node:http; default 300 s)
   └─ tool budget                       ≤ 25 s
      └─ attempts × per-attempt timeout + backoff   3 × 2 s + ≤ 2 × 2 s backoff ≤ 10 s
         └─ upstream client timeouts    connect 2 s, headers/body ≤ per-attempt (undici defaults: connect 10 s, headers 300 s, body 300 s)
```

- Pass the tool's `ctx.mcpReq.signal` (client cancellation) and the per-attempt signal into the I/O with `AbortSignal.any` (§2). A timeout that does not abort the socket just stops waiting for it.
- Undici/`fetch` defaults (`headersTimeout`/`bodyTimeout` 300 s; undici 8.13.1 docs) are far above any tool budget: always set the per-attempt timeout.
- Graceful shutdown's drain budget must be longer than the longest tool budget you want to finish, and shorter than the platform's termination grace period ([production-runtime-shutdown-health.md](production-runtime-shutdown-health.md)).

## 4. Bulkheads

- One bulkhead per upstream, sized from the upstream's capacity and your replica count (`maxConcurrent ≈ upstream concurrency limit / replicas`).
- Keep the queue small and bounded. An unbounded queue converts overload into latency and memory growth; a rejection is cheaper and visible (`app.upstream.bulkhead.queued`, observability-metrics.md §3).
- A slow upstream fills its bulkhead and fails fast there, instead of exhausting the event loop's sockets and memory for every other tool.

## 5. Retries: the rules

1. Retry only idempotent operations: GET/HEAD/PUT/DELETE by HTTP semantics, or a POST that carries an idempotency key the upstream documents it honours. The old client on this page retried POST: one refund request became 3 charges in the *executed* reproduction.
2. Retry only transient outcomes (§1), with exponential backoff **and jitter** (`ExponentialBackoff` defaults to decorrelated jitter), a small attempt cap (2 retries), and a per-attempt timeout.
3. Retry at one layer only. If the agent framework, the MCP client and the server all retry 3 times, one failure becomes 27 upstream calls.
4. Do not retry while the breaker is open; the order in §2 guarantees it.

## 6. opossum instead of cockatiel

`opossum@10.0.0` (2026-06-24; types from `@types/opossum@8.1.9`, which lag the major version) wraps one async function per breaker and uses a rolling error-percentage window (`errorThresholdPercentage`, `rollingCountTimeout`, `volumeThreshold`) with a built-in `timeout`. Use its `errorFilter` to keep 4xx out of the failure count. It has no bulkhead or retry: combine it with your own concurrency limit and the retry rules above. Not executed in this validation; cockatiel was chosen because it ships timeout, retry, breaker and bulkhead as composable policies with first-party TypeScript types.
