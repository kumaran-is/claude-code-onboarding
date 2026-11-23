# Angular 21.2 Signals, Interop and Resources — Canonical Reference

This file is the single home for `signal`/`computed`/`linkedSignal`/`effect`, RxJS interop and the
resource APIs. Other Angular skills link here instead of restating it. Every snippet was compiled
against `@angular/*@21.2.x` + TypeScript 5.9 (`strict`, `strictTemplates`).

## API stability in Angular 21.2 (from the `.d.ts` tags)

| API | Status |
|---|---|
| `signal`, `computed`, `effect`, `linkedSignal`, `input`/`output`/`model`, signal queries | Stable |
| `toSignal`, `toObservable`, `takeUntilDestroyed`, `outputFromObservable` | Stable |
| `afterNextRender`, `afterEveryRender`, `afterRenderEffect` | Stable (`afterRender` was removed; use `afterEveryRender`) |
| `resource()` | **EXPERIMENTAL** (`@experimental 19.0`) |
| `rxResource()` | **EXPERIMENTAL** |
| `httpResource()` | **EXPERIMENTAL** (`@experimental 19.2`) |
| Signal Forms (`@angular/forms/signals`) | **EXPERIMENTAL** — see [signal-forms.md](signal-forms.md) |

Experimental APIs may change in a minor release. Using them is a team decision: pin `@angular/*`
with `~21.2.x` and re-check this table on every upgrade. Never describe them as "preferred".

---

## Choosing the tool

| Need | Use |
|---|---|
| Local state | `signal()` |
| Read-only value derived from other signals | `computed()` |
| Writable value that resets when a source changes (selection, page index) | `linkedSignal()` |
| Async read tied to signals (GET) | `rxResource()` / `httpResource()` (experimental) or `toSignal(observable)` |
| Mutations (POST/PUT/PATCH/DELETE) | `HttpClient` call, then `resource.reload()` |
| Event streams, debounce, cancellation, retry | RxJS, bridged with `toSignal` / `toObservable` |
| Push signal state OUT to an imperative API (storage, logging, third-party widget, navigation) | `effect()` |
| DOM work after render | `afterNextRender()` / `afterRenderEffect()` |
| Query DOM / children / projected content | `viewChild()` / `viewChildren()` / `contentChild()` |

---

## Signal queries

```typescript
import { ChangeDetectionStrategy, Component, ElementRef, input, viewChild, viewChildren } from '@angular/core';

@Component({
  selector: 'app-item',
  template: `{{ label() }}`,
})
export class Item {
  readonly label = input.required<string>();
}

@Component({
  selector: 'app-container',
  imports: [Item],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <input #searchInput />
    @for (label of labels(); track label) {
      <app-item [label]="label" />
    }
  `,
})
export class Container {
  readonly labels = input<string[]>([]);
  readonly searchInput = viewChild.required<ElementRef<HTMLInputElement>>('searchInput');
  readonly items = viewChildren(Item);

  focusSearch(): void {
    this.searchInput().nativeElement.focus();
  }
}
```

`viewChild.required` throws when read before the element exists; use the optional `viewChild()` for
elements inside `@if`.

---

## linkedSignal

```typescript
import { linkedSignal, signal } from '@angular/core';

const options = signal(['A', 'B', 'C']);

// Short form: resets to the first option whenever options() changes.
const first = linkedSignal(() => options()[0]);

// Long form: keep the user's choice if it still exists in the new options.
const selected = linkedSignal<string[], string>({
  source: options,
  computation: (next, previous) =>
    previous && next.includes(previous.value) ? previous.value : next[0],
});

selected.set('B');
options.set(['B', 'C', 'D']); // selected() === 'B'
options.set(['X', 'Y']);      // selected() === 'X'
```

---

## effect — the last resort

`effect()` exists to push signal state **out** to code that is not reactive. It is not a state tool.

Use it for: writing a preference to storage, logging/analytics, syncing a third-party widget or
canvas, navigating after a state change.

Never use it to set another signal from a signal. That creates circular updates,
`ExpressionChangedAfterItHasBeenChecked` errors and an extra change-detection pass. The replacement
is `computed()` (read-only) or `linkedSignal()` (writable, resets with its source).

```typescript
import { Injectable, effect, signal } from '@angular/core';

type Theme = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class ThemePreference {
  readonly theme = signal<Theme>('light');

  constructor() {
    // Correct: syncs OUT to the DOM and to storage (a preference, never a credential).
    effect(() => {
      const theme = this.theme();
      document.documentElement.dataset['theme'] = theme;
      localStorage.setItem('theme', theme);
    });
  }
}

// WRONG — mirrors state with an effect:
//   effect(() => this.fullName.set(`${this.first()} ${this.last()}`));
// RIGHT:
//   readonly fullName = computed(() => `${this.first()} ${this.last()}`);
```

For DOM measurement or focus after a render, use `afterNextRender` / `afterRenderEffect`
(see `../SKILL.md` §Render hooks), not `effect()` + `setTimeout`.

---

## RxJS interop and the injection context

`toSignal`, `toObservable`, `effect` and argument-less `takeUntilDestroyed()` must run in an
**injection context**: a field initializer, the constructor, or a factory. Called from a method or
an event handler they throw `NG0203`, and every call would create another live pipeline. If you
really must create one later, pass `{ injector }` (or a `DestroyRef` to `takeUntilDestroyed`).

```typescript
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, interval, map, switchMap } from 'rxjs';
import { UsersApi } from './users-api';

@Component({
  selector: 'app-user-search',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label for="q">Search</label>
    <input id="q" [value]="term()" (input)="term.set($any($event.target).value)" />
    @for (name of names(); track name) { <p>{{ name }}</p> }
  `,
})
export class UserSearch {
  private readonly api = inject(UsersApi);
  private readonly destroyRef = inject(DestroyRef);
  readonly term = signal('');

  // Field initializer = injection context. switchMap cancels stale requests.
  readonly names = toSignal(
    toObservable(this.term).pipe(
      debounceTime(300),
      distinctUntilChanged(),
      switchMap((filter) => this.api.list({ filter, offset: 0 })),
      map((page) => page.items.map((u) => u.name)),
    ),
    { initialValue: [] as string[] },
  );

  startPolling(): void {
    // Outside the injection context: pass the DestroyRef explicitly.
    interval(30_000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.term.update((t) => t));
  }
}
```

Subscriptions: prefer no manual `subscribe()` (resource, `toSignal`, `async` pipe). A one-shot
`HttpClient` call completes on its own, so a blanket "never subscribe" rule is wrong; long-lived
streams (`interval`, `fromEvent`, `valueChanges`, websockets) need `takeUntilDestroyed`.

---

## Resources (EXPERIMENTAL in 21.x)

Since v20 the option is **`params`** (not `request`). `resource` takes a `loader` that returns a
**Promise**; `rxResource` takes a `stream` that returns an Observable; `httpResource` takes a
function returning a URL, an `HttpResourceRequest` object, or `undefined`.

```typescript
import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input, resource } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { UsersApi, type User } from './users-api';

function isUser(value: unknown): value is User {
  return typeof value === 'object' && value !== null && 'id' in value && 'name' in value;
}

@Component({
  selector: 'app-user-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (user.error()) {
      <p role="alert">The user could not be loaded.</p>
      <button type="button" (click)="user.reload()">Try again</button>
    } @else if (user.hasValue()) {
      <h2>{{ user.value().name }}</h2>
    } @else {
      <p role="status">Loading…</p>
    }
  `,
})
export class UserDetail {
  private readonly api = inject(UsersApi);
  readonly id = input<string>(); // bound from the route by withComponentInputBinding()

  // rxResource: Observable source. params → undefined keeps it idle (no request).
  readonly user = rxResource({
    params: () => this.id(),
    stream: ({ params }) => this.api.get(params),
  });

  // httpResource: returning undefined keeps it idle. `parse` validates at runtime —
  // http.get<T>() is only a compile-time cast. Use a schema library here if the project has one.
  readonly profile = httpResource(
    () => {
      const id = this.id();
      return id ? `/api/users/${encodeURIComponent(id)}/profile` : undefined;
    },
    {
      parse: (raw: unknown): User => {
        if (!isUser(raw)) throw new Error('Unexpected profile payload');
        return raw;
      },
    },
  );

  // resource: Promise loader; abortSignal cancels the stale fetch when params change.
  readonly avatar = resource({
    params: () => this.id(),
    loader: async ({ params, abortSignal }) => {
      const res = await fetch(`/api/avatars/${encodeURIComponent(params)}`, { signal: abortSignal });
      if (!res.ok) throw new Error(`Avatar request failed: HTTP ${res.status}`);
      return res.blob();
    },
  });
}
```

### Reading a resource safely

- `value()` **throws** while the resource is in the `error` state. Branch on `error()` first, then
  `hasValue()`, then read `value()` — in templates and in `computed()`.
- `status()` is `'idle' | 'loading' | 'reloading' | 'resolved' | 'error' | 'local'`.
  `loading` (params changed) clears the value; `reloading` (`reload()`) keeps it. Decide on purpose
  whether the page shows a skeleton or keeps the previous data.
- `params` returning `undefined` leaves the resource `idle` with no request — use it for a search
  not yet submitted or a closed dialog.
- Derive one load-state union per page with `computed()`; the canonical pattern (401 → expired,
  403 → forbidden, empty vs ready) lives in
  `../../angular-ui-patterns/reference/loading-control-flow.md`.

### Mutations

Read with resources, write with `HttpClient`. A resource aborts its in-flight load when params
change, so never drive a mutation through one. After the write call `reload()`; on `409 Conflict`
call `reload()` and show the other actor's state.

```typescript
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';

interface Todo { readonly id: string; readonly title: string; readonly done: boolean }

@Injectable()
export class TodoStore {
  private readonly http = inject(HttpClient);
  readonly saving = signal(false);
  readonly todos = rxResource({ stream: () => this.http.get<Todo[]>('/api/todos') });

  async toggle(todo: Todo): Promise<void> {
    if (this.saving()) return; // in-flight guard: no double submit
    this.saving.set(true);
    try {
      await firstValueFrom(
        this.http.patch<Todo>(`/api/todos/${encodeURIComponent(todo.id)}`, { done: !todo.done }),
      );
    } catch (err) {
      if (!(err instanceof HttpErrorResponse && err.status === 409)) throw err;
      // 409: someone else changed it — fall through to reload and show the server state.
    } finally {
      this.saving.set(false);
    }
    this.todos.reload();
  }
}
```

Retries: auto-retry only idempotent GETs, bounded with backoff (`retry({ count: 2, delay: 500 })`).
Never auto-retry POST/PATCH without an idempotency key.

### Paging with a query signal

Keep filters and offset in one query signal, reset the offset when the filter changes, and keep the
backend page cap as a constant. The canonical list example is
`../../angular-spa/reference/angular-ui-tables.md`.
