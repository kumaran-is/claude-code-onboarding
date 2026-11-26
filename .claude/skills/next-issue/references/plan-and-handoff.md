# `/next` — plan mode and handoff (do not duplicate `/verify` or `/ship`)

## Human gates (mandatory)

1. **Plan approval** — `--plan` stops after the plan is saved. Wait for `approve` / `looks good`.
2. **Merge approval** — after CI is green, stop. The human says `merge` / `ship it`. Auto-merge is forbidden. `/ship` is readiness (does not merge). Open the PR with `/create-pr` (prints `gh pr create`; does not run it). Never `gh pr merge` from this skill. `/next --auto` is documented in `auto-loop.md` and does not apply here.

One stop per `--plan` run. Batch clarifying questions once before drafting. Do not serial-ask.

## Plan depth (adaptive)

Reuse-first and AC-to-live-code checks are mandatory in **content**, not in length. Effort `1`/`2`: a few lines citing grep. Effort `5`/`8`: full tables. A plan longer than the diff is a smell. Existing skill: `plan-mode-review`.

Every `--plan` output includes:

- **Plan Verdict** — Engineering Fit (Right / Over / Under) · Effort `1/2/3/5/8` · Risk Low/Med/High
- **Acceptance Criteria Mapping** — AC → work → how it will be verified
- **Scope & follow-ups** — IN-SCOPE vs DEFER, with effort and routing
- **Test Strategy** — points at `/verify` and the stack's Definition of Done; Flutter Android/iOS E2E is Maestro; web E2E is Playwright CLI/Test; Chrome DevTools MCP is diagnostics only
- **Final Recommendation** — Approve | Revise | Block. Only an Approve self-verdict reaches the human gate
- **Task contracts** (each implementation task, proportional to effort): objective/scope, files to create or modify, interfaces consumed/produced (`none` if none), dependencies, architecture constraints, acceptance criteria, exact stack verification command, review focus, completion evidence, out of scope. Use `docs/plans/TEMPLATE.md`. Scan with `python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py --scan-plan <plan>`. Do not write a second plan when this file is already adequate; enrich it.

`/brainstorm` is optional and never a gate on an approved issue.

Save to `docs/plans/YYYY-MM-DD-issue-<N>-<short-title>.md` (or `docs/plans/YYYY-MM-DD-<slug>.md` when there is no issue number) **before** presenting. `--build` reads that file; missing plan → STOP, never re-plan silently.

`--html` is opt-in. The `.md` stays the content SSOT.

## Reuse-first (3a-0)

For every capability the story needs, grep the live tree. Verdict per capability: **REUSE** (`file:line`) / **ENHANCE** (`file:line` + what to add) / **BUILD-NEW** (grep proof of absence). "File X doesn't exist" ≠ "capability X doesn't exist". No new service/package/agent while an existing owner can take the endpoint.

## AC-to-live-code

Every AC that names a contract (column, enum, route, path, event, shared widget) is grepped against **live** code before implementation. Mismatch → build to live truth, reconcile the AC, route leftovers: effort `1/2/3` fold into this PR; `5/8` become a follow-up work item visible to `/next` (same board/labels/wave as the parent, or it is invisible forever).

## Stack dispatch

Load the skill from `.claude/SKILLS_GUIDE.md` from the item's labels and the files in scope. Do not embed stack implementation rules here.

| Signal | Skill |
|---|---|
| Java / Spring | `java-spring-api` |
| NestJS | `nestjs-api` |
| Python / FastAPI | `python-dev` |
| LangChain / LangGraph | `agentic-ai-dev` |
| Google ADK | `google-adk` |
| Angular | `angular-spa` |
| React | `react-spa` |
| Flutter | `flutter-mobile` |
| MCP server | `mcp-builder` |
| Schema / migration | `database-schema-designer` |

Flutter UI work still follows `flutter-mobile` + `design-system` (DESIGN.md, tokens, Maestro). Web UI follows `angular-spa` or `react-spa` + `design-system` (Playwright).

## Branching

An optional worktree is **not mandatory**. Before creating a branch or worktree:

```bash
python3 .claude/scripts/check-worktree-isolation.py --detect
```

If already inside a linked worktree, stay there. If isolation is justified (parallel agents, dirty unrelated files you must not touch), `/worktree-sync --new <branch>` after `--propose-branch` exits 0. Do not stash, reset, discard, or commit `.gitignore`. Preserve unrelated staged, unstaged, and untracked files.

- Whole issue will ship in this PR and GitHub is in use → `gh issue develop <N> --checkout` then set board Status to In Progress (IDs fetched live).
- Slice / partial delivery → plain `git checkout -b …`. `gh issue develop` auto-closes on merge even with `Refs #N`.
- No GitHub → create a local branch named from the plan slug. Do not invent a remote.

If the project board exists, flipping Status to In Progress is part of picking work up — the board is what humans read.

## Implementation notes (Step 5b, then continuous)

See `references/implementation-notes.md`. Seed `docs/plans/<N>-implementation-notes.md` (or the branch-slug file) **before the first code write** if it does not exist. Append-only. The `needs human review` flag is the product. End of run: print flagged entries into the PR concerns section.

## After implementation

1. Plan → diff checklist (`file:line` or NOT IMPLEMENTED). Reverse: every changed file must be in the plan's file list or be surfaced as scope creep.
2. `python3 .claude/scripts/check-verify-impact.py --stage iteration`, then `/verify` for the reached stacks (quick or full as the issue requires). Unknown impact → all present stacks. On FAIL, **stop** unless `--fix-loop` was requested. `--fix-loop` follows `references/loop-and-qualify.md`: GO/NO-GO, `--snapshot-contract`, then `/ralph-loop` with the **same shell command** you ran (never `/verify`), `--max-iterations 5`, `REQUIRE_VERIFY=true`. After 5 iterations or 3 identical failures the hook writes **ESCALATED**. `WEAKENED` contracts (skipped tests, dropped coverage, swapped verifier) do not complete. Do not commit, push, merge, or start the next issue.
3. Reviewers from SKILLS_GUIDE (code-reviewer plus the domain reviewer). Prefer `/review-code`, which builds a BASE/HEAD or uncommitted package — do not commit merely to obtain a SHA. Independent review is required before `/ship`. Re-review is scoped (open/closed finding owners + newly appearing stacks + security when still applicable).
4. Freeze the tree. `python3 .claude/scripts/check-verify-impact.py --stage frozen`, then `/verify pre-pr`. `/verify quick` is never pre-pr evidence. `/ship` for readiness (does not merge). `/create-pr` to print `gh pr create` (does not run it). Stop at the merge gate.
5. `--finish` / explicit merge keyword → confirm `/ship` READY TO SHIP, then the **human** merges. After merge: board → Done, then unblock dependents (remove this id from their `blocked_by_open` / comment). Do not invoke `/next` again on your own. Do not run `gh pr merge`.

Do not re-implement CI wait loops, reviewer prompts, or merge bash in this skill.

## Resume modes

| Mode | Enters | Stops |
|---|---|---|
| `/next --plan` | discovery → plan saved | plan gate |
| `/next --build #N` | load saved plan → branch → implement → impact `/verify` → `/create-pr` | merge gate (does not merge) |
| `/next --finish #N` | `/ship` readiness (does not merge); after the human merges: board Done + unblock | issue done |
| `/next --fix-loop` | after failing `/verify` only if qualify is GO | merge gate (does not merge; does not pick the next issue) |

`--build` without a saved plan → STOP.
