---
name: ai-decision-record
description: Fill out the AI Feature Decision Record before building any AI feature. Use when the user explicitly runs /ai-decision-record or asks to "start a new AI feature", "create a decision record", "kick off an AI design", or similar ritual phrasing.
disable-model-invocation: true
allowed-tools: Read, Write
last-reviewed: 2026-11-22
metadata:
  triggers: AI decision record, AI feature design doc, should we build this AI feature, AI risk tier
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, ai-audit
---

# AI Feature Decision Record

## Iron Law

**Do not proceed to implementation without a completed Decision Record written to `docs/ai-decisions/<feature-slug>.md`. It is a required artifact — not optional documentation.**

Walk the user through filling out the Decision Record from the AI Playbook (Layer 3 §3.3). This is a required artifact before building any AI feature.

## Procedure

1. Confirm the user is starting a new AI feature, not modifying an existing one. If modifying: load the existing Decision Record and update it; do not start fresh.
2. Ask the questions below **one at a time**. Do not skip ahead.
3. For each answer, validate it against the playbook's principles. Push back when:
   - The answer suggests AI is being added where deterministic code would work better (cross-check Layer 1 §1.6 Red Flag Matrix).
   - The risk tier proposed is lower than the blast radius justifies (cross-check Layer 2 §2.2 Autonomy Ladder).
   - The pattern (assistant / workflow / agent / autonomous) is more complex than needed (apply Layer 1 §1.4: start one tier below where you think you need to be).
   - No fallback is named.
   - No named human owner.
4. After all questions are answered, write the Decision Record to `docs/ai-decisions/<feature-slug>.md` in the repo (create the directory if needed).
5. Output a summary of the **three biggest risks** in the Decision Record and recommend whether to proceed, scope down, or rethink.

## The questions

Ask these in order. Do not batch them. Wait for an answer before moving on.

1. **What is the user problem this AI feature solves?** (Not "what AI tech we're using" — what the user gets out of it.)
2. **Why is deterministic code insufficient?** (If you can't answer this in one sentence, the answer might be "it's not.")
3. **Why is AI the right tool here?** (Pattern recognition, ambiguity, ranking, summarization, etc. Map to Layer 1 §1.5 Green Light Matrix.)
4. **What pattern fits: assistant, workflow, agent, or autonomous?** (Default to the lower tier. Most "agent" problems are workflows.)
5. **What is the risk tier (0–5)?** (Reference Layer 2 §2.2 Autonomy Ladder. Sum blast radius across a session, not per action.) **Which steps stay deterministic** (authorization, state transitions, final decisions) and which are AI (interpretation, ranking, drafting)? **Which tools can it call, at what authority** (read · draft · controlled write · high-consequence write), and which need approval? Adding a write tool later re-opens this record.
6. **What is the fallback when AI fails?** (Timeout, provider outage, low confidence, schema violation → what happens? A specific deterministic path.)
7. **What is the primary eval metric and target value?**
8. **How large is the eval set and where does it come from?** (Default floor is 100; check Layer 2 §2.14 for risk-tiered minimums.)
9. **What gets human review? Who reviews it? What's the SLA?** (Reference Layer 2 §2.1 default SLA table.)
10. **What is the cost ceiling per task, and what are the per-run budgets** (model calls, tool calls, tokens, wall-clock), shared across sub-agents, retries and fallbacks? (Reference Layer 2 §2.6, §2.10.)
11. **What is the p95 latency target?**
12. **Which model? Smallest viable, or routing strategy with fallback?** (Reference Layer 2 §2.9.)
13. **Has a security review covered prompt injection, tool-output injection, exfiltration, and tenant isolation?** (Reference Layer 2 §2.5.)
14. **Has a data governance review covered: what enters context, what's logged, retention, training-use, tenant isolation, deletion propagation?** Which data classes may be sent to which approved providers/regions, and which are blocked before the call? (Reference Layer 2 §2.13.)
15. **Where is the kill switch / feature flag? Has it been tested?** (Reference Layer 4 §4.4.)
16. **What is the rollback plan?**
17. **What is the 12-month AI tax estimate?** (Model spend + evals + review queue + observability + drift fighting + security + compliance + on-call. Reference Layer 2 §2.11.)
18. **Who is the named human owner — not a team, a person — accountable for the eval metric?**

## Output format

```md
# Decision Record: <Feature Name>

**Status**: Draft | Approved | Shipped | Deprecated
**Owner**: <Named Person>
**Last updated**: <Date>

## Problem & justification
- User problem: ...
- Why deterministic code is insufficient: ...
- Why AI is the right tool: ...

## Design
- Pattern: <assistant | workflow | agent | autonomous>
- Risk tier: <0-5>
- Deterministic steps vs AI steps: ...
- Tools and authority tier (approval required for): ...
- Model and routing (pinned versions; fallback only on transient errors, to approved providers): ...
- Fallback when AI fails: ...

## Evaluation
- Primary metric: ... (target: ...)
- Eval set size & source: ...

## Operating envelope
- Cost ceiling per task: $... ; per-run budgets: <calls / tool calls / tokens / deadline>
- p95 latency target: ...
- Human review: <what / who / SLA>

## Reviews
- Security review: <date, reviewer, link to adversarial test results>
- Data governance review: <date, reviewer>; allowed/prohibited data classes per provider: ...

## Operations
- Kill switch location: ...
- Rollback plan: ...
- 12-month AI tax estimate: $...

## Risks (top 3)
1. ...
2. ...
3. ...
```

## After completion

Recommend the next step:
- **Proceed**: ship the Implementation Minimum (Layer 2 §2.3), then run `/ai-launch-check` before going to production.
- **Scope down**: list specific items to defer or remove.
- **Rethink**: list the questions whose answers indicate AI is the wrong tool here.

## If this skill cannot proceed

```
Abort condition: user cannot answer Q2 ("Why is deterministic code insufficient?")
→ Stop. Output: "If you can't answer this in one sentence, AI may be the wrong tool.
  Re-evaluate with /ai-playbook before creating a Decision Record."

Abort condition: risk tier proposed is Tier 3+ but no named human owner for Q18
→ Hard stop on that question. Do not write the Decision Record without a named owner.
  Output: "Tier 3+ features require a named human owner. A team is not an owner."

Abort condition: modifying an existing feature, existing Decision Record not found
→ Output: "No Decision Record found at docs/ai-decisions/<feature-slug>.md.
  Either the slug is wrong or this feature was built without one. Run /ai-audit to reverse-engineer it."
```

## Verify

After writing the Decision Record:

```
✅ Verify: docs/ai-decisions/<feature-slug>.md exists and is non-empty
✅ Verify: all 18 questions have answers (no blank fields)
✅ Verify: risk tier matches blast-radius described in the answers
✅ Verify: owner is a named person, not "the team" or "engineering"
```

## References

- AI Playbook Layer 1 §1.6 Red Flag Matrix: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 2 §2.2 Autonomy Ladder: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 2 §2.14 Eval sizing: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 4 §4.4 Kill switch: `.claude/skills/ai-playbook/playbook.md`
- Next step after Decision Record: `/ai-launch-check`
