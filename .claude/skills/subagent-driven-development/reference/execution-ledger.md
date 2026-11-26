# SDD execution ledger and independent review package

Loaded by `subagent-driven-development`. Not a lifecycle engine and not AWS AI-DLC state.
NEXUS (`nexus-state-template.md`) remains the 10+ task multi-session coordinator. This
ledger is the per-plan, compaction-resistant task board for a single SDD run.

Inspired by Superpowers SDD helpers (obra/superpowers v7.0.2 MIT,
`22f0b463e7a5e579904dd6211a520321035526f7`). Original implementation.

## Location

```
.claude/temp/sdd/<plan-stem>/ledger.json
.claude/temp/sdd/<plan-stem>/briefs/task-N.md
```

`.claude/temp/` is already gitignored. Do not commit the ledger. Do not put it in
`.git/claude-state/` (enforcement-kit owns that tree). Do not create `.superpowers/`.

A **complete** ledger row is **never verification proof**. Re-run the stack command
named in the task contract and record its exit code with `--mark`.

## Orchestrator steps

After Step 0 parses the plan:

```bash
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py \
  --init --plan docs/plans/YYYY-MM-DD-<feature>.md
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py --next
```

`--init` refuses a plan that fails the task-contract scan (see below). It writes
briefs and creates rows; it does **not** reset an existing task's status.

Before dispatching a task:

```bash
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py --next
```

Skip any task whose status is `complete`, `--verify-exit` is `0`, and reconcile
did not mark it `STALE` or `INCONSISTENT`. Pass the **brief body inline** plus the
brief path. Never tell the implementer to read the whole plan.

After the quality reviewer passes and `/verify` (or the task's verification
command) actually exited 0:

```bash
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py \
  --mark N --status complete --verify-exit 0 \
  --verify-cmd '<stack command>' --files 'a.ts,b.ts'
```

`--mark complete` without `--verify-exit 0` is refused.

## Compaction / session resume

After `/clear`, compaction, or a new session on the same plan:

1. `TaskList` (in-session tasks, if any).
2. `--status` then `--reconcile` (implied by `--status`).
3. `--next` — resume that task. Do not redispatch a verified complete task.
4. If a row is `STALE` or `INCONSISTENT`, treat it as incomplete: re-verify,
   then re-review. Do not overwrite unrelated working-tree files.

Reconcile vs Git:

| Ledger | Working tree / range | Result |
|--------|----------------------|--------|
| complete, verify exit 0, claimed files in `base..head` or dirty | consistent | skip |
| complete, no verify exit 0 | `STALE` — not proof | re-verify |
| complete, claimed files absent from git and disk | `INCONSISTENT` | re-implement or fix the row |
| in_progress, clean tree, no files | `STALE` | confirm with the human before touching files |

Do not `git add` / commit / reset / checkout to make a row look consistent.

## Task briefs

Each `briefs/task-N.md` is the task section copied from `docs/plans/`. The
implementer receives that text **inline**. The file exists so a compacted
orchestrator can recover the contract without the conversation. Updating the
plan and re-running `--init` refreshes brief bodies and adds new tasks; it
does not clobber status.

## Independent review package (SP-003)

Before dispatching spec or quality review (and from `/review-code`):

```bash
python3 .claude/skills/subagent-driven-development/scripts/check-sdd-ledger.py \
  --review-package --uncommitted --task N --plan docs/plans/YYYY-MM-DD-<feature>.md
```

The JSON names `base`, `head`, `uncommitted`, `files`, `review_focus`,
`task_contract`, and `verify`. Give that package to a **fresh** reviewer
agent together with the approved task contract. Do not rely on the
implementer's self-assessment. Do not commit merely to obtain a SHA —
uncommitted diffs are first-class. An empty `BASE..HEAD` with a clean tree
exits 3 (nothing to review). `HEAD` that is not a descendant of `BASE` exits 3.

Route quality review through the existing tech-stack reviewers in `SKILL.md`.
Preserve `/review-code` severity (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW`) and
PR governance. Blocking findings require a fix and a re-run of `--review-package`
plus the same reviewer; then `--mark` with `--findings` closed.

## What this is not

- Not NEXUS phases, not AWS AI-DLC workflow state, not a second planner.
- Not a substitute for `/verify` or `/test-partner`.
- Not permission to skip the human plan-approval or merge gates.
