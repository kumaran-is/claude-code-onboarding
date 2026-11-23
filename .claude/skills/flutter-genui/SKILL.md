---
name: flutter-genui
description: "Flutter generative UI with the A2UI protocol v0.9 — a2ui_flutter 0.4.0 + a2ui_core 0.8.0 renderer, optional a2ui_agent 0.4.0 for apps that prompt a model themselves. Use when rendering agent-driven surfaces in Flutter, building a v0.9 catalog or custom ComponentImplementation, wiring MessageProcessor, A2uiSurface, data model bindings, user actions, SSE/JSONL transport to an agent, or migrating off the discontinued genui package."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs, mcp__dart-mcp-server__dart
metadata:
  triggers: A2UI Flutter, a2ui_flutter, a2ui_core, a2ui_agent, MessageProcessor, A2uiSurface, CatalogImplementation, ComponentImplementation, BasicComponents, basicCatalog, A2uiGenerator, ResponseStream, GenUI, genui, Flutter GenUI, generative UI Flutter, agent-driven UI Flutter, conversational UI Flutter, createSurface, updateComponents, updateDataModel
  related-skills: flutter-mobile, a2ui-angular, google-adk, streaming-protocols, accessibility-audit
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# Flutter A2UI — Agent-Driven Native UI

> **Tech Stack**: Flutter 3.41.x / Dart 3.10.x, `a2ui_flutter` **0.4.0** + `a2ui_core` **0.8.0**, A2UI protocol **v0.9** (wire value `"version": "v0.9"`), optional `a2ui_agent` **0.4.0**, Riverpod 3.x (optional)

## What this skill covers

An agent describes a UI as A2UI JSON messages; the Flutter app validates them against catalogs it registered and renders its own native widgets. The agent never sends code. `a2ui_core` processes messages and holds each surface's state, `a2ui_flutter` renders surfaces as Flutter widgets, and `a2ui_agent` is for an app (or Dart server) that calls a model itself and must teach it A2UI and parse its reply.

**Version policy** (verified 2026-11-23 against the published package sources):

- `genui` is discontinued on pub.dev; the `a2ui_flutter` README states that `a2ui_flutter`, `a2ui_core` and `a2ui_agent` replace it. Do not add `genui` or its A2A connector package to new code.
- **New work targets v0.9**, matching the `a2ui-angular` skill. Import the v0.9 catalog from `package:a2ui_flutter/v0_9/basic_catalog.dart` and set `defaultVersion: A2uiProtocolVersion.v0_9`.
- **v1.0 exists**: `package:a2ui_flutter/basic_catalog.dart` (no `v0_9/`) is the v1.0 catalog, and `VersionAdapterRegistry.standard()` holds the v0.9 and v1.0 adapters. Do not mix versions between agent, renderer and catalog.
- Older protocol messages have no adapter: `processMessages` throws on them. See [Migrating from genui](#migrating-from-genui).

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
# pubspec.yaml — exact pins
dependencies:
  a2ui_core: 0.8.0
  a2ui_flutter: 0.4.0
  # Only for a custom component schema (Schema.object):
  json_schema_builder: 0.1.7
  # Only if the app prompts a model itself:
  a2ui_agent: 0.4.0
```

`a2ui_flutter` 0.4.0 requires Flutter ≥ 3.38 and Dart ≥ 3.10. Its Video and AudioPlayer components play through `video_player`, which it depends on.

## Before writing any A2UI code

1. `reference/genui-state-binding.md` — processor, surfaces, data model, rendering, the semantics boundary
2. `reference/genui-catalog-design.md` — basic catalog, your own v0.9 catalog, schema design
3. `reference/genui-custom-widgets.md` — `ComponentImplementation`, `ComponentProps`, write-back, actions, accessibility, tests
4. `reference/genui-a2ui-transport.md` — v0.9 message shapes, SSE/JSONL into `processMessages`, actions back to the agent
5. `reference/genui-conversation-orchestration.md` — agent-server and in-app-model topologies, Riverpod, fallback
6. `reference/genui-functions.md` — the 14 v0.9 basic functions, checks, `openUrl`
7. `reference/genui-security.md` — threat model, `ValidationConfig`, locked-down catalogs, limits
8. Verify any API not shown in these files in the package source (`dart-mcp-server` `read_package_uris` / `rip_grep_packages`) before using it

## Process

1. **Pick the topology** — an agent server streams A2UI to the app, or the app calls a model and parses its reply with `a2ui_agent` (orchestration reference).
2. **Register catalogs** — `basicCatalog()` for v0.9, or your own `CatalogImplementation` with the basic components plus custom ones. Catalogs are the allowlist.
3. **Create one `MessageProcessor` per conversation** with `defaultVersion: A2uiProtocolVersion.v0_9` and a `validationConfig` suited to how payloads arrive (security reference). Dispose it with the conversation.
4. **Feed it** — decode each transport payload and call `processor.processMessages`; catch `A2uiError`, log it and show the user an error state.
5. **Render** — subscribe to `onSurfaceCreated` / `onSurfaceDeleted`; render each surface with `A2uiSurface`, inside a `Semantics(container: true, explicitChildNodes: true)` boundary.
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
| Mix v0.9 messages, a v1.0 catalog and a v1.0 agent | One version end to end: v0.9 catalog, `defaultVersion` v0.9, agent writing v0.9 |
| Put `^` ranges or a git dependency for the A2UI packages | Pin `a2ui_flutter: 0.4.0`, `a2ui_core: 0.8.0` |

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
flutter pub add a2ui_flutter:0.4.0 a2ui_core:0.8.0
flutter analyze
flutter test test/features/<feature>/
maestro test .maestro/<flow>.yaml   # device E2E only (Android emulator / iOS simulator)
```

Flutter Android/iOS UI and E2E automation uses Maestro only (`.claude/rules/testing-tool-selection.md`); never a browser.

## Migrating from genui

The only place older-protocol names belong. Every row was checked against `a2ui_flutter` 0.4.0 / `a2ui_core` 0.8.0 source.

| genui / A2UI v0.8 | a2ui_flutter 0.4.0 / a2ui_core 0.8.0 on v0.9 |
|---|---|
| `genui`, `genui_a2a` (git or ^0.10) | `a2ui_flutter: 0.4.0` + `a2ui_core: 0.8.0` (+ `a2ui_agent: 0.4.0` if the app prompts a model) |
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
| Shared protocol notes | `../a2ui-angular/reference/a2ui-protocol.md` | v0.9 message reference used by the Angular skill |
| Dart MCP | `dart-mcp-server` | Read the resolved package source |
| Context7 | `Context7` MCP | Fallback docs |
