# A2UI State Binding — Processor, Surfaces and Data Model

Verified against `a2ui_flutter` 0.4.0 and `a2ui_core` 0.8.0 on protocol v0.9. Every Dart block here compiles in a check app (`flutter analyze` exit 0) and the behaviour described is covered by `flutter test`.

## Overview

| Piece | Type | Owns |
|---|---|---|
| Processor | `MessageProcessor<ComponentImplementation>` | Registered catalogs, version adapters, all surfaces (`processor.model`) |
| Surface group | `processor.model` (`SurfaceGroupModel`) | `onSurfaceCreated`, `onSurfaceDeleted`, `onAction`, `onError`, `allSurfaces` |
| Surface | `SurfaceModel<ComponentImplementation>` | `id`, `dataModel`, `componentsModel`, `sendDataModel`, `protocolVersion`, theme |
| Data model | `DataModel` | One JSON document per surface, addressed by JSON Pointer |
| Renderer | `A2uiSurface(surface:)` | Widgets for one surface; rebuilds what a data change affects |

The agent never touches widgets. It sends messages; the processor validates and applies them; `A2uiSurface` renders the result.

## The processor and its surfaces

One processor per conversation, disposed with it. This widget renders every surface the agent creates, removes deleted ones, forwards actions and shows rejected payloads:

```dart
import 'dart:developer' as developer;

import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:a2ui_flutter/v0_9/basic_catalog.dart';
import 'package:flutter/material.dart';

/// Renders every surface an agent creates, on protocol v0.9, with the basic catalog.
class AgentSurfaces extends StatefulWidget {
  const AgentSurfaces({super.key, required this.onAction});

  /// Called with each user action; forward it to the agent.
  final void Function(A2uiRendererAction action) onAction;

  @override
  State<AgentSurfaces> createState() => AgentSurfacesState();
}

class AgentSurfacesState extends State<AgentSurfaces> {
  final MessageProcessor<ComponentImplementation> processor = MessageProcessor(
    catalogs: [basicCatalog()],
    defaultVersion: A2uiProtocolVersion.v0_9,
  );
  final List<SurfaceModel<ComponentImplementation>> _surfaces = [];
  String? _errorCode;

  @override
  void initState() {
    super.initState();
    processor.model.onSurfaceCreated.subscribe(
      (surface) => setState(() => _surfaces.add(surface)),
    );
    processor.model.onSurfaceDeleted.subscribe(
      (id) => setState(() => _surfaces.removeWhere((s) => s.id == id)),
    );
    processor.model.onAction.subscribe(widget.onAction);
  }

  /// Applies one decoded payload from the agent: a list of v0.9 messages.
  void receive(Object? messages) {
    try {
      processor.processMessages(messages);
    } on A2uiError catch (error) {
      developer.log('${error.code}: ${error.message}', name: 'a2ui');
      setState(() => _errorCode = error.code); // visible, never swallowed
    }
  }

  @override
  void dispose() {
    processor.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16), // ignore-design: replace with the app's spacing token
      children: [
        if (_errorCode case final code?)
          Text('The assistant sent a screen this app cannot show ($code).'),
        for (final surface in _surfaces)
          // A ListView item merges its children's semantics into one node;
          // this boundary keeps each control (text field, button) its own node.
          Semantics(
            key: ObjectKey(surface),
            container: true,
            explicitChildNodes: true,
            child: A2uiSurface(surface: surface),
          ),
      ],
    );
  }
}
```

Rules:

- **Key each surface with `ObjectKey(surface)`.** A surface deleted and re-created with the same id is a new object, so its widget state is not reused.
- **`processMessages` throws `A2uiError`** (subclasses include `A2uiValidationError` and `A2uiDataError`); each carries `code` (for example `CATALOG_NOT_FOUND`, `SCHEMA_VALIDATION_FAILED`, `VALIDATION_FAILED`) and `message`. Log both and show an error state.
- **Errors during rendering** (a function that fails, a bad binding) arrive on `processor.model.onError` as `A2uiRendererError`, or through the `onError:` constructor callback. Show or report them; with `unifiedOutbound: true` they also reach `outboundListener` for sending to the agent.
- **Unsubscribe** with the `Subscription` that `subscribe` returns (`unsubscribe()`) when the listener's owner is disposed before the processor, as the Riverpod example below does.

### Accessibility boundary (proven)

A `ListView` item merges its children's semantics. Without the `Semantics(container: true, explicitChildNodes: true)` wrapper, a surface's text field node took the labels of the heading and button around it, and Maestro's tap on the field's label landed on the merged node, so typed text was lost. With the wrapper, `tester.getSemantics(find.byType(EditableText)).label` is exactly the field's label. This is general Flutter behaviour (a plain `Column` in a `ListView` does the same), so apply it wherever surfaces sit in a scrolling list.

## Data model

Each surface has its own `DataModel`, created by `createSurface` and changed by `updateDataModel` messages and by user input.

```json
{"version": "v0.9", "updateDataModel": {"surfaceId": "signup", "value": {"email": "", "stars": 3}}}
{"version": "v0.9", "updateDataModel": {"surfaceId": "list", "path": "/items/1/name", "value": "Shed"}}
```

- Without `path`, `value` replaces the whole model (the processor calls `dataModel.set('/', value)`). With `path`, only that JSON Pointer location changes, and only components bound under it rebuild. A v0.9 message that omits `value` deletes the key at `path`.
- Paths are JSON Pointers: `/email`, `/items/0/name`. List indexes are numbers.
- App code reads and writes with `surface.dataModel.get('/email')`, `surface.dataModel.set('/photoUrl', url)` and `surface.dataModel.delete('/draft')`. `subscribe<T>(path, onChange)` returns a `DataSubscription<T>` with `value` and `unsubscribe()`.
- `set` throws `A2uiDataError` when a path cannot exist (for example a property of a string). Catch it, log it, keep the old value.

### Binding components

A component property is a literal, a binding or a function call:

| Form | JSON | Resolves to |
|---|---|---|
| Literal | `"text": "Hello"` | the literal |
| Binding | `"value": {"path": "/email"}` | the data at `/email`, live |
| Function call | `{"call": "formatCurrency", "args": {...}}` | the function result, re-evaluated when its inputs change (see `genui-functions.md`) |

Input components write back through their binding: a TextField bound to `/email` sets `/email` on every keystroke, so a later Button action whose `context` reads `{"path": "/email"}` gets what the user typed. This is tested end to end: typed `ada@example.com`, tapped Subscribe, the action's `context` was `{"email": "ada@example.com"}`.

A literal value is read-only: the component cannot write it back (`ComponentProps.writable` returns null for it; see `genui-custom-widgets.md`).

### Templated lists

`children` is either a list of component ids or a template over a data list:

```json
{"id": "root", "component": "List", "children": {"componentId": "item", "path": "/items"}},
{"id": "item", "component": "Text", "text": {"path": "name"}}
```

The `item` component renders once per element of `/items`. Inside the template a path without a leading `/` is relative to the current element, so `name` reads `/items/0/name`, `/items/1/name`, and so on. Updating `/items/1/name` re-renders only that row (tested).

### Sending the data model to the agent

A surface created with `"sendDataModel": true` includes its data model in what the renderer reports to the agent. Read it with `processor.getRendererDataModel(version: A2uiProtocolVersion.v0_9)` and send it as `a2uiClientDataModel` (see `genui-a2ui-transport.md`). Only ask for this on surfaces whose data the agent needs, and never put secrets or tokens in a data model: it is agent-visible state.

## Riverpod (optional)

Riverpod is not required. If the app uses it, own the processor in a provider so it is disposed with the scope, and expose the surface list from a `Notifier`:

```dart
import 'package:a2ui_core/a2ui_core.dart';
import 'package:a2ui_flutter/a2ui_flutter.dart';
import 'package:a2ui_flutter/v0_9/basic_catalog.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// One processor per conversation, disposed with the provider.
final a2uiProcessorProvider =
    Provider<MessageProcessor<ComponentImplementation>>((ref) {
      final processor = MessageProcessor<ComponentImplementation>(
        catalogs: [basicCatalog()],
        defaultVersion: A2uiProtocolVersion.v0_9,
      );
      ref.onDispose(processor.dispose);
      return processor;
    });

/// The surfaces currently shown, in creation order.
final a2uiSurfacesProvider =
    NotifierProvider<A2uiSurfaces, List<SurfaceModel<ComponentImplementation>>>(
      A2uiSurfaces.new,
    );

class A2uiSurfaces
    extends Notifier<List<SurfaceModel<ComponentImplementation>>> {
  @override
  List<SurfaceModel<ComponentImplementation>> build() {
    final MessageProcessor<ComponentImplementation> processor = ref.watch(
      a2uiProcessorProvider,
    );
    final Subscription created = processor.model.onSurfaceCreated.subscribe(
      (surface) => state = [...state, surface],
    );
    final Subscription deleted = processor.model.onSurfaceDeleted.subscribe(
      (id) => state = [
        for (final surface in state)
          if (surface.id != id) surface,
      ],
    );
    ref.onDispose(() {
      created.unsubscribe();
      deleted.unsubscribe();
    });
    return const [];
  }
}
```

Compiled with `flutter_riverpod: 3.5.0`. Keep the surface's own data in its `DataModel`; do not mirror it into Riverpod state, or the two drift.

## Testing

Widget tests (`flutter test`) that the check app runs and passes:

```dart
testWidgets('typed input reaches the action context', (tester) async {
  final actions = <A2uiRendererAction>[];
  final host = GlobalKey<AgentSurfacesState>();
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: AgentSurfaces(key: host, onAction: actions.add),
      ),
    ),
  );
  host.currentState!.receive(signupForm()); // createSurface, updateDataModel, updateComponents
  await tester.pumpAndSettle();

  await tester.enterText(find.byType(TextField), 'ada@example.com');
  await tester.tap(find.text('Subscribe'));
  await tester.pumpAndSettle();

  expect(actions.single.name, 'subscribe');
  expect(actions.single.context, {'email': 'ada@example.com'});
});
```

Cover at least: a surface renders; input → data model → action context; `updateDataModel` re-renders; `deleteSurface` removes the surface; an unregistered catalog is shown as an error, not rendered; each control keeps its own semantics node (`tester.ensureSemantics()` + `tester.getSemantics`).
