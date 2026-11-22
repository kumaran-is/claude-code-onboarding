#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — never wipe/clear local data inside a catch block.
#
# Why: a transient failure (timeout, parse error, 5xx) handled by clearing a cache, queue or
# table turns a recoverable error into silent data loss, and unsynced local writes cannot be
# recovered from the server. Handle the error (log, surface, retry, mark the item failed).
#
# Scope:  edited *.dart files (not tests / generated files).
# Flags:  inside a `catch (...) { ... }` / `on Type { ... }` block, a call to
#         clear( deleteAll( removeAll( truncate( deleteFromDisk( wipe*( or clear<All|Cache|Queue|Store|Table|
#         Db|Database|Storage|Token|Session|Data>*( .
# Exempt: `// wipe-ok: <reason>` on the flagged line or the line above (e.g. an explicit sign-out
#         whose intended handling is to clear local state).
# Limits: brace matching is textual; braces inside string literals can confuse it. It is a
#         tripwire for review, not a parser: a hit means "look at this", not "wrong".
#         Single-line handlers (catch (e) { cache.clear(); }) are not scanned.
# Behavior: ADVISORY. Always exit 0. Findings go to Claude as PostToolUse additionalContext JSON.
#         Fails open if jq is missing.
# Test:   bash .claude/hooks/post-edit-flutter-catch-wipe-advisory.sh --selftest
set -uo pipefail

# scan_file <path> -> "line: text" for each un-exempted wipe call inside a catch/on block.
# POSIX awk only (BSD awk on macOS has no \s, \b or gensub).
scan_file() {
  awk '
    function count(s, ch,    n, i) { n = 0; for (i = 1; i <= length(s); i++) if (substr(s, i, 1) == ch) n++; return n }
    BEGIN { incatch = 0; depth = 0; pending = 0 }
    {
      line = $0
      code = line
      sub(/\/\/.*/, "", code)
      if (!incatch) {
        if (code ~ /(^|[^A-Za-z0-9_])catch[[:space:]]*\(/ || code ~ /(^|[[:space:]}])on[[:space:]]+[A-Z][A-Za-z0-9_<>?]*[[:space:]]*(catch[[:space:]]*\([^)]*\))?[[:space:]]*\{?[[:space:]]*$/) pending = 1
        if (pending) {
          tail = code
          if (match(tail, /catch[[:space:]]*\(/) || match(tail, /(^|[[:space:]}])on[[:space:]]+[A-Z]/)) tail = substr(tail, RSTART)
          sub(/^}/, "", tail)
          o = count(tail, "{"); c = count(tail, "}")
          if (o > 0) { incatch = 1; depth = o - c; pending = 0; if (depth <= 0) incatch = 0 }
        }
      } else {
        if (code ~ /(\.|[[:space:]])(clear|deleteAll|removeAll|truncate|deleteFromDisk|wipe[A-Za-z0-9_]*|clear(All|Cache|Queue|Store|Table|Db|Database|Storage|Token|Session|Data)[A-Za-z0-9_]*)[[:space:]]*\(/ && !(line ~ /wipe-ok:/ || prev ~ /wipe-ok:/)) printf "%d: %s\n", NR, line
        depth += count(code, "{") - count(code, "}")
        if (depth <= 0) incatch = 0
      }
      prev = line
    }
  ' "$1"
}

is_candidate() {
  case "$1" in
    *_test.dart|*.g.dart|*.freezed.dart|*.mocks.dart|*/test/*) return 1 ;;
    *.dart) return 0 ;;
    *) return 1 ;;
  esac
}

run_hook() {
  local input file hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "catch-wipe-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  is_candidate "$file" || return 0
  hits=$(scan_file "$file")
  [ -n "$hits" ] || return 0
  msg="Wipe/clear call inside a catch block in $file:
$hits
A transient error must not delete local data. Log it, surface it, retry or mark the item failed. If clearing is the intended handling, add '// wipe-ok: <reason>' on or above the line."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  printf '%s\n' 'Future<void> sync() async {' '  try {' '    await api.push();' '  } catch (e, st) {' "    log.warning('failed', e, st);" '    await queue.clear();' '  }' '}' > "$tmp/bad.dart"
  printf '%s\n' 'Future<void> sync() async {' '  try {' '    await api.push();' '  } on TimeoutException {' '    await cache.deleteAll();' '  }' '}' > "$tmp/bad_on.dart"
  printf '%s\n' 'Future<void> signOut() async {' '  try {' '    await auth.signOut();' '  } catch (e) {' '    // wipe-ok: sign-out failure still ends the local session' '    await store.clearAll();' '  }' '}' > "$tmp/exempt.dart"
  printf '%s\n' 'Future<void> sync() async {' '  try {' '    await api.push();' '    await queue.clear();' '  } catch (e, st) {' "    log.warning('failed', e, st);" '    rethrow;' '  }' '}' > "$tmp/clean.dart"
  printf '%s\n' 'void f() { try { g(); } catch (e) { rethrow; } }' 'void h() { list.clear(); }' > "$tmp/outside.dart"
  printf '%s\n' 'Future<void> sync() async {' '  try {' '    await api.push();' '  } catch (e) {' '    await clearAllCaches();' '  }' '}' > "$tmp/bad_named.dart"
  printf '%s\n' 'Future<void> f() async {' '  try {' '    await g();' '  } catch (e) {' '    focus.clearFocus();' '  }' '}' > "$tmp/clean_focus.dart"
  cp "$tmp/bad.dart" "$tmp/bad_test.dart"
  probe() { # label file expect
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | grep -q 'additionalContext'; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: clear() inside catch"            "$tmp/bad.dart"      advise
  probe "positive: deleteAll() inside on-clause"    "$tmp/bad_on.dart"   advise
  probe "positive: clearAllCaches() inside catch"   "$tmp/bad_named.dart" advise
  probe "negative: clearFocus() is not a data wipe"  "$tmp/clean_focus.dart" silent
  probe "negative: wipe-ok marker exempts"          "$tmp/exempt.dart"   silent
  probe "negative: clear() in try, not catch"       "$tmp/clean.dart"    silent
  probe "negative: clear() outside any catch"       "$tmp/outside.dart"  silent
  probe "negative: test file skipped"               "$tmp/bad_test.dart" silent
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
