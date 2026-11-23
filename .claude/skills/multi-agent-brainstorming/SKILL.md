---
name: multi-agent-brainstorming
description: "Structured design peer review with five constrained sequential roles that surface assumptions and failure modes, producing a Decision Log and APPROVED / REVISE / REJECT verdict. Use to validate a design before implementation. Not for open-ended option generation (/brainstorm)."
allowed-tools: Read, Write, Glob, Grep
metadata:
  triggers: validate design, design review, stress test design, challenge design, pre-implementation review, adversarial design review, design validation, review before build
  related-skills: the-fool, plan-mode-review, brainstorm, feature-forge, architecture-design
  domain: workflow
  role: architect
  scope: review
  output-format: decision-log
last-reviewed: "2026-03-15"
---

## Iron Law

**NO IMPLEMENTATION UNTIL ARBITER DECLARES APPROVED — a design not reviewed by all 5 roles may proceed to brainstorming but NEVER to code**

**Explanation:** Single-agent designs have blind spots. Without adversarial validation, hidden assumptions become production failures. The 5-role review exists specifically to find these before a line is written.

# Multi-Agent Brainstorming (Structured Design Review)

Transform a single-agent design into a **review-validated design** by simulating a formal peer-review process using 5 constrained agent roles invoked sequentially.

This is **not** parallel brainstorming. It is **sequential design review with enforced scope limits**.

---

## When to Use

- Validating a system architecture before committing to implementation
- Stress-testing a major feature design (multi-service, schema change, auth flow)
- Reviewing any irreversible decision (public API contract, DB migration, auth architecture)
- After `/brainstorm` produces a preferred option — before `/plan-review` locks the plan
- When `the-fool` single-agent critique is not sufficient for high-stakes decisions

**Relationship to other skills:**

| Skill | When |
|-------|------|
| `/brainstorm` | Generate options (no validation) — runs BEFORE this skill |
| `the-fool` | Single-agent adversarial critique — lighter-weight alternative for low-stakes decisions |
| `multi-agent-brainstorming` | 5-role structured review — use for high-stakes or irreversible decisions |
| `plan-mode-review` | Validates the approved plan — runs AFTER this skill |

---

## Operating Model

- One agent designs.
- Other agents review.
- No agent may exceed its mandate.
- Creativity is centralized; critique is distributed.
- Decisions are explicit and logged.

The process is **gated** and **terminates by design**.

---

## Agent Roles (Non-Negotiable)

Each role operates under a **hard scope limit**. Load `references/agent-role-scripts.md` for detailed prompting guidance per role.

| Role | Job | May | May NOT |
|------|-----|-----|---------|
| **Primary Designer** | Owns the design, runs `/brainstorm`, maintains Decision Log | Ask clarifications, propose designs, revise based on feedback | Self-approve, ignore objections, invent requirements post-lock |
| **Skeptic / Challenger** | Assumes the design fails — finds weaknesses | Question assumptions, flag edge cases, highlight YAGNI violations | Propose new features, redesign the system |
| **Constraint Guardian** | Enforces NFRs (performance, scalability, security, cost, maintainability) | Reject designs violating constraints, request clarification of limits | Debate product goals, suggest feature changes |
| **User Advocate** | Represents the end user — cognitive load, clarity, error handling | Identify confusing flows, flag poor defaults | Redesign architecture, add features |
| **Integrator / Arbiter** | Resolves conflicts, finalizes decisions, enforces exit criteria | Accept/reject objections, require revisions, declare the design complete | Invent new ideas, add requirements, reopen locked decisions without cause |

---

## Process

### Phase 1 — Single-Agent Design

1. Primary Designer runs `/brainstorm` or defines the initial design independently
2. Understanding Lock is completed and confirmed (restate goal, constraints, and assumptions)
3. Initial design is produced
4. Decision Log is started (load `references/decision-log-template.md`)

**No other roles participate in Phase 1.**

---

### Phase 2 — Structured Review Loop

Roles are invoked **one at a time**, in this order:

1. **Skeptic / Challenger**
2. **Constraint Guardian**
3. **User Advocate**

For each reviewer:
- Feedback must be explicit and scoped to the role's mandate
- Objections must reference specific assumptions or decisions
- No new features may be introduced

Primary Designer must respond to each objection, revise if required, and update the Decision Log.

---

### Phase 3 — Integration & Arbitration

Integrator / Arbiter reviews:
- The final design
- The completed Decision Log
- Any unresolved objections

The Arbiter must explicitly decide which objections are accepted (with revisions) and which are rejected (with rationale).

**Final verdict must be one of: `APPROVED` | `REVISE` | `REJECT`**

---

## Exit Criteria (Hard Stop)

You may exit only when **all** of these are true:

- [ ] Understanding Lock was completed
- [ ] All 3 reviewer roles have been invoked (Skeptic, Constraint Guardian, User Advocate)
- [ ] All objections are resolved or explicitly rejected with rationale
- [ ] Decision Log is complete
- [ ] Arbiter has declared `APPROVED`, `REVISE`, or `REJECT`

If any criterion is unmet — continue review. Do NOT proceed to implementation.

---

## Reference Files

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Role prompts and scope enforcement | `references/agent-role-scripts.md` | At the start of Phase 2 — before invoking any reviewer |
| Decision Log template | `references/decision-log-template.md` | At the start of Phase 1 — when design starts |
| Exit criteria checklist | `references/exit-criteria-checklist.md` | Before Phase 3 arbitration to verify readiness |

---

## Constraints

### MUST DO
- Run Phase 1 fully before invoking any reviewer
- Invoke reviewers in order: Skeptic → Constraint Guardian → User Advocate
- Log every objection and its resolution in the Decision Log
- Produce a final Arbiter verdict before reporting done

### MUST NOT DO
- Allow reviewers to introduce new features or redesign the system
- Skip any reviewer role, even if the design seems solid
- Declare the design approved without completing the Decision Log
- Proceed to implementation on `REVISE` or `REJECT` verdict

---

## Output Format

```
## Design Review: [design name]

### Understanding Lock
- Goal: [what we're building]
- Constraints: [technical, resource, time]
- Assumptions: [what we're taking for granted]

### Initial Design
[Description + diagram if applicable]

### Skeptic Review
**Objections raised:**
- [objection 1]
**Resolution:** [how it was addressed]

### Constraint Guardian Review
**Objections raised:**
- [objection 1]
**Resolution:** [how it was addressed]

### User Advocate Review
**Objections raised:**
- [objection 1]
**Resolution:** [how it was addressed]

### Decision Log
[Summary of all decisions, alternatives considered, and rationale]

### Arbiter Verdict
**APPROVED / REVISE / REJECT**
**Rationale:** [one paragraph]
**Next step:** [proceed to /plan-review | revise design and re-review | abandon]
```

---

## Failure Modes This Skill Prevents

- Idea swarm chaos (reviewers proposing new features instead of critiquing)
- Hallucinated consensus (agreeing without adversarial challenge)
- Overconfident single-agent designs (no external critique)
- Hidden assumptions running unchecked into implementation
- Premature implementation (building before validation)
- Endless debate (hard exit criteria force resolution)

---

## Knowledge Reference

Pre-mortem analysis, red-team adversarial review, structured debate, adversarial collaboration, design review, decision log, consensus mechanisms, YAGNI, non-functional requirements
