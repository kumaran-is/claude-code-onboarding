---
description: Learning lifecycle — intake corrections, reviewer findings, successes and post-ship outcomes, classify each (lesson, rule, deterministic control, skill reference, implementation note), promote recurrences, consolidate agent memory, enforce the lessons cap. Run periodically, after a merge or at session end.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Promote Lessons

Run the learning lifecycle: intake, classify, promote, consolidate, prune. Every change to a shared rule, skill, agent or hook lands as an ordinary diff for human review in the PR; nothing here commits or auto-applies.

## Step 0: Intake

Collect candidates from every source, not only corrections:

| Source | How |
|---|---|
| Corrections | `lessons.md` entries (the CLAUDE.md Self-Improvement Loop writes them) |
| Reviewer findings | Closed and dismissed findings in `.claude/state/review/*/ledger.json` (enforcement kit). The same root-cause class closed on 2 or more branches is a recurrence |
| Successes | An approach that worked first time on something that usually fails (a debugging route, a test seam, a release step), noted by the user or in the PR's lessons step |
| Post-ship | Since the last run: reverted PRs (`git log --oneline --grep='^Revert' --since=<date>`), fix commits that touch code merged in the window, incidents or bug reports the user names. For each: what escaped, which gate should have caught it, and why it did not |
| Agent memory | `.claude/agent-memory/**` (Step 2) |

## Step 1: Classify, then route

Write each candidate as a pair: **avoid X, do Y, because Z**. A candidate that cannot be written that way is a fact, not a lesson: drop it or put it in the plan's implementation notes.

| Class | Test | Destination |
|---|---|---|
| Prohibition, first time | "never / always" judgement a rule file does not already state | `lessons.md` entry `[x1]` (search first; increment instead of duplicating) |
| Prohibition, recurring | `[x3]`, or the same class on 2+ branches | The rule file (table below), then delete the lesson |
| Mechanically detectable | One regex on a tool call, or one checkable file shape | A deterministic control: Hookify rule (below) or a `check-*` script with `--selftest`, edit-hook advisory and CI caller (`hook-and-gate-authoring.md`, one detector three callers). Prefer this over prose once it recurs |
| Procedure | A sequence of steps that worked | The owning skill's `reference/`, through `/skill-create`'s improve path and `skill-reviewer` |
| Decision on one issue | Why this design, for this change | The plan's implementation notes (`plan-mode-review`), not a lesson |
| Success | "Do Y" with no prior mistake | The owning skill's reference as a "what works" line, or nothing if it is already there |
| One-off fact | Coordinates, ids, a person's preference | Nothing (or user memory) |

Rule-file targets for promoted prohibitions:
   - "all tasks" → `core-behaviors.md`
   - "specific tech" → `code-standards.md` or the tech's skill reference
   - "specific pattern" → the owning skill's reference (`leverage-patterns.md` holds mandates only, and the always-loaded total has a ceiling: `check-context-budget.sh --strict`)
   - Category `Tech:Flutter` → `.claude/skills/flutter-mobile/` reference files
   - Category `Tech:NestJS` → `.claude/skills/nestjs-api/` reference files
   - Category `Tech:Java` → `.claude/skills/java-spring-api/` reference files
   - Category `Scope` → `core-behaviors.md`
   - Category `Verification` → `verification-and-reporting.md`
   - Category `Code Style` → `code-standards.md`
   - Category `Communication` → `core-behaviors.md`
   - Category `Architecture` → `core-behaviors.md` or the `architecture-design` skill

For each promotion: read the target, find the most relevant section, add the `**Rule:**` line, delete the lesson entry, and re-run `bash .claude/scripts/check-context-budget.sh --strict` when the target is always loaded. If it is a critical rule with no mechanical enforcement, pin an anchor in `.claude/context-canaries.tsv`.

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

## Step 2: Consolidate and prune agent memory

If `.claude/agent-memory/` exists, read each `MEMORY.md` or `*.md` file and route every item through the Step 1 table (mistake → lesson, reusable pattern → skill reference, coordinates or per-issue notes → drop). Then delete the processed files and remove empty directories. For the user's auto-memory (outside the repo), only report: index over 200 lines, entries that name files or flags that no longer exist (grep them), and duplicates.

## Step 3: Enforce the cap

`lessons.md` holds at most 15 dated entries; `pre-edit-lessons-dedup.sh` denies an edit that would exceed it. When it is full: promote `[x3]` entries, merge entries on the same topic (sum the counters), and remove `[x1]` entries older than 30 days that never recurred (list them in the report with their dates).

## Step 4: Report

```
## Lessons Lifecycle Report

### Promoted (x3+ → rules)
- [lesson summary] → [target-file:section | .claude/hookify.<name>.local.md (event, action)]

### Consolidated (agent-memory → lessons/skills)
- [agent]/[file]: [N] items → lessons.md, [M] items → [skill reference]

### Routed (intake → destination)
- [source: correction | finding | success | post-ship | memory] [avoid X, do Y, because Z] → [destination]

### Deterministic controls proposed or added
- [recurrence] → [hookify rule | check script] (selftest: [result])

### Pruned
- [entry] — removed (stale, never recurred)

### Current State
- lessons.md: [N]/15 entries
- agent-memory/: [exists/cleaned up]
```

Use instead when: `/rules-distill` — the source is repeated patterns across skills, not corrections logged in `lessons.md`. Rule-file edits that change shared rules are proposals for human approval, not silent writes.

$ARGUMENTS
