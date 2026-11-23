---
name: code-reviewer
description: General-purpose code review skill. Provides checklists for security, code quality, performance, and best practices. Use when reviewing code changes, PRs, or performing quality audits.
allowed-tools: Read, Grep, Glob, Bash
agent: code-reviewer
context: fork
metadata:
  triggers: code review, review code, PR review, pull request review, code quality, code audit, review this code
  related-skills: security-reviewer, dedup-code-agent, test-driven-development
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-15"
---

## Iron Law

Never approve code without reading the actual implementation; always provide severity-bucketed findings with file:line evidence.

# Code Reviewer

General-purpose code review skill covering security, quality, performance, and best practices.

## When to Use

- After writing or modifying code
- During PR reviews
- When auditing code quality

## Process

1. Identify changed files via `git diff` or user request
2. Read [reference/code-review-checklist.md](reference/code-review-checklist.md) for review categories, severity levels, and output format
3. Review each file against the checklist
4. Report findings by severity (Critical > High > Medium > Low)

## Reference Files

| File | Contents | Load When |
|------|----------|-----------|
| `reference/code-review-checklist.md` | Security checks, code quality, performance, best practices, output format | Reviewing any code change, pre-PR checklist, security audit |

## Error Handling

If no changes are found, report "No changes detected" and list the files/paths searched.
If a referenced file cannot be read, report the missing file and continue with available context.

## Anti-Patterns

- **Never rubber-stamp without file:line** — "looks good" with no evidence is a failed review
- **Never mark APPROVED if any Critical or High finding is unresolved** — severity discipline is non-negotiable
- **Never review from memory** — always read the actual changed files; filenames do not tell you what changed
- **Never scope-creep the review** — report what changed, not what you wish were different in adjacent code
- **Never merge findings across files** — report per-file with specific line numbers, not aggregate impressions
- **Avoid vague findings** — "this could be a security issue" is not a finding; "SQL built via string concatenation at service.ts:47 allows injection" is

## Verify

After completing a review:

```bash
# Confirm all files you reviewed are the ones that actually changed
git diff --name-only HEAD~1

# Confirm no new linting errors introduced
npm run lint 2>&1 | grep -E "error|warning" | head -20

# Confirm tests still pass after changes
npm test > /tmp/test.log 2>&1; echo "TEST EXIT:$?"; tail -5 /tmp/test.log   # no --passWithNoTests: zero tests must fail
```

Report format after verification:
```
REVIEW COMPLETE:
- Files reviewed: N (list them)
- Findings: X Critical, Y High, Z Medium, W Low
- Verdict: APPROVED / NEEDS_REVIEW / REJECT
- Evidence: [file:line for each finding]
```
