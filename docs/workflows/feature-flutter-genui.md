# Flutter A2UI — Agent-Driven Native UI (v0.9)

> **When to use**: Building Flutter UIs where an AI agent's replies render as native widgets through the A2UI protocol
> **Time estimate**: 4–8 hours for the first integration; 1–2 hours per additional custom component
> **Prerequisites**: Flutter app scaffolded (Flutter ≥ 3.38, Dart ≥ 3.10); an agent that writes A2UI v0.9 (or a model the app calls); `flutter-genui` skill loaded
> **Related**: [`feature-a2ui-renderer.md`](feature-a2ui-renderer.md) (Angular equivalent), [`feature-flutter-mobile.md`](feature-flutter-mobile.md), [`feature-google-adk.md`](feature-google-adk.md)

## Overview

The agent describes UI as A2UI v0.9 JSON messages; the app validates them against catalogs it registered and renders native Flutter widgets (not webviews, not Markdown). The packages are `a2ui_core` 0.8.0 (processing and state), `a2ui_flutter` 0.4.0 (rendering) and, only when the app prompts a model itself, `a2ui_agent` 0.4.0. They replace the discontinued `genui` package; the skill's `SKILL.md` has the migration table.

The core loop: **user input → request with renderer capabilities → agent streams v0.9 messages → `MessageProcessor.processMessages` → `A2uiSurface` renders catalog components → input updates the data model → action → next request**.

New work targets v0.9, matching the Angular A2UI skill. `a2ui_flutter` also ships a v1.0 catalog; do not mix versions.

---

## Iron Law (from `skills/flutter-genui/SKILL.md`)

> **AGENT PAYLOADS ARE UNTRUSTED. RENDER ONLY CATALOGS THE APP REGISTERED, VALIDATE EVERY PAYLOAD BEFORE IT CHANGES A SURFACE, AND NEVER EXECUTE ANYTHING AN AGENT SENDS. A REJECTED PAYLOAD IS SHOWN AND LOGGED, NEVER SWALLOWED.**

---

## A2UI v0.9 Message Types

| Message | Direction | Purpose |
|---|---|---|
| `createSurface` | Agent → App | New surface: `surfaceId`, `catalogId`, optional `sendDataModel` |
| `updateComponents` | Agent → App | Flat list of components by id; tree starts at `root` |
| `updateDataModel` | Agent → App | Write the surface's data model (whole, or at a JSON Pointer `path`) |
| `deleteSurface` | Agent → App | Remove a surface |
| `action` | App → Agent | A user action (`ActionMessage` in `RendererToAgentMessagePayload`) with its resolved `context` |

Every message carries `"version": "v0.9"`. Shapes and examples: `reference/genui-a2ui-transport.md`.

---

## Phases

### Phase 1 — Load Skill, Pin Packages, Choose Topology

```yaml
dependencies:
  a2ui_core: 0.8.0
  a2ui_flutter: 0.4.0
  json_schema_builder: 0.1.7   # only for custom component schemas
  # a2ui_agent: 0.4.0          # only if the app prompts the model itself
```

Topology (`reference/genui-conversation-orchestration.md`): an **agent server** streams A2UI (default; keys and tools stay server-side), or the **app calls a model** and parses A2UI from its reply with `a2ui_agent`.

**Gate:** packages pinned exactly; topology agreed with the backend team.

---

### Phase 2 — Catalog

Start from `basicCatalog()` (`package:a2ui_flutter/v0_9/basic_catalog.dart`). For custom components, build one `CatalogImplementation` with the `BasicComponents` members you need, your components and `BasicCatalog.v0_9().functions` — a v0.9 surface uses one catalog. For agents you do not control, start from the locked-down catalog (no Image, Video, AudioPlayer, Modal or `openUrl`).

References: `genui-catalog-design.md`, `genui-security.md`.

**Gate:** catalog id owned and versioned; only needed components and functions listed.

---

### Phase 3 — Processor, Surfaces and Data Model

One `MessageProcessor<ComponentImplementation>` per conversation with `defaultVersion: A2uiProtocolVersion.v0_9` and a `validationConfig`, disposed with the conversation. Subscribe to `onSurfaceCreated` / `onSurfaceDeleted` / `onAction`. Render each surface with `A2uiSurface`, keyed `ObjectKey(surface)`, inside `Semantics(container: true, explicitChildNodes: true)`.

Input components write their bound `{"path"}`; a Button action's `context` reads the data model at tap time.

Reference: `genui-state-binding.md`.

**Gate:** widget test proves typed input reaches the action `context`.

---

### Phase 4 — Transport and Actions

The app's transport decodes each SSE event or JSONL line (with a byte limit) and calls `processor.processMessages`. Actions go back as `RendererToAgentMessagePayload([ActionMessage(...)])` with `a2uiClientCapabilities` and, for `sendDataModel` surfaces, `a2uiClientDataModel`. Check each action name against the app's allowlist before any local effect.

Reference: `genui-a2ui-transport.md`.

**Gate:** tests for decode, oversize rejection and the action body's v0.9 capabilities.

---

### Phase 5 — Custom Components

`ComponentImplementation(name, schema, builder)` with `CommonSchemas` v0.9 types. Write back through `props.writable(key)` (handle `A2uiDataError`); run actions with `props.action(key)`; keep I/O (camera, upload) in the app behind an action. Every component gets `Semantics(container: true, ...)`, a tooltip on icon-only controls, and 48dp targets.

Reference: `genui-custom-widgets.md`.

**Gate:** each component renders from a payload, writes back, and has its own semantics node (test with a negative control).

---

### Phase 6 — Functions and Checks

Use the 14 v0.9 basic functions (`required`, `regex`, `length`, `numeric`, `email`, `formatString`, `formatNumber`, `formatCurrency`, `formatDate`, `pluralize`, `openUrl`, `and`, `or`, `not`). Inputs show failing `checks`; a Button with a failing check is disabled. Decide `openUrl` explicitly: no callback, an allowlisting callback, or removed from the catalog.

Reference: `genui-functions.md`.

**Gate:** check-gated submit tested (disabled until valid, then the action fires).

---

### Phase 7 — Security Validation

Strict `validationConfig` for whole-surface payloads, the streaming config for parent-before-child streams; never `ValidationConfig.relaxed` for an untrusted agent. Byte limits before `jsonDecode`; caps on surfaces and components. No credentials or payment details in agent-built surfaces. Dispatch `security-reviewer` (and `flutter-security-expert` for mobile hardening).

Reference: `genui-security.md`.

**Gate:** tests for unregistered catalog, unknown component type, oversize payload, and the locked-down catalog with a positive control; reviewer has no unresolved CRITICAL or HIGH.

---

### Phase 8 — Riverpod Integration (optional)

Own the processor in a `Provider` with `ref.onDispose(processor.dispose)`; expose surfaces from a `Notifier`; keep transcript, loading and error in a notifier that calls the transport. Scope to the screen so leaving it cancels the stream. Keep surface data in its `DataModel`, not mirrored into providers.

Reference: `genui-state-binding.md` (Riverpod section), `genui-conversation-orchestration.md`.

**Gate:** leaving the screen disposes the processor (test or manual check).

---

### Phase 9 — Fallback Path

If the stream fails, a payload is rejected or the feature is off, show an app-owned form so the user can still finish, and mark the submission as not agent-classified. Never leave a spinner or an empty surface.

**Gate:** fallback reachable from every error state.

---

### Phase 9b — Canonical Catalog (cross-platform features only)

When web and mobile render the same agent output, use the framework-neutral catalog from the `genui-contract` skill and `skills/flutter-genui/reference/genui-canonical-catalog-adapter.md`:

- One adapter folder owns every `a2ui_core` / `a2ui_flutter` import; the contract guard and graph checks run before `processMessages`.
- Component schemas are built from the contract JSON; each canonical id maps to a themed Flutter widget.
- Actions leave as the canonical `{"version":"v0.9","action":{…}}` payload; side-effecting ones carry an `Idempotency-Key` header.
- `shared-backend` and `standalone-backend` differ only in the transport's base URL. Flutter consumes AG-UI only through an adapter you build and test.

**Gate:** every contract fixture (valid, invalid, streams) and action golden passes in `flutter test`; the emitted payloads are written for `/audit-a2ui-parity`; live tests pass against both topologies; each check has a negative control.

---

### Phase 10 — Device Verification

`flutter test` for widget and unit tests. Android/iOS UI and E2E: Maestro only (`flutter-mobile` → `reference/flutter-e2e-maestro.md`). Target fields by their exact label, icon-only controls by tooltip, and wait for the first frame with `extendedWaitUntil` in debug builds. If no emulator, simulator or device is available, report BLOCKED; never substitute a browser.

**Gate:** Maestro flow passes on at least one platform, and a deliberately wrong assertion fails (negative control).

---

## Quick Reference

| Phase | Action | Skill reference | Gate |
|---|---|---|---|
| 1 — Setup | Pin packages, choose topology | `SKILL.md` | Exact pins |
| 2 — Catalog | Basic subset + custom components | `genui-catalog-design.md` | Only needed entries |
| 3 — State | Processor, surfaces, bindings | `genui-state-binding.md` | Input → action context test |
| 4 — Transport | SSE/JSONL → `processMessages`; actions back | `genui-a2ui-transport.md` | Decode + limit tests |
| 5 — Components | `ComponentImplementation` with semantics | `genui-custom-widgets.md` | Write-back + semantics tests |
| 6 — Functions | Checks, formatting, `openUrl` decision | `genui-functions.md` | Gated submit test |
| 7 — Security | Validation configs, limits, review | `genui-security.md` | Rejection tests; reviewer clean |
| 8 — Riverpod | Providers + lifecycle (optional) | `genui-state-binding.md` | Dispose on leave |
| 9 — Fallback | Static form | `SKILL.md` → Error handling | No dead ends |
| 10 — Device | Maestro E2E | `flutter-e2e-maestro.md` | Pass + negative control |

---

## Common Pitfalls

- **Adding `genui` or its A2A connector** — discontinued; use `a2ui_flutter` + `a2ui_core`
- **Unpinned A2UI packages** — pin `0.4.0` / `0.8.0`; the API changes between minors
- **No `validationConfig`** — unknown component types are then accepted and render nothing instead of being rejected
- **`ValidationConfig.relaxed` for an untrusted agent** — it allows unknown elements
- **`openUrl` callback for an untrusted agent** — on v0.9 a bound call opens URLs without a tap
- **Surfaces straight in a `ListView`** — semantics merge; wrap each in `Semantics(container: true, explicitChildNodes: true)`
- **Custom component without `Semantics(container: true)`** — its label and value merge into the parent node
- **Swallowing `A2uiError`** — log `code` + `message` and show an error state
- **Mixing v0.9 and v1.0** — one version across agent, renderer and catalog
- **Hardcoded colours and spacing** — use the app's theme and spacing tokens
- **Touch targets < 48dp** — keep Material defaults on interactive components

## Combined Skill Stack

1. `flutter-genui` — A2UI renderer, catalog, transport, security
2. `flutter-mobile` — architecture, Riverpod, testing, Maestro
3. `google-adk` (or the team's agent stack) — the agent that writes v0.9 A2UI
4. Dispatch `security-reviewer`, `flutter-security-expert` and `accessibility-auditor` after implementation

## Related Workflows

- [`feature-a2ui-renderer.md`](feature-a2ui-renderer.md) — Angular equivalent (A2UI renderer)
- [`genui-contract` skill](../../.claude/skills/genui-contract/SKILL.md) — canonical cross-platform catalog and fixtures
- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — base Flutter patterns
- [`feature-google-adk.md`](feature-google-adk.md) — backend agent generating A2UI payloads
- [`security-audit.md`](security-audit.md) — security review of the agent-UI boundary
