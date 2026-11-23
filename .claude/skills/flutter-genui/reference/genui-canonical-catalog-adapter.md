# Canonical Catalog Adapter (Flutter, A2UI v0.9)

How a Flutter app renders the framework-neutral canonical GenUI catalog (owned by the `genui-contract` skill) behind an app-owned adapter, with a conventional fallback, typed bindings, canonical action payloads and both backend topologies.

Evidence (2026-11-23, Flutter 3.44.2; the kit declares Flutter 3.41.x, so re-run on your pinned SDK before relying on it; `a2ui_flutter` 0.4.0, `a2ui_core` 0.8.0, `http` 1.6.0, check app outside the repo):

| Check | Result |
|---|---|
| `flutter analyze` / `dart format --set-exit-if-changed` | 0 issues / exit 0 |
| `flutter test` offline (contract fixtures, action goldens, streams, reconnect, resync, 403, fallback, a11y guidelines) | 48/48 PASS |
| `flutter test` live against the reference backend, `shared-backend` and `standalone-backend` | 20/20 PASS (server log: 200, 202, 403, `stream_stopped` on cancel) |
| Negative controls (integer binding, guard removed, Last-Event-ID dropped, 10 px tap target, idempotency key dropped) | each run exits 1 |
| Maestro on iOS simulator / Android emulator | BLOCKED (see the end of this file) |

## Contents

- [Adapter boundary](#adapter-boundary)
- [Contract guard (before the SDK)](#contract-guard-before-the-sdk)
- [Catalog from the contract JSON](#catalog-from-the-contract-json)
- [Canonical id to widget mapping](#canonical-id-to-widget-mapping)
- [Theme adapter](#theme-adapter)
- [Typed data bindings](#typed-data-bindings)
- [Canonical action payloads](#canonical-action-payloads)
- [Conventional fallback](#conventional-fallback)
- [Backend topologies and transport](#backend-topologies-and-transport)
- [AG-UI and CopilotKit](#ag-ui-and-copilotkit)
- [Secrets](#secrets)
- [Tests](#tests)
- [What the SDK does not do](#what-the-sdk-does-not-do)

## Adapter boundary

Only one folder imports `a2ui_core` / `a2ui_flutter`. Screens, state management and tests talk to the adapter's own types, so an SDK upgrade (or a v1.0 migration) changes this folder and nothing else.

```
lib/features/<feature>/genui/          # the ONLY code that imports a2ui_core / a2ui_flutter
  canonical_contract.dart              # catalog id, wire version, limits, action allowlist, guard()
  canonical_catalog.g.dart             # generated: the contract's catalog JSON as a Dart const
  canonical_catalog.dart               # CatalogImplementation built from that JSON + 8 widget builders
  genui_theme.dart                     # GenUiTokens ThemeExtension (from ColorScheme)
  genui_session.dart                   # GenUiSession: apply(), failure, surfaces, canonical actions
  genui_transport.dart                 # BackendTopology, SSE client, action POST, AG-UI adapter
lib/features/<feature>/presentation/
  genui_screen.dart                    # surfaces + failure banner + conventional fallback
```

The public surface of the adapter:

| Type | Purpose |
|---|---|
| `GenUiSession` | `apply(message)` → `GenUiFailure?`; `finishStream()`; `failure`; `surfaceIds`; `surfaceView(id)`; `reset()`; `onAction` callback with `CanonicalAction` |
| `GenUiFailure(code, message)` | Contract error code (`UNKNOWN_COMPONENT`, `UNSUPPORTED_VERSION`, …) or transport code (`HTTP_403`, `STREAM_DROPPED`, `INCOMPLETE_FRAME`) |
| `CanonicalAction(payload, idempotencyKey)` | The canonical `{"version":"v0.9","action":{…}}` message and its out-of-band key |
| `A2uiStreamClient`, `AguiA2uiAdapter`, `GenUiBackend`, `BackendTopology` | Transport; the only part that differs between topologies |

The session keeps the processor private. It is created with the canonical catalog, `defaultVersion: A2uiProtocolVersion.v0_9` and a `ValidationConfig(maxDepth: 8, allowedMessages: [the four agent messages], allowDanglingReferences: true)`. Dangling references are allowed while a stream is open (the contract's progressive-render fixture sends a parent before its child); `finishStream()` reports any child that never arrived as `DANGLING_REFERENCE`.

## Contract guard (before the SDK)

`a2ui_core` 0.8.0 validates schemas and the component graph, but it does not enforce the canonical contract's wire rules. With the guard removed, 9 of the 20 invalid contract fixtures were accepted or reported with the wrong code (tested; see [What the SDK does not do](#what-the-sdk-does-not-do)). Run this guard on every decoded message first. Complete file, compiled in the check app:

```dart
import 'dart:convert';

/// The app's copy of the canonical catalog contract (A2UI v0.9).
abstract final class CanonicalContract {
  static const String catalogId =
      'https://catalogs.example.com/genui/canonical/v1/catalog.json';
  static const String wireVersion = 'v0.9';
  static const int maxMessageBytes = 262144;
  static const int maxDepth = 8;

  static const Set<String> agentMessageKinds = {
    'createSurface',
    'updateComponents',
    'updateDataModel',
    'deleteSurface',
  };

  /// Canonical component id -> actions that component may raise.
  static const Map<String, Set<String>> componentActions = {
    'ActionCard': {'item.open', 'item.dismiss'},
    'DataSummaryTable': {},
    'ApprovalForm': {'approval.approve', 'approval.reject'},
    'SelectionList': {'selection.submit'},
    'DetailPanel': {},
    'StatusIndicator': {},
    'InputForm': {'form.submit', 'form.cancel'},
    'ConfirmationDialog': {'dialog.confirm', 'dialog.cancel'},
  };

  /// Actions whose side effect needs an Idempotency-Key per user intent.
  static const Set<String> idempotentActions = {
    'item.dismiss',
    'approval.approve',
    'approval.reject',
    'selection.submit',
    'form.submit',
    'dialog.confirm',
  };

  static final List<RegExp> _forbidden = [
    RegExp(r'^\s*javascript:', caseSensitive: false),
    RegExp(r'^\s*vbscript:', caseSensitive: false),
    RegExp(r'^\s*data:text/html', caseSensitive: false),
    RegExp(r'<\s*script', caseSensitive: false),
  ];

  /// Returns the contract error code, or null when the message may be applied.
  static String? guard(Object? message) {
    if (message is! Map<String, Object?>) return 'MALFORMED_MESSAGE';
    final Object? version = message['version'];
    if (version is! String) return 'MALFORMED_MESSAGE';
    final List<String> bodies = [
      for (final key in message.keys)
        if (key != 'version') key,
    ];
    if (bodies.length != 1 || !agentMessageKinds.contains(bodies.single)) {
      return 'MALFORMED_MESSAGE';
    }
    if (version != wireVersion) return 'UNSUPPORTED_VERSION';
    if (utf8.encode(jsonEncode(message)).length > maxMessageBytes) {
      return 'MESSAGE_TOO_LARGE';
    }
    if (_anyString(message, (s) => _forbidden.any((p) => p.hasMatch(s)))) {
      return 'UNSAFE_CONTENT';
    }
    if (_anyKey(message, 'functionCall')) return 'FUNCTION_ACTION_FORBIDDEN';
    final Object? update = message['updateComponents'];
    if (update is Map<String, Object?>) {
      final Object? components = update['components'];
      if (components is! List<Object?>) return 'MALFORMED_MESSAGE';
      for (final component in components) {
        if (component is! Map<String, Object?>) return 'MALFORMED_MESSAGE';
        final Set<String>? allowed = componentActions[component['component']];
        if (allowed == null) return 'UNKNOWN_COMPONENT';
        if (_eventNames(component).any((name) => !allowed.contains(name))) {
          return 'ACTION_NOT_ALLOWED';
        }
      }
    }
    return null;
  }

  static bool _anyString(Object? node, bool Function(String) test) =>
      switch (node) {
        String s => test(s),
        Map<String, Object?> m => m.values.any((v) => _anyString(v, test)),
        List<Object?> l => l.any((v) => _anyString(v, test)),
        _ => false,
      };

  static bool _anyKey(Object? node, String key) => switch (node) {
    Map<String, Object?> m =>
      m.containsKey(key) || m.values.any((v) => _anyKey(v, key)),
    List<Object?> l => l.any((v) => _anyKey(v, key)),
    _ => false,
  };

  static Iterable<String> _eventNames(Object? node) sync* {
    if (node is Map<String, Object?>) {
      final Object? event = node['event'];
      if (event is Map<String, Object?> && event['name'] is String) {
        yield event['name']! as String;
      }
      for (final value in node.values) {
        yield* _eventNames(value);
      }
    } else if (node is List<Object?>) {
      for (final value in node) {
        yield* _eventNames(value);
      }
    }
  }
}
```

After the guard the session checks surface state and the graph itself, because the SDK reports these as generic `INTEGRITY_ERROR` or not at all: `createSurface` for a live surface → `DUPLICATE_SURFACE`; a catalog other than the canonical one → `UNSUPPORTED_CATALOG`; any update for a surface that does not exist → `SURFACE_NOT_FOUND` (no client-side reordering); an `updateComponents` leaving the surface without `root` → `MISSING_ROOT`; a revisit on the path from `root` → `CYCLE`; a chain deeper than 8 → `MAX_DEPTH_EXCEEDED`. SDK codes that remain are mapped: `VALIDATION_FAILED` / `SCHEMA_VALIDATION_FAILED` → `SCHEMA_INVALID`, `CATALOG_ERROR` / `CATALOG_NOT_FOUND` → `UNSUPPORTED_CATALOG`. A rejected message changes nothing; earlier surfaces stay.

## Catalog from the contract JSON

Do not hand-copy schemas into Dart. Generate a const from the contract (`const String canonicalCatalogJson = r'''…''';`, regenerated in CI so drift fails the build) and build the catalog from it. `Schema.fromMap` takes each component schema as is; the `$defs` (minus `theme`) go into `definitions` so `#/$defs/ServerEvent` resolves; the functions are the basic v0.9 functions the contract lists. Excerpt of `canonical_catalog.dart`:

```dart
CatalogImplementation buildCanonicalCatalog() {
  final Map<String, Object?> doc =
      jsonDecode(canonicalCatalogJson) as Map<String, Object?>;
  if (doc['catalogId'] != CanonicalContract.catalogId) {
    throw StateError('catalog contract id changed: ${doc['catalogId']}');
  }
  final Map<String, Object?> components =
      doc['components']! as Map<String, Object?>;
  final Map<String, Object?> defs = Map.of(
    doc[r'$defs']! as Map<String, Object?>,
  )..remove('theme');
  final Set<String> functionNames =
      (doc['functions']! as Map<String, Object?>).keys.toSet();
  return CatalogImplementation(
    id: CanonicalContract.catalogId,
    components: [
      for (final MapEntry<String, ComponentWidgetBuilder> entry
          in _builders.entries)
        ComponentImplementation(
          name: entry.key,
          schema: Schema.fromMap(
            components[entry.key]! as Map<String, Object?>,
          ),
          builder: entry.value,
        ),
    ],
    functions: [
      for (final FunctionImplementation fn
          in BasicCatalog.v0_9().functions.values)
        if (functionNames.contains(fn.name)) fn,
    ],
    definitions: defs,
  );
}
```

Why this works (SOURCE-PROVEN, `a2ui_core` 0.8.0 `resolution/generic_binder.dart`): the binder derives each property's behaviour from the schema. A `$ref` to `DynamicString` / `DataBinding` gives a resolved, writable binding; an object schema whose only property is `event` (the contract's `ServerEvent`) is treated as an action, also inside arrays, so `props.list('actions')` yields maps whose `action` is a `NodeAction`.

## Canonical id to widget mapping

No Flutter class name is on the wire; the app maps each id.

| Canonical id | Flutter widget | Binding / actions | Semantics |
|---|---|---|---|
| `ActionCard` | `Card` + header `Text` + `FilledButton` (primary) / `OutlinedButton` | `title`, `body` dynamic; `actions[].action` → `item.open`, `item.dismiss` | container, label = `accessibility.label` else title |
| `InputForm` | `Card` + `Form` + one `BoundTextField` per field | `fields[].value` two-way; `submitAction` (`form.submit`), `cancelAction` | container labelled by title; visible field labels; validator errors |
| `ApprovalForm` | `Card`, risk `Chip` ("Risk: high"), comment `BoundTextField`, Approve / Reject | `comment` two-way; Reject disabled until a reason exists | risk stated in text, not colour only |
| `DetailPanel` | header + label/value lines + `buildChild` for `children` | `fields[].value` dynamic | container + header |
| `StatusIndicator` | `Chip` with "label: status" | `status` literal or bound; unknown value → `unknown` | `liveRegion: true` |
| `DataSummaryTable` | `DataTable` in a horizontal scroll | `rows` bound; `maxRows` (default 50) + "Showing N of M" | container labelled by caption |
| `SelectionList` | `CheckboxListTile` per option + submit | `selected` two-way list of ids; `selection.submit` | container labelled by label |
| `ConfirmationDialog` | inline `Card` with confirm / cancel buttons | `dialog.confirm`, `dialog.cancel`; destructive → `colorScheme.error` | container labelled by title |

`ConfirmationDialog` renders inline: a surface owns no navigator, so the app decides whether to present that surface in a sheet or dialog route.

## Theme adapter

Widgets read colours from `Theme.of(context).colorScheme` and spacing and status colours from a `ThemeExtension` derived from the same scheme, so surfaces follow light, dark and brand themes and the agent never picks a colour. The contract's optional `theme.primaryColor` is not applied (RECOMMENDED PRACTICE: ignore agent colours; brand comes from the app). Excerpt of `genui_theme.dart`:

```dart
@immutable
class GenUiTokens extends ThemeExtension<GenUiTokens> {
  const GenUiTokens({required this.gap, required this.padding,
      required this.success, required this.onSuccess,
      required this.warning, required this.onWarning});

  factory GenUiTokens.fromScheme(ColorScheme scheme) => GenUiTokens(
    gap: 8,      // ignore-design: token definition; map to AppSpacing.sm
    padding: 16, // ignore-design: token definition; map to AppSpacing.md
    success: scheme.primaryContainer,
    onSuccess: scheme.onPrimaryContainer,
    warning: scheme.tertiaryContainer,
    onWarning: scheme.onTertiaryContainer,
  );
  // gap, padding, success, onSuccess, warning, onWarning fields; copyWith; lerp
  static GenUiTokens of(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return theme.extension<GenUiTokens>() ??
        GenUiTokens.fromScheme(theme.colorScheme);
  }
}
```

Register it with `ThemeData(colorScheme: scheme, extensions: [GenUiTokens.fromScheme(scheme)])` for both `theme` and `darkTheme`. `textContrastGuideline` passed on all four valid fixtures with a seeded scheme.

## Typed data bindings

The contract's `inputType` becomes an enum that parses user text into the type the data model and the golden payload expect (an `integer` field writes `3`, not `"3"`; the negative control writing the string fails the golden):

```dart
enum FieldInputType {
  text, email, integer, multiline, date;

  static FieldInputType parse(Object? raw) => FieldInputType.values
      .firstWhere((t) => t.name == raw, orElse: () => FieldInputType.text);

  /// The typed value written to the data model for [input].
  Object? toModel(String input) => switch (this) {
    FieldInputType.integer => int.tryParse(input.trim()),
    _ => input,
  };
}
```

`BoundTextField` holds a `TextEditingController`, writes `binding.set(inputType.toModel(text))` on every change (catching `A2uiDataError`), and updates the controller only when the agent changes the bound value to something other than what the user typed. Client checks (`required`, email shape, whole number) are UX only and block a submit; the server validates again.

## Canonical action payloads

The session turns each `A2uiRendererAction` into the contract's client message, and adds a UUIDv4 idempotency key for side-effecting actions. The key is sent as an `Idempotency-Key` header, never inside `action.context`:

```dart
void _emitAction(A2uiRendererAction action) {
  final String? key = CanonicalContract.idempotentActions.contains(action.name)
      ? _uuidV4() // Random.secure(), version 4 / variant bits set
      : null;
  onAction(CanonicalAction(
    payload: {
      'version': CanonicalContract.wireVersion,
      'action': {
        'name': action.name,
        'surfaceId': action.surfaceId,
        'sourceComponentId': action.sourceComponentId,
        'timestamp': _clock().toUtc().toIso8601String(),
        'context': action.context,
      },
    },
    idempotencyKey: key,
  ));
}
```

`ActionMessage(version:, action:).toJson()` also exists, but `A2uiRendererAction.toJson()` adds `catalogId` when set, which the canonical goldens do not carry; build the map explicitly. All six golden payloads (`item.open`, `form.submit`, `approval.approve`, `approval.reject`, `dialog.confirm`, `selection.submit`) matched byte for byte in canonical form after driving the real widgets (`enterText`, `tap`), and were accepted live by the reference backend.

High-risk actions: the backend answers `approval.approve` / `approval.reject` with `202 confirmation_required` and A2UI messages for a `ConfirmationDialog`; the transport applies them to the session, and the user's `dialog.confirm` executes the action. Authorization is the server's: a 403 for another user's resource is shown, never retried silently.

## Conventional fallback

When `session.failure` is set (validation, version, transport or action failure), the screen shows a banner with the failure code and an app-owned, non-generated form so the user can still finish the task; surfaces that are still valid stay visible. Tested: `wrong-version-v0_8`, `unknown-component` and a 403 each show the fallback; a valid `input-form` does not.

```dart
if (failure != null) ...[
  MaterialBanner(
    content: Text('This screen could not be shown (${failure.code}).'),
    actions: [TextButton(onPressed: onRetry, child: const Text('Retry'))],
  ),
  const ConventionalFallbackForm(), // app-owned form, submitted via the normal API
],
for (final String id in session.surfaceIds) session.surfaceView(id),
```

Mark a fallback submission as not agent-generated so downstream processing can route it.

## Backend topologies and transport

| Topology | Base URL (reference backend) | What differs in the app |
|---|---|---|
| `shared-backend` | one backend for web and mobile (`:8710` locally) | `GenUiBackend.baseUri` only |
| `standalone-backend` | a backend dedicated to the Flutter app (`:8713` locally; no CORS, native client) | `GenUiBackend.baseUri` only |

The catalog, guard, session and widgets are identical; the same 10 live tests passed against both.

`A2uiStreamClient` (excerpts in the check app's `genui_transport.dart`):

- **Stream**: `GET /a2ui/stream?scenario=…` with `Authorization: Bearer <user session token>`; each SSE `message` event's `data` is one v0.9 message → `session.apply`. A `LineFramer` buffers an unterminated tail; a stream ending mid-line reports `INCOMPLETE_FRAME` and never parses the partial frame.
- **Cancel**: an `http.AbortableRequest` whose `abortTrigger` completes on `cancel()` (`http` 1.6.0, SOURCE-PROVEN); applied surfaces stay; the server logged `stream_stopped`.
- **Reconnect**: a stream that ends without `event: done` is reopened with `Last-Event-ID: <last id>`, up to `maxReconnects` with linear backoff; exhaustion reports `STREAM_DROPPED`. `event: resync` → `session.reset()` before the replay (no `DUPLICATE_SURFACE`). `event: error` → `STREAM_ERROR`.
- **Actions**: `POST /actions` with the canonical body and the `Idempotency-Key` header; a non-2xx body `{"error":{"code"}}` is reported as `HTTP_<status>`; `messages` in a 2xx body are applied.
- **Non-200 on open** (401 without a token, 403) is reported and nothing renders.

## AG-UI and CopilotKit

Flutter has no AG-UI or CopilotKit client. A Flutter app does **not** consume CopilotKit or AG-UI streams unless you build an adapter. CopilotKit is a web (Angular/React) copilot framework and is never needed on Flutter; render A2UI directly.

If the backend speaks AG-UI, `AguiA2uiAdapter` (RECOMMENDED PRACTICE, DOCUMENTED AND TESTED against the reference backend in both topologies) posts an AG-UI `RunAgentInput` to `/agui` and reads AG-UI 1.0 SSE:

- It takes A2UI only from `ACTIVITY_SNAPSHOT` events with `activityType == "a2ui-surface"`, whose `content.a2ui_operations` holds every op so far for one surface (`replace: true`). This matches `@ag-ui/a2ui-middleware` 0.0.16 (SOURCE-PROVEN from its published `dist`).
- Because each snapshot is cumulative, it applies only the new suffix of ops; if earlier ops changed, it deletes the surface and replays the list. Every op still goes through `session.apply` (guard + SDK).
- `RUN_ERROR` → failure with the event's `code`; `RUN_FINISHED` → `finishStream()`; a stream ending without either → `STREAM_DROPPED`.
- Tested: the `detail-panel-composite` run produced the same component ids and data model as the fixture applied directly.
- An action over AG-UI goes in `forwardedProps.a2uiAction.userAction` (the run id is the idempotency key). The check app posts actions to `/actions` instead; the AG-UI action path is DOCUMENTED BUT NOT TESTED here.

## Secrets

The app holds only the signed-in user's short-lived session token, sent as a bearer token to a dedicated agent backend. Model provider keys, tool credentials and A2UI generation stay on that backend. Never put a provider key in `--dart-define`, assets or code; never put secrets in a data model or action context (both are agent-visible).

## Tests

| Test | What it proves |
|---|---|
| Every `fixtures/valid/*.json` | Renders with no failure and no exception |
| Every `fixtures/invalid/*.json` | First failure equals the fixture's `expectedError`; `failure` set (fallback shown) |
| Every `fixtures/streams/*.jsonl` fed in 7-character chunks through `LineFramer` | Per-line error codes and final component ids + data model equal `*.expect.json` (progressive, truncated, duplicate create/updates, out-of-order) |
| `fixtures/actions/*.json` via real taps and typing | Canonical payload equals the golden; key present only for idempotent actions; written to `parity/flutter/<golden>.json` for the parity audit |
| Reconnect (`MockClient.streaming`) | Second request carries `Last-Event-ID`; surface completes; failure cleared |
| Resync, error frame, bounded reconnects, 403 | Each surfaced as specified |
| `meetsGuideline(androidTapTargetGuideline / iOSTapTargetGuideline / labeledTapTargetGuideline / textContrastGuideline)` | Pass on all four valid fixtures; a planted 10 px button fails |
| Live (tag `live`, both topologies) | Streams equal fixtures; goldens accepted (200 / 202); user B → 403; no token → 401; cancel mid-stream; AG-UI adapter |

Device E2E uses Maestro only (`.claude/rules/testing-tool-selection.md`); never a browser. A flow for the check app:

```yaml
appId: com.example.genuipoc
---
- launchApp:
    clearState: true
- extendedWaitUntil:
    visible: "Request a document"
    timeout: 30000
- tapOn: "Full name"
- inputText: "Ada Lovelace"
- tapOn: "Email"
- inputText: "ada@example.com"
- tapOn: "Request a document"
- tapOn: "Send request"
- extendedWaitUntil:
    visible: "Sent: form.submit (ok)"
    timeout: 10000
```

Status: BLOCKED on 2026-11-23. iOS: `flutter build ios --simulator` (Flutter 3.44.2) failed in `debug_unpack_ios` because Xcode 27's `lipo` rejects the multi-arch `lipo <file> -verify_arch arm64 x86_64` call (`-verify_arch requires exactly one input file`; single-arch verify succeeds). Android: emulators exist, but the check app has no Android runner because raw project creation is blocked outside the scaffold command. The flow above has not run.

## What the SDK does not do

Measured by removing the guard (negative control) and re-running the 20 invalid contract fixtures against `a2ui_core` 0.8.0:

| Contract rule | SDK alone |
|---|---|
| Reject `<script>` / `javascript:` strings (`UNSAFE_CONTENT`) | Accepted, no error |
| Reject `functionCall` actions (`FUNCTION_ACTION_FORBIDDEN`) | `SCHEMA_INVALID` (rejected, wrong code) |
| Unknown component, disallowed action, two bodies | `SCHEMA_INVALID` |
| Version `1.0` | Routed to the v1.0 adapter, then `UNSUPPORTED_CATALOG` |
| Version `v0.8`, `v0.9.1`, missing | Not reported as `UNSUPPORTED_VERSION` / `MALFORMED_MESSAGE` (missing → `SCHEMA_INVALID`) |
| Duplicate surface, update before create, missing root, cycle | `INTEGRITY_ERROR` (or not at all) |
| `maxDepth: 8` in `ValidationConfig` | Nine nested panels accepted |

So the guard and graph checks above are required, not optional, when a cross-platform contract defines error codes.
