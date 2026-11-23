---
description: "Named checkpoints for long sessions: create, verify, list or compare snapshots of session state."
argument-hint: '"create|verify|list <name>"'
allowed-tools: Read, Write, Bash, Glob
---

# /checkpoint — Named Checkpoints for Long Sessions

Save named snapshots of session state so you can compare before/after or roll back context.

## Modes

### `/checkpoint create <name>`
Save a checkpoint at the current point in the session.

Actions:
1. Run `git diff --stat HEAD` — capture list of changed files
2. Run `git rev-parse HEAD` — capture current SHA
3. Append to `.claude/checkpoints.log`:
   ```
   {ISO-8601-timestamp}|{name}|{git-SHA}|{changed-file-count} files changed
   ```
4. Report:
   ```
   ✅ Checkpoint saved: {name}
   SHA: {git-SHA}
   Changed files: {list from git diff --stat}
   ```

### `/checkpoint verify <name>`
Compare current state against a saved checkpoint.

Actions:
1. Read `.claude/checkpoints.log` — find entry matching `{name}`
2. Run `git diff {saved-SHA} HEAD --stat`
3. Report:
   ```
   Checkpoint: {name} (saved at {timestamp})
   Base SHA: {saved-SHA}
   Current SHA: {current-SHA}

   Files changed since checkpoint:
   {git diff output}

   Delta: +{added} -{removed} lines across {N} files
   ```

### `/checkpoint list`
Show all saved checkpoints for this session.

Actions:
1. Read `.claude/checkpoints.log`
2. Report table:
   ```
   | Name | Saved At | SHA | Files |
   |------|----------|-----|-------|
   | {name} | {timestamp} | {short-SHA} | {count} |
   ```
3. If file is empty or missing: "No checkpoints saved yet. Use `/checkpoint create <name>` to save one."

### `/checkpoint clear`
Remove all entries from `.claude/checkpoints.log`.

Actions:
1. Confirm: "This will delete all {N} checkpoints. Proceed? (yes/no)"
2. On yes: overwrite `.claude/checkpoints.log` with empty content
3. Report: "✅ Checkpoints cleared."

## Log Format

File: `.claude/checkpoints.log`
One entry per line, pipe-separated:
```
2026-03-29T14:22:00Z|pre-refactor|abc1234def|7 files changed
2026-03-29T15:45:00Z|post-auth|def5678abc|3 files changed
```

## When to Use

- Before a large refactor: `/checkpoint create pre-refactor`
- After completing a phase: `/checkpoint create phase-1-complete`
- Before trying a risky approach: `/checkpoint create before-experiment`
- To verify progress: `/checkpoint verify pre-refactor`

## Rules

- Checkpoint names must be lowercase with hyphens (no spaces)
- The log file is append-only (except `/checkpoint clear`)
- Do NOT use checkpoints as a substitute for git commits — they are session-level state markers only
- If `.claude/checkpoints.log` does not exist, create it on first write
