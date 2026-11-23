---
name: code-reviewer
description: "General code review across all stacks: correctness, security, quality and performance findings with file:line evidence and an APPROVE / NEEDS_REVIEW / BLOCK verdict. Use when reviewing changed code, a PR or a diff before commit. Not for simplicity-only (code-simplifier), comment accuracy (comment-analyzer) or deep security audits (security-reviewer)."
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
last-reviewed: "2026-11-23"
---

## Iron Law

Never approve code without reading the actual implementation; always provide severity-bucketed findings with file:line evidence.

# Code Reviewer

Thin entry point: this skill forks into the `code-reviewer` agent ([`.claude/agents/code-reviewer.md`](../../agents/code-reviewer.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Reusable reference

- [reference/code-review-checklist.md](reference/code-review-checklist.md) — the reusable review checklist (also loaded by the agent).

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `code-reviewer` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Complexity only → `code-simplifier`; comment accuracy → `comment-analyzer`; swallowed errors → `silent-failure-hunter`
- Security audit → `security-reviewer`; stack depth → the stack reviewer (`nestjs-reviewer`, `python-reviewer`, `spring-reactive-reviewer`, `riverpod-reviewer`)
- Reviewing someone else's GitHub PR for posting → `pr-review`
