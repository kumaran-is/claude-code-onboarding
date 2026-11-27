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
- **Test Strategy** — points at `/verify` and the stack's Definition of Done; Flutter Android/iOS E2E is Maestro; web E2E is Playwright CLI/Test (`playwright test` is the gate). Official Playwright Test Agents are conditional `/next` specialists for Angular/React journeys only (`.claude/skills/browser-testing/reference/playwright-test-agents.md`); Chrome DevTools MCP is diagnostics only
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

Flutter UI work still follows `flutter-mobile` + `design-system` (DESIGN.md, tokens, Maestro). Web UI follows `angular-spa` or `react-spa` + `design-system` (Playwright). See **E2E quality contract** below — same gates, framework-specific tools; no extra Maestro agents.

## E2E quality contract (Flutter and web)

Same `/next` gates on every UI journey. Tools differ; the contract does not. Do **not** add Maestro Planner / Generator / Healer agents to match Playwright Test Agents.

| Gate | Flutter Android/iOS | Angular / React |
|---|---|---|
| Plan coverage from approved AC | `/next --plan` + MFRI + `flutter-mobile` | `/next --plan`; product `playwright-test-planner` only when a journey is new or changed |
| Implement | `flutter-mobile` + Riverpod | `angular-spa` / `react-spa` |
| Generate or update E2E for changed journeys | Maestro YAML via `flutter-mobile` E2E Workflow + Maestro MCP; files in `<app>/.maestro/` (`flutter-e2e-maestro.md` §4). Same-PR co-change: §6 | Product `playwright-test-generator` when coverage is missing/stale; else write the spec by hand |
| Execute on real target | `/verify` → `maestro test` on emulator/simulator/device. Missing Maestro/device = **BLOCKED**, never a browser | `/verify` → `npx playwright test --fail-on-flaky-tests`. Missing browser/server = **BLOCKED** |
| Classify a failure, then repair | traps §8: FAIL (app) / TEST_DEFECT (flow) / SETUP_FAIL / INFRA_FAIL. No dedicated healer agent. After a TEST_DEFECT YAML edit: `python3 .claude/skills/next-issue/scripts/check-next-issue.py --scan-skip-delta <edited flows>` (new `optional: true` = WEAKENED) | App bug → stack skill / `--fix-loop`. Test/selector/timing → product `playwright-test-healer` only after diagnosis; then `--scan-skip-delta` on edited specs |
| Never weaken to go green | No `optional: true` on required checks; no deleted checkpoints (`flutter-e2e-maestro.md` §5) | No `test.fixme` / skip / weaker `expect()` |
| Independent review + ship | `/review-code` (incl. Maestro co-change) → `/verify pre-pr` → `/ship` → human merge | `/review-code` (incl. healer edits) → `/verify pre-pr` → `/ship` → human merge |

Cosmetic / unit-only work skips E2E generation. Unrelated stacks skip the other framework's runner.

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

## Web E2E Test Agents (conditional, Angular/React only)

Load `.claude/skills/browser-testing/reference/playwright-test-agents.md` for Planner/Generator/Healer triggers. Not a parallel E2E lifecycle. Missing product agents → write specs by hand; mark those agents **NOT RUN**. After Healer, `--scan-skip-delta` on edited specs (new `test.fixme`/`test.skip` = fail), then the same `playwright test` command. Do not invoke all three agents on every change.

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
