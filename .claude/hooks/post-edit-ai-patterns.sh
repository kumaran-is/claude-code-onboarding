#!/usr/bin/env bash
# post-edit-ai-patterns.sh — PostToolUse (Write|Edit)
# Scans the edited file for AI-specific code pathologies and reports them to the model.
#   1. Unresolvable relative imports in TS/JS (file not on disk)
#   2. Placeholder / stub implementations (TODO: implement, throw not implemented, ...)
#   3. Mock / test-framework code in non-test files
#   4. Hedging comments left in code
#   5. Placeholder values ("changeme", "YOUR_API_KEY", ...)
#
# Contract (see .claude/rules/hook-and-gate-authoring.md):
#   - Advisory only: always exit 0; never blocks a write. Fails open when jq is missing.
#   - Delivered as PostToolUse additionalContext JSON (stdout/stderr text of an exit-0 hook is NOT shown
#     to the model).
#   - POSIX tools only (BSD grep/sed on macOS): no `grep -P`, no `set -e`.
#   - `raise NotImplementedError` is NOT flagged when it sits under @abstractmethod (a legitimate pattern).
# Test: bash .claude/hooks/post-edit-ai-patterns.sh --selftest
set -uo pipefail

MAX_FINDINGS=15

is_test_path() {
  printf '%s' "$1" | grep -qiE '(^|/)(tests?|__tests__|__mocks__|fixtures|e2e)/|(\.|_)(test|spec)\.[a-z]+$|(^|/)test_[^/]*$|(^|/)conftest\.py$'
}

# grep -in over a literal-ish ERE; prints up to $3 lines as "<tag>: <line>"
scan() { # $1 file, $2 ERE, $3 max lines, $4 tag
  grep -inE "$2" "$1" 2>/dev/null | head -"$3" | while IFS= read -r m; do printf '%s: %s\n' "$4" "$m"; done
}

check_imports() { # $1 file; TS/JS relative imports that resolve to nothing on disk
  local file="$1" dir path resolved base
  dir=$(dirname "$file")
  grep -nE "from[[:space:]]+['\"]\.\.?/" "$file" 2>/dev/null | while IFS= read -r line; do
    path=$(printf '%s' "$line" | sed -nE "s/.*from[[:space:]]+['\"](\.\.?\/[^'\"]*)['\"].*/\1/p" | head -1)
    [ -n "$path" ] || continue
    resolved="$dir/$path"
    base="${resolved%.js}"; base="${base%.mjs}"; base="${base%.jsx}"
    if [ ! -f "$resolved" ] && [ ! -f "$resolved.ts" ] && [ ! -f "$resolved.tsx" ] && [ ! -f "$resolved.js" ] \
       && [ ! -f "$resolved.jsx" ] && [ ! -f "$resolved.mjs" ] && [ ! -f "$resolved/index.ts" ] \
       && [ ! -f "$resolved/index.tsx" ] && [ ! -f "$resolved/index.js" ] \
       && [ ! -f "$base.ts" ] && [ ! -f "$base.tsx" ] && [ ! -f "$base.jsx" ]; then
      printf "HALLUCINATED_IMPORT: '%s' referenced but file not found on disk\n" "$path"
    fi
  done
}

abstract_not_implemented() { # $1 file: stub lines for raise NotImplementedError NOT under @abstractmethod (8-line look-back)
  awk '
    { buf[NR] = $0 }
    /raise[[:space:]]+NotImplementedError/ {
      ok = 0
      for (i = NR - 1; i >= 1 && i >= NR - 8; i--) if (buf[i] ~ /@(abc\.)?abstractmethod/) { ok = 1; break }
      if (!ok) printf "STUB_FUNCTION: %d:%s\n", NR, $0
    }' "$1" | head -3
}

collect_findings() { # $1 file -> findings, one per line
  local file="$1" ext="${1##*.}"
  case "$ext" in
    ts|tsx|js|jsx|mjs) check_imports "$file" ;;
  esac

  scan "$file" 'TODO: implement|TODO: add implementation|throw new Error.*not implemented|pass  # TODO|# TODO.*implement|return null; // TODO|return None  # TODO|\.\.\.  # implement|throw Error\("Not implemented"\)' 3 STUB_FUNCTION
  if [ "$ext" = "py" ]; then abstract_not_implemented "$file"; fi

  if ! is_test_path "$file"; then
    scan "$file" 'jest\.mock\(|sinon\.|unittest\.mock|MockProvider|createMockStore|mockReturnValue|spyOn\(|\.mockImplementation\(|TestBed\.|factory_boy|(import|from)[[:space:]]+faker' 2 MOCK_LEAK
  fi

  scan "$file" '(#|//) (Note: this may not work|This might need adjustment|You may want to change|I think|Not sure if)' 2 AI_HEDGE_COMMENT
  scan "$file" '"your-api-key-here"|"YOUR_API_KEY"|"REPLACE_ME"|"TODO_FILL_IN"|"changeme"|'"'changeme'"'|"placeholder"|'"'placeholder'"'|"example\.com"|http://localhost:3000.*TODO' 2 HARDCODED_PLACEHOLDER
}

run_hook() {
  local input file ext findings count msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || return 0
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  ext="${file##*.}"
  case "$ext" in
    md|json|lock|yaml|yml|txt|png|jpg|svg|ico|sh) return 0 ;;
  esac
  findings=$(collect_findings "$file" | head -"$MAX_FINDINGS")
  [ -n "$findings" ] || return 0
  count=$(printf '%s\n' "$findings" | wc -l | tr -d ' ')
  msg="AI-pattern check: $count possible issue(s) in $file (advisory; review before committing):
$findings"
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | /bin/bash "$self" 2>"$tmp/stderr"; }
  expect_has() { # $1 label, $2 output, $3 needle
    if printf '%s' "$2" | jq -e --arg n "$3" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then
      echo "  ok   positive: $1"; else echo "  FAIL $1 (got: $2)"; fail=1; fi
  }
  expect_silent() { if [ -z "$2" ]; then echo "  ok   negative: $1"; else echo "  FAIL $1 (got: $2)"; fail=1; fi; }

  mkdir -p "$tmp/src"
  printf 'export const x = 1;\n' > "$tmp/src/exists.ts"
  printf "import { x } from './exists';\nimport { y } from './missing';\nimport { z } from './exists.js';\n" > "$tmp/src/a.ts"
  out=$(run "$tmp/src/a.ts"); rc=$?
  expect_has "missing relative import flagged (BSD grep, no -P)" "$out" "'./missing'"
  if printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext' | grep -q "exists"; then echo "  FAIL resolvable imports flagged"; fail=1; else echo "  ok   negative: resolvable imports (incl. ./x.js -> x.ts) not flagged"; fi
  if [ "$rc" -eq 0 ] && [ ! -s "$tmp/stderr" ]; then echo "  ok   exit 0, empty stderr on a relative import"; else echo "  FAIL rc=$rc stderr=$(cat "$tmp/stderr")"; fail=1; fi

  printf 'class A:\n    def f(self):\n        raise NotImplementedError\n' > "$tmp/stub.py"
  out=$(run "$tmp/stub.py"); expect_has "concrete method raising NotImplementedError flagged" "$out" "STUB_FUNCTION"
  printf 'from abc import ABC, abstractmethod\n\nclass A(ABC):\n    @abstractmethod\n    def f(self):\n        raise NotImplementedError\n' > "$tmp/abs.py"
  out=$(run "$tmp/abs.py"); expect_silent "abstract method raising NotImplementedError not flagged" "$out"

  printf 'from unittest.mock import MagicMock\n' > "$tmp/prod.py"
  out=$(run "$tmp/prod.py"); expect_has "mock import in production file flagged" "$out" "MOCK_LEAK"
  mkdir -p "$tmp/tests"; cp "$tmp/prod.py" "$tmp/tests/test_prod.py"
  out=$(run "$tmp/tests/test_prod.py"); expect_silent "mock import in a test file not flagged" "$out"
  printf 'See fixtures.md and the faker. library docs\n' > "$tmp/prose.py"
  out=$(run "$tmp/prose.py"); expect_silent "prose mentioning fixtures./faker. not flagged" "$out"

  printf 'KEY = "changeme"\n' > "$tmp/cfg.py"
  out=$(run "$tmp/cfg.py"); expect_has "placeholder value flagged" "$out" "HARDCODED_PLACEHOLDER"
  printf 'def ok():\n    return 1\n' > "$tmp/clean.py"
  out=$(run "$tmp/clean.py"); expect_silent "clean file silent" "$out"
  printf 'changeme\n' > "$tmp/n.md"
  out=$(run "$tmp/n.md"); expect_silent "markdown skipped" "$out"
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
