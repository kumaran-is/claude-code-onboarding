# Angular 22.3 Code Templates

Bodies for features in an Angular 22.3 SPA. Compiled against `@angular/*@22.3.0`,
TypeScript 6.0.3, `strictTemplates`. **Create each file with the CLI first** (`npm exec --no -- ng generate
service|component|guard|interceptor <path/name>`), then replace the generated body with the code
below. Never create these files by hand.

> Zoneless and OnPush are the v22 defaults: no `zone.js`, no change-detection provider, no
> `changeDetection` property. `standalone: true` is the default — omit it. Do not import
> `CommonModule`. Background: `angular` skill §Zoneless + OnPush.

Canonical homes used by these templates:
- Load / empty / error states and the typed `ApiError`: `angular-ui-patterns/reference/loading-control-flow.md`, `error-handling.md`
- Auth interceptor, guard, returnUrl, token storage: [web-security.md](web-security.md)
- Unit tests: [testing-vitest.md](testing-vitest.md)
- Paged list with a query signal: [angular-ui-tables.md](angular-ui-tables.md)

---

## Service

```typescript
import { HttpClient, HttpParams } from '@angular/common/http';
import { Service, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_CONFIG } from '../../core/config/api-config';

export interface User { readonly id: string; readonly name: string }
export interface Page<T> { readonly items: readonly T[]; readonly total: number }
export interface UserQuery { readonly filter: string; readonly offset: number }

@Service()
export class UsersApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_CONFIG).apiRoots[0]}/users`;

  list(query: UserQuery): Observable<Page<User>> {
    const params = new HttpParams().set('filter', query.filter).set('offset', query.offset);
    return this.http.get<Page<User>>(this.base, { params });
  }

  get(id: string): Observable<User> {
    return this.http.get<User>(`${this.base}/${encodeURIComponent(id)}`);
  }
}
```

- Services return typed observables and **let errors propagate**; the page decides what to show.
  Never `catchError(() => of([]))`.
- Encode every path segment (`encodeURIComponent`); build query strings with `HttpParams`.
- `http.get<T>()` is a compile-time cast. Validate untrusted payloads at the boundary (a `parse`
  function or a schema library) when the shape matters for security or money.
- Map API DTOs to view models inside the service when they differ; components never import raw API types.
- Frontend `environment.ts` files are public. Put only public config there (API origin, feature
  flags) — never secrets.

## Page component (resource + load-state union)

```typescript
import { Component, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { toApiError } from '../../core/http/api-error';
import { UserQuery, UsersApi } from './users-api';

@Component({
  selector: 'app-user-list',
  template: `
    @if (users.error()) {
      <div role="alert" class="alert alert-error">
        <span>{{ errorMessage() }}</span>
        <button type="button" class="btn btn-sm" (click)="users.reload()">Try again</button>
      </div>
    } @else if (!users.hasValue()) {
      <p role="status"><span class="loading loading-spinner" aria-hidden="true"></span> Loading users…</p>
    } @else {
      <ul class="list">
        @for (user of users.value().items; track user.id) {
          <li class="list-row">{{ user.name }}</li>
        } @empty {
          <li>No users match “{{ query().filter }}”.</li>
        }
      </ul>
    }
  `,
})
export class UserList {
  private readonly api = inject(UsersApi);
  protected readonly query = signal<UserQuery>({ filter: '', offset: 0 });

  // rxResource is stable in v22. Branch on error() → hasValue() → value(): value() throws in error.
  readonly users = rxResource({ params: () => this.query(), stream: ({ params }) => this.api.list(params) });

  protected readonly errorMessage = computed(() => {
    const kind = toApiError(this.users.error()).kind;
    return kind === 'network' ? 'You appear to be offline.' : 'Users could not be loaded.';
  });

  search(filter: string): void {
    this.query.set({ filter: filter.trim(), offset: 0 }); // a filter change resets paging
  }
}
```

The full version (401 → sign in again, 403 → no retry, typed `LoadState` union, tests) lives in
`angular-ui-patterns/reference/loading-control-flow.md` and [testing-vitest.md](testing-vitest.md).

## Lazy routes

```typescript
import { Routes } from '@angular/router';
import { signedInGuard } from './core/auth/signed-in.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'users' },
  { path: 'login', loadComponent: () => import('./features/auth/login').then((m) => m.Login) },
  {
    path: 'users',
    canActivate: [signedInGuard], // UX only — the API authorizes every request
    loadChildren: () => import('./features/users/users.routes').then((m) => m.USER_ROUTES),
  },
  { path: '**', loadComponent: () => import('./features/not-found').then((m) => m.NotFound) },
];
```

Use a real not-found page for `**` instead of silently redirecting; set a `title` per route so the
document title changes on navigation (route-change focus: `angular-spa/reference/angular-aria.md`).

## app.config.ts

```typescript
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { API_CONFIG } from './core/config/api-config';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor])),
    {
      provide: API_CONFIG,
      useValue: { apiRoots: ['https://api.example.test/v1'], refreshUrl: 'https://api.example.test/v1/auth/refresh' },
    },
  ],
};
```

- No zone provider (zoneless default). No `provideAnimations()`: `@angular/animations` is deprecated
  since v20.2 — use `animate.enter` / `animate.leave` + CSS ([angular-animations.md](angular-animations.md)).
- `authInterceptor`, `API_CONFIG`, `signedInGuard`: [web-security.md](web-security.md).

## Tests

Component, service, harness, `HttpTestingController` and fake-timer templates:
[testing-vitest.md](testing-vitest.md). Do not copy Karma/Jasmine or `fakeAsync` templates from
older docs — they fail under the 21.x Vitest runner.
