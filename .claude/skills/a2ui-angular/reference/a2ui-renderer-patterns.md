# A2UI Angular Renderer Patterns

> **LEGACY v0.8 message shapes.** This hand-built renderer reads v0.8 payloads (`surfaceUpdate`, `beginRendering`, `{ "component": { "type" } }`, `literalString`). New work uses v0.9 through the official SDK with `STRICT_VALIDATION` (`SKILL.md` § Security Defaults). The security guards below (URL policy, cycle/depth guard, unknown-type placeholder) apply to any hand-built renderer whatever the version. The models, catalog, sanitizer and renderer here were compiled on Angular 21.2.26 and browser-tested in Chromium on 2026-11-22.

## Architecture Overview

```
+------------------------------------------------------+
|                  Angular Application                  |
|                                                       |
|  +-------------+    +--------------------------+      |
|  |  Chat Page   |    |   A2UI Feature Module    |      |
|  |  Component   |--->|                          |      |
|  +-------------+    |  +--------------------+  |      |
|                      |  | A2UIRendererComponent|  |     |
|                      |  |  (recursive)        |  |      |
|                      |  +--------------------+  |      |
|                      |  +--------------------+  |      |
|                      |  | A2UICatalogService  |  |      |
|                      |  |  (allowlist)        |  |      |
|                      |  +--------------------+  |      |
|                      |  +--------------------+  |      |
|                      |  | A2UIAgentService    |  |      |
|                      |  |  (transport)        |  |      |
|                      |  +--------------------+  |      |
|                      +--------------------------+      |
+------------------------------------------------------+
```

## File Structure

```
src/app/features/a2ui-chat/
+-- models/
|   +-- a2ui.model.ts              # A2UI types and interfaces
+-- services/
|   +-- a2ui-catalog.service.ts    # Component allowlist
|   +-- a2ui-agent.service.ts      # Agent communication
|   +-- a2ui-sanitizer.service.ts  # Property sanitization
+-- components/
|   +-- a2ui-renderer/
|   |   +-- a2ui-renderer.component.ts
|   |   +-- a2ui-renderer.component.spec.ts
|   +-- a2ui-chat/
|       +-- a2ui-chat.component.ts
|       +-- a2ui-chat.component.spec.ts
+-- a2ui-chat.routes.ts
```

## Models

```typescript
// models/a2ui.model.ts

// Property value — static text or data binding path (or combined with default)
export type A2UIValue =
  | { literalString: string; path?: never }
  | { path: string; literalString?: string }   // literalString = default value when path resolves to nothing
  | { valueString: string }
  | { valueNumber: number }
  | { valueMap: { key: string; value: A2UIValue }[] };

// Children references
export type A2UIChildren =
  | { explicitList: string[] }
  | { template: { dataBinding: string; componentId: string } };

// A component definition inside surfaceUpdate.components[]
export interface A2UIComponentEntry {
  id: string;
  component: A2UIComponentDef;
}

// Component definition (type + type-specific fields)
export interface A2UIComponentDef {
  type: string;
  // Layout
  children?: A2UIChildren;        // Row, Column, List
  child?: string;                  // Card, Modal.entryPointChild/contentChild
  alignment?: 'center' | 'start' | 'end';  // Row, Column
  // Text
  text?: A2UIValue;
  usageHint?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'body' | 'caption';
  // Button
  action?: { name: string; context?: { key: string; value: A2UIValue }[] };
  primary?: boolean;
  // TextField
  label?: A2UIValue;
  textFieldType?: 'shortText' | 'longText' | 'email';
  // Checkbox
  value?: A2UIValue;              // path -> boolean
  // Image
  url?: A2UIValue;
  // Icon
  name?: A2UIValue;
  // Tabs
  tabItems?: { title: A2UIValue; child: string }[];
  // Modal
  entryPointChild?: string;
  contentChild?: string;
  // Divider
  axis?: 'horizontal' | 'vertical';
  // DateTimeInput
  enableDate?: boolean;
  enableTime?: boolean;
  // Allow additional unknown fields (forward compat)
  [key: string]: unknown;
}

// surfaceUpdate message (agent -> client)
export interface SurfaceUpdateMsg {
  surfaceId: string;
  components: A2UIComponentEntry[];   // ARRAY not map
}

// dataModelUpdate contents entry
export type DataModelContentsEntry =
  | { key: string; valueString: string }
  | { key: string; valueNumber: number }
  | { key: string; valueMap: DataModelContentsEntry[] };

// dataModelUpdate message (agent -> client)
export interface DataModelUpdateMsg {
  surfaceId?: string;
  path?: string;
  contents: DataModelContentsEntry[];
}

// beginRendering message (agent -> client)
export interface BeginRenderingMsg {
  surfaceId: string;
  root: string;          // component id (field is 'root', not 'rootComponent')
  catalogId?: string;    // URI, optional
}

// deleteSurface message (agent -> client)
export interface DeleteSurfaceMsg {
  surfaceId: string;
}

// Incoming message wrapper (one per JSONL line, agent -> client)
export interface A2UIMessage {
  surfaceUpdate?: SurfaceUpdateMsg;
  dataModelUpdate?: DataModelUpdateMsg;
  beginRendering?: BeginRenderingMsg;
  deleteSurface?: DeleteSurfaceMsg;
}

// userAction (client -> agent)
export interface UserAction {
  name: string;
  surfaceId: string;
  sourceComponentId?: string;
  timestamp: string;                // ISO 8601
  context: Record<string, unknown>;
}

// App-level surface state (built from incoming messages)
export interface SurfaceState {
  surfaceId: string;
  componentMap: Map<string, A2UIComponentDef>;  // id -> def, built from array
  rootComponentId: string;                       // from beginRendering.root
  dataModel: Record<string, unknown>;            // from dataModelUpdate
}

// Chat message (app-level wrapper)
export interface ChatMessage {
  role: 'user' | 'agent';
  content?: string;
  surface?: SurfaceState;
  timestamp: Date;
}
```

## Catalog Service

```typescript
// services/a2ui-catalog.service.ts

import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class A2UICatalogService {
  private readonly allowedTypes = new Set([
    // Layout
    'Row', 'Column',
    // Display
    'Text', 'Image', 'Icon', 'Divider',
    // Interactive
    'Button', 'TextField', 'Checkbox', 'DateTimeInput',
    // Container
    'Card', 'Modal', 'Tabs', 'List',
  ]);

  isAllowed(type: string): boolean {
    return this.allowedTypes.has(type);
  }
}
```

## Sanitizer Service (single URL policy)

`https:` only **and** a host allowlist, used by every `[src]`, `[href]` and `openUrl`. Browser-tested: with the allowlist `img.example.com`, only `https://img.example.com/a.png` rendered; `http://img.example.com/…`, `https://evil.example/…` and `javascript:…` produced no `<img>`.

```typescript
// services/a2ui-sanitizer.service.ts
import { Injectable, InjectionToken, inject } from '@angular/core';

/** Hosts that agent-supplied image/link URLs may point at. Empty (default) = every URL is rejected. */
export const A2UI_ALLOWED_URL_HOSTS = new InjectionToken<ReadonlySet<string>>('A2UI_ALLOWED_URL_HOSTS', {
  factory: () => new Set<string>(),
});

@Injectable({ providedIn: 'root' })
export class A2UISanitizerService {
  private readonly allowedHosts = inject(A2UI_ALLOWED_URL_HOSTS);

  /** The one URL policy for [src], [href] and openUrl: https only + host allowlist. '' = rejected. */
  sanitizeUrl(url: unknown): string {
    if (typeof url !== 'string') return '';
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || !this.allowedHosts.has(parsed.hostname)) return '';
      return parsed.href;
    } catch {
      return ''; // not an absolute URL
    }
  }

  sanitizeText(value: unknown): string {
    if (typeof value !== 'string') return '';
    return value.slice(0, 10_000); // length limit; rendered with {{ }} interpolation, never [innerHTML]
  }
}
```

Provide the allowlist at application level (`app.config.ts`): the service is `providedIn: 'root'`, so a component-level provider of the token is never seen (verified — the component-level provider left every image blocked).

```typescript
{ provide: A2UI_ALLOWED_URL_HOSTS, useValue: new Set(['images.example.com']) }
```

## Renderer Component (Recursive)

The renderer takes a `surface` (SurfaceState) and a `componentId` (string key into `surface.componentMap`).
It validates the component type against the catalog, resolves text via `resolveText()`, and recurses for
children. See `a2ui-renderer-template.md` for the full component implementation.

Key patterns:

- **Signal inputs**: `surface = input.required<SurfaceState>()`, `componentId = input.required<string>()`
- **Computed component**: `getComponent = computed(() => surface().componentMap.get(componentId()))`
- **Computed children (multi-child)**: `childIds = computed(() => { const comp = getComponent(); return comp?.children && 'explicitList' in comp.children ? comp.children.explicitList : []; })`
- **Computed single child (Card)**: `childId = computed(() => getComponent()?.child ?? null)`
- **Self-import**: `imports: [A2UIRendererComponent]` for recursive rendering
- **Cycle/depth guard**: inputs `depth` (default 0) and `ancestors` (`ReadonlySet<string>`); every child gets `[depth]="depth() + 1" [ancestors]="lineage()"`. A node whose id is already among its ancestors, or deeper than `MAX_DEPTH` (32), renders a placeholder. Negative control: without the guard, `root → a → root` threw `RangeError: Maximum call stack size exceeded` and crashed the tab
- **Action output**: `actionTriggered = output<UserAction>()`
- **Text resolution**: `resolveText(comp, key)` handles `{literalString}` (static), `{path}` (data binding via `surface().dataModel`), and `{path, literalString}` (path with default)
- **URL sanitization**: All `[src]`/`[href]` bindings go through `safeUrl()` which calls `sanitizeUrl()`; an empty result renders nothing
- **Unknown type, dangling id, cycle, depth**: a `problem` computed returns the reason; the template renders a visible "can't be displayed" placeholder and an `effect` reports it through Angular `ErrorHandler` (no `console.*`, no silent skip)

> Agent service (REST + SSE) and unit test templates are in `a2ui-renderer-services.md`.

---

## Bug 9 — SVG/Image fills full viewport and hides all content

**What happened:** The A2UI renderer rendered an Image or SVG component with no size constraints. The element expanded to 100% viewport width and height, hiding the rest of the UI. The user saw a blank or black screen.

## Image and SVG Size Constraints (Required)

All Image components rendered by the A2UI renderer MUST have explicit size constraints. Never render images or SVGs without capping their dimensions.

❌ FORBIDDEN — unconstrained image:
```html
<img [src]="src" />
```

✅ CORRECT — always constrain width and height:
```html
<img [src]="src" class="max-w-full max-h-64 object-contain rounded-lg" />
```

SVG from an agent is rendered only as an image file (`<img [src]>` with an allowlisted `https:` URL) inside a wrapper — never through `[innerHTML]`, `bypassSecurityTrust*` or an `<iframe>` (inline SVG can carry script and event handlers):
```html
<div class="w-full max-h-64 overflow-hidden flex items-center justify-center">
  <img [src]="src" alt="" class="max-w-full max-h-64 object-contain" />
</div>
```

**Rule:** Before shipping any A2UI renderer, test rendering a card that contains an oversized image. If it breaks the layout, the constraint is missing. Fix before reporting done.
