# Form Patterns & Dialog/Modal Patterns

Forms here use **typed reactive forms** — the production default on Angular 21.x. Signal Forms
(`@angular/forms/signals`) are EXPERIMENTAL in 21.x; see `angular/references/signal-forms.md` before
using them. Field-level validation catalogues live in `angular-spa/reference/angular-forms-validation.md`.

## Form with Validation, In-Flight Guard and Server Errors

```typescript
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { toApiError } from '../core/http/api-error';
import { Logger } from '../core/logging/logger';
import { ToastService } from '../core/ui/toast.service';

type FieldName = 'name' | 'email';

@Component({
  selector: 'app-user-form',
  imports: [ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form [formGroup]="form" (ngSubmit)="onSubmit()" novalidate>
      <label for="name">Name</label>
      <input id="name" formControlName="name" [attr.aria-invalid]="isFieldInvalid('name')"
             aria-describedby="name-error" />
      @if (isFieldInvalid('name')) { <span id="name-error" class="text-error">{{ fieldError('name') }}</span> }

      <label for="email">Email</label>
      <input id="email" type="email" formControlName="email" [attr.aria-invalid]="isFieldInvalid('email')"
             aria-describedby="email-error" />
      @if (isFieldInvalid('email')) { <span id="email-error" class="text-error">{{ fieldError('email') }}</span> }

      @if (serverError(); as message) { <p role="alert" class="text-error">{{ message }}</p> }

      <button type="submit" class="btn btn-primary" [disabled]="submitting()">
        {{ submitting() ? 'Submitting…' : 'Submit' }}
      </button>
    </form>
  `,
})
export class UserForm {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly http = inject(HttpClient);
  private readonly toast = inject(ToastService);
  private readonly logger = inject(Logger);

  readonly submitting = signal(false);
  readonly serverError = signal<string | null>(null);

  // FormGroup<{ name: FormControl<string>; email: FormControl<string> }> — mirror server limits here
  readonly form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(80)]],
    email: ['', [Validators.required, Validators.email]],
  });

  isFieldInvalid(field: FieldName): boolean {
    const control = this.form.controls[field];
    return control.invalid && control.touched;
  }

  fieldError(field: FieldName): string {
    const control = this.form.controls[field];
    if (control.hasError('required')) return 'This field is required';
    if (control.hasError('email')) return 'Enter a valid email address';
    if (control.hasError('minlength')) return 'Use at least 2 characters';
    if (control.hasError('maxlength')) return 'Use at most 80 characters';
    return '';
  }

  async onSubmit(): Promise<void> {
    if (this.submitting()) return;        // in-flight guard (Enter + click can both submit)
    if (this.form.invalid) {
      this.form.markAllAsTouched();       // reveal errors instead of a silently disabled button
      return;
    }
    this.submitting.set(true);
    this.serverError.set(null);
    try {
      const value = this.form.getRawValue();
      await firstValueFrom(this.http.post('/api/users', { ...value, name: value.name.trim() }));
      this.toast.success('User saved.');
    } catch (err) {
      this.logger.error('saveUser failed', err);
      const apiError = toApiError(err);
      // 409/422: show the server's string detail verbatim; generic copy otherwise.
      this.serverError.set(
        (apiError.kind === 'validation' || apiError.kind === 'conflict') && apiError.detail
          ? apiError.detail
          : 'The user could not be saved. Try again.',
      );
    } finally {
      this.submitting.set(false);
    }
  }
}
```

Rules:
- Use `NonNullableFormBuilder` / typed controls; index fields with `form.controls[name]`, not `form.get('string')`.
- Zoneless: `setValue` / `patchValue` from code do not schedule change detection on their own. Template
  events do; programmatic updates need a signal the template reads (or `markForCheck`).
- Mirror server limits (required, max length, trim) on the client — the server still validates.

---

## Confirmation Dialog — Stays Open While the Mutation Runs

The action runs **inside** the dialog so the dialog can keep focus, block Escape/backdrop dismissal while
the request is in flight, and show the failure in place.

```typescript
import { DIALOG_DATA, Dialog, DialogRef } from '@angular/cdk/dialog';
import { ChangeDetectionStrategy, Component, Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Logger } from '../core/logging/logger';

export interface ConfirmOptions {
  readonly title: string;
  readonly message: string;
  readonly confirmText: string;
  readonly action: () => Promise<void>;
}

@Component({
  selector: 'app-confirm-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 id="confirm-title">{{ data.title }}</h2>
    <p>{{ data.message }}</p>
    @if (failed()) {
      <p role="alert" class="text-error">That did not work. Nothing was changed. Try again.</p>
    }
    <button type="button" class="btn" [disabled]="busy()" (click)="ref.close(false)">Cancel</button>
    <button type="button" class="btn btn-error" [disabled]="busy()" (click)="confirm()">
      {{ busy() ? 'Working…' : data.confirmText }}
    </button>
  `,
})
export class ConfirmDialog {
  protected readonly data = inject<ConfirmOptions>(DIALOG_DATA);
  protected readonly ref = inject<DialogRef<boolean>>(DialogRef);
  private readonly logger = inject(Logger);
  protected readonly busy = signal(false);
  protected readonly failed = signal(false);

  async confirm(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.failed.set(false);
    this.ref.disableClose = true; // Escape / backdrop cannot dismiss a running mutation
    try {
      await this.data.action();
      this.ref.close(true);
    } catch (err) {
      this.logger.error('confirm action failed', err);
      this.failed.set(true); // stay open: retry or cancel
    } finally {
      this.busy.set(false);
      this.ref.disableClose = false;
    }
  }
}

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly dialog = inject(Dialog);

  /** Resolves true only when the action completed. CDK Dialog traps focus and focuses the first tabbable element after render. */
  async confirm(options: ConfirmOptions): Promise<boolean> {
    const ref = this.dialog.open<boolean, ConfirmOptions>(ConfirmDialog, {
      data: options,
      ariaLabelledBy: 'confirm-title',
    });
    return (await firstValueFrom(ref.closed)) ?? false;
  }
}

// Usage (in a page that reads with a resource)
async remove(item: Item): Promise<void> {
  const done = await this.confirmService.confirm({
    title: 'Delete item',
    message: `Delete "${item.name}"? This cannot be undone.`,
    confirmText: 'Delete',
    action: () => firstValueFrom(this.api.remove(item.id)),
  });
  if (!done) return;
  this.toast.success(`"${item.name}" was deleted.`);
  this.items.reload(); // mutate with HttpClient, then reload the resource
}
```

Verified with Vitest on Angular 21.2 + CDK 21.2: Escape is ignored while the action is pending and the
error renders in the still-open dialog; with `disableClose` removed the same test fails (negative control).
If you use a native `<dialog>` instead, open it with `showModal()` inside `afterNextRender(…, { injector })`
so it has an accessible name and a focus target, and cancel the `cancel` event while busy.
