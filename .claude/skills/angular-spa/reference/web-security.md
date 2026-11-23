# Angular 22.3 Auth and Web Security — Canonical Reference

Canonical home for Angular authentication plumbing: credential allow-list, token refresh, auth
guard, safe `returnUrl`, token storage and Angular XSS rules. Framework-neutral browser security
(CSP, Trusted Types, headers, OAuth PKCE, uploads, postMessage, supply chain) lives in
`../../security-reviewer/reference/web-frontend-security.md`.

Every file below compiled against `@angular/*@21.2.26`, TypeScript 5.9.3, `strictTemplates`, and the
specs in §Testing passed under `ng test` (Vitest); on 22.3.0 / TypeScript 6.0.3 the code was re-compiled
but the specs were not re-run. Negative controls (the old interceptor and guard
from earlier versions of this skill) were run and **failed** the same specs — see the report for
commands.

## Ground rules

1. **Client guards are UX.** They hide pages; they do not protect data. The API authorizes every
   request and returns 401/403.
2. **Credentials go only to allow-listed API origins.** An interceptor that adds `Authorization` to
   every request leaks the token to CDNs, analytics and look-alike hosts.
3. **Tokens never in `localStorage`/`sessionStorage`** (readable by any XSS). Prefer an HttpOnly,
   `Secure`, `SameSite` cookie set by the API or a backend-for-frontend (BFF). If the API needs a
   bearer token, keep the access token **in memory** and refresh it via an HttpOnly refresh cookie.
4. **Frontend config is public.** `environment.ts` and runtime config ship to every browser; no
   secrets, client secrets or private keys.
5. **Refresh at most once per 401 burst, retry at most once per request.** A second 401 surfaces;
   it never loops.

## Config token

```typescript
// core/config/api-config.ts
import { InjectionToken } from '@angular/core';

export interface ApiConfig {
  /** Absolute API roots that may receive credentials, e.g. 'https://api.example.test/v1'. */
  readonly apiRoots: readonly string[];
  /** Absolute URL of the refresh endpoint (reads/sets an HttpOnly refresh cookie). */
  readonly refreshUrl: string;
}

export const API_CONFIG = new InjectionToken<ApiConfig>('API_CONFIG');
```

## Allow-list check

```typescript
// core/auth/allowlist.ts
/**
 * True only when `url` (absolute or relative to `base`) is under one of `roots`: same origin
 * (scheme + host + port) AND path equal to the root path or below it on a '/' boundary.
 * URL parsing defeats 'https://api.example.test.evil.com', 'https://api.example.test@evil.com'
 * and '/v10' vs '/v1'. String startsWith() checks do not.
 */
export function isAllowlisted(url: string, roots: readonly string[], base: string): boolean {
  let target: URL;
  try {
    target = new URL(url, base);
  } catch {
    return false;
  }
  return roots.some((raw) => {
    const root = new URL(raw);
    const rootPath = root.pathname.replace(/\/+$/, '');
    return (
      target.origin === root.origin &&
      (target.pathname === rootPath || target.pathname.startsWith(`${rootPath}/`))
    );
  });
}
```

## Session: in-memory token, single-flight refresh, restore once

```typescript
// core/auth/auth-session.ts
import { HttpClient, HttpContext, HttpContextToken, HttpErrorResponse } from '@angular/common/http';
import { Service, computed, inject, signal } from '@angular/core';
import { Observable, catchError, finalize, firstValueFrom, map, of, shareReplay, tap, throwError } from 'rxjs';
import { API_CONFIG } from '../config/api-config';

/** Marks requests the auth interceptor must not touch (the refresh call itself). */
export const SKIP_AUTH = new HttpContextToken<boolean>(() => false);

type SessionStatus = 'restoring' | 'signed-in' | 'signed-out';

@Service()
export class AuthSession {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  private readonly token = signal<string | null>(null); // memory only
  private readonly status = signal<SessionStatus>('restoring');
  readonly isSignedIn = computed(() => this.status() === 'signed-in');

  private refreshInFlight: Observable<string> | null = null;
  private restored: Promise<boolean> | null = null;

  accessToken(): string | null {
    return this.token();
  }

  /** Single-flight: concurrent callers share one refresh request. */
  refresh(): Observable<string> {
    this.refreshInFlight ??= this.http
      .post<{ accessToken: string }>(this.config.refreshUrl, null, {
        withCredentials: true, // sends the HttpOnly refresh cookie
        context: new HttpContext().set(SKIP_AUTH, true),
      })
      .pipe(
        map((res) => res.accessToken),
        tap({
          next: (accessToken) => {
            this.token.set(accessToken);
            this.status.set('signed-in');
          },
          error: () => this.expire(),
        }),
        finalize(() => (this.refreshInFlight = null)),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    return this.refreshInFlight;
  }

  /**
   * Restores the session once at startup. Resolves false when the server says there is no session
   * (401/403); rejects on any other failure so the guard shows an error, not a login loop.
   */
  restore(): Promise<boolean> {
    this.restored ??= firstValueFrom(
      this.refresh().pipe(
        map(() => true),
        catchError((err: unknown) =>
          err instanceof HttpErrorResponse && (err.status === 401 || err.status === 403)
            ? of(false)
            : throwError(() => err),
        ),
      ),
    );
    return this.restored;
  }

  expire(): void {
    this.token.set(null);
    this.status.set('signed-out');
  }
}
```

With a cookie/BFF session instead of bearer tokens, drop `token`/`Authorization` and keep the same
shape: `withCredentials: true` only for allow-listed origins, `restore()` calls a `/session`
endpoint, and Angular's XSRF support (`withXsrfConfiguration`) covers same-origin mutating requests
only — cross-origin APIs need their own CSRF defence (SameSite cookies + server checks).

## Interceptor

```typescript
// core/auth/auth.interceptor.ts
import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { DOCUMENT, inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { API_CONFIG } from '../config/api-config';
import { isAllowlisted } from './allowlist';
import { AuthSession, SKIP_AUTH } from './auth-session';

const withToken = (req: HttpRequest<unknown>, token: string | null) =>
  token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const { apiRoots } = inject(API_CONFIG);
  const session = inject(AuthSession);
  const base = inject(DOCUMENT).baseURI;

  // Never attach credentials to third-party, CDN or look-alike origins.
  if (req.context.get(SKIP_AUTH) || !isAllowlisted(req.url, apiRoots, base)) {
    return next(req);
  }

  return next(withToken(req, session.accessToken())).pipe(
    catchError((err: unknown) => {
      // 403 = authenticated but not allowed: surface it, never refresh.
      if (!(err instanceof HttpErrorResponse) || err.status !== 401) {
        return throwError(() => err);
      }
      // One refresh (shared by all concurrent 401s), one retry through `next`, so a second 401
      // propagates instead of looping. A failed refresh expires the session and rethrows the 401.
      return session.refresh().pipe(
        catchError(() => throwError(() => err)),
        switchMap((token) => next(withToken(req, token))),
      );
    }),
  );
};
```

Register: `provideHttpClient(withInterceptors([authInterceptor]))` plus an `API_CONFIG`
provider (see `angular-templates.md` §app.config.ts).

## Guard that waits for session restore

```typescript
// core/auth/signed-in.guard.ts
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Logger } from '../logging/logger';
import { AuthSession } from './auth-session';

/** UX only: hides pages from signed-out users. The API still authorizes every request. */
export const signedInGuard: CanActivateFn = async (_route, state) => {
  // inject() only works synchronously: resolve every dependency before the first await.
  const session = inject(AuthSession);
  const router = inject(Router);
  const logger = inject(Logger);
  try {
    if (await session.restore()) return true; // no flash of the login page on reload
  } catch (err) {
    logger.error('Session restore failed', err);
    return router.createUrlTree(['/unavailable']);
  }
  return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};
```

A synchronous `auth.isSignedIn() ? true : redirect` guard races the restore on a hard reload and
bounces signed-in users to the login page.

## Safe `returnUrl`

```typescript
// core/auth/safe-return-url.ts
const PROBE_ORIGIN = 'https://app.invalid';

/**
 * Accepts only an app-relative path ('/orders?id=1#x'); anything that would leave the origin
 * ('//evil.com', '/\\evil.com', '/\t/evil.com', 'https://…', 'javascript:…') returns `fallback`.
 */
export function safeReturnUrl(raw: string | null | undefined, fallback = '/'): string {
  if (!raw || !raw.startsWith('/')) return fallback;
  let parsed: URL;
  try {
    parsed = new URL(raw, PROBE_ORIGIN);
  } catch {
    return fallback;
  }
  if (parsed.origin !== PROBE_ORIGIN) return fallback;
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}
```

After login: `router.navigateByUrl(safeReturnUrl(route.snapshot.queryParamMap.get('returnUrl')))`.
A `startsWith('/') && !startsWith('//')` check is **not** enough: URL parsing strips tabs/newlines,
so `'/\t/evil.com'` resolves to `https://evil.com/` (verified in Chromium 145).

## 401 vs 403 in the UI

401 after the interceptor gave up = the session is gone → "Sign in again" (navigate to login with a
safe `returnUrl`). 403 = signed in but not allowed → explain, no retry, no refresh. Typed error model
and messages: `../../angular-ui-patterns/reference/error-handling.md`.

## XSS rules for Angular templates

- Interpolation and property bindings are escaped/sanitized by Angular. Keep it that way.
- Never call `bypassSecurityTrustHtml/Url/ResourceUrl/Script/Style` on user, API or model output.
- `[innerHTML]` only with content you sanitized with DOMPurify (strict allow-list) first; prefer
  rendering text. Markdown/LLM output pipeline: `../../ai-chat/reference/streaming-patterns.md`.
- No `document.write`, `insertAdjacentHTML`, `eval`, `new Function`, or building `href` from input
  without an `https:`/relative check.
- A post-edit advisory hook flags these sinks; CSP + Trusted Types guidance lives in the web
  security reference linked above.

## Testing

Specs that prove the behaviour (all passing under 21.2 Vitest; the pre-fix interceptor and guard
fail them):

```typescript
// auth.interceptor.spec.ts (excerpt)
it.each([
  'https://api.example.test.evil.com/v1/users', // look-alike host
  'https://api.example.test@evil.com/v1/users', // userinfo trick
  'https://api.example.test/v10/users',         // path boundary
  'http://api.example.test/v1/users',           // scheme downgrade
  'https://cdn.other.test/lib.js',              // third party
])('never attaches credentials to %s', async (url) => {
  await signIn();
  http.get(url).subscribe();
  const req = ctrl.expectOne(url);
  expect(req.request.headers.has('Authorization')).toBe(false);
  expect(req.request.withCredentials).toBe(false);
  req.flush({});
});

it('refreshes once for concurrent 401s, then retries each request once', async () => {
  await signIn('old');
  const a = firstValueFrom(http.get<string>(`${API}/a`));
  const b = firstValueFrom(http.get<string>(`${API}/b`));
  ctrl.expectOne(`${API}/a`).flush(null, { status: 401, statusText: 'Unauthorized' });
  ctrl.expectOne(`${API}/b`).flush(null, { status: 401, statusText: 'Unauthorized' });
  ctrl.expectOne(REFRESH).flush({ accessToken: 'new' }); // exactly one refresh
  const retryA = ctrl.expectOne(`${API}/a`);
  expect(retryA.request.headers.get('Authorization')).toBe('Bearer new');
  retryA.flush('A');
  ctrl.expectOne(`${API}/b`).flush('B');
  await expect(Promise.all([a, b])).resolves.toEqual(['A', 'B']);
});

it('does not loop when the retried request is still 401', async () => {
  await signIn();
  const result = firstValueFrom(http.get(`${API}/a`));
  ctrl.expectOne(`${API}/a`).flush(null, { status: 401, statusText: 'Unauthorized' });
  ctrl.expectOne(REFRESH).flush({ accessToken: 't2' });
  ctrl.expectOne(`${API}/a`).flush(null, { status: 401, statusText: 'Unauthorized' });
  await expect(result).rejects.toMatchObject({ status: 401 });
  ctrl.expectNone(REFRESH);
});
```

```typescript
// signed-in.guard.spec.ts (excerpt) — RouterTestingHarness with a real router config
it('waits for a slow session restore instead of redirecting', async () => {
  setup(() => new Promise((resolve) => setTimeout(() => resolve(true), 50)));
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl('/secret');
  expect(TestBed.inject(Router).url).toBe('/secret');
});

it('redirects a signed-out user to /login with returnUrl', async () => {
  setup(() => Promise.resolve(false));
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl('/secret?tab=2');
  expect(TestBed.inject(Router).url).toBe('/login?returnUrl=%2Fsecret%3Ftab%3D2');
});
```

Also test: 403 never triggers refresh; a failed refresh expires the session; `safeReturnUrl`
rejects `'//evil.com'`, `'/\\evil.com'`, `'/\t/evil.com'`, `'https://evil.com'`, `'javascript:alert(1)'`.
Browser-level proof (real Chromium, Playwright): `browser-testing` skill.
