---
name: ship
description: Comprehensive pre-deployment readiness check across all stacks (Java/Spring, NestJS, Python/FastAPI, Angular, Flutter). Runs tests, linting, build, security audit, secrets scan, and migration checks. Outputs a Ship Readiness Report with READY TO SHIP / NOT READY verdict.
allowed-tools: Bash, Read, Glob, Grep
---

# Ship — Pre-Deploy Readiness Check

Run before every production or staging deployment to verify the branch is safe to ship.

## Step 1 — Detect Stack

Check which stacks are present in the repo root:

```bash
[ -f "pom.xml" ]        && echo "STACK:java"
[ -f "package.json" ]   && grep -q '"@nestjs/core"' package.json && echo "STACK:nestjs"
[ -f "package.json" ]   && grep -q '"@angular/core"' package.json && echo "STACK:angular"
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

### Java / Spring Boot
```bash
./mvnw test -q 2>&1 | tail -20
./mvnw package -DskipTests -q 2>&1 | tail -10
./mvnw dependency:check -q 2>&1 | grep -E "WARN|ERROR|CVE" | head -20
```

### NestJS
```bash
npm test -- --passWithNoTests 2>&1 | tail -20
npx tsc --noEmit 2>&1 | head -20
npm run lint 2>&1 | tail -10
npm run build 2>&1 | tail -10
npm audit --audit-level=high 2>&1 | tail -20
```

### Angular
```bash
npm test -- --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
npx tsc --noEmit 2>&1 | head -20
npm run lint 2>&1 | tail -10
npm run build -- --configuration=production 2>&1 | tail -10
```

### Python / FastAPI
```bash
uv run pytest -q 2>&1 | tail -20
uv run mypy . --ignore-missing-imports 2>&1 | tail -10
uv run ruff check . 2>&1 | tail -10
uv run pip-audit 2>&1 | grep -E "CRITICAL|HIGH" | head -20
```

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
Lint           ✅ clean     |  ❌ N issues
Build          ✅ success   |  ❌ failed — [detail]
CVE audit      ✅ none      |  ❌ N high/critical — [list]

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
Blockers:      X/5 passed
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
