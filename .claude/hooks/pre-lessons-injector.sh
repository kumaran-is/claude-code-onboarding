#!/usr/bin/env bash
# SubagentStart: inject the entries of .claude/rules/lessons.md into every subagent's context.
# The built-in Explore/Plan subagents (and agents with omitClaudeMd) start without CLAUDE.md and
# .claude/rules/, so accumulated corrections would be lost at the agent boundary; for other
# subagents this is a small, harmless repeat.
#
# Delivery: hookSpecificOutput.additionalContext on SubagentStart goes into the subagent. On
# PreToolUse (the old wiring) it would reach only the PARENT, so for any other event this hook
# stays silent. The previous version also printed hand-built JSON with the raw lessons text
# (quotes, backticks, newlines), which was invalid JSON, so nothing was ever injected.
# Wire under "SubagentStart" in .claude/settings.json (no matcher).
# Test: bash .claude/hooks/pre-lessons-injector.sh --selftest
set -uo pipefail

run_hook() {
  local input event lessons_file lessons
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  event=$(printf '%s' "$input" | jq -r '.hook_event_name // ""' 2>/dev/null) || event=""
  [ "$event" = "SubagentStart" ] || return 0
  lessons_file="${CLAUDE_PROJECT_DIR:-.}/.claude/rules/lessons.md"
  [ -f "$lessons_file" ] || return 0
  # entries only (from the first "## [date]" heading), capped so a long log cannot flood the agent
  lessons=$(sed -n '/^## \[/,$p' "$lessons_file" | head -n 60)
  [ -n "$lessons" ] || return 0
  jq -n --arg l "$lessons" '{hookSpecificOutput:{hookEventName:"SubagentStart",
    additionalContext:("TEAM LESSONS (from .claude/rules/lessons.md: corrections accumulated across sessions). Apply them:\n" + $l)}}'
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/.claude/rules"
  printf '# Lessons\n\nHeader text.\n\n## [2026-01-01] Scope [x1]\n**Mistake:** Ran `rm` on "quoted" paths\twith a tab.\n**Rule:** Do not.\n' > "$tmp/.claude/rules/lessons.md"
  out=$(echo '{"hook_event_name":"SubagentStart","agent_type":"Explore"}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.hookEventName == "SubagentStart"
       and (.hookSpecificOutput.additionalContext | contains("## [2026-01-01] Scope") and contains("\"quoted\"") and (contains("Header text") | not))' >/dev/null 2>&1; then
    echo "  ok   positive: entries injected on SubagentStart as valid JSON (quotes, backticks, tab survive; header skipped)"
  else echo "  FAIL SubagentStart injection: $out"; fail=1; fi
  out=$(echo '{"hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"prompt":"x"}}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if [ -z "$out" ]; then echo "  ok   negative: PreToolUse (would reach only the parent) is silent"; else echo "  FAIL PreToolUse output: $out"; fail=1; fi
  printf '# Lessons\n\nNo entries yet.\n' > "$tmp/.claude/rules/lessons.md"
  out=$(echo '{"hook_event_name":"SubagentStart"}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if [ -z "$out" ]; then echo "  ok   negative: no entries, nothing injected"; else echo "  FAIL empty lessons: $out"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
