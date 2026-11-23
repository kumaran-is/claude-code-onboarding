#!/usr/bin/env bash
# post-edit-ts-log-pii-advisory.sh — PostToolUse (Write|Edit), TypeScript MCP server files, check-only.
# TypeScript twin of post-edit-python-log-pii-advisory.sh.
#
# Flags exception TEXT reaching structured log metadata or a trace span on the same line:
#   metadata: { ... String(err) / err.message / error.message / err.stack ... }
#   span.setAttribute(...) / setAttributes(...) with the same values
# Error messages echo request data (validation errors echo the body, provider errors echo the prompt),
# so they leak PII into logs and traces. Log the error class (`err.name`, a code) and correlation ids.
# Scope: *.ts under a `mcp`, `mcp-server` or `*-mcp/src` directory, and `src/server.ts`; tests skipped.
# Advisory: always exit 0; findings go to Claude as hookSpecificOutput.additionalContext. Mark an
# intentional line with `log-pii: ok <reason>`. Fails open without jq (said once).
# Line-based POSIX ERE: a value built on one line and logged on another is not seen.
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

run_hook() {
  local input file hits marker
  input=$(cat)
  if ! command -v jq >/dev/null 2>&1; then
    marker="${TMPDIR:-/tmp}/claude-ts-log-pii-nojq"
    [ -f "$marker" ] || { : > "$marker" 2>/dev/null; echo "post-edit-ts-log-pii-advisory: jq not found; check disabled." >&2; }
    return 0
  fi
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || return 0
  [ -n "$file" ] && [ -f "$file" ] && in_scope "$file" || return 0
  hits=$(scan "$file")
  [ -n "$hits" ] || return 0
  jq -n --arg f "$file" --arg h "$hits" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:
    ("log-PII advisory (" + $f + "): error text reaches log metadata or a span attribute. Error messages echo request data. Log the error class (err.name or a code) and ids instead, or mark the line `log-pii: ok <reason>`:\n" + $h)}}'
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
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
