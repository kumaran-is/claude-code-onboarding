# PR Shipping

> **When to use**: Code is implemented, reviewed locally, and ready to go from commit → merged PR
> **Time estimate**: 15–45 minutes
> **Prerequisites**: [`pre-commit-validation.md`](pre-commit-validation.md) complete, `/validate-changes` returned APPROVE

## Overview

Complete PR lifecycle from opening the PR through CI iteration to merge and branch cleanup. Uses automated risk scoring, multi-role review, security gate, and pre-deploy readiness check before merge is allowed.

---

## Phases

### Phase 1 — Open PR

**Trigger**: Changes committed, branch pushed
**Command**: `gh pr create --title "..." --body "..."`

**PR body must include** (from CLAUDE.md git workflow):
- Summary (3 bullet points)
- Test plan (checklist)
- Risk level (from `/pr-risk` score)
- Any accepted HIGH findings with justification

**Branch naming** (from `CLAUDE.md`):
- `feature/<ticket>-<description>`
- `bugfix/<ticket>-<description>`

**Commit message style**: conventional commits — `feat:`, `fix:`, `docs:`, `refactor:`

**Gate**: PR opened with description that includes test plan and risk acknowledgment

---

### Phase 2 — Risk Assessment

**Command**: `/pr-risk`
**Source**: `commands/pr-risk.md`
**Produces**: Risk score 0–10 across 5 factors (size, complexity, tests, deps, security)

If risk score ≥ 7 and PR has >20 files or >1000 lines → **split the PR** before proceeding. Large PRs are harder to review and riskier to merge.

**Gate**: Risk score understood; split decision made

---

### Phase 3 — Multi-Role PR Review

**Command**: `/review-pr`
**Source**: `commands/review-pr.md`
**6 agents dispatched concurrently** (from `commands/review-pr.md:15-20`):

| Role | Agent |
|------|-------|
| Comment accuracy | `comment-analyzer` |
| Test coverage | `pr-test-analyzer` |
| Error handling | `silent-failure-hunter` |
| Type design | `type-design-analyzer` |
| Code quality | `code-reviewer` |
| Simplification | `code-simplifier` |

**Severity actions**:
- CRITICAL → fix before proceeding
- HIGH → fix or document justification in PR
- MEDIUM → fix or create follow-up ticket
- LOW → optional

**Gate**: Zero CRITICAL; all HIGH either fixed or documented

---

### Phase 4 — Security Gate

**Command**: `/audit-security`
**Source**: `commands/audit-security.md`
**Agent**: `security-reviewer` (opus model)

**Checks** (from `commands/audit-security.md:11-39`):
- Hardcoded secrets, API keys, passwords
- OWASP Top 10: injection, XSS, SSRF, auth bypass, unsafe deserialization
- Insecure cryptography (MD5, SHA1, ECB)
- Missing input validation
- Debug endpoints exposed in production
- Configuration: CORS, security headers, env file exposure
- Dependencies: npm/pip/Maven CVE scan

**Produces**: Security findings by severity (CRITICAL/WARNING/CONFIG/DEPS)
**Gate**: Zero CRITICAL security findings unresolved

---

### Phase 5 — Pre-Deploy Readiness

**Command**: `/ship`
**Source**: `commands/ship.md`

**Blocker checks** (auto-detected by stack):

| Stack | Blockers Checked |
|-------|-----------------|
| Java/Spring | `./mvnw test`, `mvn compile`, CVE audit |
| NestJS | `npm test`, `npm run build`, `npm audit` |
| Python | `/verify` Python block: `uv lock --check`, `uv sync --locked`, ruff, mypy, pytest, `pip-audit` on the exported lock |
| Angular | `ng test --watch=false`, `ng build` |
| Flutter | `flutter test`, `flutter analyze` |

**High priority checks** (all stacks):
- Hardcoded credentials in source
- `console.log()` / `print()` statements left in
- TODO / FIXME comments in changed files
- Pending Flyway/Prisma migrations unapplied

**Recommended checks**:
- Docs updated if public API changed
- `.env.example` reflects new env vars
- No `localhost` references in production code
- Debug flags disabled

**Verdict**: `✅ READY TO SHIP` or `❌ NOT READY` with blocking items listed
**Gate**: `✅ READY TO SHIP` verdict required

---

### Phase 6 — CI Iteration (if CI fails)

**Trigger**: CI checks fail on the PR
**Command**: `/iterate-pr [PR number]`
**Source**: `commands/iterate-pr.md`
**Skill**: `iterate-pr` skill (8-step loop)

For autonomous iteration:
```
/ralph-loop "Fix all CI failures on PR #<N> until all checks pass" --max-iterations 10 --completion-promise "All CI checks pass"
```

**The loop**:
1. Read CI failure output
2. Identify root cause
3. Fix
4. Push
5. Check CI status
6. Repeat until all checks pass or max-iterations reached

**Gate**: All CI checks green

---

### Phase 7 — Merge and Cleanup

**Trigger**: PR approved, CI green, `/ship` verdict READY
**Merge strategy**: Squash merge (from `CLAUDE.md`): `gh pr merge --squash`

**Post-merge cleanup**:

**Command**: `/branch-cleanup`
**Source**: `commands/branch-cleanup.md`

- Deletes merged local + remote branches
- Protects: `main`, `master`, `develop`, `staging`, `production`, `release/*`, `hotfix/*`
- Run with `--dry-run` first to preview

**Worktree sync** (if using parallel PR worktrees):

**Command**: `/worktree-sync`
**Source**: `commands/worktree-sync.md`

- Syncs all open PR worktrees after merge
- Prunes stale worktrees

**Gate**: Branch deleted, worktrees cleaned up

---

## Full Sequence (Quick Reference)

| Step | Command | Gate |
|------|---------|------|
| 1 — Open PR | `gh pr create` | PR description complete |
| 2 — Risk score | `/pr-risk` | Score understood; split if >7 + large |
| 3 — Multi-role review | `/review-pr` | Zero CRITICAL; HIGH resolved/documented |
| 4 — Security gate | `/audit-security` | Zero CRITICAL security findings |
| 5 — Readiness check | `/ship` | `✅ READY TO SHIP` verdict |
| 6 — CI iteration | `/iterate-pr` or `/ralph-loop` | All CI checks green |
| 7 — Merge + cleanup | `gh pr merge --squash` + `/branch-cleanup` | Branch deleted |

---

## Common Pitfalls

- **Merging without `/ship` verdict** — blockers (failing tests, exposed secrets, stale migrations) get into main
- **Not splitting high-risk large PRs** — >1000 lines is a review anti-pattern; reviewers miss things
- **Skipping `/audit-security`** — security-reviewer in `/review-code` covers the diff; `/audit-security` covers the full codebase context including config files
- **Force-push to main** — blocked by `pre-bash-guard.sh` hook AND the deny list in `settings.json`
- **Not running `/branch-cleanup`** — stale branches accumulate; they become confusing after 10+ PRs
- **`iterate-pr` on a REJECT verdict** — if `output-evaluator` REJECTs, fix the issues manually before automating CI iteration

## Related Workflows

- [`pre-commit-validation.md`](pre-commit-validation.md) — must complete before this
- [`code-review.md`](code-review.md) — review workflow before opening PR
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — after merge, deploying to Cloud Run
- [`iterate-pr.md`](iterate-pr.md) — detailed CI iteration workflow
