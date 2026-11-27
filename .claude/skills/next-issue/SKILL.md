---
name: next-issue
description: "Use when the user says /next, next issue, start next issue, pick up next task, what should I work on, or /next-issue --wave N / --plan / --auto. Picks the next actionable work item from GitHub Project/issues, local plans, session tasks, and in-flight branches, honouring blockers, assignees, waves, layer order, and failed verification. `/next --auto` is opt-in multi-story automation (explicit flag only). Not /status-check (binary feature health), /project-status (inventory), or /checkpoint (session snapshots)."
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, Agent
argument-hint: "[--plan] [--wave N] [--build #N] [--finish #N] [--fix-loop] [--auto] [#N]"
metadata:
  domain: workflow
  role: orchestrator
  scope: session
  triggers: /next, next issue, next-issue, what should I work on, pick up next task, start next issue
  related-skills: plan-mode-review, verification-before-completion, systematic-debugging, subagent-driven-development, browser-testing
last-reviewed: "2026-11-27"
---

# Next Issue (`/next`)

## Iron Law

**NEVER start implementing, create a branch, or touch any file before reading the full issue with `gh issue view <N>` (or the full local plan when there is no GitHub item) — and in `--plan` mode, never proceed until the user explicitly approves the plan.**

## How this skill is organised

This SKILL.md is the spine. Detailed discovery and the implement/ship handoff live in `references/`:

| Reference | Covers |
|---|---|
| `references/discovery.md` | Adapters: resume current work, GitHub Project, GitHub Issues, local plans. Candidate JSON. Blocker collection. |
| `references/plan-and-handoff.md` | `--plan` gates, reuse-first, AC-to-live-code, stack dispatch, impact `/verify` + `/ship` readiness + `/create-pr` (no duplicated merge pipeline; `/ship` does not merge). |
| `references/loop-and-qualify.md` | Opt-in `--fix-loop`: GO/NO-GO, real `--verify-cmd`, Ralph max 5, no next-issue chaining. |
| `references/auto-loop.md` | Opt-in `/next --auto` only. HITL `/next` must not load this. |
| `references/implementation-notes.md` | Sub-ADR decision log (`docs/plans/<N>-implementation-notes.md`). The `needs human review` flag is the product. |

Mechanical ranking is `scripts/check-next-issue.py` — do not re-implement the sort in prose.

## Invocation

| Command | Behaviour |
|---|---|
| `/next` | Discover → pick → read fully → implement (human merge gate still applies) |
| `/next --plan` | Discover → plan → **wait for approval** |
| `/next --wave N` | Restrict discovery to wave N when a Wave field exists |
| `/next #N` / `--plan #N` | Skip discovery; plan or take over that item |
| `/next --build #N` | Load saved plan → implement → impact `/verify` → `/create-pr` → **stop at merge** |
| `/next --finish #N` | After merge approval: `/ship` readiness (does not merge); after the human merges: board Done, unblock dependents |
| `/next --fix-loop` | After a failing `/verify`: qualify (GO/NO-GO), then bounded Ralph fix/retest (max 5, required shell `--verify-cmd`). Still stops at merge. Never starts the next issue. |
| `/next --auto --wave N` (or `--milestone` / `#N #M`) | Opt-in coordinator: bounded dependency-ordered stories. Load `references/auto-loop.md`. |

Natural language ("what should I work on", "start next issue from Wave 3 with a plan") maps to the same flags. Natural language never enables `--auto`.

**Two human gates for `/next` without `--auto`:** plan approval (`--plan`) and merge approval (all HITL modes). Auto-merge is forbidden. `--auto` applies only when the `--auto` flag is present (only the `--auto` flag; never implied).

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

Dispatch from SKILLS_GUIDE (`references/plan-and-handoff.md`). Both UI stacks follow the same **E2E quality contract** there: plan coverage → implement → update E2E → run on a real browser/device → classify failures → never weaken assertions → `/review-code` → `/ship` → human merge. Flutter Android/iOS uses `flutter-mobile` + Maestro CLI/MCP (no Maestro Planner/Generator/Healer agents). Web uses Playwright CLI/Test; product Playwright Test Agents are conditional specialists only (`browser-testing/reference/playwright-test-agents.md`). Chrome DevTools MCP is diagnostics, not a substitute.

## Step 5–8 — Branch, implement, verify, ship

See `references/plan-and-handoff.md`. Short form:

5. Branch + board In Progress (GitHub) or local branch (no GitHub). Slice PRs must **not** use `gh issue develop`. Optional worktree isolation (`/worktree-sync --new`) is not a gate — `python3 .claude/scripts/check-worktree-isolation.py --detect` first. `/brainstorm` is never required on an approved issue.
5b. Seed `docs/plans/<N>-implementation-notes.md` if missing (`references/implementation-notes.md`). Append-only after that. Never `Write` over an existing log. Each entry has **Files** scope; this is not a second plan.
6. Implement via the stack skill. Reuse-first. No silent scope creep. Log sub-ADR decisions as they happen; auto-flag `needs human review: yes` on every `deviation`.
6b. Plan ↔ diff evidence, then `python3 .claude/scripts/check-verify-impact.py --stage iteration` and `/verify` on reached stacks (unknown → all present). On FAIL, default **stop**. `--fix-loop` only after GO from `references/loop-and-qualify.md` (real shell `--verify-cmd`, max 5, `require_verify=true`). NO-GO → human. Do not pass `/verify` to Ralph. Do not start the next issue.
7. Domain reviewers from SKILLS_GUIDE (`/review-code`). Independent review is required before `/ship`; SDD tasks also need ledger spec+quality PASS (`check-sdd-ledger.py --review-round`). Re-review is scoped (finding owners + newly appearing stacks + security when still applicable).
8. Freeze the tree, `check-verify-impact.py --stage frozen`, `/verify pre-pr`, `/ship` for readiness (does not merge), `/create-pr` to print `gh pr create` (does not run it). **Stop.** Merge only after an explicit human keyword. Do not run `gh pr merge`. (`/next --auto` is the sole exception: `references/auto-loop.md`.)

## Not this skill

| Need | Use |
|---|---|
| Binary what works / is broken | `/status-check` |
| Repo inventory | `/project-status` |
| Session snapshot | `/checkpoint` |
| Build+test exit codes | `/verify` |
| Open PR (print `gh pr create`; does not run it) | `/create-pr` |
| Readiness (does not merge) | `/ship` |
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
- [ ] Merge waited for an explicit human keyword; `/ship` is readiness (does not merge); `/create-pr` does not run `gh pr create`
- [ ] `--fix-loop` ran only after GO, with a shell `--verify-cmd` (not `/verify`) and max 5 iterations
- [ ] `--auto` ran only when the exact `--auto` flag was present, with an explicit wave/milestone/issue scope
- [ ] Implementation notes exist for the issue (or an explicit “no sub-ADR decisions”) and every `deviation` is flagged `needs human review: yes`
