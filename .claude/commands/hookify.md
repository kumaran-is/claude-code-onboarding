---
description: "Create a Hookify rule to prevent an unwanted behavior. Describe the behavior or leave blank to scan the conversation. Usage: /hookify [description of behavior to prevent]"
allowed-tools: Bash, Read, Write, Glob, AskUserQuestion
---

# Hookify — Create Rule

Create a `.claude/hookify.*.local.md` rule file to prevent an unwanted behavior.
Rules are active immediately — no restart needed.

## Rule File Format

```markdown
---
name: warn-console-log        # kebab-case, start with verb: warn/block/require
enabled: true
event: file                   # bash | file | stop | prompt | all
pattern: console\.log\(       # Python regex matched against relevant field
action: warn                  # warn (show message) | block (deny the tool call)
---

Message shown to Claude when rule triggers. Use markdown.
```

**Fields for `event`:**
- `bash` → matches the `command` field of Bash tool calls
- `file` → matches `new_text`/`file_path` of Edit/Write/MultiEdit calls
- `stop` → fires when Claude tries to stop; block to enforce checklist
- `prompt` → fires on user_prompt before Claude reads it
- `all` → fires on every tool call

**Advanced: multiple conditions (all must match)**
```markdown
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.ts$
  - field: new_text
    operator: contains
    pattern: console.log
```
Operators: `regex_match` `contains` `equals` `not_contains` `starts_with` `ends_with`

## Step 1 — Identify the Behavior

**If `$ARGUMENTS` is provided:** use that description as the behavior to prevent.

**If `$ARGUMENTS` is empty:** scan recent conversation for:
- Explicit corrections ("don't do X", "stop doing Y", "I didn't ask for that")
- Repeated patterns the user had to revert
- Frustrated reactions

List up to 4 candidate behaviors.

## Step 2 — Ask User to Confirm

Use AskUserQuestion:
- **Q1**: "Which behavior(s) should become a rule?" (multiSelect: true, list each candidate)
- **Q2**: For each selected — "Should this block the operation or just warn?"
  - Option A: `warn` — show message but allow it to proceed
  - Option B: `block` — deny the tool call entirely

## Step 3 — Infer Pattern

For each confirmed behavior:
1. Determine `event` (bash, file, stop, prompt)
2. Write a Python regex `pattern` for the relevant field
3. Test pattern mentally: does it match the bad case? Does it avoid false positives?

Pattern tips:
- `\s+` = whitespace, `\.` = literal dot, `\(` = literal paren
- `|` for OR: `console\.log\(|debugger`
- Too broad → add `tool_matcher` to limit which tools fire

## Step 4 — Create the Rule File

Write to `.claude/hookify.{descriptive-name}.local.md` (relative to project root).

Naming: `warn-console-log`, `block-force-push`, `require-tests-before-stop`

Show user what was created:
```
Created: .claude/hookify.{name}.local.md
  event: {event}  |  action: {action}  |  pattern: {pattern}
Active immediately — trigger it to test.
```

Verify file exists with Glob: `.claude/hookify.*.local.md`

**To test the pattern:**
```bash
python3 -c "import re; print(re.search(r'YOUR_PATTERN', 'test text'))"
```

$ARGUMENTS
