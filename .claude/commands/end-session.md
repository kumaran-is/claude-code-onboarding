---
description: "Wrap the session: snapshot via /checkpoint, run /promote-lessons, capture current work, failed approaches, decisions, blockers, Git status, and a pasteable resume prompt. Use when the user says end session, done for the day, close this session, or wrap up. Does not commit or push unless the user already asked in this session."
argument-hint: "[optional wrap note]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /end-session

## Iron Law

**Do not commit or push unless the user already asked in this session. Reuse `/checkpoint` and `/promote-lessons` — do not invent a second snapshot format or a second lessons classifier. "No lesson" is valid.**

Handoff so a fresh session (or a teammate) continues from the repo, not this chat.

**Request:** $ARGUMENTS

## Step 0 — Snapshot (reuse `/checkpoint`)

Follow `.claude/commands/checkpoint.md` mode `create session-wrap-<YYYY-MM-DD>`. Appends `.claude/checkpoints.log` only. Not a git commit. If that name already exists today, skip the duplicate write and cite the existing line.

## Step 1 — Lessons (reuse `/promote-lessons`)

Follow `.claude/commands/promote-lessons.md` end to end for this session + `git log <default>..HEAD`. **"No lesson this session" is valid — never pad `lessons.md`.**

Post-ship incidents in this session go through promote-lessons Step 0b (escaped-defect protocol). Do not silently weaken a check.

## Step 2 — Capture (read-only unless asked)

```bash
git status --short
git rev-parse --abbrev-ref HEAD
git log --oneline -5
git rev-list --count @{u}..HEAD 2>/dev/null || echo "no upstream"
```

Collect, then print:

| Field | Source |
|---|---|
| Current work | Branch, uncommitted paths, last 5 SHAs, in-flight issue from the branch name if any |
| Decisions | Every `Needs human review: yes` in `docs/plans/*-implementation-notes.md` |
| Blockers | Failed `/verify`, open human-review flags, `blocked_by` still open, dirty paths the user did not want committed |
| Git status | Dirty yes/no, unpushed count. **Do not commit. Do not push.** |
| Resume marker | Active `docs/plans/*` or `.startup-design/manifest.json` — print the suggested “done / next”; write it only if the user wants the wrap in git |
| What Did Not Work | Failed approaches from this session. Cite evidence (command + exit code, failing test, or a `/checkpoint` name such as `before-experiment`). **This is not a lesson** — do not write `lessons.md` here; `/promote-lessons` already ran in Step 1. If a PreCompact snapshot exists at `.claude/temp/precompact/latest.md`, you may cite its checkpoint line as evidence. |

## Step 2b — What Did Not Work and Why (reuse `/checkpoint`)

List approaches tried this session that failed, so the next session does not retry them. Do not invent a second snapshot file: if you checkpointed before an experiment, cite that `/checkpoint` name.

- One line per attempt: `<what was tried>: <why it failed> · evidence: <cmd exit N | test name | checkpoint name>`
- Include supporting evidence that already exists (verify output, test names, hook stderr, checkpoint log). Do not dump secrets or full logs.
- If nothing failed: `none — no failed approaches this session`

## Step 3 — Summary (binary, no percentages)

```
## Session wrap
Accomplished: <what, with SHAs if committed>
Lessons: none — <reason> | <N routed>
Current work: <branch + dirty paths or clean>
Decisions needing human review: <list or none>
Blockers: <list or none>
Branch: <name> · dirty <yes/no> · unpushed <N>
Checkpoint: session-wrap-<date> @ <SHA>
Verified: cite /verify or /status-check evidence, or say NOT RUN

## What Did Not Work and Why
- <attempt>: <why it failed> · evidence: <cmd exit N | test | checkpoint name>
none — no failed approaches this session

## Resume prompt (paste into a new session)
Continue <branch> from <SHA>. Last done: <one line>. Next: <one concrete step>. Blockers: <list or none>. Review: <human-review flags or none>. Dirty: <yes/no — list paths>. Failed approaches: <one line or none>.
```

Do not claim work “done” without evidence (`verification-and-reporting.md`).

## Not this command

| Need | Use |
|---|---|
| Classify lessons only | `/promote-lessons` |
| Named snapshot only | `/checkpoint` |
| Pick next work | `/next` |
| Binary feature health | `/status-check` |
