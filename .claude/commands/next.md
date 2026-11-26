---
name: next
description: "Pick the next actionable work item from GitHub issues/project, local plans, session tasks, and in-flight branches. Use for /next, next issue, what should I work on, or start next issue. Supports --plan, --wave N, --build #N, --finish #N."
argument-hint: "[--plan] [--wave N] [--build #N] [--finish #N] [#N]"
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
---

# /next

Load `.claude/skills/next-issue/SKILL.md` and follow it. Do not implement, branch, or edit files until the full issue or local plan has been read. `--plan` waits for explicit approval. Merge waits for an explicit keyword and goes through `/ship`. Seed and append `docs/plans/<N>-implementation-notes.md` (`references/implementation-notes.md`) for any choice a reviewer would question. `/brainstorm` is optional and never blocks an approved issue. Optional worktree isolation is not a gate; detect first with `python3 .claude/scripts/check-worktree-isolation.py --detect`.

**Request:** $ARGUMENTS

## 1. Gate

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py --selftest
python3 .claude/skills/next-issue/scripts/check-next-issue.py --scan-skill
```

Both must exit 0. Then collect candidates (`references/discovery.md`), rank with `--pick`, and continue the skill steps.

## 2. Not this command

- Binary feature health → `/status-check`
- Repo inventory → `/project-status`
- Session snapshot → `/checkpoint`
- Build+test → `/verify`
- Paired manual QA → `/test-partner`
