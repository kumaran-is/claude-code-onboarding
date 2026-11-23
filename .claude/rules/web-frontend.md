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

# Web frontend guardrails (Angular 21 / React)

Path-scoped: loads for web-app files only. Globs avoid `**/*.ts` and `**/src/**/*.ts` (NestJS, MCP servers, scripts); `src/app/**` needs the `app/` directory, so a NestJS `src/app.module.ts` or `src/modules/**` does not match. A NestJS repo that has its own `src/app/` folder would load this rule harmlessly. Depth: `.claude/skills/angular-spa/`, `.claude/skills/typescript-advanced-types/`, `.claude/skills/security-reviewer/`, `.claude/skills/accessibility-audit/`.

- React web (Vite SPA, React 19): load the `react-spa` skill before writing code (RECOMMENDED PRACTICE; React Router 8 imports from `react-router`, TanStack Query for server state, `tsc -b` + `vitest run` + `playwright test` as verification). React Native → `mobile-developer`.

**Security (non-negotiable)**
- Never `bypassSecurityTrust*`, `[innerHTML]`, `innerHTML =` or `dangerouslySetInnerHTML` on API, user or model output. Render it as text, or through a sanitizing markdown pipeline (DOMPurify, pinned). A line that calls DOMPurify is still flagged by `post-edit-web-security-advisory.sh` with softer wording: confirm the config and that the sanitized value is what renders, then mark it `xss-reviewed: <reason>`.
- Auth tokens never go in `localStorage` / `sessionStorage`: use an HttpOnly Secure cookie set by the server/BFF, or keep a bearer token in memory. Attach credentials only to allow-listed API origins.
- Route guards and hidden buttons are UX; the server authorizes every request. `environment.ts`, `import.meta.env.VITE_*` and `NEXT_PUBLIC_*` ship to the browser: no secrets there.
- No `eval`, `new Function` or string `setTimeout`.

**State and effects**
- Angular: signals + `computed` for state; effects only for side effects at the edge (DOM, storage, logging), never to copy state. Signal Forms and `resource`/`httpResource` are experimental in v21: do not present them as the default.
- React: derive values during render instead of syncing them in `useEffect`; effects that fetch need cleanup or cancellation (`AbortController`) so a stale response cannot overwrite a newer one.

**Typed boundaries**
- Wire DTOs are not domain models: map them in one service/module, never pass DTOs to templates or components.
- Compile-time types do not check runtime data. Parse untrusted JSON at the boundary (API responses, SSE frames, model output, URL params, storage) with a schema (Zod) into the domain type. Model UI state as a discriminated union with an exhaustive `never` check. No `any`: use `unknown` and narrow.

**Accessibility:** target WCAG 2.2 AA (`.claude/skills/accessibility-audit/`). Axe finding nothing means "no automated violations; manual checks required", never "compliant".

**Testing and gates:** web UI/E2E uses Playwright / Chrome DevTools (`.claude/rules/testing-tool-selection.md`). Angular template errors are caught only by `ng build` / `ng test`, not `tsc`. Run `/verify` (web block: type-check, lint or NOT RUN, unit, build, E2E) before claiming done.

**Versions:** pin exact versions in scaffolds (`@angular/cli@21.2.x`, `create-vite@<version>`, never `@latest`); keep TypeScript on the project's 5.9.x pin (create-vite templates may pull a newer major).
