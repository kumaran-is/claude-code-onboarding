# Security — React SPA

> RECOMMENDED PRACTICE. Every control below has a positive test (attack neutralised) and a
> negative control (the naive code lets it through), run with Vitest on 2026-11-23.

## Rules

1. No `dangerouslySetInnerHTML` on user, CMS or model output without `DOMPurify.sanitize`. Prefer text
   (`{value}` is escaped by React) or a markdown renderer that does not emit raw HTML. AI/GenUI
   streams: `ai-chat` skill (`reference/streaming-patterns.md`); A2UI surfaces render only through
   catalog views behind the ingest guard and action allowlist in `generative-ui-a2ui.md`
   (framework-neutral rules: `a2ui-angular/reference/a2ui-security.md`).
2. URLs from data go through `safeHref` before `href`/`src` (`javascript:` and `data:` dropped).
3. Post-login redirects go through `safeReturnPath` (same-origin path only).
4. No tokens in `localStorage`/`sessionStorage` (readable by any XSS). Prefer an HttpOnly, Secure,
   SameSite cookie set by a BFF; otherwise keep the access token in memory and refresh via cookie.
5. Credentials only to allow-listed API origins (`apiRequest` in `server-state-and-api.md`).
6. `VITE_*` variables are public: Vite exposes every variable starting with `envPrefix` (default
   `'VITE_'`, from `vite/dist/node/index.d.ts`) to client code and inlines it into the bundle.
   Config only (API origin, feature flags), never secrets.
7. Client guards are UX; the server authorizes every request.
8. Keep a CSP (`script-src 'self'`, no `unsafe-inline`) at the host; it limits damage if a sink slips.
   Full host CSP: **UNVERIFIED here (no hosting config) — check before use.**
9. Enforce Trusted Types (React 19.3+): send `Content-Security-Policy: require-trusted-types-for 'script';
   trusted-types dompurify`. Every HTML sink then needs a `TrustedHTML`; `SafeHtml` gets one from
   `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: true })` (DOMPurify's default policy name is
   `dompurify`). React 19.3 passes Trusted Types objects to the DOM without string coercion (react.dev
   blog "React 19.3", 2026-09-09); earlier React turned them back into strings, which the browser rejects.
   Verified in Chromium with the header served by `vite preview` (below). Side effects found: zod 4's JIT
   probe logs a violation unless `z.config({ jitless: true })` runs at startup (`routing.md`, `main.tsx`), and
   test code that writes `innerHTML` is blocked too (build planted DOM with `createElement`).

## Code

`src/shared/ui/SafeHtml.tsx`

```tsx
import DOMPurify from 'dompurify'

/**
 * Renders HTML from users, CMS or model output only after DOMPurify. Prefer plain text when markup is not needed.
 * RETURN_TRUSTED_TYPE returns a TrustedHTML object where the browser supports Trusted Types (a string elsewhere);
 * React 19.3 passes it to innerHTML without converting it to a string, so a
 * `require-trusted-types-for 'script'` CSP can be enforced.
 */
export function SafeHtml({ html }: { html: string }) {
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: true }) }} />
}
```

`src/shared/lib/safe-url.ts`

```ts
/**
 * Returns a same-origin path for post-login redirects, or `fallback`.
 * Rejects absolute URLs, protocol-relative (`//evil`), backslash tricks (`/\evil`) and non-http schemes.
 */
export function safeReturnPath(raw: string | null, fallback: string): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return fallback
  if (!URL.canParse(raw, window.location.origin)) return fallback
  const url = new URL(raw, window.location.origin)
  return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : fallback
}

/** Allows only http(s) and mailto links from untrusted data; anything else (javascript:, data:) returns undefined. */
export function safeHref(raw: string): string | undefined {
  if (!URL.canParse(raw, window.location.origin)) return undefined
  const url = new URL(raw, window.location.origin)
  return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? url.href : undefined
}
```

## Tests with controls

`src/shared/lib/security.test.tsx`

```tsx
import { render } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { z } from 'zod'
import { server } from '@/test/msw-server'
import { SafeHtml } from '@/shared/ui/SafeHtml'
import { apiRequest, setAccessToken } from './http'
import { safeHref, safeReturnPath } from './safe-url'

const attacks = ['//evil.example/x', 'https://evil.example/x', '/\\evil.example', 'javascript:alert(1)', '']

describe('safeReturnPath (open-redirect guard)', () => {
  it.each(attacks)('rejects %j', (raw) => expect(safeReturnPath(raw, '/home')).toBe('/home'))
  it('keeps a same-origin path with query and hash', () =>
    expect(safeReturnPath('/app/projects?tab=2#x', '/home')).toBe('/app/projects?tab=2#x'))
  it('control: the naive "use returnUrl as-is" pattern lets the attack through', () => {
    const naive = (raw: string) => raw || '/home'
    const resolved = new URL(naive('//evil.example/x'), window.location.origin)
    expect(resolved.origin).toBe('http://evil.example')
  })
})

describe('safeHref', () => {
  it('drops javascript: and data: URLs', () => {
    expect(safeHref('javascript:alert(1)')).toBeUndefined()
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBeUndefined()
    expect(safeHref('https://example.com/a')).toBe('https://example.com/a')
  })
})

describe('SafeHtml', () => {
  const payload = '<img src="x" onerror="window.__pwned=1"><script>window.__pwned=2</script><b>ok</b>'
  it('strips script and event-handler attributes', () => {
    const { container } = render(<SafeHtml html={payload} />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')?.getAttribute('onerror')).toBeNull()
    expect(container.querySelector('b')).toHaveTextContent('ok')
  })
  it('control: raw dangerouslySetInnerHTML keeps the handler', () => {
    const { container } = render(<div dangerouslySetInnerHTML={{ __html: payload }} />)
    expect(container.querySelector('img')?.getAttribute('onerror')).toBe('window.__pwned=1')
  })
})

describe('apiRequest credential allow-list', () => {
  afterEach(() => setAccessToken(null))
  const seen: Record<string, string | null> = {}
  const record = (key: string) => ({ request }: { request: Request }) => {
    seen[key] = request.headers.get('authorization')
    return HttpResponse.json({ ok: true })
  }

  it('sends the token to the API origin only', async () => {
    server.use(
      http.get(`${window.location.origin}/api/me`, record('api')),
      http.get('https://third-party.example/collect', record('third')),
    )
    setAccessToken('secret-token')
    await apiRequest('/api/me', z.object({ ok: z.boolean() }))
    await apiRequest('https://third-party.example/collect', z.object({ ok: z.boolean() }))
    expect(seen.api).toBe('Bearer secret-token')
    expect(seen.third).toBeNull()
  })

  it('control: a request that attaches the header without the allow-list leaks it', async () => {
    server.use(http.get('https://third-party.example/collect', record('leak')))
    await fetch('https://third-party.example/collect', { headers: { Authorization: 'Bearer secret-token' } })
    expect(seen.leak).toBe('Bearer secret-token') // the recorder sees a leak, so the test above can fail
  })
})
```


## Trusted Types enforced end to end (Chromium)

Serve the header from the host in production. For `vite preview` (the E2E server) the validation app adds
to `vite.config.ts`:

```ts
preview: { headers: { 'Content-Security-Policy': "require-trusted-types-for 'script'; trusted-types dompurify" } },
```

The spec below exercises the React 19 examples on the settings route with the policy enforced. It uses
the console/page-error fixture from `testing.md` (`e2e/fixtures.ts`), so any Trusted Types violation (it
logs a console error) fails the test.

`e2e/react19.spec.ts`

```ts
import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures.ts' // fails a test on any console error, page error or 5xx

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const ATTACK = '<img src="x" alt="" onerror="window.__pwned=1"><b>Maintenance on Sunday</b>'

async function openSettings(page: Page) {
  // Count the browser View Transitions React starts (proves <ViewTransition> used the real API).
  await page.addInitScript(() => {
    const original = document.startViewTransition?.bind(document)
    if (!original) return
    const w = window as unknown as { __viewTransitions: number }
    w.__viewTransitions = 0
    document.startViewTransition = ((arg: Parameters<typeof original>[0]) => {
      w.__viewTransitions += 1
      return original(arg)
    }) as typeof document.startViewTransition
  })
  await page.route('**/api/projects', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/announcement', (route) => route.fulfill({ json: { html: ATTACK } }))
  await page.route('**/api/release-notes', (route) => route.fulfill({ json: ['Faster search'] }))
  await page.route('**/api/me/display-name', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300))
    await route.fulfill({ json: { name: (route.request().postDataJSON() as { name: string }).name } })
  })
  await page.goto('/app/settings')
  await page.getByLabel('Name').fill('Dana')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()
}

test('React 19.3 settings page: metadata, Actions, use(), ViewTransition, Fragment ref, Trusted Types, axe', async ({ page }) => {
  await openSettings(page)

  await expect(page).toHaveTitle('Settings · Projects app')

  // Trusted Types enforced by CSP: sanitized TrustedHTML renders, the handler is gone, no violation logged.
  await expect(page.getByText('Maintenance on Sunday')).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined()

  // use() + Suspense
  await expect(page.getByRole('list', { name: 'Release notes' })).toContainText('Faster search')

  // Action: pending UI from useFormStatus, optimistic name, then saved
  await page.getByLabel('Display name').fill('Robin')
  await page.getByRole('button', { name: 'Save name' }).click()
  await expect(page.getByRole('button', { name: 'Saving…' })).toBeDisabled()
  await expect(page.getByTestId('current-name')).toHaveText('Robin')
  await expect(page.getByRole('button', { name: 'Save name' })).toBeEnabled()

  // ViewTransition: the tab switch runs inside a browser view transition
  await page.getByRole('button', { name: 'Privacy' }).click()
  await expect(page.getByRole('heading', { name: 'Privacy' })).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { __viewTransitions?: number }).__viewTransitions)).toBeGreaterThan(0)

  // Fragment ref moves focus into the revealed group
  await page.getByRole('button', { name: 'Danger zone' }).click()
  await expect(page.getByRole('button', { name: 'Delete account' })).toBeFocused()

  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
  expect(violations.map((v) => v.id)).toEqual([])
})

test.describe('control', () => {
  // The blocked assignment logs a console error on purpose; allow only that message.
  test.use({ allowedErrors: /requires 'TrustedHTML' assignment/ })

  test('the CSP really enforces Trusted Types (a raw string into innerHTML is blocked)', async ({ page }) => {
    await openSettings(page)
    const outcome = await page.evaluate(() => {
      try {
        document.createElement('div').innerHTML = '<b>raw</b>'
        return 'allowed'
      } catch (error) {
        return (error as Error).name
      }
    })
    expect(outcome).toBe('TypeError')
  })
})
```

Evidence (2026-11-23, Chromium, 375 and 1280 px, TypeScript 6.0.3 toolchain from `tooling.md`): both
tests pass. Controls run against the same spec:
`DOMPurify.sanitize(html)` without `RETURN_TRUSTED_TYPE` → the sanitized text never renders (exit 1);
before `z.config({ jitless: true })` the guard reported "This document requires 'TrustedScript'
assignment" from the zod chunk (exit 1); the control test proves the policy is really enforced. Any
other spec that plants markup with `innerHTML` is blocked under this policy: build it with DOM APIs.
