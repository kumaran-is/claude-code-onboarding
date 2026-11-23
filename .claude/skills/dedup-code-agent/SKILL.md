---
name: dedup-code-agent
description: Code duplication detection and technical debt analysis skill. Provides methodology for finding duplicate code, dead code, and dependency bloat.
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
last-reviewed: "2026-03-15"
---

## Iron Law

Never delete code labeled as duplicate without verifying all call sites are updated; always confirm zero remaining references before removing.

# Code Deduplication Skill

## Purpose

Provides systematic methodology for detecting code duplication, unused code, and dependency bloat -- primarily in Flutter + Firebase codebases but applicable to any project.

## Process

1. **Discover** -- Map project structure, features, shared utilities, and test coverage
2. **Scan** -- Run multi-phase analysis for duplicates, dead code, and unused dependencies
3. **Classify** -- Categorize findings by severity (Critical / Warning / Suggestion)
4. **Report** -- Output structured report with file locations, counts, and recommendations

For the complete analysis methodology, detection patterns, and report format:

Read [reference/dedup-analysis-methodology.md](reference/dedup-analysis-methodology.md)

## Error Handling

If the target directory does not exist, report "Target not found" with the path searched.
If no duplication is found, report "No duplicates detected" with the scan scope and file count.
