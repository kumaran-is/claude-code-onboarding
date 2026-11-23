# A2UI Custom Components (v0.9)

First verified against `a2ui_flutter` 0.4.0 and `a2ui_core` 0.8.0. Both examples compile in a check app (`flutter analyze` exit 0). The Rating component was also run on an iOS simulator with a Maestro flow (positive flow exit 0; a negative flow expecting the wrong reply exits 1). Re-compiled on 2026-11-23 with `a2ui_flutter` 0.5.0, `a2ui_core` 0.9.0, `a2ui_agent` 0.5.0 and `material_ui` 1.11.1 on Flutter 3.50.1 / Dart 3.14.0 (`flutter analyze` 0 issues across every block in this skill; the widget tests pass). The 1.0 path is in `../SKILL.md` "Versioned adapter boundary".

## Overview

A custom component is a `ComponentImplementation`: a name the agent writes, a JSON schema the processor validates against, and a builder that returns a Flutter widget. Register it in a catalog with the basic components (`genui-catalog-design.md`).

```
agent JSON ──► processor (schema check, binding resolution) ──► builder(context, node, props, buildChild) ──► Widget
                                                                     │
                                       user input ──► props.writable(key).set(...)  ──► data model
                                       user tap   ──► props.action(key)()           ──► onAction / functionCall
```

## The builder

`builder: (BuildContext context, ComponentNode<ComponentImplementation> node, ComponentProps props, ChildWidgetBuilder buildChild)`

| `ComponentProps` member | Returns |
|---|---|
| `string(key)`, `number(key)`, `boolean(key)`, `value(key)` | The resolved value (literal, binding or function result), or null |
| `list(key)` | The resolved value as a `List<Object?>` |
| `writable(key)` | A `WritableBinding` when the property is a `{"path"}` binding, null for a literal. `set(value)` writes the data model and throws `A2uiDataError` if the path cannot hold it |
| `action(key)` | A `NodeAction` (`Future<void> Function([ActionDispatchOptions?])`) for an `action` property, or null |
| `child(key)`, `children(key)` | The child `ComponentNode` (or null) / the list of child nodes; render each with `buildChild(node)` |
| `isValid`, `validationErrors`, `validationResults` | The result of the component's `checks` |

The builder runs again when a value it read changes. Keep it pure: read props, return widgets, and do I/O only in response to a user gesture.

## Example 1 — Rating (input with write-back)

```dart
import 'dart:developer' as developer;

import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:material_ui/material_ui.dart';
import 'package:json_schema_builder/json_schema_builder.dart'
    hide ValidationResult;

/// A 1-5 star rating bound to a data model path.
final ComponentImplementation rating = ComponentImplementation(
  name: 'Rating',
  schema: Schema.object(
    description: 'A 1 to 5 star rating. Bind value to a number path.',
    properties: {
      'label': CommonSchemas.dynamicString,
      'value': CommonSchemas.dynamicNumber,
    },
    required: ['value'],
  ),
  builder: (context, node, props, buildChild) {
    final WritableBinding<Object?>? value = props.writable('value');
    final int current = (props.number('value') ?? 0).round().clamp(0, 5);
    // container: true gives the rating its own semantics node; without it the
    // label and value merge into whatever node encloses the surface.
    return Semantics(
      container: true,
      label: props.string('label') ?? 'Rating',
      value: '$current of 5',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var star = 1; star <= 5; star++)
            IconButton(
              tooltip: 'Rate $star',
              icon: Icon(star <= current ? Icons.star : Icons.star_border),
              onPressed: value == null
                  ? null // a literal value is read-only
                  : () {
                      try {
                        value.set(star);
                      } on A2uiDataError catch (error) {
                        developer.log(
                          '${error.code}: ${error.message}',
                          name: 'a2ui',
                        );
                      }
                    },
            ),
        ],
      ),
    );
  },
);
```

The agent uses it like a basic component:

```json
{"id": "interest", "component": "Rating", "label": "Interest", "value": {"path": "/stars"}}
```

A Button whose action `context` reads `{"path": "/stars"}` then receives the tapped value. Tested: tapping "Rate 5" set `/stars` to 5, and the Subscribe action's context was `{"email": "ada@example.com", "stars": 5}`. A negative control (builder without `value.set`) fails that test.

## Example 2 — PhotoRequest (app-owned I/O behind an action)

A component must not capture, upload or fetch on its own: the agent decides when it is shown, so any I/O in the builder would run on the agent's say-so. The component runs the agent-declared action on a tap; the app, which owns camera permission, size and type checks and the upload, answers the action and writes the result back.

```dart
import 'dart:async';

import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:material_ui/material_ui.dart';
import 'package:json_schema_builder/json_schema_builder.dart'
    hide ValidationResult;

/// A custom component that asks for a photo. It does no I/O itself: the tap
/// runs the agent-declared action, and the app (which owns the camera and
/// upload code) answers that action and writes the result to the data model.
final ComponentImplementation photoRequest = ComponentImplementation(
  name: 'PhotoRequest',
  schema: Schema.object(
    description: 'Asks the user for a photo. The app captures and uploads it.',
    properties: {
      'label': CommonSchemas.dynamicString,
      'photoUrl': CommonSchemas.dynamicString,
      'onRequest': CommonSchemas.action,
    },
    required: ['label', 'onRequest'],
  ),
  builder: (context, node, props, buildChild) {
    final String label = props.string('label') ?? 'Add a photo';
    final String? photoUrl = props.string('photoUrl');
    final NodeAction? request = props.action('onRequest');
    return Semantics(
      container: true,
      child: OutlinedButton.icon(
        icon: Icon(photoUrl == null ? Icons.add_a_photo : Icons.check_circle),
        label: Text(photoUrl == null ? label : '$label (added)'),
        // Run the action synchronously inside the tap handler.
        onPressed: request == null ? null : () => unawaited(request()),
      ),
    );
  },
);

/// App side: handle the action, then write the uploaded URL back.
Future<void> onPhotoRequested(
  SurfaceModel<ComponentImplementation> surface,
  Future<Uri?> Function() captureAndUpload,
) async {
  final Uri? url =
      await captureAndUpload(); // permissions, size and type checks live here
  if (url != null) surface.dataModel.set('/photoUrl', url.toString());
}
```

In the app's `onAction` handler, match the event name (for example `photo_requested`) against the app's allowlist, find the surface by `action.surfaceId` in `processor.model.allSurfaces`, and call `onPhotoRequested`. The same pattern fits a dropdown backed by app data, a signature pad or a document picker.

## Accessibility (required for every custom component)

| Rule | Why |
|---|---|
| Wrap the component in `Semantics(container: true, label:, value:)` | Without `container: true` its label and value merged into the enclosing node; tested with a negative control |
| Give icon-only controls a `tooltip` | It becomes the accessible name (`Rate 5`) and a stable Maestro target |
| Touch targets ≥ 48dp | Material `IconButton` / `OutlinedButton` meet it by default; do not shrink them |
| Announce changed values in `value`, not only in the icon state | Screen readers read `3 of 5`, not three star glyphs |
| Use theme colours and the app's spacing tokens | No hardcoded colours or raw spacing in production components |

The host must also wrap each `A2uiSurface` in a `Semantics(container: true, explicitChildNodes: true)` boundary (`genui-state-binding.md`).

## Testing custom components

`flutter test` widget tests:

```dart
testWidgets('the custom Rating is its own semantics node with label and value',
    (tester) async {
  final handle = tester.ensureSemantics();
  await tester.pumpWidget(const ProbeApp()); // renders a surface using Rating
  await tester.pumpAndSettle();
  final node = tester.getSemantics(find.bySemanticsLabel('Interest'));
  expect(node.label, 'Interest');
  expect(node.value, '3 of 5');
  handle.dispose();
});
```

Also test: tapping a star writes the bound path (check the next action's `context` or `surface.dataModel.get`); a literal `value` renders read-only (`onPressed` null); a missing required property is rejected by `processMessages`.

Device E2E on Android/iOS uses Maestro only. This flow passed on an iOS simulator (only `appId` changed here):

```yaml
appId: com.example.app
---
- launchApp:
    clearState: true
- extendedWaitUntil:      # debug builds need time for the first frame
    visible: "Subscribe"
    timeout: 30000
- tapOn:
    text: "Email"         # the field's exact label
- inputText: "ada@example.com"
- tapOn: "Rate 5"         # the IconButton tooltip
- assertVisible: "5 of 5"
- tapOn: "Subscribe"
- extendedWaitUntil:
    visible: ".*Subscribed: ada@example.com \\(5 stars\\).*"
    timeout: 10000
```

On iOS, `hideKeyboard` failed with a Flutter text field; tap a target above the keyboard instead.
