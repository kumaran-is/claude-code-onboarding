---
description: Scaffold a TypeScript MCP server (SDK v2, Node 26 LTS, TypeScript 6.0.3) with stdio and/or Streamable HTTP on Fastify, one shared tool registry, zod schemas, bearer auth + per-tool scope allowlist, pino to stderr, real-Client vitest tests, Dockerfile, CI and Inspector. Use when starting a new MCP server; not for Python servers (mcp-builder python-mcp-setup.md) or adding tools to an existing one.
argument-hint: "[server-name] [stdio|http|both]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold: TypeScript MCP Server

**Arguments:** $ARGUMENTS (first word = project directory and server name; second = `stdio`, `http` or `both`, default `both`).

There is no maintained official initializer: `@modelcontextprotocol/create-server` 0.3.1 is deprecated on npm (re-check with `npm view @modelcontextprotocol/create-server deprecated`). This command writes verbatim, verified files from two templates:

- `C` = `.claude/skills/mcp-builder/assets/scaffold-templates-core.md`
- `H` = `.claude/skills/mcp-builder/assets/scaffold-templates-http-ops.md`

Load the `mcp-builder` skill first. Tool design rules are in `reference/mcp-design-principles.md`, security in `reference/security-core.md`.

Verified 2026-11-23 on Node 26.13.1 / TypeScript 6.0.3 / SDK v2 (server, client 2.4.0): every file was extracted from `C` and `H` into an empty directory, and all steps under Verify ran with exit 0.

## Rules

- MCP servers use Node 26 LTS only (Angular, React and NestJS keep their own pins). Use TypeScript 6.0.3, not 7.x: typescript-eslint 8.74.0 peers `typescript >=4.8.4 <6.1.0`.
- Exact pins (`npm i -E`), ESM (`"type": "module"`), unbundled `tsc` output.
- New code imports only the v2 packages (`@modelcontextprotocol/server`, `/client`, `/node`, `/fastify`), never `@modelcontextprotocol/sdk`. Tools use `registerTool`; v2 has no `tool()` and no `SSEServerTransport`.
- stdout belongs to the stdio transport: log with pino to fd 2. ESLint `no-console: error` is the gate.
- Identity comes from the verified token (HTTP) or the process owner (stdio), never from tool arguments. Every tool needs a scope in `TOOL_SCOPES`; a tool missing there is denied.
- The HTTP bearer gate is always on. There is no unauthenticated HTTP mode; use stdio locally.
- Add optional pieces only when the user asks: OpenTelemetry (section below), metrics (`reference/observability-metrics.md`), Redis/DB clients, sessions. For plain `node:http` instead of Fastify, see `reference/node-mcp-setup.md`.

## Steps

1. Confirm `node -v` prints `v26.x` and that the target directory does not exist (never overwrite). Create the directory and `cd` into it. Resolve the host with `python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --find-host <target parent>` (exit 1 = standalone). If `--root "$HOST"` reports `join.npm`, add this server path to host `workspaces` after writing files. Do not add Nx.
2. Write the project files from `C` §1. For `stdio`, apply the dependency note at the top of §1.
3. Write the tool registry from `C` §2 (`src/logger.ts`, `src/notes.ts`, `src/tools.ts`). Rename the sample tool and data to the user's domain.
4. `stdio` or `both`: write `src/stdio.ts` and `test/stdio.test.ts` from `C` §3.
5. `http` or `both`: write `src/auth.ts` (`H` §1), `src/app.ts` and `src/http.ts` (`H` §2), `test/http.test.ts` (`H` §3) and `test/config.test.ts` (`C` §3), and the `Dockerfile` and `.dockerignore` (`H` §4).
6. Write `scripts/check-test-count.js` and `.github/workflows/ci.yml` from `C` §4. Set the count to the project's test total (18 for `both`, 5 for `stdio`, 13 for `http`).
7. If OpenTelemetry was requested, follow "OpenTelemetry" below.
8. Standalone: `npm install` (exact pins), then Verify. Joining a host workspace: skip nested `npm install`; at the **host** run `npm install` then `npm ci -w <name>` (or `npm install -w <name>`) so one `package-lock.json` remains. Dockerfile context is the **host** when joined.

## OpenTelemetry (only when the user asks)

1. Install: `npm i -E @opentelemetry/api@1.10.0 @opentelemetry/sdk-node@0.301.2 @opentelemetry/sdk-trace@3.1.1 @opentelemetry/sdk-metrics@3.1.1 @opentelemetry/resources@3.1.1 @opentelemetry/semantic-conventions@1.45.0 @opentelemetry/exporter-trace-otlp-http@0.301.2 @opentelemetry/exporter-metrics-otlp-http@0.301.2 @opentelemetry/instrumentation-http@0.301.2 @opentelemetry/instrumentation-undici@0.35.1 import-in-the-middle@3.6.0 @fastify/otel@1.0.1`. Never install `@opentelemetry/instrumentation-fastify` (deprecated on npm).
2. Copy `src/register-hooks.ts` and `src/instrumentation.ts` verbatim from `.claude/skills/deployment-ci-cd/reference/node-ci-and-observability.md` §1, then run `npx prettier --write src`. Set `OTEL_SERVICE_NAME` (the fallback in that file is `orders-mcp`).
3. In `src/http.ts`, add `import { shutdownTelemetry } from './instrumentation.js';` and make telemetry the last shutdown step:

```typescript
    app
      .close()
      .then(shutdownTelemetry) // last: flushes spans recorded during shutdown
      .then(
        () => process.exit(0),
        (err: unknown) => {
          logger.error({ err }, 'http_shutdown_failed');
          process.exit(1);
        },
      );
```

4. Start with `node --import ./dist/instrumentation.js dist/http.js`, and in the Dockerfile use `CMD ["node", "--import", "./dist/instrumentation.js", "dist/http.js"]`.
5. Tool spans and metrics: `mcp-builder/reference/observability-tracing.md` §3. Outbound HTTP must use `fetch()` or a default `import http from 'node:http'`, because named imports get no client span under the sync hook. Metrics use the OTel API (prom-client is deprecated on npm).

Executed on Node 26.13.1 with a fake OTLP/JSON collector: one unauthenticated POST exported 5 spans, SIGTERM exited 0 after the flush, no DEP0205, `OTEL_SDK_DISABLED=true` exported nothing; all gates stayed at exit 0.

## Verify

Run each command on its own and read its own exit code:

```bash
npm run typecheck      # 0; a planted type error exits 2
npm run lint           # 0; a console.log in src/ exits 1 (no-console)
npm run format:check   # 0
npm run build          # 0; the stdio test spawns dist/stdio.js
npm run test:ci        # 0; 18 tests for both (stdio 5 + HTTP 13)
node scripts/check-test-count.js test-results.json 18   # 0; with 19 it exits 1
npm audit --audit-level=high
npm run inspect        # Inspector 2.16.0 CLI: tools/list over stdio
npx -y @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/call --tool-name notes_search --tool-arg query=release
```

HTTP smoke test:

1. Start the server: `MCP_RESOURCE=http://127.0.0.1:3000/mcp OAUTH_ISSUER=https://issuer.example OAUTH_JWKS_URI=https://issuer.example/jwks npm run start:http`.
2. `curl -s http://127.0.0.1:3000/health/live` must return 200.
3. An unauthenticated `POST /mcp` must return 401 with `WWW-Authenticate: Bearer … resource_metadata=`.
4. A missing `MCP_RESOURCE` must exit 1.

Container (`H` §4):

1. `docker build -t <name> .`
2. Run it with `--read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m`, the same env vars, `ALLOWED_HOSTS=<public hostname>,127.0.0.1,localhost` and `ALLOWED_ORIGINS=` (browser client hostnames, or empty to reject any Origin). Without both lists the container exits 1. Both take hostnames without port; Kubernetes probes need `httpHeaders: [{name: Host, value: localhost}]` (`H` §4).
3. It must report healthy, return 401 without a token, 403 for a foreign `Host` or `Origin`, and `docker stop` must exit 0.

Mutation checks that must turn the suite red:

- Delete the `allowed(...)` line in `src/tools.ts`: 2 tests fail.
- Return early from the `onRequest` bearer gate: 6 tests fail.
- Remove `process.exit(1)` after `config.allowlists_required` in `src/http.ts`: 2 tests fail.

Then run `/verify` (its MCP section does a real Client handshake) and dispatch `code-reviewer` + `security-reviewer` with `mcp-builder/reference/mcp-quality-standards.md` as the checklist. Report each step with its exit code. A step that could not run is BLOCKED or NOT RUN, never PASS.
