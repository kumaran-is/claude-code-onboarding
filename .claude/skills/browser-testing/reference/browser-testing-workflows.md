# Browser Testing — Interactive QA Workflows (web targets)

Step-by-step `playwright-cli` workflows for **interactive** QA of a running web app. Commands are verified against `@playwright/cli@0.1.25` (full list: [playwright-cli-tools.md](playwright-cli-tools.md)). Anything that must run on every PR belongs in a committed `@playwright/test` suite: [playwright-test-suite.md](playwright-test-suite.md). Flutter Android/iOS apps use Maestro, never these workflows (`.claude/rules/testing-tool-selection.md`).

Conventions in every pattern:
- Refs such as `e9` come from the latest `snapshot`; re-snapshot after each re-render. A unique CSS selector also works as a target.
- Credentials come from env vars for a **test** account (`$E2E_USER`, `$E2E_PASSWORD`). Never real user credentials.
- Evidence goes under `evidence/` with `--filename`; report each path with its verdict.
- Status per check: PASS | FAIL | BLOCKED (tool, browser or server unavailable) | NOT RUN.

---

## Pattern 1: Sign-in flow with network and console checks

```bash
playwright-cli -s=login open http://127.0.0.1:4200/login
playwright-cli -s=login console error               # baseline
playwright-cli -s=login snapshot                    # find the email, password and submit refs
playwright-cli -s=login fill e5 "$E2E_USER"
playwright-cli -s=login fill e6 "$E2E_PASSWORD"
playwright-cli -s=login click e7
playwright-cli -s=login requests --filter "/api/"   # expect the sign-in call => [200]
playwright-cli -s=login console error               # expect none
playwright-cli -s=login snapshot                    # expect the protected page with the user's identity
playwright-cli -s=login screenshot --filename evidence/signed-in.png
```

Success criteria (user + server, never client storage):
- The protected page renders and shows the signed-in identity.
- The session check API (e.g. `/api/me`) answered 200 (`requests --filter "/api/me"`, then `request <n>`).
- After sign-out, the same API answers 401 and a deep link to the protected page redirects to sign-in.
- No console errors.

Never treat "a token is in `localStorage`" as success. A token readable by page script is an XSS exfiltration target; tokens belong in HttpOnly cookies (or in memory).

Interactive variant: Chrome DevTools MCP `navigate_page` → `fill_form` → `click` → `list_network_requests` + `list_console_messages` ([chrome-devtools-tools.md](chrome-devtools-tools.md)). It is supporting evidence only; a committed `@playwright/test` spec is the gate.

---

## Pattern 2: Error, empty and offline states

Every screen that loads data must show a visible state for each failure. Mock at the network layer so the app's real HTTP client and interceptors run; never monkey-patch `window.fetch` with `eval`.

```bash
playwright-cli -s=states open http://127.0.0.1:4200/orders
# 500
playwright-cli -s=states route "**/api/orders*" --status 500 --body '{"error":"boom"}' --content-type application/json
playwright-cli -s=states reload
playwright-cli -s=states find "Could not load"          # the error state text your app shows
playwright-cli -s=states screenshot --filename evidence/orders-500.png
# empty
playwright-cli -s=states unroute
playwright-cli -s=states route "**/api/orders*" --status 200 --body '[]' --content-type application/json
playwright-cli -s=states reload
playwright-cli -s=states find "No orders"
playwright-cli -s=states unroute
# offline during an action (a reload while offline exits 1 by design)
playwright-cli -s=states network-state-set offline
playwright-cli -s=states click "button[type=submit]"
playwright-cli -s=states snapshot                         # an error must be visible; nothing pretends it succeeded
playwright-cli -s=states network-state-set online
```

---

## Pattern 3: Form validation

```bash
playwright-cli -s=form open http://127.0.0.1:4200/contact
playwright-cli -s=form snapshot
playwright-cli -s=form click e12                          # submit empty
playwright-cli -s=form snapshot                           # expect field errors, focus on the first invalid field
playwright-cli -s=form fill e8 "not-an-email"
playwright-cli -s=form click e12
playwright-cli -s=form find "valid email"
playwright-cli -s=form fill e8 "qa+contact@example.test"
playwright-cli -s=form fill e9 "Hello, I need help with billing."
playwright-cli -s=form click e12
playwright-cli -s=form requests --filter "/api/contact"   # expect => [200] or [201]
playwright-cli -s=form console error
```

Also check server-side validation: `route` the submit endpoint to 422 with a field error body and confirm the message appears next to the field.

---

## Pattern 4: Keyboard and accessibility spot check

```bash
playwright-cli -s=a11y open http://127.0.0.1:4200/login
playwright-cli -s=a11y snapshot          # headings, labelled inputs, named buttons, alt text
playwright-cli -s=a11y press Tab
playwright-cli -s=a11y snapshot          # the [active] node shows where focus is
playwright-cli -s=a11y press Enter
playwright-cli -s=a11y press Escape      # dialogs close and focus returns to the trigger
```

This is a spot check. The automated gate is `@axe-core/playwright` in the suite (tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`, scanned per UI state); see [playwright-test-suite.md](playwright-test-suite.md). Report "no automated violations; manual checks required" — automated checks never prove WCAG compliance. Full method: the `accessibility-audit` skill.

---

## Pattern 5: Responsive layout (web viewports)

A phone-sized **viewport** tests the web layout. It is never evidence about a native or Flutter mobile app.

```bash
playwright-cli -s=rwd open http://127.0.0.1:4200/
for size in "390 844" "768 1024" "1440 900"; do
  set -- $size
  playwright-cli -s=rwd resize $1 $2
  playwright-cli -s=rwd eval "document.documentElement.scrollWidth <= document.documentElement.clientWidth"   # true = no horizontal overflow
  playwright-cli -s=rwd screenshot --filename evidence/viewport-$1.png
done
```

Also assert one breakpoint-dependent behaviour (e.g. the nav collapses into a menu button at 390 px). If nothing changes across sizes, a wrapper may be hiding the viewport from the app: that is a FAIL, not a pass.

---

## Pattern 6: Error monitoring during a critical flow

```bash
playwright-cli -s=monitor open http://127.0.0.1:4200/checkout
playwright-cli -s=monitor console error
playwright-cli -s=monitor snapshot
playwright-cli -s=monitor fill e14 "4242424242424242"     # payment provider TEST card only
playwright-cli -s=monitor click e20
playwright-cli -s=monitor console error
playwright-cli -s=monitor requests --filter "/api/"       # any 4xx/5xx? inspect with: request <n>
playwright-cli -s=monitor screenshot --filename evidence/checkout-result.png
```

---

## Pattern 7: Performance

Use Chrome DevTools MCP for Core Web Vitals ([chrome-devtools-tools.md](chrome-devtools-tools.md)):

| Metric | Where to read it | Pass | Warn | Fail |
|--------|---------|------|------|------|
| LCP | trace summary; drill in with insight `LCPBreakdown` | < 2.5 s | 2.5–4 s | > 4 s |
| CLS | trace summary; insight `CLSCulprits` | < 0.1 | 0.1–0.25 | > 0.25 |
| INP | trace of a real interaction (`autoStop: false`) | < 200 ms | 200–500 ms | > 500 ms |
| TTFB | trace summary (LCP breakdown) or Navigation Timing below | < 800 ms | 0.8–1.8 s | > 1.8 s |

TTFB from playwright-cli:

```bash
playwright-cli -s=perf open http://127.0.0.1:4200/
playwright-cli -s=perf eval "Math.round(performance.getEntriesByType('navigation')[0].responseStart)"
playwright-cli -s=perf tracing-start
playwright-cli -s=perf reload
playwright-cli -s=perf tracing-stop      # prints the trace path under .playwright-cli/traces/
```

Measure a production build (`ng build` / `vite build` served statically), not a dev server.

---

## Flutter web build notes

> Applies only to a Flutter **web** build. It never validates the Android/iOS app; that uses Maestro (`.claude/rules/testing-tool-selection.md`).

- Test a release build served statically (`flutter build web --release`, then `python3 -m http.server 8080 --directory build/web`). Do not drive the debug (DDC) dev server: it needs a manual bootstrap and is far slower.
- Flutter renders to a canvas. Prefer the semantics tree (enable semantics in the app for tests) over pixel coordinates; coordinates (`mousemove`/`mousedown`/`mouseup`) are a last resort.
- Wait on a visible result (`find <text>` / a suite `expect(...).toPass()`), never a fixed sleep.
- Locator traps (accessible name vs text, merged `Semantics` nodes, hash routing, offline signals): [flutter-web-e2e.md](flutter-web-e2e.md).

---

## Pre-ship browser QA (summary report)

Run against a fresh build of the branch (confirm the build stamp: a server left on the port can serve an old bundle). Combine Patterns 1, 2, 4, 5, 6 and 7, then report:

```markdown
## Browser QA Report — <url> — <build id> — <timestamp>
| Check | Status | Command / evidence |
|---|---|---|
| Smoke: console errors | PASS/FAIL | `console error` output |
| Smoke: failed requests | PASS/FAIL | `requests` output |
| Sign-in (server-proven) | PASS/FAIL | /api/me 200, after sign-out 401 |
| Error / empty / offline states | PASS/FAIL | evidence/orders-500.png ... |
| Keyboard spot check | PASS/FAIL | notes |
| Automated a11y (suite) | PASS/FAIL/NOT RUN | `npx playwright test -g axe` exit code |
| Viewports 390/768/1440 | PASS/FAIL | evidence/viewport-*.png |
| CWV | PASS/WARN/FAIL | LCP, CLS, INP, TTFB values |
Verdict: SHIP | SHIP WITH FIXES | DO NOT SHIP — blockers: <list or none>
```

Clean up: `playwright-cli close-all`.
