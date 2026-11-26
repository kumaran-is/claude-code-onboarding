# `/next` and Partner Testing — verification

Date: 2026-11-26
Property Harbor: read-only reference
Toolkit: claude-code-onboarding

## Comparison matrix

| Capability | Property Harbor | Existing Toolkit | Gap | Action | Verification |
|---|---|---|---|---|---|
| `/next` | Skill `next-issue`: GitHub Project waves, assignee/blocker filters, layer buckets, `--plan`/`--build`/`--finish`, implement→CI→merge (PH `make` gates, env-preflight) | Empty stub `.claude/skills/next-issue/`; `/status-check`, `/project-status`, `/checkpoint`, `/verify`, `/ship` are **not** equivalent | No pick-next orchestrator; stub directory had no SKILL.md | Filled `next-issue` as framework-agnostic `/next`; ranking in `scripts/check-next-issue.py`; handoff to existing `/verify` + `/ship` (no duplicate merge pipeline, no product paths) | Selftest PASS; independent fixture picked `#10` foundation over blocked/assigned/epic/frontend; `lint-skills` PASS; skill-reviewer PASS |
| Partner Testing | Skill `test-partner`: paired device QA, pass/fail/shot, ledger, PH docker/seed/Stripe/Drift/personas, Maestro + dart-mcp | `browser-testing`, Maestro routing, `/debug` — scripted E2E or known-defect RCA, not a live QA partner | No paired-walk protocol, ledger, fix/retest loop, or QA report | Added `test-partner` + `/test-partner`; adapters Flutter→Maestro, web→Playwright, CDP diagnostics; gitignored ledger under `.claude/state/` | Selftest PASS (detect, Maestro vs Playwright negatives, ledger); `lint-testing-tools` 0 violations; skill-reviewer PASS |

## What was reused (not duplicated)

- `/verify`, `/ship`, `plan-mode-review`, SKILLS_GUIDE stack dispatch
- `browser-testing` for scripted web E2E; Maestro via `testing-tool-selection.md`
- `systematic-debugging` / `/debug` as Phase 5 RCA
- `.claude/state/` already gitignored

## Remaining gaps (by design)

- PH `make env-preflight`, seed-world, Stripe TEST, Drift/WAL, tenant cost-privacy, Spanish pass, Hermes/Telegram outer loop — product-specific; not ported
- GitHub Project GraphQL mutations run only when the consuming repo has live project config; no hardcoded owner/repo
- HTML plan companion (`--html`) not ported; `--plan` writes markdown SSOT only
- No second command alias `/next-issue` (would duplicate `/next`)

## Tests executed

| Check | Result |
|---|---|
| `check-next-issue.py --selftest` | EXIT 0 |
| `check-test-partner.py --selftest` | EXIT 0 |
| Independent `--pick` fixture (epic + other-assignee + blocker + migration + react) | picked `10` `foundation` |
| `--select-tools --target react` | Playwright; Maestro forbidden |
| `--select-tools --target flutter-ios` | Maestro; Playwright + CDP forbidden |
| `lint-skills.sh --dir next-issue` | 1 passed, 0 failed |
| `lint-skills.sh --dir test-partner` | 1 passed, 0 failed |
| `lint-testing-tools.sh` | 0 violations |
| `check-context-budget.sh --strict` | PASS (always-loaded unchanged) |
| `git check-ignore .claude/state/test-sessions/` | IGNORED |
| `.claude/settings.json` | unmodified |
| skill-reviewer (both skills) | PASS 10/10 each |

## Status

**PASS** — both workflows are reusable, product-agnostic, routed from `/next` and `/test-partner`, and independently verified.
