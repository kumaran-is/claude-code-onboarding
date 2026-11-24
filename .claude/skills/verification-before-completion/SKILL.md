---
name: verification-before-completion
description: "Pre-completion verification checklist that mandates running tests, linting, and build commands before claiming work is done, fixed, or passing. Use before any commit, PR creation, or completion claim — evidence must precede assertions; triggers: done, complete, finished, working, before committing, before PR."
allowed-tools: Read, Bash
metadata:
  triggers: verification, done, complete, finished, working, before committing, before PR, verify before claiming
  related-skills: test-driven-development, systematic-debugging, pr-review
  domain: workflow
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-15"
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |
| Feature works | The business outcome: persisted state re-read from the store, under the right tenant/owner, exactly once (a retry or double submit creates no duplicate), async work (job, webhook, notification) at its final status | HTTP 200/201, a success toast, "the API returned ok" |
| PR task complete | GitHub Actions CI green + deployment workflow succeeded on the base branch | PR merged |

## Red Flags — STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

**Post-merge deployment (GitHub Actions):**
```
✅ PR merged → Check Actions run → CI green + deploy workflow succeeded → Task complete
❌ "PR merged" (deployment may have failed silently)
```

## Post-Merge Verification

When a task involves a PR that has been merged, "done" means the deployment succeeded — not just that the code was merged. Check the runs on the PR's base branch (`develop` in this toolkit's Git workflow) with the `gh` CLI:

```bash
gh run list --branch develop --limit 5; echo "exit=$?"   # recent workflow runs on the base branch
gh run view <run-id>                                      # inspect CI + deploy jobs
```

All jobs green → complete. Any job failed, cancelled or still running → NOT complete; say so with the run URL.

**Trigger:** a PR was merged as part of the task, the task included deployment or release, or the human says "it's merged" / "it's deployed". CI can pass locally and fail in the pipeline (environment variables, container build, migration runner) — merge is never evidence of success.

## Which Command, Which Checklist

Do not keep a private list of commands here — use the authoritative ones:

| Need | Authoritative source |
|------|----------------------|
| Build + test command per stack (Spring, Python, NestJS, Angular, React, Flutter), each with its own exit code | `/verify` (`.claude/commands/verify.md`); `/verify full` before claiming tests pass |
| Which tool tests which target (Maestro for Flutter Android/iOS, Playwright for web, Vitest/`ng test`/`flutter test`/pytest for units) | `.claude/rules/testing-tool-selection.md` |
| Evidence a claim needs (own exit code, positive control, env parity) | `.claude/rules/verification-and-reporting.md` → "Action Claims Require Evidence" |
| When to run which gate, reusing results whose inputs have not changed, findings ledger, standing habits | [reference/verification-loop.md](reference/verification-loop.md) |
| How to write a positive control that cannot lie (anchor guards, inert mutations, restore in `finally`, the absence trap, stale `.pyc`) | [reference/positive-control-harness.md](reference/positive-control-harness.md) |
| Gates per workflow type (Feature/PR, Architecture, Database, UI, Release) | `.claude/rules/verification-and-reporting.md` → "Quality Gates" (the single canonical completion checklist) |
| Pre-deploy readiness across all stacks | `/ship` |

Capture each tool's **own** exit code (`cmd > log 2>&1; echo $?`), never a pipe's. In a monorepo, run the command for every changed target separately — one target's green run is never evidence for another, and `npm test` in a Python project proves nothing.

## Why This Matters

Verification failures lead to:
- Broken trust ("I don't believe you")
- Undefined functions shipped — would crash
- Missing requirements shipped — incomplete features
- Time wasted on false completion → redirect → rework

This rule exists because honesty is a core value. Unverified claims are not efficiency — they are debt.

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
