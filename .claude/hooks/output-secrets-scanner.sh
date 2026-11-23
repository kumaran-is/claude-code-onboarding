#!/usr/bin/env bash
# PostToolUse (Bash|Read|WebFetch): scan what Claude READS BACK (command output, file reads, web
# responses) for credentials. Advisory: always exit 0. The model is told (additionalContext) not to
# repeat the value; the user sees a stderr note; an audit line goes to .claude/secrets-detected.log
# (gitignored). The value itself is never printed or logged.
#
# Token shapes come from post-edit-secrets-scan.sh --scan-file (the single pattern table). Extra
# output-only shapes checked here: JWT, redis/mysql URLs with a password, generic NAME=value secrets.
# Matching reads from a file or here-string, never `echo "$content" | grep -q` (under pipefail a large
# output with an early match reported "no match" via SIGPIPE).
# The audit context never includes the Bash command text or a URL query string: those can hold the
# secret itself.
# Test: bash .claude/hooks/output-secrets-scanner.sh --selftest
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCANNER="$HOOK_DIR/post-edit-secrets-scan.sh"

detect() { # $1 file holding the output -> prints a label, returns 0 on a hit
  local file="$1" label db_re
  if [ -f "$SCANNER" ] && label=$("$BASH" "$SCANNER" --scan-file "$file"); then printf '%s' "$label"; return 0; fi
  if grep -qE -e 'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}' "$file"; then printf 'JWT token (eyJ...)'; return 0; fi
  db_re='redis''://:[^@[:space:]]{6,}@[a-zA-Z0-9._-]+|mysql''://[^:[:space:]]{1,64}:[^@[:space:]]{6,}@[a-zA-Z0-9._-]+'
  if grep -qE -e "$db_re" "$file"; then printf 'Database connection string with embedded credentials'; return 0; fi
  if grep -qiE -e '(PASSWORD|PASSWD|SECRET|API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PRIVATE_KEY)[[:space:]]*[=:][[:space:]]*[a-zA-Z0-9+/_!@#%-]{16,}' "$file"; then
    printf 'Hardcoded secret in environment variable or config'; return 0
  fi
  return 1
}

run_hook() {
  local input tool_context reason tmp log_dir
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  tmp=$(mktemp) || return 0
  # tool_response may be a string or an object; normalise to text in a file (no SIGPIPE, no size limit)
  printf '%s' "$input" | jq -r '
    if (.tool_response | type) == "string" then .tool_response
    elif .tool_response.output? then .tool_response.output
    elif .tool_response.content? then (.tool_response.content | if type == "string" then . else tostring end)
    elif .tool_response.stdout? then ((.tool_response.stdout // "") + "\n" + (.tool_response.stderr // ""))
    else (.tool_response | tostring) end // ""' > "$tmp" 2>/dev/null
  if [ "$(wc -c < "$tmp" | tr -d ' ')" -lt 20 ] || ! reason=$(detect "$tmp"); then rm -f "$tmp"; return 0; fi
  rm -f "$tmp"
  tool_context=$(printf '%s' "$input" | jq -r '
    if .tool_name == "Bash" then "a Bash command"
    elif .tool_name == "Read" then "Read " + (.tool_input.file_path // "?")
    elif .tool_name == "WebFetch" then "WebFetch " + ((.tool_input.url // "?") | sub("[?#].*$"; ""))
    else (.tool_name // "a tool") end' 2>/dev/null | head -c 160) || tool_context="a tool"
  {
    echo ""
    echo "SECRET DETECTED in tool output — $reason (from $tool_context)."
    echo "Move the credential to .env (gitignored) or a secrets manager; do not repeat it."
  } >&2
  jq -n --arg m "A credential-like value (${reason}) appeared in the output of ${tool_context}. Do not repeat, quote, or reference the value in responses, files or commits; refer to it by name only, and suggest moving it to an environment variable or secrets manager." \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  log_dir="${CLAUDE_PROJECT_DIR:-}"
  [ -n "$log_dir" ] && [ -d "$log_dir/.claude" ] &&
    printf '[%s] DETECTED: %s | Tool: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" "$tool_context" >> "$log_dir/.claude/secrets-detected.log" 2>/dev/null
  return 0
}

selftest() {
  local self fail=0 tmp out p_aws p_jwt big
  self="$HOOK_DIR/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  p_aws="AK""IA$(printf '%016d' 0 | tr 0 Q)"
  # positive: Bash output with an AWS key (shared table); the command text holds the key too
  out=$(jq -n --arg k "$p_aws" '{tool_name:"Bash",tool_input:{command:("echo " + $k)},tool_response:{stdout:("key=" + $k),stderr:""}}' |
        CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>/dev/null)
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("AWS Access Key") and contains("a Bash command")' >/dev/null 2>&1; then
    echo "  ok   positive: AWS key in Bash stdout reported via additionalContext"
  else echo "  FAIL AWS key in Bash output ($out)"; fail=1; fi
  if printf '%s' "$out" | grep -qF -- "$p_aws"; then echo "  FAIL secret value echoed to the model"; fail=1; else echo "  ok   value and command text never echoed"; fi
  # positive: JWT (output-only extra) in a Read response
  p_jwt="ey""J$(printf '%012d' 0 | tr 0 a).$(printf '%012d' 0 | tr 0 b).$(printf '%012d' 0 | tr 0 c)"
  out=$(jq -n --arg k "$p_jwt" '{tool_name:"Read",tool_input:{file_path:"/x/a.http"},tool_response:{content:("Authorization: " + $k)}}' | "$BASH" "$self" 2>/dev/null)
  case "$out" in *"JWT token"*) echo "  ok   positive: JWT in Read output reported" ;; *) echo "  FAIL JWT ($out)"; fail=1 ;; esac
  # SIGPIPE regression: key on line 1 of a >1 MB output
  big="$tmp/big.txt"; { printf '%s\n' "$p_aws"; i=0; while [ $i -lt 20000 ]; do printf 'line %s %s\n' "$i" "$(printf '%048d' 0)"; i=$((i + 1)); done; } > "$big"
  out=$(jq -n --rawfile c "$big" '{tool_name:"Read",tool_input:{file_path:"/x/big"},tool_response:$c}' | "$BASH" "$self" 2>/dev/null)
  case "$out" in *"AWS Access Key"*) echo "  ok   positive: key on line 1 of a $(wc -c < "$big" | tr -d ' ')-byte output (SIGPIPE regression)" ;; *) echo "  FAIL large output missed"; fail=1 ;; esac
  # negatives
  out=$(jq -n '{tool_name:"Bash",tool_input:{command:"ls"},tool_response:{stdout:"README.md\nsrc\nconst k = process.env.API_KEY;",stderr:""}}' | "$BASH" "$self" 2>&1)
  if [ -z "$out" ]; then echo "  ok   negative: ordinary output silent"; else echo "  FAIL false positive ($out)"; fail=1; fi
  out=$(jq -n '{tool_name:"WebFetch",tool_input:{url:"https://x.test/?token=abc"},tool_response:"short"}' | "$BASH" "$self" 2>&1)
  if [ -z "$out" ]; then echo "  ok   negative: short output skipped"; else echo "  FAIL short output ($out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
