# Angular Form Fields

Angular 21+ form field components using daisyUI 5.5.5 + TailwindCSS 4.x.
All components use standalone, OnPush, and signal-based APIs.

---

## Section A: Component Selection Framework

**The Golden Rule: Data Type → Input Component → Validation Pattern**

| Data Type | Component | daisyUI Class |
|-----------|-----------|---------------|
| Short text (<100 chars) | `input[type=text/email/password/url]` | `input` |
| Long text (>100 chars) | `textarea` | `textarea` |
| Numeric (integer/decimal) | `input[type=number]` | `input` |
| Currency | Composite: prefix `$` + `input[type=number]` | `input` with `join` wrapper |
| Date | `input[type=date]` | `input` |
| Time | `input[type=time]` | `input` |
| Boolean (single toggle) | `input[type=checkbox]` | `checkbox` or `toggle` |
| Single choice, 2–7 options | Radio group | `radio` inside `fieldset` |
| Single choice, 8–15 options | `select` | `select` |
| Single choice, >15 options | Autocomplete / combobox | `input` + dropdown |
| Multiple choice, ≤8 options | Checkbox group | `checkbox` per option |
| Multiple choice, >8 options | `select[multiple]` | `select h-auto` |
| File / media upload | `input[type=file]` | `file-input` |
| Structured (address, phone) | Composite inputs | Multiple `input` in grid |
| Search | `input[type=search]` | `input` with search icon |
| Range / slider | `input[type=range]` | `range range-primary` |

**Decision rules:**
- Never use `select` for boolean — use `checkbox` or `toggle`
- Never use `input[type=number]` for phone numbers — use `input[type=tel]` to preserve leading zeros
- Never use `textarea` for structured data that belongs in separate fields
- Prefer radio groups over selects when option count is ≤7 and screen space allows

---

## Form Field Wrapper Component

Reusable wrapper for label + input slot + error/hint display.

```typescript
import { Component, ChangeDetectionStrategy, input, computed } from '@angular/core';

@Component({
  selector: 'app-form-field',
  template: `
    <div class="fieldset w-full">
      <label class="label" [for]="inputId()">
        <span>
          {{ label() }}
          @if (required()) {
            <span class="text-error ml-1" aria-hidden="true">*</span>
          }
        </span>
        @if (labelAlt()) {
          <span class="label">{{ labelAlt() }}</span>
        }
      </label>
      <ng-content></ng-content>
      @if (errorMessage()) {
        <label class="label">
          <span class="label text-error" role="alert">{{ errorMessage() }}</span>
        </label>
      }
      @if (hint() && !errorMessage()) {
        <label class="label">
          <span class="label text-base-content/60">{{ hint() }}</span>
        </label>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class FormFieldComponent {
  label = input.required<string>();
  hint = input<string>('');
  labelAlt = input<string>('');
  required = input<boolean>(false);
  errorMessage = input<string | null>(null);

  protected readonly inputId = computed(() =>
    `field-${this.label().toLowerCase().replace(/\s+/g, '-')}-${Math.random().toString(36).slice(2, 9)}`
  );
}
```

---

## Contact Form with Validation

Complete form using `FormFieldComponent` and reactive forms.

```typescript
import {
  Component, ChangeDetectionStrategy, signal, inject
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { FormFieldComponent } from './form-field.component';

@Component({
  selector: 'app-contact-form',
  imports: [ReactiveFormsModule, FormFieldComponent],
  template: `
    <form [formGroup]="form" (ngSubmit)="onSubmit()" class="space-y-4">
      <app-form-field label="Full Name" [required]="true" [errorMessage]="getError('name')">
        <input type="text" formControlName="name"
          class="input w-full"
          [class.input-error]="hasError('name')"
          [attr.aria-invalid]="hasError('name')"
          aria-required="true" />
      </app-form-field>

      <app-form-field label="Email" [required]="true" [errorMessage]="getError('email')">
        <input type="email" formControlName="email"
          class="input w-full"
          [class.input-error]="hasError('email')"
          [attr.aria-invalid]="hasError('email')"
          aria-required="true" />
      </app-form-field>

      <app-form-field label="Message" [required]="true"
        [errorMessage]="getError('message')" labelAlt="Max 500 chars">
        <textarea formControlName="message"
          class="textarea w-full h-32"
          [class.textarea-error]="hasError('message')"
          [attr.aria-invalid]="hasError('message')"
          aria-required="true"></textarea>
      </app-form-field>

      <div class="flex justify-end gap-2 pt-4">
        <button type="button" class="btn btn-ghost" (click)="form.reset()">Clear</button>
        <button type="submit" class="btn btn-primary"
          [disabled]="!form.valid || submitting()">
          @if (submitting()) {
            <span class="loading loading-spinner loading-sm"></span>
          }
          Send
        </button>
      </div>
    </form>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ContactFormComponent {
  private readonly fb = inject(FormBuilder);
  protected readonly submitting = signal(false);

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    message: ['', [Validators.required, Validators.minLength(10), Validators.maxLength(500)]]
  });

  protected hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }

  protected getError(field: string): string | null {
    const c = this.form.get(field);
    if (!c?.invalid || !c?.touched) return null;
    if (c.errors?.['required']) return `${field.charAt(0).toUpperCase() + field.slice(1)} is required`;
    if (c.errors?.['email']) return 'Please enter a valid email';
    if (c.errors?.['minlength']) return `Minimum ${c.errors['minlength'].requiredLength} characters`;
    if (c.errors?.['maxlength']) return `Maximum ${c.errors['maxlength'].requiredLength} characters`;
    return 'Invalid value';
  }

  protected async onSubmit(): Promise<void> {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.submitting.set(true);
    try {
      // API call here
      this.form.reset();
    } finally {
      this.submitting.set(false);
    }
  }
}
```

---

## Checkbox and Radio Patterns

```html
<!-- Single checkbox -->
<div class="fieldset">
  <label class="label cursor-pointer gap-3">
    <input type="checkbox" formControlName="agreed" class="checkbox checkbox-primary" />
    <span>I agree to the terms and conditions</span>
  </label>
</div>

<!-- Radio group -->
<fieldset class="space-y-2">
  <legend class="font-medium">Preferred contact method</legend>
  @for (option of contactOptions; track option.value) {
    <div class="fieldset">
      <label class="label cursor-pointer gap-3 justify-start">
        <input type="radio" formControlName="contactMethod"
          [value]="option.value" class="radio radio-primary" />
        <span>{{ option.label }}</span>
      </label>
    </div>
  }
</fieldset>

<!-- Toggle -->
<div class="fieldset">
  <label class="label cursor-pointer gap-3">
    <span>Enable notifications</span>
    <input type="checkbox" formControlName="notifications" class="toggle toggle-primary" />
  </label>
</div>
```
