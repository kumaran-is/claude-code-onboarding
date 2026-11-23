# Angular UI Patterns References

| Reference | Contents | Load When |
|-----------|----------|-----------|
| [loading-control-flow.md](loading-control-flow.md) | Canonical load-state union from a resource (error → hasValue → value), loading vs reloading, idle params, skeleton vs spinner, @if/@for/@defer | Building any async list or page |
| [error-handling.md](error-handling.md) | Typed `ApiError`/`toApiError`, 401 vs 403 UX, error hierarchy, Logger + toast pattern, error-state component | Adding error handling to a component |
| [button-empty-states.md](button-empty-states.md) | Button loading states, in-flight guard, empty state component | Adding buttons or collections |
| [form-dialog-patterns.md](form-dialog-patterns.md) | Typed reactive form with in-flight guard and server errors; confirm dialog that stays open while the mutation runs | Building forms or confirmation flows |
| [anti-patterns.md](anti-patterns.md) | What NOT to do for loading, error, button states | Reviewing a component for mistakes |
