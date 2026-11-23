---
name: code-simplifier
description: "Simplicity review: excessive nesting, single-implementation abstractions, wrapper-around-wrapper, dead flexibility, over-parameterisation — each with a concrete simpler alternative. Use when code feels over-engineered, before a PR, or after a feature grew. Not for correctness or bugs (code-reviewer)."
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
last-reviewed: "2026-11-23"
---

## Iron Law

Never claim code is too complex without showing a concrete simpler alternative at the same file:line.

# Code Simplifier

Thin entry point: this skill forks into the `code-simplifier` agent ([`.claude/agents/code-simplifier.md`](../../agents/code-simplifier.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `code-simplifier` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Correctness, security or bugs → `code-reviewer`
- Duplicate or dead code across the codebase → `dedup-code-agent`
