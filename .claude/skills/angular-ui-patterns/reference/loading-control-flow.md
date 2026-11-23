# Loading State Patterns & Control Flow

Canonical home for the **load-state union**: how a page turns an async read into exactly one of
loading / empty / ready / error. Resource API details (options, stability) live in
`angular/references/signals-core.md`; error typing and 401/403 copy live in `error-handling.md`.

> `resource`, `rxResource` and `httpResource` are stable in Angular 22 (`@publicApi 22.0` in the
> 22.3 `.d.ts`). Re-check the tags on every major upgrade.

## The Golden Rule

**Show a loading indicator only when there is no data to display.** A background refresh keeps the
current data on screen.

## Derive One Load State With `computed()`

Never keep hand-set `loading` / `error` / `items` flags in sync. Derive one discriminated union from the
resource, in this order:

1. **`error()` first** — `value()` throws while the resource is in the error state.
2. **`hasValue()`** — false on the first load and while idle; it narrows `value()` to non-`undefined`.
3. **`value()`** — now safe; split empty vs ready.

```typescript
import { Component, computed, inject, input } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { rxResource } from '@angular/core/rxjs-interop';
import { ApiErrorKind, toApiError } from '../core/http/api-error'; // see error-handling.md
import { ErrorState } from '../shared/components/error-state';       // see error-handling.md

interface Item { readonly id: string; readonly name: string }

type LoadState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'empty' }
  | { readonly kind: 'ready'; readonly items: readonly Item[] }
  | { readonly kind: 'error'; readonly error: ApiErrorKind };

@Component({
  selector: 'app-item-list-page',
  imports: [ErrorState],
  template: `
    @switch (state().kind) {
      @case ('loading') { <div class="skeleton h-8 w-full" role="status" aria-label="Loading items"></div> }
      @case ('empty') { <p>No items yet.</p> }
      @case ('ready') {
        @if (items.isLoading()) { <progress class="progress" aria-label="Refreshing"></progress> }
        <ul>
          @for (item of readyItems(); track item.id) { <li>{{ item.name }}</li> }
        </ul>
      }
      @case ('error') {
        <app-error-state [message]="errorMessage()" [retryable]="retryable()" (retry)="items.reload()" />
      }
    }
  `,
})
export class ItemListPage {
  private readonly http = inject(HttpClient);
  /** Route param bound by withComponentInputBinding(). */
  readonly folder = input<string>();

  // Stable in v22. params() returning undefined → status 'idle', no request is made.
  readonly items = rxResource({
    params: () => this.folder() || undefined,
    stream: ({ params }) =>
      this.http.get<Item[]>(`/api/folders/${encodeURIComponent(params)}/items`),
  });

  readonly state = computed<LoadState>(() => {
    const err = this.items.error();                       // 1. error first
    if (err) return { kind: 'error', error: toApiError(err).kind };
    if (!this.items.hasValue()) return { kind: 'loading' }; // 2. nothing to show yet
    const items = this.items.value();                     // 3. safe now
    return items.length ? { kind: 'ready', items } : { kind: 'empty' };
  });

  protected readonly readyItems = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.items : [];
  });
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    if (s.kind !== 'error') return '';
    return s.error === 'forbidden' ? 'You are not authorised to view these items.' : 'Items could not be loaded.';
  });
  protected readonly retryable = computed(() => {
    const s = this.state();
    return s.kind === 'error' && s.error !== 'forbidden' && s.error !== 'unauthenticated';
  });
}
```

Verified against Angular 21.2.26 with Vitest (not re-run on 22.3; the resource API is unchanged apart from becoming stable): `value()` throws after a 403; `params` returning `undefined`
leaves `status()` at `'idle'` with no request; `reload()` keeps `state()` at `ready` while `status()` is
`'reloading'`.

### `loading` vs `reloading` — choose on purpose

| `status()` | Trigger | `value()` | UI |
|---|---|---|---|
| `'idle'` | `params` returned `undefined` | `undefined` | Prompt ("Pick a folder"), no spinner |
| `'loading'` | `params` changed (new folder, new filter) | cleared | Skeleton |
| `'reloading'` | `reload()` with same params | kept | Keep the list, show a thin progress bar |
| `'error'` | loader/stream failed | throws | Error state (see `error-handling.md`) |
| `'resolved'` / `'local'` | loaded / `set()` locally | value | Data |

If a params change must keep the previous page visible (pagination), keep a snapshot with
`linkedSignal` instead of letting the list blank.

### Stale-while-error (refresh fails while data is on screen)

A resource that errors drops its value (`value()` throws), so the union above would replace a
populated list with a full error page. The framework-neutral standard
(`../../design-system/reference/interaction-contracts.md` §6b) says: error **with** data keeps the
content and adds an inline, non-blocking error; "empty" only after a settled load. Keep the last good
value in a `linkedSignal`:

```typescript
readonly users = rxResource({ stream: () => this.api.list({ filter: '', offset: 0 }) });
/** Last successfully loaded page; survives a later error. */
readonly lastGood = linkedSignal<Page<User> | undefined, Page<User> | undefined>({
  source: () => (this.users.hasValue() ? this.users.value() : undefined),
  computation: (next, previous) => next ?? previous?.value,
});
// Template: @if (users.error() && lastGood()) { <div role="alert" class="alert alert-warning">
//   Showing earlier results — refresh failed. <button (click)="users.reload()">Retry</button></div> }
//   then render lastGood()?.items.
```

Verified (Vitest, 21.2.26; not re-run on 22.3): after a successful load and a 503 on `reload()`, the list stays on screen
with the inline alert. Clear `lastGood` when params change to a different entity (different user,
different tenant) — stale data from another context is worse than a spinner. Skeletons carry
`aria-hidden="true"` inside an `aria-busy="true"` region; timing thresholds are in §6b.

### Reads vs mutations

Read with a resource; mutate with `HttpClient` (`firstValueFrom(...)`) and then call `reload()`. A resource
aborts its in-flight request when params change, so it must never carry a mutation. On a **409** from a
mutation, call `reload()` and show the other actor's state. The mutation flow with an in-flight guard is in
`form-dialog-patterns.md`.

### Extract at the third use

Write the `state` computed inline in the first two pages. When a third page copies it, extract a typed
helper (for example `toLoadState(resource)`) into `shared/` — the Rule of Three in `code-standards.md`.

### Loading State Decision Tree

```
error()?                       → error state (retry only if retryable)
!hasValue() and status idle?   → prompt, no request
!hasValue()?                   → skeleton / spinner
value() empty?                 → empty state
otherwise                      → data (thin progress bar while 'reloading')
```

### Skeleton vs Spinner

| Use Skeleton When    | Use Spinner When      |
| -------------------- | --------------------- |
| Known content shape  | Unknown content shape |
| List/card layouts    | Modal actions         |
| Initial page load    | Button submissions    |
| Content placeholders | Inline operations     |

---

## Control Flow Patterns

### @if/@else for Conditional Rendering

```html
@if (user(); as user) {
  <span>Welcome, {{ user.name }}</span>
} @else {
  <a routerLink="/login">Sign in</a>
}
```

### @for with Track and @empty

```html
@for (item of items(); track item.id) {
  <app-item-card [item]="item" (delete)="remove(item.id)" />
} @empty {
  <app-empty-state title="No items yet" actionLabel="Create item" (action)="create()" />
}
```

### @defer for Progressive Loading

```html
<!-- Critical content loads immediately -->
<app-header />
<app-hero-section />

<!-- Non-critical content deferred -->
@defer (on viewport) {
  <app-comments [postId]="postId()" />
} @placeholder {
  <div class="skeleton h-32 w-full"></div>
} @loading (minimum 200ms) {
  <span class="loading loading-spinner" role="status" aria-label="Loading comments"></span>
} @error {
  <app-error-state message="Comments could not be loaded." />
}
```

`@defer`'s `@error` covers a failed **chunk** load only; data errors inside the deferred component still
need that component's own load state.
