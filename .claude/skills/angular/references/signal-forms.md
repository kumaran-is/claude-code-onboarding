# Signal Forms (stable in Angular 22)

> **Status:** `@angular/forms/signals` is stable in v22 (`form()` is `@publicApi 22.0` in the 22.3
> `.d.ts`; `get_best_practices` for v22: "Prefer Signal Forms for new forms"). **New forms use Signal
> Forms.** Existing typed reactive forms (`NonNullableFormBuilder`, `FormGroup<T>`, patterns in
> `../../angular-spa/reference/angular-forms-*.md`) stay supported; migrate them deliberately.
>
> Every snippet below was compiled and its spec run against `@angular/*@22.3.0`, TypeScript 6.0.3,
> `strictTemplates`, Vitest via `@angular/build:unit-test`.

## Decision

| Situation | Use |
|---|---|
| New form (any size) | Signal Forms |
| Existing form on typed reactive forms | Keep it; migrate only as a planned change with tests |
| Shared custom control used by both | Implement `FormValueControl` for Signal Forms; keep `ControlValueAccessor` while reactive forms still use it |
| Template-driven `ngModel` | Avoid for new code |

## The real API (names verified in `node_modules/@angular/forms/types/signals.d.ts`)

| Need | Export from `@angular/forms/signals` |
|---|---|
| Create a field tree from a `WritableSignal<T>` model | `form(model, schemaFn?)` |
| Bind a field to a native input or custom control | `FormField` directive, `[formField]="f.email"` |
| Built-in rules | `required`, `email`, `min`, `max`, `minLength`, `maxLength`, `pattern` (each takes an optional `{ message }`) |
| Custom / cross-field rule | `validate(path, ({ value, valueOf }) => error \| undefined)` |
| Async rule / HTTP rule | `validateAsync`, `validateHttp` |
| Whole-tree rule | `validateTree` |
| Conditional state | `disabled`, `hidden`, `readonly`, `applyWhen`, `applyWhenValue` |
| Reusable schema / arrays | `schema(fn)`, `apply`, `applyEach` |
| Input debounce | `debounce(path, ms \| 'blur')` |
| Submission | `submit(form, action)` or `submit(form, { action, onInvalid, ignoreValidators })` |
| Standard Schema (e.g. Zod) | `validateStandardSchema` |

There is **no** `signalForm`, `signalInput`, `@angular/forms/signal`, `[control]` or `[field]` binding
in 22.3 — those names appear in older blog posts and earlier drafts of this file and do not compile.

Field state is read by calling the field: `f.email().value()`, `.valid()`, `.invalid()`,
`.touched()`, `.dirty()`, `.disabled()`, `.errors()`, `.pending()`; the root adds
`f().submitting()`. Errors are `{ kind: string; message?: string }`.

## Example — registration form with cross-field and server errors

```typescript
import { Component, inject, signal } from '@angular/core';
import { FormField, disabled, email, form, minLength, required, submit, validate } from '@angular/forms/signals';
import { RegistrationApi } from './registration-api'; // register(body): Promise<'created' | 'email-taken'>

interface Registration {
  email: string;
  password: string;
  confirmPassword: string;
  acceptTerms: boolean;
}

@Component({
  selector: 'app-register-form',
  imports: [FormField],
  template: `
    <form novalidate (submit)="onSubmit($event)">
      <label for="email">Email</label>
      <input id="email" type="email" [formField]="registerForm.email" />
      @if (registerForm.email().touched()) {
        @for (error of registerForm.email().errors(); track error.kind) {
          <p class="text-error" role="alert">{{ error.message }}</p>
        }
      }

      <label for="password">Password</label>
      <input id="password" type="password" [formField]="registerForm.password" />

      <label for="confirm">Confirm password</label>
      <input id="confirm" type="password" [formField]="registerForm.confirmPassword" />
      @for (error of registerForm.confirmPassword().errors(); track error.kind) {
        <p class="text-error" role="alert">{{ error.message }}</p>
      }

      <label><input type="checkbox" [formField]="registerForm.acceptTerms" /> I accept the terms</label>

      <button type="submit" class="btn btn-primary" [disabled]="registerForm().submitting()">
        Create account
      </button>
    </form>
  `,
})
export class RegisterForm {
  private readonly api = inject(RegistrationApi);

  readonly model = signal<Registration>({ email: '', password: '', confirmPassword: '', acceptTerms: false });

  readonly registerForm = form(this.model, (path) => {
    required(path.email, { message: 'Email is required' });
    email(path.email, { message: 'Enter a valid email address' });
    required(path.password, { message: 'Password is required' });
    minLength(path.password, 12, { message: 'Use at least 12 characters' });
    // Cross-field rule: read a sibling with valueOf().
    validate(path.confirmPassword, ({ value, valueOf }) =>
      value() === valueOf(path.password) ? undefined : { kind: 'mismatch', message: 'Passwords do not match' },
    );
    // Conditional state: confirm is disabled until a password is typed.
    disabled(path.confirmPassword, ({ valueOf }) => valueOf(path.password) === '');
    validate(path.acceptTerms, ({ value }) =>
      value() ? undefined : { kind: 'terms', message: 'You must accept the terms' },
    );
  });

  async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    // submit() marks every field touched, runs the action only when valid, drives submitting(),
    // and attaches returned errors to the named field.
    await submit(this.registerForm, async (f) => {
      const outcome = await this.api.register(f().value());
      return outcome === 'email-taken'
        ? { fieldTree: f.email, kind: 'server', message: 'This email is already registered' }
        : undefined;
    });
  }
}
```

Notes:
- The model signal is the single source of truth: `model.set(...)` updates the form and typing
  updates the model. Do not mirror it into other signals with `effect()`.
- Network or 5xx failures inside the action must still surface: let them throw to the page's
  error handling (see `../../angular-ui-patterns/reference/error-handling.md`), and log via the
  central `Logger`. Only map **expected** business rejections (taken email) to field errors.
- Server validation stays authoritative; client rules are UX.

## Testing (Vitest, zoneless TestBed)

```typescript
import { TestBed } from '@angular/core/testing';
import { RegisterForm } from './register-form';
import { RegistrationApi, type RegisterOutcome } from './registration-api';

describe('RegisterForm', () => {
  const register = vi.fn<(body: { email: string; password: string }) => Promise<RegisterOutcome>>();

  beforeEach(() => {
    register.mockReset();
    TestBed.configureTestingModule({ providers: [{ provide: RegistrationApi, useValue: { register } }] });
  });

  function fill(cmp: RegisterForm, confirm = 'correct horse battery'): void {
    cmp.model.set({ email: 'ada@example.test', password: 'correct horse battery', confirmPassword: confirm, acceptTerms: true });
  }

  it('blocks submit and touches fields while invalid', async () => {
    const cmp = TestBed.createComponent(RegisterForm).componentInstance;
    fill(cmp, 'different');
    await cmp.onSubmit(new Event('submit'));
    expect(register).not.toHaveBeenCalled();
    expect(cmp.registerForm.confirmPassword().errors().map((e) => e.kind)).toEqual(['mismatch']);
    expect(cmp.registerForm.email().touched()).toBe(true);
  });

  it('maps a server rejection onto the email field', async () => {
    register.mockResolvedValue('email-taken');
    const fixture = TestBed.createComponent(RegisterForm);
    fill(fixture.componentInstance);
    await fixture.componentInstance.onSubmit(new Event('submit'));
    expect(fixture.componentInstance.registerForm.email().errors().map((e) => e.kind)).toEqual(['server']);
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('This email is already registered');
  });
});
```

Runner, harness and timer rules: `../../angular-spa/reference/testing-vitest.md`.
