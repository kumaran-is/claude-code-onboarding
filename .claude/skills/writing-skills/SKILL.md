---
name: writing-skills
description: "Author or extend a Claude Code skill: anatomy, frontmatter, trigger-word descriptions, progressive disclosure, 500-line limit, creation checklist. Use when creating or restructuring a skill. Review a finished skill with skill-reviewer."
allowed-tools: Read, Write, Edit, Glob, Grep
metadata:
  triggers: create a skill, write a skill, add a skill, new skill, skill structure, skill authoring, skill template, SKILL.md
  related-skills: subagent-driven-development, plan-mode-review, documentation-generation
  domain: workflow
  role: specialist
  scope: design
  output-format: document
last-reviewed: "2026-03-16"
---

# Writing Skills

## Iron Law

**NO SKILL AUTHORING WITHOUT READING AN EXISTING SKILL FIRST**

Read at least one existing SKILL.md in `.claude/skills/` before writing your own. Understand what the pattern looks like in practice, not just in spec.

## Anatomy of a Skill

```
.claude/skills/<skill-name>/
  SKILL.md                    <- Body: <=500 lines. Loaded on trigger.
  references/                 <- Deep content: loaded as needed
    <topic>.md
  assets/                     <- Diagrams, templates, static files
  scripts/                    <- Executable helper scripts
```

**Frontmatter fields** (see `references/skill-anatomy.md` for full spec):

```yaml
---
name: my-skill                          # Required -- matches directory name
description: [trigger text]            # Required -- this is how the skill gets selected
allowed-tools: Read, Write, Glob        # Strongly recommended -- limits available tools
last-reviewed: "YYYY-MM-DD"            # Recommended -- for /audit-skills staleness check
metadata:                              # Optional -- arbitrary key/value
  version: "1.0"
---
```

**Note on `allowed-tools`:** This onboarding kit uses `allowed-tools` in 24 of 29 skills. It IS valid per the official spec. Always include it -- it makes tool availability explicit and prevents the skill from inheriting an unrestricted toolset.

## Progressive Disclosure (3 Levels)

```
Level 1 -- Always loaded:    Frontmatter (name, description, allowed-tools)
Level 2 -- Loaded on trigger: SKILL.md body (<=500 lines)
Level 3 -- Loaded as needed:  references/ files (deep content, patterns, templates)
```

**Rule:** If content is referenced once per session, put it in the body. If it's deep reference material consulted occasionally, put it in `references/`.

## The 500-Line Limit

SKILL.md body must stay under 500 lines. When approaching the limit:
1. Move detailed examples to `references/`
2. Move stack-specific patterns to `references/<stack>.md`
3. Keep only: Iron Laws, decision trees, quick checklists, cross-references in the body

## What NOT to Include

Do NOT create these files in a skill directory:
- `README.md` -- skills are not packages, no installation docs needed
- `INSTALLATION_GUIDE.md` -- same reason
- `CHANGELOG.md` -- version history belongs in git, not skill files
- `CONTRIBUTING.md` -- meta-meta documentation that nobody reads

## Description as the Trigger Mechanism

The `description` field is how Claude selects this skill. Write it like a search-optimized trigger:

```yaml
# BAD -- too vague
description: Skill for building things with Flutter

# GOOD -- includes all trigger words, usage contexts, explicit "when to use"
description: Use when building Flutter screens, Riverpod providers, Freezed models,
  or widget tests. Covers clean architecture, Firebase integration, and adaptive UI.
  Triggers: "Flutter", "Dart", "mobile app", "Riverpod provider", "widget test".
```

Rule: Include every word a developer would type when they need this skill.

## Minimal Correct Skill Example

```yaml
---
name: my-linter
description: Use when running or configuring the project linter. Covers ESLint,
  Prettier, and auto-fix workflows. Triggers: "lint", "fix lint", "eslint config".
allowed-tools: Bash, Read, Edit
last-reviewed: "2026-01-01"
---

**Iron Law:** Always run the linter before reporting a file clean.

# My Linter Skill

## Verify

```bash
npx eslint . --max-warnings 0   # must exit 0
```
```

The `description` gets the skill selected; the Iron Law prevents silent skips; the verify command gives a binary pass/fail gate.

## 8-Step Creation Checklist

```
[] 0. OVERLAP     -- ls .claude/skills/ and grep the domain's trigger words across
                     .claude/skills/*/SKILL.md; if a skill already covers it in part,
                     extend that skill (new section or reference file) instead
[] 1. NAME        -- matches directory, lowercase-hyphenated, specific domain
[] 2. DESCRIPTION -- includes all trigger words; passes the CSO test above
[] 3. ALLOWED-TOOLS -- listed explicitly; minimum needed for the skill's tasks
[] 4. BODY        -- Iron Law first; decision trees > prose; <=500 lines
[] 5. REFERENCES  -- deep patterns offloaded to the skill's reference folder
                     (`reference/` is the common convention here; keep whichever
                     the skill already uses); each file < 300 lines
[] 6. TEST        -- load the skill, ask it a question, verify it triggers correctly
[] 7. REGISTER    -- add a row to the `.claude/SKILLS_GUIDE.md` Routing table
                     (technology skills) and its reviewer table (if a reviewer agent
                     applies); add the skill under its domain there; touch CLAUDE.md
                     only for a new stack row (always-loaded budget); run `bash .claude/scripts/lint-skills.sh` and `skill-reviewer`
```

## Verify Command (required in every skill)

Every skill MUST include a "Run X to verify" gate — a command or checklist that produces a binary pass/fail result. Place it in its own `## Verify` section near the bottom of SKILL.md.

```markdown
## Verify

Run:  <command>   # exit 0 = green
-or-
Checklist:
- [ ] <criterion 1>
- [ ] <criterion 2>
```

## Cross-Stack Skill Pattern

For skills that cover multiple tech stacks (Java, NestJS, Python, Flutter):

```markdown
## Stack Dispatch

| Stack   | Reference File |
|---------|---------------|
| Java    | references/patterns-java.md |
| NestJS  | references/patterns-nestjs.md |
| Python  | references/patterns-python.md |
| Flutter | references/patterns-flutter.md |
```

Keep the body stack-agnostic. Push all stack-specific code into reference files.

## References

- `references/skill-anatomy.md` -- full frontmatter field spec, directory conventions
- `references/skill-authoring-spec.md` -- condensed official spec, what NOT to include, CSO rules
