#!/usr/bin/env bash
# PreToolUse(Bash): advisory LOW-DISK warning before a disk-hungry build/container command.
#
# WHY: image builds, full-stack bring-up, and `--no-cache` rebuilds consume a lot of disk. When the host
# (or Docker Desktop's VM) disk is low they fail MID-WAY with opaque errors that read like code bugs.
# This warns right before such a command so space can be checked first.
#
# Advisory: ALWAYS exits 0 and never blocks. Delivery: PreToolUse additionalContext (reaches Claude) plus
# systemMessage (shown to the user). stderr of an exit-0 hook is not delivered to either.
#
# Thresholds (GB of free host space): GUARD_DISK_WARN_GB (default 30), GUARD_DISK_CRIT_GB (default 15).
# Test: bash .claude/hooks/pre-bash-disk-guard.sh --selftest
set -uo pipefail

advise() { # $1 = free GB, $2 = threshold GB, $3 = level
  local msg
  if [ "$3" = crit ]; then
    msg="Low disk: ${1} GB free (< ${2} GB) before a disk-hungry build or container command. A full image rebuild is likely to fail part-way with errors that look like code bugs. Check usage first (df -h, docker system df) and free space deliberately; do not run a blanket prune without asking."
  else
    msg="Disk is getting low: ${1} GB free (< ${2} GB) before a build or container command. A full rebuild may not complete. Check usage with df -h and docker system df."
  fi
  jq -n --arg m "$msg" '{systemMessage:$m, hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:$m}}'
}

evaluate() { # $1 = command, $2 = free GB
  echo "$1" | grep -qiE 'docker[ -]?compose[^|]*(build|up)|docker (build|buildx)|podman build|nerdctl build|--no-cache|vagrant up|minikube start|kind create' || return 0
  local warn="${GUARD_DISK_WARN_GB:-30}" crit="${GUARD_DISK_CRIT_GB:-15}"
  if [ "$2" -lt "$crit" ]; then advise "$2" "$crit" crit
  elif [ "$2" -lt "$warn" ]; then advise "$2" "$warn" warn
  fi
  return 0
}

if [ "${1:-}" = "--selftest" ]; then
  fail=0
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; exit 1; }
  chk() { # label want(advise|silent) command freeGB
    out=$(evaluate "$3" "$4")
    case "$2" in
      advise) printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1 && echo "  ok   $1" || { echo "  FAIL $1"; fail=1; } ;;
      silent) [ -z "$out" ] && echo "  ok   $1" || { echo "  FAIL $1 (got output)"; fail=1; } ;;
    esac
  }
  chk "positive: docker build at 5 GB free (critical)"        advise 'docker build -t x .' 5
  chk "positive: compose up at 20 GB free (warning)"          advise 'docker compose up -d' 20
  chk "positive: --no-cache rebuild at 10 GB"                 advise 'docker compose build --no-cache' 10
  chk "negative: enough free space"                           silent 'docker build -t x .' 200
  chk "negative: unrelated command at low disk"               silent 'ls -la' 1
  chk "negative: command that only mentions docker build"     silent 'echo hello' 1
  out=$(evaluate 'docker build .' 5); printf '%s' "$out" | grep -qi 'prune -af' && { echo "  FAIL advice recommends a blanket prune"; fail=1; } || echo "  ok   advice does not recommend a blanket prune"
  [ "$fail" -eq 0 ] && echo "selftest PASS" || echo "selftest FAIL"
  exit "$fail"
fi

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[ "$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)" = "Bash" ] || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)
[ -n "$CMD" ] || exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# df -P -k: column 4 of the data row = available 1024-blocks (portable across macOS/Linux).
avail_kb=$(df -P -k "$ROOT" 2>/dev/null | awk 'NR==2{print $4}')
case "${avail_kb:-}" in ''|*[!0-9]*) exit 0 ;; esac
evaluate "$CMD" $(( avail_kb / 1024 / 1024 ))
exit 0
