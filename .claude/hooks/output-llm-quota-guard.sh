#!/usr/bin/env bash
# output-llm-quota-guard.sh — PostToolUse (Bash)
# Scans command OUTPUT for LLM-provider quota / rate-limit errors and tells the model which kind it is,
# so a provider condition is not misdiagnosed as a code or test failure.
#
# Three classes, checked in this order (first match wins):
#   BILLING   credits/billing exhausted (Anthropic `billing_error` / "credit balance is too low",
#             OpenAI `insufficient_quota`, `BILLING_DISABLED`) -> stop LLM-dependent commands, report BLOCKED.
#   QUOTA     quota exhausted, period unknown (`RESOURCE_EXHAUSTED`, "exceeded your current quota",
#             "quota exceeded"): may be a per-minute limit or a daily/project quota -> at most two retries
#             with backoff (or Retry-After), then stop and report BLOCKED.
#   TRANSIENT throttling/overload (Anthropic `rate_limit_error` / `overloaded_error`, OpenAI
#             `rate_limit_exceeded`, "rate limit reached/exceeded", or 429 / "Too Many Requests" on a line
#             that also names a provider) -> bounded retry with backoff is correct; do not change code.
# A bare "429" or "too many requests" without a provider name on the same line (e.g. a test called
# test_too_many_requests_returns_429) is ignored.
#
# False-positive guards (the signatures also appear in docs, code, logs and this file):
#   1. Read/search-only commands are skipped: when EVERY simple command in the Bash string (split on
#      unquoted ; & | ( ) ` and newlines) starts with cat, grep/rg, sed, awk, head/tail, less, wc, ls, find,
#      diff, jq, echo/printf, cd, or git log/diff/show/grep/blame/status, the command printed files, it did
#      not call a provider. Unparseable commands (unbalanced quotes) are classified, i.e. fail toward firing.
#   2. In any other command's output, grep-style `path:N:` lines and diff lines (`+`/`-`/`@@`, `diff --git`)
#      are dropped before classifying, so `pytest ...; git diff` does not fire on the diff.
#
# Contract (see .claude/rules/hook-and-gate-authoring.md): advisory, always exit 0, delivered as
# hookSpecificOutput.additionalContext (hookEventName PostToolUse) plus a systemMessage for the user.
# Fails open (silent) without jq: the command already ran and nothing is blocked.
# Provider error strings: Anthropic ErrorType literals verified in the Python SDK; the others are
# documented provider codes, re-check them when a provider changes its error format.
# Test: bash .claude/hooks/output-llm-quota-guard.sh --selftest
set -uo pipefail

PROVIDERS='openai|anthropic|claude|gemini|vertex|generativelanguage|aiplatform|googleapis|x-ratelimit|litellm|bedrock|azure'

read_only_command() { # $1 Bash command string -> exit 0 when every simple command only reads/prints files
  local segs seg w1 w2 rest
  segs=$(printf '%s\n' "$1" | awk '
    { s = s $0 "\n" }
    END {
      q = ""; seg = ""; n = length(s)
      for (i = 1; i <= n; i++) {
        c = substr(s, i, 1)
        if (q != "") { seg = seg c; if (c == q) q = ""; else if (c == "\\" && q == "\"") { i++; seg = seg substr(s, i, 1) }; continue }
        if (c == "\047" || c == "\"") { q = c; seg = seg c; continue }
        if (c == "\\") { i++; seg = seg c substr(s, i, 1); continue }
        if (c == ";" || c == "&" || c == "|" || c == "\n" || c == "(" || c == ")" || c == "`") { print seg; seg = ""; continue }
        seg = seg c
      }
      print seg
      if (q != "") { print "__UNBALANCED_QUOTE__" }
    }') || return 1
  while IFS= read -r seg; do
    [ "$seg" = "__UNBALANCED_QUOTE__" ] && return 1
    set -f; set -- $seg; set +f
    while [ $# -gt 0 ]; do   # skip VAR=value prefixes, shell keywords and neutral wrappers
      case "$1" in
        [A-Za-z_]*=*|do|then|else|elif|if|while|until|'!'|'{'|'}'|time|command|env|'$') shift ;;
        *) break ;;
      esac
    done
    [ $# -eq 0 ] && continue
    w1=${1##*/}; w2=${2:-}
    case "$w1" in
      cat|grep|egrep|fgrep|rg|ag|sed|awk|head|tail|less|more|wc|ls|find|diff|cmp|nl|jq|stat|file|echo|printf|cd|pwd|sort|uniq|cut|tr|true|done|fi|for|in|esac) ;;
      git) case "$w2" in log|diff|show|grep|blame|status|ls-files|cat-file) ;; *) return 1 ;; esac ;;
      *) return 1 ;;
    esac
  done <<<"$segs"
  return 0
}

classify() { # stdin: command output -> prints BILLING | QUOTA | TRANSIENT | nothing
  local text
  # drop grep-style "path:N:" listing lines and diff lines: they quote files, they are not provider errors
  text=$(grep -vE '^[^ :]*[./][^ :]*:[0-9]+[:-]|^[+-]|^@@|^diff --git |^index [0-9a-f]+\.\.' || true)
  if grep -qiE 'insufficient_quota|billing_error|credit balance is too low|BILLING_DISABLED' <<<"$text"; then
    echo BILLING
  elif grep -qiE 'RESOURCE_EXHAUSTED|exceeded your current quota|quota exceeded' <<<"$text"; then
    echo QUOTA
  elif grep -qiE 'rate_limit_error|rate_limit_exceeded|overloaded_error|rate limit (reached|exceeded)' <<<"$text"; then
    echo TRANSIENT
  else
    local lines
    lines=$(grep -iE '(^|[^0-9])429([^0-9]|$)|too many requests' <<<"$text" || true)
    if [ -n "$lines" ] && grep -qiE "$PROVIDERS" <<<"$lines"; then echo TRANSIENT; fi
  fi
}

run_hook() {
  local input tool content kind cmd msg ctx logfile ts
  command -v jq >/dev/null 2>&1 || return 0
  input=$(cat)
  tool=$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null) || tool=""
  [ "$tool" = "Bash" ] || return 0
  content=$(printf '%s' "$input" | jq -r '
    if (.tool_response | type) == "string" then .tool_response
    else ([.tool_response.stdout?, .tool_response.stderr?, .tool_response.output?, .tool_response.content?]
          | map(select(type == "string")) | join("\n"))
    end // ""' 2>/dev/null) || content=""
  [ "${#content}" -ge 12 ] || return 0
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null) || cmd=""
  [ -n "$cmd" ] && read_only_command "$cmd" && return 0
  kind=$(printf '%s' "$content" | classify)
  [ -n "$kind" ] || return 0
  cmd=$(printf '%s' "$cmd" | head -c 120)

  case "$kind" in
    BILLING)
      msg="LLM provider billing/credits exhausted in the output of the last command. This is a provider BLOCKER, not a code or test failure."
      ctx="LLM provider BILLING/credit exhaustion (billing_error / insufficient_quota / credit balance too low) in the output of: '${cmd}'. Retrying cannot succeed until credits or billing are fixed. Stop running LLM-dependent commands, do not change code or tests to work around it, and report the affected checks as BLOCKED (provider billing), not FAIL." ;;
    QUOTA)
      msg="LLM provider quota exhausted in the output of the last command (may be a per-minute limit or a daily/project quota)."
      ctx="LLM provider QUOTA exhausted (RESOURCE_EXHAUSTED / exceeded quota) in the output of: '${cmd}'. The period is unknown: it may be a per-minute limit that clears in seconds or a daily/project quota. Retry at most twice with backoff (honour Retry-After if present, otherwise wait about 30 s, then about 2 min). If it still fails, stop and report the affected checks as BLOCKED (provider quota). Do not change code or tests to work around it." ;;
    TRANSIENT)
      msg="LLM provider throttling/overload in the output of the last command (transient rate limit)."
      ctx="LLM provider RATE LIMIT or OVERLOAD (429 / rate_limit_error / overloaded_error) in the output of: '${cmd}'. This is usually transient: a bounded retry with exponential backoff and jitter is correct (provider SDKs already retry 429 and 5xx a few times). Do not change code for it. Lower concurrency if many LLM calls run in parallel. If it persists after about three spaced attempts, report the affected checks as BLOCKED (provider throttling), not FAIL." ;;
  esac

  logfile="${CLAUDE_PROJECT_DIR:-.}/.claude/llm-quota-detected.log"
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "?")
  { printf "[%s] %s | cmd: %s\n" "$ts" "$kind" "$cmd" >> "$logfile"; } 2>/dev/null || true   # redirect errors would leak to stderr otherwise

  jq -n --arg m "$msg" --arg c "$ctx" \
    '{systemMessage:$m, hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$c}}'
  return 0
}

selftest() {
  local self fail=0 tmp out err rc big
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required for selftest"; return 1; }
  tmp=$(mktemp -d) || return 1
  probe() { # $1 output text, $2 optional response shape: "string" (default) or "object", $3 optional command
    local pcmd="${3:-pytest -m llm}"
    if [ "${2:-string}" = "object" ]; then
      jq -n --arg o "$1" --arg c "$pcmd" '{tool_name:"Bash", tool_input:{command:$c}, tool_response:{stdout:"", stderr:$o}}'
    else
      jq -n --arg o "$1" --arg c "$pcmd" '{tool_name:"Bash", tool_input:{command:$c}, tool_response:$o}'
    fi | CLAUDE_PROJECT_DIR="$tmp" /bin/bash "$self" >"$tmp/out" 2>"$tmp/err"
    rc=$?; out=$(cat "$tmp/out"); err=$(cat "$tmp/err")
  }
  expect_ctx() { # $1 label, $2 needle in hookSpecificOutput.additionalContext
    if [ "$rc" -eq 0 ] && [ -z "$err" ] && printf '%s' "$out" | jq -e --arg n "$2" \
        '.hookSpecificOutput.hookEventName == "PostToolUse" and (.hookSpecificOutput.additionalContext | contains($n)) and (has("additionalContext") | not)' >/dev/null 2>&1
    then echo "  ok   positive: $1"; else echo "  FAIL $1 (rc=$rc err=$err out=$out)"; fail=1; fi
  }
  expect_silent() {
    if [ "$rc" -eq 0 ] && [ -z "$out" ] && [ -z "$err" ]; then echo "  ok   negative: $1"
    else echo "  FAIL $1 (rc=$rc err=$err out=$out)"; fail=1; fi
  }

  probe 'anthropic.BadRequestError: {"type":"error","error":{"type":"billing_error","message":"Your credit balance is too low"}}'
  expect_ctx "Anthropic billing error -> BILLING, stop" "BILLING"
  probe 'openai.RateLimitError: Error code: 429 - {"error":{"code":"insufficient_quota"}}' object
  expect_ctx "OpenAI insufficient quota (stderr of object response) -> BILLING" "BLOCKED (provider billing)"
  probe 'google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED. Quota exceeded for metric generate_content'
  expect_ctx "Gemini resource exhausted -> QUOTA, bounded retry" "Retry at most twice"
  probe 'anthropic.RateLimitError: {"type":"error","error":{"type":"rate_limit_error"}}'
  expect_ctx "Anthropic rate limit error -> TRANSIENT, retry allowed" "bounded retry"
  probe 'httpx.HTTPStatusError: 429 Too Many Requests for url https://api.openai.com/v1/chat/completions'
  expect_ctx "429 on a provider URL line -> TRANSIENT" "RATE LIMIT"

  probe 'tests/test_api.py::test_too_many_requests_returns_429 PASSED'
  expect_silent "test name with 429 / too many requests, no provider"
  probe 'GET /health 200 OK in 4290 ms; 12 passed'
  expect_silent "4290 is not 429"
  big=$(printf 'line %s ok\n' $(seq 1 6000))
  probe "$big"
  expect_silent "large clean output (SIGPIPE-sized)"
  probe "${big}
vertexai: 429 RESOURCE_EXHAUSTED"
  expect_ctx "signature after large output still detected" "QUOTA"
  jq -n '{tool_name:"Read", tool_response:"RESOURCE_EXHAUSTED"}' | /bin/bash "$self" >"$tmp/out" 2>"$tmp/err"
  rc=$?; out=$(cat "$tmp/out"); err=$(cat "$tmp/err"); expect_silent "non-Bash tool ignored"

  # False-positive guards: read/search commands and quoted file content (signature strings built from parts)
  local bq cb
  bq="insufficient""_quota"; cb="credit balance is ""too low"
  probe "docs/runbook.md:12:- \`${bq}\` means billing is exhausted" string "grep -rn ${bq} docs/"
  expect_silent "grep -rn <billing code> docs/ (search output)"
  probe "If you see '${cb}', top up credits." string "cat digest.md"
  expect_silent "cat digest.md containing the billing sentence"
  probe "diff --git a/h.sh b/h.sh
@@ -1,2 +1,2 @@
-# RESOURCE""_EXHAUSTED old
+# RESOURCE""_EXHAUSTED new" string "git diff"
  expect_silent "git diff output"
  probe "x RESOURCE""_EXHAUSTED y" string "cd /repo && sed -n 1,30p .claude/hooks/h.sh | head -5"
  expect_silent "cd && sed -n | head (compound read-only)"
  probe "a ${bq} b" string "grep -E 'pytest|curl' notes.md"
  expect_silent "quoted | inside a grep pattern is not a pipe"
  probe "12 passed
diff --git a/x b/x
+${cb}" string "pytest -q; git diff"
  expect_silent "pytest then git diff: diff lines are not provider errors"
  # ...and the guards must not hide real provider failures
  probe "anthropic.BadRequestError: ${cb}" string "cd /repo && pytest -m llm"
  expect_ctx "cd && pytest with billing error still fires" "BILLING"
  probe "openai.RateLimitError: ${bq}" string "grep -c x f; python run_eval.py"
  expect_ctx "read command followed by a provider-calling command still fires" "BILLING"
  probe "google.genai.errors.ClientError: 429 RESOURCE""_EXHAUSTED" string "cat <<EOF
it's
EOF
python run.py"
  expect_ctx "unbalanced quote (heredoc) fails toward firing" "QUOTA"
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
