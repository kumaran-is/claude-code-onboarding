# Button State Patterns & Empty States

## Button State Patterns

### Button Loading State

```html
<button
  (click)="handleSubmit()"
  [disabled]="isSubmitting() || !form.valid"
  class="btn-primary"
>
  @if (isSubmitting()) {
  <app-spinner size="small" class="mr-2" />
  Saving... } @else { Save Changes }
</button>
```

### Disable During Operations

**CRITICAL: Always disable triggers during async operations.**

```typescript
// CORRECT - Button disabled while saving AND the handler guards re-entry
@Component({
  template: `
    <button type="button" [disabled]="saving()" (click)="save()">
      @if (saving()) {
        <span class="loading loading-spinner loading-sm" aria-hidden="true"></span> Saving…
      } @else {
        Save
      }
    </button>
  `
})
export class SaveButton {
  private readonly api = inject(SettingsApi);
  private readonly toast = inject(ToastService);
  private readonly logger = inject(Logger);
  readonly saving = signal(false);

  async save(): Promise<void> {
    if (this.saving()) return; // disabled is not a guard: Enter keys and programmatic calls still arrive
    this.saving.set(true);
    try {
      await firstValueFrom(this.api.save());
      this.toast.success('Settings saved.');
    } catch (err) {
      this.logger.error('save settings failed', err);
      this.toast.error('Settings could not be saved. Try again.');
    } finally {
      this.saving.set(false);
    }
  }
}

// ❌ WRONG - User can click multiple times
<button (click)="save()">
  {{ saving() ? 'Saving...' : 'Save' }}
</button>
```

---

## Empty States

### Empty State Requirements

Every list/collection MUST have an empty state:

```html
@for (item of items(); track item.id) {
<app-item-card [item]="item" />
} @empty {
<app-empty-state
  icon="folder-open"
  title="No items yet"
  description="Create your first item to get started"
  actionLabel="Create Item"
  (action)="openCreateDialog()"
/>
}
```

### Contextual Empty State Component

```typescript
@Component({
  selector: "app-empty-state",
  template: `
    <div class="empty-state">
      <span class="icon" [class]="icon()"></span>
      <h3>{{ title() }}</h3>
      <p>{{ description() }}</p>
      @if (actionLabel()) {
        <button type="button" (click)="action.emit()" class="btn btn-primary">
          {{ actionLabel() }}
        </button>
      }
    </div>
  `,
})
export class EmptyStateComponent {
  icon = input("inbox");
  title = input.required<string>();
  description = input("");
  actionLabel = input<string | null>(null);
  action = output<void>();
}
```
