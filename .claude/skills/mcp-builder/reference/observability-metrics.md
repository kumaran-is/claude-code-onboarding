# MCP Server Metrics

Which metrics a Node MCP server exports, how they are named, and which attributes are allowed on them. Spans and `_meta` propagation are in [observability-tracing.md](observability-tracing.md). SLOs and alerts built on these metrics are in [observability-monitoring.md](observability-monitoring.md).

Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3 strict, `@opentelemetry/api@1.10.0`, `@opentelemetry/sdk-metrics@3.1.1`, `cockatiel@4.0.0`, `lru-cache@11.5.3`, `@prometheus-io/client@0.16.1`. The duration histogram, auth denials, retries and cache hit/miss counters were asserted end to end through a fake OTLP collector; the §3 snippet was compiled, not run, on this toolchain (its slot arithmetic was executed earlier on Node 24.13.1).

## 1. The set

| Question | Metric | Instrument | Attributes (bounded only) |
|----------|--------|-----------|---------------------------|
| Rate, Errors, Duration (RED) per tool | `mcp.server.operation.duration` (semconv, Development) | Histogram, `s`, buckets `[0.01 … 300]` | `mcp.method.name`, `gen_ai.tool.name`, `error.type` on failure |
| Concurrency / in-flight | `app.mcp.active_tool_calls` | UpDownCounter | `gen_ai.tool.name` |
| Saturation of the event loop | `app.nodejs.eventloop.delay.p99` | ObservableGauge, `s` | none |
| Upstream bulkhead occupancy and queue depth | `app.upstream.bulkhead.in_use`, `.queued` | ObservableUpDownCounter | `app.upstream` |
| Breaker state | `app.upstream.breaker.open` | ObservableGauge (0/1) | `app.upstream` |
| Cache effectiveness | `app.cache.lookups` | Counter | `app.cache.name`, `app.cache.result` = `hit`/`miss` |
| Auth denials (no tool ran) | `app.mcp.auth.denials` | Counter | `app.auth.reason` (fixed enum: `invalid_token`, `expired`, `scope`) |
| Upstream retries | `app.upstream.retries` | Counter | `app.upstream` |
| Upstream timeouts | `error.type` = `TaskCancelledError` on the duration histogram (cockatiel timeout) or `TimeoutError` (native `AbortSignal.timeout`) | (histogram) | as above |
| Agent loops refused | `app.mcp.tool_loops_blocked` | Counter | `gen_ai.tool.name` |
| Open sessions (legacy sessionful transports only) | `app.mcp.active_sessions` | UpDownCounter | none |
| Model token usage (if the server calls an LLM) | `gen_ai.client.token.usage` or its successor | Histogram/Counter, `{token}` | see §4 |

- **Rate and error rate come from the histogram**: its count is the request rate; filter on `error.type` for errors. A separate `*_total` counter per tool duplicates it.
- Names under `mcp.*` and `gen_ai.*` belong to the semantic conventions. Put your own metrics under an `app.` prefix so a future semconv release cannot collide with them.
- The semconv duration histogram (code in observability-tracing.md §3) passes `advice: { explicitBucketBoundaries: [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 120, 300] }`. *Executed:* the exported points carried exactly these bounds. The SDK default buckets are milliseconds-shaped (0–10000), which puts every sub-5-second call in the first two buckets of a seconds histogram.

## 2. Cardinality rules

Every distinct attribute set is a separate time series held in memory and billed by your backend.

- Allowed: tool name (fixed, registered at start), method, error class, upstream name, cache name, outcome enums.
- Never on metrics: session id, request id, user/tenant id, trace id, URL with ids, tool arguments, error messages. Put them on spans. *Executed:* adding `mcp.session.id` to the histogram attributes failed the cardinality test.
- Tenant-level usage for billing or quotas belongs in an audit/usage store keyed by tenant ([production-runtime-multi-tenant.md](production-runtime-multi-tenant.md)), not in metric labels. If you must chart a few large tenants, map to a bounded set (`tier`, or top-N + `other`).
- Use a **Counter** for anything that only goes up (hits, misses, refusals). A Gauge set to a running total loses data between exports and cannot be rate()'d correctly (SOURCE-PROVEN defect: cache hit/miss totals registered as gauges).

## 3. Saturation metrics (event loop, bulkhead, breaker)

```typescript
import { monitorEventLoopDelay } from "node:perf_hooks";
import { metrics } from "@opentelemetry/api";
import { CircuitState, type BulkheadPolicy, type CircuitBreakerPolicy } from "cockatiel";

const meter = metrics.getMeter("orders-mcp");

/** Saturation signals the request histogram cannot show: event-loop lag, bulkhead occupancy, breaker state. */
export function registerSaturationMetrics(upstream: string, limiter: BulkheadPolicy, breaker: CircuitBreakerPolicy, maxConcurrent: number, maxQueued: number): void {
  const loopDelay = monitorEventLoopDelay({ resolution: 20 });
  loopDelay.enable();
  meter
    .createObservableGauge("app.nodejs.eventloop.delay.p99", { unit: "s", description: "Event-loop delay p99 since last export" })
    .addCallback((result) => {
      result.observe(loopDelay.percentile(99) / 1e9);
      loopDelay.reset();
    });
  meter
    .createObservableUpDownCounter("app.upstream.bulkhead.in_use", { description: "Occupied execution slots" })
    .addCallback((result) => { result.observe(maxConcurrent - limiter.executionSlots, { "app.upstream": upstream }); });
  meter
    .createObservableUpDownCounter("app.upstream.bulkhead.queued", { description: "Calls waiting for a slot (queue depth)" })
    .addCallback((result) => { result.observe(maxQueued - limiter.queueSlots, { "app.upstream": upstream }); });
  meter
    .createObservableGauge("app.upstream.breaker.open", { description: "1 when the breaker is not closed" })
    .addCallback((result) => { result.observe(breaker.state === CircuitState.Closed ? 0 : 1, { "app.upstream": upstream }); });
}
```

- `executionSlots` / `queueSlots` return the **free** slots (cockatiel 4 typings; *executed:* `bulkhead(2, 1)` reported `[2, 1]` idle and `[0, 0]` with three calls running/queued), so occupancy is `max - free`.
- Event-loop delay above ~100 ms p99 means CPU-bound or synchronous work on the request path (JSON of large payloads, sync crypto, sync fs, regex backtracking). It inflates every request's latency regardless of upstream health. `@opentelemetry/instrumentation-runtime-node` (0.38.0, not executed here) emits standard `nodejs.eventloop.*` metrics if you prefer the semconv names.
- Cache counters, loop refusals and the in-flight counter are created next to the code that changes them: [resilience-retry-cache.md](resilience-retry-cache.md) and observability-tracing.md §3.

## 4. Token, API usage and cost

When the server calls a model or a metered API, count usage where the call returns, not by estimating from text length.

- GenAI semconv (Development): `gen_ai.client.token.usage` (histogram, `{token}`, attribute `gen_ai.token.type` = `input`/`output`) is the long-standing name; `@opentelemetry/semantic-conventions@1.45.0` marks its constant `@deprecated` ("moved to the GenAI semantic conventions repository"). That repository now documents a `gen_ai.client.inference.usage.*` counter family with a `gen_ai.token.modality` attribute (UNVERIFIED in full: the page was only partly read). Pick one, emit it from one helper, and expect a rename.
- Attributes: `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.operation.name`, tool name. No user/tenant id (see §2).
- Cost is derived downstream (tokens × price table versioned with the deploy), not computed in the server.
- Per-tenant quota enforcement is a request-path check against a store, not a metric; see production-runtime-multi-tenant.md. Model-routing and cost controls: `agentic-ai-dev` `reference/llm-inference-and-model-routing.md`.

## 5. Export and test

- Export interval: `PeriodicExportingMetricReader` default 60 s; set `OTEL_METRIC_EXPORT_INTERVAL` lower only in tests. Graceful shutdown flushes the last interval (`sdk.shutdown()`); a `process.exit` before it loses up to one interval of metrics.
- **Pick one metrics API: OpenTelemetry.** One SDK feeds traces and metrics, exemplars link the two, and OTLP reaches any backend (a Collector can expose Prometheus). Pull-based scraping without a Collector: `@opentelemetry/exporter-prometheus@0.301.2` as the metric reader (not executed here).
- `prom-client` is deprecated on npm ("prom-client has been replaced by @prometheus-io/client"). OPTIONAL, for services that already instrument with the Prometheus client API: `@prometheus-io/client@0.16.1` (pre-1.0, pin exactly; engines `^22 || ^24 || >=26`). *Executed* on Node 26.13.1 / TS 6.0.3 (ESM named import of the CJS package compiles): a separate `Registry` with a Counter, a Histogram and `collectDefaultMetrics` served `/metrics` as `text/plain; version=0.0.4`; an undeclared label name threw. Do not run both APIs for the same metric.
- Serve `/metrics` on an internal port, never on the public `/mcp` listener.
- Test the contract, not the library: assert metric name, unit, bucket bounds and the exact attribute keys a dashboard or alert depends on (pattern: node-ci-and-observability.md §3).
