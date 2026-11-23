---
name: a2ui-angular
description: "A2UI (Agent-to-User Interface) renderer development for Angular 22.x. Use when building A2UI component renderers, agent-driven UIs, A2UI catalogs, action handlers, or streaming A2UI payloads. Covers protocol implementation, security validation, component mapping, and agent integration."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__angular-cli__get_best_practices, mcp__angular-cli__search_documentation, mcp__context7__resolve-library-id, mcp__context7__query-docs
metadata:
  triggers: A2UI, agent-to-user interface, agent UI, A2UI renderer, A2UI catalog, A2UI component, agent-driven UI, declarative UI protocol
  related-skills: genui-contract, angular-spa, frontend-design, ui-standards-tokens, ai-chat
  domain: frontend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# A2UI Angular Renderer Development Skill

> **Tech Stack**: Angular 22.3.0 (zoneless, OnPush default), TypeScript 6.0.3, `@a2ui/angular@0.16.0` + `@a2ui/web_core@0.16.1` (+ optional `@a2ui/markdown-it@0.2.4`), zod 3.25.76, TailwindCSS 4.3.5, daisyUI 5.8.2. Optional: `@ag-ui/client@1.0.5` (AG-UI transport), `@copilotkit/angular@0.6.0` (latest; peer Angular ^22, cdk ^22). `@a2ui/angular` 0.16.0 is the first release that peers Angular `^22.2.3`; 0.14.0/0.15.0 require `^21.2.5`.
>
> **Cross-platform contract:** the canonical catalog, action table, fixtures and backend topologies are owned by the `genui-contract` skill (`../genui-contract/SKILL.md`). This skill is the Angular side of that contract.

## Protocol Version (pin one per surface)

Verified 2026-11-23 by execution in an Angular 22.3.0 app on the shared `genui-contract` catalogs (Vitest LIVE-PROTOCOL with the real renderer, Playwright Chromium on a production build, axe, and one LIVE run against an AG-UI backend):

| Wire | Import from | Catalog | Status on Angular |
|---|---|---|---|
| **v1.0** (`"version": "1.0"`, not `"v1.0"`) — **target** | `@a2ui/angular` (package root) | `new AngularCatalog(id, '1.0', [...BASIC_COMPONENTS, ...custom], BASIC_FUNCTIONS)` or root `BasicCatalog`, with `useUniversalComponents: true` | **Proven for the shared ActionCard, EditableForm and ApprovalRequest plus the basic catalog only**: render, `@path` bindings, `@accessibility`, actions, required-field validation, SDK rejection of unknown types, axe 0 violations. Other custom components need their own proof. |
| **v0.9** (`"version": "v0.9"`) — compatibility path | `@a2ui/angular/v0_9` for v0.9 `BASIC_COMPONENTS`/`BASIC_FUNCTIONS`; services from the root | `new AngularCatalog(id, '0.9', …)` | Proven with the same tests. Use it for agents that cannot send 1.0, and for CopilotKit (its A2UI path is v0.9 only). |
| v0.8 | `@a2ui/angular/v0_8` | v0.8 catalog | LEGACY. Hand-built renderer docs (`a2ui-renderer-patterns.md`, `a2ui-renderer-template.md`) use it. |

- The package exports `.`, `./v0_8`, `./v0_9` (and `/testing`). There is no `./v1_0` subpath: v1.0 is served by the root entry (CHANGELOG 0.12.0: "the root exports version-agnostic core services … and the v1.0 `BasicCatalog`"). SOURCE-PROVEN from `package.json` and `types/a2ui-angular.d.ts`.
- v1.0 differences that bite: wire literal `"1.0"`; common directives are `@`-prefixed (`@path`, `@call`, `@accessibility`, `@checks`, `@catalogId`, `@metadata`); `createSurface` may carry `components` and `dataModel` inline. Schemas: `@a2ui/web_core/v1_0`.
- Never mix versions on one surface, and never translate between versions without a documented, tested adapter.
- `@a2ui/angular/testing` `createBoundProperty` returns a `jasmine.Spy`; it does not type-check in a Vitest project. Build `BoundProperty` stubs with `signal()` or render through `A2uiRendererService` instead.

## Integration Paths

| Path | Use when | What you build |
|---|---|---|
| **A. Direct A2UI** (default) | The app owns chat, state and transport | `SurfaceComponent` + an `AngularCatalog` for the canonical IDs + ingest guard + action gateway, fed by JSONL/SSE or by an `@ag-ui/client` `HttpAgent` (AG-UI `ACTIVITY_SNAPSHOT`, `activityType: "a2ui-surface"`, `content.a2ui_operations`) |
| **B. Full copilot** (optional) | You want CopilotKit's chat, tools, human-in-the-loop and an AG-UI runtime | `@copilotkit/angular@0.6.0`: `provideCopilotKit({ runtimeUrl, humanInTheLoop: [...] })`, HITL renderers implementing `HumanInTheLoopToolRenderer`, `injectAgentStore` for streaming state, `injectInterrupt` for interrupts |

- `@copilotkit/angular` 0.6.0 (latest; `next` is a 2.0.0 RC, not for production) nests its own `@a2ui/web_core` 0.10.4 and `@ag-ui/client` 1.0.2; `@copilotkit/core` 1.90.0 brings `@a2ui/web_core` 0.15.0. Tested by execution: CopilotKit's A2UI code imports `@a2ui/web_core/v0_9`, which resolves to its nested **0.10.4**, and that copy has **no `./v1_0` export**. Fed a 1.0 stream, its v0.9 processor reported no error and created the surface, so it accepts 1.0 messages silently. Path B is **v0.9 only**: never send it a 1.0 surface.
- Two supported combinations: (A) `@a2ui/angular` 0.16.0 + `@a2ui/web_core` 0.16.1 over AG-UI or JSONL, on 1.0 or v0.9; (B) CopilotKit Angular with its own bundled runtime, on v0.9. Each surface belongs to one of them. Mixing them on one surface is untested; do not do it.
- Details and the compiled HITL example: `reference/copilotkit-angular.md`.

## Canonical Catalog (shared contract)

The wire IDs are `ActionCard`, `DataSummaryTable`, `ApprovalForm`, `SelectionList`, `DetailPanel`, `StatusIndicator`, `InputForm`, `ConfirmationDialog`. No Angular class names go on the wire. Topologies are `shared-backend` and `standalone-backend`; only the adapter edge (base URL from runtime config) differs, and the catalog, guard and gateway are identical. Tested Angular implementation (ActionCard, InputForm, ApprovalForm, ConfirmationDialog; Vitest + Playwright + axe in both topologies): `reference/canonical-catalog-angular.md`.

- Register components with `new AngularCatalog(id, '0.9', [createComponentImplementation(Api, Component)], functions)`. `BasicCatalogBase` `extraComponents`/`functions` are deprecated. Register the catalog functions the contract uses (for example `required`, `email`) from `BASIC_FUNCTIONS`; they are not inherited.
- Components extend `CatalogComponent<typeof Api>`. Scalar `Dynamic*` props arrive as `BoundProperty` (`value()`). On 0.16.0, `Action` props arrive as plain action objects: check the event name against the component's allowlist, resolve with `new DataContext(surface, dataContextPath).resolveAction(action, { userActivation: true })`, then send with `surface.dispatchAction(resolved, componentId)`. Nested bindings arrive resolved; write an edit back with `new DataContext(surface, dataContextPath).set(path, value)` (tested: `reference/canonical-catalog-angular22-components.md`).
- **SDK validation is the primary control** for unknown component types and prop schemas: `processorOptions.validationConfig: STRICT_VALIDATION` with `reportErrorsOnly: true` sends `VALIDATION_FAILED` (unknown type, an action name outside the component's `z.enum`) and `INTEGRITY_ERROR` (1.0 `createSurface.theme`) to `errorHandler`. This was tested on v0.9 and 1.0; removing it made the unknown-component tests fail. No separate app component allowlist is needed.
- web_core does **not** cover the rest of the contract. In tests it accepted `javascript:` strings, a v0.9 `{"path"}` binding on a 1.0 surface and mixed versions in one stream. `@a2ui/agent`'s `validatePayload` also accepts `javascript:` URLs and non-allowlisted actions. Run an app gate before `processMessages`: byte cap before `JSON.parse`, one wire version per stream, `forbiddenStringPatterns`, and no legacy bindings on 1.0. At dispatch, check the per-component action allowlist again. Map every failure to a visible error state.

## Supply-Chain Note (2026-11-23)

- `@a2ui/angular@0.16.0`, `@a2ui/web_core@0.16.1` and `@a2ui/markdown-it@0.2.4` were all published on 2026-11-23 by the `a2ui-team` npm account. They carry `dist.integrity` (sha512) but **no npm provenance attestations**. `@copilotkit/angular@0.6.0` (published by GitHub Actions) and `@ag-ui/client@1.0.5` do have SLSA provenance. Pin exact versions (`npm install --save-exact`) and review the lockfile diff on every bump.
- `npm audit` reports **zod 3.25.76 as HIGH** (GHSA-mrhx-c7xc-m3w5, range `<4.6.6`). It comes in through `@a2ui/angular`, `@a2ui/web_core` and `@a2ui/markdown-it`, which require `zod ^3.25.76`, and no zod 3.x fix exists. A baseline Angular 22.3.0 app without A2UI passes `npm audit --audit-level=high`. **Override decision: do not override.** `overrides: { "zod": "4.6.7" }` is outside the declared `^3.25.76` range. It was tested: install exit 0 and audit clean, but `ng test` failed 9 of 28 because bindings stopped resolving (`[object Object]` text) and the processor raised `INTERNAL_ERROR`. Run `npm audit` on every install and record the result. Report it as an unresolved HIGH; never describe the stack as clean. Mitigation: cap message bytes **before** `JSON.parse` (the session rejects lines over 256 KiB) and keep `STRICT_VALIDATION` plus the app gate. The Feature/PR gate (`npm audit --audit-level=high`) stays NEEDS_REVIEW until `@a2ui/*` moves to zod 4.
- Install zod 3.25.76 as a direct dependency (exact) so your catalog schemas use the **same** zod copy as `web_core`. Angular 22 itself pulls zod 4 (CLI, forms), and `web_core` uses `instanceof z.ZodType` checks.

## Secure Action Handling

1. **Allowlist:** an action name not in the contract's action table never leaves the browser. Validate `context` against the per-action schema.
2. **Server authz:** send the session credential; nothing in `context` grants permission. Surface 401/403/404/409 to the user (`role="alert"`), never silently.
3. **Idempotency:** side-effecting actions carry an `Idempotency-Key` **header**, never a context field. Create it once per user intent, reuse it on retry, drop a duplicate click while the request is in flight, and disable the control meanwhile.
4. **Human approval:** high-risk actions (`approval.*`, `dialog.confirm`) are held by the server, which replies `202` with a server-authored `ConfirmationDialog` surface. Button labels on approval UIs are app-authored, not model text.
5. **Golden payloads:** emitted actions must equal the contract's golden payloads in canonical form (sorted keys, fixed timestamp). Strip SDK-only fields such as `catalogId`.

## What is A2UI?

A2UI (Agent-to-User Interface) is a **declarative protocol by Google** that lets AI agents describe rich, interactive UIs as structured JSON data instead of generating executable code. The agent sends a JSON blueprint; the client app renders it using its own native components.

**Key principle:** UI-as-data, not UI-as-code. Agents never generate HTML/JS — they describe intent via a flat component adjacency list. The client validates against an approved component catalog and renders with native framework components.

## Iron Law

**A2UI PAYLOADS ARE UNTRUSTED. VALIDATE COMPONENT TYPES AGAINST THE CATALOG ALLOWLIST BEFORE RENDERING. NEVER EXECUTE AGENT-PROVIDED CODE.**

Every component from an agent must be validated against the client's approved catalog. Rendering any component type the agent sends, or executing agent-provided scripts, exposes the application to XSS, code injection, and data theft. The catalog allowlist is the security boundary.

## Conventions & Structure

> For Angular coding conventions, read the `angular-spa` skill's `reference/angular-conventions.md`
> For A2UI-specific patterns, read `reference/a2ui-protocol.md`

## Documentation Sources

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| A2UI Spec | `https://a2ui.org/` | Protocol specification, component format |
| A2UI GitHub | `https://github.com/google/A2UI` | Reference implementations, samples |
| A2A Extension | `https://a2ui.org/a2a-extension/a2ui/v0.8` | A2A protocol integration (Python ADK) — v0.8 URI; confirm the v0.9 URI before use (UNVERIFIED) |
| A2UI Composer | `https://a2ui.org/composer/` | Visual widget builder — prototype before wiring |
| @a2ui/angular | `npm install --save-exact @a2ui/angular@0.16.0 @a2ui/web_core@0.16.1 @a2ui/markdown-it@0.2.4 zod@3.25.76` | Official Angular renderer SDK (peer: Angular ^22.2.3; `@a2ui/markdown-it` 0.2.4 peers `web_core ^0.16.1` and is optional) |
| Angular v22 | `angular-cli` MCP (`get_best_practices` with `workspacePath`, `search_documentation` version 22) | Workspace-aware best practices |
| daisyUI v5 | `https://daisyui.com/llms.txt` | Component reference for rendering |
| TailwindCSS | `Context7` MCP | Utility classes for layout |

## Before Writing Any A2UI Code

0. **Load `genui-contract`** when the feature uses the canonical catalog, then read `reference/canonical-catalog-angular.md`
1. **Read `reference/a2ui-protocol.md`** — protocol structure, JSON format, adjacency list, action model
2. **Read `reference/a2ui-renderer-patterns.md`** — Angular renderer architecture, catalog service, recursive rendering
3. **Read `reference/a2ui-security.md`** — allowlist enforcement, injection prevention, input sanitization
4. **Read `reference/a2ui-component-catalog.md`** — standard component types, property schemas, action definitions
5. **Verify Angular APIs** — Use the `angular-cli` MCP (Context7 as fallback) before using any Angular API

## Process

1. **Understand Requirements** — Clarify which A2UI component types to support, agent transport (REST/WebSocket/SSE), and action handling needs
2. **Define Component Catalog** — Create the allowlist of approved A2UI component types with their property schemas
3. **Build Renderer** — Prefer the official SDK (`SurfaceComponent` + an `AngularCatalog` for your catalog, or `BasicCatalog` from `@a2ui/angular/v0_9` for the basic one, `STRICT_VALIDATION`, sanitizing `MarkdownRenderer`). Hand-build a recursive renderer only when you need your own design system, and then copy the guards from `reference/a2ui-renderer-template.md`
4. **Implement Agent Service** — Create the service that communicates with the AI agent and receives A2UI payloads
5. **Add Action Handling** — Wire user interactions (clicks, form submits) back to the agent as A2UI actions
6. **Enable Streaming** — Support progressive rendering via SSE or WebSocket for real-time UI updates
7. **Write Tests** — Unit tests for catalog validation, renderer component, and action dispatch
8. **Verify Build** — Run `ng build` to ensure no compilation errors

## Reference Files

Detailed patterns are in `reference/`:

### A2UI Protocol
- `a2ui-protocol.md` — Protocol specification, JSON format, adjacency list structure, message types, userAction
- `a2ui-protocol-advanced.md` — Action model, streaming (JSONL/SSE/WebSocket/REST/A2A), A2A integration, versioning, backend rules (payload examples are LEGACY v0.8)
- `a2ui-security.md` — Allowlist enforcement, injection prevention, untrusted payload handling
- `a2ui-component-catalog.md` — Layout (Row, Column) + Display (Text, Image, Icon, Divider) + Interactive (Button, TextField, Checkbox, DateTimeInput) component schemas
- `a2ui-component-containers.md` — Container types (Card, Modal, Tabs, List), extended catalog (ChoicePicker, Slider, AudioPlayer, Video), how to add new types
- `a2ui-functions.md` — Full functions reference: validation (required, regex, email), formatting (formatCurrency, formatDate, pluralize), logical (and, or, not), navigation (openUrl) — `A2UIFunctionService` implementation

### Angular Implementation
- `canonical-catalog-angular.md` — Canonical catalog → Angular components, ingest guard order + error codes, action gateway (allowlist, idempotency header, server-held approval), topology runtime config, AG-UI `HttpAgent` adapter
- `canonical-catalog-angular22-components.md` — Angular 22 components on the shared contract (tested): component APIs for both wire versions, dispatch allowlist, ActionCard, ApprovalRequest, EditableForm
- `canonical-catalog-angular22-session.md` — Angular 22 stream session (contract gate, size cap, cancellation, bounded reconnect), providers per wire version, lazy routes
- `copilotkit-angular.md` — CopilotKit Angular 0.6.0 on Angular 22: provider config, human-in-the-loop renderer (compiled + tested), streaming state, interrupts, its v0.9 A2UI path
- `a2ui-renderer-patterns.md` — LEGACY v0.8 hand-built renderer: architecture, models, catalog service, URL policy (https + host allowlist), cycle/depth guard
- `a2ui-renderer-template.md` — LEGACY v0.8 `A2UIRendererComponent` (compiled + browser-tested guards: cycle/depth placeholder, unknown type, URL allowlist, accessible tabs)
- `a2ui-chat-template.md` — LEGACY v0.8 chat page for the hand-built renderer, streaming variant (SSE + JSONL), v0.8 wire format reference
- `a2ui-renderer-services.md` — Official `@a2ui/angular` SDK setup on v0.9 (`provideA2Ui`, `A2uiRendererService.processMessages`, `SurfaceComponent`), production vs demo action handler; LEGACY v0.8 agent service + unit test template for the hand-built renderer
- `a2ui-production-architecture.md` — Production stack, AG-UI `a2ui_operations` envelope, Domain DSL, Custom Catalog patterns (`AngularCatalog` constructor, BoundProperty, FunctionImplementation), Charts/Dashboard, Testing patterns, Observability metrics
- `a2ui-client-integration.md` — `agUiResource` service pattern, `registerHandlers`, widget template, **demo-only vs production action handler warning**, rate limits (surfaces/session, actions/sec, payload size)

## Security Defaults (official SDK, tested on 0.16.0)

Verified 2026-11-23 (Angular 22.3.0, `@a2ui/angular@0.16.0`, `@a2ui/web_core@0.16.1`, Vitest 5.1.1, Playwright 1.65.1 Chromium):

- **Without** `validationConfig`, an unknown component type passes `processMessages` with no error. `ComponentHostComponent.reportUnresolved` only writes to the console and renders nothing. A console-only `reportUnresolved` is **not an error signal**: nothing reaches `errorHandler` and the user sees an empty slot.
- **With** `STRICT_VALIDATION` and `reportErrorsOnly: true`, the unknown type reaches `processorOptions.errorHandler` on v0.9 and 1.0. The app turns it into `role="alert"` text ("Part of this response could not be displayed.").
- Some failures throw out of `processMessages` instead (for example a renderer with no catalogs). Catch them in the session and show the same error state; do not let them look like a transport failure that triggers a retry.
- The v0.9 `Text` component renders markdown into `[innerHTML]`. Use `@a2ui/markdown-it` 0.2.4 (depends on DOMPurify) or the `marked` → DOMPurify `MarkdownService` from `ai-chat` (`reference/streaming-patterns.md`). Never `bypassSecurityTrust*`.

Recommended wiring: one lazy route per wire version. It keeps the renderer out of the initial bundle (initial 287 kB with this pattern, 916 kB without it; the GenUI chunk is 670 kB) and gives each version its own renderer. `provideGenui(version)` returns `A2uiRendererService` itself (it is `providedIn: 'root'` and would otherwise miss the route's config with `Catalog not found`), the session gate, and `provideA2Ui` with `STRICT_VALIDATION`. Full compiled files: `reference/canonical-catalog-angular22-components.md` and `reference/canonical-catalog-angular22-session.md`.

```typescript
import { type Routes } from '@angular/router';
import { provideGenui } from './genui-providers';

const SURFACES = ['card-1', 'appr-1', 'form-1'];

/** Lazy GenUI routes: each wire version gets its own renderer instance. */
export const GENUI_ROUTES: Routes = [
  {
    path: '',
    providers: provideGenui('0.9'),
    loadComponent: () => import('./genui-page'),
    data: { version: 'v0.9', streamUrl: '/genui-v0_9.jsonl', surfaceIds: SURFACES },
  },
  {
    path: 'v1',
    providers: provideGenui('1.0'),
    loadComponent: () => import('./genui-page'),
    data: { version: '1.0', streamUrl: '/genui-v1_0.jsonl', surfaceIds: SURFACES },
  },
];
```

```typescript
// genui-providers.ts (excerpt): the renderer half of provideGenui()
A2uiRendererService, // re-provided at route level
provideA2Ui(() => {
  const outbox = inject(GenuiOutbox);
  const injector = inject(Injector); // GenuiSession depends on the renderer: resolve lazily (NG0200)
  return {
    catalogs: [createCatalog(version)], // AngularCatalog(GENUI_CATALOG_ID_V10, '1.0', …) or (…_V09, '0.9', …)
    useUniversalComponents: version === '1.0',
    processorOptions: {
      validationConfig: STRICT_VALIDATION, // primary control for unknown types and prop schemas
      outboundListener: (message) => outbox.push(message), // forward to the agent; the server re-authorizes
      unifiedOutbound: true,
      errorHandler: (error) => injector.get(GenuiSession).reportRendererError(error),
      reportErrorsOnly: true,
    },
  };
}),
```

## Anti-Patterns — What to Avoid

```typescript
// ❌ FORBIDDEN: Rendering arbitrary component types or agent HTML
@switch (comp.type) {
  @default {
    <div [innerHTML]="comp.properties['html']"></div>  // XSS vector!
  }
}

// ✅ REQUIRED: unknown type, dangling id, cycle or depth > limit -> visible placeholder + ErrorHandler
@if (problem()) {
  <p role="note">This content can't be displayed.</p>
}
```

```typescript
// ❌ FORBIDDEN: Executing agent-provided code
eval(comp.properties['script']);
new Function(comp.properties['handler'])();

// ✅ REQUIRED: declarative action dispatch; the app forwards it and the server decides
onAction(name: string, context: Record<string, unknown>): void {
  this.actionTriggered.emit({ name, context });
}
```

```jsonc
// ❌ FORBIDDEN: nested JSON tree from the agent
{ "children": [{ "children": [{ "children": [] }] }] }

// ✅ REQUIRED (v0.9): flat adjacency list, exactly one component with id "root"
{ "version": "v0.9", "createSurface": { "surfaceId": "main", "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json" } }
{ "version": "v0.9", "updateComponents": { "surfaceId": "main", "components": [
  { "id": "root", "component": "Column", "children": ["btn-1"] },
  { "id": "btn-1", "component": "Button", "child": "btn-1-label", "variant": "primary",
    "action": { "event": { "name": "submit", "context": {} } } },
  { "id": "btn-1-label", "component": "Text", "text": "Submit" }
] } }

// ✅ client → agent (v0.9 `action` message)
{ "version": "v0.9", "action": { "name": "book_hotel", "surfaceId": "main", "sourceComponentId": "btn-book",
  "timestamp": "2026-03-10T12:00:00Z", "context": { "hotelId": "H-456" } } }
```

Shapes checked against `@a2ui/web_core@0.15.0` `src/v0_9/schemas/` (unchanged in 0.16.1 for v0.9) (`server_to_client.json`, `client_to_server.json`, `catalogs/basic/examples/00_interactive-button.json`).

## Error Handling

- Unknown component type, dangling child id, cycle or depth limit → render a visible "can't be displayed" placeholder for that node and log through Angular `ErrorHandler` (never `console.*` in production code, never a silent skip)
- Malformed JSON or a rejected message → show a recoverable error, keep the last good surface, log the full error
- Messages apply in order: reject `updateComponents` before `createSurface` (`reference/a2ui-production-architecture.md`)
- If the agent connection drops mid-stream → render what was received so far, show a reconnect option
- If action dispatch fails → show an error toast, do NOT silently swallow
- Consequential actions (payment, delete, submit, send) → the server holds them and returns a confirmation step (canonical contract: `202` + `ConfirmationDialog`); approval button labels are app-authored, not model text; the server authorizes (`reference/a2ui-security.md` § Authority model)

## Common Commands

```bash
# Generate A2UI feature module
mkdir -p src/app/features/a2ui-chat/{components,services,models}

# Run tests (Vitest via @angular/build:unit-test)
npm exec --no -- ng test --no-watch

# Build
npm exec --no -- ng build
```
