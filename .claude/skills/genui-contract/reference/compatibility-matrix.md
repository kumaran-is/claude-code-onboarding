# GenUI compatibility matrix (target A2UI 1.0, compatibility path v0.9.x)

Two catalog documents carry one contract: `canonical-catalog-v1_0.json` (A2UI **1.0**, catalogId `https://catalogs.example.com/genui/canonical-a2ui-1_0/v1/catalog.json`) and `canonical-catalog.json` (A2UI **v0.9.x**, catalogId `https://catalogs.example.com/genui/canonical/v1/catalog.json`). Same 8 components, same 9 actions, same payload schemas; the validator fails if they drift. Versions re-checked 2026-11-23 with `npm view <pkg> dist-tags.latest`, `https://pub.dev/api/packages/<name>`, `https://a2ui.org/specification/versions.json` and the installed `@a2ui/web_core@0.16.1` source.

Evidence labels: **DOCUMENTED AND TESTED** (ran this session), **DOCUMENTED BUT NOT TESTED** (read in package source or docs only), **UNVERIFIED**, **PENDING** (owned by a renderer track that has not reported executable evidence).

## Protocol

| Item | Pin | Status |
|---|---|---|
| A2UI wire protocol, target | `"version": "1.0"` (no `v`; status `current` in `versions.json`). Schemas vendored in `vendor/a2ui-v1_0/` (byte-identical to upstream `main` and to `@a2ui/web_core@0.16.1` `src/v1_0/schemas/`) | DOCUMENTED AND TESTED (validator: 3 valid, 7 invalid, 2 stream fixtures; `@a2ui/web_core` 0.16.1 `MessageProcessor` processed the 1.0 samples with 0 errors) |
| A2UI wire protocol, compatibility | `"v0.9"` and `"v0.9.1"` (status `previous`; one web_core adapter handles both) | DOCUMENTED AND TESTED (validator: all pre-existing v0.9 fixtures) |
| Rejected | `"v0.8"` (deprecated), `"v1.0"` (non-canonical spelling), missing version, two versions in one stream (`MIXED_VERSIONS`) | DOCUMENTED AND TESTED |
| A2UI over AG-UI | Surface: `ACTIVITY_SNAPSHOT`, `activityType: "a2ui-surface"`, `content.a2ui_operations`; user actions back via `forwardedProps.a2uiAction.userAction` (`@ag-ui/a2ui-middleware` 0.0.16 package source) | DOCUMENTED AND TESTED on v0.9 and 1.0 for the backend → `@ag-ui/client` 1.0.5 `HttpAgent` path (Node 26, `@ag-ui/encoder` 1.0.5, 1.0 surfaces validated against the 1.0 catalog, 21 LIVE-PROTOCOL tests). 1.0 rendering over AG-UI in a renderer: PENDING |

## Version selection

| Technology | Current (pinned in this repo before the 1.0 migration; historical) | Latest stable (registry, 2026-11-23) | 1.0 support (evidence) | Selected target |
|---|---|---|---|---|
| `@a2ui/web_core` | 0.15.0 | 0.16.1 | YES: exports `./v1_0`, `./catalogs/basic/v1`; CHANGELOG 0.16.x describes 1.0; LIVE-PROTOCOL run this session processed the 1.0 samples | 0.16.1 (core message processing on 1.0) |
| `@a2ui/angular` | 0.14.0 | 0.16.0 (peer `@angular/* ^22.2.3`) | PROVEN for ActionCard, EditableForm, ApprovalRequest + the basic catalog: the package root (no `./v1_0` subpath) with `AngularCatalog(id, '1.0')` + `useUniversalComponents: true`. Every shared 1.0 and v0.9 sample in Vitest LIVE-PROTOCOL (valid render; invalid → pinned error code), Playwright + axe (Chromium, production build, 0 violations) on both versions, and a LIVE run against the shared AG-UI backend on 1.0 | 0.16.0 on 1.0 for those components (prove others first); v0.9.x still supported |
| `@a2ui/react` | 0.15.0 | 0.16.1 | PROVEN: the package root (no `./v1_0` subpath) renders 1.0 with `Catalog(id, '1.0')` and the `@a2ui/web_core/v1_0` schemas; Vitest 27/27 and Playwright + axe 16/16 (Chromium) on both 1.0 and v0.9, real packages, mocked transport | 0.16.1 on 1.0 (v0.9.x still supported) |
| `@a2ui/lit` | not used | 0.16.0 | UNVERIFIED (not inspected) | not selected |
| `@copilotkit/angular` | 0.3.1 / 0.6.0 (inconsistent) | 0.6.0 (peer Angular ^22) | NOT SUPPORTED: its renderer imports `@a2ui/web_core/v0_9` from a nested 0.10.4 that has no `./v1_0` export, and it accepts a 1.0 stream silently (no error; tested by execution) | 0.6.0 on v0.9.x only |
| `@copilotkit/a2ui-renderer`, `@copilotkit/react-core` | 1.90.0 | 1.90.0 | PARTIAL: `a2ui-renderer` pins `@a2ui/web_core` 0.15.0 and rejects `@accessibility` | 1.90.0 on v0.9.x; not on 1.0 |
| `@ag-ui/client` | 1.0.5 | 1.0.5 | transport only (carries A2UI operations, version-agnostic) | 1.0.5 |
| `@ag-ui/a2ui-middleware` | 0.0.16 | 0.0.16 | backend → client path tested with 1.0 surfaces (see Protocol); renderer side over AG-UI PENDING | 0.0.16 |
| `a2ui_flutter` / `a2ui_core` (pub) | 0.4.0 / 0.8.0 | 0.5.0 / 0.9.0 | PROVEN on both pairs, for both 1.0 and v0.9.x (LIVE-PROTOCOL, real `MessageProcessor` + `A2uiSurface`, shared valid samples render, tapped actions emit correctly versioned envelopes, app gate rejects every invalid sample): 0.5.0 / 0.9.0 on Flutter 3.50.1 and 0.4.0 / 0.8.0 on Flutter 3.44.2, 31/31 widget tests each. Maestro iOS simulator flow: 0.5.0 only (0.4.0 device run NOT RUN). Pub metadata lists v0.9.1 + v1.0 | The pairs differ in SDK floor, not protocol: **0.5.0 / 0.9.0 for Flutter >=3.47 / Dart >=3.13**; **0.4.0 / 0.8.0 for Flutter 3.38–3.46** (only for apps still below 3.47; the repo targets 3.50.x; tested on 3.44.2) |
| `a2ui_agent` (pub) | 0.4.0 | 0.5.0 | follows the matching `a2ui_flutter` pair (same SDK floor); not separately tested | 0.5.0 with 0.5.0 / 0.9.0; 0.4.0 with 0.4.0 / 0.8.0 |

Rule: a renderer row moves to "1.0" only with a passing test in which that renderer's real package renders a 1.0 `createSurface`/`updateComponents` stream. Until then it stays on v0.9.x and the blocker is recorded here. `@a2ui/web_core` processing a 1.0 stream is not evidence for any renderer built on it.

## Clients (current pins, 2026-11-23)

| Platform | Packages (pin exactly) | Framework | A2UI entry point | Status |
|---|---|---|---|---|
| Angular (direct, default) | `@a2ui/angular@0.16.0`, `@a2ui/web_core@0.16.1`, `zod@3.25.76` exact | Angular 22.x (tested 22.3.0) | v0.9.x: `@a2ui/angular/v0_9`; 1.0: the package root (v1 `BasicCatalog` + `useUniversalComponents: true`, or `AngularCatalog(id, '1.0')`) DOCUMENTED AND TESTED on 1.0 and v0.9: tsc strict, ng build, ng lint, ng test (Vitest) 30 passed over all shared samples, Playwright + axe (Chromium, production build) 7/7 on both versions, LIVE 1.0 run against the shared backend; negative controls for SDK validation, the unsafe-string gate and the dispatch allowlist. Unknown components: `STRICT_VALIDATION` + `errorHandler` (primary); an app gate adds `javascript:`, mixed-version and legacy-binding checks. Put GenUI in a lazy route and re-provide `A2uiRendererService` there. (Before this migration: 0.14.0 + web_core 0.15.0 on Angular 21.2.x, 33/33 + 18/18.) |
| Angular + CopilotKit (optional) | `@copilotkit/angular@0.6.0` (peer Angular ^22, `@angular/cdk` 22.3.0; nests `@ag-ui/client` 1.0.2 and its own Lit A2UI renderer on `web_core` 0.10.4; SLSA provenance) | Angular 22.x | CopilotKit activity renderer | v0.9 only. 1.0: NOT SUPPORTED, and it accepts a 1.0 stream silently, so never send it one. Tested with a hand-built tool call (MOCK, HITL); no live CopilotKit runtime. (Before: 0.3.1 on Angular 21.2.x, compile-only.) |
| React (direct, default) | `@a2ui/react@0.16.1`, `@a2ui/web_core@0.16.1`, `zod@3.25.76` | React 19, Vite 8, TS 5.9.3 | 1.0: the package root with `Catalog(id, '1.0')` + `@a2ui/web_core/v1_0` schemas; v0.9.x: `@a2ui/react/v0_9` | DOCUMENTED AND TESTED on 1.0 and v0.9: ESLint, Vitest 27/27, Playwright + axe 16/16 (Chromium, 375 and 1280 px) with negative controls; real packages, mocked transport. (Before: 0.15.0 + web_core 0.15.0, v0.9 only.) |
| React + CopilotKit (optional) | `@copilotkit/react-core@1.90.0`, `@copilotkit/a2ui-renderer@1.90.0` | React 19 | `a2ui` provider prop, `A2UIActionInterceptor` | DOCUMENTED BUT NOT TESTED (type definitions only) |
| Flutter (Flutter >=3.47) | `a2ui_flutter 0.5.0`, `a2ui_core 0.9.0` (optional `a2ui_agent 0.5.0`), latest on pub.dev 2026-11-23 | Flutter >=3.47 / Dart >=3.13 (tested 3.50.1) | 1.0 or v0.9.x `MessageProcessor` + `A2uiSurface` behind the app contract gate, hosted in a `material_ui` 1.11.1 app: `a2ui_flutter` still builds on `flutter/material.dart`, so one bridge file (`MaterialUiCompatibilityBridge` + legacy `Material`) wraps the surface; the bridge is `@Deprecated` (temporary), and component themes do not reach the A2UI basic widgets | DOCUMENTED AND TESTED (LIVE-PROTOCOL) on 1.0 and v0.9.x: 31/31 widget tests, all shared valid samples render, versioned action envelopes, app gate rejects every invalid sample. `material_ui` host on Flutter 3.50.1: 36 widget tests (bridge theme + a11y), removing either half of the bridge fails; Maestro iOS simulator flow 8/8. Text-entry Maestro flow FAIL (iOS keyboard covers the result line; field reads back doubled text); typing is proven by widget tests only. Android device run: BLOCKED (no emulator) |
| Flutter (Flutter 3.38–3.46 older-SDK path; the repo targets 3.50.x, so this row applies only to apps still below 3.47; tested on 3.44.2) | `a2ui_flutter 0.4.0`, `a2ui_core 0.8.0` (optional `a2ui_agent 0.4.0`); renders **1.0 and v0.9.x** (31/31 LIVE-PROTOCOL widget tests on Flutter 3.44.2 with the fixed shared samples; Maestro device run NOT RUN on this pair). `genui 0.10.4` is discontinued on pub.dev; the docs.flutter.dev GenUI page (updated 2026-08-19) still calls it alpha, so trust pub.dev | Flutter 3.38–3.46 declared by the packages; tests ran on Flutter 3.44.2 (historical; not re-run on 3.50) | 1.0 or v0.9.x `MessageProcessor` behind an app-owned adapter, with an app contract guard and a conventional UI fallback | DOCUMENTED AND TESTED (2026-11-23, 1.0 + v0.9.x): 31/31 LIVE-PROTOCOL widget tests on 3.44.2. Earlier v0.9 run: format 0, analyze 0, `flutter test` 48/48 offline + 20/20 live (both topologies, plus an AG-UI stream run), all 8 components. Maestro: **BLOCKED** (iOS: Flutter 3.44.2 `lipo -verify_arch` fails on Xcode 27; Android: no Android runner in the test app). Sending actions over AG-UI: not tested |

## Backends

| Component | Pin | Status |
|---|---|---|
| Reference backend | Python 3.14, FastAPI 0.165.0, sse-starlette 3.7.1 | DOCUMENTED AND TESTED: 62/62 pytest, ruff, mypy --strict; shared (one server) and standalone (one per client) modes |
| AG-UI Python SDK | `ag-ui-protocol` 1.0.0 | DOCUMENTED AND TESTED (event types and `RunAgentInput` parsed in tests) |
| AG-UI TS client | `@ag-ui/client` 1.0.5 | DOCUMENTED AND TESTED via Angular. Splits SSE frames on `\n\n` only, so servers must send LF-only frames |
| Google ADK hand-off | ADK 2.15 (`google-adk` skill) | DOCUMENTED BUT NOT TESTED in this contract |
| LangGraph hand-off | LangGraph 1.2.24 (`agentic-ai-dev` skill) | DOCUMENTED BUT NOT TESTED in this contract |
| Node emitter | none | UNVERIFIED (not covered) |

## Cross-client action parity

The action payloads of each client were compared after a real user edit, in the canonical form defined in `catalog-contract.md`: sorted keys, integers only, no null, timestamp zeroed. The golden payloads are in `fixtures/actions/`.

| Action | Angular | React | Flutter |
|---|---|---|---|
| `item.open` | match (shared, standalone, AG-UI) | match (shared, standalone) | match |
| `form.submit` | match (shared, standalone) | match (shared, standalone) | match |
| `approval.approve` | match (shared, standalone) | match (shared, standalone) | match |
| `approval.reject` | match (shared, standalone) | not exercised | match |
| `selection.submit`, `dialog.confirm` | not exercised | not exercised | match |

The comparison covers 25 payload files with 0 differences. A planted value change makes the comparison fail.

## Known risks

- `@a2ui/web_core@0.16.1` (as 0.15.0 before it) depends on zod 3.25.76 (it checks `instanceof z.ZodType`), which `npm audit` rates HIGH (GHSA-mrhx-c7xc-m3w5). Forcing zod 4 crashes `web_core` at runtime. Mitigation:
  - Reject any inbound message larger than the contract's size limit before parsing it.
  - Record the exception in the security review.
  - Re-run `npm audit` on every A2UI upgrade.
- `@a2ui/markdown-it@0.2.2` brings in moderate DOMPurify advisories. A `dompurify@3.5.0` override clears them and was verified in React.
- In `web_core`, `STRICT_VALIDATION` does not validate props and does not reject unversioned messages. An app-owned ingest guard is mandatory (`catalog-contract.md` §5).
- `@a2ui/web_core` 0.16.1 accepts a legacy v0.9 `{"path"}` binding inside a 1.0 message (it is a literal object in 1.0). Emitters reject it before streaming and renderers before processing (`SCHEMA_INVALID`).
- SDK structural validation is not the contract: `@a2ui/web_core` 0.16.1 (`MessageProcessor`, STRICT) and `@a2ui/agent` 0.2.1 (`validatePayload`) both accepted a non-allowlisted action, a `javascript:` URL and a v0.9 `{"path"}` binding in a 1.0 message. Keep the app allowlist, payload schema, URL scheme check and server authorization.
- `@a2ui/angular` 0.16.0 without `validationConfig` + `errorHandler` logs an unknown component to the console and renders nothing. Configure both and show a fallback; `post-edit-genui-advisory.sh` flags a bare `new MessageProcessor(`.
- Do not upgrade one platform's A2UI packages alone. Re-run the contract validator and the parity fixtures on every platform first.
