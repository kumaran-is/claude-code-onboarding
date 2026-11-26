# Skill Authoring Spec (Condensed)

## Source

Canonical format: [Agent Skills specification](https://agentskills.io/specification). Used by `writing-skills`, `lint-skills.sh` and `/audit-skills`. Do not vendor `skills-ref` or Anthropic plugins; the kit detector is `scripts/check-skill-spec.py`.

## The Core Principle: Context is a Public Good

Every token loaded into Claude's context window costs real money and occupies finite space. Skill authors must treat context as a shared resource:

- **Concise is key** -- write skills that are dense with value, not dense with words
- **Progressive disclosure** -- load only what's needed, when it's needed
- **Degrees of freedom** -- give Claude enough guidance to work, not a rigid script

## Frontmatter Spec

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | 1–64 chars; `a-z0-9` and single hyphens; no leading/trailing/consecutive hyphen; matches the skill directory (nested plugin skills may use `{parent}-{leaf}`, e.g. `daisyui-colors`) |
| `description` | string | 1–1024 chars; what the skill does **and** when to use it; this is the always-loaded trigger |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `allowed-tools` | string | Comma-separated tool list; limits available tools |
| `metadata` | map | Arbitrary key-value metadata |

**Important:** The `allowed-tools` field IS valid per this spec. Some older skill samples incorrectly omit it -- always include it in new skills.

## What Makes a Good Description

The description field is the skill's search engine optimization (CSO -- Claude Search Optimization).

```
GOOD description includes:
+ Explicit "Use when..." or "Triggers when..." phrasing
+ The technology names (e.g., "Flutter", "NestJS", "Spring Boot")
+ The action words (e.g., "building", "reviewing", "debugging", "testing")
+ Synonyms for the same concept (e.g., "test", "spec", "unit test", "TDD")

BAD description:
- Too short: "Flutter skill" -- no trigger words
- Too vague: "Use for mobile development" -- doesn't match specific queries
- Missing synonyms: Only mentions "testing" but not "TDD" or "test-driven"
- Under-trigger: owns Flutter/Riverpod work but never says "Riverpod" or "widget test"
- Over-trigger: "Use when writing code" -- fires on every stack
```

## Activation reliability

The `description` (plus `metadata.triggers` in this kit) is the only always-loaded signal. Two failures:

| Mode | Symptom | Eval |
|------|---------|------|
| **Under-trigger** | Skill never loads for work it owns | Representative prompt overlap < 2 distinctive tokens |
| **Over-trigger** | Skill loads for an unrelated stack | Sibling skill overlap ≥ 2 distinctive tokens on that prompt |

Same detector as `lint-skills.sh` (not a second eval framework):

```bash
python3 .claude/skills/writing-skills/scripts/check-skill-spec.py --dir .claude/skills --activation
```

Representative suites (positive + negative): Flutter, Angular, React, Java, Python, AI/MCP, startup-design. A generic prompt ("What is today's date?") must not activate those stack skills.

Ad-hoc, while authoring:

```bash
python3 .claude/skills/writing-skills/scripts/check-skill-spec.py --dir .claude/skills \
  --prompt "Add a Riverpod provider for the Flutter login screen" \
  --expect flutter-mobile --forbid angular-spa,react-spa
```

## What NOT to Include in a Skill Directory

| File | Why Not |
|------|---------|
| `README.md` | Skills are not packages -- no user installation needed |
| `INSTALLATION_GUIDE.md` | Same reason |
| `CHANGELOG.md` | Version history belongs in git commit history |
| `CONTRIBUTING.md` | Meta-meta documentation; no developer reads it |
| `requirements.txt` / `package.json` | Skills don't have dependencies |

## The Iron Law Pattern

Every effective skill leads with an Iron Law -- a short, memorable rule that captures the most important constraint:

```markdown
## Iron Law

**NO <ACTION> WITHOUT <PREREQUISITE> FIRST**
```

Examples from this codebase:
- `systematic-debugging`: "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST"
- `verification-before-completion`: "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE"
- `writing-skills`: "NO SKILL AUTHORING WITHOUT READING AN EXISTING SKILL FIRST"

The Iron Law appears first in the body, before any other content.

## Decision Trees over Prose

Prefer decision trees to paragraphs:

```
# BAD -- prose
When you need to add code, first check if a relevant file exists.
If it does, modify that file. If not, consider whether the code
is more than 150-200 lines of cohesive logic, and if so, create
a new file. Otherwise, find the closest existing file.

# GOOD -- decision tree
Need to add code?
    |
    v
Does relevant file exist?
    YES -> Modify existing file (DEFAULT)
    NO  -> Is this >150 lines of cohesive new logic?
               YES -> Create new file (ask human first)
               NO  -> Add to closest existing file
```

## Cross-Reference Pattern

When a skill overlaps with another, use explicit cross-references instead of duplicating content:

```markdown
> For [specific scenario], see `<other-skill-name>` -- [one sentence on what it adds].
```

Never copy-paste content from one skill into another. Reference it.

## Recommended Skill Types

Not all skills have the same shape. Match the skill type to the job it does.

| Skill Type | When to Use | Signature Pattern |
|---|---|---|
| **How-to skill** | Teaches a technology or pattern (e.g., `flutter-mobile`, `nestjs-api`) | Iron Law → quick-start template → pattern table → reference files |
| **Workflow skill** | Enforces a multi-step process (e.g., `systematic-debugging`, `verification-before-completion`) | Iron Law → phase/step sequence → stop conditions → escalation protocol |
| **Codebase orientation skill** | Helps a developer navigate an unfamiliar repo or system | Reading-order-by-intent table → topology diagram → patterns worth understanding → gotchas |
| **Review/audit skill** | Used to evaluate existing code or decisions | Severity rubric → checklist → output format → pass/fail gates |
| **Config/setup skill** | One-time bootstrapping that must not be re-done | Pre-flight checklist → step sequence → verification commands → known failure modes |

### Codebase Orientation Skill — Template

Use this template when writing a skill whose primary job is to orient a developer in a codebase, explain how a system works, or provide a guided reading path. This type is distinct from how-to or workflow skills.

Sourced from the `race-condition` reference architecture (Google Cloud Next '26 keynote demo).

```markdown
## Iron Law

**READ THE ARCHITECTURE BEFORE CHANGING ANYTHING — code changes without orientation create bugs that are hard to diagnose**

## Where to Start (by Intent)

Pick the question that matches your goal and follow the file pointers.

| You want to understand... | Read in this order |
|---|---|
| The whole system end-to-end | [entry file] → [next file] → [next file] |
| How components discover each other | [protocol doc] → [implementation dir] → [example config] |
| The [core loop / tick / pipeline] | [agent/service file] → [callback file] → [output file] |
| How [feature X] works | [design doc] → [implementation file] → [test file] |
| Deployment and infra | [infra README] → [terraform/docker dir] → [Dockerfile] |
| Tests and how they run offline | [testing guide] → [conftest / test config] |

## High-Level Topology

[Mermaid diagram — 5-8 nodes max, show the data flow not the file tree]

[3-5 bullet summary of layers]

## Patterns Worth Understanding

### 1. [Pattern Name]

**What:** [One sentence]
**Why:** [The non-obvious reason this design was chosen]
**Where:** [file:line or directory pointer]

### 2. [Pattern Name]
...

## Common Gotchas

- [Gotcha]: [How to avoid it / file:line where it matters]
- [Gotcha]: [How to avoid it / file:line where it matters]
```

**When to use this type:** when the skill's primary trigger is "explain", "how does", "orient me", "give me a tour", "understand the system", "architecture of", or "before I change X I want to understand Y".

## Checklist for Reviewing a Skill You've Written

```
[] Iron Law appears first?
[] Description includes all trigger words (under-trigger test passes)?
[] Name+description match https://agentskills.io/specification?
[] allowed-tools listed and minimal?
[] Body <=500 lines?
[] Deep content in references/, not inline?
[] No README.md / CHANGELOG.md in directory?
[] Cross-references use "see X" pattern, no duplicate content?
[] Decision trees where prose would be verbose?
```
