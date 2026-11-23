---
name: genui-contract
description: "Framework-neutral GenUI contract on A2UI v0.9: canonical component catalog, action allowlist and payload schemas, fixtures and the deterministic validator shared by Angular, React, Flutter and backends. Use when deciding whether a workflow should use GenUI, changing a GenUI catalog, component or action, choosing A2UI vs AG-UI vs CopilotKit, checking cross-platform parity or planning v0.9→v1.0."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
metadata:
  triggers: GenUI contract, generative UI, should this use GenUI, GenUI suitability, A2UI catalog, A2UI v0.9, canonical catalog, component catalog, catalogId, action allowlist, golden action payload, A2UI fixtures, contract-first, cross-platform GenUI, AG-UI, CopilotKit, A2UI vs AG-UI, catalog versioning, A2UI v1.0 migration
  related-skills: a2ui-angular, flutter-genui, react-spa, streaming-protocols, security-reviewer, agentic-ai-dev, google-adk
  domain: frontend
  role: specialist
  scope: design
  output-format: specification
last-reviewed: "2026-11-23"
---

# GenUI Contract: one A2UI v0.9 catalog for every platform

The contract is the single source of truth between whatever generates UI (agent, backend, template engine) and every renderer (Angular, React, Flutter). Platforms differ only in how they draw a component. The catalog, the actions and the payloads they send are the same everywhere.

## Iron Law

**GENERATED UI IS UNTRUSTED INPUT. A SURFACE RENDERS ONLY COMPONENTS AND ACTIONS THAT THE PINNED CATALOG ALLOWLISTS, ONLY AFTER STRICT SCHEMA VALIDATION, AND ONLY ON WIRE VERSION `v0.9`. NOTHING FROM THE MODEL IS EXECUTED AS HTML, JS OR DART, AND NOTHING IN A PAYLOAD GRANTS PERMISSION. THE SERVER AUTHORISES EVERY ACTION AGAIN.**

## When to use

| Situation | Use |
|---|---|
| Should this workflow use GenUI at all? Which subflows stay deterministic? | [genui-suitability.md](reference/genui-suitability.md): hard gates, the deterministic baseline, verdict. Run it before the workflow below |
| New GenUI feature on any platform | Start here: pick components and actions from the canonical catalog, then go to the platform skill |
| Adding or changing a component, prop or action | [catalog-contract.md](reference/catalog-contract.md) §Versioning, then regenerate fixtures and run the validator |
| Angular renderer code | `a2ui-angular` skill (`@a2ui/angular@0.14.0`, `@a2ui/web_core@0.15.0`) |
| Flutter renderer code | `flutter-genui` skill (`a2ui_flutter 0.4.0`, `a2ui_core 0.8.0`) |
| React renderer code | `react-spa` skill plus this contract (no dedicated React A2UI skill yet) |
| Choosing a backend shape | [backend-topologies.md](reference/backend-topologies.md) |
| Plain SSE/NDJSON transport | `streaming-protocols` skill |

Do not use this skill for a chat UI with no generated components (`ai-chat`) or for agent logic (`agentic-ai-dev`, `google-adk`).

## Which protocol does what

| Technology | Role | Required? | Platforms | Notes |
|---|---|---|---|---|
| **A2UI v0.9** | Generated-UI payload contract: surfaces, components, data model, actions | Yes, it is the contract | Angular, React, Flutter, any backend | This skill. Wire `version` is exactly `"v0.9"` |
| **AG-UI** | Agent event and transport protocol (runs, messages, tool calls, state events) | Optional. Only when the backend already speaks it | Web clients. Flutter needs an adapter that you build and test | Carries A2UI messages as payloads, it does not replace them. See [ag-ui-transport.md](reference/ag-ui-transport.md) |
| **CopilotKit** | App-level copilot framework for Angular and React | Optional. Never required just to render A2UI | Angular, React | Use it only for its copilot features. The A2UI renderer works without it |
| **Flutter GenUI (`a2ui_flutter`)** | Flutter renderer for A2UI | Yes for Flutter | Flutter | Sits behind an app-owned adapter. It does not consume AG-UI or CopilotKit streams directly |

## Contract-first workflow (after the suitability review)

1. **Pick from the catalog.** Use the 8 canonical components ([canonical-catalog.json](reference/canonical-catalog.json)). If none fits, propose a catalog change. Do not add a platform-only component.
2. **Name the actions.** Every interactive control emits one allowlisted action ID (`item.open`, `approval.approve`, …). Each ID has a payload schema, a risk level, a side-effect flag, an idempotency requirement and a human-approval requirement in `x-genui.actions`.
3. **Write fixtures before renderers.** Add the surface to `fixtures/valid/`. Add the golden action the UI must send after a given user edit to `fixtures/actions/`. Add the failure cases you rely on to `fixtures/invalid/`.
4. **Validate.** Run `uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py`, which must exit 0, and `--selftest`, which must also exit 0.
5. **Implement each platform.** Map the canonical ID to the platform component ([catalog-contract.md](reference/catalog-contract.md) §Platform mapping). Each platform's tests replay the same fixtures and must emit the golden action payload exactly (canonical form).
6. **Wire the backend.** Choose a topology ([backend-topologies.md](reference/backend-topologies.md)) and an emitter ([backend-emitters.md](reference/backend-emitters.md)). Enforce the action rules in [action-security.md](reference/action-security.md).
7. **Check the runtime lifecycle.** Cover stream open, partial delivery, cancel, reconnect and surface deletion ([runtime-lifecycle.md](reference/runtime-lifecycle.md)).

Topology identifiers are `shared-backend` and `standalone-backend`. The catalog and fixtures are the same for both. Only the adapters differ.

## Rules on untrusted UI

1. **Exact version.** Accept only `"version": "v0.9"`. `v0.8`, `v0.9.1` and `1.0` are rejected explicitly with `UNSUPPORTED_VERSION`, never parsed best-effort. Versions are never mixed on one surface.
2. **Closed catalog.** Accept only the pinned `catalogId`. An unknown component name rejects the whole `updateComponents` message, and the surface keeps its previous state. Every component sets `unevaluatedProperties: false`, so unknown props are rejected too.
3. **Action allowlist per component.** A component may emit only the IDs in its `x-genui.allowedActions`. Client-side `functionCall` actions (including `openUrl`) are forbidden. Actions are server events only.
4. **No executable content.** Strings are rendered as text. Markdown and HTML are never interpreted. `javascript:`, `vbscript:`, `data:text/html` and `<script` anywhere in a message reject it with `UNSAFE_CONTENT`.
5. **Bounded payloads.** Messages are at most 256 KiB, a surface has at most 200 components, the tree is at most 8 levels deep, and strings are at most 10,000 characters. A tree with a cycle is rejected.
6. **Server-side authority.** The server re-authenticates and re-authorises every action from the session. It never acts on a role, price, user ID or permission taken from `action.context`. For `dialog.confirm` and `approval.*`, the server executes the operation it stored under the ID, not one described in the payload.
7. **Idempotency and approval.** For actions with `requiresIdempotencyKey`, the client adapter generates one UUIDv4 per user intent and sends it beside the A2UI message, never inside `context`. High-risk actions need a human click in the UI. An agent cannot confirm them for the user.
8. **Loud failure.** A rejected message is logged, reported to the agent as a v0.9 `error` (`VALIDATION_FAILED` with a JSON Pointer `path`), and shown to the user as an app-owned error state. It is never swallowed.
9. **No secrets in clients.** Model keys and agent credentials stay on the server. Client bundles (web and native) hold only the user's session.

## Golden action payloads

Every platform must produce exactly the same client-to-server `action` message after the same user edit. The validator compares the **canonical form**:

- UTF-8 JSON, object keys sorted, no whitespace, non-ASCII characters left unescaped.
- Integers only. Send decimals and money as strings, because Dart encodes `2.0` as `2.0` and JavaScript encodes it as `2`.
- No `null` values. Every bound path must be initialised in the data model.
- `action.timestamp` must be RFC 3339 UTC (`…Z`). It is replaced with `1970-01-01T00:00:00.000Z` before comparison.

Example (`fixtures/actions/approval-approve.json`, canonical):

```json
{"action":{"context":{"comment":"Matches policy","requestId":"req-7731"},"name":"approval.approve","sourceComponentId":"root","surfaceId":"approval-1","timestamp":"1970-01-01T00:00:00.000Z"},"version":"v0.9"}
```

## Validator

```bash
uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py             # exit 0 = contract OK
uv run .claude/skills/genui-contract/scripts/validate_a2ui_contract.py --selftest  # exit 0 = 10 planted violations caught
```

The validator checks the catalog against `catalog-schema.json` and the JSON Schema 2020-12 metaschema. It runs every valid and invalid fixture through the official v0.9 wire schemas (vendored from `@a2ui/web_core@0.15.0`) plus the contract rules above. It also replays every golden action and every JSONL stream. Its error codes are listed in [catalog-contract.md](reference/catalog-contract.md) §Error codes. Dependencies are pinned inline (`jsonschema==4.26.0`, `referencing==0.37.0`).

## References

| File | Owner | Content |
|---|---|---|
| [catalog-contract.md](reference/catalog-contract.md) | this skill | Component semantics, platform mapping, versioning, unknown-component and version policy, error codes, v0.9→v1.0 migration |
| [canonical-catalog.json](reference/canonical-catalog.json) | this skill | The A2UI v0.9 catalog with `x-genui` extension blocks |
| [catalog-schema.json](reference/catalog-schema.json) | this skill | JSON Schema for the catalog and for one component instance |
| [fixtures/](reference/fixtures/) | this skill | `valid/`, `invalid/`, `actions/` (golden), `streams/` (JSONL + `.expect.json`) |
| [vendor/a2ui-v0_9/](reference/vendor/a2ui-v0_9/) | upstream | Official v0.9 wire schemas (Apache-2.0), unmodified |
| [backend-topologies.md](reference/backend-topologies.md) | this skill | `shared-backend` vs `standalone-backend` |
| [ag-ui-transport.md](reference/ag-ui-transport.md) | this skill | Carrying A2UI over AG-UI events |
| [action-security.md](reference/action-security.md) | this skill | Server-side action handling, authz, idempotency, approval |
| [runtime-lifecycle.md](reference/runtime-lifecycle.md) | this skill | Stream open, partial delivery, cancel, reconnect, delete |
| [backend-emitters.md](reference/backend-emitters.md) | this skill | Emitting validated v0.9 messages from a Python (FastAPI) backend; Google ADK and LangGraph hand-off |
| [compatibility-matrix.md](reference/compatibility-matrix.md) | this skill | Pinned versions per platform and evidence level |
| [genui-suitability.md](reference/genui-suitability.md) | this skill | Whether to use GenUI: 8 hard gates, CONTROLLED vs DECLARATIVE per subflow, failure handling, scoring, verdicts |
