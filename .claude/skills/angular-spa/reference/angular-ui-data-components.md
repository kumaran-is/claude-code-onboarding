# Angular UI Data Display Components

Reusable Angular 22+ data display components using daisyUI 5.8.2 + Tailwind CSS 4.3.5.
Components are standalone by default (do not write `standalone: true`), use OnPush and signal-based APIs.

---

## Tables, pagination, server-side paging, virtual scroll

Canonical home: [`angular-ui-tables.md`](angular-ui-tables.md) — tier decision, `PaginationComponent`,
server-side paged table with `rxResource` (stable in v22), CDK virtual scroll, library choice and
responsive strategies. Do not copy those patterns here.

---

## Component Templates

---

## Card Component

```typescript
import {
  Component, signal, computed,
  input, output
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

## Empty State

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

## Data Table

```typescript
import {
  Component, input, signal, computed, output
} from '@angular/core';
import { EmptyStateComponent } from './empty-state.component';

export interface TableColumn<T> {
  key: keyof T & string;
  label: string;
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

@Component({
  selector: 'app-data-table',

  imports: [EmptyStateComponent],
  template: `
    <div class="overflow-x-auto rounded-box border border-base-300">
      <table class="table table-zebra">
        <thead class="bg-base-200">
          <tr>
            @for (col of columns(); track col.key) {
              <th [class.cursor-pointer]="col.sortable" [style.width]="col.width"
                [style.text-align]="col.align || 'left'"
                (click)="col.sortable && sort(col.key)"
                [attr.aria-sort]="sortKey() === col.key ? (sortDir() === 'asc' ? 'ascending' : 'descending') : 'none'">
                <div class="flex items-center gap-2">
                  <span>{{ col.label }}</span>
                  @if (col.sortable) {
                    <span class="text-base-content/60 text-sm">
                      {{ sortKey() === col.key ? (sortDir() === 'asc' ? '↑' : '↓') : '↕' }}
                    </span>
                  }
                </div>
              </th>
            }
          </tr>
        </thead>
        <tbody>
          @for (row of sortedData(); track $index) {
            <tr class="hover:bg-base-200/50 transition-colors"
              [class.cursor-pointer]="rowClickable()"
              (click)="rowClickable() && rowClick.emit(row)">
              @for (col of columns(); track col.key) {
                <td [style.text-align]="col.align || 'left'">{{ row[col.key] }}</td>
              }
            </tr>
          } @empty {
            <tr>
              <td [attr.colspan]="columns().length" class="p-0">
                <app-empty-state [title]="emptyTitle()" [description]="emptyDescription()" />
              </td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
})
export class DataTableComponent<T extends Record<string, unknown>> {
  columns = input.required<TableColumn<T>[]>();
  data = input.required<T[]>();
  rowClickable = input<boolean>(false);
  rowClick = output<T>();
  emptyTitle = input<string>('No data');
  emptyDescription = input<string>('No records found');

  protected readonly sortKey = signal<string | null>(null);
  protected readonly sortDir = signal<'asc' | 'desc'>('asc');

  protected readonly sortedData = computed(() => {
    const key = this.sortKey();
    const result = [...this.data()];
    if (!key) return result;
    const mod = this.sortDir() === 'asc' ? 1 : -1;
    return result.sort((a, b) => {
      if (a[key] == null) return mod;
      if (b[key] == null) return -mod;
      return a[key] < b[key] ? -mod : a[key] > b[key] ? mod : 0;
    });
  });

  protected sort(key: string): void {
    if (this.sortKey() === key) {
      this.sortDir.update(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortKey.set(key);
      this.sortDir.set('asc');
    }
  }
}
```

## Responsive Navigation

```typescript
import {
  Component, signal, input
} from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

interface NavItem { label: string; path: string; icon?: string; }

@Component({
  selector: 'app-responsive-nav',

  imports: [RouterLink, RouterLinkActive],
  template: `
    <div class="drawer lg:drawer-open">
      <input id="nav-drawer" type="checkbox" class="drawer-toggle"
        [checked]="drawerOpen()" (change)="toggleDrawer($event)" />
      <div class="drawer-content flex flex-col min-h-screen">
        <header class="navbar bg-base-100 border-b border-base-300 lg:hidden sticky top-0 z-30">
          <div class="flex-none">
            <label for="nav-drawer" class="btn btn-square btn-ghost" aria-label="Open navigation">
              <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
              </svg>
            </label>
          </div>
          <div class="flex-1"><span class="text-xl font-bold px-2">{{ title() }}</span></div>
        </header>
        <main class="flex-1 p-4 lg:p-6"><ng-content></ng-content></main>
      </div>
      <aside class="drawer-side z-40">
        <label for="nav-drawer" class="drawer-overlay" aria-label="Close navigation"></label>
        <div class="bg-base-200 min-h-full w-64 flex flex-col">
          <div class="p-4 border-b border-base-300">
            <h1 class="text-xl font-bold">{{ title() }}</h1>
          </div>
          <nav class="flex-1 p-4">
            <ul class="menu gap-1">
              @for (item of navItems(); track item.path) {
                <li>
                  <a [routerLink]="item.path" routerLinkActive="active"
                    [routerLinkActiveOptions]="{ exact: item.path === '/' }"
                    (click)="drawerOpen.set(false)">
                    @if (item.icon) { <span>{{ item.icon }}</span> }
                    {{ item.label }}
                  </a>
                </li>
              }
            </ul>
          </nav>
        </div>
      </aside>
    </div>
  `,
})
export class ResponsiveNavComponent {
  title = input<string>('App');
  navItems = input<NavItem[]>([]);
  protected readonly drawerOpen = signal(false);

  protected toggleDrawer(event: Event): void {
    this.drawerOpen.set((event.target as HTMLInputElement).checked);
  }
}
```

## Expandable Section

```typescript
import { Component, input, signal } from '@angular/core';

@Component({
  selector: 'app-expandable-section',

  template: `
    <div class="collapse collapse-arrow bg-base-200 rounded-box">
      <input type="checkbox" [checked]="isExpanded()" (change)="isExpanded.update(v => !v)"
        [attr.aria-expanded]="isExpanded()" />
      <div class="collapse-title text-lg font-medium">
        {{ title() }}
        @if (badge()) { <span class="badge badge-sm ml-2">{{ badge() }}</span> }
      </div>
      <div class="collapse-content"><div class="pt-2"><ng-content></ng-content></div></div>
    </div>
  `,
})
export class ExpandableSectionComponent {
  title = input.required<string>();
  badge = input<string>('');
  defaultExpanded = input<boolean>(false);
  protected readonly isExpanded = signal(false);
}
```

---

## Chat / Agent UI — Visual Quality Baseline

When building any chat or conversational agent UI (message list + input bar pattern), apply ALL of the following from the first scaffold. Do not wait for user feedback to add these.

### Layout
- Outer container: `h-screen flex flex-col overflow-hidden` — never `min-h-screen` (causes footer scroll-away)
- Header: `flex-shrink-0` — must not grow or shrink
- Message list: `flex-1 overflow-y-auto` — scrolls independently
- Input bar: `flex-shrink-0` at bottom — always visible, never scrolls away
- Empty state: center the input bar vertically with `min-h-[55vh] flex flex-col items-center justify-center`
- After first message: move input bar to sticky footer pattern

### Cards
- Use `card bg-base-100 shadow-sm border border-base-200` — not plain divs
- Card content: `card-body p-4` with `card-title text-sm font-semibold`
- Price / key stats: `text-lg font-bold text-neutral` for emphasis
- Secondary text: `text-base-content/60 text-xs`

### Buttons
- Primary action: `btn btn-neutral rounded-xl` — not `btn btn-primary` (often invisible on dark themes)
- Text on dark buttons must be `text-neutral-content` — always verify contrast
- Disabled state: `[disabled]="loading()"` on all submit buttons

### Loading states
- Inline spinner in button: `<span class="loading loading-spinner loading-sm"></span>`
- Agent thinking indicator: `<span class="loading loading-dots loading-sm text-neutral"></span>` with explanatory text
- Never show a blank area while waiting — always show a loading indicator

### Empty state
- Show branded icon, headline, subtitle, and suggestion chips
- Suggestion chips: `btn btn-sm bg-base-100 border border-base-300 hover:bg-neutral hover:text-neutral-content`

### Auto-scroll
- Inject `viewChild<ElementRef>('messageContainer')`
- Use `effect()` to watch the messages signal and scroll to bottom: `el.scrollTop = el.scrollHeight` inside a `setTimeout(..., 50)`

### Smoke test before reporting done
Open the app and verify:
- [ ] Header visible and not overlapping content
- [ ] Input bar always visible at bottom (even when messages overflow)
- [ ] Cards have visible borders/shadows — not flat invisible boxes
- [ ] Buttons have visible text (check contrast on dark background)
- [ ] Loading spinner appears when request is in-flight

---

## Bug 10 — Missing left padding after layout change

**What happened:** After modifying the outer container's CSS class, the `px-4`/`px-6` padding was dropped. Content rendered flush against the left edge of the viewport with zero margin.

## Layout Padding — Always Preserve on Refactor

When refactoring the outer container or changing flex/grid structure, ALWAYS verify padding is carried forward.

Checklist when changing `<div class="...">` on an outer container:
- [ ] `px-4` or `px-6` still present on content wrapper (not just outer container)
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

Never put padding only on the outermost div — it gets lost when structure changes.

---

## Bug 11 — Invisible text on dark button

**What happened:** A button used `btn btn-neutral` but the text color was not set to `text-neutral-content`. On a dark neutral background, the text was invisible.

## Button Text Contrast — Always Verify

When using DaisyUI semantic button classes, never assume text color is set automatically.

| Button class | Required text class |
|---|---|
| `btn btn-neutral` | `text-neutral-content` (explicit or via DaisyUI) |
| `btn btn-primary` | `text-primary-content` |
| `btn btn-base-100` (custom) | `text-base-content` explicitly |

❌ Common mistake:
```html
<button class="btn btn-neutral">Search</button>
<!-- text may be invisible if neutral bg = dark and text defaults to dark -->
```

✅ Safe pattern — always include text color:
```html
<button class="btn btn-neutral text-neutral-content">Search</button>
```

**Smoke test:** After adding any button, visually verify the label is readable against its background. Do not skip this for "obviously styled" components.
