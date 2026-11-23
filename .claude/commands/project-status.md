---
description: Get a quick status summary of the current project — files, structure, dependencies, and health
allowed-tools: Bash, Read, Glob, Grep
---

# Project Status Report

Analyze the current project and provide a concise status report:

1. **Project type detection** — Spring Boot, NestJS/Node, Python, Angular, React, Flutter, or a multi-project repo
2. **File counts** — total files, lines of code by language
3. **Directory structure** — show top 2 levels
4. **Dependencies** — list key dependencies from `pom.xml`, `package.json`, `pyproject.toml` or `pubspec.yaml`
5. **Configuration health** — check if CLAUDE.md, .mcp.json, and `.claude/` are present
6. **Recent git activity** — last 5 commits (if git repo)
7. **Potential issues** — flag missing tests, TODO comments, or config problems

Output as a clean markdown summary.

This is an inventory: it runs no builds or tests and gives no PASS/FAIL verdict. Use instead when: `/verify` — build/test status with exit codes; `/status-check` — what works or is broken, feature by feature.
