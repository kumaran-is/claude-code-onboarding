---
description: Review code for quality, security, and maintainability. Dispatches all relevant reviewer agents in parallel and merges findings by severity.
allowed-tools: Bash, Read, Glob, Grep, Task
disable-model-invocation: true
---

# Code Review

Review the specified code for quality, security, and maintainability using **parallel multi-perspective review**.

## Process

**Re-review rounds (enforcement kit ON, `.claude/state/ledger.json` exists):** a follow-up run after fixes dispatches only the reviewers `python3 .claude/scripts/review_state.py findings rereview` names (owners of open or newly closed findings), not the whole set again, plus a reviewer for a stack or concern that newly appears in the diff. Every reviewer report counts as a round (from round 3, MEDIUM/LOW findings stop blocking), and `/review-code` and `/review-pr` both dispatch `code-reviewer`: run one of them per round, never both, or the round count doubles.

### Step 1 — Detect scope
Determine which files/directories to review from `$ARGUMENTS` (default: recent changes via `git diff --name-only HEAD`).

### Step 2 — Identify active stacks
Scan the file list for tech signals and build a dispatch list:

| Signal | Agent |
|--------|-------|
| `*.java` or `pom.xml` | `spring-boot-reviewer` |
| `*.ts` + NestJS decorators (`@Controller`, `@Injectable`, `@Module`) | `nestjs-reviewer` |
| `*.ts`/`*.html` under Angular project (`angular.json` present) | `code-reviewer` (Angular) |
| `*.tsx`/`*.jsx` (React) | `code-reviewer` (React) |
| UI templates/widgets changed (Angular, React, Flutter) | + `accessibility-auditor` |
| Web UI behaviour changed (routes, forms, auth, journeys, error states), or `playwright.config.*` / `e2e/**` changed | + `pr-test-analyzer` (missing Playwright spec, flaky-test shapes; triggers in `.claude/rules/web-frontend.md`) |
| GenUI catalog, renderer or action (`**/a2ui/**`, `**/genui/**`, `*catalog*.json`) | `genui-contract-reviewer` |
| MCP server code (`**/mcp/**`, `@modelcontextprotocol/*`) | `code-reviewer` + `security-reviewer` (tool contracts, authz); checklist `mcp-builder/reference/mcp-quality-standards.md` |
| `*.dart` or `pubspec.yaml` | `riverpod-reviewer` |
| `*.py` + LangChain/LangGraph imports | `agentic-ai-reviewer` + `ai-security-reviewer` |
| `*.py` + `google.adk` imports | `adk-reviewer` + `ai-security-reviewer` |
| Any code that calls a model, retrieves for a model, declares agent tools or writes agent memory (any stack) | + `ai-security-reviewer` |
| Retrieval / embedding / RAG pipeline code | + `rag-implementation-reviewer` |
| Eval code, golden data, CI eval gates, prompt files (`**/evals/**`, `**/golden/**`, `prompts/**`) | + `eval-reviewer` |
| AI assets present (golden data, `prompts/`, governance records, AI code) | run `python3 .claude/scripts/check-ai-assets.py --root .` and report its exit code: BLOCK lines are CRITICAL findings, REVIEW lines HIGH, ADVISORY lines LOW; exit 3 (BLOCKED) caps the verdict |
| `*.py` (other) | `python-reviewer` (+ `python-worker-reviewer` when a worker/Pub/Sub/scheduler entrypoint changed) |
| `*.sql`, `alembic/**` or migration files | `postgresql-database-reviewer` |
| Mixed/other | `code-reviewer` (general) |

> **Always add:** `security-reviewer` — runs on ALL scopes regardless of stack.

> **Dependency manifest changed** (`pyproject.toml`, `uv.lock`, `package.json`/lockfile, `pom.xml`): also run the stack's dependency audit and report PASS | FAIL | BLOCKED | NOT RUN from the tool's OWN exit code (`cmd > log 2>&1; echo "EXIT:$?"`). Python: the `/verify` pre-pr EXPORT + AUDIT lines (`pip-audit` on the exported `uv.lock`, not on the interpreter it runs in; no severity column, so never grep it for CRITICAL/HIGH; `pip audit` is not a command) — see `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`. A missing tool or failed scan is BLOCKED, never a green.

### Step 3 — Dispatch in parallel
First run `/verify quick` for the diff's stacks and fix what it reports: reviewers spend their budget on judgement, not on compile and lint errors a tool finds in seconds. A quick-verify FAIL left unfixed is listed in the report, and the verdict cannot be APPROVE.

Launch all identified agents simultaneously with the Agent tool (`run_in_background: true`).
Give each reviewer its own slice of the file list from Step 2 (a stack reviewer gets that stack's files; `security-reviewer` gets auth, input, crypto and config files; `code-reviewer` gets the whole list) and name the files in its prompt. A reviewer handed the whole diff spends its budget on files it cannot judge.
Do **not** wait for one to finish before starting the next.

Example for a NestJS + database change:
- Background agent 1: `nestjs-reviewer` — NestJS-specific quality checks
- Background agent 2: `postgresql-database-reviewer` — SQL/migration safety
- Background agent 3: `security-reviewer` — auth, injection, secrets

### Step 4 — Merge findings by severity

Collect all agent outputs and produce a unified report. De-duplicate issues that multiple
agents flagged independently (keep the most specific description).

```
## Review: [scope] — [N] agents, [N] files

### CRITICAL (must fix before merge)
- [file:line] [agent] [description]

### HIGH (strongly recommended to fix)
- [file:line] [agent] [description]

### MEDIUM (fix soon, can merge with justification)
- [file:line] [agent] [description]

### LOW / INFO (consider for future)
- [file:line] [agent] [description]

### Summary
- Agents dispatched: [list]
- Total issues: N  (critical: X, high: Y, medium: Z, low: W)
- Duplicate findings collapsed: N
- Verdict: ✅ APPROVE / ⚠️ NEEDS_REVIEW / ❌ BLOCK @ [HEAD short sha] (+ "uncommitted changes" when the tree is dirty)

Dependency audit: [PASS | FAIL | BLOCKED | NOT RUN | NOT APPLICABLE — command and exit code]
Docs conformance: [PASS | FAIL — deprecated API / stale pin at file:line | UNVERIFIED]

Verdict rules:
  ✅ APPROVE     — 0 critical, 0 high unresolved
  ⚠️ NEEDS_REVIEW — 0 critical, ≥1 high (must justify in PR)
  ❌ BLOCK        — ≥1 critical unresolved
  MEDIUM / LOW only → ✅ APPROVE with advisories listed (track MEDIUMs as follow-up tasks)
  Policy: .claude/rules/verification-and-reporting.md → Review Severity Policy
  Any dispatched agent or audit that is BLOCKED/NOT RUN caps the verdict at ⚠️ NEEDS_REVIEW (never ✅ APPROVE)
  Docs conformance FAIL is at least a HIGH finding; UNVERIFIED caps the verdict at ⚠️ NEEDS_REVIEW
```

A verdict describes the commit it names. Any commit or edit after it makes it stale: re-run the affected reviewers (scoped re-review, `verification-loop.md` §4) before quoting the verdict in a PR, never the earlier sha's result.

### Step 5 — Documentation conformance (`code-standards.md` "Documentation Before Code")

For each library or framework API the diff introduces or changes, confirm from the source, with `file:line`: the pinned version is current stable and matches the `CLAUDE.md` stack pins; no deprecated API or outdated pattern is used (check the current docs via the skill's MCP server or Context7, falling back to official docs); the API signature matches those docs. A deprecated call or a stale or unpinned version is a HIGH finding. If you could not check the docs this run, report Docs conformance as UNVERIFIED — never PASS.

Use instead when: `/review-pr` — concern-based review (comments, tests, errors, types, simplicity) of a PR diff; built-in `/code-review` — Claude Code's own correctness review of the diff; `/pr-risk` — a risk score without review; `pr-review` skill — post an approved review to GitHub. Reviews are read-only: findings, not fixes, and never a substitute for `/verify`.

$ARGUMENTS
