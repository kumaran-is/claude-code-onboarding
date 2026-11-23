# Angular UI Feedback & Utility Components

Reusable Angular 22+ feedback and utility components using daisyUI 5.8.2 + Tailwind CSS 4.3.5. All components use standalone, OnPush, and signal-based APIs.

## Toast Service & Component

```typescript
// toast.service.ts
import { Service, signal } from '@angular/core';

export type ToastType = 'info' | 'success' | 'warning' | 'error';
export interface Toast { id: string; type: ToastType; message: string; title?: string; }

@Service()
export class ToastService {
  private readonly _toasts = signal<Toast[]>([]);
  readonly toasts = this._toasts.asReadonly();

  show(type: ToastType, message: string, opts: { title?: string; duration?: number } = {}): string {
    const id = crypto.randomUUID();
    const duration = opts.duration ?? (type === 'error' ? 0 : 5000);
    this._toasts.update(t => [...t, { id, type, message, title: opts.title }]);
    if (duration > 0) setTimeout(() => this.dismiss(id), duration);
    return id;
  }

  dismiss(id: string): void { this._toasts.update(t => t.filter(x => x.id !== id)); }

  info(msg: string, title?: string) { return this.show('info', msg, { title }); }
  success(msg: string, title?: string) { return this.show('success', msg, { title }); }
  warning(msg: string, title?: string) { return this.show('warning', msg, { title }); }
  error(msg: string, title?: string) { return this.show('error', msg, { title, duration: 0 }); }
}

// toast-container.component.ts
import { Component, inject } from '@angular/core';
import { ToastService } from './toast.service';

@Component({
  selector: 'app-toast-container',
  template: `
    <div class="toast toast-end toast-bottom z-50">
      @for (toast of toastService.toasts(); track toast.id) {
        <div class="alert shadow-lg"
          [class.alert-info]="toast.type === 'info'"
          [class.alert-success]="toast.type === 'success'"
          [class.alert-warning]="toast.type === 'warning'"
          [class.alert-error]="toast.type === 'error'"
          role="alert" [attr.aria-live]="toast.type === 'error' ? 'assertive' : 'polite'">
          <div class="flex-1">
            @if (toast.title) { <h3 class="font-bold">{{ toast.title }}</h3> }
            <p class="text-sm">{{ toast.message }}</p>
          </div>
          <button type="button" class="btn btn-ghost btn-sm btn-circle"
            (click)="toastService.dismiss(toast.id)" aria-label="Dismiss">x</button>
        </div>
      }
    </div>
  `,
})
export class ToastContainerComponent {
  protected readonly toastService = inject(ToastService);
}
```

## Theme Toggle Component

```typescript
import { Component, signal, inject, PLATFORM_ID, afterNextRender } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

@Component({
  selector: 'app-theme-toggle',
  template: `
    <label class="swap swap-rotate">
      <input type="checkbox" class="theme-controller" value="dark"
        [checked]="isDark()" (change)="onToggle($event)" aria-label="Toggle dark mode" />
      <!-- sun icon svg class="swap-off h-8 w-8 fill-current" aria-hidden="true" -->
      <!-- moon icon svg class="swap-on h-8 w-8 fill-current" aria-hidden="true" -->
    </label>
  `,
})
export class ThemeToggleComponent {
  private readonly platformId = inject(PLATFORM_ID);
  protected readonly isDark = signal(false);

  constructor() {
    afterNextRender(() => {
      if (isPlatformBrowser(this.platformId)) {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.isDark.set(saved ? saved === 'dark' : prefersDark);
      }
    });
  }

  protected onToggle(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.isDark.set(checked);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem('theme', checked ? 'dark' : 'light');
    }
  }
}
```

## Theme Service

```typescript
import { Service, signal, computed, inject, PLATFORM_ID, effect } from '@angular/core';
import { DOCUMENT, isPlatformBrowser } from '@angular/common';

export const DAISY_THEMES = [
  { name: 'light', label: 'Light', isDark: false },
  { name: 'dark', label: 'Dark', isDark: true },
  { name: 'corporate', label: 'Corporate', isDark: false },
  { name: 'business', label: 'Business', isDark: true },
] as const;

export type ThemeName = typeof DAISY_THEMES[number]['name'];

@Service()
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);

  readonly themes = DAISY_THEMES;
  private readonly _current = signal<ThemeName>('light');
  readonly currentTheme = this._current.asReadonly();
  readonly isDarkMode = computed(() => this.themes.find(t => t.name === this._current())?.isDark ?? false);

  constructor() {
    if (isPlatformBrowser(this.platformId)) {
      const saved = localStorage.getItem('theme') as ThemeName;
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      this._current.set(saved && this.themes.some(t => t.name === saved) ? saved : prefersDark ? 'dark' : 'light');
    }
    effect(() => {
      const theme = this._current();
      const isDark = this.themes.find(t => t.name === theme)?.isDark ?? false;
      this.document.documentElement.setAttribute('data-theme', theme);
      this.document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';
    });
  }

  setTheme(theme: ThemeName): void {
    this._current.set(theme);
    if (isPlatformBrowser(this.platformId)) localStorage.setItem('theme', theme);
  }

  toggleDarkMode(): void {
    this.setTheme(this.isDarkMode() ? 'light' : 'dark');
  }
}
```

## Confirm Dialog Service & Component

```typescript
// confirm-dialog.service.ts
import { Service, signal, computed } from '@angular/core';

export interface ConfirmDialogOptions {
  title: string; message: string;
  confirmLabel?: string; cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
}

@Service()
export class ConfirmDialogService {
  private readonly _state = signal<{
    isOpen: boolean; title: string; message: string;
    confirmLabel: string; cancelLabel: string;
    variant: string; resolve: ((v: boolean) => void) | null;
  }>({ isOpen: false, title: '', message: '', confirmLabel: 'Confirm', cancelLabel: 'Cancel', variant: 'info', resolve: null });

  readonly state = this._state.asReadonly();
  readonly isOpen = computed(() => this._state().isOpen);

  confirm(opts: ConfirmDialogOptions): Promise<boolean> {
    return new Promise(resolve => {
      this._state.set({ isOpen: true, title: opts.title, message: opts.message,
        confirmLabel: opts.confirmLabel ?? 'Confirm', cancelLabel: opts.cancelLabel ?? 'Cancel',
        variant: opts.variant ?? 'info', resolve });
    });
  }

  handleConfirm(): void { this._state().resolve?.(true); this.close(); }
  handleCancel(): void { this._state().resolve?.(false); this.close(); }
  private close(): void { this._state.update(s => ({ ...s, isOpen: false, resolve: null })); }
}

// confirm-dialog.component.ts
import { Component, inject, effect, viewChild, ElementRef } from '@angular/core';
import { ConfirmDialogService } from './confirm-dialog.service';

@Component({
  selector: 'app-confirm-dialog',
  template: `
    <dialog #dialogEl class="modal" (close)="service.handleCancel()">
      <div class="modal-box">
        <h3 class="font-bold text-lg">{{ service.state().title }}</h3>
        <p class="py-4">{{ service.state().message }}</p>
        <div class="modal-action">
          <button type="button" class="btn btn-ghost" (click)="service.handleCancel()">
            {{ service.state().cancelLabel }}
          </button>
          <button type="button" class="btn"
            [class.btn-error]="service.state().variant === 'danger'"
            [class.btn-warning]="service.state().variant === 'warning'"
            [class.btn-info]="service.state().variant === 'info'"
            (click)="service.handleConfirm()">
            {{ service.state().confirmLabel }}
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop"><button>close</button></form>
    </dialog>
  `,
})
export class ConfirmDialogComponent {
  protected readonly service = inject(ConfirmDialogService);
  private readonly dialogEl = viewChild<ElementRef<HTMLDialogElement>>('dialogEl');

  constructor() {
    effect(() => {
      const dialog = this.dialogEl()?.nativeElement;
      if (!dialog) return;
      this.service.isOpen() ? dialog.showModal() : dialog.close();
    });
  }
}
```

## Error Boundary

```typescript
import { Component, input, signal, output } from '@angular/core';

@Component({
  selector: 'app-error-boundary',
  template: `
    @if (hasError()) {
      <div class="alert alert-error shadow-lg">
        <div class="flex-1">
          <h3 class="font-bold">{{ errorTitle() }}</h3>
          <p class="text-sm">{{ errorMessage() }}</p>
        </div>
        <button type="button" class="btn btn-sm btn-ghost" (click)="handleRetry()">Try Again</button>
      </div>
    } @else {
      <ng-content></ng-content>
    }
  `,
})
export class ErrorBoundaryComponent {
  errorTitle = input<string>('Something went wrong');
  protected readonly hasError = signal(false);
  protected readonly errorMessage = signal('');
  retryAction = output<void>();

  setError(message: string): void { this.hasError.set(true); this.errorMessage.set(message); }
  clearError(): void { this.hasError.set(false); this.errorMessage.set(''); }
  protected handleRetry(): void { this.clearError(); this.retryAction.emit(); }
}
```

## Infinite Scroll Directive

```typescript
import { Directive, ElementRef, inject, input, output, afterNextRender, OnDestroy } from '@angular/core';

@Directive({ selector: '[appInfiniteScroll]' })
export class InfiniteScrollDirective implements OnDestroy {
  private readonly el = inject(ElementRef);
  threshold = input<number>(100); disabled = input<boolean>(false); loadMore = output<void>();
  private observer?: IntersectionObserver; private sentinel?: HTMLElement;

  constructor() {
    afterNextRender(() => {
      this.sentinel = document.createElement('div');
      this.sentinel.style.height = '1px';
      this.sentinel.setAttribute('aria-hidden', 'true');
      this.el.nativeElement.appendChild(this.sentinel);
      this.observer = new IntersectionObserver(
        entries => { if (entries[0].isIntersecting && !this.disabled()) this.loadMore.emit(); },
        { rootMargin: `${this.threshold()}px`, threshold: 0 }
      );
      this.observer.observe(this.sentinel);
    });
  }

  ngOnDestroy(): void { this.observer?.disconnect(); this.sentinel?.remove(); }
}
```
