# `/next --auto` — opt-in multi-story coordinator (not a third mode)

Loaded **only** when the exact token `--auto` is present in `$ARGUMENTS`.
`--auto` must **never be activated implicitly** (not by “run autonomously”,
`--autoresearch`, `--fix-loop`, Auto mode, or an issue title containing “auto”).

HITL `/next` (no `--auto`) is unchanged: plan approval, print-only `/create-pr`,
human merge keyword, no next-issue chaining. This file does not apply there.

## Scope (required, fail-closed)

`--auto` without an explicit scope is **BLOCKED**. Whole-board automation is forbidden.

| Flag | Scope |
|---|---|
| `--wave N` | Issues whose Wave field is N |
| `--milestone NAME` | Issues in that milestone |
| `#N #M …` | Exactly those issue numbers |

Freeze the set with a fingerprint. **Do not silently expand** it if the board
gains issues. Extra wave/milestone items → `BLOCKED` (scope expansion). Recheck
before every story.

Optional budgets (defaults in the coordinator): `--max-stories`, `--max-duration-hours`,
`--max-story-attempts` (3), review rounds (3). Cost USD is **not metered**.

Cancel: `/next --auto --cancel`. Recover a dead lock: `/next --auto --recover`.
`/cancel-ralph` cancels only the inner Ralph loop.

## Coordinator

Durable state lives in `.git/claude-state/next-auto/` (existing claude-state
tree, not a new working-tree store). The Stop hook
`.claude/hooks/stop-next-auto.sh` resumes **without re-prompting** while this
session is alive. A killed Claude Code process does not continue until a human
re-invokes `/next --auto` (resume from state) or a live session’s Stop hook fires.

```bash
python3 .claude/skills/next-issue/scripts/check-next-auto.py --selftest
python3 .claude/skills/next-issue/scripts/check-next-auto.py --scan-skill
python3 .claude/skills/next-issue/scripts/check-next-auto.py --has-auto-flag -- $ARGUMENTS
# must print AUTO; otherwise this file does not apply

python3 .claude/skills/next-issue/scripts/check-next-auto.py \
  --start --session "$CLAUDE_SESSION_ID" --scope-file /tmp/next-auto-scope.json \
  --items /tmp/next-auto-items.json
```

`--start` / `--advance` take a flock lock. A second coordinator for the same
scope is `CONCURRENT` → stop. Inner `/ralph-loop` owns Stop while
`.claude/ralph-loop.local.md` exists; this outer hook no-ops then.

## Per-story pipeline (one at a time)

Reuse HITL steps; only the human gates are replaced.

1. **Discover** in-scope issues (`references/discovery.md`). Parse GitHub
   `Blocked by: #N` / `blocked_by_open`. Unknown deps → fail-closed (that story
   is not ready).
2. **Order** with `--order` / `--next-ready`: topological, then existing
   `pick_next` (layer, lowest number) among independent stories. Cycles →
   `BLOCKED` for the cycle. Never start a dependent story before the
   prerequisite’s **confirmed merge SHA**.
3. **Qualify** `--qualify-auto` (reuses GO/NO-GO). High-risk, auth/payments,
   ambiguous AC, or `needs human review` → `BLOCKED` (do not downgrade).
4. **Plan** automatically. Scan with `check-sdd-ledger.py --scan-plan`. Plan
   verdict must be Approve. Revise/Block → `BLOCKED`, do not self-approve a bad plan.
5. **Implement** via stack skills (Sonnet). Seed implementation notes. Follow the
   E2E quality contract in `plan-and-handoff.md`. Angular/React Playwright Test
   Agents stay conditional; Flutter Maestro stays `flutter-mobile` + MCP (no extra
   agents). Do not invoke Planner+Generator+Healer on every story.
6. **Verify** `check-verify-impact.py --stage iteration` then `/verify`
   (`playwright test` / `maestro test` are the gates). Classify failures before
   `--fix-loop`; Healer only after a diagnosed Playwright test defect.
7. **Auto-fix** only after GO: existing `--fix-loop` / Ralph max 5,
   `require_verify`, contract snapshot, WEAKENED → ESCALATED. Ralph still does
   not chain issues; this coordinator does after merge confirm.
8. **Independent review** `/review-code` (Opus reviewers). Scoped re-review.
   Round cap 3; then `BLOCKED`.
9. **Remediate**, re-verify, re-review within caps.
10. **Frozen gates** `--stage frozen`, `/verify pre-pr`, security lock, `/ship`
    READY TO SHIP. Enforcement-kit stamps must be VALID.
11. **Create PR** after `/create-pr` has written the body: this mode **runs**
    `gh pr create` (HITL still only prints it). Idempotent: reuse an open PR
    for the head branch (`--pr-idempotent`). Do not open a second PR. Push the
    branch first so CI can run. Do not commit secrets.
12. **Wait for CI** `gh pr checks <PR> --watch --fail-fast`. Pending → WAIT
    (recheck). Failed required checks → `BLOCKED`.
13. **Merge** only when `--merge-gate` prints `ALLOW`. Then
    `gh pr merge <PR> --squash --delete-branch`. **Never** `--admin`,
    `--force`, check skip, self-approve, or ruleset bypass. If reviews are
    required and no independent approval exists, report `BLOCKED` and stop.
    Protected branches stay protected.
14. **Confirm** merge SHA on the target branch (`--confirm-merge`) before
    advancing. Then board Done.
15. **Continue** the next dependency-ready story, or write the final report
    when the approved scope is complete.

`--advance --event EVENT.json` after every phase. Events: `phase_ok`,
`nogo`, `verify_fail`, `escalated`, `review_fail`, `pr_created`, `pr_reused`,
`ci_pending`, `ci_fail`, `merged`, `confirmed`, `merge_blocked`,
`approval_missing`, `stale_verify`, `cancel`, `refresh_issues`.

## GitHub safety

This coordinator **never** calls `gh`. The model calls `gh` only after the
script ALLOWs it. Simulated tests use fixtures; they are not real GitHub
validation.

- Correct source and target branches (`expected_base`).
- PR head SHA == local HEAD.
- VALID verify + review stamps (enforcement kit still denies otherwise).
- No unresolved blocking findings.
- No conflicts / `BEHIND` / `DIRTY` (do not force).
- Required checks completed successfully on the **current** revision.
- Required external approvals present when configured.

## Stop conditions

Stop and persist `blocked` / `cancelled` / `complete` when: scope done; NO-GO;
Ralph ESCALATED / WEAKENED; review cap; CI fail; missing external approval;
protected-branch denial; concurrent coordinator; duration / story / hook
budget; Stop-hook platform cap (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`); cancel.

A Stop-hook cap interrupt is **not** complete — re-invoke `/next --auto` to
resume the same state.
