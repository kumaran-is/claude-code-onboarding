---
description: Binary build + test verification for every detected stack (Spring, Python, NestJS, Angular, React, Flutter) with each command's own exit code. Modes quick | full | pre-commit | pre-pr.
argument-hint: "[quick|full|pre-commit|pre-pr]"
allowed-tools: Bash, Read, Glob, Grep
---

# /verify — Binary Build + Test Verification

Runs the fastest possible verification for changed stacks. Returns binary PASS/FAIL with counts.

## Modes

### `/verify` (default: quick)
Compile + lint only. No test execution. Fastest feedback.

### `/verify full`
Compile + lint + all tests. Full confidence.

### `/verify pre-commit`
Quick verify + check for TODO/FIXME/console.log in staged files.

### `/verify pre-pr`
Full verify + security scan + coverage check.

## Stack Detection + Commands

Detected by file presence in current directory tree:

### Spring Boot (`pom.xml` with spring-boot)
```bash
# quick
./mvnw compile -q > /tmp/mvn-compile.log 2>&1; echo "COMPILE EXIT:$?"; tail -10 /tmp/mvn-compile.log

# full
./mvnw test -q > /tmp/mvn-test.log 2>&1; echo "TEST EXIT:$?"; tail -10 /tmp/mvn-test.log

# pre-pr additions (needs the OWASP dependency-check plugin configured in pom.xml; otherwise BLOCKED)
./mvnw dependency-check:check -q > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"; grep -E "(CRITICAL|HIGH)" /tmp/mvn-dc.log
```

### Python (`pyproject.toml` or `requirements.txt`)

Each command's OWN exit code is captured (`cmd | tail; echo $?` reports `tail`'s status: `false | tail; echo $?` prints 0).

```bash
# quick
uv run ruff check . > /tmp/ruff.log 2>&1; echo "RUFF EXIT:$?"; tail -10 /tmp/ruff.log
uv run ruff format --check . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
uv lock --check; echo "LOCK EXIT:$?"          # exit 1 = pyproject and uv.lock disagree

# full
uv run pytest -q --junitxml=/tmp/junit.xml > /tmp/pytest.log 2>&1; echo "PYTEST EXIT:$?"; tail -5 /tmp/pytest.log
uv run python scripts/check_executed.py /tmp/junit.xml; echo "EXECUTED EXIT:$?"   # all-skipped exits 0 in pytest: executed must be > 0

# pre-pr additions
uv run bandit -r src/ -ll -q > /tmp/bandit.log 2>&1; echo "BANDIT EXIT:$?"; tail -10 /tmp/bandit.log
uv export --locked --no-dev --no-hashes --no-emit-project -o /tmp/req.audit.txt > /dev/null; echo "EXPORT EXIT:$?"
uv run pip-audit -r /tmp/req.audit.txt --no-deps --disable-pip > /tmp/audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -15 /tmp/audit.log
```

`pip-audit` has no severity column: gate on its exit code (0 = PASS, 1 = findings = FAIL unless every ID is listed with `--ignore-vuln <ID>` and a reason, 2 = tool/usage error = BLOCKED). `pip audit` is not a command. If `scripts/check_executed.py` does not exist, count executed tests from the junit file yourself (tests minus skipped). Details: `skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

### NestJS (`package.json` with @nestjs/core)
```bash
# quick
npm run build > /tmp/nest-build.log 2>&1; echo "BUILD EXIT:$?"; tail -5 /tmp/nest-build.log

# full
npm test > /tmp/nest-test.log 2>&1; echo "TEST EXIT:$?"; tail -10 /tmp/nest-test.log

# pre-pr additions
npm audit --audit-level=high > /tmp/nest-audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -15 /tmp/nest-audit.log
```

### Web apps — Angular (`angular.json`) and React (`package.json` with `react` + `vite` / `react-scripts` / `next`)

Run this block once from the repo root with `MODE=quick`, `MODE=full` or `MODE=pre-pr`. It finds every app root up to 4 levels deep (`web/<app>/angular.json`, `apps/<app>/package.json`), so nested apps are never skipped, and prints one `PASS` / `FAIL` / `BLOCKED` / `NOT RUN` line per check from the command's own exit code. React Native and NestJS packages are excluded.

| Check | Angular 21 | React (Vite / CRA / Next) |
|---|---|---|
| Type-check | `tsc -p tsconfig.app.json --noEmit` and `tsconfig.spec.json` (the root tsconfig is `"files": []`, so plain `tsc --noEmit` checks nothing). Templates are checked only by `ng build` / `ng test` | `tsc -b` when tsconfig.json has `references` (create-vite), else `tsc --noEmit` |
| Lint (quick+) | `npm run lint` / `ng lint` target / `eslint.config.*`; none → **NOT RUN** (a new Angular 21 workspace has no linter until `ng add angular-eslint`) | `npm run lint` / `eslint.config.*`; none → **NOT RUN** |
| Unit (full+) | `ng test --watch=false` (`@angular/build:unit-test`: Vitest + jsdom by default; no Karma `--browsers` flag) | `vitest run`, else `npm test` |
| Build (full+) | `npm run build` (`ng build`, production by default) | `npm run build` |
| E2E (full+) | `playwright test` when `playwright.config.*` exists; missing browser/server → **BLOCKED** | same |
| Audit (pre-pr) | `npm audit --audit-level=high` | same |

```bash
# Web gate: Angular + React (Vite / CRA / Next) apps, nested roots included. MODE=quick|full|pre-pr.
MODE="${MODE:-quick}"; WEB_FAIL=0; WEB_BLOCKED=0; WEB_NOTRUN=0; WEB_RAN=0; WEB_ROOTS=""
pkg_has() { node -e 'const p=require(process.argv[1]);const s={...p.dependencies,...p.devDependencies};process.exit(process.argv.slice(2).some(n=>n in s)?0:1)' "$1/package.json" "${@:2}" 2>/dev/null; }
has_script() { node -e 'const p=require(process.argv[1]);process.exit(p.scripts&&p.scripts[process.argv[2]]?0:1)' "$1/package.json" "$2" 2>/dev/null; }
web_check() { # root label cmd... -> PASS/FAIL from the command's OWN exit code; log tail only on failure
  local root="$1" label="$2" log rc; shift 2; log=$(mktemp)
  (cd "$root" && CI=true NO_COLOR=1 FORCE_COLOR=0 "$@") > "$log" 2>&1; rc=$?
  if [ "$rc" -eq 0 ]; then echo "WEB $root | $label: PASS (exit 0)"; WEB_RAN=$((WEB_RAN + 1))
  elif [ "$label" = e2e ] && grep -qE "Executable doesn't exist|browserType\.launch|ECONNREFUSED" "$log"; then echo "WEB $root | $label: BLOCKED (exit $rc: browser or server missing)"; tail -5 "$log"; WEB_BLOCKED=1
  else echo "WEB $root | $label: FAIL (exit $rc)"; tail -15 "$log"; WEB_FAIL=1; WEB_RAN=$((WEB_RAN + 1)); fi
  rm -f "$log"
}
not_run() { echo "WEB $1 | $2: NOT RUN ($3)"; WEB_NOTRUN=$((WEB_NOTRUN + 1)); }
FOUND=$(find . -maxdepth 4 \( -name node_modules -o -name dist -o -name .git -o -name .angular \) -prune -o \( -name angular.json -o -name package.json \) -print)
while IFS= read -r f; do
  [ -n "$f" ] || continue; d=$(dirname "$f")
  case "$f" in
    */angular.json) WEB_ROOTS="${WEB_ROOTS}angular:$d
" ;;
    */package.json) [ -f "$d/angular.json" ] && continue
      pkg_has "$d" react && pkg_has "$d" vite react-scripts next && ! pkg_has "$d" react-native @angular/core && WEB_ROOTS="${WEB_ROOTS}react:$d
" ;;
  esac
done <<EOF_FOUND
$FOUND
EOF_FOUND
[ -n "$WEB_ROOTS" ] || echo "WEB: NOT APPLICABLE (no Angular/React app within 4 levels of $(pwd))"
while IFS= read -r entry <&3; do
  [ -n "$entry" ] || continue
  kind="${entry%%:*}"; root="${entry#*:}"
  echo "WEB $root: $kind"
  if [ ! -d "$root/node_modules" ]; then echo "WEB $root | all checks: BLOCKED (no node_modules: run npm ci in $root)"; WEB_BLOCKED=1; continue; fi
  # 1. type-check (the root tsconfig of Angular 21 / create-vite has "files": [] -> plain `tsc --noEmit` there checks nothing)
  if [ ! -f "$root/tsconfig.json" ]; then not_run "$root" typecheck "no tsconfig.json (JavaScript-only app)"
  elif [ ! -x "$root/node_modules/.bin/tsc" ]; then echo "WEB $root | typecheck: BLOCKED (tsconfig.json present but no local typescript: npm ci)"; WEB_BLOCKED=1
  elif [ "$kind" = angular ]; then
    for cfg in tsconfig.app.json tsconfig.spec.json; do
      [ -f "$root/$cfg" ] && web_check "$root" "typecheck $cfg" npx tsc -p "$cfg" --noEmit
    done
  elif grep -q '"references"' "$root/tsconfig.json" 2>/dev/null; then web_check "$root" "typecheck" npx tsc -b
  else web_check "$root" "typecheck" npx tsc --noEmit; fi
  # 2. lint: only a configured linter; absence is NOT RUN, never PASS
  if has_script "$root" lint; then web_check "$root" lint npm run lint
  elif [ "$kind" = angular ] && grep -q '"lint"' "$root/angular.json"; then web_check "$root" lint npx ng lint
  elif ls "$root"/eslint.config.* >/dev/null 2>&1; then web_check "$root" lint npx eslint .
  else not_run "$root" lint "no lint script, ng lint target or eslint.config.* (Angular: ng add angular-eslint)"; fi
  [ "$MODE" = quick ] && continue
  # 3. unit tests
  if [ "$kind" = angular ]; then
    if grep -q '"@angular/build:unit-test"' "$root/angular.json"; then web_check "$root" "unit (ng test, Vitest)" npx ng test --watch=false
    elif grep -q '"test"' "$root/angular.json"; then web_check "$root" "unit (ng test, configured builder)" npx ng test --watch=false
    else not_run "$root" unit "no test target in angular.json"; fi
  elif [ -x "$root/node_modules/.bin/vitest" ]; then web_check "$root" "unit (vitest)" npx vitest run
  elif has_script "$root" test; then web_check "$root" "unit (npm test)" npm test
  else not_run "$root" unit "no vitest and no test script"; fi
  # 4. production build (Angular: also the only template type-check)
  if has_script "$root" build; then web_check "$root" build npm run build
  elif [ "$kind" = angular ]; then web_check "$root" build npx ng build
  else not_run "$root" build "no build script"; fi
  # 5. E2E (Playwright), when configured
  if ls "$root"/playwright.config.* >/dev/null 2>&1; then web_check "$root" e2e npx playwright test
  else not_run "$root" e2e "no playwright.config.*"; fi
  [ "$MODE" = pre-pr ] && web_check "$root" "npm audit (high)" npm audit --audit-level=high
done 3<<EOF_ROOTS
$WEB_ROOTS
EOF_ROOTS
if [ "$WEB_FAIL" -ne 0 ]; then v=FAIL; elif [ "$WEB_BLOCKED" -ne 0 ]; then v=BLOCKED; elif [ -z "$WEB_ROOTS" ]; then v="NOT APPLICABLE"; elif [ "$WEB_RAN" -eq 0 ]; then v="NOT RUN"; else v=PASS; fi
echo "WEB VERDICT: $v; $WEB_NOTRUN check(s) NOT RUN (not passes: report each with its reason)"
[ "$v" = PASS ] || [ "$v" = "NOT APPLICABLE" ]
```

Proven on 2026-11-22 fixtures (Angular CLI 21.2.30, create-vite 9.3.4 + TypeScript 5.9.3, Vitest 5.1.1): clean apps → PASS; planted `const n: number = "x"` → typecheck + unit + build FAIL; an unknown template binding (NG8002) passes `tsc` and FAILs `ng test` and `ng build`; no lint setup → NOT RUN; no `node_modules` → BLOCKED. The previous line `npm run build -- --configuration=production --silent 2>&1 | tail -5; echo "EXIT:$?"` printed `EXIT:0` on a broken build (`--silent` is also rejected by `ng build`). In a multi-project Angular workspace, run `ng test <project>` / `ng build <project>` per project (UNVERIFIED — check `ng test --help` before relying on the no-argument form). Web UI tool choice: `.claude/rules/testing-tool-selection.md`.

### Flutter (`pubspec.yaml` with flutter:)

Capture each command's OWN exit code (a pipe into `tail` reports `tail`'s status, not the tool's):

```bash
# quick — static checks (every Dart change)
dart format --output=none --set-exit-if-changed . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
flutter analyze --no-pub > /tmp/analyze.log 2>&1; echo "ANALYZE EXIT:$?"; tail -5 /tmp/analyze.log

# full — tests (per package root in a multi-package repo; mixing roots fabricates failures)
flutter test > /tmp/test.log 2>&1; echo "TEST EXIT:$?"; tail -5 /tmp/test.log
```

Count `error`, `warning` AND `info` findings from `flutter analyze` — by default it exits non-zero on info-level issues too (confirm for your SDK version with `flutter analyze --help`).

**Proportional validation.** Run what the change can affect — not everything, not less. The full change-type table is in
[flutter-testing-traps.md §10](../skills/flutter-mobile/reference/flutter-testing-traps.md); summary:

| Change | Minimum before reporting PASS |
|--------|-------------------------------|
| Dart source (logic, state) | format + analyze + the tests that reach the changed code |
| Widget / screen / navigation | the above + a widget test per state; a routing/boot test for navigation |
| Offline / sync | the above + the sync/outbox tests; device-only checks on a simulator are BLOCKED, not PASS |
| Native / platform config (Gradle, Info.plist, manifests, entitlements) | analyze + a build for each affected platform |
| Generated code / l10n inputs | regenerate first, then format + analyze + tests |
| CI, hooks, scripts | run the script itself (self-test or dry run); app tests are NOT APPLICABLE |
| Docs / comments only | app checks are NOT APPLICABLE; confirm no code file changed |

**UI/E2E on a Flutter Android/iOS target** uses Maestro only (`.claude/rules/testing-tool-selection.md`); if Maestro or a device is missing the check is `BLOCKED`, never a browser substitute.

**Status vocabulary** (per check, never blended): `PASS` ran and succeeded · `FAIL` ran and failed · `BLOCKED` could not
run (say why: no device, tool missing, backend down) · `NOT RUN` skipped by choice (say why) · `NOT APPLICABLE` the change
cannot affect it. Only `PASS` counts as a pass.

## Output Format

```
## Verification — {mode} — {date}

| Stack | Compile | Tests | Status |
|-------|---------|-------|--------|
| Spring Boot | ✅ EXIT 0 | ✅ 47 passed | PASS |
| Python | ✅ EXIT 0 | ❌ 2 failed | FAIL |
| NestJS | ✅ EXIT 0 | ✅ 83 passed | PASS |
| Angular `web/admin` | ✅ EXIT 0 (lint NOT RUN: no linter) | ✅ 12 passed | PASS |
| React `apps/site` | ✅ EXIT 0 | ❌ 1 failed | FAIL |
| Flutter | ✅ EXIT 0 | ✅ 31 passed | PASS |

### FAIL Details
Python — 2 failures:
- test_create_user_duplicate: AssertionError at tests/test_user.py:45
- test_payment_timeout: TimeoutError at tests/test_payment.py:78

## Final Verdict: ❌ FAIL (2 of 6 stacks failing)
```

**Binary rule:** If ANY stack fails → overall verdict is FAIL. No partial credit.

## pre-commit Checks

```bash
# Check staged files for forbidden patterns
git diff --cached --name-only | xargs grep -n "TODO\|FIXME\|console\.log\|print(" 2>/dev/null
```

If any matches: list them. These are not blocking (human decides) but must be acknowledged.

## Rules

- Run ALL detected stacks — never skip a stack silently
- Report exact exit codes — not "it looks like it passed"; use the command's own exit code, never a pipe's
- A scan that reports ZERO findings needs a positive control: a known-bad input the same scan must flag
- A test run that EXECUTED zero tests is not a PASS (all-skipped exits 0): report collected / skipped / executed
- A diff-aware check that is green on UNCOMMITTED work is vacuous (it sees no changed files) — commit first or say "vacuous"
- If a stack build tool is missing (`mvnw`, `flutter`, `node_modules`, etc.) → report BLOCKED with "install X" — never PASS
- A check with nothing configured (no lint script, no E2E config) is NOT RUN with its reason, never PASS
- Do NOT interpret test failure messages — show raw output, human diagnoses
