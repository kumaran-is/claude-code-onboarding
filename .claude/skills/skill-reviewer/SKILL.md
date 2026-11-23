---
name: skill-reviewer
description: Reviews newly created or modified Claude Code skills against the writing-skills spec. Checks Iron Law presence, description quality, allowed-tools declaration, body line count, progressive disclosure structure, and cross-reference patterns. Use after creating or modifying any skill in .claude/skills/.
allowed-tools: Read, Glob, Grep
agent: skill-reviewer
context: fork
metadata:
  triggers: review skill, audit skill, check skill, skill compliance, new skill, skill authoring, writing-skills spec
  related-skills: writing-skills, audit-skills
  domain: meta
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-16"
---

## Iron Law

Load `writing-skills/references/skill-authoring-spec.md` before reviewing any skill — never assess skill quality from memory.

# Skill Reviewer

Audits a Claude Code skill in `.claude/skills/` against the writing-skills spec. Ensures the skill is correctly structured, discoverable, and usable.

## When to Use

- After creating a new skill with `/new-skill-creation`
- After modifying an existing skill's SKILL.md or reference files
- Before committing a skill to verify it will function correctly

## Review Criteria (10 checks)

| # | Criterion | FAIL condition |
|---|-----------|---------------|
| 1 | `name` matches directory | name field ≠ directory name |
| 2 | Description has trigger words | No "Use when..." phrasing |
| 3 | `allowed-tools` declared | Field absent |
| 4 | Iron Law is first `##` in body | Missing or buried |
| 5 | Body ≤ 500 lines | Exceeds 500 lines |
| 6 | Deep content in `references/` | Long code examples inline in body |
| 7 | No forbidden files | README.md, CHANGELOG.md present |
| 8 | Cross-references use "see X" | Content copy-pasted verbatim |
| 9 | Each `references/` file < 300 lines | Any reference file > 300 lines |
| 10 | `references/` exists for stack patterns | Stack-specific code but no references/ |

## Process

1. Identify target skill directory from `$ARGUMENTS`
2. Load `writing-skills/references/skill-authoring-spec.md`
3. Read `SKILL.md` in full + list all files in the directory
4. Apply all 10 criteria
5. Report with PASS/WARN/FAIL per criterion + file:line evidence

## Verdict

```
VERDICT: [PASS|CONDITIONAL PASS|FAIL] — PASS: N | WARN: N | FAIL: N
```
