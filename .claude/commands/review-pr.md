---
description: "Run a 6-role PR review covering comment accuracy, test coverage, error handling, type design, code quality, and simplification. Dispatches specialized agents by concern — not by tech stack. Use before creating a PR or reviewing someone else's changes. Optional topic filter: comments, tests, errors, types, code, simplify (default: all 6 roles)."
allowed-tools: Bash, Read, Glob, Grep, Task
disable-model-invocation: true
---

# PR Review — 6 Roles

Run a concern-specific review of code changes. Each role examines a different dimension regardless of tech stack.

## Roles

| Role | Agent | Focus |
|------|-------|-------|
| Comment accuracy | `comment-analyzer` | Comments vs actual code |
| Test coverage | `pr-test-analyzer` | Behavioral gaps, not line coverage |
| Error handling | `silent-failure-hunter` | Silent failures, swallowed exceptions |
| Type design | `type-design-analyzer` | Invariants, encapsulation, invalid states |
| Code quality | `code-reviewer` | Bugs, style, CLAUDE.md compliance |
| Simplification | `code-simplifier` | Unnecessary complexity |

## Process

## Step 0 — Risk-Gated Scope Assessment

Before dispatching reviewers, calculate the PR risk score to calibrate review depth.

```bash
git diff --shortstat HEAD~1
git diff --name-status HEAD~1
```

Apply the Size Risk factor from `/pr-risk`:

| Files / Lines | Risk Tier | Review Depth |
|--------------|-----------|--------------|
| ≤ 5 files, ≤ 100 lines | 🟢 Low | Run roles: errors, code only (skip comment-analyzer, type-design-analyzer for speed) |
| 6-20 files, ≤ 600 lines | 🟡 Medium | Run all 6 roles |
| > 20 files OR > 600 lines | 🟠 High | Run all 6 roles + recommend running `/pr-risk` for full scoring |

Check for security-sensitive patterns:

```bash
git diff --name-only HEAD~1 | grep -iE "auth|login|token|jwt|crypto|secret|password|permission|role|guard"
```

If security-sensitive files changed: also dispatch the `security-reviewer` agent (flag it explicitly).

Print the risk tier before dispatching agents so the user sees it.

**Re-review rounds (enforcement kit ON, `.git/claude-state/review/<branch>/ledger.json` exists):** a follow-up run after fixes dispatches only the reviewers `python3 .claude/scripts/review_state.py findings rereview` names (owners of open or newly closed findings), not the whole set again, plus a reviewer for a stack or concern that newly appears in the diff. Every reviewer report counts as a round (from round 3, MEDIUM/LOW findings stop blocking), and `/review-code` and `/review-pr` both dispatch `code-reviewer`: run one of them per round, never both, or the round count doubles.

1. **Determine scope** — From `$ARGUMENTS`; if not specified use `git diff HEAD~1`
2. **Determine roles** — Parse topic filter from `$ARGUMENTS` (see Topic Filters below); default: all 6 (adjusted by risk tier from Step 0)
3. **Dispatch agents** — Run each selected agent against the scope; collect findings
4. **Aggregate** — Group all findings by severity across all roles

## Topic Filters

If `$ARGUMENTS` contains one of these words, run only that role:

| Filter word | Agent dispatched |
|-------------|-----------------|
| `comments` | comment-analyzer |
| `tests` | pr-test-analyzer |
| `errors` | silent-failure-hunter |
| `types` | type-design-analyzer |
| `code` | code-reviewer |
| `simplify` | code-simplifier |
| `all` or no filter | all 6 roles |

## Aggregated Output Format

```
## PR Review: [scope]

### CRITICAL — must fix before merge
- [role] [file:line] [description]

### IMPORTANT — should fix
- [role] [file:line] [description]

### SUGGESTIONS — nice to have
- [role] [file:line] [description]

### POSITIVE
- [role] [description of what was done well]

### Summary

| Role | Issues | Critical |
|------|--------|---------|
| comment-analyzer | N | X |
| pr-test-analyzer | N | X |
| silent-failure-hunter | N | X |
| type-design-analyzer | N | X |
| code-reviewer | N | X |
| code-simplifier | N | X |
| **Total** | **N** | **X** |

Status: READY FOR PR / NEEDS FIXES (N critical issues)
```

> For quantitative risk scoring (size, complexity, test coverage, dependencies, security) before this review: run `/pr-risk`.
> For two-stage PR review (internal analysis -> human approval -> posting to GitHub): load the `pr-review` skill.

Use instead when: `/review-code` — stack-specific reviewers (Spring, NestJS, Riverpod, Python, DB) plus security; `/pr-risk` — the full five-factor risk score; `pr-review` skill — post the review to GitHub after approval.

$ARGUMENTS
