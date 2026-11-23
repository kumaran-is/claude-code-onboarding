# Catalog Contract: canonical A2UI catalog (target 1.0, compatibility v0.9.x)

The contract is published as two catalog documents with identical components, actions and payload schemas: `canonical-catalog-v1_0.json` (A2UI 1.0, the target) and `canonical-catalog.json` (A2UI v0.9.x, the compatibility path). Sections 1–5 describe the v0.9 document format; §7 lists what differs in the 1.0 document and on the 1.0 wire. The validator fails when the two documents drift.

Source of truth: [canonical-catalog.json](canonical-catalog.json). This page explains it. If the page and the JSON disagree, the JSON wins. Fix the page.

Evidence (historical, v0.9 document, before the 1.0 migration): the format was checked against the v0.9 schemas shipped in `@a2ui/web_core@0.15.0` (`src/v0_9/schemas/`) and against the upstream `specification/v0_9/docs/a2ui_protocol.md` (SOURCE-PROVEN). The fixtures pass the vendored wire schemas through `validate_a2ui_contract.py` (DOCUMENTED AND TESTED).

## 1. Catalog format

A v0.9 catalog is a JSON Schema 2020-12 document:

| Key | Meaning |
|---|---|
| `$id` = `catalogId` | `https://catalogs.example.com/genui/canonical/v1/catalog.json`. The spec says both should be set to the same URI. Replace the domain with one you own |
| `components.<Name>` | `allOf: [common_types#ComponentCommon, #/$defs/CatalogComponentCommon, {component: const <Name>, …props}]` with `unevaluatedProperties: false` |
| `functions.<name>` | Client functions usable in `checks`: `required`, `length`, `email`, `numeric`, copied from the v0.9 basic catalog. `regex` (ReDoS risk) and `openUrl` (navigation) are deliberately excluded |
| `$defs.anyComponent` / `$defs.anyFunction` | The discriminated unions that `server_to_client.json` references as `catalog.json#/$defs/…` |
| `$defs.theme` | Required by `createSurface.theme`. Restricted to `primaryColor` |
| `$defs.ServerEvent` | The v0.9 `Action` narrowed to `{event:{name, context}}`. Context values are scalars or `{path}` |
| `x-genui` (root and per component) | **Extension block, not on the wire.** JSON Schema ignores unknown keywords, so renderers and SDKs never see it. Tools and reviewers read it |

The root `x-genui` holds `contractVersion` (semver), `protocolVersion`, `acceptedWireVersions`, optional `platforms`, `limits`, `forbiddenStringPatterns` and `actions` (the action registry).

`platforms` is an optional, unique array whose values must be `angular`, `react` or `flutter`. The canonical catalog declares all three. Declaring a platform commits it to rendering every catalog component: `/audit-a2ui-parity` reports **FAIL** when a declared platform's renderer or any of its component mappings is missing. A platform that is not declared is reported as **NOT RUN**, never FAIL. An unknown value fails `catalog-schema.json`. Each component's `x-genui` holds `schemaVersion`, `allowedActions`, `dataBinding`, `a11y` and `fallback`.

## 2. Components

| ID | Purpose | Required props | Data binding (v0.9 JSON Pointer) | Actions | Fallback |
|---|---|---|---|---|---|
| `ActionCard` | Title, body, 1–3 buttons | `title` | `title`/`subtitle`/`body` may be `{path}` | `item.open`, `item.dismiss` | error placeholder |
| `DataSummaryTable` | Read-only table | `caption`, `columns`, `rows` | `rows` is `{path}` to an array of flat objects keyed by `columns[].key`. Only `maxRows` (default 50, max 200) rows render | — | error placeholder |
| `ApprovalForm` | Approve or reject a request | `title`, `summary`, `requestId`, `riskLevel`, `approveAction`, `rejectAction` | `comment` is a two-way `{path}` | `approval.approve`, `approval.reject` | **reject surface** |
| `SelectionList` | Single- or multi-select | `label`, `listId`, `options`, `selected`, `selectionMode` | `selected` is a two-way `{path}` to an id array. `options` is a literal array or a `{path}` | `selection.submit` | error placeholder |
| `DetailPanel` | Label/value panel, the only container | `title`, `fields` | `fields[].value` may be `{path}`. `children` is a static id list (max 20) | — | error placeholder |
| `StatusIndicator` | Operation status | `label`, `status` | `status` is an enum literal or a `{path}`. A bound value outside the enum renders as `unknown` | — | text label |
| `InputForm` | Editable form | `title`, `formId`, `fields`, `submitAction` | `fields[].value` is a two-way `{path}`. Submit context binds the parent object (`"values": {"path": "/form"}`) | `form.submit`, `form.cancel` | **reject surface** |
| `ConfirmationDialog` | Confirm one stored operation | `title`, `message`, `dialogId`, `confirmAction`, `cancelAction` | `title`/`message` may be `{path}` | `dialog.confirm`, `dialog.cancel` | **reject surface** |

Fallback values:
- `reject-surface`: an interactive component with side effects must never render half-validated. Show the app's error state instead.
- `render-error-placeholder`: render an inline "could not display" box. The rest of the surface stays usable.
- `render-text-label`: show only the label text.

### Accessibility semantics (from `x-genui.a11y`)

| ID | Role (web / Flutter) | Accessible name source |
|---|---|---|
| ActionCard | `article`; buttons are `button` / `Semantics(container)` + buttons | `accessibility.label`, else `title`; buttons from `actions[].label` |
| DataSummaryTable | `<table>` with `<caption>` and `<th scope="col">` / `Table` in `Semantics` | `caption` |
| ApprovalForm | `form` / `Semantics` container; risk level shown as text, not colour alone | `accessibility.label`, else `title` |
| SelectionList | `radiogroup` (single) or a group of checkboxes (multiple) | `label` |
| DetailPanel | `section` with `aria-labelledby` heading / `Semantics(container)` + header | `title` |
| StatusIndicator | `status` (polite live region); status conveyed as text | `label` |
| InputForm | `form`; each field has a visible, associated label; errors announced and linked | `title`; field names from `fields[].label` |
| ConfirmationDialog | `alertdialog` if `destructive`, else `dialog`; focus moves in, Escape cancels, focus returns to the trigger | `title`; description from `message` |

v0.9 `ComponentCommon.accessibility` (`label`, `description`) is available on every component and overrides the default name source. Accessibility conformance is verified per platform (`accessibility-audit` skill), not by this contract.

## 3. Actions

| ID | Payload (`action.context`) | Side effect | Risk | Idempotency key | Human approval |
|---|---|---|---|---|---|
| `item.open` | `{itemId}` | no | low | no | no |
| `item.dismiss` | `{itemId}` | yes | low | yes | no |
| `approval.approve` | `{requestId, comment?}` | yes | high | yes | yes |
| `approval.reject` | `{requestId, reason}` | yes | high | yes | yes |
| `selection.submit` | `{listId, selectedIds[1..50]}` | yes | medium | yes | no |
| `form.submit` | `{formId, values{name: string\|integer\|boolean}}` | yes | medium | yes | no |
| `form.cancel` | `{formId}` | no | low | no | no |
| `dialog.confirm` | `{dialogId}` | yes | high | yes | yes |
| `dialog.cancel` | `{dialogId}` | no | low | no | no |

The exact payload JSON Schemas are in `x-genui.actions.<id>.payloadSchema` (`additionalProperties: false`). `catalog-schema.json` enforces that a side-effecting action requires an idempotency key and that a high-risk action requires human approval. The client→server envelope is the official v0.9 `action` (`name`, `surfaceId`, `sourceComponentId`, `timestamp`, `context`). Canonical comparison rules are in [SKILL.md](../SKILL.md#golden-action-payloads).

## 4. Platform mapping

The wire carries only the canonical ID. Each platform registers its implementation under exactly that name. The class names below are recommended generic names (RECOMMENDED PRACTICE). The registration APIs are in the platform skills.

| Canonical ID | Angular component | React component | Flutter widget |
|---|---|---|---|
| ActionCard | `GenuiActionCardComponent` | `GenuiActionCard` | `GenuiActionCard` |
| DataSummaryTable | `GenuiDataSummaryTableComponent` | `GenuiDataSummaryTable` | `GenuiDataSummaryTable` |
| ApprovalForm | `GenuiApprovalFormComponent` | `GenuiApprovalForm` | `GenuiApprovalForm` |
| SelectionList | `GenuiSelectionListComponent` | `GenuiSelectionList` | `GenuiSelectionList` |
| DetailPanel | `GenuiDetailPanelComponent` | `GenuiDetailPanel` | `GenuiDetailPanel` |
| StatusIndicator | `GenuiStatusIndicatorComponent` | `GenuiStatusIndicator` | `GenuiStatusIndicator` |
| InputForm | `GenuiInputFormComponent` | `GenuiInputForm` | `GenuiInputForm` |
| ConfirmationDialog | `GenuiConfirmationDialogComponent` | `GenuiConfirmationDialog` | `GenuiConfirmationDialog` |

Registration: Angular through the `a2ui-angular` skill's v0.9 catalog, Flutter through a `ComponentImplementation` per ID in the `flutter-genui` skill, React through the React renderer guidance (owned outside this skill). A platform that cannot render an ID applies that component's `fallback`. It never substitutes another component.

## 5. Policies

### Unknown components and props
- An unknown `component` name in `updateComponents` rejects that **whole message** (`UNKNOWN_COMPONENT`). Earlier state stays, and the client sends a v0.9 `error` `{code: "VALIDATION_FAILED", surfaceId, path, message}`.
- Unknown props are rejected (`SCHEMA_INVALID`, via `unevaluatedProperties: false`). They are not ignored, because ignoring them hides drift between the backend and the client.

### Version negotiation and explicit rejection
- The renderer advertises what it is proven on, per version, in transport metadata: 1.0 `a2uiRendererCapabilities` `{"1.0": {"supportedCatalogIds": ["<1.0 catalogId>"]}}` (official `renderer_capabilities.json`; `@a2ui/web_core` builds it with `MessageProcessor.getRendererCapabilities({versions})`), v0.9 `{"v0.9": {"supportedCatalogIds": ["<v0.9 catalogId>"]}}` (`client_capabilities.json`). A renderer proven on both may advertise both. The agent advertises `{"1.0": {"supportedCatalogIds", "acceptsInlineCatalogs"}}` (`agent_capabilities.json`); this contract never accepts inline catalogs.
- The agent picks ONE version per surface session: `1.0` when the renderer advertised the 1.0 catalogId, otherwise the v0.9.x path. Every message of that stream carries that exact version string; another value is `MIXED_VERSIONS`. `v0.8`, `v1.0` (non-canonical spelling: the wire value is `"1.0"`), and anything else are `UNSUPPORTED_VERSION`; a missing version is `MALFORMED_MESSAGE`.
- `v0.9` and `v0.9.1` are wire-identical in `@a2ui/web_core` 0.16.1 (one `V0Point9Adapter`, schema enum `['v0.9','v0.9.1']`), so both are accepted on the compatibility path. The validator normalises `v0.9.1` to the vendored schema's `v0.9` const for schema validation only.
- A `createSurface` with another `catalogId` → `UNSUPPORTED_CATALOG`. A second `createSurface` for a live surface → `DUPLICATE_SURFACE` (the spec calls this an error).

### Ordering and partial delivery
- Components may reference children that have not arrived yet. The client renders placeholders progressively, as the spec requires. When a fixture or stream completes, every reference must resolve (`DANGLING_REFERENCE`) and `root` must exist (`MISSING_ROOT`).
- Messages for a surface that has not been created are rejected (`SURFACE_NOT_FOUND`). The client does not reorder messages, so the server must order them per surface.
- An unterminated JSONL line is buffered and never parsed (`INCOMPLETE_FRAME`). Duplicate `updateComponents`/`updateDataModel` messages are idempotent upserts.

### The SDK validator is not the contract validator
- Every client needs an app-owned ingest guard that runs before the SDK message processor. It checks:
  - message size, then that the message has a single body with `version === "v0.9"`
  - the catalog ID and that the surface is known
  - the component and per-component action allowlists
  - prop schemas and forbidden strings
  - that no actions are `functionCall`

  Each failure maps to a code below and is shown to the user.
- The size cap (`MESSAGE_TOO_LARGE`) runs on the raw bytes **before** any JSON parsing, on every platform.
- Reason the guard is needed, found by the Angular, React and Flutter proofs of concept on 2026-11-23:
  - In `@a2ui/web_core@0.15.0` (historical observation; the 0.16.1 LIVE run likewise accepted non-allowlisted actions, bad payloads and unsafe URLs), `STRICT_VALIDATION` checks references, cycles and depth. It does **not** validate component props and does **not** reject a message with no `version` field.
  - `a2ui_core 0.8.0` on its own accepts `<script>` and `javascript:` strings and does not apply the depth limit. It accepted, or gave the wrong error code for, 11 of the 20 `invalid/` fixtures.
- Scope rendered DOM and semantics IDs per surface. Every surface has a `root`, so unscoped IDs collide and give controls the wrong accessible name.
- Register catalog functions explicitly. A component that reads or writes the data model itself must resolve an action's `{path}` bindings before dispatching. If it doesn't, the server receives unresolved bindings, which is `ACTION_CONTEXT_UNRESOLVED`.
- To fully replay the `invalid/` fixtures with their exact error codes, a client must implement all eight components. With fewer components, unrelated fixtures are rejected as `UNKNOWN_COMPONENT` instead of their intended code.

### Error codes (validator and client log vocabulary)
`MALFORMED_MESSAGE`, `UNSUPPORTED_VERSION`, `UNSUPPORTED_CATALOG`, `UNKNOWN_COMPONENT`, `SCHEMA_INVALID`, `ACTION_NOT_ALLOWED`, `FUNCTION_ACTION_FORBIDDEN`, `UNSAFE_CONTENT`, `STRING_TOO_LONG`, `MESSAGE_TOO_LARGE`, `TOO_MANY_COMPONENTS`, `MAX_DEPTH_EXCEEDED`, `CYCLE`, `DUPLICATE_COMPONENT_ID`, `MISSING_ROOT`, `DANGLING_REFERENCE`, `SURFACE_NOT_FOUND`, `DUPLICATE_SURFACE`, `INVALID_POINTER`, `INCOMPLETE_FRAME`, `ACTION_PAYLOAD_INVALID`, `ACTION_CONTEXT_UNRESOLVED`, `NON_INTEGER_NUMBER`, `NULL_VALUE`, `BAD_TIMESTAMP`.

Added for 1.0: `MIXED_VERSIONS`, `FUNCTION_CALL_NOT_ALLOWED` (spec code `INVALID_FUNCTION_CALL`). On the wire, contract codes map to the `VALIDATION_FAILED` error of the stream's version. The specific code goes in the client log and the `message`.

**Every renderer and every backend emitter runs this gate itself**, before the SDK (renderer) and before streaming (emitter). SDK structural validation is not a substitute: `@a2ui/web_core` 0.16.1, `@a2ui/agent` 0.2.1 `validatePayload` and `a2ui_flutter` 0.5.0 each accepted at least one of: a non-allowlisted action, a bad action payload, a `javascript:` URL, mixed versions, a v0.9 `{"path"}` binding in a 1.0 message.

## 6. Versioning and backward compatibility

| Change | Kind | What to do |
|---|---|---|
| Add an optional prop, a new component, or a new action | minor (`contractVersion` x.**y**.0) | Bump `contractVersion` and the component `schemaVersion`. Old servers keep working. Ship renderers **before** any server emits the addition |
| Fix a description or an a11y note | patch | Bump the patch only |
| Remove or rename a component, prop or action; make a prop required; narrow an enum or limit; change a payload schema | **breaking** | New `catalogId` (`…/v2/catalog.json`). The client advertises both IDs during migration, and the server picks per surface. Never change the meaning of an existing catalogId |
| Change the wire protocol version | **breaking** | See §7. Never mix versions on one surface |

Every change updates the fixtures and golden actions in the same PR, and the validator must exit 0.

## 7. A2UI 1.0 (target) — what differs from v0.9

Verified 2026-11-23 against a2ui.org `/specification/v1.0-evolution-guide/`, the upstream `specification/v1_0/json/` schemas (vendored in `vendor/a2ui-v1_0/`, identical to `@a2ui/web_core@0.16.1` `src/v1_0/schemas/`) and the web_core 0.16.x CHANGELOG (SOURCE-PROVEN). The 1.0 catalog and fixtures use all of this.

- Envelope `version` changes from `"v0.9"` to `"1.0"`. The schema files are renamed `server_to_client` → `agent_to_renderer` and `client_to_server` → `renderer_to_agent`.
- New messages: `callRendererFunction`, `agentFunctionResponse` (agent→renderer); `callAgentFunction`, `rendererFunctionResponse` (renderer→agent).
- `createSurface` loses `theme` (the catalog `$defs/theme` is removed). It may carry `components` and `dataModel` inline, and `catalogId` becomes optional. Catalogs can be mixed per component via `@catalogId`.
- Component envelope keys gain an `@` prefix: `accessibility` → `@accessibility`, `checks` → `@checks`, and data bindings use `@path` and `@call`. Do **not** find-and-replace blindly. The evolution guide lists the positions that stay unprefixed (for example the `ChildList` template `path` and the `updateDataModel.path`).
- `updateDataModel.value` becomes required, and a `null` value deletes the key. In v0.9 the key is deleted by omitting `value`.
- The `action` message gains optional `userMessage` and `metadata`. `AccessibilityAttributes` gains `live` and `hidden`. Catalogs gain `protocolVersion`, `instructions`, `allowedParents`/`allowedChildren` and a reserved `Surface` root.
- `CheckRule.message` becomes optional, and checks can return a `ValidationResult`.

Semantics changes (not renames) that this contract relies on:

- **Catalog resolution:** component `@catalogId` → surface `catalogId` → error; no fallback to advertised catalogs. This contract uses one catalog per surface; a different `@catalogId` is `UNSUPPORTED_CATALOG`.
- **Single-message surface init:** a `createSurface` may carry `components` + `dataModel`; the validator applies them atomically.
- **Data deletion:** `updateDataModel` with `"value": null` deletes; omitting `value` is `SCHEMA_INVALID`.
- **Literal `path`/`call` keys:** in 1.0 a `{"path": …}` object in a dynamic position is a literal, not a binding. Strict schema validation rejects it where the catalog requires a `DataBinding`; `@a2ui/web_core` 0.16.1 accepted it in a LIVE-PROTOCOL run, so the contract gate is required in front of the SDK.
- **Functions:** `allowedCallers` (`rendererOnly` | `agentOnly` | `rendererOrAgent`) and `returnType` live in the catalog, not on the wire. Our check functions are `rendererOnly` and return `validationResult`.
- **Bare envelope keys:** the evolution guide lets renderers accept legacy bare `accessibility`/`checks` on 1.0 components during transition. This contract does not: agents emit only `@` keys and the validator rejects bare ones.

The 1.0 catalog document (`canonical-catalog-v1_0.json`) differs from the v0.9 one because the official `catalog_definition.json` closes the root and composes `ComponentCommon` at the envelope: `protocolVersion: "1.0"`; policy under `metadata.extensions.genui_contract` (root) and per component `metadata.extensions.genui_contract` (was `x-genui`); no `ComponentCommon` mixin and no per-component `unevaluatedProperties`; standard types referenced as relative `common_types.json#/$defs/...`; `$defs.theme` removed; function call schemas keyed `@call` with `returnType`/`allowedCallers` on the definition. Catalog-local property names (e.g. `InputForm.fields[].checks`, `ApprovalForm.comment`) are ordinary catalog properties and keep plain names.

Rollout: keep both documents in parity; a renderer switches a surface to 1.0 only after its real package renders the `fixtures/valid-v1_0/` streams in a test (see `compatibility-matrix.md`).

## 8. Known discrepancy

The upstream v0.9 protocol doc's long example (`a2ui_protocol.md`, the contact form) writes `checks` items as `{call, args, message}`. The shipped `common_types.json` `CheckRule` requires `{condition, message}`. This contract follows the **shipped schema**. The fixtures use `condition`.
