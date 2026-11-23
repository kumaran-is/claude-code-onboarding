---
name: a2ui-angular
description: "A2UI (Agent-to-User Interface) renderer development for Angular 21.x. Use when building A2UI component renderers, agent-driven UIs, A2UI catalogs, action handlers, or streaming A2UI payloads. Covers protocol implementation, security validation, component mapping, and agent integration."
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, mcp__context7__resolve-library-id, mcp__context7__query-docs
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

> **Tech Stack**: Angular 21.2.x, A2UI protocol **v0.9** (wire value `"version": "v0.9"`), `@a2ui/angular@0.14.0` + `@a2ui/web_core@0.15.0`, TailwindCSS 4.x, daisyUI 5.5.5. Optional: `@ag-ui/client@1.0.5` (AG-UI transport), `@copilotkit/angular@0.3.1` (the last line that supports Angular 21).
>
> **Cross-platform contract:** the canonical catalog, action table, fixtures and backend topologies are owned by the `genui-contract` skill (`../genui-contract/SKILL.md`). This skill is the Angular side of that contract.

## Protocol Version (pin one per stack)

- **New work targets v0.9.** Verified 2026-11-22 against the published packages: `@a2ui/web_core@0.15.0` has `DEFAULT_PROTOCOL_VERSION = '0.9'`; its v0.9 schemas define `createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface` and the client→server `action` message. `@a2ui/angular@0.14.0` serves v0.9 from `@a2ui/angular/v0_9` (`SurfaceComponent`, `BasicCatalog`).
- **v0.8 is legacy.** Its shapes (`surfaceUpdate`, `beginRendering`, `dataModelUpdate`, `{ "component": { "type": … } }`, `{ "literalString": … }`) remain only for agents that still emit v0.8; the SDK keeps them under `@a2ui/angular/v0_8`. The hand-built renderer in `reference/a2ui-renderer-patterns.md` / `a2ui-renderer-template.md` uses the v0.8 shapes and is labelled LEGACY there.
- **v1.0** exists in the packages (`@a2ui/web_core/v1_0`, wire value `"1.0"`), and the `@a2ui/angular` root `BasicCatalog` is the v1.0 catalog. Treat it as not yet adopted here: import v0.9 classes from `@a2ui/angular/v0_9`, not the package root.
- Never mix versions between agent, renderer and catalog. The spec status labels on a2ui.org (v0.9 current, v1.0 candidate) were not re-checked this session — UNVERIFIED, check before relying on them.

## Integration Paths

| Path | Use when | What you build |
|---|---|---|
| **A. Direct A2UI** (default) | The app owns chat, state and transport | `@a2ui/angular` `SurfaceComponent` + an `AngularCatalog` for the canonical IDs + ingest guard + action gateway, fed by SSE or by an `@ag-ui/client` `HttpAgent` (AG-UI `ACTIVITY_SNAPSHOT`, `activityType: "a2ui-surface"`, `content.a2ui_operations`) |
| **B. Full copilot** (optional) | You want CopilotKit's agent/chat client and an AG-UI-compatible runtime | `@copilotkit/angular@0.3.1` + an activity renderer that feeds `a2ui-surface` activities into the same `@a2ui/angular` catalog and guard |

- `@copilotkit/angular` 0.4.0 and later (latest 0.6.0) peer `@angular/core ^22`, so they do **not** support Angular 21.2.x. 0.3.1 peers `^20 || ^21 || ^22`. SOURCE-PROVEN from `npm view`/`npm pack` on 2026-11-23.
- CopilotKit's built-in A2UI renderer is Lit-based with its own `@a2ui/web_core` 0.10.4. Do not run it next to `@a2ui/angular` for the canonical catalog. Its action bridge sends no idempotency key, so the server must authorize and hold every side effect.
- Details, compatibility table and the compile-proven bridge: `reference/copilotkit-angular.md`.

## Canonical Catalog (shared contract)

The wire IDs are `ActionCard`, `DataSummaryTable`, `ApprovalForm`, `SelectionList`, `DetailPanel`, `StatusIndicator`, `InputForm`, `ConfirmationDialog`. No Angular class names go on the wire. Topologies are `shared-backend` and `standalone-backend`; only the adapter edge (base URL from runtime config) differs, and the catalog, guard and gateway are identical. Tested Angular implementation (ActionCard, InputForm, ApprovalForm, ConfirmationDialog; Vitest + Playwright + axe in both topologies): `reference/canonical-catalog-angular.md`.

- Register components with `new AngularCatalog(id, '0.9', [createComponentImplementation(Api, Component)], functions)`. `BasicCatalogBase` `extraComponents`/`functions` are deprecated. Register the catalog functions the contract uses (for example `required`, `email`) from `BASIC_FUNCTIONS`; they are not inherited.
- Components extend `CatalogComponent<typeof Api>`. Scalar `Dynamic*` props arrive as `BoundProperty` (`value()`); `Action` props arrive as ready-to-call closures; nested bindings write through `surface.dataModel.set(path, value)`.
- `STRICT_VALIDATION` does not validate component props and does not reject unversioned messages. Run an app ingest guard first: size, single body + `version === "v0.9"`, forbidden strings, catalog ID, known surface, component allowlist, no `functionCall` actions, per-component action allowlist, zod prop schema. Map each failure to the contract error code and show it.

## Supply-Chain Note (npm audit, 2026-11-23)

`npm audit` on Angular 21.2.26 + `@a2ui/angular@0.14.0` + `@a2ui/web_core@0.15.0` reports **zod 3.25.76 as HIGH** (GHSA-mrhx-c7xc-m3w5, fixed in zod ≥ 4.6.6). It comes in through `@a2ui/web_core` and also through `@ag-ui/client` 1.0.5 and `@copilotkit/angular` 0.3.1. Overriding zod to 4.x is not an option: web_core 0.15.0 crashes at runtime, verified in a separate React test app (2026-11-23). Mitigation: cap message bytes **before** `JSON.parse` and before any zod parse (tested: `canonical-catalog-angular.md` § Ingest guard), keep the strict ingest guard, and re-run `npm audit` on every A2UI/AG-UI/CopilotKit bump. DOMPurify ≤ 3.4.16 has moderate advisories; pin `dompurify@3.5.0` (all checks stayed green).

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
| @a2ui/angular | `npm install -E @a2ui/angular@0.14.0 @a2ui/web_core@0.15.0` | Official Angular renderer SDK (peer: Angular ^21.2.5). The optional `@a2ui/markdown-it@0.2.2` peer requires `web_core@^0.14` and fails to resolve with 0.15 — supply your own sanitizing `MarkdownRenderer` instead (see Security Defaults) |
| Angular v21 | `angular-cli` MCP | Workspace-aware help, schematics |
| daisyUI v5 | `https://daisyui.com/llms.txt` | Component reference for rendering |
| TailwindCSS | `Context7` MCP | Utility classes for layout |

## Before Writing Any A2UI Code

0. **Load `genui-contract`** when the feature uses the canonical catalog, then read `reference/canonical-catalog-angular.md`
1. **Read `reference/a2ui-protocol.md`** — protocol structure, JSON format, adjacency list, action model
2. **Read `reference/a2ui-renderer-patterns.md`** — Angular renderer architecture, catalog service, recursive rendering
3. **Read `reference/a2ui-security.md`** — allowlist enforcement, injection prevention, input sanitization
4. **Read `reference/a2ui-component-catalog.md`** — standard component types, property schemas, action definitions
5. **Verify Angular APIs** — Use `angular-cli` MCP or Context7 MCP before using any Angular API

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
- `canonical-catalog-angular.md` — Canonical catalog → Angular components (tested), ingest guard order + error codes, action gateway (allowlist, idempotency header, server-held approval), topology runtime config, AG-UI `HttpAgent` adapter
- `copilotkit-angular.md` — CopilotKit Angular compatibility (0.6.0 needs Angular 22; 0.3.1 supports 21), built-in Lit A2UI renderer facts, bridge from CopilotKit activities to `@a2ui/angular`
- `a2ui-renderer-patterns.md` — LEGACY v0.8 hand-built renderer: architecture, models, catalog service, URL policy (https + host allowlist), cycle/depth guard
- `a2ui-renderer-template.md` — LEGACY v0.8 `A2UIRendererComponent` (compiled + browser-tested guards: cycle/depth placeholder, unknown type, URL allowlist, accessible tabs)
- `a2ui-chat-template.md` — LEGACY v0.8 chat page for the hand-built renderer, streaming variant (SSE + JSONL), v0.8 wire format reference
- `a2ui-renderer-services.md` — Official `@a2ui/angular` SDK setup on v0.9 (`provideA2Ui`, `A2uiRendererService.processMessages`, `SurfaceComponent`), production vs demo action handler; LEGACY v0.8 agent service + unit test template for the hand-built renderer
- `a2ui-production-architecture.md` — Production stack, AG-UI `a2ui_operations` envelope, Domain DSL, Custom Catalog patterns (`AngularCatalog` constructor, BoundProperty, FunctionImplementation), Charts/Dashboard, Testing patterns, Observability metrics
- `a2ui-client-integration.md` — `agUiResource` service pattern, `registerHandlers`, widget template, **demo-only vs production action handler warning**, rate limits (surfaces/session, actions/sec, payload size)

## Security Defaults (official SDK, browser-tested)

Verified 2026-11-22 in Chromium (Angular 21.2.26, `@a2ui/angular@0.14.0`, Playwright 1.58.2):

- **Without** a `validationConfig`, the v0.9 `MessageProcessor` accepts a self-referencing child, an unknown component type and a 61-level tree at ingest; the renderer only logs a console error and shows the user nothing.
- **With** `STRICT_VALIDATION`, `processMessages` throws `A2uiRecursionError` (cycle, depth) or `A2uiValidationError` (unknown type), so the app can log it and show a recoverable error.
- The v0.9 `Text` component binds rendered markdown to `[innerHTML]`. Angular's sanitizer alone keeps `<img src>` and `unsafe:javascript:` links, so plug in the `marked` → DOMPurify `MarkdownService` from `ai-chat` (`reference/streaming-patterns.md`).

```typescript
// app.config.ts excerpt — official renderer, A2UI v0.9 wire format, strict validation
import { EnvironmentProviders, Provider, inject, makeEnvironmentProviders } from '@angular/core';
import { MarkdownRenderer, provideA2Ui } from '@a2ui/angular';
import { BasicCatalog } from '@a2ui/angular/v0_9';
import { STRICT_VALIDATION } from '@a2ui/web_core/v0_9';
import { MarkdownService } from './features/chat/services/markdown.service'; // ai-chat: marked -> DOMPurify
import { AgentActionsService } from './features/a2ui/agent-actions.service';   // your agent client

// The v0.9 Text component binds rendered markdown to [innerHTML]. Route it through the
// marked -> DOMPurify pipeline (ai-chat streaming-patterns.md) instead of the default renderer.
const sanitizedMarkdown: Provider = {
  provide: MarkdownRenderer,
  useFactory: () => {
    const markdown = inject(MarkdownService);
    return { render: async (text: string) => markdown.render(text) };
  },
};

export function provideA2uiStrict(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideA2Ui(() => {
      const agent = inject(AgentActionsService); // factory runs in an injection context
      return {
        catalogs: [new BasicCatalog()],
        // Without a validationConfig the v0.9 processor accepts self-referencing children,
        // unknown component types and unbounded depth (web_core 0.15.0, verified). STRICT rejects them.
        processorOptions: { validationConfig: STRICT_VALIDATION },
        actionHandler: (action) => agent.forward(action), // the server re-authorizes every action
      };
    }),
    sanitizedMarkdown,
  ]);
}
```

`provideA2uiStrict()` goes in `appConfig.providers`. `AgentActionsService.forward(action)` posts the action (`ActionPayload` from `@a2ui/web_core/v0_9`: `name`, `surfaceId`, `sourceComponentId`, `timestamp`, `context`) to your agent API. Ingest inside `try { renderer.processMessages(msgs) } catch (err) { errorHandler.handleError(err); showRecoverableError(); }` and keep the last good surface.

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

Shapes checked against `@a2ui/web_core@0.15.0` `src/v0_9/schemas/` (`server_to_client.json`, `client_to_server.json`, `catalogs/basic/examples/00_interactive-button.json`).

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

# Run tests
npx ng test --watch=false

# Build
npx ng build
```
