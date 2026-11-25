# Testing — Vitest, Testing Library, MSW, Playwright + axe

> RECOMMENDED PRACTICE. All files below ran green on 2026-11-23 (Vitest 5.1.1, and Playwright in Chromium at
> 375 and 1280 px, `@playwright/test@1.65.1`). Fixture, visual and CI sections re-verified on Node 26.13.1
> with TypeScript 6.0.3. Tool choice by target: `.claude/rules/testing-tool-selection.md`.
> Playwright workflows (traces, storageState, sharding): `browser-testing` skill.

## Vitest config and setup

`vitest.config.ts`

```ts
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}', 'build-tests/**/*.test.ts'],
      restoreMocks: true,
    },
  }),
)
```

`src/test/setup.ts`

```ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { server } from './msw-server'

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))

// jsdom implements neither matchMedia (ThemeProvider reads prefers-color-scheme) nor ResizeObserver (Base UI).
// build-tests/ run in the node environment: no DOM there.
const hasDom = typeof window !== 'undefined'

beforeEach(() => {
  if (!hasDom) return
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

afterEach(() => {
  if (!hasDom) return
  cleanup()
  server.resetHandlers()
  window.localStorage.clear()
  document.documentElement.className = ''
})
afterAll(() => server.close())
```

`src/test/msw-server.ts`

```ts
import { setupServer } from 'msw/node'

// Handlers are added per test with server.use(); unhandled requests fail the test.
export const server = setupServer()
```

`src/test/render.tsx`

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { Toaster } from '@/components/ui/toast'
import { ThemeProvider } from '@/shared/ui/theme-provider'

/** Fresh QueryClient per test, retries off so error states appear immediately. Theme provider and toaster as in main.tsx. */
export function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return {
    client,
    ...render(
      <ThemeProvider>
        <QueryClientProvider client={client}>{ui}</QueryClientProvider>
        <Toaster />
      </ThemeProvider>,
    ),
  }
}
```

MSW 3: `server.listen({ onUnhandledFrame: 'error' })`. The v2 name `onUnhandledRequest` fails `tsc -b`
against `msw@3.0.7` (`SharedOptions` has only `onUnhandledFrame`). Any unmocked request fails the test.

Rules:
- Query by role and label (`getByRole`, `getByLabelText`); `await` every `user-event` call; `findBy*` for async.
- Mock the network with MSW, not your hooks: the real query, parsing and error code stay under test.
- Fresh `QueryClient` per test with `retry: false`.
- Each concurrency or security test has a control that fails without the fix (abort, rollback, XSS).
- Vitest does not type-check: run `tsc -b` in CI too.
- React 19 types have no global `JSX` namespace; use `import type { JSX } from 'react'` or `React.JSX`.

## Playwright + axe

`playwright.config.ts`

```ts
import { defineConfig, devices } from '@playwright/test'

const port = 5179

export default defineConfig({
  testDir: './e2e',
  forbidOnly: !!process.env.CI,
  retries: 0, // a flake must fail (the /verify gate also passes --fail-on-flaky-tests)
  reporter: [['list']],
  use: { baseURL: `http://localhost:${port}`, trace: 'on-first-retry' },
  projects: [
    { name: 'mobile-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 } } },
    { name: 'desktop-1280', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: `npx vite build && npx vite preview --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
```

`e2e/projects.spec.ts`

```ts
import { expect, test } from './fixtures.ts'
import { axeViolations, mockProjects, signIn } from './support.ts'

test.describe('projects feature', () => {
  test('loaded table, dialog form validation and axe (no automated violations)', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
    expect(new URL(page.url()).pathname).toBe('/app/projects')
    await expect(page.getByRole('table', { name: 'Projects' })).toContainText('Alpha')
    expect(await axeViolations(page)).toEqual([])

    const opener = page.getByRole('button', { name: 'New project' })
    await opener.click()
    const dialog = page.getByRole('dialog', { name: 'New project' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Create project' }).click()
    const name = dialog.getByLabel('Project name')
    await expect(name).toHaveAttribute('aria-invalid', 'true')
    await expect(name).toHaveAccessibleDescription(/Name must be at least 3 characters/)
    await expect(name).toBeFocused()
    expect(await axeViolations(page)).toEqual([])

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(opener).toBeFocused()
  })

  test('sorting by the Name header reorders the rows and sets aria-sort', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    const rows = page.getByRole('table', { name: 'Projects' }).getByRole('row')
    await expect(rows.nth(1)).toContainText('Alpha')
    await page.getByRole('button', { name: 'Name' }).click()
    await expect(page.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'ascending')
    await expect(rows.nth(1)).toContainText('Alpha')
    await expect(rows.nth(3)).toContainText('Gamma')
    await page.getByRole('button', { name: 'Name' }).click()
    await expect(page.getByRole('columnheader', { name: /Name/ })).toHaveAttribute('aria-sort', 'descending')
    await expect(rows.nth(1)).toContainText('Gamma')
  })

  test('creating a project shows a toast and the new row', async ({ page }) => {
    await mockProjects(page)
    await signIn(page)
    await page.getByRole('button', { name: 'New project' }).click()
    const dialog = page.getByRole('dialog', { name: 'New project' })
    await dialog.getByLabel('Project name').fill('Delta')
    await dialog.getByLabel('Owner email').fill('d@example.com')
    await dialog.getByRole('button', { name: 'Create project' }).click()
    await expect(page.getByText('Project "Delta" created')).toBeVisible()
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('table', { name: 'Projects' })).toContainText('Delta')
    expect(await axeViolations(page)).toEqual([])
  })

  test.describe('server error', () => {
    // The 500 response, the browser's resource-load message and the app logger's line are expected here.
    test.use({ allowedErrors: /\/api\/projects|HTTP 500|status of 500/ })

    test('shows an alert with retry', async ({ page }) => {
      await page.route('**/api/projects', (route) => route.fulfill({ status: 500, body: '' }))
      await signIn(page)
      // TanStack Query retries a failed query 3 times with backoff (~7 s) before showing the error state.
      await expect(page.getByRole('alert')).toContainText('Projects could not be loaded', { timeout: 15_000 })
      await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
      expect(await axeViolations(page)).toEqual([])
    })
  })

  test('empty list shows an empty state', async ({ page }) => {
    await mockProjects(page, [])
    await signIn(page)
    await expect(page.getByText('No projects yet')).toBeVisible()
  })

  test('positive control: axe detects a planted violation in real Chromium', async ({ page }) => {
    await mockProjects(page, [])
    await signIn(page)
    await expect(page.getByText('No projects yet')).toBeVisible()
    await page.evaluate(() => {
      const button = document.createElement('button') // no accessible name
      // DOM APIs, not innerHTML: the page enforces Trusted Types, which blocks raw string HTML.
      const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
      icon.setAttribute('width', '24')
      icon.setAttribute('height', '24')
      icon.setAttribute('aria-hidden', 'true')
      button.append(icon)
      document.querySelector('main')?.append(button)
    })
    expect((await axeViolations(page)).some((v) => v.startsWith('button-name'))).toBe(true)
  })
})
```

- The API is mocked with `page.route`, so the run needs no backend.
- Positive control kept in the suite: an injected unnamed button must produce `button-name`.
- The preview server enforces Trusted Types (`tooling.md`), so tests plant DOM with DOM APIs, never
  `innerHTML`: a string assignment is blocked and the console error fails the test (verified, exit 1).
- Planted in source during validation: low-contrast text (`#bbb` on `#fff`) → `color-contrast`, exit 1.
- "No automated violations" is not WCAG conformance; keyboard, screen-reader and zoom checks are manual
  (`accessibility-audit` skill, `reference/manual-testing-checklist.md`).
- The error-state test waits 15 s because the app keeps TanStack's default 3 retries.

E2E tsconfig (`tsconfig.e2e.json`, referenced from the root solution file so `tsc -b` checks specs):

`tsconfig.e2e.json`

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.e2e.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "types": ["node"],
    "module": "nodenext",
    "skipLibCheck": true,
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "strict": true
  },
  "include": ["e2e"]
}
```

`nodenext` requires explicit extensions on relative imports (`./fixtures.ts`); without
`allowImportingTsExtensions` `tsc -b` fails with TS2835.

## Shared E2E helpers

Sign-in, API mocking and the axe scan live in one module so every spec uses the same WCAG tags. The scan
waits for finite animations first: axe flagged `color-contrast` once on a menu that was still fading in.

`e2e/support.ts`

```ts
import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect } from './fixtures.ts'

export const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

export type ProjectRow = { id: string; name: string; ownerEmail: string }
export const seed: ProjectRow[] = [
  { id: '1', name: 'Alpha', ownerEmail: 'a@example.com' },
  { id: '2', name: 'Gamma', ownerEmail: 'g@example.com' },
  { id: '3', name: 'Beta', ownerEmail: 'b@example.com' },
]

export async function axeViolations(page: Page): Promise<string[]> {
  // Let enter/exit animations (dialog, menu, toast) finish: axe reads colours mid-fade otherwise (false color-contrast).
  // Infinite animations (skeleton pulse, spinner) never finish and are skipped.
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  )
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

/** GET returns the rows, POST appends the created one: a tiny in-memory API for the page under test. */
export async function mockProjects(page: Page, initial: ProjectRow[] = seed) {
  const rows = [...initial]
  await page.route('**/api/projects', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Omit<ProjectRow, 'id'>
      const created = { id: String(rows.length + 1), ...body }
      rows.push(created)
      await route.fulfill({ status: 201, json: created })
      return
    }
    await route.fulfill({ json: rows })
  })
}

export async function signIn(page: Page, path = '/app/projects') {
  await page.goto(path)
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.getByLabel('Name').fill('Dana')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

/** Opens the app shell's menu button when the viewport shows the collapsed (mobile) nav. */
export async function openNavIfCollapsed(page: Page) {
  const menu = page.getByRole('button', { name: 'Menu' })
  if (await menu.isVisible()) await menu.click()
}

export async function chooseTheme(page: Page, label: 'Light' | 'Dark' | 'System') {
  await page.getByRole('button', { name: /Toggle theme/ }).click()
  await page.getByRole('menuitemradio', { name: label }).click()
  await expect(page.getByRole('menu')).toBeHidden()
}
```

## Fail on console and network errors

Specs import `test`/`expect` from `./fixtures.ts` instead of `@playwright/test`. `net::ERR_ABORTED` is
ignored: it is a client cancel (a navigation leaving a page mid-load, an `AbortController`), and counting it
made the 375 px overflow test fail 11 of 30 runs under `--fail-on-flaky-tests`. A refused request
(`route.abort('connectionrefused')`) still fails the test (control run 2026-11-24).

`e2e/fixtures.ts`

```ts
import { test as base, expect } from '@playwright/test'

/**
 * Auto fixture: fails any test whose page logs a console error, throws an uncaught
 * exception, has a request that fails at the network level, or gets a 5xx response,
 * unless the message matches the test's `allowedErrors` pattern (an expected-failure scenario).
 * A single RegExp, not an array: Playwright reads an array passed to test.use() as [value, options].
 */
export const test = base.extend<{ allowedErrors: RegExp | null; failOnPageErrors: void }>({
  allowedErrors: [null, { option: true }],
  failOnPageErrors: [
    async ({ page, allowedErrors }, use) => {
      const errors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(`console: ${msg.text()}`)
      })
      page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))
      page.on('requestfailed', (req) => {
        const reason = req.failure()?.errorText ?? ''
        // net::ERR_ABORTED is a client-side cancel (a navigation leaving the page mid-load, or an AbortController
        // such as TanStack Query's on unmount), not a network failure. Every other reason still fails the test.
        if (reason === 'net::ERR_ABORTED') return
        errors.push(`requestfailed: ${req.url()} ${reason}`)
      })
      page.on('response', (res) => {
        if (res.status() >= 500) errors.push(`http ${res.status()}: ${res.url()}`)
      })
      await use()
      const unexpected = errors.filter((e) => !allowedErrors?.test(e))
      expect(unexpected, 'unexpected console/network errors').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
```

A test that exercises a failure states what it expects, and nothing else is tolerated: see the `server error`
block in `projects.spec.ts`. Without its `test.use`, that test fails on the 500 response and the logger's
`query failed` console line.

Verified: a planted `console.error` and a `route.abort('failed')` request each fail the test (exit 1).

## Visual regression

```ts
await expect(page).toHaveScreenshot('projects.png')
```

with `expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } }` in `playwright.config.ts`. Create
baselines once with `playwright test --update-snapshots=missing` and commit `e2e/*-snapshots/`. Baselines are
per platform (`*-darwin.png`, `*-linux.png`): generate the CI baselines in the CI image (or the official
Playwright Docker image), never by copying macOS ones. Verified: a planted colour change fails
`toHaveScreenshot` (and axe `color-contrast`), exit 1.

## CI cannot skip tests

- `forbidOnly: !!process.env.CI`: a committed `test.only` fails the run (verified: `CI=1` + `test.only` → exit 1).
- An empty selection fails: `playwright test` with no matching tests and `vitest run` with no test files both
  exit 1 by default. Never add `--pass-with-no-tests` / `passWithNoTests`.
- MSW `onUnhandledFrame: 'error'`: an unmocked request fails the unit test (verified, exit 1).
- CI runs `tsc -b`, `eslint .`, `vitest run`, `vite build` and `playwright test` as separate required steps,
  each with its own exit code, and installs the browser with `npm exec --no -- playwright install --with-deps chromium`.

## Full-stack apps (Next.js, React Router framework mode)

Same tools, different seams: Testing Library for Client Components, Playwright against the production
server (`next build && next start`). An async Server Component cannot be rendered by Testing Library.
Verified Playwright checks in a Next.js 16.4.6 app:

- Streaming: in the raw HTML from `request.get('/')`, the `<Suspense>` fallback appears before the
  streamed server data.
- Server/client boundary: no downloaded `.js` contains a server-only identifier; importing a `server-only`
  module into a `'use client'` file fails `next build`.
- Errors: `error.tsx` (a Client Component receiving `{ error, retry }` in Next.js 16.4) renders
  `role="alert"` with a retry button. Next.js adds its own empty `role="alert"` route announcer, so locate
  with `getByRole('alert').filter({ hasText: … })`. React logs error #441 ("The server could not finish this
  Suspense boundary … Switched to client rendering") for a boundary that failed on the server: allow it
  only in that test.

