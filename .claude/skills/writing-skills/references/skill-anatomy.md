# Skill Anatomy Reference

## Directory Structure

```
.claude/skills/<skill-name>/
|
+-- SKILL.md                    <- Primary body file
|   +-- Frontmatter (YAML)      <- Always loaded by Claude
|   +-- Body (Markdown)         <- Loaded when skill triggers; <=500 lines
|
+-- references/                 <- Deep content, loaded on demand
|   +-- <topic-a>.md            <- Stack-specific patterns
|   +-- <topic-b>.md            <- Checklists, templates
|   +-- <review-checklist>.md   <- Reviewer agents use these
|
+-- assets/                     <- Non-executable static content
|   +-- diagrams/
|   +-- templates/
|
+-- scripts/                    <- Executable helpers
    +-- setup.sh
```

## Frontmatter Fields

All fields are defined at the top of SKILL.md between `---` markers.

### `name` (Required)

```yaml
name: flutter-mobile
```

- Matches the directory name exactly (nested plugin skills may use `{parent}-{leaf}`)
- Agent Skills spec: 1–64 chars; lowercase `a-z0-9` and single hyphens; no leading, trailing, or consecutive hyphen
- Should be a specific domain, not generic ("api-patterns" is bad; "nestjs-api" is good)

### `description` (Required)

```yaml
description: Use when building Flutter screens...
```

- This is the PRIMARY trigger mechanism -- Claude selects skills by matching description
- Agent Skills spec: 1–1024 characters, non-empty; describe what it does **and** when to use it
- Must include: what the skill does, when to use it, trigger words/phrases
- Minimum 2 sentences; up to 8 sentences is fine
- Include ALL synonyms a developer might type
- Under-trigger (missing keywords) is as bad as over-trigger (vague keywords)

### `allowed-tools` (Strongly Recommended)

```yaml
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
```

Available tool names:
- `Read` -- read file contents
- `Write` -- create/overwrite files
- `Edit` -- targeted string replacement in files
- `Glob` -- file pattern matching
- `Grep` -- content search (ripgrep)
- `Bash` -- shell command execution
- `Agent` -- spawn sub-agents (use sparingly)
- `WebFetch` -- fetch URL content
- `WebSearch` -- search the web

**Principle:** List the MINIMUM tools the skill needs. Do not grant Write/Edit if the skill is read-only (reviewers). Do not grant Bash if no shell commands are needed.

### `last-reviewed` (Kit extra — not an official Claude Code field)

Official skill fields: [Extend Claude with skills](https://code.claude.com/docs/en/skills). Claude Code ignores unrecognized keys. This kit still reads a top-level `last-reviewed` in `/audit-skills`. For new skills, also set `metadata.last-reviewed` so Agent Skills packaging stays spec-legal (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`).

```yaml
last-reviewed: "2026-03-14"
metadata:
  last-reviewed: "2026-03-14"
```

- ISO-8601 date of last substantive review (content verified against current docs/APIs)
- Updated whenever the skill body or references are meaningfully revised
- Used by `/audit-skills` to flag skills not reviewed in 90+ days
- Do NOT update just for typo fixes — only when content correctness was verified

### `model` (Optional — official Claude Code field)

```yaml
model: opus
```

- Official field ([Extend Claude with skills](https://code.claude.com/docs/en/skills)): alias values from `/model` (`opus`, `sonnet`, `haiku`, `inherit`).
- Takes effect on **`/name` invocation** for that turn. When Claude auto-loads the skill, the session keeps its model — unless `context: fork`, in which case `model` is the forked subagent's per-invocation model.
- Use `opus` only on independent LLM review / spec / architecture / security / quality-assessment skills. Implementation and orchestration stay on session `sonnet`.
- If the skill forks to a named `agent:`, set `model:` on **`.claude/agents/<agent>.md`** (that is what `/review-code` and SDD quality review dispatch). Do not duplicate `model:` on the skill unless the skill is invoked as `/name` without going through that agent.

### `metadata` (Optional)

```yaml
metadata:
  version: "1.0"
  domain: "backend"
  stack: "java"
```

Arbitrary key-value store. Use for tagging, versioning, or domain classification.

## Progressive Disclosure Rules

| Content Type | Where to Put It |
|-------------|----------------|
| Iron Laws | SKILL.md body (always visible) |
| Decision trees | SKILL.md body |
| Quick checklists | SKILL.md body |
| Stack-specific code examples | references/ |
| Long pattern catalogs | references/ |
| Review checklists (for agents) | references/ |
| Diagrams | assets/ |
| Setup scripts | scripts/ |

## File Size Limits

| File | Limit | Action if Exceeded |
|------|-------|--------------------|
| SKILL.md (body) | 500 lines | Move examples to references/ |
| references/*.md | 300 lines | Split into topic-specific files |
| Total skill directory | No hard limit | Keep lean -- context is precious |

## Naming Conventions

| Item | Convention | Example |
|------|------------|---------|
| Skill directory | lowercase-hyphenated | `nestjs-api` |
| Reference files | descriptive-hyphenated | `reactive-patterns.md` |
| Review checklists | `*-review-checklist.md` | `spring-boot-review-checklist.md` |
| Stack patterns | `patterns-<stack>.md` | `patterns-java.md` |
