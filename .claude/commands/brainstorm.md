---
name: brainstorm
description: Divergent exploration mode — generates 3+ alternatives with trade-offs and Mermaid diagrams before any code is written. Use when planning features, exploring architecture options, or deciding between approaches.
allowed-tools: Read, AskUserQuestion
---

# Brainstorm

Divergent exploration before committing to an approach. No code yet — only ideas, trade-offs, and diagrams.

## Input

`$ARGUMENTS` — the topic, feature, or decision to explore (e.g. "real-time notifications for NestJS", "auth strategy", "database for user sessions")

If `$ARGUMENTS` is empty, ask: "What do you want to explore?"

## Process

1. **Load `feature-forge` skill** for requirements context if the topic is a new feature
2. **Ask one clarifying question** if the topic is ambiguous — only one, not a questionnaire
3. **Generate ≥ 3 distinct options** — not variations of the same idea
4. **For each option**, produce the structured block below
5. **Draw a Mermaid diagram** for the option that best illustrates the architecture or data flow
6. **End with an open question** — do not pick a winner unless asked

## Output Format

```
## Exploring: [topic]

### Option A: [Name]
**What it is:** [one sentence]
✅ Pros: [2–4 bullets]
❌ Cons: [2–4 bullets]
⚠️  Watch out for: [biggest risk or gotcha]

### Option B: [Name]
...

### Option C: [Name]
...

---

### Diagram — [Option that benefits most from visualization]

[Mermaid block]

---

What resonates? Or should we explore a different direction?
```

## Rules

- **No code** — this mode is for deciding, not building
- **No recommendation** unless the user explicitly asks "which would you choose?"
- Minimum 3 options — if you can only think of 2, add a "hybrid" or "unconventional" option
- Each option must be genuinely distinct (different trade-off profile, not just different library names)
- If the topic maps to an existing skill (e.g. database design → `database-schema-designer`, architecture → `architecture-design`), note that skill at the end as the next step

## Example

```
/brainstorm real-time notifications for NestJS
```

Produces: WebSockets vs SSE vs Firebase vs Polling — with trade-offs on scaling, complexity, mobile support, and a Mermaid diagram of the SSE flow.

Use instead when: `/exploration` — you already picked an option and want it attacked; `/plan-review` — a written implementation plan needs a structured review; `/design-architecture` — the choice is made and needs an ADR.

$ARGUMENTS
