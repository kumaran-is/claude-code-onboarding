# A2UI Client Integration Patterns

Reference for wiring the A2UI renderer into a real Angular application — the `agUiResource` service pattern, action handler production rules, and rate limiting. Complements `a2ui-production-architecture.md` (which covers the full stack and custom catalogs).

---

## 1. `agUiResource` Service Pattern

The recommended Angular abstraction wraps the AG-UI connection, chat history, tool definitions, widget extraction, and cleanup in a single injectable service. The component layer never touches AG-UI or A2UI directly.

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```ts
@Service()
export class TicketingChatService {
  private readonly config = inject(ConfigService);
  private readonly chatStore = inject(ChatRegistry);
  private readonly destroyRef = inject(DestroyRef);

  private readonly chat = agUiResource({
    url: this.config.agUiUrl,
    model: this.config.model,
    useServerMemory: true,
    tools: [
      findFlightsTool,
      getLoadedFlightsTool,
      toggleFlightSelectionTool,
      getCurrentBasketTool,
      displayFlightDetailTool,
    ],
  });

  constructor() {
    registerHandlers({
      checkIn: (action) => checkInAction(action),
      submitAnswer: (action) => submitAnswerAction(action, this.chat),
    });
    this.destroyRef.onDestroy(() => this.cleanupChat());
  }

  public init(): void {
    this.chatStore.setChat(this.chat);
  }

  private cleanupChat(): void {
    this.chat.dispose();
    this.chatStore.clearChat();
  }
}
```

**Key design decisions:**

| Decision | Why |
|----------|-----|
| One service per conversation context | Prevents state leaks across routes |
| `destroyRef.onDestroy` cleanup | Ensures connection disposal on route leave |
| Tools registered at construction | Agent receives consistent tool list per session |
| `useServerMemory: true` | Session memory lives on server — survives client refreshes |

---

## 2. Template Pattern — Rendering Widgets

The component template does not need to know about A2UI protocol details. It iterates messages and delegates widget rendering to `<app-widget-container>`:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```html
@for (message of chat.value(); track message.id) {
  @if (message.content) {
    <div class="message-bubble">{{ message.content }}</div>
  }
  @for (widget of message.widgets; track widget.id) {
    <app-widget-container [widget]="widget" />
  }
  @for (toolCall of message.toolCalls; track toolCall.id) {
    <div class="tool-call">Tool: {{ toolCall.name }}</div>
  }
}
```

Sending a message:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
this.chat.sendMessage({ role: 'user', content: 'Did I book my flight to France?' });
```

**Surface collection for dashboards** (request/response mode, not chat):

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
function collectWidgets(messages: AgUiChatMessage[]): AgUiWidget[] {
  return messages.flatMap(m =>
    m.role === 'assistant' && m.widgets.length > 0 ? m.widgets : [],
  );
}
```

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```html
@for (widget of widgets(); track widget.a2uiSurfaceId) {
  <app-widget-container [widget]="widget" />
}
```

---

## 3. Action Handler — Demo vs Production Pattern

### ⚠️ Demo-Only Anti-Pattern (do NOT use in production)

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
// ❌ FORBIDDEN in production
private registerHandler(): void {
  this.renderer.surfaceGroup.onAction.subscribe((action: A2uiClientAction) => {
    if (action.name !== 'increaseMiles') return;
    const passenger = action.context['passenger'] as Passenger;

    // Calling processMessages() directly from the client short-circuits the agent loop.
    // Do not do this in production.
    this.renderer.processMessages([{
      version: 'v0.9',
      updateDataModel: {
        surfaceId: this.surfaceId,
        path: '/passenger',
        value: { ...passenger, bonusMiles: passenger.bonusMiles + 300 },
      },
    }]);
  });
}
```

**Why this is dangerous:**

| Problem | Impact |
|---------|--------|
| Cuts the agent out of the loop | Agent cannot log, validate, or respond to the action |
| Breaks observability | Action is not traced; you can't debug what changed |
| Bypasses server-side validation | New A2UI state is never schema-checked |
| Creates state divergence | Client state and agent state desync silently |

### ✅ Production Pattern

Forward every action to the agent. Let the agent decide whether to emit a new `updateDataModel`.

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
// In your action handler service
private registerHandler(): void {
  this.renderer.surfaceGroup.onAction.subscribe((action: A2uiClientAction) => {
    // Forward to agent via A2A, AG-UI, or HTTP — agent decides what to update
    this.agentService.dispatchAction({
      name: action.name,
      surfaceId: action.surfaceId,
      context: action.context,
    }).subscribe();  // agent responds with new A2UI messages through the open stream
  });
}
```

```
User clicks button
  ↓
Client captures action (name, surfaceId, context)
  ↓
Client forwards action to agent (A2A / AG-UI / HTTP POST)
  ↓
Agent validates, decides response, emits new A2UI messages
  ↓
Client receives updateDataModel / updateComponents through open stream
  ↓
Renderer updates surface
```

**Rule:** The agent is always the authority on state. The client's job is to forward actions and render what comes back — never to compute state locally.

---

## 4. Rate Limits (Server-Side)

A misbehaving or compromised agent can DOS the client by spamming surface creation calls or rapid-fire actions. Apply these limits server-side (in the agent gateway or A2UI validation layer). Client-side limits are bypassable.

| Resource | Recommended Limit | Why |
|----------|------------------|-----|
| **Surfaces per session** | ~50 max | Catches runaway loops without affecting normal use |
| **Actions per second per surface** | ~5–10/s | Buttons should not fire 100 times in a second |
| **`updateDataModel` payload size** | Cap per payload | Prevents large data injections; reject oversized payloads |
| **`updateComponents` batch size** | Cap component count | Prevents single message with 10,000 components |

**Implementation location:** Apply in your agent gateway or the A2UI validation middleware, not in the Angular renderer. The renderer is the consumer of validated payloads, not the enforcer.

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
// Example: server-side surface session guard (pseudocode)
const MAX_SURFACES_PER_SESSION = 50;

function validateCreateSurface(sessionId: string, msg: A2uiMessage): void {
  const count = sessionSurfaceCount.get(sessionId) ?? 0;
  if (count >= MAX_SURFACES_PER_SESSION) {
    throw new RateLimitError(`Session ${sessionId} exceeded max surface count`);
  }
  sessionSurfaceCount.set(sessionId, count + 1);
}
```

---

## 5. `registerHandlers` Pattern

When using `agUiResource`, named action handlers are registered once at service construction. Each handler receives the action and has access to the chat resource:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```ts
registerHandlers({
  // Handler name matches the A2UI action name emitted by the component
  checkIn: (action) => checkInAction(action),

  // Handler that needs the chat resource for follow-up messages
  submitAnswer: (action) => submitAnswerAction(action, this.chat),

  // Handler for form submission with typed context
  bookFlight: (action) => {
    const { flightId, seat } = action.context as BookingContext;
    return this.bookingService.book(flightId, seat);
  },
});
```

**Rules:**

- Handler names must exactly match the `name` field in the A2UI action definition
- Handlers should forward to the agent or a backend service — never compute state locally
- `registerHandlers` should be called once, in the constructor, not on every render
- Clean up via `this.destroyRef.onDestroy(() => this.chat.dispose())` — dispose releases the connection and clears handlers
