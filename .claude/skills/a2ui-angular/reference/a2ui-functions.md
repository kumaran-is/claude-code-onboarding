# A2UI Functions Reference

A2UI components can use **declarative functions** inside property value objects instead of (or wrapping) raw literals or paths. Functions allow validation, formatting, and logic to be expressed in JSON — the agent declares the intent; the renderer evaluates it.

## How Functions Work

Instead of `{"literalString": "..."}` or `{"path": "/..."}`, a value object uses `{"call": {...}}`:

```json
{
  "call": {
    "name": "formatCurrency",
    "args": [{"path": "/booking/totalPrice"}, {"literalString": "USD"}],
    "returnType": "string"
  }
}
```

Functions are **evaluated by the renderer**, not the agent. The agent sends a call descriptor; the client executes the named function using its own implementation. No agent-provided code is executed.

---

## Validation Functions

Used in `TextField`, `ChoicePicker`, `DateTimeInput` to enforce input rules before submitting an action.

| Function | Signature | Description |
|----------|-----------|-------------|
| `required` | `required(value)` | Fails if value is null, empty string, or undefined |
| `regex` | `regex(value, pattern)` | Fails if value does not match the regex pattern string |
| `length` | `length(value, min, max)` | Fails if string length is outside [min, max] |
| `numeric` | `numeric(value, min?, max?)` | Fails if value is not a number, optionally within range |
| `email` | `email(value)` | Fails if value is not a valid email format |

**Example — email field with validation:**
```json
{
  "id": "email-field",
  "component": {
    "type": "TextField",
    "label": {"literalString": "Email"},
    "text": {"path": "/user/email"},
    "validation": {
      "call": {
        "name": "email",
        "args": [{"path": "/user/email"}],
        "returnType": "boolean"
      }
    }
  }
}
```

---

## Formatting Functions

Used in `Text` components to display values in locale-aware or structured formats.

| Function | Signature | Description |
|----------|-----------|-------------|
| `formatString` | `formatString(template, ...args)` | String interpolation: `"Hello, {0}!"` with arg substitution |
| `formatNumber` | `formatNumber(value, decimalPlaces?)` | Locale-aware number formatting |
| `formatCurrency` | `formatCurrency(value, currencyCode)` | Formats as currency: `"$1,234.56"` for `USD` |
| `formatDate` | `formatDate(value, pattern?)` | Date formatting — ISO 8601 input, pattern like `"MMM d, yyyy"` |
| `pluralize` | `pluralize(count, singular, plural)` | `"1 item"` vs `"3 items"` |

**Example — price display:**
```json
{
  "id": "price-text",
  "component": {
    "type": "Text",
    "text": {
      "call": {
        "name": "formatCurrency",
        "args": [{"path": "/booking/totalPrice"}, {"literalString": "USD"}],
        "returnType": "string"
      }
    }
  }
}
```

**Example — pluralized count:**
```json
{
  "id": "results-count",
  "component": {
    "type": "Text",
    "text": {
      "call": {
        "name": "pluralize",
        "args": [
          {"path": "/results/count"},
          {"literalString": "result"},
          {"literalString": "results"}
        ],
        "returnType": "string"
      }
    }
  }
}
```

---

## Logical Functions

Used in component `visible` or `disabled` properties to conditionally show/hide or enable/disable components.

| Function | Signature | Description |
|----------|-----------|-------------|
| `and` | `and(...booleans)` | True if all args are truthy |
| `or` | `or(...booleans)` | True if any arg is truthy |
| `not` | `not(boolean)` | Logical negation |

**Example — show submit only when both fields filled:**
```json
{
  "id": "submit-btn",
  "component": {
    "type": "Button",
    "label": {"literalString": "Submit"},
    "disabled": {
      "call": {
        "name": "not",
        "args": [{
          "call": {
            "name": "and",
            "args": [
              {"call": {"name": "required", "args": [{"path": "/user/name"}], "returnType": "boolean"}},
              {"call": {"name": "required", "args": [{"path": "/user/email"}], "returnType": "boolean"}}
            ],
            "returnType": "boolean"
          }
        }],
        "returnType": "boolean"
      }
    }
  }
}
```

---

## Navigation Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `openUrl` | `openUrl(url)` | Opens the URL in a new browser tab — renderer validates URL protocol before executing |

**Security:** `openUrl` uses the same `A2UISanitizerService.sanitizeUrl()` as `[src]`/`[href]` (`https:` only AND an allowlisted host — `a2ui-renderer-patterns.md`). Never call `window.open()` with an agent-provided URL that has not passed it.

---

## Angular Implementation Pattern

Register function evaluators in the renderer. Use a dedicated `A2UIFunctionService` (illustrative — not compiled; `A2UISanitizerService` is the one in `a2ui-renderer-patterns.md`):

```typescript
import { ErrorHandler, Injectable, inject } from '@angular/core';
import { A2UISanitizerService } from './a2ui-sanitizer.service';

@Injectable({ providedIn: 'root' })
export class A2UIFunctionService {
  private readonly errorHandler = inject(ErrorHandler);
  private readonly sanitizer = inject(A2UISanitizerService);
  private readonly ALLOWED_FUNCTIONS = new Set([
    'required', 'regex', 'length', 'numeric', 'email',
    'formatString', 'formatNumber', 'formatCurrency', 'formatDate', 'pluralize',
    'and', 'or', 'not', 'openUrl',
  ]);

  evaluate(call: A2UIFunctionCall, dataModel: Record<string, unknown>): unknown {
    if (!this.ALLOWED_FUNCTIONS.has(call.name)) {
      this.errorHandler.handleError(new Error(`A2UI: unknown function "${call.name}" rejected`));
      return null;
    }
    const args = call.args.map(a => this.resolveArg(a, dataModel));
    return this.dispatch(call.name, args);
  }

  private resolveArg(arg: A2UIValue, dataModel: Record<string, unknown>): unknown {
    if ('literalString' in arg) return arg.literalString;
    if ('path' in arg) return this.resolvePath(arg.path, dataModel);
    if ('call' in arg) return this.evaluate(arg.call, dataModel);
    return null;
  }

  private dispatch(name: string, args: unknown[]): unknown {
    switch (name) {
      case 'required': return args[0] != null && args[0] !== '';
      case 'email': return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(args[0]));
      case 'formatCurrency': return new Intl.NumberFormat('en-US', { style: 'currency', currency: String(args[1]) }).format(Number(args[0]));
      case 'formatDate': return new Date(String(args[0])).toLocaleDateString();
      case 'pluralize': return Number(args[0]) === 1 ? args[1] : args[2];
      case 'and': return args.every(Boolean);
      case 'or': return args.some(Boolean);
      case 'not': return !args[0];
      case 'openUrl': {
        const url = this.sanitizer.sanitizeUrl(args[0]);
        if (!url) { this.errorHandler.handleError(new Error('A2UI: openUrl blocked a URL outside the allowlist')); return; }
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
      }
      // ... add remaining implementations
      default: return null;
    }
  }

  private resolvePath(path: string, dataModel: Record<string, unknown>): unknown {
    return path.replace(/^\//, '').split('/').reduce<unknown>((obj, key) =>
      (obj as Record<string, unknown>)?.[key], dataModel);
  }
}
```

**Key rule:** The function allowlist in `A2UIFunctionService` is a security boundary — just like the component type allowlist in `A2UICatalogService`. Never evaluate a function name not in `ALLOWED_FUNCTIONS`.
