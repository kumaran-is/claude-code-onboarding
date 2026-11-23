---
name: iterate-pr
description: Iterate on a PR until CI passes and review feedback is addressed. Use when fixing CI failures, addressing PR review comments, or running the feedback-fix-push cycle autonomously. Covers LOGAF-scale feedback triage, CI polling, GitHub thread replies, and exit conditions.
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
metadata:
  triggers: iterate PR, fix CI, CI failing, PR feedback, address review comments, PR checks failing, make CI green, iterate until green
  related-skills: pr-review, verification-before-completion
  domain: workflow
  role: autonomous
  scope: pr-lifecycle
  output-format: actions
last-reviewed: "2026-03-15"
---

## Iron Law

Never mark a PR iteration complete without all CI checks passing; always show actual CI output as evidence, not inference.

# Iterate PR Until CI Passes

Autonomously fixes CI failures and addresses review feedback in a loop until all checks are green and feedback is resolved.

**Requires:** GitHub CLI (`gh`) authenticated, Python `uv` installed.

> **GitHub access:** This skill uses the **GitHub CLI (`gh`)** — NOT the GitHub MCP server. All GitHub operations (fetching PR status, posting review replies, reading CI logs) go through `gh` commands and the helper scripts in `scripts/`. No MCP tool calls are needed.

## Quick Reference

```bash
uv run ${CLAUDE_SKILL_ROOT}/scripts/fetch_pr_checks.py [--pr NUMBER]
uv run ${CLAUDE_SKILL_ROOT}/scripts/fetch_pr_feedback.py [--pr NUMBER]
```

## Workflow Summary (8 Steps)

1. Identify PR (`gh pr view`)
2. Gather review feedback (`fetch_pr_feedback.py`)
3. Handle feedback by LOGAF priority — auto-fix high/medium, ask for low
4. Check CI status (`fetch_pr_checks.py`)
5. Fix CI failures — read logs, trace root cause, fix, run tests
6. Verify locally, commit, push
7. Monitor CI in a poll loop — address new feedback as it arrives
8. Repeat from Step 2 if new feedback required changes

## Circuit Breaker — 6-Cycle Limit

Track the number of full fix→push→CI cycles completed. **After 6 cycles without reaching exit conditions, stop and escalate.**

A "cycle" = one complete pass through Steps 2–8 (gather feedback → fix → push → CI result).

**On hitting cycle 6 with no resolution:**
```
ESCALATION — Cycle limit reached (6/6)

What was attempted:
- Cycle 1: [what was fixed, what CI returned]
- Cycle 2: [what was fixed, what CI returned]
- Cycle 3: [what was fixed, what CI returned]
- Cycle 4: [what was fixed, what CI returned]
- Cycle 5: [what was fixed, what CI returned]
- Cycle 6: [what was fixed, what CI returned]

Still failing:
- [check name]: [error description] — [log snippet or file:line]

Options:
A) Provide direction on the specific failure above
B) Approve the PR with known failures (describe what to accept)
C) Close the PR and start fresh with a different approach
→ Which do you prefer?
```

Do NOT attempt a 7th cycle. Do NOT make any more code changes. Wait for human direction.

## LOGAF Scale

| Level | Labels | Action |
|-------|--------|--------|
| `high` | `h:`, blocker, changes requested | Auto-fix |
| `medium` | `m:`, standard feedback | Auto-fix |
| `low` | `l:`, nit, style, suggestion | Ask user |
| `bot` | Codecov, Dependabot informational | Skip |
| `resolved` | Already resolved threads | Skip |

Review bot feedback (`review_bot: true`) in high/medium/low — treat as human feedback.

## CI Failure Error Path (D3)

When CI fails, apply this decision tree before touching code:

```
CI check fails
    |
    +-- Is the failure in YOUR changed files?
    |   YES → Read the failing log (`gh run view --log-failed`), trace to file:line, fix
    |   NO  → Flaky/pre-existing failure? Check: did this check pass on the base branch?
    |             YES (pre-existing) → Do not fix it yourself. Report: "CI check [X]
    |                                   was already failing on base branch. Skip or
    |                                   ask owner to fix before merge?"
    |             NO (new failure)   → Fix as if it's yours
    |
    +-- Fix applied, pushed — CI still fails same check?
    |   → This is now Cycle 2. Log it in the cycle tracker.
    |
    +-- CI log is truncated or unreadable?
    |   → Run: `gh run view <run-id> --log-failed 2>&1 | head -200`
    |     If still unreadable: report the check name + run URL to the human.
    |
    +-- CI passes locally but fails in CI environment?
        → Likely env/secret mismatch. Report: "Tests pass locally but fail in CI.
          Suspect missing env var or secret. Check CI env configuration."
```

**Never mark CI as "passing" based on local test output alone.** Always wait for the actual CI run result from `fetch_pr_checks.py` before moving to the next cycle.

## Reference Files

| File | Contents |
|------|----------|
| `reference/workflow.md` | Full 8-step procedure, GraphQL reply mutation, fallback commands, exit conditions |
| `scripts/fetch_pr_checks.py` | Fetches CI check status + log snippets via `gh` CLI |
| `scripts/fetch_pr_feedback.py` | Fetches PR review comments, categorizes by LOGAF scale |
