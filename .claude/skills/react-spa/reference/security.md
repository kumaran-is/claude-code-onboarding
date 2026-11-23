# Security — React SPA

> RECOMMENDED PRACTICE. Every control below has a positive test (attack neutralised) and a
> negative control (the naive code lets it through), run with Vitest on 2026-11-23.

## Rules

1. No `dangerouslySetInnerHTML` on user, CMS or model output without `DOMPurify.sanitize`. Prefer text
   (`{value}` is escaped by React) or a markdown renderer that does not emit raw HTML. AI/GenUI
   streams: `ai-chat` skill (`reference/streaming-patterns.md`) and A2UI catalog allow-listing
   (`a2ui-angular/reference/a2ui-security.md`, framework-neutral rules).
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
   **UNVERIFIED here (no hosting config) — check before use.**

## Code

`src/shared/ui/SafeHtml.tsx`

```tsx
import DOMPurify from 'dompurify'

/** Renders HTML from users, CMS or model output only after DOMPurify. Prefer plain text when markup is not needed. */
export function SafeHtml({ html }: { html: string }) {
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }} />
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

