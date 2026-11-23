# A2UI Angular Renderer

> **When to use**: Rendering agent-generated A2UI surfaces (protocol 1.0, v0.9.x compatibility path) in an Angular 22.x app
> **Time estimate**: 4–8 hours for the first catalog; 1–2 hours per additional component
> **Prerequisites**: Angular SPA scaffolded (`/scaffold-angular-app`); a backend agent that emits A2UI messages; `a2ui-angular` and `genui-contract` skills loaded

## Overview

Use the official SDK: `@a2ui/angular` 0.16.0 + `@a2ui/web_core` 0.16.1, pinned exactly. Do not hand-build a recursive renderer. Your work is four things:

- a custom `AngularCatalog` for the shared catalog IDs;
- an app ingest gate in front of `processMessages`;
- a transport adapter;
- an action gateway that the server re-authorizes.

All of these are compiled and tested. Copy them from the skill instead of writing them from scratch:

- `.claude/skills/a2ui-angular/reference/canonical-catalog-angular22-components.md`: component APIs for both wire versions, dispatch allowlist, ActionCard, ApprovalRequest, EditableForm.
- `.claude/skills/a2ui-angular/reference/canonical-catalog-angular22-session.md`: stream session (contract gate, size cap, cancellation, bounded reconnect), providers per wire version, lazy routes.

---

## Iron Law (from `skills/a2ui-angular/SKILL.md`)

> **VALIDATE ALL A2UI PAYLOADS BEFORE RENDERING — NEVER TRUST AGENT OUTPUT DIRECTLY**
> Agent-generated payloads can contain unknown components, unsafe URLs or forged actions. Validate them at the renderer boundary. The server must still authorize every action.

---

## A2UI message structure

An A2UI stream is a sequence of messages. Each message carries one wire version and targets one surface. Components form a flat adjacency list (`id` plus child IDs), not a nested tree. Props are literals or data-model bindings. The example below is a v0.9 surface from the shared contract samples; 1.0 uses the same shape with `"version": "1.0"`, the 1.0 catalog ID and `{"@path": …}` bindings.

```json
{"version": "v0.9", "createSurface": {"surfaceId": "card-1", "catalogId": "https://catalogs.example.com/genui/shared-runtime/v1/catalog.json"}}
{"version": "v0.9", "updateComponents": {"surfaceId": "card-1", "components": [
  {"id": "root", "component": "ActionCard", "title": {"path": "/card/title"}, "subtitle": "Suggested next step",
   "accessibility": {"label": "Suggested booking"},
   "actions": [{"label": "Open booking", "variant": "primary",
                "action": {"event": {"name": "item.open", "context": {"itemId": "booking-1042"}}}}]}
]}}
```

Wire format and catalog rules: `.claude/skills/genui-contract/reference/catalog-contract.md`. Version pins: `.claude/skills/genui-contract/reference/compatibility-matrix.md`.

---

## Phases

### Phase 1 — Load skills and pick the catalog

**Skills**: `genui-contract` (catalog, versions, action security), then `a2ui-angular`.
**Agent**: `a2ui-angular`

1. Choose the catalog IDs from the shared contract (`ActionCard`, `DataSummaryTable`, `ApprovalForm`, `SelectionList`, `DetailPanel`, `StatusIndicator`, `InputForm`, `ConfirmationDialog`). Never put Angular class names on the wire.
2. Choose the wire version per surface. Target 1.0, with v0.9 as the compatibility path. Use one version per stream, and never mix versions on one surface.
3. Choose the topology (`shared-backend` or `standalone-backend`). Only the adapter's base URL, read from runtime config, differs.
4. CopilotKit Angular 0.6.0 is optional and **v0.9 only**: it silently accepts a 1.0 stream. See `reference/copilotkit-angular.md`.

### Phase 2 — Catalog and providers (SDK)

Dispatch the `a2ui-angular` agent with the contract, the version(s) and the topology. The renderer is the SDK's `SurfaceComponent`, fed by a custom catalog:

- **Registration.** Register each component with `new AngularCatalog(catalogId, version, [createComponentImplementation(Api, Component)], functions)`. Register the catalog functions you use (for example `required`, `email`) from `BASIC_FUNCTIONS`. `BasicCatalogBase` `extraComponents`/`functions` are deprecated.
- **Component class.** Components extend `CatalogComponent<typeof Api>`. The API's zod schema (zod 3.25.76, the same copy as `web_core`) is the per-component contract.
- **Validation.** Set `processorOptions.validationConfig: STRICT_VALIDATION`. It is the control for unknown components and invalid props: removing it made the unknown-component tests fail.
- **Lazy routes.** Put GenUI behind a lazy route: one route and one renderer per wire version. Re-provide `A2uiRendererService` in the route's `providers`, or the browser fails with `Catalog not found`.

### Phase 3 — App ingest gate (before `processMessages`)

`web_core` 0.16.1 does not enforce the whole contract. In tests it accepted `javascript:` strings, a v0.9 `{"path"}` binding on a 1.0 surface, and mixed versions in one stream. The session in `canonical-catalog-angular22-session.md` runs these checks first:

| Check | Error code |
|---|---|
| Byte cap **before** `JSON.parse` | `MESSAGE_TOO_LARGE` |
| One wire version per stream | `MIXED_VERSIONS` |
| `forbiddenStringPatterns` (`javascript:`, HTML script) | `UNSAFE_CONTENT` |
| No legacy `{"path"}` bindings on 1.0 | `SCHEMA_INVALID` |

Every failure is mapped to a visible error state, never an empty surface.

### Phase 4 — Transport adapter (AG-UI or plain SSE)

Keep the transport in one adapter that yields A2UI messages, so the renderer never depends on it. Do not use `EventSource`: it cannot send an `Authorization` header, and a prompt in the query string ends up in logs. The adapter below uses `@ag-ui/client` 1.0.5 `HttpAgent` (API read from the package and run against a test backend) and declares which A2UI versions the renderer can draw. Declare `1.0` only if the `a2ui-angular` skill records a passing 1.0 render test for the pinned `@a2ui/angular`; otherwise declare v0.9 only. Negotiation rules: `.claude/skills/genui-contract/reference/ag-ui-transport.md`.

```typescript
// a2ui-transport.ts: AG-UI HTTP SSE -> A2UI messages. Wrap it in the app's agent service.
import { HttpAgent } from '@ag-ui/client';
import { Observable, filter, mergeMap, from } from 'rxjs';

export function a2uiOverAgUi(url: string, token: string, catalogIdV09: string, runId: string): Observable<unknown> {
  const agent = new HttpAgent({ url, headers: { authorization: `Bearer ${token}` } });
  return agent.run({
    threadId: crypto.randomUUID(), runId, messages: [], tools: [], context: [], state: {},
    forwardedProps: { a2uiClientCapabilities: { 'v0.9': { supportedCatalogIds: [catalogIdV09] } } },
  }).pipe(
    filter((e) => e.type === 'ACTIVITY_SNAPSHOT' && (e as { activityType?: string }).activityType === 'a2ui-surface'),
    // replace: true -> each snapshot holds every operation for the surface; re-create the surface from it
    mergeMap((e) => from((e as { content: { a2ui_operations: unknown[] } }).content.a2ui_operations)),
  );
}
```

A `RUN_ERROR` event or a non-2xx response (401, 403, 406 for an undeclared version) errors the stream: show an error state, never an empty surface. Unsubscribing cancels the HTTP request, and the server stops the run.

---

### Phase 5 — Action gateway

- **Client side.** The dispatcher checks the event name against the component's allowlist, resolves the action with `new DataContext(surface, dataContextPath).resolveAction(action, { userActivation: true })`, and sends it with `surface.dispatchAction(resolved, componentId)`.
- **One request per intent.** Send exactly one request per user intent, guarded in-flight and carrying an `Idempotency-Key`.
- **Authorization is the server's job.** The client allowlist is not authorization. The server re-authorizes every action (tenant, role, server-held approval) and rejects extra payload fields. See `.claude/skills/genui-contract/reference/action-security.md`.

---

## Quick Reference

| Phase | Action | Gate |
|-------|--------|------|
| 1 — Catalog | Contract IDs, wire version per surface, topology | Matches `genui-contract` |
| 2 — SDK | `AngularCatalog` + `STRICT_VALIDATION`, lazy route per version | Unknown component → `VALIDATION_FAILED` error state (test) |
| 3 — Gate | Size cap, version, unsafe strings, legacy bindings | Each invalid shared sample shows its error code (test) |
| 4 — Transport | AG-UI or JSONL adapter, bearer auth, declared versions | 401/406/`RUN_ERROR` show an error state |
| 5 — Actions | Allowlist, resolve, dispatch, idempotency, server authz | Double click sends one request; 403 is shown |
| Verify | `ng build`, `ng test`, Playwright + axe | All exit 0; `npm audit` result recorded (zod HIGH is a known, unresolved finding: see the skill) |

---

## Common Pitfalls

- **Hand-rolled tree renderer instead of the SDK** — loses `STRICT_VALIDATION`, binding resolution and data-model write-back
- **Trusting SDK validation alone** — it does not reject `javascript:` URLs, mixed versions or legacy bindings on 1.0; add the app gate
- **`provideA2Ui` in a lazy route without re-providing `A2uiRendererService`** — `Catalog not found`
- **Sending a 1.0 surface to CopilotKit Angular 0.6.0** — accepted silently and rendered by a v0.9 processor
- **Treating the client allowlist as authorization** — the server re-authorizes every action
- **Trusting agent output as HTML** — never use `innerHTML` with agent-generated content

## Related Workflows

- [`feature-angular-spa.md`](feature-angular-spa.md) — base Angular patterns
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — the backend agent generating A2UI payloads
- [`security-audit.md`](security-audit.md) — security review of the renderer boundary
