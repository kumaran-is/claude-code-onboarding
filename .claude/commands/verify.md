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
./mvnw compile -q 2>&1; echo "EXIT:$?"

# full
./mvnw test -q 2>&1 | tail -5; echo "EXIT:$?"

# pre-pr additions
./mvnw dependency-check:check -q 2>&1 | grep -E "(CRITICAL|HIGH)"
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
npm run build -- --silent 2>&1 | tail -5; echo "EXIT:$?"

# full
npm run test -- --silent 2>&1 | tail -5; echo "EXIT:$?"

# pre-pr additions
npm audit --audit-level=high
```

### Angular (`angular.json`)
```bash
# quick
npm run build -- --configuration=production --silent 2>&1 | tail -5; echo "EXIT:$?"

# full
npm test -- --watch=false --browsers=ChromeHeadless 2>&1 | tail -5; echo "EXIT:$?"
```

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
| Flutter | ✅ EXIT 0 | ✅ 31 passed | PASS |

### FAIL Details
Python — 2 failures:
- test_create_user_duplicate: AssertionError at tests/test_user.py:45
- test_payment_timeout: TimeoutError at tests/test_payment.py:78

## Final Verdict: ❌ FAIL (1 of 4 stacks failing)
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
- If a stack build tool is missing (`mvnw`, `flutter`, etc.) → report "BUILD TOOL NOT FOUND — install X"
- Do NOT interpret test failure messages — show raw output, human diagnoses
