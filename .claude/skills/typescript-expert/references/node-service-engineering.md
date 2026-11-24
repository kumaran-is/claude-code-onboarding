# Node.js 26 service engineering (TypeScript 6.0, no framework required)

Production patterns for plain Node services, MCP servers, CLIs and workers. NestJS services follow `nestjs-api` for framework concerns and keep that skill's Node and TypeScript pins; everything else here still applies underneath it.

**Evidence.** Verified 2026-11-23 against Node 26.13.1 + TypeScript 6.0.3 + @types/node 26.6.6: every code block below, copied into a disposable app, passed `tsc --noEmit` (the tsconfig below), ESLint 10.15.0 + typescript-eslint 8.74.0 `strictTypeChecked`, and 23 Vitest 5.1.1 tests, with negative controls (a planted type error → TS2322 exit 2; a dropped `return await` → `return-await` exit 1; a planted failing test → exit 1). Versions used: zod 4.6.7, pino 10.4.0. The patterns were first verified on Node 24.13.1 + TypeScript 5.9.3. Behaviour marked *reproduced* was re-run on Node 26.13.1; re-check it when you change major versions.

## Contents

1. [Project setup: ESM, tsconfig, lint](#1-project-setup-esm-tsconfig-lint)
2. [ESM and CommonJS interop on Node 26](#2-esm-and-commonjs-interop-on-node-26)
3. [Configuration and secrets](#3-configuration-and-secrets)
4. [Errors: cause chains and typed results](#4-errors-cause-chains-and-typed-results)
5. [Outbound calls: deadlines and cancellation](#5-outbound-calls-deadlines-and-cancellation)
6. [Dependency injection without a framework](#6-dependency-injection-without-a-framework)
7. [Structured logging and trace correlation](#7-structured-logging-and-trace-correlation)
8. [Event-loop safety and worker threads](#8-event-loop-safety-and-worker-threads)
9. [Streams and backpressure](#9-streams-and-backpressure)
10. [Resource lifecycle: `await using`](#10-resource-lifecycle-await-using)
11. [Graceful shutdown and fatal errors](#11-graceful-shutdown-and-fatal-errors)
12. [Profiling and memory leaks](#12-profiling-and-memory-leaks)
13. [Testing](#13-testing)
14. [Dependency governance](#14-dependency-governance)
15. [Production-readiness checklist](#15-production-readiness-checklist)

## 1. Project setup: ESM, tsconfig, lint

`package.json`: `"type": "module"`, `"engines": { "node": ">=26.0.0" }` (Node 26 is the active LTS; 24 still works), exact versions. `.npmrc` in the repo:

```ini
save-exact=true
engine-strict=true
```

`tsconfig.json` for a Node service (type-checks `src` and `test`; a `tsconfig.build.json` extends it with `"noEmit": false, "rootDir": "src", "outDir": "dist", "include": ["src"]`):

```json
{
  "compilerOptions": {
    "module": "nodenext",
    "target": "es2024",
    "lib": ["es2024", "esnext.disposable"],
    "types": ["node"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "noPropertyAccessFromIndexSignature": true,
    "useUnknownInCatchVariables": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "rootDir": ".",
    "outDir": "dist",
    "sourceMap": true,
    "noEmit": true
  },
  "include": ["src", "test"]
}
```

- `module: nodenext` implies `moduleResolution: nodenext`, `esModuleInterop` and `resolveJsonModule` (confirmed with `tsc --showConfig`). TS 5.9 also accepts `module: node20`, a stable alias for Node 20+ semantics.
- TypeScript 6.0 changes, each reproduced with `tsc` 6.0.3: `types` now defaults to `[]`, so `"types": ["node"]` is required (without it `process` is TS2591); `strict` defaults to on (an untyped parameter is TS7006 with no tsconfig); `baseUrl`, `outFile` and `downlevelIteration` are TS5101, and `moduleResolution: node10`/`classic`, `module: amd`, `target: es5`, `esModuleInterop: false` are TS5107. `"ignoreDeprecations": "6.0"` silences them for one migration step only; remove the option instead. `tsc file.ts` inside a folder with a `tsconfig.json` is TS5112 (pass `--ignoreConfig` or use `-p`). When emitting from `src/`, set `rootDir` explicitly.
- TypeScript 7.0.2 (npm `latest`, native compiler) compiled this app with exit 0 in 0.16 s against 1.55 s for 6.0.3, and caught the same planted TS2322. Defer it: typescript-eslint 8.74.0 declares the peer `typescript >=4.8.4 <6.1.0`, so the lint step above is unsupported on 7. Pin `typescript` 6.0.3.
- Use `moduleResolution: bundler` only when a bundler (Vite, esbuild, Angular CLI) produces what runs. For code that Node loads directly it hides errors Node will hit at runtime, such as missing file extensions. The bundler template is `tsconfig-strict.json`.
- `paths` aliases are compile-time only. Node does not resolve them. In a Node service, use relative imports or package.json `"imports"` (`#src/*`).
- Relative imports need the runtime extension: `import { ok } from './errors.js'` for `errors.ts`. Negative control: `from './errors'` fails with TS2835.

`eslint.config.js` (flat config). `tseslint.config()` is deprecated in typescript-eslint 8.x in favour of ESLint core's `defineConfig`:

```js
import { defineConfig } from 'eslint/config';
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default defineConfig(
  { ignores: ['dist/**', 'coverage/**', 'eslint.config.js'] },
  eslint.configs.recommended,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: { parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname } },
    rules: {
      'no-console': 'error',
      // Async safety: an un-awaited promise or an async callback passed where void is expected
      // (e.g. an event listener) loses its rejection.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      '@typescript-eslint/only-throw-error': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
    },
  },
);
```

These rules catch async bugs that `tsc` accepts. Negative controls: an un-awaited `.then()` chain, an `async` listener passed to `EventEmitter.on`, and `return promise` inside an `await using` scope were flagged (`no-floating-promises`, `no-misused-promises`, `return-await`). A missing `switch` case was flagged by `switch-exhaustiveness-check`, and `tsc` reported it as TS2345 at `assertNever`. `console.log` was flagged by `no-console`.

## 2. ESM and CommonJS interop on Node 26

| Situation | Behaviour on Node 26.13.1 (*reproduced*; identical on 24.13.1) |
|---|---|
| CJS `require()` of an ESM file with no top-level `await` | Works without a flag (`process.features.require_module === true`); `require` returns the module namespace |
| CJS `require()` of ESM that uses top-level `await` | Throws `ERR_REQUIRE_ASYNC_MODULE`; use `await import()` |
| ESM `import x from './c.cjs'` | Always works; `x` is `module.exports` |
| ESM `import { named } from './c.cjs'` | Works only when Node's static analysis finds the name (`exports.named = …`). With `module.exports = { named: "ok" }` it failed: `SyntaxError: Named export 'named' not found` |
| `package.json` `"type"` | Decides how `.js` files load. `.mjs`/`.cjs` (and `.mts`/`.cts`) override it per file |
| `node file.ts` | Type stripping is on by default (`process.features.typescript === 'strip'`): erasable syntax runs; `enum`, `namespace` with values and parameter properties throw `ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`. `--experimental-transform-types` is gone (`bad option`, exit 9). Production images still run `tsc` output: stripping does no type checking |

Rules:

- One format per package. Publish ESM. Add an `"exports"` map with `"types"` first, so consumers cannot deep-import internals:

  ```json
  { "type": "module", "exports": { ".": { "types": "./dist/index.d.ts", "default": "./dist/index.js" } } }
  ```

- If you bundle an ESM-source service to CJS (for example esbuild `--format=cjs` to keep OTel instrumentation patching `require`), the output must not sit next to a `package.json` with `"type": "module"`. Name it `.cjs`, or do not copy that `package.json` into the image. Otherwise Node loads the CJS bundle as ESM and fails at startup.
- Preload instrumentation with `node --import ./dist/instrumentation.js dist/main.js`, so it runs before any application module is evaluated.
- **Default: unbundled ESM (`tsc` output) + `npm ci --omit=dev`.** Measured on Node 26.13.1 with a real MCP SDK 2.4.0 stdio `Client`, 50 tool calls, medians of 3+ runs: unbundled ESM connect 163–251 ms, peak RSS 93–96 MB; esbuild 0.28.2 CJS bundle connect 80–159 ms, peak RSS 78–80 MB. A CJS bundle saves roughly 80 ms and 15 MB, so make it opt-in for cold-start-bound deployments; it costs source maps for stack traces and makes ESM-only dependencies harder. Turning on the compile cache (`esm-compile-cache` run) changed nothing measurable.
- **OpenTelemetry in ESM: use the synchronous hook.** Register `import-in-the-middle/register-hooks.mjs` (built on `module.registerHooks()`, no warning) first in the preload. Reproduced on Node 26.13.1 with a real stdio Client: a tool calling `http.get` through `import http from 'node:http'` produced the outgoing `GET` span under that hook; the same call through `import { get } from 'node:http'` produced none, and with no hook neither did. So make traced outgoing calls with `fetch()` or a default import of `node:http`/`node:https`. `module.register('@opentelemetry/instrumentation/hook.mjs', import.meta.url)` covered every import style but prints `DEP0205`; keep it only as a fallback. A CJS bundle with `--require` recorded the span without a hook. Full matrix and bootstrap: `deployment-ci-cd` › `node-ci-and-observability.md` §1.

Node 26 runtime features worth adopting (each checked on 26.13.1):

| Feature | Use it for | Instead of |
|---|---|---|
| `--env-file=.env` | local runs and tests | `dotenv` |
| Permission model `--permission --allow-fs-read=…` (stable; denied access throws `ERR_ACCESS_DENIED`) | CLIs and tools that run untrusted input | nothing; it is defence in depth, not a sandbox |
| `AbortSignal.any` / `AbortSignal.timeout` | deadlines (§5) | timer + controller plumbing |
| `Error.isError(x)` | `catch (e: unknown)` narrowing across realms | `e instanceof Error` |
| `RegExp.escape`, `Uint8Array.fromBase64` / `toBase64` | user text in regexes; binary encoding | hand-written escapers, `Buffer` round trips |
| `Temporal` (global object) | new date/time code | moment/date libraries |

## 3. Configuration and secrets

Parse the whole environment once, at startup, with a schema. Derive the type from the schema. Freeze the result and pass it down; nothing else reads `process.env`.

```ts
import { z } from 'zod';

// Every setting the process needs, parsed once at startup. Secrets have no default:
// a missing secret must stop the process, not start it in a half-configured state.
const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3000),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
  DATABASE_URL: z.url({ protocol: /^postgres(ql)?$/ }),
  // z.httpUrl() also demands a dotted domain: it rejects IPs, localhost and service names like http://orders:8080.
  ORDERS_API_URL: z.url({ protocol: /^https?$/ }),
  ORDERS_API_TIMEOUT_MS: z.coerce.number().int().min(100).max(60_000).default(5_000),
  SHUTDOWN_TIMEOUT_MS: z.coerce.number().int().min(1_000).max(120_000).default(10_000),
  ORDERS_API_TOKEN: z.string().min(32), // secret: no default, no empty string
  FEATURE_BULK_IMPORT: z.stringbool().default(false), // "true"/"false"/"1"/"0"/"yes"/"no"/...
});

export type Config = Readonly<z.infer<typeof EnvSchema>>;

export class ConfigError extends Error {
  override readonly name = 'ConfigError';
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const parsed = EnvSchema.safeParse(env);
  if (!parsed.success) {
    // prettifyError lists variable names and rule messages, not the offending values,
    // so a malformed secret is not echoed into logs.
    throw new ConfigError(`Invalid environment:\n${z.prettifyError(parsed.error)}`);
  }
  return Object.freeze(parsed.data);
}

/** Safe to log: secrets are reduced to "set". */
export function describeConfig(config: Config): Record<string, string | number | boolean> {
  return {
    nodeEnv: config.NODE_ENV,
    port: config.PORT,
    logLevel: config.LOG_LEVEL,
    ordersApiHost: new URL(config.ORDERS_API_URL).host,
    ordersApiToken: 'set',
    featureBulkImport: config.FEATURE_BULK_IMPORT,
  };
}
```

Gotchas, each found while testing:

- **No defaults for secrets.** A `.default('')` on a token starts the service with auth silently broken. Negative control: giving `ORDERS_API_TOKEN` a default failed 2 tests. Use `.min(n)`, not `.optional()`, so an empty string is rejected too.
- **`z.coerce.number()` turns `''` into `0`.** Always bound coerced numbers (`.min(1)`). The test "rejects an empty PORT" pins this.
- **`z.httpUrl()` requires a dotted domain.** It rejects `http://127.0.0.1:4411/`, `http://localhost:3000` and in-cluster names like `http://orders:8080/`. For internal service URLs use `z.url({ protocol: /^https?$/ })`.
- **Zod 4 deprecations.** `z.string().url()`, `.email()`, `.uuid()` and similar are deprecated: use `z.url()`, `z.email()`, `z.uuid()`. For booleans use `z.stringbool()`. `z.coerce.boolean()` makes `"false"` true.
- **Empty strings from env files.** `.env` and compose pass `VAR=` as `""`. `??` keeps `""`, so treat empty as unset deliberately (`value?.trim() || fallback`) or reject it with `.min(1)`.
- **Cross-field rules** (for example "A is required when B=true") go in `.superRefine()` or a check right after parsing, still before `listen()`.
- **Do not log values.** `z.prettifyError` prints variable names and rule messages; a test asserts that a rejected secret value is not in the message. Log `describeConfig()`, never the parsed object.
- **No secrets in argv.** Command lines are visible to other local users through `ps` and are often captured by orchestrators. Pass secrets through env vars or a mounted secret file. For local development, `node --env-file=.env` loads a file (exit 9 if it is missing); `--env-file-if-exists` does not fail. Keep `.env` out of git.
- Exit with a distinct code on bad config (78, `EX_CONFIG`, below), before opening ports or connections.

## 4. Errors: cause chains and typed results

```ts
// Expected, recoverable outcomes are values (Result); bugs and broken invariants are thrown.
export type Result<T, E> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly error: E };

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
export const fail = <E>(error: E): Result<never, E> => ({ ok: false, error });

/** Wrap a lower-level error without losing it: `cause` keeps the original stack. */
export class UpstreamError extends Error {
  override readonly name = 'UpstreamError';
  constructor(
    message: string,
    readonly status: number | undefined,
    options?: ErrorOptions,
  ) {
    super(message, options);
  }
}

export function assertNever(value: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(value)}`);
}
```

- **Expected outcomes are values; bugs are thrown.** A timeout, a 404 or an invalid payload is part of the contract, so it goes in a `Result` whose error is a discriminated union, and callers must handle it (§5, §6). A broken invariant throws.
- **Wrap with `cause`.** `new UpstreamError('orders call failed', 503, { cause: err })` keeps the original stack. pino's `err` serializer appends cause messages and stacks (`caused by: …`); a test pins this.
- **Never swallow.** Every `catch` either returns a typed failure, logs and rethrows, or logs and converts to a response. `catch (e) {}` and `catch { return [] }` are defects. With `useUnknownInCatchVariables` (part of `strict`), narrow `unknown` before use.
- Throw only `Error` instances (`@typescript-eslint/only-throw-error`).

## 5. Outbound calls: deadlines and cancellation

`fetch()` has no default timeout. Every outbound call needs a deadline and should also stop when its caller stops (client disconnect, shutdown):

```ts
import type { z } from 'zod';
import { fail, ok, type Result } from './errors.js';

export type FetchFailure =
  | { readonly kind: 'timeout'; readonly timeoutMs: number }
  | { readonly kind: 'aborted' }
  | { readonly kind: 'http'; readonly status: number }
  | { readonly kind: 'invalid-payload'; readonly issues: readonly string[] }
  | { readonly kind: 'network'; readonly cause: unknown };

export interface GetJsonOptions {
  readonly timeoutMs: number;
  /** Caller cancellation, e.g. the incoming request's signal or the shutdown signal. */
  readonly signal?: AbortSignal;
  readonly headers?: Readonly<Record<string, string>>;
}

/**
 * GET a JSON resource with a hard deadline and caller cancellation, and validate it.
 * Every outbound call needs a deadline: fetch() has no default timeout of its own.
 */
export async function getJson<S extends z.ZodType>(
  url: URL,
  schema: S,
  options: GetJsonOptions,
): Promise<Result<z.output<S>, FetchFailure>> {
  const timeout = AbortSignal.timeout(options.timeoutMs);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;

  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { accept: 'application/json', ...options.headers } });
  } catch (error: unknown) {
    return fail(classify(error, timeout, options));
  }

  if (!response.ok) {
    await response.body?.cancel(); // release the connection; an unread body pins it
    return fail({ kind: 'http', status: response.status });
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (error: unknown) {
    if (signal.aborted) return fail(classify(error, timeout, options));
    return fail({ kind: 'invalid-payload', issues: ['body is not JSON'] });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return fail({
      kind: 'invalid-payload',
      issues: parsed.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`),
    });
  }
  return ok(parsed.data);
}

// Decide from the signals, not the error shape: fetch rejects with whatever reason the
// caller passed to abort(), which need not be an AbortError.
function classify(error: unknown, timeout: AbortSignal, options: GetJsonOptions): FetchFailure {
  if (options.signal?.aborted === true) return { kind: 'aborted' };
  if (timeout.aborted) return { kind: 'timeout', timeoutMs: options.timeoutMs };
  return { kind: 'network', cause: error };
}
```

- Combine signals with `AbortSignal.any([callerSignal, AbortSignal.timeout(ms)])`.
- Decide timeout vs. cancellation from which signal aborted, not from the error. `fetch` rejects with whatever reason the caller passed to `abort()`. Tests cover timeout, caller abort (with a custom reason), non-2xx, schema mismatch, and connection refused (the `TypeError` is kept as `cause`).
- Cancel or consume the body of a response you do not read (`response.body?.cancel()`). An unread body holds the connection.
- Retries: retry only idempotent requests, with capped exponential backoff and jitter, inside the same overall deadline. Never retry a 4xx other than 408 or 429.

## 6. Dependency injection without a framework

Constructor or factory injection with plain interfaces is enough. Depend on **ports**: small interfaces such as `orders.get()`, not a whole client class. Build the concrete graph in one **composition root** (`main.ts`). Tests pass fakes, with no container and no module mocking.

```ts
import { randomUUID } from 'node:crypto';
import type { IncomingMessage, RequestListener, ServerResponse } from 'node:http';
import type { Logger } from 'pino';
import { z } from 'zod';
import { assertNever, type Result } from './errors.js';
import type { FetchFailure } from './http-client.js';
import { requestContext, traceIdFrom } from './logger.js';

export const Order = z.object({ id: z.string().min(1), status: z.enum(['pending', 'paid', 'cancelled']) });
export type Order = z.infer<typeof Order>;

/** Ports the handler depends on. Production wiring lives in main.ts; tests pass fakes. */
export interface AppDeps {
  readonly logger: Logger;
  readonly orders: { get(id: string, signal: AbortSignal): Promise<Result<Order, FetchFailure>> };
  readonly isShuttingDown: () => boolean;
}

export function createRequestListener(deps: AppDeps): RequestListener {
  return (req, res) => {
    const requestId = randomUUID();
    const traceId = traceIdFrom(header(req, 'traceparent'));
    requestContext.run({ requestId, traceId }, () => {
      handle(deps, req, res).catch((error: unknown) => {
        deps.logger.error({ err: error }, 'unhandled_request_error');
        if (!res.headersSent) send(res, 500, { error: 'internal_error', requestId });
        else res.destroy();
      });
    });
  };
}

async function handle(deps: AppDeps, req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? '/', 'http://localhost');
  if (url.pathname === '/readyz') {
    send(res, deps.isShuttingDown() ? 503 : 200, { ready: !deps.isShuttingDown() });
    return;
  }
  const match = /^\/orders\/([\w-]{1,64})$/.exec(url.pathname);
  const id = match?.[1];
  if (req.method !== 'GET' || id === undefined) {
    send(res, 404, { error: 'not_found' });
    return;
  }
  // Abort the upstream call when the client goes away.
  const controller = new AbortController();
  res.once('close', () => { if (!res.writableFinished) controller.abort(); });

  const result = await deps.orders.get(id, controller.signal);
  if (result.ok) {
    send(res, 200, result.value);
    return;
  }
  const failure = result.error;
  deps.logger.warn({ failure: failure.kind }, 'orders_lookup_failed');
  switch (failure.kind) {
    case 'http':
      send(res, failure.status === 404 ? 404 : 502, { error: 'upstream_error' });
      return;
    case 'timeout':
      send(res, 504, { error: 'upstream_timeout' });
      return;
    case 'aborted':
      res.destroy();
      return;
    case 'invalid-payload':
    case 'network':
      send(res, 502, { error: 'upstream_error' });
      return;
    default:
      assertNever(failure);
  }
}

function header(req: IncomingMessage, name: string): string | undefined {
  const value = req.headers[name];
  return Array.isArray(value) ? value[0] : value;
}

function send(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify(body));
}
```

```ts
import { createServer } from 'node:http';
import { createRequestListener, Order } from './app.js';
import { ConfigError, describeConfig, loadConfig, type Config } from './config.js';
import { getJson } from './http-client.js';
import { createLogger } from './logger.js';
import { createShutdown } from './shutdown.js';

// Composition root: the only place that reads process.env and builds concrete dependencies.
function loadConfigOrExit(): Config {
  try {
    return loadConfig();
  } catch (error: unknown) {
    if (error instanceof ConfigError) {
      process.stderr.write(`${error.message}\n`); // no logger yet: config decides the log level
      process.exit(78); // EX_CONFIG: fail at startup, before listening
    }
    throw error;
  }
}
const config = loadConfigOrExit();

const logger = createLogger(config.LOG_LEVEL);
const controller = new AbortController();
let shuttingDown = false;
const ordersBase = new URL(config.ORDERS_API_URL);
const token = config.ORDERS_API_TOKEN;
const timeoutMs = config.ORDERS_API_TIMEOUT_MS;

const server = createServer(
  createRequestListener({
    logger,
    isShuttingDown: () => shuttingDown,
    orders: {
      get: (id, signal) =>
        getJson(new URL(`orders/${encodeURIComponent(id)}`, ordersBase), Order, {
          timeoutMs,
          signal: AbortSignal.any([signal, controller.signal]),
          headers: { authorization: `Bearer ${token}` },
        }),
    },
  }),
);
server.requestTimeout = 30_000; // bound slow clients
server.headersTimeout = 10_000;

const shutdown = createShutdown({ server, logger, timeoutMs: config.SHUTDOWN_TIMEOUT_MS, controller, closers: [] });
const onSignal = (signal: NodeJS.Signals): void => {
  shuttingDown = true;
  void shutdown(signal);
};
process.once('SIGTERM', onSignal);
process.once('SIGINT', onSignal);
// A rejection nobody handled is a bug: log it and take the normal shutdown path with a failing exit code.
process.on('unhandledRejection', (reason: unknown) => {
  logger.fatal({ err: reason }, 'unhandled_rejection');
  shuttingDown = true;
  void shutdown('unhandledRejection').then(() => { process.exitCode = 1; });
});

server.listen(config.PORT, () => {
  logger.info({ config: describeConfig(config) }, 'server_listening');
});
```

- `main.ts` is the only file that reads `process.env`, creates clients, and registers signal handlers. Everything else is a function of its arguments.
- `requestContext.run()` (§7) wraps each request, so every log line inside it carries `request_id` and `trace_id`.
- The `.catch` on `handle()` is the request-level safety net. It logs, then answers 500 or destroys the socket if headers were already sent.
- Set `server.requestTimeout` and `server.headersTimeout` deliberately.
- Test (excerpt): fakes in, real HTTP server, no framework:

```ts
import { once } from 'node:events';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Writable } from 'node:stream';
import { afterEach, describe, expect, it } from 'vitest';
import { createRequestListener, type AppDeps } from '../src/app.js';
import { fail, ok } from '../src/errors.js';
import { createLogger } from '../src/logger.js';

const silent = createLogger('info', new Writable({ write(_c, _e, done) { done(); } }));
let server: Server | undefined;

async function start(orders: AppDeps['orders'], shuttingDown = false): Promise<string> {
  server = createServer(createRequestListener({ logger: silent, orders, isShuttingDown: () => shuttingDown }));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return `http://127.0.0.1:${String((server.address() as AddressInfo).port)}`;
}
afterEach(() => { server?.closeAllConnections(); server?.close(); });

describe('request listener (dependencies injected, no framework)', () => {
  it('returns the order from the injected port', async () => {
    const base = await start({ get: (id) => Promise.resolve(ok({ id, status: 'paid' as const })) });
    const res = await fetch(`${base}/orders/o-1`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ id: 'o-1', status: 'paid' });
  });
  it('maps an upstream timeout to 504', async () => {
    const base = await start({ get: () => Promise.resolve(fail({ kind: 'timeout' as const, timeoutMs: 5 })) });
    expect((await fetch(`${base}/orders/o-1`)).status).toBe(504);
  });
  it('returns 500 with a request id when a dependency throws', async () => {
    const base = await start({ get: () => Promise.reject(new Error('bug')) });
    const res = await fetch(`${base}/orders/o-1`);
    expect(res.status).toBe(500);
    expect(await res.json()).toMatchObject({ error: 'internal_error', requestId: expect.any(String) as unknown });
  });
  it('reports not ready while shutting down', async () => {
    const base = await start({ get: () => Promise.reject(new Error('unused')) }, true);
    expect((await fetch(`${base}/readyz`)).status).toBe(503);
  });
});
```

## 7. Structured logging and trace correlation

```ts
import { AsyncLocalStorage } from 'node:async_hooks';
import { pino, type DestinationStream, type Logger } from 'pino';

export interface RequestContext {
  readonly requestId: string;
  /** W3C trace id (32 hex chars) when the caller sent a `traceparent` header. */
  readonly traceId: string | undefined;
}

/** Per-request context that follows the async call chain without being passed by hand. */
export const requestContext = new AsyncLocalStorage<RequestContext>();

export function createLogger(level: string, destination?: DestinationStream): Logger {
  return pino(
    {
      level,
      base: { service: 'orders-api' },
      timestamp: pino.stdTimeFunctions.isoTime,
      // Redact by path before serialisation. Wildcards match one level only.
      redact: {
        paths: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token', '*.apiKey'],
        censor: '[REDACTED]',
      },
      // Every line logged inside requestContext.run() carries the ids, with no manual threading.
      mixin() {
        const ctx = requestContext.getStore();
        return ctx === undefined ? {} : { request_id: ctx.requestId, trace_id: ctx.traceId };
      },
    },
    destination,
  );
}

const TRACEPARENT = /^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/;

export function traceIdFrom(traceparent: string | undefined): string | undefined {
  return traceparent === undefined ? undefined : TRACEPARENT.exec(traceparent)?.[1];
}
```

- JSON to stdout (or **stderr** when stdout carries a protocol, such as an MCP stdio server). One logger instance, created in the composition root and passed down or retrieved from context; children via `logger.child({ component })`.
- **Redact by path** (`redact.paths`, `censor`). `*` matches one level only, so list deeper paths explicitly. Negative control: removing the paths failed the redaction test. Redaction backs up, and does not replace, not logging secrets in the first place.
- **Correlation:** `AsyncLocalStorage` carries the request id through `await`s, and pino's `mixin()` stamps it on every line. The example takes the trace id from the W3C `traceparent` header. With OpenTelemetry, read `trace.getActiveSpan()?.spanContext()` in the mixin instead, or use the OTel pino instrumentation. Exporter and SDK setup is owned by `deployment-ci-cd/reference/ai-observability.md`.
- Log events as stable snake_case `msg` values (`orders_lookup_failed`) with fields, not interpolated sentences, so they can be queried.

## 8. Event-loop safety and worker threads

One synchronous 100 ms loop stalls every request in the process. Keep the main thread for I/O:

- Avoid `*Sync` fs/crypto/zlib calls on request paths. Watch for large `JSON.parse`/`JSON.stringify` and catastrophic regexes on user input. Paginate instead of building huge arrays.
- Measure loop delay continuously:

```ts
import { monitorEventLoopDelay } from 'node:perf_hooks';
import type { Logger } from 'pino';

/** Warn when synchronous work stalls the event loop. Returns a stop function. */
export function startEventLoopMonitor(logger: Logger, intervalMs: number, thresholdMs: number): () => void {
  const histogram = monitorEventLoopDelay({ resolution: 20 });
  histogram.enable();
  const timer = setInterval(() => {
    const p99Ms = histogram.percentile(99) / 1e6; // histogram values are nanoseconds
    if (p99Ms > thresholdMs) logger.warn({ p99Ms, maxMs: histogram.max / 1e6 }, 'event_loop_delay_high');
    histogram.reset();
  }, intervalMs);
  timer.unref(); // a monitor must never keep the process alive
  return () => {
    clearInterval(timer);
    histogram.disable();
  };
}
```

  Test: a 150 ms busy loop produced `event_loop_delay_high` at a 50 ms threshold.

- Move CPU-bound work (hashing, parsing, image work) to `worker_threads`. Validate `workerData` inside the worker. Make tasks cancellable. Inject the worker URL so dev and production can load different build outputs:

```ts
import { pbkdf2Sync } from 'node:crypto';
import { parentPort, workerData } from 'node:worker_threads';
import { z } from 'zod';

// CPU-bound work runs off the main thread so the event loop keeps serving requests.
const Input = z.object({ password: z.string().min(1), salt: z.string().min(16), iterations: z.number().int().positive() });
const input = Input.parse(workerData);
const digest = pbkdf2Sync(input.password, input.salt, input.iterations, 32, 'sha256').toString('hex');
parentPort?.postMessage(digest);
```

```ts
import { Worker } from 'node:worker_threads';

/**
 * Run one task in a worker thread with cancellation. The worker URL is injected so the
 * caller decides which build output to load (src in dev, dist in production).
 * For sustained load reuse workers through a pool instead of one Worker per task.
 */
export function runWorker(workerUrl: URL, data: unknown, signal: AbortSignal): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    signal.throwIfAborted();
    const worker = new Worker(workerUrl, { workerData: data });
    const onAbort = (): void => {
      void worker.terminate();
      reject(signal.reason instanceof Error ? signal.reason : new Error('worker aborted', { cause: signal.reason }));
    };
    signal.addEventListener('abort', onAbort, { once: true });
    worker.once('message', (message: unknown) => {
      signal.removeEventListener('abort', onAbort);
      if (typeof message === 'string') resolve(message);
      else reject(new Error('worker returned a non-string result'));
    });
    worker.once('error', (error) => {
      signal.removeEventListener('abort', onAbort);
      reject(new Error('worker failed', { cause: error }));
    });
    worker.once('exit', (code) => {
      signal.removeEventListener('abort', onAbort);
      if (code !== 0) reject(new Error(`worker exited with code ${String(code)}`));
    });
  });
}
```

  Tests: result matches the main-thread computation; abort terminates a long task; a worker that throws on invalid input rejects with `worker failed` and the original error as `cause`. Under sustained load reuse workers through a pool sized to the CPU count, rather than one `Worker` per task.

- Unbounded `Promise.all` over user-sized input is a concurrency bug. Process it in fixed-size batches, or use a semaphore or bulkhead with a bounded queue and a queue timeout.

## 9. Streams and backpressure

Use `pipeline` from `node:stream/promises`. Never chain `.pipe()`, which neither forwards errors nor destroys the other stages. `pipeline` propagates backpressure, tears down every stage on error or abort, and accepts async generators as transforms:

```ts
import { createReadStream, createWriteStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { createGzip } from 'node:zlib';

/**
 * Redact a line-oriented log file and gzip it. pipeline() propagates backpressure,
 * destroys every stage on error or abort, and rejects with the first error.
 */
export async function redactAndCompress(
  source: string,
  destination: string,
  pattern: RegExp,
  signal?: AbortSignal,
): Promise<void> {
  await pipeline(
    createReadStream(source, { encoding: 'utf8' }),
    async function* redact(chunks: AsyncIterable<string>): AsyncGenerator<string> {
      let carry = '';
      for await (const chunk of chunks) {
        const lines = (carry + chunk).split('\n');
        carry = lines.pop() ?? '';
        for (const line of lines) yield `${line.replace(pattern, '[REDACTED]')}\n`;
      }
      if (carry.length > 0) yield carry.replace(pattern, '[REDACTED]');
    },
    createGzip(),
    createWriteStream(destination),
    signal === undefined ? {} : { signal },
  );
}
```

Tests: redaction and gzip round-trip; an aborted signal rejects with `AbortError`. When writing to a stream by hand, respect `write()` returning `false` and `await once(stream, 'drain')` before writing more.

## 10. Resource lifecycle: `await using`

TypeScript 5.9+ compiles `using` / `await using` (lib `esnext.disposable`), and Node 24+ runs them natively (Node 26.13.1: V8 14.6, `Symbol.asyncDispose` built in):

```ts
/** A resource that releases itself at scope exit, even when the scope throws (`await using`). */
export interface Connection extends AsyncDisposable {
  query(sql: string): Promise<number>;
}

export interface Pool {
  acquire(): Promise<Connection>;
}

export async function countOrders(pool: Pool): Promise<number> {
  await using connection = await pool.acquire();
  // `return await`, not `return`: without it the connection is disposed before the query settles.
  return await connection.query('select count(*) from orders');
} // connection[Symbol.asyncDispose]() runs here on return and on throw
```

**`return await` is required inside a `using` scope.** With a bare `return connection.query(...)`, the connection is disposed before the query settles. Negative control: dropping the `await` failed both ordering tests, and typescript-eslint `return-await` (in `strictTypeChecked`) flags it. Use `using` for per-scope resources such as pool connections, temp files, locks and spans. Process-lifetime resources are closed by the shutdown sequence (§11).

Common leak sources: listeners added per request and never removed (pass `{ once: true }` or remove them in `finally`), unbounded `Map` caches (bound them with LRU + TTL), timers without `clearTimeout`/`unref()`, and closures captured by long-lived emitters.

## 11. Graceful shutdown and fatal errors

```ts
import type { Server } from 'node:http';
import type { Logger } from 'pino';

export interface ShutdownOptions {
  readonly server: Server;
  readonly logger: Logger;
  readonly timeoutMs: number;
  /** Closed in order after the server stops accepting work, e.g. queue consumer, DB pool, telemetry flush last. */
  readonly closers: ReadonlyArray<{ readonly name: string; readonly close: () => Promise<void> }>;
  /** Aborted if in-flight work has not drained by half the deadline; outbound calls listen to it. */
  readonly controller: AbortController;
}

/**
 * One shutdown path for every trigger (SIGTERM, SIGINT, fatal error). Idempotent.
 * Sets process.exitCode instead of calling process.exit() so pending log writes flush;
 * a hard deadline (unref'd, so it never keeps the process alive) covers hung closers.
 */
export function createShutdown(options: ShutdownOptions): (reason: string) => Promise<void> {
  let started: Promise<void> | undefined;
  return (reason) => {
    started ??= run(options, reason);
    return started;
  };
}

async function run(options: ShutdownOptions, reason: string): Promise<void> {
  const { server, logger, timeoutMs, closers, controller } = options;
  logger.info({ reason }, 'shutdown_started');

  const deadline = setTimeout(() => {
    logger.fatal({ timeoutMs }, 'shutdown_timed_out');
    process.exit(1);
  }, timeoutMs);
  deadline.unref();

  // Let in-flight requests finish; cancel what is still running at half the deadline.
  const cancelInFlight = setTimeout(() => {
    controller.abort(new Error(`shutdown: ${reason}`));
  }, Math.floor(timeoutMs / 2));
  cancelInFlight.unref();

  let failed = false;
  // Stop accepting connections and wait for in-flight requests; idle keep-alive sockets
  // would otherwise hold close() open until they time out.
  const closed = new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) reject(error);
      else resolve();
    });
  });
  server.closeIdleConnections();
  try {
    await closed;
  } catch (error: unknown) {
    failed = true;
    logger.error({ err: error }, 'http_server_close_failed');
  }
  clearTimeout(cancelInFlight);

  for (const closer of closers) {
    try {
      await closer.close();
      logger.info({ resource: closer.name }, 'resource_closed');
    } catch (error: unknown) {
      failed = true;
      logger.error({ err: error, resource: closer.name }, 'resource_close_failed');
    }
  }

  clearTimeout(deadline);
  logger.info({ failed }, 'shutdown_complete');
  process.exitCode = failed ? 1 : 0;
}
```

Wiring is in `main.ts` (§6): `process.once('SIGTERM' | 'SIGINT')` → mark not ready → `shutdown(signal)`. *Reproduced* end to end against the built service:

| Scenario | Result |
|---|---|
| SIGTERM while a request waits 800 ms on its upstream (deadline 5 s) | In-flight request completed with **200**, new connections refused, exit **0** |
| SIGTERM with an upstream that never answers (deadline 2 s) | Call cancelled at half the deadline, socket closed, exit **0** |
| A closer that rejects | Logged; the later closers still ran; exit **1** |
| A closer that hangs while holding a handle | `shutdown_timed_out` at the deadline, exit **1** |

- **One coordinator** for every trigger; idempotent; resources closed in reverse dependency order, telemetry flush last. Do not register separate `SIGTERM` listeners in instrumentation files that race a `process.exit()` elsewhere; register their flush as a closer.
- Set `process.exitCode` instead of calling `process.exit()` on the success path, so buffered logs flush. Keep the deadline `unref()`'d. A pending promise does not keep Node alive (in a test, a closer that held no handle ended with exit 13, unsettled top-level `await`). The deadline only matters when something is still holding the loop open, which is exactly the hung case.
- The deadline must be below the orchestrator's kill grace period (Kubernetes `terminationGracePeriodSeconds`, 30 s by default). Behind a load balancer, keep serving briefly with readiness at 503 so endpoints are removed before `server.close()`. Run Node as PID 1 only with an init (`dumb-init`/`tini` or `docker run --init`), so signals are delivered and zombies reaped.
- **Unhandled rejections are fatal.** Node's default (`--unhandled-rejections=throw`) crashes with exit 1 (*reproduced*). Do not install a handler that only logs, and do not make the behaviour depend on `NODE_ENV`: a dev-only "non-fatal" mode hides bugs until production. If you add a handler, log at `fatal` and take the shutdown path with a failing exit code, as `main.ts` does. For `uncaughtException`, log and exit 1: the process state is unknown.

## 12. Profiling and memory leaks

All *reproduced* on Node 26.13.1 (each flag wrote its file, exit 0):

| Need | Command |
|---|---|
| CPU profile of a run | `node --cpu-prof --cpu-prof-dir=prof dist/main.js` → `*.cpuprofile` on exit (open in Chrome DevTools › Performance, or `speedscope`) |
| Heap snapshot of a live process | start with `--heapsnapshot-signal=SIGUSR2 --diagnostic-dir=prof`, then `kill -USR2 <pid>` |
| Heap snapshot from code (admin endpoint, test) | `v8.writeHeapSnapshot(path)` (blocks the loop while it writes; the file is roughly heap size) |
| Allocation sampling | `node --heap-prof` |
| Live debugging | `node --inspect=127.0.0.1:9229`; never bind the inspector to `0.0.0.0` |

Leak workflow: take snapshot A after warm-up, apply load, force steady state, take snapshot B, then compare in DevTools (Comparison view) and follow the retainers of the growing constructor. Snapshots contain heap data (tokens, PII): treat them as secrets. Set `--max-old-space-size` below the container memory limit, so V8 collects garbage before the kernel OOM-kills the process. The real heap limit is that value plus about 96 MB (`v8.getHeapStatistics().heap_size_limit`: 320 → 416 MB on Node 26.13.1), and RSS adds code, stacks and buffers on top. Filling the heap until V8's own OOM peaked at 433 MiB RSS with 320 and 520 MiB with 384, so for a 512 MiB container use `--max-old-space-size=320` (about 62 % of the limit). A stdio MCP server under 50 calls peaked at 80–143 MB RSS, OTel included. Profile before optimising (`code-standards.md` › Performance).

## 13. Testing

The workspace standard for TypeScript services is **Vitest** (5.1.1 here). Use `vitest run` in CI, never watch mode. Tests run against real Node primitives: an `http` server on port 0, temp dirs, child processes for signal handling. Mock only the ports from §6. For a dependency-free library or script, `node:test` + `node:assert/strict` is built in (`node --test`). Run it on compiled `.js`, or on `.ts` that imports with `.ts` extensions, because Node's type stripping does not rewrite `./x.js` to `./x.ts`.

```ts
import { once } from 'node:events';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { z } from 'zod';
import { getJson } from '../src/http-client.js';

const Order = z.object({ id: z.string(), status: z.enum(['pending', 'paid']) });
let server: Server;
let base: URL;

beforeAll(async () => {
  server = createServer((req, res) => {
    if (req.url === '/slow') { setTimeout(() => res.end('{}'), 2_000).unref(); return; }
    if (req.url === '/bad') { res.end(JSON.stringify({ id: 1 })); return; }
    if (req.url === '/missing') { res.writeHead(404).end('nope'); return; }
    res.setHeader('content-type', 'application/json').end(JSON.stringify({ id: 'o1', status: 'paid' }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  base = new URL(`http://127.0.0.1:${String((server.address() as AddressInfo).port)}/`);
});
afterAll(() => { server.closeAllConnections(); server.close(); });

describe('getJson', () => {
  it('returns the validated value', async () => {
    const result = await getJson(new URL('ok', base), Order, { timeoutMs: 1_000 });
    expect(result).toEqual({ ok: true, value: { id: 'o1', status: 'paid' } });
  });
  it('reports a timeout as a value, not a throw', async () => {
    const result = await getJson(new URL('slow', base), Order, { timeoutMs: 100 });
    expect(result).toEqual({ ok: false, error: { kind: 'timeout', timeoutMs: 100 } });
  });
  it('distinguishes caller cancellation from timeout', async () => {
    const controller = new AbortController();
    setTimeout(() => { controller.abort(new Error('client gone')); }, 50);
    const result = await getJson(new URL('slow', base), Order, { timeoutMs: 1_000, signal: controller.signal });
    expect(result).toEqual({ ok: false, error: { kind: 'aborted' } });
  });
  it('rejects a payload that does not match the schema', async () => {
    const result = await getJson(new URL('bad', base), Order, { timeoutMs: 1_000 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe('invalid-payload');
  });
  it('maps non-2xx to an http failure', async () => {
    const result = await getJson(new URL('missing', base), Order, { timeoutMs: 1_000 });
    expect(result).toEqual({ ok: false, error: { kind: 'http', status: 404 } });
  });
  it('maps connection refusal to a network failure that keeps the cause', async () => {
    const result = await getJson(new URL('http://127.0.0.1:9/'), Order, { timeoutMs: 1_000 });
    expect(result.ok).toBe(false);
    if (!result.ok && result.error.kind === 'network') expect(result.error.cause).toBeInstanceOf(TypeError);
    else expect.unreachable('expected a network failure');
  });
});
```

## 14. Dependency governance

| Control | Command / setting | Negative control (*reproduced*) |
|---|---|---|
| Exact pins | `.npmrc` `save-exact=true`; `npm i -E` | — |
| Reproducible install | `npm ci` in CI and Docker (never `npm install`); commit `package-lock.json` | dependency bumped in `package.json` only → `npm ci` exit 1 `EUSAGE` "…not in sync" |
| Known CVEs | `npm audit --audit-level=high` (fails on high/critical) | `lodash@4.17.20` → exit 1, "1 high severity vulnerability" |
| Registry signatures and provenance | `npm audit signatures` | clean tree: "145 packages have verified registry signatures, 53 … verified attestations", exit 0 |
| Install scripts | `npm ci --ignore-scripts` in image builds where no dependency needs a build step | — |
| Production image | `npm ci --omit=dev`, non-root user, base image pinned by digest | — |

Before adding a package: confirm it is the real package name (typosquatting), check maintenance and weekly downloads, pin it exactly, and prefer Node built-ins (`fetch`, `AbortSignal`, `node:test`, `--env-file`, `util.parseArgs`, `crypto.randomUUID`) over a dependency.

## 15. Production-readiness checklist

- [ ] `type: module`, `module: nodenext`, strict flags from §1; `tsc --noEmit` and `eslint .` exit 0 (`strictTypeChecked` + async rules)
- [ ] Config parsed by one schema at startup; no secret defaults; no secrets in argv or logs; bad config → non-zero exit before `listen()`
- [ ] Every outbound call has a deadline and a cancellation signal; non-2xx and invalid payloads are typed failures
- [ ] No swallowed errors; wrapped errors keep `cause`; expected failures are `Result` unions with exhaustive handling
- [ ] Structured JSON logs with redaction and request/trace ids; no `console.*`
- [ ] No synchronous CPU work on request paths; loop-delay metric; CPU work in workers
- [ ] Streams via `stream/promises` `pipeline`; bounded concurrency and queues
- [ ] SIGTERM drains in-flight work within a deadline below the orchestrator's grace period; unhandled rejection → fatal
- [ ] `npm ci`, `npm audit --audit-level=high`, `npm audit signatures` in CI; exact pins; lockfile committed
- [ ] Tests cover the happy path and each failure kind, and the shutdown path is exercised at least once in a real process
