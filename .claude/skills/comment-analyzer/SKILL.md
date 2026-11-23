---
name: comment-analyzer
description: "Comment accuracy review: comments, docstrings, JSDoc/JavaDoc/dartdoc checked against the code they describe for rot, contradiction, staleness and redundancy. Use after a refactor or before a PR. Not for writing new documentation (documentation-generation)."
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
last-reviewed: "2026-11-23"
---

## Iron Law

If the comment contradicts the code, the comment is wrong — never accept a comment at face value without reading the implementation it describes.

# Comment Analyzer

Thin entry point: this skill forks into the `comment-analyzer` agent ([`.claude/agents/comment-analyzer.md`](../../agents/comment-analyzer.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `comment-analyzer` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Writing or generating docs → `documentation-generation`
- General code review → `code-reviewer`
