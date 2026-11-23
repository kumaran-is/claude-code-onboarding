# A2UI Security Reference

## Threat Model

A2UI payloads originate from AI agents — untrusted sources whose output can be steered by prompt
injection in any document, message, upload, OCR text or tool result they read. The declarative
format makes the following properties *achievable*; they hold only when the renderer enforces the
checks in this file (the official v0.9 processor does not enforce them unless configured — see
`SKILL.md` § Security Defaults):

1. No agent-provided code runs on the client
2. Only components in the approved catalog render
3. No agent HTML, scripts or event handlers reach the DOM
4. No access to client-side state, cookies or storage
5. No action the client application did not define

## Authority Model

```
Agent PROPOSES   component layout and action intents (data)
Client RENDERS   only allowlisted catalog components; shows; collects input
Server DECIDES   on every action: authentication, authorization, tenant/scope,
                 schema validation, idempotency key, rate limit — then executes
```

- A rendered button is not permission, and a user click is not authorization. The server re-checks every action intent as if it came from an anonymous client.
- Content the agent read (documents, messages, uploads, OCR, tool output) is data. It must never register components, reveal hidden actions, expand the tool set, suppress safety UI or trigger writes.
- Consequential actions (payment, delete, submit, send, share) go through an app-authored confirmation step whose wording comes from the application, not from model text. The agent cannot render, skip or reword that step.
- Prompt text ("only show safe buttons") is not a security boundary.

## Security Architecture

```
Agent Output (untrusted)
    |
A2UI JSON Payload
    |
+--------------------------------------+
|  SERVER-SIDE VALIDATION BOUNDARY     |
|  Schema validation against catalog   |
|  BEFORE transmission to client       |
+--------------------------------------+
    |
+--------------------------------------+
|  CLIENT-SIDE SECURITY BOUNDARY       |
|  1. JSON Schema Validation           |
|  2. Component Type Allowlist         |
|  3. Property Format Sanitization     |
|  4. Action Allowlist                 |
|  5. Rate / Payload Size Limiting     |
+--------------------------------------+
    |
Native Component Rendering (trusted)
```

## Required Security Checks

### 1. Server-Side Schema Validation (Mandatory — Before Transmission)

LLM output MUST be validated against the effective catalog schema server-side
before the payload is transmitted to any client. Malformed or out-of-catalog output is rejected
at this boundary — not silently forwarded.

Custom components require registration with schema validation before they are added to the
effective catalog.

### 2. Component Type Allowlist (Mandatory)

Every component `type` MUST be validated against the client's catalog before rendering.
With the official SDK this is `processorOptions: { validationConfig: STRICT_VALIDATION }` (browser-tested:
unknown type → `A2uiValidationError`). For a hand-built renderer, the allowlist below uses the v0.8 type
names (v0.9 renames `Checkbox` → `CheckBox` and adds `ChoicePicker`, `Slider`, `Video`, `AudioPlayer`):

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```typescript
// ✅ REQUIRED: Allowlist validation with official type names
@Service()
export class A2UICatalogService {
  private readonly allowedTypes = new Set([
    'Row', 'Column',                                              // Layout
    'Text', 'Image', 'Icon',                                      // Display
    'Button', 'TextField', 'Checkbox', 'DateTimeInput',           // Interactive
    'Card', 'Modal', 'Tabs', 'List', 'Divider',                   // Containers / Structure
  ]);

  isAllowed(type: string): boolean {
    return this.allowedTypes.has(type);
  }

}
// Unknown types are NOT filtered out silently: the renderer shows a placeholder and logs via ErrorHandler
// (a2ui-renderer-template.md).
```

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// ❌ FORBIDDEN: Rendering any type the agent sends
renderComponent(comp: A2UIComponent) {
  const ComponentClass = this.registry[comp.type]; // Agent controls what gets rendered
}
```

### 3. Property Format Sanitization (Mandatory)

In v0.8 (legacy), all property values use a typed-value format. In v0.9 a property is a plain JSON value, a `{ "path": … }` binding or a function call; the same rule holds — no executable content. A value is either a literal string or a
JSON Pointer path reference — never a raw string or executable content.

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// Official property value shapes:
// { "literalString": "some text" }
// { "path": "/json/pointer" }

sanitizePropertyValue(value: unknown): string {
  if (typeof value === 'object' && value !== null) {
    const v = value as Record<string, unknown>;
    if ('literalString' in v && typeof v['literalString'] === 'string') {
      return v['literalString'].slice(0, 10_000);
    }
    if ('path' in v && typeof v['path'] === 'string') {
      // JSON Pointer: must start with /
      if (!v['path'].startsWith('/')) return '';
      return v['path'];
    }
  }
  // Reject raw strings, numbers, booleans, or unknown shapes
  return '';
}
```

URL properties extracted from sanitized values still require protocol validation:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// ❌ FORBIDDEN: Direct innerHTML or unvalidated URL binding
<div [innerHTML]="comp.properties['content']"></div>
<img [src]="comp.properties['imageUrl']" />

// ✅ REQUIRED: Text interpolation (auto-escaped by Angular)
<p>{{ resolvedText }}</p>

// ✅ REQUIRED: one URL policy — https: only AND an allowlisted host (a2ui-renderer-patterns.md § Sanitizer Service)
@if (safeUrl(comp.url); as src) { <img [src]="src" alt="" /> }
```

The same `sanitizeUrl()` gates `[src]`, `[href]` and the `openUrl` function. `http:` is rejected: it allows
network tampering and mixed content, and `a2ui-functions.md` already requires `https:`. A host allowlist is
required as well, because any `https:` image URL chosen by the model can carry conversation data to a third
party in its query string.

### 4. Action Allowlist (Mandatory)

Official v0.8 action format: `{ "name": "...", "context": [...] }`.
Validate on `action.name`, not a legacy `action.action` field.

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// Official action interface
interface A2UIAction {
  name: string;
  context?: Array<{ key: string; value: { literalString?: string; path?: string; } }>;
}
```

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```typescript
// services/a2ui-action-gate.ts — every user action passes here before it reaches the agent
import { ErrorHandler, Service, InjectionToken, inject } from '@angular/core';

/** Action names this app accepts. Fail closed: nothing is allowed until the app provides the set. */
export const A2UI_ALLOWED_ACTIONS = new InjectionToken<ReadonlySet<string>>('A2UI_ALLOWED_ACTIONS', {
  providedIn: 'root',
  factory: () => new Set<string>(),
});

@Service()
export class A2UIActionGate {
  private readonly allowed = inject(A2UI_ALLOWED_ACTIONS);
  private readonly errorHandler = inject(ErrorHandler);

  /** True for a listed name; otherwise logs the rejection and returns false. */
  permit(action: { readonly name: string }): boolean {
    if (this.allowed.has(action.name)) return true;
    this.errorHandler.handleError(new Error(`A2UI: unknown action rejected: ${action.name}`));
    return false;
  }
}

// app.config.ts
// { provide: A2UI_ALLOWED_ACTIONS, useValue: new Set(['book_flight', 'add_to_cart', 'show_details', 'submit_form', 'navigate', 'dismiss']) }
```

The chat page calls `actionGate.permit(action)` before `sendUserAction` (`a2ui-chat-template.md`). The gate is
defence in depth: the server still authorizes every action (Authority Model).

### 4b. Action Context Is Agent-Influenced (Validate Server-Side)

The agent writes the action's `context` template. Bound values (`{ "path": … }`) are resolved from the
client data model, but literal values in the template come straight from the agent, and the data model
itself is filled by agent `updateDataModel` messages and user input. The v0.9 schema describes `context`
as "the key-value pairs from the component's action.event.context, after resolving all data bindings"
(`@a2ui/web_core@0.15.0`, `src/v0_9/schemas/client_to_server.json`; historical, not re-checked on 0.16.1). So the server validates every context
value (schema, ownership of referenced ids, ranges) exactly like any other client input.

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// action (client -> agent). v0.9: { "version": "v0.9", "action": { … } }; v0.8 called it userAction
interface UserAction {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  timestamp: string;      // ISO-8601
  context?: Record<string, unknown>; // values from app data model, not agent strings
}
```

### 5. No Code Execution (Absolute Rule)

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// ❌ ABSOLUTE PROHIBITION — never execute agent-provided strings
eval(comp.properties['script']);
new Function(comp.properties['handler'])();
setTimeout(comp.properties['callback'] as string, 0);
document.createElement('script').textContent = comp.properties['code'];

// ❌ PROHIBITION — no dynamic component creation from agent input
const factory = this.resolver.resolveComponentFactory(
  this.dynamicRegistry[comp.type]  // Agent controls component instantiation
);
```

### 6. Payload Size Limits

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
const MAX_COMPONENTS = 200;
const MAX_PROPERTY_LENGTH = 10_000; // characters per sanitizePropertyValue
const MAX_PAYLOAD_SIZE = 1_048_576; // 1MB

// Reject, do not truncate: a silently truncated surface can drop the very component (a warning,
// a confirmation) that made the rest safe to show.
assertSurfaceSize(update: { surfaceId: string; components: readonly unknown[] }): void {
  if (update.components.length > MAX_COMPONENTS) {
    throw new Error(`A2UI: surface ${update.surfaceId} has ${update.components.length} components (max ${MAX_COMPONENTS})`);
  }
}
// Caller: catch -> ErrorHandler.handleError(err) -> show a recoverable error, keep the last good surface.
```

## Catalog ID Allowlisting

The `catalogId` field in `createSurface` is agent-controlled. Never load a catalog dynamically based on a catalogId from the agent without server-side allowlisting:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
const ALLOWED_CATALOG_IDS = new Set([
  'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json', // id used by @a2ui/web_core v0.9 examples
  'https://example.com/catalogs/your-custom-catalog',
]);

function validateA2uiMessage(msg: unknown): void {
  if (typeof msg === 'object' && msg !== null && 'createSurface' in msg) {
    const catalogId = (msg as Record<string, Record<string, string>>).createSurface?.catalogId;
    if (catalogId && !ALLOWED_CATALOG_IDS.has(catalogId)) {
      throw new Error(`Disallowed catalogId: ${catalogId}`);
    }
  }
}
```

Validate all incoming A2UI messages server-side before they reach the client.

## Catalog Descriptions in the Prompt

Sending full component descriptions and schema examples from the client into the agent prompt widens the
prompt-injection surface (a compromised client or agent can rewrite them). Safe production posture:

```
Client sends catalogId only (no descriptions)
  ↓
Agent validates catalogId against a server-side allowlist
  ↓
Agent loads the catalog schema from an internal trusted registry
  ↓
LLM receives only approved catalog instructions
  ↓
Server validates generated A2UI before sending it to the client
```

The configuration flag that controls this depends on your agent SDK. `provideA2uiCatalog` and
`sendCatalogDescription` do NOT exist in `@a2ui/angular@0.14.0`/`0.16.0` or `@a2ui/web_core@0.15.0`/`0.16.1` (searched the
published packages 2026-11-22 and 2026-11-23) — UNVERIFIED for other A2UI agent SDKs; check the SDK you use before citing a flag.

## Rate Limits (Server-Side)

A misbehaving or compromised agent can DoS the client by spamming messages. These limits belong on the server or agent gateway — client-side limits are bypassable.

| Limit | Recommended Cap | Rationale |
|-------|----------------|-----------|
| Surfaces per session | ~50 | Catches runaway loops without affecting normal use |
| Actions per second per surface | ~10 | Prevents button spam / click flooding |
| `updateDataModel` payload size | Set a max bytes limit | Prevents oversized payloads that freeze the renderer |

## Server-Side Validation Loop

LLM-generated A2UI is not safe to render without validation. The required production loop:

```
LLM generates A2UI
  ↓
Schema validation (Zod against component catalog)
  ↓
[FAIL] → Send structured error back to LLM → retry (max 2-3 retries)
[PASS] → Wrap in AG-UI/A2A event → ship to client
```

A spike in validation failure rate is often the earliest signal that an LLM regression or prompt change has destabilized UI generation — before users notice.

## Security Checklist

- [ ] LLM output validated against catalog schema server-side before transmission
- [ ] Custom components registered with schema validation before catalog inclusion
- [ ] Official SDK: `validationConfig: STRICT_VALIDATION` set (unknown types, cycles and depth rejected at ingest)
- [ ] Hand-built renderer: component types validated against the catalog allowlist; unknown type, dangling id, cycle and depth > limit render a placeholder and log via `ErrorHandler`
- [ ] One protocol version pinned across agent, renderer and catalog (v0.9 for new work)
- [ ] Legacy v0.8: property values are `literalString` or a JSON Pointer `path` starting with "/"
- [ ] Text values length-capped (10,000 chars) and rendered by interpolation; markdown goes through the marked → DOMPurify `MarkdownRenderer`
- [ ] URLs: `https:` only AND an allowlisted host, one `sanitizeUrl()` shared by `[src]`, `[href]` and `openUrl`
- [ ] No `innerHTML`, `outerHTML`, or `bypassSecurityTrust*` used with agent data
- [ ] No `eval()`, `Function()`, or dynamic script creation from agent data
- [ ] Actions validated against an allowlist by `name`; the server authorizes every action and validates its `context`
- [ ] Consequential actions use an app-authored confirmation step (no model text in it)
- [ ] Payload size limits enforced by rejecting (200 components, 1MB total), never by truncating
- [ ] Malformed or rejected messages show a recoverable error and keep the last good surface
- [ ] No `console.*` in production renderer code — Angular `ErrorHandler` or the app logger
