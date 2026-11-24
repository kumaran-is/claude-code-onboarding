#!/usr/bin/env bash
# StopFailure: the turn ended due to a CLAUDE (Anthropic) API error — rate limit, auth,
# billing, max-output-tokens, etc. Surface a specific, actionable notice instead of leaving
# the user to guess. Advisory; always exits 0.
#
# Scope note: this catches ANTHROPIC-side (your Claude Code session) turn failures. An LLM
# quota/rate-limit error that surfaces inside a command's OUTPUT (e.g. your app calling an
# LLM provider in a test/eval) is a different thing — handled by output-llm-quota-guard.sh
# (PostToolUse Bash). The two are complementary.
#
# StopFailure is notification-only (the turn already ended) — it cannot block or inject
# conversation context, so this writes a clear stderr notice + an audit-log line. Wired with
# no matcher (fires on every StopFailure); the error class is read from stdin and classified
# here (the stdin field name varies by version, so we read both `error_type` and `error`).
set -uo pipefail

if [ "${1:-}" = "--selftest" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"; fail=0
  check() { if [ "$1" = 0 ]; then echo "  ok   $2"; else echo "  FAIL $2: $3"; fail=1; fi; }
  bash -n "$self"; check $? "parses (bash -n)" ""
  tmp=$(mktemp -d); mkdir -p "$tmp/.claude"
  err=$(printf '{"error_type":"rate_limit","error_message":"429 too many"}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1 >/dev/null)
  case "$err" in *"rate limit hit"*) r=0 ;; *) r=1 ;; esac; check $r "positive: rate_limit gets specific advice" "$err"
  grep -q "StopFailure: rate_limit | 429 too many" "$tmp/.claude/api-error-detected.log" 2>/dev/null
  check $? "positive: the audit line is written" "$(cat "$tmp/.claude/api-error-detected.log" 2>/dev/null)"
  rm -f "$tmp/.claude/api-error-detected.log"
  err=$(printf '' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  [ -z "$err" ] && [ ! -f "$tmp/.claude/api-error-detected.log" ]; check $? "negative: an empty payload writes nothing" "$err"
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  exit "$fail"
fi

input=$(cat 2>/dev/null || true)
[ -z "$input" ] && exit 0

etype=$(echo "$input" | jq -r '.error_type // .error // "unknown"' 2>/dev/null) || etype="unknown"
emsg=$(echo "$input" | jq -r '.error_message // ""' 2>/dev/null | head -c 200) || emsg=""

case "$etype" in
  rate_limit)
    advice="Anthropic API rate limit hit. Wait and retry, slow the request rate, or check your plan limits. NOT a code problem — do not 'fix' code for this." ;;
  billing_error)
    advice="Anthropic billing error — check your Claude account billing/credits. Account-level, not a code problem." ;;
  authentication_failed)
    advice="Anthropic authentication failed — re-authenticate (/login or check API key). Not a code problem." ;;
  max_output_tokens)
    advice="Hit max output tokens for the turn. Ask Claude to continue, or split the task into smaller steps." ;;
  server_error)
    advice="Anthropic server error (transient). Retry shortly." ;;
  invalid_request)
    advice="Invalid request to the Anthropic API — inspect the last message / tool call that triggered it." ;;
  *)
    advice="Claude turn ended on an API error (${etype})." ;;
esac

{
  echo ""
  echo "🛑 Turn ended on a Claude API error: ${etype}"
  echo "   ${advice}"
  [ -n "$emsg" ] && echo "   Detail: ${emsg}"
  echo ""
} >&2

LOGFILE="${CLAUDE_PROJECT_DIR:-.}/.claude/api-error-detected.log"
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "?")
printf '[%s] StopFailure: %s | %s\n' "$ts" "$etype" "$emsg" >> "$LOGFILE" 2>/dev/null || true

exit 0
