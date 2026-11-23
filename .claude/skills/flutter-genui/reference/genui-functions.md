# A2UI Declarative Functions (v0.9)

Verified against `a2ui_core` 0.8.0 (`lib/src/basic_catalog/v0_9/catalog.g.dart` and `functions.dart`). The examples below are exercised by `flutter test` in a check app.

## How it works

An agent never sends code. Where a property accepts a dynamic value, it may send a **function call** that names a function the surface's catalog declares:

```json
{"call": "formatCurrency", "args": {"value": {"path": "/total"}, "currency": "USD"}}
```

- `args` values are literals, `{"path"}` bindings or nested calls.
- The renderer evaluates the call and re-evaluates it when a bound input changes.
- **The catalog's function list is the allowlist.** The v0.9 basic catalog supplies 14 functions, implemented in `a2ui_core`; apps do not write a function evaluator. A custom catalog includes them with `BasicCatalog.v0_9().functions.values.toList()`, or a filtered subset.
- With a strict `validationConfig`, a call to a function the catalog does not declare is rejected when the payload is processed (tested with a catalog that omits `openUrl`, plus a positive control against the full catalog).

## The 14 v0.9 basic functions

### Validation (return `boolean`)

| Function | Args | True when |
|---|---|---|
| `required` | `value` | the value is not null or empty |
| `regex` | `value`, `pattern` | the value matches the pattern |
| `length` | `value`, `min` and/or `max` | the string length is within bounds |
| `numeric` | `value`, `min` and/or `max` | the number is within bounds |
| `email` | `value` | the value is a valid email address |

### Formatting (return `string`)

| Function | Args | Notes |
|---|---|---|
| `formatString` | `value` | Interpolates `${/absolute/path}`, `${relative/path}` and `${call(arg:...)}` expressions; escape a literal `${` as `\${` |
| `formatNumber` | `value`, optional `decimals`, `grouping` | Uses the catalog's `locale` |
| `formatCurrency` | `value`, `currency`, optional `decimals`, `grouping` | `1234.5` + `USD` → `$1,234.50` in `en-US` (tested) |
| `formatDate` | `value`, `format` | `format` is a date pattern |
| `pluralize` | `value`, `other`, optional `zero`, `one`, `two`, `few`, `many` | Plural category for the locale |

The locale is the one passed to `basicCatalog(locale: ...)`, `en-US` by default.

### Logic (return `boolean`)

| Function | Args |
|---|---|
| `and` | `values`: a list |
| `or` | `values`: a list |
| `not` | `value` |

`and`, `or` and `not` read plain truthiness, so a bound boolean (`{"path": "/agree"}`) or a validation call both work as operands.

### Navigation (return `void`)

| Function | Args | Behaviour |
|---|---|---|
| `openUrl` | `url` | Hands a validated `http`, `https`, `mailto` or `tel` URL to the `openUrl:` callback of `basicCatalog`; rejects `javascript:`, `file:` and relative URLs; **fails if no callback was passed** |

On v0.9 a bound `openUrl` call runs whenever it resolves, without a tap. See `genui-security.md` before passing a callback.

## Checks: validation on inputs and buttons

Inputs and Button take `checks`: a list of `{condition, message}`. A failing check on an input shows `message` under it; a failing check on a Button disables it.

```json
{"id": "email", "component": "TextField", "label": "Email", "value": {"path": "/email"},
 "checks": [{"condition": {"call": "email", "args": {"value": {"path": "/email"}}}, "message": "Enter a valid email address."}]}
```

Validation-gated submit (tested: disabled until a valid email is typed **and** the checkbox is ticked; then the tap reaches `onAction`):

```json
{"id": "submit", "component": "Button", "variant": "primary", "child": "submit_label",
 "checks": [{
   "condition": {"call": "and", "args": {"values": [
     {"call": "email", "args": {"value": {"path": "/email"}}},
     {"path": "/agree"}
   ]}},
   "message": "Enter an email and accept the terms."
 }],
 "action": {"event": {"name": "send"}}}
```

Client checks are for the user's benefit. The agent or API that receives the action must validate the same values again: the payload came from an agent, and the request can be forged.

## Formatting example

```json
{"id": "total", "component": "Text",
 "text": {"call": "formatCurrency", "args": {"value": {"path": "/total"}, "currency": "USD"}}}
```

With `/total` = `1234.5` and the default locale this renders `$1,234.50`, and re-renders when `/total` changes.

## Restricting functions

Build a catalog with a filtered function list to remove a function entirely:

```dart
functions: [
  for (final function in BasicCatalog.v0_9().functions.values)
    if (function.name != 'openUrl') function,
],
```

The full locked-down catalog is in `genui-security.md`.

## Security rule

Functions are part of the catalog contract, not an extension point for the agent. Do not add a custom function that performs I/O, navigation or anything with side effects on the agent's say-so; route such work through an action the app handles and allowlists.
