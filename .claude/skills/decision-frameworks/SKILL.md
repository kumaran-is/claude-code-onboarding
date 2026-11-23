---
name: decision-frameworks
description: "Apply ONE reasoning framework deeply and interactively to a decision: first principles, inversion, regret minimization or opportunity cost. Use when the user names one of these or asks \"help me think through\" / \"what am I giving up\". Not for picking frameworks (mental-model-applier), consequence chains (second-order-thinker) or attacking a plan (the-fool)."
allowed-tools: Read
metadata:
  triggers: first principles, inversion, regret minimization, opportunity cost, challenge my assumptions, think through this decision, work backwards, what am I giving up, what would I regret, break this down to fundamentals
  related-skills: the-fool, second-order-thinker, mental-model-applier
  domain: workflow
  role: expert
  scope: analysis
  output-format: report
last-reviewed: "2026-05-26"
---

## Iron Law

**NO GENERIC ADVICE — every framework must be applied to the specific situation the user describes; "consider your assumptions" is not an application; naming the actual assumptions is**

# Decision Frameworks

Four single-framework deep-dives for decisions, problems, and commitments. Each mode applies one reasoning framework interactively — asking follow-up questions, pushing for specificity, and refusing vague answers.

Use this skill when you want to go deep on one framework. Use `mental-model-applier` when you want three frameworks applied in parallel for a broader perspective shift.

## When to Use This Skill

- You are stuck on a specific problem and want to reason through it systematically
- A decision keeps feeling hard despite having information — you need a different lens
- You want to challenge your own assumptions before committing
- You are about to make an irreversible choice and want to stress-test it
- You need to make tradeoffs explicit rather than implicit

## The Four Modes

| Mode | Framework | Best For |
|------|-----------|----------|
| **First Principles** | Break to fundamental truths, rebuild | Overcoming convention, designing from scratch, "why do we do it this way?" |
| **Inversion** | Guarantee failure, then flip | Risk surfacing, strategy validation, pre-commitment checks |
| **Regret Minimization** | Decide from age 80 | Long-horizon personal or career decisions, emotional clarity |
| **Opportunity Cost** | Make tradeoffs visible | Commitments, resource allocation, "should I do this?" decisions |

## Mode Selection

Ask the user which framework to apply if they have not specified one. Present the four options with a one-line description. Use `AskUserQuestion` when interactive mode permits.

If the user's problem maps clearly to one mode, state which you are using and why before beginning.

## Core Workflow

1. **Read the problem** — Understand what is being decided or solved. If the description is vague, ask one clarifying question before proceeding.
2. **Select mode** — Match to the problem type using the table above, or ask.
3. **Load reference** — Read the corresponding reference file for the full method and output template.
4. **Apply interactively** — Do not produce a monologue. Ask follow-up questions. Push for specificity. Refuse vague answers.
5. **Produce structured output** — Use the output template from the reference file.
6. **Offer a second pass** — After completing one mode, offer to run a complementary framework.

## Reference Guide

| Mode | Reference File | Load When |
|------|---------------|-----------|
| First Principles | `references/first-principles.md` | User wants to break assumptions and rebuild |
| Inversion | `references/inversion.md` | User wants to work backwards from failure |
| Regret Minimization | `references/regret-minimization.md` | User faces a long-horizon personal or career decision |
| Opportunity Cost | `references/opportunity-cost.md` | User is evaluating a commitment or resource allocation |

## Constraints

### MUST DO
- Apply the framework specifically to the user's situation — name their actual assumptions, their actual tradeoffs, their actual failure modes
- Push back on vague answers: "poor execution" is not a failure mode; "the API migration slips 3 weeks because the external team has no SLA" is
- Ask follow-up questions rather than filling gaps with invention
- State which framework you are applying and why before starting
- End with a concrete output the user can act on — not just analysis

### MUST NOT DO
- Apply multiple frameworks simultaneously — this skill is for single-framework depth; use `mental-model-applier` for multi-model breadth
- Produce generic advice that would apply to any situation
- Accept "it depends" as a final answer — push for the specific version that applies here
- Skip the interactive element and produce a monologue

## Complementary Framework Pairings

After completing one mode, suggest a natural follow-on:

| Completed Mode | Natural Follow-On | Why |
|----------------|-------------------|-----|
| First Principles | Inversion | First Principles finds the right foundation; Inversion stress-tests it |
| Inversion | Second-Order Thinker | Inversion finds failure modes; Second-Order maps their downstream consequences |
| Regret Minimization | Opportunity Cost | Emotional clarity on direction + explicit tradeoffs of the chosen path |
| Opportunity Cost | First Principles | Tradeoffs made visible + assumptions challenged on why those options exist |

## Related

> For adversarially stress-testing any decision or plan: use `the-fool` skill.
> For applying three frameworks in parallel for perspective shift: use `mental-model-applier` skill.
> For mapping downstream consequences of a decision: use `second-order-thinker` skill.
