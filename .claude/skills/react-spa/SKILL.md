---
name: react-spa
description: "React 19 single-page app development with Vite 8, TypeScript 5.9.3, React Router 8 (data mode), TanStack Query 5, React Hook Form + zod 4, Vitest + Testing Library + MSW, and Playwright + axe. Use when building or changing React web components, hooks, routes, forms, server state, API clients, auth plumbing, performance or tests. Not for React Native (mobile-developer) and not a Next.js/SSR guide."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch
metadata:
  triggers: React, React 19, Vite, React SPA, tsx component, React hook, useEffect, React Router, TanStack Query, React Query, React Hook Form, zod, Vitest React, Testing Library, MSW, React Compiler
  related-skills: accessibility-audit, browser-testing, design-system, security-reviewer, ai-chat, web-performance-optimization, typescript-expert
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# React SPA Development Skill

> **RECOMMENDED PRACTICE.** This toolkit has no production React history. Everything here is current
> official guidance plus patterns that were compiled and executed in a disposable Vite app on
> 2026-11-22/23 (`tsc -b`, ESLint, Vitest, `vite build`, Playwright + axe in Chromium: all exit 0).
> It is not a record of what any team shipped. Where something could not be executed it says
> **UNVERIFIED — check before use**.

## Iron Law

**CLASSIFY THE STATE BEFORE WRITING THE COMPONENT, AND WRITE NO EFFECT WITHOUT AN EXTERNAL SYSTEM.**
Local UI → `useState`; URL → search params; server data → TanStack Query; derived → computed in render.
An effect exists only to synchronise with something outside React (a browser API, a socket, a widget).

## Stack (pinned, verified together)

| Package | Version | Note |
|---|---|---|
| `react`, `react-dom` | `19.3.1` | `ref` is a plain prop; `<Ctx value>` is the provider; `useEffectEvent`, `useOptimistic`, `useActionState`, `Activity` exported |
| `vite` / `@vitejs/plugin-react` | `8.3.8` / `6.3.0` | creator `create-vite@9.3.4` (template `react-ts`) |
| `typescript` | `5.9.3` | **pin it**: `create-vite@9.3.4` ships `typescript ~7.0.2` and no `strict`; `typescript-eslint@8.73.0` peers `typescript >=4.8.4 <6.1.0` |
| `react-router` | `8.5.2` | **not** `react-router-dom` (see Routing) |
| `@tanstack/react-query` (+ eslint plugin) | `5.108.3` | |
| `react-hook-form` / `@hookform/resolvers` / `zod` | `7.92.0` / `7.0.8` / `4.6.7` | |
| `react-error-boundary` / `dompurify` | `6.1.6` / `3.5.0` | |
| `babel-plugin-react-compiler` / `@rolldown/plugin-babel` | `1.0.0` / `0.3.1` | React Compiler 1.0 (stable) |
| `vitest` / `jsdom` | `5.1.1` / `31.0.1` | |
| `@testing-library/react` / `user-event` / `jest-dom` | `16.3.3` / `14.6.13` / `8.0.0` | |
| `msw` | `3.0.7` | v3 option is `onUnhandledFrame` (v2's `onUnhandledRequest` no longer type-checks) |
| `@playwright/test` / `@axe-core/playwright` | `1.65.1` / `4.14.0` | |
| `eslint` / `typescript-eslint` | `9.39.5` / `8.73.0` | ESLint 9 because `eslint-plugin-jsx-a11y@6.10.2` peers ESLint `<=9` |
| `eslint-plugin-react-hooks` / `eslint-plugin-jsx-a11y` | `7.1.1` / `6.10.2` | |

Node 24.x (React Router 8 requires Node `>=22.22.0`). Pin exact versions (`npm i -E`); re-check with
`npm view <pkg> version` before moving any row, and re-run the verification below after a move.

## Documentation sources

| Need | Where |
|---|---|
| React APIs, rules, compiler | react.dev (Context7 `/reactjs/react.dev` when quota allows) |
| Installed truth | `node_modules/<pkg>/package.json`, `*.d.ts`, `CHANGELOG.md`, `README.md` |
| React Router 8 | `node_modules/react-router/CHANGELOG.md`; reactrouter.com |
| TanStack Query | tanstack.com/query/v5; `node_modules/@tanstack/query-core/build/modern/*.d.ts` |
| Versions | `npm view <pkg> version dist-tags` |

Trust the installed `.d.ts` over memory: the MSW 3 option rename and the TanStack v5 callback
signatures below were found that way.

## Project structure (by feature)

```text
src/
  main.tsx                     createRoot + StrictMode + QueryClientProvider + RouterProvider
  app/                         routes.tsx, AppLayout.tsx, RouteErrorPage.tsx, query-client.ts, session.ts
  features/<feature>/
    routes/                    route components (lazy-loaded)
    components/                feature components (may use queries, router hooks)
    api/                       <feature>.api.ts (fetch + zod parse), <feature>.queries.ts (keys, queryOptions, mutations)
    model/                     zod schemas + inferred types (shared by form and API parse)
  shared/
    ui/                        presentational only: props in, callbacks out. No useQuery, no router hooks, no fetch
    lib/                       http.ts, logger.ts, safe-url.ts (pure utilities; Rule of Three before adding)
  test/                        setup.ts, msw-server.ts, render.tsx
e2e/                           Playwright specs
```

A feature imports `shared/*` and its own folders; it never reaches into another feature's internals.
`shared/ui` is the React equivalent of Angular's "zero `inject()`" dumb-component rule.

## Components and composition

- Function components only. Compose with `children` and slot props instead of large config objects.
- React 19: pass `ref` as a normal prop; `forwardRef` is unnecessary in new code. Provide context with
  `<ThemeContext value={theme}>`; read with `use(ThemeContext)` or `useContext`.
- Split context by change frequency; never put server data in context (that is the query cache's job).
- Keys come from stable ids, never the array index of a list that can reorder.
- A custom hook owns one concern, starts with `use`, and is extracted at the third use (Rule of Three).

## Hooks rules

- Call hooks unconditionally at the top level, in the same order every render. Enforced by
  `react-hooks/rules-of-hooks` (a planted conditional `useState` fails ESLint with exit 1).
- `react-hooks/exhaustive-deps` is a warning in the preset: raise it to **error** (missing deps are
  stale-closure bugs). Never silence it with `eslint-disable`; read non-reactive values in an effect
  through `useEffectEvent`.
- The `recommended-latest` preset of `eslint-plugin-react-hooks` 7 adds compiler-powered rules
  (`set-state-in-effect`, `refs`, `purity`, `immutability`, `static-components`).

## You might not need an effect

| Situation | Do this, not an effect |
|---|---|
| Value computable from props/state | compute it during render |
| Reset a subtree when an id changes | `<Editor key={id} />` |
| Respond to a click/submit | do it in the event handler |
| Fetch server data | TanStack Query (`useQuery`) |
| Remount a form each time a dialog opens | render it conditionally with a `key` (see `ProjectsPage` in `reference/server-state-and-api.md`) |

Legitimate effects: sync with a browser API (`<dialog>.showModal()`, focus after navigation),
subscribe/unsubscribe, third-party widgets. Every effect that starts async work cleans up
(`AbortController` or an `ignore` flag); otherwise the slower, stale response wins.
Details and examples: `reference/architecture-and-state.md`.

## State ownership

| Value | Home |
|---|---|
| Toggle, draft input, open/closed | `useState` / `useReducer` in the owning component |
| Filters, sort, page, tab | URL search params (shareable, back-button safe) |
| Data owned by the server | TanStack Query cache, never copied into a store |
| Cross-feature client state (few fields) | a small store (e.g. Zustand) with selectors |
| Theme, locale, current user | context, split by change rate |

One source of truth; derive the rest in render.

## Server state (TanStack Query v5)

- One key factory + `queryOptions()` per feature; the key contains every input the `queryFn` reads.
- `queryFn: ({ signal }) => api.list(signal)`: forward the signal so superseded/unmounted requests abort.
- Render four states: pending (`role="status"`), error (`role="alert"` + Retry), empty, success.
  `isPending` is the first load; `isFetching` is any fetch, so a background refetch must not blank the page.
- Mutations: `onMutate(variables, context)` → `context.client.cancelQueries` → snapshot → `setQueryData`
  → return the snapshot; `onError(error, variables, onMutateResult, context)` restores; `onSettled`
  invalidates the narrowest key. `invalidateQueries` refetches only **observed** queries.
- Defaults: `retry: 3` with backoff, so a failing query shows its error state after ~7 s
  (measured in Chromium). Tests set `retry: false`.
- Log once, centrally, via `QueryCache`/`MutationCache` `onError`; show the error in the UI.

Full code (all compiled and tested): `reference/server-state-and-api.md`.

## Typed API client

`apiRequest(path, schema, init)` fetches, throws `ApiError` on non-2xx, and `schema.parse`s the body,
so a response with the wrong shape becomes an error state, not wrong data. Client validation is UX;
the server validates again. Credentials (bearer header) are attached only when the URL's origin is
in an allow-list. Code: `reference/server-state-and-api.md`.

## Routing (React Router 8, data mode)

- Import everything from `react-router` (and `RouterProvider` from `react-router/dom`). v8 removed the
  `react-router-dom` package from the v8 line; `npm i react-router-dom@latest` installs **7.18.6**, which
  brings its own `react-router@7.18.6` beside your 8.5.2 (two routers in one bundle; verified).
- Data mode: `createBrowserRouter(routes)` + `<RouterProvider router={router} />`. Declarative mode
  (`<BrowserRouter>`) and Framework mode (Vite plugin, optional SSR) exist; this skill uses data mode.
- Lazy routes: `lazy: async () => ({ Component: (await import('...')).Page })`. Prefer the function form
  when one `routes` array is shared by several routers (tests): with the object form the router writes
  the resolved values back and empties `lazy`, so the second router built from the same array returns
  404 (verified on 8.5.2).
- Nested layouts: parent route `Component` renders `<Outlet />`.
- Auth-aware routes: route `middleware` (always on in v8) redirects to `/login?returnUrl=…`. This is UX
  only; the API authorizes every request.
- `returnUrl` is validated (`safeReturnPath`): same-origin path only; `//host`, `/\host`, absolute and
  `javascript:` values fall back.
- Error boundaries: `ErrorBoundary` on the root and on each feature route, using `useRouteError` +
  `isRouteErrorResponse`; non-route lazy widgets use `<Suspense>` inside `react-error-boundary`.

Code: `reference/routing.md`.

## Forms

React Hook Form + `zodResolver`; one zod schema per form (zod 4: `z.email()`, `z.infer`), shared with the
API layer. `noValidate`, `aria-invalid` and error text linked with `aria-describedby`, focus moves to the
first invalid field (RHF default `shouldFocusError`), submit disabled while `isSubmitting`, server
errors set with `setError('root.server', …)` and rendered in `role="alert"`, never swallowed.
Code: `reference/forms.md`.

## Security (non-negotiable)

- No `dangerouslySetInnerHTML` on user, CMS or **model** output without `DOMPurify.sanitize`; prefer
  rendering text or a safe markdown pipeline. For streamed AI/GenUI output follow the `ai-chat` skill
  (`reference/streaming-patterns.md`) and the A2UI rules in `a2ui-angular/reference/a2ui-security.md`
  (catalog allow-list, no executable payloads; the rules are framework-neutral).
- URLs from data reach `href`/`src` only through `safeHref` (http, https, mailto).
- Tokens never in `localStorage`/`sessionStorage`. Prefer an HttpOnly cookie set by a BFF; otherwise an
  in-memory access token. Attach credentials only to allow-listed API origins.
- `VITE_*` variables are compiled into the public bundle (Vite `envPrefix` default `'VITE_'`): config
  only, never secrets.
- Client guards and hidden buttons are UX; the server authorizes.

Code, attack payloads and their controls: `reference/security.md`.

## Performance

- React Compiler 1.0 (stable) via `@rolldown/plugin-babel` + `reactCompilerPreset()` from
  `@vitejs/plugin-react` 6 (the old `react({ babel: { plugins } })` option is gone). Compiled output
  contains the compiler's memo cache (`react.memo_cache_sentinel` found in the built chunks).
- No new `useMemo`/`useCallback`/`memo` without a profiler trace or an effect-dependency reason.
- Code-split by route (`lazy`); read `vite build` chunk sizes; add a visualizer when a budget is exceeded.
- Virtualize lists beyond ~100 rows (`@tanstack/react-virtual`); `useTransition` / `useDeferredValue`
  for expensive non-urgent updates.
- Profile first: React DevTools Profiler and the Chrome Performance panel.

Details: `reference/performance.md`.

## Accessibility (WCAG 2.2 AA)

Canonical checklist: `accessibility-audit` skill (`reference/wcag22-checklist.md`); automated-test
patterns in `accessibility-audit/reference/angular-a11y-automated.md` apply to React too (axe +
Playwright are framework-neutral). React specifics: semantic elements, never `div onClick`; labels
bound with `htmlFor`/`useId`; native `<dialog>` + `showModal()` for modals; move focus to `<main>` after
client-side navigation; `eslint-plugin-jsx-a11y` in lint. Automated results never prove conformance:
report "no automated violations; manual checks required".
Details and i18n basics (`Intl`, `lang`/`dir`, RTL via logical CSS): `reference/accessibility-and-i18n.md`,
canonical i18n reference `design-system/reference/i18n-rtl-intl.md`.

## Testing

| Layer | Tool |
|---|---|
| Types | `tsc -b` (Vitest does not type-check; the root tsconfig is a solution file, so plain `tsc --noEmit` checks nothing) |
| Lint | ESLint flat config: typescript-eslint, react-hooks (`recommended-latest`), jsx-a11y, TanStack Query plugin |
| Unit/component | Vitest + jsdom + Testing Library + user-event; MSW for HTTP (mock the network, not hooks) |
| E2E + a11y | Playwright (`@playwright/test`) + `@axe-core/playwright` in real Chromium at 375 and 1280 px |

Tool choice by target is canonical in `.claude/rules/testing-tool-selection.md`; Playwright workflows
live in the `browser-testing` skill. Code: `reference/testing.md`.

## Verification (run each, report its own exit code)

```bash
npx tsc -b; echo "tsc exit=$?"
npx eslint .; echo "eslint exit=$?"
npx vitest run; echo "vitest exit=$?"
npx vite build; echo "build exit=$?"
npx playwright test; echo "e2e exit=$?"
```

Do not claim a check passed unless you ran it in this session and show the command and its output;
otherwise mark it NOT RUN. Positive controls that were run for this skill: a conditional hook fails
ESLint (`react-hooks/rules-of-hooks`), an `<img>` without `alt` fails ESLint (`jsx-a11y/alt-text`), a
failing test fails Vitest, and low-contrast text fails the axe scan (`color-contrast`).

## Optional: SSR / RSC

This skill assumes a client-rendered SPA. Do not add `hydrateRoot`, Server Components or
`"use client"` boundaries to it. If the team adopts SSR (React Router Framework mode or Next.js), that is
an architecture decision (ADR via `architecture-design`) with its own data-loading, caching and
security model (server secrets, request-scoped data, hydration mismatches); this skill's routing and
env-var guidance does not transfer unchanged. **UNVERIFIED — no SSR setup was executed here.**

## Reference files

| File | Covers |
|---|---|
| `reference/architecture-and-state.md` | components, context, hooks, effects, state ownership |
| `reference/server-state-and-api.md` | API client, query keys, list states, optimistic mutation |
| `reference/routing.md` | React Router 8 data mode, lazy routes, layouts, auth middleware, returnUrl, error boundaries |
| `reference/forms.md` | React Hook Form + zod, accessible errors, server errors, dialog |
| `reference/security.md` | XSS, URLs, tokens, credentials allow-list, env vars |
| `reference/performance.md` | compiler, memo policy, splitting, virtualization, profiling |
| `reference/accessibility-and-i18n.md` | focus, dialog, forms, axe, i18n basics |
| `reference/testing.md` | Vitest/RTL/MSW setup, Playwright + axe spec |
| `reference/tooling.md` | scaffold pins, tsconfig, Vite config, ESLint flat config |
