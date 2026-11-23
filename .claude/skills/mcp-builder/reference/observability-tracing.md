# MCP Server Tracing (OpenTelemetry, Node 24)

Request-level and tool-level spans for a Node MCP server, trace context from the client's `params._meta`, and logs joined to traces. The SDK bootstrap, the ESM loader hook, structured logs and the CI gates live in one place: [node-ci-and-observability.md](../../deployment-ci-cd/reference/node-ci-and-observability.md) §1–3. Read it first; this file only adds the MCP layer.

Verified 2026-11-23: `@modelcontextprotocol/server@2.4.0` + `@modelcontextprotocol/node@2.1.2` (`createMcpHandler`, stateless), `@opentelemetry/sdk-node@0.301.2`, `@opentelemetry/api@1.10.0`, Node 24.13.1, TypeScript 5.9.3 strict. The tests started the real server with `node --import ./dist/instrumentation.js`, exported to a fake OTLP/HTTP collector and asserted on the received spans and histograms (6 end-to-end tests; every claim marked *executed* below had a planted defect that made a test fail).

## 1. What to emit

| Signal | Name | Kind / unit | Source |
|--------|------|-------------|--------|
| HTTP server span per request | `POST` (from `@opentelemetry/instrumentation-http`) | SERVER | automatic, needs the ESM hook |
| Tool span per call | `tools/call {gen_ai.tool.name}`, e.g. `tools/call echo` | SERVER | `withToolTelemetry` (§3) |
| Operation duration | `mcp.server.operation.duration` | histogram, `s` | §3 + [observability-metrics.md](observability-metrics.md) |
| Logs | pino JSON with `trace_id`, `span_id` | stdout (HTTP) / stderr (stdio) | node-ci-and-observability.md §2 |

## 2. Semantic conventions: status and names

The MCP conventions are **Development** status. They moved from the main semantic-conventions repository to [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) (RECOMMENDED PRACTICE: follow them, expect renames). In `@opentelemetry/semantic-conventions@1.45.0` the `ATTR_MCP_*`, `ATTR_GEN_AI_TOOL_*` and `METRIC_MCP_*` constants still exist under `/incubating` but are marked `@deprecated` ("moved"), so declare the strings locally:

```typescript
// MCP / GenAI attribute names from the OpenTelemetry GenAI semantic conventions (status: Development).
// @opentelemetry/semantic-conventions 1.45.0 still exports ATTR_MCP_* / ATTR_GEN_AI_* from
// "/incubating", but marks them @deprecated ("moved to the semantic-conventions-genai repository"),
// so they are declared here as plain strings. Re-check the names when that repository releases.
export const MCP_METHOD_NAME = "mcp.method.name";
export const MCP_SESSION_ID = "mcp.session.id";
export const MCP_PROTOCOL_VERSION = "mcp.protocol.version";
export const JSONRPC_REQUEST_ID = "jsonrpc.request.id";
export const GEN_AI_TOOL_NAME = "gen_ai.tool.name";
export const GEN_AI_OPERATION_NAME = "gen_ai.operation.name";
export const MCP_SERVER_OPERATION_DURATION = "mcp.server.operation.duration";
export const MCP_SERVER_OPERATION_DURATION_BUCKETS = [
  0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 120, 300,
];
```

| Attribute | Requirement (semconv) | Value here |
|-----------|----------------------|------------|
| `mcp.method.name` | required | `tools/call` |
| `gen_ai.tool.name` | conditionally required (tool calls) | registered tool name |
| `gen_ai.operation.name` | recommended | `execute_tool` |
| `jsonrpc.request.id` | conditionally required (requests) | `ctx.mcpReq.id` |
| `mcp.session.id` | recommended when a session exists | absent with `createMcpHandler` (no sessions in 2026-07-28); set it on legacy sessionful transports |
| `error.type` | conditionally required (on failure) | exception class name, never the message |
| `mcp.protocol.version`, `network.transport` | recommended | add from the request header / transport if you need them |

UNVERIFIED: the exact attribute name for a JSON-RPC error code (`rpc.response.status_code` vs `rpc.status_code`) and the definition of `mcp.server.session.duration`; check the genai repository before emitting either.

## 3. Tool span + duration histogram

```typescript
import {
  context,
  metrics,
  propagation,
  trace,
  SpanKind,
  SpanStatusCode,
  type Attributes,
  type Link,
} from "@opentelemetry/api";
import {
  GEN_AI_OPERATION_NAME,
  GEN_AI_TOOL_NAME,
  JSONRPC_REQUEST_ID,
  MCP_METHOD_NAME,
  MCP_SERVER_OPERATION_DURATION,
  MCP_SERVER_OPERATION_DURATION_BUCKETS,
  MCP_SESSION_ID,
} from "./semconv.js";

const tracer = trace.getTracer("orders-mcp");
const meter = metrics.getMeter("orders-mcp");

const operationDuration = meter.createHistogram(MCP_SERVER_OPERATION_DURATION, {
  unit: "s",
  description: "MCP request duration as observed by the server",
  advice: { explicitBucketBoundaries: MCP_SERVER_OPERATION_DURATION_BUCKETS },
});
// App-specific names stay out of the semconv `mcp.*` namespace.
const activeToolCalls = meter.createUpDownCounter("app.mcp.active_tool_calls", {
  description: "Tool calls currently executing (concurrency / saturation)",
});

/** The slice of the SDK v2 handler context (`ctx`) this wrapper reads. */
export interface ToolCallContext {
  sessionId?: string | undefined; // legacy sessionful transports only; absent on 2026-07-28 (stateless)
  mcpReq: { id: string | number; _meta?: Record<string, unknown> | undefined };
}

/** W3C trace context a client put in `params._meta` (semconv-genai MCP; keys unprefixed). */
function metaCarrier(meta: Record<string, unknown> | undefined): Record<string, string> {
  const carrier: Record<string, string> = {};
  for (const key of ["traceparent", "tracestate", "baggage"]) {
    const value = meta?.[key];
    if (typeof value === "string") carrier[key] = value;
  }
  return carrier;
}

/** Low-cardinality error class for `error.type`; never the message (it can carry user data). */
export function errorType(err: unknown): string {
  if (err instanceof Error) return err.name === "Error" ? err.constructor.name : err.name;
  return "_OTHER";
}

/**
 * Wrap an MCP tool handler: one SERVER span `tools/call {tool}` per call, parented on the
 * `_meta` trace context when present (linked to the ambient HTTP span), plus the
 * `mcp.server.operation.duration` histogram and an in-flight counter.
 * Arguments and results are NOT recorded: they can contain PII and secrets.
 */
export async function withToolTelemetry<T>(
  toolName: string,
  ctx: ToolCallContext,
  run: () => Promise<T>,
): Promise<T> {
  const carrier = metaCarrier(ctx.mcpReq._meta);
  const ambient = context.active();
  const ambientSpan = trace.getSpan(ambient);
  const hasMetaParent = carrier["traceparent"] !== undefined;
  const parent = hasMetaParent ? propagation.extract(ambient, carrier) : ambient;
  const links: Link[] =
    hasMetaParent && ambientSpan !== undefined ? [{ context: ambientSpan.spanContext() }] : [];

  const attributes: Attributes = {
    [MCP_METHOD_NAME]: "tools/call",
    [GEN_AI_TOOL_NAME]: toolName,
    [GEN_AI_OPERATION_NAME]: "execute_tool",
    [JSONRPC_REQUEST_ID]: String(ctx.mcpReq.id),
  };
  if (ctx.sessionId !== undefined) attributes[MCP_SESSION_ID] = ctx.sessionId;
  // Metric attributes must stay low-cardinality: no session or request ids.
  const metricAttributes: Attributes = { [MCP_METHOD_NAME]: "tools/call", [GEN_AI_TOOL_NAME]: toolName };

  const started = performance.now();
  activeToolCalls.add(1, { [GEN_AI_TOOL_NAME]: toolName });
  return tracer.startActiveSpan(
    `tools/call ${toolName}`,
    { kind: SpanKind.SERVER, attributes, links },
    parent,
    async (span) => {
      try {
        return await run();
      } catch (err: unknown) {
        const type = errorType(err);
        span.setAttribute("error.type", type);
        metricAttributes["error.type"] = type;
        span.setStatus({ code: SpanStatusCode.ERROR, message: type });
        throw err;
      } finally {
        operationDuration.record((performance.now() - started) / 1000, metricAttributes);
        activeToolCalls.add(-1, { [GEN_AI_TOOL_NAME]: toolName });
        span.end();
      }
    },
  );
}
```

Registering a tool with it (SDK v2 handler context `ctx`):

```typescript
mcp.registerTool(
  "echo",
  { description: "Echo text back", inputSchema: z.object({ text: z.string().max(1_000) }) },
  ({ text }, ctx) =>
    withToolTelemetry("echo", ctx, () => {
      logger.info({ tool: "echo" }, "tool_call");
      return Promise.resolve({ content: [{ type: "text" as const, text }] });
    }),
);
```

Executed results:

- One HTTP `POST` span per request and one `tools/call <tool>` SERVER span per call, with the attributes above. The plain call's tool span is a child of the HTTP span (`parentSpanId` = the HTTP span id).
- The failing tool's span had status ERROR, `error.type=RangeError`, and the status message was the type, not the error text. Its argument `token` value appeared in no span attribute and no log line.
- The log line written inside the tool carried the same `trace_id` as the tool span.
- Histogram points carried only `mcp.method.name`, `gen_ai.tool.name` (+ `error.type`) and the advised bucket bounds. A planted `mcp.session.id` metric attribute failed the test: session and request ids are unbounded and belong on spans, never on metrics.
- A planted `gen_ai.tool.call.arguments` span attribute holding the arguments failed the secret-leak assertion.

## 4. Propagation through `params._meta`

An MCP client that is itself traced (an agent framework, a gateway) should inject W3C trace context into the request's `params._meta` using **unprefixed** `traceparent` / `tracestate` / `baggage` keys (semconv-genai MCP spec; the SEP it references is UNVERIFIED). The MCP specification reserves `_meta` and reserves key prefixes whose second label is `modelcontextprotocol` or `mcp`; unprefixed keys are allowed, and the base spec does not itself define `traceparent` (MCP spec 2025-11-25, *General fields: `_meta`*).

Server rule (implemented above): if `_meta.traceparent` is present, it becomes the tool span's **parent**, and the ambient HTTP span is attached as a **link**. Otherwise the HTTP span is the parent.

- Executed: a call with `_meta.traceparent = 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` produced a tool span with that trace id and parent span id `00f067aa0ba902b7`, plus a link to the HTTP span. Forcing the wrapper to ignore `_meta` failed the test.
- Why `_meta` and not only the HTTP `traceparent` header: stdio has no headers, and an HTTP client library's own instrumentation may start a different trace for the transport request than the one the agent is in (SOURCE-PROVEN in an agent-to-MCP integration).
- Client side, inject explicitly: `const meta: Record<string, string> = {}; propagation.inject(context.active(), meta);` then pass `_meta: meta` in the request params.
- Validate before trusting: `propagation.extract` ignores a malformed `traceparent`; never echo `_meta` content into logs.
- Outbound: inject `traceparent` and request-id headers only into clients for your own internal services. Third-party model, cloud and payment SDK clients get none: the ids correlate your traffic for an outside party and some APIs reject unknown headers. Build the internal-auth headers and the trace headers in one helper so a new internal client gets both and an external one gets neither (RECOMMENDED PRACTICE; SOURCE-PROVEN pattern).

## 5. Sampling

- Default: parent-based. A remote parent with `sampled=00` makes every child unsampled, including your tool spans. If tool spans must always be recorded, use `new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(r), remoteParentNotSampled: new AlwaysOnSampler() })` from `@opentelemetry/sdk-trace` (SOURCE-PROVEN pattern; it means you sample independently of callers, which raises volume).
- Keep sampling decisions at the head simple. "Keep all errors and slow calls" is a **tail** decision: do it in the OpenTelemetry Collector `tail_sampling` processor, not in a custom in-process sampler (a head sampler cannot know the outcome; the previous version of this page returned `NOT_RECORD` from a custom sampler and lost the spans it meant to keep).
- Exclude probes from tracing (`ignoreIncomingRequestHook` for `/health/*`).

## 6. Never record

Tool arguments, tool results, prompts, bearer tokens, cookies, `Mcp-Session-Id` header values in logs, upstream response bodies, or error messages from drivers (they carry hosts and sometimes credentials). Record ids, sizes, counts, types and durations instead. Content capture for AI debugging is opt-in, off in production, and redacted: [ai-observability.md](../../deployment-ci-cd/reference/ai-observability.md) §5.

## 7. Checklist

- [ ] Bootstrap and ESM hook as in node-ci-and-observability.md §1; a test proves HTTP spans exist
- [ ] Every tool wrapped: SERVER span `tools/call {tool}`, `error.type` on failure, args/results not recorded
- [ ] `_meta` trace context honoured as parent, ambient span linked
- [ ] Duration histogram with semconv buckets and low-cardinality attributes only
- [ ] Logs carry `trace_id`; redaction tested with a planted secret
