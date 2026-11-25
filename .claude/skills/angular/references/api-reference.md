# Angular 22.3 API Reference — Routing, DI, Composition, State

Canonical home for routing/DI/composition APIs. Signals and resources live in
[signals-core.md](signals-core.md); auth guards and interceptors live in
`../../angular-spa/reference/web-security.md`; tests live in
`../../angular-spa/reference/testing-vitest.md`. Every snippet compiled against `@angular/*@22.3.0`,
TypeScript 6.0.3, `strictTemplates`.

---

## Routing

### Route matching, resolvers and component input binding

```typescript
import { HttpClient } from '@angular/common/http';
import { Component, Service, inject, input, signal } from '@angular/core';
import { CanMatchFn, RedirectCommand, ResolveFn, Router, Routes } from '@angular/router';
import { catchError, of } from 'rxjs';

export interface Product { readonly id: string; readonly name: string }

@Service()
export class ProductsApi {
  private readonly http = inject(HttpClient);
  get(id: string) { return this.http.get<Product>(`/api/products/${encodeURIComponent(id)}`); }
  list() { return this.http.get<Product[]>('/api/products'); }
}

@Service()
export class FeatureFlags {
  private readonly enabled = signal<ReadonlySet<string>>(new Set());
  isOn(flag: string): boolean { return this.enabled().has(flag); }
}

// canMatch: decides whether the route matches at all (the lazy chunk is not downloaded).
export const betaMatch: CanMatchFn = () => inject(FeatureFlags).isOn('beta-reports');

// Resolver: a missing record becomes a redirect, not an unhandled navigation error.
export const productResolver: ResolveFn<Product> = (route) => {
  const router = inject(Router);
  return inject(ProductsApi)
    .get(route.paramMap.get('id') ?? '')
    .pipe(catchError(() => of(new RedirectCommand(router.parseUrl('/not-found')))));
};

@Component({
  selector: 'app-product-page',
  template: `<h1>{{ product().name }}</h1><p>Tab: {{ tab() ?? 'overview' }}</p>`,
})
export class ProductPage {
  // provideRouter(routes, withComponentInputBinding()): resolved data, path params and
  // query params bind to inputs by name. No ActivatedRoute subscription needed.
  readonly product = input.required<Product>();
  readonly tab = input<string>(); // ?tab=reviews
}

export const productRoutes: Routes = [
  { path: 'reports', canMatch: [betaMatch], loadComponent: () => import('./reports').then((m) => m.Reports) },
  { path: 'products/:id', resolve: { product: productResolver }, component: ProductPage },
];
```

Rules:
- Guards, resolvers and `CanMatchFn` are functions; call every `inject()` **before** the first
  `await` (after it there is no injection context).
- Return a `UrlTree` or `RedirectCommand` to redirect; never call `router.navigate()` inside a guard.
- Prefer a resource in the component over a resolver when the page can render a loading state —
  resolvers block navigation with no feedback.
- Guards are UX. The server authorizes every request. Auth guard that waits for session restore and
  validates `returnUrl`: `../../angular-spa/reference/web-security.md`.

---

## Dependency injection

```typescript
import { InjectionToken } from '@angular/core';

// Typed token with a factory default: no provider needed unless you override it.
export interface PagingConfig { readonly pageSize: number; readonly maxPageSize: number }
export const PAGING_CONFIG = new InjectionToken<PagingConfig>('PAGING_CONFIG', {
  providedIn: 'root',
  factory: () => ({ pageSize: 25, maxPageSize: 100 }),
});
// Override: providers: [{ provide: PAGING_CONFIG, useValue: { pageSize: 50, maxPageSize: 100 } }]
```

- Use `inject()` in field initializers; constructor parameter injection still works but is not the
  house style.
- `@Service()` for app-wide singletons (Angular 22; `providedIn: 'root'` stays only on `InjectionToken`
  factories like the one above); `@Service({ autoProvided: false })` + component or route `providers: [...]`
  for a store scoped to one page (destroyed with it).

---

## Component composition

```typescript
import { Component, Directive, input } from '@angular/core';

@Component({
  selector: 'app-card',
  template: `
    <div class="card bg-base-100 shadow-sm">
      <div class="card-body">
        <h2 class="card-title"><ng-content select="[card-title]" /></h2>
        <ng-content />
      </div>
    </div>
  `,
})
export class Card {}
// <app-card><span card-title>Title</span><p>Body</p></app-card>

@Directive({ selector: '[appTooltip]', host: { '[attr.title]': 'tooltip()' } })
export class Tooltip {
  readonly tooltip = input('');
}

// hostDirectives: behaviour composition without inheritance; inputs can be re-mapped.
@Component({
  selector: 'app-icon-button',
  hostDirectives: [{ directive: Tooltip, inputs: ['tooltip: label'] }],
  template: `<ng-content />`,
})
export class IconButton {}
// <app-icon-button label="Delete">…</app-icon-button>
```

Use `host: {}` in the decorator, not `@HostBinding`/`@HostListener`.

---

## Signal-based state

```typescript
import { Injectable, Service, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { ProductsApi } from './products-api';

type Theme = 'light' | 'dark';
interface Notice { readonly id: string; readonly read: boolean }

// App-wide state: private writable signals, public read-only views.
@Service()
export class UiState {
  private readonly _theme = signal<Theme>('light');
  private readonly _notices = signal<readonly Notice[]>([]);
  readonly theme = this._theme.asReadonly();
  readonly notices = this._notices.asReadonly();
  readonly unreadCount = computed(() => this._notices().filter((n) => !n.read).length);

  toggleTheme(): void { this._theme.update((t) => (t === 'light' ? 'dark' : 'light')); }
  addNotice(notice: Notice): void { this._notices.update((list) => [...list, notice]); }
}

// Page-scoped store (provide in the component). Reads use a resource (stable in v22) so the
// page gets loading/error/value without a hand-rolled subscribe + loading flag.
@Injectable()
export class ProductStore {
  private readonly api = inject(ProductsApi);
  readonly filter = signal('');
  readonly products = rxResource({ stream: () => this.api.list() });
  readonly filtered = computed(() => {
    if (!this.products.hasValue()) return [];
    const term = this.filter().toLowerCase();
    return this.products.value().filter((p) => p.name.toLowerCase().includes(term));
  });
}
```

The page renders `products.error()` before `filtered()` — see
`../../angular-ui-patterns/reference/loading-control-flow.md`. Never hide a failed load behind an
empty list.

---

## Signals vs RxJS

| Use case | Signals | RxJS |
|---|---|---|
| Local / shared UI state | `signal`, `computed`, `linkedSignal` | Overkill |
| Read data tied to inputs | `httpResource` / `rxResource` / `resource` or `toSignal` | `HttpClient` observable |
| Debounce, cancel, retry, merge event streams | — | `switchMap`, `debounceTime`, `retry` |
| Push state to non-reactive code | `effect()` (last resort) | `tap` in a stream you already have |

## Do / Don't

| Area | Do | Don't |
|---|---|---|
| Change detection | OnPush default (v22) — never set it explicitly | Opt into `Eager` without a reason |
| Zoneless | Nothing to add — default in 22.x | Add zone.js or `provideZoneChangeDetection()` without a reason |
| Inputs / outputs | `input()`, `output()`, `model()` | `@Input()` / `@Output()` in new code |
| DI | `inject()` | Constructor parameter lists in new code |
| Lazy loading | `loadComponent`, `loadChildren`, `@defer` | Eager-load every feature |
| Forms | Signal Forms for new forms; typed reactive forms in existing code | Untyped `FormGroup` / `any` |
