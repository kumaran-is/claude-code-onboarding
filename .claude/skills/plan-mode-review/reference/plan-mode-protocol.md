# Plan Mode Protocol

> Loaded by the `plan-mode-review` skill. Not an always-loaded rule.

## Approval Scope Rules

Not every issue needs explicit human sign-off. Use this triage:

| Level | Scope | Action |
|-------|-------|--------|
| **Critical — Requires approval** | Architecture changes, public API contracts, data model/schema changes, rollback-risky changes, anything affecting other teams/services | Ask before proceeding |
| **High — Inform and proceed** | Internal refactors, DRY cleanups, test additions, naming improvements, performance tweaks that don't change behavior | State what you're doing, proceed unless objected |
| **Low — Just do it** | Typo fixes, formatting, import ordering, obvious bug fixes with clear solutions | Batch at the end of a section as "auto-applied fixes" |

**When uncertain:** escalate to High. Never silently apply a Critical-level change.

## Phase 0 Gate Requirements

Before any implementation begins, Phase 0 must complete all of:

1. **Outcome defined** — success criteria in user/business terms, not technical terms
2. **Approaches compared** — at least 3 distinct approaches with LOC/files/complexity estimates (always consider a no-code/config-only option)
3. **Self-critique done** — edge cases, over/under-engineering, wrong assumptions, confidence rating
4. **Deletion pass done** — every component that could be deferred or removed is listed with impact
5. **Human approved direction** — explicit go-ahead before proceeding to review phases

If ANY gate item is incomplete, do NOT proceed. Ask for what's missing.

When the artifact is an implementation plan (not a design sketch), each task must be an executable contract at `docs/plans/TEMPLATE.md` density: objective/scope, requirement traceability (AC mapping), files, interfaces consumed/produced, dependencies, constraints, acceptance criteria, exact stack verification command, review focus, completion evidence, out of scope. Proportional: Complexity S may set interfaces to `none`. Do not invent a second plan or a Superpowers planning directory. Do not add an extra approval gate — the existing human `approve` on `/next --plan` / `/plan-review` is the gate.

```bash
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py --scan-plan docs/plans/<plan>.md
```

## Implementation notes (during and after the plan)

Sub-ADR decisions that appear while implementing belong in `docs/plans/<issue-N>-implementation-notes.md`, not in this review transcript and not in `lessons.md`. Schema, append-only rule, and the `needs human review` flag: `next-issue/references/implementation-notes.md`. Load-bearing architectural choices still go through `architecture-decision-records` first.

## Multi-Turn Continuity

When the review spans multiple messages:

1. **Start each new turn** with a "Decisions so far" summary:
   ```
   DECISION LOG (updated after Section N):
   ---
   Approved:  [list with IDs]
   Rejected:  [list with IDs]
   Deferred:  [list with IDs and reasons]
   Auto-fixed: [list]
   ---
   ```
2. Do NOT re-review completed sections
3. If earlier decisions are lost to context compression, say so and request a recap

## Token Limit Triage

When running low on context:

1. **Prioritize Critical** — full analysis with diagrams
2. **Summarize High** — 2-3 sentence description per issue
3. **Batch Low** — one-line list as auto-fixes
4. **Skip** diagram generation for low-severity items
5. Always complete the current section before triaging the next

## Severity Classification

Align with existing `code-reviewer` severity levels. Present Critical first, then High, then Medium, then Low:

| Severity | Criteria | Action |
|----------|----------|--------|
| **Critical** | Bugs, security vulnerabilities, data loss risks, architectural flaws that block shipping | Must fix before merge |
| **High** | DRY violations, missing edge cases, performance concerns, test gaps on critical paths | Should fix; track if deferred |
| **Medium** | Code style improvements, naming consistency, minor refactors | Fix if time permits |
| **Low** | Nice-to-have tests, documentation, trivial cleanup | Batch as auto-fixes |

## Structured Question Format

See [review-interaction-protocol.md](review-interaction-protocol.md) for the complete question format template, decision log format, and visualization requirements.
