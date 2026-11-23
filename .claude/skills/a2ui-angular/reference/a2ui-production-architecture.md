# A2UI Production Architecture

## Full Stack Architecture

```
Frontend (Angular / Flutter / React)
  A2UI renderer (@a2ui/angular)
  AG-UI or A2A client
  Trusted component catalog (client sends catalogId only — a2ui-security.md § Catalog Descriptions)
  validationConfig: STRICT_VALIDATION (SKILL.md § Security Defaults)
        ↓
Transport (SSE / WebSocket / HTTP streaming)
  AG-UI or A2A event protocol
        ↓
Agent Gateway
  AuthN/AuthZ, session state, tool routing, validation
        ↓
Agent Runtime
  ADK / LangGraph / custom orchestrator
        ↓
A2UI Validation (non-negotiable)
  Schema validation (Zod), catalog allowlist, retry loop back to LLM
  Optional: DSL → A2UI transform
        ↓
Observability + Evaluation
  Traces, tool call logs, UI generation success rate,
  validation failures, user action analytics
```

**The validation step is non-negotiable.** LLM-generated A2UI is not safe to render without it.

## AG-UI Transport Integration

A2UI messages travel inside AG-UI `ACTIVITY_SNAPSHOT` events:

```json
{
  "type": "ACTIVITY_SNAPSHOT",
  "messageId": "call_123",
  "activityType": "a2ui-surface",
  "content": {
    "operations": [
      { "version": "v0.9", "createSurface": { "surfaceId": "main", "catalogId": "https://..." } },
      { "version": "v0.9", "updateComponents": { "surfaceId": "main", "components": [...] } }
    ]
  }
}
```

There is no single required way to embed A2UI in AG-UI — `ACTIVITY_SNAPSHOT` + `activityType: 'a2ui-surface'` is the common convention.

## Domain DSL Pattern

For complex domains or mid-tier models, don't ask the LLM to generate raw A2UI. Use a domain DSL:

```
LLM generates domain DSL (small, constrained vocabulary)
  ↓
Server transforms DSL → A2UI (deterministic, tested)
  ↓
Server validates A2UI (Zod schema check)
  ↓
Client renders
```

**When to use DSL vs direct A2UI:**

| Approach | When to use |
|----------|-------------|
| Direct A2UI | Strong models, simple catalogs, team comfortable with A2UI debugging |
| Domain DSL | Mid-tier models, complex domains, lower prompt failure rate required |

## Custom Catalog Patterns

### Component definition (v0.9 SDK)

> Zod version: `@a2ui/web_core@0.15.0` depends on `zod@^3.25.76` and imports `'zod'`. Author catalog schemas with that same Zod 3 copy (`zod/v3` resolves to it); whether Zod 4 schemas are accepted is UNVERIFIED — do not mix. `@a2ui/angular@0.14.0` also exports `createComponentImplementation`, which keeps `allowedParents`/`allowedChildren` (enforced since 0.14.0) and avoids the `as unknown as` cast below; check its signature in the installed `.d.ts` before use. These two snippets are illustrative (not compiled).

```typescript
import { AngularComponentImplementation } from '@a2ui/angular/v0_9';
import { z } from 'zod/v3';

// Schema: allow concrete value OR data-model path binding
const pathBindingSchema = z.object({ path: z.string() }).strict();
const passengerOrPath = z.union([passengerSchema, pathBindingSchema]);

const milesProgressSchema = z.object({
  passenger: passengerOrPath.optional(),
}).strict();

const milesProgressEntry = {
  name: 'MilesProgress',
  component: MilesProgressComponent,
  schema: milesProgressSchema,
} as unknown as AngularComponentImplementation;
```

### Custom function (v0.9 SDK)

```typescript
import type { FunctionImplementation } from '@a2ui/web_core/v0_9';
import { z, type ZodTypeAny } from 'zod/v3';

export const formatIdImplementation = {
  name: 'formatId',
  returnType: 'string',
  schema: z.object({ value: z.number() }).strict() as unknown as ZodTypeAny,
  execute: (args: Record<string, unknown>) => {
    const { value } = z.object({ value: z.number() }).parse(args);
    return `P-${String(Math.max(0, Math.trunc(value))).padStart(4, '0')}`;
  },
} as unknown as FunctionImplementation;
```

### Extending BasicCatalogBase

```typescript
@Injectable({ providedIn: 'root' })
export class CustomCatalog extends BasicCatalogBase {
  constructor() {
    super({
      id: 'https://example.com/catalogs/my-catalog',
      extraComponents: [milesProgressEntry],
      functions: [...BASIC_FUNCTIONS, formatIdImplementation],
    });
  }
}
```

### Using the binding() helper (AG-UI abstraction)

```typescript
import { createCustomComponent, binding } from '@internal/ag-ui-client';

export const ticketWidgetEntry = createCustomComponent({
  name: 'TicketWidget',
  description: 'Boarding-pass-style widget.',
  component: TicketWidget,
  schema: z.object({
    ticketId: binding(z.union([z.string(), z.number()])),
    from: binding(z.string()),
    to: binding(z.string()),
    date: binding(z.string()),
  }).strict(),
});
```

`binding()` marks a field as accepting either a direct value or a `{ path: "/..." }` data-model reference.

### Component input types (v0.9)

```typescript
// Angular component receives context via typed input
export interface MilesProgressContext {
  passenger: BoundProperty<Passenger>; // reactive, resolves path bindings
}

@Component({ ... })
export class MilesProgressComponent {
  readonly props = input<MilesProgressContext>(initialContext);
  readonly surfaceId = input.required<string>();
  readonly componentId = input.required<string>();
  readonly dataContextPath = input('/');

  protected readonly passenger = computed(() => this.props().passenger.value());
}
```

## Charts and Dashboards

### Chart options

| Option | Use when |
|--------|---------|
| Image-based (QuickChart URL) | Prototype only — no interactivity, no accessibility |
| Custom catalog component (Chart.js etc.) | Production — interactive, themed, accessible |
| Hybrid | Custom for known visualizations, image fallback for ad-hoc |

### Dashboard widget collection pattern

```typescript
function collectWidgets(messages: AgUiChatMessage[]): AgUiWidget[] {
  return messages.flatMap(m =>
    m.role === 'assistant' && m.widgets.length > 0 ? m.widgets : [],
  );
}
```

```html
@for (widget of widgets(); track widget.a2uiSurfaceId) {
  <app-widget-container [widget]="widget" />
}
```

Dashboards work in request/response mode (not just chat): user describes a dashboard, agent emits A2UI widgets, client collects them from assistant messages.

## Testing Patterns

### Schema validation as test oracle

```typescript
test('MilesProgress rejects unknown props', () => {
  expect(() =>
    milesProgressSchema.parse({ passenger: { path: '/p' }, foo: 'bar' })
  ).toThrow();
});
```

### Golden-file tests

```typescript
test('booking confirmation emits expected A2UI', async () => {
  const messages = await runAgent('confirm booking for 2 at 7pm');
  expect(messages).toMatchSnapshot();
});
```

### Replay captured streams

Capture real A2UI streams from staging and replay them against the renderer in unit tests. Catches breakage on `@a2ui/web_core` upgrades or catalog changes.

## Observability Metrics

Standard metrics (latency, error rate) plus these A2UI-specific ones:

| Metric | Why it matters |
|--------|---------------|
| Validation failure rate per component | Which catalog entries does the LLM trip on most? |
| Catalog usage frequency | Are you maintaining unused components? |
| Action-to-rerender latency | User-perceived loop time (click → new UI) |
| Most common invalid outputs | Feeds prompt improvements |
| Surface lifecycle errors | `updateComponents` before `createSurface`, etc. |

A spike in validation failure rate is usually the earliest signal of an LLM regression — before users notice.

## When NOT to Use A2UI

- Plain text is enough (don't reach for structured UI when a sentence works)
- The UI is fully static and deterministic — build it normally
- The visualization is genuinely novel (3D, complex animations, custom gestures) — use MCP Apps instead
- You can't host a server-side validator — A2UI without validation is dangerous
- Latency is critical and your transport doesn't stream — REST-only loses progressive rendering

## A2UI vs MCP Apps

| | A2UI | MCP Apps |
|--|------|---------|
| Rendering | Native client components | Sandboxed iframe |
| Design system | Consistent with host app | Visually disjoint |
| Agent control | Bounded by catalog | Full UI expressivity |
| Pick when | Brand consistency matters | Agent needs UI beyond catalog |

They can coexist: A2UI can host an MCP App as a registered component (double-iframe isolation pattern).

## Resources

- A2UI Composer (visual widget builder): https://a2ui.org/composer/
- v0.9 spec: https://a2ui.org/specification/v0.9-a2ui/
- v0.8 spec: https://a2ui.org/specification/v0.8-a2ui/
- v0.8 → v0.9 evolution guide: https://a2ui.org/specification/v0.9-evolution-guide/
- Message reference: https://a2ui.org/reference/messages/
