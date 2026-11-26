# Partner testing — session protocol

Loaded for every interactive walk where the developer answers **pass / fail / shot**, asks for a mid-walk fix, or resumes a ledger.

## 1. One step card, then wait

```text
S<n> — <scenario name>
Precondition : <device/browser + backend state, verified not assumed>
Do           : <one action, in the product's own words>
Expect       : <what the UI must show>
I will check : <Maestro tree / Playwright snapshot / log / API / DB>
Reply pass / fail / shot
```

Take a UTC watermark **before** sending the card. Never stack a second step behind an unanswered one. If the precondition is false, fix setup (with approval) instead of starting the step.

## 2. PASS / FAIL / SHOT

| Reply | Claude does |
|---|---|
| **pass** | Gather the other source anyway. PASS only under the two-source rule. |
| **fail** | Capture screenshot + logs since watermark, record the finding, ask: fix now or continue. |
| **shot** | Capture the screen, **Read** the image, compare to Expect, add the other source, verdict. |

A visual or accessibility defect does **not** need a backend failure to be valid.

## 3. Two-source rule

A screenshot alone or logs alone never make a PASS.

- UI claim → UI evidence **and** a canonical source (API/DB, Playwright request log, Maestro assertion, or explicit `N/A` with why).
- One side only → `PARTIAL`.
- Backend `200 []` is not automatically success.

## 4. Scenario board and resume

Ledger path: `.claude/state/test-sessions/YYYY-MM-DD-<target>-<flow>-<device>.md`

Confirm the directory is gitignored (`git check-ignore -q .claude/state/test-sessions/` — this toolkit ignores `.claude/state/`). **Append only.** Never `Write` over a ledger created in an earlier session.

At start, append the planned scenarios (`TODO`). After each scenario append `STATUS <id> PASS|FAIL|…`. Resume = read the newest summary plus every `STATUS` / finding line after it, then re-run preflight. Do not trust the first board table (it goes stale).

## 5. No unasked state change

Propose, wait, act. Driving a record to the next lifecycle state, resetting the app, toggling airplane mode, or seeding data all require an explicit go-ahead **this turn, for this record**. "We are testing this flow" is not permission.

Resolve legal transitions from **code** (enums, allowed-transition maps, OpenAPI), never from memory. Prefer the real product API as the acting role. Direct SQL `UPDATE` skips guards, history, and notifications — it is not evidence the product performs the transition. Mark driven steps `DRIVEN`.

## 6. Quick-fix loop (only when asked for THAT finding)

1. `systematic-debugging` / `/debug` for root cause.
2. Smallest fix + the missing test.
3. Rebuild / reload (Flutter: relaunch the app under test; web: hard refresh or restart the dev server; backend: recreate the changed process).
4. Re-walk the **exact** failing step on the same target.
5. Nearby regression paths.
6. Ledger: before/after evidence, `retest: PASS|FAIL`.

A fix not re-walked stays `OPEN`. Leave changes uncommitted unless asked.

## 7. Offline / online

Walk the selected flow online, then the transitions that matter: go offline mid-flow, retry, come back online, conflict/queue behaviour if the product claims it. Record radio / Playwright offline flag in the step evidence. Skip only when the flow is documented online-only — say so in the Phase 6 report.

## 8. Stop conditions

Say so plainly:

- The app is talking to a different backend than the developer thinks.
- Cannot tell whether this is a finding → `needs-repro`.
- Expected behaviour is undocumented → documentation-gap finding; do not invent the spec.
- Evidence is from before the fix → rerun.
- Local state and backend disagree → investigate sync/auth before continuing.
