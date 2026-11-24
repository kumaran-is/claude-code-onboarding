# Production Runtime: Graceful Shutdown and Health Checks

Liveness and readiness endpoints, in-flight tracking and a graceful shutdown for a Node MCP server over Streamable HTTP. Multi-tenant concerns: [production-runtime-multi-tenant.md](production-runtime-multi-tenant.md). Container and Kubernetes wiring: [production-deployment-docker.md](production-deployment-docker.md). NestJS (Terminus) and other stacks: [health-endpoints.md](../../deployment-ci-cd/reference/health-endpoints.md).

Verified 2026-11-23 against `@modelcontextprotocol/server@2.4.0` + `@modelcontextprotocol/node@2.1.2` (+ `@modelcontextprotocol/fastify@2.0.1`, Fastify 5.12.8 for §8), Node 26.13.1, TypeScript 6.0.3 strict with `exactOptionalPropertyTypes`. The end-to-end tests spawn the real process, send SIGTERM during a 1.5 s tool call, and poll the probes. Planted defects that each failed a test: liveness calling the database, no readiness flip, no wait for in-flight work, telemetry not flushed at shutdown (the span-export check ran on Node 24.13.1; the probe, drain and exit-code checks were re-run on Node 26.13.1).

## 1. Rules

| Endpoint | Answers | Checks | During shutdown |
|----------|---------|--------|-----------------|
| `/health/live` | "is this process able to serve HTTP at all?" | nothing external | **200** until the process exits |
| `/health/ready` | "should the load balancer send traffic here now?" | required dependencies, each with a short timeout | **503** from the first moment of shutdown |
| startup probe (optional) | "has initialisation finished?" | same as ready, with a longer allowance | n/a |

- A liveness probe that checks dependencies restarts every replica when the database blips, turning a dependency incident into a full outage. One `/health` endpoint that does both is the common form of this bug (SOURCE-PROVEN).
- Readiness responses say *what* failed, never *why*: no driver messages, hosts or connection strings. Log the error type server-side (*executed*: the fake DB error contained an IP address; the 503 body and the logs did not).
- Exclude probe paths from tracing and from the SLO request count.

## 2. Lifecycle (readiness flag, in-flight tracking, shutdown)

```typescript
import type { Server } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import type { Logger } from "pino";

export interface ShutdownOptions {
  /** Keep serving (readiness already failing) so the load balancer stops routing here. */
  readinessDrainMs: number;
  /** Hard budget for in-flight work; must be below the platform grace period (k8s default 30 s). */
  drainTimeoutMs: number;
  /** After in-flight work drains: close the MCP handler (aborts leftovers, ends open streams). */
  closeMcp: () => Promise<void>;
  /** Closed in order once the listener has closed: pools, then telemetry LAST so it flushes everything. */
  closers: Array<{ name: string; close: () => Promise<void> }>;
}

/** Process lifecycle: readiness flag, in-flight tracking and an idempotent graceful shutdown. */
export class Lifecycle {
  #ready = false;
  #draining = false;
  #inFlight = 0;
  #idle: Array<() => void> = [];
  #shutdown: Promise<number> | undefined;

  constructor(private readonly logger: Logger) {}

  markReady(): void {
    this.#ready = true;
  }
  get ready(): boolean {
    return this.#ready && !this.#draining;
  }
  get draining(): boolean {
    return this.#draining;
  }
  get inFlight(): number {
    return this.#inFlight;
  }

  /** Wrap a unit of work; returns false (caller answers 503) once draining has started. */
  async track(work: () => Promise<void>): Promise<boolean> {
    if (this.#draining) return false;
    this.#inFlight++;
    try {
      await work();
    } finally {
      this.#inFlight--;
      if (this.#inFlight === 0) this.#idle.splice(0).forEach((resolve) => { resolve(); });
    }
    return true;
  }

  #whenIdle(): Promise<void> {
    return this.#inFlight === 0 ? Promise.resolve() : new Promise((resolve) => this.#idle.push(resolve));
  }

  /** Returns the exit code. Safe to call from several signals: runs once. */
  shutdown(server: Server, signal: string, opts: ShutdownOptions): Promise<number> {
    this.#shutdown ??= this.#run(server, signal, opts);
    return this.#shutdown;
  }

  async #run(server: Server, signal: string, opts: ShutdownOptions): Promise<number> {
    this.logger.info({ signal, in_flight: this.#inFlight }, "shutdown_started");
    this.#ready = false; // 1. readiness -> 503; liveness stays 200
    await delay(opts.readinessDrainMs); // 2. let endpoints/LB deregister while still serving
    this.#draining = true; // 3. new work on kept-alive sockets gets 503 + Connection: close
    const closed = new Promise<void>((resolve) => server.close(() => { resolve(); })); // 4. stop accepting
    server.closeIdleConnections();
    let exitCode = 0;
    const drained = await Promise.race([
      this.#whenIdle().then(() => true),
      delay(opts.drainTimeoutMs, false, { ref: false }), // unref: never holds the process open
    ]);
    if (!drained) {
      this.logger.error({ in_flight: this.#inFlight }, "shutdown_drain_timeout");
      exitCode = 1;
    }
    await opts.closeMcp();
    server.closeAllConnections(); // anything still open after drain + MCP close is abandoned
    await closed;
    for (const closer of opts.closers) {
      try {
        await closer.close();
      } catch (err: unknown) {
        this.logger.error({ err, closer: closer.name }, "shutdown_closer_failed");
        exitCode = 1;
      }
    }
    this.logger.info({ exit_code: exitCode }, "shutdown_complete");
    return exitCode;
  }
}
```

Sequence on SIGTERM and why each step exists:

1. **Readiness 503, keep serving.** Endpoints controllers and load balancers take seconds to stop routing to a terminating pod. Requests still arrive during this window; refusing them would surface as errors to callers.
2. **Wait `readinessDrainMs`** (≥ the LB's deregistration delay; 5–10 s typical). Alternatively a Kubernetes `preStop: sleep`; do not do both or you pay twice.
3. **Stop accepting**: `server.close()`; close idle keep-alive sockets. New requests that still arrive on a kept-alive socket get 503 with `Connection: close`.
4. **Drain** in-flight work, bounded by `drainTimeoutMs`.
5. **Close the MCP handler** (aborts what is left, ends open streams), then force-close remaining sockets.
6. **Closers in order**: upstream pools, database, then telemetry **last** so the spans of the drained requests are exported.
7. **Exit** with 0, or 1 if the drain timed out or a closer failed. The previous version of this page exited 0 even after a failed cleanup, which hides shutdown bugs from the platform.

## 3. Server: probes and the MCP endpoint

```typescript
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { localhostHostValidation, localhostOriginValidation, toNodeHandler, type NodeIncomingMessageLike } from "@modelcontextprotocol/node";
import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import type { Logger } from "pino";
import { withToolTelemetry } from "./mcp-telemetry.js";
import type { Lifecycle } from "./lifecycle.js";

export interface Dependencies {
  /** Readiness check for a required dependency; must be fast and bounded. */
  checkDatabase: (signal: AbortSignal) => Promise<void>;
}

const READINESS_CHECK_TIMEOUT_MS = 1_000;

function buildMcpServer(logger: Logger): McpServer {
  const mcp = new McpServer({ name: "orders-mcp", version: "1.0.0" });
  mcp.registerTool(
    "echo",
    { description: "Echo text back", inputSchema: z.object({ text: z.string().max(1_000) }) },
    ({ text }, ctx) =>
      withToolTelemetry("echo", ctx, () => {
        logger.info({ tool: "echo" }, "tool_call");
        return Promise.resolve({ content: [{ type: "text" as const, text }] });
      }),
  );
  mcp.registerTool(
    "slow_report",
    { description: "Long-running report (drain test)", inputSchema: z.object({ ms: z.number().int().min(0).max(10_000) }) },
    ({ ms }, ctx) =>
      withToolTelemetry("slow_report", ctx, async () => {
        await delay(ms, undefined, { signal: ctx.mcpReq.signal });
        return { content: [{ type: "text" as const, text: `done after ${ms} ms` }] };
      }),
  );
  mcp.registerTool(
    "fail",
    { description: "Always fails (error-path telemetry)", inputSchema: z.object({ token: z.string().optional() }) },
    (args, ctx) =>
      withToolTelemetry("fail", ctx, () => {
        // `args.token` is removed by the logger's redact paths.
        logger.warn({ args }, "tool_failing");
        return Promise.reject(new RangeError("quota exceeded"));
      }),
  );
  return mcp;
}

function sendJson(res: ServerResponse, status: number, body: unknown, close = false): void {
  res.writeHead(status, { "content-type": "application/json", ...(close ? { connection: "close" } : {}) });
  res.end(JSON.stringify(body));
}

export function createAppServer(logger: Logger, lifecycle: Lifecycle, deps: Dependencies) {
  // One McpServer per request, no sessions (SDK v2 createMcpHandler).
  const mcpHandler = createMcpHandler(() => buildMcpServer(logger));
  const nodeHandler = toNodeHandler(mcpHandler);
  // Local sandbox: localhost guards. Behind a load balancer use explicit allow-lists (node-mcp-setup.md).
  const validateHost = localhostHostValidation();
  const validateOrigin = localhostOriginValidation();

  async function handleReady(res: ServerResponse): Promise<void> {
    if (!lifecycle.ready) {
      sendJson(res, 503, { status: "draining" });
      return;
    }
    try {
      await deps.checkDatabase(AbortSignal.timeout(READINESS_CHECK_TIMEOUT_MS));
      sendJson(res, 200, { status: "ok", checks: { database: "ok" } });
    } catch (err: unknown) {
      // Log the type; never put the message (hosts, credentials) in the response.
      logger.warn({ check: "database", error_type: err instanceof Error ? err.name : "unknown" }, "readiness_check_failed");
      sendJson(res, 503, { status: "unavailable", checks: { database: "error" } });
    }
  }

  const server: Server = createServer((req: IncomingMessage, res: ServerResponse) => {
    const path = (req.url ?? "/").split("?")[0];
    // Liveness: the process can serve HTTP. No dependency calls; stays 200 while draining.
    if (path === "/health/live") {
      sendJson(res, 200, { status: "ok" });
      return;
    }
    if (path === "/health/ready") {
      void handleReady(res);
      return;
    }
    if (path !== "/mcp") {
      sendJson(res, 404, { error: "not_found" });
      return;
    }
    if (!validateHost(req, res) || !validateOrigin(req, res)) return;
    void lifecycle
      .track(() =>
        // Cast: IncomingMessage.method is `string | undefined`; NodeIncomingMessageLike.method is optional (TS2379 under exactOptionalPropertyTypes).
        nodeHandler(req as NodeIncomingMessageLike, res).catch((err: unknown) => {
          logger.error({ err }, "mcp_request_failed");
          if (!res.headersSent) sendJson(res, 500, { jsonrpc: "2.0", error: { code: -32603, message: "Internal error" }, id: null });
        }),
      )
      .then((accepted) => {
        if (!accepted) sendJson(res, 503, { error: "shutting_down" }, true);
      });
  });

  return {
    server,
    /** After in-flight requests drained: aborts anything left and closes the MCP handler. */
    closeMcp: () => mcpHandler.close(),
  };
}
```

## 4. Entry point: signals, timeouts, fatal errors

```typescript
import type { AddressInfo } from "node:net";
import { shutdownTelemetry } from "./instrumentation.js";
import { createLogger } from "./logger.js";
import { Lifecycle } from "./lifecycle.js";
import { createAppServer } from "./server.js";

const logger = createLogger();
const lifecycle = new Lifecycle(logger);

// Test hook standing in for a real dependency ping (e.g. `SELECT 1` with a bounded timeout).
const app = createAppServer(logger, lifecycle, {
  checkDatabase: () =>
    process.env["FAKE_DB_DOWN"] === "true"
      ? Promise.reject(new Error("connect ECONNREFUSED 10.0.0.5:5432"))
      : Promise.resolve(),
});

// Node's defaults: keepAliveTimeout 5 s, headersTimeout 60 s, requestTimeout 300 s. Keep the
// server keep-alive above the load balancer's idle timeout to avoid 502s on reused sockets.
app.server.keepAliveTimeout = Number(process.env["HTTP_KEEP_ALIVE_MS"] ?? 65_000);
app.server.headersTimeout = app.server.keepAliveTimeout + 1_000;
app.server.requestTimeout = 30_000;

app.server.listen(Number(process.env["PORT"] ?? 3000), process.env["HOST"] ?? "0.0.0.0", () => {
  lifecycle.markReady();
  const { port } = app.server.address() as AddressInfo;
  logger.info({ port }, "listening");
});

const shutdownMode = process.env["SHUTDOWN_MODE"] ?? "graceful";
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.once(signal, () => {
    if (shutdownMode === "naive") process.exit(0); // negative control only: drops in-flight work and spans
    void lifecycle
      .shutdown(app.server, signal, {
        readinessDrainMs: Number(process.env["READINESS_DRAIN_MS"] ?? 5_000),
        drainTimeoutMs: Number(process.env["DRAIN_TIMEOUT_MS"] ?? 20_000),
        closeMcp: () => app.closeMcp(),
        closers: [{ name: "telemetry", close: shutdownTelemetry }],
      })
      .then((code) => process.exit(code));
  });
}

// A programming error leaves state unknown: log it and exit non-zero; the orchestrator restarts us.
process.on("uncaughtException", (err) => {
  logger.fatal({ err }, "uncaught_exception");
  process.exit(1);
});
process.on("unhandledRejection", (reason) => {
  logger.fatal({ err: reason }, "unhandled_rejection");
  process.exit(1);
});
```

- **One owner for signals.** The telemetry bootstrap registers no SIGTERM handler; the app's shutdown calls `shutdownTelemetry()` as its last closer. Two independent handlers race: one calls `process.exit` while the other is still flushing (SOURCE-PROVEN: spans of the last requests were lost). `process.once` guards against a second signal re-entering; `Lifecycle.shutdown` is idempotent as well.
- **`keepAliveTimeout` above the load balancer's idle timeout** (for example 65 s against a 60 s ALB default) so the LB, not Node, closes idle sockets. Otherwise the LB reuses a socket Node just closed and returns 502. Node's defaults are `keepAliveTimeout` 5 s, `headersTimeout` 60 s, `requestTimeout` 300 s (*executed* `node -e` on 24.13.1 and 26.13.1: unchanged).
- **`uncaughtException` exits.** After a programming error the process state is unknown; log fatal and let the orchestrator restart it. Do not run the graceful drain from there.

## 5. What the tests showed

| Check | Result |
|-------|--------|
| Ready while healthy | `/health/ready` 200 `{"status":"ok"}` |
| Database down | ready 503 `{"status":"unavailable","checks":{"database":"error"}}` without the IP from the error; live 200 |
| SIGTERM during a 1.5 s tool call, `READINESS_DRAIN_MS=500` | ready 503 and live 200 during the drain window; then a new connection got `ECONNREFUSED`; the in-flight call completed with its result; exit code 0; the call's span reached the collector |
| Negative control `SHUTDOWN_MODE=naive` (`process.exit(0)` on SIGTERM) | the in-flight call failed, its span never arrived |

## 6. Budgets that must line up

```
LB deregistration delay  ≤  readinessDrainMs (or preStop sleep)
longest tool budget      ≤  drainTimeoutMs
readinessDrainMs + drainTimeoutMs + closers (≈ 1–2 s)  <  terminationGracePeriodSeconds (Kubernetes default 30 s)
```

With the defaults above (5 s + 20 s + ~2 s = 27 s), the default 30 s grace period is just enough. If tools run longer, raise `terminationGracePeriodSeconds`, not only the drain timeout: after the grace period the kubelet sends SIGKILL and nothing is flushed. Cloud Run sends SIGTERM and allows 10 s before SIGKILL (RECOMMENDED PRACTICE source: https://cloud.google.com/run/docs/container-contract#instance-shutdown), so on Cloud Run use a short readiness drain (≈ 1 s) and keep tool budgets well under 10 s, or move long work to a job.

## 7. stdio servers

A stdio server has no probes. Handle stdin `end`/`close` and SIGTERM with the same ordered close (abort in-flight, close pools, flush telemetry, exit), and log to stderr only: stdout carries the protocol.

## 8. Fastify variant

For the Fastify app in [node-mcp-advanced.md](node-mcp-advanced.md#streamable-http-on-fastify): `Fastify({ return503OnClosing: true })` answers new requests on kept-alive sockets with 503 while closing, and `app.close()` waits for in-flight requests. One trap, found in testing: `close()` only drops sockets that are idle *at that instant*; a keep-alive socket whose call finishes later held `close()` open until `keepAliveTimeout` (Fastify default 72 s). Sweep idle sockets while closing.

```typescript
import { setTimeout as delay } from "node:timers/promises";
import type { FastifyInstance } from "fastify";
import type { McpHttpHandler } from "@modelcontextprotocol/server";

export interface DrainOptions {
  readinessDrainMs: number; // >= load balancer deregistration delay
  drainTimeoutMs: number; // >= longest tool budget, < platform grace period
}

/** Resolves with the exit code: 1 if the drain timed out. */
export async function shutdownFastify(
  app: Pick<FastifyInstance, "close" | "server" | "log">,
  handler: McpHttpHandler,
  setReady: (ready: boolean) => void,
  opts: DrainOptions,
): Promise<number> {
  setReady(false); // /health/ready -> 503; keep serving while the LB deregisters
  await delay(opts.readinessDrainMs);
  let exitCode = 0;
  const timer = setTimeout(() => {
    exitCode = 1; // budget spent: abort leftovers through the MCP handler, then drop sockets
    app.log.error("shutdown_drain_timeout");
    void handler.close().finally(() => app.server.closeAllConnections());
  }, opts.drainTimeoutMs);
  timer.unref();
  const sweep = setInterval(() => app.server.closeIdleConnections(), 250);
  sweep.unref();
  await app.close(); // stop accepting, wait for in-flight requests
  clearInterval(sweep);
  clearTimeout(timer);
  await handler.close(); // idempotent
  return exitCode; // then close pools, telemetry last, and process.exit(exitCode)
}
```

Verified with a real `Client`: SIGTERM during a 1.5 s call → ready 503, live 200, call completed, new connection `ECONNREFUSED`, exit 0. Negative controls (each failed a test): drain budget 300 ms shorter than the call → call aborted, exit 1; idle sweep removed → `close()` stalled on the client's idle keep-alive socket until the 5 s drain timeout fired: exit 1 after ~6 s instead of 0 after ~2 s. On stdio, `serveStdio()` returns a handle with `close()`; when the host closed stdin mid-call the in-flight handler's signal aborted and the process exited.

