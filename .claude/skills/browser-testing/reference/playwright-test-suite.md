# Playwright Test Suite (`@playwright/test`)

Committed, CI-run E2E suites for **web targets** (Angular, React, any SPA, or a Flutter **web** build). `playwright-cli` (see `playwright-cli-tools.md`) is for interactive QA and debugging; this file is for `.spec.ts` suites that gate PRs. Flutter Android/iOS apps are tested with Maestro, never here (`.claude/rules/testing-tool-selection.md`).

Every config and spec below ran in real Chromium against `@playwright/test@1.58.2` and `@axe-core/playwright@4.11.0` (clean run: 31 passed, exit 0; each planted regression: exit 1). Pin the versions your lockfile resolves; check newer releases with `npm view @playwright/test version`.

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
npm install -D @playwright/test@1.58.2 @axe-core/playwright@4.11.0
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
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  failOnFlakyTests: !!process.env.CI,            // a test that passes only on retry fails the CI run
  reporter: process.env.CI ? [['blob'], ['github']] : [['list'], ['html', { open: 'never' }]],
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
  ],
  webServer: {
    command: 'npx ng serve --port 4200',         // React/Vite: 'npx vite --port 5173 --strictPort'
    url: `${baseURL}/`,
    reuseExistingServer: !process.env.CI,        // CI always starts a fresh server; see "Stale-build guard"
  },
});
```

Why each setting:

| Setting | Reason |
|---|---|
| `outputDir: 'test-results/playwright'` | Playwright deletes this directory at the start of every run. Reproduced: a trace from a failed run was gone after the next run. Never point it at a directory other tools write to. Copy artifacts out before re-running (see "Evidence"). |
| `failOnFlakyTests` with `retries` | Reproduced: with `retries: 2` alone, a test that fails on attempt 1 and passes on attempt 2 exits **0** ("1 flaky"). With `failOnFlakyTests: true` the same run exits **1**. A flaky pass is a defect signal, never a pass. |
| `locale`, `timezoneId`, `colorScheme`, `reducedMotion` | Deterministic dates, number formats, theme and animations for assertions and screenshots. |
| `phone-viewport` project | A phone-sized **web layout**. It is never evidence about a mobile app. Never name it "mobile". |
| `trace/screenshot/video` on failure | Each failure leaves `trace.zip`, `test-failed-1.png` and `video.webm` under `outputDir`. |
| Firefox / WebKit | Chromium on every PR. Add `devices['Desktop Firefox']` / `devices['Desktop Safari']` projects nightly, or per PR for browser-sensitive code (date inputs, CSS features). |

## Locators and waiting

- Locator priority: `getByRole` → `getByLabel` → `getByText` → `getByTestId`. Never CSS classes or `nth-child`. If the app uses another attribute, set `use: { testIdAttribute: 'data-test' }` once.
- Act through locators (`page.getByRole('button', { name: 'Save' }).click()`); they auto-wait for the element to be actionable. Do not call `page.click(selector)` or `locator.waitFor()` before an action.
- Wait with web-first assertions (`await expect(locator).toBeVisible()`, `toHaveText`, `toHaveURL`, `toHaveCount`); they retry until the timeout.
- **Never** `page.waitForTimeout(ms)`: it is a race on fast machines and dead time on slow ones. For animations set `reducedMotion: 'reduce'` and assert the end state.
- **Never** `waitForLoadState('networkidle')` / `waitUntil: 'networkidle'`. The installed types mark it **DISCOURAGED**: "rely on web assertions to assess readiness instead".
- `expect.poll(fn)` or `expect(async () => { … }).toPass()` only for genuinely eventual state (a backend job, a polled count).

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
- Quarantine = tag the title `@quarantine`, link an issue and an expiry date in a comment, run PRs with `--grep-invert @quarantine`, and run the quarantined set in a separate non-blocking job. Never `test.skip(!!process.env.CI)`: it hides the failure exactly where it matters.
- Put a conditional `test.skip(condition, reason)` at the **top** of a test. Called after assertions it marks the whole test skipped and drops the evidence it produced.
- A step that prints "skipped" and exits 0 is NOT RUN, never PASS.

## Evidence and artifacts

- Save your own evidence with `testInfo.outputPath('name.png')` or `testInfo.attach(...)`, never a hand-made path in a shared directory.
- `outputDir` is wiped at the start of the next run. Copy `test-results/playwright/` somewhere durable (CI artifact upload, or `cp -R test-results/playwright evidence/<run-id>`) **before** re-running. Proven: the failed run's `trace.zip` disappeared on the next run; the copied one remained.
- Open a trace: `npx playwright show-trace test-results/playwright/<test>/trace.zip`.
- Report the exit code of `npx playwright test` itself (`npx playwright test; echo "EXIT:$?"`), never the exit code of a pipe into `tail`.

## GitHub Actions: sharded run + merged report

```yaml
# .github/workflows/e2e.yml
name: e2e
on: pull_request
jobs:
  e2e:
    runs-on: ubuntu-latest
    strategy: { fail-fast: false, matrix: { shard: [1, 2, 3, 4] } }
    steps:
      - uses: actions/checkout@v4      # pin to a full commit SHA: deployment-ci-cd/reference/python-ci-supply-chain.md
      - uses: actions/setup-node@v4    # pin to a full commit SHA
        with: { node-version: '24', cache: 'npm' }
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test --shard=${{ matrix.shard }}/4 --grep-invert @quarantine
        env: { E2E_USER: '${{ secrets.E2E_USER }}', E2E_PASSWORD: '${{ secrets.E2E_PASSWORD }}', EXPECTED_BUILD: '${{ github.sha }}' }
      - uses: actions/upload-artifact@v4   # pin to a full commit SHA
        if: ${{ !cancelled() }}
        with:
          name: e2e-${{ matrix.shard }}
          path: |
            blob-report
            test-results/playwright
          retention-days: 7
  report:
    if: ${{ !cancelled() }}
    needs: e2e
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '24', cache: 'npm' }
      - run: npm ci
      - uses: actions/download-artifact@v4
        with: { path: all-blob-reports, pattern: 'e2e-*', merge-multiple: true }
      - run: npx playwright merge-reports --reporter html ./all-blob-reports/blob-report
      - uses: actions/upload-artifact@v4
        with: { name: playwright-report, path: playwright-report, retention-days: 14 }
```

The backend for E2E is a disposable service started by `webServer` (an array of servers is allowed; each waits for its `url` before tests start), never `npm run start &` without a health wait. Run on `pull_request` once, not on both `push` and `pull_request`. The workflow YAML above is not executed in this repo's sandbox: validate it with `actionlint` and a real PR run before relying on it.

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
