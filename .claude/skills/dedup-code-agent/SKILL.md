---
name: dedup-code-agent
description: "Technical-debt scan for duplicate code, dead/unused code and dependency bloat with file locations and counts (Flutter + Firebase first, any stack). Use when cleaning up, before a refactor, or when duplication is suspected. Not for single-diff code review (code-reviewer)."
allowed-tools: Read, Glob, Grep, Bash
agent: dedup-code-agent
context: fork
metadata:
  triggers: duplicate code, dead code, code duplication, dependency bloat, technical debt, unused code, code cleanup
  related-skills: code-reviewer, systematic-debugging, receiving-code-review
  domain: quality
  role: specialist
  scope: analysis
  output-format: report
last-reviewed: "2026-11-23"
---

## Iron Law

Never delete code labeled as duplicate without verifying all call sites are updated; always confirm zero remaining references before removing.

# Code Deduplication Skill

Thin entry point: this skill forks into the `dedup-code-agent` agent ([`.claude/agents/dedup-code-agent.md`](../../agents/dedup-code-agent.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Reusable reference

- [reference/dedup-analysis-methodology.md](reference/dedup-analysis-methodology.md) — detection phases, patterns and report format (also loaded by the agent).

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `dedup-code-agent` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Reviewing a single change for correctness → `code-reviewer`
- Over-engineering inside one file → `code-simplifier`
