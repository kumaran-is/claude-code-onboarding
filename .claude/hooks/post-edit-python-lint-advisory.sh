#!/usr/bin/env bash
# PostToolUse -> Write|Edit: Python lint advisory (check-only, never blocks, never edits files).
#
# What it does for an edited *.py file (tests, conftest.py, alembic/versions, venvs are skipped):
#   1. `ruff check --no-fix` with the project's own config (nearest pyproject.toml / ruff.toml),
#      plus F401/F811/F841 (unused import / redefinition / unused variable) as extra signal.
#   2. A small grep for hardcoded-config shapes: os.getenv("X", "literal"), os.environ.get("X", "literal"),
#      verify=False.
#   Findings are delivered as ONE PostToolUse additionalContext message (first lines only).
#
# Contract (see .claude/rules/hook-and-gate-authoring.md):
#   - Always exit 0. Fails open when jq or ruff is missing (ruff-missing is noted once per project).
#   - Uses ruff from PATH or the project's .venv/bin/ruff only. Never `uv run`: on a project without a
#     .venv that creates one (and may download a Python) as a side effect of an edit.
#   - NEVER passes --fix: an auto-fix pass can delete an import added in one edit before the edit that
#     uses it lands (F401), and can strip quotes inside Literal[...] (UP037).
#   - stderr of an exit-0 hook is not shown to the model; additionalContext JSON is.
# Test: bash .claude/hooks/post-edit-python-lint-advisory.sh --selftest
set -uo pipefail

MAX_LINES=12

note_missing() { # once per project
  local key marker
  key=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | cksum | awk '{print $1}')
  marker="${TMPDIR:-/tmp}/claude-pylint-advisory-missing-$key"
  [ -e "$marker" ] && return 0
  : > "$marker" 2>/dev/null || true
  printf '%s' "python lint advisory: ruff not found (not on PATH, no .venv/bin/ruff), so edited Python files are NOT being linted. Run \`uv sync\` (ruff in the dev group) or run ruff manually before committing."
}

skip_path() { # echo 0 if the file should be skipped
  case "$1" in
    */.venv/*|*/venv/*|*/site-packages/*|*/node_modules/*|*/alembic/versions/*|*/migrations/versions/*) return 0 ;;
    */tests/*|*/test/*|*/conftest.py|conftest.py|*/test_*.py|*_test.py) return 0 ;;
  esac
  return 1
}

find_root() { # nearest dir with pyproject.toml / ruff.toml / .ruff.toml, else the file's dir
  local dir
  dir=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 1
  local d="$dir"
  while [ "$d" != "/" ] && [ -n "$d" ]; do
    if [ -f "$d/pyproject.toml" ] || [ -f "$d/ruff.toml" ] || [ -f "$d/.ruff.toml" ]; then
      printf '%s' "$d"; return 0
    fi
    d=$(dirname "$d")
  done
  printf '%s' "$dir"
}

lint_message() { # $1 absolute file; prints message (possibly empty)
  local file="$1" root out rc msg="" ruff_cmd ext_sel
  root=$(find_root "$file") || return 0

  if command -v ruff >/dev/null 2>&1; then ruff_cmd=(ruff)
  elif [ -x "$root/.venv/bin/ruff" ]; then ruff_cmd=("$root/.venv/bin/ruff")
  else
    note_missing
    return 0
  fi

  ext_sel="F401,F811,F841"
  [ "$(basename "$file")" = "__init__.py" ] && ext_sel="F811,F841" # re-exports are intentional there

  out=$(cd "$root" && "${ruff_cmd[@]}" check --no-fix --no-cache --force-exclude \
        --output-format=concise --extend-select "$ext_sel" "$file" 2>&1)
  rc=$?
  case "$rc" in
    0) ;;
    1) msg="python lint advisory: ruff reported findings in $file (check-only; nothing was changed):
$(printf '%s\n' "$out" | grep -vE '^(Found [0-9]+ error|\[\*\] [0-9]+ fixable|No fixes available)' | head -"$MAX_LINES")" ;;
    *) msg="python lint advisory: ruff could not check $file (exit $rc):
$(printf '%s\n' "$out" | head -5)" ;;
  esac

  local cfg=""
  cfg=$(grep -nE "(getenv|environ\.get)\([^)]*,[[:space:]]*['\"][^'\"]+['\"][[:space:]]*\)|verify[[:space:]]*=[[:space:]]*False" "$file" 2>/dev/null | head -5)
  if [ -n "$cfg" ]; then
    msg="${msg}${msg:+
}python lint advisory: possible hardcoded config (a literal fallback for an env var, or TLS verification off). Confirm each is intentional, non-secret and not environment-specific:
$cfg"
  fi
  printf '%s' "$msg"
}

run_hook() {
  local input file msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  case "$file" in *.py) ;; *) return 0 ;; esac
  [ -f "$file" ] || return 0
  skip_path "$file" && return 0
  msg=$(lint_message "$file")
  if [ -n "$msg" ]; then
    jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  fi
  return 0
}

selftest() {
  local self fail=0 tmp out bindir proj
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  proj="$tmp/proj"; mkdir -p "$proj/app" "$proj/tests" "$proj/alembic/versions"
  printf '[project]\nname="x"\n' > "$proj/pyproject.toml"
  printf 'import os\nx = os.getenv("API_URL", "http://localhost:9")\n' > "$proj/app/bad.py"
  printf 'x = 1\n' > "$proj/app/clean.py"
  cp "$proj/app/bad.py" "$proj/tests/test_bad.py"
  cp "$proj/app/bad.py" "$proj/alembic/versions/001_bad.py"
  printf 'import os\n' > "$proj/app/__init__.py"

  bindir="$tmp/bin"; mkdir -p "$bindir"
  for t in jq cksum awk cat head printf dirname basename mkdir cd grep sed pwd; do
    p=$(command -v "$t" 2>/dev/null) && [ -x "$p" ] && ln -s "$p" "$bindir/$t"
  done
  run() { # $1 file, $2 extra PATH prefix, $3 project tag
    printf '{"tool_input":{"file_path":"%s"}}' "$1" | TMPDIR="$tmp" CLAUDE_PROJECT_DIR="$tmp/$3" PATH="$2:$bindir" /bin/bash "$self" 2>/dev/null
  }

  # Fake ruff: prints a finding and exits 1 (positive), exits 0 silently (negative), exits 2 (tool error).
  mkdir -p "$tmp/f1" "$tmp/f0" "$tmp/f2"
  printf '#!/bin/sh\necho "app/bad.py:1:8: F401 [*] `os` imported but unused"\necho "Found 1 error."\nexit 1\n' > "$tmp/f1/ruff"
  printf '#!/bin/sh\nexit 0\n' > "$tmp/f0/ruff"
  printf '#!/bin/sh\necho "ruff failed: bad config" >&2\nexit 2\n' > "$tmp/f2/ruff"
  chmod +x "$tmp/f1/ruff" "$tmp/f0/ruff" "$tmp/f2/ruff"
  # Fake ruff that records its argv so we can prove --fix is never passed.
  mkdir -p "$tmp/fa"; printf '#!/bin/sh\necho "$@" > "%s/argv.txt"\nexit 0\n' "$tmp" > "$tmp/fa/ruff"; chmod +x "$tmp/fa/ruff"

  out=$(run "$proj/app/clean.py" "$tmp/f1" p1)
  if printf '%s' "$out" | grep -q "F401" && printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1; then
    echo "  ok   positive: ruff finding delivered as additionalContext JSON"; else echo "  FAIL finding not delivered (got: $out)"; fail=1; fi
  if printf '%s' "$out" | grep -q "Found 1 error"; then echo "  FAIL summary line not filtered"; fail=1; else echo "  ok   negative: ruff summary noise filtered"; fi

  out=$(run "$proj/app/clean.py" "$tmp/f0" p2)
  if [ -z "$out" ]; then echo "  ok   negative: clean file is silent"; else echo "  FAIL clean file not silent (got: $out)"; fail=1; fi

  out=$(run "$proj/app/clean.py" "$tmp/f2" p3)
  if printf '%s' "$out" | grep -q "could not check"; then echo "  ok   positive: ruff tool error is reported, not treated as clean"; else echo "  FAIL ruff error hidden (got: $out)"; fail=1; fi

  out=$(run "$proj/app/bad.py" "$tmp/f0" p4)
  if printf '%s' "$out" | grep -q "hardcoded config"; then echo "  ok   positive: getenv literal fallback flagged"; else echo "  FAIL hardcoded config not flagged (got: $out)"; fail=1; fi

  out=$(run "$proj/tests/test_bad.py" "$tmp/f1" p5)
  if [ -z "$out" ]; then echo "  ok   negative: test files are skipped"; else echo "  FAIL test file not skipped (got: $out)"; fail=1; fi
  out=$(run "$proj/alembic/versions/001_bad.py" "$tmp/f1" p5)
  if [ -z "$out" ]; then echo "  ok   negative: migration versions are skipped"; else echo "  FAIL migration not skipped (got: $out)"; fail=1; fi

  run "$proj/app/clean.py" "$tmp/fa" p6 >/dev/null
  if [ -f "$tmp/argv.txt" ] && ! grep -q -- '--fix' "$tmp/argv.txt" && grep -q -- '--no-fix' "$tmp/argv.txt"; then
    echo "  ok   negative: --fix is never passed (argv: $(cat "$tmp/argv.txt"))"; else echo "  FAIL --fix control (argv: $(cat "$tmp/argv.txt" 2>/dev/null))"; fail=1; fi
  if grep -q -- '--extend-select F401,F811,F841' "$tmp/argv.txt" 2>/dev/null; then echo "  ok   positive: dead-code rules added"; else echo "  FAIL dead-code rules missing"; fail=1; fi
  run "$proj/app/__init__.py" "$tmp/fa" p6 >/dev/null
  if grep -q -- '--extend-select F811,F841 ' "$tmp/argv.txt" 2>/dev/null; then echo "  ok   negative: F401 not forced on __init__.py"; else echo "  FAIL __init__ handling"; fail=1; fi

  # Fake uv that records any call: the hook must never fall back to `uv run` (it creates a .venv).
  mkdir -p "$tmp/fu"; printf '#!/bin/sh\necho "$@" > "%s/uv-called"\nexit 0\n' "$tmp" > "$tmp/fu/uv"; chmod +x "$tmp/fu/uv"
  out=$(run "$proj/app/clean.py" "$tmp/fu" p7)
  if printf '%s' "$out" | grep -q "ruff not found"; then echo "  ok   positive: missing ruff reported"; else echo "  FAIL missing ruff not reported (got: $out)"; fail=1; fi
  if [ ! -e "$tmp/uv-called" ] && [ ! -d "$proj/.venv" ]; then echo "  ok   negative: uv never invoked, no .venv created"; else echo "  FAIL uv was invoked ($(cat "$tmp/uv-called" 2>/dev/null))"; fail=1; fi
  out=$(run "$proj/app/clean.py" "" p7)
  if [ -z "$out" ]; then echo "  ok   negative: missing-ruff note is throttled"; else echo "  FAIL not throttled (got: $out)"; fail=1; fi

  printf 'hi\n' > "$tmp/a.txt"
  out=$(run "$tmp/a.txt" "$tmp/f1" p8); rc=$?
  if [ -z "$out" ] && [ "$rc" -eq 0 ]; then echo "  ok   negative: non-Python files ignored"; else echo "  FAIL non-python (rc=$rc out=$out)"; fail=1; fi

  # Optional end-to-end control against a real ruff, if one is available.
  if command -v ruff >/dev/null 2>&1; then
    printf 'import os\n\n\ndef f():\n    y = 1\n' > "$proj/app/real.py"
    out=$(run "$proj/app/real.py" "$(dirname "$(command -v ruff)")" p9)
    if printf '%s' "$out" | grep -q "F401" && printf '%s' "$out" | grep -q "F841" && [ "$(cat "$proj/app/real.py" | head -1)" = "import os" ]; then
      echo "  ok   real ruff: F401+F841 reported and the file is untouched"; else echo "  FAIL real ruff control (got: $out)"; fail=1; fi
  else
    echo "  skip real-ruff control (ruff not on PATH)"
  fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
