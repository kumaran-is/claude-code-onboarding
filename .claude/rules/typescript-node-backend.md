---
paths:
  - "**/*.controller.ts"
  - "**/src/app.module.ts"
  - "**/src/modules/**/*.ts"
  - "**/test/**/*.e2e-spec.ts"
  - "**/nest-cli.json"
  - "**/prisma/schema.prisma"
  - "**/mcp/**/*.ts"
  - "**/*-mcp/src/**/*.ts"
  - "**/mcp-server/**/*.ts"
  - "**/src/server.ts"
---

# TypeScript / Node.js backend guardrails (NestJS, plain Node, MCP servers)

Path-scoped: loads for NestJS, Node service and MCP server files only. Globs avoid `**/*.service.ts`, `**/*.module.ts`, `**/src/main.ts` and `tsconfig*.json`, which Angular (`src/app/**`) and React apps also have; a NestJS app without `src/modules/` still loads this rule through its controllers, `src/app.module.ts` or `nest-cli.json`. Depth: `.claude/skills/typescript-expert/`, `.claude/skills/nestjs-api/` (NestJS is optional: plain Node services follow typescript-expert), `.claude/skills/mcp-builder/`. Pinned stack: CLAUDE.md.

**Verification that can fail**
- Type-check with `tsc -p tsconfig.json --noEmit`. The Nest CLI build config (`tsconfig.build.json`) excludes `**/*spec.ts` and `test/`, so `npm run build` passes a type error in a spec; a solution config (`"files": []`) needs `-p` per reference or `tsc -b`.
- A test run counts only when executed tests > 0: Vitest exits 0 when every test is skipped, Jest exits 1 when no test file matches. Never add `--passWithNoTests` to a gate.
- Use `/verify` (Node/NestJS and MCP server blocks) and `/ship`; each check reports PASS / FAIL / BLOCKED / NOT RUN from its own exit code.

**Code**
- No `as any`, no `: any` parameters, no swallowed `catch`: log with context, then rethrow or return a typed error. Validate every external input (HTTP body, env, tool arguments) at the boundary with a schema (class-validator DTOs or zod).
- No `console.log` in production code: NestJS `Logger` or the service logger (pino). Config and secrets come from validated env, never from literals.

**MCP servers** (new servers: `/scaffold-mcp-server`; Node 26 LTS, TypeScript 6.0.3, SDK v2)
- New code imports the v2 packages (`@modelcontextprotocol/server`, `/client`, `/node`, `/fastify`), never `@modelcontextprotocol/sdk` (v1, maintenance only). Register tools with `registerTool(name, { description, inputSchema, outputSchema?, annotations? }, handler)`: v2's `McpServer` has no `tool()` (compile error TS2339) and v1 marks it `@deprecated`. Remote servers use Streamable HTTP; HTTP+SSE (`SSEServerTransport`) is deprecated and not exported by v2.
- stdio servers MUST NOT write anything but MCP messages to stdout: logs go to stderr (pino `destination(2)`, `console.error`). ESLint `no-console: error` is the gate. `post-edit-ts-log-pii-advisory.sh` reports v1 imports in a v2 project, `.tool(`, `SSEServerTransport` and stdout writes in stdio servers right after an edit.
- TypeScript 6.0 defaults `types` to `[]`: set `"types": ["node"]` or `process`/`Buffer` fail with TS2591.
- Tool names match `[A-Za-z0-9_.-]{1,128}`, every tool has a description, and `inputSchema` is a JSON Schema object (`"type": "object"`). Tools are read-only unless the human approved a side effect; annotations are hints, not authorization.
- In `.mcp.json`, pin packages exactly (`npx -y <pkg>@<x.y.z>`, `uvx --from <pkg>==<x.y.z>`) and pass secrets only as `env` entries that reference `${VAR}`: an argument is visible in the process list. `session-mcp-governance.sh` reports both at session start, and again right after any `.mcp.json` edit.
- The spec revision a server negotiates is reported by `/verify`; revision 2026-07-28 removes the `initialize` handshake. SDK v2 (server/client 2.4.0) supports it; its `Client` negotiates the legacy era unless `versionNegotiation` is `{ mode: 'auto' }` or pinned. Check `SUPPORTED_PROTOCOL_VERSIONS` before claiming support for any other SDK.
