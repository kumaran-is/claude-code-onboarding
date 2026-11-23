# Web Frontend Security (Angular 22, React)

Browser-side review rules for single-page apps and static sites. Angular rows are official-doc practice
(angular.dev v21 security guide, read through the Angular CLI MCP on 2026-11-22) or were executed in a
sandbox on Angular 21.2.26 in Chromium (Playwright 1.58.2) — each row says which. The toolkit now targets
Angular 22.3: the executed rows below were not re-run on 22.3, so re-check them in your app. React rows are
**RECOMMENDED PRACTICE**: not executed here, no production history claimed.

Severity labels match `security-review-checklist.md`. Server-side authorization rules live in the
`security-reviewer` agent (API Authorization Review); this file covers what the browser can and cannot do.

## 1. XSS sinks

| Sink | Rule | Severity if violated |
|---|---|---|
| `bypassSecurityTrustHtml/Script/Style/Url/ResourceUrl` on user, API, markdown or model data | Never. `bypassSecurityTrustUrl/ResourceUrl` only on a value the code built from a fixed scheme + origin + validated id (e.g. a fixed embed prefix + an id matching `^[A-Za-z0-9_-]{11}$`), as close to the input as possible | CRITICAL |
| `ElementRef.nativeElement.innerHTML =`, `outerHTML`, `insertAdjacentHTML`, `Renderer2.setProperty(el, 'innerHTML', …)`, `document.write` | Not sanitized by Angular (direct DOM APIs). Use template bindings | CRITICAL with untrusted data |
| `[innerHTML]` binding of a string | Angular sanitizes it, but keeps `<img src>` (tracking/exfiltration URLs) and leaves blocked links as `href="unsafe:javascript:…"` (executed sandbox run). For markdown/model output: `marked` → `DOMPurify.sanitize` (strict allowlist) → `[innerHTML]` — `ai-chat/reference/streaming-patterns.md` (Playwright-tested, with negative control) | HIGH for model/user HTML without DOMPurify |
| Templates built from user data, JIT compilation in production | Never. AOT (CLI default) prevents template injection (angular.dev v21 security guide) | CRITICAL |
| React `dangerouslySetInnerHTML` | Only with `DOMPurify.sanitize(html, strictConfig)` output — RECOMMENDED | CRITICAL with untrusted data |
| React `href`/`src`/`action` from user data | Allow `https:` (and `mailto:` where needed) by parsing with `new URL()`; React does not block every dangerous URL for you — RECOMMENDED, UNVERIFIED for React 19 specifics | HIGH |
| `eval`, `new Function`, `setTimeout(string)` | Never with any external data | CRITICAL |

Grep front-end: `grep -rnE "bypassSecurityTrust|nativeElement\.(inner|outer)HTML|insertAdjacentHTML|setProperty\([^)]*innerHTML|dangerouslySetInnerHTML|new Function|eval\(" src --include='*.ts' --include='*.tsx' --include='*.html'`. Every hit is reviewed; a hit is not automatically a finding (`/xss-scan` runs the same family of patterns).

## 2. Content Security Policy and critical-CSS inlining

Verified on Angular 21.2 (schema of `@angular/build@21.2.30` + Chromium run, 2026-11-22):

- `optimization.styles.inlineCritical` defaults to **true**. The build then emits
  `<link rel="stylesheet" media="print" onload="this.media='all'">`. Under `script-src 'self'` the inline
  `onload` is blocked (`script-src-attr` violation) and the global stylesheet **stays `media="print"`**: the
  app renders unstyled. This is a silent production defect, not just a console warning.
- Static hosting (no per-response nonce), option A: set `"inlineCritical": false` in the production
  `optimization.styles`. Result: 0 violations under
  `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`.
  Trade-off: no critical-CSS inlining, so first paint waits for the stylesheet — measure LCP before and after.
- Option B: `"security": { "autoCsp": true }` — **experimental/preview** in 21.2 (schema text: "Will default to
  true once we are out of experimental/preview phases"). The build adds a hash-based
  `<meta http-equiv="Content-Security-Policy" content="script-src 'strict-dynamic' 'sha256-…' https: 'unsafe-inline'; object-src 'none'; base-uri 'self';">`
  and a loader script, and critical CSS keeps working (0 violations, stylesheet `media="all"`). The HTTP header
  must then **omit** `default-src`/`script-src` (both policies apply; `default-src 'self'` in the header blocked the
  loader: 2 `script-src-elem` violations, app did not boot) and carry what a meta CSP cannot:
  `frame-ancestors 'none'`, plus `style-src`. Not for SSR responses (use a nonce there).
- SSR/edge rendering: per-request nonce via `ngCspNonce` on the root element or the `CSP_NONCE` token; with critical
  CSS inlining use `autoCsp` or `ngCspNonce`, not `CSP_NONCE` (v21 guide). Generate nonces at the edge; a CDN that
  caches HTML carrying a nonce makes it a constant (v21 guide).
- Component styles still need `style-src 'unsafe-inline'` unless you supply a style nonce.
- `subresourceIntegrity: true` adds integrity attributes; check the emitted `index.html` for any inline script it adds
  before tightening `script-src` (UNVERIFIED in this session).
- No inline `<script>` in `index.html` (theme bootstrap, analytics snippet): move it to a same-origin file. JSON-LD
  `<script type="application/ld+json">` is data and is not blocked by `script-src`.
- Third-party scripts/CSS: pin the exact version URL, add `integrity` + `crossorigin="anonymous"`, list the origin
  explicitly in CSP; prefer self-hosting (fonts especially) to remove the origin from CSP entirely.
- Roll out with `Content-Security-Policy-Report-Only` first, then enforce. The post-deploy header check in
  `deployment-ci-cd/reference/web-frontend-delivery.md` fails a release whose live CSP is missing or loosened.

## 3. Trusted Types (v21 guide)

`Content-Security-Policy: trusted-types angular angular#bundler; require-trusted-types-for 'script';`
(`angular#bundler` for lazy chunks). Needing `angular#unsafe-bypass` means the app calls `bypassSecurityTrust*` —
itself a review item. `angular#unsafe-jit` means JIT in production — CRITICAL. Start in report-only. Configure the
header in production serving and in `ng serve` (`headers` in `angular.json`) so E2E runs see the same policy.

## 4. Tokens, cookies and sessions

Angular implementation (allow-listed credential interceptor, single-flight refresh, session-restore guard, `returnUrl` validation, tested on 21.2): `angular-spa/reference/web-security.md`.

| Rule | Severity |
|---|---|
| App code never writes access/refresh tokens to `localStorage`/`sessionStorage` (`grep -rnE "(local\|session)Storage\.setItem\([^)]*(token\|jwt\|auth\|refresh)" src` → 0). XSS can read web storage | HIGH |
| Preferred: a backend-for-frontend (BFF) session in a `HttpOnly; Secure; SameSite=Lax` (or `Strict`) cookie, `__Host-` prefix, no `Domain` attribute. Bearer tokens, if used, live in memory (below) and are fetched from the auth SDK per request | — |
| An auth SDK that persists its own session in IndexedDB/localStorage (common for client SDKs; check yours — UNVERIFIED per SDK) is recorded as accepted residual risk with CSP + Trusted Types in place; consider session-only persistence for staff/admin consoles | MEDIUM if undocumented |
| Browser tests assert "session established" (UI state, an authorized API call returns 200), never "token present in localStorage" | — |
| Logout clears in-memory state, revokes the server session and does not rely on deleting client storage alone | MEDIUM |

**Bearer token only to allow-listed API origins** (framework-neutral rule). Parse the request URL with
`new URL(url, location.href)` and compare `origin` plus a path boundary against roots that come from validated
runtime config; never a bare `startsWith(root)` on the raw string (`https://api.example.com.evil.net` and
`https://api.example.com/v1x` must not match). Sending the token to every URL leaks it to third parties — HIGH.
Keep the token in memory (or behind a BFF cookie), refresh single-flight, and attach nothing to CDN or asset URLs.

- Angular (canonical, tested on 21.2: `API_CONFIG`, `core/auth/auth.interceptor.ts`, allow-list, single-flight
  refresh, guard, `returnUrl`): `angular-spa/reference/web-security.md`. Do not keep a second interceptor.
- React (RECOMMENDED PRACTICE): `react-spa/reference/server-state-and-api.md` (`apiRequest` credential allow-list).
- Runtime config that feeds the allow-list: `deployment-ci-cd/reference/web-frontend-delivery.md` §2.

## 5. CSRF / XSRF (Angular)

Verified (v21 guide + Chromium run): `HttpClient` copies the `XSRF-TOKEN` cookie into `X-XSRF-TOKEN` **only on
mutating requests to relative or same-origin URLs**. Same-origin `POST` carried the header; a same-origin `GET` and a
cross-origin `POST` to the API did not. Consequences:

- An API on another origin that authenticates with cookies gets **no** Angular XSRF protection. It needs its own
  design: `SameSite=Lax/Strict` session cookie + server-side `Origin`/`Sec-Fetch-Site` check, or a custom header
  the server requires. Missing → HIGH.
- The server must set the cookie and verify the header; Angular implements only the client half. Rename with
  `withXsrfConfiguration({ cookieName, headerName })` when several apps share a domain.
- Bearer-token APIs (no ambient cookie) are not CSRF-prone; cookie-session APIs are.

## 6. Authorization, guards and redirects

- Route guards (Angular `CanActivateFn`, React route loaders/wrappers) decide only "signed in → show this screen".
  They are UX. The server authorizes every request; hiding a button is not access control. A role check that exists
  only in the client → HIGH (CRITICAL if it gates writes).
- Guards await session restoration before deciding (otherwise a refresh bounces signed-in users to login).
- The UI renders 401 and 403 differently: 401 → clear session, re-authenticate with a safe `returnUrl`; 403 → "not
  authorized" state, no retry loop.
- Post-login redirect — open-redirect safe (compiled; 11 cases pass under Node 24's WHATWG URL parser, the same parser
  browsers use). Negative control: the common prefix check `startsWith('/') && !startsWith('//') && !startsWith('/\\')`
  accepts `"/\t/evil.com"`, which resolves to `https://evil.com/`. Open redirect → MEDIUM (HIGH when it carries
  tokens or OAuth codes).

```typescript
// core/auth/safe-return-url.ts — open-redirect-safe post-login target
const SENTINEL_ORIGIN = 'https://app.invalid';

/** Returns an in-app path (path + query + hash) or the fallback. Parse, don't prefix-match:
 *  the URL parser strips tab/newline, so '/\t/evil.com' would otherwise become '//evil.com'. */
export function safeReturnUrl(raw: string | null | undefined, fallback = '/'): string {
  if (!raw || !raw.startsWith('/')) return fallback;
  try {
    const url = new URL(raw, SENTINEL_ORIGIN);
    return url.origin === SENTINEL_ORIGIN ? `${url.pathname}${url.search}${url.hash}` : fallback;
  } catch {
    return fallback;
  }
}
// usage: void this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl')));
// never: location.href = returnUrl
```

## 7. OAuth / OIDC in the browser

- Authorization Code + PKCE (S256) only; no implicit flow; `state` (and `nonce` for OIDC) generated per attempt and
  checked; exact-match redirect URIs registered per environment, including preview channels — RECOMMENDED (OAuth 2.0
  for Browser-Based Apps BCP; not re-read this session).
- Popup flows need `Cross-Origin-Opener-Policy: same-origin-allow-popups` on the app origin; `same-origin` breaks the
  popup handshake.
- Tokens never in the URL after the callback (replace history), never in logs or error reports.

## 8. URLs, uploads, iframes, postMessage

- User/model URLs bound to `href`/`src`: parse with `new URL()`, allow `https:` (+ `mailto:` where needed) and, for
  images or embeds, an explicit host allowlist (A2UI: `a2ui-angular/reference/a2ui-renderer-patterns.md`, tested).
- Uploads: client-side type/size checks are UX only. The server validates size and content type by magic bytes, stores
  outside the web root, serves with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`, and never
  serves user uploads from the app origin.
- `<iframe>`: `sandbox` with the minimum tokens (never `allow-scripts` + `allow-same-origin` together for untrusted
  content); `src` built from a fixed origin.
- `postMessage` receivers check `event.origin` against an exact allowlist and validate the payload shape; senders pass
  an explicit `targetOrigin`, never `'*'`. Missing origin check → HIGH.

## 9. Secrets in bundles and supply chain

- Everything in `environment*.ts`, `fileReplacements`, `define`, `import.meta.env` / `VITE_*`, and served
  `config.json` is **public**. Only publishable identifiers may ship (a Firebase web config, a publishable payment key,
  a public analytics id). A server secret in a bundle → CRITICAL (rotate it; deleting the line is not enough).
- CI scans the build output, including any `.map` files, for secret patterns before deploy (e.g.
  `grep -rElI "sk_live_|-----BEGIN [A-Z ]*PRIVATE KEY|xox[abp]-" dist/` must find nothing; tune per stack).
- Source maps are not deployed publicly (`web-frontend-delivery.md` § Source maps).
- Release builds: `npm ci` from the lockfile, exact or `~` pins for app dependencies (no `^`, `*`, `latest`),
  `npm audit --audit-level=high` judged by its exit code, GitHub Actions pinned to commit SHAs
  (`security-review-checklist.md` §6).

## 10. Security headers baseline (static origin)

`Content-Security-Policy` (§2), `Strict-Transport-Security: max-age=63072000; includeSubDomains` (custom domains, once
HTTPS is confirmed everywhere), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`frame-ancestors 'none'` in CSP (or `X-Frame-Options: DENY`), `Permissions-Policy` for unused features,
COOP per §7. Authenticated apps and admin consoles also send `X-Robots-Tag: noindex`. Verify the **live** response
after every deploy, not the config file.

## 11. Privacy-aware client logging

Client error reports and analytics never contain tokens, cookies, `Authorization` headers, form values, emails, or
ids/query strings from URLs (send the route template, e.g. `/orders/:id`). Do not forward `HttpErrorResponse.message`
or server error bodies verbatim — servers echo submitted input. Details: `web-frontend-delivery.md` § Error monitoring.

## 12. SSR (Angular) — server-side request safety

v21 guide: configure `security.allowedHosts` in `angular.json` (or `NG_ALLOWED_HOSTS` for `AngularNodeAppEngine`);
avoid `*`. `X-Forwarded-*` headers are dropped unless `trustProxyHeaders` is set — enable it only behind a proxy that
overwrites them (header-based SSRF). Per-user data never in `useValue` providers that live across requests.

## Severity summary for reviewers

| Finding | Severity |
|---|---|
| `bypassSecurityTrust*` / raw DOM HTML / `dangerouslySetInnerHTML` on untrusted, API or model data | CRITICAL |
| Server secret in bundle, env file, `config.json` or source map | CRITICAL |
| JIT or runtime template construction from data in production | CRITICAL |
| Client-only authorization gating a write | CRITICAL |
| Token sent to non-allowlisted origins; token in web storage written by app code | HIGH |
| Cookie-session API on another origin with no CSRF design | HIGH |
| Model/user markdown rendered via `[innerHTML]` without DOMPurify | HIGH |
| `postMessage` without origin check; `targetOrigin: '*'` with sensitive data | HIGH |
| No CSP on an authenticated app, or CSP with `'unsafe-inline'` in `script-src` | HIGH |
| Default critical-CSS inlining under a strict `script-src` (unstyled app) | MEDIUM (functional) |
| Open redirect via `returnUrl` | MEDIUM (HIGH with tokens/codes) |
| Missing HSTS / nosniff / Referrer-Policy / frame-ancestors | MEDIUM |
| Public source maps | MEDIUM |
| Auth SDK web-storage persistence not documented as residual risk | MEDIUM |
