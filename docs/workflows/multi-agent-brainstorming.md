# Multi-Agent Brainstorming

> **When to use**: After `/brainstorm` produces a preferred design option and before `/plan-review` locks the plan — for high-stakes, irreversible, or cross-service decisions
> **Time estimate**: 30–60 min for a typical feature design; longer for architecture decisions
> **Prerequisites**: An initial design or preferred option exists; brainstorming has already been done

## Overview

5-role sequential design review from the `multi-agent-brainstorming` skill. One agent designs; four constrained reviewers critique; one arbiter issues a binding verdict (APPROVED / REVISE / REJECT). Produces a Decision Log that persists to `docs/decisions/` as the record of why a design was accepted or rejected.

Fills the gap between exploring options (`/brainstorm`) and locking an implementation plan (`/plan-review`).

---

## Iron Law (from `skills/multi-agent-brainstorming/SKILL.md`)

> **NO IMPLEMENTATION UNTIL ARBITER DECLARES APPROVED — a design not reviewed by all 5 roles may proceed to brainstorming but NEVER to code**

---

## When to Use vs. When Not To

| Use This Workflow | Skip This Workflow |
|-------------------|-------------------|
| Irreversible decisions (schema migration, public API contract, auth architecture) | Simple bug fixes or small isolated changes |
| Major feature design touching multiple services | Changes to a single file with no shared contracts |
| Architecture decisions affecting Flutter + Firebase + backend | Well-understood changes following established patterns |
| After `the-fool` returns concerns that need deeper resolution | When `the-fool` single-agent critique was sufficient |
| High-stakes decisions where "looks right" is not enough | Prototypes or experiments that will be thrown away |

---

## Phase 1 — Load Skill and Start Decision Log

**Skill**: Load `multi-agent-brainstorming`

```
Load multi-agent-brainstorming skill
```

Start the Decision Log immediately — before any review:

```
Load references/decision-log-template.md
Create Decision Log at: docs/decisions/YYYY-MM-DD-<feature-name>.md
```

---

## Phase 2 — Understanding Lock (Primary Designer)

Before any reviewer is invoked, the Primary Designer must complete the Understanding Lock:

```markdown
## Understanding Lock

Goal: [What are we building and why?]

Constraints:
- Technical: [e.g., must fit within existing NestJS monolith — no new services]
- Resource: [e.g., no Kafka; only PostgreSQL + Redis available]
- Time: [e.g., must deploy by YYYY-MM-DD]

Assumptions:
- [e.g., "User auth is handled upstream; this service receives a validated JWT"]
- [e.g., "Peak load < 500 RPS for the first 6 months"]
```

**Gate:** Do NOT invoke any reviewer until Understanding Lock is confirmed.

---

## Phase 3 — Sequential Review

Reviewers are invoked **one at a time** in this fixed order. Each reviewer must complete before the next starts.

### Step 3a — Skeptic / Challenger

```
Activate Skeptic role (see references/agent-role-scripts.md for full prompting guidance):
"I am now acting as the Skeptic. Assume this design fails in production. Why?"

Focus: assumptions, edge cases, production failure modes, YAGNI violations
Output: 3-5 specific objections — not design proposals
```

Primary Designer responds to each objection and updates the Decision Log.

---

### Step 3b — Constraint Guardian

```
Activate Constraint Guardian role:
"I am now acting as the Constraint Guardian. I enforce non-functional requirements."

Focus (this workspace):
- NestJS + Prisma: connection pools, N+1 queries, transaction scope
- Spring WebFlux: blocking calls in reactive chains, backpressure
- Flutter + Firebase: Firestore read/write cost, offline conflict
- PostgreSQL: index coverage, migration reversibility
- LangGraph: token budget, loop termination, context degradation
```

Primary Designer responds and updates Decision Log.

---

### Step 3c — User Advocate

```
Activate User Advocate role:
"I am now acting as the User Advocate. I represent the end user."

Focus: confusing flows, missing error states, bad defaults, recovery gaps
```

Primary Designer responds and updates Decision Log.

---

## Phase 4 — Integration & Arbitration

**Before starting Phase 4:** Run the exit criteria checklist from `references/exit-criteria-checklist.md`. All boxes must be checked.

```
Activate Integrator / Arbiter role:
"I am now acting as the Integrator / Arbiter. I review the Decision Log
and all objections. I will issue a binding verdict."

Arbiter reviews:
1. Final design (post-revisions)
2. Completed Decision Log
3. All unresolved objections

Arbiter output:
- Which objections are accepted (design must change) vs rejected (with rationale)
- Final verdict: APPROVED | REVISE | REJECT
- Next step
```

---

## Phase 5 — Post-Verdict Routing

| Verdict | Action |
|---------|--------|
| **APPROVED** | Proceed to `/plan-review` — the design is validated, lock the implementation plan |
| **REVISE** | Make required changes, re-invoke only the relevant reviewer(s), re-run arbitration |
| **REJECT** | Return to `/brainstorm` — design has fundamental flaw; preserve Decision Log as context for next pass |

Save the Decision Log to `docs/decisions/YYYY-MM-DD-<feature-name>.md` regardless of verdict.

---

## Quick Reference

| Phase | Role | Input | Output |
|-------|------|-------|--------|
| 1 | Setup | New design | Skill loaded, Decision Log started |
| 2 | Primary Designer | Design brief | Understanding Lock + initial design |
| 3a | Skeptic | Initial design | 3-5 failure scenario objections |
| 3b | Constraint Guardian | Design + Skeptic revisions | NFR violations |
| 3c | User Advocate | Design + all revisions | UX gap objections |
| 4 | Arbiter | Final design + Decision Log | APPROVED / REVISE / REJECT |
| 5 | Routing | Verdict | Next step |

---

## Common Pitfalls

- **Reviewers proposing features** — Hard limit: reviewers critique only; no new features allowed
- **Skipping a reviewer** — Iron Law violation; proceed anyway = no validation
- **Incomplete Decision Log** — Arbiter cannot give valid verdict without full log
- **Re-entering after REJECT without fresh design** — REJECT means start over, not patch the same design
- **Using this for low-stakes changes** — Overhead is real; use `the-fool` for lighter-weight critique

---

## Related Workflows

- [`/brainstorm`](../../.claude/commands/brainstorm.md) — explore options BEFORE running this workflow (input)
- [`plan-review.md`](plan-review.md) — lock implementation plan AFTER APPROVED verdict (output)
- [`architecture-design.md`](architecture-design.md) — generates the C4/sequence diagrams this workflow validates
- [`subagent-driven-development.md`](subagent-driven-development.md) — implements the validated plan
