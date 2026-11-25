# Angular Forms Validation

Angular 22+ validation patterns, error messages, and accessibility for forms using daisyUI 5.8.2 + Tailwind CSS 4.3.5.

---

## Section B: Validation Timing Strategy

**Recommended: On Blur with Progressive Enhancement**

```
Field pristine (never touched):   No validation shown
User typing (dirty, not blurred): No errors shown
On blur (field loses focus):      Validate and show errors immediately
After first error shown:          Switch to onChange for that field only
On fix:                           Show success state immediately
```

This prevents "angry forms" (errors before user finishes typing) while ensuring fast feedback.

### Five Modes with Angular Reactive Forms Mapping

| Mode | When to Use | Angular Config |
|------|-------------|----------------|
| **On Submit** | Low-friction short forms (login, search) | `fb.group({...}, { updateOn: 'submit' })` |
| **On Blur** | Standard data-entry forms (recommended default) | `fb.group({...}, { updateOn: 'blur' })` |
| **On Change** | Real-time constraint enforcement (password strength) | `fb.group({...}, { updateOn: 'change' })` |
| **Debounced** | Async validation (username availability check) | `updateOn: 'change'` + `debounceTime(300)` on `valueChanges` |
| **Progressive** | Complex long forms | Start with blur; add `.valueChanges` listener after first error per field |

### Progressive Enhancement Implementation

```typescript
setupProgressiveValidation(): void {
  Object.keys(this.form.controls).forEach(key => {
    const ctrl = this.form.get(key)!;
    ctrl.valueChanges.subscribe(() => {
      if (ctrl.touched) ctrl.updateValueAndValidity();
    });
  });
}
```

---

## Section C: Error Message Best Practice

**Formula: What's wrong + Why it matters + How to fix**

| Vague (forbidden) | Actionable (required) |
|------------------|-----------------------|
| "Invalid input" | "Email must include @ symbol (e.g., name@example.com)" |
| "Error" | "Password must be at least 8 characters long" |
| "Field required" | "Please enter your email so we can send your order confirmation" |
| "Too long" | "Message must be 500 characters or fewer (currently 523)" |
| "Invalid date" | "Date must be today or in the future (format: DD/MM/YYYY)" |
| "Passwords don't match" | "Passwords must match — please re-enter your new password" |

**Rules:**
- Always name the field in the message if not rendered directly beneath it
- Always include the constraint value: "at least 8" not "too short"
- For async errors (server-side): show the exact rejection reason if safe, else "This [thing] is already in use — try a different one"
- Never blame the user: "You entered an invalid…" → "This email address doesn't look right…"

---

## Section E: Accessibility Requirements

Every form element must satisfy all of the following:

| Requirement | Implementation |
|-------------|---------------|
| Every input/textarea/select has a visible label | `<label [for]="id">` or `aria-label` on the element |
| Required fields announced to screen readers | `aria-required="true"` on input; visual asterisk with `aria-hidden="true"` |
| Error state communicated to screen readers | `aria-invalid="true"` on input when invalid and touched |
| Error messages linked to their input | `aria-describedby="field-error-id"` on input; `id="field-error-id"` on error `<span>` |
| Error messages announced immediately | `role="alert"` on the error `<span>` (live region) |
| Focus lands on first error after failed submit | See focus management pattern below |
| Keyboard-only navigation works end-to-end | Tab order follows visual order; no focus traps except modals |
| Color is not the only error indicator | Use `input-error` class (border) AND error message text, never color alone |

### Error Announcement Template Pattern

```html
<!-- Always pair aria-invalid + aria-describedby on the input -->
<input
  type="email"
  formControlName="email"
  [attr.aria-invalid]="hasError('email')"
  [attr.aria-describedby]="hasError('email') ? 'email-error' : null"
  aria-required="true"
  class="input" />

<!-- role="alert" triggers immediate screen reader announcement -->
@if (hasError('email')) {
  <span id="email-error" class="label text-error" role="alert">
    Email must include @ symbol (e.g., name@example.com)
  </span>
}
```

### Focus Management After Failed Submit

```typescript
import { ElementRef, inject } from '@angular/core';

export class MyFormComponent {
  private readonly elementRef = inject(ElementRef);

  protected onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      // Focus the first invalid field after change detection runs
      setTimeout(() => {
        const firstInvalidKey = Object.keys(this.form.controls)
          .find(key => this.form.get(key)?.invalid);
        if (firstInvalidKey) {
          const el = this.elementRef.nativeElement
            .querySelector(`[formControlName="${firstInvalidKey}"]`);
          el?.focus();
        }
      }, 0);
      return;
    }
    // proceed with submission
  }
}
```

---

## Async Validator Pattern

Use for server-side uniqueness checks (username, email).

```typescript
// src/app/shared/validators/unique-email.validator.ts
import { AbstractControl, AsyncValidatorFn, ValidationErrors } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, of } from 'rxjs';
import { Logger } from '../../core/logging/logger';
import { map, catchError, debounceTime, switchMap, first } from 'rxjs/operators';

export function uniqueEmailValidator(): AsyncValidatorFn {
  const http = inject(HttpClient);
  const logger = inject(Logger);

  return (control: AbstractControl): Observable<ValidationErrors | null> => {
    if (!control.value) return of(null);

    return of(control.value).pipe(
      debounceTime(300),
      switchMap(value =>
        http.get<{ available: boolean }>(`/api/check-email?email=${encodeURIComponent(value)}`).pipe(
          map(res => res.available ? null : { emailTaken: true }),
          // The check itself failed: log it and return a distinct error instead of reporting the address as
          // available. The control stays invalid (submit blocked) until a retry succeeds; the server still
          // enforces uniqueness on submit.
          catchError((error: unknown) => {
            logger.error('uniqueEmailValidator: availability check failed', { error });
            return of({ emailCheckUnavailable: true });
          })
        )
      ),
      first()
    );
  };
}

// Usage in FormBuilder
// email: ['', [Validators.required, Validators.email], [uniqueEmailValidator()]]
```

**Error message for async validator:**
```typescript
if (c.errors?.['emailTaken']) return 'This email is already registered — try signing in instead';
if (c.errors?.['emailCheckUnavailable']) return 'We could not check this email right now. Try again in a moment.';
```

---

## Custom Sync Validator Pattern

```typescript
import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export function passwordMatchValidator(): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const password = group.get('password')?.value;
    const confirm = group.get('confirmPassword')?.value;
    if (!password || !confirm) return null;
    return password === confirm ? null : { passwordMismatch: true };
  };
}

// Usage: fb.group({ password: [...], confirmPassword: [...] }, { validators: [passwordMatchValidator()] })
// Error message: 'Passwords must match — please re-enter your new password'
```
