# Angular UI Table Patterns

Angular 22+ table and grid components using daisyUI 5.8.2 + Tailwind CSS 4.3.5.
Components are standalone by default (do not write `standalone: true`), use OnPush and signal-based APIs.

---

## Section A: Table Tier Decision Framework

Choose the right implementation based on row count.

```
< 100 rows        Simple HTML table
                  Use: existing DataTableComponent (no extra libraries)

100–1,000 rows    Client-side features
                  Use: DataTableComponent + PaginationComponent + client filter

1,000–10,000 rows Server-side pagination
                  Use: query signal + rxResource (Section C)

10,000+ rows      Virtual scrolling
                  Use: @angular/cdk CdkVirtualScrollViewport (Section D below)
```

**Determining row count in practice:**
- Check the API's total count response field at integration time
- If unbounded (e.g., audit log, event stream), default to server-side from the start
- If unsure: start with client-side pagination; migrate to server-side if P95 load > 500 rows

---

## Section B: Pagination Component

```typescript
import {
  Component, input, output, computed
} from '@angular/core';

@Component({
  selector: 'app-pagination',
  template: `
    <nav class="flex items-center justify-between mt-4" aria-label="Pagination">
      <div class="flex items-center gap-2">
        <span class="text-sm text-base-content/60">Rows per page:</span>
        <select class="select select-sm"
          [value]="pageSize()"
          (change)="onPageSizeChange($event)"
          aria-label="Rows per page">
          @for (size of pageSizeOptions(); track size) {
            <option [value]="size" [selected]="size === pageSize()">{{ size }}</option>
          }
        </select>
        <span class="text-sm text-base-content/60">
          {{ rangeStart() }}–{{ rangeEnd() }} of {{ total() }}
        </span>
      </div>
      <div class="join" role="group" aria-label="Page navigation">
        <button type="button" class="join-item btn btn-sm"
          [class.btn-disabled]="currentPage() === 0"
          [attr.aria-disabled]="currentPage() === 0"
          [attr.aria-label]="'Previous page'"
          (click)="goTo(currentPage() - 1)">«</button>
        @for (page of visiblePages(); track page) {
          @if (page === -1) {
            <button type="button" class="join-item btn btn-sm btn-disabled" aria-hidden="true">…</button>
          } @else {
            <button type="button" class="join-item btn btn-sm"
              [class.btn-active]="page === currentPage()"
              [attr.aria-current]="page === currentPage() ? 'page' : null"
              [attr.aria-label]="'Page ' + (page + 1)"
              (click)="goTo(page)">{{ page + 1 }}</button>
          }
        }
        <button type="button" class="join-item btn btn-sm"
          [class.btn-disabled]="currentPage() === totalPages() - 1"
          [attr.aria-disabled]="currentPage() === totalPages() - 1"
          [attr.aria-label]="'Next page'"
          (click)="goTo(currentPage() + 1)">»</button>
      </div>
    </nav>
  `,
})
export class PaginationComponent {
  total = input.required<number>();
  currentPage = input<number>(0);
  pageSize = input<number>(10);
  pageSizeOptions = input<number[]>([10, 25, 50, 100]);
  pageChange = output<number>();
  pageSizeChange = output<number>();

  protected readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.total() / this.pageSize()))
  );
  protected readonly rangeStart = computed(() =>
    this.total() === 0 ? 0 : this.currentPage() * this.pageSize() + 1
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.total())
  );
  protected readonly visiblePages = computed<number[]>(() => {
    const total = this.totalPages();
    const current = this.currentPage();
    if (total <= 7) return Array.from({ length: total }, (_, i) => i);
    const pages: number[] = [0];
    if (current > 2) pages.push(-1);
    for (let i = Math.max(1, current - 1); i <= Math.min(total - 2, current + 1); i++) {
      pages.push(i);
    }
    if (current < total - 3) pages.push(-1);
    pages.push(total - 1);
    return pages;
  });

  protected goTo(page: number): void {
    if (page < 0 || page >= this.totalPages() || page === this.currentPage()) return;
    this.pageChange.emit(page);
  }
  protected onPageSizeChange(event: Event): void {
    const size = Number((event.target as HTMLSelectElement).value);
    this.pageSizeChange.emit(size);
    this.pageChange.emit(0);
  }
}
```

---

## Section C: Server-Side Paged Table (canonical paged fetch)

Use when row count exceeds 1,000 or data must be filtered/sorted server-side. This is the single
home for the paged-fetch pattern; other files link here.

- One `query` signal holds page, size, sort and filter. Changing the filter or sort resets `page` to 0.
- `rxResource` re-fetches when `query()` changes and cancels the stale request (latest wins).
  `rxResource` is stable in v22 (`@publicApi 22.0`).
- Never wire `toObservable(...)` inside a method: it needs an injection context (throws `NG0203`) and
  each call adds another live subscription. Declare the resource as a field.
- Never replace a failed load with `{ items: [], total: 0 }` — that renders a failure as "no data".
  Render the error state with a retry (`reload()`). Load-state rules (check `error()` before `value()`,
  `hasValue()`, 401 vs 403 messages) live in `angular-ui-patterns/reference/loading-control-flow.md`
  and `error-handling.md`.
- Mutations go through `HttpClient`, then call `orders.reload()`.

```typescript
import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, Service, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { PaginationComponent } from './pagination.component';

export interface Order { readonly id: string; readonly customer: string; readonly total: number; }
export interface PagedResponse<T> { readonly items: readonly T[]; readonly total: number; }
export interface TableQuery {
  readonly page: number;
  readonly pageSize: number;
  readonly sortField: 'customer' | 'total' | null;
  readonly sortDir: 'asc' | 'desc';
  readonly filter: string;
}

@Service()
export class OrdersApi {
  private readonly http = inject(HttpClient);

  list(q: TableQuery): Observable<PagedResponse<Order>> {
    let params = new HttpParams()
      .set('page', q.page)
      .set('pageSize', q.pageSize)
      .set('filter', q.filter);
    if (q.sortField) params = params.set('sort', q.sortField).set('dir', q.sortDir);
    return this.http.get<PagedResponse<Order>>('/api/orders', { params });
  }
}

@Component({
  selector: 'app-orders-table',
  imports: [PaginationComponent],
  template: `
    @if (orders.error()) {
      <div class="alert alert-error" role="alert">
        <span>Orders could not be loaded.</span>
        <button type="button" class="btn btn-sm" (click)="orders.reload()">Try again</button>
      </div>
    } @else if (!orders.hasValue()) {
      <div class="flex justify-center p-8" role="status" aria-label="Loading orders">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    } @else {
      <div class="overflow-x-auto rounded-box border border-base-300">
        <table class="table table-zebra">
          <thead class="bg-base-200">
            <tr>
              <th [attr.aria-sort]="ariaSort('customer')">
                <button type="button" class="btn btn-ghost btn-xs" (click)="sortBy('customer')">Customer</button>
              </th>
              <th [attr.aria-sort]="ariaSort('total')">
                <button type="button" class="btn btn-ghost btn-xs" (click)="sortBy('total')">Total</button>
              </th>
            </tr>
          </thead>
          <tbody>
            @for (order of orders.value().items; track order.id) {
              <tr><td>{{ order.customer }}</td><td>{{ order.total }}</td></tr>
            } @empty {
              <tr><td colspan="2">No orders match this filter.</td></tr>
            }
          </tbody>
        </table>
      </div>
      <app-pagination
        [total]="orders.value().total"
        [currentPage]="query().page"
        [pageSize]="query().pageSize"
        (pageChange)="goTo($event)"
        (pageSizeChange)="setPageSize($event)" />
    }
  `,
})
export class OrdersTableComponent {
  private readonly api = inject(OrdersApi);

  protected readonly query = signal<TableQuery>({
    page: 0, pageSize: 25, sortField: null, sortDir: 'asc', filter: '',
  });

  // Stable in v22. A params change moves status to 'loading' and clears value();
  // reload() keeps the previous value while status is 'reloading'.
  protected readonly orders = rxResource({
    params: () => this.query(),
    stream: ({ params }) => this.api.list(params),
  });

  protected readonly sortState = computed(() => {
    const q = this.query();
    return { field: q.sortField, dir: q.sortDir };
  });

  search(filter: string): void {
    this.query.update((q) => ({ ...q, filter: filter.trim(), page: 0 }));
  }

  protected sortBy(field: 'customer' | 'total'): void {
    this.query.update((q) => ({
      ...q,
      sortField: field,
      sortDir: q.sortField === field && q.sortDir === 'asc' ? 'desc' : 'asc',
      page: 0,
    }));
  }

  protected ariaSort(field: 'customer' | 'total'): 'ascending' | 'descending' | 'none' {
    const s = this.sortState();
    if (s.field !== field) return 'none';
    return s.dir === 'asc' ? 'ascending' : 'descending';
  }

  protected goTo(page: number): void {
    this.query.update((q) => ({ ...q, page }));
  }

  protected setPageSize(pageSize: number): void {
    this.query.update((q) => ({ ...q, pageSize, page: 0 }));
  }
}
```

---

## Section D: Virtual Scrolling (10,000+ rows)

**Install:** `npm install @angular/cdk@22.3.0` (match the installed `@angular/core` minor).

Virtual scrolling renders only the rows in the viewport, so DOM size stays fixed regardless of dataset size.
`*cdkVirtualFor` is still the CDK API (there is no `@for` equivalent for virtual scroll).

```typescript
import { Component, input } from '@angular/core';
import { ScrollingModule } from '@angular/cdk/scrolling';

export interface VirtualRow { readonly id: string | number; readonly [key: string]: unknown; }

@Component({
  selector: 'app-virtual-table',
  imports: [ScrollingModule],
  template: `
    <div class="overflow-x-auto rounded-box border border-base-300">
      <!-- Header outside the viewport so it stays visible -->
      <table class="table w-full">
        <thead class="bg-base-200 sticky top-0 z-10">
          <tr>
            @for (col of columns(); track col.key) {
              <th [style.width]="col.width">{{ col.label }}</th>
            }
          </tr>
        </thead>
      </table>
      <cdk-virtual-scroll-viewport [itemSize]="rowHeightPx()" [style.height.px]="viewportHeightPx()" class="w-full">
        <table class="table w-full">
          <tbody>
            <tr *cdkVirtualFor="let row of items(); trackBy: trackById; let odd = odd" [class.bg-base-200]="odd">
              @for (col of columns(); track col.key) {
                <td [style.width]="col.width">{{ row[col.key] }}</td>
              }
            </tr>
          </tbody>
        </table>
      </cdk-virtual-scroll-viewport>
    </div>
  `,
})
export class VirtualTableComponent<T extends VirtualRow> {
  readonly columns = input.required<readonly { key: keyof T & string; label: string; width?: string }[]>();
  readonly items = input.required<readonly T[]>();
  readonly rowHeightPx = input(48); // must equal the rendered row height
  readonly viewportHeightPx = input(600);

  protected trackById(_index: number, row: T): string | number {
    return row.id;
  }
}
```

**Key constraints:**
- `itemSize` must match the rendered row height — mismatches cause scroll jitter.
- `trackBy` is mandatory — without it CDK re-renders every row on scroll.
- Rows are recycled: stripe from the item index (`let odd = odd`), not with `table-zebra` (DOM-index striping flickers).
- Import `ScrollingModule` from `@angular/cdk/scrolling`.

---

## Section E: Library Comparison

| Need | Recommended | Install |
|------|-------------|---------|
| Full design control, TypeScript-first, headless | **TanStack Table** | `@tanstack/angular-table` (pin the version) |
| Enterprise: grouping, aggregation, export, pivot | **AG Grid Community** | `ag-grid-angular ag-grid-community` (pin) |
| Standard sort/filter/paginate, <1K rows | **Existing DataTableComponent** | No install needed |
| 10K+ rows, smooth scroll | **Angular CDK virtual scroll** | `@angular/cdk` |

Rule: introduce a table library only when you need ≥3 features DataTableComponent does not provide
(e.g. inline editing + column resize + export). A library for a simple CRUD list adds bundle weight for no user-visible benefit.

---

## Section F: Responsive Table Strategies

| Strategy | When to Use | Implementation |
|----------|-------------|----------------|
| **Horizontal scroll** (default) | All columns critical | `<div class="overflow-x-auto">` around `<table class="table min-w-[640px]">` |
| **Priority columns** | Some columns secondary on mobile | `hidden md:table-cell` on the `<th>` AND matching `<td>` |
| **Card stack** | Row count < 50; mobile-first | `<div class="block md:hidden">` card per row + `<div class="hidden md:block">` table |
| **Truncate & expand** | Many columns | Show 2–3 columns + an expand button revealing the rest |

**Expand row toggle:**
```typescript
protected readonly expandedRows = signal(new Set<string>());

protected toggleRow(id: string): void {
  this.expandedRows.update((set) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
}
```

```html
<button type="button" class="btn btn-xs btn-ghost"
  [attr.aria-expanded]="expandedRows().has(row.id)"
  [attr.aria-label]="'Toggle details for ' + row.name"
  (click)="toggleRow(row.id)">{{ expandedRows().has(row.id) ? '−' : '+' }}</button>
```

---

## DataTable Component Interface

```typescript
export interface TableColumn<T> {
  key: keyof T & string;
  label: string;
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

// DataTableComponent inputs/outputs:
// columns = input.required<TableColumn<T>[]>()
// data = input.required<T[]>()
// rowClickable = input<boolean>(false)
// rowClick = output<T>()
// emptyTitle = input<string>('No data')
// emptyDescription = input<string>('No records found')
//
// Internals: sortKey signal, sortDir signal, sortedData computed
// Template: overflow-x-auto > table.table-zebra > thead.bg-base-200 + tbody @for/@empty
// Sort indicator: aria-sort="ascending|descending|none" on <th>
// Empty state: uses <app-empty-state> with colspan
```
