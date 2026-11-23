---
name: skill-reviewer
description: "Reviews a new or changed skill in .claude/skills/ against the writing-skills spec (name, trigger-word description, allowed-tools, Iron Law, ≤500-line body, references, forbidden files) and returns PASS / CONDITIONAL PASS / FAIL with file:line evidence. Use after creating or editing a skill. Not for grading the whole library (/audit-skills)."
allowed-tools: Read, Glob, Grep
agent: skill-reviewer
context: fork
metadata:
  triggers: review skill, audit skill, check skill, skill compliance, new skill, skill authoring, writing-skills spec
  related-skills: writing-skills, audit-skills
  domain: meta
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-23"
---

## Iron Law

Load `writing-skills/references/skill-authoring-spec.md` before reviewing any skill — never assess skill quality from memory.

# Skill Reviewer

Thin entry point: this skill forks into the `skill-reviewer` agent ([`.claude/agents/skill-reviewer.md`](../../agents/skill-reviewer.md)). The agent is authoritative for the review criteria, severity levels, output format and verdict; this file does not repeat them.

## Task for the forked agent

1. Scope: `$ARGUMENTS`. If empty, use the working-tree changes: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. If both are empty, report "No changes detected" and the paths searched.
2. Follow the `skill-reviewer` agent instructions end to end on that scope.
3. Cite file:line for every finding and end with the agent's verdict line. Mark any test or check you did not run in this session as NOT RUN.

## Not for

- Periodic health grade of every skill and agent → `/audit-skills`
- Writing a new skill → `writing-skills`
