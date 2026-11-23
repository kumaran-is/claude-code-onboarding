---
name: flutter-genui
description: "Flutter generative UI with A2UI 1.0 (v0.9.x compatibility path) — a2ui_flutter 0.5.0 + a2ui_core 0.9.0 renderer (Flutter >= 3.47; 0.4.0 + 0.8.0 on older SDKs), optional a2ui_agent 0.5.0 for apps that prompt a model themselves. Use when rendering agent-driven surfaces in Flutter, building a 1.0 or v0.9 catalog or custom ComponentImplementation, wiring MessageProcessor, A2uiSurface, data model bindings, user actions, SSE/JSONL transport to an agent, or migrating off the discontinued genui package."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__dart-mcp-server__dart
metadata:
  triggers: A2UI Flutter, a2ui_flutter, a2ui_core, a2ui_agent, MessageProcessor, A2uiSurface, CatalogImplementation, ComponentImplementation, BasicComponents, basicCatalog, A2uiGenerator, ResponseStream, GenUI, genui, Flutter GenUI, generative UI Flutter, agent-driven UI Flutter, conversational UI Flutter, createSurface, updateComponents, updateDataModel
  related-skills: genui-contract, flutter-mobile, a2ui-angular, google-adk, streaming-protocols, accessibility-audit
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# Flutter A2UI — Agent-Driven Native UI

> **Tech Stack**: A2UI **1.0** (wire `"version": "1.0"`) with a **v0.9.x** compatibility path (`"v0.9"`, `"v0.9.1"`). Two package paths, chosen by the app's Flutter SDK: **current** `a2ui_flutter` **0.5.0** + `a2ui_core` **0.9.0** (+ optional `a2ui_agent` **0.5.0**), Flutter ≥ 3.47.0 / Dart ≥ 3.13.0, verified on the kit's Flutter 3.50.1 / Dart 3.14.0 with a `material_ui` 1.11.1 host; **older SDKs** (apps still on Flutter 3.38–3.46, Dart 3.10–3.12) `a2ui_flutter` **0.4.0** + `a2ui_core` **0.8.0** (+ `a2ui_agent` **0.4.0**), verified on 3.44.2. Riverpod 3.x is optional.

## What this skill covers

An agent describes a UI as A2UI JSON messages; the Flutter app validates them against catalogs it registered and renders its own native widgets. The agent never sends code. `a2ui_core` processes messages and holds each surface's state, `a2ui_flutter` renders surfaces as Flutter widgets, and `a2ui_agent` is for an app (or Dart server) that calls a model itself and must teach it A2UI and parse its reply.

**Version policy** (verified 2026-11-23 against the published package sources):

- `genui` is discontinued on pub.dev; the `a2ui_flutter` README states that `a2ui_flutter`, `a2ui_core` and `a2ui_agent` replace it. Do not add `genui` or its A2A connector package to new code.
- **Protocol support (package source + a2ui.org/concepts/sdks + execution, 2026-11-23):** `a2ui_core` 0.8.0 and 0.9.0 both implement v0.9, v0.9.1 and 1.0 envelopes (`A2uiProtocolVersion.v0_9`, `v0_9_1`, `v1_0`). `a2ui_flutter` 0.4.0 and 0.5.0 both render 1.0 (`package:a2ui_flutter/basic_catalog.dart`, the default) and v0.9 (`package:a2ui_flutter/v0_9/basic_catalog.dart`).
- **New work targets 1.0** when the agent and the `genui-contract` catalog speak 1.0. Evidence (LIVE-PROTOCOL, same 31 widget tests on each path: 0.5.0/0.9.0 on Flutter 3.50.1 and 0.4.0/0.8.0 on Flutter 3.44.2): the shared contract's 3 valid 1.0 and 3 valid v0.9 samples render through `MessageProcessor` + `A2uiSurface`; taps emit `"1.0"` / `"v0.9"` action envelopes with the bound context (`form.submit` `{formId, values}`, `approval.reject` `{requestId, reason}`); every invalid sample is rejected. A Maestro flow on an iOS simulator passed on the 0.5.0 path.
- **v0.9.x is the compatibility path** for agents or web renderers not yet on 1.0. One wire version per stream; never translate between versions. Use the versioned adapter boundary below.
- Older protocol messages (v0.8) have no adapter: `processMessages` throws on them. See [Migrating from genui](#migrating-from-genui).
- pub.dev 2026-11-23: `a2ui_flutter` 0.5.0, `a2ui_core` 0.9.0, `a2ui_agent` 0.5.0 published that day by verified publisher `labs.flutter.dev`, repository `github.com/a2ui-project/a2ui`, archive SHA-256 matched the pub API. `genui` 0.10.4 is `isDiscontinued: true`, `replacedBy: a2ui_flutter`. docs.flutter.dev/ai/genui (last updated 2026-08-19) still describes `genui` as alpha: treat pub.dev and the package source as authoritative.
- **Material import:** the app imports `package:material_ui/material_ui.dart` (Flutter 3.47+ deprecates `package:flutter/material.dart`). `a2ui_flutter` 0.5.0 still builds its basic catalog on `flutter/material.dart` (a2ui issue #3235), a separate library with its own `Theme`, `Material` and localizations, so every `A2uiSurface` goes through the one bridge file in [Material host](#material-host-flutter-347). Your own `ComponentImplementation` builders use `material_ui`.

## Canonical catalog and the adapter boundary

When the feature uses the cross-platform canonical catalog (`genui-contract` skill: `ActionCard`, `DataSummaryTable`, `ApprovalForm`, `SelectionList`, `DetailPanel`, `StatusIndicator`, `InputForm`, `ConfirmationDialog`), follow `reference/genui-canonical-catalog-adapter.md`:

- **One adapter folder** is the only code that imports `a2ui_core` / `a2ui_flutter`; screens use `GenUiSession`, `GenUiFailure` and `CanonicalAction`, so an SDK change touches one module.
- **Contract guard before the SDK (MANDATORY on both paths).** `a2ui_core` 0.8.0 and 0.9.0 alone, with `ValidationConfig.strict`, accept `javascript:` strings and action payloads with unexpected fields on the shared contract samples (tested); on the older canonical fixtures 0.8.0 also mis-coded 9 of 20 invalid fixtures. Check version, single body, unsafe strings, `functionCall`, component and per-component action allowlists, then surface state and graph (duplicate, not found, missing root, cycle, depth 8).
- **Schemas come from the contract JSON** (`Schema.fromMap` + `$defs` as `definitions`), never a hand copy.
- **Map ids to your widgets** with theme tokens from `ColorScheme` + a `ThemeExtension`; no hardcoded colours, no agent-chosen colours.
- **Typed bindings** (`integer` writes an `int`), **canonical action payloads** (`{"version":"v0.9","action":{…}}`), and an `Idempotency-Key` header (UUIDv4 per intent) for side-effecting actions, never in `context`.
- **Conventional fallback**: on any validation, version, transport or action failure, show the code and an app-owned form; keep valid surfaces.
- **Topologies** `shared-backend` and `standalone-backend` differ only in the transport's base URL; cancel (`AbortableRequest`), reconnect (`Last-Event-ID`), `resync` and `INCOMPLETE_FRAME` handling are in the reference.
- **Flutter does not consume CopilotKit or AG-UI streams** without an adapter you build and test. The reference's `AguiA2uiAdapter` (RECOMMENDED PRACTICE, tested against the reference backend) reads only `ACTIVITY_SNAPSHOT` events with `activityType: "a2ui-surface"`.
- **No secrets in the app**: only the user's session token; model and tool keys stay on the dedicated agent backend.

## Iron Law

**AGENT PAYLOADS ARE UNTRUSTED. RENDER ONLY CATALOGS THE APP REGISTERED, VALIDATE EVERY PAYLOAD BEFORE IT CHANGES A SURFACE, AND NEVER EXECUTE ANYTHING AN AGENT SENDS. A REJECTED PAYLOAD IS SHOWN AND LOGGED, NEVER SWALLOWED.**

## Core concepts

| Concept | Type (package) | Role |
|---|---|---|
| Processor | `MessageProcessor<ComponentImplementation>` (`a2ui_core`) | Applies agent messages, owns the surfaces; `processMessages` throws `A2uiError` on a rejected message |
| Catalog | `CatalogImplementation` / `basicCatalog()` (`a2ui_flutter`) | The allowlist: component names + schemas + builders, and the functions a surface may call |
| Component | `ComponentImplementation(name, schema, builder)` | One component: a JSON schema and a Flutter builder |
| Surface | `SurfaceModel` (`a2ui_core`), rendered by `A2uiSurface` | One agent-built UI with its own component tree and data model |
| Data model | `surface.dataModel` (`DataModel`) | Per-surface JSON state; components bind to it with `{"path": "/x"}` |
| Events | `processor.model.onSurfaceCreated` / `onSurfaceDeleted` / `onAction` / `onError` | `.subscribe(...)` returns a `Subscription` |
| Model side | `A2uiGenerator`, `A2uiRequestProcessor`, `ResponseStream` (`a2ui_agent`) | Prompt snippet for the catalog, and a parser that turns streamed model text into `TextPart` / `A2uiPart` |

## Packages

```yaml
# pubspec.yaml — exact pins. Current path (Flutter >= 3.47.0, Dart >= 3.13.0):
dependencies:
  a2ui_core: 0.9.0
  a2ui_flutter: 0.5.0
  material_ui: 1.11.1   # the app's Material library; see "Material host"
  # Only for a custom component schema (Schema.object):
  json_schema_builder: 0.1.7
  # Only if the app prompts a model itself:
  a2ui_agent: 0.5.0
```

| Path | Pins | SDK floor | Protocols (tested) |
|---|---|---|---|
| Current | `a2ui_flutter` 0.5.0, `a2ui_core` 0.9.0, `a2ui_agent` 0.5.0 | Flutter ≥ 3.47.0, Dart ≥ 3.13.0 | 1.0 and v0.9.x |
| Older SDKs | `a2ui_flutter` 0.4.0, `a2ui_core` 0.8.0, `a2ui_agent` 0.4.0 | Flutter ≥ 3.38, Dart ≥ 3.10 | 1.0 and v0.9.x |

`pub get` of 0.5.0 fails on Flutter < 3.47 / Dart < 3.13; stay on the 0.4.0 path until the app's SDK pin moves. The adapter and gate code in this skill compiles unchanged on both paths. Only `dart format` line-wrapping differs between Dart 3.12 and 3.14, so format with the app's own SDK. Its Video and AudioPlayer components play through `video_player`, which it depends on.

## Material host (Flutter 3.47+)

Under a `material_ui` `MaterialApp`, the basic catalog's widgets (built on `flutter/material.dart`) find no legacy `Material` ancestor ("No Material widget found"), no legacy `MaterialLocalizations`, and read the default light `Theme` instead of the app's. Wrap every `A2uiSurface` in this bridge. It is the ONLY file that imports `flutter/material.dart`; delete it when `a2ui_flutter` moves to `material_ui`:

```dart
// lib/features/<feature>/a2ui/a2ui_material_bridge.dart
// a2ui_flutter 0.5.0 builds on package:flutter/material.dart (a2ui#3235).
// ignore: deprecated_member_use
import 'package:flutter/material.dart' as legacy;
import 'package:material_ui/material_ui.dart';

/// Gives an A2UI surface the host theme, Material localizations and a legacy
/// Material ancestor.
class A2uiMaterialBridge extends StatelessWidget {
  const A2uiMaterialBridge({super.key, required this.child});

  final Widget child;

  @override
  // ignore: deprecated_member_use
  Widget build(BuildContext context) => MaterialUiCompatibilityBridge(
    child: legacy.Material(
      type: legacy.MaterialType.transparency,
      child: child,
    ),
  );
}
```

- `MaterialUiCompatibilityBridge` (from `material_ui`, itself `@Deprecated` as a temporary migration utility) maps the host `ColorScheme` and `TextTheme` into a legacy `ThemeData` and adds Material localizations; the legacy `Material` is what text fields and ink need. Component themes (`inputDecorationTheme`, `filledButtonTheme`, …) are NOT copied: style A2UI controls through the colour scheme and text theme, or override them in your own components.
- Keep the two `ignore`s in this file only, never app-wide; `flutter analyze` must report 0 issues everywhere else.
- In tests, `find.byType(TextField)` matches only `material_ui`'s class. Find basic-catalog fields with `find.byType(EditableText)` or by label.
- Tested on Flutter 3.50.1 (widget tests): with the bridge, legacy `Theme.of` returns the host's dark scheme and `primary`, typing and Submit emit `form.submit {name: Ada}`, and the tap-target and label guidelines pass. Negative controls: without the legacy `Material` → "No Material widget found"; with only the legacy `Material` → "No MaterialLocalizations found"; an unignored `flutter/material.dart` import elsewhere → `flutter analyze` exit 1.

## Upgrading 0.4.0 / 0.8.0 → 0.5.0 / 0.9.0 (package CHANGELOGs)

- **Breaking:** SDK floor raised to Dart ≥ 3.13.0 and Flutter ≥ 3.47.0 (`a2ui_core` #4305, `a2ui_flutter` #4303). Upgrade the app's Flutter pin first; `a2ui_agent` 0.5.0 needs Dart ≥ 3.13.0 too.
- `a2ui_flutter` 0.5.0 requires `a2ui_core` ^0.9.0; `a2ui_agent` 0.5.0 likewise. Bump all three together.
- New `MessageProcessor.addCatalog` (a catalog added later is seen by new surfaces only; a duplicate id throws `A2uiCatalogError`).
- Unknown envelope keys (e.g. a misspelled message type) are now reported at the key's JSON Pointer.
- `Slider` is named by its `label` and announces its shown value; the value bubble is gone.
- No API used in this skill was renamed or removed.

## Versioned adapter boundary

Choose the protocol per stream through an interface keyed by wire version. Register only versions whose renderer tests pass; never translate one version into another. Compiled and tested (31 widget tests) on both package paths:

```dart
abstract interface class GenUiProtocolAdapter {
  Set<String> get wireVersions; // e.g. {'1.0'} or {'v0.9', 'v0.9.1'}
  A2uiProtocolVersion get protocolVersion;
  MessageProcessor<ComponentImplementation> createProcessor();
}

final class _ContractAdapter implements GenUiProtocolAdapter {
  _ContractAdapter(this.contract, this.protocolVersion, this.wireVersions);

  final Map<String, Object?> contract; // the genui-contract catalog JSON
  @override
  final A2uiProtocolVersion protocolVersion;
  @override
  final Set<String> wireVersions;

  // The SDK registry holds only this version, so the SDK rejects the others.
  @override
  MessageProcessor<ComponentImplementation> createProcessor() =>
      MessageProcessor<ComponentImplementation>(
        catalogs: [sharedCatalog(contract, protocolVersion)],
        defaultVersion: protocolVersion,
        adapterRegistry: VersionAdapterRegistry([
          if (protocolVersion == A2uiProtocolVersion.v1_0)
            const V1_0Adapter()
          else
            const V0_9Adapter(),
        ]),
        validationConfig: ValidationConfig.strict,
      );
}

GenUiProtocolAdapter genUiV10Adapter(Map<String, Object?> catalogV10) =>
    _ContractAdapter(catalogV10, A2uiProtocolVersion.v1_0, const {'1.0'});

GenUiProtocolAdapter genUiV09Adapter(Map<String, Object?> catalogV09) =>
    _ContractAdapter(catalogV09, A2uiProtocolVersion.v0_9, const {
      'v0.9',
      'v0.9.1',
    });
```

`sharedCatalog` builds a `CatalogImplementation` (`protocolVersion:` set, `definitions:` = the contract's `$defs`, component schemas via `Schema.fromMap` with the catalog-level `metadata` key removed). A session wraps one adapter. Before `processMessages` it rejects a first message in another version (`VERSION_MISMATCH`), a later one (`MIXED_VERSIONS`), unsafe strings (`UNSAFE_CONTENT`), components outside the catalog (`UNKNOWN_COMPONENT`), actions outside the per-component allowlist (`ACTION_NOT_ALLOWED`), and v0.9 `{"path"}` bindings in a 1.0 message (`SCHEMA_INVALID`).

**The SDK alone is not the contract (tested on 0.8.0 and 0.9.0):** `a2ui_core` with strict validation still ACCEPTS a `javascript:` string and an action payload with unexpected fields. It does reject unknown components, mixed versions, a 1.0 `createSurface.theme` and a v0.9 binding under 1.0 (`VALIDATION_FAILED`).

**Two-way bindings inside array items** (e.g. `fields[].value` declared as `DataBinding`): `ComponentProps` hands you the *resolved* value, not the path. Read the raw path from `A2uiSurface.of(context).componentsModel.get(node.componentId)?.properties` and write with `A2uiSurface.of(context).dataModel.set(path, value)`. Actions nested in arrays (`actions[].action` with an inline `event`) resolve to a `NodeAction` you call from the tap.

## Before writing any A2UI code

1. `reference/genui-state-binding.md` — processor, surfaces, data model, rendering, the semantics boundary
2. `reference/genui-catalog-design.md` — basic catalog, your own v0.9 catalog, schema design
3. `reference/genui-custom-widgets.md` — `ComponentImplementation`, `ComponentProps`, write-back, actions, accessibility, tests
4. `reference/genui-a2ui-transport.md` — v0.9 message shapes, SSE/JSONL into `processMessages`, actions back to the agent
5. `reference/genui-conversation-orchestration.md` — agent-server and in-app-model topologies, Riverpod, fallback
6. `reference/genui-functions.md` — the 14 v0.9 basic functions, checks, `openUrl`
7. `reference/genui-security.md` — threat model, `ValidationConfig`, locked-down catalogs, limits
8. `reference/genui-canonical-catalog-adapter.md` — canonical catalog, adapter boundary, contract guard, fallback, topologies, AG-UI adapter
9. Verify any API not shown in these files in the package source (`dart-mcp-server` `read_package_uris` / `rip_grep_packages`) before using it

## Process

1. **Pick the topology** — an agent server streams A2UI to the app, or the app calls a model and parses its reply with `a2ui_agent` (orchestration reference).
2. **Register catalogs** — `basicCatalog()` (1.0) or `v0_9/basic_catalog.dart` `basicCatalog()` (v0.9), or your own `CatalogImplementation` with the basic components plus custom ones. Catalogs are the allowlist.
3. **Create one `MessageProcessor` per conversation** for ONE protocol version (`defaultVersion`, and an `adapterRegistry` holding only that version's SDK adapter) and a `validationConfig` suited to how payloads arrive (security reference). Dispose it with the conversation.
4. **Feed it** — decode each transport payload and call `processor.processMessages`; catch `A2uiError`, log it and show the user an error state.
5. **Render** — subscribe to `onSurfaceCreated` / `onSurfaceDeleted`; render each surface with `A2uiSurface` inside `A2uiMaterialBridge` (Flutter 3.47+ `material_ui` host) and a `Semantics(container: true, explicitChildNodes: true)` boundary.
6. **Handle actions** — subscribe to `onAction` (or pass `onAction:`), check the event name against the app's own allowlist, send it to the agent with the renderer capabilities and data model.
7. **Test** — `flutter test` widget tests for render, input → data model → action context, rejection of unknown catalogs and types, semantics; Maestro for device E2E.

## Example: conversational intake flow

An assistant asks follow-up questions and renders native inputs for the answers:

1. The user describes the request (text or voice); the app sends it to the agent with `a2uiClientCapabilities`.
2. The agent streams v0.9 messages (`createSurface`, `updateDataModel`, `updateComponents`).
3. The processor validates and applies them; `A2uiSurface` renders native widgets.
4. A Button's action reaches `onAction` with its `context` resolved from the data model; the app sends it back to the agent.
5. The agent replies with `updateDataModel` / `updateComponents` / `deleteSurface` until the intake is complete.

**Fallback:** if the stream fails or a payload is rejected, show the error and offer a plain form so the user can still submit. Record that the request was not classified by the agent.

```
lib/features/<feature>/
  a2ui/
    app_catalog.dart          # CatalogImplementation: basic + custom components
    a2ui_material_bridge.dart # the only flutter/material.dart import (Material host)
    custom_components.dart    # ComponentImplementation definitions
  data/
    agent_client.dart         # transport: request body, SSE decode, processMessages
  presentation/
    agent_surfaces.dart       # surface list, Semantics boundary, error state
    intake_screen.dart
```

## Anti-patterns

| Don't | Do |
|---|---|
| Build widgets from agent JSON with your own `switch` on a type string | Register components in a catalog; `A2uiSurface` renders only what the catalog declares |
| Call `processMessages` without `try`/`on A2uiError` | Catch, log `error.code` + `error.message`, show an error state |
| Pass `openUrl:` to `basicCatalog()` for an agent you do not control | Omit it (calls fail), allowlist hosts in the callback, or drop `openUrl` from the catalog |
| Keep the default processor config for whole-surface payloads from an untrusted agent | Pass `validationConfig` so unknown component types and functions are rejected |
| Render `A2uiSurface` straight into a `ListView` | Wrap it in `Semantics(container: true, explicitChildNodes: true)` so each control keeps its own node |
| Write a custom component without a `Semantics(container: true, ...)` | Give it its own semantics node with a label and value |
| Mix v0.9 and 1.0 messages in one stream, or translate between them | One version per stream, chosen by the versioned adapter boundary; reject the rest (`MIXED_VERSIONS`) |
| Put `^` ranges or a git dependency for the A2UI packages | Pin `a2ui_flutter: 0.5.0`, `a2ui_core: 0.9.0` |
| Import `flutter/material.dart` app-wide, or render `A2uiSurface` directly under a `material_ui` app | `material_ui` everywhere; `A2uiSurface` only inside `A2uiMaterialBridge` |

## Error handling

| Failure | Behaviour |
|---|---|
| `processMessages` throws `A2uiError` (unknown catalog, schema failure, version without adapter) | Log `code` and `message`, show an error state on that surface or the conversation; keep earlier surfaces |
| Transport event malformed or over the size limit | Stop the stream, show an error with a retry, never render a partial guess |
| Connection drops mid-stream | Keep what was applied, show reconnect; resend capabilities on the new request |
| `WritableBinding.set` throws `A2uiDataError` | Log it; the control keeps the previous value |
| Action send fails | Show a snackbar or inline error; let the user retry |
| Packages fail to initialise or the agent is unavailable | Fall back to a static form |

## Common commands

```bash
flutter pub add a2ui_flutter:0.5.0 a2ui_core:0.9.0 material_ui:1.11.1
flutter analyze
flutter test test/features/<feature>/
maestro test .maestro/<flow>.yaml   # device E2E only (Android emulator / iOS simulator)
```

Flutter Android/iOS UI and E2E automation uses Maestro only (`.claude/rules/testing-tool-selection.md`); never a browser.

## Migrating from genui

The only place older-protocol names belong. Rows were checked against `a2ui_flutter` 0.4.0 / `a2ui_core` 0.8.0 source; 0.5.0 / 0.9.0 keep these names (CHANGELOG: SDK floor and additions only).

| genui / A2UI v0.8 | a2ui_flutter 0.5.0 / a2ui_core 0.9.0 on v0.9 |
|---|---|
| `genui`, `genui_a2a` (git or ^0.10) | `a2ui_flutter: 0.5.0` + `a2ui_core: 0.9.0` (+ `a2ui_agent: 0.5.0` if the app prompts a model) |
| `SurfaceController` | `MessageProcessor<ComponentImplementation>` + `processor.model` events |
| `Catalog` / `CatalogItem` | `CatalogImplementation` / `ComponentImplementation(name:, schema:, builder:)` |
| `A2uiTransportAdapter` (`genui`), `genui_a2a` connector | The app's own transport calls `processor.processMessages(json)` |
| `Conversation` | The app's own controller (or a Riverpod notifier) around the processor; `A2uiGenerator` + `ResponseStream` when the app calls the model |
| `beginRendering` | `createSurface` (`surfaceId`, `catalogId`, optional `sendDataModel`) |
| `surfaceUpdate` | `updateComponents` (`surfaceId`, flat `components` list, root id `root`) |
| `dataModelUpdate` | `updateDataModel` (`surfaceId`, optional `path`, `value`) |
| `explicitList` children | `children: ["a", "b"]` id list |
| Hand-written `A2UIFunctionEvaluator` | The catalog's v0.9 functions: `BasicCatalog.v0_9().functions` |
| `userAction` / `UserAction` | `A2uiRendererAction` from `onAction`, sent as `ActionMessage` in `RendererToAgentMessagePayload` |
| Messages without `version` | Every message carries `"version": "v0.9"` |

## Documentation sources

| Source | URL / Tool | Purpose |
|---|---|---|
| `a2ui_flutter` | `https://pub.dev/packages/a2ui_flutter` | Renderer API, v0.9 section, security notes |
| `a2ui_core` | `https://pub.dev/packages/a2ui_core` | Processor, catalogs, functions, validation |
| `a2ui_agent` | `https://pub.dev/packages/a2ui_agent` | Prompt snippet, response parsing, streaming |
| Source | `https://github.com/a2ui-project/a2ui` | Packages, examples, conformance tests |
| A2UI protocol | `https://a2ui.org/` | Specification |
| Canonical contract | `../genui-contract/SKILL.md` | Catalog ids, actions, fixtures, golden payloads |
| AG-UI A2UI mapping | `@ag-ui/a2ui-middleware` 0.0.16 (npm) | `ACTIVITY_SNAPSHOT` / `a2ui-surface` shape the Flutter adapter reads |
| Shared protocol notes | `../a2ui-angular/reference/a2ui-protocol.md` | v0.9 message reference used by the Angular skill |
| Dart MCP | `dart-mcp-server` | Read the resolved package source |
| Context7 | `Context7` MCP | Fallback docs |
