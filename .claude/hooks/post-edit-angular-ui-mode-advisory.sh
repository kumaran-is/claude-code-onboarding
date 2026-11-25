#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — Angular UI-mode consistency (daisyui | spartan | hybrid).
#
# Why: an Angular workspace picks one UI mode (package.json "config": {"uiMode": ...}); code from an unselected
# library, or a hybrid component on the wrong side of the ownership split, ships two implementations of one
# control and drifts the theme. Canonical guidance: .claude/skills/angular-spa/reference/ui-mode-selection.md
#
# Scope:  edited *.ts, *.mts, *.html, *.css inside an Angular workspace (an ancestor holds angular.json).
#         node_modules, dist and generated Spartan Helm code (libs/ui, libs/helm) are skipped by the detector.
# Checks: the detector .claude/scripts/angular-ui-mode.sh check-file (one detector; /scaffold-angular-app,
#         /verify and CI call the same script). Flags unselected-library imports/classes, hybrid ownership,
#         hybrid `.dark` class toggles, and Tailwind 3 / daisyUI-as-import CSS.
# Exempt: `ui-mode-ok: <reason>` on the flagged line or the line above it.
# Behavior: ADVISORY. Always exit 0. Findings go to Claude as PostToolUse additionalContext JSON. Fails open
#         (says so on stderr) if jq or the detector is missing.
# Test:   bash .claude/hooks/post-edit-angular-ui-mode-advisory.sh --selftest
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECTOR="$HERE/../scripts/angular-ui-mode.sh"

run_hook() {
  local input file hits rc
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "angular-ui-mode-advisory: jq not found; check skipped" >&2; return 0; }
  [ -f "$DETECTOR" ] || { echo "angular-ui-mode-advisory: detector missing at $DETECTOR; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  case "$file" in
    *.ts|*.mts|*.html|*.css) ;;
    *) return 0 ;;
  esac
  case "$file" in */node_modules/*|*/dist/*) return 0 ;; esac
  hits=$(bash "$DETECTOR" check-file "$file" 2>&1); rc=$?
  case "$rc" in
    0) return 0 ;;
    1) ;;
    *) echo "angular-ui-mode-advisory: detector failed (exit $rc): $hits" >&2; return 0 ;;
  esac
  jq -n --arg m "Angular UI-mode advisory for $file:
$hits
Guidance: .claude/skills/angular-spa/reference/ui-mode-selection.md (component ownership per mode). Check the
project with: bash .claude/scripts/angular-ui-mode.sh detect <workspace>. If a line is intentional, add
'ui-mode-ok: <reason>' on or above it." '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out
  self="$HERE/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/d/src/app" "$tmp/h/src/app" "$tmp/d/node_modules/x"
  printf '{"projects":{}}' > "$tmp/d/angular.json"
  printf '{"dependencies":{"daisyui":"5.8.2"},"config":{"uiMode":"daisyui"}}' > "$tmp/d/package.json"
  printf '@import "tailwindcss";\n@plugin "daisyui";\n' > "$tmp/d/src/styles.css"
  printf '{"projects":{}}' > "$tmp/h/angular.json"
  printf '{"dependencies":{"daisyui":"5.8.2","@spartan-ng/brain":"1.10.1"},"config":{"uiMode":"hybrid"}}' > "$tmp/h/package.json"
  printf '{}' > "$tmp/h/components.json"
  printf '@import "tailwindcss";\n@plugin "daisyui";\n@import "@spartan-ng/brain/hlm-tailwind-preset.css";\n' > "$tmp/h/src/styles.css"
  printf "import { HlmDialogImports } from '@spartan-ng/helm/dialog';\n" > "$tmp/d/src/app/bad.ts"
  printf "import { HlmDialogImports } from '@spartan-ng/helm/dialog';\n" > "$tmp/d/node_modules/x/dep.ts"
  printf '<button class="btn btn-primary">Save</button>\n' > "$tmp/d/src/app/ok.html"
  printf '<dialog class="modal"></dialog>\n' > "$tmp/h/src/app/modal.html"
  printf 'const spartan = "@spartan-ng/helm";\n' > "$tmp/d/src/app/notes.md"
  probe() { # label file expect(advise|silent) [needle]
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | jq -e --arg n "${4:-}" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1 (missing '${4:-}'; got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive: Spartan import in a daisyui project"   "$tmp/d/src/app/bad.ts"      advise "[unselected-library] Spartan"
  probe "positive: daisyUI modal in a hybrid project"     "$tmp/h/src/app/modal.html"  advise "Spartan owns the dialog"
  probe "negative: clean daisyui template"                "$tmp/d/src/app/ok.html"     silent
  probe "negative: node_modules skipped"                  "$tmp/d/node_modules/x/dep.ts" silent
  probe "negative: non-web extension skipped"             "$tmp/d/src/app/notes.md"    silent
  probe "negative: missing file"                          "$tmp/d/src/app/nope.ts"     silent
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
