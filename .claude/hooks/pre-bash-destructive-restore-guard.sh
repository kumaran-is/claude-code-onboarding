#!/usr/bin/env bash
# PreToolUse -> Bash: ask for confirmation before a git command that DISCARDS uncommitted work.
#
# Why: uncommitted changes live in no commit, stash or reflog. `git checkout -- <path>`,
# `git restore <path>`, `git reset --hard` and `git clean -f` destroy them irrecoverably.
#
# Behavior (deterministic, fail-open):
#   - Only fires when the command contains one of the four shapes above AND `git status`
#     shows uncommitted (or, for clean, untracked) changes in the affected scope.
#   - Emits a permission decision of "ask" (the user confirms or denies) — NOT a hard block.
#   - Always exit 0. If jq/git is missing, not in a work tree, or the payload cannot be
#     parsed, it prints a one-line note to stderr and allows the command (never wedges a session).
#   - Safe shapes stay silent: `git checkout <branch>`, `git restore --staged <path>`,
#     `git reset --soft/--mixed`, `git clean -n`, anything on a clean tree.
#
# Test: bash .claude/hooks/pre-bash-destructive-restore-guard.sh --selftest
set -uo pipefail

# Print the ask decision for $1 (reason).
emit_ask() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
}

# Evaluate one git command string ($1). Prints reason to stdout and returns 0 if risky, 1 otherwise.
# Runs in the current directory (must be inside the work tree).
assess_segment() {
  local seg="$1" sub rest tok paths="" dirty="" has_dd=0 staged_only=0 force=0 dry=0 worktree_flag=0
  sub=$(printf '%s' "$seg" | sed -E 's/^git[[:space:]]+(-[^[:space:]]+[[:space:]]+)*//' | awk '{print $1}')
  rest=$(printf '%s' "$seg" | sed -E 's/^git[[:space:]]+(-[^[:space:]]+[[:space:]]+)*[a-z-]+[[:space:]]*//')

  case "$sub" in
    reset)
      case " $rest " in *" --hard "*) ;; *) return 1 ;; esac
      dirty=$(git status --porcelain --untracked-files=no 2>/dev/null)
      [ -n "$dirty" ] || return 1
      printf 'git reset --hard will discard uncommitted changes in %s file(s), e.g.:\n%s' \
        "$(printf '%s\n' "$dirty" | wc -l | tr -d ' ')" "$(printf '%s\n' "$dirty" | head -5)"
      return 0 ;;
    clean)
      for tok in $rest; do
        case "$tok" in
          --force) force=1 ;;
          --dry-run) dry=1 ;;
          -[a-zA-Z]*) case "$tok" in *f*) force=1 ;; esac; case "$tok" in *n*) dry=1 ;; esac ;;
        esac
      done
      [ "$force" -eq 1 ] && [ "$dry" -eq 0 ] || return 1
      dirty=$(git status --porcelain 2>/dev/null | grep '^??' || true)
      [ -n "$dirty" ] || return 1
      printf 'git clean -f will permanently delete untracked files, e.g.:\n%s' "$(printf '%s\n' "$dirty" | head -5)"
      return 0 ;;
    checkout|restore)
      set -f
      for tok in $rest; do
        case "$tok" in
          --) has_dd=1 ;;
          --staged|-S) staged_only=1 ;;
          --worktree|-W) worktree_flag=1 ;;
          -*) ;;
          *) paths="$paths $tok" ;;
        esac
      done
      set +f
      # restore --staged (without --worktree) only touches the index: safe.
      [ "$sub" = "restore" ] && [ "$staged_only" -eq 1 ] && [ "$worktree_flag" -eq 0 ] && return 1
      if [ "$sub" = "checkout" ]; then
        # Only the path-restoring forms discard work: `checkout -- <p>` or `checkout .`
        if [ "$has_dd" -eq 0 ] && [ "$(echo $paths)" != "." ]; then return 1; fi
      fi
      # Pathspecs after `--`; for checkout, a leading ref before `--` is not a path.
      if [ "$sub" = "checkout" ] && [ "$has_dd" -eq 1 ]; then
        paths=$(printf '%s' "$rest" | sed -E 's/^.*(^|[[:space:]])--([[:space:]]|$)//')
      fi
      # shellcheck disable=SC2086
      set -f
      if [ -z "$(echo $paths)" ]; then
        dirty=$(git status --porcelain --untracked-files=no 2>/dev/null)
      else
        # shellcheck disable=SC2086
        dirty=$(git status --porcelain --untracked-files=no -- $paths 2>/dev/null)
      fi
      set +f
      [ -n "$dirty" ] || return 1
      printf 'git %s will overwrite uncommitted changes in:\n%s' "$sub" "$(printf '%s\n' "$dirty" | head -5)"
      return 0 ;;
  esac
  return 1
}

run_hook() {
  local input cmd seg reason
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "destructive-restore-guard: jq not found; check skipped" >&2; return 0; }
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null) || cmd=""
  [ -n "$cmd" ] || return 0
  printf '%s' "$cmd" | grep -qE 'git[[:space:]].*(checkout|restore|reset|clean)' || return 0
  command -v git >/dev/null 2>&1 || return 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0

  while IFS= read -r seg; do
    [ -n "$seg" ] || continue
    if reason=$(assess_segment "$seg"); then
      emit_ask "$reason
Uncommitted work is unrecoverable. Commit or stash first, or undo your own edit directly."
      return 0
    fi
  done < <(printf '%s\n' "$cmd" | grep -oE 'git[[:space:]][^;&|]*' )
  return 0
}

selftest() {
  local self fail=0 tmp out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  # Control 0: the script must parse.
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required for selftest"; return 1; }
  tmp=$(mktemp -d) || return 1
  ( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t \
    && echo a > f.txt && echo b > g.txt && git add . && git commit -qm init \
    && echo changed >> f.txt && echo new > u.txt ) >/dev/null 2>&1
  probe() { # $1 label, $2 command, $3 expect ask|silent
    out=$(cd "$tmp" && printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$2" | jq -Rs .)" | bash "$self" 2>/dev/null)
    case "$3" in
      ask)    printf '%s' "$out" | grep -q '"permissionDecision": *"ask"' && echo "  ok   $1" || { echo "  FAIL $1 (expected ask, got: $out)"; fail=1; } ;;
      silent) [ -z "$out" ] && echo "  ok   $1" || { echo "  FAIL $1 (expected silent, got: $out)"; fail=1; } ;;
    esac
  }
  probe "positive: checkout -- dirty file"        'git checkout -- f.txt'       ask
  probe "positive: restore dirty file"            'git restore f.txt'           ask
  probe "positive: reset --hard on dirty tree"    'git reset --hard'            ask
  probe "positive: clean -fd with untracked"      'git clean -fd'               ask
  probe "positive: chained command"               'echo hi && git checkout -- f.txt' ask
  probe "negative: checkout -- clean file"        'git checkout -- g.txt'       silent
  probe "negative: restore clean file"            'git restore g.txt'           silent
  probe "negative: restore --staged"              'git restore --staged f.txt'  silent
  probe "negative: branch switch"                 'git checkout main'           silent
  probe "negative: clean dry-run"                 'git clean -n'                silent
  probe "negative: reset --soft"                  'git reset --soft HEAD~1'     silent
  probe "negative: unrelated command"             'ls -la'                      silent
  ( cd "$tmp" && git checkout -q -- f.txt && rm -f u.txt ) >/dev/null 2>&1
  probe "negative: reset --hard on clean tree"    'git reset --hard'            silent
  rm -rf "$tmp"
  [ "$fail" -eq 0 ] && echo "selftest PASS" || echo "selftest FAIL"
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
