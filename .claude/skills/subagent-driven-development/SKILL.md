---
name: subagent-driven-development
description: 3-role pipeline (Implementer -> Spec Reviewer -> Quality Reviewer) for plan-driven multi-task implementation. Supports subagent dispatch (Agent tool) and Agent Teams (TeamCreate). Use when a plan file exists in docs/plans/ and work spans 3+ tasks.
allowed-tools: Read, Glob, Bash
metadata:
  triggers: subagent, SDD pipeline, multi-agent, agent teams, parallel agents, plan-driven implementation, TeamCreate
  related-skills: plan-mode-review, writing-skills, test-driven-development
  domain: workflow
  role: architect
  scope: design
  output-format: document
last-reviewed: "2026-03-14"
---

## Iron Law

**NO AGENT DISPATCH WITHOUT A COMMITTED PLAN FILE IN `docs/plans/` — agents without a written plan produce unreviewed, unverifiable output**

# Subagent-Driven Development (SDD)

Turns an approved plan into working, reviewed code using a 3-role pipeline:
**Implementer → Spec Reviewer → Quality Reviewer**.

Works in two dispatch modes: subagent (Agent tool, sequential) and team (TeamCreate, concurrent).

---

## When to Use

Prerequisites — both must be true:
- A plan file exists at `docs/plans/YYYY-MM-DD-<feature>.md` (created via `/plan-review`)
- The plan has 3 or more distinct implementation tasks

Mode selection:

| Condition | Use |
|-----------|-----|
| ≤5 tasks OR tech stack has no specialized implementer agent | **Subagent mode** |
| 6+ tasks OR Java / NestJS / Flutter / Python with tech-specific implementer adds value | **Team mode** |

Present to the developer at start:
```
Plan: [file]. [N] tasks detected.
1. Subagent mode — Agent tool, general-purpose agents, best for ≤5 tasks
2. Team mode    — TeamCreate with tech-specific agents, best for 6+ tasks
```

---

## The Pipeline

This pipeline runs identically in both modes — only the dispatch mechanism differs.

### Step -1 — Research Phase (optional)

Use when the feature touches an unfamiliar external API, a new compliance domain, or a third-party service the team hasn't integrated before.

Dispatch a `general-purpose` agent with:
- The feature name and the specific unknown (e.g., "Stripe Connect payouts API — we haven't used this before")
- Output target: `docs/research/<feature>.md`
- **Mandatory constraint in prompt:** "Your role is RESEARCH ONLY. Describe what exists — APIs, constraints, auth model, rate limits, SDK options, gotchas. Do NOT propose improvements, suggest refactors, or recommend implementation approaches. If you notice problems in the existing code, note them as observations only — not as suggestions. The Spec agent will decide what to build."

The research agent should produce: API capabilities, key constraints, auth model, rate limits, SDK options, and gotchas. Save to `docs/research/<feature>.md` and commit before starting Step 0.

The spec reviewer in Step 2 receives this file path inline — include it in the spec reviewer prompt so it can verify the implementer's API usage against the research findings.

**Skip when:** the tech stack is familiar, no external unknowns, or the plan was produced from a previous research session.

**Context Isolation:** After the Research agent completes and `docs/research/<feature>.md` is committed, issue `/clear` before dispatching the Spec/Implementer. Pass the research doc path as the only context carry-forward — do NOT carry the Research agent's conversation into Step 0.

### Step 0-PRE — Plan Validation Gate

Before parsing tasks, validate the plan structure. This runs ONCE before any dispatch.

**PR-Sizing Check:** Every task in the plan must be bounded to ≤1 PR. Flag any task that:
- Touches more than 3 services simultaneously (e.g. NestJS + Flutter + Spring Boot in one task)
- Modifies more than 15 files
- Spans more than one tech-stack layer without a clear seam (split at the layer boundary)

If any task fails the PR-sizing check:
```
PLAN VALIDATION FAILED:
Task N: "[task title]" is too large for a single PR.
Touches: [list services/files]
Required split: [suggested sub-tasks A, B]
→ Update the plan file before continuing.
```

**Context Brief Check:** Every task must have a `## Context Brief` section (see `docs/plans/TEMPLATE.md`). If missing:
```
PLAN VALIDATION FAILED:
Task N: "[task title]" is missing ## Context Brief section.
Required fields: affected_files, preconditions, verification_command
→ Add the context brief to the plan file before continuing.
```

**Rollback Check:** Every task must have a `rollback_strategy` field. If missing:
```
PLAN VALIDATION FAILED:
Task N: "[task title]" is missing rollback_strategy.
→ Add rollback strategy before continuing.
```

Skip validation only for plans with a single task (≤1 task = trivial, no gate needed).

### Step 0 — Parse the Plan Once

Read the full plan file once. Extract every task as a structured object:

```
Task N:
  title: [task title from plan]
  full_text: [complete task description including acceptance criteria]
  tech_stack: [inferred from context — Java / NestJS / Python / Flutter / Angular / General]
  files_affected: [list if stated]
```

Create a `TaskCreate` entry for each task before starting any implementation.

### Step 1 — Per-Task Implementer

Dispatch the implementer with:
- Full task text (do NOT tell implementer to read the plan — provide it inline)
- Tech-stack skill reference (e.g., "consult `.claude/skills/java-spring-api/`")
- The implementer-prompt.md template content

Implementer flow:
1. Implementer may ask clarifying questions → answer them → re-dispatch
2. Implementer implements, writes tests (TDD per `leverage-patterns.md` test-first), self-reviews
3. Implementer returns: what was built, tests, files changed, self-review findings
4. Implementer writes the **implementer handoff tag** at the end of its response — read [reference/handoff-tags.md](reference/handoff-tags.md) for the exact format
5. Orchestrator extracts the tag block verbatim for use in Step 2 — do NOT summarize it

### Step 2 — Spec Compliance Review

Dispatch the spec reviewer with:
- The task's full_text from Step 0 (the spec)
- The implementer's full response from Step 1
- The implementer handoff tag block verbatim (from `reference/handoff-tags.md` format)
- The spec-reviewer-prompt.md template content

Spec reviewer flow:
- Issues found → implementer fixes → spec review re-runs (no cap on iterations)
- No issues → advance to Step 3
- Spec reviewer writes the **spec-reviewer handoff tag** at the end of its response — format in [reference/handoff-tags.md](reference/handoff-tags.md)
- `CONDITIONAL PASS` = implementer must fix open issues before Step 3 starts

### Step 3 — Quality Review

Dispatch the quality reviewer (routed by tech stack — see routing table below) with:
- The files changed by the implementer (from implementer tag `FILES_CHANGED`)
- The implementer handoff tag block verbatim
- The spec-reviewer handoff tag block verbatim
- Tech-stack reviewer instructions

Quality reviewer flow:
- Issues found → implementer fixes → quality review re-runs (not spec review — only quality)
- No issues → mark `TaskUpdate: completed` → advance to next task
- Quality reviewer writes the **quality-reviewer handoff tag** at the end of its response — format in [reference/handoff-tags.md](reference/handoff-tags.md)
- After all tasks: collect all `DEFERRED:` entries from implementer tags → add to PR body as **Known Gaps / Deferred**

### Step 4 — Final Pass and PR

After all tasks complete:
1. Dispatch `code-reviewer` agent on all changed files for a final cross-task consistency check
2. Create PR per CLAUDE.md git workflow (conventional commits, branch naming, squash merge target)

---

## Tech-Stack Routing Table (Quality Reviewer)

| Tech Stack | Agent |
|------------|-------|
| Java / Spring Boot | `spring-boot-reviewer` |
| NestJS | `nestjs-reviewer` |
| Python / FastAPI | `code-reviewer` |
| Flutter | `riverpod-reviewer` |
| Agentic AI | `agentic-ai-reviewer` |
| Angular / General | `code-reviewer` |

---

## Subagent Mode Dispatch

All agents dispatched via the `Agent` tool.

**Implementer:**
```
Agent tool:
  subagent_type: general-purpose
  prompt: [implementer-prompt.md content] + [task full_text] + [tech-stack skill reference]
```

**Spec Reviewer:**
```
Agent tool:
  subagent_type: general-purpose
  prompt: [spec-reviewer-prompt.md content] + [task spec] + [implementer output]
```

**Quality Reviewer:**
```
Agent tool:
  subagent_type: [from routing table above]
  prompt: "Review the following files for [tech stack] quality, patterns, and standards.
           Files changed: [list]. Focus on: correctness, error handling, test coverage,
           naming, and adherence to project conventions in .claude/rules/."
```

Do NOT dispatch implementer and spec reviewer in parallel — spec review depends on implementer output.
Do NOT dispatch multiple implementers in parallel — file conflicts are guaranteed.

---

## Team Mode Dispatch

Use when 6+ tasks or when a tech-specific implementer agent provides meaningful leverage.

### Setup

```
1. TeamCreate — name the team after the feature (e.g., "auth-service")
2. Spawn agents:
   - implementer: subagent_type = tech-specific developer agent
     (java-spring-api | nestjs-api | python-dev | agentic-ai-dev | angular-spa | flutter-mobile)
   - spec-reviewer: subagent_type = general-purpose
   - quality-reviewer: subagent_type = from routing table above
3. Assign tasks via TaskUpdate (owner field) + SendMessage with full task context
```

### Coordination

- Use `TaskList` to track progress across all tasks
- Assign tasks to implementer one at a time (pipeline is sequential per task)
- After implementer completes → SendMessage to spec-reviewer with task spec + output
- After spec-reviewer approves → SendMessage to quality-reviewer with changed files
- After quality-reviewer approves → mark TaskUpdate: completed → assign next task
- When all tasks complete → SendMessage shutdown_request to all agents → TeamDelete

### Message format to teammates

Always send full task context in the message body — never tell teammates to "read the plan".
Include: task title, acceptance criteria, files affected, and any prior reviewer findings.

---

## Parallel Dispatch — Independence Check

Before dispatching agents in parallel, verify independence first.

Read [reference/parallel-dispatch-checklist.md](reference/parallel-dispatch-checklist.md) for the decision tree, pre-dispatch checklist, post-completion conflict check, and examples.

**Rule:** If tasks share files, config, or have ordering dependencies → sequential only.

---

## Context Isolation Protocol

Context contamination is the #1 silent failure in multi-phase pipelines. A Research agent that mentions "the auth layer is messy" will cause a Spec agent to include auth cleanup in scope — work that was never requested.

### Why It Matters

```
Without isolation:
  Research agent → analyzes codebase → notices auth is messy → mentions it
  → Spec agent absorbs the mention → adds auth refactor to spec
  → Implementer touches auth it was never asked to touch
  → Scope creep introduced silently, never caught

With isolation:
  Research agent → outputs ONLY facts to docs/research/<feature>.md
  /clear → Spec/Implementer starts fresh with only the research doc
  → Scope stays exactly what was planned
```

### The Three Rules

**1. Research mandate — "NO improvement suggestions"**
The Research agent prompt MUST include: *"Describe what exists. Do NOT propose changes."*
Violations: suggesting refactors, flagging tech debt for fixing, recommending alternatives.
Allowed: noting constraints, documenting gotchas, describing current behavior.

**2. `/clear` between Research and Step 0**
After `docs/research/<feature>.md` is committed:
- Issue `/clear` (or equivalent context reset between agent dispatches)
- The ONLY carry-forward is the research doc file path
- The Research agent's conversation, opinions, and analysis do NOT pass to Step 0

**3. Per-phase context containment**
Each phase receives exactly what it needs — no more:

| Phase | What to pass in | What NOT to pass in |
|-------|----------------|---------------------|
| Step -1 Research | Plan file path, specific unknowns | Nothing else |
| Step 0–1 Implementer | Task full_text + research doc path (if exists) | Research agent conversation |
| Step 2 Spec Reviewer | Task spec + implementer output + handoff tag | Research agent opinions |
| Step 3 Quality Reviewer | Files changed + handoff tags | Prior reviewer conversations |

---

## Red Flags — Never Do These

- **Never carry Research agent conversation into Step 0** — `/clear` after research, pass only the doc path
- **Never let Research agent propose improvements** — Research describes what exists; Spec decides what to build
- **Never dispatch parallel implementers** — file conflicts are guaranteed
- **Never skip the independence checklist** before parallel dispatch — assumption of independence is not sufficient
- **Never skip spec review** — quality review does not check spec compliance
- **Never reverse pipeline order** — spec compliance before quality review, always
- **Never skip a review loop** — reviewer found issues = implementer fixes = re-review required. Re-dispatch only the reviewers that own open or newly closed findings; from round 3 only CRITICAL/HIGH block, and MEDIUM/LOW go into the PR body (`verification-before-completion/reference/verification-loop.md` §4, bounded re-review)
- **Never let implementer self-review replace spec/quality review** — both are required
- **Never tell implementer or reviewer to read the plan file** — provide full task text inline
- **Never declare a task complete while a reviewer has open issues**
- **Never skip the post-completion conflict check** after parallel agent dispatch

---

## Integration References

| When | Reference |
|------|-----------|
| Implementer hits a bug during implementation | `systematic-debugging` skill |
| Before marking any task complete | `verification-before-completion` skill |
| Creating the PR | CLAUDE.md git workflow (conventional commits, feature branch, squash merge) |
| Plan file must exist | `docs/plans/` convention — `/plan-review` creates it |
| Writing a new plan | `docs/plans/TEMPLATE.md` — required format for context briefs, rollback, and mutations |
| Security findings during review | `security-reviewer` agent |
| Passing context between pipeline stages | [reference/handoff-tags.md](reference/handoff-tags.md) — structured tag format |
| Feature with 10+ tasks across several domains and sessions | [reference/nexus-state-template.md](reference/nexus-state-template.md) — NEXUS phases, go/no-go gates, PR slicing, session resume, state file |

---

## Error Handling

**No plan file found:**
```
BLOCKED: No plan file found in docs/plans/.
Run /plan-review to generate and save a plan before invoking SDD.
```

**Implementer asks questions before starting:**
Answer them directly. Do not dispatch another implementer — respond to the current one and let it proceed.

**Review loop exceeds 3 iterations on same issue:**
```
STOPPED: [reviewer] has flagged [issue] 3 times without resolution.
Options:
A) Escalate — bring in the human to resolve the design conflict
B) Waive — mark issue as known gap with explicit approval
C) Redesign — scrap this task's implementation and start fresh
```

**Team mode: teammate goes unresponsive:**
Check `TaskList` for stuck in_progress tasks. Send a follow-up `SendMessage`. If still unresponsive after one retry, stop and notify the developer.
