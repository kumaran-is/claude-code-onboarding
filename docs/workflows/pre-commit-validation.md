# Pre-Commit Validation

> **When to use**: Before every commit — after implementation, before opening a PR
> **Time estimate**: 5–15 minutes
> **Prerequisites**: Code written, tests passing locally

## Overview

A 4-step gate that catches issues before they enter the PR review cycle. Uses automated risk scoring, LLM-as-judge quality evaluation, behavioral test coverage analysis, and an evidence-based completion check. Nothing proceeds to PR until this gate passes.

---

## Phases

### Phase 1 — PR Risk Score

**Trigger**: About to commit changes
**Command**: `/pr-risk [branch or commit range]` (default: `HEAD~1..HEAD`)
**Source**: `commands/pr-risk.md`

**5 factors scored 0–10** (from `commands/pr-risk.md`):

| Factor | What It Measures |
|--------|-----------------|
| Size | Files changed, lines added/deleted |
| Complexity | Cyclomatic complexity, nesting depth, function count |
| Test Coverage | New code without corresponding tests |
| Dependency | New packages added, version bumps |
| Security | Auth changes, crypto, input handling, secrets |

**Overall score**: `(sum of 5 scores) / 5`

**Risk thresholds**:
- **0–3**: Low risk — proceed
- **4–6**: Medium risk — review all HIGH+ findings before commit
- **7–10**: High risk — consider splitting the PR; at minimum get explicit review on each high-score factor

**Large PR detection**: >20 files OR >1,000 lines → recommendation to split
**Produces**: Risk report with per-factor scores, key drivers, and pre-merge checklist
**Gate**: Understand the risk level; high-risk PRs need stricter review

---

### Phase 2 — LLM-as-Judge Evaluation

**Trigger**: Risk score understood
**Command**: `/validate-changes`
**Source**: `commands/validate-changes.md`
**Agent**: `output-evaluator` (haiku model)
**Vibe**: *"Defaults to NEEDS_REVIEW — APPROVE requires evidence, not optimism"*

**Process** (from `commands/validate-changes.md`):
1. Check staged changes via `git diff --cached --stat`
2. Get full diff via `git diff --cached`
3. Invoke `output-evaluator` agent with diff
4. Parse verdict

**Three verdicts**:

| Verdict | Meaning | Action |
|---------|---------|--------|
| `APPROVE` | Changes are correct, complete, safe | Proceed to Phase 3 |
| `NEEDS_REVIEW` | Issues found, non-blocking | Fix flagged issues, re-run |
| `REJECT` | Serious issues: security, correctness, completeness | Fix ALL issues, re-run |

**Output format**: JSON with scores + specific issues per file
**Gate**: `APPROVE` verdict required to proceed

---

### Phase 3 — Behavioral Test Coverage

**Trigger**: `/validate-changes` returns APPROVE
**Agent**: `pr-test-analyzer`
**Vibe**: *"Line coverage lies — behavioral gaps on critical paths sink releases"*

**What it checks** (not line coverage — behavioral coverage):
- Critical paths: does happy path have a test?
- Edge cases: null, empty, boundary values
- Error conditions: what happens when dependencies fail?
- Concurrent scenarios: if applicable

**Coverage gap ratings**: 1 (trivial gap) – 10 (critical missing coverage)

**Gate**: No coverage gaps rated 8+ without explicit justification

---

### Phase 4 — Evidence-Based Completion Check

**Trigger**: Test coverage acceptable
**Skill**: `verification-before-completion` (`skills/verification-before-completion/SKILL.md`)
**Iron Law** (from `skills/verification-before-completion/SKILL.md:25-31`): `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE`

**Verification commands by stack** (from `skills/verification-before-completion/SKILL.md:143-158`):

| Stack | Command |
|-------|---------|
| Java/Spring | `./mvnw test` |
| NestJS | `npm test` |
| Python | `pytest && ruff check . && mypy .` |
| Angular | `ng test --watch=false && ng build` |
| Flutter | `flutter test && flutter analyze` |

**Required evidence**: Actual command output showing pass/fail counts — not "I believe it works"

**Produces**: Verified test run output attached to commit
**Gate**: Fresh test run passes with evidence (not from memory)

---

### Phase 5 — Dependency Audit (for PRs adding packages)

**Trigger**: `package.json`, `pyproject.toml`, `pom.xml`, or `pubspec.yaml` changed
**Command**: `/security-dependencies`
**Source**: `commands/security-dependencies.md`

**Runs per ecosystem detected**:
- `npm audit --audit-level=high` (Node/NestJS/Angular)
- `pip-audit` on the exported `uv.lock` (Python; `pip audit` is not a command)
- `mvn dependency-check:check` (Java)
- `flutter pub audit` (Flutter)

**Gate**: Zero HIGH or CRITICAL CVEs before committing dependency changes

---

## Decision Tree

```
Code written + tests pass locally
         │
         ▼
   /pr-risk score
         │
    ─────┼─────
   Low   │  High
         │
         ▼
  /validate-changes
         │
   ──────┼──────
  APPROVE│ REJECT/NEEDS_REVIEW
         │         └── Fix issues → re-run /validate-changes
         ▼
  pr-test-analyzer
         │
   gap ≥8?
   Yes──►Fix test gaps → re-run
   No
         │
         ▼
  Run tests locally (fresh)
         │
   Pass? No──► Fix and re-run
   Yes
         │
         ▼
  Dependencies changed?
   Yes──► /security-dependencies
   No
         │
         ▼
   git commit → proceed to PR
```

---

## Quick Reference

| Phase | Command/Agent | Output | Gate |
|-------|--------------|--------|------|
| 1 — Risk score | `/pr-risk` | Score 0–10 per factor | Understand risk level |
| 2 — LLM judge | `/validate-changes` | APPROVE/NEEDS_REVIEW/REJECT | APPROVE |
| 3 — Test coverage | `pr-test-analyzer` agent | Gap list rated 1–10 | No gap ≥8 unaddressed |
| 4 — Evidence | Run stack test command | Pass/fail count output | Fresh pass |
| 5 — Dependencies | `/security-dependencies` | CVE list | Zero HIGH/CRITICAL |

---

## Common Pitfalls

- **Staging only some files** — `/validate-changes` evaluates `git diff --cached`; stage exactly what you intend to commit
- **Trusting "it worked earlier"** — Phase 4 requires a fresh run; stale pass output is not evidence
- **Skipping Phase 3 because "I wrote tests"** — `pr-test-analyzer` checks behavioral coverage, not existence of test files; you can have tests that don't cover the right things
- **`NEEDS_REVIEW` ≠ approved** — it means specific issues were found; do not proceed to PR without addressing them
- **High risk score but proceeding anyway** — high risk (7+) doesn't block, but it means stricter PR review is required; note it in the PR description

## Related Workflows

- [`code-review.md`](code-review.md) — run before this for quality feedback
- [`pr-shipping.md`](pr-shipping.md) — run after this to complete PR lifecycle
- [`security-audit.md`](security-audit.md) — deeper security when security factor is high
