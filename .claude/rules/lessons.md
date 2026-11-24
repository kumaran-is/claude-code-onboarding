# Lessons — Shared Correction Log

## Purpose

This file records mistakes Claude made that a developer corrected, expressed
as concise rules to prevent recurrence. It is auto-loaded every session.

## Hard Cap: 15 entries maximum

15 entries x 4 lines = ~60 lines. Negligible token cost. Forces curation.

## Entry Format (4 lines max — no exceptions)

```
## [YYYY-MM-DD] [Category] [x1]
**Mistake:** [one sentence — exactly what went wrong]
**Rule:**    [one sentence — what to do instead, always]
**Applies:** [all tasks | specific tech | specific pattern]
```

## Categories (use exactly one per entry)

- `Scope` — touching code outside the request
- `Verification` — claiming something without reading it
- `Code Style` — formatting, comments, naming
- `Communication` — how answers are structured
- `Architecture` — structural decisions
- `Tech:[stack]` — tech-specific (e.g. Tech:Flutter, Tech:NestJS)

## Hygiene Rules

1. **Before adding:** search for an existing entry on the same topic.
   If found, increment the `[xN]` counter. Never add a duplicate.
2. **At x3:** promote the `Rule` line to the matching rules file
   (`core-behaviors.md`, `code-standards.md`, etc.), then DELETE the entry.
3. **At 15 entries:** promote oldest recurring lessons, delete
   non-recurring ones that have never triggered again.
4. **Each entry must fit in 4 lines.** No paragraphs. No explanations.

---

<!-- Entries below. Empty = no corrections recorded yet. -->

## [2026-03-28] Architecture [x1]
**Mistake:** Told sub-agent to run `/scaffold-flutter-app` as bash; agent fell back to `flutter create`, skipping the full industry-standard structure (design_system/, core/di/, clean arch layers).
**Rule:** Scaffold slash commands MUST be run by the orchestrator in the main session via Skill tool BEFORE spawning any agents — sub-agents cannot invoke slash commands.
**Applies:** All multi-agent project creation tasks (Flutter, Angular, NestJS, Python, Spring)

## [2026-11-24] Scope [x1]
**Mistake:** Turned a "close the 2 blocking gaps" job into a 38-file sweep (P2s, doc pins, versions) without first showing the size or checking in.
**Rule:** Before work beyond the blocking fixes, state the file count per item and do the blocking fixes first as their own reviewable set.
**Applies:** All multi-item hardening/audit follow-ups

## [2026-11-23] Communication [x2]
**Mistake:** Kept asking or hinting for yes/no approval (RED-tier edits, "nothing is committed") after the user gave blanket approval.
**Rule:** In this repo, take the recommended option and report it; no approval prompts or approval-fishing lines, commit/push included once the audit passes.
**Applies:** All toolkit maintenance tasks in this repo
