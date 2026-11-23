---
name: genui-contract
description: "Framework-neutral GenUI contract targeting A2UI 1.0 with a versioned v0.9.x compatibility path: canonical component catalog (1.0 + v0.9 documents), action allowlist and payload schemas, fixtures and the deterministic dual-version validator shared by Angular, React, Flutter and backends. Use when deciding whether a workflow should use GenUI, changing a GenUI catalog, component or action, choosing A2UI vs AG-UI vs CopilotKit, checking cross-platform parity or migrating v0.9→1.0."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
metadata:
  triggers: GenUI contract, generative UI, should this use GenUI, GenUI suitability, A2UI catalog, A2UI 1.0, A2UI v0.9, canonical catalog, component catalog, catalogId, action allowlist, golden action payload, A2UI fixtures, contract-first, cross-platform GenUI, AG-UI, CopilotKit, A2UI vs AG-UI, catalog versioning, A2UI v1.0 migration
  related-skills: a2ui-angular, flutter-genui, react-spa, streaming-protocols, security-reviewer, agentic-ai-dev, google-adk
  domain: frontend
  role: specialist
  scope: design
  output-format: specification
last-reviewed: "2026-11-23"
---

# GenUI Contract: one A2UI catalog for every platform (target 1.0, compatibility v0.9.x)

The contract is the single source of truth between whatever generates UI (agent, backend, template engine) and every renderer (Angular, React, Flutter). Platforms differ only in how they draw a component. The catalog, the actions and the payloads they send are the same everywhere.

## Iron Law

**GENERATED UI IS UNTRUSTED INPUT. A SURFACE RENDERS ONLY COMPONENTS AND ACTIONS THAT THE PINNED CATALOG ALLOWLISTS, ONLY AFTER STRICT SCHEMA VALIDATION, AND ONLY ON THE ONE WIRE VERSION THE STREAM DECLARES (`1.0` TARGET, `v0.9`/`v0.9.1` COMPATIBILITY), NEVER MIXED OR TRANSLATED. NOTHING FROM THE MODEL IS EXECUTED AS HTML, JS OR DART, AND NOTHING IN A PAYLOAD GRANTS PERMISSION. THE SERVER AUTHORISES EVERY ACTION AGAIN.**

## When to use

| Situation | Use |
|---|---|
| Should this workflow use GenUI at all? Which subflows stay deterministic? | [genui-suitability.md](reference/genui-suitability.md): hard gates, the deterministic baseline, verdict. Run it before the workflow below |
| New GenUI feature on any platform | Start here: pick components and actions from the canonical catalog, then go to the platform skill |
| Adding or changing a component, prop or action | [catalog-contract.md](reference/catalog-contract.md) §Versioning, then regenerate fixtures and run the validator |
| Angular renderer code | `a2ui-angular` skill (versions: [compatibility-matrix.md](reference/compatibility-matrix.md)) |
| Flutter renderer code | `flutter-genui` skill (versions: [compatibility-matrix.md](reference/compatibility-matrix.md)) |
| React renderer code | `react-spa` skill plus this contract (no dedicated React A2UI skill yet) |
| Choosing a backend shape | [backend-topologies.md](reference/backend-topologies.md) |
| Plain SSE/NDJSON transport | `streaming-protocols` skill |

Do not use this skill for a chat UI with no generated components (`ai-chat`) or for agent logic (`agentic-ai-dev`, `google-adk`).

## Which protocol does what

| Technology | Role | Required? | Platforms | Notes |
|---|---|---|---|---|
| **A2UI 1.0** (target) / **v0.9.x** (compatibility) | Generated-UI payload contract: surfaces, components, data model, actions | Yes, it is the contract | Angular, React, Flutter, any backend | This skill. Wire `version` is exactly `"1.0"`, or `"v0.9"`/`"v0.9.1"` for a renderer not yet proven on 1.0 |
| **AG-UI** | Agent event and transport protocol (runs, messages, tool calls, state events) | Optional. Only when the backend already speaks it | Web clients. Flutter needs an adapter that you build and test | Carries A2UI messages as payloads, it does not replace them. See [ag-ui-transport.md](reference/ag-ui-transport.md) |
| **CopilotKit** | App-level copilot framework for Angular and React | Optional. Never required just to render A2UI | Angular, React | Use it only for its copilot features. The A2UI renderer works without it |
| **Flutter GenUI (`a2ui_flutter`)** | Flutter renderer for A2UI | Yes for Flutter | Flutter | Sits behind an app-owned adapter. It does not consume AG-UI or CopilotKit streams directly |

## Contract-first workflow (after the suitability review)

1. **Pick from the catalog.** Use the 8 canonical components ([canonical-catalog-v1_0.json](reference/canonical-catalog-v1_0.json) for 1.0, [canonical-catalog.json](reference/canonical-catalog.json) for v0.9.x; the validator keeps them in parity). If none fits, propose a catalog change. Do not add a platform-only component.
2. **Name the actions.** Every interactive control emits one allowlisted action ID (`item.open`, `approval.approve`, …). Each ID has a payload schema, a risk level, a side-effect flag, an idempotency requirement and a human-approval requirement in the catalog policy (`x-genui.actions` in v0.9; `metadata.extensions.genui_contract.actions` in 1.0, whose catalog root is closed).
3. **Write fixtures before renderers.** Add the surface to `fixtures/valid-v1_0/` (and `fixtures/valid/` while any declared platform is on v0.9.x). Add the golden action the UI must send after a given user edit to `fixtures/actions/`. Add the failure cases you rely on to `fixtures/invalid/`.
4. **Validate.** Run `uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py`, which must exit 0, and `--selftest`, which must also exit 0.
5. **Implement each platform.** Map the canonical ID to the platform component ([catalog-contract.md](reference/catalog-contract.md) §Platform mapping). Each platform's tests replay the same fixtures and must emit the golden action payload exactly (canonical form).
6. **Wire the backend.** Choose a topology ([backend-topologies.md](reference/backend-topologies.md)) and an emitter ([backend-emitters.md](reference/backend-emitters.md)). Enforce the action rules in [action-security.md](reference/action-security.md).
7. **Check the runtime lifecycle.** Cover stream open, partial delivery, cancel, reconnect and surface deletion ([runtime-lifecycle.md](reference/runtime-lifecycle.md)).

Topology identifiers are `shared-backend` and `standalone-backend`. The catalog and fixtures are the same for both. Only the adapters differ.

## Rules on untrusted UI

1. **Exact, single version.** Each message's own `version` selects its schemas: `"1.0"` (target) or `"v0.9"`/`"v0.9.1"` (compatibility). `v0.8`, `v1.0` (wrong spelling) and missing versions are `UNSUPPORTED_VERSION`; a version differing from the stream's first message is `MIXED_VERSIONS`. Never parse best-effort, never translate between versions without a documented, tested adapter.
2. **Closed catalog.** Accept only the pinned `catalogId` of the message's version. In 1.0 a component `@catalogId` must be absent or equal to it (this contract does not mix catalogs). An unknown component name rejects the whole message, and the surface keeps its previous state. Unknown props are rejected (v0.9: per-component `unevaluatedProperties: false`; 1.0: the wire `Component` envelope closes the object).
3. **Action allowlist per component.** A component may emit only the IDs in its policy `allowedActions`. Client-side `functionCall` actions (including `openUrl`) are forbidden; actions are server events only. Catalog functions are `rendererOnly` checks, so an agent `callRendererFunction` for them and any `agentFunctionResponse` are rejected (`FUNCTION_CALL_NOT_ALLOWED`).
4. **No executable content.** Strings are rendered as text. Markdown and HTML are never interpreted. `javascript:`, `vbscript:`, `data:text/html` and `<script` anywhere in a message reject it with `UNSAFE_CONTENT`.
5. **Bounded payloads.** Messages are at most 256 KiB, a surface has at most 200 components, the tree is at most 8 levels deep, and strings are at most 10,000 characters. A tree with a cycle is rejected.
6. **Server-side authority.** The server re-authenticates and re-authorises every action from the session. It never acts on a role, price, user ID or permission taken from `action.context`. For `dialog.confirm` and `approval.*`, the server executes the operation it stored under the ID, not one described in the payload.
7. **Idempotency and approval.** For actions with `requiresIdempotencyKey`, the client adapter generates one UUIDv4 per user intent and sends it beside the A2UI message, never inside `context`. High-risk actions need a human click in the UI. An agent cannot confirm them for the user.
8. **Loud failure.** The SDK must report, not swallow: a web `MessageProcessor` gets `validationConfig: STRICT_VALIDATION` and an `errorHandler` (unconfigured, `@a2ui/angular` 0.16.0 renders an unknown component as nothing). SDK validation (`@a2ui/web_core`, `@a2ui/agent` `validatePayload`) never replaces rules 2–4. A rejected message is logged, reported to the agent as an `error` message in the stream's version (`VALIDATION_FAILED` with a JSON Pointer `path`), and shown to the user as an app-owned error state. It is never swallowed.
9. **No secrets in clients.** Model keys and agent credentials stay on the server. Client bundles (web and native) hold only the user's session.

## Golden action payloads

Every platform must produce exactly the same renderer-to-agent (v0.9: client-to-server) `action` message after the same user edit. The validator compares the **canonical form**:

- UTF-8 JSON, object keys sorted, no whitespace, non-ASCII characters left unescaped.
- Integers only. Send decimals and money as strings, because Dart encodes `2.0` as `2.0` and JavaScript encodes it as `2`.
- No `null` values. Every bound path must be initialised in the data model.
- `action.timestamp` must be RFC 3339 UTC (`…Z`). It is replaced with `1970-01-01T00:00:00.000Z` before comparison.

Example (`fixtures/actions/approval-approve.json`, a v0.9 compatibility golden, canonical; a 1.0 action differs only in `"version":"1.0"`):

```json
{"action":{"context":{"comment":"Matches policy","requestId":"req-7731"},"name":"approval.approve","sourceComponentId":"root","surfaceId":"approval-1","timestamp":"1970-01-01T00:00:00.000Z"},"version":"v0.9"}
```

## Validator

```bash
uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py             # exit 0 = contract OK
uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py --selftest  # exit 0 = 28 planted violations caught
```

The validator checks the v0.9 catalog against `catalog-schema.json`, the 1.0 catalog against the official `catalog_definition.json` plus the policy subschemas, both against the JSON Schema 2020-12 metaschema, and the two for parity. It runs every `valid*/` and `invalid*/` fixture through the official wire schemas of the version each message declares (`vendor/a2ui-v1_0/`, byte-identical to upstream and `@a2ui/web_core@0.16.1`; `vendor/a2ui-v0_9/`) plus the contract rules above. `@a2ui/web_core` alone does not enforce the allowlist, payload schemas, unsafe-string scan or one-version-per-stream: keep this gate (or its app-side port) in front of every renderer. It also replays every golden action and every JSONL stream. Its error codes are listed in [catalog-contract.md](reference/catalog-contract.md) §Error codes. Dependencies are pinned inline (`jsonschema==4.26.0`, `referencing==0.37.0`).

## References

| File | Owner | Content |
|---|---|---|
| [catalog-contract.md](reference/catalog-contract.md) | this skill | Component semantics, platform mapping, versioning, unknown-component and version policy, error codes, v0.9→1.0 migration |
| [canonical-catalog-v1_0.json](reference/canonical-catalog-v1_0.json) | this skill | The A2UI 1.0 catalog (target); policy in `metadata.extensions.genui_contract` |
| [canonical-catalog.json](reference/canonical-catalog.json) | this skill | The A2UI v0.9.x catalog (compatibility) with `x-genui` extension blocks |
| [catalog-schema.json](reference/catalog-schema.json) | this skill | JSON Schema for the catalog and for one component instance |
| [fixtures/](reference/fixtures/) | this skill | 1.0: `valid-v1_0/`, `invalid-v1_0/`, `streams-v1_0/`; v0.9.x: `valid/`, `invalid/`, `actions/` (golden), `streams/` (JSONL + `.expect.json`) |
| [vendor/a2ui-v1_0/](reference/vendor/a2ui-v1_0/), [vendor/a2ui-v0_9/](reference/vendor/a2ui-v0_9/) | upstream | Official 1.0 and v0.9 wire and catalog schemas (Apache-2.0), unmodified |
| [backend-topologies.md](reference/backend-topologies.md) | this skill | `shared-backend` vs `standalone-backend` |
| [ag-ui-transport.md](reference/ag-ui-transport.md) | this skill | Carrying A2UI over AG-UI events |
| [action-security.md](reference/action-security.md) | this skill | Server-side action handling, authz, idempotency, approval |
| [runtime-lifecycle.md](reference/runtime-lifecycle.md) | this skill | Stream open, partial delivery, cancel, reconnect, delete |
| [backend-emitters.md](reference/backend-emitters.md) | this skill | Emitting validated A2UI messages from a Python (FastAPI) backend (v0.9 today; see its own version notes); Google ADK and LangGraph hand-off |
| [compatibility-matrix.md](reference/compatibility-matrix.md) | this skill | Pinned versions per platform and evidence level |
| [genui-suitability.md](reference/genui-suitability.md) | this skill | Whether to use GenUI: 8 hard gates, CONTROLLED vs DECLARATIVE per subflow, failure handling, scoring, verdicts |
