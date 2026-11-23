---
name: error-detective
description: "Runtime error investigation from logs, stack traces and production errors: extract, cluster, correlate trace IDs and rank root-cause hypotheses with log evidence. Use when a running service fails or a ticket has a stack trace. Not for source review of error handling (silent-failure-hunter) or local test failures (systematic-debugging)."
allowed-tools: Read, Grep, Glob, Bash
agent: error-detective
context: fork
metadata:
  triggers: error in logs, stack trace, production error, investigate failure, log analysis, runtime error, exception in prod, service crash
  related-skills: systematic-debugging, silent-failure-hunter
  domain: quality
  role: specialist
  scope: investigation
  output-format: report
last-reviewed: "2026-11-23"
---

## Iron Law

Never state a root cause without log evidence at file:line — hypothesis and confirmed cause are different things.

# Error Detective

Thin entry point: this skill forks into the `error-detective` agent ([`.claude/agents/error-detective.md`](../../agents/error-detective.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `error-detective` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Swallowed exceptions in source code → `silent-failure-hunter`
- A failing test or build with a local reproduction → `systematic-debugging`
