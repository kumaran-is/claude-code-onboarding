---
description: Binary build + test verification for every detected stack (Spring, Python, NestJS, Angular, React, Flutter) with each command's own exit code. Modes quick | full | pre-commit | pre-pr.
argument-hint: "[quick|full|pre-commit|pre-pr]"
allowed-tools: Bash, Read, Glob, Grep
---

# /verify — Binary Build + Test Verification

Runs the fastest possible verification for changed stacks. Returns binary PASS/FAIL with counts.

## Modes

| Mode | Runs |
|---|---|
| `/verify` (default: quick) | Compile + lint only. No test execution. Fastest feedback. |
| `/verify full` | Compile + lint + all tests + parity checks (env, l10n, deprecations, Alembic). Full confidence. |
| `/verify pre-commit` | Quick verify + check for TODO/FIXME/console.log in staged files. |
| `/verify pre-pr` | Full verify + security scan + coverage check. |

## Stack Detection + Commands (detected by file presence in the current directory tree)

### Spring Boot (`pom.xml` with spring-boot)
```bash
# quick
./mvnw compile -q > /tmp/mvn-compile.log 2>&1; echo "COMPILE EXIT:$?"; tail -10 /tmp/mvn-compile.log

# full
./mvnw test -q > /tmp/mvn-test.log 2>&1; echo "TEST EXIT:$?"; tail -10 /tmp/mvn-test.log

# pre-pr additions (needs the OWASP dependency-check plugin configured in pom.xml; otherwise BLOCKED)
./mvnw dependency-check:check -q > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"; grep -E "(CRITICAL|HIGH)" /tmp/mvn-dc.log
```

### Python (`pyproject.toml` or `requirements.txt`)

Each command's OWN exit code is captured (`cmd | tail; echo $?` reports `tail`'s status: `false | tail; echo $?` prints 0).

Toolchain = the project's own: the interpreter from `.python-version` / `requires-python` and the versions in `uv.lock`. Check the lock and sync with `--locked` FIRST, then run every tool with `uv run --no-sync`. A plain `uv run` re-locks and re-syncs silently, so a drifted `pyproject.toml` passes; in a project with no `.venv` it also creates one and may download a Python. A project without `uv.lock` (bare `requirements.txt`) is **BLOCKED** for this block: say so rather than running tools from whatever is on `PATH`.

```bash
# toolchain (every mode): record what ran, fail on a stale lock before anything can re-lock it
uv --version; uv lock --check > /tmp/lock.log 2>&1; echo "LOCK EXIT:$?"; tail -3 /tmp/lock.log   # 1 = pyproject and uv.lock disagree
uv sync --locked > /tmp/sync.log 2>&1; echo "SYNC EXIT:$?"; tail -3 /tmp/sync.log
uv run --no-sync python -VV; echo "PYTHON EXIT:$?"

# quick
uv run --no-sync ruff check . > /tmp/ruff.log 2>&1; echo "RUFF EXIT:$?"; tail -10 /tmp/ruff.log
uv run --no-sync ruff format --check . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
uv run --no-sync mypy > /tmp/mypy.log 2>&1; echo "MYPY EXIT:$?"; tail -10 /tmp/mypy.log   # targets from [tool.mypy] files; exit 2 "Missing target" = BLOCKED (configure it)

# full
uv run --no-sync pytest -q --junitxml=/tmp/junit.xml > /tmp/pytest.log 2>&1; echo "PYTEST EXIT:$?"; tail -5 /tmp/pytest.log   # exit 5 (no tests collected) = FAIL
uv run --no-sync python -c "import sys, xml.etree.ElementTree as E; s=[x for x in E.parse(sys.argv[1]).iter('testsuite')]; n=sum(int(x.get('tests',0))-int(x.get('skipped',0)) for x in s); print('EXECUTED', n); sys.exit(0 if n else 1)" /tmp/junit.xml; echo "EXECUTED EXIT:$?"   # all-skipped exits 0 in pytest

# pre-pr additions
uv export --locked --no-dev --no-hashes --no-emit-project -o /tmp/req.audit.txt > /tmp/export.log 2>&1; echo "EXPORT EXIT:$?"
uv run --no-sync pip-audit -r /tmp/req.audit.txt --no-deps --disable-pip > /tmp/audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -15 /tmp/audit.log
# migrations, when the project has Alembic: the round-trip gate in skills/python-dev/reference/alembic-migration-safety.md section 7, then drift
uv run --no-sync alembic check > /tmp/alembic-check.log 2>&1; echo "ALEMBIC CHECK EXIT:$?"; tail -3 /tmp/alembic-check.log   # non-zero = models changed without a revision
```

`pip-audit` has no severity column: gate on its exit code (0 = PASS, 1 = findings = FAIL unless every ID is listed with `--ignore-vuln <ID>` and a reason, 2 = tool/usage error = BLOCKED). It audits the exported lock, not the interpreter it runs in. `pip audit` is not a command. A tool missing from the dev group (`Failed to spawn: mypy`) is BLOCKED, not PASS. Security lint is ruff's `S` rules in `ruff check`; Bandit/Semgrep live in `/security-sast`. Details: `skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

Proven on 2026-11-23 with uv 0.13.9 and Python 3.14.10 on a `/scaffold-python-api` project (FastAPI 0.165.0, SQLAlchemy 2.1.9, PostgreSQL 18.7): clean → every line exit 0 (22 tests executed); `pyproject.toml` edited without `uv lock` → LOCK and SYNC exit 1 (a plain `uv run` would have re-locked it); a `str` passed to an `int` ORM column → MYPY exit 1; `print()` + an unused import → RUFF exit 1; an unformatted file → FORMAT exit 1; an auth bypass, a widened JWT algorithm list, a dropped owner filter, a 422 that echoes input → PYTEST exit 1; a model column with no revision → ALEMBIC CHECK exit 255.

### Node.js — NestJS, TypeScript Node services and MCP servers (`package.json` with `@nestjs/core`, `@modelcontextprotocol/*`, or a `tsconfig.json`)

Run this block once from the repo root with `MODE=quick`, `MODE=full` or `MODE=pre-pr` (it runs under `bash`, also from zsh). It finds every package root up to 4 levels deep and skips Angular, React, Vite, Next and React Native packages (the web block owns those). Tools are looked up in the package and its parents, so npm-workspaces hoisting is handled. One `PASS` / `FAIL` / `BLOCKED` / `NOT RUN` line per check, from the command's own exit code.

| Check | Command | Why not the obvious one |
|---|---|---|
| Type-check (quick+) | `tsc -p tsconfig.json --noEmit`; `tsc -b` for a solution config (`"files": []`) | The Nest CLI build config (`tsconfig.build.json`) excludes `**/*spec.ts` and `test/`: `npm run build` passes a type error in a spec |
| Lint (quick+) | `npm run lint`, else `eslint .` with an `eslint.config.*`, else `oxlint --deny-warnings src test` (`--type-aware` with `oxlint-tsgolint`) with an `.oxlintrc.json`; none → **NOT RUN** | |
| Unit (full+) | `vitest run` / `jest --ci` with a JSON report; PASS needs executed (passed + failed) > 0 | Vitest exits 0 when every test is skipped; `npm test` alone gives no count → **BLOCKED** |
| Build (full+) | `npm run build`; none → **NOT RUN** | |
| MCP server (full+, MCP packages) | real SDK client (the package's own `@modelcontextprotocol/client` v2 or `@modelcontextprotocol/sdk` v1): connect (an `initialize` handshake only on revisions ≤ 2025-11-25; 2026-07-28 removed it), negotiated spec revision, `tools/list` (all pages), per tool: name `[A-Za-z0-9_.-]{1,128}`, unique, description, `inputSchema`/`outputSchema` of `"type": "object"` that compile. Never calls a tool | Server from `bin`/`main` over stdio, or `MCP_SERVER_CMD="node dist/index.js"`, or `MCP_SERVER_URL=http://127.0.0.1:3000/mcp` (Streamable HTTP; nothing listening → **BLOCKED**). `MCP_MIN_PROTOCOL=2025-11-25` fails an older revision; `MCP_GATE_TIMEOUT_MS` (default 20000) |
| Audit (pre-pr) | `npm audit --audit-level=high`; no lockfile or registry unreachable → **BLOCKED** | |

```bash
MODE="${MODE:-quick}" bash <<'NODE_GATE'
# Node gate: NestJS, plain TypeScript Node services and MCP servers; nested roots included. MODE=quick|full|pre-pr.
set -u
MODE="${MODE:-quick}"; NF=0; NB=0; NN=0; NRAN=0; ROOTS=""; GATE_DIR=$(mktemp -d) # left for the OS temp cleaner
cat > "$GATE_DIR/mcp-gate.mjs" <<'MCP_GATE'
// MCP server gate: node mcp-gate.mjs <server-root>. Real SDK client, read-only (never calls tools).
// Server: MCP_SERVER_URL (Streamable HTTP) | MCP_SERVER_CMD (stdio, whitespace-split) | package.json bin/main via node.
// Prints "MCP <root> | <check>: PASS|FAIL|BLOCKED|NOT RUN (...)"; exit 1 on FAIL, 3 on BLOCKED only, 0 otherwise.
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.argv[2] ?? '.');
const results = [];
const report = (check, status, detail) => {
  results.push(status);
  process.stdout.write(`MCP ${root} | ${check}: ${status} (${detail})\n`);
};
const req = createRequire(join(root, 'package.json'));
const load = async (spec) => {
  try { return await import(pathToFileURL(req.resolve(spec)).href); } catch { return null; }
};
const finish = () => {
  process.exitCode = results.includes('FAIL') ? 1 : results.includes('BLOCKED') ? 3 : 0;
};

// The project's own client: SDK v2 split package first, then SDK v1.
let sdk = null;
const v2 = await load('@modelcontextprotocol/client');
if (v2?.Client) {
  const stdio = await load('@modelcontextprotocol/client/stdio');
  const ajv = await load('@modelcontextprotocol/client/validators/ajv');
  sdk = { line: 'v2', ...v2, StdioClientTransport: stdio?.StdioClientTransport, Validator: ajv?.AjvJsonSchemaValidator };
} else {
  const v1 = await load('@modelcontextprotocol/sdk/client/index.js');
  if (v1?.Client) {
    const types = await load('@modelcontextprotocol/sdk/types.js');
    const stdio = await load('@modelcontextprotocol/sdk/client/stdio.js');
    const http = await load('@modelcontextprotocol/sdk/client/streamableHttp.js');
    const ajv = await load('@modelcontextprotocol/sdk/validation/ajv');
    sdk = {
      line: 'v1', Client: v1.Client, LATEST_PROTOCOL_VERSION: types?.LATEST_PROTOCOL_VERSION,
      SUPPORTED_PROTOCOL_VERSIONS: types?.SUPPORTED_PROTOCOL_VERSIONS, StdioClientTransport: stdio?.StdioClientTransport,
      StreamableHTTPClientTransport: http?.StreamableHTTPClientTransport, Validator: ajv?.AjvJsonSchemaValidator,
    };
  }
}
if (!sdk?.StdioClientTransport || !sdk.Validator || !sdk.SUPPORTED_PROTOCOL_VERSIONS) {
  report('client', 'BLOCKED', 'no MCP client SDK resolvable from this root: npm i -D -E @modelcontextprotocol/client (or @modelcontextprotocol/sdk)');
  finish();
} else {
  await runGate(sdk);
  finish();
}

async function runGate(sdk) {
  let transport;
  let target;
  if (process.env.MCP_SERVER_URL) {
    transport = new sdk.StreamableHTTPClientTransport(new URL(process.env.MCP_SERVER_URL));
    target = 'Streamable HTTP';
  } else {
    let argv = process.env.MCP_SERVER_CMD ? process.env.MCP_SERVER_CMD.trim().split(/\s+/) : null;
    if (!argv) {
      const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
      const entry = typeof pkg.bin === 'string' ? pkg.bin : pkg.bin ? Object.values(pkg.bin)[0] : pkg.main;
      if (!entry) {
        report('connect', 'BLOCKED', 'no bin/main in package.json: set MCP_SERVER_CMD (stdio) or MCP_SERVER_URL (HTTP)');
        return;
      }
      if (!existsSync(join(root, entry))) {
        report('connect', 'BLOCKED', `entry ${entry} does not exist: build first`);
        return;
      }
      argv = [process.execPath, entry];
    }
    const env = Object.fromEntries(Object.entries(process.env).filter(([, v]) => v !== undefined));
    transport = new sdk.StdioClientTransport({ command: argv[0], args: argv.slice(1), cwd: root, env, stderr: 'pipe' });
    target = 'stdio';
  }
  const stderrTail = [];
  transport.stderr?.on('data', (chunk) => stderrTail.push(...String(chunk).split('\n').filter(Boolean)));
  // v2 clients default to the 2025 'legacy' handshake; 'auto' probes server/discover first, then falls back to initialize.
  const options = sdk.line === 'v2' ? { versionNegotiation: { mode: 'auto' } } : undefined;
  const client = new sdk.Client({ name: 'verify-mcp-gate', version: '1.0.0' }, options);
  const timeoutMs = Number(process.env.MCP_GATE_TIMEOUT_MS ?? 20000);
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${timeoutMs} ms`)), timeoutMs);
  });
  deadline.catch(() => undefined); // handled by the Promise.race calls; avoids an unhandled rejection between them
  try {
    await Promise.race([client.connect(transport), deadline]);
    const negotiated = client.getNegotiatedProtocolVersion?.() ?? transport.protocolVersion ?? sdk.LATEST_PROTOCOL_VERSION;
    const info = client.getServerVersion();
    report('connect', 'PASS', `${target}, server ${info?.name ?? '?'}@${info?.version ?? '?'}, client SDK ${sdk.line}`);
    const min = process.env.MCP_MIN_PROTOCOL;
    // v2 exports only the 2025-era list (SUPPORTED_PROTOCOL_VERSIONS, LATEST = 2025-11-25); 2026-07-28 is negotiated
    // through server/discover, so a completed v2 connect already proves the client supports the revision.
    if (sdk.line === 'v1' && !sdk.SUPPORTED_PROTOCOL_VERSIONS.includes(negotiated)) {
      report('spec version', 'FAIL', `negotiated ${negotiated} is not a revision this client supports`);
    } else if (min && negotiated < min) {
      report('spec version', 'FAIL', `negotiated ${negotiated} < MCP_MIN_PROTOCOL ${min}`);
    } else {
      report('spec version', 'PASS', `negotiated ${negotiated}`);
    }
    if (!client.getServerCapabilities()?.tools) {
      report('tools/list', 'NOT RUN', 'server does not declare the tools capability');
      return;
    }
    const tools = [];
    let cursor;
    do {
      const page = await Promise.race([client.listTools(cursor ? { cursor } : {}), deadline]);
      tools.push(...page.tools);
      cursor = page.nextCursor;
    } while (cursor);
    report('tools/list', tools.length > 0 ? 'PASS' : 'FAIL', `${tools.length} tool(s)`);
    const validator = new sdk.Validator();
    const problems = [];
    const seen = new Set();
    for (const tool of tools) {
      if (!/^[A-Za-z0-9_.-]{1,128}$/.test(tool.name)) problems.push(`${tool.name}: name outside [A-Za-z0-9_.-]{1,128}`);
      if (seen.has(tool.name)) problems.push(`${tool.name}: duplicate name`);
      seen.add(tool.name);
      if (!tool.description?.trim()) problems.push(`${tool.name}: empty description`);
      for (const key of ['inputSchema', 'outputSchema']) {
        const schema = tool[key];
        if (schema === undefined && key === 'outputSchema') continue;
        if (schema?.type !== 'object') { problems.push(`${tool.name}: ${key}.type is not "object"`); continue; }
        try { validator.getValidator(schema); } catch (err) { problems.push(`${tool.name}: ${key} does not compile: ${err.message}`); }
      }
    }
    report('tool schemas', problems.length ? 'FAIL' : 'PASS', problems.length ? problems.join('; ') : `${tools.length} schema set(s) compile, names valid`);
  } catch (err) {
    // v1: err.cause is the socket error; v2 'auto' wraps it once more (ERA_NEGOTIATION_FAILED -> fetch failed -> socket)
    const netCode = [err.cause?.code, err.cause?.cause?.code].find((c) => ['ECONNREFUSED', 'ENOTFOUND'].includes(c));
    if (process.env.MCP_SERVER_URL && netCode) {
      report('connect', 'BLOCKED', `nothing listening at MCP_SERVER_URL (${netCode}): start the server first`);
      return;
    }
    report('session', 'FAIL', `${err.message}${stderrTail.length ? ` | server stderr: ${(stderrTail.find((l) => /error/i.test(l)) ?? stderrTail.at(-1)).trim()}` : ''}`);
  } finally {
    clearTimeout(timer);
    await client.close().catch((err) => process.stderr.write(`close failed: ${err.message}\n`));
  }
}
MCP_GATE
pkg_has() { node -e 'const p=require(process.argv[1]);const s={...p.dependencies,...p.devDependencies};process.exit(process.argv.slice(2).some(n=>n in s)?0:1)' "$1/package.json" "${@:2}" 2>/dev/null; }
has_script() { node -e 'const p=require(process.argv[1]);process.exit(p.scripts&&p.scripts[process.argv[2]]?0:1)' "$1/package.json" "$2" 2>/dev/null; }
bin_up() { # $1 root, $2 bin -> path of node_modules/.bin/<bin> in root or a parent (npm workspaces hoist)
  local d; d=$(cd "$1" && pwd)
  while [ "$d" != "/" ]; do [ -x "$d/node_modules/.bin/$2" ] && { echo "$d/node_modules/.bin/$2"; return 0; }; d=$(dirname "$d"); done; return 1; }
say() { echo "NODE $1 | $2: $3"; }
check() { # root label cmd... -> PASS/FAIL from the command's OWN exit code; log tail only on failure
  local root="$1" label="$2" log="$GATE_DIR/log" rc; shift 2
  (cd "$root" && CI=true NO_COLOR=1 FORCE_COLOR=0 "$@") > "$log" 2>&1; rc=$?
  if [ "$rc" -eq 0 ]; then say "$root" "$label" "PASS (exit 0)"; NRAN=$((NRAN + 1))
  elif [ "$label" = "npm audit (high)" ] && grep -qE 'ENOLOCK|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|audit endpoint returned an error' "$log"; then
    say "$root" "$label" "BLOCKED (exit $rc: no lockfile or registry unreachable)"; tail -5 "$log"; NB=1
  else say "$root" "$label" "FAIL (exit $rc)"; tail -15 "$log"; NF=1; NRAN=$((NRAN + 1)); fi
  return "$rc"
}
not_run() { say "$1" "$2" "NOT RUN ($3)"; NN=$((NN + 1)); }
tests() { # root -> vitest/jest with a JSON report: PASS only when executed (passed + failed) > 0
  local root="$1" json="$GATE_DIR/tests.json" bin rc ran label
  : > "$json"
  if bin=$(bin_up "$root" vitest); then label="unit (vitest)"
    (cd "$root" && CI=true "$bin" run --reporter=default --reporter=json --outputFile="$json") > "$GATE_DIR/log" 2>&1; rc=$?
  elif bin=$(bin_up "$root" jest); then label="unit (jest)"
    (cd "$root" && CI=true "$bin" --ci --json --outputFile="$json") > "$GATE_DIR/log" 2>&1; rc=$?
  elif has_script "$root" test; then
    (cd "$root" && CI=true npm test) > "$GATE_DIR/log" 2>&1; rc=$?
    if [ "$rc" -ne 0 ]; then say "$root" "unit (npm test)" "FAIL (exit $rc)"; tail -15 "$GATE_DIR/log"; NF=1; NRAN=$((NRAN + 1))
    else say "$root" "unit (npm test)" "BLOCKED (exit 0 but the executed count is not measurable: use vitest/jest, or count by hand)"; NB=1; fi
    return
  else not_run "$root" unit "no vitest, jest or test script"; return; fi
  ran=$(node -e 'const r=require(process.argv[1]);console.log((r.numPassedTests||0)+(r.numFailedTests||0), r.numTotalTests||0, r.numPendingTests||0)' "$json" 2>/dev/null)
  set -- $ran
  if [ "$rc" -eq 0 ] && [ "${1:-0}" -gt 0 ]; then say "$root" "$label" "PASS (exit 0, executed $1 of $2, skipped ${3:-0})"; NRAN=$((NRAN + 1))
  elif [ "$rc" -eq 0 ]; then say "$root" "$label" "FAIL (exit 0 but executed ${1:-0} of ${2:-0}: all skipped or no report)"; NF=1; NRAN=$((NRAN + 1))
  else say "$root" "$label" "FAIL (exit $rc, executed ${1:-?} of ${2:-?})"; tail -15 "$GATE_DIR/log"; NF=1; NRAN=$((NRAN + 1)); fi
}
FOUND=$(find . -maxdepth 4 \( -name node_modules -o -name dist -o -name .git \) -prune -o -name package.json -print)
while IFS= read -r f; do
  [ -n "$f" ] || continue; d=$(dirname "$f")
  [ -f "$d/angular.json" ] && continue
  # web and mobile apps: other blocks. A NestJS 12 package pins vite for Vitest 5, so @nestjs/core wins over vite.
  pkg_has "$d" @nestjs/core || { pkg_has "$d" react @angular/core react-native vite next && continue; }
  if pkg_has "$d" @nestjs/core; then kind=nest
  elif pkg_has "$d" @modelcontextprotocol/sdk @modelcontextprotocol/server; then kind=mcp
  elif [ -f "$d/tsconfig.json" ]; then kind=node
  else continue; fi
  pkg_has "$d" @modelcontextprotocol/sdk @modelcontextprotocol/server && [ "$kind" = nest ] && kind=nest+mcp
  ROOTS="${ROOTS}${kind}:$d
"
done <<EOF_FOUND
$FOUND
EOF_FOUND
[ -n "$ROOTS" ] || echo "NODE: NOT APPLICABLE (no NestJS / TypeScript Node / MCP server package within 4 levels of $(pwd))"
while IFS= read -r entry <&3; do
  [ -n "$entry" ] || continue
  kind="${entry%%:*}"; root="${entry#*:}"; echo "NODE $root: $kind"
  if ! bin_up "$root" tsc >/dev/null && [ ! -d "$root/node_modules" ]; then say "$root" "all checks" "BLOCKED (no node_modules here or in a parent: npm ci)"; NB=1; continue; fi
  # 1. type-check: tsconfig.json covers specs and test/ (the Nest build config excludes them)
  if [ ! -f "$root/tsconfig.json" ]; then not_run "$root" typecheck "no tsconfig.json (JavaScript package)"
  elif ! tsc=$(bin_up "$root" tsc); then say "$root" typecheck "BLOCKED (no typescript in node_modules: npm ci)"; NB=1
  elif grep -qE '"files"[[:space:]]*:[[:space:]]*\[[[:space:]]*\]' "$root/tsconfig.json"; then check "$root" "typecheck (tsc -b, solution config)" "$tsc" -b
  else check "$root" "typecheck (tsc -p tsconfig.json --noEmit)" "$tsc" -p tsconfig.json --noEmit; fi
  # 2. lint: only a configured linter; absence is NOT RUN, never PASS
  if has_script "$root" lint; then check "$root" lint npm run lint
  elif ls "$root"/eslint.config.* >/dev/null 2>&1 && eslint=$(bin_up "$root" eslint); then check "$root" lint "$eslint" .
  elif [ -f "$root/.oxlintrc.json" ] && oxlint=$(bin_up "$root" oxlint); then # NestJS 12 default linter
    ox_dirs=""; for d in src test; do [ -d "$root/$d" ] && ox_dirs="$ox_dirs $d"; done # never ".": it lints node_modules
    if [ -z "$ox_dirs" ]; then not_run "$root" lint ".oxlintrc.json but no src/ or test/"
    elif bin_up "$root" tsgolint >/dev/null; then check "$root" "lint (oxlint --type-aware)" "$oxlint" --type-aware --deny-warnings $ox_dirs
    else check "$root" "lint (oxlint)" "$oxlint" --deny-warnings $ox_dirs; fi
  else not_run "$root" lint "no lint script, eslint.config.* or .oxlintrc.json"; fi
  [ "$MODE" = quick ] && continue
  tests "$root"
  if has_script "$root" build; then check "$root" build npm run build; else not_run "$root" build "no build script"; fi
  # MCP server: real SDK client over stdio (bin/main) or MCP_SERVER_URL / MCP_SERVER_CMD; never calls a tool
  case "$kind" in *mcp)
    node "$GATE_DIR/mcp-gate.mjs" "$root"; rc=$?
    case "$rc" in 0) NRAN=$((NRAN + 1)) ;; 3) NB=1 ;; *) NF=1; NRAN=$((NRAN + 1)) ;; esac ;;
  esac
  [ "$MODE" = pre-pr ] && check "$root" "npm audit (high)" npm audit --audit-level=high
done 3<<EOF_ROOTS
$ROOTS
EOF_ROOTS
if [ "$NF" -ne 0 ]; then v=FAIL; elif [ "$NB" -ne 0 ]; then v=BLOCKED; elif [ -z "$ROOTS" ]; then v="NOT APPLICABLE"; elif [ "$NRAN" -eq 0 ]; then v="NOT RUN"; else v=PASS; fi
echo "NODE VERDICT: $v; $NN check(s) NOT RUN (not passes: report each with its reason)"
[ "$v" = PASS ] || [ "$v" = "NOT APPLICABLE" ]
NODE_GATE
```

Proven on 2026-11-23 fixtures (TypeScript 5.9.3, NestJS 11.2.11, Vitest 5.1.1, Jest 30.5.2, ESLint 10.15.0, `@modelcontextprotocol/sdk` 1.32.2 and `@modelcontextprotocol/client` 2.4.0, Node 24.13.1): clean NestJS + MCP packages → PASS in `pre-pr`; a type error planted in a spec → typecheck FAIL while `npm run build` stays green; all tests `it.skip` → unit FAIL (Vitest exit 0, executed 0 of 2); `console.log` with `no-console` → lint FAIL; a tool named `get order!` with an empty description → tool schemas FAIL; a server that throws at boot, or hangs → FAIL with its stderr line / timeout; no `node_modules` or no TypeScript → BLOCKED; nothing listening at `MCP_SERVER_URL` → BLOCKED; the gate over Streamable HTTP → PASS. A Python (FastMCP) server is not detected by this block: `npx -y @modelcontextprotocol/inspector@2.16.0 --cli <server command> --method tools/list` exits 1 on a server that fails to start (verified against a Node stdio server only).

Re-proven on 2026-11-24 against a NestJS 12.6.0 ESM app (Node 26.13.1, TypeScript 6.0.3, Vitest 5.1.1, oxlint 1.95.0 via `npm run lint`): before the `@nestjs/core` precedence fix the gate reported NOT APPLICABLE with exit 0, because the app pins `vite` for Vitest and was skipped as a web app; after it, `full` and `pre-pr` → PASS (unit executed 9 of 9, audit exit 0), and a type error planted in a spec plus a `console.log` → typecheck FAIL (exit 2) and lint FAIL (exit 1), gate exit 1. The same app without a `lint` script: the `.oxlintrc.json` fallback ran `oxlint --type-aware --deny-warnings src test` → PASS, a planted `console.log` → lint FAIL (exit 1), no linter config → NOT RUN. With `@nestjs/mcp` 0.0.4 added it is `nest+mcp`: `full` without `MCP_SERVER_URL` → MCP BLOCKED (no `bin`/`main`); `pre-pr` with `MCP_SERVER_URL` at the running app → connect, spec version 2026-07-28, tools/list and tool schemas PASS.

### Web apps — Angular (`angular.json`) and React (`package.json` with `react` + `vite` / `react-scripts` / `next`)

Run this block once from the repo root with `MODE=quick`, `MODE=full` or `MODE=pre-pr`. It finds every app root up to 4 levels deep (`web/<app>/angular.json`, `apps/<app>/package.json`), so nested apps are never skipped, and prints one `PASS` / `FAIL` / `BLOCKED` / `NOT RUN` line per check from the command's own exit code. React Native and NestJS packages are excluded. Local binaries run through `npm exec --no --`, which uses the app's own `node_modules/.bin` and never downloads a package (npm 11 docs for `npm exec`: "When standard input is not a TTY or a CI environment is detected, `--yes` is assumed", so a bare `npx <typo>` in this gate would install from the registry). Nothing here needs `zone.js`: Angular 22 apps are zoneless by default. Angular checks follow the CLI-first rule (`.claude/rules/web-frontend.md`): lint, unit and build run through the workspace's own `ng`, never a `package.json` script or raw `eslint`; `tsc -p` is the one non-`ng` step, because `ng` has no type-check-only command and `ng build` does not compile `tsconfig.spec.json`.

| Check | Angular 22 | React (Vite / CRA / Next) |
|---|---|---|
| Type-check | `tsc -p tsconfig.app.json --noEmit` and `tsconfig.spec.json` (the root tsconfig is `"files": []`, so plain `tsc --noEmit` checks nothing). Templates are checked only by `ng build` / `ng test` | `tsc -b` when tsconfig.json has `references` (create-vite), else `tsc --noEmit` |
| Lint (quick+) | `ng lint` (the `lint` target in `angular.json`); none → **NOT RUN** (a new Angular 22 workspace has no linter until `ng add angular-eslint`) | `npm run lint` / `eslint.config.*`; none → **NOT RUN** |
| UI mode (quick+) | `angular-ui-mode.sh detect`: `package.json` `config.uiMode` matches the installed UI packages and the global stylesheet (`angular-spa/reference/ui-mode-selection.md`); a plain-CSS workspace passes as `none` | — |
| Unit (full+) | `ng test --watch=false` (`@angular/build:unit-test`: Vitest + jsdom by default; no Karma `--browsers` flag) | `vitest run`, else `npm test` |
| Build (full+) | `ng build` (production by default) | `npm run build` |
| E2E (full+) | `playwright test --fail-on-flaky-tests` when `playwright.config.*` exists; PASS needs exit 0 **and** executed > 0 (an all-skipped run exits 0); missing browser/server → **BLOCKED** | same |
| Audit (pre-pr) | `npm audit --audit-level=high` | same |

```bash
# Web gate: Angular + React (Vite / CRA / Next) apps, nested roots included. MODE=quick|full|pre-pr.
MODE="${MODE:-quick}"; WEB_FAIL=0; WEB_BLOCKED=0; WEB_NOTRUN=0; WEB_RAN=0; WEB_ROOTS=""; TOP=$(pwd)
pkg_has() { node -e 'const p=require(process.argv[1]);const s={...p.dependencies,...p.devDependencies};process.exit(process.argv.slice(2).some(n=>n in s)?0:1)' "$1/package.json" "${@:2}" 2>/dev/null; }
has_script() { node -e 'const p=require(process.argv[1]);process.exit(p.scripts&&p.scripts[process.argv[2]]?0:1)' "$1/package.json" "$2" 2>/dev/null; }
web_check() { # root label cmd... -> PASS/FAIL from the command's OWN exit code; log tail only on failure
  local root="$1" label="$2" log rc; shift 2; log=$(mktemp)
  (cd "$root" && CI=true NO_COLOR=1 FORCE_COLOR=0 "$@") > "$log" 2>&1; rc=$?
  if [ "$rc" -eq 0 ]; then echo "WEB $root | $label: PASS (exit 0)"; WEB_RAN=$((WEB_RAN + 1))
  else echo "WEB $root | $label: FAIL (exit $rc)"; tail -15 "$log"; WEB_FAIL=1; WEB_RAN=$((WEB_RAN + 1)); fi
  rm -f "$log"
}
not_run() { echo "WEB $1 | $2: NOT RUN ($3)"; WEB_NOTRUN=$((WEB_NOTRUN + 1)); }
web_e2e() { # root -> Playwright Test; PASS = exit 0 AND executed > 0; flaky fails; missing browser/server = BLOCKED
  local root="$1" log json rc ran; log=$(mktemp); json=$(mktemp)
  (cd "$root" && CI=true NO_COLOR=1 FORCE_COLOR=0 PLAYWRIGHT_JSON_OUTPUT_FILE="$json" npm exec --no -- playwright test --reporter=line,json --fail-on-flaky-tests) > "$log" 2>&1; rc=$?
  ran=$(node -e 'const s=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).stats;console.log(s.expected+s.unexpected+s.flaky)' "$json" 2>/dev/null)
  if [ "$rc" -eq 0 ] && [ "${ran:-0}" -gt 0 ]; then echo "WEB $root | e2e: PASS (exit 0, executed $ran)"; WEB_RAN=$((WEB_RAN + 1))
  elif [ "$rc" -eq 0 ]; then echo "WEB $root | e2e: FAIL (exit 0 but executed ${ran:-0}: all skipped or filtered out)"; WEB_FAIL=1; WEB_RAN=$((WEB_RAN + 1))
  elif grep -qE "Executable doesn't exist|browserType\.launch|ECONNREFUSED" "$log"; then echo "WEB $root | e2e: BLOCKED (exit $rc: browser or server missing)"; tail -5 "$log"; WEB_BLOCKED=1
  else echo "WEB $root | e2e: FAIL (exit $rc, executed ${ran:-?}; flaky counts as failure)"; tail -15 "$log"; WEB_FAIL=1; WEB_RAN=$((WEB_RAN + 1)); fi
  rm -f "$log" "$json"
}
has_cfg() { local e; for e in js mjs cjs ts mts cts; do [ -f "$1/$2.$e" ] && return 0; done; return 1; } # real config names only: eslint.config.js.bak must not count
FOUND=$(find . -maxdepth 4 \( -name node_modules -o -name dist -o -name .git -o -name .angular \) -prune -o \( -name angular.json -o -name package.json \) -print)
while IFS= read -r f; do
  [ -n "$f" ] || continue; d=$(dirname "$f")
  case "$f" in
    */angular.json) WEB_ROOTS="${WEB_ROOTS}angular:$d
" ;;
    */package.json) [ -f "$d/angular.json" ] && continue
      pkg_has "$d" react && pkg_has "$d" vite react-scripts next && ! pkg_has "$d" react-native @angular/core && WEB_ROOTS="${WEB_ROOTS}react:$d
" ;;
  esac
done <<EOF_FOUND
$FOUND
EOF_FOUND
[ -n "$WEB_ROOTS" ] || echo "WEB: NOT APPLICABLE (no Angular/React app within 4 levels of $(pwd))"
while IFS= read -r entry <&3; do
  [ -n "$entry" ] || continue
  kind="${entry%%:*}"; root="${entry#*:}"
  echo "WEB $root: $kind"
  if [ ! -d "$root/node_modules" ]; then echo "WEB $root | all checks: BLOCKED (no node_modules: run npm ci in $root)"; WEB_BLOCKED=1; continue; fi
  # 1. type-check (the root tsconfig of Angular 22 / create-vite has "files": [] -> plain `tsc --noEmit` there checks nothing)
  if [ ! -f "$root/tsconfig.json" ]; then not_run "$root" typecheck "no tsconfig.json (JavaScript-only app)"
  elif [ ! -x "$root/node_modules/.bin/tsc" ]; then echo "WEB $root | typecheck: BLOCKED (tsconfig.json present but no local typescript: npm ci)"; WEB_BLOCKED=1
  elif [ "$kind" = angular ]; then
    for cfg in tsconfig.app.json tsconfig.spec.json; do
      [ -f "$root/$cfg" ] && web_check "$root" "typecheck $cfg" npm exec --no -- tsc -p "$cfg" --noEmit
    done
  elif grep -q '"references"' "$root/tsconfig.json" 2>/dev/null; then web_check "$root" "typecheck" npm exec --no -- tsc -b
  else web_check "$root" "typecheck" npm exec --no -- tsc --noEmit; fi
  # 2. lint: only a configured linter; absence is NOT RUN, never PASS
  # Angular is CLI-first (.claude/rules/web-frontend.md): lint, test and build run through the workspace's own `ng`.
  if [ "$kind" = angular ]; then
    if grep -q '"lint"' "$root/angular.json"; then web_check "$root" lint npm exec --no -- ng lint
    else not_run "$root" lint "no lint target in angular.json (ng add angular-eslint)"; fi
  elif has_script "$root" lint; then web_check "$root" lint npm run lint
  elif has_cfg "$root" eslint.config; then web_check "$root" lint npm exec --no -- eslint .
  else not_run "$root" lint "no lint script or eslint.config.*"; fi
  # 2b. Angular UI mode: config.uiMode matches the installed UI packages and the global stylesheet
  if [ "$kind" = angular ]; then
    if [ -f "$TOP/.claude/scripts/angular-ui-mode.sh" ]; then web_check "$root" "ui mode (angular-ui-mode.sh detect)" bash "$TOP/.claude/scripts/angular-ui-mode.sh" detect .
    else not_run "$root" "ui mode" "no .claude/scripts/angular-ui-mode.sh at the repo root"; fi
  fi
  [ "$MODE" = quick ] && continue
  # 3. unit tests
  if [ "$kind" = angular ]; then
    if grep -q '"@angular/build:unit-test"' "$root/angular.json"; then web_check "$root" "unit (ng test, Vitest)" npm exec --no -- ng test --watch=false
    elif grep -q '"test"' "$root/angular.json"; then web_check "$root" "unit (ng test, configured builder)" npm exec --no -- ng test --watch=false
    else not_run "$root" unit "no test target in angular.json"; fi
  elif [ -x "$root/node_modules/.bin/vitest" ]; then web_check "$root" "unit (vitest)" npm exec --no -- vitest run
  elif has_script "$root" test; then web_check "$root" "unit (npm test)" npm test
  else not_run "$root" unit "no vitest and no test script"; fi
  # 4. production build (Angular: also the only template type-check)
  if [ "$kind" = angular ]; then web_check "$root" build npm exec --no -- ng build
  elif has_script "$root" build; then web_check "$root" build npm run build
  else not_run "$root" build "no build script"; fi
  # 5. E2E (Playwright), when configured
  if has_cfg "$root" playwright.config; then web_e2e "$root"
  else not_run "$root" e2e "no playwright.config.*"; fi
  [ "$MODE" = pre-pr ] && web_check "$root" "npm audit (high)" npm audit --audit-level=high
done 3<<EOF_ROOTS
$WEB_ROOTS
EOF_ROOTS
if [ "$WEB_FAIL" -ne 0 ]; then v=FAIL; elif [ "$WEB_BLOCKED" -ne 0 ]; then v=BLOCKED; elif [ -z "$WEB_ROOTS" ]; then v="NOT APPLICABLE"; elif [ "$WEB_RAN" -eq 0 ]; then v="NOT RUN"; else v=PASS; fi
echo "WEB VERDICT: $v; $WEB_NOTRUN check(s) NOT RUN (not passes: report each with its reason)"
[ "$v" = PASS ] || [ "$v" = "NOT APPLICABLE" ]
```

Proven on 2026-11-23, `MODE=full`, Node 26.13.1, against an Angular 22.3.0 workspace (`ng new` 22.3 output: zoneless, `@angular/build:unit-test`, TypeScript 6.0.3, Vitest 5.1.1, jsdom 31.0.1, angular-eslint 22.8.0) and a create-vite 9.3.4 React SPA (React 19.3.1, Vite 8.3.8, TypeScript 6.0.3, Vitest 5.1.1, ESLint 10.15.0, Playwright 1.65.1): clean apps → PASS (e2e ran 8 Playwright tests in Chromium); planted `const n: number = "x"` → typecheck + build FAIL in both (plus `ng test`, which compiles the app, and the React Playwright run, whose `webServer` builds it); an unknown template binding (NG8002) passes `tsc` and FAILs `ng test` and `ng build`; one changed assertion → unit FAIL only (Angular 1 of 2, React 4 of 4 failed); no lint setup → NOT RUN with verdict PASS (Angular: no `lint` target in `angular.json` → NOT RUN even with an `eslint.config.js` and a `lint` script present, because Angular lint runs only as `ng lint`); a planted `any` → `ng lint` FAIL; an `eslint.config.js.bak` alone is not a config (it used to make ESLint exit 2); no `node_modules` → BLOCKED. The previous line `npm run build -- --configuration=production --silent 2>&1 | tail -5; echo "EXIT:$?"` printed `EXIT:0` on a broken build (`--silent` is also rejected by `ng build`). In a multi-project Angular workspace, run `ng test <project>` / `ng build <project>` per project (UNVERIFIED — check `ng test --help` before relying on the no-argument form). Web UI tool choice: `.claude/rules/testing-tool-selection.md`.

### Flutter (`pubspec.yaml` with flutter:)

Capture each command's OWN exit code (a pipe into `tail` reports `tail`'s status, not the tool's):

```bash
# codegen first when pubspec lists build_runner (generated files are usually gitignored)
grep -q 'build_runner:' pubspec.yaml && { dart run build_runner build > /tmp/codegen.log 2>&1; echo "CODEGEN EXIT:$?"; tail -5 /tmp/codegen.log; }

# quick — static checks (every Dart change)
dart format --output=none --set-exit-if-changed . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
flutter analyze --no-pub > /tmp/analyze.log 2>&1; echo "ANALYZE EXIT:$?"; tail -5 /tmp/analyze.log

# full — tests (per package root in a multi-package repo; mixing roots fabricates failures)
flutter test > /tmp/test.log 2>&1; echo "TEST EXIT:$?"; tail -5 /tmp/test.log
```

Count `error`, `warning` AND `info` findings from `flutter analyze`: on Flutter 3.50.1 it exits 1 on a single info, e.g. the
`deprecated_member_use` info for `package:flutter/material.dart` (deprecated since 3.47; import `package:material_ui/material_ui.dart`).
Proven 2026-11-23 on Flutter 3.50.1: a clean sample app → format, analyze, codegen and 9 tests exit 0; a deleted
`*.mocks.dart` → analyze exit 1 until codegen re-runs; one unformatted file, one deprecated import, one broken assertion → exit 1 each.

**Proportional validation.** Run what the change can affect — not everything, not less. The full change-type table is in
[flutter-testing-traps.md §10](../skills/flutter-mobile/reference/flutter-testing-traps.md); summary:

| Change | Minimum before reporting PASS |
|--------|-------------------------------|
| Dart source (logic, state) | format + analyze + the tests that reach the changed code |
| Widget / screen / navigation | the above + a widget test per state; a routing/boot test for navigation |
| Offline / sync | the above + the sync/outbox tests; device-only checks on a simulator are BLOCKED, not PASS |
| Native / platform config (Gradle, Info.plist, manifests, entitlements) | analyze + a build for each affected platform |
| Generated code / l10n inputs | regenerate first, then format + analyze + tests |
| CI, hooks, scripts | run the script itself (self-test or dry run); app tests are NOT APPLICABLE |
| Docs / comments only | app checks are NOT APPLICABLE; confirm no code file changed |

**UI/E2E on a Flutter Android/iOS target** uses Maestro only (`.claude/rules/testing-tool-selection.md`); if Maestro or a device is missing the check is `BLOCKED`, never a browser substitute.

### AI assets and evals (golden data, `prompts/`, governance records or AI code present; otherwise NOT APPLICABLE)

```bash
python3 .claude/scripts/check-ai-assets.py --root . --json ai-assets.json > ai-assets.log 2>&1; echo "AI ASSETS EXIT:$?"; tail -20 ai-assets.log
# full+ (Python AI services): the deterministic R1 tier only, scripted fake model, never a live provider
uv run --no-sync pytest -m r1 -q --junit-xml=reports/pytest-r1.xml > r1.log 2>&1; echo "R1 EXIT:$?"; tail -5 r1.log
```

`check-ai-assets.py`: exit 0 = PASS, REVIEW (list each item for the human) or NOT_APPLICABLE · 1 = a BLOCK finding (missing dataset manifest, invalid manifest, prompt card or governance record, secret in a prompt, golden, notebook or eval-report file, prompt label `latest`) → FAIL; REVIEW includes unpinned model ids and LiteLLM fallback defaults · 3 = BLOCKED (a delegate validator is missing or crashed). ADVISORY lines are pattern-only and never count as pass or fail. R1: no `r1` marker → NOT RUN; executed count 0 → FAIL. Judged (R2), red-team and live-provider suites are NOT RUN here (`eval-guide/reference/ci-tiers.md`).

### Parity checks (`full` and `pre-pr`; any stack)

Four stdlib checkers (Python 3.10+) catch drift that compiles and tests clean: a config key read in code or compose but missing from `.env.example` (`check_env_parity.py`), an ARB locale missing template keys or placeholders (`check_l10n_parity.py`), a `REMOVE-BY: YYYY-MM-DD` deprecation past its date (`check_deprecations.py`), a model table no Alembic revision creates (`check_alembic_models.py`). Each runs per root it finds (`.env.example`, `l10n.yaml`, `alembic.ini`, up to 4 levels deep); exit 2 means no inputs and is NOT APPLICABLE, never PASS.

```bash
# Parity gate: env/config, l10n, deprecations, Alembic. MODE=full|pre-pr. Stdlib checkers; exit 2 = no inputs.
PCK=".claude/scripts"; P_FAIL=0; P_BLOCKED=0; P_RAN=0
parity() { # label cmd... -> PASS / WARN / FAIL / NOT APPLICABLE from the checker's OWN exit code
  local label="$1" out rc; shift
  out=$("$@" 2>&1); rc=$?
  case "$rc" in
    0) if printf '%s\n' "$out" | grep -q '^WARN'; then echo "PARITY $label: PASS with warnings"; printf '%s\n' "$out" | grep '^WARN' | head -5
       else echo "PARITY $label: PASS"; fi; P_RAN=$((P_RAN + 1)) ;;
    2) echo "PARITY $label: NOT APPLICABLE ($(printf '%s\n' "$out" | tail -1))" ;;
    *) echo "PARITY $label: FAIL (exit $rc)"; printf '%s\n' "$out" | grep -E '^(FAIL|WARN)' | head -10; P_FAIL=1; P_RAN=$((P_RAN + 1)) ;;
  esac
}
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
  echo "PARITY: BLOCKED (the checkers need python3 >= 3.10; found $(python3 -V 2>&1))"; P_BLOCKED=1
else
  ROOTS=$(find . -maxdepth 4 \( -name node_modules -o -name .git -o -name .venv -o -name build -o -name dist \) -prune -o \
          \( -name .env.example -o -name l10n.yaml -o -name alembic.ini \) -print)
  [ -n "$(printf '%s' "$ROOTS" | grep '/.env.example$')" ] || echo "PARITY env: NOT APPLICABLE (no .env.example)"
  [ -n "$(printf '%s' "$ROOTS" | grep '/l10n.yaml$')" ] || echo "PARITY l10n: NOT APPLICABLE (no l10n.yaml)"
  [ -n "$(printf '%s' "$ROOTS" | grep '/alembic.ini$')" ] || echo "PARITY alembic: NOT APPLICABLE (no alembic.ini)"
  while IFS= read -r f; do
    [ -n "$f" ] || continue; d=$(dirname "$f")
    case "$f" in
      */.env.example) parity "env $d" python3 "$PCK/check_env_parity.py" "$d" ;;
      */l10n.yaml) dir=$(sed -n 's/^arb-dir:[[:space:]]*//p' "$f" | tr -d "\"'"); parity "l10n $d" python3 "$PCK/check_l10n_parity.py" "$d/${dir:-lib/l10n}" ;;
      */alembic.ini) parity "alembic $d" python3 "$PCK/check_alembic_models.py" "$d" ;;
    esac
  done <<EOF_PARITY
$ROOTS
EOF_PARITY
  parity "deprecations" python3 "$PCK/check_deprecations.py" .
fi
if [ "$P_FAIL" -ne 0 ]; then v=FAIL; elif [ "$P_BLOCKED" -ne 0 ]; then v=BLOCKED; elif [ "$P_RAN" -eq 0 ]; then v="NOT APPLICABLE"; else v=PASS; fi
echo "PARITY VERDICT: $v"
[ "$v" = PASS ] || [ "$v" = "NOT APPLICABLE" ]
```

Proven 2026-11-24 on fixtures: a clean API + Flutter tree → 4 PASS; an `os.environ` key missing from `.env.example`, a missing ARB key, an unmigrated model and an overdue `REMOVE-BY` → 4 FAIL with file:line; a repo with none of the inputs and no `REMOVE-BY` marker → NOT APPLICABLE (the deprecations checker exits 2 when no marker exists, so it never counts as ran); python3 3.9 → BLOCKED.

**Status vocabulary** (per check, never blended): `PASS` ran and succeeded · `FAIL` ran and failed · `BLOCKED` could not run (say why: no device, tool missing, backend down) · `NOT RUN` skipped by choice (say why) · `NOT APPLICABLE` the change cannot affect it. Only `PASS` counts as a pass.

## Output Format

```
## Verification — {mode} — {date}

| Stack | Compile | Tests | Status |
|-------|---------|-------|--------|
| Spring Boot | ✅ EXIT 0 | ✅ 47 passed | PASS |
| Python | ✅ EXIT 0 | ❌ 2 failed | FAIL |
| NestJS | ✅ EXIT 0 | ✅ 83 passed | PASS |
| Angular `web/admin` | ✅ EXIT 0 (lint NOT RUN: no linter) | ✅ 12 passed | PASS |
| React `apps/site` | ✅ EXIT 0 | ❌ 1 failed | FAIL |
| Flutter | ✅ EXIT 0 | ✅ 31 passed | PASS |
| AI assets | ✅ EXIT 0 (2 REVIEW listed) | ✅ R1 24 passed | PASS |

### FAIL Details
Python — 2 failures:
- test_create_user_duplicate: AssertionError at tests/test_user.py:45
- test_payment_timeout: TimeoutError at tests/test_payment.py:78

## Final Verdict: ❌ FAIL (2 of 6 stacks failing)
```

**Evidence stamp:** when the verdict is PASS (every applicable check PASS, none BLOCKED), record it against the current content: `python3 .claude/scripts/review_state.py stamp write verify --mode <quick|pre-commit|full|pre-pr> --note "<stacks and executed counts>"`. Only a `full` or `pre-pr` stamp authorizes `gh pr create` / `gh pr merge`: quick and pre-commit run no tests, so the PR gate reports them INSUFFICIENT. Executed Playwright or Maestro runs that passed stamp `ui-web` / `ui-mobile` the same way. Never stamp a FAIL, BLOCKED or NOT RUN verdict. The stamp goes stale as soon as a file in its scope changes; `gh pr create` and `gh pr merge` check it (`verification-loop.md` §4, enforcement kit).

**Binary rule:** If ANY stack fails → overall verdict is FAIL. No partial credit. `/verify` reports build/test PASS/FAIL only; review-finding severities (CRITICAL → BLOCK, HIGH → NEEDS_REVIEW) follow the Review Severity Policy in `.claude/rules/verification-and-reporting.md`.

## pre-commit Checks

```bash
# Check staged files for forbidden patterns
git diff --cached --name-only | xargs grep -n "TODO\|FIXME\|console\.log\|print(" 2>/dev/null

# Staged skill files: the same lint CI runs (frontmatter, triggers, body size, references)
if git diff --cached --name-only | grep -q '^\.claude/skills/'; then
  bash .claude/scripts/lint-skills.sh > /tmp/lint-skills.log 2>&1; echo "LINT-SKILLS EXIT:$?"; tail -5 /tmp/lint-skills.log
fi
```

Pattern matches are not blocking (human decides) but must be acknowledged. `LINT-SKILLS EXIT` non-zero is a FAIL: fix it before committing (CI runs the same script).

## Rules

- Run ALL detected stacks — never skip a stack silently
- Report exact exit codes — not "it looks like it passed"; use the command's own exit code, never a pipe's
- A scan that reports ZERO findings needs a positive control: a known-bad input the same scan must flag
- A test run that EXECUTED zero tests is not a PASS (all-skipped exits 0): report collected / skipped / executed
- A diff-aware check that is green on UNCOMMITTED work is vacuous (it sees no changed files) — commit first or say "vacuous"
- If a stack build tool is missing (`mvnw`, `flutter`, `node_modules`, etc.) → report BLOCKED with "install X" — never PASS
- A check with nothing configured (no lint script, no E2E config) is NOT RUN with its reason, never PASS
- Do NOT interpret test failure messages — show raw output, human diagnoses

## Related

Use instead when: `/ship` — release readiness (runs this gate plus release builds and the security Lock Document check); `/test-coverage` — coverage percentages per stack; `/validate-changes` — advisory LLM judgement of the staged diff (never a substitute for this gate); `/status-check` — feature-level WORKS / BROKEN report backed by this evidence.
