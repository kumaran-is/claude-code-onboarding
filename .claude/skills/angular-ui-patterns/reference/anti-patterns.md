# Anti-Patterns

## Loading States

```html
<!-- ❌ WRONG — spinner over existing data (flashes on every refresh) -->
@if (items.isLoading()) { <app-spinner /> }

<!-- ❌ WRONG — reads value() before error(): value() throws in the error state -->
@for (item of items.value(); track item.id) { … }

<!-- ✅ CORRECT — one derived load state (loading-control-flow.md) -->
@switch (state().kind) {
  @case ('loading') { <app-skeleton-list /> }
  @case ('error') { <app-error-state … /> }
  …
}
```

- ❌ Hand-set `loading` / `error` / `items` signals updated inside a `subscribe` — derive them from a resource.
- ❌ `effect()` that copies resource state into other signals — use `computed()` / `linkedSignal()`.
- ❌ Showing a skeleton during `'reloading'` — keep the data and show a thin progress bar.

## Error Handling

```typescript
// ❌ WRONG — error swallowed (and console.* is banned in production code)
try {
  await firstValueFrom(this.api.save(dto));
} catch (e) {
  console.log(e);
}

// ❌ WRONG — fallback/mock data hides the failure
catchError(() => of([]))

// ✅ CORRECT — log through Logger AND surface to the user
try {
  await firstValueFrom(this.api.save(dto));
} catch (err) {
  this.logger.error('save failed', err);
  this.toast.error('Changes could not be saved. Try again.');
}
```

- ❌ Treating 403 as 401 (redirect to login) — 403 is "not authorised" (`error-handling.md`).
- ❌ `@if (retry.observed)` — `OutputEmitterRef` has no `observed`; use a `retryable` input.

## Button States

```html
<!-- ❌ WRONG — not disabled during submission -->
<button type="button" (click)="submit()">Submit</button>

<!-- ✅ CORRECT — disabled, shows progress; the handler ALSO returns early while in flight -->
<button type="button" (click)="submit()" [disabled]="saving()">
  {{ saving() ? 'Saving…' : 'Submit' }}
</button>
```

A disabled button alone is not a guard: Enter-key submits and programmatic calls still run. Start the handler
with `if (this.saving()) return;`.
