#!/usr/bin/env bash
# PostToolUse -> Write|Edit: auto-format the edited file with the language's formatter.
#
# Behavior (explicit, never silent):
#   - Formatting is best-effort and NEVER blocks: always exit 0.
#   - Formatter present and succeeds  -> nothing printed.
#   - Formatter present but FAILS (e.g. a syntax error it cannot parse) -> reported to Claude
#     via PostToolUse additionalContext JSON, with the first lines of the formatter output.
#   - Formatter MISSING for a file type that expects one (dart, python) -> reported once per
#     tool per project (throttled with a marker file in $TMPDIR) instead of silently doing
#     nothing. A hook that quietly no-ops is indistinguishable from one that works.
#   - JS/TS/JSON/CSS/HTML: only the project-local Prettier is used; if the project has none
#     this is a deliberate choice, so it stays quiet.
#   - jq missing -> one stderr line, no formatting (cannot read the payload).
# Note: stderr of an exit-0 hook is not shown to the model; additionalContext JSON is.
# Test: bash .claude/hooks/post-edit-format.sh --selftest
set -uo pipefail

MSGS=""
add_msg() { MSGS="${MSGS}${MSGS:+
}$1"; }

# Report a missing tool at most once per tool per project.
note_missing() { # $1 tool, $2 hint
  local key marker
  key=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | cksum | awk '{print $1}')
  marker="${TMPDIR:-/tmp}/claude-format-missing-$1-$key"
  [ -e "$marker" ] && return 0
  : > "$marker" 2>/dev/null || true
  add_msg "format hook: '$1' not found on PATH, so $2 files are NOT being auto-formatted. Install it or run the formatter manually before committing."
}

# Run a formatter; record its output as a message if it fails.
run_fmt() { # $1 label, rest = command
  local label="$1" out
  shift
  if ! out=$("$@" 2>&1); then
    add_msg "format hook: $label failed on $FILE (file left as-is):
$(printf '%s\n' "$out" | head -5)"
  fi
}

format_file() {
  case "$FILE" in
    *.ts|*.tsx|*.js|*.jsx|*.html|*.css|*.scss|*.json)
      if [ -x node_modules/.bin/prettier ]; then
        run_fmt "prettier" node_modules/.bin/prettier --write "$FILE"
      fi ;;
    *.dart)
      if command -v dart >/dev/null 2>&1; then
        run_fmt "dart format" dart format "$FILE"
      else
        note_missing dart "Dart"
      fi ;;
    *.py)
      if command -v ruff >/dev/null 2>&1; then
        run_fmt "ruff format" ruff format "$FILE"
      elif command -v black >/dev/null 2>&1; then
        run_fmt "black" black --quiet "$FILE"
      else
        note_missing ruff "Python (neither ruff nor black)"
      fi ;;
    # Java: formatting is handled by the build (e.g. spotless:apply); too slow per edit.
  esac
}

run_hook() {
  local input
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "format hook: jq not found; auto-format skipped" >&2; return 0; }
  FILE=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || FILE=""
  [ -n "$FILE" ] && [ -f "$FILE" ] || return 0
  format_file
  if [ -n "$MSGS" ]; then
    jq -n --arg m "$MSGS" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  fi
  return 0
}

selftest() {
  local self fail=0 tmp out bindir
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  printf 'void main(){print( 1 );}\n' > "$tmp/a.dart"
  printf 'x = 1\n' > "$tmp/a.py"

  # Positive: formatter missing -> reported (PATH holds only jq/coreutils symlinks, no dart/ruff/black).
  bindir="$tmp/bin"; mkdir -p "$bindir"
  for t in jq cksum awk cat head printf dirname basename mkdir touch; do
    p=$(command -v "$t" 2>/dev/null) && [ -x "$p" ] && ln -s "$p" "$bindir/$t"
  done
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/a.dart" | TMPDIR="$tmp" CLAUDE_PROJECT_DIR="$tmp/p1" PATH="$bindir" /bin/bash "$self" 2>/dev/null)
  if printf '%s' "$out" | grep -q "not found on PATH"; then echo "  ok   positive: missing dart is reported"; else echo "  FAIL missing dart not reported (got: $out)"; fail=1; fi

  # Negative: throttled — second identical miss in the same project stays quiet.
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/a.dart" | TMPDIR="$tmp" CLAUDE_PROJECT_DIR="$tmp/p1" PATH="$bindir" /bin/bash "$self" 2>/dev/null)
  if [ -z "$out" ]; then echo "  ok   negative: repeat miss is throttled"; else echo "  FAIL repeat miss not throttled (got: $out)"; fail=1; fi

  # Positive: formatter present but failing -> reported.
  mkdir -p "$tmp/fake"; printf '#!/bin/sh\necho "boom: cannot parse" >&2\nexit 65\n' > "$tmp/fake/dart"; chmod +x "$tmp/fake/dart"
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/a.dart" | TMPDIR="$tmp" CLAUDE_PROJECT_DIR="$tmp/p2" PATH="$tmp/fake:$bindir" /bin/bash "$self" 2>/dev/null)
  if printf '%s' "$out" | grep -q "dart format failed"; then echo "  ok   positive: formatter failure is reported"; else echo "  FAIL formatter failure not reported (got: $out)"; fail=1; fi

  # Negative: formatter succeeds -> silent.
  printf '#!/bin/sh\nexit 0\n' > "$tmp/fake/dart"
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/a.dart" | TMPDIR="$tmp" CLAUDE_PROJECT_DIR="$tmp/p3" PATH="$tmp/fake:$bindir" /bin/bash "$self" 2>/dev/null)
  if [ -z "$out" ]; then echo "  ok   negative: successful format is silent"; else echo "  FAIL success not silent (got: $out)"; fail=1; fi

  # Negative: unknown file type and missing file are silent and exit 0.
  printf 'hi\n' > "$tmp/a.txt"
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/a.txt" | PATH="$bindir" /bin/bash "$self" 2>/dev/null); rc=$?
  if [ -z "$out" ] && [ "$rc" -eq 0 ]; then echo "  ok   negative: other file types are ignored"; else echo "  FAIL other types (rc=$rc out=$out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
