#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — A2UI protocol drift and unsafe GenUI patterns in generative-UI code and fixtures.
#
# Why:    the GenUI contract targets A2UI 1.0 (wire "version": "1.0") and keeps a versioned v0.9.x compatibility path
#         ("v0.9" / "v0.9.1") for renderers not yet proven on 1.0 (.claude/rules/genui-a2ui.md). One stream, one file and
#         one surface use ONE version; mixing versions or carrying the other version's wire fields breaks silently
#         (@a2ui/web_core 0.16.1 accepts a v0.9 {"path":...} object under 1.0 as a literal). These shapes are
#         deterministic, so they are cheap to flag at edit time. Schema validity in depth is the contract validator's job.
# Scope:  edited *.ts, *.tsx, *.js, *.mjs, *.dart, *.json whose path has an `a2ui` or `genui` directory or file-name
#         part, or a JSON file whose name contains `catalog`.
#         Skipped: node_modules, dist, build, .dart_tool, *.d.ts, and paths with an `invalid` part (negative
#         fixtures carry wrong versions on purpose).
# Flags:
#   JSON  not parseable (jq)                                             invalid JSON in a GenUI file
#   JSON  "version": "v0.8"/"0.8"                                        deprecated protocol version
#   JSON  "version": "v1.0"                                              1.0 wire value is "1.0" (no v prefix)
#   JSON  "version" values from both 1.0 and v0.9.x in one file          mixed protocol versions
#   JSON  1.0 file: bare "path"/"call" key opening an object, "theme"   v0.9 wire fields (1.0 uses @path/@call; theme removed)
#   JSON  v0.9.x file: "@path"/"@call"/"@accessibility"/"@checks"/"@catalogId"/"@metadata"   1.0 wire fields
#   JSON  "component": "<Name>" not in the nearest canonical catalog    unsupported catalog component
#         (catalog = nearest canonical-catalog-v1_0.json / canonical-catalog.json in the file's dir, a catalog/ or
#         reference/ sibling, walking up 6 levels; GENUI_CATALOG=<file> overrides; no catalog found -> check skipped)
#   TS/JS import from @a2ui/*/v0_8                                       deprecated protocol entry point
#   TS/JS imports from both a /v1_0 and a /v0_9 entry point in one file   mixed protocol versions
#   TS/JS innerHTML / [innerHTML] / outerHTML / bypassSecurityTrust* / dangerouslySetInnerHTML   unsafe rendering of agent content
#   TS/JS/Dart  action handler (onAction, actionHandler, ActionListener, handleAction, dispatchAction) in a file with
#         no allowlist/payload check (allowedActions, isAllowedAction, validateAction, payloadSchema, ALLOWED_ACTIONS)
#   TS/JS `new MessageProcessor(` in a file that sets neither validationConfig/STRICT_VALIDATION nor errorHandler
#         (@a2ui/angular 0.16.0 only console.errors an unknown component and renders nothing without them)
#   Dart  package:genui/                                                 discontinued package (use a2ui_flutter)
#   Dart  imports of both a2ui_flutter v0_9/ and a non-v0_9 catalog      mixed protocol versions
# v0.9.1 compatibility: a file that declares only "v0.9"/"v0.9.1" (or imports only /v0_9 entry points) is the
#         supported compatibility path and is NOT flagged for being pre-1.0.
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

# find_catalog <file> -> path of the nearest canonical catalog (empty when none)
find_catalog() {
  local d c n=0
  if [ -n "${GENUI_CATALOG:-}" ] && [ -f "$GENUI_CATALOG" ]; then printf '%s' "$GENUI_CATALOG"; return; fi
  d=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 0
  while [ -n "$d" ] && [ "$n" -lt 7 ]; do
    for c in "$d/canonical-catalog-v1_0.json" "$d/canonical-catalog.json" "$d/catalog/canonical-catalog-v1_0.json" "$d/catalog/canonical-catalog.json" "$d/reference/canonical-catalog-v1_0.json" "$d/reference/canonical-catalog.json"; do
      [ -f "$c" ] && { printf '%s' "$c"; return; }
    done
    [ "$d" = "/" ] && return 0
    d=$(dirname "$d"); n=$((n + 1))
  done
}

# scan_file <path> -> prints "line: [kind] text" for each un-exempted hit.
scan_file() {
  local f="$1" lang has_msg=0 fam="" names="" cat
  case "$f" in
    *.dart) lang=dart ;;
    *.json) lang=json ;;
    *) lang=js ;;
  esac
  if [ "$lang" = json ]; then
    if ! jq empty "$f" >/dev/null 2>&1; then echo "1: [invalid JSON in a GenUI file] $(basename "$f")"; return; fi
    if grep -qE '"(createSurface|updateComponents|updateDataModel|deleteSurface|callRendererFunction|surfaceUpdate|beginRendering)"' "$f"; then
      has_msg=1
      if grep -qE '"version"[[:space:]]*:[[:space:]]*"v?1\.0"' "$f"; then fam="1.0"; fi
      if grep -qE '"version"[[:space:]]*:[[:space:]]*"v0\.9(\.1)?"' "$f"; then
        if [ -n "$fam" ]; then fam=mixed; else fam=0.9; fi
      fi
      if grep -qE '"component"[[:space:]]*:' "$f"; then
        cat=$(find_catalog "$f")
        [ -n "$cat" ] && names=" $(jq -r '.components // {} | keys[]' "$cat" 2>/dev/null | tr '\n' ' ')"
      fi
    fi
  fi
  awk -v lang="$lang" -v hasmsg="$has_msg" -v fam="$fam" -v names="$names" '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return substr(s, 1, 160) }
    function hit(k) { if (!(cur ~ /a2ui-version-reviewed:[[:space:]]*[^[:space:]]/ || prevc ~ /a2ui-version-reviewed:[[:space:]]*[^[:space:]]/)) printf "%d: [%s] %s\n", NR, k, trim(cur) }
    BEGIN { mixedReported = 0 }
    {
      cur = $0
      if ($0 ~ /^[[:space:]]*\/\//) { prevc = $0; next }
      if (lang == "js") {
        if ($0 ~ /@a2ui\/[a-z_]+\/v0_8/) hit("A2UI v0.8 entry point (deprecated)")
        if ($0 ~ /@a2ui\/[a-z_]+\/v1_0/) { v10 = NR }
        if ($0 ~ /@a2ui\/[a-z_]+\/v0_9/) { v09 = NR }
        if (v10 && v09 && !mixedReported) { mixedReported = 1; hit("mixed A2UI versions: /v1_0 and /v0_9 entry points in one file") }
        if ($0 ~ /dangerouslySetInnerHTML|bypassSecurityTrust[A-Za-z]*|\[innerHTML\]|\.(inner|outer)HTML[[:space:]]*=/) hit("unsafe rendering sink for agent-provided content")
        if ($0 ~ /new[[:space:]]+MessageProcessor[[:space:]]*[(<]/ && !mpLine) { mpLine = NR; mpText = $0 }
        if ($0 ~ /STRICT_VALIDATION|validationConfig/) mpVal = 1
        if ($0 ~ /errorHandler/) mpErr = 1
      } else if (lang == "dart") {
        if ($0 ~ /package:genui\//) hit("discontinued genui package; use a2ui_flutter")
        if ($0 ~ /package:a2ui_flutter\/v0_9\//) { v09 = NR }
        else if ($0 ~ /package:a2ui_flutter\/[a-z_\/]*catalog/) { v10 = NR }
        if (v10 && v09 && !mixedReported) { mixedReported = 1; hit("mixed A2UI versions: v0_9 and non-v0_9 a2ui_flutter catalogs in one file") }
      } else if (lang == "json" && hasmsg == 1) {
        if ($0 ~ /"version"[[:space:]]*:[[:space:]]*"v?0\.8"/) hit("A2UI v0.8 message (deprecated)")
        else if ($0 ~ /"version"[[:space:]]*:[[:space:]]*"v1\.0"/) hit("1.0 wire version is \"1.0\" (no v prefix)")
        if (fam == "mixed" && $0 ~ /"version"[[:space:]]*:/ && !mixedReported) { mixedReported = 1; hit("mixed A2UI versions (1.0 and v0.9.x) in one file") }
        if (fam == "1.0" && (($0 ~ /^[[:space:]]*"(path|call)"[[:space:]]*:/ && prevline ~ /\{[[:space:]]*$/) || $0 ~ /\{[[:space:]]*"(path|call)"[[:space:]]*:/))
          hit("v0.9 binding/call key in a 1.0 message; use \"@path\"/\"@call\"")
        if (fam == "1.0" && $0 ~ /"theme"[[:space:]]*:/) hit("createSurface.theme was removed in 1.0")
        if (fam == "0.9" && $0 ~ /"@(path|call|accessibility|checks|catalogId|metadata)"[[:space:]]*:/) hit("1.0 wire field in a v0.9.x message")
        if (names != "" && match($0, /"component"[[:space:]]*:[[:space:]]*"[^"]+"/)) {
          c = substr($0, RSTART, RLENGTH); sub(/^"component"[[:space:]]*:[[:space:]]*"/, "", c); sub(/"$/, "", c)
          if (index(names, " " c " ") == 0) hit("component \"" c "\" is not in the canonical catalog")
        }
      }
      if ((lang == "js" || lang == "dart") && $0 ~ /(onAction|actionHandler|ActionListener|handleAction|dispatchAction)/ && !handlerLine) { handlerLine = NR; handlerText = $0 }
      if ($0 ~ /(allowedActions|isAllowedAction|validateAction|payloadSchema|ALLOWED_ACTIONS)/) guarded = 1
      prevc = ""; if ($0 !~ /^[[:space:]]*$/) prevline = $0
    }
    END {
      if (handlerLine && !guarded) printf "%d: [action handler without an allowlist/payload check] %s\n", handlerLine, trim(handlerText)
      if (mpLine && !(mpVal && mpErr)) printf "%d: [MessageProcessor without validationConfig/STRICT_VALIDATION and errorHandler: unknown components fail silently] %s\n", mpLine, trim(mpText)
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
  msg="A2UI contract drift in $file (advisory, .claude/rules/genui-a2ui.md):
$hits
- Target: A2UI 1.0 (wire \"version\": \"1.0\", @path/@call/@accessibility/@checks). Compatibility path: \"v0.9\"/\"v0.9.1\" only where a renderer is not proven on 1.0. One version per stream and per file; never translate without a tested adapter.
- Render agent content through the renderer's components, never an HTML sink. Every action handler checks the catalog allowlist and payload schema; the server re-authorises.
- Run the contract validator (genui-contract/scripts/validate_a2ui_contract.py). A reviewed, intentional line may carry 'a2ui-version-reviewed: <reason>' on or above it."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out rc
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/web/src/app/features/a2ui" "$tmp/app/lib/features/genui" "$tmp/contract/fixtures/invalid" "$tmp/contract/fixtures/valid" "$tmp/contract/catalog" "$tmp/other/src"
  printf '{ "components": { "ActionCard": {}, "InputForm": {} } }\n' > "$tmp/contract/catalog/canonical-catalog-v1_0.json"
  # positives
  printf "import { SurfaceComponent } from '@a2ui/angular/v0_8';\n" > "$tmp/web/src/app/features/a2ui/v08.ts"
  printf "import { MessageProcessor } from '@a2ui/web_core/v1_0';\nimport { A2uiSurface } from '@a2ui/angular/v0_9';\n" > "$tmp/web/src/app/features/a2ui/mixed.ts"
  printf "el.innerHTML = msg.text;\nconst safe = this.s.bypassSecurityTrustHtml(x);\n" > "$tmp/web/src/app/features/a2ui/sink.ts"
  printf "export function Card(p) { return <div dangerouslySetInnerHTML={{ __html: p.body }} />; }\n" > "$tmp/web/src/app/features/a2ui/card.tsx"
  printf "export function handleAction(msg) {\n  return fetch('/agent', { body: JSON.stringify(msg) });\n}\n" > "$tmp/web/src/app/features/a2ui/actions.ts"
  printf "import 'package:genui/genui.dart';\n" > "$tmp/app/lib/features/genui/old.dart"
  printf "import 'package:a2ui_flutter/v0_9/basic_catalog.dart';\nimport 'package:a2ui_flutter/basic_catalog.dart';\n" > "$tmp/app/lib/features/genui/mixed.dart"
  printf '{ "version": "v0.8", "surfaceUpdate": {} }\n' > "$tmp/contract/product_catalog.json"
  printf '{"messages": [\n{ "version": "v1.0", "createSurface": { "surfaceId": "s1" } }\n]}\n' > "$tmp/contract/fixtures/valid/a2ui-vprefix.json"
  printf '{"messages": [\n{ "version": "1.0", "createSurface": { "surfaceId": "s1" } },\n{ "version": "v0.9", "deleteSurface": { "surfaceId": "s1" } }\n]}\n' > "$tmp/contract/fixtures/valid/a2ui-mixed.json"
  printf '{ "version": "1.0", "updateComponents": { "surfaceId": "s1", "components": [\n  { "id": "root", "component": "ActionCard", "title": {\n    "path": "/t" } }\n] } }\n' > "$tmp/contract/fixtures/valid/a2ui-legacy-binding.json"
  printf '{ "version": "1.0", "createSurface": { "surfaceId": "s1", "theme": { "primaryColor": "#000000" } } }\n' > "$tmp/contract/fixtures/valid/a2ui-theme.json"
  printf '{ "version": "v0.9.1", "updateComponents": { "surfaceId": "s1", "components": [ { "id": "root", "component": "ActionCard", "title": { "@path": "/t" } } ] } }\n' > "$tmp/contract/fixtures/valid/a2ui-v09-with-v1-field.json"
  printf '{ "version": "1.0", "updateComponents": { "surfaceId": "s1", "components": [ { "id": "root", "component": "HtmlBlock" } ] } }\n' > "$tmp/contract/fixtures/valid/a2ui-unknown.json"
  printf '{ "version": "1.0", "createSurface": { "surfaceId": "s1", ' > "$tmp/contract/fixtures/valid/a2ui-broken.json"
  printf "import { X } from '@a2ui/angular/v0_8'; // a2ui-version-reviewed: migration spike\nimport { Y } from '@a2ui/angular/v0_8';\n" > "$tmp/web/src/app/features/a2ui/bleed.ts"
  # negatives
  printf "import { MessageProcessor, Catalog } from '@a2ui/web_core/v1_0';\nimport { provideA2Ui } from '@a2ui/angular';\n" > "$tmp/web/src/app/features/a2ui/target.ts"
  printf "// a2ui-protocol: v0.9.1 compatibility path (renderer not proven on 1.0)\nimport { A2uiSurface } from '@a2ui/angular/v0_9';\nimport { MessageProcessor } from '@a2ui/web_core/v0_9';\n" > "$tmp/web/src/app/features/a2ui/compat.ts"
  printf "export function handleAction(msg) {\n  if (!ALLOWED_ACTIONS.has(msg.action.name)) throw new Error('blocked');\n}\n" > "$tmp/web/src/app/features/a2ui/guarded.ts"
  printf "el.textContent = msg.text;\n" > "$tmp/web/src/app/features/a2ui/text.ts"
  printf "import { MessageProcessor } from '@a2ui/web_core/v0_9';\nexport const p = new MessageProcessor([catalog]);\n" > "$tmp/web/src/app/features/a2ui/mp-bare.ts"
  printf "// a2ui-protocol: v0.9.1 compatibility path\nimport { MessageProcessor, STRICT_VALIDATION } from '@a2ui/web_core/v0_9';\nexport const p = new MessageProcessor([catalog], undefined, {\n  validationConfig: STRICT_VALIDATION, reportErrorsOnly: true,\n  errorHandler: (e) => surfaceError.set(e),\n});\n" > "$tmp/web/src/app/features/a2ui/mp-strict.ts"
  printf "import 'package:a2ui_flutter/v0_9/basic_catalog.dart';\nimport 'package:a2ui_core/a2ui_core.dart';\n" > "$tmp/app/lib/features/genui/ok.dart"
  printf '{ "version": "1.0", "updateComponents": { "surfaceId": "s1", "components": [ { "id": "root", "component": "ActionCard", "title": { "@path": "/t" }, "@accessibility": { "label": "x" } } ] } }\n' > "$tmp/contract/fixtures/valid/a2ui-ok-v1.json"
  printf '{ "version": "v0.9.1", "updateComponents": { "surfaceId": "s1", "components": [ { "id": "root", "component": "InputForm", "title": { "path": "/t" } } ] } }\n' > "$tmp/contract/fixtures/valid/a2ui-ok-v091.json"
  printf '{ "version": "1.0", "updateDataModel": { "surfaceId": "s1", "path": "/user/name", "value": "Ada" } }\n' > "$tmp/contract/fixtures/valid/a2ui-ok-datamodel.json"
  printf '{ "version": "1.0", "components": ["ActionCard"] }\n' > "$tmp/contract/product_catalog_meta.json"
  printf '{ "version": "v0.8", "createSurface": {} }\n' > "$tmp/contract/fixtures/invalid/a2ui-wrong-version.json"
  printf "import { A2uiMessage } from '@a2ui/web_core/v0_8';\n" > "$tmp/other/src/unrelated.ts"
  printf "// do not import '@a2ui/web_core/v0_8' here\nexport const a = 1;\n" > "$tmp/web/src/app/features/a2ui/comment.ts"
  printf "// a2ui-version-reviewed: v0.8 bridge behind a flag\nimport { Z } from '@a2ui/web_core/v0_8';\n" > "$tmp/web/src/app/features/a2ui/exempt.ts"
  probe() { # label file expect(advise|silent) [content-needle]
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | jq -e --arg n "${4:-}" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: TS import of angular/v0_8"                 "$tmp/web/src/app/features/a2ui/v08.ts"          advise "1: [A2UI v0.8 entry point"
  probe "positive: TS mixes /v1_0 and /v0_9 entry points"     "$tmp/web/src/app/features/a2ui/mixed.ts"        advise "2: [mixed A2UI versions"
  probe "positive: innerHTML assignment"                      "$tmp/web/src/app/features/a2ui/sink.ts"         advise "1: [unsafe rendering sink"
  probe "positive: bypassSecurityTrustHtml"                   "$tmp/web/src/app/features/a2ui/sink.ts"         advise "2: [unsafe rendering sink"
  probe "positive: dangerouslySetInnerHTML"                   "$tmp/web/src/app/features/a2ui/card.tsx"        advise "1: [unsafe rendering sink"
  probe "positive: action handler without allowlist check"    "$tmp/web/src/app/features/a2ui/actions.ts"      advise "1: [action handler without an allowlist"
  probe "positive: Dart package:genui import"                 "$tmp/app/lib/features/genui/old.dart"           advise "discontinued genui package"
  probe "positive: Dart mixes v0_9 and non-v0_9 catalogs"     "$tmp/app/lib/features/genui/mixed.dart"         advise "2: [mixed A2UI versions"
  probe "positive: catalog JSON message with v0.8"            "$tmp/contract/product_catalog.json"             advise "1: [A2UI v0.8 message"
  probe "positive: v1.0 wire prefix"                          "$tmp/contract/fixtures/valid/a2ui-vprefix.json" advise "2: [1.0 wire version is"
  probe "positive: 1.0 and v0.9 in one file"                  "$tmp/contract/fixtures/valid/a2ui-mixed.json"   advise "[mixed A2UI versions (1.0 and v0.9.x)"
  probe "positive: v0.9 path binding inside 1.0 message"      "$tmp/contract/fixtures/valid/a2ui-legacy-binding.json" advise "3: [v0.9 binding/call key"
  probe "positive: createSurface.theme in 1.0"                "$tmp/contract/fixtures/valid/a2ui-theme.json"   advise "[createSurface.theme was removed"
  probe "positive: @path inside a v0.9.1 message"             "$tmp/contract/fixtures/valid/a2ui-v09-with-v1-field.json" advise "[1.0 wire field in a v0.9.x message]"
  probe "positive: component outside the canonical catalog"   "$tmp/contract/fixtures/valid/a2ui-unknown.json" advise "[component \"HtmlBlock\" is not in the canonical catalog]"
  probe "positive: unparseable GenUI JSON"                    "$tmp/contract/fixtures/valid/a2ui-broken.json"  advise "[invalid JSON in a GenUI file]"
  probe "positive: trailing marker does not exempt next line" "$tmp/web/src/app/features/a2ui/bleed.ts"        advise "2: [A2UI v0.8 entry point"
  probe "negative: 1.0 entry points (target)"                 "$tmp/web/src/app/features/a2ui/target.ts"       silent
  probe "negative: declared v0.9.1 compatibility path (TS)"   "$tmp/web/src/app/features/a2ui/compat.ts"       silent
  probe "negative: action handler with allowlist check"       "$tmp/web/src/app/features/a2ui/guarded.ts"      silent
  probe "negative: textContent is not a sink"                 "$tmp/web/src/app/features/a2ui/text.ts"         silent
  probe "positive: MessageProcessor without validation/errorHandler" "$tmp/web/src/app/features/a2ui/mp-bare.ts" advise "2: [MessageProcessor without validationConfig"
  probe "negative: v0.9.1 MessageProcessor with STRICT + errorHandler" "$tmp/web/src/app/features/a2ui/mp-strict.ts" silent
  probe "negative: Dart v0_9 catalog import only"             "$tmp/app/lib/features/genui/ok.dart"            silent
  probe "negative: clean 1.0 message with @ keys"             "$tmp/contract/fixtures/valid/a2ui-ok-v1.json"   silent
  probe "negative: clean v0.9.1 compatibility message"        "$tmp/contract/fixtures/valid/a2ui-ok-v091.json" silent
  probe "negative: 1.0 updateDataModel path parameter"        "$tmp/contract/fixtures/valid/a2ui-ok-datamodel.json" silent
  probe "negative: catalog JSON without message keys"         "$tmp/contract/product_catalog_meta.json"        silent
  probe "negative: invalid/ fixtures skipped"                 "$tmp/contract/fixtures/invalid/a2ui-wrong-version.json" silent
  probe "negative: path outside GenUI scope"                  "$tmp/other/src/unrelated.ts"                    silent
  probe "negative: comment line ignored"                      "$tmp/web/src/app/features/a2ui/comment.ts"      silent
  probe "negative: reviewed marker on the line above exempts" "$tmp/web/src/app/features/a2ui/exempt.ts"       silent
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$tmp/web/src/app/features/a2ui/v08.ts" | bash "$self" 2>/dev/null); rc=$?
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
