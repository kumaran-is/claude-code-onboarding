---
description: "Pick the next actionable work item from GitHub issues/project, local plans, session tasks, and in-flight branches. Use for /next, next issue, what should I work on, or start next issue. Supports --plan, --wave N, --build #N, --finish #N, --fix-loop, --auto."
argument-hint: "[--plan] [--wave N] [--build #N] [--finish #N] [--fix-loop] [--auto] [#N]"
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, Agent
---

# /next

Load `.claude/skills/next-issue/SKILL.md` and follow it. Angular/React Playwright Test Agents (Planner/Generator/Healer) are conditional specialists in that skill (`browser-testing/reference/playwright-test-agents.md`); `/verify` still runs `playwright test`. Do not implement, branch, or edit files until the full issue or local plan has been read. `--plan` waits for explicit approval. Merge waits for an explicit keyword; `/ship` is readiness (does not merge); `/create-pr` prints `gh pr create` and does not run it. During implement/review-fix run `python3 .claude/scripts/check-verify-impact.py --stage iteration` then the listed gates; on a frozen tree before PR run `--stage frozen` then `/verify pre-pr`. `--fix-loop` is opt-in after a failing `/verify`: qualify GO/NO-GO (`references/loop-and-qualify.md`), then existing `/ralph-loop` with a real shell `--verify-cmd` and max 5 iterations. Never chain the next issue. Seed and append `docs/plans/<N>-implementation-notes.md` (`references/implementation-notes.md`) for any choice a reviewer would question. `/brainstorm` is optional and never blocks an approved issue. Optional worktree isolation is not a gate; detect first with `python3 .claude/scripts/check-worktree-isolation.py --detect`. If `$ARGUMENTS` contains the exact token `--auto` (not `--autoresearch`), also load `references/auto-loop.md` and run `check-next-auto.py`; `--auto` is never implied.

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
