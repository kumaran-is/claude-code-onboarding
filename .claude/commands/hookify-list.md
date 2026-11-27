---
description: "List all Hookify rules — shows name, event, pattern, enabled/disabled status. Usage: /hookify-list"
allowed-tools: Glob, Read
---

# Hookify List — Show All Rules

List every `.claude/hookify.*.local.md` file and its current status.

## Steps

1. Use Glob to find all rule files: `.claude/hookify.*.local.md`

2. For each file, read it and extract:
   - `name`, `enabled`, `event`, `action`, `pattern` (or `conditions`)
   - First line of message body (for preview)

3. Print a summary table:

```
## Hookify Rules

| Name | Status | Event | Action | Pattern |
|------|--------|-------|--------|---------|
| warn-console-log | ✅ enabled | file | warn | console\.log\( |
| require-tests    | ❌ disabled | stop | block | (conditions) |

Total: N rules  (X enabled, Y disabled)
```

4. For each rule, add a one-line preview of its message body.

5. Footer:
```
To toggle rules:    /hookify-configure
To create a rule:   /hookify [describe behavior]
To edit manually:   Edit .claude/hookify.{name}.local.md (changes apply immediately)
To disable:         Set enabled: false  |  To delete: remove the file
```

## If No Rules Found

```
No Hookify rules configured yet.

To create one:
  /hookify Warn me when I use console.log
  /hookify Block force-push to main
  /hookify    # scan conversation for behaviors to prevent
```

$ARGUMENTS
