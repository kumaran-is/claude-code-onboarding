#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — A2UI protocol-version drift in generative-UI (GenUI) code and fixtures.
#
# Why:    every renderer in this toolkit is pinned to A2UI v0.9 (.claude/rules/genui-a2ui.md). Mixing v0.8 / v1.0
#         with v0.9 between agent, renderer and catalog breaks silently (unknown message keys are dropped or the
#         wrong catalog resolves). These shapes are deterministic, so they are cheap to flag at edit time.
# Scope:  edited *.ts, *.tsx, *.js, *.mjs, *.dart, *.json whose path has an `a2ui` or `genui` directory or file-name
#         part, or a JSON file whose name contains `catalog`.
#         Skipped: node_modules, dist, build, .dart_tool, *.d.ts, and paths with an `invalid` part (negative
#         fixtures carry wrong versions on purpose).
# Flags (per line, POSIX ERE):
#   TS/JS   import from @a2ui/web_core/v1_0, @a2ui/*/v0_8               non-adopted or legacy protocol entry point
#   TS/JS   BasicCatalog imported from the '@a2ui/angular' package root   that root catalog is the v1.0 catalog
#   Dart    package:genui/                                               discontinued package (use a2ui_flutter 0.4.0)
#   Dart    package:a2ui_flutter/basic_catalog.dart                      v1.0 catalog (v0.9 is v0_9/basic_catalog.dart)
#   JSON    "version": "v0.8" | "0.8" | "v1.0" | "1.0"  in a file that contains an A2UI message key
#           (createSurface, updateComponents, updateDataModel, deleteSurface, surfaceUpdate, beginRendering)
# Not covered here (no overlap): HTML/XSS sinks and token storage -> post-edit-web-security-advisory.sh;
#         secrets -> post-edit-secrets-scan.sh. Schema validity is the contract validator's job, not this hook's.
# Exempt: `a2ui-version-reviewed: <reason>` (reason required) on the flagged line, or on a comment-only line directly
#         above (a trailing marker on a code line exempts that line only, never the next one).
# Comments: lines starting with // are ignored (JSON has none).
# Behavior: ADVISORY. Always exit 0, never blocks. Findings go to Claude as PostToolUse additionalContext JSON.
#         Fails open (says so on stderr) if jq is missing.
# Test:   bash .claude/hooks/post-edit-genui-advisory.sh --selftest
set -uo pipefail

is_candidate() { # $1 path -> 0 when in GenUI scope
  local p="$1" base lower
  case "$p" in
    */node_modules/*|*/dist/*|*/build/*|*/.dart_tool/*|*.d.ts) return 1 ;;
  esac
  lower=$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')
  case "$lower" in
    */invalid/*|*/invalid_*|*/invalid-*|*.invalid.*) return 1 ;;
  esac
  base=$(basename "$lower")
  case "$base" in
    *.ts|*.tsx|*.js|*.mjs|*.dart|*.json) ;;
    *) return 1 ;;
  esac
  case "$lower" in
    */a2ui/*|*/genui/*|*a2ui*|*genui*) return 0 ;;
  esac
  case "$base" in
    *catalog*.json) return 0 ;;
  esac
  return 1
}

# scan_file <path> -> prints "line: [kind] text" for each un-exempted hit.
scan_file() {
  local f="$1" kind_lang has_msg=0
  case "$f" in
    *.dart) kind_lang=dart ;;
    *.json) kind_lang=json ;;
    *) kind_lang=js ;;
  esac
  if [ "$kind_lang" = json ] && grep -qE '"(createSurface|updateComponents|updateDataModel|deleteSurface|surfaceUpdate|beginRendering)"' "$f"; then
    has_msg=1
  fi
  awk -v lang="$kind_lang" -v hasmsg="$has_msg" '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return substr(s, 1, 160) }
    {
      kind = ""
      if ($0 ~ /^[[:space:]]*\/\//) { prevc = $0; next }
      if (lang == "js") {
        if ($0 ~ /@a2ui\/[a-z_]+\/v1_0/) kind = "A2UI v1.0 entry point (not adopted; v0.9 only)"
        else if ($0 ~ /@a2ui\/[a-z_]+\/v0_8/) kind = "A2UI v0.8 legacy entry point"
        else if ($0 ~ /BasicCatalog/ && $0 ~ /from[[:space:]]*["\x27]@a2ui\/angular["\x27]/) kind = "root BasicCatalog is the v1.0 catalog; import it from @a2ui/angular/v0_9"
      } else if (lang == "dart") {
        if ($0 ~ /package:genui\//) kind = "discontinued genui package; use a2ui_flutter 0.4.0 + a2ui_core 0.8.0"
        else if ($0 ~ /package:a2ui_flutter\/basic_catalog\.dart/) kind = "v1.0 catalog; use package:a2ui_flutter/v0_9/basic_catalog.dart"
      } else if (lang == "json" && hasmsg == 1) {
        if ($0 ~ /"version"[[:space:]]*:[[:space:]]*"v?(0\.8|1\.0)"/) kind = "A2UI message version is not v0.9"
      }
      if (kind != "" && !($0 ~ /a2ui-version-reviewed:[[:space:]]*[^[:space:]]/ || prevc ~ /a2ui-version-reviewed:[[:space:]]*[^[:space:]]/))
        printf "%d: [%s] %s\n", NR, kind, trim($0)
      prevc = ""
    }
  ' "$f"
}

run_hook() {
  local input file hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "genui-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  is_candidate "$file" || return 0
  hits=$(scan_file "$file")
  [ -n "$hits" ] || return 0
  msg="A2UI protocol-version drift in $file (advisory, .claude/rules/genui-a2ui.md):
$hits
- One protocol version end to end: agent, renderer and catalog all on A2UI v0.9 (wire value \"version\": \"v0.9\").
- Angular/React: import v0.9 classes from the /v0_9 entry points. Flutter: a2ui_flutter 0.4.0 v0_9/ catalog, never package:genui.
- v1.0 is a documented future migration only. A reviewed, intentional line may carry 'a2ui-version-reviewed: <reason>' on or above it."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/web/src/app/features/a2ui" "$tmp/app/lib/features/genui" "$tmp/contract/fixtures/invalid" "$tmp/contract/fixtures/valid" "$tmp/other/src"
  # positives
  printf "import { A2uiMessage } from '@a2ui/web_core/v1_0';\n" > "$tmp/web/src/app/features/a2ui/v1.ts"
  printf "import { SurfaceComponent } from '@a2ui/angular/v0_8';\n" > "$tmp/web/src/app/features/a2ui/v08.ts"
  printf "import { BasicCatalog } from '@a2ui/angular';\n" > "$tmp/web/src/app/features/a2ui/root-catalog.ts"
  printf "import 'package:genui/genui.dart';\n" > "$tmp/app/lib/features/genui/old.dart"
  printf "import 'package:a2ui_flutter/basic_catalog.dart';\n" > "$tmp/app/lib/features/genui/v1_catalog.dart"
  printf '{\n  "version": "1.0",\n  "createSurface": { "surfaceId": "s1" }\n}\n' > "$tmp/contract/fixtures/valid/a2ui-create.json"
  printf '{ "version": "v0.8", "surfaceUpdate": {} }\n' > "$tmp/contract/product_catalog.json"
  printf "import { X } from '@a2ui/web_core/v1_0'; // a2ui-version-reviewed: migration spike\nimport { Y } from '@a2ui/web_core/v1_0';\n" > "$tmp/web/src/app/features/a2ui/bleed.ts"
  # negatives
  printf "import { BasicCatalog, SurfaceComponent } from '@a2ui/angular/v0_9';\nimport { MarkdownRenderer, provideA2Ui } from '@a2ui/angular';\nimport { MessageProcessor } from '@a2ui/web_core/v0_9';\n" > "$tmp/web/src/app/features/a2ui/ok.ts"
  printf "import 'package:a2ui_flutter/v0_9/basic_catalog.dart';\nimport 'package:a2ui_core/a2ui_core.dart';\n" > "$tmp/app/lib/features/genui/ok.dart"
  printf '{ "version": "v0.9", "createSurface": { "surfaceId": "s1" } }\n' > "$tmp/contract/fixtures/valid/a2ui-ok.json"
  printf '{ "version": "1.0", "components": ["ActionCard"] }\n' > "$tmp/contract/product_catalog_meta.json"
  printf '{ "version": "1.0", "createSurface": {} }\n' > "$tmp/contract/fixtures/invalid/a2ui-wrong-version.json"
  printf "import { A2uiMessage } from '@a2ui/web_core/v1_0';\n" > "$tmp/other/src/unrelated.ts"
  printf "// do not import '@a2ui/web_core/v1_0' here\nexport const a = 1;\n" > "$tmp/web/src/app/features/a2ui/comment.ts"
  printf "// a2ui-version-reviewed: v1.0 migration spike behind a flag\nimport { Z } from '@a2ui/web_core/v1_0';\n" > "$tmp/web/src/app/features/a2ui/exempt.ts"
  probe() { # label file expect(advise|silent) [content-needle]
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | jq -e --arg n "${4:-}" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: TS import of web_core/v1_0"                "$tmp/web/src/app/features/a2ui/v1.ts"           advise "1: [A2UI v1.0 entry point"
  probe "positive: TS import of angular/v0_8"                 "$tmp/web/src/app/features/a2ui/v08.ts"          advise "1: [A2UI v0.8 legacy entry point]"
  probe "positive: BasicCatalog from @a2ui/angular root"      "$tmp/web/src/app/features/a2ui/root-catalog.ts" advise "root BasicCatalog is the v1.0 catalog"
  probe "positive: Dart package:genui import"                 "$tmp/app/lib/features/genui/old.dart"           advise "discontinued genui package"
  probe "positive: Dart v1.0 basic_catalog import"            "$tmp/app/lib/features/genui/v1_catalog.dart"    advise "1: [v1.0 catalog"
  probe "positive: JSON message with version 1.0"             "$tmp/contract/fixtures/valid/a2ui-create.json"  advise "2: [A2UI message version is not v0.9]"
  probe "positive: catalog JSON message with v0.8"            "$tmp/contract/product_catalog.json"             advise "1: [A2UI message version is not v0.9]"
  probe "positive: trailing marker does not exempt next line" "$tmp/web/src/app/features/a2ui/bleed.ts"        advise "2: [A2UI v1.0 entry point"
  probe "negative: v0_9 entry points and root providers"      "$tmp/web/src/app/features/a2ui/ok.ts"           silent
  probe "negative: Dart v0_9 catalog import"                  "$tmp/app/lib/features/genui/ok.dart"            silent
  probe "negative: JSON message on v0.9"                      "$tmp/contract/fixtures/valid/a2ui-ok.json"      silent
  probe "negative: catalog JSON without message keys"         "$tmp/contract/product_catalog_meta.json"        silent
  probe "negative: invalid/ fixtures skipped"                 "$tmp/contract/fixtures/invalid/a2ui-wrong-version.json" silent
  probe "negative: path outside GenUI scope"                  "$tmp/other/src/unrelated.ts"                    silent
  probe "negative: comment line ignored"                      "$tmp/web/src/app/features/a2ui/comment.ts"      silent
  probe "negative: reviewed marker on the line above exempts" "$tmp/web/src/app/features/a2ui/exempt.ts"       silent
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/web/src/app/features/a2ui/v1.ts" | bash "$self" 2>/dev/null); rc=$?
  if [ "$rc" -eq 0 ]; then echo "  ok   advisory only: exit 0 on a finding"; else echo "  FAIL exit $rc on a finding"; fail=1; fi
  out=$(printf 'not json' | bash "$self" 2>/dev/null); rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then echo "  ok   malformed stdin: silent exit 0"; else echo "  FAIL malformed stdin (rc=$rc out=$out)"; fail=1; fi
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
