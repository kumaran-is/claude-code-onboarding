# Browser E2E Testing

> **Scope:** web targets (Angular, React, websites, Flutter web builds). Flutter Android/iOS UI/E2E is Maestro-only, see Phase 7 and `.claude/rules/testing-tool-selection.md`.

> **When to use**: Validating critical user journeys end-to-end in a real browser — sign-in, checkout, core feature workflows
> **Time estimate**: 30 min per E2E scenario; 2–4 hours for a full critical-path suite
> **Prerequisites**: A fresh build of the branch running locally (or via `webServer`); `@playwright/test` and `@playwright/cli` installed at pinned versions

## Overview

The default is **Playwright**: committed `@playwright/test` specs gate PRs. Chrome DevTools MCP is the default for interactive debugging (DOM, console, network, JS evaluation) and adds performance traces and Lighthouse. `playwright-cli` covers interactive checks that need mocking, offline state or a saved session. Details: the `browser-testing` skill (`.claude/skills/browser-testing/SKILL.md`) and its `reference/playwright-test-suite.md`.

| Tool | Role |
|---|---|
| `@playwright/test` | Repeatable specs in CI: auth via `storageState`, mocked 500/empty/offline, axe, viewports, visual, sharding |
| Chrome DevTools MCP | Interactive debugging (`take_snapshot`, `list_console_messages`, `list_network_requests`, `evaluate_script`); performance traces (LCP, CLS, INP), throttling, Lighthouse |
| `playwright-cli` | Scripted interactive QA: `requests`, `console`, `route`, `network-state-set`, `screenshot --filename` |

---

## Phases

### Phase 1 — Load the skill and identify critical paths

**Skill**: `browser-testing` · **Agent**: `browser-testing`

```
Which user journeys, if broken, block the user completely?
    +-- Authentication → sign in → protected page → sign out
    +-- Core feature   → the primary value action (create, search, purchase)
    +-- Data entry     → submit → confirmation → persisted (re-load shows it)
    +-- Navigation     → deep link while signed out → sign-in → back to the target; unknown route → 404
```

Each journey gets a happy path plus at least two error paths (server error, invalid input, empty, offline).

### Phase 2 — Set up the suite

```bash
npm i -D @playwright/test@1.58.2 @axe-core/playwright@4.11.0   # match your lockfile
npx playwright install --with-deps chromium
```

Use the `playwright.config.ts` from `playwright-test-suite.md`: Playwright-only `outputDir`, `fullyParallel`, `retries` only with `failOnFlakyTests` in CI, traces/screenshots/video on failure, `locale`/`timezoneId`/`reducedMotion` pinned, a `setup` project that signs in once with a **test** account from env vars and saves `storageState` (gitignored), `desktop` and `phone-viewport` projects, and a `webServer` that CI always starts fresh.

### Phase 3 — Write the journeys

```ts
test('success: shows the orders returned by the API', async ({ page }) => {
  await page.goto('/orders');
  await expect(page.getByRole('list', { name: 'Orders' }).getByRole('listitem')).toHaveCount(2);
});

test('server error (500): shows a visible error state', async ({ page }) => {
  await page.route('**/api/orders*', route => route.fulfill({ status: 500 }));
  await page.goto('/orders');
  await expect(page.getByRole('alert')).toContainText(/could not load/i);
});

test('authorization is decided by the server', async ({ request }) => {
  expect((await request.get('/api/admin/users')).status()).toBe(403);   // not "the button is hidden"
});
```

Locators: `getByRole` → `getByLabel` → `getByText` → `getByTestId`. Waiting: web-first assertions only — never `waitForTimeout`, never `networkidle`.

### Phase 4 — Run and capture evidence

```bash
npx playwright test; echo "E2E EXIT:$?"          # the runner's own exit code, never a pipe's
cp -R test-results/playwright evidence/run-$(date +%s)   # before the next run wipes outputDir
```

For interactive investigation of a failing journey:

```bash
playwright-cli -s=qa open http://127.0.0.1:4200/orders
playwright-cli -s=qa requests --filter "/api/"
playwright-cli -s=qa console error
playwright-cli -s=qa screenshot --filename evidence/orders.png
```

### Phase 5 — Error paths

- **Server error / empty**: `page.route(...).fulfill({ status: 500 })` or `{ status: 200, body: '[]' }` in specs; `playwright-cli route "<pattern>" --status 500` interactively. Assert the user-visible state.
- **Offline**: `context.setOffline(true)` in specs; `playwright-cli network-state-set offline` interactively. Mock at the network layer — never override `window.fetch` with an injected script, which bypasses the app's HTTP client and interceptors.
- **Invalid input**: submit, assert the field error, and assert no API call was made (`requests --filter`, or `page.waitForRequest` not firing).

### Phase 6 — Accessibility, viewports and performance

- `@axe-core/playwright` per UI state with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`; report "no automated violations; manual checks required".
- `phone-viewport` project: assert no horizontal overflow and one breakpoint-dependent behaviour. A phone-sized viewport tests the web layout only.
- Performance (Chrome DevTools MCP): `new_page` → `performance_start_trace({ pageId, reload: true })` → read LCP/CLS from the summary → `performance_analyze_insight({ pageId, insightSetId: "NAVIGATION_0", insightName: "LCPBreakdown" })`. Targets: LCP < 2.5 s, CLS < 0.1, INP < 200 ms. Lighthouse: `lighthouse_audit`.

### Phase 7 — Flutter Mobile E2E (Maestro)

Flutter Android/iOS E2E uses Maestro CLI/MCP only — never a browser:

```yaml
# .maestro/login_flow.yaml
appId: com.example.app
---
- launchApp
- tapOn: "Email"
- inputText: ${E2E_USER}
- tapOn: "Password"
- inputText: ${E2E_PASSWORD}
- tapOn: "Sign in"
- assertVisible: "Dashboard"
```

```bash
maestro test -e E2E_USER="$E2E_USER" -e E2E_PASSWORD="$E2E_PASSWORD" .maestro/login_flow.yaml
```

No emulator/simulator/device or no Maestro → BLOCKED, not a browser substitute. The Dart MCP server (`get_runtime_errors`, `widget_inspector`) is a runtime-inspection aid for a running app, not an E2E tool. Detail: `.claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md`.

---

## Quick Reference

| Phase | Tool | Gate |
|-------|------|------|
| 1 — Identify | Manual | Happy path + 2 error paths per journey |
| 2 — Setup | `@playwright/test` | Config from `playwright-test-suite.md`; test accounts from env |
| 3 — Journeys | `@playwright/test` | Role-first locators, web-first assertions, server-side authorization asserted |
| 4 — Run | `npx playwright test` | Own exit code 0; evidence copied out of `outputDir` |
| 5 — Error paths | `page.route`, `setOffline` | Visible error/empty states, no silent failures |
| 6 — a11y, viewports, perf | axe, `phone-viewport`, Chrome DevTools MCP | No automated violations (manual checks listed); no overflow; LCP < 2.5 s |
| 7 — Flutter mobile | Maestro | All flows pass on a real emulator/simulator/device |

## Common Pitfalls

- **Testing only happy paths** — error states are where users get stuck.
- **A green run against a stale server** — CI must start a fresh server; locally, confirm the build stamp.
- **`retries` hiding flakes** — use `failOnFlakyTests` in CI and quarantine with an issue + expiry.
- **Token in `localStorage` as proof of sign-in** — prove it with the protected page and the API status.
- **Screenshot without assertion** — screenshots are evidence, not assertions.

## Related Workflows

- [`test-driven-development.md`](test-driven-development.md) — unit and component layer below E2E
- [`api-testing.md`](api-testing.md) — API contract and integration testing
- [`visual-regression-testing.md`](visual-regression-testing.md) — `toHaveScreenshot` baselines
- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — Maestro E2E for Flutter
- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular E2E context
