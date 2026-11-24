#!/usr/bin/env bash
# post-edit-ai-patterns.sh — PostToolUse (Write|Edit)
# Scans the edited file for AI-specific code pathologies and reports them to the model.
#   1. Unresolvable relative imports in TS/JS (file not on disk)
#   2. Placeholder / stub implementations (TODO: implement, throw not implemented, ...)
#   3. Mock / test-framework code in non-test files
#   4. Hedging comments left in code
#   5. Placeholder values ("changeme", "YOUR_API_KEY", ...)
#   6. AI guardrail signals from `.claude/scripts/check-ai-assets.py --file` (one detector, shared with CI):
#      retrieval without a tenant/principal filter (G9), state-changing tool without idempotency/authorization
#      markers (G2, G4), prompt label 'latest' (G11). Pattern-only: cannot prove semantics.
#   7. Silent catch (code-standards "No Silent Failures"): a catch/except whose body is empty or only
#      pass / continue / break / return <default> (TS/JS, Java, Kotlin, Dart, Python; test files skipped). Exempt with
#      `silent-ok: <reason>` on the handler line or the line above. Textual brace/indent tracking, not a parser.
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
AI_ASSET_CHECK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/check-ai-assets.py"

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

ai_asset_signals() { # $1 file -> guardrail signals from the shared detector; says once when it cannot run
  local marker="${TMPDIR:-/tmp}/claude-ai-asset-check-unavailable"
  if ! command -v python3 >/dev/null 2>&1 || [ ! -f "$AI_ASSET_CHECK" ]; then
    [ -f "$marker" ] || { : > "$marker" 2>/dev/null; echo "AI_ASSET_CHECK_UNAVAILABLE: python3 or check-ai-assets.py missing; guardrail signals not checked"; }
    return 0
  fi
  python3 "$AI_ASSET_CHECK" --file "$1" 2>/dev/null | head -5
}

# Silent = the handler body (comments removed) is empty, or ONLY pass / continue / break / return [default]:
# exactly the forbidden shapes in code-standards.md. A body that records, returns a status or falls back is
# left to review (it may be an error state), which keeps this advisory quiet on legitimate handlers.
SILENT_BODY_ERE='^((pass|continue|break|return)( +(\[\]|\{\}|None|null|nil|undefined|""|'"''"'|0|-1|false|False|true|True|const +\[\]|Optional\.empty\(\)|List\.of\(\)|Collections\.empty[A-Za-z]*\(\)))? *;?)?$'

silent_catch() { # $1 file, $2 lang (c | py) -> "SILENT_CATCH: <line>: <text>"
  SILENT_RE="$SILENT_BODY_ERE" awk -v lang="$2" '  # ENVIRON: awk -v would unescape the ERE
    BEGIN { silent_re = ENVIRON["SILENT_RE"] }
    function cnt(s, ch,    n, i) { n = 0; for (i = 1; i <= length(s); i++) if (substr(s, i, 1) == ch) n++; return n }
    function indent(s) { match(s, /^[ \t]*/); return RLENGTH }
    function report(    b, i, cut, d, ch) {
      b = body
      if (lang == "c") { cut = 0; d = 1   # the brace that closes THIS handler, not the last one on the line
                         for (i = 1; i <= length(b); i++) { ch = substr(b, i, 1)
                           if (ch == "{") d++; else if (ch == "}" && --d == 0) { cut = i; break } }
                         if (cut) b = substr(b, 1, cut - 1)
                         gsub(/\/\*[^*]*\*\//, "", b); gsub(/\/\/[^\n]*/, "", b) }
      else gsub(/#[^\n]*/, "", b)
      gsub(/[ \t\n]+/, " ", b); sub(/^ /, "", b); sub(/ $/, "", b)
      if (b ~ silent_re && start_txt !~ /silent-ok:/ && prev_of_start !~ /silent-ok:/)
        printf "SILENT_CATCH: %d: %s\n", start, start_txt
      open = 0
    }
    lang == "c" {
      if (open) {
        body = body "\n" $0; depth += cnt($0, "{") - cnt($0, "}")
        if (depth <= 0) report()
      } else if (match($0, /(^|[^A-Za-z0-9_])catch[ \t]*(\([^)]*\))?[ \t]*\{|(^|[} \t])on[ \t]+[A-Z][A-Za-z0-9_<>]*[ \t]*\{/)) {
        rest = substr($0, RSTART + RLENGTH); start = NR; start_txt = $0; prev_of_start = prev
        open = 1; body = rest; depth = 1 + cnt(rest, "{") - cnt(rest, "}")
        if (depth <= 0) report()
      }
      prev = $0; next
    }
    lang == "py" {
      if (open) {
        if ($0 ~ /^[ \t]*$/ || $0 ~ /^[ \t]*#/) { prev = $0; next }
        if (indent($0) > ex_indent) { body = body "\n" $0; prev = $0; next }
        report()
      }
      if ($0 ~ /^[ \t]*except([ \t(][^:]*)?:/) {
        start = NR; start_txt = $0; prev_of_start = prev; ex_indent = indent($0); open = 1
        body = $0; sub(/^[^:]*:/, "", body)
      }
      prev = $0
    }
    END { if (open) report() }' "$1" 2>/dev/null | head -3
}

promise_catch() { # $1 file: .catch(handler) that returns nothing or a default -> "SILENT_CATCH: <line>: <text>"
  grep -nE '\.catch\([[:space:]]*(\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)[[:space:]]*=>[[:space:]]*(\{[[:space:]]*(return[[:space:]]*(null|undefined|false|true|\[\]|\{\}|0)?[[:space:]]*;?[[:space:]]*)?\}|null|undefined|false|\[\]|\{\})[[:space:]]*\)' "$1" 2>/dev/null |
    grep -v 'silent-ok:' | head -3 | sed 's/^/SILENT_CATCH: /'
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

  case "$ext" in
    py|ts|tsx|js|jsx|mjs|java|dart) ai_asset_signals "$file" ;;
  esac
  if ! is_test_path "$file"; then
    case "$ext" in
      ts|tsx|js|jsx|mjs) silent_catch "$file" c; promise_catch "$file" ;;
      java|kt|dart) silent_catch "$file" c ;;
      py) silent_catch "$file" py ;;
    esac
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

  mkdir -p "$tmp/rag"
  printf 'docs = store.similarity_search(query, k=5)\n' > "$tmp/rag/search.py"
  out=$(run "$tmp/rag/search.py"); expect_has "retrieval without scope filter flagged (shared detector)" "$out" "RETRIEVAL_WITHOUT_SCOPE_FILTER"
  printf 'docs = store.similarity_search(query, k=5, filter={"tenant_id": tid})\n' > "$tmp/rag/scoped.py"
  out=$(run "$tmp/rag/scoped.py"); expect_silent "tenant-filtered retrieval not flagged" "$out"
  printf '@tool\ndef send_payment(amount: int) -> str:\n    return "ok"\n' > "$tmp/rag/tools.py"
  out=$(run "$tmp/rag/tools.py"); expect_has "state-changing tool without idempotency/authz flagged" "$out" "STATE_CHANGING_TOOL_UNGUARDED"
  printf '"""Compare a <-> b."""\n' > "$tmp/rag/prose.py"
  out=$(run "$tmp/rag/prose.py"); expect_silent "pgvector operator in prose not flagged as retrieval" "$out"
  printf 'MODEL = "gemini-3-flash-preview"\n' > "$tmp/rag/agent.py"
  out=$(run "$tmp/rag/agent.py"); expect_has "preview model id flagged, as ADVISORY" "$out" "ADVISORY MODEL_UNPINNED"

  mkdir -p "$tmp/sc"
  printf 'export async function load() {\n  try { return await api(); } catch (e) { return []; }\n}\n' > "$tmp/sc/a.ts"
  out=$(run "$tmp/sc/a.ts"); expect_has "TS single-line catch returning a default" "$out" "SILENT_CATCH: 2"
  printf 'try {\n  run();\n} catch (IOException e) {\n}\n' > "$tmp/sc/B.java"
  out=$(run "$tmp/sc/B.java"); expect_has "Java empty multi-line catch" "$out" "SILENT_CATCH: 3"
  printf 'Future<int?> f() async {\n  try {\n    return await g();\n  } on TimeoutException catch (e) {\n    return null;\n  }\n}\n' > "$tmp/sc/c.dart"
  out=$(run "$tmp/sc/c.dart"); expect_has "Dart on/catch returning null" "$out" "SILENT_CATCH: 4"
  printf 'def f():\n    try:\n        return g()\n    except Exception:\n        return []\n' > "$tmp/sc/d.py"
  out=$(run "$tmp/sc/d.py"); expect_has "Python except returning a default" "$out" "SILENT_CATCH: 4"
  printf 'try:\n    g()\nexcept: pass\n' > "$tmp/sc/e.py"
  out=$(run "$tmp/sc/e.py"); expect_has "Python bare except: pass" "$out" "SILENT_CATCH: 3"
  printf 'try {\n  run();\n} catch (e) {\n  logger.error("run failed", e);\n  throw e;\n}\n' > "$tmp/sc/ok.ts"
  out=$(run "$tmp/sc/ok.ts"); expect_silent "TS catch that logs and rethrows" "$out"
  printf 'try {\n  await g();\n} catch (e, st) {\n  _log.severe("g failed", e, st);\n  rethrow;\n}\n' > "$tmp/sc/ok.dart"
  out=$(run "$tmp/sc/ok.dart"); expect_silent "Dart catch that logs and rethrows" "$out"
  printf 'def f():\n    try:\n        g()\n    except ValueError as exc:\n        logger.warning("g failed: %%s", type(exc).__name__)\n        raise\n' > "$tmp/sc/ok.py"
  out=$(run "$tmp/sc/ok.py"); expect_silent "Python except that logs and raises" "$out"
  printf 'try {\n  x();\n} catch (e) { // silent-ok: best-effort cache warm-up, next read refetches\n}\n' > "$tmp/sc/ex.ts"
  out=$(run "$tmp/sc/ex.ts"); expect_silent "silent-ok marker exempts a deliberate handler" "$out"
  printf 'try:\n    toks = shlex.split(s)\nexcept ValueError:\n    toks = s.split()  # fallback\n' > "$tmp/sc/fb.py"
  out=$(run "$tmp/sc/fb.py"); expect_silent "a fallback assignment is left to review, not flagged" "$out"
  printf 'try {\n  x();\n} catch (e) {\n  return Result.failure(e);\n}\n' > "$tmp/sc/st.ts"
  out=$(run "$tmp/sc/st.ts"); expect_silent "returning an error state is not flagged" "$out"
  printf 'fetchUser().catch(() => {});\nload().catch((e) => { return false; });\n' > "$tmp/sc/p.ts"
  out=$(run "$tmp/sc/p.ts"); expect_has "promise .catch(() => {}) swallowing the error" "$out" "SILENT_CATCH: 1"
  printf 'load().catch((e) => { logger.error("load failed", e); throw e; });\nload().catch(reportError);\n' > "$tmp/sc/pok.ts"
  out=$(run "$tmp/sc/pok.ts"); expect_silent "promise .catch that logs and rethrows, or hands off to a reporter" "$out"
  printf 'try { x(); } catch (e) { return null; } finally { cleanup(); }\n' > "$tmp/sc/f.ts"
  out=$(run "$tmp/sc/f.ts"); expect_has "one-line catch before a finally block" "$out" "SILENT_CATCH: 1"
  mkdir -p "$tmp/sc/tests"; cp "$tmp/sc/d.py" "$tmp/sc/tests/test_d.py"
  out=$(run "$tmp/sc/tests/test_d.py"); expect_silent "silent catch in a test file not flagged" "$out"

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
