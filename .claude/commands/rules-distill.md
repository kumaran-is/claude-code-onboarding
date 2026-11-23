---
description: "Scan skills for behavioral patterns repeated across 2+ skills and propose promoting them to rules."
argument-hint: '"[skill-name filter]"'
allowed-tools: Read, Glob, Grep, Write, Edit, Agent
---

# /rules-distill — Distill Skill Patterns Into Rules

Scan all skills for repeated behavioral patterns and promote high-value ones to rules.

## Iron Law

**Only promote patterns with evidence in 2+ skills AND a clear violation scenario — no speculative rules.**

## Usage

```bash
/rules-distill              # Scan all skills
/rules-distill flutter      # Scan only Flutter skills
/rules-distill security     # Scan only security-related skills
```

## What It Does

Runs the 3-phase pipeline:

1. **Inventory** — Find all skills + rules files, build index of behavioral claims
2. **Cross-Read & Match** — Find patterns appearing in 2+ skills, apply 4 filters
3. **User Review** — Present candidates with verdict options, get approval before writing

## 4 Promotion Filters (all must pass)

| Filter | Test | Fail = Skip |
|--------|------|-------------|
| **2+ skills evidence** | Pattern found in ≥ 2 separate skill files | Appears in only 1 skill |
| **Actionable behavior** | Claude can detect violation at write time | Vague preference ("write clean code") |
| **Violation risk** | Missing this causes real bugs or inconsistency | Low-stakes style preference only |
| **Not already in rules** | Pattern NOT already in `.claude/rules/*.md` | Already covered |

## Verdict Taxonomy

| Verdict | Meaning | Action |
|---------|---------|--------|
| `Append` | New rule fits cleanly in an existing rules file | Add to bottom of named file |
| `Revise` | Existing rule in rules file needs strengthening | Edit the specific rule |
| `New Section` | New rules file section needed | Add H2 section to named file |
| `New File` | Cross-cutting enough to warrant its own file | Create new `.claude/rules/xxx.md` |
| `Already Covered` | Pattern exists in rules — show exact file:line | Skip |
| `Too Specific` | Pattern belongs in a skill, not a rule | Skip — stays in skill |

## Output Format (Phase 3 — User Review)

For each candidate, show:

```
## Candidate N: [Pattern Name]

**Evidence:**
- `skills/flutter-mobile/SKILL.md:47` — [quote]
- `skills/nestjs-api/SKILL.md:82` — [quote]

**Proposed Rule:**
> [One sentence rule, starting with "Always" or "Never" or a verb]

**Violation Scenario:**
> [One sentence: what breaks if this rule is absent]

**Verdict:** [Append to `rules/code-standards.md` / Revise / New Section / New File / Too Specific]

**Awaiting: APPROVE / SKIP / MODIFY**
```

## Process

```
1. Glob .claude/skills/**/*.md → build skill list
2. Read each skill (limit: 100 lines first pass, expand if needed)
3. Extract behavioral claims: "always X", "never Y", "must Z", "required", "forbidden"
4. Cross-reference: which claims appear in 2+ skills?
5. Apply 4 filters
6. For surviving candidates: check .claude/rules/*.md for existing coverage
7. Present candidates one by one — wait for APPROVE/SKIP/MODIFY per candidate
8. Write approved candidates to named destination file
```

## Error Cases

| Situation | Action |
|-----------|--------|
| No candidates survive filters | Report: "N patterns found, all filtered — [top 3 reasons]" |
| Candidate conflicts with existing rule | Flag conflict explicitly, ask which takes precedence |
| Destination rules file doesn't exist | Ask before creating a new file |

## Related

- Agent: `.claude/agents/rules-distill.md`
- Rules: `.claude/rules/`
- Skills: `.claude/skills/`
