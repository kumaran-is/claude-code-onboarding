# Error Handling Patterns

Canonical home for the **typed API error model**, the **401 vs 403** UX and the error-state component.
Where requests get credentials, refresh and redirect: `angular-spa/reference/web-security.md`.

## Error Handling Hierarchy

```
1. Inline error (field-level) → form validation and 400/422 field details
2. Toast notification         → recoverable action errors; user can retry
3. Error banner / state       → page data failed; offer retry when it can help
4. Full error screen          → unrecoverable (e.g. session restore failed)
```

## One Typed Error Model

Components never parse `HttpErrorResponse` ad hoc. One helper maps it to a closed set of kinds:

```typescript
// core/http/api-error.ts
import { HttpErrorResponse } from '@angular/common/http';

export type ApiErrorKind =
  | 'unauthenticated' // 401: session expired, sign in again
  | 'forbidden'       // 403: signed in, not allowed (the server decided)
  | 'not-found'
  | 'conflict'        // 409: someone else changed it, reload
  | 'validation'      // 400/422
  | 'network'         // status 0: offline, CORS, DNS
  | 'server';         // 5xx and anything else

export interface ApiError {
  readonly kind: ApiErrorKind;
  readonly status: number;
  /** Server-provided human-readable detail, shown verbatim only when it is a string. */
  readonly detail?: string;
}

/** RFC 9457 `detail` first, then the JSON envelope's `message` (api-design-principles § Error Response Format). */
function readServerText(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined;
  if ('detail' in body && typeof body.detail === 'string') return body.detail;
  if ('message' in body && typeof body.message === 'string') return body.message;
  return undefined;
}

export function toApiError(err: unknown): ApiError {
  if (!(err instanceof HttpErrorResponse)) return { kind: 'server', status: -1 };
  const detail = readServerText(err.error);
  const kind: ApiErrorKind =
    err.status === 0 ? 'network'
    : err.status === 401 ? 'unauthenticated'
    : err.status === 403 ? 'forbidden'
    : err.status === 404 ? 'not-found'
    : err.status === 409 ? 'conflict'
    : err.status === 400 || err.status === 422 ? 'validation'
    : 'server';
  return { kind, status: err.status, detail };
}
```

## 401 vs 403 — Different Problems, Different Screens

Client route guards are **UX only**: they hide pages from signed-out users. The **server authorizes every
request**, so a page can still receive 401 or 403 after the guard let the user in.

| Status | Meaning | UI | Never |
|---|---|---|---|
| 401 `unauthenticated` | Session missing or expired (after the interceptor's one refresh attempt failed) | "Your session has expired. Sign in again." Sign out, then navigate to `/login?returnUrl=<current>` once | Loop: login → page → 401 → login. If sign-out itself fails, show a page error and stop |
| 403 `forbidden` | Signed in, not allowed | "You are not authorised to …" in place of the content; optionally "Sign in with another account" | Treat as 401, auto-redirect to login, or offer "Try again" |
| 409 `conflict` | Changed by someone else | Reload the resource and say so | Overwrite silently |
| 400/422 `validation` | Bad input | Field errors; show the server's string `detail` verbatim, generic copy otherwise | Swallow |
| 0 `network` | Offline / CORS | "You appear to be offline." + retry | Show mock or cached-as-fresh data |

The interceptor (refresh once, single-flight, no retry loop) and the guard that waits for session restore
are in `angular-spa/reference/web-security.md`.

## The `Logger` service (`core/logging/logger.ts`)

The one place in the app that may call `console.*`. Everything else injects `Logger`, so swapping the sink
(an error monitor, a log endpoint) is a one-file change and tests can assert what was logged.

```typescript
// core/logging/logger.ts
import { Injectable, isDevMode } from '@angular/core';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

@Injectable({ providedIn: 'root' })
export class Logger {
  debug(message: string, context?: unknown): void { if (isDevMode()) this.write('debug', message, context); }
  info(message: string, context?: unknown): void { this.write('info', message, context); }
  warn(message: string, context?: unknown): void { this.write('warn', message, context); }
  error(message: string, context?: unknown): void { this.write('error', message, context); }

  /** Single sink. Never pass tokens, passwords or personal data in `context`. */
  protected write(level: LogLevel, message: string, context?: unknown): void {
    const at = new Date().toISOString();
    let line: string;
    try {
      line = JSON.stringify({ level, message, context, at }, (_key, value: unknown) =>
        value instanceof Error ? { name: value.name, message: value.message } : value);
    } catch {
      line = JSON.stringify({ level, message, at, context: '[unserializable]' }); // logging must never throw
    }
    console[level](line);
  }
}
```

Tests: provide a subclass that records `write()` calls (`{ provide: Logger, useClass: RecordingLogger }`) and
assert the error was logged; do not spy on `console`.

## Always Show Errors — Log AND Tell the User

**Never swallow errors.** Every catch logs through the app's `Logger` service (never `console.*` in
production code) **and** surfaces something the user can see.

```typescript
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { toApiError } from '../core/http/api-error';
import { Logger } from '../core/logging/logger';
import { CreateItemDto, ItemApi } from './item-api';
import { ToastService } from '../core/ui/toast.service';

@Component({
  selector: 'app-create-item',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button type="button" [disabled]="saving()" (click)="create({ name: 'New' })">Create</button>`,
})
export class CreateItem {
  private readonly api = inject(ItemApi);
  private readonly toast = inject(ToastService);
  private readonly logger = inject(Logger);
  private readonly router = inject(Router);
  readonly saving = signal(false);

  async create(dto: CreateItemDto): Promise<void> {
    if (this.saving()) return; // in-flight guard: a double click never sends twice
    this.saving.set(true);
    try {
      const item = await firstValueFrom(this.api.create(dto));
      this.toast.success(`"${item.name}" was added to Items.`); // say where it now lives
      await this.router.navigate(['/items']);
    } catch (err) {
      this.logger.error('createItem failed', err); // for operators
      const apiError = toApiError(err);
      this.toast.error(                              // for the user
        apiError.kind === 'validation' && apiError.detail
          ? apiError.detail
          : 'The item could not be created. Try again.',
      );
    } finally {
      this.saving.set(false);
    }
  }
}
```

```typescript
// ❌ WRONG — logged, but the user sees nothing
try {
  await firstValueFrom(this.api.create(dto));
} catch (err) {
  this.logger.error('createItem failed', err);
}
```

## Error State Component

`output()` returns an `OutputEmitterRef`, which has **no `.observed`** (TS2339 in 21.2). The parent states
whether a retry makes sense with an input:

```typescript
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-error-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div role="alert" class="alert alert-error">
      <h3>{{ title() }}</h3>
      <p>{{ message() }}</p>
      @if (retryable()) {
        <button type="button" class="btn btn-primary" (click)="retry.emit()">Try again</button>
      }
    </div>
  `,
})
export class ErrorState {
  readonly title = input('Something went wrong');
  readonly message = input('An unexpected error occurred');
  readonly retryable = input(false);
  readonly retry = output<void>();
}
```

Usage: `<app-error-state [message]="msg()" [retryable]="kind() !== 'forbidden'" (retry)="res.reload()" />`.
`role="alert"` announces the failure to screen readers; contrast and focus rules are in the
`accessibility-audit` skill (WCAG 2.2 AA).
