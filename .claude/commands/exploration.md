---
description: CTO Challenge Mode — adversarial convergent stress-test of a specific proposed solution before committing to it. Use when you have a plan and want it challenged. NOT for divergent exploration (use /brainstorm for that).
allowed-tools: Read, Grep, Glob
---

# /exploration — CTO Challenge Mode

## Purpose

Before writing a single line of code, play devil's advocate against the proposed solution.
This is NOT brainstorming (divergent). This is adversarial convergence — stress-testing a
specific plan before committing to it.

**Core philosophy:** "5 minutes of questioning before coding beats 5 hours of fixing after."

**Difference from /brainstorm:**
- `/brainstorm` → divergent: generates ≥3 options when direction is unclear
- `/exploration` → convergent: challenges a specific proposed solution when direction is set

## When to Use

- About to implement a new feature or architectural change
- You have a specific approach in mind and want it challenged
- You feel "ready to start coding" but something feels uncertain
- The task touches >2 services, a schema change, or a new dependency

## NOT when to use

- Direction is genuinely unclear (use `/brainstorm` instead)
- A written multi-step implementation plan needs a phase-by-phase review (use `/plan-review` instead)
- Task is a trivial bug fix or <50 line change
- Implementation is already approved and underway

## Execution Steps

### Step 1: Understand the Proposed Solution
Ask the user to describe in 2-3 sentences:
- What they want to build
- The specific approach they have in mind

### Step 2: CTO Challenge Mode — 5 Adversarial Questions

From a tech lead perspective, ask ALL 5 before evaluating:

1. **Why this approach instead of [alternative]?**
   - For our stack: Is this the right layer (NestJS vs Spring vs FastAPI)?
   - Could a Firebase/Cloud Run managed service replace self-hosting this?
   - Is there an existing skill/pattern in `.claude/skills/` that already solves this?

2. **What are the boundary conditions?**
   - What happens at 0 records? At 1M records?
   - What happens if the external service (Firebase/Stripe/etc.) is down?
   - What's the behavior on concurrent writes (R2DBC/Prisma transactions)?

3. **What happens in the worst case?**
   - If this fails in production, what data is at risk?
   - Is there a rollback path? (Required by `first-principles.md` Layer 3)
   - Does failure fail loudly or silently? (code-standards.md: No Silent Failures)

4. **Is there a simpler way to achieve the same goal?**
   - Can existing shared utilities handle this? (DRY — code-standards.md)
   - Is a new service/file justified, or can this extend an existing one?
   - Would ≤200 lines solve it, or are we over-engineering?

5. **What tech debt does this introduce?**
   - Does this create a new abstraction that will need maintaining?
   - Does it add a dependency that hasn't been vetted?
   - Will the next developer understand this without comments?

### Step 3: Explore Existing Code
Before generating the verdict:
- Search for related patterns in the codebase (Grep/Glob)
- Identify files that will need to change
- Estimate change scope (files × lines)

### Step 4: Go/No-Go Verdict

```
## /exploration Verdict — [Feature/Change Name]

### Solution Under Review
[1-sentence description of what was proposed]

### CTO Challenge Results

| Dimension | Assessment | Evidence |
|-----------|-----------|---------|
| Approach justification | [Strong/Weak/Needs work] | [reason] |
| Boundary conditions | [Covered/Gap found] | [specific gap or "all covered"] |
| Worst-case handling | [Handled/Risk found] | [risk description or "handled"] |
| Simplicity | [Optimal/Can simplify] | [alternative if simpler exists] |
| Tech debt | [Acceptable/Concern] | [debt description] |

### Scope Estimate
- Files to change: [N]
- New files needed: [N]
- Estimated lines: [N]
- Services touched: [list]

### Recommendation
[ ] **GO** — Ready to implement. Load the relevant skill and proceed.
[ ] **HOLD** — Resolve [specific issue] before starting. Suggested: [action]
[ ] **NO-GO** — Recommend alternative: [describe alternative + reason]

### Next Step (if GO)
Load skill: [java-spring-api / nestjs-api / flutter-mobile / angular-spa / python-dev / agentic-ai-dev]
Then: [specific first action]
```

## Stack-Specific Challenge Prompts

When the proposed solution touches these layers, add these stack-specific questions:

| Stack | Additional Challenge |
|-------|---------------------|
| **Spring Boot / WebFlux** | "Is this reactive all the way down? Any blocking calls?" |
| **NestJS / Prisma** | "Is this inside a transaction? What's the rollback on partial failure?" |
| **Flutter / Riverpod** | "What's the loading/error state? Is the provider scoped correctly?" |
| **Angular** | "Is this a signal or observable? OnPush is the v22 default: is any `Eager` opt-out justified?" |
| **PostgreSQL** | "Does this need an index? Run EXPLAIN ANALYZE first." |
| **Firebase** | "Does this need a Firestore rule change? What's the read/write cost?" |

$ARGUMENTS
