#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — Riverpod `ref` / `state` used after an `await` without `ref.mounted`.
#
# Why: since Riverpod 3.0, using a Ref after its provider was disposed throws UnmountedRefException
# (riverpod.dev/docs/3.0_migration: "guard any usage of Ref that happens after an async gap with
# ref.mounted"). A user who leaves the screen mid-request turns every unguarded post-await
# `state = ...` / `ref.read(...)` into a crash or a lost update.
#
# Scope:  edited *.dart files with a Notifier, @riverpod, a generated `extends _$X` class or `Ref ref` (not tests / generated files).
# Flags:  inside an `async` function body, a line after an `await` that sets `state`, reads `state.`
#         or calls `ref.read|watch|invalidate|refresh|listen`, with no `ref.mounted` check since that
#         await (each new await re-opens the window). `state = await f()` on the await's own line is
#         not flagged (common AsyncValue.guard idiom; review it by hand).
# Exempt: `// mounted-ok: <reason>` on the flagged line or the line above.
# Limits: textual brace tracking, not a parser; one finding per function. A hit means "look at this".
#         Awaits in one-line closures are ignored; a multi-line closure's await still counts for the outer
#         function, and any `ref.mounted` mention counts as a guard for the rest of the window.
# Behavior: ADVISORY. Always exit 0. Findings go to Claude as PostToolUse additionalContext JSON.
#         Fails open if jq is missing (says so on stderr for the user).
# Test:   bash .claude/hooks/post-edit-riverpod-mounted-advisory.sh --selftest
set -uo pipefail

# scan_file <path> -> "line: text" for the first unguarded post-await ref/state use in each async function.
# POSIX awk only (BSD awk on macOS has no \s, \b or gensub).
scan_file() {
  awk '
    function count(s, ch,    n, i) { n = 0; for (i = 1; i <= length(s); i++) if (substr(s, i, 1) == ch) n++; return n }
    {
      line = $0; code = line; sub(/\/\/.*/, "", code)
      if (!infn && code ~ /async\*?[[:space:]]*\{/) {
        infn = 1; depth = 0; awaited = 0; guarded = 0; reported = 0
      }
      if (infn) {
        if (code ~ /ref\.mounted/) guarded = 1
        use = (code ~ /(^|[^A-Za-z0-9_.])state[[:space:]]*=[^=]/ || code ~ /(^|[^A-Za-z0-9_.])state\./ || code ~ /ref\.(read|watch|invalidate|refresh|listen)[[:space:]]*\(/)
        if (awaited && !guarded && !reported && use && code !~ /await[[:space:]]/ && !(line ~ /mounted-ok:/ || prev ~ /mounted-ok:/)) {
          printf "%d: %s\n", NR, line; reported = 1
        }
        outer = code; while (gsub(/\{[^{}]*\}/, "", outer)) {}  # an await inside a one-line closure is not ours
        if (outer ~ /(^|[^A-Za-z0-9_])await[[:space:]]/) { awaited = 1; guarded = 0 }
        depth += count(code, "{") - count(code, "}")
        if (depth <= 0) infn = 0
      }
      prev = line
    }
  ' "$1"
}

is_candidate() {
  case "$1" in
    *_test.dart|*.g.dart|*.freezed.dart|*.mocks.dart|*/test/*|*/integration_test/*) return 1 ;;
    *.dart) grep -qE 'Notifier|@riverpod|extends[[:space:]]+_\$|(^|[^A-Za-z])Ref[[:space:]]+ref' "$1" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

run_hook() {
  local input file hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "riverpod-mounted-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  is_candidate "$file" || return 0
  hits=$(scan_file "$file")
  [ -n "$hits" ] || return 0
  msg="Riverpod: ref/state used after an await without a ref.mounted check in $file:
$hits
Since Riverpod 3.0 a disposed Ref throws UnmountedRefException. After each await add 'if (!ref.mounted) return;' before touching state or ref (riverpod-patterns skill, Provider lifecycle). If the provider cannot be disposed here (keepAlive), add '// mounted-ok: <reason>'."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | /bin/bash "$self" 2>/dev/null; }
  has() { if printf '%s' "$2" | jq -e --arg n "$3" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then
            echo "  ok   positive: $1"; else echo "  FAIL $1 (got: $2)"; fail=1; fi; }
  none() { if [ -z "$2" ]; then echo "  ok   negative: $1"; else echo "  FAIL $1 (got: $2)"; fail=1; fi; }
  mkdir -p "$tmp/lib" "$tmp/test"

  printf 'class Cart extends _$Cart {\n  Future<void> add(Item i) async {\n    await repo.add(i);\n    state = [...state, i];\n  }\n}\n' > "$tmp/lib/a.dart"
  out=$(run "$tmp/lib/a.dart"); has "state written after await, no guard" "$out" "4:     state = [...state, i];"
  printf 'class Cart extends _$Cart {\n  Future<void> add(Item i) async {\n    await repo.add(i);\n    if (!ref.mounted) return;\n    state = [...state, i];\n  }\n}\n' > "$tmp/lib/b.dart"
  out=$(run "$tmp/lib/b.dart"); none "guarded with ref.mounted" "$out"
  printf 'class S extends _$S {\n  Future<void> go() async {\n    await a();\n    if (!ref.mounted) return;\n    await b();\n    ref.read(logProvider).add(1);\n  }\n}\n' > "$tmp/lib/c.dart"
  out=$(run "$tmp/lib/c.dart"); has "a second await re-opens the window (ref.read)" "$out" "6:     ref.read"
  printf 'class S extends _$S {\n  Future<void> go() async {\n    state = const AsyncLoading();\n    state = await AsyncValue.guard(() => repo.load());\n  }\n}\n' > "$tmp/lib/d.dart"
  out=$(run "$tmp/lib/d.dart"); none "writes before the first await / on the await line" "$out"
  printf 'class S extends _$S {\n  Future<void> go() async {\n    await a();\n    // mounted-ok: keepAlive provider, never disposed\n    state = 1;\n  }\n}\n' > "$tmp/lib/e.dart"
  out=$(run "$tmp/lib/e.dart"); none "mounted-ok marker exempts" "$out"
  printf 'Future<void> f() async {\n  await a();\n  setState(() {});\n}\n' > "$tmp/lib/plain.dart"
  out=$(run "$tmp/lib/plain.dart"); none "a file without Notifier/Ref is out of scope" "$out"
  cp "$tmp/lib/a.dart" "$tmp/test/a_test.dart"
  out=$(run "$tmp/test/a_test.dart"); none "test files are skipped" "$out"
  printf 'class S extends _$S {\n  void sync() {\n    state = 1;\n  }\n  Future<void> go() async {\n    await a();\n    if (!ref.mounted) return;\n    state = 2;\n  }\n}\n' > "$tmp/lib/f.dart"
  out=$(run "$tmp/lib/f.dart"); none "sync method and a guarded async method" "$out"
  printf 'class S extends _$S {\n  Future<void> go() async {\n    final f = () async { await a(); };\n    state = 1;\n    await b();\n    if (!ref.mounted) return;\n    ref.read(x);\n  }\n}\n' > "$tmp/lib/g.dart"
  out=$(run "$tmp/lib/g.dart"); none "an await inside a one-line closure does not open the outer window" "$out"
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
