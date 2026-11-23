# Testing — Vitest, Testing Library, MSW, Playwright + axe

> RECOMMENDED PRACTICE. All files below ran green on 2026-11-23 (Vitest, and Playwright in Chromium at
> 375 and 1280 px, `@playwright/test@1.65.1`). Tool choice by target: `.claude/rules/testing-tool-selection.md`.
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
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
    },
  }),
)
```

`src/test/setup.ts`

```ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './msw-server'

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
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

/** Fresh QueryClient per test, retries off so error states appear immediately. */
export function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
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
  retries: process.env.CI ? 1 : 0,
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
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function axeViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

async function signIn(page: Page) {
  await page.goto('/app/projects')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('returnUrl')).toBe('/app/projects')
  await page.getByLabel('Name').fill('Dana')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
}

test.describe('projects feature', () => {
  test('loaded list, dialog form validation and axe (no automated violations)', async ({ page }) => {
    await page.route('**/api/projects', (route) =>
      route.fulfill({ json: [{ id: '1', name: 'Alpha', ownerEmail: 'a@example.com' }] }),
    )
    await signIn(page)
    await expect(page.getByRole('list', { name: 'Projects' })).toContainText('Alpha')
    expect(await axeViolations(page)).toEqual([])

    const opener = page.getByRole('button', { name: 'New project' })
    await opener.click()
    const dialog = page.getByRole('dialog', { name: 'New project' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Create project' }).click()
    const name = dialog.getByLabel('Project name')
    await expect(name).toHaveAttribute('aria-invalid', 'true')
    await expect(name).toHaveAccessibleDescription('Name must be at least 3 characters')
    await expect(name).toBeFocused()
    expect(await axeViolations(page)).toEqual([])

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(opener).toBeFocused()
  })

  test('server error shows an alert with retry', async ({ page }) => {
    await page.route('**/api/projects', (route) => route.fulfill({ status: 500, body: '' }))
    await signIn(page)
    // TanStack Query retries a failed query 3 times with backoff (~7 s) before showing the error state.
    await expect(page.getByRole('alert')).toContainText('Projects could not be loaded', { timeout: 15_000 })
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
    expect(await axeViolations(page)).toEqual([])
  })

  test('empty list shows an empty state', async ({ page }) => {
    await page.route('**/api/projects', (route) => route.fulfill({ json: [] }))
    await signIn(page)
    await expect(page.getByText('No projects yet')).toBeVisible()
  })

  test('positive control: axe detects a planted violation in real Chromium', async ({ page }) => {
    await page.route('**/api/projects', (route) => route.fulfill({ json: [] }))
    await signIn(page)
    await page.evaluate(() => {
      const button = document.createElement('button') // no accessible name
      button.innerHTML = '<svg width="24" height="24" aria-hidden="true"></svg>'
      document.querySelector('main')?.append(button)
    })
    expect((await axeViolations(page)).some((v) => v.startsWith('button-name'))).toBe(true)
  })
})
```

- The API is mocked with `page.route`, so the run needs no backend.
- Positive control kept in the suite: an injected unnamed button must produce `button-name`.
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
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "strict": true
  },
  "include": ["e2e"]
}
```

