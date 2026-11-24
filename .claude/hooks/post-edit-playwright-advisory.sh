#!/usr/bin/env bash
# PostToolUse -> Write|Edit: advisory — Playwright Test configs and specs that will flake or pass falsely.
#
# Why: these shapes make a web E2E suite green when it should be red (a stale reused server in CI, a flaky
# pass that exits 0) or flaky by construction (fixed sleeps, networkidle, page-level actions without locators).
# Canonical guidance: .claude/skills/browser-testing/reference/playwright-test-suite.md
#
# Scope:  playwright.config.{ts,mts,cts,js,mjs,cjs}, and spec/setup files (*.spec.*, *.test.*, *.setup.*)
#         that import @playwright/test, or that sit under an e2e/ directory with a playwright.config.* in an
#         ancestor directory (so Vitest/Jest specs are never scanned). Static text checks only: no browser runs
#         here; E2E execution belongs to CI and /verify.
# Config: retries without failOnFlakyTests; reuseExistingServer: true (literal).
# Specs:  waitForTimeout(; networkidle; test/describe .only(; ':visible' in a selector (use .visible());
#         test.skip(...process.env.CI...); page.click/fill/type/check/hover/dblclick/tap/selectOption(selector).
# Exempt: put `// pw-advisory-ok: <reason>` on the flagged line or the line above it. Comment lines are skipped.
# Behavior: ADVISORY. Always exit 0. Findings go to Claude as PostToolUse additionalContext JSON
#         (stderr of an exit-0 hook is not shown to the model). Fails open if jq is missing.
# Test:   bash .claude/hooks/post-edit-playwright-advisory.sh --selftest
set -uo pipefail

# scan_spec <path> -> "line: reason" for each un-exempted hit in a spec file.
scan_spec() {
  awk '
    function flag(reason) { printf "%d: %s  [%s]\n", NR, line, reason; hit = 1 }
    {
      line = $0; hit = 0
      if (line ~ /^[[:space:]]*(\/\/|\*|\/\*)/) { prev = line; next }
      if (line ~ /pw-advisory-ok:/ || prev ~ /pw-advisory-ok:/) { prev = line; next }
      if (line ~ /waitForTimeout[[:space:]]*\(/) flag("fixed sleep: wait with a web-first assertion (toBeVisible, toHaveText)")
      if (line ~ /networkidle/) flag("networkidle is discouraged: assert the content you need")
      if (line ~ /(^|[^A-Za-z0-9_.])(test|describe|it)(\.describe)?\.only[[:space:]]*\(/) flag(".only left in: forbidOnly fails CI, and locally it hides every other test")
      if (line ~ /:visible/) flag("\":visible\" pseudo-class: use locator.visible() (Playwright 1.63+)")
      if (line ~ /test\.skip[[:space:]]*\(/ && line ~ /process\.env\.CI/) flag("skipping on CI hides the failure where it matters: fix it or quarantine with @quarantine")
      if (line ~ /page\.(click|fill|type|check|uncheck|hover|dblclick|tap|selectOption)[[:space:]]*\([[:space:]]*["\x27`]/) flag("page-level action on a selector string: act through a locator (page.getByRole(...).click())")
      prev = line
    }
  ' "$1"
}

# scan_config <path> -> findings for a playwright.config.* file.
scan_config() {
  local f="$1" body
  body=$(grep -vE '^[[:space:]]*(//|\*|/\*)' "$f")
  if printf '%s\n' "$body" | grep -qE 'retries[[:space:]]*:[[:space:]]*([1-9]|process\.env)' \
     && ! printf '%s\n' "$body" | grep -q 'failOnFlakyTests'; then
    echo "retries without failOnFlakyTests: a test that passes only on retry exits 0 (\"flaky\"). Add failOnFlakyTests: !!process.env.CI"
  fi
  printf '%s\n' "$body" | grep -nE 'reuseExistingServer[[:space:]]*:[[:space:]]*true' | grep -v 'pw-advisory-ok:' | while IFS= read -r l; do
    echo "${l%%:*}: reuseExistingServer: true lets CI test a stale server; use reuseExistingServer: !process.env.CI"
  done
}

has_config_ancestor() { # $1 dir -> 0 when an ancestor (max 6 levels) holds playwright.config.*
  local d="$1" i=0 e
  while [ "$i" -lt 6 ] && [ -n "$d" ] && [ "$d" != "/" ]; do
    for e in ts mts cts js mjs cjs; do [ -f "$d/playwright.config.$e" ] && return 0; done
    d=$(dirname "$d"); i=$((i + 1))
  done
  return 1
}

classify() { # $1 path -> prints config | spec | nothing
  local f="$1" base
  base=$(basename "$f")
  case "$base" in
    playwright.config.ts|playwright.config.mts|playwright.config.cts|playwright.config.js|playwright.config.mjs|playwright.config.cjs) echo config; return ;;
    *.spec.ts|*.spec.tsx|*.spec.js|*.spec.mts|*.test.ts|*.test.tsx|*.test.js|*.setup.ts|*.setup.js) ;;
    *) return ;;
  esac
  if grep -qE "from[[:space:]]+['\"]@playwright/test['\"]" "$f"; then echo spec; return; fi
  if grep -qE "from[[:space:]]+['\"](vitest|@jest/globals)['\"]" "$f"; then return; fi
  case "/$f" in */e2e/*) has_config_ancestor "$(dirname "$f")" && echo spec ;; esac
}

run_hook() {
  local input file kind hits msg
  input=$(cat)
  command -v jq >/dev/null 2>&1 || { echo "playwright-advisory: jq not found; check skipped" >&2; return 0; }
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || file=""
  [ -n "$file" ] && [ -f "$file" ] || return 0
  case "$file" in */node_modules/*) return 0 ;; esac
  kind=$(classify "$file")
  case "$kind" in
    config) hits=$(scan_config "$file") ;;
    spec) hits=$(scan_spec "$file") ;;
    *) return 0 ;;
  esac
  [ -n "$hits" ] || return 0
  msg="Playwright $kind advisory for $file:
$hits
Guidance: .claude/skills/browser-testing/reference/playwright-test-suite.md. If a line is intentional, add '// pw-advisory-ok: <reason>' on or above it."
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$m}}'
  return 0
}

selftest() {
  local self fail=0 tmp out
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  if bash -n "$self" 2>/dev/null; then echo "  ok   control 0: parses (bash -n)"; else echo "  FAIL does not parse"; return 1; fi
  command -v jq >/dev/null 2>&1 || { echo "  FAIL jq required"; return 1; }
  tmp=$(mktemp -d) || return 1
  mkdir -p "$tmp/web/e2e" "$tmp/web/src" "$tmp/other/e2e"
  printf "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ retries: process.env.CI ? 2 : 0, webServer: { command: 'x', reuseExistingServer: true } });\n" > "$tmp/web/playwright.config.ts"
  printf "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ retries: 2, failOnFlakyTests: !!process.env.CI, webServer: { command: 'x', reuseExistingServer: !process.env.CI } });\n" > "$tmp/other/playwright.config.ts"
  {
    printf "import { test, expect } from '@playwright/test';\n"
    printf "test('a', async ({ page }) => {\n  await page.waitForTimeout(500);\n"
    printf "  await page.waitForLoadState('networkidle');\n"
    printf "  await page.locator('button:visible').click();\n"
    printf "  await page.click('#submit');\n});\n"
    printf "test.only('b', async () => {});\n"
    printf "test('c', async () => { test.skip(!!process.env.CI, 'flaky'); });\n"
  } > "$tmp/web/e2e/bad.spec.ts"
  {
    printf "import { test, expect } from './fixtures';\n"
    printf "test('ok', async ({ page }) => {\n  // await page.waitForTimeout(500) is never used here\n"
    printf "  await page.getByRole('button', { name: 'Save' }).click();\n"
    printf "  // pw-advisory-ok: third-party widget animates on a timer we do not control\n"
    printf "  await page.waitForTimeout(200);\n"
    printf "  await expect(page.getByRole('status')).toHaveText('Saved');\n});\n"
  } > "$tmp/web/e2e/clean.spec.ts"
  printf "import { test } from './fixtures';\ntest.only('x', async ({ page }) => { await page.waitForTimeout(1); });\n" > "$tmp/web/e2e/fixture-import.spec.ts"
  printf "import { describe, it } from 'vitest';\ndescribe.only('unit', () => { it('x', () => {}); });\n" > "$tmp/web/src/unit.spec.ts"
  printf "import { test } from './fixtures';\ntest.only('x', async () => {});\n" > "$tmp/web/src/no-e2e-dir.spec.ts"
  probe() { # label file expect(advise|silent) [needle]
    out=$(printf '{"tool_input":{"file_path":"%s"}}' "$2" | bash "$self" 2>/dev/null)
    case "$3" in
      advise) if printf '%s' "$out" | jq -e --arg n "$4" '.hookSpecificOutput.additionalContext | contains($n)' >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1 (missing '$4'; got: $out)"; fail=1; fi ;;
      silent) if [ -z "$out" ]; then echo "  ok   $1"; else echo "  FAIL $1 (got: $out)"; fail=1; fi ;;
    esac
  }
  probe "positive config: retries without failOnFlakyTests"  "$tmp/web/playwright.config.ts" advise "retries without failOnFlakyTests"
  probe "positive config: reuseExistingServer: true"         "$tmp/web/playwright.config.ts" advise "reuseExistingServer: true lets CI"
  probe "positive spec: waitForTimeout"                      "$tmp/web/e2e/bad.spec.ts" advise "fixed sleep"
  probe "positive spec: networkidle"                         "$tmp/web/e2e/bad.spec.ts" advise "networkidle is discouraged"
  probe "positive spec: :visible pseudo-class"               "$tmp/web/e2e/bad.spec.ts" advise "locator.visible()"
  probe "positive spec: page.click(selector)"                "$tmp/web/e2e/bad.spec.ts" advise "page-level action"
  probe "positive spec: test.only"                           "$tmp/web/e2e/bad.spec.ts" advise ".only left in"
  probe "positive spec: test.skip on CI"                     "$tmp/web/e2e/bad.spec.ts" advise "quarantine"
  probe "positive spec: fixture import under e2e/ + config"  "$tmp/web/e2e/fixture-import.spec.ts" advise ".only left in"
  probe "negative: clean config"                             "$tmp/other/playwright.config.ts" silent
  probe "negative: clean spec, comment line, exempt marker"  "$tmp/web/e2e/clean.spec.ts" silent
  probe "negative: Vitest spec is never scanned"             "$tmp/web/src/unit.spec.ts" silent
  probe "negative: non-e2e spec without @playwright/test"    "$tmp/web/src/no-e2e-dir.spec.ts" silent
  probe "negative: missing file"                             "$tmp/nope.spec.ts" silent
  rm -rf "$tmp"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi
run_hook
exit 0
