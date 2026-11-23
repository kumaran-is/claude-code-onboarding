# GenUI compatibility matrix (A2UI v0.9 contract)

Pinned, tested combinations for the canonical catalog (`canonical-catalog.json`, catalogId `https://catalogs.example.com/genui/canonical/v1/catalog.json`). Verified 2026-11-23 against package sources (`npm pack`, PyPI wheels, pub cache) and the upstream A2UI v0.9 specification. Each fact below was checked against package source or official specification files, not secondary documentation.

Evidence labels: **DOCUMENTED AND TESTED** (ran in a disposable app this session), **DOCUMENTED BUT NOT TESTED** (read in package source or docs only), **UNVERIFIED**.

## Protocol

| Item | Pin | Status |
|---|---|---|
| A2UI wire protocol | `"version": "v0.9"` exactly (`v0.9.1`, `1.0`, `v0.8`, missing → rejected) | DOCUMENTED AND TESTED (validator: 20 invalid fixtures; backend: 62 tests) |
| A2UI v1.0 | Present in `@a2ui/web_core/v1_0` and `@a2ui/angular` root exports; **not adopted**. Migration notes: `catalog-contract.md` §7 | DOCUMENTED BUT NOT TESTED |
| A2UI over AG-UI | `ACTIVITY_SNAPSHOT`, `activityType: "a2ui-surface"`, `content.a2ui_operations` (`@ag-ui/a2ui-middleware` 0.0.16) | DOCUMENTED AND TESTED (Python backend emits it; Angular `@ag-ui/client` 1.0.5 consumes it in both topologies) |

## Clients

| Platform | Packages (pin exactly) | Framework | A2UI entry point | Status |
|---|---|---|---|---|
| Angular (direct, default) | `@a2ui/angular@0.14.0`, `@a2ui/web_core@0.15.0` | Angular 21.2.x (tested 21.2.26) | `@a2ui/angular/v0_9` (never the package root = v1.0) | DOCUMENTED AND TESTED: tsc, ng build, ng test 33/33, Playwright + axe 18/18 (includes one idempotency key per user intent: a double-click sends one request), both topologies, SSE and AG-UI |
| Angular + CopilotKit (optional) | `@copilotkit/angular@0.3.1` (peers Angular ^20 ∥ ^21 ∥ ^22; its own Lit A2UI renderer on `web_core` 0.10.4, `@ag-ui/client` 0.0.57) | Angular 21.2.x | CopilotKit activity renderer | DOCUMENTED BUT NOT TESTED at runtime (installs, bridge compiles). `@copilotkit/angular@0.6.0` requires Angular ^22: **not** usable on 21.2.x |
| React (direct, default) | `@a2ui/react@0.15.0`, `@a2ui/web_core@0.15.0` | React 19 (tested 19.3.1), Vite 8.3.8, TS 5.9.3 | `@a2ui/react/v0_9` (root export = legacy v0.8 API) | DOCUMENTED AND TESTED: tsc, vite build, vitest 30/30, Playwright + axe 12/12, both topologies; exact contract error code for 17 of 20 invalid fixtures; one idempotency key per user intent |
| React + CopilotKit (optional) | `@copilotkit/react-core@1.90.0`, `@copilotkit/a2ui-renderer@1.90.0` | React 19 | `a2ui` provider prop, `A2UIActionInterceptor` | DOCUMENTED BUT NOT TESTED (type definitions only) |
| Flutter | `a2ui_flutter 0.4.0`, `a2ui_core 0.8.0` (optional `a2ui_agent 0.4.0`), all latest on pub.dev 2026-11-23. `genui 0.10.4` is discontinued on pub.dev; the docs.flutter.dev GenUI page (updated 2026-08-19) still calls it alpha, so trust pub.dev | Flutter 3.41.x / Dart 3.10.x declared; tests ran on Flutter 3.44.2 (re-run on 3.41.x before relying on it) | v0.9 `MessageProcessor` behind an app-owned adapter, with an app contract guard and a conventional UI fallback | DOCUMENTED AND TESTED: format 0, analyze 0, `flutter test` 48/48 offline + 20/20 live (both topologies, plus an AG-UI stream run), all 8 components. Maestro: **BLOCKED** (iOS: Flutter 3.44.2 `lipo -verify_arch` fails on Xcode 27; Android: no Android runner in the test app). Sending actions over AG-UI: not tested |

## Backends

| Component | Pin | Status |
|---|---|---|
| Reference backend | Python 3.14, FastAPI 0.165.0, sse-starlette 3.7.1 | DOCUMENTED AND TESTED: 62/62 pytest, ruff, mypy --strict; shared (one server) and standalone (one per client) modes |
| AG-UI Python SDK | `ag-ui-protocol` 1.0.0 | DOCUMENTED AND TESTED (event types and `RunAgentInput` parsed in tests) |
| AG-UI TS client | `@ag-ui/client` 1.0.5 | DOCUMENTED AND TESTED via Angular. Splits SSE frames on `\n\n` only, so servers must send LF-only frames |
| Google ADK hand-off | ADK 1.29 (`google-adk` skill) | DOCUMENTED BUT NOT TESTED in this contract |
| LangGraph hand-off | LangGraph 1.0.7 (`agentic-ai-dev` skill) | DOCUMENTED BUT NOT TESTED in this contract |
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

- `@a2ui/web_core@0.15.0` depends on zod 3.25.76, which `npm audit` rates HIGH (GHSA-mrhx-c7xc-m3w5). Forcing zod 4 crashes `web_core` at runtime. Mitigation:
  - Reject any inbound message larger than the contract's size limit before parsing it.
  - Record the exception in the security review.
  - Re-run `npm audit` on every A2UI upgrade.
- `@a2ui/markdown-it@0.2.2` brings in moderate DOMPurify advisories. A `dompurify@3.5.0` override clears them and was verified in React.
- In `web_core`, `STRICT_VALIDATION` does not validate props and does not reject unversioned messages. An app-owned ingest guard is mandatory (`catalog-contract.md` §5).
- Do not upgrade one platform's A2UI packages alone. Re-run the contract validator and the parity fixtures on every platform first.
