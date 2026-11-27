---
paths:
  - "**/src/app/**/*.{ts,html,scss,css}"
  - "**/*.component.{ts,html,scss}"
  - "**/*.{tsx,jsx}"
  - "**/angular.json"
  - "**/vite.config.*"
  - "**/next.config.*"
  - "**/playwright.config.*"
  - "**/e2e/**/*.{ts,tsx}"
---

# Web frontend guardrails (Angular 22 / React)

Path-scoped: loads for web-app files only. Globs avoid `**/*.ts` and `**/src/**/*.ts` (NestJS, MCP servers, scripts); `src/app/**` needs the `app/` directory, so a NestJS `src/app.module.ts` or `src/modules/**` does not match. A NestJS repo that has its own `src/app/` folder would load this rule harmlessly. Depth: `.claude/skills/angular-spa/`, `.claude/skills/typescript-advanced-types/`, `.claude/skills/security-reviewer/`, `.claude/skills/accessibility-audit/`.

- React web (Vite SPA, React 19): load the `react-spa` skill before writing code, and the `shadcn` skill when the app has a `components.json` (RECOMMENDED PRACTICE; Tailwind CSS v4 CSS-first config, shadcn/ui on one primitive library, React Router 8 imports from `react-router`, TanStack Query for server state, `tsc -b` + `vitest run` + `playwright test` as verification). React Native → `mobile-developer`.
- **UI follows the project's `DESIGN.md`** (read only the sections the task touches; missing → say so, follow the existing theme, invent no brand values). Semantic tokens only (daisyUI/Spartan/shadcn variables, Tailwind numeric scale), one icon family behind a wrapper, motion tokens with `prefers-reduced-motion`. Shared components (`src/app/shared/components/`, `src/shared/ui/`) start with `// Tier: Atom|Molecule|Organism` and are presentational: signal `input()`/`output()` or props/callbacks, no injected services, stores, query hooks or `fetch`. Every remote-read screen records its refresh strategy; no pull-to-refresh on desktop web. Gate: `python3 .claude/scripts/check-design-system.py`. → `design-system` skill

**Security (non-negotiable)**
- Never `bypassSecurityTrust*`, `[innerHTML]`, `innerHTML =` or `dangerouslySetInnerHTML` on API, user or model output. Render it as text, or through a sanitizing markdown pipeline (DOMPurify, pinned). A line that calls DOMPurify is still flagged by `post-edit-web-security-advisory.sh` with softer wording: confirm the config and that the sanitized value is what renders, then mark it `xss-reviewed: <reason>`.
- Auth tokens never go in `localStorage` / `sessionStorage`: use an HttpOnly Secure cookie set by the server/BFF, or keep a bearer token in memory. Attach credentials only to allow-listed API origins.
- Route guards and hidden buttons are UX; the server authorizes every request. `environment.ts`, `import.meta.env.VITE_*` and `NEXT_PUBLIC_*` ship to the browser: no secrets there.
- No `eval`, `new Function` or string `setTimeout`.

**State and effects**
- Angular: signals + `computed` for state; effects only for side effects at the edge (DOM, storage, logging), never to copy state. Angular 22: Signal Forms and `resource`/`rxResource`/`httpResource` are stable; use `httpResource` for reads only, never for mutations.
- React: derive values during render instead of syncing them in `useEffect`; effects that fetch need cleanup or cancellation (`AbortController`) so a stale response cannot overwrite a newer one.

**Typed boundaries**
- Wire DTOs are not domain models: map them in one service/module, never pass DTOs to templates or components.
- Compile-time types do not check runtime data. Parse untrusted JSON at the boundary (API responses, SSE frames, model output, URL params, storage) with a schema (Zod) into the domain type. Model UI state as a discriminated union with an exhaustive `never` check. No `any`: use `unknown` and narrow.

**Accessibility:** target WCAG 2.2 AA (`.claude/skills/accessibility-audit/`). Axe finding nothing means "no automated violations; manual checks required", never "compliant".

**Angular UI mode:** every Angular workspace records one mode in `package.json` `config.uiMode` (`daisyui` default, `spartan`, `hybrid`). Before UI work run `bash .claude/scripts/angular-ui-mode.sh detect <workspace>` and use only that mode's components and ownership (`.claude/skills/angular-spa/reference/ui-mode-selection.md` §4); never add the unselected library. `post-edit-angular-ui-mode-advisory.sh` flags drift on edit.

**Angular scaffolding is CLI-first:** new workspaces come from `/scaffold-angular-app` (`ng new`); components, services, guards, interceptors, interfaces, environments and libraries come from `ng generate`, and integrations from `ng add`, run with the workspace's local CLI (`npm exec --no -- ng …`). Never hand-write `angular.json`, `main.ts`, `tsconfig*.json` or a skeleton the CLI generates; hand-write only application logic, and replace every generated placeholder (`return true` guard, empty interface) before lint. Older majors are upgraded with `ng update` plus `ng generate @angular/core:<migration>` (dry run first), never re-scaffolded over. Do not overwrite a non-empty directory.

**Testing and gates:** tool routing in `.claude/rules/testing-tool-selection.md` (Playwright CLI interactive, `@playwright/test` regression, Chrome DevTools MCP diagnostics). Angular template errors are caught only by `ng build` / `ng test`, not `tsc`. Run `/verify` (web block: type-check, lint or NOT RUN, unit, build, E2E with an executed-test count) before claiming done.

**When a UI change needs a Playwright Test spec** (`.claude/skills/browser-testing/reference/playwright-test-suite.md`; `/next` may dispatch product Playwright Test Agents per `playwright-test-agents.md` — `/verify` still runs `playwright test`): add or update one when the change alters user-visible behaviour — navigation or routing (guards, redirects, deep links, 404), a form (validation, submit, server errors), sign-in/sign-out or role-dependent UI, a critical journey (checkout, onboarding, booking), how an HTTP failure, empty or offline state is shown, or a responsive breakpoint. Each such spec asserts the visible outcome and the server's answer, and the affected state gets an axe scan. Cosmetic edits (copy, colour tokens, spacing with no breakpoint change) need no new E2E; unit/component tests cover logic. If no spec is added for a material change, say so in the change description with the reason.
- React frameworks: respect the rendering boundary. For SSR / React Router framework mode / Next.js App Router, assert the server-rendered HTML (`page.request.get(url)` body or JS disabled via `javaScriptEnabled: false`) and that hydration produces no console errors; test client-only behaviour after hydration with web-first assertions.
- Marketing sites are not exempt: cover primary navigation and every critical CTA, the contact/lead form (validation, success, server error), responsive layout at phone and desktop widths, axe on each template, no broken assets (`page.on('response')` status >= 400 for same-origin requests) and no console errors.

**Versions:** pin exact versions in scaffolds (`@angular/cli@22.3.0`, `create-vite@<version>`, never `@latest`); TypeScript follows each stack's pin: Angular 22 requires `>=6.0 <6.1` (6.0.3; TypeScript 7 is not supported); React pins 6.0.3 too, because `typescript-eslint` 8.74 peers `typescript <6.1.0` (the `react-ts` template ships `~7.0.2`: pin it down). TypeScript 7 type-checks the React reference app but cannot be linted yet.
