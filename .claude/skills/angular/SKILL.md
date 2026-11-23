---
name: angular
description: "Angular 21.x core patterns and APIs — Signals, signal inputs/outputs/model, RxJS interop, resource APIs (experimental), Standalone components, Zoneless change detection, render hooks, @defer, SSR/Hydration, Dependency Injection, routing, Signal Forms (experimental). Load when writing Angular code for API reference, testing patterns, or SSR configuration."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__angular-cli__get_best_practices, mcp__angular-cli__search_documentation
metadata:
  triggers: Angular signals, Angular standalone, Angular zoneless, Angular SSR, Angular hydration, Angular DI, Angular testing, Angular state management, Angular 21
  related-skills: angular-spa, angular-best-practices, angular-ui-patterns
  domain: frontend
  role: specialist
  scope: reference
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**READ `angular-spa` skill for TailwindCSS 4.x, daisyUI 5.5.5, and workspace conventions BEFORE implementing. This skill is API reference only — no design token or styling patterns here.**

## Version and verification

- Target: **Angular 21.2.x**, TypeScript 5.9.x, `strict` + `strictTemplates`. Facts below were checked
  against the installed `@angular/*@21.2.26` `.d.ts` files and a fresh `ng new` (CLI 21.2.30).
- Angular CLI MCP: call `get_best_practices` **with `workspacePath`** set to the folder holding
  `angular.json` (it must be inside the client's project roots). Without it the tool returns the
  guide for the newest major (v22), which differs from 21.x. Use `search_documentation` with
  `version: 21`.
- Experimental APIs (`resource`, `rxResource`, `httpResource`, Signal Forms) are labelled where taught.
  They are allowed, never "preferred"; pin `@angular/*` with `~21.2.x` when you use them.

## Where each topic lives (canonical homes)

| Topic | File |
|---|---|
| signal / computed / linkedSignal / effect (when NOT to use it) / toSignal / toObservable / takeUntilDestroyed / resource / rxResource / httpResource / signal queries | [references/signals-core.md](references/signals-core.md) |
| Signal Forms (EXPERIMENTAL) and the forms decision | [references/signal-forms.md](references/signal-forms.md) |
| Routing, guards, resolvers, `withComponentInputBinding`, DI, composition, state services | [references/api-reference.md](references/api-reference.md) |
| SSR, hydration, TransferState | [references/ssr-hydration.md](references/ssr-hydration.md) |
| Unit tests (Vitest, TestBed, harnesses, HttpTestingController, fake timers) | `angular-spa/reference/testing-vitest.md` |
| Auth interceptor, guards, returnUrl, token storage, XSS/CSP | `angular-spa/reference/web-security.md` |
| Load/empty/error states, typed `ApiError`, 401 vs 403 UX | `angular-ui-patterns` skill |
| Review checklist and performance priorities | `angular-best-practices` skill |
| E2E | `browser-testing` skill (Playwright) |

---

## 1. Signal inputs, outputs and model

```typescript
import { ChangeDetectionStrategy, Component, input, model, output } from '@angular/core';

@Component({
  selector: 'app-user-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3>{{ name() }}</h3>
    <span>{{ role() }}</span>
    <button type="button" class="btn btn-sm" (click)="selected.emit(id())">Select</button>
    <input type="checkbox" [checked]="pinned()" (change)="pinned.set(!pinned())" aria-label="Pin user" />
  `,
})
export class UserCard {
  readonly id = input.required<string>();
  readonly name = input.required<string>();
  readonly role = input('User');
  readonly selected = output<string>();
  readonly pinned = model(false); // two-way: <app-user-card [(pinned)]="isPinned" />
}
```

- `standalone: true` is the default since v19 — omit it. Do not import `CommonModule`; import only
  what the template uses.
- `output()` returns an `OutputEmitterRef` (no `.observed`, no `.pipe`). Use
  `outputFromObservable()` / `outputToObservable()` for RxJS interop.
- Read inputs only through the signal (`name()`); never copy them into fields in the constructor.

## 2. Signals, effects and resources (summary)

Use `computed()` for derived read-only values, `linkedSignal()` for writable state that resets when a
source changes, and `effect()` only to push state OUT to non-reactive code (storage, logging, a
third-party widget). Never set a signal from an effect. `toSignal`/`toObservable` must be created in
an injection context (field initializer/constructor); creating them in a method throws `NG0203`.
Resources are **experimental** in 21.x and take `params` (not `request`). Full rules and compiled
examples: [references/signals-core.md](references/signals-core.md).

## 3. Zoneless change detection (the 21.x default)

- `ng new` 21.2 produces an app with **no `zone.js`** dependency and **no change-detection provider**:
  zoneless is the default. `provideZonelessChangeDetection()` (stable since 20.2) is redundant in 21.x;
  `provideZoneChangeDetection()` opts back into zone.js and needs a reason.
- **`OnPush` is still opt-in in 21.x.** The component default is `ChangeDetectionStrategy.Eager`
  (`Default` is now a deprecated alias). Set `changeDetection: ChangeDetectionStrategy.OnPush` on every
  component.
- What schedules a render without zones: a signal read in a template changes, a template/host
  listener fires, `markForCheck()`, `ComponentRef.setInput()`, `AsyncPipe` emissions.
- What does **not**: assigning a plain field from a `setTimeout`/promise/subscription, and reactive
  forms `setValue`/`patchValue` called outside an event handler. Hold such state in a signal (or
  `toSignal(form.valueChanges)`).
- `NgZone.run` / `runOutsideAngular` still compile and are harmless; they no longer drive rendering.

## 4. Render hooks

```typescript
import { ChangeDetectionStrategy, Component, ElementRef, afterNextRender, viewChild } from '@angular/core';

@Component({
  selector: 'app-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<canvas #canvas aria-label="Revenue chart" role="img"></canvas>',
})
export class Chart {
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');

  constructor() {
    // Runs once after the first render, browser only (skipped during SSR).
    afterNextRender(() => {
      const ctx = this.canvas().nativeElement.getContext('2d');
      ctx?.fillRect(0, 0, 10, 10);
    });
  }
}
```

- `afterNextRender` (once) and `afterEveryRender` (every render — use sparingly) are stable since
  20.0. `afterRender` was **removed**; use `afterEveryRender`. `afterRenderEffect` re-runs when the
  signals it reads change.
- Use these instead of `ngAfterViewInit` + `setTimeout` and instead of `effect()` for DOM work.

## 5. Template syntax

```html
@let user = currentUser();

@if (user) {
  <h1>Hello, {{ user.name }}</h1>
} @else {
  <a routerLink="/login">Sign in</a>
}

@for (item of items(); track item.id) {
  <app-item [item]="item" />
} @empty {
  <p>No items yet.</p>
}

@defer (on viewport) {
  <app-heavy-chart />
} @placeholder {
  <div class="skeleton h-48 w-full"></div>
} @loading (minimum 200ms) {
  <span class="loading loading-spinner" role="status" aria-label="Loading chart"></span>
} @error {
  <p role="alert">The chart could not be loaded.</p>
}
```

- `@for` requires `track`; track a stable id, not `$index`, for lists that reorder.
- `@defer` only splits the bundle when the deferred component is standalone and not referenced
  elsewhere in the same file. `@placeholder`/`@loading` need explicit dimensions to avoid layout shift.
- `@let` is a template alias; it does not replace `computed()` for derived state.
- `NgOptimizedImage`: `<img ngSrc="hero.jpg" width="800" height="600" priority />` for the LCP image;
  `placeholder` accepts `true` (with a loader) or a data URL.

## 6. Bootstrapping and routing

```typescript
// app.config.ts — what a 21.2 app needs (no zone provider)
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()), // route params → input()
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
  ],
};
```

- Lazy routes: `loadComponent: () => import('./x').then((m) => m.X)` and `loadChildren` for route arrays.
- Guards, resolvers and interceptors are functions (`CanActivateFn`, `ResolveFn<T>`,
  `HttpInterceptorFn`) that call `inject()` synchronously **before** any `await`. Examples:
  [references/api-reference.md](references/api-reference.md); auth versions:
  `angular-spa/reference/web-security.md`.
- Client guards are UX only; the server authorizes every request.

## 7. Forms

**Typed reactive forms are the production default on 21.x** (`NonNullableFormBuilder`,
`FormGroup<T>`, `getRawValue()`). Signal Forms (`@angular/forms/signals`: `form`, `FormField`,
`submit`, `validate`) is **EXPERIMENTAL** — see [references/signal-forms.md](references/signal-forms.md)
for the decision table and a compiled example. UI patterns for fields/validation:
`angular-spa/reference/angular-forms-*.md`.

## 8. SSR and hydration

See [references/ssr-hydration.md](references/ssr-hydration.md) (incremental hydration, TransferState,
`withFetch()`, browser-only code in render hooks).

## 9. Testing

`ng new` 21.2 configures `@angular/build:unit-test` with **Vitest + jsdom** — there is no
`vitest.config.ts`, no Karma and no zone.js. TestBed runs zoneless when zone.js is absent; adding
`provideZonelessChangeDetection()` to TestBed is optional. `fakeAsync`/`tick` need zone.js and fail
under this runner — use `vi.useFakeTimers()` + `await vi.advanceTimersByTimeAsync()` or
`await fixture.whenStable()`. Full patterns: `angular-spa/reference/testing-vitest.md`.

## Common troubleshooting

| Issue | Fix |
|---|---|
| View does not update after an async callback | The value is a plain field. Make it a signal (zoneless renders on signal change) |
| `NG0203: toObservable() can only be used within an injection context` | Move the call to a field initializer/constructor, or pass `{ injector }` |
| `resource({ request })` does not compile | 21.x uses `params`; `rxResource` uses `stream` |
| `value()` throws in template | The resource is in `error`; branch on `error()` → `hasValue()` → `value()` |
| `zone-testing.js is needed for the fakeAsync() test helper` | Replace with Vitest fake timers / `whenStable()` |
| SSR fetch runs twice | `withFetch()` + HTTP transfer cache (default with hydration); see ssr-hydration.md |

## Related Skills

- `angular-spa` — workspace conventions, TailwindCSS 4.x, daisyUI 5.5.5, testing, security
- `angular-best-practices` — impact-prioritized review checklist
- `angular-ui-patterns` — loading, error, empty state patterns
- `accessibility-audit` — WCAG 2.2 AA checklist (canonical)
