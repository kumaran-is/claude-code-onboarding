---
description: Review code for quality, security, and maintainability. Dispatches all relevant reviewer agents in parallel and merges findings by severity.
allowed-tools: Bash, Read, Glob, Grep, Task
disable-model-invocation: true
---

# Code Review

Review the specified code for quality, security, and maintainability using **parallel multi-perspective review**.

## Process

### Step 1 — Detect scope
Determine which files/directories to review from `$ARGUMENTS` (default: recent changes via `git diff --name-only HEAD`).

### Step 2 — Identify active stacks
Scan the file list for tech signals and build a dispatch list:

| Signal | Agent |
|--------|-------|
| `*.java` or `pom.xml` | `spring-reactive-reviewer` |
| `*.ts` + NestJS decorators (`@Controller`, `@Injectable`, `@Module`) | `nestjs-reviewer` |
| `*.ts`/`*.html` under Angular project (`angular.json` present) | `code-reviewer` (Angular) |
| `*.dart` or `pubspec.yaml` | `riverpod-reviewer` |
| `*.py` + LangChain/LangGraph imports | `agentic-ai-reviewer` |
| `*.py` (other) | `python-reviewer` (+ `python-worker-reviewer` when a worker/Pub/Sub/scheduler entrypoint changed) |
| `*.sql`, `alembic/**` or migration files | `postgresql-database-reviewer` |
| Mixed/other | `code-reviewer` (general) |

> **Always add:** `security-reviewer` — runs on ALL scopes regardless of stack.

> **Dependency manifest changed** (`pyproject.toml`, `uv.lock`, `package.json`/lockfile, `pom.xml`): also run the stack's dependency audit and report PASS | FAIL | BLOCKED | NOT RUN from the tool's OWN exit code (`cmd > log 2>&1; echo "EXIT:$?"`). Python: `pip-audit --strict` (no severity column, so never grep it for CRITICAL/HIGH; `pip audit` is not a command) — see `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`. A missing tool or failed scan is BLOCKED, never a green.

### Step 3 — Dispatch in parallel
Launch all identified agents simultaneously using the Task tool with `run_in_background: true`.
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
- Verdict: ✅ APPROVE / ⚠️ NEEDS_REVIEW / ❌ REJECT

Dependency audit: [PASS | FAIL | BLOCKED | NOT RUN | NOT APPLICABLE — command and exit code]

Verdict rules:
  ✅ APPROVE     — 0 critical, 0 high unresolved
  ⚠️ NEEDS_REVIEW — 0 critical, ≥1 high (must justify in PR)
  ❌ REJECT       — ≥1 critical unresolved
  Any dispatched agent or audit that is BLOCKED/NOT RUN caps the verdict at ⚠️ NEEDS_REVIEW (never ✅ APPROVE)
```

$ARGUMENTS
