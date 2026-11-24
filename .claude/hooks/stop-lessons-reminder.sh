#!/usr/bin/env bash
# Stop hook: remind the user when lessons are ready to promote (x3+), lessons.md nears its 15-entry
# cap, or agent memory changed since the last /promote-lessons pass (marker `.last-consolidated`; each
# changed state is reported once, tracked in `.reminded`). Delivered as systemMessage (shown to the
# user). Always exits 0 (never blocks). Only dated entries count (`## [YYYY-MM-DD] ...`): the fenced
# format template in lessons.md is not an entry.
# Test: bash .claude/hooks/stop-lessons-reminder.sh --selftest
set -uo pipefail

reminders_for() { # $1 project root -> reminder lines on stdout
  local lessons="$1/.claude/rules/lessons.md" memory="$1/.claude/agent-memory" promote entries changed n fp f
  if [ -f "$lessons" ]; then
    promote=$(grep -cE '^## \[[0-9]{4}-[0-9]{2}-[0-9]{2}\].*\[x([3-9]|[1-9][0-9]+)\]' "$lessons" 2>/dev/null || true)
    [ "${promote:-0}" -gt 0 ] && printf '  - %s lesson(s) at x3+ ready for promotion to rules files\n' "$promote"
    entries=$(grep -cE '^## \[[0-9]{4}-[0-9]{2}-[0-9]{2}\]' "$lessons" 2>/dev/null || true)
    [ "${entries:-0}" -ge 12 ] && printf '  - lessons.md has %s/15 entries — consider pruning stale ones\n' "$entries"
  fi
  if [ -d "$memory" ]; then
    # agent memory (memory: project) is the agents' working memory: report what changed since the last
    # consolidation, once per changed state, never "orphaned" files on every stop
    if [ -f "$memory/.last-consolidated" ]; then changed=$(find "$memory" -name "*.md" -newer "$memory/.last-consolidated" 2>/dev/null | sort)
    else changed=$(find "$memory" -name "*.md" 2>/dev/null | sort); fi
    n=$(printf '%s' "$changed" | grep -c . || true)
    if [ "${n:-0}" -gt 0 ]; then
      fp=$(printf '%s\n' "$changed" | while IFS= read -r f; do cksum "$f"; done | cksum | cut -d' ' -f1)
      if [ "$(cat "$memory/.reminded" 2>/dev/null)" != "$fp" ]; then
        printf '  - %s agent-memory file(s) changed since the last consolidation (prune entries, keep the files)\n' "$n"
        printf '%s\n' "$fp" > "$memory/.reminded" 2>/dev/null || true
      fi
    fi
  fi
  return 0
}

selftest() {
  local self tmp out fail=0
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/.claude/rules"
  { printf '# Lessons\n```\n## [YYYY-MM-DD] [Category] [x3]\n```\n'; printf '## [2026-01-01] Scope [x1]\nm\n'; } > "$tmp/.claude/rules/lessons.md"
  out=$(printf '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self")
  if [ -z "$out" ]; then echo "  ok   negative: the fenced template ([x3]) is not a promotable entry"; else echo "  FAIL template counted: $out"; fail=1; fi
  for i in 2 3 4 5 6 7 8 9; do printf '## [2026-01-0%s] Scope [x1]\nm\n' "$i"; done >> "$tmp/.claude/rules/lessons.md"
  printf '## [2026-02-01] Scope [x1]\nm\n## [2026-02-02] Scope [x1]\nm\n## [2026-02-03] Verification [x3]\nm\n' >> "$tmp/.claude/rules/lessons.md"
  mkdir -p "$tmp/.claude/agent-memory/x"; printf 'note\n' > "$tmp/.claude/agent-memory/x/MEMORY.md"
  out=$(printf '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self")
  if printf '%s' "$out" | jq -e '.systemMessage | (contains("1 lesson(s) at x3+") and contains("12/15 entries") and contains("1 agent-memory file(s) changed"))' >/dev/null 2>&1; then
    echo "  ok   positive: x3 entry, 12/15 entries and an agent-memory file are all reported"
  else echo "  FAIL reminders: $out"; fail=1; fi
  out=$(printf '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self")
  if ! printf '%s' "$out" | grep -q "agent-memory"; then echo "  ok   negative: unchanged agent memory is reported once, not on every stop"
  else echo "  FAIL repeated memory reminder: $out"; fail=1; fi
  touch -t 202001010000 "$tmp/.claude/agent-memory/x/MEMORY.md"; : > "$tmp/.claude/agent-memory/.last-consolidated"
  rm -f "$tmp/.claude/agent-memory/.reminded"
  out=$(printf '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self")
  if ! printf '%s' "$out" | grep -q "agent-memory"; then echo "  ok   negative: memory older than the last consolidation is not reported"
  else echo "  FAIL consolidated memory reported: $out"; fail=1; fi
  touch -t 202101010000 "$tmp/.claude/agent-memory/.last-consolidated"; printf 'note 2\n' >> "$tmp/.claude/agent-memory/x/MEMORY.md"
  out=$(printf '{}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self")
  if printf '%s' "$out" | grep -q "1 agent-memory file(s) changed"; then echo "  ok   positive: memory written after the last consolidation is reported"
  else echo "  FAIL new memory not reported: $out"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
cat > /dev/null 2>&1 || true   # the Stop payload is not needed
reminders=$(reminders_for "${CLAUDE_PROJECT_DIR:-$(pwd)}")
if [ -n "$reminders" ] && command -v jq >/dev/null 2>&1; then
  # stderr of an exit-0 hook is not delivered anywhere; systemMessage is shown to the user.
  jq -n --arg m "LESSONS LIFECYCLE REMINDER - run /promote-lessons to process:
$reminders" '{systemMessage:$m}'
fi
exit 0
