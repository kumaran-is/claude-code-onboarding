# Angular 22.3 Unit Testing with Vitest — Canonical Reference

Canonical home for Angular unit/component tests. The builder facts below were re-checked on an Angular CLI 22.3.0
workspace (`@angular/*@22.3.0`, TypeScript 6.0.3, Vitest 5.1.1, jsdom 31.0.1, Node 26.13.1). The specs below
were first run green on 21.2.26; on 22.3 their code was re-compiled but the specs were not re-run (NOT RUN). E2E belongs to the `browser-testing` skill (Playwright); tool choice per target:
`.claude/rules/testing-tool-selection.md`.

## What a CLI 22.3 workspace gives you

- `angular.json` → `"test": { "builder": "@angular/build:unit-test" }`, runner **Vitest** (default),
  environment **jsdom**. No `vitest.config.ts`, no `karma.conf.js`, no `test.ts`, no zone.js.
- `tsconfig.spec.json` → `"types": ["vitest/globals"]` so `describe`/`it`/`expect`/`vi` are global.
- TestBed is initialized by the builder and runs **zoneless** (zone.js is absent). Adding
  `provideZonelessChangeDetection()` to TestBed providers is optional, not required.

```bash
ng test --watch=false                          # CI run; exit code is the gate
ng test --watch=false --include src/app/users  # a folder or file
ng test --watch=false --filter '^UserList'     # by suite/test name
ng test --watch=false --coverage               # coverage (v8)
ng test --browsers ChromeHeadless              # real browser instead of jsdom (needs @vitest/browser + provider)
```

Migrating an existing Karma/Jasmine project (schematic `refactor-jasmine-vitest` in `@schematics/angular`; re-verify its presence in your CLI version):
switch the `test` target builder to `@angular/build:unit-test`, add `vitest` + `jsdom`, set
`types: ["vitest/globals"]`, then run `ng generate @schematics/angular:refactor-jasmine-vitest` to
rewrite Jasmine APIs (`jasmine.createSpyObj` → `vi.fn()` objects, `spyOn` → `vi.spyOn`). Review the
diff; remove every `fakeAsync`/`waitForAsync` by hand (see below). Browser mode setup:
`ng generate @schematics/angular:vitest-browser`.

## Rules that bite under zoneless + Vitest

| Old habit | Under 21.x Vitest | Use instead |
|---|---|---|
| `fakeAsync` / `tick` / `flush` | Throws `zone-testing.js is needed for the fakeAsync() test helper` | `vi.useFakeTimers()` + `await vi.advanceTimersByTimeAsync(ms)` |
| `waitForAsync` | Needs zone.js | Plain `async` test + `await fixture.whenStable()` |
| `fixture.detectChanges()` after every change | Works, but hides scheduling bugs | `await fixture.whenStable()` (lets the zoneless scheduler render) |
| Set a plain field, expect the DOM to update | Does not render zoneless | Make it a signal or use `componentRef.setInput()` |
| `await fixture.whenStable()` with an unflushed `HttpClient` request | **Hangs**: in-flight requests are pending tasks | Flush via `HttpTestingController` first, then await |
| Signal Forms `submission.action` that awaits `firstValueFrom(http…)` | `whenStable()` returns before the action resolves | Flush the request, then `await vi.waitFor(() => expect(…))` |
| `dialog.showModal()` / `window.matchMedia` in jsdom 31 | Not implemented (`showModal is not a function`, `matchMedia` undefined) | Stub per spec: `HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.open = true; })`, `close` likewise; `vi.stubGlobal('matchMedia', …)`. Real dialog focus and theme behaviour belong in Playwright |

## Component with HttpTestingController and a CDK harness

Harnesses come from `@angular/cdk`, which `ng new` does not install. Add it once, on the same minor as the
framework: `npm install --save-dev @angular/cdk@22.3.0` (then pin it like the other `@angular/*` packages).

The component under test (`user-list.ts`): an `rxResource` list with the error → hasValue → loading order,
a 403 shown as "not authorised" without a retry button, and Retry for other failures.

```typescript
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

interface User {
  id: string;
  name: string;
}
interface Page<T> {
  items: T[];
  total: number;
}

const USERS_URL = 'https://api.example.test/v1/users';

/** HttpClient errors reach resource.error() as the HttpErrorResponse or wrapped in `cause`. */
function httpStatus(error: unknown): number | null {
  if (error instanceof HttpErrorResponse) return error.status;
  const cause = (error as { cause?: unknown } | undefined)?.cause;
  return cause instanceof HttpErrorResponse ? cause.status : null;
}

@Component({
  selector: 'app-user-list',
  template: `
    @if (users.error()) {
      <p role="alert">{{ errorMessage() }}</p>
      @if (canRetry()) {
        <button type="button" class="btn" (click)="users.reload()">Retry</button>
      }
    } @else if (users.hasValue()) {
      <ul>
        @for (user of users.value().items; track user.id) {
          <li>{{ user.name }}</li>
        }
      </ul>
    } @else {
      <p aria-live="polite">Loading users…</p>
    }
  `,
})
export class UserList {
  private readonly http = inject(HttpClient);
  // rxResource is stable in Angular 22 (@publicApi 22.0 in @angular/core/rxjs-interop).
  protected readonly users = rxResource({ stream: () => this.http.get<Page<User>>(USERS_URL) });
  private readonly status = computed(() => httpStatus(this.users.error()));
  // 401/403 will not change on retry: show the reason, offer no retry button.
  protected readonly canRetry = computed(() => this.status() !== 401 && this.status() !== 403);
  protected readonly errorMessage = computed(() =>
    this.status() === 403 ? 'You are not authorised to view users.' : 'Users could not be loaded.',
  );
}
```

The spec and harness below ran green against it on Angular 21.2.26 (`ng test`, 3 tests, exit 0; not re-run on 22.3); removing the
403 message or the Retry button each fails one test (exit 1).

```typescript
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { TestBed } from '@angular/core/testing';
import { UserList } from './user-list';           // rxResource-backed list with a load-state union
import { UserListHarness } from './user-list.harness';

const URL = 'https://api.example.test/v1/users';

describe('UserList', () => {
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    ctrl = TestBed.inject(HttpTestingController);
  });
  afterEach(() => ctrl.verify()); // fails on unexpected or unflushed requests

  const pending = () => ctrl.expectOne((r) => r.url === URL);

  async function render(respond: (req: ReturnType<typeof pending>) => void) {
    const fixture = TestBed.createComponent(UserList);
    fixture.detectChanges();                 // first render: loading state, request issued
    const loadingText: string = fixture.nativeElement.textContent;
    respond(pending());                      // flush BEFORE whenStable()/harness calls
    await fixture.whenStable();
    const harness = await TestbedHarnessEnvironment.harnessForFixture(fixture, UserListHarness);
    return { harness, loadingText };
  }

  it('renders rows on success', async () => {
    const { harness, loadingText } = await render((r) => r.flush({ items: [{ id: '1', name: 'Ada' }], total: 1 }));
    expect(loadingText).toContain('Loading users');
    expect(await harness.names()).toEqual(['Ada']);
  });

  it('renders 403 as not authorised, without retry', async () => {
    const { harness } = await render((r) => r.flush(null, { status: 403, statusText: 'Forbidden' }));
    expect(await harness.errorText()).toContain('not authorised');
  });

  it('retries after a 503', async () => {
    const { harness } = await render((r) => r.flush({ detail: 'Upstream timeout' }, { status: 503, statusText: 'Unavailable' }));
    const click = harness.retry();                  // the click's stability wait blocks on the reload…
    const reload = await vi.waitFor(() => pending()); // …so flush it while the click is pending
    reload.flush({ items: [{ id: '2', name: 'Grace' }], total: 1 });
    await click;
    expect(await harness.names()).toEqual(['Grace']);
  });
});
```

```typescript
// user-list.harness.ts — tests talk to the harness, not to CSS selectors
import { ComponentHarness } from '@angular/cdk/testing';

export class UserListHarness extends ComponentHarness {
  static hostSelector = 'app-user-list';
  private readonly rows = this.locatorForAll('li');
  private readonly alert = this.locatorForOptional('[role="alert"]');
  private readonly retryButton = this.locatorForOptional('button');

  async names(): Promise<string[]> {
    return Promise.all((await this.rows()).map((row) => row.text()));
  }
  async errorText(): Promise<string | null> {
    return (await this.alert())?.text() ?? null;
  }
  async retry(): Promise<void> {
    const button = await this.retryButton();
    if (!button) throw new Error('No retry button rendered');
    await button.click();
  }
}
```

Harness API detail (Material harnesses, `getHarness`, `getAllHarnesses`): [component-harnesses.md](component-harnesses.md).

## Debounce with Vitest fake timers

```typescript
beforeEach(() => {
  vi.useFakeTimers();
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
});
afterEach(() => vi.useRealTimers());

it('debounces input and renders results', async () => {
  const ctrl = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(UserSearch); // toObservable(term).pipe(debounceTime(300), switchMap(...))
  fixture.componentInstance.term.set('a');
  fixture.componentInstance.term.set('ad');
  await vi.advanceTimersByTimeAsync(300);
  ctrl.expectNone((r) => r.params.get('filter') === 'a');
  ctrl.expectOne((r) => r.params.get('filter') === 'ad').flush({ items: [{ id: '1', name: 'Ada' }], total: 1 });
  await vi.advanceTimersByTimeAsync(0);
  await fixture.whenStable();
  expect(fixture.nativeElement.querySelectorAll('li').length).toBe(1);
  ctrl.verify();
});
```

## Signal inputs, outputs and services

```typescript
it('renders the name input and emits on select', async () => {
  const fixture = TestBed.createComponent(UserCard);
  fixture.componentRef.setInput('id', 'u1');      // signal inputs: setInput, never assign
  fixture.componentRef.setInput('name', 'Ada');
  const emitted = vi.fn();
  fixture.componentInstance.selected.subscribe(emitted);
  await fixture.whenStable();
  expect(fixture.nativeElement.textContent).toContain('Ada');
  fixture.nativeElement.querySelector('button').click();
  expect(emitted).toHaveBeenCalledWith('u1');
});
```

Code that calls `inject()` outside a class (a factory function, a guard) runs in tests via
`TestBed.runInInjectionContext(() => fn())`.

Mock collaborators with `{ provide: X, useValue: { method: vi.fn() } }`; type the mock with
`vi.fn<(arg: A) => R>()` rather than `any`.

## Guards and routing

Use `RouterTestingHarness` with a real `provideRouter([...])` config. Example for an async auth
guard (waits for session restore, redirects with `returnUrl`, shows an error page when restore
fails): `web-security.md` §Testing.

## What to test per component

- Every load state the template can show: loading, empty, error (401, 403, 5xx, offline), success.
- Every user action, including the in-flight guard (double click does not double submit).
- Accessibility basics in the unit test (role="alert"/"status" present, labels); full checks with
  axe in Playwright — "no automated violations; manual checks required" (see `accessibility-audit`).
