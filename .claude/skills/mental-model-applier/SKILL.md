---
name: mental-model-applier
description: "Pick the three mental models that fit a specific problem and apply each to produce a concrete insight. Use when the user is stuck, asks for a framework or a different perspective. Not when they already named a framework (decision-frameworks)."
allowed-tools: Read
metadata:
  triggers: apply mental models, mental model, thinking framework, stuck on a problem, perspective shift, need a framework, different angle, been thinking about this too long, reframe this
  related-skills: the-fool, second-order-thinker, multi-agent-brainstorming
  domain: workflow
  role: expert
  scope: analysis
  output-format: report
last-reviewed: "2026-05-26"
---

## Iron Law

**NO GENERIC MODEL LISTS — select models based on fit to this specific problem; applying the wrong model confidently produces worse outcomes than no model at all**

# Mental Model Applier

Mental models are only useful when applied, not listed. The problem is not that people lack mental models — it is that they apply the same 2-3 familiar ones regardless of whether they fit. This skill selects the three models with the highest fit to the specific problem and applies each one to produce an insight the user was not seeing.

## When to Use This Skill

- You have been thinking about a problem from the same angle for too long
- A decision keeps feeling difficult despite having information
- You want a perspective shift, not more research
- You need to explain or reframe a situation to someone else
- You are about to act from habit rather than considered judgment

## Core Workflow

1. **Understand the problem** — Read the situation carefully. Identify: Is this a decision, a diagnosis, a design problem, a people problem, or a strategy problem? The problem type constrains which models are relevant.
2. **Select three models** — Choose from the model library (see `references/model-library.md`) based on fit to the specific situation. Do not default to popular models. Choose models that illuminate *this* problem.
3. **Apply each model** — Apply it specifically to the situation. "This model suggests you think about incentives" is not an application. Name the specific incentives, the specific constraints, the specific dynamic.
4. **Extract the dominant insight** — Synthesize across all three models. What does the combination reveal that no single model showed?
5. **State the action** — One concrete thing to do differently based on the analysis.

## Output Format

```
## Mental Model Analysis: [Problem / Decision]

### Model 1: [Model Name]
**What it says:** [One sentence — the core claim of this model]
**Applied here:** [How this model specifically maps to this situation. Specific, not general.]
**Insight produced:** [What this model reveals that was not visible before]

### Model 2: [Model Name]
**What it says:** [One sentence — the core claim of this model]
**Applied here:** [How this model specifically maps to this situation. Specific, not general.]
**Insight produced:** [What this model reveals that was not visible before]

### Model 3: [Model Name]
**What it says:** [One sentence — the core claim of this model]
**Applied here:** [How this model specifically maps to this situation. Specific, not general.]
**Insight produced:** [What this model reveals that was not visible before]

### The Dominant Insight
[One sentence. What emerges from the combination of all three models — not a repeat of any single model's insight.]

### The Action
[One sentence. What to do differently based on this analysis.]
```

## Model Selection Criteria

Choose models based on fit, not fame. Match the model to the problem type:

| Problem Type | Likely Useful Models |
|---|---|
| Decision under uncertainty | Expected value, Regret minimization, Reversibility |
| People / incentives | Principal-agent, Goodhart's Law, Game theory |
| Systems / feedback | Second-order thinking, Feedback loops, Unintended consequences |
| Strategy / competition | Competitive moats, Prisoner's dilemma, OODA loop |
| Diagnosis / root cause | Five Whys, Inversion, First principles |
| Design / complexity | Occam's Razor, Forcing function, Abstraction layers |
| Bias / judgment | Availability heuristic, Sunk cost, Overfitting |

When two models would produce the same insight, replace one with a model from a different domain — cross-domain application surfaces more.

## Rules

- The application section must name specific elements of the user's situation, not generic advice.
- The three models must come from at least two different domains (e.g. not three psychology models for a strategy problem).
- The dominant insight must emerge from the *combination* — if it is just a repeat of one model, the synthesis failed.
- The action must be concrete enough that the user knows what to do next session, not just in principle.
- If the problem is underspecified, ask one clarifying question before selecting models. Do not apply models to a vague statement.

## Common Failure Modes to Avoid

| Failure | What to Do Instead |
|---------|-------------------|
| Applying the three most famous models (first principles, Occam's Razor, inversion) regardless of fit | Match model to problem type using the selection criteria above |
| Describing a model without applying it ("Inversion says to think backwards…") | Apply it: "Inverting this: instead of asking how to grow users, ask what would cause us to lose every user we have, then eliminate those causes") |
| Dominant insight that repeats one model's output | Synthesize — the dominant insight must require all three models to produce |
| Action that is vague ("think more carefully about incentives") | Action must be specific ("restructure the contractor payment to be output-based, not time-based") |

## Deep Reference

Load `references/model-library.md` when you need the full model catalog with definitions, use cases, and application patterns.

## Related

> For adversarially stress-testing a conclusion after applying models: use `the-fool` skill.
> For mapping downstream consequences of an action: use `second-order-thinker` skill.
> For validating a design decision with structured peer review: use `multi-agent-brainstorming` skill.
