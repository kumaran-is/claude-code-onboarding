# MCP Server Scaffold Templates: Core

Verbatim files for `/scaffold-mcp-server`: project config, the shared tool registry, the stdio entry and its test, and CI. The HTTP transport, auth, container and OpenTelemetry are in `scaffold-templates-http-ops.md`. Replace `notes-mcp`, `notes_search` and `SAMPLE_NOTES` with the user's names. Verified 2026-11-23 against Node 26.13.1, TypeScript 6.0.3, `@modelcontextprotocol/server`/`client` 2.4.0, zod 4.6.7, pino 10.4.0, vitest 5.1.1, ESLint 10.15.0 + typescript-eslint 8.74.0: the files in both template files were extracted into an empty directory and every `/scaffold-mcp-server` Verify step ran with exit 0 (18 tests).

## 1. Project files

**`package.json`**: serves both transports. For a stdio-only server, drop `@modelcontextprotocol/fastify`, `@modelcontextprotocol/node`, `fastify`, `jose` and `start:http`.

```json
{
  "name": "notes-mcp",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=26.13.1"
  },
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "typecheck": "tsc -p tsconfig.json",
    "lint": "eslint . --max-warnings=0",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "test:ci": "vitest run --reporter=default --reporter=json --outputFile=test-results.json",
    "test:coverage": "vitest run --coverage",
    "start:stdio": "node dist/stdio.js",
    "start:http": "node dist/http.js",
    "inspect": "npx -y @modelcontextprotocol/inspector@2.16.0 --cli node dist/stdio.js --method tools/list"
  },
  "dependencies": {
    "@modelcontextprotocol/fastify": "2.0.1",
    "@modelcontextprotocol/node": "2.1.2",
    "@modelcontextprotocol/server": "2.4.0",
    "fastify": "5.12.8",
    "jose": "6.2.18",
    "pino": "10.4.0",
    "zod": "4.6.7"
  },
  "devDependencies": {
    "@eslint/js": "10.0.1",
    "@modelcontextprotocol/client": "2.4.0",
    "@types/node": "26.6.6",
    "@vitest/coverage-v8": "5.1.1",
    "eslint": "10.15.0",
    "eslint-config-prettier": "10.1.8",
    "globals": "17.14.0",
    "prettier": "3.10.1",
    "typescript": "6.0.3",
    "typescript-eslint": "8.74.0",
    "vitest": "5.1.1"
  }
}
```

**`tsconfig.json`** (TypeScript 6.0 defaults `types` to `[]`; without `"types": ["node"]`, `process` fails with TS2591)

```json
{
  "compilerOptions": {
    "target": "es2024",
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "types": ["node"],
    "noEmit": true,
    "rootDir": "."
  },
  "include": ["src", "test", "vitest.config.ts"]
}
```

**`tsconfig.build.json`**

```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "noEmit": false, "rootDir": "src", "outDir": "dist", "sourceMap": true },
  "include": ["src"]
}
```

**`eslint.config.js`** (`no-console: error` is the gate for stdout pollution)

```javascript
// @ts-check
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig(
  { ignores: ['dist/', 'coverage/'] },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: globals.node,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: { 'no-console': 'error' }, // stdout belongs to the stdio transport; log with pino to stderr
  },
  { files: ['**/*.js'], extends: [tseslint.configs.disableTypeChecked] },
  prettier,
);
```

**`vitest.config.ts`**

```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
    testTimeout: 15_000,
    coverage: { provider: 'v8', include: ['src/**/*.ts'], reporter: ['text', 'json-summary'] },
  },
});
```

**`.prettierrc.json`**

```json
{ "singleQuote": true, "printWidth": 120 }
```

**`.prettierignore`**

```text
dist/
coverage/
package-lock.json
test-results.json
```

**`.gitignore`**

```text
node_modules/
dist/
coverage/
.env
*.pem
*.key
.DS_Store
test-results.json
```

**`.nvmrc`**

```text
26.13.1
```

## 2. Shared tool registry

**`src/logger.ts`**

```typescript
import { pino } from 'pino';

// fd 2: on stdio, stdout carries only JSON-RPC. Never log tokens or tool arguments.
export const logger = pino({ level: process.env['LOG_LEVEL'] ?? 'info' }, pino.destination(2));
```

**`src/notes.ts`** (sample data: replace with the real source, injected through `ToolDeps` so tests use a fixture)

```typescript
/** Replace with your data source; inject it through ToolDeps so tests can use a fixture. */
export const SAMPLE_NOTES = [
  { id: 'n1', title: 'Release checklist' },
  { id: 'n2', title: 'Incident review template' },
] as const;
```

**`src/tools.ts`**: One `registerTools` serves every transport. The allowlist check runs before every handler body; a tool without an entry in `TOOL_SCOPES` is denied to everyone.

```typescript
import type { CallToolResult, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod';
import { logger } from './logger.js';

/** The verified caller. Identity comes only from the token (HTTP) or the process owner (stdio), never from tool arguments. */
export interface Principal {
  subject: string;
  scopes: ReadonlySet<string>;
}

/** Per-tool allowlist: the scope a caller needs. A tool missing here is denied to everyone. */
export const TOOL_SCOPES: Readonly<Record<string, string>> = { notes_search: 'notes:read' };

export interface ToolDeps {
  /** Resolves the verified caller for this request; undefined = unauthenticated (deny). */
  principal: () => Principal | undefined;
  notes: ReadonlyArray<{ id: string; title: string }>;
}

const denied = (tool: string): CallToolResult => ({
  isError: true,
  content: [{ type: 'text', text: JSON.stringify({ code: 'TOOL_NOT_ALLOWED', tool }) }],
});

/** Allowlist check that runs BEFORE every handler body. */
function allowed(tool: string, deps: ToolDeps): Principal | undefined {
  const caller = deps.principal();
  const scope = TOOL_SCOPES[tool];
  const ok = caller !== undefined && scope !== undefined && caller.scopes.has(scope);
  logger.info({ tool, sub: caller?.subject, decision: ok ? 'allow' : 'deny' }, 'audit.tool_call');
  return ok ? caller : undefined;
}

const Note = z.object({ id: z.string(), title: z.string() });

/** One registry for every transport (stdio and Streamable HTTP). */
export function registerTools(server: McpServer, deps: ToolDeps): McpServer {
  server.registerTool(
    'notes_search',
    {
      title: 'Search notes',
      description:
        'Find notes whose title contains the query (case-insensitive). Returns at most `limit` notes. Read-only.',
      inputSchema: z
        .object({ query: z.string().min(1).max(200), limit: z.number().int().min(1).max(50).default(10) })
        .strict(),
      outputSchema: z.object({ notes: z.array(Note) }),
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    },
    ({ query, limit }) => {
      if (!allowed('notes_search', deps)) return denied('notes_search');
      const q = query.toLowerCase();
      const output = { notes: deps.notes.filter((n) => n.title.toLowerCase().includes(q)).slice(0, limit) };
      return { content: [{ type: 'text', text: JSON.stringify(output) }], structuredContent: output };
    },
  );
  return server;
}
```

## 3. stdio entry and tests

**`src/stdio.ts`**: The stdio principal is the local user who launched the process; scopes come from `MCP_STDIO_SCOPES`. `test/config.test.ts` belongs to the HTTP transport but lives here for size.

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { logger } from './logger.js';
import { registerTools, TOOL_SCOPES } from './tools.js';
import { SAMPLE_NOTES } from './notes.js';

// stdio runs as the local user who launched it: that user is the principal. Scopes come from configuration,
// default all tools in TOOL_SCOPES; narrow with MCP_STDIO_SCOPES="notes:read".
const scopes = new Set(process.env['MCP_STDIO_SCOPES']?.split(',').filter(Boolean) ?? Object.values(TOOL_SCOPES));
const principal = { subject: `local:${process.env['USER'] ?? 'unknown'}`, scopes };

const handle = serveStdio(() =>
  registerTools(new McpServer({ name: 'notes-mcp', version: '0.1.0' }), {
    principal: () => principal,
    notes: SAMPLE_NOTES,
  }),
);
logger.info('listening on stdio');

for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  process.once(signal, () => {
    handle.close().then(
      () => process.exit(0),
      (err: unknown) => {
        logger.error({ err }, 'stdio_shutdown_failed');
        process.exit(1);
      },
    );
  });
}
```

**`test/config.test.ts`** (HTTP only: three startup refusals, each must exit 1 with its own reason)

```typescript
import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

// Runs the BUILT entry (npm run build first). Each config must be refused at startup with exit 1.
describe('startup config (dist/http.js)', () => {
  const base = {
    PATH: process.env['PATH'] ?? '',
    MCP_RESOURCE: 'https://mcp.example.com/mcp',
    OAUTH_ISSUER: 'https://issuer.example',
    OAUTH_JWKS_URI: 'https://issuer.example/jwks',
  };
  it.each([
    ['0.0.0.0 without allowlists', { HOST: '0.0.0.0' }, 'config.allowlists_required'],
    [
      '0.0.0.0 without ALLOWED_ORIGINS',
      { HOST: '0.0.0.0', ALLOWED_HOSTS: 'mcp.example.com' },
      'config.allowlists_required',
    ],
    [
      'http issuer in production',
      { NODE_ENV: 'production', OAUTH_ISSUER: 'http://127.0.0.1:9/issuer' },
      'Invalid protocol',
    ],
  ])('%s: exit 1', (_label, extra, reason) => {
    const run = spawnSync(process.execPath, ['dist/http.js'], { env: { ...base, ...extra }, timeout: 10_000 });
    expect(run.status).toBe(1);
    const stderr = run.stderr.toString();
    expect(stderr).toContain(reason); // the intended guard, not an unrelated crash
    expect(stderr).not.toMatch(/EADDRINUSE|"msg":"listening"/); // it must stop BEFORE listen
  });
});
```

**`test/stdio.test.ts`** (drives the BUILT server exactly as a host launches it: run `npm run build` first)

```typescript
import { Client } from '@modelcontextprotocol/client';
import { getDefaultEnvironment, StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { afterEach, describe, expect, it } from 'vitest';
import { TOOL_SCOPES } from '../src/tools.js';

const open: Client[] = [];
afterEach(async () => {
  await Promise.all(open.splice(0).map((c) => c.close()));
});

// Runs the BUILT server (npm run build first), exactly as an MCP host launches it.
async function connect(env: Record<string, string> = {}): Promise<Client> {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ['dist/stdio.js'],
    env: { ...getDefaultEnvironment(), ...env },
    stderr: 'pipe',
  });
  const client = new Client({ name: 'stdio-test', version: '1.0.0' }, { versionNegotiation: { mode: 'auto' } });
  await client.connect(transport);
  open.push(client);
  return client;
}

describe('stdio transport (real Client)', () => {
  it('negotiates 2026-07-28 and lists the tool with schemas and annotations', async () => {
    const client = await connect();
    expect(client.getNegotiatedProtocolVersion()).toBe('2026-07-28');
    const { tools } = await client.listTools();
    const tool = tools.find((t) => t.name === 'notes_search');
    expect(tool?.annotations).toMatchObject({ readOnlyHint: true });
    expect(tool?.outputSchema?.['required']).toEqual(['notes']);
  });

  it('every registered tool has a TOOL_SCOPES entry (otherwise it is denied to everyone)', async () => {
    const client = await connect();
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name).filter((name) => !(name in TOOL_SCOPES))).toEqual([]);
  });

  it('returns structuredContent', async () => {
    const client = await connect();
    const res = await client.callTool({ name: 'notes_search', arguments: { query: 'release' } });
    expect(res.isError).toBeFalsy();
    expect(res.structuredContent).toEqual({ notes: [{ id: 'n1', title: 'Release checklist' }] });
  });

  it('rejects invalid input before the handler runs', async () => {
    const client = await connect();
    const res = await client.callTool({ name: 'notes_search', arguments: { query: '' } });
    expect(res.isError).toBe(true);
    expect(JSON.stringify(res.content)).toContain('Input validation error');
  });

  it('denies a tool outside the configured scopes', async () => {
    const client = await connect({ MCP_STDIO_SCOPES: 'other:read' });
    const res = await client.callTool({ name: 'notes_search', arguments: { query: 'release' } });
    expect(res.isError).toBe(true);
    expect(JSON.stringify(res.content)).toContain('TOOL_NOT_ALLOWED');
  });
});
```

## 4. CI

**`scripts/check-test-count.js`** (from `deployment-ci-cd/reference/node-ci-and-observability.md` §4. Kept as `.js` so ESLint's untyped `**/*.js` block covers it; a `.mjs` copy fails lint and Prettier)

```javascript
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

**`.github/workflows/ci.yml`** (action SHAs and pin policy: `node-ci-and-observability.md` §4. Set the count to the number of tests the project has. Stdio-only projects drop the `image` job)

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
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run format:check
      - run: npm run build # the stdio tests spawn dist/stdio.js
      - run: npm run test:ci
      - name: Executed-test-count gate (0 collected or any skipped = red)
        run: node scripts/check-test-count.js test-results.json 18
      - run: npm audit --audit-level=high
      - run: npm audit signatures
      - name: Lockfile unchanged by the job
        run: git diff --exit-code -- package-lock.json

  image:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - run: docker build -t mcp-server:ci .
```
