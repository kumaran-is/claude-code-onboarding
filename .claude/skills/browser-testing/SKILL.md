---
name: browser-testing
description: Browser testing for web targets (Angular, React, any served site, Flutter web builds). playwright-cli for interactive QA (network, console, route mocking, offline, screenshots, traces); @playwright/test for committed CI suites (storageState auth, mocked failure states, axe accessibility, viewports, visual regression, sharding, flaky control); Browser-Use MCP for exploratory goal-driven flows. Use when testing web apps, debugging browser issues, running E2E user flows, or writing Playwright specs. Not for Flutter Android/iOS apps (Maestro).
allowed-tools: Bash, mcp__browser-use__browser_exec, mcp__browser-use__browser_screenshot, mcp__browser-use__browser_login
agent: browser-testing
context: fork
metadata:
  triggers: browser testing, playwright, playwright test, E2E test, browser automation, Browser-Use, UI testing, end-to-end, login flow, axe, visual regression, toHaveScreenshot, flaky test
  related-skills: angular-spa, accessibility-audit, ui-visual-validator, systematic-debugging
  domain: quality
  role: specialist
  scope: testing
  output-format: report
last-reviewed: "2026-11-22"
---

**Iron Law:** Never claim a web UI flow works without running it in a real browser and showing the command, its exit code and the evidence path. Not executed in this session → NOT RUN.

# Browser Testing (web targets)

> **Scope:** web targets only — Angular, React, any served site, or a Flutter **web** build (which says nothing about the Android/iOS app). Flutter Android/iOS UI/E2E uses Maestro CLI/MCP (`.claude/rules/testing-tool-selection.md`); never route a Flutter mobile app here, and never substitute a browser when Maestro or a device is unavailable (report BLOCKED / NOT RUN).

## Which tool

| Need | Tool | Reference |
|---|---|---|
| Committed E2E suite that gates PRs (config, auth, mocked 500/empty/offline, axe, viewports, visual, sharding) | `@playwright/test` (`npx playwright test`) | [playwright-test-suite.md](reference/playwright-test-suite.md) |
| Interactive QA, reproducing a bug, inspecting network/console, quick evidence | `playwright-cli` (Bash, stateful sessions) | [playwright-cli-tools.md](reference/playwright-cli-tools.md) |
| Core Web Vitals, CPU/network throttling, Lighthouse | Chrome DevTools MCP | [chrome-devtools-tools.md](reference/chrome-devtools-tools.md) |
| Exploratory goal-driven flow, cloud browser | Browser-Use MCP (`browser_exec`, `browser_screenshot`) | [browser-use-tools.md](reference/browser-use-tools.md) |
| Unit / component tests | Angular: `ng test` (Vitest via `@angular/build:unit-test`); React: Vitest + React Testing Library | `.claude/rules/testing-tool-selection.md` |

Default to `@playwright/test` for anything that must be repeatable and `playwright-cli` for anything interactive. Cypress is not the toolkit's web E2E tool; keep it only where a repo already runs it.

## Install (pinned)

```bash
npm i -D @playwright/test@1.58.2 @axe-core/playwright@4.11.0   # suite validated here; react-spa ran on 1.65.1 / 4.14.0. Pin what your lockfile resolves
npx playwright install --with-deps chromium
npm i -g @playwright/cli@0.1.25        # binary: playwright-cli (NOT @playwright/mcp, whose binary is playwright-mcp)
playwright-cli install-browser chromium
```

## Quick example (playwright-cli, verified on 0.1.25)

```bash
playwright-cli -s=qa open http://127.0.0.1:4200/login
playwright-cli -s=qa snapshot                          # refs: e5, e9, ...
playwright-cli -s=qa fill e5 "$E2E_USER"               # test account from env, never real credentials
playwright-cli -s=qa fill e6 "$E2E_PASSWORD"
playwright-cli -s=qa click e7
playwright-cli -s=qa requests --filter "/api/"         # POST /api/auth/... => [200]; was `network` in old versions
playwright-cli -s=qa console error                     # any error → NEEDS WORK unless explained
playwright-cli -s=qa screenshot --filename evidence/signed-in.png   # `--filename`, not `--output`
playwright-cli close-all
```

Sign-in is proven by the protected page rendering and the API answering 200 (and 401 after sign-out) — never by a token in `localStorage`.

`file://` URLs are blocked by playwright-cli: serve static HTML (`npx http-server <dir> -p 4310` or `python3 -m http.server 4310`) and open `http://127.0.0.1:4310/...`.

## Server lifecycle — `scripts/with_server.py`

For a server that is not running yet. Run `python scripts/with_server.py --help` first; treat it as a black box. A committed suite uses `webServer` in `playwright.config.ts` instead (see the stale-build guard there: in CI never reuse a server you did not just start).

| Stack | Command |
|-------|---------|
| Angular | `python scripts/with_server.py --server "npx ng serve --port 4200" --port 4200 -- npx playwright test` |
| React (Vite) | `python scripts/with_server.py --server "npx vite --port 5173 --strictPort" --port 5173 -- npx playwright test` |
| Backend + frontend | `python scripts/with_server.py --server "npm run start:dev" --port 3000 --server "npx ng serve --port 4200" --port 4200 -- npx playwright test` |
| Flutter **web** build (web only: says nothing about Android/iOS) | `flutter build web --release`, then `python scripts/with_server.py --server "python3 -m http.server 8080 --directory build/web" --port 8080 -- npx playwright test` |

## Critical rules

1. **Every check must be able to fail.** Prove a new gate with a negative control: plant one violation, the command must exit non-zero. A step that prints "skipped" and exits 0 is NOT RUN, never PASS.
2. **Capture the tool's own exit code** (`npx playwright test; echo "E2E EXIT:$?"`), never the exit code of a `| tail` pipe.
3. **Assert user-visible outcomes with web-first assertions** (`toBeVisible`, `toHaveText`, `toHaveURL`). Never `waitForTimeout`; never `networkidle` (DISCOURAGED in the Playwright types).
4. **Each data screen**: success, empty, 500 and offline cases via `page.route` / `context.setOffline` (suite) or `route` / `network-state-set` (cli). Assert the visible error state.
5. **Authorization**: assert the backend's answer (401/403/200 via `request`), not that a button is hidden.
6. **Accessibility**: `@axe-core/playwright` with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` per UI state. Report "no automated violations; manual checks required" — automated results never prove WCAG compliance.
7. **Phone-sized viewport = web layout evidence only.** Name the project `phone-viewport`, never "mobile"; it is never evidence about a mobile app.
8. **Evidence**: traces/screenshots/video on failure; copy `test-results/playwright/` out before re-running (Playwright wipes `outputDir`). Report evidence paths with the verdict.
9. **Console errors** after a critical action = NEEDS WORK unless explained.
10. **Close sessions**: `playwright-cli close-all`.

## Reference files (load only what you need)

| Resource | When to load |
|----------|-------------|
| [playwright-test-suite.md](reference/playwright-test-suite.md) | Writing or reviewing `@playwright/test` config/specs, CI workflow, flaky policy, visual thresholds, axe |
| [playwright-cli-tools.md](reference/playwright-cli-tools.md) | Full verified command list for `playwright-cli` 0.1.25, recipes for mocking, offline, responsive, evidence |
| [browser-testing-workflows.md](reference/browser-testing-workflows.md) | Step-by-step QA workflows (login, form validation, journeys, responsive, performance) |
| [chrome-devtools-tools.md](reference/chrome-devtools-tools.md) | Core Web Vitals, performance traces, throttling, Lighthouse |
| [api-performance.md](reference/api-performance.md) | API latency and payload checks during browser flows |
| [agentic-debug-loop.md](reference/agentic-debug-loop.md) | Observe → diagnose → fix → re-verify on a live app |
| [browser-use-tools.md](reference/browser-use-tools.md) | The four Browser-Use MCP tools that actually exist |

## Report

Per check: PASS | FAIL | BLOCKED (tool, browser or server unavailable — say which) | NOT RUN (skipped by choice — say why), with the command, its exit code and evidence paths. Do not claim a test, eval or runtime check passed unless you executed it in this session and show the command and its output; otherwise mark it NOT RUN.
