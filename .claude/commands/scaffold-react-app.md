---
description: Scaffold a React 19 SPA with pinned versions — Vite 8, TypeScript 5.9.3, React Router 8 (data mode), TanStack Query 5, React Hook Form + zod, ESLint (react-hooks, jsx-a11y), Vitest + Testing Library + MSW, Playwright + axe, and a sample feature with loading/empty/error/success states
argument-hint: "[app name]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch
disable-model-invocation: true
---

# Scaffold React SPA

**App name:** $ARGUMENTS (default `my-app`)

Guidance is RECOMMENDED PRACTICE from the `react-spa` skill (validated in a disposable app, not a
production history). Client-rendered SPA only: no Next.js, no SSR.

## Pinned versions (verified together on 2026-11-23: `tsc -b`, `eslint .`, `vitest run`, `vite build`, `playwright test` all exit 0)

| Package | Version |
|---|---|
| `create-vite` (creator, template `react-ts`) | `9.3.4` |
| `react`, `react-dom` | `19.3.1` |
| `typescript` | `5.9.3` (the template ships `~7.0.2`, which `typescript-eslint@8.73.0` rejects: peers `<6.1.0`) |
| `vite`, `@vitejs/plugin-react` | `8.3.8`, `6.3.0` |
| `react-router` | `8.5.2` (never `react-router-dom`: its latest is 7.18.6 and installs a second router) |
| `@tanstack/react-query`, `@tanstack/eslint-plugin-query` | `5.108.3` |
| `react-hook-form`, `@hookform/resolvers`, `zod` | `7.92.0`, `7.0.8`, `4.6.7` |
| `react-error-boundary`, `dompurify` | `6.1.6`, `3.5.0` |
| `babel-plugin-react-compiler`, `@rolldown/plugin-babel`, `@babel/core` | `1.0.0`, `0.3.1`, `8.1.3` |
| `eslint`, `@eslint/js`, `typescript-eslint`, `globals` | `9.39.5`, `9.39.5`, `8.73.0`, `17.14.0` |
| `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-plugin-jsx-a11y` | `7.1.1`, `0.5.8`, `6.10.2` (peers ESLint `<=9`) |
| `vitest`, `jsdom` | `5.1.1`, `31.0.1` |
| `@testing-library/react`, `/dom`, `/user-event`, `/jest-dom` | `16.3.3`, `10.4.2`, `14.6.13`, `8.0.0` |
| `msw` | `3.0.7` |
| `@playwright/test`, `@axe-core/playwright` | `1.65.1`, `4.14.0` |
| `@types/react`, `@types/react-dom`, `@types/node` | `19.3.0`, `19.3.0`, `24.19.2` |

Node 24.x (React Router 8 needs `>=22.22.0`). Never `@latest`. To move a version, `npm view <pkg> version`,
change this table, and re-run step 10.

## Pre-requisites

Read the `react-spa` skill: `SKILL.md`, `reference/tooling.md`, `reference/server-state-and-api.md`,
`reference/routing.md`, `reference/forms.md`, `reference/security.md`, `reference/testing.md`. Every file
the steps below create has a verified source block in those references — copy it, then rename the
sample feature.

## Steps

1. **Create the project** (the `CC_SCAFFOLD=` prefix is the per-command authorization that
   `block-raw-scaffold.sh` requires):
   `CC_SCAFFOLD=scaffold-react-app npx --yes create-vite@9.3.4 <name> --template react-ts --no-interactive --no-immediate`
2. **Runtime dependencies** (exact pins):
   `npm i -E react@19.3.1 react-dom@19.3.1 react-router@8.5.2 @tanstack/react-query@5.108.3 react-hook-form@7.92.0 @hookform/resolvers@7.0.8 zod@4.6.7 react-error-boundary@6.1.6 dompurify@3.5.0`
3. **Dev dependencies**: `npm uninstall oxlint`, then
   `npm i -DE typescript@5.9.3 vite@8.3.8 @vitejs/plugin-react@6.3.0 @types/react@19.3.0 @types/react-dom@19.3.0 @types/node@24.19.2 babel-plugin-react-compiler@1.0.0 @rolldown/plugin-babel@0.3.1 @babel/core@8.1.3 eslint@9.39.5 @eslint/js@9.39.5 typescript-eslint@8.73.0 globals@17.14.0 eslint-plugin-react-hooks@7.1.1 eslint-plugin-react-refresh@0.5.8 eslint-plugin-jsx-a11y@6.10.2 @tanstack/eslint-plugin-query@5.108.3 vitest@5.1.1 jsdom@31.0.1 @testing-library/react@16.3.3 @testing-library/dom@10.4.2 @testing-library/user-event@14.6.13 @testing-library/jest-dom@8.0.0 msw@3.0.7 @playwright/test@1.65.1 @axe-core/playwright@4.14.0`
   Then pin the remaining template carets to exact versions in `package.json` and set the scripts from
   `reference/tooling.md` (`build`: `tsc -b && vite build`, `lint`, `test`, `e2e`).
4. **Config** (`reference/tooling.md`): `tsconfig.app.json` with `strict`, `noUncheckedIndexedAccess`
   and the `@/*` path; `tsconfig.e2e.json` referenced from the root solution file; `vite.config.ts` with
   the React Compiler Babel preset and the `@` alias; `vitest.config.ts`; `eslint.config.js` with
   `react-hooks/exhaustive-deps: 'error'`; `playwright.config.ts` with 375 and 1280 px projects;
   `src/vite-env.d.ts` typing only public `VITE_*` values.
5. **Folders**: `src/app/`, `src/features/`, `src/shared/{ui,lib}/`, `src/test/`, `e2e/`. Delete the
   template files the app no longer uses: `src/App.tsx`, `src/App.css`, `src/assets/`, `.oxlintrc.json`.
   Replace `src/index.css` with the base stylesheet in `reference/tooling.md` (44 px controls; the
   template CSS fails the axe `target-size` check at 375 px).
6. **App shell** (`reference/routing.md`): `main.tsx` (StrictMode + QueryClientProvider +
   RouterProvider), `app/query-client.ts` (central logging), `app/routes.tsx` (function-form `lazy` through `app/lazy-route.ts`, so a missing chunk shows the error page,
   authenticated layout with `middleware`, `ErrorBoundary`, 404), `app/AppLayout.tsx` (focus `<main>` on
   navigation), `app/RouteErrorPage.tsx` (`RouteErrorPage` at the root, `FeatureErrorPage` inside the layout), `app/session.ts`. Comment that middleware is UX and the API
   authorizes. Replace the demo sign-in with the real auth endpoint before shipping (HttpOnly cookie or
   in-memory token; never web storage).
7. **Shared lib** (`reference/server-state-and-api.md`, `reference/security.md`): `shared/lib/http.ts`
   (`apiRequest` with zod parse + credential allow-list), `logger.ts` (the only `console` call site),
   `safe-url.ts` (`safeReturnPath`, `safeHref`); `shared/ui/Dialog.tsx` (native `<dialog>`),
   `shared/ui/SafeHtml.tsx` (DOMPurify) only if HTML must render.
8. **Sample feature** `features/projects/`: `model/project.ts`, `api/projects.api.ts`,
   `api/projects.queries.ts` (keys, `queryOptions` with `signal`, optimistic create with rollback),
   `components/ProjectList.tsx` (pending/error+retry/empty/success), `components/ProjectForm.tsx`
   (RHF + zod, accessible errors, server error alert), `routes/ProjectsPage.tsx` (dialog + mutation),
   `features/auth/routes/LoginPage.tsx` (validated `returnUrl`). With no backend the list shows the
   **error state with Retry** — never fallback or mock data in app code.
9. **Tests** (`reference/testing.md`): `src/test/{setup.ts,msw-server.ts,render.tsx}` (MSW
   `onUnhandledFrame: 'error'`); unit tests for every list state, schema-mismatch → error, abort on
   unmount, optimistic rollback + success control, form validation/focus/server error, routing
   (redirect with `returnUrl`, external `returnUrl` ignored, 404), security (open redirect, `javascript:`
   URL, DOMPurify, credential allow-list, each with a control); `e2e/projects.spec.ts` with axe tags
   `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` and the planted-violation positive control.
   Install the browser once: `npx playwright install chromium`.
10. **Verify** — run each and report its own exit code; any non-zero → fix before finishing:
    ```bash
    npx tsc -b; echo "tsc exit=$?"
    npx eslint .; echo "eslint exit=$?"
    npx vitest run; echo "vitest exit=$?"
    npx vite build; echo "build exit=$?"
    npx playwright test; echo "e2e exit=$?"
    ```
11. **Summary** — created files, the five exit codes, how to run (`npm run dev`), next steps (real auth
    endpoint, API origin in `VITE_API_BASE_URL`, CSP at the host).

## Reference

- `react-spa` skill and its `reference/` files (all code blocks compiled and tested)
- `accessibility-audit` skill — WCAG 2.2 AA checklist (canonical)
- `browser-testing` skill and `.claude/rules/testing-tool-selection.md` — Playwright for web targets
