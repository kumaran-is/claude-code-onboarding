---
name: next-issue
description: "Use when the user says /next, next issue, start next issue, pick up next task, what should I work on, or /next-issue --wave N / --plan. Picks the next actionable work item from GitHub Project/issues, local plans, session tasks, and in-flight branches, honouring blockers, assignees, waves, layer order, and failed verification. Not /status-check (binary feature health), /project-status (inventory), or /checkpoint (session snapshots)."
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
argument-hint: "[--plan] [--wave N] [--build #N] [--finish #N] [#N]"
metadata:
  domain: workflow
  role: orchestrator
  scope: session
  triggers: /next, next issue, next-issue, what should I work on, pick up next task, start next issue
  related-skills: plan-mode-review, verification-before-completion, systematic-debugging
last-reviewed: "2026-11-26"
---

# Next Issue (`/next`)

## Iron Law

**NEVER start implementing, create a branch, or touch any file before reading the full issue with `gh issue view <N>` (or the full local plan when there is no GitHub item) — and in `--plan` mode, never proceed until the user explicitly approves the plan.**

## How this skill is organised

This SKILL.md is the spine. Detailed discovery and the implement/ship handoff live in `references/`:

| Reference | Covers |
|---|---|
| `references/discovery.md` | Adapters: resume current work, GitHub Project, GitHub Issues, local plans. Candidate JSON. Blocker collection. |
| `references/plan-and-handoff.md` | `--plan` gates, reuse-first, AC-to-live-code, stack dispatch, `/verify` + `/ship` (no duplicated merge pipeline). |
| `references/implementation-notes.md` | Sub-ADR decision log (`docs/plans/<N>-implementation-notes.md`). The `needs human review` flag is the product. |

Mechanical ranking is `scripts/check-next-issue.py` — do not re-implement the sort in prose.

## Invocation

| Command | Behaviour |
|---|---|
| `/next` | Discover → pick → read fully → implement (human merge gate still applies) |
| `/next --plan` | Discover → plan → **wait for approval** |
| `/next --wave N` | Restrict discovery to wave N when a Wave field exists |
| `/next #N` / `--plan #N` | Skip discovery; plan or take over that item |
| `/next --build #N` | Load saved plan → implement → PR → **stop at merge** |
| `/next --finish #N` | After merge approval: `/ship` merge, board Done, unblock dependents |

Natural language ("what should I work on", "start next issue from Wave 3 with a plan") maps to the same flags.

**Two human gates, every mode:** plan approval (`--plan`) and merge approval (all modes). Auto-merge is forbidden.

## Step 0 — Selftest + sources

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py --selftest
python3 .claude/skills/next-issue/scripts/check-next-issue.py --scan-skill
```

Both must exit 0. Then collect candidates per `references/discovery.md`. Never hardcode owner, repo, project IDs, or a product path. If GitHub Project config is absent, skip that adapter. If `gh` is absent, use local plans and session tasks.

Resume **in-flight** work (branch, uncommitted diff, In Progress assigned to the invoker, failed `/verify`) **before** any new Todo.

## Step 1 — Rank

Write candidates to a temp JSON file, then:

```bash
INVOKER=$(gh api user --jq .login 2>/dev/null || git config user.name)
python3 .claude/skills/next-issue/scripts/check-next-issue.py \
  --pick /tmp/next-candidates.json --invoker "$INVOKER"
```

Add `--wave N` or `--include-assigned-to-others` when those flags were passed.

The script already applies, in order:

1. Resume failed verification, then other in-progress assigned to the invoker.
2. Drop Done / In Review / `[EPIC]` titles / open `blocked_by_open` / other assignees.
3. Lowest wave that still has Todo items (only if any item has `wave` set).
4. Layer buckets: foundation (schema/migration/infra) → api/mcp/backend → agent → frontend (Flutter/Angular/React/web) → other.
5. Lowest issue number inside the winning bucket.

`NONE` → report that and **stop**. Do not invent work.

State the pick's layer. If you would present an `agent` item while any `foundation` or `api` Todo remains in the JSON you passed, you assembled the JSON wrong — fix the labels, do not override the script.

## Step 2 — Read the work item

GitHub: `gh issue view <N>`. Local: Read the plan file. Confirm:

- [ ] Story + acceptance criteria read
- [ ] File/service scope identified (issue “Service / file scope”, plan file list, or AC paths) — only those paths may be touched
- [ ] Open blockers → STOP
- [ ] Labels mapped to a skill via SKILLS_GUIDE
- [ ] AC-to-live-code: every AC that names a contract is grepped against **live** code (`references/plan-and-handoff.md`)

## Step 3 — Plan (`--plan` only)

Skip if not `--plan`. Follow `references/plan-and-handoff.md`. Save the plan, then:

```
PLAN READY — reply "approve" to start implementation, or give feedback to revise.
```

Do not write code, create a branch, or touch files until the user replies `approve` (or a clear equivalent).

## Step 4 — Load the stack skill

Dispatch from SKILLS_GUIDE (`references/plan-and-handoff.md`). Flutter Android/iOS E2E remains Maestro. Web E2E remains Playwright CLI/Test. Chrome DevTools MCP is diagnostics, not a substitute for either.

## Step 5–8 — Branch, implement, verify, ship

See `references/plan-and-handoff.md`. Short form:

5. Branch + board In Progress (GitHub) or local branch (no GitHub). Slice PRs must **not** use `gh issue develop`. Optional worktree isolation (`/worktree-sync --new`) is not a gate — `python3 .claude/scripts/check-worktree-isolation.py --detect` first. `/brainstorm` is never required on an approved issue.
5b. Seed `docs/plans/<N>-implementation-notes.md` if missing (`references/implementation-notes.md`). Append-only after that. Never `Write` over an existing log. Each entry has **Files** scope; this is not a second plan.
6. Implement via the stack skill. Reuse-first. No silent scope creep. Log sub-ADR decisions as they happen; auto-flag `needs human review: yes` on every `deviation`.
6b. Plan ↔ diff evidence, then `/verify` on touched stacks.
7. Domain reviewers from SKILLS_GUIDE.
8. `/ship` for the PR. **Stop.** Merge only after an explicit keyword, via `/ship` / `--finish`.

## Not this skill

| Need | Use |
|---|---|
| Binary what works / is broken | `/status-check` |
| Repo inventory | `/project-status` |
| Session snapshot | `/checkpoint` |
| Build+test exit codes | `/verify` |
| Open PR + merge | `/ship` |
| Paired manual QA | `/test-partner` |
| Session wrap | `/end-session` |

## Verify

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py --selftest
python3 .claude/skills/next-issue/scripts/check-next-issue.py --scan-skill
```

A pick is valid only when:

- [ ] Selftest and scan exit 0
- [ ] The full issue or plan was read before any write
- [ ] `--plan` stopped at `PLAN READY` until approval
- [ ] Merge waited for an explicit human keyword and went through `/ship`
- [ ] Implementation notes exist for the issue (or an explicit “no sub-ADR decisions”) and every `deviation` is flagged `needs human review: yes`
