---
name: ship
description: Comprehensive pre-deployment readiness check across all stacks (Java/Spring, NestJS, Python/FastAPI, Angular, React, Flutter). Runs tests, linting, build, security audit, secrets scan, and migration checks. Outputs a Ship Readiness Report with READY TO SHIP / NOT READY verdict.
allowed-tools: Bash, Read, Glob, Grep
---

# Ship — Pre-Deploy Readiness Check

Run before every production or staging deployment to verify the branch is safe to ship.

## Step 1 — Detect Stack

Check which stacks are present in the repo root (web apps are also found in nested folders by the web block in Step 2):

```bash
[ -f "pom.xml" ]        && echo "STACK:java"
[ -f "package.json" ]   && grep -q '"@nestjs/core"' package.json && echo "STACK:nestjs"
find . -maxdepth 4 -name node_modules -prune -o \( -name angular.json -o -name 'vite.config.*' -o -name 'next.config.*' \) -print | sed 's/^/STACK:web /'
[ -f "pyproject.toml" ] || [ -f "requirements.txt" ] && echo "STACK:python"
[ -f "pubspec.yaml" ]   && echo "STACK:flutter"
git log --oneline -3
git status --short
```

Run all applicable checks below for each detected stack.

## Step 1b — Security Lock Document Check

Before running any stack checks, verify a security approval exists for the current commit:

```bash
COMMIT=$(git rev-parse --short HEAD)
ls docs/approvals/security-*-${COMMIT}.md 2>/dev/null && echo "LOCK: found" || echo "LOCK: missing"
```

**If missing:** STOP. Do not proceed with the ship check.

```
❌ BLOCKED: No security approval found for commit [COMMIT].

Run /audit-security first. The Lock Document (docs/approvals/security-*-[COMMIT].md)
must exist before /ship can proceed. This ensures the security audit was not skipped.

If this is a staging deploy and you intentionally want to skip the security gate,
pass --skip-security-lock with explicit justification.
```

**If found:** continue to Step 2.

## Step 2 — Blockers (must all pass)

Every command below records its OWN exit code (`cmd > log 2>&1; echo "EXIT:$?"`, then `tail` the log); `cmd | tail; echo $?` reports `tail`'s status and turns a failure into a pass.

### Java / Spring Boot
```bash
./mvnw test -q > /tmp/mvn-test.log 2>&1; echo "TEST EXIT:$?"; tail -20 /tmp/mvn-test.log
./mvnw package -DskipTests -q > /tmp/mvn-pkg.log 2>&1; echo "PACKAGE EXIT:$?"; tail -10 /tmp/mvn-pkg.log
./mvnw dependency-check:check -q > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"; grep -E "CRITICAL|HIGH|CVE" /tmp/mvn-dc.log | head -20   # plugin not configured → BLOCKED
```

### NestJS
```bash
npm test > /tmp/nest-test.log 2>&1; echo "TEST EXIT:$?"; tail -20 /tmp/nest-test.log   # no --passWithNoTests: zero tests is not a pass
npx tsc --noEmit > /tmp/nest-tsc.log 2>&1; echo "TSC EXIT:$?"; head -20 /tmp/nest-tsc.log
if node -e 'process.exit(require("./package.json").scripts?.lint?0:1)'; then npm run lint > /tmp/nest-lint.log 2>&1; echo "LINT EXIT:$?"; tail -10 /tmp/nest-lint.log; else echo "LINT: NOT RUN (no lint script)"; fi
npm run build > /tmp/nest-build.log 2>&1; echo "BUILD EXIT:$?"; tail -10 /tmp/nest-build.log
npm audit --audit-level=high > /tmp/nest-audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -20 /tmp/nest-audit.log
```

### Web apps — Angular and React
Run the web block from [`/verify`](verify.md) ("Web apps" section) from the repo root with `MODE=pre-pr`: per app root it runs type-check, lint, unit tests (`ng test --watch=false` on Angular 21's Vitest builder, `vitest run` for React), production build, Playwright E2E when configured, and `npm audit --audit-level=high`, each with its own exit code. Copy its `WEB ... : PASS|FAIL|BLOCKED|NOT RUN` lines into the report. A detected app that the block did not run is a blocker, not a pass; `NOT RUN` (no linter, no E2E config) is listed with its reason and never counted as passed. Any web check reported `FAIL` or `BLOCKED` makes the verdict **NOT READY**.

### Python / FastAPI
Capture each tool's own exit code (a pipe into `tail` reports `tail`'s status). Report `PASS` / `FAIL` / `BLOCKED` / `NOT RUN` / `NOT APPLICABLE` per check.

```bash
uv lock --check; echo "LOCK EXIT:$?"
uv run pytest -q --junitxml=/tmp/junit.xml > /tmp/pytest.log 2>&1; echo "PYTEST EXIT:$?"; tail -20 /tmp/pytest.log
uv run python scripts/check_executed.py /tmp/junit.xml; echo "EXECUTED EXIT:$?"   # executed > 0; all-skipped exits 0 in pytest
uv run mypy . > /tmp/mypy.log 2>&1; echo "MYPY EXIT:$?"; tail -10 /tmp/mypy.log
uv run ruff check . > /tmp/ruff.log 2>&1; echo "RUFF EXIT:$?"; tail -10 /tmp/ruff.log
uv run ruff format --check . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
uv export --locked --no-dev --no-hashes --no-emit-project -o /tmp/req.audit.txt > /dev/null; echo "EXPORT EXIT:$?"
uv run pip-audit -r /tmp/req.audit.txt --no-deps --disable-pip > /tmp/audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -20 /tmp/audit.log
```

- `pip-audit` prints name / version / advisory ID / fix versions and NO severity, so grepping it for `CRITICAL|HIGH` is always empty (a false green). Exit 0 = PASS; exit 1 = findings = FAIL unless each ID is accepted explicitly (`--ignore-vuln <ID>`, with reason and expiry); exit 2 = BLOCKED. `pip audit` is not a command.
- Do not add `--ignore-missing-imports` to mypy as a default: it hides missing stubs; configure per-package overrides in `pyproject.toml`.
- Canonical audit/CI details: `skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

### Flutter
Capture each command's own exit code (a pipe into `tail` hides it). Report every check as `PASS` / `FAIL` /
`BLOCKED` (could not run — say why) / `NOT RUN` (skipped — say why) / `NOT APPLICABLE`; only `PASS` counts toward
READY TO SHIP. Proportional validation by change type:
[flutter-testing-traps.md §10](../skills/flutter-mobile/reference/flutter-testing-traps.md).

```bash
dart format --output=none --set-exit-if-changed . > /tmp/fmt.log 2>&1; echo "FORMAT EXIT:$?"; tail -5 /tmp/fmt.log
flutter analyze > /tmp/analyze.log 2>&1; echo "ANALYZE EXIT:$?"; tail -20 /tmp/analyze.log   # 0 issues, incl. info
flutter test --coverage > /tmp/test.log 2>&1; echo "TEST EXIT:$?"; tail -20 /tmp/test.log
flutter build apk --release > /tmp/build.log 2>&1; echo "BUILD EXIT:$?"; tail -10 /tmp/build.log
```

- Flutter mobile UI/E2E gates run with Maestro only (`.claude/rules/testing-tool-selection.md`); a missing Maestro/device is BLOCKED, not a browser substitute
- Run heavy gates (device/E2E, release builds) LAST, after version bump and changelog are final — a later edit voids them.
- Checks that cannot run here (iOS build on Linux, offline behaviour on a simulator) are `BLOCKED`, never `PASS`.
- Zero findings from a scan/grep is evidence only if a known-bad input proved the same scan can fire (positive control).
- Run against COMMITTED work: a diff-aware check on uncommitted changes sees nothing and passes vacuously.

## Step 3 — High Priority (should pass)

```bash
# Hardcoded credentials in source files
grep -rn \
  -e "password\s*=" \
  -e "api_key\s*=" \
  -e "secret\s*=" \
  -e "AWS_ACCESS_KEY" \
  -e "PRIVATE_KEY" \
  --include="*.java" --include="*.ts" --include="*.py" --include="*.dart" \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=build --exclude-dir=target \
  . 2>/dev/null | grep -v ".example" | grep -v "_test\." | head -20

# console.log in TypeScript (should use NestJS Logger or Angular ErrorHandler)
grep -rn "console\.log\b\|console\.debug\b" \
  --include="*.ts" \
  --exclude-dir=node_modules --exclude-dir=dist \
  . 2>/dev/null | grep -v "// allowed" | head -10

# print() in Python (should use structured logger)
grep -rn "^\s*print(" --include="*.py" . 2>/dev/null | head -10

# TODO / FIXME in files changed since last commit
git diff --name-only HEAD~1 2>/dev/null | xargs grep -lnE "TODO|FIXME|HACK|XXX" 2>/dev/null | head -10

# Database migrations count
[ -d "src/main/resources/db/migration" ] && \
  echo "Flyway migrations: $(find src/main/resources/db/migration -name '*.sql' | wc -l | tr -d ' ') total"
[ -d "prisma/migrations" ] && \
  echo "Prisma migrations: $(find prisma/migrations -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') total"
```

## Step 4 — Recommended

```bash
# CHANGELOG or docs updated in last 5 commits
git diff --name-only HEAD~5 2>/dev/null | grep -E "CHANGELOG|README|docs/" | head -5

# .env.example present
[ -f ".env.example" ] && echo "OK .env.example exists" || echo "WARN .env.example missing"

# localhost refs in non-dev config
grep -rn "localhost\|127\.0\.0\.1" \
  --include="*.properties" --include="*.yml" --include="*.yaml" \
  --exclude-dir=.git . 2>/dev/null \
  | grep -v "test\|dev\|local\|example" | head -10

# Debug flags
grep -rn "DEBUG\s*=\s*true\|NODE_ENV\s*=\s*development" \
  --include="*.env*" --include="*.properties" \
  --exclude-dir=.git . 2>/dev/null | head -5
```

## Step 5 — Render Ship Readiness Report

Summarise all results from Steps 2–4 in this format:

```
Branch:  [current branch]
Commit:  [HEAD short hash — message]
Target:  [production | staging]   (auto: main/master=production, develop/staging=staging)
Stacks:  [detected stacks]

BLOCKERS (must fix before deploying)
─────────────────────────────────────────────────
Tests          ✅ N passed  |  ❌ N failed — [detail]
Type check     ✅ clean     |  ❌ N errors
Lint           ✅ clean     |  ❌ N issues  |  ⏸ NOT RUN — [reason; not a pass]
Build          ✅ success   |  ❌ failed — [detail]
CVE audit      ✅ none      |  ❌ N high/critical — [list]
Web apps       ✅ all PASS  |  ❌ FAIL/BLOCKED — [root | check]  |  ⏸ NOT RUN — [check: reason]

HIGH PRIORITY
─────────────────────────────────────────────────
Credentials    ✅ clean     |  ⚠️  N matches — [files]
Console leaks  ✅ clean     |  ⚠️  N found — [file:line]
TODOs changed  ✅ none      |  ⚠️  N in changed files
Migrations     ✅ N total   |  ⚠️  [detail]

RECOMMENDED
─────────────────────────────────────────────────
Docs updated   ✅ yes       |  ⚠️  no changelog in last 5 commits
.env.example   ✅ present   |  ⚠️  missing
Localhost refs ✅ clean     |  ⚠️  N in prod config
Debug flags    ✅ off       |  ⚠️  found

─────────────────────────────────────────────────
Blockers:      X/6 passed
High priority: X/4 passed
Recommended:   X/4 passed

Verdict: ✅ READY TO SHIP  |  ❌ NOT READY — fix blockers first
─────────────────────────────────────────────────

Action Items (if NOT READY):
1. [Most critical fix]
2. [Second priority]
3. [Third priority]
```

## Usage

```
/ship                    # Full check, auto-detect target from branch name
/ship --target=staging   # Explicit target label in report
/ship --quick            # Blockers only (skip high priority + recommended)
/ship --stack=nestjs     # Force single stack (skip auto-detect)
```

**Branch to target mapping (auto):**
- `main` / `master` → production
- `develop` / `staging` → staging
- `feature/*` / `bugfix/*` → staging

## Tips

- Run before opening a PR, not just before merging
- `--quick` runs Step 2 only — fastest signal when iterating
- A clean `/ship` does not replace `/audit-security` for major releases

## Related Commands

- `/audit-security` — deep OWASP security audit
- `/validate-changes` — LLM-as-a-Judge review of staged diff
- `/review-code` — code quality and security reviewer agents

$ARGUMENTS
