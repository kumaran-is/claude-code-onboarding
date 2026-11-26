---
name: brainstorm
description: Optional divergent exploration — playback of intent, Socratic questions when ambiguous, then 3+ alternatives with trade-offs. Use when planning features or deciding between approaches. Never a gate on approved work.
allowed-tools: Read, AskUserQuestion
---

# Brainstorm

Optional, on-demand exploration. **Never** required before `/next`, SDD, or implementation. It never blocks an already specified or approved issue. This is not `/startup-design` and not a feature-spec workflow. No extra design approval gate.

## Input

`$ARGUMENTS` — the topic, feature, or decision to explore (e.g. "real-time notifications for NestJS", "auth strategy", "database for user sessions")

If `$ARGUMENTS` is empty, ask: "What do you want to explore?"

## Process

1. **Playback** (2–4 sentences) — restate the user's intent, the underlying problem, and the desired outcome. Wait only if the playback is likely wrong.
2. **Assumptions and constraints** — list what you are treating as given vs unknown. Do not invent product names or stack pins the repo does not use.
3. **Socratic questions** — if a meaningful ambiguity remains, ask at most three focused questions (one round). Skip when the request is already specified or an approved plan/issue exists.
4. Load `feature-forge` only when the topic is a **new** feature with no spec; skip when a plan or issue already exists.
5. **Generate ≥ 3 distinct options** — not variations of the same idea. Preserve divergent behavior.
6. For each option: architecture / business / operational / implementation trade-offs.
7. Draw a Mermaid diagram for the option that best illustrates the architecture or data flow.
8. End with an open question. Do not pick a winner unless asked. Separate **confirmed**, **hypotheses**, and **recommendations**.

## Output Format

```
## Exploring: [topic]

### Playback
[Intent in 2–4 sentences. Problem. Desired outcome.]

### Assumptions and constraints
- Confirmed: …
- Hypothesis: …
- Constraint: …

### Option A: [Name]
**What it is:** [one sentence]
**Trade-offs:** architecture / business / operational / implementation
✅ Pros: [2–4 bullets]
❌ Cons: [2–4 bullets]
⚠️  Watch out for: [biggest risk or gotcha]

### Option B: [Name]
...

### Option C: [Name]
...

---

### Confirmed vs hypotheses vs recommendations
- Confirmed: [facts the user stated]
- Hypotheses: [unverified]
- Recommendations: [only if asked; otherwise omit]

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
- **Do not** block `/next`, SDD, or an approved plan. **Do not** duplicate `/startup-design` or `feature-forge` specs.

## Example

```
/brainstorm real-time notifications for NestJS
```

Produces: playback of the notification problem, assumptions, then WebSockets vs SSE vs Firebase vs Polling — with trade-offs on scaling, complexity, mobile support, and a Mermaid diagram of the SSE flow.

Use instead when: `/exploration` — you already picked an option and want it attacked; `/plan-review` — a written implementation plan needs a structured review; `/design-architecture` — the choice is made and needs an ADR; `/next --plan` — the issue is already specified.

$ARGUMENTS
