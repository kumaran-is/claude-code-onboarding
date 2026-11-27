---
description: Scaffold a React 19 SPA with pinned versions — Vite 8, TypeScript 6.0.3, Tailwind CSS 4.3 + shadcn/ui (Base UI, light/dark theme), React Router 8 (data mode), TanStack Query 5, React Hook Form + zod, ESLint (react-hooks, jsx-a11y), Vitest + Testing Library + MSW, Playwright + axe, and a sample feature with loading/empty/error/success states
argument-hint: "[app name]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch
disable-model-invocation: true
---

# Scaffold React SPA

**App name:** $ARGUMENTS (default `my-app`)

Guidance is RECOMMENDED PRACTICE from the `react-spa` skill (validated in a disposable app, not a
production history). This command scaffolds a client-rendered SPA. When the requirements need SSR, streaming,
React Server Components or per-route SEO, use a full-stack framework instead (see "Choosing SPA vs full-stack" below).

## Pinned versions (2026-11-23; Tailwind/shadcn rows 2026-11-24)

Toolchain rows (TypeScript, Vite, React Compiler, ESLint, Vitest, Testing Library, MSW, Playwright, axe) were
verified together on Node 26.13.1 in a disposable app: `tsc -b`, `eslint .`, `vitest run`, `vite build` and
`playwright test` all exit 0, and a planted failure makes each one exit non-zero. The whole table, including
the Tailwind CSS v4 + shadcn/ui rows, was re-verified 2026-11-24 in a fresh app built with these steps (59 unit,
54 E2E tests, light and dark axe scans; `react-spa/reference/tailwind-shadcn.md`). Library rows (router, query,
forms) come from the `react-spa` reference-app validation.

| Package | Version |
|---|---|
| `create-vite` (creator, template `react-ts`) | `9.3.4` |
| `react`, `react-dom` | `19.3.1` |
| `typescript` | `6.0.3`: the newest version every tool accepts. The template ships `~7.0.2`, which `typescript-eslint@8.74.0` rejects (peer `>=4.8.4 <6.1.0`, also stated at typescript-eslint.io/users/dependency-versions) |
| `vite`, `@vitejs/plugin-react` | `8.3.8`, `6.3.0` |
| `tailwindcss`, `@tailwindcss/vite`, `tw-animate-css` | `4.3.5`, `4.3.5`, `1.4.0` |
| `shadcn` (CLI), `@base-ui/react`, `cn`, `class-variance-authority`, `lucide-react`, `@fontsource-variable/geist` | `4.23.0`, `1.9.0`, `0.5.2`, `0.7.1`, `1.79.0`, `5.3.0` |
| `@tanstack/react-table` | `9.3.1` (v9 API) |
| `react-router` | `8.5.2` (never `react-router-dom`: its latest is 7.18.6 and installs a second router) |
| `@tanstack/react-query`, `@tanstack/eslint-plugin-query` | `5.108.4` |
| `react-hook-form`, `@hookform/resolvers`, `zod` | `7.92.0`, `7.0.8`, `4.6.7` |
| `react-error-boundary`, `dompurify` | `6.1.6`, `3.5.0` |
| `babel-plugin-react-compiler`, `@rolldown/plugin-babel`, `@babel/core` | `1.0.0`, `0.3.1`, `8.1.3` |
| `eslint`, `@eslint/js`, `typescript-eslint`, `globals` | `10.15.0`, `10.0.1`, `8.74.0`, `17.14.0` |
| `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-plugin-jsx-a11y-x` | `7.1.1`, `0.5.8`, `0.2.0` (ESLint 10-compatible fork of `eslint-plugin-jsx-a11y`; `overrides` pins its `minimatch` to `11.0.9`) |
| `vitest`, `jsdom` | `5.1.1`, `31.0.1` |
| `@testing-library/react`, `/dom`, `/user-event`, `/jest-dom` | `16.3.3`, `10.4.2`, `14.6.13`, `8.0.0` |
| `msw` | `3.0.7` |
| `@playwright/test`, `@axe-core/playwright` | `1.65.1`, `4.14.1` |
| `@types/react`, `@types/react-dom`, `@types/node` | `19.3.0`, `19.3.0`, `26.6.6` (match the Node major you run) |

Node 26.13.1 (Active LTS); the stack's floor is `^22.22.0 || ^24.15.0 || >=26.0.0` (React Router 8 `>=22.22.0`, jsdom 31
`^22.22.2 || ^24.15.0 || >=26.0.0`). Never `@latest`. To move a version, `npm view <pkg> version`,
change this table, and re-run step 10.

## Pre-requisites

Read the `react-spa` skill: `SKILL.md`, `reference/tooling.md`, `reference/tailwind-shadcn.md`,
`reference/server-state-and-api.md`, `reference/routing.md`, `reference/forms.md`, `reference/security.md`,
`reference/testing.md`; and the `shadcn` skill (`SKILL.md`, `rules/`). Every file
the steps below create has a verified source block in those references — copy it, then rename the
sample feature.

## Steps

1. **Create the project** (the `CC_SCAFFOLD=` prefix is the per-command authorization that
   `block-raw-scaffold.sh` requires):
   `CC_SCAFFOLD=scaffold-react-app npx --yes create-vite@9.3.4 <name> --template react-ts --no-interactive --no-immediate`
2. **Runtime dependencies** (exact pins):
   `npm i -E react@19.3.1 react-dom@19.3.1 react-router@8.5.2 @tanstack/react-query@5.108.4 @tanstack/react-table@9.3.1 react-hook-form@7.92.0 @hookform/resolvers@7.0.8 zod@4.6.7 react-error-boundary@6.1.6 dompurify@3.5.0`
3. **Dev dependencies**: `npm uninstall oxlint`, then
   `npm i -DE typescript@6.0.3 vite@8.3.8 @vitejs/plugin-react@6.3.0 @types/react@19.3.0 @types/react-dom@19.3.0 @types/node@26.6.6 babel-plugin-react-compiler@1.0.0 @rolldown/plugin-babel@0.3.1 @babel/core@8.1.3 tailwindcss@4.3.5 @tailwindcss/vite@4.3.5 eslint@10.15.0 @eslint/js@10.0.1 typescript-eslint@8.74.0 globals@17.14.0 eslint-plugin-react-hooks@7.1.1 eslint-plugin-react-refresh@0.5.8 eslint-plugin-jsx-a11y-x@0.2.0 @tanstack/eslint-plugin-query@5.108.4 vitest@5.1.1 jsdom@31.0.1 @testing-library/react@16.3.3 @testing-library/dom@10.4.2 @testing-library/user-event@14.6.13 @testing-library/jest-dom@8.0.0 msw@3.0.7 @playwright/test@1.65.1 @axe-core/playwright@4.14.1`
   Add the `overrides` block from `reference/tooling.md` (patched `minimatch` for the a11y plugin and the shadcn CLI), run
   `npm install`, then pin the remaining template carets to exact versions in `package.json` and set the scripts from
   `reference/tooling.md` (`build`: `tsc -b && vite build`, `lint`, `test`, `e2e`).
4. **Config** (`reference/tooling.md`): `tsconfig.app.json` with `strict`, `noUncheckedIndexedAccess`
   and the `@/*` path, and the same `paths` in the root `tsconfig.json` (the shadcn CLI reads the root file; no
   `baseUrl`); `tsconfig.e2e.json` referenced from the root solution file; `vite.config.ts` with
   `tailwindcss()`, the React Compiler Babel preset and the `@` alias; `vitest.config.ts`; `eslint.config.js` with
   `react-hooks/exhaustive-deps: 'error'` and the `src/components/ui/**` override; `playwright.config.ts` with 375 and 1280 px projects;
   `src/vite-env.d.ts` typing only public `VITE_*` values.
4b. **shadcn/ui on Base UI** (`reference/tailwind-shadcn.md`; the CLI is pinned, stdin closed because `init`
   otherwise waits for a preset prompt). First replace the template's `src/index.css` with the single line
   `@import "tailwindcss";`: `init` looks for it and exits 1 ("No Tailwind CSS configuration found") on the
   template stylesheet. Then
   `npx shadcn@4.23.0 init --base base -p nova --yes --no-monorepo </dev/null` and
   `npx shadcn@4.23.0 add button card input label field dialog dropdown-menu table skeleton toast empty alert spinner toggle-group </dev/null`.
   The CLI writes caret ranges; re-pin exactly with
   `npm i -E @base-ui/react@1.9.0 cn@0.5.2 class-variance-authority@0.7.1 lucide-react@1.79.0 @fontsource-variable/geist@5.3.0`
   and `npm i -DE shadcn@4.23.0 tw-animate-css@1.4.0` (this also moves both to `devDependencies`; check that
   `tailwindcss` and `@tailwindcss/vite` are in `devDependencies` too). Replace `src/index.css` with the merged file in `reference/tooling.md`
   (shadcn tokens + 44 px controls, focus outline, reduced motion). Add `src/shared/ui/theme-context.ts`,
   `theme-provider.tsx`, `icons.ts` and `mode-toggle.tsx` (every shared component block starts with its `// Tier:` line; providers/contexts carry none).
   Write `DESIGN.md` at the project root from `design-system/reference/design-md-governance.md` §5, filled from the
   `:root`/`.dark` variables in `src/index.css` and marked `status: toolkit-default`; invent no brand values. Never add Radix packages next to Base UI.
5. **Folders**: `src/app/`, `src/features/`, `src/shared/{ui,lib}/`, `src/components/ui/` (CLI-owned),
   `src/test/`, `e2e/`, `build-tests/`. Delete the template files the app no longer uses: `src/App.tsx`,
   `src/App.css`, `src/assets/`, `.oxlintrc.json`.
6. **App shell** (`reference/routing.md`): `main.tsx` (StrictMode + ThemeProvider + QueryClientProvider +
   RouterProvider + Toaster), `app/query-client.ts` (central logging), `app/routes.tsx` (function-form `lazy` through `app/lazy-route.ts`, so a missing chunk shows the error page,
   authenticated layout with `middleware`, `ErrorBoundary`, 404), `app/AppLayout.tsx` (focus `<main>` on
   navigation, responsive header with the mode toggle and a container query), `app/RouteErrorPage.tsx` (`RouteErrorPage` at the root, `FeatureErrorPage` inside the layout), `app/session.ts`. Comment that middleware is UX and the API
   authorizes. Replace the demo sign-in with the real auth endpoint before shipping (HttpOnly cookie or
   in-memory token; never web storage).
7. **Shared lib** (`reference/server-state-and-api.md`, `reference/security.md`): `shared/lib/http.ts`
   (`apiRequest` with zod parse + credential allow-list), `logger.ts` (the only `console` call site),
   `safe-url.ts` (`safeReturnPath`, `safeHref`); `shared/ui/SafeHtml.tsx` (DOMPurify) only if HTML must render.
   Dialogs, menus, tables and toasts are the shadcn components from step 4b.
8. **Sample feature** `features/projects/`: `model/project.ts`, `api/projects.api.ts`,
   `api/projects.queries.ts` (keys, `queryOptions` with `signal`, optimistic create with rollback),
   `components/ProjectList.tsx` (Skeleton pending, Alert error + Retry, Empty, sortable TanStack Table v9),
   `components/ProjectForm.tsx` (RHF `Controller` + zod in `FieldGroup`/`Field`, hand-wired `aria-describedby`,
   server error `Alert`, `Spinner` while submitting), `routes/ProjectsPage.tsx` (shadcn Dialog + mutation +
   toast),
   `features/auth/routes/LoginPage.tsx` (validated `returnUrl`). With no backend the list shows the
   **error state with Retry** — never fallback or mock data in app code.
9. **Tests** (`reference/testing.md`): `src/test/{setup.ts,msw-server.ts,render.tsx}` (MSW
   `onUnhandledFrame: 'error'`); unit tests for every list state, schema-mismatch → error, abort on
   unmount, optimistic rollback + success control, form validation/focus/server error, routing
   (redirect with `returnUrl`, external `returnUrl` ignored, 404), security (open redirect, `javascript:`
   URL, DOMPurify, credential allow-list, each with a control), theme toggle (class + persistence), dialog
   focus and Escape, menu keyboard, table sort, toast after create; `build-tests/tailwind-build.test.ts`
   (Tailwind and React Compiler output present in `dist/`); `e2e/fixtures.ts` (fails a test on console
   errors, page errors, failed requests and 5xx), `e2e/support.ts`, `e2e/projects.spec.ts`,
   `e2e/themes-a11y.spec.ts` (axe light and dark, dialog and menu open), `e2e/dialog-menu.spec.ts` (Tab
   trap, Escape, focus return), `e2e/responsive-security.spec.ts` (no overflow at 375 px, open-redirect
   negatives); axe tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` and the planted-violation control.
   Install the browser once: `npx playwright install chromium`.
   Optional in the **product** app (never this toolkit): backup `.mcp.json` if it exists, `npx playwright init-agents --loop=claude` (that command **replaces** `.mcp.json` with only `playwright-test`), then merge other servers back — `browser-testing/reference/playwright-test-agents.md` "Scaffold hint" and `browser-testing/scripts/merge-playwright-test-mcp.py`.
10. **Verify** — run each and report its own exit code; any non-zero → fix before finishing:
    ```bash
    npx tsc -b; echo "tsc exit=$?"
    npx eslint .; echo "eslint exit=$?"
    npx vitest run; echo "vitest exit=$?"
    npx vite build; echo "build exit=$?"
    npx playwright test; echo "e2e exit=$?"
    python3 <claude project root>/.claude/scripts/check-design-system.py --root .; echo "design gate exit=$?"
    ```
    Shared components in `src/shared/ui/` start with `// Tier: Atom|Molecule|Organism` and stay presentational
    (props in, callbacks out; no query hooks, stores or `fetch`): `design-system/reference/atomic-decision-tree.md`.
11. **Summary** — created files, the six exit codes (plus `npm audit --audit-level=high`), how to run (`npm run dev`), next steps (real auth
    endpoint, API origin in `VITE_API_BASE_URL`, CSP at the host).

## Choosing SPA vs full-stack

Decide from the requirements, not habit. react.dev recommends starting new apps with a framework; this
command covers the SPA case. Create React App is deprecated for new apps (react.dev blog, 2025-02-14): never use it.

| Requirement | Vite SPA (this command) | Next.js App Router | React Router framework mode |
|---|---|---|---|
| Rendering | CSR only | SSR, SSG, streaming, React Server Components, static export | SSR, SSG/pre-render, SPA mode, streaming |
| SEO for public pages | weak (client-rendered) | strong | strong |
| Data on the server, secrets kept off the client | no: needs a separate API | Server Components, Route Handlers, Server Actions | loaders and actions |
| Deploy target | any static host / CDN | Node server, Docker, or static export | Node or edge adapters, or static (SPA mode) |
| Pick when | authenticated app behind a login, API owned by another service | public content, RSC, per-route rendering choices | you want Vite + React Router APIs end to end with server rendering |

Full-stack creators are pinned and run without prompts (flags verified with `--help` on 2026-11-23):

- **Next.js 16.4.6**:
  `CC_SCAFFOLD=scaffold-react-app npm exec --yes -- create-next-app@16.4.6 <name> --ts --app --eslint --no-tailwind --react-compiler --src-dir --import-alias "@/*" --use-npm --disable-git --no-agent-feedback --yes`
  (add `--tailwind` only when the design system uses Tailwind). With `--yes` the generated `next.config.ts`
  enables `reactCompiler`, `cacheComponents` and `partialPrefetching`. The template pins `react@19.3.0`,
  `typescript ^5`, `eslint ^9` and `@types/node ^20`: move them to the table's pins (`react@19.3.1`,
  `typescript@6.0.3`, `@types/node@26.6.6`). Validated in a disposable app: `tsc --noEmit`, `eslint`,
  `next build` and Playwright (streaming order, client island hydration, server code not shipped, `error.tsx`
  with `retry`, axe) all exit 0; importing a `server-only` module into a Client Component and reading
  request data outside `<Suspense>` both fail `next build`. ESLint: `eslint-config-next@16.4.6` depends on
  `eslint-plugin-react@7.37.5`, `eslint-plugin-import@2.32.0` and `eslint-plugin-jsx-a11y@6.10.2`, whose
  peers stop at ESLint 9 (and ESLint 9.39.5 is npm-deprecated). ESLint 10.15.0 installs with
  `ERESOLVE overriding peer dependency` warnings. In the validation app, lint still exited 0 and planted
  violations still failed it (`rules-of-hooks`, `refs`, `alt-text`, `@next/next/no-img-element`). Record that
  choice in the PR.
- **React Router framework mode 8.5.2**:
  `CC_SCAFFOLD=scaffold-react-app npm exec --yes -- create-react-router@8.5.2 <name> --yes --no-git-init --no-agent-skills --package-manager npm`
  (flags from `--help`; the default template was not generated in this validation: run the five checks
  above before relying on it).

Full-stack testing uses the same tools: Vitest + Testing Library for components, and Playwright against
the production server (`next build && next start`, or `react-router build` + its server). An async Server
Component cannot be rendered by Testing Library: cover it in Playwright.

## Reference

- `react-spa` skill and its `reference/` files (all code blocks compiled and tested)
- `shadcn` skill (official, vendored and pinned) — component rules, CLI, registries, theming
- `accessibility-audit` skill — WCAG 2.2 AA checklist (canonical)
- `browser-testing` skill and `.claude/rules/testing-tool-selection.md` — Playwright for web targets
