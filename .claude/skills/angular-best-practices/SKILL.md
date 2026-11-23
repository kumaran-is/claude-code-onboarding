---
name: angular-best-practices
description: "Impact-prioritized Angular 22.x review checklist — CRITICAL: Signals on the zoneless + OnPush defaults, async waterfalls, bundle optimization. HIGH: rendering performance, SSR hydration. MEDIUM: template optimization, state management. LOW: memory management. Load when reviewing Angular code, writing components, or optimizing performance."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__angular-cli__get_best_practices, mcp__angular-cli__search_documentation
metadata:
  triggers: Angular performance, Angular optimization, Angular OnPush, Angular bundle, Angular lazy loading, Angular SSR, Angular memory leak, Angular track, Angular virtual scroll, Angular review
  related-skills: angular-spa, angular, angular-ui-patterns
  domain: frontend
  role: specialist
  scope: review
  output-format: checklist
last-reviewed: "2026-11-22"
---

## Iron Law

**LOAD `angular-spa` FIRST for Tailwind CSS 4.3.5 + daisyUI workspace conventions. This skill is the ranked review checklist — not the API reference (`angular`) and not implementation templates (`angular-spa`).**

## Documentation Sources

Verify every Angular API against the `angular-cli` MCP before citing it in a review:
- `search_documentation` with `version: 22` — check the page's experimental / developer-preview banner.
- `get_best_practices` **with `workspacePath`** (an `angular.json` folder inside the client's project).
  Without it the tool returns the bundled generic guide, which may not match the installed major.

Context7 is a fallback for non-Angular libraries.

**Version facts for 22.3** (checked against `@angular/*@22.3.0` `.d.ts` and `get_best_practices` for v22):
zoneless is the default; **OnPush is the default** (`ChangeDetectionStrategy` docs: "OnPush is enabled by default") —
do not write `changeDetection: ChangeDetectionStrategy.OnPush`; `resource` / `rxResource` / `httpResource` and
Signal Forms are stable (`@publicApi 22.0`); `standalone: true` is the default and must not be written;
new singleton services use `@Service()` instead of `@Injectable({ providedIn: 'root' })`.

---

## When to Apply

- Reviewing a PR that touches Angular components, routes, services or templates
- Writing new components or data fetching
- Optimizing bundle size or load times
- Configuring SSR / hydration (details: `angular/references/ssr-hydration.md`)

---

## Priority Matrix

| Priority | Category              | Impact     | Focus                                   |
| -------- | --------------------- | ---------- | --------------------------------------- |
| 1        | Change Detection      | CRITICAL   | Signals, OnPush, zoneless default       |
| 2        | Async Waterfalls      | CRITICAL   | Resources, flattening, SSR preloading   |
| 3        | Bundle Optimization   | CRITICAL   | Lazy loading, tree shaking              |
| 4        | Rendering Performance | HIGH       | @defer, track, virtualization           |
| 5        | Server-Side Rendering | HIGH       | Hydration, prerendering                 |
| 6        | Template Optimization | MEDIUM     | Control flow, pipes                     |
| 7        | State Management      | MEDIUM     | Signal services, scoped stores          |
| 8        | Memory Management     | LOW-MEDIUM | Cleanup, subscriptions                  |

---

## 1. Change Detection (CRITICAL)

### Rely on the OnPush Default

```typescript
// ✅ CORRECT - signals on the v22 OnPush default (no changeDetection property)
@Component({
  template: `<div>{{ count() }}</div>`,
})
export class Counter {
  readonly count = signal(0);
}

// ❌ WRONG - Default change detection, mutable field
@Component({
  template: `<div>{{ count }}</div>`,
})
export class Counter {
  count = 0;
}
```

### Prefer Signals Over Mutable Properties

Template state lives in `signal()` / `computed()` / `input()`. Under zoneless change detection a plain
field mutated from a timer or a promise never re-renders.

### Zoneless Is the Default — Do Not Add Providers

Angular 22 apps are zoneless by default: no `zone.js` polyfill, no change-detection provider in
`app.config.ts`. Review findings:

- `provideZoneChangeDetection(...)` present → the app opted back into zone.js; flag unless justified.
- `provideZonelessChangeDetection()` in a 22.x app → redundant (it was the v20 opt-in); remove.
- `changeDetection: ChangeDetectionStrategy.OnPush` → redundant in v22 (the default); remove. A component that
  explicitly sets `ChangeDetectionStrategy.Eager` needs a recorded reason.
- `NgZone.onStable` / `onMicrotaskEmpty` / `isStable` → never fire / always true under zoneless; replace
  with `afterNextRender` / `afterEveryRender`. `NgZone.run` / `runOutsideAngular` remain compatible.
- Reactive-forms `setValue` / `patchValue` from code do not schedule change detection; the template must
  read a signal (or call `markForCheck`).

Details: `angular/SKILL.md` (Zoneless section).

---

## 2. Async Operations & Waterfalls (CRITICAL)

### Eliminate Nested Subscriptions

```typescript
// ❌ WRONG - Nested subscriptions: waterfall, leaks, no cancellation
this.route.params.subscribe((params) => {
  this.userService.getUser(params['id']).subscribe((user) => {
    this.postsService.getPosts(user.id).subscribe((posts) => { /* … */ });
  });
});

// ✅ CORRECT - Route param as input() + a resource: latest id wins, stale requests cancelled,
// no manual subscribe. rxResource is stable in v22 (@publicApi 22.0).
export class PostsPage {
  private readonly http = inject(HttpClient);
  readonly id = input.required<string>(); // provideRouter(routes, withComponentInputBinding())
  readonly posts = rxResource({
    params: () => this.id(),
    stream: ({ params }) =>
      this.http.get<Post[]>(`/api/users/${encodeURIComponent(params)}/posts`),
  });
}

// ✅ CORRECT - Independent reads in parallel
forkJoin({ user: this.users.get(id), posts: this.posts.list(id) });
```

A stream that must stay imperative (websocket, polling) is subscribed in an injection context with
`takeUntilDestroyed()`. One-shot mutations use `firstValueFrom(...)` and complete on their own.

### Avoid Client-Side Waterfalls in SSR

```typescript
// ✅ CORRECT - Resolver runs before activation (on the server during SSR); lazy component
export const routes: Routes = [
  {
    path: 'profile/:id',
    resolve: { profile: profileResolver },
    loadComponent: () => import('./profile/profile-page').then((m) => m.ProfilePage),
  },
];
// ProfilePage: readonly profile = input.required<Profile>(); // bound by withComponentInputBinding()

// ❌ WRONG - Component starts fetching only after its JS loads and renders
class ProfilePage implements OnInit {
  ngOnInit() {
    this.http.get('/api/profile').subscribe();
  }
}
```

---

## 3. Bundle Optimization (CRITICAL)

### Lazy Load Routes

```typescript
// ✅ CORRECT - Lazy load every route-level component
export const routes: Routes = [
  { path: 'admin', loadChildren: () => import('./admin/admin.routes').then((m) => m.ADMIN_ROUTES) },
  { path: 'dashboard', loadComponent: () => import('./dashboard/dashboard').then((m) => m.Dashboard) },
];

// ❌ WRONG - Eagerly imported route component lands in the main bundle
import { AdminPage } from './admin/admin-page';
export const routes: Routes = [{ path: 'admin', component: AdminPage }];
```

### Use @defer for Heavy Components

```html
<!-- ✅ CORRECT - Heavy component loads on demand -->
@defer (on viewport) {
  <app-analytics-chart [data]="data()" />
} @placeholder {
  <div class="skeleton h-64 w-full"></div>
}

<!-- ❌ WRONG - Heavy component in the initial bundle -->
<app-analytics-chart [data]="data()" />
```

### Barrels: Library Public API Yes, Intra-App Barrels No

```typescript
// ✅ CORRECT - A shared library exposes ONE public API file (index.ts / public-api.ts) and is
// imported by package name; its package.json declares "sideEffects": false.
import { Button, Modal } from '@acme/shared-ui';

// ✅ CORRECT - Inside an app, import the file directly
import { OrderTable } from './orders/order-table';

// ❌ WRONG - Intra-app "index.ts re-export everything" barrels: cycles, slower builds, accidental eager imports
import { OrderTable, OrderForm, OrderChart } from './orders';
```

Whether a given barrel defeats tree-shaking depends on side effects in the re-exported modules —
UNVERIFIED for any specific library; measure with `ng build --stats-json` before claiming bundle savings.

### Dynamic Import Third-Party Libraries

```typescript
// ✅ CORRECT - Load a heavy library on demand
async loadChart(): Promise<void> {
  const { Chart } = await import('chart.js');
  this.chart = new Chart(this.canvas().nativeElement, config);
}

// ❌ WRONG - Static import puts it in the main chunk
import { Chart } from 'chart.js';
```

---

## 4. Rendering Performance (HIGH)

### Track by a Stable Identity in @for

```html
<!-- ✅ CORRECT - Efficient DOM updates -->
@for (item of items(); track item.id) {
  <app-item-card [item]="item" />
}

<!-- ❌ WRONG - $index on a list that reorders/filters re-creates DOM -->
@for (item of items(); track $index) {
  <app-item-card [item]="item" />
}
```

### Use Virtual Scrolling for Large Lists

Use `CdkVirtualScrollViewport` with `itemSize` for lists >50 items. See [references/extended-patterns.md](references/extended-patterns.md).

### Prefer Pure Pipes and computed() Over Template Methods

Template method calls run on every check of the view; a pure pipe or `computed()` is memoized. See [references/extended-patterns.md](references/extended-patterns.md).

---

## 5. Server-Side Rendering (HIGH)

Canonical guide: `angular/references/ssr-hydration.md`. Review points:

- Hydration on: `provideClientHydration(...)` in `app.config.ts`.
- Incremental hydration (`withIncrementalHydration()`, stable) **enables event replay itself** —
  `withEventReplay()` next to it is redundant.
- Hydrate triggers are `hydrate on …`, `hydrate when …`, `hydrate never`; each `@defer` block is separate
  (`@defer (hydrate on viewport) { … } @placeholder { … }`).
- `HttpClient` GET/HEAD responses are transferred to the client automatically by `provideClientHydration()`;
  hand-written `TransferState` for HttpClient calls is redundant. A double fetch usually means hydration is
  missing, the request carries auth headers, or server and client use different origins.
- Incremental hydration reduces JS on load; it does not fix slow TTFB (server/data latency).

---

## 6. Template Optimization (MEDIUM)

### Use Built-in Control Flow

```html
<!-- ✅ CORRECT -->
@if (user(); as user) {
  <span>{{ user.name }}</span>
} @else {
  <span>Guest</span>
}

@for (item of items(); track item.id) {
  <app-item [item]="item" />
} @empty {
  <p>No items</p>
}

<!-- ❌ WRONG - Legacy structural directives -->
<span *ngIf="user; else guest">{{ user.name }}</span>
<ng-template #guest><span>Guest</span></ng-template>
```

### Avoid Complex Template Expressions

```typescript
// ✅ CORRECT - Precompute in the component
class ItemList {
  readonly items = signal<Item[]>([]);
  readonly sortedItems = computed(() =>
    [...this.items()].sort((a, b) => a.name.localeCompare(b.name)),
  );
}
// Template: @for (item of sortedItems(); track item.id) { … }
```

---

## 7. State Management (MEDIUM)

The stack uses **signal services**, not a store library (no NgRx). Rules:

- Private writable `signal()`, public read-only via `asReadonly()` or `computed()` for derived values.
- Feature-scoped state: `@Injectable()` (no `providedIn: 'root'`) provided in the feature route or page
  component — it is created and destroyed with that feature.
- Derived state is `computed()` / `linkedSignal()`; never mirror state with `effect()`.
- Server state is read through resources (stable in v22) and mutated through `HttpClient` + `reload()`.

Examples: [references/extended-patterns.md](references/extended-patterns.md). Adopting a store library is an
architecture decision (ADR), not a review fix.

---

## 8. Memory Management (LOW-MEDIUM)

- Prefer no manual subscription: resources, `toSignal()`, the `async` pipe.
- Long-lived streams subscribed imperatively → `takeUntilDestroyed()` in an injection context (or pass
  `destroyRef`); no `ngOnDestroy` bookkeeping.
- `toSignal` / `toObservable` / `effect` / `takeUntilDestroyed()` called inside a method throw **NG0203**
  unless given an `injector` — create them in field initializers or the constructor.
- One-shot `HttpClient` calls complete by themselves; a blanket "never `.subscribe()`" rule is a false positive there.

Examples: [references/extended-patterns.md](references/extended-patterns.md).

---

## Quick Reference Checklists

> Full New Component, Performance Review and SSR checklists: [references/extended-patterns.md](references/extended-patterns.md).

**New component minimum:**
- [ ] No explicit `changeDetection` (OnPush is the v22 default); any `Eager` override is justified
- [ ] No `standalone: true` (the default since v19) and no `NgModule`
- [ ] `input()` / `output()` / `model()`, `inject()`, signal queries
- [ ] `@for` with `track item.id` (not `$index`)
- [ ] Async data has loading / empty / error / ready states (`angular-ui-patterns`)
- [ ] Accessibility meets WCAG 2.2 AA (`accessibility-audit` skill owns the checklist)

---

## Related Skills

- `angular` — API reference: signals and resources (`references/signals-core.md`), Signal Forms, routing/DI, SSR (`references/ssr-hydration.md`)
- `angular-spa` — workspace conventions, templates, `reference/web-security.md`, `reference/testing-vitest.md`
- `angular-ui-patterns` — canonical load-state union, typed API errors, 401/403 UX, dialogs
- `accessibility-audit` — WCAG 2.2 AA checklist and automated checks
