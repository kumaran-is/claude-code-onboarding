# Playwright Test Agents (Planner / Generator / Healer)

Official Playwright Test Agents ([test-agents](https://playwright.dev/docs/test-agents)) are **conditional specialists inside `/next`** for **product Angular/React apps** after `init-agents`. They are not a second E2E lifecycle, not a substitute for `/verify`, and not Flutter Android/iOS tooling (`.claude/rules/testing-tool-selection.md`). Flutter uses the same `/next` **E2E quality contract** (`next-issue/references/plan-and-handoff.md`) with Maestro CLI/MCP — do not invent Maestro Planner/Generator/Healer agents to match these. Marketing sites still use Playwright CLI/Test; they do not get these agents unless the product repo ran `init-agents`.

The deterministic engine stays `@playwright/test`: `/verify` and CI run `npx playwright test --fail-on-flaky-tests`. Interactive exploration stays Playwright CLI. Diagnostics stay Chrome DevTools MCP.

Verified 2026-11-27 on `@playwright/test@1.65.1` (`npx playwright init-agents --help`: `--loop` choices `claude|codex|copilot|opencode|vscode|vscode-legacy`). Isolated Angular 22, React (create-vite 9.3.4), and bare Playwright fixtures:

| Artifact | First run (no file) | Re-run / existing file |
|---|---|---|
| `.claude/agents/playwright-test-{planner,generator,healer}.md` | created | **overwritten** (custom edits to those three names are lost; other agent files are left alone) |
| `.mcp.json` | **created** with only `mcpServers.playwright-test` (`npx playwright run-test-mcp-server`, **not** `@playwright/mcp`) | **replaced** — other servers (`chrome-devtools`, `github`, `firebase`, …) are deleted |
| `seed.spec.ts` | written under Playwright `testDir` (`e2e/seed.spec.ts` when `testDir: './e2e'`; else repo-root `seed.spec.ts`) | **left unchanged** if already present |
| `specs/README.md` | created | left in place (log omits it on re-run) |
| `CLAUDE.md`, custom `.claude/agents/*.md` | untouched | untouched |
| `playwright.config.ts` | not created | not created |

Official docs do not mention `.mcp.json`. Observed: `--loop=claude` always writes it. Missing Playwright on PATH/`npx --no-install` → exit 1. Invalid `--loop` → exit 1. Regenerated after a Playwright upgrade; the generated files are version-matched to the installed runner.

## Kit vs product repo

| Location | Policy |
|---|---|
| This toolkit | **Do not** run `init-agents`. **Do not** copy the three agents into `.claude/agents/`. **Do not** add a `playwright-test` server to kit `.mcp.json`. Lint R8 fails closed if those land here. |
| Product Angular/React app | Pin `@playwright/test@1.65.1`, then the **backup → init-agents → merge** sequence below. Never run `init-agents` against this toolkit tree. |

If `.claude/agents/playwright-test-planner.md` (and generator/healer) are missing, **or** this session has no `playwright-test` MCP tools (`planner_setup_page`, `generator_write_test`, `test_debug`), treat Planner/Generator/Healer as **NOT RUN** (say why). Write or update specs by hand from [playwright-test-suite.md](playwright-test-suite.md). Do not invent a kit-local copy of the agents, and do not add that server to the toolkit `.mcp.json`.

`playwright-cli install --skills` is a **different** install (Playwright CLI skill). It remains forbidden in this toolkit (`SKILL.md` "Official agent skill").

## When each agent runs

Do **not** invoke all three on every change. Unrelated edits, copy/token tweaks, and unit-only work skip them.

| Agent | Trigger | Skip when |
|---|---|---|
| **Planner** (`playwright-test-planner`) | `/next --plan` (or an approved plan) for a **new or significantly changed user journey** (auth, routing, a form that submits, checkout/onboarding, error/empty/offline UI) | Cosmetic UI; no journey change; agents not installed |
| **Generator** (`playwright-test-generator`) | After implementation, **relevant E2E coverage is missing or outdated** (no spec for the journey, or the spec does not match the new UI) | Specs already cover the AC; unit tests suffice (`web-frontend.md` "When a UI change needs a Playwright Test spec") |
| **Healer** (`playwright-test-healer`) | A Playwright failure has been **diagnosed as a test/selector/timing defect** (stale locator, missing `toPass`, seed drift) | The failure is an **application bug**; diagnosis is incomplete; you have not reproduced with `playwright test` |
| **Regular Playwright** | Any Angular/React change that `/verify` impact selects | Never skip the gate for a reached web app that has `playwright.config.*` |

## `/next` → `/verify` → `/review-code` → `/ship`

```
/next --plan     → Planner (if journey changed) → human approve
implement        → angular-spa / react-spa (production code)
                 → Generator (if coverage missing/outdated)
/verify          → npx playwright test --fail-on-flaky-tests   # not the agents
                 → on FAIL: diagnose first (debug.md)
                 → Healer only for a verified test defect
                 → application bugs go to the stack skill / --fix-loop, never Healer
/review-code     → pr-test-analyzer + code-reviewer (healer edits included)
/ship            → same Playwright gate as /verify; agents are not evidence
human PR/merge
```

Ralph `--fix-loop` is for **application** `/verify` failures after GO. Do not pass Healer into Ralph. `WEAKENED` contracts (skipped tests, deleted assertions) already reject the completion promise (`loop-and-qualify.md`).

## Healer overlay (overrides the generated agent)

The generated healer is allowed to edit tests, will keep going until green, and will `test.fixme()` a case it believes is "the test is correct but still fails". **This kit forbids that path.**

After a failing `playwright test`:

1. Reproduce: command, exit code, trace / `error-context.md` (`SKILL.md` "Debugging a failing Playwright test").
2. Diagnose: application bug vs test defect. If unsure, it is an application bug.
3. **Application bug** → fix production code. Do not dispatch Healer. Do not skip, `test.fixme()`, `test.skip()`, or delete/weaken `expect()`.
4. **Test defect** (and the product healer agent exists) → dispatch `playwright-test-healer` with the failing spec path and the diagnosis. Allowed edits: locators, auto-waiting, seed/setup, comments. Then `python3 .claude/skills/next-issue/scripts/check-next-issue.py --scan-skip-delta <edited specs>` (exit 1 = WEAKENED: new `test.fixme` / `test.skip`). Re-run the same `playwright test` command; exit 0 and executed > 0 required. A green suite with a new `fixme` is not a pass.
5. Healer output still goes through `/review-code`. `pr-test-analyzer` treats new `test.fixme` / `test.skip` / removed assertions as coverage loss.

Never: hide a real bug, broaden a matcher so both the old and new (wrong) UI pass, set `retries` to silence flake, or `--pass-with-no-tests`.

## Dispatch (product repo)

The agents live under the **product** `.claude/agents/` after `init-agents`. Load this reference from `/next`, then dispatch the matching `playwright-test-*` agent (Claude Code `Agent` tool) when the trigger hits. The kit `browser-testing` agent stays read-only (CLI + suite evidence); it does not generate or heal specs.

Planner uses `planner_setup_page` then `planner_save_plan`. Generator uses `generator_setup_page`, `generator_read_log`, `generator_write_test`. Healer uses `test_list` / `test_debug` / `test_run`. Those tools are served by `npx playwright run-test-mcp-server` (MCP server name `playwright-test`).

## Scaffold hint (product repo only)

Human-approved, never from this toolkit tree. `init-agents --loop=claude` **replaces** `.mcp.json`; backup first.

```bash
# KIT = this onboarding repo checkout (session that ran the scaffold), not the product app
set -euo pipefail
if [ -f .mcp.json.bak ]; then
  echo "refusing to overwrite .mcp.json.bak — merge it or remove it first" >&2
  exit 1
fi
[ -f .mcp.json ] && cp .mcp.json .mcp.json.bak
npx playwright init-agents --loop=claude
if [ -f .mcp.json.bak ]; then
  python3 "$KIT/.claude/skills/browser-testing/scripts/merge-playwright-test-mcp.py" \
    --backup .mcp.json.bak --generated .mcp.json --write .mcp.json \
    || { cp .mcp.json.bak .mcp.json; exit 1; }
fi
```

`$KIT` is this toolkit checkout (the session that ran `/scaffold-angular-app` or `/scaffold-react-app`). A product repo that does not have the script: copy `.mcp.json.bak` servers back by hand, then set `mcpServers.playwright-test` to `{ "command": "npx", "args": ["playwright", "run-test-mcp-server"] }`. Do not leave `.mcp.json` as the generated one-server file if the backup had other servers. Delete `.mcp.json.bak` after a successful merge. Gitignore `playwright/.auth/` and `.playwright-cli/` as usual.
