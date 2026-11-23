---
name: review-wireframe
description: "Review a wireframe HTML file with Elon + Steve dual-persona scoring"
argument-hint: "[path to wireframe HTML file]"
allowed-tools: Read, Write, Glob, Grep
---

Use the **wireframe-reviewer** agent to review and score: $ARGUMENTS

If no file path is provided, find the most recently modified wireframe HTML file in the project directories (exclude index.html, sample/, .claude/, .github/).

The agent is read-only. If its verdict is **APPROVED** (score ≥ 80), save the `## Lock Document` section of its report to `[project-folder]/[project]-approval.md` with the Write tool, then show the saved path.
