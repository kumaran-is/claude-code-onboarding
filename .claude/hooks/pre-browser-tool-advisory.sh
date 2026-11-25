#!/usr/bin/env bash
# PreToolUse -> browser automation tools (and Bash calls that start one): advisory test-tool routing.
#
# Rule (canonical): .claude/rules/testing-tool-selection.md
#   Flutter Android/iOS UI/E2E -> Maestro CLI/MCP only; browser automation is for web targets.
#
# Fires when the call is a browser tool (mcp__chrome-devtools__*, mcp__claude-in-chrome__*,
# or a Bash command that starts playwright-cli / npx|npm exec|pnpm exec|yarn|bunx playwright (test|cli|...) / puppeteer / cypress / selenium) AND the
# workspace contains a Flutter MOBILE app (a pubspec.yaml that depends on the Flutter SDK with an android/ or
# ios/ directory beside it, up to 4 levels deep). A web-only repo, or a Flutter project with no mobile target,
# is silent. In a hybrid repo it is a reminder, not a block: the call may well target the Angular/React side.
#
# Advisory only: always exits 0. Delivered as PreToolUse additionalContext (stderr of an exit-0 hook is not
# delivered). Throttled to once per session. Fails open if jq is missing.
# Test: bash .claude/hooks/pre-browser-tool-advisory.sh --selftest
set -uo pipefail

BROWSER_TOOL='^mcp__(chrome-devtools|claude-in-chrome)__'
BROWSER_CMD='(^|[;&|])[[:space:]]*(npx[[:space:]]+((-y|--no-install)[[:space:]]+)?|npm[[:space:]]+exec[[:space:]]+(--no[[:space:]]+)?(--[[:space:]]+)?|pnpm[[:space:]]+((exec|dlx)[[:space:]]+)?|yarn[[:space:]]+(dlx[[:space:]]+)?|bunx[[:space:]]+)?(playwright-cli|playwright[[:space:]]+(test|cli|codegen|install|open)|puppeteer|cypress[[:space:]]+(run|open)|selenium)'

flutter_mobile_app() { # $1 = root; prints the first mobile app dir found
  local root="$1" f d
  while IFS= read -r f; do
    d=$(dirname "$f")
    if grep -qE '^[[:space:]]+sdk:[[:space:]]*flutter' "$f" 2>/dev/null && { [ -d "$d/android" ] || [ -d "$d/ios" ]; }; then
      printf '%s' "${d#"$root"/}"; [ "$d" = "$root" ] && printf '.'
      return 0
    fi
  done < <(find "$root" -maxdepth 4 \( -name node_modules -o -name .dart_tool -o -name build -o -name .git -o -name .symlinks \) -prune -o -name pubspec.yaml -print 2>/dev/null)
  return 1
}

state_dir_for() { # $1 project root -> runtime state dir inside its git dir (never the working tree); temp dir outside git
  local d
  if d=$(git -C "$1" rev-parse --git-common-dir 2>/dev/null); then
    case "$d" in /*) ;; *) d="$1/$d" ;; esac
    printf '%s/claude-state' "$d"
  else
    printf '%s/claude-state/%s' "${TMPDIR:-/tmp}" "$(printf '%s' "$1" | shasum | cut -c1-12)"
  fi
}

evaluate() { # $1 = tool name, $2 = bash command, $3 = root, $4 = session id, $5 = state dir
  local tool="$1" cmd="$2" root="$3" sid="$4" state="$5" app marker msg
  if [[ "$tool" =~ $BROWSER_TOOL ]]; then :
  elif [ "$tool" = "Bash" ] && printf '%s' "$cmd" | grep -qE "$BROWSER_CMD"; then :
  else return 0; fi
  app=$(flutter_mobile_app "$root") || return 0
  marker="$state/browser-advisory-${sid:-nosession}"
  [ -e "$marker" ] && return 0
  mkdir -p "$state" 2>/dev/null && : > "$marker" 2>/dev/null
  msg="This workspace contains a Flutter mobile app (${app}). Test-tool rule (.claude/rules/testing-tool-selection.md): UI/E2E automation for its Android/iOS builds uses Maestro CLI/MCP only; browser automation is for web targets (Angular/React sites, a Flutter web build). If this call is meant to test the mobile app, switch to Maestro, or report BLOCKED/NOT RUN if Maestro or an emulator/simulator/device is unavailable; do not substitute a browser. If it targets a web app, carry on."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
}

selftest() {
  local fail=0 t out
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  t=$(mktemp -d)
  mkdir -p "$t/mobile/apps/app/android" "$t/web/src" "$t/fluweb/app" "$t/hybrid/apps/mobile/ios" "$t/hybrid/web" "$t/mobile/node_modules/x/android"
  printf 'dependencies:\n  flutter:\n    sdk: flutter\n' | tee "$t/mobile/apps/app/pubspec.yaml" "$t/fluweb/app/pubspec.yaml" "$t/hybrid/apps/mobile/pubspec.yaml" >/dev/null
  echo '{"name":"site"}' > "$t/web/package.json"
  chk() { # label want(advise|silent) tool cmd root session
    out=$(evaluate "$3" "$4" "$5" "$6" "$t/state"); case "$2" in
      advise) printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext|test("Maestro")' >/dev/null 2>&1 && echo "  ok   $1" || { echo "  FAIL $1 (no advisory)"; fail=1; } ;;
      silent) [ -z "$out" ] && echo "  ok   $1" || { echo "  FAIL $1 (unexpected output)"; fail=1; } ;; esac; }
  chk "Flutter Android app + Chrome DevTools MCP -> advises"        advise mcp__chrome-devtools__navigate_page "" "$t/mobile" s1
  chk "Flutter iOS app + Chrome DevTools MCP -> advises"            advise mcp__chrome-devtools__take_snapshot "" "$t/hybrid" s2
  chk "Flutter app + claude-in-chrome -> advises"                   advise mcp__claude-in-chrome__navigate "" "$t/mobile" s3
  chk "Flutter app + Bash playwright-cli -> advises"                advise Bash "playwright-cli goto http://localhost:4200" "$t/mobile" s4
  chk "Flutter app + npx playwright test -> advises"                advise Bash "cd web && npx playwright test" "$t/mobile" s5
  chk "Flutter app + pnpm exec playwright test -> advises"          advise Bash "pnpm exec playwright test" "$t/mobile" s13
  chk "Flutter app + yarn playwright test -> advises"               advise Bash "yarn playwright test --project=desktop" "$t/hybrid" s14
  chk "Flutter app + bunx playwright-cli -> advises"                advise Bash "bunx playwright-cli open http://x" "$t/mobile" s15
  chk "Flutter app + npx --no-install playwright cli -> advises"    advise Bash "npx --no-install playwright cli -s=qa open http://x" "$t/mobile" s18
  chk "Flutter app + npm exec --no -- playwright test -> advises"   advise Bash "npm exec --no -- playwright test" "$t/hybrid" s19
  chk "web-only repo + pnpm exec playwright test -> silent"         silent Bash "pnpm exec playwright test" "$t/web" s16
  chk "Flutter app + pnpm install (not a browser run) -> silent"    silent Bash "pnpm install" "$t/mobile" s17
  chk "same session again -> throttled"                             silent mcp__chrome-devtools__click "" "$t/mobile" s1
  chk "web-only repo + Chrome DevTools MCP -> silent"               silent mcp__chrome-devtools__navigate_page "" "$t/web" s6
  chk "web-only repo + playwright-cli -> silent"                    silent Bash "playwright-cli goto http://x" "$t/web" s7
  chk "Flutter web-only project (no android/ios) -> silent"         silent mcp__chrome-devtools__navigate_page "" "$t/fluweb" s8
  chk "Flutter app + non-browser Bash command -> silent"            silent Bash "flutter test" "$t/mobile" s9
  chk "Flutter app + maestro MCP -> silent"                         silent mcp__maestro__run "" "$t/mobile" s10
  chk "Flutter app + a grep that only mentions playwright -> silent" silent Bash "grep -rn playwright-cli docs" "$t/mobile" s11
  chk "pubspec only inside node_modules is ignored -> silent"       silent mcp__chrome-devtools__click "" "$t/web" s12
  rm -rf "$t"
  [ "$fail" -eq 0 ] && echo "selftest PASS" || echo "selftest FAIL"
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)
SID=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
ROOT="${CLAUDE_PROJECT_DIR:-$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)}"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || exit 0
evaluate "$TOOL" "$CMD" "$ROOT" "$SID" "$(state_dir_for "$ROOT")"
exit 0
