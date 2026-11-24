#!/usr/bin/env bash
# post-edit-ts-log-pii-advisory.sh — PostToolUse (Write|Edit), TypeScript/JavaScript MCP server files + .mcp.json, check-only.
# Three advisories (always exit 0; findings go to Claude as hookSpecificOutput.additionalContext):
#
# 1. Log PII (TypeScript twin of post-edit-python-log-pii-advisory.sh). Flags exception TEXT reaching structured
#    log metadata or a trace span on the same line:
#      metadata: { ... String(err) / err.message / error.message / err.stack ... }
#      span.setAttribute(...) / setAttributes(...) with the same values
#    Error messages echo request data (validation errors echo the body, provider errors echo the prompt), so they
#    leak PII into logs and traces. Log the error class (`err.name`, a code) and correlation ids.
#    Scope: *.ts under a `mcp`, `mcp-server` or `*-mcp/src` directory, and `src/server.ts`. Mark: `log-pii: ok <reason>`.
# 2. MCP SDK v2 shapes. Scope: any *.ts/*.mts/*.cts/*.js/*.mjs/*.cjs that imports `@modelcontextprotocol/...`:
#      - `@modelcontextprotocol/sdk` (v1, maintenance only) imported in a project whose nearest package.json depends
#        on the v2 packages `@modelcontextprotocol/server` or `/client`;
#      - `<x>.tool(`: removed from McpServer in v2 (`registerTool`), deprecated in v1;
#      - `SSEServerTransport`: the deprecated HTTP+SSE transport (v2 does not export it; use Streamable HTTP);
#      - `console.log/info/debug/dir/table(` or `process.stdout.write(` when the project's src/ uses the stdio
#        transport: stdout carries the JSON-RPC stream, so any other byte corrupts the session (logs go to stderr).
#    Mark an intentional line with `mcp-lint: ok <reason>`. Comment lines are skipped.
# 3. `.mcp.json` hygiene right after an edit: credentials in args/env/headers/url and unpinned npx/uvx packages,
#    via `session-mcp-governance.sh --hygiene` (one detector, two triggers; names, never values).
# Tests are skipped. Fails open without jq (said once). Line-based POSIX ERE: a value built on one line and used on
# another is not seen; this is advisory, the compile (`tsc`) and `/verify` stay the gates.
# Test: bash .claude/hooks/post-edit-ts-log-pii-advisory.sh --selftest
set -uo pipefail

SINK='(metadata[[:space:]]*:|[.]setAttributes?[[:space:]]*\()'
TEXT='(String\([[:space:]]*(e|err|error|exc|ex)[[:space:]]*\)|(^|[^[:alnum:]_.])(e|err|error|exc|ex)\.(message|stack)([^[:alnum:]_]|$)|`[^`]*\$\{[[:space:]]*(err|error|e)[[:space:]]*\}[^`]*`)'

in_scope() {
  case "$1" in
    *.spec.ts|*.test.ts|*/test/*|*/tests/*|*/__tests__/*|*/node_modules/*|*/dist/*|*.d.ts) return 1 ;;
    */mcp/*.ts|*/mcp-server/*.ts|*-mcp/src/*.ts|*/src/server.ts|src/server.ts) return 0 ;;
  esac
  return 1
}

scan() { # $1 file -> "LINE: text" per finding
  grep -nE -e "$SINK" "$1" 2>/dev/null | grep -E -e "$TEXT" | grep -v 'log-pii: ok' | cut -c1-160
}

MCP_IMPORT='(from|import|require)[[:space:]]*[(]?[[:space:]]*['"'"'"]@modelcontextprotocol/'
STDIO_USE='@modelcontextprotocol/(server/stdio|sdk/server/stdio)|StdioServerTransport'
STDOUT_WRITE='(^|[^[:alnum:]_.])console[.](log|info|debug|dir|table)[[:space:]]*[(]|process[.]stdout[.]write[[:space:]]*[(]'

mcp_in_scope() { # $1 file: JS/TS source (not a test) that imports an MCP SDK package
  case "$1" in
    *.spec.*|*.test.*|*/test/*|*/tests/*|*/__tests__/*|*/node_modules/*|*/dist/*|*.d.ts|*.d.mts|*.d.cts) return 1 ;;
    *.ts|*.mts|*.cts|*.js|*.mjs|*.cjs) grep -qE -e "$MCP_IMPORT" "$1" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

code_lines() { # $1 file, $2 ERE -> "LINE: text" for matching non-comment, unmarked lines
  grep -nE -e "$2" "$1" 2>/dev/null | grep -vE '^[0-9]+:[[:space:]]*(//|/[*]|[*])' | grep -v 'mcp-lint: ok' | cut -c1-160
}

mcp_scan() { # $1 file -> findings text ("" = clean)
  local f="$1" d pkg="" root="" src out="" hits
  d=$(dirname "$f")
  while [ -n "$d" ] && [ "$d" != "/" ]; do [ -f "$d/package.json" ] && { root="$d"; pkg="$d/package.json"; break; }; d=$(dirname "$d"); done
  if [ -n "$pkg" ] && grep -qE '"@modelcontextprotocol/(server|client)"[[:space:]]*:' "$pkg"; then
    hits=$(code_lines "$f" '@modelcontextprotocol/sdk([/"'"'"']|$)')
    [ -n "$hits" ] && out="${out}- v1 SDK import in a v2 project (package.json depends on @modelcontextprotocol/server|client): import from @modelcontextprotocol/server, /client, /node or /fastify instead:
$hits
"
  fi
  hits=$(code_lines "$f" '[[:alnum:]_)][.]tool[[:space:]]*[(]')
  [ -n "$hits" ] && out="${out}- \`.tool(\`: removed from McpServer in SDK v2 (deprecated in v1); use registerTool(name, { description, inputSchema, outputSchema?, annotations? }, handler):
$hits
"
  hits=$(code_lines "$f" 'SSEServerTransport')
  [ -n "$hits" ] && out="${out}- SSEServerTransport is the deprecated HTTP+SSE transport (not exported by SDK v2): use Streamable HTTP:
$hits
"
  src="${root:-$(dirname "$f")}/src"; [ -d "$src" ] || src="$f"
  if grep -qE -e "$STDIO_USE" "$f" 2>/dev/null || grep -rlE --include='*.ts' --include='*.mts' --include='*.js' --include='*.mjs' -e "$STDIO_USE" "$src" >/dev/null 2>&1; then
    hits=$(code_lines "$f" "$STDOUT_WRITE")
    [ -n "$hits" ] && out="${out}- stdout write in a stdio MCP server: stdout carries only JSON-RPC, so this corrupts the session. Log to stderr (pino destination 2, console.error):
$hits
"
  fi
  printf '%s' "$out"
}

run_hook() {
  local input file hits marker msg="" gov hyg rc
  input=$(cat)
  if ! command -v jq >/dev/null 2>&1; then
    marker="${TMPDIR:-/tmp}/claude-ts-log-pii-nojq"
    [ -f "$marker" ] || { : > "$marker" 2>/dev/null; echo "post-edit-ts-log-pii-advisory: jq not found; check disabled." >&2; }
    return 0
  fi
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || return 0
  [ -n "$file" ] && [ -f "$file" ] || return 0
  if [ "$(basename "$file")" = ".mcp.json" ]; then
    gov="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/session-mcp-governance.sh"
    hyg=$("$BASH" "$gov" --hygiene "$file" 2>&1); rc=$?
    if [ "$rc" -ne 0 ]; then msg="MCP config advisory ($file): ${hyg:-hygiene check exit $rc}"
    elif [ -n "$hyg" ]; then msg="MCP config advisory ($file): pass secrets only as env entries that reference \${VAR} (never args: visible in the process list) and pin packages exactly (npx -y <pkg>@<x.y.z>, uvx --from <pkg>==<x.y.z>). Values are not shown:
$hyg"; fi
  else
    if in_scope "$file"; then
      hits=$(scan "$file")
      [ -n "$hits" ] && msg="log-PII advisory ($file): error text reaches log metadata or a span attribute. Error messages echo request data. Log the error class (err.name or a code) and ids instead, or mark the line \`log-pii: ok <reason>\`:
$hits"
    fi
    if mcp_in_scope "$file"; then
      hits=$(mcp_scan "$file")
      [ -n "$hits" ] && msg="${msg:+$msg

}MCP SDK advisory ($file) — mark an intentional line \`mcp-lint: ok <reason>\`:
$hits"
    fi
  fi
  [ -n "$msg" ] || return 0
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
}

selftest() {
  local self fail=0 tmp out f
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/src/mcp"
  probe() { jq -n --arg f "$1" '{tool_name:"Edit",tool_input:{file_path:$f}}' | "$BASH" "$self" 2>&1; }
  expect() { # $1 label, $2 file content, $3 path, $4 needle ("" = silent)
    printf '%s\n' "$2" > "$3"; out=$(probe "$3")
    if [ -z "$4" ]; then
      if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got $out)"; fail=1; fi
    elif printf '%s' "$out" | jq -e --arg n "$4" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"
    else echo "  FAIL $1 (got $out)"; fail=1; fi
  }
  f="$tmp/src/mcp/tools.ts"
  expect "positive: metadata: { error: String(err) }" "logger.error('tool failed', { metadata: { error: String(err) } });" "$f" "String(err)"
  expect "positive: span.setAttribute with err.message" "span.setAttribute('error.detail', err.message);" "$f" "err.message"
  expect "negative: metadata: { errorType: err.name }" "logger.error('tool failed', { metadata: { errorType: err.name, requestId } });" "$f" ""
  expect "negative: marked line" "logger.warn('x', { metadata: { e: String(err) } }); // log-pii: ok static startup error" "$f" ""
  expect "negative: out of scope (not an MCP file)" "logger.error('x', { metadata: { error: String(err) } });" "$tmp/src/app.service.ts" ""
  mkdir -p "$tmp/src/mcp/__tests__"
  expect "negative: tests skipped" "logger.error('x', { metadata: { error: String(err) } });" "$tmp/src/mcp/__tests__/tools.spec.ts" ""

  # --- MCP SDK v2 shapes: a v2 project (package.json depends on @modelcontextprotocol/server) using stdio.
  local v2="$tmp/v2srv" v1="$tmp/v1srv" imp sdk
  imp="import { McpServer } from '@modelcontextprotocol/server';"
  sdk="@modelcontextprotocol/""sdk" # split: this hook's own source must not look like a v1 import
  mkdir -p "$v2/src/tools" "$v2/src/__tests__" "$v1/src" "$tmp/http/src"
  printf '{ "type": "module", "dependencies": { "@modelcontextprotocol/server": "2.4.0" } }\n' > "$v2/package.json"
  printf "import { StdioServerTransport } from '@modelcontextprotocol/server/stdio';\n" > "$v2/src/stdio.ts"
  expect "positive: v1 SDK import in a v2 project" "$imp
import { Client } from '$sdk/client/index.js';" "$v2/src/tools/a.ts" "v1 SDK import in a v2 project"
  expect "positive: server.tool( (removed in v2)" "$imp
server.tool('echo', schema, handler);" "$v2/src/tools/a.ts" "removed from McpServer"
  expect "positive: SSEServerTransport" "$imp
const t = new SSEServerTransport('/messages', res);" "$v2/src/tools/a.ts" "deprecated HTTP+SSE"
  expect "positive: console.log in a stdio server module (stdio entry is another file)" "$imp
console.log('ready');" "$v2/src/tools/a.ts" "stdout write in a stdio MCP server"
  expect "positive: process.stdout.write in a stdio server" "$imp
process.stdout.write('x');" "$v2/src/tools/a.ts" "corrupts the session"
  expect "negative: v2 registerTool + console.error + comments + marked line are silent" "$imp
server.registerTool('echo', { description: 'Echo', inputSchema: z.object({ t: z.string() }) }, h);
console.error('ready'); logger.info({ tool: 'echo' }, 'ok');
// server.tool( and SSEServerTransport are v1 shapes; console.log goes to stdout
const dbg = () => console.log('x'); // mcp-lint: ok dev-only CLI flag, never under stdio" "$v2/src/tools/a.ts" ""
  expect "negative: MCP test files skipped" "$imp
server.tool('x', s, h); console.log('t');" "$v2/src/__tests__/a.test.ts" ""
  expect "negative: file without an MCP import is ignored" "console.log('x'); router.tool('x');" "$v2/src/tools/util.ts" ""
  # Prose that NAMES the v1 shapes (a Markdown "Do not" line in MCP setup docs): only JS/TS source is scanned.
  expect "negative: Markdown prose naming v1 shapes in a v2 project is silent" "**Do not** start new code on the v1 package (\`$sdk\`, \`new Server(...)\` + \`setRequestHandler(ListToolsRequestSchema, ...)\`, \`server.tool(...)\`, \`SSEServerTransport\`): v1 is in maintenance.
Migrating means replacing \`server.tool(\` and \`SSEServerTransport\` and \`$sdk/server/mcp.js\`; console.log breaks stdio.
import { McpServer } from '@modelcontextprotocol/server';" "$v2/mcp-server-setup.md" ""
  printf '{ "dependencies": { "%s": "1.32.2" } }\n' "$sdk" > "$v1/package.json"
  expect "negative: sdk import in a v1-only project is not the v2-mix finding" "import { McpServer } from '$sdk/server/mcp.js';" "$v1/src/a.ts" ""
  printf '{ "dependencies": { "@modelcontextprotocol/node": "2.1.2" } }\n' > "$tmp/http/package.json"
  expect "negative: console.log in an HTTP-only server is not a stdio finding" "$imp
console.log('listening');" "$tmp/http/src/server.ts" ""

  # --- .mcp.json edit: delegated to session-mcp-governance.sh --hygiene (same detector as SessionStart).
  local cfg="$tmp/proj/.mcp.json" tok
  tok="--api""-key"
  mkdir -p "$tmp/proj"
  jq -n --arg f "$tok" '{mcpServers:{pay:{command:"npx",args:["-y","@acme/pay-mcp@latest",($f + "=${PAY_KEY}")]}}}' > "$cfg"
  out=$(probe "$cfg")
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | (contains("pay — --api-key in args") and contains("unpinned package"))' >/dev/null 2>&1; then echo "  ok   positive: .mcp.json edit -> credential-in-args + unpinned reported"
  else echo "  FAIL .mcp.json positive (got $out)"; fail=1; fi
  jq -n '{mcpServers:{pay:{command:"npx",args:["-y","@acme/pay-mcp@3.4.1"],env:{PAY_KEY:"${PAY_KEY}"}}}}' > "$cfg"
  out=$(probe "$cfg")
  if [ -z "$out" ]; then echo "  ok   negative: clean .mcp.json edit is silent"; else echo "  FAIL clean .mcp.json (got $out)"; fail=1; fi
  printf '{ broken' > "$cfg"; out=$(probe "$cfg")
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("NOT checked")' >/dev/null 2>&1; then echo "  ok   fail-loud: invalid .mcp.json reported as NOT checked"; else echo "  FAIL invalid .mcp.json (got $out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
