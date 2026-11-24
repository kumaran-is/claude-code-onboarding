---
name: plan-mode-review
description: Structured plan review with Phase 0 self-review, 5-phase code review (Architecture, Code Quality, Tests, Performance, Production Readiness), optional Phase 6 Debate-Based Verification for architecture decisions, approval scope triage, decision logging, and blast radius assessment. Use when reviewing plans, PRs, or preparing non-trivial changes for implementation.
allowed-tools: Read, Glob, Grep
metadata:
  triggers: plan review, review plan, technical plan, implementation plan, architectural plan, plan approval
  related-skills: architecture-decision-records, subagent-driven-development, verification-before-completion
  domain: workflow
  role: architect
  scope: review
  output-format: report
last-reviewed: "2026-03-14"
---

## Iron Law

**NO PLAN APPROVAL WITHOUT ALL 5 PHASES REVIEWED — Phase 0 self-review runs first; skipping any phase voids the review**

# Plan Mode Review

Structured review workflow for non-trivial changes. Covers planning discipline (Phase 0) and 5-phase technical review with severity triage, decision logging, and production readiness gates.

## Modes

Ask the user which mode to use:

| Mode | When | Phases |
|------|------|--------|
| **Big Change** | New features, architectural changes, multi-service work | Phase 0 + all 5 review sections (up to 4 issues each) + Phase 6 if architecture decision present |
| **Small Change** | Focused feature, single-service change | Phase 0 + top issue per section only |
| **Review Only** | PR review, existing code audit, refactor | Skip Phase 0 (lightweight outcome check only) + all 5 review sections |

## Reference Files

Load references as needed per phase:

| Phase | Reference File | Contents |
|-------|---------------|----------|
| Core | [reference/plan-mode-protocol.md](reference/plan-mode-protocol.md) | Approval scope triage, severity classification, Phase 0 gate requirements, multi-turn continuity, token limit triage |
| Phase 0 | [reference/phase0-self-review.md](reference/phase0-self-review.md) | Outcome spec, 3 approaches, self-critique, deletion pass, gate check |
| Phase 0.5 | [reference/confidence-gate.md](reference/confidence-gate.md) | 4-dimension confidence scoring rubric, thresholds, gap recovery | Big Change mode only |
| Phase 5 | [reference/production-readiness-gate.md](reference/production-readiness-gate.md) | Blast radius, rollback strategy, dependency health, cost/infra impact, data migration, second-order effects |
| All phases | [reference/review-interaction-protocol.md](reference/review-interaction-protocol.md) | Question format, decision log, visualization requirements, section pause protocol |

## Process

### Phase 0: Self-Review Loop (Big Change / Small Change only)

1. Read [reference/plan-mode-protocol.md](reference/plan-mode-protocol.md) for approval scope and severity rules
2. Read [reference/phase0-self-review.md](reference/phase0-self-review.md)
3. Execute Steps 0.1 through 0.5 in order
4. Do NOT proceed to Phase 1 until Phase 0 gate passes

For **Review Only** mode: skip Phase 0 but run a lightweight outcome check — ask "Is this still the right thing to build/maintain? Has the original goal changed?"

### Phase 0.5: Confidence Gate (Big Change only)

Score the plan across 4 dimensions before allowing implementation to proceed. Each dimension is 0–100. Overall must reach **≥ 80** to proceed (≥ 95 for irreversible changes: migrations, public API contracts, auth architecture).

| Dimension | Questions | Score |
|-----------|-----------|-------|
| **Requirement Clarity** | All user stories defined? Edge cases documented? Acceptance criteria measurable? Dependencies identified? | /100 |
| **Technical Feasibility** | Architecture approach proven? No unknown unknowns? APIs/libs verified against docs? Performance implications understood? | /100 |
| **Resource Assessment** | Scope realistic for session? Dependencies available? No unverified external APIs? | /100 |
| **Quality Assurance** | Test strategy defined? Rollback plan exists? Security implications understood? | /100 |

```
OVERALL CONFIDENCE: (D1 + D2 + D3 + D4) / 4 = XX%

[≥ 80%] → Proceed to implementation
[60–79%] → Address gaps listed below before proceeding
[< 60%] → STOP — plan needs significant work

Gaps to resolve before proceeding:
- [dimension]: [specific gap — what question couldn't be answered]
```

**Skip for:** Small Change and Review Only modes (qualitative Phase 0 gate is sufficient).

**For irreversible changes** (schema migrations, public API contracts, auth changes): threshold is 95%, not 80%.

Read [reference/confidence-gate.md](reference/confidence-gate.md) for the full scoring rubric, gap recovery actions, and examples.

### Phase 1: Architecture Review

Read [reference/review-interaction-protocol.md](reference/review-interaction-protocol.md) for visualization and question format requirements.

Evaluate:
- System design and component boundaries
- Dependency graph and coupling
- Data flow patterns and bottlenecks
- Scaling characteristics and single points of failure
- Security architecture (auth, data access, API boundaries)

Generate a Mermaid or ASCII diagram of the current architecture BEFORE discussing issues.

### Phase 2: Code Quality Review

Evaluate:
- Code organization and module structure
- DRY violations (be aggressive — per `code-standards.md`)
- Error handling patterns and missing edge cases
- Technical debt hotspots
- Over-engineering vs under-engineering

For deep review, delegate to the `code-reviewer` agent with its checklist.

### Phase 3: Test Review

Evaluate:
- Coverage gaps (unit, integration, e2e)
- Assertion quality — strong assertions > high coverage percentage
- Missing edge case coverage
- Untested failure modes and error paths

### Phase 4: Performance Review

Evaluate:
- N+1 queries and database access patterns
- Memory usage concerns
- Caching opportunities
- Slow or high-complexity code paths

Generate an annotated request/data flow diagram showing timing or complexity.

### Phase 5: Production Readiness Review

1. Read [reference/production-readiness-gate.md](reference/production-readiness-gate.md)
2. Execute all subsections: blast radius, rollback, dependency health, second-order effects, cost/infra, data migration
3. Verify the production readiness gate checklist before approving

### Phase 6: Debate-Based Verification (Optional — Big Change with architecture decision)

**When to trigger:** Phase 1 (Architecture Review) identified two or more competing valid approaches, OR the change is irreversible (schema migration, public API contract, auth architecture, major refactor).

**Skip when:** The approach is already decided and uncontested, or the change is scoped to a single service with no structural impact.

**3-role structure:**

```
Proponent  →  Presents the chosen approach with supporting evidence
     ↓
Opponent   →  Identifies flaws, raises the strongest case for an alternative
     ↓
Synthesizer →  Weighs both sides, produces a verdict with explicit trade-off reasoning
     ↓
If unresolved → Escalate to human with both positions documented
```

**How to run:**

1. **Proponent pass** — Argue FOR the current plan: what evidence supports it, what constraints it satisfies, what risks it mitigates.
2. **Opponent pass** — Argue AGAINST: what the alternative approach achieves better, what failure modes the plan has, what the proponent's evidence overlooks.
3. **Synthesizer verdict** — State which position is stronger and why. Name the deciding factors explicitly. If genuinely tied, list what additional information would break the tie.
4. **Escalate if unresolved** — If the synthesizer cannot produce a clear verdict, surface both positions to the human with a specific question: "This decision requires human judgement because [reason]."

**Output format:**

```
## Debate: [decision being evaluated]

### Proponent
[Strongest case FOR the chosen approach — evidence-backed]

### Opponent
[Strongest case AGAINST — concrete failure scenarios or better alternative]

### Synthesizer Verdict
**Winner:** [Chosen approach / Alternative / Inconclusive]
**Deciding factors:** [What tipped the balance]
**Accepted trade-offs:** [What the winning side gives up]
**Escalate to human:** [Yes/No — if yes, state the specific question]
```

**Relationship to `plan-challenger` agent:** `plan-challenger` runs one-sided attack (finds holes). Phase 6 debate runs two-sided structured opposition (proponent + opponent + neutral verdict). Use `plan-challenger` first to find weaknesses, then Phase 6 when two competing valid positions remain after the challenge.

## Implementation notes (decisions too small for an ADR)

While implementing an approved plan, append a dated line under `## Implementation notes` at the end of the plan file for every choice a reviewer would otherwise ask about (library option, data shape, a rejected alternative): `- YYYY-MM-DD: chose X over Y because Z (file:line)`. The section is append-only: once the plan file is committed, `git diff --numstat -- docs/plans/<plan>.md` must show `N	0` before each later commit (no deleted lines; an uncommitted new plan has nothing to compare); correct an earlier note with a new line. A choice that changes the architecture still needs an ADR (`architecture-decision-records`).

## Cross-Skill Delegation

| Need | Delegate to |
|------|-------------|
| Architecture Decision Records | `architecture-decision-records` skill |
| Deep security audit | `security-reviewer` agent |
| Database migration patterns | `database-schema-designer` skill |
| Code review checklist | `code-reviewer` agent |
| Tech debt / duplication | `dedup-code-agent` agent |

## Error Handling

**No plan provided:** Ask the user to describe the change, paste the plan, or point to a PR/branch.

**Scope unclear:** Ask which mode (Big Change / Small Change / Review Only) and which phases to include.

**Phase 0 gate fails:** List which gate items are incomplete. Do NOT proceed — ask the user to resolve.

**Cannot verify a claim:** Mark as `[UNVERIFIED — needs manual check]` with the specific command or URL to verify. Never fabricate evidence.
