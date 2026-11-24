---
description: Promote mature lessons to rules, consolidate agent-memory orphans, and prune stale entries. Run periodically or at session end.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Promote Lessons

Run the full lessons lifecycle: promote, consolidate, and prune.

## Step 1: Check lessons.md for x3+ promotions

Read `.claude/rules/lessons.md`. For each entry with `[x3]` or higher:

1. Identify the target rules file from the entry's `**Applies:**` field:
   - "all tasks" → `core-behaviors.md`
   - "specific tech" → `code-standards.md` or the tech's skill reference
   - "specific pattern" → `leverage-patterns.md`
   - Category `Tech:Flutter` → `.claude/skills/flutter-mobile/` reference files
   - Category `Tech:NestJS` → `.claude/skills/nestjs-api/` reference files
   - Category `Tech:Java` → `.claude/skills/java-spring-api/` reference files
   - Category `Scope` → `core-behaviors.md`
   - Category `Verification` → `verification-and-reporting.md`
   - Category `Code Style` → `code-standards.md`
   - Category `Communication` → `core-behaviors.md`
   - Category `Architecture` → `core-behaviors.md` or `leverage-patterns.md`

2. Read the target file. Find the most relevant section.
3. Append the `**Rule:**` line as a new bullet or paragraph in that section.
4. Delete the entry from `lessons.md`.
5. Report what was promoted and where.

**Hookify alternative.** If the mistake is detectable by a regex on one tool-call field (a Bash command, an edited file's path or new text, the stop event or the user prompt), enforce it with a Hookify rule instead of, or as well as, a rules-file line. Write `.claude/hookify.<verb>-<name>.local.md` using the schema in `.claude/commands/hookify.md`:

```markdown
---
name: warn-console-log-typescript
enabled: true
event: file          # bash | file | stop | prompt | all
pattern: console\.(log|warn|error)\(
action: warn         # warn | block
---

New production TypeScript must use the Logger, not console.* (first-principles.md Layer 1).
```

Test the pattern against a bad and a good sample (`python3 -c "import re; print(re.search(r'<pattern>', '<sample>'))"`), narrow it with `conditions:` (e.g. `file_path` `regex_match` `\.ts$`) when it would fire on unrelated files, then delete the lesson entry and report the rule file as its destination. Judgment calls (scope, communication) stay as rules-file text.

## Step 2: Consolidate agent-memory orphans

Check if `.claude/agent-memory/` exists. If it does, for each `MEMORY.md` or `*.md` file:

1. Read the file.
2. Classify each item:
   - **Mistake/trap/gotcha** → Write as a lesson entry in `lessons.md` (4-line format, `[x1]`)
   - **Reusable pattern/fix template** → Append to the matching skill's reference file under `.claude/skills/<agent-name>/reference/`
   - **Project-specific coordinates/config** → Skip (ephemeral, not worth keeping)

3. After consolidation, delete the processed `.claude/agent-memory/` files.
4. If the directory is empty after cleanup, delete it.

## Step 3: Prune stale entries

If `lessons.md` has more than 15 entries after consolidation:

1. Identify entries that are still `[x1]` and older than 30 days.
2. List them and ask: "These lessons never recurred. Remove them to stay under the 15-entry cap?"
3. Only delete after confirmation.

## Step 4: Report

```
## Lessons Lifecycle Report

### Promoted (x3+ → rules)
- [lesson summary] → [target-file:section | .claude/hookify.<name>.local.md (event, action)]

### Consolidated (agent-memory → lessons/skills)
- [agent]/[file]: [N] items → lessons.md, [M] items → [skill reference]

### Pruned
- [entry] — removed (stale, never recurred)

### Current State
- lessons.md: [N]/15 entries
- agent-memory/: [exists/cleaned up]
```

Use instead when: `/rules-distill` — the source is repeated patterns across skills, not corrections logged in `lessons.md`. Rule-file edits that change shared rules are proposals for human approval, not silent writes.

$ARGUMENTS
