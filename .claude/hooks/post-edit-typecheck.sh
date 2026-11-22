#!/usr/bin/env bash
# PostToolUse -> Write|Edit: type-check the edited file and report errors IN that file.
#   *.ts/*.tsx : project-local tsc (node_modules/.bin/tsc --noEmit) from the nearest tsconfig.json
#   *.dart     : dart analyze <file>
#   *.py       : mypy or pyright, ONLY when the nearest pyproject.toml configures one
#                ([tool.mypy] / [tool.pyright]); otherwise silent (a deliberate project choice).
#
# Contract (see .claude/rules/hook-and-gate-authoring.md):
#   - Always exit 0 (advisory). Fails open when jq or the checker is missing.
#   - Each checker's OWN exit status is captured (`out=$(cmd); rc=$?`), never a pipe's.
#   - Output is built with `jq -n --arg`, so backslashes/quotes/tabs in compiler messages stay valid JSON.
#   - Delivered as PostToolUse additionalContext (stderr of an exit-0 hook is not shown to the model).
# Cost note: tsc and mypy check the whole project/import graph, so this can take seconds per edit.
# Test: bash .claude/hooks/post-edit-typecheck.sh --selftest
set -uo pipefail

MAX_LINES=5

nearest_up() { # $1 start dir, $2 file name -> echo dir containing it
  local d="$1"
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    [ -f "$d/$2" ] && { printf '%s' "$d"; return 0; }
    d=$(dirname "$d")
  done
  return 1
}

check_ts() { # $1 file
  local file="$1" root out rc lines
  root=$(nearest_up "$(dirname "$file")" tsconfig.json) || return 0
  [ -x "$root/node_modules/.bin/tsc" ] || return 0
  out=$(cd "$root" && node_modules/.bin/tsc --noEmit --pretty false 2>&1); rc=$?
  [ "$rc" -eq 0 ] && return 0
  lines=$(printf '%s\n' "$out" | grep -F "$(basename "$file")" | head -"$MAX_LINES")
  [ -n "$lines" ] && printf 'TypeScript type errors in edited file %s:\n%s' "$file" "$lines"
  return 0
}

check_dart() { # $1 file
  local file="$1" out lines
  command -v dart >/dev/null 2>&1 || return 0
  out=$(dart analyze "$file" 2>&1); : "$?"
  lines=$(printf '%s\n' "$out" | grep -E '^[[:space:]]*(error|warning)[[:space:]]+-' | head -"$MAX_LINES")
  [ -n "$lines" ] && printf 'Dart analysis issues in edited file %s:\n%s' "$file" "$lines"
  return 0
}

check_py() { # $1 file
  local file="$1" root out rc lines tool cmd=()
  root=$(nearest_up "$(dirname "$file")" pyproject.toml) || return 0
  if grep -qE '^\[tool\.mypy' "$root/pyproject.toml" 2>/dev/null; then tool=mypy
  elif grep -qE '^\[tool\.pyright' "$root/pyproject.toml" 2>/dev/null; then tool=pyright
  else return 0; fi
  if [ -x "$root/.venv/bin/$tool" ]; then cmd=("$root/.venv/bin/$tool")
  elif command -v "$tool" >/dev/null 2>&1; then cmd=("$tool")
  elif command -v uv >/dev/null 2>&1; then cmd=(uv run --no-sync "$tool")
  else
    printf 'Python type check: pyproject.toml configures %s but it was not found (PATH, .venv, uv); %s was NOT type-checked.' "$tool" "$file"
    return 0
  fi
  out=$(cd "$root" && "${cmd[@]}" "$file" 2>&1); rc=$?
  [ "$rc" -eq 0 ] && return 0
  lines=$(printf '%s\n' "$out" | grep -F "$(basename "$file")" | head -"$MAX_LINES")
  if [ -z "$lines" ] && [ "$rc" -ge 2 ]; then # crash / config error with no per-file line: surface it
    lines=$(printf '%s\n' "$out" | head -"$MAX_LINES")
    printf '%s could not run on %s (exit %s):\n%s' "$tool" "$file" "$rc" "$lines"
    return 0
  fi
  [ -n "$lines" ] && printf '%s errors in edited file %s:\n%s' "$tool" "$file" "$lines"
  return 0
}

run_hook() {
  local input file msg=""
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  case "$file" in
    *.ts|*.tsx) msg=$(check_ts "$file") ;;
    *.dart) msg=$(check_dart "$file") ;;
    *.py) msg=$(check_py "$file") ;;
  esac
  if [ -n "$msg" ]; then
    jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  fi
  return 0
}

selftest() {
  local self fail=0 tmp out bindir ts py nocfg
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  bindir="$tmp/bin"; mkdir -p "$bindir"
  for t in jq cat head printf dirname basename grep sed pwd; do
    p=$(command -v "$t" 2>/dev/null) && [ -x "$p" ] && ln -s "$p" "$bindir/$t"
  done
  run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | PATH="$2:$bindir" /bin/bash "$self" 2>/dev/null; }

  # --- TypeScript: fake local tsc that reports an error (with a backslash and quotation marks) and exits 2.
  ts="$tmp/ts"; mkdir -p "$ts/node_modules/.bin" "$ts/src"
  printf '{}' > "$ts/tsconfig.json"; printf 'export const a = 1;\n' > "$ts/src/a.ts"; printf 'export const b = 1;\n' > "$ts/src/b.ts"
  printf '#!/bin/sh\necho "src/a.ts(1,1): error TS2322: Type \\"x\\" C:\\\\dir not assignable"\necho "src/other.ts(2,2): error TS1: elsewhere"\nexit 2\n' > "$ts/node_modules/.bin/tsc"
  chmod +x "$ts/node_modules/.bin/tsc"
  out=$(run "$ts/src/a.ts" "")
  if printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("TS2322")' >/dev/null 2>&1; then
    echo "  ok   positive: tsc error in the edited file reported (valid JSON despite backslash and quotation marks)"; else echo "  FAIL ts positive (got: $out)"; fail=1; fi
  if printf '%s' "$out" | grep -q "elsewhere"; then echo "  FAIL errors from other files leaked"; fail=1; else echo "  ok   negative: errors in other files are not reported"; fi
  out=$(run "$ts/src/b.ts" "")
  if [ -z "$out" ]; then echo "  ok   negative: no error in the edited file is silent"; else echo "  FAIL ts negative (got: $out)"; fail=1; fi

  # --- Dart: fake dart; error count must work with zero matches (the old arithmetic bug).
  printf 'void main(){}\n' > "$tmp/a.dart"
  mkdir -p "$tmp/d1" "$tmp/d0"
  printf '#!/bin/sh\necho "Analyzing a.dart..."\necho "  error - a.dart:1:1 - Undefined name x - undefined_identifier"\necho "1 issue found."\nexit 3\n' > "$tmp/d1/dart"
  printf '#!/bin/sh\necho "Analyzing a.dart..."\necho "No issues found!"\nexit 0\n' > "$tmp/d0/dart"
  chmod +x "$tmp/d1/dart" "$tmp/d0/dart"
  out=$(run "$tmp/a.dart" "$tmp/d1")
  if printf '%s' "$out" | grep -q "undefined_identifier"; then echo "  ok   positive: dart error reported"; else echo "  FAIL dart positive (got: $out)"; fail=1; fi
  out=$(run "$tmp/a.dart" "$tmp/d0")
  if [ -z "$out" ]; then echo "  ok   negative: dart clean file silent (zero-match path)"; else echo "  FAIL dart negative (got: $out)"; fail=1; fi

  # --- Python: mypy configured vs not configured.
  py="$tmp/py"; mkdir -p "$py/app" "$tmp/m1" "$tmp/m0"
  printf '[tool.mypy]\nstrict = true\n' > "$py/pyproject.toml"; printf 'x: int = "s"\n' > "$py/app/m.py"
  printf '#!/bin/sh\necho "app/m.py:1: error: Incompatible types in assignment  [assignment]"\necho "Found 1 error in 1 file"\nexit 1\n' > "$tmp/m1/mypy"
  printf '#!/bin/sh\necho "Success: no issues found in 1 source file"\nexit 0\n' > "$tmp/m0/mypy"
  chmod +x "$tmp/m1/mypy" "$tmp/m0/mypy"
  out=$(run "$py/app/m.py" "$tmp/m1")
  if printf '%s' "$out" | grep -q "assignment"; then echo "  ok   positive: mypy error reported"; else echo "  FAIL mypy positive (got: $out)"; fail=1; fi
  out=$(run "$py/app/m.py" "$tmp/m0")
  if [ -z "$out" ]; then echo "  ok   negative: mypy clean is silent"; else echo "  FAIL mypy negative (got: $out)"; fail=1; fi
  out=$(run "$py/app/m.py" "")
  if printf '%s' "$out" | grep -q "was NOT type-checked"; then echo "  ok   positive: configured but missing checker is reported"; else echo "  FAIL missing checker hidden (got: $out)"; fail=1; fi
  nocfg="$tmp/nocfg"; mkdir -p "$nocfg"; printf '[project]\nname="x"\n' > "$nocfg/pyproject.toml"; printf 'x: int = "s"\n' > "$nocfg/m.py"
  out=$(run "$nocfg/m.py" "$tmp/m1")
  if [ -z "$out" ]; then echo "  ok   negative: no type checker configured -> silent"; else echo "  FAIL unconfigured project not silent (got: $out)"; fail=1; fi

  printf 'hi\n' > "$tmp/a.txt"
  out=$(run "$tmp/a.txt" "$tmp/m1"); rc=$?
  if [ -z "$out" ] && [ "$rc" -eq 0 ]; then echo "  ok   negative: other file types ignored"; else echo "  FAIL other types"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
