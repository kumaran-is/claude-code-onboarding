---
paths:
  - "**/src/app/**/*.{ts,html,scss,css}"
  - "**/*.component.{ts,html,scss}"
  - "**/*.{tsx,jsx}"
  - "**/angular.json"
  - "**/vite.config.*"
  - "**/next.config.*"
  - "**/playwright.config.*"
---

# Web frontend guardrails (Angular 22 / React)

Path-scoped: loads for web-app files only. Globs avoid `**/*.ts` and `**/src/**/*.ts` (NestJS, MCP servers, scripts); `src/app/**` needs the `app/` directory, so a NestJS `src/app.module.ts` or `src/modules/**` does not match. A NestJS repo that has its own `src/app/` folder would load this rule harmlessly. Depth: `.claude/skills/angular-spa/`, `.claude/skills/typescript-advanced-types/`, `.claude/skills/security-reviewer/`, `.claude/skills/accessibility-audit/`.

- React web (Vite SPA, React 19): load the `react-spa` skill before writing code (RECOMMENDED PRACTICE; React Router 8 imports from `react-router`, TanStack Query for server state, `tsc -b` + `vitest run` + `playwright test` as verification). React Native → `mobile-developer`.

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

**Angular scaffolding is CLI-first:** new workspaces come from `/scaffold-angular-app` (`ng new`); components, services, guards, interceptors, interfaces, environments and libraries come from `ng generate`, and integrations from `ng add`, run with the workspace's local CLI (`npm exec --no -- ng …`). Never hand-write `angular.json`, `main.ts`, `tsconfig*.json` or a skeleton the CLI generates; hand-write only application logic, and replace every generated placeholder (`return true` guard, empty interface) before lint. Older majors are upgraded with `ng update` plus `ng generate @angular/core:<migration>` (dry run first), never re-scaffolded over. Do not overwrite a non-empty directory.

**Testing and gates:** web UI/E2E uses Playwright / Chrome DevTools (`.claude/rules/testing-tool-selection.md`). Angular template errors are caught only by `ng build` / `ng test`, not `tsc`. Run `/verify` (web block: type-check, lint or NOT RUN, unit, build, E2E) before claiming done.

**Versions:** pin exact versions in scaffolds (`@angular/cli@22.3.0`, `create-vite@<version>`, never `@latest`); TypeScript follows each stack's pin: Angular 22 requires `>=6.0 <6.1` (6.0.3; TypeScript 7 is not supported); React keeps its own 5.9.x pin (create-vite templates may pull a newer major).
