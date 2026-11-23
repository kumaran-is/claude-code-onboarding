#!/usr/bin/env bash
# PreToolUse (Edit|Write): advisory. When a `**Rule:**` line is being written into
# .claude/rules/lessons.md, check whether it repeats a rule already promoted to another
# .claude/rules/*.md file (any 4-word window of the new Rule found verbatim, case-insensitive).
# A promoted rule that was violated should be cited, not re-added as a lesson, or lessons.md
# fills with duplicates of rules that already apply.
# Always exit 0. Finding -> hookSpecificOutput.additionalContext. Fails open (says so once) without jq.
# Test: bash .claude/hooks/pre-edit-lessons-dedup.sh --selftest
set -uo pipefail

# Prints "file" of the first promoted rule that shares a 4-word window with the Rule text in $1.
find_duplicate() { # $1 rule text, $2 rules dir
  local window hit
  while IFS= read -r window; do
    [ "${#window}" -ge 15 ] || continue   # skip windows of tiny words ("is to be in")
    hit=$(grep -rilF --include="*.md" -e "$window" "$2" 2>/dev/null | grep -v '/lessons\.md$' | head -n 1)
    if [ -n "$hit" ]; then printf '%s' "$hit"; return 0; fi
  done <<EOF_WINDOWS
$(printf '%s' "$1" | tr 'A-Z' 'a-z' | tr -d '.,;:!?()`*"[]' | awk '{ for (i = 1; i + 3 <= NF; i++) print $i " " $(i + 1) " " $(i + 2) " " $(i + 3) }')
EOF_WINDOWS
  return 1
}

run_hook() {
  local input file text rule root hit marker
  input=$(cat)
  if ! command -v jq >/dev/null 2>&1; then
    marker="${TMPDIR:-/tmp}/claude-lessons-dedup-nojq"
    [ -f "$marker" ] || { : > "$marker" 2>/dev/null; echo "pre-edit-lessons-dedup: jq not found; lessons duplicate check disabled." >&2; }
    return 0
  fi
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || return 0
  case "$file" in */.claude/rules/lessons.md|.claude/rules/lessons.md) ;; *) return 0 ;; esac
  text=$(printf '%s' "$input" | jq -r '.tool_input.new_string // .tool_input.content // ""' 2>/dev/null) || return 0
  rule=$(printf '%s\n' "$text" | sed -n 's/^\*\*Rule:\*\*[[:space:]]*//p' | tail -n 1)
  [ -n "$rule" ] || return 0
  root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  hit=$(find_duplicate "$rule" "$root/.claude/rules") || return 0
  jq -n --arg f "${hit#"$root"/}" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:
    ("This lesson may duplicate a rule already promoted to " + $f + ". If so, do not add a lesson: cite the rule that was violated.")}}'
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/.claude/rules"
  printf '## 5. Scope Discipline\n\nTouch only what you'"'"'re asked to touch.\n' > "$tmp/.claude/rules/core-behaviors.md"
  printf '# Lessons\n' > "$tmp/.claude/rules/lessons.md"
  probe() { # $1 file_path, $2 Rule text
    jq -n --arg f "$1" --arg r "$2" '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"x",new_string:("## [2026-01-01] Scope [x1]\n**Mistake:** m\n**Rule:**    " + $r + "\n**Applies:** all")}}' |
      CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1
  }
  out=$(probe "$tmp/.claude/rules/lessons.md" "Always touch only what you're asked to touch, nothing else.")
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains(".claude/rules/core-behaviors.md")' >/dev/null 2>&1; then
    echo "  ok   positive: Rule repeating core-behaviors §5 is flagged"
  else echo "  FAIL duplicate not flagged: $out"; fail=1; fi
  out=$(probe "$tmp/.claude/rules/lessons.md" "Pin the emulator API level in the Maestro flow header")
  if [ -z "$out" ]; then echo "  ok   negative: novel Rule is silent"; else echo "  FAIL novel rule flagged: $out"; fail=1; fi
  out=$(probe "$tmp/docs/notes.md" "Always touch only what you're asked to touch, nothing else.")
  if [ -z "$out" ]; then echo "  ok   negative: non-lessons file ignored"; else echo "  FAIL non-lessons file: $out"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
