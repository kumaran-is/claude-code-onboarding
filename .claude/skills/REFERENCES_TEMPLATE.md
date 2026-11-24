# Skill References Template

## Purpose

Standardizes how skill reference files are organized. Copy this pattern when creating or expanding a skill's `references/` directory.

## Standard Structure

Every skill with reference files should have:

```
skills/{skill-name}/
├── SKILL.md                    # Core — must stay <= 200 lines
└── references/                 # (or reference/) — detailed content
    ├── index.md                # REQUIRED: navigation map to all refs
    ├── documentation/          # Detailed guides and explanations
    ├── examples/               # Copy-paste code templates
    ├── patterns/               # Best practices, anti-patterns
    ├── troubleshooting/        # Common errors and fixes
    └── api-reference/          # Interface/API signatures
```

Note: Most existing skills use a flat `reference/` directory (no subdirectories) rather than subdirectories. The subdirectory layout above is the aspirational target for new skills. For existing skills, a flat `reference/` with an `index.md` navigation file is sufficient.

## index.md Format

Every `reference/` or `references/` directory must have `index.md`:

```markdown
# {Skill Name} References

## Quick Navigation

| Reference | When to Load | Key Content |
|-----------|-------------|-------------|
| [file.md](file.md) | [specific trigger condition] | [what it covers] |
```

Rules for the table:
- "When to Load" must be a concrete trigger, not a vague description
- Every file in the directory must appear in the table
- Files used by reviewer agents must be marked: "(used by `agent-name`)"

## Conditional Loading Table (add to SKILL.md)

Every SKILL.md body should include a **Reference Files** section with this format:

```markdown
## Reference Files

| File | Content | Load When |
|------|---------|-----------|
| [references/index.md](references/index.md) | Navigation map | Any time — start here |
| [references/...](references/...) | [description] | [specific condition] |
```

## Size Guidelines

| File | Target Size | Hard Limit |
|------|-------------|------------|
| SKILL.md core | <= 150 lines | 200 lines |
| Each reference file | <= 100 lines | 200 lines |
| index.md | <= 30 lines | 50 lines |

## Naming Conventions

- Reference files: `kebab-case.md`
- Stack-specific: `{concept}-java.md`, `{concept}-ts.md`, `{concept}-dart.md`
- Examples: `{pattern}-example.md` or just `{pattern}.md` in `examples/`
- Reviewer checklists: `{skill}-review-checklist.md`

## Creating a New Skill — Checklist

- [ ] Create `SKILL.md` (use frontmatter: name, description, metadata.triggers, related-skills)
- [ ] Add an Iron Law at the top if there is a critical must-read reference
- [ ] Create `reference/index.md` mapping every file to a load condition
- [ ] Add a "Reference Files" table to `SKILL.md`
- [ ] Add a "Post-Code Review" section listing reviewer agents
- [ ] Add a row to the Routing table in `.claude/SKILLS_GUIDE.md` (see `feedback_new_docs_location.md`)
- [ ] Keep SKILL.md under 200 lines — move detail into `reference/`
