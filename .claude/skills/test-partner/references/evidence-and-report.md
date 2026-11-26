# Partner testing — evidence, ledger, QA report

## Redaction

Redact on the way in. Tokens, passwords, auth headers, connection strings, and personal names that are not part of a documented test persona never land in the ledger. Screenshots that show secrets are cropped or omitted.

## Ledger format (append-only)

```markdown
# test-partner — <target> / <flow> / <device>

build: <git sha + runtime versions>
tools: <maestro | playwright-cli | …>  (from check-test-partner.py --select-tools)
env: local/dev/test confirmed

## Scenario board — session 1 (<UTC>)
| ID | Scenario | Status | Finding | Evidence |
|---|---|---|---|---|
| S1 | Happy path | TODO | | |

## S1 — <action>
evidence:
- UI:
- Device/Browser:
- Request:
- Canonical:
- Local:
- Notify:
- Trace:
- Observability: PASS | PARTIAL | FAIL | N/A
- Screenshot:
verdict: expected | finding #k | needs-repro | PARTIAL

## Findings

### F1 [MAJOR] <screen/flow>
observed:
expected:
repro:
evidence:
root cause:
fix / tests:
retest: PENDING
status: OPEN
```

Severity: `BLOCKER` (flow cannot complete, or security/safety) · `MAJOR` (wrong behaviour, workaround exists) · `MINOR` (cosmetic) · `NOTE` (documented surprise) · `UNVERIFIED` (observation without evidence).

Validate with:

```bash
python3 .claude/skills/test-partner/scripts/check-test-partner.py --check-ledger <ledger>
```

Promote confirmed findings to an issue, DESIGN.md/Screen Guide, or a committed Maestro / Playwright regression. Raw session logs are not product docs.

## Coverage floor (every walk)

Happy path **and** the failure paths that belong to this flow. Also reach, or explicitly skip with reason:

- loading / empty / error (a blank screen is not an empty state)
- accessibility spot check (target size, contrast in both themes if they exist, one screen-reader or keyboard pass)
- i18n extra locale if the app ships one
- offline/online transitions if the product claims them
- authorization / isolation if more than one role exists

Expected behaviour source order: architecture/domain rules → DESIGN.md / product docs → story AC → existing tests → current implementation. If undocumented, record a docs-gap finding.

## Phase 6 — QA report

```text
Target / flow / device · tools used
Coverage : offline ☐ · extra locale ☐ · a11y ☐ · loading/empty/error ☐ · observability ☐
Driven    : <n> state advances by Claude (method) — or none
Findings by severity · visual evidence captured? · open findings
Fixes applied · tests/gates run · re-walk result
```

An unticked box is a coverage statement, not a failure — say what was not walked.

## Not this skill

| Need | Use |
|---|---|
| Scripted Flutter E2E | Maestro via `flutter-mobile` |
| Scripted web E2E | `browser-testing` |
| Known defect, root cause | `systematic-debugging` / `/debug` |
| Build+test exit codes | `/verify` |
| Pick next implementation task | `/next` |
