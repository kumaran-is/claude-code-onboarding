# Angular UI List, Card, and Feed Patterns

Angular 22+ list, card, skeleton, and chat/agent UI components using daisyUI 5.8.2 + Tailwind CSS 4.3.5.
All components use standalone, OnPush, and signal-based APIs.

---

## Card Component

```typescript
import {
  Component, input, output
} from '@angular/core';

@Component({
  selector: 'app-example-card',
  template: `
    <article class="card bg-base-100 shadow-xl">
      <div class="card-body">
        <h2 class="card-title">{{ title() }}</h2>
        @if (loading()) {
          <div class="space-y-2">
            <div class="skeleton h-4 w-full"></div>
            <div class="skeleton h-4 w-3/4"></div>
          </div>
        } @else {
          <p class="text-base-content/70">{{ content() }}</p>
        }
        <div class="card-actions justify-end mt-4">
          <button type="button" class="btn btn-primary"
            [class.btn-disabled]="loading()"
            [attr.aria-busy]="loading()"
            (click)="handleAction()">
            @if (loading()) {
              <span class="loading loading-spinner loading-sm"></span>
            }
            {{ actionLabel() }}
          </button>
        </div>
      </div>
    </article>
  `,
})
export class ExampleCardComponent {
  title = input.required<string>();
  content = input<string>('');
  actionLabel = input<string>('Submit');
  loading = input<boolean>(false);
  action = output<void>();

  protected handleAction(): void {
    if (!this.loading()) this.action.emit();
  }
}
```

---

## Empty State Component

```typescript
import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  template: `
    <div class="hero min-h-[300px] bg-base-200 rounded-box">
      <div class="hero-content text-center">
        <div class="max-w-md">
          <div class="text-6xl mb-4" aria-hidden="true">{{ icon() }}</div>
          <h2 class="text-2xl font-bold">{{ title() }}</h2>
          <p class="py-4 text-base-content/60">{{ description() }}</p>
          @if (actionLabel()) {
            <button type="button" class="btn btn-primary" (click)="action.emit()">
              {{ actionLabel() }}
            </button>
          }
        </div>
      </div>
    </div>
  `,
})
export class EmptyStateComponent {
  icon = input<string>('');
  title = input.required<string>();
  description = input.required<string>();
  actionLabel = input<string>('');
  action = output<void>();
}
```

---

## Skeleton Loader

```typescript
import { Component, input } from '@angular/core';

@Component({
  selector: 'app-skeleton',
  template: `
    <div class="animate-pulse" role="status" aria-label="Loading content">
      @for (row of rowsArray(); track $index) {
        <div class="flex items-start gap-4 mb-4">
          @if (showAvatar()) {
            <div class="skeleton w-12 h-12 rounded-full shrink-0"></div>
          }
          <div class="flex-1 space-y-3">
            <div class="skeleton h-4 w-3/4"></div>
            <div class="skeleton h-4 w-1/2"></div>
          </div>
        </div>
      }
      <span class="sr-only">Loading...</span>
    </div>
  `,
})
export class SkeletonComponent {
  rows = input<number>(3);
  showAvatar = input<boolean>(true);
  protected rowsArray = () => Array.from({ length: this.rows() });
}
```

---

## Chat / Agent UI — Visual Quality Baseline

When building any chat or conversational agent UI, apply ALL of the following from the first scaffold.

### Layout Rules

- Outer container: `h-screen flex flex-col overflow-hidden` — never `min-h-screen`
- Header: `flex-shrink-0` — must not grow or shrink
- Message list: `flex-1 overflow-y-auto` — scrolls independently
- Input bar: `flex-shrink-0` at bottom — always visible, never scrolls away
- Empty state: center input bar vertically with `min-h-[55vh] flex flex-col items-center justify-center`

### Cards

- Use `card bg-base-100 shadow-sm border border-base-200` — not plain divs
- Card content: `card-body p-4` with `card-title text-sm font-semibold`
- Price / key stats: `text-lg font-bold text-neutral`
- Secondary text: `text-base-content/60 text-xs`

### Buttons

- Primary action: `btn btn-neutral rounded-xl` — not `btn btn-primary` (often invisible on dark themes)
- Text on dark buttons must be `text-neutral-content` — always verify contrast
- Disabled state: `[disabled]="loading()"` on all submit buttons

### Loading States

- Inline spinner in button: `<span class="loading loading-spinner loading-sm"></span>`
- Agent thinking indicator: `<span class="loading loading-dots loading-sm text-neutral"></span>`
- Never show a blank area while waiting — always show a loading indicator

### Auto-Scroll Pattern

```typescript
// Inject viewChild and use effect() to auto-scroll on new messages
import { viewChild, ElementRef, effect } from '@angular/core';

protected readonly messageContainer = viewChild<ElementRef>('messageContainer');

constructor() {
  effect(() => {
    this.messages(); // track signal
    setTimeout(() => {
      const el = this.messageContainer()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  });
}
```

### Smoke Test Before Reporting Done

- [ ] Header visible and not overlapping content
- [ ] Input bar always visible at bottom (even when messages overflow)
- [ ] Cards have visible borders/shadows — not flat invisible boxes
- [ ] Buttons have visible text (check contrast on dark background)
- [ ] Loading spinner appears when request is in-flight

---

## Layout Padding — Always Preserve on Refactor

When refactoring the outer container or changing flex/grid structure, verify padding is carried forward.

Checklist when changing `<div class="...">` on an outer container:
- [ ] `px-4` or `px-6` still present on content wrapper
- [ ] `max-w-4xl mx-auto` still applied to centre-constrain content
- [ ] Inner `<main>` and `<footer>` both have their own horizontal padding

Pattern that survives layout refactors:

```html
<!-- Outer: layout only, no padding -->
<div class="h-screen flex flex-col overflow-hidden">
  <!-- Inner: content width and padding -->
  <main class="flex-1 overflow-y-auto">
    <div class="max-w-4xl mx-auto px-4 py-8">
      <!-- content here -->
    </div>
  </main>
  <footer class="flex-shrink-0 px-4 py-4">
    <div class="max-w-4xl mx-auto">
      <!-- input bar here -->
    </div>
  </footer>
</div>
```

---

## Button Text Contrast — Always Verify

When using daisyUI semantic button classes, never assume text color is set automatically.

| Button class | Required text class |
|---|---|
| `btn btn-neutral` | `text-neutral-content` |
| `btn btn-primary` | `text-primary-content` |
| `btn btn-base-100` (custom) | `text-base-content` explicitly |

Always include text color explicitly:
```html
<button class="btn btn-neutral text-neutral-content">Search</button>
```

After adding any button, visually verify the label is readable against its background.
