---
name: angular-spa
description: "Angular 21.x SPA development skill with TailwindCSS 4.x and daisyUI 5.5.5. Use when building Angular standalone components, services, lazy-loaded routes, auth (interceptor, guards), unit tests with Vitest, or creating UI with TailwindCSS + daisyUI. Covers component scaffolding, UI/UX design, accessibility, web security, and design systems."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__angular-cli__get_best_practices, mcp__angular-cli__search_documentation
metadata:
  triggers: Angular, Angular 21, standalone components, Angular SPA, TailwindCSS, daisyUI, Angular component, Angular service, lazy-loaded route, Angular testing, Angular auth, Angular interceptor
  related-skills: angular, angular-best-practices, angular-ui-patterns, accessibility-audit, browser-testing, tailwind-patterns, frontend-design, ui-standards-tokens
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**NO ANGULAR CODE WITHOUT READING `reference/angular-conventions.md` FIRST — conventions, folder structure, and daisyUI token rules are all there**

**STYLE LAW:** Follow https://angular.dev/style-guide for naming, file structure and code organization. Quick reference: `reference/angular-conventions.md`.

**ANIMATION LAW:** `@angular/animations` is deprecated since v20.2. Use `animate.enter` / `animate.leave` with CSS classes and native CSS transitions; respect `prefers-reduced-motion`. See `reference/angular-animations.md`.

# Angular 21.x SPA Development Skill

> **Tech stack**: Angular 21.2.x, TypeScript 5.9.x, TailwindCSS 4.x, daisyUI 5.5.5, Vitest (via `@angular/build:unit-test`), Playwright for E2E.

## Documentation sources

| Source | Tool | Purpose |
|---|---|---|
| Angular 21 | `angular-cli` MCP: `get_best_practices` **with `workspacePath`**; `search_documentation` with `version: 21` | Version-matched standards and API docs |
| Installed packages | `node_modules/@angular/*/types/*.d.ts` | Ground truth for signatures and `@experimental` tags |
| daisyUI 5.5.5 | `https://daisyui.com/llms.txt` | Component classes, themes |
| Tailwind / RxJS | Context7 MCP (fallback) | Utilities, operators |

`get_best_practices` without `workspacePath` returns the guide for the newest Angular major (v22),
which contradicts 21.x in places (for example the default change-detection strategy). Always pass
the folder that contains `angular.json`; it must be inside the client's project roots. If the MCP
refuses the path, say so and fall back to the `.d.ts` files — do not apply v22 guidance to a 21.x app.

## Quick scaffold — new project

Use `/scaffold-angular-app <name>` (pinned versions, Tailwind 4, daisyUI 5.5.5, angular-eslint).
Do not run `npx @angular/cli@latest` — pin the CLI to the workspace major
(`npx @angular/cli@21.2.30 new …`); the raw-scaffold hook blocks ad-hoc creator calls.

## Before writing UI code

1. Read `reference/daisyui-v5-components.md` (semantic color tokens, component classes) and
   `reference/tailwind-v4-config.md` (setup constraints).
2. Every async view handles loading, empty, error and success — `angular-ui-patterns` skill.
3. Accessibility target is **WCAG 2.2 AA**. The checklist lives in the `accessibility-audit` skill;
   Angular specifics (CDK a11y, route-change focus, LiveAnnouncer) are in `reference/angular-aria.md`.

## Process

1. **Understand requirements** — scope, endpoints, data models, states, roles (401 vs 403 UX).
2. **Feature folder** — `src/app/features/<feature>/`.
3. **Service** — typed `HttpClient` calls that let errors propagate (`reference/angular-templates.md`).
4. **Component** — signals + resource or `toSignal`, `OnPush`, load-state union (`angular-ui-patterns`).
5. **Route** — lazy `loadComponent`/`loadChildren`; guards are UX only (`reference/web-security.md`).
6. **Tests** — Vitest + TestBed + harnesses + `HttpTestingController` (`reference/testing-vitest.md`);
   E2E with Playwright (`browser-testing` skill).
7. **Style** — daisyUI components + Tailwind utilities on semantic tokens.
8. **Verify** — `ng test --watch=false`, `ng build`, `ng lint`, each with its own exit code.

## Reference files

### Core (canonical homes)
- `angular-conventions.md` — conventions, folder structure, style guide, lint
- `angular-templates.md` — service, page component, lazy routes, `app.config.ts`
- `web-security.md` — **auth**: credential allow-list interceptor, single-flight refresh, guard that waits for session restore, safe `returnUrl`, token storage, XSS rules
- `testing-vitest.md` — **unit tests**: `@angular/build:unit-test`, zoneless TestBed, harness timing, `HttpTestingController`, Vitest fake timers (no `fakeAsync`)
- `component-harnesses.md` — CDK/Material harness API
- `angular-troubleshooting.md` — common errors (NG0908, NullInjectorError, blank screen)
- `angular-best-practices.md` — pointer to the `angular-best-practices` skill (review checklist)

API reference for signals/resources/forms/SSR lives in the `angular` skill.

### UI / design system
- `tailwind-v4-config.md`, `daisyui-v5-components.md`
- `angular-forms-fields.md`, `angular-forms-validation.md` (validation modes, async validators — canonical), `angular-forms-advanced.md` — typed reactive forms (production default; Signal Forms is experimental, see `angular` skill)
- `angular-ui-tables.md` (paged list with a query signal — canonical), `angular-ui-lists.md`, `angular-ui-navigation.md`, `angular-ui-data-components.md`, `angular-ui-form-components.md`, `angular-ui-feedback-components.md`
- `angular-aria.md` — CDK a11y primitives, route-change focus, live announcements
- i18n, RTL, `Intl` formatting: `design-system/reference/i18n-rtl-intl.md` (canonical; no Angular copy)
- `accessibility-checklist.md` — pointer to `accessibility-audit` + Angular-only notes
- `smart-dumb-components.md`, `angular-animations.md`, `user-research.md`
- `e2e-cypress.md` — legacy pointer; E2E is Playwright via `browser-testing`

## Anti-patterns

- `NgModule`, `CommonModule`, `HttpClientModule`, `*ngIf`/`*ngFor` → standalone, control flow, `provideHttpClient()`.
- `@Input()`/`@Output()` in new code → `input()`, `output()`, `model()`.
- Missing `changeDetection: ChangeDetectionStrategy.OnPush` → still opt-in in 21.x; set it everywhere.
- Plain mutable fields updated from async callbacks → signals (zoneless only renders on signal/event/markForCheck).
- `effect()` that sets another signal → `computed()` / `linkedSignal()`.
- `toObservable`/`toSignal` created in a method → field initializer (else `NG0203`).
- Long-lived `subscribe()` without `takeUntilDestroyed` → leak. One-shot `HttpClient` calls complete on their own.
- `catchError(() => of([]))` or fallback/mock data on API failure → show the error state and log via `Logger`.
- Interceptor that adds `Authorization` to every URL, tokens in `localStorage`, unvalidated `returnUrl` → `reference/web-security.md`.
- `bypassSecurityTrust*` or `[innerHTML]` with unsanitized API/model output → render text, or DOMPurify first.
- `document.getElementById` / direct DOM writes → `viewChild()`, CDK, render hooks.
- Inline `style=""`, hex colours, primitive palette classes (`bg-blue-500`), arbitrary values (`p-[13px]`) → semantic daisyUI/Tailwind tokens.

## Common commands

```bash
ng serve                                   # dev server
ng test --watch=false                      # unit tests once (Vitest); exit code is the gate
ng build                                   # production build
ng lint                                    # needs angular-eslint (added by /scaffold-angular-app)
ng generate component features/orders/order-list
ng generate service features/orders/orders-api
```

## Design tokens

Full token definitions: `.claude/skills/ui-standards-tokens/reference/ui-design-tokens.md`.
daisyUI 5 semantic classes switch with `data-theme` on `<html>`; components use `bg-base-100`,
`text-base-content`, `btn-primary`, `text-error`, never raw colours. Tailwind 4 numeric spacing
utilities (`p-4`, `gap-2`) are the spacing scale and are allowed; arbitrary values are not.
Theme switching that persists a **preference** (never a credential) in `localStorage` is fine; guard
it with `isPlatformBrowser` under SSR (`reference/angular-ui-feedback-components.md`).

## Verify

```bash
ng test --watch=false; echo "test exit=$?"
ng build; echo "build exit=$?"
ng lint; echo "lint exit=$?"
```

- [ ] Each command's own exit code is 0 (not a pipe's)
- [ ] Every page shows loading, empty, error and success states (unit-tested)
- [ ] No automated axe violations in Playwright; manual keyboard/screen-reader checks done (`accessibility-audit`)
- [ ] Shared components in `shared/components/` have zero `inject()` calls (dumb rule)
- [ ] Service-injecting components live in `pages/` or `features/` (smart rule)
