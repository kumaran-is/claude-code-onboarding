---
name: code-simplifier
description: Reviews code for unnecessary complexity, excessive nesting, redundant abstractions, and over-engineering. Use when code feels over-engineered, before PRs, or after implementations. Complements code-reviewer (correctness) by focusing purely on simplicity and readability.
allowed-tools: Read, Grep, Glob
agent: code-simplifier
context: fork
metadata:
  triggers: over-engineered, simplify, too complex, unnecessary abstraction, reduce complexity, simplify code, premature abstraction
  related-skills: code-reviewer, clean-code, dedup-code-agent
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-16"
---

## Iron Law

Never claim code is too complex without showing a concrete simpler alternative at the same file:line.

# Code Simplifier

Reviews code for complexity that doesn't earn its place — abstractions with one implementation, excessive nesting, dead flexibility, and wrapper-around-wrapper patterns.

## When to Use

- Code works correctly but feels over-engineered
- Before opening a PR on new implementation
- When a reviewer says "couldn't you just do X?"
- After implementing a feature that grew beyond its original scope

## What to Check

| Pattern | Description |
|---------|-------------|
| **Excessive nesting** | 3+ levels of if/for/try — flatten with early returns |
| **Premature abstraction** | Factory/strategy/plugin with only 1 current implementation |
| **Wrapper around wrapper** | Class that just delegates with no added value |
| **Over-parameterization** | 5+ params where a config object would be clearer |
| **Dead flexibility** | Config flags, extension points with zero current users |
| **Complex when simple** | 15-line solution where a 3-line solution exists |

## Severity Levels

| Level | Meaning |
|-------|---------|
| **HIGH** | Abstraction adds zero value; removing it simplifies significantly |
| **MEDIUM** | Could be simplified; modest readability improvement |
| **LOW** | Minor cleanup; marginal improvement |

## Output Format

```
## Simplification Review: [scope]

### HIGH — Remove or simplify immediately
**[file:line] — [pattern name]**
Current: [description]
Simpler: [concrete suggestion]
Savings: ~N lines

### MEDIUM — Should simplify
- [file:line] [description] — [suggestion]

### Summary
- Issues: N (high: X, medium: Y, low: Z)
- Recommendation: Complexity acceptable / Simplify before merge
```
