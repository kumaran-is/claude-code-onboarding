# Node.js / TypeScript CI Gates, Supply Chain and Observability

Canonical reference for Node 26 services (plain `node:http`, Fastify, NestJS, MCP servers): OpenTelemetry bootstrap, structured logs, CI quality gates and the container image. The Python equivalents are `python-observability.md` and `python-ci-supply-chain.md`; MCP-specific spans and metrics are in `../../mcp-builder/reference/observability-tracing.md`.

Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3 strict (`nodenext`, `exactOptionalPropertyTypes`), Vitest 5.1.1 (§1–3: an ESM Fastify 5.12.8 + MCP SDK v2 server exporting to a fake OTLP collector, 29 tests including negative controls). §4 was executed on Node 24.13.1, TypeScript 5.9.3, ESLint 10.15 + typescript-eslint 8.73, actionlint 1.7.12 (its gate script re-checked on Node 26 with typescript-eslint 8.74 + prettier 3.10.1); §5 on Docker with Node 26.13.1. Re-check versions with `npm view <pkg> version` before you copy a pin.

| Package | Version used | Note |
|---------|--------------|------|
| `@opentelemetry/api` | 1.10.0 | `sdk-node` 0.301 peer-requires `>=1.10.0 <1.11.0` |
| `@opentelemetry/sdk-node`, `instrumentation`, `instrumentation-http`, `exporter-*-otlp-http` | 0.301.2 | experimental line, moves fast |
| `@opentelemetry/instrumentation-undici` | 0.35.1 | client spans + `traceparent` for global `fetch()` |
| `@fastify/otel` | 1.0.1 | replaces `@opentelemetry/instrumentation-fastify` (0.57.0, deprecated on npm "in favor of @fastify/otel"); it nests `@opentelemetry/instrumentation@0.300.0` |
| `import-in-the-middle` | 3.6.0 | synchronous ESM loader hook (`register-hooks.mjs`) |
| `@opentelemetry/sdk-trace`, `sdk-metrics`, `resources`, `core` | 3.1.1 | `sdk-trace-base` is deprecated on npm: "Use @opentelemetry/sdk-trace package" |
| `@opentelemetry/semantic-conventions` | 1.45.0 | stable entry point; `/incubating` for Development attributes |
| `pino` | 10.4.0 | |
| `prom-client` | 15.1.3 | deprecated on npm: "replaced by @prometheus-io/client" (0.16.1); see mcp-builder `observability-metrics.md` §5 |
| `@opentelemetry/auto-instrumentations-node` | 0.83.1 (not installed) | meta-package; prefer the individual instrumentations you use |

## 1. Bootstrap: start the SDK before the app, and register the ESM hook

Two files, loaded with `node --import ./dist/instrumentation.js dist/main.js`. The SDK must start before the app imports `node:http`, the database driver or the framework. Ship unbundled ESM (`"type": "module"`, `tsc` output): a bundler inlines the packages the instrumentations patch.

```typescript
// src/register-hooks.ts: must be the FIRST import of the bootstrap
// Node 26 (and 24.11.1+, 22.22.3+): synchronous in-thread loader hook built on module.registerHooks().
// module.register() still works but prints DEP0205 (runtime-deprecated) on Node 26.
import { register } from "import-in-the-middle/register-hooks.mjs";

register();
```

```typescript
// src/instrumentation.ts
import "./register-hooks.js";
import { NodeSDK } from "@opentelemetry/sdk-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { UndiciInstrumentation } from "@opentelemetry/instrumentation-undici";
import { FastifyOtelInstrumentation } from "@fastify/otel";
import { defaultResource, resourceFromAttributes } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";

const enabled = process.env["OTEL_SDK_DISABLED"] !== "true";

const sdk = enabled
  ? new NodeSDK({
      // Merge with defaultResource() so telemetry.sdk.* attributes are kept. `.trim() ||` (not `??`)
      // because an empty OTEL_SERVICE_NAME from a .env file is a string, not undefined.
      resource: defaultResource().merge(
        resourceFromAttributes({
          [ATTR_SERVICE_NAME]: process.env["OTEL_SERVICE_NAME"]?.trim() || "orders-mcp",
          [ATTR_SERVICE_VERSION]: process.env["APP_VERSION"] ?? "0.0.0",
        }),
      ),
      // Exporter endpoint, headers and protocol come from OTEL_EXPORTER_OTLP_* env vars.
      spanProcessors: [new BatchSpanProcessor({ exporter: new OTLPTraceExporter() })],
      metricReaders: [
        new PeriodicExportingMetricReader({
          exporter: new OTLPMetricExporter(),
          exportIntervalMillis: Number(process.env["OTEL_METRIC_EXPORT_INTERVAL"] ?? 60_000),
        }),
      ],
      instrumentations: [
        new HttpInstrumentation({
          // Probes would otherwise dominate trace volume.
          ignoreIncomingRequestHook: (req) => req.url?.startsWith("/health/") ?? false,
        }),
        new UndiciInstrumentation(), // global fetch(): client span + traceparent header
        // Fastify only: route/hook spans. registerOnInitialization adds the plugin to every Fastify instance.
        new FastifyOtelInstrumentation({ registerOnInitialization: true, ignorePaths: "/health/*" }),
      ],
    })
  : undefined;

sdk?.start();

/** Flush and stop telemetry. Call once, as the LAST step of graceful shutdown. */
export async function shutdownTelemetry(): Promise<void> {
  await sdk?.shutdown();
}
```

The app imports `shutdownTelemetry` from the same module URL, so it gets the instance `--import` started. That import also means dropping `--import` does not, by itself, drop spans: in the container run `node dist/main.js` still exported HTTP and Fastify spans, because the bootstrap is evaluated before the CommonJS framework loads `node:http`. Keep `--import` anyway: it runs the hook and SDK before the app's whole import graph is linked (ESM-only dependencies, for example; that case was NOT RUN in a container). The control that proves the hook matters is the plain-ESM probe in the matrix below, not removing `--import`. It registers **no** signal handler of its own: the app's shutdown sequence calls it last (`../../mcp-builder/reference/production-runtime-shutdown-health.md`).

What was proven on Node 26.13.1 (all executed; span counts from the fake collector):

| Hook in `register-hooks.ts` | DEP0205 warning | Plain ESM `node:http` server span | ESM client `import http from "node:http"` | ESM client `import { get }` / `import * as http` | global `fetch()` |
|-----|-----|-----|-----|-----|-----|
| none | no | **0** | **0** | **0** | 1 (undici, diagnostics channel) |
| `import-in-the-middle/register-hooks.mjs` (sync, above) | no | 1 | 1 | **0** | 1 |
| `module.register("@opentelemetry/instrumentation/hook.mjs", import.meta.url)` | **yes** | 1 | 1 | 1 | 1 |

- Rule with the sync hook: make outbound HTTP calls with `fetch()` (or `undici`), or import `node:http`/`node:https` as the default export. Named and namespace imports of those builtins are not patched, so those calls get no client span and send no `traceparent`. Keep a test that asserts a CLIENT span for each outbound client you use (§3); it caught this gap.
- Fastify (and any CommonJS framework) `require()`s `node:http`, so `require-in-the-middle` patches it in every mode: an ESM Fastify app had HTTP server spans even with no hook. A plain ESM `node:http` server had none without the hook.
- `module.register()` is runtime-deprecated on Node 26 (DEP0205) but still the only mode that covered every import style here; use it only as a fallback (for example on Node older than 22.22.3 / 24.11.1, where `supportsSyncHooks()` from the same module returns false).
- CommonJS output (`"type": "commonjs"`) does not need the hook; `--require` / `--import` of the bootstrap is enough.
- **Bundlers:** instrumentation patches modules at load time, so a module inlined into a bundle is never patched. Mark instrumented packages external (`esbuild --external:@opentelemetry/* --external:pg ...`) or do not bundle. Bundled ESM output that imports a CJS bootstrap with `"type": "module"` in the runtime `package.json` also fails to load; ship the `package.json` that matches the build format.
- Merge your attributes into `defaultResource()`: a bare `resourceFromAttributes(...)` drops `telemetry.sdk.*` (executed; detectors still add `host.*` / `process.*`). Exported `telemetry.sdk.version` was `3.1.1`.
- Family split (npm, 2026-11-23): `api` 1.10.0; stable SDK packages (`core`, `resources`, `sdk-trace`, `sdk-metrics`) 3.1.1; experimental packages (`sdk-node`, `instrumentation*`, OTLP exporters, `exporter-prometheus`) 0.301.2. Upgrade each family together; `sdk-node` 0.301 peer-requires api `>=1.10.0 <1.11.0`.
- API drift from 1.x/2.x guidance (each was a compile error against these versions): `new Resource(...)` (use `resourceFromAttributes`), `metricReader:` (use `metricReaders: [...]`), `import { tracing } from "@opentelemetry/sdk-node"` (no longer exported; samplers come from `@opentelemetry/sdk-trace`), `new BatchSpanProcessor(exporter)` (now an options object), `ATTR_DEPLOYMENT_ENVIRONMENT` from the stable entry (use `ATTR_DEPLOYMENT_ENVIRONMENT_NAME`).
- The `sdk-node` README still documents `metricReader`; the published `NodeSDKConfiguration` type does not have it. Trust the types.
- `startNodeSdk()` (`@experimental`) configures from env vars or a declarative YAML file; use it only if you accept an experimental API.

## 2. Structured logs that link to traces

```typescript
import { pino, type Logger } from "pino";
import { trace, context } from "@opentelemetry/api";

/**
 * JSON logs. HTTP servers log to stdout (fd 1); a stdio MCP server MUST pass fd 2, because stdout
 * carries JSON-RPC. Every line carries trace_id/span_id of the active span, and secrets are
 * redacted by path before serialisation.
 */
export function createLogger(fd: 1 | 2 = 1, level = process.env["LOG_LEVEL"] ?? "info"): Logger {
  return pino(
    {
      level,
      base: { service: process.env["OTEL_SERVICE_NAME"] ?? "orders-mcp" },
      timestamp: pino.stdTimeFunctions.isoTime,
      redact: {
        paths: [
          "req.headers.authorization",
          "req.headers.cookie",
          'req.headers["mcp-session-id"]',
          "args.token",
          "args.password",
          "*.apiKey",
        ],
        censor: "[REDACTED]",
      },
      mixin() {
        const span = trace.getSpan(context.active());
        if (span === undefined) return {};
        const { traceId, spanId } = span.spanContext();
        return { trace_id: traceId, span_id: spanId };
      },
    },
    pino.destination({ fd, sync: true }),
  );
}
```

- Executed: the tool-call log line's `trace_id` equalled the tool span's trace id; a `token` argument logged as `[REDACTED]`, and the raw value appeared nowhere in the log stream. Removing the `"args.token"` path made the test fail.
- `redact` is path-based: it only protects the paths you list. Prefer logging an allow-list of fields (`{ tool, order_id }`) over whole objects, and log `err.name`/error type rather than messages that may carry user data.
- Never log request or tool arguments wholesale, bearer tokens, cookies, session ids, or upstream response bodies.

## 3. Prove spans exist (test pattern)

Telemetry that is configured but never exported fails silently. The sandbox test spawns the service exactly as production does (`node --import ./dist/instrumentation.js dist/main.js`) with `OTEL_EXPORTER_OTLP_ENDPOINT` pointing at a ~40-line fake collector (`node:http` server that parses OTLP/HTTP JSON from `/v1/traces` and `/v1/metrics`), sets `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, drives real requests, then asserts on span names, kinds, parent ids and attributes. Keep `fileParallelism: false` for these process-level tests. Flush test: with long export intervals (`OTEL_BSP_SCHEDULE_DELAY=60000`, `OTEL_METRIC_EXPORT_INTERVAL=600000`) nothing reached the collector before SIGTERM and spans + metrics arrived after it (exit 0); a variant that exited without `shutdownTelemetry()` exported nothing (negative control). In-process alternative: `InMemorySpanExporter` + `SimpleSpanProcessor({ exporter })` from `@opentelemetry/sdk-trace`, which cannot catch bootstrap-order or ESM-hook mistakes.

## 4. CI gates (GitHub Actions)

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [develop]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  node:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: .nvmrc
          cache: npm
      - name: Install from lockfile (fails if package.json and package-lock.json disagree)
        run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run build
      - name: Tests (JSON report for the count gate)
        run: npm run test:ci
      - name: Executed-test-count gate (0 collected or any skipped = red)
        run: node scripts/check-test-count.js test-results.json 23
      - name: Dependency audit (exit 1 on high or critical)
        run: npm audit --audit-level=high
      - name: Verify registry signatures and provenance
        run: npm audit signatures
      - name: Lockfile unchanged by the job
        run: git diff --exit-code -- package-lock.json
```

`actionlint` 1.7.12: exit 0 on this file; a control file with `${{ github.event.pull_request.title }}` inside `run:` exited 1 (script-injection finding). SHAs were resolved with `git ls-remote https://github.com/<owner>/<repo> 'refs/tags/<tag>' 'refs/tags/<tag>^{}'`; pin rules are in `python-ci-supply-chain.md` §3 and apply unchanged.

Scripts: `"typecheck": "tsc -p tsconfig.test.json"` (a config whose `include` covers `src` AND `test`, so test files are type-checked too), `"lint": "eslint ."`, `"test:ci": "vitest run --reporter=default --reporter=json --outputFile=test-results.json"`.

Name the gate `.js` (the package is `"type": "module"`), not `.mjs`: with typescript-eslint's `projectService`, a `.mjs` file outside the tsconfig fails with "was not found by the project service", while the usual `{ files: ['**/*.js'], extends: [tseslint.configs.disableTypeChecked] }` block lints a `.js` script untyped. Verified 2026-11-23 against eslint 10.15.0 + typescript-eslint 8.74.0 + prettier 3.10.1 with the `/scaffold-mcp-server` configs (`.prettierrc.json` `{ "singleQuote": true, "printWidth": 120 }`): the script below passed `prettier --check` (exit 0) and `eslint --max-warnings=0` (exit 0); the previous `.mjs` copy exited 1 on both. Against real Vitest 5.1.1 JSON, an empty run (`--passWithNoTests`, vitest exit 0) made the gate exit 1; 3 passing with minimum 3 exited 0.

```javascript
// scripts/check-test-count.js
// Fails CI when the suite executed fewer tests than expected, skipped any, or reported failures.
// A runner that collects 0 tests can exit 0; this turns "nothing ran" into a red build.
import { readFileSync } from 'node:fs';

const [file = 'test-results.json', minArg = '1'] = process.argv.slice(2);
const r = JSON.parse(readFileSync(file, 'utf8'));
const min = Number(minArg);
const executed = r.numPassedTests + r.numFailedTests;
const problems = [];
if (executed < min) problems.push(`executed ${executed} < expected minimum ${min}`);
if (r.numPendingTests + r.numTodoTests > 0) problems.push(`${r.numPendingTests + r.numTodoTests} skipped/todo`);
if (r.numFailedTests > 0 || r.success !== true) problems.push(`${r.numFailedTests} failed`);
process.stderr.write(
  `tests: total=${r.numTotalTests} passed=${r.numPassedTests} failed=${r.numFailedTests} skipped=${r.numPendingTests}\n`,
);
if (problems.length > 0) {
  process.stderr.write(`TEST COUNT GATE FAILED: ${problems.join('; ')}\n`);
  process.exit(1);
}
```

| Check | Observed (executed) |
|-------|---------------------|
| `vitest run` with no matching files | exit 1 (default) |
| `vitest run --passWithNoTests` with no files | exit 0; count gate on its report exit 1 ("executed 0") |
| suite with one `it.skip` | vitest exit 0; count gate exit 1 ("1 skipped/todo") |
| 23 passing, minimum 23 / minimum 24 | gate exit 0 / exit 1 |
| `npm audit --audit-level=high`, clean tree | exit 0 |
| same, `lodash@4.17.20` installed (high advisories) | exit 1 |
| same tree, `--audit-level=critical` | **exit 0**: a high finding passes; keep `high` |
| `npm ci`, lock in sync / `package.json` pin changed without re-locking | exit 0 / exit 1 (`EUSAGE ... not in sync`) |
| `tsc` strict on a file with `as any` + `string` returned as `number` | exit 2 |
| ESLint `strictTypeChecked` + `no-console` on the same file | exit 1 (`no-console`, `no-explicit-any`, `no-unsafe-member-access`) |

- `npm ci` validates the dependency graph, not a workspace member's own `version` field; a hand-bumped workspace version with a stale root lock still installs (SOURCE-PROVEN in a monorepo). Add a check that every `package.json` `version` matches its lock entry if you hand-edit versions.
- Never `npm install` in CI. `npm audit` needs registry access; a network failure is BLOCKED, not PASS.
- A workflow cited in docs must exist: verify `.github/workflows/<name>.yml` before claiming "CI runs X" (a monorepo's architecture doc pointed at a Node CI workflow that did not exist, SOURCE-PROVEN).

## 5. Container image

```dockerfile
# Base image pinned by multi-arch index digest (resolved 2026-11-23 for node:26.13.1-trixie-slim). Renovate/Dependabot bump it.
ARG NODE_IMAGE=node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM ${NODE_IMAGE} AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM ${NODE_IMAGE} AS runtime
# Heap cap ~60-65% of the container memory limit (320 MiB for 512 MiB), leaving room for buffers and native memory.
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=320
WORKDIR /app
# Files stay root-owned and read-only to the app user. package.json is required: it carries "type": "module".
COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER node
EXPOSE 3000
# Docker/Compose only: Kubernetes and Cloud Run ignore HEALTHCHECK and use their own probes.
# The slim image has no curl/wget, so the check uses node's global fetch against LIVENESS (no dependency calls).
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
# Exec form: node is PID 1 and receives SIGTERM directly (no shell in between).
CMD ["node", "--import", "./dist/instrumentation.js", "dist/main.js"]
```

- Verified 2026-11-23 against Docker with Node 26.13.1: digest from `docker buildx imagetools inspect node:26.13.1-trixie-slim` (exit 0); an MCP server image built and ran healthy under `docker run --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m`; a host SDK v2 `Client` negotiated protocol 2026-07-28 and, in legacy mode, 2025-11-25 and called a tool; inside the container the process ran as uid 1000 with no dev dependencies, `/app` was read-only and `heap_size_limit` was 332 MiB with the 320 flag (268 MiB without); `docker stop` returned exit 0 after 1 s (exec-form PID 1 got SIGTERM). With the real §1 bootstrap in the same hardened container (Fastify + MCP SDK v2, OTLP to a host-side receiver, long batch delay): 0 spans before `docker stop`, then 15 spans (HTTP `POST`, `@fastify/otel` request/preHandler/handler, `mcp.auth`, `tools/call echo` in the same trace as its `POST /mcp`) and a metrics batch after SIGTERM; no DEP0205; `OTEL_SDK_DISABLED=true` → 0 spans.
- MCP servers: the Host/Origin allowlist needed when binding `0.0.0.0` (hostnames without port; it also guards `/health/*`, so a `HEALTHCHECK` on 127.0.0.1 needs `127.0.0.1` in the list), Kubernetes probe `Host` headers, the distroless variant, the smoke test and the image CI job are in `../../mcp-builder/reference/production-deployment-docker.md` §0. Do not copy them here.
- `npm prune --production` is the old spelling; use `npm ci --omit=dev` in a separate stage so dev dependencies never enter the runtime layers.
- `--ignore-scripts` blocks install-time scripts (supply-chain hardening). Packages with native builds need an explicit `npm rebuild <pkg>` step; list them.
- `node` as PID 1 is fine when the app handles SIGTERM/SIGINT itself (§ shutdown); add `--init` / `tini` only if you spawn child processes that must be reaped.
- Scan the image (Trivy/Grype/`docker scout`) in CI; OS packages are outside `npm audit`.

## 6. Checklist

- [ ] Bootstrap loaded with `--import`, sync ESM hook (`import-in-the-middle/register-hooks.mjs`) registered first, no DEP0205 warning, SDK flushed by the app's shutdown (not its own SIGTERM handler)
- [ ] A test proves an HTTP span per request, a CLIENT span per outbound client, and the custom spans reach an exporter
- [ ] Logs are single-line JSON with `trace_id`, secrets redacted, no `console.log`
- [ ] CI: `npm ci`, typecheck incl. tests, lint, build, tests + executed-count gate, `npm audit --audit-level=high`, `npm audit signatures`, lockfile unchanged
- [ ] Actions pinned by SHA, runner pinned, base image pinned by digest, update bot enabled
- [ ] Image: non-root, prod deps only, liveness `HEALTHCHECK`, exec-form `CMD`
