---
description: Evaluate staged git changes with the output-evaluator agent (LLM-as-a-Judge) before committing. Returns APPROVE / NEEDS_REVIEW / REJECT with scores and specific issues.
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Validate Changes Before Commit

## Step 1 — Check staged changes

Run `git diff --cached --stat`. If nothing is staged, tell the user and stop.

## Step 2 — Get the full diff

Run `git diff --cached` to get the complete diff of all staged changes.

## Step 3 — Invoke the evaluator

Use the Agent tool to launch the `output-evaluator` agent with this prompt:

```
Evaluate these staged changes for correctness, completeness, and safety.
Return a JSON verdict with scores and issues.

Changes:
[paste the full git diff here]
```

## Step 4 — Parse verdict and act

**APPROVE** — scores >= 7, no high issues:
- Show scores and summary
- Ask: "Proceed with commit?"

**NEEDS_REVIEW** — score 5–6 or medium issues:
- Show all issues grouped by severity
- Offer three options:
  1. Fix issues and re-evaluate
  2. Commit anyway (acknowledge risks)
  3. Abort

**REJECT** — score < 5 or any high-severity issue:
- State the rejection clearly
- Show critical issues
- Do NOT offer to commit anyway
- Suggest specific fixes

## Step 5 — Commit (if approved)

If user confirms, create the commit using the conventional commit flow (`feat:`, `fix:`, etc.).

## Output example

```
Evaluating 3 staged files...

VERDICT: NEEDS_REVIEW

Scores:
  Correctness:  8/10
  Completeness: 6/10
  Safety:       9/10

Issues:
  [MEDIUM] src/api/handler.ts:45
    Missing error handling for network failures

  [LOW] src/utils/format.ts:12
    Consider adding input validation

Suggestion: Add try-catch around the fetch call in handler.ts

How to proceed?
  1. Fix and re-evaluate
  2. Commit anyway (1 medium issue)
  3. Abort
```

## When to use

Advisory only: `output-evaluator` is an LLM judge (probabilistic). An APPROVE never replaces `/verify` exit codes or reviewer-agent verdicts; use `/review-code` for stack reviewers and `/verify pre-commit` for the deterministic gate.


- After significant code changes before committing
- Changes touching security-sensitive code (auth, tokens, DB)
- Before pushing to a shared branch

## When to skip

- Trivial changes: typos, formatting, docs only
- Already manually reviewed thoroughly
- Rapid iteration on a local feature branch

$ARGUMENTS
