# Routing — React Router 8 (data mode)

> RECOMMENDED PRACTICE. Code compiled and tested on `react-router@8.5.2` with React 19.3.1 (Vitest with
> `createMemoryRouter`, and Playwright in Chromium; re-run 2026-11-23 on Node 26.13.1).

## Package facts (verified 2026-11-23)

- `npm view react-router dist-tags`: `latest` 8.5.2, `version-7` 7.18.6.
- `npm view react-router-dom dist-tags`: `latest` **7.18.6** on 2026-11-24 (no v8; later 7.x releases keep
  the same problem). The v8 CHANGELOG says
  "Remove `react-router-dom` package". Installing `react-router-dom@latest` beside `react-router@8.5.2`
  produced `node_modules/react-router-dom/node_modules/react-router@7.18.6` — a second router copy.
  Import from `react-router` only; `RouterProvider` comes from `react-router/dom`.
- v8 requires React `>=19.2.7` and Node `>=22.22.0`; middleware is always on (the `future.v8_middleware`
  flag was removed).

## Mount

`src/main.tsx`

```tsx
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { z } from 'zod'
import { createQueryClient } from './app/query-client'
import { routes } from './app/routes'
import { Toaster } from './components/ui/toast'
import { applyStoredTheme } from './shared/ui/theme-context'
import { ThemeProvider } from './shared/ui/theme-provider'
import './index.css'

// zod 4 probes `new Function` for its JIT; under a Trusted Types / no-eval CSP the probe logs a violation.
z.config({ jitless: true })

const queryClient = createQueryClient()
const router = createBrowserRouter(routes)
const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('#root element missing from index.html')

applyStoredTheme() // before the first render: no flash of the wrong theme

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
      <Toaster />
    </ThemeProvider>
  </StrictMode>,
)
```

`z.config({ jitless: true })` stops zod 4 from probing `new Function` (its JIT). Under a CSP without
`unsafe-eval`, or with Trusted Types enforced (`security.md`), that probe logs a violation even though zod
catches it; the Playwright console-error guard caught it (`zod/v4/core/util.js` `allowsEval`).

## Route table: lazy routes, nested layout, auth middleware, error boundaries

`src/app/routes.tsx`

```tsx
import { redirect, type RouteObject } from 'react-router'
import { AppLayout } from './AppLayout'
import { lazyRoute } from './lazy-route'
import { FeatureErrorPage, RouteErrorPage } from './RouteErrorPage'
import { requireSession } from './session'

// Function-form `lazy`: the router writes the resolved properties back onto these route objects. With the
// object form (`lazy: { Component }`) a second router built from the same array (e.g. the next test) finds
// an emptied `lazy` object and returns 404 (verified with react-router 8.5.2).
export const routes: RouteObject[] = [
  {
    path: '/',
    ErrorBoundary: RouteErrorPage,
    children: [
      { index: true, loader: () => redirect('/app/projects') },
      {
        path: 'login',
        lazy: () => lazyRoute(async () => (await import('@/features/auth/routes/LoginPage')).LoginPage),
      },
      {
        path: 'app',
        middleware: [requireSession],
        Component: AppLayout,
        children: [
          {
            path: 'projects',
            lazy: () => lazyRoute(async () => (await import('@/features/projects/routes/ProjectsPage')).ProjectsPage),
            ErrorBoundary: FeatureErrorPage, // renders inside AppLayout's <main>: no second main landmark
          },
          {
            path: 'settings',
            lazy: () => lazyRoute(async () => (await import('@/features/settings/routes/SettingsPage')).SettingsPage),
            ErrorBoundary: FeatureErrorPage,
          },
        ],
      },
      { path: '*', loader: () => { throw new Response(null, { status: 404, statusText: 'Not Found' }) } },
    ],
  },
]
```

Object-form `lazy` (`lazy: { Component: async () => ... }`) also works and lets loader and component load
in parallel, but React Router writes the resolved values back onto the route object and empties the
`lazy` object. A second router created from the same array (each test, or HMR) then cannot match the
route and returns 404. Either use the function form (above) or build routes with a `createRoutes()`
function per router.

`vite build` emits a separate chunk per lazy route (`LoginPage-*.js`, `ProjectsPage-*.js`,
`SettingsPage-*.js`; React 19.3.1 build, 2026-11-23). The settings route hosts the React 19 examples
(`forms.md`, `architecture-and-state.md`, `performance.md`, `security.md`).

### A chunk that fails to load must not blank the page

After a deploy replaces the hashed files, an open tab can request a chunk that no longer exists. With a
plain `lazy: async () => ({ Component: (await import(...)).X })`, react-router 8.5.2 keeps `lazy` on the
route whose import rejected and renders only the root match: the page goes blank and no ErrorBoundary
runs (reproduced in Chromium by answering the chunk request with 404). `lazyRoute` resolves with a
component that throws instead, so the route's own boundary shows the error inside the layout.

`src/app/lazy-route.ts`

```ts
import type { ComponentType } from 'react'
import { logger } from '@/shared/lib/logger'

export async function lazyRoute(load: () => Promise<ComponentType>): Promise<{ Component: ComponentType }> {
  try {
    return { Component: await load() }
  } catch (error) {
    logger.error('route chunk failed to load', { error: String(error) })
    return {
      Component: function ChunkLoadFailed(): never {
        throw new Error('This page failed to load. Reload the app to get the latest version.')
      },
    }
  }
}
```

Tested in Chromium at 375 and 1280 px: chunk answered with 404 → error heading and alert inside the
layout, one `<main>` (exit 0); the plain `lazy` form → blank page (exit 1). Keep the previous release's
hashed files on the host for a while after a deploy (`deployment-ci-cd/reference/web-frontend-delivery.md`)
so most open tabs never hit this path.

## Session and auth middleware (UX only)

`src/app/session.ts`

```ts
import { redirect, type MiddlewareFunction } from 'react-router'
import { setAccessToken } from '@/shared/lib/http'

export type Session = { userName: string }

// In-memory session for the demo. A real app asks the server (cookie session or token refresh) here.
let current: Session | null = null

export const session = {
  get: (): Session | null => current,
  signIn(userName: string, accessToken: string): void {
    current = { userName }
    setAccessToken(accessToken)
  },
  signOut(): void {
    current = null
    setAccessToken(null)
  },
}

/** Route middleware: UX only. The API still authorizes every request. */
export const requireSession: MiddlewareFunction = ({ request }) => {
  if (session.get()) return
  const { pathname, search } = new URL(request.url)
  throw redirect(`/login?returnUrl=${encodeURIComponent(`${pathname}${search}`)}`)
}
```

A real app restores the session from the server (cookie session, or a refresh endpoint that sets an
HttpOnly cookie) before deciding; the middleware can `await` that. The API still authorizes every call.

## returnUrl validation

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

`src/features/auth/routes/LoginPage.tsx`

```tsx
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'
import { session } from '@/app/session'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { safeReturnPath } from '@/shared/lib/safe-url'

const loginSchema = z.object({ userName: z.string().trim().min(1, 'Enter your name') })
type LoginValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { userName: '' } })

  function signIn({ userName }: LoginValues) {
    // Demo only: a real app posts credentials to its auth endpoint and receives an HttpOnly cookie or token.
    session.signIn(userName, 'demo-access-token')
    navigate(safeReturnPath(searchParams.get('returnUrl'), '/app/projects'), { replace: true })
  }

  return (
    <main className="flex flex-col gap-4">
      <h1>Sign in</h1>
      <form onSubmit={handleSubmit(signIn)} noValidate>
        <FieldGroup>
          <Field data-invalid={!!errors.userName}>
            <FieldLabel htmlFor="login-name">Name</FieldLabel>
            <Input
              id="login-name"
              autoComplete="username"
              aria-invalid={errors.userName ? true : undefined}
              aria-describedby={errors.userName ? 'login-name-error' : undefined}
              {...register('userName')}
            />
            {errors.userName && <FieldError id="login-name-error" errors={[errors.userName]} />}
          </Field>
          <Button type="submit">Sign in</Button>
        </FieldGroup>
      </form>
    </main>
  )
}
```

## Layout with focus management

`src/app/AppLayout.tsx`

```tsx
import { MenuIcon } from '@/shared/ui/icons'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { cn } from 'cn'
import { Button, buttonVariants } from '@/components/ui/button'
import { ModeToggle } from '@/shared/ui/mode-toggle'
import { session } from './session'

const links = [
  { to: '/app/projects', label: 'Projects' },
  { to: '/app/settings', label: 'Settings' },
]

/**
 * Authenticated shell. Moves focus to <main> after client-side navigation so keyboard and screen-reader users land on the new page.
 * Responsive: viewport breakpoint `sm:` (640px) switches the nav between a collapsible menu and an inline row;
 * the `@container` on the header row decides (by its own width) whether "Signed in as" is shown.
 */
export function AppLayout() {
  const mainRef = useRef<HTMLElement>(null)
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    mainRef.current?.focus()
  }, [pathname])

  function signOut() {
    session.signOut()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <header className="border-b">
        <div className="@container mx-auto flex max-w-4xl flex-wrap items-center gap-2 p-3" data-testid="header-container">
          <Button
            variant="outline"
            className="sm:hidden"
            aria-expanded={menuOpen}
            aria-controls="main-nav"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MenuIcon data-icon="inline-start" aria-hidden="true" /> Menu
          </Button>
          <nav
            id="main-nav"
            aria-label="Main"
            className={cn('order-last w-full flex-col gap-1 sm:order-none sm:flex sm:w-auto sm:flex-row', menuOpen ? 'flex' : 'hidden')}
          >
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  cn(buttonVariants({ variant: isActive ? 'secondary' : 'ghost' }), 'justify-start')
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground @lg:inline">Signed in as {session.get()?.userName}</span>
            <ModeToggle />
            <Button variant="outline" onClick={signOut}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main ref={mainRef} tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
```

Moving focus to `<main>` (with `tabIndex={-1}`) after navigation lets keyboard and screen-reader users
start on the new page. Give each page one `<h1>`.

## Error boundaries

`src/app/RouteErrorPage.tsx`

```tsx
import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { logger } from '@/shared/lib/logger'

function RouteErrorContent() {
  const error = useRouteError()
  const title = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : 'Something went wrong'
  if (!isRouteErrorResponse(error)) logger.error('route render failed', { error: String(error) })
  return (
    <>
      <h1 id="route-error-title">{title}</h1>
      <p role="alert">This page could not be displayed.</p>
      <Link to="/">Go to the start page</Link>
    </>
  )
}

/** Top-level boundary: no layout around it, so it owns the page's single <main>. */
export function RouteErrorPage() {
  return (
    <main>
      <RouteErrorContent />
    </main>
  )
}

/** Boundary of a route nested in AppLayout, which already renders <main>: one main landmark per page. */
export function FeatureErrorPage() {
  return (
    <section aria-labelledby="route-error-title">
      <RouteErrorContent />
    </section>
  )
}
```

For lazy components outside the router (a heavy chart, an editor), wrap `<Suspense fallback>` in
`ErrorBoundary` from `react-error-boundary` and log in its `onError`; with `useSuspenseQuery`, add
`QueryErrorResetBoundary` so Retry refetches. **UNVERIFIED in this app — check before use.**

## Tests

`src/app/routes.test.tsx`

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { ThemeProvider } from '@/shared/ui/theme-provider'
import { server } from '@/test/msw-server'
import { routes } from './routes'
import { session } from './session'

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>,
  )
  return router
}

describe('routing', () => {
  afterEach(() => session.signOut())

  it('redirects a signed-out user to login with returnUrl, then back to the lazy route', async () => {
    server.use(http.get(`${window.location.origin}/api/projects`, () => HttpResponse.json([])))
    const router = renderAt('/app/projects?tab=2')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?returnUrl=%2Fapp%2Fprojects%3Ftab%3D2')

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Name'), 'Dana')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(router.state.location.pathname + router.state.location.search).toBe('/app/projects?tab=2')
  })

  it('ignores an external returnUrl', async () => {
    server.use(http.get(`${window.location.origin}/api/projects`, () => HttpResponse.json([])))
    const router = renderAt('/login?returnUrl=%2F%2Fevil.example%2Fphish')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Name'), 'Dana')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/projects')
  })

  it('renders the route error boundary for an unknown URL', async () => {
    renderAt('/does-not-exist')
    expect(await screen.findByRole('heading', { name: '404 Not Found' })).toBeInTheDocument()
  })
})
```

