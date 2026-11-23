# Angular Forms Advanced Patterns

Multi-step forms, dynamic fields, form arrays, and file upload patterns.
Angular 21+ with daisyUI 5.5.5 + TailwindCSS 4.x. Standalone, OnPush, signal-based.

---

## Section D: Multi-Step Wizard Pattern

Signals-based wizard. Each step is a standalone component; the orchestrator manages navigation and per-step validation.

### Step Components

```typescript
import {
  Component, ChangeDetectionStrategy, inject, input
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

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
```

### Wizard Orchestrator

```typescript
import {
  Component, ChangeDetectionStrategy, signal, computed
} from '@angular/core';
import { WizardStepPersonalComponent } from './wizard-step-personal.component';

@Component({
  selector: 'app-multi-step-wizard',
  imports: [WizardStepPersonalComponent],
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
          @case (1) { <div>Step 2 content here</div> }
          @case (2) {
            <div class="bg-base-200 rounded-box p-4">
              Review summary here
            </div>
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
            <button type="button" class="btn btn-primary" (click)="goNext()">Next</button>
          }
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class MultiStepWizardComponent {
  protected readonly currentStep = signal(0);
  protected readonly steps = signal(['Personal Info', 'Contact', 'Review']);
  protected readonly submitting = signal(false);

  protected readonly canGoBack = computed(() => this.currentStep() > 0);
  protected readonly canSubmit = computed(
    () => this.currentStep() === this.steps().length - 1
  );

  protected goNext(): void {
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
      // Collect values from child step forms via @ViewChild, then API call
    } finally {
      this.submitting.set(false);
    }
  }
}
```

**Accessing child step form values:** Use `@ViewChild(WizardStepPersonalComponent)` and read `.form.getRawValue()` before advancing. Store in a parent signal and pass to the Review step.

---

## Section F: File Upload Patterns

| Pattern | When to Use |
|---------|-------------|
| **Direct multipart POST** | Files ≤ 10 MB, backend stores the file |
| **GCS presigned URL** | Files > 10 MB — backend issues URL, client uploads directly to GCS |

### Pattern 1 — Direct Multipart POST with Progress

```typescript
import {
  Component, ChangeDetectionStrategy, signal, computed, inject
} from '@angular/core';
import { HttpClient, HttpEventType, HttpErrorResponse } from '@angular/common/http';

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
      <input id="file-input" type="file"
        accept=".jpg,.jpeg,.png,.webp,.pdf"
        class="file-input w-full"
        [class.file-input-error]="state() === 'error'"
        [disabled]="state() === 'uploading'"
        (change)="onFileSelected($event)" />
      @if (validationError()) {
        <p class="text-error text-sm" role="alert">{{ validationError() }}</p>
      }
      @if (state() === 'uploading') {
        <div aria-live="polite">
          <div class="flex justify-between text-sm mb-1">
            <span>Uploading…</span><span>{{ progress() }}%</span>
          </div>
          <progress class="progress progress-primary w-full"
            [value]="progress()" max="100"></progress>
        </div>
      }
      @if (state() === 'done') {
        <div class="alert alert-success" role="status">Upload complete.</div>
      }
      @if (state() === 'error') {
        <div class="alert alert-error" role="alert">{{ uploadError() }} — please try again.</div>
      }
      <button type="button" class="btn btn-primary w-full"
        [disabled]="!canUpload()" (click)="upload()">
        @if (state() === 'uploading') {
          <span class="loading loading-spinner loading-sm"></span>
        }
        Upload
      </button>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class FileUploadComponent {
  private readonly http = inject(HttpClient);

  protected readonly state = signal<'idle' | 'uploading' | 'done' | 'error'>('idle');
  protected readonly progress = signal(0);
  protected readonly validationError = signal<string | null>(null);
  protected readonly uploadError = signal<string | null>(null);
  private selectedFile = signal<File | null>(null);

  protected readonly canUpload = computed(
    () => this.selectedFile() !== null && this.state() !== 'uploading'
  );

  protected onFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.validationError.set(null);
    this.state.set('idle');
    this.selectedFile.set(null);
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      this.validationError.set(`File type not allowed. Accepted: JPEG, PNG, WebP, PDF.`);
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
      reportProgress: true, observe: 'events'
    }).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress && event.total) {
          this.progress.set(Math.round(100 * event.loaded / event.total));
        } else if (event.type === HttpEventType.Response) {
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

**Key rules:**
- `reportProgress: true` + `observe: 'events'` enables `HttpEventType.UploadProgress`
- Client-side type/size validation is UX only — backend MUST also validate both
- For GCS presigned URL uploads: set `Content-Type` header to match what was used when generating the signed URL — mismatch causes 403
- Never log or store a presigned URL — it is a credential valid for 15 minutes
