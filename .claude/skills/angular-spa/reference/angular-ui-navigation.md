# Angular UI Navigation Patterns

Angular 22+ navigation, sidebar, and expandable section components using daisyUI 5.8.2 + Tailwind CSS 4.3.5.
All components use standalone, OnPush, and signal-based APIs.

---

## Responsive Navigation (Drawer Sidebar)

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
        <!-- Mobile header (hidden on lg+) -->
        <header class="navbar bg-base-100 border-b border-base-300 lg:hidden sticky top-0 z-30">
          <div class="flex-none">
            <label for="nav-drawer" class="btn btn-square btn-ghost" aria-label="Open navigation">
              <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 6h16M4 12h16M4 18h16"/>
              </svg>
            </label>
          </div>
          <div class="flex-1">
            <span class="text-xl font-bold px-2">{{ title() }}</span>
          </div>
        </header>
        <main class="flex-1 p-4 lg:p-6">
          <ng-content></ng-content>
        </main>
      </div>
      <!-- Sidebar -->
      <aside class="drawer-side z-40">
        <label for="nav-drawer" class="drawer-overlay" aria-label="Close navigation"></label>
        <div class="bg-base-200 min-h-full w-64 flex flex-col">
          <div class="p-4 border-b border-base-300">
            <h1 class="text-xl font-bold">{{ title() }}</h1>
          </div>
          <nav class="flex-1 p-4" aria-label="Main navigation">
            <ul class="menu gap-1">
              @for (item of navItems(); track item.path) {
                <li>
                  <a [routerLink]="item.path" routerLinkActive="active"
                    [routerLinkActiveOptions]="{ exact: item.path === '/' }"
                    (click)="drawerOpen.set(false)">
                    @if (item.icon) { <span aria-hidden="true">{{ item.icon }}</span> }
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

**Usage:**
```html
<app-responsive-nav title="My App" [navItems]="navItems">
  <!-- page content here — projected into <main> -->
  <router-outlet />
</app-responsive-nav>
```

---

## Expandable Section (Accordion)

```typescript
import { Component, input, signal } from '@angular/core';

@Component({
  selector: 'app-expandable-section',
  template: `
    <div class="collapse collapse-arrow bg-base-200 rounded-box">
      <input type="checkbox"
        [checked]="isExpanded()"
        (change)="isExpanded.update(v => !v)"
        [attr.aria-expanded]="isExpanded()" />
      <div class="collapse-title text-lg font-medium">
        {{ title() }}
        @if (badge()) {
          <span class="badge badge-sm ml-2">{{ badge() }}</span>
        }
      </div>
      <div class="collapse-content">
        <div class="pt-2">
          <ng-content></ng-content>
        </div>
      </div>
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

**Usage:**
```html
<app-expandable-section title="Maintenance History" badge="3">
  <!-- content projected here -->
  <ul class="menu">
    <li><a>Ticket #001 — Plumbing</a></li>
  </ul>
</app-expandable-section>
```

---

## Breadcrumb Pattern

```typescript
import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

interface BreadcrumbItem { label: string; path?: string; }

@Component({
  selector: 'app-breadcrumb',
  imports: [RouterLink],
  template: `
    <div class="breadcrumbs text-sm">
      <ul aria-label="Breadcrumb">
        @for (item of items(); track item.label; let last = $last) {
          <li>
            @if (item.path && !last) {
              <a [routerLink]="item.path">{{ item.label }}</a>
            } @else {
              <span [attr.aria-current]="last ? 'page' : null">{{ item.label }}</span>
            }
          </li>
        }
      </ul>
    </div>
  `,
})
export class BreadcrumbComponent {
  items = input.required<BreadcrumbItem[]>();
}
```

**Usage:**
```html
<app-breadcrumb [items]="[
  { label: 'Dashboard', path: '/dashboard' },
  { label: 'Properties', path: '/properties' },
  { label: '123 Main St' }
]" />
```

---

## Tabs Pattern

Panel content is passed as `<ng-template [appTabPanel]="id">`: `<ng-content>` projects once, so it cannot
fill one panel per loop iteration, and a structural `*ngIf` on it (without importing `NgIf`) silently renders
nothing (`NG8103` is only a warning).

```typescript
import {
  Component, Directive, TemplateRef, computed, contentChildren, inject, input, signal,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';

export interface TabItem { id: string; label: string; }

/** Marks the template for one panel: <ng-template appTabPanel="details">…</ng-template> */
@Directive({ selector: 'ng-template[appTabPanel]' })
export class TabPanel {
  readonly id = input.required<string>({ alias: 'appTabPanel' });
  readonly template = inject(TemplateRef);
}

@Component({
  selector: 'app-tabs',
  imports: [NgTemplateOutlet],
  template: `
    <div role="tablist" class="tabs tabs-border">
      @for (tab of tabs(); track tab.id) {
        <button
          role="tab"
          type="button"
          class="tab"
          [class.tab-active]="activeTab() === tab.id"
          [attr.aria-selected]="activeTab() === tab.id"
          [attr.aria-controls]="'tabpanel-' + tab.id"
          [attr.tabindex]="activeTab() === tab.id ? 0 : -1"
          [id]="'tab-' + tab.id"
          (click)="selected.set(tab.id)"
          (keydown)="onKey($event)">
          {{ tab.label }}
        </button>
      }
    </div>
    <div class="pt-4">
      @for (tab of tabs(); track tab.id) {
        <div
          role="tabpanel"
          tabindex="0"
          [id]="'tabpanel-' + tab.id"
          [attr.aria-labelledby]="'tab-' + tab.id"
          [hidden]="activeTab() !== tab.id">
          @if (activeTab() === tab.id) {
            <ng-container [ngTemplateOutlet]="panelFor(tab.id)" />
          }
        </div>
      }
    </div>
  `,
})
export class TabsComponent {
  readonly tabs = input.required<TabItem[]>();
  private readonly panels = contentChildren(TabPanel);
  protected readonly selected = signal<string | null>(null);
  protected readonly activeTab = computed(() => this.selected() ?? this.tabs()[0]?.id ?? '');

  protected panelFor(id: string): TemplateRef<unknown> | null {
    return this.panels().find((panel) => panel.id() === id)?.template ?? null;
  }

  /** Arrow keys move between tabs (roving tabindex), as in the WAI-ARIA tabs pattern. */
  protected onKey(event: KeyboardEvent): void {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    const ids = this.tabs().map((tab) => tab.id);
    if (ids.length === 0) return;
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = ids[(ids.indexOf(this.activeTab()) + step + ids.length) % ids.length];
    this.selected.set(next);
    (event.currentTarget as HTMLElement).closest('[role="tablist"]')?.querySelector<HTMLElement>(`#tab-${next}`)?.focus();
  }
}
```

**Usage** (import `TabsComponent` and `TabPanel`):
```html
<app-tabs [tabs]="[{ id: 'details', label: 'Details' }, { id: 'history', label: 'History' }]">
  <ng-template appTabPanel="details"><p>Details content</p></ng-template>
  <ng-template appTabPanel="history"><p>History content</p></ng-template>
</app-tabs>
```

Verified: compiles under `strictTemplates` with no `NG8103`; a Vitest spec shows the first panel's content,
switches on click and on ArrowRight.

---

## Navigation Rules

- Always use `routerLinkActive="active"` — never manually compare `router.url` for active state
- Drawer sidebar: `lg:drawer-open` makes sidebar always-open on large screens, toggled on small
- Close the mobile drawer on nav item click: `(click)="drawerOpen.set(false)"`
- All interactive nav elements need `aria-label` or visible text — icon-only buttons need `aria-label`
- Breadcrumb last item: `aria-current="page"` required for screen reader context
- Tabs: `role="tab"` + `aria-selected` + `role="tabpanel"` + `aria-labelledby` are all required
