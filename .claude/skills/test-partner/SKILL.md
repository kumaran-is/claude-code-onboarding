---
name: test-partner
description: "Use when the user says /test-partner, partner testing, paired testing, manual walkthrough, physical device QA, pass fail shot, watch logs while I test, or resume a QA session. Claude is the live QA partner: one step at a time, the developer acts, this skill watches UI/logs/backend, records a findings ledger, suggests fixes only when asked, and verifies retests. Flutter Android/iOS uses Maestro; web (Angular, React, other) uses Playwright CLI/Test; Chrome DevTools MCP is diagnostics. Not scripted E2E (browser-testing / Maestro suites) and not /debug (known defect root-cause)."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
argument-hint: "[--target flutter-android|flutter-ios|angular|react|web] [--flow <name>] [--device auto|<id>]"
metadata:
  domain: testing
  role: orchestrator
  scope: session
  triggers: test-partner, partner testing, paired testing, manual walkthrough, physical device QA, pass fail shot, resume QA session, watch logs while I test
  related-skills: browser-testing, systematic-debugging, flutter-mobile, accessibility-audit
last-reviewed: "2026-11-26"
---

# Test Partner — paired manual testing

## Iron Law

**NO FINDING WITHOUT EVIDENCE.** Evidence must match the failure type — UI observation, screenshot, semantics, platform logs, request/response, service logs, traces, canonical state. If evidence is insufficient, tag `UNVERIFIED` / `needs-repro`.

**NO UNASKED FIX — AND NO UNASKED STATE CHANGE.** A finding is fixed mid-walk only when the developer asks for **that** finding. Otherwise it waits until the walk ends.

**NO PASS ON ONE SOURCE.** A screenshot alone or logs alone never make a PASS. One side → `PARTIAL`.

**CURRENT IMPLEMENTATION IS NOT THE SPEC.** Expected behaviour comes from architecture, DESIGN.md / product docs, acceptance criteria, and tests — then current code.

## What this is

The developer is the actor. Claude is the live test partner:

```text
Developer acts on device or browser
        ↓
Claude watches: UI · logs · canonical API/DB · notifications · offline queue
        ↓
Evidence → discuss → ledger updated immediately
        ↓
Fix only when asked, then re-walk the failing step
```

Not `browser-testing` (scripted Playwright), not Maestro suites, not `/debug` (root cause of a known defect — used in Phase 5). No Playwright MCP and no Browser Use MCP.

## Reference dispatch

| When | Read |
|---|---|
| target / tools / offline radios | `references/adapters.md` |
| step cards, pass / fail / shot, resume, quick-fix | `references/qa-session-protocol.md` |
| ledger, redaction, coverage floor, QA report | `references/evidence-and-report.md` |

# Phase 0 — Preflight

Do not begin until the developer confirms preflight.

```bash
python3 .claude/skills/test-partner/scripts/check-test-partner.py --selftest
python3 .claude/skills/test-partner/scripts/check-test-partner.py --detect-target --root .
python3 .claude/skills/test-partner/scripts/check-test-partner.py --select-tools --target <target>
```

1. **Target** — from `--target` or auto-detect (`pubspec.yaml`+`android`/`ios` → Flutter + **Maestro**; `angular.json` → Angular + **Playwright**; React `package.json` → Playwright; other served sites → Playwright; Flutter web → Playwright and say so). Unknown → BLOCKED.
2. **Stack** — `docker compose ps` / process list from **this** repo. Missing required services → stop and report. Do not invent container names.
3. **Device / browser** — resolve a live id (Maestro `list_devices`, `adb devices`, Playwright session). Prove reachability before the first action.
4. **Environment** — local/dev/test only. Direct SQL is read-only. No destructive commands unless the developer asks and confirms non-production.
5. **Ledger** — `git check-ignore -q .claude/state/test-sessions/` must succeed, then `mkdir -p .claude/state/test-sessions`. Path: `.claude/state/test-sessions/YYYY-MM-DD-<target>-<flow>-<device>.md`
6. **Intent** — if `--flow` is omitted, ask which flow and which outcome. Stay scoped. Do not expand into a full regression suite.

# Phase 1 — Baseline

Record git SHA, runtime versions, device/OS or browser, flow, UTC watermark, canonical row state, local/offline state if inspectable. Prefer product read APIs for actor-visible truth.

# Phase 2 — Paired loop

For every developer action, send **one** step card (`references/qa-session-protocol.md`) and wait for pass / fail / shot.

Then inspect with the selected tools only:

- Flutter Android/iOS → Maestro tree + screenshot; `adb` / `simctl` / `flutter logs`; owning service logs.
- Angular / React / web / Flutter web → Playwright CLI snapshot + screenshot + `console`/`requests`; Chrome DevTools MCP when the question is performance or deep diagnostics.

Return:

```text
STEP n — <developer action>
UI          : <observed state>
Device/Browser: <Maestro / Playwright / platform evidence>
Request     : <service> <method> <path> <status> | none observed
Canonical   : <API/DB before → after>
Local       : <queue / persisted client state if applicable>
Trace       : <correlation id if present>
Observability: PASS | PARTIAL | FAIL | N/A
Verdict     : expected | finding #k | needs-repro
```

Append every finding to the ledger immediately, redacted.

# Phase 2B — Driving state (only when asked)

Propose, wait, act. Resolve legal transitions from live code. Prefer the real product API as the acting role. Driven transitions are never evidence the product performs them — mark `DRIVEN`.

# Phase 3 — Coverage

Happy path and the failure paths that belong to this flow. Surface quality (loading/empty/error, a11y spot check, extra locale if shipped) on every walk. Offline/online transitions when the product claims them (`references/adapters.md`, `references/evidence-and-report.md`).

If the flow has no documented minimum, write three lines into the ledger before walking: canonical record + owning service; who else should see the result and how you will observe them; the failure this flow must not have.

# Phase 4 — Ledger

Append-only file under `.claude/state/test-sessions/`. Format and severity: `references/evidence-and-report.md`. Never `Write` over a ledger from an earlier session.

# Phase 5 — Triage and fix

After the developer ends the walk — or for one finding they ask to fix now:

1. Summarize by severity; deduplicate; ask which to pursue.
2. `systematic-debugging` / `/debug`.
3. Smallest fix + missing test.
4. Rebuild / relaunch the **same** target (otherwise you retest the old build).
5. Re-walk the exact failing step.
6. Nearby regressions; update `retest:` in the ledger.
7. Leave changes uncommitted unless asked.

A fix not re-walked stays OPEN.

# Phase 6 — QA report

Return the Phase 6 block in `references/evidence-and-report.md`. Unticked coverage is a statement, not a failure.

## Verify

```bash
python3 .claude/skills/test-partner/scripts/check-test-partner.py --selftest
python3 .claude/skills/test-partner/scripts/check-test-partner.py --scan-skill
```

A session is complete only when:

- [ ] every step has a `STEP n` block with evidence
- [ ] every finding is in the ledger with severity, repro, evidence
- [ ] no fix was applied before the developer asked
- [ ] each applied fix was re-walked on a rebuilt target
- [ ] the Phase 6 report is returned in full
- [ ] Flutter Android/iOS used Maestro; web used Playwright; Chrome DevTools MCP only for diagnostics
