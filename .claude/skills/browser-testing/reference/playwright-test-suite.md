# Playwright Test Suite (`@playwright/test`)

Committed, CI-run E2E suites for **web targets** (Angular, React, any SPA, or a Flutter **web** build). `playwright-cli` (see `playwright-cli-tools.md`) is for interactive QA and debugging; this file is for `.spec.ts` suites that gate PRs. Product-repo Playwright Test Agents may plan or generate those specs (`playwright-test-agents.md`); `/verify` still runs this suite. Flutter Android/iOS apps are tested with Maestro, never here (`.claude/rules/testing-tool-selection.md`).

Re-verified 2026-11-24 on `@playwright/test@1.65.1` + `@axe-core/playwright@4.14.1`, Node 26.13.1, TypeScript 6.0.3, real Chromium, in a disposable app (cookie session, JSON API, static pages): config, auth setup, routing, forms, success/empty/500/network-failure states, signed-out 401, axe (and its planted-violation control), layout and element-level visual regression — 29 passed, exit 0; `--repeat-each=3 --shuffle` 85 passed; CI mode in 2 shards plus `merge-reports`, exit 0. Every negative control in [Negative controls](#negative-controls-proven-on-1651) exited as listed. The patterns were first proven on 1.58.2 (31 specs). Pin the versions your lockfile resolves; check newer releases with `npm view @playwright/test version` (stable `latest`, never the `next` / `beta` tags).

## Where E2E sits in the web test pyramid

| Layer | Tool | Covers | Size |
|---|---|---|---|
| Unit | Angular `ng test` (Vitest builder `@angular/build:unit-test`, jsdom); React: Vitest | services, pure logic, pipes, reducers | many |
| Component | Angular TestBed / CDK harnesses; React: Vitest + React Testing Library + user-event | every state of a component (loading, empty, error, data) | many |
| Integration | the same runners with a mocked HTTP layer (`HttpTestingController`, MSW, or `page.route`) | screen + data layer | some |
| E2E (this file) | `@playwright/test` in a real browser | critical journeys, auth, routing, layout, a11y in context, visual | few |

E2E never owns business rules; if a rule can be tested below the browser, test it there. jsdom cannot compute colour contrast or layout, so those checks live here.

## Install

```bash
npm install -D --save-exact @playwright/test@1.65.1 @axe-core/playwright@4.14.1
npx playwright install --with-deps chromium     # browser build that matches the installed @playwright/test
echo "playwright/.auth/" >> .gitignore           # saved sessions are credentials
```

## `playwright.config.ts`

```ts
import { defineConfig, devices } from '@playwright/test';

const PORT = 4200;                              // React/Vite: 5173
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results/playwright',          // Playwright-only: it is emptied at the start of every run
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 2 : 0,
  retryStrategy: 'isolated',                     // 1.62+: retries run at the end, one by one, away from the rest of the suite
  failOnFlakyTests: !!process.env['CI'],            // a test that passes only on retry fails the CI run
  reporter: process.env['CI']
    ? [['blob'], ['github'], ['junit', { outputFile: 'test-results/junit.xml' }]]
    : [['failures'], ['html', { open: 'never' }]],   // 1.65+: 'failures' prints only failures and flaky retries
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'en-US',
    timezoneId: 'UTC',
    colorScheme: 'light',
    reducedMotion: 'reduce',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' }, dependencies: ['setup'] },
    { name: 'phone-viewport', use: { ...devices['Pixel 7'], storageState: 'playwright/.auth/user.json' }, dependencies: ['setup'] },
    // 1.64+: kept in the config, runs only when named (--project=firefox), e.g. in a nightly job
    { name: 'firefox', default: false, use: { ...devices['Desktop Firefox'], storageState: 'playwright/.auth/user.json' }, dependencies: ['setup'] },
  ],
  webServer: {
    command: 'npm exec --no -- ng serve --host 127.0.0.1 --port 4200', // ng serve may bind only [::1]: pin the host baseURL uses; React/Vite: 'npx vite --host 127.0.0.1 --port 5173 --strictPort'
    url: `${baseURL}/`,
    reuseExistingServer: !process.env['CI'],        // CI always starts a fresh server; see "Stale-build guard"
  },
});
```

`process.env['CI']`, not `process.env.CI`: an `e2e/tsconfig.json` that extends an Angular workspace's root
tsconfig inherits `noPropertyAccessFromIndexSignature`, and `tsc -p e2e/tsconfig.json` fails with TS4111.
`ng new` does not install `@types/node`; add it pinned (`npm i -D --save-exact @types/node@26.6.7`) and list
`"types": ["node"]` in the e2e tsconfig. Verified on Angular 22.3 + Playwright 1.65.1 (2026-11-24).

Why each setting:

| Setting | Reason |
|---|---|
| `outputDir: 'test-results/playwright'` | Playwright deletes this directory at the start of every run. Reproduced: a trace from a failed run was gone after the next run. Never point it at a directory other tools write to. Copy artifacts out before re-running (see "Evidence"). |
| `failOnFlakyTests` with `retries` | Reproduced: with `retries: 2` alone, a test that fails on attempt 1 and passes on attempt 2 exits **0** ("1 flaky"). With `failOnFlakyTests: true` the same run exits **1**. A flaky pass is a defect signal, never a pass. |
| `locale`, `timezoneId`, `colorScheme`, `reducedMotion` | Deterministic dates, number formats, theme and animations for assertions and screenshots. |
| `phone-viewport` project | A phone-sized **web layout**. It is never evidence about a mobile app. Never name it "mobile". |
| `trace/screenshot/video` on failure | Each failure leaves `trace.zip`, `test-failed-1.png` and `video.webm` under `outputDir`. |
| `retryStrategy: 'isolated'` | A failed test is retried after the rest of the run, alone in one worker, so a retry does not pass only because the load dropped. |
| `failures` / `junit` reporters | `failures` keeps the local log to what broke; JUnit XML gives CI an executed/skipped count to gate on (see below) and feeds flaky-test dashboards. |
| Firefox / WebKit with `default: false` | Chromium on every PR. Keep Firefox/WebKit projects in the config with `default: false` and run them nightly (`--project=firefox`), or per PR for browser-sensitive code. Verified: `--list` without `--project` shows 0 firefox tests. |
| `screen` (1.64) | Device descriptors now also emulate `window.screen` and screen media queries; set `screen: undefined` to opt out if a layout test depended on the old behaviour. |

## Locators and waiting

- Locator priority: `getByRole` → `getByLabel` → `getByText` → `getByTestId`. Never CSS classes or `nth-child`. If the app uses another attribute, set `use: { testIdAttribute: 'data-test' }` once.
- Act through locators (`page.getByRole('button', { name: 'Save' }).click()`); they auto-wait for the element to be actionable. Do not call `page.click(selector)` or `locator.waitFor()` before an action.
- Wait with web-first assertions (`await expect(locator).toBeVisible()`, `toHaveText`, `toHaveURL`, `toHaveCount`); they retry until the timeout.
- **Never** `page.waitForTimeout(ms)`: it is a race on fast machines and dead time on slow ones. For animations set `reducedMotion: 'reduce'` and assert the end state.
- **Never** `waitForLoadState('networkidle')` / `waitUntil: 'networkidle'`. The installed types mark it **DISCOURAGED**: "rely on web assertions to assess readiness instead".
- `expect.poll(fn)` or `expect(async () => { … }).toPass()` only for genuinely eventual state (a backend job, a polled count).
- `locator.visible()` (1.63) replaces the `:visible` pseudo-class: `page.getByRole('button').visible()`.
- `locator.within(parent)` (1.64) reads "this button, within that dialog", and resolves `nth()`/`first()` per parent (column queries in tables).
- `page.frameLocator()` with no selector (1.63) searches every frame for the rest of the chain; it throws if several frames match.
- Actions wait for an element to stop being `inert` (1.65): a click on an element inside an open modal's inert background now times out instead of hitting it.
- Page objects: TypeScript class fields follow `useDefineForClassFields` (1.65). A field initializer that reads a constructor parameter property (`readonly submit = this.page.getByRole(...)` with `constructor(private readonly page: Page)`) now throws; assign locators in the constructor.

## Console guard fixture (deny by default)

A regex list of "known bad" messages misses new error classes. Fail on every `console.error` and `pageerror`; a test that provokes a failure on purpose declares exactly the line it expects.

```ts
// e2e/fixtures.ts
import { test as base, expect } from '@playwright/test';

// A single RegExp, not an array: test.use() reads an array value as a [value, options] fixture tuple
// (reproduced: an array option crashed with "expectedConsoleErrors.some is not a function").
export const test = base.extend<{ expectedConsoleError: RegExp; consoleGuard: void }>({
  expectedConsoleError: [/$^/, { option: true }],   // matches nothing by default
  consoleGuard: [async ({ page, expectedConsoleError }, use) => {
    const errors: string[] = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', e => errors.push(e.message));
    await use();
    expect(errors.filter(e => !expectedConsoleError.test(e)), 'unexpected console errors').toEqual([]);
  }, { auto: true }],
});
export { expect };
```

Chromium logs every failed request as a console error ("Failed to load resource: … status of 500"), so failure-state tests must declare it (below). Unexpected errors still fail them.

If the app enforces Trusted Types (`require-trusted-types-for 'script'`), never plant DOM with `innerHTML` from a test (`page.evaluate`): the assignment is a Trusted Types violation, which the browser reports as a console error, so the guard fails the test for a reason the app did not cause. Build fixtures with `textContent` / `createElement`, go through the app's Trusted Types policy, or load a test page.

## Auth: set up once, reuse `storageState`

```ts
// e2e/auth.setup.ts
import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json'; // gitignored

setup('sign in once with the test account', async ({ page }) => {
  const email = process.env.E2E_USER, password = process.env.E2E_PASSWORD;
  if (!email || !password) throw new Error('E2E_USER / E2E_PASSWORD not set: use a test account, never real credentials');
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('status')).toHaveText(`Signed in as ${email}`); // success = the server answered, not a stored token
  await page.context().storageState({ path: authFile });
});
```

Rules:
- Test or emulator accounts only, from env vars / CI secrets. Never real user credentials, never committed.
- Sign-in success is proved by what the **server** returns: a protected page renders the session's identity, or `/api/me` → 200. A token in `localStorage` is never a success criterion. Tokens belong in HttpOnly cookies (or in memory); a token readable by page script is an XSS exfiltration target.
- Override per describe for signed-out cases: `test.use({ storageState: { cookies: [], origins: [] } })`.

### Authorization and routing assert the backend's answer

A hidden button is not authorization. Call the API with the session and assert the status.

```ts
import { test, expect } from './fixtures';

test('authorization is decided by the server: a normal user gets 403 from the admin API', async ({ page }) => {
  const res = await page.request.get('/api/admin/users');   // shares the page's cookies
  expect(res.status()).toBe(403);
});

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] }, expectedConsoleError: /status of 401/ });
  test('deep link to a protected page redirects to sign-in and keeps the target', async ({ page }) => {
    await page.goto('/account');
    await expect(page).toHaveURL(/\/login\?next=%2Faccount$/);
  });
  test('admin API without a session returns 401', async ({ request }) => {
    expect((await request.get('/api/admin/users')).status()).toBe(401);
  });
});
```

Also cover: after sign-in the user returns to the original URL; an unknown route renders the 404 page; for role changes assert 403 → 200 → 403 through `request` as the role is granted and revoked.

## Every data screen: success, empty, 500, timeout, offline

Mock the network at the browser boundary with `page.route()`; the app's real HTTP client and interceptors still run. Do not monkey-patch `window.fetch` with `evaluate`, which skips that path.

```ts
import { test, expect } from './fixtures';

test.describe('orders list states', () => {
  test('success: shows the orders returned by the API', async ({ page }) => {
    await page.route('**/api/orders*', r => r.fulfill({ json: [{ id: 'A-1', total: '$12.00' }] }));
    await page.goto('/orders');
    await expect(page.getByRole('list', { name: 'Orders' }).getByRole('listitem')).toHaveCount(1);
  });

  test('empty: shows the empty state', async ({ page }) => {
    await page.route('**/api/orders*', r => r.fulfill({ json: [] }));
    await page.goto('/orders');
    await expect(page.getByRole('status')).toHaveText('No orders yet');
  });

  test.describe('failure states', () => {
    // the browser itself logs failed requests; these tests expect exactly those lines and nothing else
    test.use({ expectedConsoleError: /status of 500|ERR_TIMED_OUT|ERR_INTERNET_DISCONNECTED|Failed to fetch/ });

    test('server error (500): shows a visible error state', async ({ page }, testInfo) => {
      await page.route('**/api/orders*', r => r.fulfill({ status: 500, json: { error: 'boom' } }));
      await page.goto('/orders');
      await expect(page.getByRole('alert')).toHaveText(/could not load orders/i);
      await page.screenshot({ path: testInfo.outputPath('error-500.png') });
    });

    test('timeout / network failure: shows the same error state', async ({ page }) => {
      await page.route('**/api/orders*', r => r.abort('timedout'));
      await page.goto('/orders');
      await expect(page.getByRole('alert')).toBeVisible();
    });

    test('offline after load: the request fails and nothing pretends it succeeded', async ({ page, context }) => {
      await page.goto('/orders');
      await expect(page.getByRole('status')).toHaveText('2 orders');
      await context.setOffline(true);
      const failed = page.waitForEvent('requestfailed', r => r.url().includes('/api/orders?q='));
      await page.getByRole('textbox', { name: 'Search' }).fill('A-1');
      await page.getByRole('button', { name: 'Search' }).click();
      expect((await failed).failure()?.errorText).toContain('ERR_INTERNET_DISCONNECTED');
    });
  });
});
```

Assert the visible error state, not just "no crash". Proven negative control: with the error UI removed from the page, the 500 test failed (`element(s) not found` for `getByRole('alert')`, exit 1) and left `trace.zip` + `test-failed-1.png`.

## Test data

- Unique per test: suffix with `test.info().workerIndex` or a timestamp. Create data through the API in a fixture, not through the UI.
- Tests never depend on order; `fullyParallel: true` unless a serial block has a written reason.
- Fixed clock when the UI shows dates: `await page.clock.setFixedTime(new Date('2026-01-15T10:00:00Z'))` plus `timezoneId` in the config.
- Never point PR E2E at a shared staging database with real data or secrets.

## Accessibility with `@axe-core/playwright`

```ts
import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

test('no automated axe violations on load and with the dialog open', async ({ page }) => {
  await page.goto('/orders');
  await expect(page.getByRole('status')).toHaveText('2 orders');
  expect((await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Delete first order' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()).violations).toEqual([]);
});
```

- Scan each **state** (dialog open, error banner, empty list), not only the page at load.
- Every `.exclude(selector)` carries a comment naming the reason and a ticket.
- Keep one negative control in the suite: a fixture page with low-contrast text, an unlabelled input and an icon-only button must yield `color-contrast`, `label` and `button-name` (proven in Chromium; pointing that control at a clean page made it fail, exit 1).
- **"No automated violations" is not "compliant".** axe finds a subset of WCAG 2.2 failures. Keyboard order, focus visibility and return, screen-reader announcements, target size in context and content meaning still need manual checks. Report "no automated violations; manual checks required".
- Also assert keyboard behaviour in specs: Tab reaches the primary action (`toBeFocused()`), Escape closes dialogs (`toBeHidden()`).

## Responsive layout (web only)

```ts
test('layout: no horizontal overflow and the breakpoint behaviour actually switches', async ({ page, isMobile }) => {
  await page.goto('/orders');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  // assert behaviour that depends on the viewport, so a wrapper that masks the viewport fails this test
  if (isMobile) {
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
  } else {
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeHidden();
  }
});
```

A device frame or preview wrapper can stop viewport changes reaching the app; an overflow check alone would still pass. The breakpoint assertion catches it.

## Visual regression with `toHaveScreenshot`

```ts
test('visual: orders page matches the baseline', async ({ page }) => {
  await page.route('**/api/orders*', r => r.fulfill({ json: [{ id: 'A-1', total: '$12.00' }] }));
  await page.goto('/orders');
  await expect(page.getByRole('status')).toHaveText('1 orders');
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot('orders.png');   // whole page: config default maxDiffPixelRatio 0.01
  // the data region gets a zero-pixel budget: 1% of a full page is enough to hide a changed price
  await expect(page.getByRole('list', { name: 'Orders' })).toHaveScreenshot('orders-list.png', { maxDiffPixels: 0 });
});
```

Tolerance options (from the installed `test.d.ts`):

| Option | Meaning |
|---|---|
| `threshold` | Per-pixel **colour** tolerance in YIQ space, `0` (strict) to `1` (lax), default `0.2`. It is **not** a percentage of pixels. |
| `maxDiffPixelRatio` | Share of pixels allowed to differ, `0`–`1` (`0.01` = 1 % of the image). |
| `maxDiffPixels` | Absolute count of pixels allowed to differ. |

Proven: changing `$12.00` to `$99.00` passed the full-page assertion at `maxDiffPixelRatio: 0.01` and failed the element assertion ("256 pixels (ratio 0.02 of all image pixels) are different", exit 1). Put tight budgets on the regions that carry data.

Determinism:
- `animations` defaults to `"disabled"` for `toHaveScreenshot`; still set `reducedMotion: 'reduce'` so JS-driven motion settles.
- Self-host fonts and await `document.fonts.ready`; a fallback font swaps every glyph.
- `mask: [locator]` for clocks, avatars and ads; `stylePath` for CSS that hides volatile regions in screenshots only.
- Baselines are per OS and browser (`orders-desktop-darwin.png`). Generate and update them only in the pinned CI image (`--update-snapshots` there), never accept laptop baselines for CI.
- Stability check: `npx playwright test -g visual --repeat-each=3` must pass before a baseline is trusted (proven: 6/6 passed).

## Stale-build guard

A green run against an old bundle is a false pass (a server left on the port kept serving a bundle many hours old while the runner exited 0). In CI `reuseExistingServer` is false. Locally, assert the build you just made:

```ts
test('stale-build guard: the page under test is the build we just made', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('meta[name="app-build"]')).toHaveAttribute('content', process.env.EXPECTED_BUILD!);
});
```

Emit the meta tag (or a `/version.json`) from the build with the commit SHA and pass `EXPECTED_BUILD=$(git rev-parse --short HEAD)`. Proven: a mismatched `EXPECTED_BUILD` failed (exit 1).

## Flaky tests: retries and quarantine

- `retries` is allowed in CI only together with `failOnFlakyTests: true` (or `--fail-on-flaky-tests`).
- Reproduce flakiness: `npx playwright test path/to.spec.ts --repeat-each=20 --workers=4`.
- Find order dependence: `--shuffle` (1.64) runs tests in random order; combine with `--repeat-each`. Verified: `--repeat-each=3 --shuffle` → 85 passed.
- Shared resources (one test account, a global setting): declare a test lock, `test('...', { lock: 'user-settings' }, ...)` (1.63); tests holding the same lock never overlap, the rest stays parallel. `lock: '-exclusive-'` (1.65) runs a test alone.
- Quarantine = tag the title `@quarantine`, link an issue and an expiry date in a comment, run PRs with `--grep-invert @quarantine`, and run the quarantined set in a separate non-blocking job. Never `test.skip(!!process.env.CI)`: it hides the failure exactly where it matters.
- Put a conditional `test.skip(condition, reason)` at the **top** of a test. Called after assertions it marks the whole test skipped and drops the evidence it produced.
- A step that prints "skipped" and exits 0 is NOT RUN, never PASS.
- **An all-skipped run exits 0** (verified: 3 skipped, exit 0). Gate on the executed count: `PLAYWRIGHT_JSON_OUTPUT_FILE=r.json npx playwright test --reporter=line,json --fail-on-flaky-tests`, then `stats.expected + stats.unexpected + stats.flaky > 0` (`/verify` does this), or count `tests - skipped` in the JUnit XML.
- Never `--pass-with-no-tests` in a gate: it turns "No tests found" (exit 1) into exit 0. Since 1.65 a sharded run with no matching tests in any shard fails instead of passing.

## Debugging a failing test

- `npx playwright show-report` (HTML), `npx playwright show-trace <trace.zip>` (Trace Viewer: DOM snapshots, network, console per step), `npx playwright test --ui` (UI mode, local only).
- For Claude: `PLAYWRIGHT_HTML_OPEN=never npx playwright test <spec> --debug=cli` in the background, then `npx playwright cli attach <session>` and `step-over` / `pause-at` / `snapshot` / `resume` (1.59+, verified on 1.65.1; see the browser-testing SKILL.md). Every action the CLI takes prints the matching Playwright code to paste back into the spec.
- `error-context.md` next to each failure holds the aria snapshot at the failing assertion: read it before re-running.

## Evidence and artifacts

- Save your own evidence with `testInfo.outputPath('name.png')` or `testInfo.attach(...)`, never a hand-made path in a shared directory.
- `outputDir` is wiped at the start of the next run. Copy `test-results/playwright/` somewhere durable (CI artifact upload, or `cp -R test-results/playwright evidence/<run-id>`) **before** re-running. Proven: the failed run's `trace.zip` disappeared on the next run; the copied one remained.
- Open a trace: `npx playwright show-trace test-results/playwright/<test>/trace.zip`.
- Report the exit code of `npx playwright test` itself (`npx playwright test; echo "EXIT:$?"`), never the exit code of a pipe into `tail`.

## GitHub Actions: sharded run + merged report

```yaml
# .github/workflows/e2e.yml (Node 26 = Active LTS; Angular 22 engines ^22.22.3 || ^24.15.0 || ^26.0.0)
name: e2e
on: pull_request
permissions: { contents: read }
jobs:
  e2e:
    runs-on: ubuntu-latest
    strategy: { fail-fast: false, matrix: { shard: [1, 2, 3, 4] } }
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1        # v7.0.1
        with: { persist-credentials: false }
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1      # v7.1.0
        with: { node-version: '26', cache: 'npm' }                             # caches npm downloads, not browsers
      - run: npm ci
      - run: npm exec --no -- playwright install --with-deps chromium   # --no: never downloads a package; uses the lockfile's @playwright/test
      - run: npm exec --no -- playwright test --shard=${{ matrix.shard }}/4 --grep-invert @quarantine --fail-on-flaky-tests
        env: { E2E_USER: '${{ secrets.E2E_USER }}', E2E_PASSWORD: '${{ secrets.E2E_PASSWORD }}', EXPECTED_BUILD: '${{ github.sha }}' }
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
        if: ${{ !cancelled() }}
        with:
          name: e2e-${{ matrix.shard }}
          path: |
            blob-report
            test-results/playwright
            test-results/junit.xml
          retention-days: 7
  report:
    if: ${{ !cancelled() }}
    needs: e2e
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1        # v7.0.1
        with: { persist-credentials: false }
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1      # v7.1.0
        with: { node-version: '26', cache: 'npm' }
      - run: npm ci
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333  # v8.0.2
        with: { path: all-blob-reports, pattern: 'e2e-*', merge-multiple: true }
      - run: npm exec --no -- playwright merge-reports --reporter html ./all-blob-reports/blob-report
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9  # v7.0.2
        with: { name: playwright-report, path: playwright-report, retention-days: 14 }
```

The backend for E2E is a disposable service started by `webServer` (an array of servers is allowed; each waits for its `url` before tests start), never `npm run start &` without a health wait. Run on `pull_request` once, not on both `push` and `pull_request`.

- Actions are pinned to the commit SHA of the tag in the comment (resolved 2026-11-24 with `git ls-remote`); Dependabot or Renovate keeps them current. `permissions: contents: read` at the top of the workflow.
- Do not cache browser binaries: Playwright's CI guide says restoring takes about as long as downloading, and the OS dependencies cannot be cached anyway. `setup-node`'s npm cache is enough.
- Shard only when one job exceeds ~10 minutes; each shard repeats `npm ci`, browser install and auth setup (verified: setup runs once per shard).
- Flaky reporting: `--fail-on-flaky-tests` fails the job; the merged HTML report and `junit.xml` list each flaky test with its retries for the issue tracker.
- Proven locally in CI mode (`CI=1`, shards 1/2 and 2/2, blob + github + junit reporters, `merge-reports --reporter html`): every step exit 0. The workflow file itself passes `actionlint`; a real GitHub run is still required before relying on it.

## Negative controls (proven on 1.65.1)

Each control was planted in the disposable app and run with `npx playwright test`; the exit code is the runner's own.

| Planted fault | Result |
|---|---|
| Wrong expected heading (`toHaveText`) | exit 1, `expect(locator).toHaveText(expected) failed`, `trace.zip` + `test-failed-1.png` + `error-context.md` kept |
| Uncaught page error | exit 1 via the console guard fixture (`unexpected console errors`) |
| Missing element (`toBeVisible` on an absent dialog) | exit 1, `element(s) not found` |
| Action on a missing button (`actionTimeout: 1000`) | exit 1, `TimeoutError: locator.click: Timeout 1000ms exceeded` |
| Passes only on retry, `--retries=1` | **exit 0** ("flaky"); with `--fail-on-flaky-tests` exit 1 |
| Every test skipped | **exit 0**: gate on the executed count |
| `--grep` matching nothing, plain and `--shard=1/2` | exit 1, `No tests found`; with `--pass-with-no-tests` exit 0 |
| Price changed under an element screenshot with `maxDiffPixels: 0` | exit 1, `toHaveScreenshot(expected) failed` |
| Invalid config (`projects: 'oops'`) | exit 1, `config.projects must be an array` |
| No browser (`PLAYWRIGHT_BROWSERS_PATH` empty dir) | exit 1, `Executable doesn't exist` → report **BLOCKED**, never FAIL-as-regression or PASS |
| axe on a page with low-contrast text, an unlabelled input, an icon-only button | `color-contrast`, `label`, `button-name` reported |

## Playwright 1.59–1.65: what the toolkit adopts

Source: the official release notes (`docs/src/release-notes-js.md`, read 2026-11-24; Context7 was over quota). Breaking changes are folded into the sections above.

| Feature (version) | Decision | Where |
|---|---|---|
| CLI inside Playwright, `npx playwright cli` (1.59) and `--debug=cli` + `attach` / `step-over` / `resume` | ADOPT | SKILL.md, "Debugging a failing test" |
| `retryStrategy: 'isolated'` (1.62) | ADOPT | config |
| Test locks `lock` (1.63), `-exclusive-` (1.65) | ADOPT for shared resources | Flaky tests |
| `locator.visible()` (1.63), `frameLocator()` without selector (1.63), `locator.within()` (1.64) | ADOPT | Locators |
| `TestProject.default: false` (1.64), `--shuffle` (1.64) | ADOPT | config, Flaky tests |
| `failures` reporter, `onlyFailures` for html/json/junit (1.65) | ADOPT `failures` locally; `onlyFailures` OPTIONAL for large suites | config |
| `--add-reporter` (1.63), `reducedMotion` / `forcedColors` / `contrast` test options (1.63) | OPTIONAL | — |
| WebP screenshots, `toHaveScreenshot` `type: 'webp'` (1.62/1.64) | OPTIONAL (smaller baselines; regenerate all at once) | Visual regression |
| `perfetto` reporter (1.63), HAR on tracing (1.60), video `fps` (1.64) | OPTIONAL diagnostics | — |
| New component-testing model, stories and galleries (1.62) | DEFER: component tests stay in Vitest + Testing Library / `ng test` | `.claude/rules/testing-tool-selection.md` |
| WebMCP (`page.webmcp`, 1.64) | DEFER: experimental browser API | — |
| Running the runner under Bun (1.65) | REJECT for this toolkit: Node 26 is the pinned runtime | — |
| `--update-snapshots=missing` now passes (1.64) | ADOPT with care: CI generates missing baselines only in the pinned image | Visual regression |

## Report template

```markdown
## E2E report — <date> — <branch>
Command: `npx playwright test` → EXIT <n>
Result: PASS | FAIL | BLOCKED (no browser/server: say which) | NOT RUN (why)
Passed <n> · Failed <n> · Flaky <n> (flaky fails CI) · Skipped <n> (each with reason)
Failures: <spec:line> — <assertion> — trace: <path> — screenshot: <path>
Evidence copied to: <durable path or CI artifact name>
a11y: no automated violations at <tags>; manual checks required: <list>
```

## Anti-patterns

| Anti-pattern | Use instead |
|---|---|
| `waitForTimeout(500)` for a modal or animation | `await expect(dialog).toBeVisible()` + `reducedMotion: 'reduce'` |
| `waitForLoadState('networkidle')` | web-first assertion on the content you need |
| `page.locator('.btn-primary')`, `nth-child` | `getByRole('button', { name })` |
| Token in `localStorage` as proof of login | protected page shows the identity / `/api/me` → 200 |
| Asserting a hidden button as "authorization" | `request.get(adminApi)` → 403 |
| `retries: 2` without `failOnFlakyTests` | both, plus quarantine tag + issue |
| `test.skip(!!process.env.CI)` | fix it or quarantine it |
| Evidence written to a shared `artifacts/` path | `testInfo.outputPath()`; copy `outputDir` out before re-running |
| `reuseExistingServer: true` in CI | fresh server + build-stamp assertion |
| `threshold: 0.1` described as "10 % of pixels" | `maxDiffPixelRatio` / `maxDiffPixels` |
| A project called `mobile` | `phone-viewport` (a web layout check); Flutter Android/iOS apps use Maestro, never a browser |
| Cypress for new web E2E | Playwright (the toolkit's web E2E tool); Cypress only where a repo already runs it |
