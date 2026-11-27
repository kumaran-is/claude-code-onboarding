---
description: "Enable or disable Hookify rules interactively. Usage: /hookify-configure"
allowed-tools: Glob, Read, Edit, AskUserQuestion
---

# Hookify Configure — Toggle Rules

Enable or disable existing Hookify rules with an interactive picker.

## Step 1 — Find Existing Rules

Use Glob: `.claude/hookify.*.local.md`

If none found:
```
No Hookify rules configured yet.
Use /hookify to create your first rule.
```

## Step 2 — Read Current State

For each file, read and extract: `name`, `enabled` (true/false), `event`, and the first line of the message body.

## Step 3 — Ask User Which Rules to Toggle

Use AskUserQuestion (multiSelect: true):
- Question: "Which rules do you want to toggle?"
- Options (max 4): `{name} — currently {enabled|disabled} | {event}: {pattern-preview}`
- Description: first line of rule message body

## Step 4 — Apply Toggles

For each selected rule:
- If currently `enabled: true` → change to `enabled: false`
- If currently `enabled: false` → change to `enabled: true`

Use Edit tool. Match exactly `enabled: true` or `enabled: false`.

## Step 5 — Report

```
## Hookify Rules Updated

Enabled now:   warn-console-log
Disabled now:  require-tests

Changes apply immediately — no restart needed.

Run /hookify-list to see full status.
```

## Edge Cases

- User selects nothing → "No changes made."
- File write error → show error, suggest editing manually.
- All rules already in desired state → note which were unchanged.

$ARGUMENTS
