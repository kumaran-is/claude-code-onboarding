---
name: titan-methodology
description: "Dual-lens product evaluation and scoring for build/no-build decisions and feature ideas. Use when evaluating product ideas or prioritising an MVP."
metadata:
  triggers: should we build this, evaluate feature idea, product direction, prioritize ideas, Titan scoring, build or not
allowed-tools: Read
---

# Titan Methodology

Dual-lens product evaluation framework. Use when deciding whether to build something, evaluating feature ideas, or brainstorming product direction.

## Iron Law

Score every idea through both lenses with the written criteria before recommending build, refine or kill. Never decide from one lens or from enthusiasm alone.

## When to Use

- Evaluating a new feature or product idea before committing to build
- Comparing multiple approaches during brainstorm sessions
- Prioritizing a backlog of feature requests
- Deciding whether to pivot, refine, or kill an idea

## Elon's Lens — "The 10x Thinker"

Core question: "What are the fundamental truths, and can we 10x improve this?"

| # | Criterion | Weight | What to Evaluate |
|---|-----------|--------|------------------|
| 1 | Problem Magnitude | 25% | How severe is the pain? How many people affected? |
| 2 | 10x Potential | 25% | Is this 10x faster, cheaper, simpler, or better? |
| 3 | Technical Feasibility | 20% | Can this be built with current tech? Any blockers? |
| 4 | Execution Speed | 15% | Can an MVP ship in weeks, not months? |
| 5 | Scalability | 15% | Does this grow with users? Network effects? |

**Elon's Score** = weighted average of all 5 criteria (each scored /10)

Style: Direct, no sugar-coating, questions assumptions, uses specific numbers.

---

## Jobs' Lens — "The Taste Maker"

Core question: "How does this make users FEEL? Is this insanely great?"

| # | Criterion | Weight | What to Evaluate |
|---|-----------|--------|------------------|
| 1 | User Delight | 30% | Does this spark joy? Would users tell friends? |
| 2 | Simplicity | 25% | Can a first-time user succeed without instructions? |
| 3 | Design Quality | 20% | Typography, color, spacing — does it feel premium? |
| 4 | Emotional Connection | 15% | Does the product tell a coherent story? |
| 5 | Market Positioning | 10% | Would this stand out in the App Store / market? |

**Steve's Score** = weighted average of all 5 criteria (each scored /10)

Style: Passionate about details, references art and craft, uses metaphors.

---

## Combined Scoring

```
Combined Score = (Elon's Score × 0.5) + (Steve's Score × 0.5)
```

| Score | Verdict | Action |
|-------|---------|--------|
| 9.0 - 10.0 | EXCEPTIONAL | Fast-track — build immediately |
| 8.0 - 8.9 | BUILD IT | Strong — proceed with confidence |
| 7.0 - 7.9 | REFINE IT | Promising — address weaknesses first |
| 6.0 - 6.9 | UNCERTAIN | Needs significant iteration |
| < 6.0 | RETHINK | Pass or pivot — fundamentals are weak |

## Disagreement Resolution

When Elon and Steve scores differ by > 2 points:

- **Elon scores higher:** Technical strength but UX weakness. Steve leads redesign of the experience.
- **Steve scores higher:** Beautiful but impractical. Validate technical feasibility before proceeding.
- **Both score < 7.0:** Consider pivoting or passing entirely.

## Output Format

Present results as:

```
## Titan Evaluation: [Idea Name]

### Elon's Score: X.X/10
- Problem Magnitude (25%): X/10 — [one line]
- 10x Potential (25%): X/10 — [one line]
- Technical Feasibility (20%): X/10 — [one line]
- Execution Speed (15%): X/10 — [one line]
- Scalability (15%): X/10 — [one line]

### Steve's Score: X.X/10
- User Delight (30%): X/10 — [one line]
- Simplicity (25%): X/10 — [one line]
- Design Quality (20%): X/10 — [one line]
- Emotional Connection (15%): X/10 — [one line]
- Market Positioning (10%): X/10 — [one line]

### Combined: X.X/10 — [VERDICT]
### Key Tension: [Where Elon and Steve disagree, if applicable]
### Recommendation: [One paragraph — build, refine, or rethink]
```
