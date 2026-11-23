---
name: second-order-thinker
description: "Map first-, second- and third-order consequences of a decision, action or trend. Use when asked about ripple, downstream or knock-on effects before a significant decision. Not for challenging a plan's assumptions (the-fool)."
allowed-tools: Read
metadata:
  triggers: second order effects, map consequences, think ahead, downstream effects, systems thinking, ripple effects, what happens after, analyze this decision, consequence mapping
  related-skills: the-fool, multi-agent-brainstorming, architecture-decision-records
  domain: workflow
  role: expert
  scope: analysis
  output-format: report
last-reviewed: "2026-05-26"
---

## Iron Law

**NO ANALYSIS THAT STOPS AT FIRST ORDER — first order effects are what everyone sees; the analysis only earns its value at second and third order**

# Second Order Thinker

Most decisions are made on first order thinking: action A causes obvious result B. This is where most people stop. Second order thinking asks what happens after B. Third order asks what happens after that. The consequences that bite hardest are almost always second or third order — by which point they feel like bad luck rather than predictable outcomes.

## When to Use This Skill

- Before any decision with a time horizon beyond 30 days
- When analyzing a trend that others are treating as a simple story
- When evaluating a policy, product feature, or architectural change with broad reach
- When a decision affects more than one team, system, or stakeholder group
- When something "obviously good" deserves more scrutiny before committing

## Core Workflow

1. **Restate** — Confirm the decision, action, or trend being analyzed. One sentence. Ask for clarification if the scope is ambiguous.
2. **Map first order** — Identify the immediate, obvious consequences. These are not the interesting ones.
3. **Map second order** — For each first order effect, ask: "And then what?" These are where unintended consequences live.
4. **Map third order** — For the most significant second order effects, ask: "And then what?" This is where unpredictability begins.
5. **Identify the unintended consequence** — The one outcome nobody is planning for that is most likely to emerge.
6. **Name the feedback loop** — The dynamic where an effect circles back and amplifies or undermines the original decision.

## Output Format

```
## Second Order Analysis: [Decision / Action / Trend]

### First Order Effects (immediate, obvious)
- [Effect 1]
- [Effect 2]
- [Effect 3]

### Second Order Effects (consequences of the above)
- [Effect 1 — traces back to which first order effect]
- [Effect 2 — traces back to which first order effect]
- [Effect 3 — traces back to which first order effect]

### Third Order Effects (where it gets unpredictable)
- [Effect 1 — traces back to which second order effect]
- [Effect 2 — traces back to which second order effect]

### The Unintended Consequence
[One sentence. Specific. The outcome nobody is planning for that is most likely to emerge.]

### The Feedback Loop
[One sentence. The dynamic where an effect circles back and amplifies or undermines the original decision. This is the most strategically important output.]
```

## Rules

- First order effects are not the point. State them briefly and move on.
- Every second and third order effect must trace back to a prior effect — not appear from nowhere.
- The unintended consequence must be specific. "There could be unforeseen effects" is not analysis.
- The feedback loop is the highest-value output. It is where a decision becomes self-reinforcing or self-undermining. Identify it carefully.
- If the decision has multiple actors (e.g. competitors, regulators, users), model their responses as second order effects — they will adapt to first order outcomes.
- When the third order effects become genuinely unpredictable, say so explicitly rather than inventing false precision.

## Common Failure Modes to Avoid

| Failure | What to Do Instead |
|---------|-------------------|
| Listing only negative consequences | Model both amplifying and undermining effects |
| Vague second order effects ("it could cause problems") | Name the specific mechanism and who is affected |
| Stopping at first order and calling it analysis | Always surface at least 3 second order effects |
| Treating the feedback loop as optional | It is mandatory — every significant decision has one |
| Confusing second order with "bad things that might happen" | Second order = the effect of an effect, positive or negative |

## Worked Example Structure

For "Introduce a free tier to a paid SaaS product":

- **First order:** More signups, lower ARPU, increased infrastructure load
- **Second order:** Free users generate word-of-mouth (from signups) → Paid conversion pressure increases as free tier matures (from lower ARPU) → Support costs rise disproportionately (from infrastructure + free users)
- **Third order:** Enterprise prospects perceive product as commodity (from word-of-mouth positioning) → Competitors match free tier, eliminating the acquisition advantage
- **Unintended:** The free tier attracts a user segment that is structurally unable to convert, anchoring the product's reputation in a market it cannot monetize.
- **Feedback loop:** Free tier growth generates social proof → social proof attracts more free users → each free user raises the support-to-revenue ratio → the ratio increase pressures the team to restrict the free tier → restriction reduces social proof.

## Related

> For adversarially challenging a decision before it is made: use `the-fool` skill.
> For validating a system design with structured peer review: use `multi-agent-brainstorming` skill.
> For recording the decision and its rationale after analysis: use `architecture-decision-records` skill.
