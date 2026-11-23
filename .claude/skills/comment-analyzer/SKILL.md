---
name: comment-analyzer
description: Reviews code comments for accuracy against actual implementation, detects comment rot, outdated documentation, and misleading inline comments. Use after refactoring, before PRs, or when comments might be stale.
allowed-tools: Read, Grep, Glob
agent: comment-analyzer
context: fork
metadata:
  triggers: comment rot, stale comments, outdated docs, comment accuracy, misleading comments, review comments, JSDoc, JavaDoc, docstring
  related-skills: code-reviewer, documentation-generation
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-16"
---

## Iron Law

If the comment contradicts the code, the comment is wrong — never accept a comment at face value without reading the implementation it describes.

# Comment Analyzer

Verifies that comments, docstrings, JSDoc, JavaDoc, and inline documentation accurately describe the actual code implementation.

## When to Use

- After refactoring code that has existing comments
- Before opening a PR with documentation changes
- When code was changed but comments might not have been updated
- Code review gate for documentation accuracy

## What to Check

| Category | Description |
|----------|-------------|
| **Accuracy** | Does the comment describe what the code actually does? |
| **Staleness** | Was code changed but the comment not updated? |
| **Misleading** | Does the comment describe different behavior than implemented? |
| **Completeness** | Are error cases, side effects undocumented? |
| **Redundancy** | Comments that just restate the code (`i++ // increment i`) |

## Severity Levels

| Level | Meaning |
|-------|---------|
| **CRITICAL** | Comment directly contradicts code behavior |
| **HIGH** | Comment describes old behavior after refactor |
| **MEDIUM** | Incomplete — missing error cases, missing params |
| **LOW** | Redundant or trivial comments |

## Output Format

```
## Comment Analysis: [scope]

### CRITICAL
- [file:line] Comment: "[quote]" -> Actual: [what code really does]

### HIGH
- [file:line] Comment: "[quote]" -> Stale since: [what changed]

### Summary
- Total: N (critical: X, high: Y, medium: Z, low: W)
- Recommendation: PASS / FAIL Comments need updates before PR
```
