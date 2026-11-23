# NEXUS Orchestration — Full-Lifecycle Multi-Session Feature Delivery

> **When to use**: Delivering a large feature that spans multiple sessions, multiple tech domains (backend + mobile + infra + security), and 10+ tasks — too large for a single SDD pipeline run
> **Time estimate**: Days to weeks across multiple sessions; setup 1–2 hours per phase transition
> **Prerequisites**: Feature idea scoped and agreed; CLAUDE.md onboarding complete; relevant skills available for all domains in scope

## Overview

NEXUS is the conductor's score for multi-sprint features. Where SDD handles a single session of 3–10 tasks within one domain, NEXUS coordinates the full lifecycle: spec → architecture → schema → implementation (multiple SDD runs) → security audit → deploy. Each phase has a hard go/no-go gate. A persistent state file (`docs/nexus-state/<feature>.md`) carries context between sessions so work can resume cleanly after any interruption.

---

## Iron Law

> **NEVER START IMPLEMENTATION (PHASE 4) WITHOUT A SIGNED-OFF SPEC (PHASE 1) AND API CONTRACTS (PHASE 2)**
> Implementing against a moving spec causes cascading rewrites across every layer. A one-hour spec session prevents days of rework.

---

## SDD vs NEXUS — When to Use Which

| Signal | Use |
|--------|-----|
| ≤10 tasks, single domain, fits in one session | SDD (`subagent-driven-development.md`) |
| 10+ tasks, multiple domains, work spans days | NEXUS (this workflow) |
| Single long autonomous iteration | Ralph loop (`ralph-loop-autonomous.md`) |
| Any NEXUS implementation phase | SDD pipeline inside NEXUS Phase 4 |

---

## Phases

### Phase 1 — Feature Spec

**Skill**: `feature-forge` (load via `/feature-forge`)
**Agent**: none — Claude + human collaborate directly
**Command**: `/feature-forge`

Produce a spec in EARS format (Easy Approach to Requirements Syntax):
- User stories with WHEN/THEN acceptance criteria
- Non-functional requirements (latency targets, throughput, error budgets)
- Out-of-scope list (explicit, agreed)
- Open questions resolved before proceeding

**Output**: `docs/specs/YYYY-MM-DD-<feature>.md`

**Gate**: Spec approved by human and saved to `docs/specs/`. No open questions. Every WHEN/THEN scenario agreed. → **Proceed to Phase 2**

---

### Phase 2 — Architecture

**Skill**: `architecture-design` (load via `/design-architecture`)
**Command**: `/design-architecture`
**Agent**: `architect`, then `plan-challenger` for adversarial review

Produce:
- C4 context + container diagrams in `docs/diagrams/`
- API contracts (request/response shapes, error codes) — defined BEFORE any code
- Sequence diagrams for all non-trivial flows
- ADR for each key technology decision in `docs/adr/NNNN-<decision>.md` (numbering per the `architecture-decision-records` skill)

The `plan-challenger` agent must review the architecture for assumptions, missing failure modes, and over-engineering. Address all BLOCK-level findings before advancing.

**Output**: `docs/adr/`, `docs/diagrams/`, API contract document

**Gate**: API contracts defined and approved; `plan-challenger` review complete with no unresolved BLOCK findings. → **Proceed to Phase 3 (or Phase 4 if no schema work)**

---

### Phase 3 — Database Schema (if applicable)

**Skill**: `database-schema-designer` (load via `/design-database`)
**Command**: `/design-database`
**Agents**: `database-designer`, `postgresql-database-reviewer`

Produce:
- Flyway migrations in `db/migrations/` — every migration must be reversible (up + down)
- ERD in `docs/diagrams/<feature>-erd.md`
- Index definitions for all expected query patterns (`EXPLAIN ANALYZE` run before finalizing)

Run `postgresql-database-reviewer` against all migration files before advancing. No direct table drops without explicit human approval.

**Output**: `db/migrations/`, `docs/diagrams/<feature>-erd.md`

**Gate**: `postgresql-database-reviewer` returns SAFE TO APPLY; migration is reversible; indexes cover query patterns. → **Proceed to Phase 4** *(Skip this phase entirely if no schema changes)*

---

### Phase 4 — Implementation (SDD pipeline, one or more runs)

**Skill**: `subagent-driven-development` (load before dispatching any agent)
**Command**: `/plan-review` → produces `docs/plans/YYYY-MM-DD-<feature>.md` → then SDD
**Agents**: implementer + spec-reviewer + quality-reviewer per task (3-role SDD pipeline)

For features with 10+ tasks, split implementation into logical slices and ship each slice as its own PR rather than one giant diff (see **Splitting Into Multiple PRs** below). Update `docs/nexus-state/<feature>.md` after each slice merges.

**State tracking**:
- `TaskList` tracks current task status across agents
- `docs/nexus-state/<feature>.md` records current phase, completed slices, open items, deferred decisions
- Handoff tags in `reference/handoff-tags.md` carry inter-agent context

**Session resume** (see **Session Resume Protocol** below): on restart, read `TaskList` → identify last completed task → resume from next incomplete task in current phase.

**Output**: All implementation code, tests passing, PRs merged per logical slice

**Gate**: All tasks in `TaskList` marked completed; all SDD reviewer verdicts APPROVE or NEEDS_REVIEW with documented exceptions; no BLOCK verdicts outstanding. → **Proceed to Phase 5**

---

### Phase 5 — Security Audit

**Skill**: `security-audit` (loaded implicitly by commands below)
**Commands**: `/audit-security` → `/security-sast` → `/security-dependencies` → `/xss-scan`
**Agents**: `security-reviewer` (use opus model for depth), `flutter-security-expert` (if mobile is in scope), `threat-modeling-expert` (if a new attack surface was introduced)

Run all four commands in sequence. Each produces a findings report. Address all CRITICAL findings before advancing. HIGH findings must be triaged — either fixed or accepted with explicit human sign-off and a linked ADR entry.

**Output**: Security findings reports; patched code; updated `docs/adr/` if any HIGH finding is accepted

**Gate**: Zero CRITICAL findings unresolved. All HIGH findings either fixed or accepted with documented rationale. → **Proceed to Phase 6**

---

### Phase 6 — Deploy

**Workflows**: `deployment-ci-cd.md` (GitHub Actions pipeline) + `cloud-run-terraform.md` (infrastructure)
**Command**: `/ship` (pre-deploy readiness check)
**Agents**: `deployment-engineer`, `terraform-specialist`

Steps:
1. Run `/ship` — it checks all quality gates and returns `✅ READY TO SHIP` or a blocking list
2. Apply Terraform changes via `cloud-run-terraform.md` workflow
3. Deploy to staging; run smoke tests; verify Cloud Run health check passes
4. Promote to production only after staging health check is green
5. Monitor error rate and latency for 30 minutes post-deploy

**Gate**: `/ship` returns `✅ READY TO SHIP`; staging health check passes; production deploy completes with no elevated error rate. → **Feature complete — close NEXUS state file**

---

## Session Resume Protocol

NEXUS runs span multiple days. Context is lost between sessions. Follow this protocol every time a session starts on an active NEXUS feature:

```
On session start:
1. Run TaskList — identify current phase and last completed task
2. Read docs/plans/YYYY-MM-DD-<feature>.md — recover task list and acceptance criteria
3. Read docs/nexus-state/<feature>.md — recover phase, open items, deferred list
4. Check recent git log — verify what was committed vs what is still in-progress
5. Resume from the next incomplete task in the current phase
```

**State file location**: `docs/nexus-state/<feature>.md`
Template defined in: `reference/nexus-state-template.md`

The state file is the NEXUS memory. If it does not exist, create it at the start of Phase 1. Update it at every phase gate crossing and after every merged PR slice.

---

## Splitting Implementation Into Multiple PRs

For features with 10+ tasks, never ship one giant PR. Split by logical slice:

| Slice | Contents | When to Ship |
|-------|----------|-------------|
| 1 — Data model | Migrations, seed data, model types | After Phase 3 gate |
| 2 — Backend API | Endpoints, services, unit tests | When API contract is fully implemented |
| 3 — Frontend / Mobile | UI components, state management, integration tests | After Slice 2 merges |
| 4 — Integrations + E2E | Third-party integrations, E2E test suite, observability | After Slice 3 merges |

Each slice goes through its own PR shipping workflow (`pr-shipping.md`). The NEXUS state file tracks which slices are merged. Slices 2–4 may proceed in parallel if there are no inter-slice dependencies — coordinate via `TaskList` and `TeamCreate`.

---

## Go/No-Go Gates

| Phase | Gate Condition | Blocking? |
|-------|---------------|-----------|
| 1 — Spec | Spec approved and saved to `docs/specs/`; no open questions | Yes |
| 2 — Architecture | API contracts defined; `plan-challenger` reviewed; no BLOCK findings | Yes |
| 3 — Database | `postgresql-database-reviewer` returns SAFE TO APPLY; migration reversible | Yes (if applicable) |
| 4 — Implementation | All tasks complete in `TaskList`; no BLOCK reviewer verdicts outstanding | Yes |
| 5 — Security | Zero CRITICAL findings unresolved | Yes |
| 6 — Deploy | `/ship` returns READY TO SHIP; staging health check passes | Yes |

---

## Quick Reference

| Phase | Command / Skill | Key Agent | Output |
|-------|----------------|-----------|--------|
| 1 — Spec | `/feature-forge` | — | `docs/specs/YYYY-MM-DD-<feature>.md` |
| 2 — Architecture | `/design-architecture` | `architect`, `plan-challenger` | `docs/adr/`, `docs/diagrams/`, API contracts |
| 3 — Database | `/design-database` | `database-designer`, `postgresql-database-reviewer` | `db/migrations/`, ERD |
| 4 — Implementation | `/plan-review` → SDD | implementer, spec-reviewer, quality-reviewer | Code, tests, merged PRs |
| 5 — Security | `/audit-security` chain | `security-reviewer`, `threat-modeling-expert` | Findings reports, patches |
| 6 — Deploy | `/ship` | `deployment-engineer`, `terraform-specialist` | Live feature on production |

---

## Common Pitfalls

- **Skipping Phase 1 spec** — "we know what we're building" leads to mid-implementation pivots that invalidate completed SDD tasks and force full rewrites across multiple layers
- **Starting Phase 4 without API contracts** — frontend and backend diverge immediately; merging them later takes longer than writing the contracts upfront
- **One giant PR for the whole feature** — reviewers cannot meaningfully review 2000-line diffs; split by logical slice as described above
- **Not writing the nexus-state file** — session context is lost between days; the state file is the only persistent memory across sessions
- **Running security audit after deploy** — Phase 5 must complete before Phase 6; security findings discovered post-deploy require emergency hotfixes and potential rollbacks
- **Using NEXUS for small features** — if the feature fits in a single SDD run (≤10 tasks, single domain, single session), use SDD directly; NEXUS overhead is not justified

## Related Workflows

- [`subagent-driven-development.md`](subagent-driven-development.md) — the implementation engine used inside Phase 4
- [`architecture-design.md`](architecture-design.md) — full detail on Phase 2 deliverables and the `architect` agent
- [`database-schema-design.md`](database-schema-design.md) — full detail on Phase 3 migration and review process
- [`security-audit.md`](security-audit.md) — full detail on Phase 5 commands and findings triage
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — GitHub Actions pipeline used in Phase 6
- [`pr-shipping.md`](pr-shipping.md) — per-slice PR process referenced in Phase 4
- [`plan-review.md`](plan-review.md) — validates the plan before each SDD run in Phase 4
- [`adr-creation.md`](adr-creation.md) — format and process for ADRs produced in Phase 2
