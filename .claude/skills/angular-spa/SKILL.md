---
name: angular-spa
description: "Angular 22.x SPA development skill with Tailwind CSS 4.3.5 and one UI mode per workspace: daisyUI 5.8.2 (default), Spartan UI 1.10.1 or hybrid. Use when building Angular standalone components, services, lazy-loaded routes, auth (interceptor, guards), unit tests with Vitest, or creating UI with TailwindCSS + daisyUI or Spartan. Covers component scaffolding, UI/UX design, accessibility, web security, and design systems."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__angular-cli__get_best_practices, mcp__angular-cli__search_documentation
metadata:
  triggers: Angular, Angular 22, standalone components, Angular SPA, TailwindCSS, daisyUI, Spartan UI, UI mode, Angular component, Angular service, lazy-loaded route, Angular testing, Angular auth, Angular interceptor
  related-skills: angular, angular-best-practices, angular-ui-patterns, accessibility-audit, browser-testing, tailwind-patterns, frontend-design, ui-standards-tokens
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**NO ANGULAR CODE WITHOUT READING `reference/angular-conventions.md` FIRST — conventions, folder structure, and token rules are all there; UI components follow the workspace UI mode (`reference/ui-mode-selection.md`)**

**STYLE LAW:** Follow https://angular.dev/style-guide for naming, file structure and code organization. Quick reference: `reference/angular-conventions.md`.

**ANIMATION LAW:** `@angular/animations` is deprecated since v20.2. Use `animate.enter` / `animate.leave` with CSS classes and native CSS transitions; respect `prefers-reduced-motion`. See `reference/angular-animations.md`.

# Angular 22.x SPA Development Skill

> **Tech stack**: Angular 22.3.x, TypeScript 6.0.x (Angular 22 requires `>=6.0 <6.1`; TypeScript 7 is not supported), Node `^22.22.3 || ^24.15.0 || ^26.0.0` (team default: Node 26 LTS), RxJS 7.8, Tailwind CSS 4.3.5, daisyUI 5.8.2, Vitest 5 + jsdom (via `@angular/build:unit-test`), Playwright for E2E.

## Documentation sources

| Source | Tool | Purpose |
|---|---|---|
| Angular 22 | `angular-cli` MCP: `get_best_practices` **with `workspacePath`**; `search_documentation` with `version: 22` | Version-matched standards and API docs |
| Angular team skills | `angular-developer` skill (official, angular/skills 22.3.x; `angular-new-app` is reference only) | Upstream patterns for every Angular area; this skill adds the house rules on top |
| Installed packages | `node_modules/@angular/*/types/*.d.ts` | Ground truth for signatures and `@publicApi` / `@experimental` / `@deprecated` tags |
| daisyUI 5.8.2 | `https://daisyui.com/llms.txt` | Component classes, themes |
| Tailwind / RxJS | Context7 MCP (fallback) | Utilities, operators |

Where the official `angular-developer` skill and this repo differ, the repo wins: new workspaces only through
`/scaffold-angular-app` (pinned CLI 22.3.0, never `@latest`, never a global install); E2E with Playwright only
(`testing-tool-selection.md`), not the Cypress/WebdriverIO/Puppeteer options in its `e2e-testing.md`; UI per the
workspace UI mode. Everything else in it (v22 APIs, `@Service`, Signal Forms, `@boundary`, Aria) matches.

`get_best_practices` without `workspacePath` returns the CLI's bundled generic guide, which may not
match the installed major. Always pass the folder that contains `angular.json`; it must be inside the
client's project roots. If the MCP refuses the path, say so and fall back to the `.d.ts` files. An app
still on 21.x is upgraded first (`ng update @angular/core@22 @angular/cli@22`, see angular.dev/update-guide);
this skill's v22 defaults (OnPush, stable resources and Signal Forms, `@Service`) do not apply to it.

## Quick scaffold — new project

Use `/scaffold-angular-app <name> [--ui=daisyui|spartan|hybrid]` (pinned versions, Tailwind 4.3.5, angular-eslint 22.8.0;
asks once for the UI mode when no `--ui` is given, daisyUI recommended).
Do not run `npx @angular/cli@latest` — pin the CLI to the workspace major
(`@angular/cli@22.3.0`, run by the scaffold command); the raw-scaffold hook blocks ad-hoc creator calls.

## Before writing UI code

1. Find the workspace's UI mode: `bash .claude/scripts/angular-ui-mode.sh detect <workspace>` (exit 1 = fix the
   inconsistency first). Use only that mode's components and the ownership map in `reference/ui-mode-selection.md`
   §4. `daisyui`/`hybrid`: `reference/daisyui-v5-components.md` + the official `daisyui` skill; `spartan`/`hybrid`:
   the official `spartan` skill and the `spartan-ui` MCP. All modes: `reference/tailwind-v4-config.md`.
2. Every async view handles loading, empty, error and success — `angular-ui-patterns` skill.
3. Accessibility target is **WCAG 2.2 AA**. The checklist lives in the `accessibility-audit` skill;
   Angular specifics (CDK a11y, route-change focus, LiveAnnouncer) are in `reference/angular-aria.md`.

## Process

1. **Understand requirements** — scope, endpoints, data models, states, roles (401 vs 403 UX).
2. **Generate, don't hand-write, the skeleton** — `npm exec --no -- ng generate component|service|guard|interceptor|interface features/<feature>/<name>` (CLI-first rule in `.claude/rules/web-frontend.md`); then fill in the logic. Check the target paths do not exist first: generating over an existing file fails with "A merge conflicted" and exit 1. Never pass `--force`.
3. **Service** — `@Service()` singleton with typed `HttpClient` calls that let errors propagate (`reference/angular-templates.md`).
4. **Component** — signals + resource or `toSignal` (OnPush is the default), load-state union (`angular-ui-patterns`).
5. **Route** — lazy `loadComponent`/`loadChildren`; guards are UX only (`reference/web-security.md`).
6. **Tests** — Vitest + TestBed + harnesses + `HttpTestingController` (`reference/testing-vitest.md`);
   E2E with Playwright (`browser-testing` skill).
7. **Style** — the mode's components (daisyUI classes or Spartan Helm) + Tailwind utilities on semantic tokens.
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
- `ui-mode-selection.md` — UI modes (daisyui / spartan / hybrid): selection question, setup, ownership, hybrid tokens (canonical)
- `tailwind-v4-config.md`, `daisyui-v5-components.md`
- `angular-forms-fields.md`, `angular-forms-validation.md` (validation modes, async validators — canonical), `angular-forms-advanced.md` — typed reactive forms for existing reactive-form code (new forms: Signal Forms, stable in v22, see `angular` skill `references/signal-forms.md`)
- `angular-ui-tables.md` (paged list with a query signal — canonical), `angular-ui-lists.md`, `angular-ui-navigation.md`, `angular-ui-data-components.md`, `angular-ui-form-components.md`, `angular-ui-feedback-components.md`
- `angular-aria.md` — CDK a11y primitives, route-change focus, live announcements
- i18n, RTL, `Intl` formatting: `design-system/reference/i18n-rtl-intl.md` (canonical; no Angular copy)
- `accessibility-checklist.md` — pointer to `accessibility-audit` + Angular-only notes
- `smart-dumb-components.md`, `angular-animations.md`, `user-research.md`
- `e2e-cypress.md` — legacy pointer; E2E is Playwright via `browser-testing`

## Anti-patterns

- `NgModule`, `CommonModule`, `HttpClientModule`, `*ngIf`/`*ngFor` → standalone, control flow, `provideHttpClient()`.
- `@Input()`/`@Output()` in new code → `input()`, `output()`, `model()`.
- Explicit `changeDetection: ChangeDetectionStrategy.OnPush` → redundant in v22 (OnPush is the default); remove it.
- `@Injectable({ providedIn: 'root' })` on a new singleton → `@Service()` (`ng generate @angular/core:service` migrates eligible classes).
- Plain mutable fields updated from async callbacks → signals (zoneless only renders on signal/event/markForCheck).
- `effect()` that sets another signal → `computed()` / `linkedSignal()`.
- `toObservable`/`toSignal` created in a method → field initializer (else `NG0203`).
- Long-lived `subscribe()` without `takeUntilDestroyed` → leak. One-shot `HttpClient` calls complete on their own.
- `catchError(() => of([]))` or fallback/mock data on API failure → show the error state and log via `Logger`.
- Interceptor that adds `Authorization` to every URL, tokens in `localStorage`, unvalidated `returnUrl` → `reference/web-security.md`.
- `bypassSecurityTrust*` or `[innerHTML]` with unsanitized API/model output → render text, or DOMPurify first.
- `document.getElementById` / direct DOM writes → `viewChild()`, CDK, render hooks.
- Inline `style=""`, hex colours, primitive palette classes (`bg-blue-500`), arbitrary values (`p-[13px]`) → the UI mode's semantic tokens (daisyUI theme or Spartan variables) and the Tailwind scale.

## Common commands

```bash
ng serve                                   # dev server
ng test --watch=false                      # unit tests once (Vitest); exit code is the gate
ng build                                   # production build
ng lint                                    # needs angular-eslint (added by /scaffold-angular-app)
ng generate component features/orders/order-list   # local CLI: npm exec --no -- ng …
ng generate service features/orders/orders-api     # emits @Service()
ng generate guard core/auth/signed-in --implements CanActivate   # functional
ng generate interceptor core/http/auth             # functional
ng update @angular/core@22 @angular/cli@22         # existing app on an older major
ng generate @angular/core:service-migration --dry-run   # Injectable → Service
```

## Design tokens

Full token definitions: `.claude/skills/ui-standards-tokens/reference/ui-design-tokens.md`.
Semantic tokens come from the UI mode: daisyUI 5 classes (`bg-base-100`, `text-base-content`, `btn-primary`,
`text-error`) switch with `data-theme` on `<html>` (also in `hybrid`); Spartan variables (`bg-background`,
`text-foreground`, `bg-primary`) switch with the `.dark` class. Never raw colours. Tailwind 4 numeric spacing
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
