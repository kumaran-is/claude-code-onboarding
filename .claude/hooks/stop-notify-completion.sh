#!/bin/bash
# Hook: Notify Completion — desktop notification when Claude stops
# Event: Stop
#
# Sends a desktop notification when a Claude session/task completes.
# Useful for long-running tasks (Ralph loop, agent teams, builds).
#
# Supports: macOS (osascript), Linux (notify-send)
# Disable: set CLAUDE_NOTIFY_DISABLE=1

# Test: bash .claude/hooks/stop-notify-completion.sh --selftest
set -uo pipefail

if [ "${1:-}" = "--selftest" ]; then
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  bash -n "$self" || { echo "  FAIL does not parse"; exit 1; }
  echo "  ok   parses (bash -n)"
  stub=$(mktemp -d) || exit 1
  printf '#!/bin/sh\nfor a in "$@"; do printf "%%s\\n" "$a"; done > "%s/osa.args"\n' "$stub" > "$stub/osascript"
  printf '#!/bin/sh\necho Darwin\n' > "$stub/uname"; printf '#!/bin/sh\nexit 0\n' > "$stub/afplay"
  chmod +x "$stub/osascript" "$stub/uname" "$stub/afplay"
  echo '{"reason":"done\" & do shell script \"touch /tmp/x\" & \""}' | PATH="$stub:$PATH" "$BASH" "$self"
  fail=0
  if grep -qF 'display notification (item 1 of argv)' "$stub/osa.args" && grep -qF 'do shell script' "$stub/osa.args" &&
     ! grep -F 'display notification' "$stub/osa.args" | grep -qF 'do shell script'; then
    echo "  ok   positive: message with quotes is passed as argv data, not AppleScript source"
  else echo "  FAIL osascript args: $(cat "$stub/osa.args" 2>/dev/null)"; fail=1; fi
  CLAUDE_NOTIFY_DISABLE=1 PATH="$stub:$PATH" "$BASH" "$self" < /dev/null; rm -f "$stub/osa.args"
  CLAUDE_NOTIFY_DISABLE=1 PATH="$stub:$PATH" "$BASH" "$self" < /dev/null
  if [ ! -f "$stub/osa.args" ]; then echo "  ok   negative: CLAUDE_NOTIFY_DISABLE=1 sends nothing"; else echo "  FAIL notified while disabled"; fail=1; fi
  rm -rf "$stub"
  [ "$fail" -eq 0 ] && echo "selftest PASS" || echo "selftest FAIL"
  exit "$fail"
fi

# Skip if disabled
if [[ "${CLAUDE_NOTIFY_DISABLE:-0}" == "1" ]]; then
  exit 0
fi

TITLE="Claude Code"
MESSAGE="Task completed"

# Read stop reason from stdin if available
INPUT=$(cat 2>/dev/null || echo "{}")
STOP_REASON=$(echo "$INPUT" | jq -r '.reason // ""' 2>/dev/null || echo "")

if [[ -n "$STOP_REASON" ]]; then
  MESSAGE="$STOP_REASON"
fi

# macOS notification
if [[ "$(uname)" == "Darwin" ]]; then
  # Text goes in as argv, never spliced into the AppleScript source (a quote would run as code).
  osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' -e 'end run' \
    "$MESSAGE" "$TITLE" 2>/dev/null || true

  # Play completion sound (non-blocking)
  if [[ -f "/System/Library/Sounds/Hero.aiff" ]]; then
    afplay "/System/Library/Sounds/Hero.aiff" &
  fi
  exit 0
fi

# Linux notification
if command -v notify-send &>/dev/null; then
  notify-send "$TITLE" "$MESSAGE" --expire-time=5000 2>/dev/null || true
  exit 0
fi

# Fallback: terminal bell
printf '\a'
exit 0
