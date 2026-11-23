# Angular UI Form Components

Reusable Angular 21+ form components using daisyUI 5.5.5 + TailwindCSS 4.x.
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
| Credit card | Composite: number + expiry + CVV | `join` wrapper with `input` |
| Search | `input[type=search]` | `input` with search icon |
| Range / slider | `input[type=range]` | `range range-primary` |
| Color | `input[type=color]` | Native color picker |

**Decision rules:**

- Never use `select` for boolean — use `checkbox` or `toggle` (clearer cognitive model)
- Never use `input[type=number]` for phone numbers — use `input[type=tel]` to preserve leading zeros
- Never use `textarea` for structured data that belongs in separate fields
- Prefer radio groups over selects when the option count is ≤7 and screen space allows (all options visible at a glance reduces errors)

---

## Section B: Validation Timing Strategy

**Recommended: On Blur with Progressive Enhancement**

```
Field pristine (never touched):  No validation shown
User typing (dirty, not blurred): No errors shown
On blur (field loses focus):      Validate and show errors immediately
After first error shown:          Switch to onChange for that field only
On fix:                           Show success state immediately
```

This prevents "angry forms" (showing errors before the user finishes typing) while ensuring fast feedback once the user has left a field.

### Five Modes with Angular Reactive Forms Mapping

| Mode | When to Use | Angular Config |
|------|-------------|----------------|
| **On Submit** | Low-friction short forms (login, search) | `fb.group({...}, { updateOn: 'submit' })` |
| **On Blur** | Standard data-entry forms (recommended default) | `fb.group({...}, { updateOn: 'blur' })` |
| **On Change** | Real-time constraint enforcement (password strength) | `fb.group({...}, { updateOn: 'change' })` |
| **Debounced** | Async validation (username availability check) | `updateOn: 'change'` + `debounceTime(300)` on `valueChanges` |
| **Progressive** | Complex long forms where UX research matters | Start with blur; add `.valueChanges` listener after first error per field |

### Progressive Enhancement Implementation

```typescript
// After the form group is touched (first submit attempt):
// switch individual fields to live validation
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

| ❌ Vague (forbidden) | ✅ Actionable (required) |
|---------------------|--------------------------|
| "Invalid input" | "Email must include @ symbol (e.g., name@example.com)" |
| "Error" | "Password must be at least 8 characters long" |
| "Field required" | "Please enter your email so we can send your order confirmation" |
| "Too long" | "Message must be 500 characters or fewer (currently 523)" |
| "Invalid date" | "Date must be today or in the future (format: DD/MM/YYYY)" |
| "Passwords don't match" | "Passwords must match — please re-enter your new password" |

**Rules:**
- Always name the field in the message if not rendered directly beneath it
- Always include the constraint value: "at least 8" not "too short"
- For async errors (server-side): show the exact rejection reason if safe to expose, else "This [thing] is already in use — try a different one"
- Never blame the user: "You entered an invalid…" → "This email address doesn't look right…"

---

## Section D: Multi-Step Wizard Pattern

Angular 21 signals-based wizard. Each step is a standalone component; the wizard orchestrates navigation and validates step-by-step.

```typescript
import {
  Component, ChangeDetectionStrategy, signal, computed, inject
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

// Step 1 component
@Component({
  selector: 'app-wizard-step-personal',
  imports: [ReactiveFormsModule],
  template: `
    <div class="space-y-4">
      <h3 class="text-lg font-semibold">Personal Information</h3>
      <div [formGroup]="form" class="space-y-4">
        <div class="fieldset">
          <label class="label" for="firstName">
            <span>First Name <span class="text-error" aria-hidden="true">*</span></span>
          </label>
          <input id="firstName" type="text" formControlName="firstName"
            class="input"
            [class.input-error]="hasError('firstName')"
            [attr.aria-invalid]="hasError('firstName')"
            [attr.aria-describedby]="hasError('firstName') ? 'firstName-error' : null"
            aria-required="true" />
          @if (hasError('firstName')) {
            <label class="label">
              <span id="firstName-error" class="label text-error" role="alert">
                {{ getError('firstName') }}
              </span>
            </label>
          }
        </div>
        <div class="fieldset">
          <label class="label" for="lastName">
            <span>Last Name <span class="text-error" aria-hidden="true">*</span></span>
          </label>
          <input id="lastName" type="text" formControlName="lastName"
            class="input"
            [class.input-error]="hasError('lastName')"
            [attr.aria-invalid]="hasError('lastName')"
            [attr.aria-describedby]="hasError('lastName') ? 'lastName-error' : null"
            aria-required="true" />
          @if (hasError('lastName')) {
            <label class="label">
              <span id="lastName-error" class="label text-error" role="alert">
                {{ getError('lastName') }}
              </span>
            </label>
          }
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class WizardStepPersonalComponent {
  private readonly fb = inject(FormBuilder);

  readonly form = this.fb.nonNullable.group({
    firstName: ['', [Validators.required, Validators.minLength(2)]],
    lastName: ['', [Validators.required, Validators.minLength(2)]]
  });

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }

  getError(field: string): string | null {
    const c = this.form.get(field);
    if (!c?.invalid || !c?.touched) return null;
    if (c.errors?.['required']) return `${field === 'firstName' ? 'First name' : 'Last name'} is required`;
    if (c.errors?.['minlength']) return `Must be at least ${c.errors['minlength'].requiredLength} characters`;
    return null;
  }
}

// Step 2 component (contact)
@Component({
  selector: 'app-wizard-step-contact',
  imports: [ReactiveFormsModule],
  template: `
    <div class="space-y-4">
      <h3 class="text-lg font-semibold">Contact Details</h3>
      <div [formGroup]="form">
        <div class="fieldset">
          <label class="label" for="email">
            <span>Email <span class="text-error" aria-hidden="true">*</span></span>
          </label>
          <input id="email" type="email" formControlName="email"
            class="input"
            [class.input-error]="hasError('email')"
            [attr.aria-invalid]="hasError('email')"
            [attr.aria-describedby]="hasError('email') ? 'email-error' : null"
            aria-required="true" />
          @if (hasError('email')) {
            <label class="label">
              <span id="email-error" class="label text-error" role="alert">
                {{ getError('email') }}
              </span>
            </label>
          }
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class WizardStepContactComponent {
  private readonly fb = inject(FormBuilder);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]]
  });

  hasError(field: string): boolean {
    const c = this.form.get(field);
    return !!(c?.invalid && c?.touched);
  }

  getError(field: string): string | null {
    const c = this.form.get(field);
    if (!c?.invalid || !c?.touched) return null;
    if (c.errors?.['required']) return 'Email is required so we can confirm your submission';
    if (c.errors?.['email']) return 'Email must include @ symbol (e.g., name@example.com)';
    return null;
  }
}

// Step 3 — Review (read-only summary, no form)
@Component({
  selector: 'app-wizard-step-review',
  template: `
    <div class="space-y-4">
      <h3 class="text-lg font-semibold">Review Your Information</h3>
      <div class="bg-base-200 rounded-box p-4 space-y-2">
        @for (entry of summaryEntries(); track entry.label) {
          <div class="flex justify-between">
            <span class="text-base-content/60">{{ entry.label }}</span>
            <span class="font-medium">{{ entry.value }}</span>
          </div>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class WizardStepReviewComponent {
  summaryEntries = input<{ label: string; value: string }[]>([]);
}

// Wizard orchestrator
@Component({
  selector: 'app-multi-step-wizard',
  imports: [
    WizardStepPersonalComponent,
    WizardStepContactComponent,
    WizardStepReviewComponent
  ],
  template: `
    <div class="card bg-base-100 shadow-xl max-w-2xl mx-auto">
      <div class="card-body space-y-6">

        <!-- daisyUI steps progress bar -->
        <ul class="steps steps-horizontal w-full">
          @for (step of steps(); track $index) {
            <li class="step"
              [class.step-primary]="$index <= currentStep()"
              [attr.data-content]="$index < currentStep() ? '✓' : $index + 1">
              {{ step }}
            </li>
          }
        </ul>

        <!-- Step content -->
        @switch (currentStep()) {
          @case (0) { <app-wizard-step-personal #step0 /> }
          @case (1) { <app-wizard-step-contact #step1 /> }
          @case (2) {
            <app-wizard-step-review [summaryEntries]="summaryData()" />
          }
        }

        <!-- Navigation controls -->
        <div class="flex justify-between pt-4">
          <button type="button" class="btn btn-ghost"
            [class.btn-disabled]="!canGoBack()"
            [attr.aria-disabled]="!canGoBack()"
            (click)="goBack()">
            Back
          </button>

          @if (canSubmit()) {
            <button type="button" class="btn btn-primary"
              [disabled]="submitting()"
              (click)="submit()">
              @if (submitting()) { <span class="loading loading-spinner loading-sm"></span> }
              Submit
            </button>
          } @else {
            <button type="button" class="btn btn-primary"
              (click)="goNext()">
              Next
            </button>
          }
        </div>

      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class MultiStepWizardComponent {
  // ---- State signals ----
  protected readonly currentStep = signal(0);
  protected readonly steps = signal(['Personal Info', 'Contact', 'Review']);
  protected readonly submitting = signal(false);

  // ---- Derived signals ----
  protected readonly progress = computed(
    () => ((this.currentStep() + 1) / this.steps().length) * 100
  );
  protected readonly canGoBack = computed(() => this.currentStep() > 0);
  protected readonly canSubmit = computed(
    () => this.currentStep() === this.steps().length - 1
  );

  // Collect form values from child step components via ViewChild in real usage.
  // Shown here as a plain signal for illustration.
  protected readonly summaryData = computed<{ label: string; value: string }[]>(
    () => [
      { label: 'First Name', value: '—' },
      { label: 'Last Name', value: '—' },
      { label: 'Email', value: '—' }
    ]
  );

  protected goNext(): void {
    // In practice: validate the current step's FormGroup before advancing.
    // e.g., if (this.stepRef.form.invalid) { this.stepRef.form.markAllAsTouched(); return; }
    if (this.currentStep() < this.steps().length - 1) {
      this.currentStep.update(s => s + 1);
    }
  }

  protected goBack(): void {
    if (this.canGoBack()) this.currentStep.update(s => s - 1);
  }

  protected async submit(): Promise<void> {
    this.submitting.set(true);
    try {
      // API call here — collect values from child step forms
    } finally {
      this.submitting.set(false);
    }
  }
}
```

**Accessing child step form values:** Use `@ViewChild(WizardStepPersonalComponent)` and read `.form.getRawValue()` before advancing. Store collected values in a parent signal and pass to the Review step as `summaryEntries`.

---

## Section E: Accessibility Requirements

Every form element must satisfy all of the following:

| Requirement | Implementation |
|-------------|---------------|
| Every `<input>` / `<textarea>` / `<select>` has a visible label | `<label [for]="id">` or `aria-label` on the element |
| Required fields are announced to screen readers | `aria-required="true"` on the input; visual asterisk with `aria-hidden="true"` |
| Error state is communicated to screen readers | `aria-invalid="true"` on the input when invalid and touched |
| Error messages are linked to their input | `aria-describedby="field-error-id"` on input; `id="field-error-id"` on error `<span>` |
| Error messages are announced immediately | `role="alert"` on the error `<span>` (live region) |
| Focus lands on the first error after failed submit | See focus management pattern below |
| Keyboard-only navigation works end-to-end | Tab order follows visual order; no focus traps except modals |
| Color is not the only indicator of error state | Use `input-error` class (border change) AND error message text, never color alone |

### Focus Management After Failed Submit

```typescript
// In your form component, inject ElementRef or use ViewChildren
import { ElementRef, inject, viewChildren } from '@angular/core';

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
  // proceed
}
```

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

---

## Section F: File Upload with Progress Tracking

Two patterns depending on file destination:

| Pattern | When to Use |
|---------|-------------|
| **Direct multipart POST** | Files ≤ 10 MB, backend stores or processes the file |
| **GCS presigned URL** | Files > 10 MB, or you want to bypass server bandwidth — backend issues URL, client uploads directly to GCS |

See `docs/workflows/file-uploads.md` for backend presigned URL endpoint implementations (NestJS, FastAPI, Spring Boot).

---

### Pattern 1 — Direct Multipart POST with Progress

```typescript
import {
  Component, ChangeDetectionStrategy, signal, computed, inject
} from '@angular/core';
import { HttpClient, HttpEventType, HttpErrorResponse } from '@angular/common/http';

type UploadState = 'idle' | 'uploading' | 'done' | 'error';

// Allowed MIME types — validate client-side AND server-side
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

@Component({
  selector: 'app-file-upload',
  template: `
    <div class="fieldset w-full space-y-3">
      <label class="label" for="file-input">
        <span class="font-medium">Upload File</span>
        <span class="label text-base-content/60">JPEG, PNG, WebP, PDF — max 10 MB</span>
      </label>

      <!-- File picker -->
      <input
        id="file-input"
        type="file"
        accept=".jpg,.jpeg,.png,.webp,.pdf"
        class="file-input w-full"
        [class.file-input-error]="state() === 'error'"
        [disabled]="state() === 'uploading'"
        (change)="onFileSelected($event)"
        aria-describedby="upload-status"
      />

      <!-- Validation error -->
      @if (validationError()) {
        <p class="text-error text-sm" role="alert">{{ validationError() }}</p>
      }

      <!-- Progress bar (uploading state) -->
      @if (state() === 'uploading') {
        <div aria-live="polite" aria-label="Upload progress">
          <div class="flex justify-between text-sm mb-1">
            <span>Uploading…</span>
            <span>{{ progress() }}%</span>
          </div>
          <progress
            class="progress progress-primary w-full"
            [value]="progress()"
            max="100"
            [attr.aria-valuenow]="progress()"
            aria-valuemin="0"
            aria-valuemax="100">
          </progress>
        </div>
      }

      <!-- Success state -->
      @if (state() === 'done') {
        <div class="alert alert-success" role="status" aria-live="polite">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
          </svg>
          <span>Upload complete — {{ uploadedUrl() }}</span>
        </div>
      }

      <!-- Error state -->
      @if (state() === 'error') {
        <div class="alert alert-error" role="alert">
          <span>{{ uploadError() }} — please try again.</span>
        </div>
      }

      <!-- Upload button -->
      <button
        type="button"
        class="btn btn-primary w-full"
        [disabled]="!canUpload()"
        (click)="upload()"
        [attr.aria-busy]="state() === 'uploading'">
        @if (state() === 'uploading') {
          <span class="loading loading-spinner loading-sm" aria-hidden="true"></span>
          Uploading…
        } @else {
          Upload
        }
      </button>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class FileUploadComponent {
  private readonly http = inject(HttpClient);

  protected readonly state = signal<UploadState>('idle');
  protected readonly progress = signal(0);
  protected readonly validationError = signal<string | null>(null);
  protected readonly uploadError = signal<string | null>(null);
  protected readonly uploadedUrl = signal<string | null>(null);

  private selectedFile = signal<File | null>(null);

  protected readonly canUpload = computed(
    () => this.selectedFile() !== null && this.state() !== 'uploading'
  );

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;

    this.validationError.set(null);
    this.state.set('idle');
    this.selectedFile.set(null);

    if (!file) return;

    // Client-side validation — server MUST also validate (defense in depth)
    if (!ALLOWED_TYPES.includes(file.type)) {
      this.validationError.set(
        `File type not allowed. Accepted: JPEG, PNG, WebP, PDF. Got: ${file.type || 'unknown'}`
      );
      return;
    }

    if (file.size > MAX_SIZE_BYTES) {
      this.validationError.set(
        `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum is 10 MB.`
      );
      return;
    }

    this.selectedFile.set(file);
  }

  protected upload(): void {
    const file = this.selectedFile();
    if (!file) return;

    const form = new FormData();
    form.append('file', file, file.name);

    this.state.set('uploading');
    this.progress.set(0);

    this.http.post<{ url: string }>('/api/upload', form, {
      reportProgress: true,
      observe: 'events'
    }).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress && event.total) {
          this.progress.set(Math.round(100 * event.loaded / event.total));
        } else if (event.type === HttpEventType.Response) {
          this.uploadedUrl.set(event.body?.url ?? null);
          this.state.set('done');
        }
      },
      error: (err: HttpErrorResponse) => {
        this.uploadError.set(err.error?.message ?? 'Upload failed');
        this.state.set('error');
      }
    });
  }
}
```

---

### Pattern 2 — GCS Presigned URL Upload (large files, bypass server bandwidth)

```
Flow:
1. Client requests presigned URL from your backend  POST /api/upload/presigned-url
2. Backend generates GCS signed URL with 15-min expiry, returns { uploadUrl, objectKey }
3. Client PUTs file directly to GCS using uploadUrl  (no backend bandwidth used)
4. Client notifies backend of completion             POST /api/upload/confirm
```

```typescript
import {
  Component, ChangeDetectionStrategy, signal, computed, inject
} from '@angular/core';
import { HttpClient, HttpEventType, HttpErrorResponse, HttpRequest } from '@angular/common/http';

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4'];
const MAX_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB

interface PresignedUrlResponse {
  uploadUrl: string;   // GCS signed URL — PUT directly to this
  objectKey: string;   // GCS object path — send back on confirm
  expiresAt: string;   // ISO timestamp — warn user if upload stalls
}

@Component({
  selector: 'app-gcs-upload',
  template: `
    <div class="space-y-4">
      <input
        type="file"
        accept=".jpg,.jpeg,.png,.webp,.mp4"
        class="file-input w-full"
        [disabled]="state() === 'uploading'"
        (change)="onFileSelected($event)"
      />

      @if (validationError()) {
        <p class="text-error text-sm" role="alert">{{ validationError() }}</p>
      }

      @if (state() === 'uploading') {
        <div aria-live="polite">
          <div class="flex justify-between text-sm mb-1">
            <span>{{ statusLabel() }}</span>
            <span>{{ progress() }}%</span>
          </div>
          <progress class="progress progress-primary w-full"
            [value]="progress()" max="100"></progress>
        </div>
      }

      @if (state() === 'done') {
        <div class="alert alert-success" role="status">File uploaded successfully.</div>
      }

      @if (state() === 'error') {
        <div class="alert alert-error" role="alert">{{ uploadError() }}</div>
      }

      <button type="button" class="btn btn-primary w-full"
        [disabled]="!canUpload()"
        (click)="uploadViaPresignedUrl()">
        @if (state() === 'uploading') {
          <span class="loading loading-spinner loading-sm"></span>
        }
        Upload
      </button>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class GcsUploadComponent {
  private readonly http = inject(HttpClient);

  protected readonly state = signal<'idle' | 'requesting' | 'uploading' | 'confirming' | 'done' | 'error'>('idle');
  protected readonly progress = signal(0);
  protected readonly validationError = signal<string | null>(null);
  protected readonly uploadError = signal<string | null>(null);
  private selectedFile = signal<File | null>(null);

  protected readonly canUpload = computed(
    () => this.selectedFile() !== null && !['uploading', 'requesting', 'confirming'].includes(this.state())
  );

  protected readonly statusLabel = computed(() => {
    switch (this.state()) {
      case 'requesting': return 'Requesting upload URL…';
      case 'uploading':  return 'Uploading to storage…';
      case 'confirming': return 'Confirming…';
      default: return '';
    }
  });

  protected onFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.validationError.set(null);
    this.selectedFile.set(null);
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      this.validationError.set(`File type not allowed: ${file.type}`);
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      this.validationError.set(`File exceeds 500 MB limit.`);
      return;
    }
    this.selectedFile.set(file);
  }

  protected uploadViaPresignedUrl(): void {
    const file = this.selectedFile();
    if (!file) return;

    this.state.set('requesting');
    this.progress.set(0);

    // Step 1: request presigned URL from your backend
    this.http.post<PresignedUrlResponse>('/api/upload/presigned-url', {
      filename: file.name,
      contentType: file.type,
      size: file.size
    }).subscribe({
      next: ({ uploadUrl, objectKey }) => {
        this.state.set('uploading');
        // Step 2: PUT directly to GCS — no backend bandwidth used
        const req = new HttpRequest('PUT', uploadUrl, file, {
          headers: { 'Content-Type': file.type },
          reportProgress: true
        });
        this.http.request(req).subscribe({
          next: (event) => {
            if (event.type === HttpEventType.UploadProgress && event.total) {
              this.progress.set(Math.round(100 * event.loaded / event.total));
            } else if (event.type === HttpEventType.Response) {
              // Step 3: notify backend of completion
              this.state.set('confirming');
              this.http.post('/api/upload/confirm', { objectKey }).subscribe({
                next: () => this.state.set('done'),
                error: (err: HttpErrorResponse) => {
                  this.uploadError.set('Upload succeeded but confirmation failed — contact support.');
                  this.state.set('error');
                }
              });
            }
          },
          error: (err: HttpErrorResponse) => {
            this.uploadError.set('Upload to storage failed. Please try again.');
            this.state.set('error');
          }
        });
      },
      error: (err: HttpErrorResponse) => {
        this.uploadError.set(err.error?.message ?? 'Could not get upload URL.');
        this.state.set('error');
      }
    });
  }
}
```

**Key rules:**
- `reportProgress: true` + `observe: 'events'` on the `HttpRequest` enables `HttpEventType.UploadProgress`
- For GCS PUT: set `Content-Type` header to match what was used when generating the signed URL — mismatch causes 403
- Client-side type/size validation is UX only — the backend endpoint MUST also validate both before issuing a presigned URL
- Never log or store the presigned URL — it is a credential valid for 15 minutes

---

## Component Templates

---

## Form Field Component

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

## Form with Validation

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
          class="input w-full" [class.input-error]="hasError('name')" />
      </app-form-field>

      <app-form-field label="Email" [required]="true" [errorMessage]="getError('email')">
        <input type="email" formControlName="email"
          class="input w-full" [class.input-error]="hasError('email')" />
      </app-form-field>

      <app-form-field label="Message" [required]="true" [errorMessage]="getError('message')" labelAlt="Max 500 chars">
        <textarea formControlName="message"
          class="textarea w-full h-32" [class.textarea-error]="hasError('message')"></textarea>
      </app-form-field>

      <div class="flex justify-end gap-2 pt-4">
        <button type="button" class="btn btn-ghost" (click)="form.reset()">Clear</button>
        <button type="submit" class="btn btn-primary" [disabled]="!form.valid || submitting()">
          @if (submitting()) { <span class="loading loading-spinner loading-sm"></span> }
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
