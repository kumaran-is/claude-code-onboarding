# MCP Server Monitoring: SLOs, Alerts, Runbook, Cost

How to turn the spans and metrics from [observability-tracing.md](observability-tracing.md) and [observability-metrics.md](observability-metrics.md) into SLOs, pages and an investigation routine. Thresholds in this file are starting points to tune against your own baseline. They are not measured industry numbers; earlier "typical result" percentages were removed because they had no source.

## 1. SLIs and SLOs

| SLI | Good event | Source |
|-----|-----------|--------|
| Availability | a `tools/call` that did not fail for a server or dependency reason | `mcp.server.operation.duration` count, minus points whose `error.type` is a server/dependency class |
| Latency | a call finishing under the per-tool threshold (e.g. 1 s for reads, 5 s for reports) | same histogram, bucket at the threshold |
| Readiness | `/health/ready` 200 from the load balancer's view | LB / probe metrics |

- Count caller errors (validation failures, 4xx-style tool errors such as "order not found") as **good** events for availability. Otherwise one misbehaving agent burns your budget.
- Pick latency thresholds that are bucket boundaries (0.5, 1, 2, 5 …). A histogram cannot answer "under 750 ms" exactly.
- One SLO per user-visible journey (or per tool group), not per tool, unless a tool has its own consumer.

## 2. Burn-rate alerts (multiwindow, multi-burn-rate)

RECOMMENDED PRACTICE: Google SRE Workbook, *Alerting on SLOs*, Table 5-8 (https://sre.google/workbook/alerting-on-slos/), for a 99.9% SLO over 30 days:

| Severity | Long window | Short window | Burn rate | Budget consumed when it fires |
|----------|-------------|--------------|-----------|-------------------------------|
| Page | 1 h | 5 min | 14.4 | 2% |
| Page | 6 h | 30 min | 6 | 5% |
| Ticket | 3 d | 6 h | 1 | 10% |

An alert fires when **both** windows exceed `burn_rate × (1 − SLO)` (for 99.9%, 14.4 × 0.001 = 1.44% errors). The short window (1/12 of the long one, per the Workbook) makes the alert reset quickly once the problem stops.

PromQL shape (UNVERIFIED: not run through `promtool`; metric names depend on your exporter's OTLP→Prometheus translation, typically `mcp_server_operation_duration_seconds_count`):

```promql
# error ratio over a window; repeat for 5m, 30m, 1h, 6h as recording rules
sum(rate(mcp_server_operation_duration_seconds_count{error_type=~"UpstreamHttpError|TaskCancelledError|BrokenCircuitError|_OTHER"}[1h]))
/
sum(rate(mcp_server_operation_duration_seconds_count[1h]))
```

```yaml
# page: fast burn
- alert: McpToolsErrorBudgetFastBurn
  expr: (job:mcp_error_ratio:rate1h > 14.4 * 0.001) and (job:mcp_error_ratio:rate5m > 14.4 * 0.001)
  labels: { severity: page }
```

Also alert, without an SLO, on: readiness failing on all replicas for > 2 min; breaker open > 5 min for a required upstream; event-loop delay p99 > 200 ms for 10 min; restarts (container restart count rising); and no telemetry at all for 10 min (`absent()` on the request histogram), because a dead exporter looks like a quiet system.

## 3. Failure investigation runbook

Work from the outside in. Each step names the signal and what it rules out.

1. **Scope.** Which SLO is burning; one tool, all tools, one replica, one region? Histogram by `gen_ai.tool.name` and `error.type`; replica from the resource attributes.
2. **Recent change.** Deploy, config, flag, upstream deploy, model/prompt version (`deployment-ci-cd/reference/llmops-release-and-rollout.md`). If a change lines up with the start, roll back first and investigate after.
3. **Dependency or self?** Breaker state and `UpstreamHttpError`/`TaskCancelledError` share → upstream. Event-loop delay, CPU, memory (RSS growth, GC) → this process. Bulkhead `queued` > 0 or `BulkheadRejectedError` → saturation: capacity or a slow upstream holding slots. `app.upstream.retries` rising before errors do → the upstream is degrading. `app.mcp.auth.denials` jumping → a rotated key, an expired client token or probing (check `app.auth.reason`; the token itself is never recorded).
4. **Exemplar trace.** Pick a failing span (`status=ERROR`, filter by `gen_ai.tool.name`), follow parent and links: the client's trace (via `_meta`), the HTTP span, the outbound HTTP/DB spans. The slowest child is the suspect.
5. **Logs for that trace.** Query by `trace_id`. Logs give the event names and error types; they must not give you the arguments (§4).
6. **Readiness and shutdown.** Spikes of 503 `shutting_down` during deploys mean the readiness drain is shorter than the load balancer's deregistration delay ([production-runtime-shutdown-health.md](production-runtime-shutdown-health.md)). `shutdown_drain_timeout` logs mean in-flight work exceeds the drain budget.
7. **Agent behaviour.** `app.mcp.tool_loops_blocked` rising or one tool's rate jumping without user traffic → a client agent is looping or a prompt changed. That is fixed on the client; the server's job is to refuse and stay healthy.
8. **Close out.** Write down the trigger, the detection gap (which alert should have fired earlier), and add a test or alert that would have caught it. AI-specific incidents: `/ai-incident-response`.

## 4. Safe diagnostic logging

- Raise verbosity by configuration (`LOG_LEVEL=debug` on one replica, time-boxed), never by redeploying code that logs payloads.
- Debug logs follow the same redaction as production logs: ids, sizes, types, durations. Never tool arguments, results, prompts, tokens, cookies, session ids or driver error messages.
- Prefer a trace sample (`OTEL_TRACES_SAMPLER=parentbased_traceidratio`, higher ratio) over more logs: spans already carry structure and timing.
- CPU or memory investigation: `node --cpu-prof` / `--heap-prof` on a replica taken out of rotation (readiness off), or a heap snapshot via the inspector bound to localhost and reached through a port-forward. Heap snapshots contain every live string, including secrets and user data: treat the file as sensitive and delete it after use.
- Never expose `--inspect` on a public interface.

## 5. Token, API usage and cost governance

- Count model tokens and metered API calls where the response returns (observability-metrics.md §4); cost is tokens × a versioned price table, computed downstream.
- Budgets: a per-tenant or per-key quota checked **before** the call (token bucket or a counter in a shared store), returning a clear "quota exceeded" tool error; a daily spend alert on the derived cost; a hard cap on tool calls per agent run on the client side.
- Upstream API quotas: the client-side token bucket in [resilience-retry-cache.md](resilience-retry-cache.md) keeps you under the vendor's rate limit; 429s still count as dependency failures for the breaker (resilience-core.md).
- Cost levers, in order: cache stable reads (resilience-retry-cache.md), return smaller structured results instead of whole documents, route simple calls to cheaper models (`agentic-ai-dev` `reference/llm-inference-and-model-routing.md`). Measure each change against the cost metric before and after; do not quote savings you did not measure.

## 6. Dashboard

Top row (page-worthy): SLO burn, error ratio, p99 per tool group, readiness across replicas. Middle: per-tool rate and errors by `error.type`, breaker state, bulkhead occupancy/queue, event-loop delay. Bottom: cache hit ratio, retries, auth denials, loops blocked, token usage and derived cost, export health.
