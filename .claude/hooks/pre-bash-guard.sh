#!/usr/bin/env bash
# PreToolUse -> Bash: destructive-command guard. The logic lives in pre-bash-guard.py (a parser,
# not a regex over the raw text); this wrapper keeps the registered hook path stable.
# Exit 0 = allow, Exit 2 = block (reason on stderr is shown to Claude).
# Test: bash .claude/hooks/pre-bash-guard.sh --selftest
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "BLOCKED: pre-bash-guard needs python3 to analyse commands and will not fail open. Install python3 or disable the hook deliberately." >&2
  exit 2
fi
exec python3 "$here/pre-bash-guard.py" "$@"
