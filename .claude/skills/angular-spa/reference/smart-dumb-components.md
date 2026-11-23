# Smart (Container) vs Dumb (Presentational) Component Pattern

> **Applies to:** Angular 21.2.x, signals, standalone components, `input()`/`output()` APIs.

---

## 1. Pattern Definition

### Smart (Container) Component

A **smart component** owns state, coordinates data flow, and delegates rendering to dumb children.

- Injects services via `inject()`
- Makes HTTP calls (via `resource()` or service methods)
- Owns signals (`signal()`, `computed()`)
- Passes data **down** to children via `input()`
- Receives events **up** from children via `output()`
- Lives in `features/` directory

### Dumb (Presentational) Component

A **dumb component** renders what it is given and emits what the user does — nothing more.

- Receives ALL data via `input()`
- Emits events via `output()`
- Injects **nothing** — zero `inject()` calls
- Contains zero business logic
- Contains zero HTTP calls
- Lives in `shared/components/` directory

**The portability test:** If you can move this component to any other Angular project and it still compiles and works, it is dumb. If it breaks because it depends on `ItemService`, `Router`, or any project-specific injectable, it is (or should be) smart.

---

## 2. Decision Tree

```
Is this component reused in 2+ places OR is it a leaf UI element?
  YES → Dumb component
          - receive data via input()
          - emit user actions via output()
          - inject nothing
          - place in shared/components/
  NO  → Is it a page or feature root?
          YES → Smart component
                  - own state with signal()
                  - inject services
                  - compose dumb children
                  - place in features/
          NO  → Prefer dumb
                  - escalate to smart ONLY if unavoidable local state
                  - document WHY it cannot be dumb
```

---

## 3. Angular 21 Signal-Based Examples

### Smart Component (page-level container)

```typescript
// features/items/items-page.component.ts
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { resource } from '@angular/core';
import { ItemCardComponent } from '../../shared/components/item-card/item-card.component';
import { LoadingSpinnerComponent } from '../../shared/components/loading-spinner/loading-spinner.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { ItemService } from '../../core/services/item.service';
import { Item } from '../../shared/models/item.model';

@Component({
  selector: 'app-items-page',
  imports: [ItemCardComponent, LoadingSpinnerComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- error → hasValue → loading: a reload after an error keeps showing the error, not a bare spinner -->
    @if (itemsResource.error(); as err) {
      <app-error-state [message]="err.message" />
    } @else if (itemsResource.hasValue()) {
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        @for (item of itemsResource.value(); track item.id) {
          <app-item-card
            [item]="item"
            (selected)="onItemSelected($event)"
          />
        }
      </div>
    } @else {
      <app-loading-spinner />
    }
  `,
})
export class ItemsPageComponent {
  // ✅ Smart: injects service
  private itemService = inject(ItemService);

  // ✅ Smart: owns async state via resource() — EXPERIMENTAL in Angular 21 (`@experimental` in the
  // 21.2 typings; the API may change). `loader` must return a Promise: here `getAll(): Promise<Item[]>`.
  // For an Observable-returning service use rxResource({ stream: () => this.itemService.getAll() })
  // from '@angular/core/rxjs-interop' (also experimental).
  protected itemsResource = resource({
    loader: () => this.itemService.getAll(),
  });

  // ✅ Smart: handles business events from dumb children
  protected onItemSelected(id: string): void {
    // navigate, open modal, update state, etc.
  }
}
```

### Dumb Component (shared presentational)

```typescript
// shared/components/item-card/item-card.component.ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { Item } from '../../models/item.model';

@Component({
  selector: 'app-item-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="card bg-base-100 shadow-md hover:shadow-xl transition-shadow duration-200">
      <div class="card-body">
        <h3 class="card-title text-base-content">{{ item().name }}</h3>
        <p class="text-base-content/70 text-sm">{{ item().category }}</p>
        <div class="card-actions justify-end mt-4">
          <button
            class="btn btn-primary btn-sm"
            (click)="selected.emit(item().id)"
            [attr.aria-label]="'View details for ' + item().name"
          >
            View Details
          </button>
        </div>
      </div>
    </article>
  `,
})
export class ItemCardComponent {
  // ✅ Dumb: receives ALL data via input()
  readonly item = input.required<Item>();

  // ✅ Dumb: emits user actions via output()
  readonly selected = output<string>();

  // NO inject() calls — this component is fully portable
}
```

### Dumb Component with Optional Input and Local UI State

Local UI state (e.g. hover, open/closed) that does not affect business logic is the ONE exception — dumb components MAY own it:

```typescript
// shared/components/accordion-item/accordion-item.component.ts
import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';

@Component({
  selector: 'app-accordion-item',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="collapse collapse-arrow bg-base-200">
      <input type="checkbox" [checked]="isOpen()" (change)="toggle()" />
      <div class="collapse-title font-semibold">{{ title() }}</div>
      <div class="collapse-content">
        <ng-content />
      </div>
    </div>
  `,
})
export class AccordionItemComponent {
  readonly title = input.required<string>();
  // ✅ Optional input with default value
  readonly initiallyOpen = input<boolean>(false);

  // ✅ Local UI state only — does not flow to business logic
  protected isOpen = signal(this.initiallyOpen());

  protected toggle(): void {
    this.isOpen.update(v => !v);
  }

  // NO inject() calls
}
```

---

## 4. Hard Rules (Zero Tolerance)

### Dumb Component Rules

```
❌ NEVER inject a service in a shared/components/ component
❌ NEVER call inject(HttpClient) or inject(AnyService) in a dumb component
❌ NEVER use inject(Router) or inject(ActivatedRoute) in a dumb component
❌ NEVER fetch data in a dumb component — receive it via input()
❌ NEVER own business state (filter selections, selected IDs, form data) in a dumb component
   Exception: local UI-only state (hover, open/closed toggle) is allowed

✅ ALWAYS use input.required<T>() for mandatory data
✅ ALWAYS use input<T>(defaultValue) for optional data
✅ ALWAYS use output<T>() for user-triggered events
✅ ALWAYS use ChangeDetectionStrategy.OnPush
✅ ALWAYS place in shared/components/<component-name>/
```

### Smart Component Rules

```
✅ Allowed to inject services via inject()
✅ Allowed to own business signals: signal(), computed()
✅ Allowed to trigger HTTP via resource() or service method calls
✅ Should compose dumb children — never render everything in one monolith
✅ Should be the ONLY component in the chain that calls inject()

❌ NEVER put smart components in shared/components/
   Smart components belong in features/ only
❌ NEVER duplicate data-fetching logic across multiple smart components
   Extract to a shared service instead
```

---

## 5. File Location Rule

```
src/app/
├── features/                       ← Smart components (own state, inject services)
│   └── <feature-name>/
│       ├── <feature-name>.component.ts
│       └── <feature-name>.component.spec.ts
│
└── shared/
    └── components/                 ← Dumb components ONLY (no inject(), no services)
        └── <component-name>/
            ├── <component-name>.component.ts
            ├── <component-name>.component.spec.ts
            └── index.ts            (barrel export — optional)
```

**Rule:** If a component file lives under `shared/components/`, it is dumb by contract. Code review blocks any `inject()` call found there.

---

## 6. Signal-Based State Lifting Pattern

When a dumb component needs state that multiple siblings share, lift it to the nearest smart parent.

```typescript
// ❌ Wrong: dumb component owns shared state
// shared/components/search-filter/search-filter.component.ts
@Component({ selector: 'app-search-filter' })
export class SearchFilterComponent {
  private filterService = inject(FilterService); // ❌ inject() in shared/components/

  protected filters = this.filterService.current;
}

// ✅ Correct: smart parent owns state, passes down via input(), receives changes via output()
// features/search/search-page.component.ts
@Component({ selector: 'app-search-page' })
export class SearchPageComponent {
  private filterService = inject(FilterService); // ✅ smart component injects

  protected filters = this.filterService.current; // signal from service

  protected onFiltersChanged(updated: FilterState): void {
    this.filterService.apply(updated); // smart component updates state
  }
}

// shared/components/search-filter/search-filter.component.ts
@Component({ selector: 'app-search-filter' })
export class SearchFilterComponent {
  readonly filters = input.required<FilterState>();  // ✅ receives state via input()
  readonly filtersChanged = output<FilterState>();   // ✅ emits changes via output()
  // NO inject() calls
}
```

### When Lifting Reveals Too Much Coupling

If a smart parent must pass 5+ inputs to a dumb component, consider:

1. **Consolidate inputs into one typed model** — pass a single `config: CardConfig` input instead of 5 separate primitives
2. **Re-evaluate if it belongs in shared** — highly coupled components may not be reusable and should live closer to the feature that needs them

---

## 7. Testing Implications

Dumb components are trivially testable because they have no dependencies:

```typescript
// shared/components/item-card/item-card.component.spec.ts
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ItemCardComponent } from './item-card.component';

describe('ItemCardComponent', () => {
  let fixture: ComponentFixture<ItemCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ItemCardComponent],
      providers: [provideZonelessChangeDetection()],
      // ✅ No mocks needed — dumb component has no inject() calls
    }).compileComponents();

    fixture = TestBed.createComponent(ItemCardComponent);
    fixture.componentRef.setInput('item', {
      id: '1',
      name: 'Sample item',
      category: 'General',
    });
    await fixture.whenStable();
  });

  it('displays the item name', () => {
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Sample item');
  });

  it('emits selected event when View Details is clicked', async () => {
    let emittedId: string | undefined;
    fixture.componentInstance.selected.subscribe((id: string) => (emittedId = id));

    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click();
    await fixture.whenStable();

    expect(emittedId).toBe('1');
  });
});
```

Smart component tests require service mocks — but dumb component tests never do.

---

## 8. Pre-Submit Checklist

```
Before committing any component:

□ Is it in shared/components/?
  → MUST have zero inject() calls
  → grep -c "inject(" <component-file> must return 0

□ Does it call inject()?
  → MUST live in features/, never in shared/components/

□ Does it call HTTP (HttpClient, resource(), service methods)?
  → MUST live in features/

□ Does it use input.required<T>()?
  → ✅ Dumb-safe — correct API for mandatory inputs

□ Does it use input<T>(defaultValue)?
  → ✅ Dumb-safe — correct API for optional inputs

□ Does it use output<T>()?
  → ✅ Dumb-safe — correct API for event emission

□ Does it own business state (selected IDs, filter values, form data)?
  → If YES and it is in shared/components/ → lift the state to the smart parent

□ Does it have local UI-only state (hover, toggle, open/closed)?
  → Allowed in dumb components — this is the one exception

□ Does it use ChangeDetectionStrategy.OnPush?
  → Required on ALL components — smart and dumb alike
```
