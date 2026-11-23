# Angular Best Practices — Extended Patterns

Detailed examples for `../SKILL.md`. Angular 22.3: zoneless default, OnPush default (never set
explicitly), `standalone` implicit, resources and Signal Forms stable, `@Service()` for new singletons.

---

## Rendering Performance (HIGH) — Extended Examples

### Virtual Scrolling for Large Lists

```typescript
import { CdkFixedSizeVirtualScroll, CdkVirtualForOf, CdkVirtualScrollViewport } from '@angular/cdk/scrolling';

@Component({
  selector: 'app-large-list',
  imports: [CdkVirtualScrollViewport, CdkFixedSizeVirtualScroll, CdkVirtualForOf],
  template: `
    <cdk-virtual-scroll-viewport itemSize="50" class="h-96">
      <!-- *cdkVirtualFor is the CDK API; @for does not virtualize -->
      <div *cdkVirtualFor="let item of items(); trackBy: trackById" class="h-[50px]">{{ item.name }}</div>
    </cdk-virtual-scroll-viewport>
  `,
})
export class LargeList {
  readonly items = input.required<readonly Item[]>();
  protected readonly trackById = (_: number, item: Item) => item.id;
}
```

### Pure Pipes Over Methods

```typescript
// ✅ CORRECT - Pure pipe (pipes are pure and standalone by default)
@Pipe({ name: 'activeOnly' })
export class ActiveOnlyPipe implements PipeTransform {
  transform(items: readonly Item[]): Item[] {
    return items.filter((i) => i.active);
  }
}
// Template: @for (item of items() | activeOnly; track item.id) { … }

// ❌ WRONG - Method re-runs every time the view is checked
// @for (item of getActiveItems(); track item.id) { … }
```

### computed() for Derived Data

```typescript
// ✅ CORRECT - Cached until a dependency changes
export class ProductFilter {
  readonly products = signal<Product[]>([]);
  readonly filter = signal('');
  readonly filteredProducts = computed(() => {
    const f = this.filter().toLowerCase();
    return this.products().filter((p) => p.name.toLowerCase().includes(f));
  });
}

// ❌ WRONG - Getter recalculates on every access
get filteredProducts() {
  return this.products().filter((p) => p.name.toLowerCase().includes(this.filter()));
}
```

---

## State Management (MEDIUM) — Extended Examples

### Signal Service With Read-Only Exposure

```typescript
@Service()
export class SessionPrefs {
  private readonly _theme = signal<'light' | 'dark'>('light');
  readonly theme = this._theme.asReadonly(); // not computed(() => this._theme())

  toggleTheme(): void {
    this._theme.update((t) => (t === 'light' ? 'dark' : 'light'));
  }
}
```

### Colocate State With Features

```typescript
// ✅ CORRECT - Feature-scoped: created and destroyed with the page
@Injectable() // NOT providedIn: 'root'
export class ProductFilters {
  readonly query = signal('');
}

@Component({
  selector: 'app-product-page',
  providers: [ProductFilters],
  template: `…`,
})
export class ProductPage {
  protected readonly filters = inject(ProductFilters);
}

// ❌ WRONG - One root service holding every feature's state
@Service()
export class GlobalState { /* all app state */ }
```

### Derive, Don't Mirror

```typescript
// ❌ WRONG - effect() copying state: extra pass, circular-update and ExpressionChanged risk
effect(() => this.selected.set(this.items()[0]));

// ✅ CORRECT - writable value that resets when the source changes
readonly selected = linkedSignal(() => this.items()[0]);
```

---

## Memory Management (LOW-MEDIUM) — Extended Examples

### takeUntilDestroyed for Long-Lived Streams

```typescript
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({ selector: 'app-live-feed', template: `…` })
export class LiveFeed {
  private readonly feed = inject(FeedSocket);
  readonly last = signal<FeedEvent | null>(null);

  constructor() {
    // Injection context (constructor): takeUntilDestroyed() finds DestroyRef itself.
    this.feed.events$.pipe(takeUntilDestroyed()).subscribe((e) => this.last.set(e));
  }
}

// ❌ WRONG - Manual Subscription + ngOnDestroy bookkeeping
export class LiveFeed implements OnInit, OnDestroy {
  private sub?: Subscription;
  ngOnInit() { this.sub = this.feed.events$.subscribe(/* … */); }
  ngOnDestroy() { this.sub?.unsubscribe(); }
}
```

Outside an injection context (e.g. inside a method), pass the `DestroyRef`:
`takeUntilDestroyed(this.destroyRef)` with `private readonly destroyRef = inject(DestroyRef)`.

### Prefer Signals Over Subscriptions

```typescript
// ✅ CORRECT - No subscription to manage
@Component({ selector: 'app-account', template: `{{ account()?.name }}` })
export class Account {
  private readonly api = inject(AccountApi);
  readonly account = toSignal(this.api.current$, { initialValue: null });
}
```

`toSignal` / `toObservable` must run in an injection context (field initializer or constructor). Called
from a method they throw NG0203 — verified on Angular 21.2 (not re-run on 22.3).

---

## Quick Reference Checklists

### New Component Checklist

- [ ] No explicit `changeDetection` (OnPush is the v22 default)
- [ ] No `standalone: true`, no `NgModule`, no `CommonModule`
- [ ] Signals for state (`signal()`, `computed()`, `input()`, `output()`, `model()`)
- [ ] `inject()` for dependencies
- [ ] `@for` with `track` on a unique identifier (not `$index`)
- [ ] Async data shows loading / empty / error / ready (`angular-ui-patterns`)
- [ ] Errors logged through `Logger` and shown to the user — no `console.*`, no fallback data

### Performance Review Checklist

- [ ] No methods called in templates — use pure pipes or `computed()`
- [ ] Large lists (>50 items) use `CdkVirtualScrollViewport`
- [ ] Heavy components wrapped in `@defer`
- [ ] Every route-level component uses `loadComponent` / `loadChildren`
- [ ] Heavy third-party libraries use dynamic `import()`
- [ ] No intra-app barrel re-exports; shared libraries expose one public API file

### SSR Checklist (details: `angular/references/ssr-hydration.md`)

- [ ] `provideClientHydration(...)` configured; `withIncrementalHydration()` if `hydrate` triggers are used (it enables event replay — no separate `withEventReplay()`)
- [ ] Critical above-the-fold content renders without `@defer`
- [ ] Below-fold content uses `@defer (hydrate on viewport)`; interactive-only widgets `hydrate on interaction`
- [ ] No hand-written `TransferState` for `HttpClient` GET/HEAD calls (transferred automatically); requests with auth headers are not cached by default
