# A2UI Catalog Design (v0.9)

First verified against `a2ui_flutter` 0.4.0 and `a2ui_core` 0.8.0. Dart blocks compile in a check app; the behaviour is covered by `flutter test`. Re-compiled on 2026-11-23 with `a2ui_flutter` 0.5.0, `a2ui_core` 0.9.0, `a2ui_agent` 0.5.0 and `material_ui` 1.11.1 on Flutter 3.50.1 / Dart 3.14.0 (`flutter analyze` 0 issues across every block in this skill; the widget tests pass). The 1.0 path is in `../SKILL.md` "Versioned adapter boundary".

## Overview

A catalog is the contract between agent and app: the component names, their JSON schemas, the Flutter builders, and the functions a surface may call. The agent names a catalog in `createSurface` (`catalogId`); the processor accepts only catalogs registered with it and only components and functions those catalogs declare. **The registered catalogs are the allowlist.**

A v0.9 surface uses exactly one catalog. To add a custom component, build one catalog that holds the basic components and functions you need plus your own.

## The v0.9 basic catalog

```dart
import 'package:a2ui_flutter/v0_9/basic_catalog.dart';

final catalog = basicCatalog(); // id: BasicCatalog.v0_9Id
```

- Id: `BasicCatalog.v0_9Id` = `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json`.
- `basicCatalog({locale, openUrl})`: `locale` drives the formatting functions (`en-US` by default); `openUrl` is the callback for the `openUrl` function, which fails without one (see `genui-security.md`).
- 18 components, each also available on its own as a `BasicComponents` member (`BasicComponents.text`, `.textField`, …) and all together as `BasicComponents.all`:

| Group | Components |
|---|---|
| Layout | `Row`, `Column`, `List`, `Card`, `Tabs`, `Modal`, `Divider` |
| Content | `Text` (variants `h1`–`h5`, `body`, `caption`), `Image`, `Icon`, `Video`, `AudioPlayer` |
| Input | `Button`, `TextField` (with `checks` and `validationRegexp`), `CheckBox`, `ChoicePicker`, `Slider`, `DateTimeInput` |

- `BasicComponents.api` is the v0.9 catalog API (`themeSchema`, `definitions`).
- Image, Video and AudioPlayer load any `http` or `https` URL the agent names. For an agent you do not control, leave them out (see the locked-down catalog in `genui-security.md`).
- Text renders without Markdown markers unless an `A2uiMarkdown` wrapper supplies a Markdown widget.

## Your own v0.9 catalog

```dart
/// The app's id for its catalog. The agent names it in `createSurface`.
const String appCatalogId = 'https://example.com/app/v0_9/catalog.json';

/// A v0.9 surface has one catalog, so the app catalog carries the basic
/// components and functions it needs plus its own components.
final CatalogImplementation appCatalog = CatalogImplementation(
  id: appCatalogId,
  components: [...BasicComponents.all, rating],
  functions: BasicCatalog.v0_9().functions.values.toList(),
  themeSchema: BasicComponents.api.themeSchema,
  definitions: BasicComponents.api.definitions,
);

final MessageProcessor<ComponentImplementation> processor = MessageProcessor(
  catalogs: [appCatalog],
  defaultVersion: A2uiProtocolVersion.v0_9,
);
```

`rating` is a `ComponentImplementation` (see `genui-custom-widgets.md`). Imports: `package:a2ui_core/a2ui_core.dart`, `package:a2ui_flutter/a2ui_flutter.dart`, `package:a2ui_flutter/v0_9/basic_catalog.dart`.

- **Catalog id** is a URI you own. Version it in the path (`/v0_9/`), and change it when you change a schema incompatibly, so an agent built against the old shape fails loudly instead of rendering wrongly.
- **Subset, don't fork.** List only the `BasicComponents` members and functions the feature needs. Fewer components means a shorter prompt for the model and a smaller attack surface.
- **Several catalogs** may be registered with one processor; each surface picks one by `catalogId`. The renderer's capabilities list every registered catalog (`genui-a2ui-transport.md`).

## Schema design

Component schemas use `json_schema_builder` (`Schema.object`, `Schema.string`, …) with the v0.9 dynamic types from `CommonSchemas`:

| `CommonSchemas` member | Accepts |
|---|---|
| `dynamicString`, `dynamicNumber`, `dynamicBoolean`, `dynamicStringList`, `dynamicValue` | a literal, a `{"path"}` binding, or a function call |
| `dataBinding` | a `{"path": "/x"}` binding only |
| `functionCall` | a `{"call", "args"}` function call |
| `componentId`, `childList` | one child id; a list of ids or a `{"componentId", "path"}` template |
| `action` | `{"event": {"name", "context"}}` or `{"functionCall": {...}}` |
| `checkable`, `checkRule` | `checks` rules with `condition` and `message` |
| `accessibilityAttributes`, `componentCommon` | shared attributes |

`CommonSchemasV1` is the v1.0 equivalent; do not use it in a v0.9 catalog.

1. **Describe intent in `description`.** The schema is what the model is taught; say what the component is for and what each property means ("A 1 to 5 star rating. Bind value to a number path.").
2. **Use the dynamic types for anything the agent may bind.** A plain `Schema.string()` accepts only a literal.
3. **Mark required properties** (`required: ['value']`). The processor rejects a component missing one before it renders.
4. **Bound numbers and lists.** Clamp in the builder too: a schema says what is valid, the builder must still survive a value at the edge (`.clamp(0, 5)`).
5. **Import with `hide ValidationResult`**: `json_schema_builder` and `a2ui_core` both export a `ValidationResult`.

```dart
import 'package:json_schema_builder/json_schema_builder.dart'
    hide ValidationResult;
```

## Granularity

| Too fine | Right size | Too coarse |
|---|---|---|
| The agent assembles every label, icon and spacer | Molecules and organisms: a rating, a photo request, a summary card | One component per screen with 20 properties |
| Long prompts, many round trips, inconsistent layouts | The agent composes meaning; the app owns layout details | The agent cannot adapt the UI to the conversation |

Expose a property only when the agent has a reason to change it. Start small, watch what the model writes in evals, and add properties when it repeatedly needs them.

## Testing catalogs

| Test | Expectation |
|---|---|
| A surface using each custom component renders | widget found |
| A component name the catalog does not declare | rejected with a strict `validationConfig` (`A2uiError`) |
| A surface naming an unregistered `catalogId` | `processMessages` throws; nothing renders |
| A required property missing | rejected |
| A locked-down catalog | the omitted component and function are rejected, and the same payload passes against the full catalog (positive control) |

See `genui-security.md` for the validation configs these tests use.
