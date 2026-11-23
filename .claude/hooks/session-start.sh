#!/usr/bin/env bash
# SessionStart (startup, resume, /clear, /compact): remind Claude to recover task state before new
# work (core-behaviors.md §9). Kept short on purpose: CLAUDE.md is loaded at launch and holds the
# full resume template and skill table, so this only points at them.
#
# Delivery: hookSpecificOutput.additionalContext (built with jq). The previous version printed a
# top-level {"additionalContext": ...}, a shape the hooks reference does not define.
# Test: bash .claude/hooks/session-start.sh --selftest
set -uo pipefail

CONTENT='SESSION RESUME (injected by hook): context may have been reset. Before any other action, run TaskList; if tasks exist, present the "Session Resumed" summary from CLAUDE.md → Resuming Tasks and ask where to continue. Load the matching skill from CLAUDE.md → Code Conventions before writing code.'

if [ "${1:-}" = "--selftest" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  bash -n "$self" || { echo "  FAIL does not parse"; exit 1; }
  echo "  ok   parses (bash -n)"
  out=$(echo '{"hook_event_name":"SessionStart","source":"compact"}' | "$BASH" "$self")
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart" and (.hookSpecificOutput.additionalContext | contains("TaskList")) and (has("additionalContext") | not)' >/dev/null 2>&1; then
    echo "  ok   positive: documented SessionStart shape, valid JSON"; echo "selftest PASS"; exit 0
  fi
  echo "  FAIL output: $out"; echo "selftest FAIL"; exit 1
fi

cat > /dev/null 2>&1 || true
if command -v jq >/dev/null 2>&1; then
  jq -n --arg c "$CONTENT" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
else
  printf '%s\n' "$CONTENT" # SessionStart plain stdout is also added to context
fi
exit 0
