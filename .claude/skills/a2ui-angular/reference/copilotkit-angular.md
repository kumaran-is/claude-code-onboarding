# CopilotKit for Angular (optional integration path B)

Verified 2026-11-23 with `npm view`, the package's `.d.ts`, and a compiled Angular 22.3.0 sandbox (Node 26.13.1).

## Compatibility

| Package | Version | Peer | A2UI wire | Status |
|---|---|---|---|---|
| `@copilotkit/angular` | **0.6.0** (npm `latest`; `next` is `2.0.0-rc.68`, prerelease, not used) | `@angular/core`/`common`/`cdk` `^22.0.0`, `rxjs ^7.8.0` | v0.9 (nests `@a2ui/web_core` 0.10.4; `@copilotkit/core` 1.90.0 brings 0.15.0) | Installs on Angular 22.3.0 with no peer conflict. HITL renderer compiled and unit-tested (MOCK). LIVE run against a CopilotKit runtime: NOT RUN |
| `@ag-ui/client` | 1.0.5 | `zod ^3.25.18 \|\| ^4` | — | CopilotKit 0.6.0 nests its own 1.0.2 |
| `@a2ui/angular` | 0.16.0 | Angular `^22.2.3` | v0.9 (`/v0_9`) and v1.0 (root) | Default renderer (`../SKILL.md`) |

There is no `@copilotkit/angular` 1.x; the 1.90.0 line is React/runtime (`@copilotkit/react-core`, `runtime`, `a2ui-renderer`). `@copilotkit/angular` 0.6.0 is published by GitHub Actions with SLSA provenance.

## Which path

| Path | Use when |
|---|---|
| A. Direct A2UI (`@a2ui/angular`) | The app owns transport, the catalog must match the cross-platform contract, or you need v1.0 |
| B. CopilotKit | You want CopilotKit chat (`CopilotChat`, `CopilotSidebar`, `CopilotPopup`), frontend tools, human-in-the-loop and interrupts against a CopilotKit runtime |

Which runtime processes the messages (determined by execution, 2026-11-23):

| Path | Code that processes A2UI | web_core copy | Wire versions |
|---|---|---|---|
| A. `@a2ui/angular` direct (AG-UI `ACTIVITY_SNAPSHOT` `a2ui-surface` or JSONL) | `A2uiRendererService` → `MessageProcessor` | top-level `@a2ui/web_core` 0.16.1 | 1.0 (root entry) and v0.9. A LIVE run against an AG-UI backend on 1.0 passed |
| B. CopilotKit Angular 0.6.0 (`@copilotkit/angular/a2ui`) | CopilotKit's renderer, which imports `@a2ui/web_core/v0_9` | its nested `@a2ui/web_core` **0.10.4** (no `./v1_0` export) | v0.9 only. A 1.0 stream fed to that processor raised **no error** and created the surface, so the rejection has to come from your gate |

Do not render one surface with both CopilotKit's A2UI renderer and `@a2ui/angular`: that means two processors on two web_core versions and double dispatch. Mixing them on one surface is untested. Use path B for v0.9 surfaces only, or keep A2UI surfaces on path A and use CopilotKit only for chat, tools and HITL.

## Current (non-deprecated) APIs used here

From `dist/types/copilotkit-angular.d.ts` (0.6.0; no `@deprecated` tags in that file):
- `provideCopilotKit(config?: CopilotKitConfig): Provider`. Config fields: `runtimeUrl`, `headers` (record or sync/async builder), `credentials`, `messageFilter`, `agents`, `tools`, `frontendTools`, `humanInTheLoop`, `renderToolCalls`, `renderActivityMessages`, `a2ui` (`catalog`, `loadingComponent`, `recovery`), `openGenerativeUI`, `enableInspector`.
- `registerHumanInTheLoop(config)` / `registerFrontendTool` / `registerComponent` / `registerRenderToolCall`: call in an injection context; registration ends with that injector.
- `HumanInTheLoopToolRenderer<Args>`: `toolCall: Signal<HumanInTheLoopToolCall<Args>>`, status `in-progress` → `executing` → `complete`, `respond(result)`.
- Streaming state: `injectAgentStore(agentId)` → `Signal<AgentStore>` with `isRunning`, `messages`, `state` signals.
- Interrupts and cancellation: `injectInterrupt(agentId?)` → `InterruptController` with `resolve(payload?)` and `cancel()`.
- `parameters` takes a Standard Schema; zod 3.25.x qualifies.

## Human-in-the-loop renderer (compiled, ng lint clean, unit test passes)

```typescript
import { Component, computed, input, signal } from '@angular/core';
import type { HumanInTheLoopToolCall, HumanInTheLoopToolRenderer } from '@copilotkit/angular';
import { z } from 'zod';

export const approvalArgs = z.object({ requestId: z.string(), summary: z.string() });
export type ApprovalArgs = z.infer<typeof approvalArgs>;

/** HITL renderer: the agent's run pauses until the user answers through `respond`. */
@Component({
  selector: 'app-approval-hitl',
  template: `
    <section role="group" aria-label="Approval required" class="space-y-2">
      <p>{{ summary() }}</p>
      @if (toolCall().status === 'executing' && !answered()) {
        <button type="button" class="btn btn-primary min-h-11" (click)="answer(true)">Approve</button>
        <button type="button" class="btn min-h-11" (click)="answer(false)">Reject</button>
      } @else if (toolCall().status === 'complete') {
        <p role="status">Answered.</p>
      }
    </section>
  `,
})
export class ApprovalHitl implements HumanInTheLoopToolRenderer<ApprovalArgs> {
  readonly toolCall = input.required<HumanInTheLoopToolCall<ApprovalArgs>>();
  protected readonly summary = computed(() => this.toolCall().args.summary ?? '');
  protected readonly answered = signal(false);

  protected answer(approved: boolean): void {
    if (this.answered()) return;
    this.answered.set(true);
    this.toolCall().respond({ approved, requestId: this.toolCall().args.requestId });
  }
}
```

```typescript
import { type Provider } from '@angular/core';
import { provideCopilotKit } from '@copilotkit/angular';
import { ApprovalHitl, approvalArgs } from './approval-hitl';

/** CopilotKit for Angular 0.6.0: runtime endpoint plus a HITL tool rendered by ApprovalHitl. */
export function provideCopilot(runtimeUrl: string): Provider {
  return provideCopilotKit({
    runtimeUrl,
    credentials: 'include',
    humanInTheLoop: [
      {
        name: 'request_approval',
        description: 'Ask the user to approve or reject a request before acting on it.',
        parameters: approvalArgs,
        component: ApprovalHitl,
      },
    ],
  });
}
```

Add `provideCopilot('/api/copilotkit')` to `appConfig.providers`. Use the session cookie (`credentials: 'include'`) or a `headers` builder for a short-lived token; never put a long-lived secret in the bundle.

Test (MOCK: hand-built tool call, no runtime): clicking Approve twice calls `respond` exactly once with `{ approved: true, requestId: 'req-1' }`.

## Rules

- The agent's tool result is a request, not an authorization. The backend re-checks the user's permission before acting on `approved: true`.
- Show `isRunning()` from `injectAgentStore` as a polite live region and offer a stop control (`injectInterrupt().cancel()` for interrupts; abort the run for streaming).
- Button labels on approval UIs are app-authored, never model text.
- Re-check the peer range and nested `@a2ui/web_core` version on every CopilotKit bump (`npm ls @a2ui/web_core`).
