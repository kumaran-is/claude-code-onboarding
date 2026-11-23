#!/usr/bin/env bash
# PreToolUse → Bash: catch the zsh "silent zero" class before an ad-hoc command runs.
#
# When the Bash tool's shell is zsh (macOS default), two things differ from bash:
#   1. An unquoted `$VAR` does NOT word-split. `for x in $LIST` runs ONCE over the whole
#      string; `grep pat $PATHS` gets the list as ONE nonexistent path, prints a warning
#      that a pipe hides, and `wc -l` reports 0 — which reads as "nothing found".
#   2. An unquoted glob that matches nothing ABORTS the command ("no matches found").
#      `grep -r pat --include=*.md .` therefore never runs at all, and its silence reads as
#      a clean result.
#
# BLOCKS (exit 2) the two forms that have no legitimate reading:
#   - an unquoted --include=/--exclude= glob;
#   - an unquoted $VAR used as a docker compose service list.
# WARNS (exit 0 + additionalContext) on `for x in $VAR` and on a bare $VAR passed to a
# command that takes a list of paths or names.
# Also WARNS when a command starts with `timeout N` on macOS without a `timeout` binary: zsh prints
# "command not found" into a pipe that hides it, and the empty output reads like a hang or a clean run.
# Not affected: scripts run as `bash file.sh` (real bash word-splits), quoted globs, and the
# explicit zsh list forms ${=VAR}, ${(f)VAR}, "${arr[@]}".
#
# Test: bash .claude/hooks/pre-bash-zsh-split-guard.sh --selftest
set -uo pipefail

# Overridable for the selftest: the real values come from uname and PATH.
os_name() { printf '%s' "${ZSH_GUARD_UNAME:-$(uname -s 2>/dev/null)}"; }
has_timeout() { case "${ZSH_GUARD_HAS_TIMEOUT:-}" in 1) return 0 ;; 0) return 1 ;; esac; command -v timeout >/dev/null 2>&1; }

check() { # $1 = command text; prints the advisory JSON, exits 2 to block
  local cmd="$1" warn=""
  [ -z "$cmd" ] && return 0
  # A script file run by bash/sh word-splits normally.
  grep -qE '^[[:space:]]*(bash|sh)[[:space:]]+[^-[:space:]]' <<<"$cmd" && return 0

  if grep -qE -- '--(include|exclude)(-dir)?=[^"'"'"'[:space:]]*[*?[]' <<<"$cmd"; then
    {
      printf 'BLOCKED: unquoted --include/--exclude glob. zsh expands it before grep sees it:\n'
      printf '  no match in the current directory -> the command aborts ("no matches found") and never runs;\n'
      printf '  a match -> the sweep silently narrows to that one file name.\n'
      printf 'Fix: quote it, e.g. --include="*.md", and pair any zero result with a positive control.\n'
    } >&2
    return 2
  fi

  if grep -qE '(docker[[:space:]]+compose|docker-compose)[^|;&]*[[:space:]](build|up|restart|stop|rm|pull|logs)[[:space:]][^|;&]*\$[A-Za-z_][A-Za-z_0-9]*([[:space:]]|$)' <<<"$cmd"; then
    {
      printf 'BLOCKED: unquoted $VAR used as a docker compose service list. zsh does not word-split it,\n'
      printf 'so the whole string arrives as ONE service name ("no such service: a b c").\n'
      printf 'Fix: list the services literally, or use "${SVCS[@]}" / ${=SVCS}.\n'
    } >&2
    return 2
  fi

  if grep -qE '(^|[;&|[:space:]])for[[:space:]]+[A-Za-z_][A-Za-z_0-9]*[[:space:]]+in[[:space:]]+"?\$[A-Za-z_]' <<<"$cmd"; then
    warn="${warn}- 'for x in \$VAR': in zsh the loop runs once over the whole string. Use literals, \${=VAR} or an array. "
  fi
  # A bare list-named $VAR (…S, …LIST, …ARR; 3+ chars) as an argument of a command that takes a LIST
  # of paths or names. A single-path variable like $D or $ROOT is fine and stays silent.
  if grep -qE '(^|[|;&(]|&&|[[:space:]](do|then|else))[[:space:]]*(grep|ugrep|rg|find|ls|wc|xargs|cat|head|tail|rm|cp|mv|stat|du|git[[:space:]]+(add|diff|log|show|rm))[[:space:]]([^|;&]*[[:space:]])?\$[A-Za-z_][A-Za-z_0-9]+([Ss]|LIST|List|list|ARR|Arr|arr)([[:space:]]|$)' <<<"$cmd"; then
    warn="${warn}- a bare \$VAR passed as a path or name list: in zsh it is ONE argument, so a multi-item list becomes one bogus path and the result can be a silent zero. "
  fi
  if grep -qE '(^|[;&|(]|&&)[[:space:]]*(sudo[[:space:]]+)?timeout[[:space:]]+(-[A-Za-z]+[[:space:]]+)*[0-9]' <<<"$cmd" &&
     [ "$(os_name)" = "Darwin" ] && ! has_timeout; then
    warn="${warn}- 'timeout' is not installed on macOS: the command fails with 'command not found' and the pipeline prints nothing, which reads like a hang or a clean run. Use the Bash tool's timeout parameter, or gtimeout (coreutils). "
  fi
  if [ -n "$warn" ]; then
    jq -n --arg m "zsh-split advisory: ${warn}Never trust a zero-findings result until a positive control matched in the same session." \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
  fi
  return 0
}

selftest() {
  local fail=0 c rc out
  bash -n "$0" && echo "  ok   bash -n" || { echo "  FAIL bash -n"; fail=1; }
  probe() { # expected(block|warn|pass) command
    out=$(check "$2" 2>/dev/null); rc=$?
    case "$1" in
      block) [ "$rc" -eq 2 ] && echo "  ok   block: $2" || { echo "  FAIL expected block (rc=$rc): $2"; fail=1; } ;;
      warn)  [ "$rc" -eq 0 ] && printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext|test("zsh-split")' >/dev/null 2>&1 \
               && echo "  ok   warn:  $2" || { echo "  FAIL expected warn: $2"; fail=1; } ;;
      pass)  [ "$rc" -eq 0 ] && [ -z "$out" ] && echo "  ok   pass:  $2" || { echo "  FAIL expected silence (rc=$rc): $2"; fail=1; } ;;
    esac
  }
  probe block 'grep -rn foo --include=*.md .'
  probe block 'grep -rln x --exclude-dir=node_* src'
  probe block 'grep -rn x --include=v?.md .'
  probe block 'docker compose build $SVCS'
  probe block 'docker-compose up -d $SERVICES'
  probe warn  'for f in $FILES; do wc -l "$f"; done'
  probe warn  'grep -n TODO $PATHS | wc -l'
  probe warn  'cd /x && ls $DIRS'
  probe warn  'if true; then grep -c x $PATHS | wc -l; fi'
  probe pass  'grep -rn foo --include="*.md" .'
  probe pass  "grep -rn foo --include='*.ts' src"
  probe pass  'docker compose build "${SVCS[@]}"'
  probe pass  'for f in ${=FILES}; do echo "$f"; done'
  probe pass  'for f in ${=FILES}; do grep -n x $f | wc -l; done'
  probe warn  'grep -n x ${=PATHS} $MOREFILES | wc -l'
  probe pass  'grep -n x "$FILE"'
  probe pass  'cd $D && git status'
  probe pass  'bash scripts/run.sh $ARGS'
  probe pass  'git commit -m "$MSG"'
  probe pass  'ls src/app'
  probe pass  'ls -la $S | head -30'
  probe pass  'cd $ROOT && ls $DIR'
  export ZSH_GUARD_UNAME=Darwin ZSH_GUARD_HAS_TIMEOUT=0
  probe warn  'timeout 30 pytest -q'
  probe warn  'cd app && timeout 120 npm test 2>&1 | tail -5'
  probe pass  'gtimeout 30 pytest -q'
  probe pass  'echo timeout'
  probe pass  'git commit -m "raise timeout 30 to 60"'
  ZSH_GUARD_HAS_TIMEOUT=1; probe pass 'timeout 30 pytest -q'
  ZSH_GUARD_UNAME=Linux ZSH_GUARD_HAS_TIMEOUT=0; probe pass 'timeout 30 pytest -q'
  unset ZSH_GUARD_UNAME ZSH_GUARD_HAS_TIMEOUT
  # The hook entry point reads the PreToolUse JSON from stdin.
  out=$(printf '{"tool_input":{"command":"grep -r a --include=*.md ."}}' | bash "$0" 2>/dev/null); rc=$?
  [ "$rc" -eq 2 ] && echo "  ok   stdin entry point blocks" || { echo "  FAIL stdin entry point (rc=$rc)"; fail=1; }
  [ "$fail" -eq 0 ] && echo "selftest PASS" || echo "selftest FAIL"
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
cmd=$(jq -r '.tool_input.command // ""' <<<"$input" 2>/dev/null) || exit 0
check "$cmd"
exit $?
