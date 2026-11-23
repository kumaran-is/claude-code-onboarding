---
description: "Generate a new skill from git history patterns, matching the writing-skills spec."
allowed-tools: Read, Write, Glob, Grep, Bash
---

# /skill-create — Generate a New Skill from Git History

Analyzes git log to detect patterns, then generates a new skill file that matches the workspace's `writing-skills` spec.

## When to Use

- You've noticed a repeated workflow not yet captured in a skill
- A pattern has emerged from 3+ similar commits
- You want to codify a debugging or implementation technique

## Process

### Step 1: Analyze git history
```bash
git log --oneline -n 200 --name-only | head -300
```

Detect:
- **Commit conventions** — what prefixes appear? (`feat:`, `fix:`, `refactor:`)
- **File co-changes** — which files always change together? (signals a workflow)
- **Workflow sequences** — do commits follow a pattern? (e.g., schema → service → controller → test)
- **Architecture patterns** — which directories are touched most often?

### Step 2: Identify the pattern

State the pattern in one sentence:
> "Every time we add a NestJS endpoint, we touch: DTO → service → controller → e2e test, in that order."

If no clear pattern emerges from 200 commits, report: "No repeated pattern detected. Provide a manual description of the skill you want to create."

### Step 3: Generate the skill

Output a complete skill file matching the `writing-skills` spec:

**Required frontmatter fields:**
```yaml
---
name: {skill-name}
description: {CSO trigger words — "Use when...", specific scenario, not vague}
allowed-tools: {minimal set — only what the skill needs}
metadata:
  triggers: {comma-separated trigger words}
  related-skills: {comma-separated related skill names}
  domain: {backend|frontend|mobile|infrastructure|quality|architecture}
  role: {specialist|reviewer|generator}
  scope: {implementation|review|design|testing}
  output-format: {code|report|plan}
last-reviewed: "{YYYY-MM-DD}"
---
```

**Required body sections (in this order):**
1. `**Iron Law:**` — one mandatory rule, no exceptions
2. Summary — 2-3 sentences on what this skill does
3. Process — numbered steps
4. Key patterns — code examples
5. Anti-patterns — at least 1 explicit "don't do this"
6. Error handling — what to do when things go wrong
7. References section — links to related files

**Body constraints:**
- ≤ 500 lines total
- Progressive disclosure: summary → rules → examples → references
- No vague descriptions — every section must be actionable

### Step 4: Validate against spec

Before outputting, self-check:
- [ ] Iron Law present and labeled?
- [ ] Description has CSO trigger words ("Use when...")?
- [ ] allowed-tools is minimal (not `*`)?
- [ ] Body ≤ 500 lines?
- [ ] Anti-patterns section present?
- [ ] Error handling shown?
- [ ] References section present?

If any item fails: fix before outputting.

### Step 5: Save location

Skills go in: `.claude/skills/{skill-name}/SKILL.md`

Reference files go in: `.claude/skills/{skill-name}/reference/`

## Output

Report:
```
Pattern detected: {description}
Skill name: {name}
File: .claude/skills/{name}/SKILL.md
Trigger words: {list}
Lines: {count}
Spec compliance: {list of checks — all green}
```

## Constraints

- Do NOT create skills for one-off tasks (Rule of Three: pattern must appear 3+ times)
- Do NOT reference external scripts that don't exist in this workspace
- Do NOT add `agent:` frontmatter field unless an agent file also exists at `.claude/agents/{name}.md`
- Stack scope: Java 21/Spring Boot, NestJS 11.x, Python 3.14/FastAPI, Angular 22.3.x, React 19.3, Flutter 3.50.x
- Reference spec: `.claude/skills/writing-skills/SKILL.md`

## Edge Cases

### Shallow git history (< 50 commits)
```
Git history too shallow to detect patterns reliably.
Options:
A) Describe the pattern manually and I'll generate the skill from your description
B) Skip pattern detection and use a template (provide: name, trigger scenario, key rules)
```

### Pattern spans multiple unrelated domains
If git log shows the same files changing across unrelated features (e.g., `AppModule` changes in every commit because it's the root import file), exclude registry/index files from pattern analysis and look for the domain-specific co-changes underneath.
