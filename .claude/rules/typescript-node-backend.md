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

**MCP servers**
- Register tools with `registerTool` (`server.tool()` is `@deprecated` in `@modelcontextprotocol/sdk` 1.x). Remote servers use Streamable HTTP; HTTP+SSE is the deprecated transport.
- stdio servers MUST NOT write anything but MCP messages to stdout: logs go to stderr.
- Tool names match `[A-Za-z0-9_.-]{1,128}`, every tool has a description, and `inputSchema` is a JSON Schema object (`"type": "object"`). Tools are read-only unless the human approved a side effect; annotations are hints, not authorization.
- In `.mcp.json`, pin packages exactly (`npx -y <pkg>@<x.y.z>`, `uvx --from <pkg>==<x.y.z>`) and pass secrets only as `env` entries that reference `${VAR}`: an argument is visible in the process list. `session-mcp-governance.sh` reports both.
- The spec revision a server negotiates is reported by `/verify`; revision 2026-07-28 removes the `initialize` handshake. Check the SDK's `SUPPORTED_PROTOCOL_VERSIONS` before claiming support for it (UNVERIFIED for any SDK not run in this repo).
