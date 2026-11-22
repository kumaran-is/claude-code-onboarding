#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — Flutter UI code should not talk to the network directly.
#
# Why: widgets that import an HTTP client or a cloud SDK bypass the repository layer, so they
# cannot read from a local cache, cannot be tested with a fake data source, and fail when offline.
#
# Scope:  edited *.dart files whose path has a UI directory segment
#         (presentation | ui | screens | pages | views | widgets).
#         Skipped: tests, generated files (*.g.dart, *.freezed.dart, *.mocks.dart).
# Flags:  imports of package:dio | http | retrofit | chopper | graphql* | firebase_* | cloud_firestore | supabase*,
#         and `HttpClient(` constructions.
# Exempt: put `// online-only: <reason>` on the flagged line or the line above it
#         (for screens that are genuinely meaningless offline, e.g. a live video call).
# Behavior: ADVISORY. Always exit 0. Findings go to Claude as PostToolUse additionalContext JSON
#         (stderr of an exit-0 hook is not shown to the model). Fails open if jq is missing.
# Test:   bash .claude/hooks/post-edit-flutter-ui-network-advisory.sh --selftest
set -uo pipefail

# scan_file <path> -> prints "line: text" for each un-exempted hit.
scan_file() {
  awk '
    {
      line = $0
      hit = 0
      if (line ~ /^[[:space:]]*import[[:space:]]+.package:(dio|http|retrofit|chopper|graphql[a-z_]*|firebase_[a-z_]+|cloud_firestore|supabase[a-z_]*)\//) hit = 1
      if (line ~ /HttpClient[[:space:]]*\(/) hit = 1
      if (hit && !(line ~ /online-only:/ || prev ~ /online-only:/)) printf "%d: %s\n", NR, line
      prev = line
    }
  ' "$1"
}

is_candidate() { # $1 path
  case "$1" in
    *_test.dart|*.g.dart|*.freezed.dart|*.mocks.dart|*/test/*) return 1 ;;
    *.dart) ;;
    *) return 1 ;;
  esac
  printf '%s' "$1" | grep -qE '(^|/)(presentation|ui|screens|pages|views|widgets)/'
}

run_hook() {
  local input file hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "ui-network-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  is_candidate "$file" || return 0
  hits=$(scan_file "$file")
  [ -n "$hits" ] || return 0
  msg="UI layer reaches the network directly in $file:
$hits
Route data through a repository/data source (cache-first, fakeable in tests). If this screen is genuinely online-only, add '// online-only: <reason>' on or above the line."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/lib/features/a/presentation" "$tmp/lib/features/a/data"
  printf "import 'package:dio/dio.dart';\nclass S {}\n" > "$tmp/lib/features/a/presentation/bad.dart"
  printf "// online-only: live session\nimport 'package:firebase_auth/firebase_auth.dart';\n" > "$tmp/lib/features/a/presentation/exempt.dart"
  printf "import 'package:flutter/material.dart';\nclass S {}\n" > "$tmp/lib/features/a/presentation/clean.dart"
  printf "import 'package:dio/dio.dart';\nclass R {}\n" > "$tmp/lib/features/a/data/repo.dart"
  printf "import 'package:dio/dio.dart';\n" > "$tmp/lib/features/a/presentation/bad.g.dart"
  probe() { # label file expect(advise|silent)
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | grep -q 'additionalContext'; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: dio import in presentation/"        "$tmp/lib/features/a/presentation/bad.dart"    advise
  probe "negative: online-only marker exempts"         "$tmp/lib/features/a/presentation/exempt.dart" silent
  probe "negative: clean UI file"                      "$tmp/lib/features/a/presentation/clean.dart"  silent
  probe "negative: data layer may import dio"          "$tmp/lib/features/a/data/repo.dart"           silent
  probe "negative: generated file skipped"             "$tmp/lib/features/a/presentation/bad.g.dart"  silent
  probe "negative: missing file"                       "$tmp/nope.dart"                               silent
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
