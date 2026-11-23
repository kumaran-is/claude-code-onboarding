# CopilotKit for Angular with A2UI (optional)

CopilotKit is **optional**. A2UI is the payload contract, AG-UI is an optional transport, and the `@a2ui/angular` renderer runs without either (`canonical-catalog-angular.md`). Use CopilotKit only when you want its chat/agent runtime client. When the app owns chat, state and transport, use the direct path.

## Compatibility (checked 2026-11-23 with `npm view` and `npm pack`, sources read)

| Package | Version | Angular peer | A2UI | AG-UI client | Status |
|---|---|---|---|---|---|
| `@copilotkit/angular` | 0.6.0 (latest) | `^22.0.0` | v0.9 via `@a2ui/web_core` 0.10.4 | `@ag-ui/client` 1.0.2 | **Not compatible with Angular 21.2.x** (0.4.x and 0.5.x also peer `^22`) |
| `@copilotkit/angular` | 0.3.1 | `^20 \|\| ^21 \|\| ^22` (package metadata lists Angular 21.2.18 / TS 5.9.3 as tested) | v0.9 through the Lit renderer `@copilotkit/a2ui-renderer` 1.66.0 (`@a2ui/web_core` 0.10.4) | `@ag-ui/client` 0.0.57 | Installs beside Angular 21.2.26 (exit 0). Bridge below: compile-proven (`tsc` exit 0). Runtime: NOT RUN |
| `@copilotkitnext/angular` | 1.54.3 | `^19` only | — | — | Not compatible |
| `@a2ui/angular` | 0.14.0 | `^21.2.5` | v0.9 (`/v0_9`), `@a2ui/web_core` 0.15.0 | — | DOCUMENTED AND TESTED (default renderer) |
| `@ag-ui/client` | 1.0.5 | — | carries A2UI in `ACTIVITY_SNAPSHOT` | — | DOCUMENTED AND TESTED with `HttpAgent` (needs CRLF normalization, see `canonical-catalog-angular.md`) |

Pin `@copilotkit/angular@0.3.1` exactly on Angular 21. Re-check the peer range before upgrading Angular.

## What CopilotKit 0.3.1 does with A2UI (SOURCE-PROVEN)

- Its built-in activity renderer handles `activityType: "a2ui-surface"`. It reads `content.a2ui_operations` (or `content.operations`) and renders through a **Lit** web component (`cpk-a2ui-surface`) with its own `@a2ui/web_core` 0.10.4 and a Lit catalog. `provideCopilotKit({ a2ui: { catalog } })` takes Lit component implementations, not `@a2ui/angular` ones.
- Its A2UI action bridge writes the action into `copilotKit.core.properties.a2uiAction` and calls `runAgent`. It sends no idempotency key and no per-action policy. The agent runtime must authorize every action server-side, and side-effecting actions need a server-held confirmation.
- `registerRenderActivityMessage({ activityType, content, component })` (or `renderActivityMessages` in the config) registers an Angular component for an activity type and takes precedence over the built-in renderers.

## Integration paths

| Path | Use when | Stack |
|---|---|---|
| **A. Direct A2UI** (default) | The app owns chat, state and transport | `@a2ui/angular` + canonical catalog + ingest guard + action gateway, over SSE or `@ag-ui/client` `HttpAgent` |
| **B. Full copilot** | You want CopilotKit's agent/chat client and an AG-UI-compatible runtime | `@copilotkit/angular@0.3.1` + the bridge below, so `a2ui-surface` activities render with the same `@a2ui/angular` catalog and guard |

Do not render the canonical catalog with CopilotKit's built-in Lit renderer next to `@a2ui/angular`. That mixes two `web_core` versions (0.10.4 and 0.15.0) and two catalogs, and the canonical guard would not run.

## Bridge: CopilotKit activity → `@a2ui/angular` (compile-proven, runtime NOT RUN)

```typescript
import { ChangeDetectionStrategy, Component, effect, inject, input, untracked, type Signal } from '@angular/core';
import { SurfaceComponent } from '@a2ui/angular';
import { anyActivityContentSchema, provideCopilotKit, registerRenderActivityMessage, type ActivityRenderer } from '@copilotkit/angular';
import type { Provider } from '@angular/core';
import { A2UI_ACTIVITY_TYPE } from './agui-adapter';
import { GenuiSession } from './genui-session';

type A2uiActivityContent = Record<string, unknown>;
// CopilotKit 0.3.1 nests its own @ag-ui/client 0.0.57; take the types from its interface, not the app's copy.
type SignalValue<S> = S extends Signal<infer V> ? V : never;
type CkMessage = SignalValue<ActivityRenderer['message']>;
type CkAgent = SignalValue<ActivityRenderer['agent']>;

/**
 * Renders CopilotKit `a2ui-surface` activity messages with the app's @a2ui/angular catalog instead
 * of CopilotKit's built-in Lit renderer (which bundles its own @a2ui/web_core 0.10.4 and Lit catalog).
 * Each activity gets its own guard; actions still leave through ActionGateway (REST + authz).
 */
@Component({
  selector: 'app-copilot-a2ui-activity',
  imports: [SurfaceComponent],
  providers: [GenuiSession],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (session.problems().length) {
      <p role="alert">Some generated content was rejected ({{ session.problems()[0].code }}).</p>
    }
    @for (surfaceId of session.surfaceIds(); track surfaceId) {
      <a2ui-v09-surface [surfaceId]="surfaceId" />
    }
  `,
})
export class CopilotA2uiActivityComponent implements ActivityRenderer<A2uiActivityContent> {
  readonly activityType = input.required<string>();
  readonly content = input.required<A2uiActivityContent>();
  readonly message = input.required<CkMessage>();
  readonly agent = input<CkAgent>();
  protected readonly session = inject(GenuiSession);

  constructor() {
    effect(() => {
      const operations = this.content()['a2ui_operations'];
      if (Array.isArray(operations)) untracked(() => this.session.replaySnapshot(operations));
    });
  }
}

/** Call from an injection context (e.g. the root component constructor). */
export function registerA2uiActivityRenderer(): void {
  registerRenderActivityMessage({
    activityType: A2UI_ACTIVITY_TYPE,
    content: anyActivityContentSchema,
    component: CopilotA2uiActivityComponent,
  });
}

/**
 * Full-copilot path: CopilotKit talks to an AG-UI-compatible runtime; `a2ui-surface` activities
 * render with this app's catalog. Headers here are public (no secrets in the bundle); auth is a
 * same-origin session cookie or a token added by an interceptor at runtime.
 */
export function provideCopilotWithA2ui(runtimeUrl: string): Provider {
  return provideCopilotKit({
    runtimeUrl,
    renderActivityMessages: [
      { activityType: A2UI_ACTIVITY_TYPE, content: anyActivityContentSchema, component: CopilotA2uiActivityComponent },
    ],
  });
}
```

Two `@ag-ui/client` copies are installed (the app's 1.0.5 and CopilotKit's nested 0.0.57). Their `AbstractAgent` types are not assignable to each other (`TS2416` when the inputs were typed from the app's copy). Take the input types from CopilotKit's `ActivityRenderer` as shown.

Each activity component provides its own `GenuiSession`, so every activity gets its own guard state. Actions from these surfaces still go through `ActionGateway` (REST, allowlist, idempotency key, server authz), not CopilotKit's `a2uiAction` bridge.
