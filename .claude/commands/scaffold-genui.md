---
name: scaffold-genui
description: Scaffold a Flutter A2UI v0.9 agent-driven UI feature module — pinned a2ui_flutter/a2ui_core, catalog, surface host, transport, actions, and tests
argument-hint: "[feature name, default: agent-ui]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, mcp__dart-mcp-server__dart, mcp__context7__resolve-library-id, mcp__context7__query-docs
disable-model-invocation: true
---

# Scaffold Flutter A2UI Feature (v0.9)

Creates an agent-driven UI feature module in an existing Flutter project, on A2UI protocol v0.9 with `a2ui_flutter` 0.4.0 and `a2ui_core` 0.8.0. The discontinued `genui` package is not used.

**Feature name:** $ARGUMENTS (default to "agent-ui" if not provided)

## Pre-requisites

1. Read the `flutter-genui` skill (`SKILL.md` and the `reference/*.md` files). Every code template below comes from those references, where it compiles and is tested.
2. Read the `flutter-mobile` skill's `reference/flutter-architecture-patterns.md` (structure) and `reference/flutter-testing-traps.md` (tests).
3. Confirm the project's Flutter is ≥ 3.38 and Dart ≥ 3.10 (`flutter --version`); `a2ui_flutter` 0.4.0 requires them.
4. Ask which topology applies if the request does not say: an agent server streams A2UI (default; `shared-backend` or `standalone-backend`), or the app calls a model itself (adds `a2ui_agent`).
5. Ask whether the feature renders the cross-platform canonical catalog (`genui-contract` skill). If yes, follow `reference/genui-canonical-catalog-adapter.md` for steps 2–9: one `genui/` adapter folder (contract guard, catalog built from the contract JSON, theme tokens, session, transport), the conventional fallback, and the fixture, golden and live tests listed there.

## Steps

1. **Add pinned dependencies to `pubspec.yaml`**

   ```yaml
   dependencies:
     a2ui_core: 0.8.0
     a2ui_flutter: 0.4.0
     json_schema_builder: 0.1.7   # only if a custom component schema is created
     # a2ui_agent: 0.4.0          # only for the in-app model topology
   ```

   Add `url_launcher` only if links are required and the agent is trusted (see step 4); pin its current stable version.

2. **Create the feature folder**

   ```
   lib/features/<name>/
   ├── a2ui/
   │   ├── app_catalog.dart          # CatalogImplementation (basic subset + custom), catalog id
   │   └── custom_components.dart    # ComponentImplementation definitions (only if needed)
   ├── data/
   │   └── agent_client.dart         # request body, SSE/JSONL decode with size limit, processMessages
   ├── application/
   │   └── conversation_controller.dart  # transcript, loading, error; owns the processor
   └── presentation/
       ├── agent_surfaces.dart       # surface list, Semantics boundary, error state
       └── <name>_screen.dart        # transcript + surfaces + input
   ```

3. **Catalog** (`app_catalog.dart`) — from `genui-catalog-design.md`:
   - `basicCatalog()` from `package:a2ui_flutter/v0_9/basic_catalog.dart` when no custom component is needed.
   - Otherwise a `CatalogImplementation` with an id you own, the `BasicComponents` members the feature needs, custom components, `BasicCatalog.v0_9().functions`, `BasicComponents.api.themeSchema` and `.definitions`.
   - For an agent you do not control, start from the locked-down catalog in `genui-security.md` (no Image, Video, AudioPlayer, Modal or `openUrl`).

4. **Processor** (`conversation_controller.dart`):
   - `MessageProcessor<ComponentImplementation>(catalogs: [...], defaultVersion: A2uiProtocolVersion.v0_9, validationConfig: ...)` — strict for whole-surface payloads, `streamingValidation` for parent-before-child streams (`genui-security.md`).
   - `openUrl`: omit the callback unless the agent is trusted; if passed, allowlist scheme and host inside it.
   - Subscribe to `onSurfaceCreated` / `onSurfaceDeleted` / `onAction`; dispose the processor with the controller.
   - Riverpod is optional; if the project uses it, follow the provider pattern in `genui-state-binding.md`.

5. **Transport** (`agent_client.dart`) — from `genui-a2ui-transport.md`:
   - SSE (`a2uiPayloads` + `applyStream`) or JSONL (`applyJsonl`), each with a per-event byte limit.
   - `actionRequestBody`: `RendererToAgentMessagePayload([ActionMessage(...)])` plus `a2uiClientCapabilities` and `a2uiClientDataModel`.
   - Connect and idle timeouts; retry with backoff for reads only.
   - In-app model topology instead: `InAppModelTurns` from `genui-conversation-orchestration.md`.

6. **Surface host** (`agent_surfaces.dart`) — from `genui-state-binding.md`:
   - `A2uiSurface(surface:)` per surface, keyed `ObjectKey(surface)`, inside `Semantics(container: true, explicitChildNodes: true)`.
   - `processMessages` in `try` / `on A2uiError`: log `code` + `message`, show an error state; never swallow.
   - Use the app's theme and spacing tokens, not raw values.

7. **Actions** — check each `A2uiRendererAction.name` against an app allowlist before any local effect; send it with `actionRequestBody`; show send failures.

8. **Custom components** (only if requested) — from `genui-custom-widgets.md`: `CommonSchemas` v0.9 types, `Semantics(container: true, ...)`, write-back via `props.writable(key)` with `A2uiDataError` handled, I/O only behind an action.

9. **Fallback** — an app-owned form shown when the stream fails or a payload is rejected.

10. **Tests** (`flutter test`)

    ```
    test/features/<name>/
    ├── agent_surfaces_test.dart   # renders; typed input reaches action context; deleteSurface; error state
    ├── security_test.dart         # unregistered catalog and unknown type rejected; oversize payload rejected
    └── agent_client_test.dart     # SSE/JSONL decode; action body carries v0.9 capabilities
    ```

    Add semantics assertions (`tester.ensureSemantics()`): each control keeps its own node. Device E2E uses Maestro only (`.maestro/<name>.yaml`); report BLOCKED if no emulator or simulator is available.

11. **Verify**

    ```bash
    flutter pub get
    flutter analyze lib/features/<name>/
    flutter test test/features/<name>/
    ```

    Show each command's exit code.

12. **Print summary** — created files, how to route to the screen, the backend contract to agree with the agent team (`genui-a2ui-transport.md` → Backend contract), and anything not done.

## Reference

- `flutter-genui` skill: `SKILL.md` and all `reference/*.md` files
- `flutter-mobile` skill: `reference/flutter-architecture-patterns.md`, `reference/flutter-testing-traps.md`, `reference/flutter-e2e-maestro.md`

$ARGUMENTS
