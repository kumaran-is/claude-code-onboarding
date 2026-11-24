#!/usr/bin/env bash
# SubagentStart: inject the dated entries of .claude/rules/lessons.md into subagents that start
# WITHOUT CLAUDE.md and .claude/rules/: the built-in Explore and Plan agents, and any project agent
# whose frontmatter sets `omitClaudeMd: true`. Every other subagent already loads lessons.md as an
# always-loaded rule, so injecting it again only doubled the text (and spent its budget).
# Entries start at the first `## [YYYY-MM-DD]` heading with a real date: the format template in the
# file's code fence (`## [YYYY-MM-DD] ...`) is never an entry. The old `/^## \[/` anchor matched that
# template first and injected the format boilerplate instead of the lessons.
#
# Delivery: hookSpecificOutput.additionalContext on SubagentStart goes into the subagent. On
# PreToolUse (the old wiring) it would reach only the PARENT, so for any other event this hook
# stays silent. The previous version also printed hand-built JSON with the raw lessons text
# (quotes, backticks, newlines), which was invalid JSON, so nothing was ever injected.
# Wire under "SubagentStart" in .claude/settings.json (no matcher).
# Test: bash .claude/hooks/pre-lessons-injector.sh --selftest
set -uo pipefail

run_hook() {
  local input event agent_type agent_file lessons_file lessons
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  event=$(printf '%s' "$input" | jq -r '.hook_event_name // ""' 2>/dev/null) || event=""
  [ "$event" = "SubagentStart" ] || return 0
  agent_type=$(printf '%s' "$input" | jq -r '.agent_type // ""' 2>/dev/null) || agent_type=""
  case "$agent_type" in
    Explore|Plan) ;;
    *[!A-Za-z0-9_-]*|"") return 0 ;;   # unknown or namespaced (plugin:x): it loads CLAUDE.md
    *) agent_file="${CLAUDE_PROJECT_DIR:-.}/.claude/agents/$agent_type.md"
       [ -f "$agent_file" ] || return 0
       awk 'NR == 1 && /^---$/ { fm = 1; next } fm && /^---$/ { exit } fm' "$agent_file" \
         | grep -qE '^omitClaudeMd:[[:space:]]*true' || return 0 ;;
  esac
  lessons_file="${CLAUDE_PROJECT_DIR:-.}/.claude/rules/lessons.md"
  [ -f "$lessons_file" ] || return 0
  # dated entries only, capped so a long log cannot flood the agent
  lessons=$(awk '/^## \[[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\]/ { on = 1 } on' "$lessons_file" | head -n 60)
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
  mkdir -p "$tmp/.claude/agents"
  printf -- '---\nname: lean\nomitClaudeMd: true\n---\nbody\n' > "$tmp/.claude/agents/lean.md"
  printf -- '---\nname: full\n---\nomitClaudeMd: true appears only in the body\n' > "$tmp/.claude/agents/full.md"
  # the real file's shape: a format template inside a code fence BEFORE the first dated entry
  printf '# Lessons\n\nHeader text.\n\n```\n## [YYYY-MM-DD] [Category] [x1]\n**Mistake:** [template]\n```\n\n## [2026-01-01] Scope [x1]\n**Mistake:** Ran `rm` on "quoted" paths\twith a tab.\n**Rule:** Do not.\n' > "$tmp/.claude/rules/lessons.md"
  out=$(echo '{"hook_event_name":"SubagentStart","agent_type":"Explore"}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.hookEventName == "SubagentStart"
       and (.hookSpecificOutput.additionalContext | contains("## [2026-01-01] Scope") and contains("\"quoted\"") and (contains("Header text") | not) and (contains("YYYY-MM-DD") | not) and (contains("[template]") | not))' >/dev/null 2>&1; then
    echo "  ok   positive: Explore gets dated entries only as valid JSON (template in the fence and header skipped; quotes, backticks, tab survive)"
  else echo "  FAIL Explore injection: $out"; fail=1; fi
  out=$(echo '{"hook_event_name":"SubagentStart","agent_type":"lean"}' | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("## [2026-01-01] Scope")' >/dev/null 2>&1; then
    echo "  ok   positive: a project agent with omitClaudeMd: true in its frontmatter gets the entries"
  else echo "  FAIL omitClaudeMd agent: $out"; fail=1; fi
  for at in full general-purpose code-reviewer 'plugin:x' ''; do
    out=$(printf '{"hook_event_name":"SubagentStart","agent_type":"%s"}' "$at" | CLAUDE_PROJECT_DIR="$tmp" "$BASH" "$self" 2>&1)
    if [ -z "$out" ]; then echo "  ok   negative: agent_type '$at' already loads CLAUDE.md, nothing injected"; else echo "  FAIL agent_type '$at' got: $out"; fail=1; fi
  done
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
