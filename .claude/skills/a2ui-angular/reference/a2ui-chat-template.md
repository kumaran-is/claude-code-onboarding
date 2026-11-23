# A2UI Chat Page Component Templates

> **LEGACY v0.8.** These templates drive the hand-built renderer (`a2ui-renderer-patterns.md`) and the wire
> format reference below documents v0.8 messages. New work uses v0.9 through the SDK
> (`a2ui-renderer-services.md` § Feeding messages) and the shared contract in the `genui-contract` skill
> (`../../genui-contract/reference/catalog-contract.md`). v0.8 → v0.9 names: `a2ui-protocol.md` (end of file).

## Chat Page Component

```typescript
// components/a2ui-chat/a2ui-chat.component.ts

import { Component, ErrorHandler, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { A2UIRendererComponent } from '../a2ui-renderer/a2ui-renderer.component';
import { A2UIActionGate } from '../../services/a2ui-action-gate';
import { A2UIAgentService } from '../../services/a2ui-agent.service';
import { ChatMessage, UserAction } from '../../models/a2ui.model';

@Component({
  selector: 'app-a2ui-chat',
  imports: [FormsModule, A2UIRendererComponent],
  template: `
    <div class="container mx-auto p-4 max-w-3xl">
      <h1 class="text-2xl font-bold mb-6">AI Assistant</h1>

      <div class="space-y-4 mb-6">
        @for (msg of messages(); track msg.timestamp) {
          @if (msg.role === 'user') {
            <div class="chat chat-end">
              <div class="chat-bubble chat-bubble-primary">{{ msg.content }}</div>
            </div>
          } @else if (msg.surface) {
            <div class="chat chat-start">
              <div class="chat-bubble bg-base-200 text-base-content w-full max-w-none">
                <app-a2ui-renderer
                  [surface]="msg.surface"
                  [componentId]="msg.surface.rootComponentId"
                  (actionTriggered)="handleUserAction($event)" />
              </div>
            </div>
          }
        }
      </div>

      @if (failed()) {
        <div role="alert" class="alert alert-error mb-4">The assistant could not respond. Try again.</div>
      }

      @if (loading()) {
        <div class="flex justify-center p-4">
          <span class="loading loading-dots loading-lg"></span>
        </div>
      }

      <div class="flex gap-2 sticky bottom-4">
        <input class="input flex-1" aria-label="Message" [(ngModel)]="userInput"
               [disabled]="loading()" placeholder="Ask the assistant..."
               (keyup.enter)="send()" />
        <button class="btn btn-primary"
                [disabled]="loading() || !userInput.trim()" (click)="send()">
          Send
        </button>
      </div>
    </div>
  `,
})
export class A2UIChatComponent {
  private agent = inject(A2UIAgentService);
  private actionGate = inject(A2UIActionGate);
  private errorHandler = inject(ErrorHandler);

  messages = signal<ChatMessage[]>([]);
  userInput = '';
  loading = signal(false);
  failed = signal(false);

  send(): void {
    const text = this.userInput.trim();
    if (!text) return;
    this.messages.update(msgs => [...msgs, { role: 'user', content: text, timestamp: new Date() }]);
    this.userInput = '';
    this.loading.set(true);

    this.agent.sendMessage(text).subscribe({
      next: (surface) => {
        this.messages.update(msgs => [...msgs, { role: 'agent', surface, timestamp: new Date() }]);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorHandler.handleError(err); // logged, never swallowed
        this.failed.set(true);
        this.loading.set(false);
      },
    });
  }

  handleUserAction(action: UserAction): void {
    if (!this.actionGate.permit(action)) return; // unlisted name: logged, never sent (a2ui-security.md §4)
    this.loading.set(true);
    this.agent.sendUserAction(action).subscribe({
      next: (surface) => {
        this.messages.update(msgs => [...msgs, { role: 'agent', surface, timestamp: new Date() }]);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorHandler.handleError(err); // logged, never swallowed
        this.failed.set(true);
        this.loading.set(false);
      },
    });
  }
}
```

---

## Streaming Variant (SSE + JSONL)

For progressive rendering, replace `send()` with `sendStreaming()`. Each SSE `message` event carries
one JSONL line. The service emits typed `A2UIMessage` values; the component accumulates them into a
live `SurfaceState` via `buildSurfaceState` and updates the signal on every message.

```typescript
// Add to A2UIChatComponent

sendStreaming(): void {
  const text = this.userInput.trim();
  if (!text) return;
  this.messages.update(msgs => [...msgs, { role: 'user', content: text, timestamp: new Date() }]);
  this.userInput = '';
  this.loading.set(true);

  // Accumulate all protocol messages and rebuild surface state progressively
  const accumulated: import('../../models/a2ui.model').A2UIMessage[] = [];
  const agentMsg: ChatMessage = {
    role: 'agent',
    surface: { surfaceId: '', componentMap: new Map(), rootComponentId: '', dataModel: {} },
    timestamp: new Date(),
  };
  this.messages.update(msgs => [...msgs, agentMsg]);

  this.agent.streamMessages(text).subscribe({
    next: (msg) => {
      accumulated.push(msg);
      const surface = this.agent.buildSurfaceState([...accumulated]);
      this.messages.update(msgs => {
        const updated = [...msgs];
        updated[updated.length - 1] = { ...agentMsg, surface };
        return updated;
      });
    },
    complete: () => this.loading.set(false),
    error: (err) => {
      this.errorHandler.handleError(err); // logged, never swallowed
        this.failed.set(true);
      this.loading.set(false);
    },
  });
}
```

---

## Wire Format Reference

Five message types define the full protocol. The agent sends the first four; the client sends the last.

```
agent -> client:
  surfaceUpdate   — components array [{id, component}], define the UI
  dataModelUpdate — contents array [{key, valueString|valueNumber|valueMap}], populate data
  beginRendering  — {surfaceId, root, catalogId?}, signal render-ready
  deleteSurface   — {surfaceId}, tear down

client -> agent:
  userAction      — {name, surfaceId, sourceComponentId?, timestamp, context{}}
```

### surfaceUpdate — adds or updates components

`components` is an **array** of `{id, component}` entries. `buildSurfaceState` converts this array
into a `Map<string, A2UIComponentDef>` stored as `SurfaceState.componentMap`.

```json
{
  "surfaceUpdate": {
    "surfaceId": "main",
    "components": [
      {
        "id": "root",
        "component": {
          "type": "Column",
          "children": { "explicitList": ["card-1", "btn-1"] }
        }
      },
      {
        "id": "card-1",
        "component": { "type": "Card", "child": "text-1" }
      },
      {
        "id": "text-1",
        "component": {
          "type": "Text",
          "text": { "literalString": "Hotel details" },
          "usageHint": "body"
        }
      },
      {
        "id": "btn-1",
        "component": {
          "type": "Button",
          "primary": true,
          "child": "btn-label-1",
          "action": {
            "name": "book_hotel",
            "context": [{ "key": "hotelId", "value": { "literalString": "H-456" } }]
          }
        }
      },
      {
        "id": "btn-label-1",
        "component": { "type": "Text", "text": { "literalString": "Book Now" } }
      }
    ]
  }
}
```

### dataModelUpdate — updates reactive data bindings

```json
{
  "dataModelUpdate": {
    "surfaceId": "main",
    "contents": [
      { "key": "reservationDate", "valueString": "2026-04-01" },
      { "key": "guestCount", "valueNumber": 2 }
    ]
  }
}
```

### beginRendering — signals client to start rendering

The `root` field (not `rootComponent`) identifies the root component id.

```json
{ "beginRendering": { "surfaceId": "main", "root": "root" } }
```

### deleteSurface — removes a surface

```json
{ "deleteSurface": { "surfaceId": "main" } }
```

### userAction — client sends to agent on interaction

```json
{
  "userAction": {
    "name": "book_hotel",
    "surfaceId": "main",
    "sourceComponentId": "btn-1",
    "timestamp": "2026-04-01T10:00:00.000Z",
    "context": { "hotelId": "H-456" }
  }
}
```
