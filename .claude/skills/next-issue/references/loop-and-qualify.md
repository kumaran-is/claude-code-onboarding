# `/next --fix-loop` — opt-in bounded fix/retest (not a new harness)

Loaded by `next-issue`. Uses existing `/ralph-loop`, `/verify`, `/review-code`, and `/ship`.
Does **not** start the next issue after this one. Does **not** commit, push, or merge.

## When it runs

Default `/next` still stops after a failing `/verify` and reports. `--fix-loop` is the
only unattended inner retry. `--plan` and merge remain human gates in every mode.

## Qualification (GO / NO-GO)

Before starting Ralph, write a payload and run:

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py --qualify /tmp/next-qualify.json
python3 .claude/skills/next-issue/scripts/check-next-issue.py --validate-verify-cmd "$CMD"
```

Exit 0 = **GO**. Exit 1 = **NO-GO** — stop, show `reasons`, and wait for a human.
Do not start `/ralph-loop` on NO-GO.

NO-GO when any of: missing or ambiguous acceptance criteria; `/verify` (or any slash
command) as `--verify-cmd`; no-op (`true`, `:`, `exit 0`); auth/payments/secrets/production
data; destructive git/merge/reset; permission bypass; `max_iterations` > 5; not machine-testable.

`--verify-cmd-for flutter|angular|react|python|java|spring|nestjs` prints a **template**
from `verify.md`. Prefer the exact stack command you just ran. Never pass `/verify`.

## Contract snapshot (test integrity)

After GO, snapshot the approved acceptance criteria, the exact verifier, named tests,
and any quality-config files (coverage thresholds, lint floors). Store the JSON in
existing `.claude/ralph-state.local.md` under `## Contract snapshot` — not a new store.

```bash
python3 .claude/skills/next-issue/scripts/check-next-issue.py \
  --snapshot-contract /tmp/next-qualify.json --root "$CLAUDE_PROJECT_DIR"
```

Copy `ac_sha256` and `verify_cmd_sha256` into the Ralph loop frontmatter (`RALPH_AC_SHA256`,
`RALPH_VERIFY_CMD_SHA256`). The Stop hook re-runs `--check-contract` on a completion
promise. `WEAKENED` (skipped tests, deleted assertions, swapped verifier, dropped
coverage floor, altered AC) rejects the promise and is **ESCALATED**. Extra `expect()` /
`assert` from TDD is OK (`tdd_added`) but `human_required` stays true — `/review-code`
is the independent review. Quality-config edits are also gated live by
`check-quality-config-weakening.py` (pre-edit); a floor drop is `WEAKENED` even if
the edit landed.

A model-written PASS in the transcript is not evidence. Only the hook-run verifier
(command, exit code, timestamp, tree fingerprint under `## Last verify`) counts.

## Inner loop (only after GO and a failing `/verify`)

```bash
/ralph-loop "fix /verify failures for #<N>; do not commit, push, or merge" \
  --max-iterations 5 \
  --completion-promise "VERIFY GREEN" \
  --verify-cmd '<the same shell command that just failed>'
```

Fill `require_verify=true` (`REQUIRE_VERIFY=true` in the Ralph setup block) and
`MAX_ITERATIONS=5`. Fill `SESSION_ID` from `CLAUDE_SESSION_ID` (or the current
session id). Empty session ids are fail-closed when `require_verify` is set.
Promise-only completion is disabled. After 5 iterations or 3 identical
failures, the hook writes **ESCALATED** — do not emit a false promise.

Then `/review-code` (required independent review) → `/ship` → **stop**. Merge still
needs an explicit human keyword. Do not start the next issue. Do not invoke `/next`
again on your own.
