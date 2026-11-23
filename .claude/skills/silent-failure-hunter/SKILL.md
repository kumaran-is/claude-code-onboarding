---
name: silent-failure-hunter
description: "Error-handling audit for swallowed exceptions, empty catch blocks, unjustified fallbacks and mock/empty data returned on failure across Java, NestJS/TS, Python and Flutter. Use after writing code with I/O, API calls, DB access or try/catch. Not for investigating runtime logs (error-detective)."
allowed-tools: Read, Grep, Glob, Bash
agent: silent-failure-hunter
context: fork
metadata:
  triggers: error handling, catch block, silent failure, swallowed exception, fallback, empty catch, return null on error, review error handling
  related-skills: error-detective, security-reviewer, code-reviewer
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-23"
---

## Iron Law

An empty catch block is not error handling — it is a lie to the operator. Every catch must log AND rethrow or return an error state.

# Silent Failure Hunter

Thin entry point: this skill forks into the `silent-failure-hunter` agent ([`.claude/agents/silent-failure-hunter.md`](../../agents/silent-failure-hunter.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `silent-failure-hunter` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Errors already happening in logs or production → `error-detective`
- Root-cause debugging of a failing test → `systematic-debugging`
