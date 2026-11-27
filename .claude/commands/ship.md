---
description: Comprehensive pre-deployment readiness check across all stacks (Java/Spring, NestJS, Python/FastAPI, Angular, React, Flutter). Runs tests, linting, build, security audit, secrets scan, and migration checks. Outputs a Ship Readiness Report with READY TO SHIP / NOT READY verdict.
allowed-tools: Bash, Read, Glob, Grep
---

# Ship — Pre-Deploy Readiness Check

Run before every production or staging deployment to verify the branch is safe to ship.

This command is a **readiness** report. It does not merge. It does not create a PR. Freeze the source tree, then run `python3 .claude/scripts/check-verify-impact.py --stage frozen` and `/verify pre-pr` for the reached stacks (unknown impact → all present stacks). Open the PR with `/create-pr` (prints `gh pr create`; the human runs it). Merge is a human action after READY TO SHIP and an explicit keyword.

## Step 1 — Detect Stack

Check which stacks are present in the repo root (web apps are also found in nested folders by the web block in Step 2):

```bash
python3 .claude/scripts/check-verify-impact.py --stage frozen
[ -f "pom.xml" ]        && echo "STACK:java"
find . -maxdepth 4 \( -name node_modules -o -name dist \) -prune -o -name package.json -print | xargs grep -lE '"@nestjs/core"|"@modelcontextprotocol/(sdk|server)"' 2>/dev/null | sed 's/^/STACK:node /'
find . -maxdepth 4 -name node_modules -prune -o \( -name angular.json -o -name 'vite.config.*' -o -name 'next.config.*' \) -print | sed 's/^/STACK:web /'
[ -f "pyproject.toml" ] || [ -f "requirements.txt" ] && echo "STACK:python"
find . \( -path '*/.dart_tool/*' -o -path '*/build/*' \) -prune -o -name pubspec.yaml -print | sed 's/^/STACK:flutter /'
git log --oneline -3
git status --short
```

Run `/verify pre-pr` for stacks the impact JSON lists (FULL / unknown → every present stack). Nested Flutter packages are first-class: do not stop at a root `pubspec.yaml`.

## Step 1b — Security Lock Document Check

Before running any stack checks, verify a security approval exists for the current commit:

```bash
COMMIT=$(git rev-parse --short HEAD)
LOCK=$(find docs/approvals -maxdepth 1 -name "security-*-${COMMIT}.md" 2>/dev/null | head -1)   # no bare glob: zsh aborts on no match
[ -n "$LOCK" ] && echo "LOCK: found $LOCK" || echo "LOCK: missing"
```

**If missing:** STOP. Do not proceed with the ship check.

```
❌ BLOCKED: No security approval found for commit [COMMIT].

Run /audit-security first. The Lock Document (docs/approvals/security-*-[COMMIT].md)
must exist before /ship can proceed. This ensures the security audit was not skipped.

If this is a staging deploy and you intentionally want to skip the security gate,
pass --skip-security-lock with explicit justification.
```

`--skip-security-lock` is staging-only: the report shows `Security lock: SKIPPED — <justification>`, and a production target can never be READY TO SHIP without the Lock Document.

**If found:** continue to Step 2.

## Step 2 — Blockers (must all pass)

Every command below records its OWN exit code (`cmd > log 2>&1; echo "EXIT:$?"`, then `tail` the log); `cmd | tail; echo $?` reports `tail`'s status and turns a failure into a pass.

### All stacks — the `/verify pre-pr` gate
Run every block of [`/verify`](verify.md) for the detected stacks with `MODE=pre-pr` (Spring, Python, Node — NestJS / TypeScript Node / MCP servers, Web — Angular and React, Flutter). `verify.md` is the single source of the gate commands; copy its per-check lines into the report rather than re-running different commands here. Any `FAIL` or `BLOCKED` makes the verdict **NOT READY**; `NOT RUN` is listed with its reason and never counted as passed; a detected stack or app the gate did not run is a blocker.

### Ship-only additions (release artefacts and stricter checks `/verify` does not run)
```bash
# Java / Spring Boot — packaged artefact
./mvnw package -DskipTests -q > /tmp/mvn-pkg.log 2>&1; echo "PACKAGE EXIT:$?"; tail -10 /tmp/mvn-pkg.log
# Python — the image the service ships in (mypy, lock, audit and the migration gate already ran in /verify pre-pr)
[ -f Dockerfile ] && { docker build -t ship-check:local . > /tmp/docker-build.log 2>&1; echo "IMAGE BUILD EXIT:$?"; tail -5 /tmp/docker-build.log; }   # no docker = BLOCKED; remove the image after
# Flutter — release build for each shipped platform (run LAST, after version bump and changelog are final)
flutter build apk --release > /tmp/build.log 2>&1; echo "BUILD EXIT:$?"; tail -10 /tmp/build.log
```
- Web E2E: the `/verify` web block runs `playwright test --fail-on-flaky-tests` and passes only with exit 0 and more than zero executed tests; a missing browser or server is BLOCKED. Interactive Playwright CLI checks are evidence for review, never a substitute for the committed suite.
- Flutter mobile UI/E2E gates run with Maestro only (`.claude/rules/testing-tool-selection.md`); a missing Maestro/device is BLOCKED, never a browser substitute. An iOS build on a non-macOS host is BLOCKED.
- Before releasing an MCP server, also review `.mcp.json` hygiene from `session-mcp-governance.sh` (unpinned packages, secrets in args).
- Zero findings from a scan is evidence only with a positive control; a diff-aware check on uncommitted work is vacuous.

### AI release gate (only when the repo has golden data, `prompts/`, governance records or AI code; otherwise NOT APPLICABLE)

Release gating for AI follows the eval strategy (§5.2 hard blockers, §7.12, §8.3 R3), the guardrails release checklist (§8) and governance release gates (§10.4, §9.3). Deterministic rows block here; organisational approvals are listed as evidence the human supplies, never inferred.

| Row | Check | Status rule |
|---|---|---|
| AI assets | `python3 .claude/scripts/check-ai-assets.py --root . --json ai-assets.json > ai-assets.log 2>&1; echo "EXIT:$?"` | 1 → NOT READY; 3 → BLOCKED (NOT READY); each REVIEW line listed with a decision |
| R1 deterministic evals | the `/verify` AI block (`pytest -m r1`) | FAIL or executed 0 → NOT READY |
| Release-candidate eval (R3) | the eval report for THIS commit names `dataset_name`, `dataset_version`, `prompt_version`, `model_name`, `tool_surface_hash` and passes the ratified thresholds: `uv run --script .claude/skills/eval-guide/scripts/eval_gate.py check --thresholds tests/eval/thresholds.yaml --results <report>` (exit 0 = pass, 1 = gate failed, 2 = invalid input) | no report, a report for another commit, or any hard blocker (isolation, injection success, unauthorized tool call, schema break, write tool without audit log, P95 latency or cost > 1.2× baseline) → NOT READY |
| Prompt drift (prompt standard §17) | when `prompts/` exists and the release has a registry snapshot: `uv run --script .claude/skills/prompt-engineering-patterns/scripts/prompt_drift.py --prompts-root prompts --registry <snapshot.json> --mode prerelease > drift.log 2>&1; echo "EXIT:$?"` (0 = staging serves the Git release content, 1 = DRIFT_STAGING_MISMATCH, 2 = unreadable input or no prompt files) | no snapshot → NOT RUN (caps the verdict at NOT READY until supplied); 1 or 2 → NOT READY |
| Launch checklist | `/ai-launch-check` verdict for the capability's risk tier (T0–T3) | not run → BLOCKED; open items → NOT READY |
| T2/T3 sign-off | independent owner sign-off and feature flag default OFF (guardrails §6, §8) | a link to the recorded approval is listed (an `ai-governance` record passes `check-ai-assets.py` for structure only; it never proves the approval happened); none → NOT READY. Never state that an approval exists without the record |
| Durable memory / fine-tuning | AI BOM complete, artifact integrity, deletion-propagation tests (governance §9.3) | applies only when the system fine-tunes or keeps durable memory; missing → NOT READY |

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

# console.log in TypeScript (should use NestJS Logger, pino in Node/MCP servers, or Angular ErrorHandler)
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
AI release     ✅ all rows PASS  |  ❌ [row: reason]  |  — NOT APPLICABLE (no AI assets)

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
Blockers:      X/7 passed (AI release counts only when applicable)
High priority: X/4 passed
Recommended:   X/4 passed

Evidence       verify stamp VALID (full/pre-pr)  |  ⚠️ INSUFFICIENT / CHANGED / EXPIRED / MISSING — re-run /verify pre-pr (`review_state.py stamp check verify --mode full,pre-pr`)
Review         kit on: `review_state.py stamp check review` VALID (reviewers re-reported on this tree, nothing blocking)  |  ⚠️ CHANGED / BLOCKED / EXPIRED / MISSING — re-dispatch the stale reviewers
Lessons        reviewed + `lessons` stamp VALID: [N routed: lesson / rule / control / skill / note]  |  "no new lesson"  (/create-pr Step 2.3; never skipped)

Verdict: ✅ READY TO SHIP  |  ❌ NOT READY — fix blockers first
─────────────────────────────────────────────────

Review findings (from `/review-code`, `/audit-security` or reviewer agents) follow the Review Severity Policy in `.claude/rules/verification-and-reporting.md`: any unresolved CRITICAL → NOT READY; each HIGH needs a fix or a written PR justification listed here, otherwise NOT READY; MEDIUM/LOW are listed as advisories and never block.

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
- After the PR opens, watch its CI: `gh pr checks <PR> --watch --fail-fast --interval 30; echo "CHECKS EXIT:$?"` (gh 2.87: 0 = every check passed, 1 = a check failed or none were reported (read the message), 8 = still pending because the watch was interrupted). Report that exit code; a failure goes to the `iterate-pr` skill. CI that was not watched is reported as NOT RUN, never as green. No hook polls CI for you.
- `--quick` runs Step 2 only — fastest signal when iterating. Step 2 is still `/verify pre-pr` on the frozen reached set; `--quick` does not mean `/verify quick`.
- A clean `/ship` does not replace `/audit-security` for major releases

## Related Commands

Use instead when: `/verify` — the build/test gate alone, during development (this command runs it plus release checks); `/pr-risk` — review-effort scoring of a diff; `/create-pr` — PR body and `gh` command.

- `/audit-security` — deep OWASP security audit
- `/validate-changes` — LLM-as-a-Judge review of staged diff
- `/review-code` — code quality and security reviewer agents

$ARGUMENTS
