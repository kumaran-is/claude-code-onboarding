# Generative UI in React (A2UI v0.9)

> **Evidence.** The renderer-only path below was compiled and executed on 2026-11-23 in a disposable
> React 19.3.1 + Vite 8.3.8 + TypeScript 5.9.3 app against the shared canonical-catalog fixtures and
> a live reference backend in **both** topologies: `tsc` exit 0, `vite build` exit 0, `vitest run`
> 30/30, Playwright + `@axe-core/playwright` 12/12 in Chromium (6 checks × 2 topologies). Negative
> controls: allowlist removed → Vitest 1 failure; integer binding broken → 1 failure; planted type
> error → `tsc` exit 2; 403 message removed → Playwright 2 failures; wrong guard code → 1 failure;
> new idempotency key per retry → 1 failure; in-flight block and `disabled` removed → 1 failure. **Not run:** the CopilotKit path
> (types read from the package only): **DOCUMENTED BUT NOT TESTED**.

The wire contract (catalog IDs, action allowlist, payload schemas, golden payloads, fixtures,
topologies) is owned by the framework-neutral [`genui-contract`](../../genui-contract/SKILL.md) skill.
This file covers only how a React SPA renders that contract. Never put a React component name on the
wire; the catalog maps IDs to components.

## Choose a path

| Need | Path | Packages (pin exactly) |
|---|---|---|
| Render agent-generated surfaces in an existing app | **A. Official renderer, no CopilotKit** (default) | `@a2ui/react@0.15.0`, `@a2ui/web_core@0.15.0` |
| Full copilot (chat, threads, tool UIs) whose agent also emits A2UI | **B. CopilotKit** (optional) | `@copilotkit/react-core@1.90.0` (bundles `@copilotkit/a2ui-renderer@1.90.0`, `@a2ui/web_core@0.15.0`, `@ag-ui/client@1.0.5`) |

Roles: A2UI is the UI payload; AG-UI is an agent event transport (needed only if you use it);
CopilotKit is an app framework. None of B is required to render A2UI.

| Package | Version | React peer | A2UI | Status |
|---|---|---|---|---|
| `@a2ui/react` | 0.15.0 | `^18 \|\| ^19` | `./v0_9` (use) and `./v0_8` (legacy; still the package root export) | DOCUMENTED AND TESTED |
| `@a2ui/web_core` | 0.15.0 | — | `./v0_9` `MessageProcessor`, `STRICT_VALIDATION`; also contains v1.0 code (not adopted) | DOCUMENTED AND TESTED |
| `@copilotkit/react-core` | 1.90.0 | `^18 \|\| ^19` | built-in A2UI renderer, activated when the runtime has `a2ui` configured | SOURCE-PROVEN (`.d.mts`), not run |
| `@copilotkit/a2ui-renderer` | 1.90.0 | `^18 \|\| ^19` | v0.9 default, `protocolVersion?: "v0.9" \| "1.0"` | SOURCE-PROVEN, not run |

Always import from `@a2ui/react/v0_9` and `@a2ui/web_core/v0_9`; the bare `@a2ui/react` root is the
v0.8 API (`A2UIProvider`, `A2UIRenderer`). Never mix versions on one surface.

### Dependency findings (check before adopting)

- `@a2ui/react@0.15.0` and `@a2ui/web_core@0.15.0` depend on **zod 3** (`^3.25.76`); this skill pins
  zod 4 for forms. npm installs both (it warns `ERESOLVE overriding peer dependency`). Write catalog
  schemas with the zod 3 copy the A2UI packages resolve; zod 4 schemas in a `Catalog` fail (tested,
  table below).
- `npm audit --omit=dev` (2026-11-23) on the A2UI packages alone: 4 **high** (GHSA-mrhx-c7xc-m3w5,
  zod `<4.6.6`, memory exhaustion on oversized constrained collections; reported on zod and the three
  A2UI packages that pull it) and 1 **moderate** (DOMPurify `<=3.4.16`, several sanitizer bypasses,
  via `@a2ui/markdown-it@0.2.2`, which also peers `@a2ui/web_core@^0.14.0`).

  | Mitigation (tested) | Result |
  |---|---|
  | `"overrides": { "dompurify": "3.5.0" }` | moderate cleared; `tsc` 0, Vitest 28/28, `vite build` 0, Playwright 12/12. **Use it.** |
  | `"overrides": { "zod": "4.6.7" }` | audit clean, but `@a2ui/web_core` fails at runtime (`TypeError: Cannot read properties of undefined (reading 'call')`), no test runs. **Do not use.** |
  | zod 4 at the app root, zod 3 nested under A2UI | catalog schemas built with zod 4 fail `tsc` (`Property '_zod' is missing`) and 5 render tests. Catalog schemas must use the zod 3 copy. |

  The zod advisory stays open until A2UI ships on zod ≥ 4.6.6. Documented risk: the attack needs an
  oversized constrained collection, so cap every inbound message at the contract's `maxMessageBytes`
  **before** `JSON.parse` (`ingest` below), keep the server's own request limit, record the
  exception in the security review, and re-run `npm audit --omit=dev` on every A2UI bump. Run
  `npm install` from a clean `node_modules` after changing overrides: an in-place install left zod 4
  at the root and broke the build.

## A. Official renderer (no CopilotKit)

Three pieces: a catalog (IDs → React), a `MessageProcessor` with `STRICT_VALIDATION`, and
`<A2uiSurface>` per surface. Use `createBinderlessComponentImplementation` when a component reads and
writes data-model paths itself (forms); it must then resolve an action's bindings before dispatch,
otherwise `{path}` objects reach the server verbatim (found by test).

```tsx
import { useId, useSyncExternalStore } from 'react';
import { z } from 'zod'; // the zod 3 copy @a2ui/web_core resolves
import { Catalog, CommonSchemas, type ComponentContext } from '@a2ui/web_core/v0_9';
import { EmailImplementation, LengthImplementation, NumericImplementation, RequiredImplementation } from '@a2ui/web_core/v0_9/basic_catalog';
import { createBinderlessComponentImplementation } from '@a2ui/react/v0_9';

export const CANONICAL_CATALOG_ID = 'https://catalogs.example.com/genui/canonical/v1/catalog.json';

/** A server event whose name is in this component's allowlist. functionCall actions are rejected. */
const serverEvent = <const N extends readonly [string, ...string[]]>(names: N) =>
  z.object({
    event: z.object({
      name: z.enum(names),
      context: z.record(
        z.string().regex(/^[a-z][a-zA-Z0-9_]{0,63}$/),
        z.union([z.string(), z.number().int(), z.boolean(), CommonSchemas.DataBinding]),
      ).optional(),
    }).strict(),
  }).strict();

const ApprovalFormApi = {
  name: 'ApprovalForm',
  schema: z.object({
    accessibility: CommonSchemas.AccessibilityAttributes.optional(),
    title: CommonSchemas.DynamicString,
    summary: CommonSchemas.DynamicString,
    requestId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/),
    riskLevel: z.enum(['low', 'medium', 'high']),
    comment: CommonSchemas.DataBinding.optional(),
    approveAction: serverEvent(['approval.approve']),
    rejectAction: serverEvent(['approval.reject']),
  }).strict(),
};

/** Subscribes to a dynamic value (literal, {path} binding or function call) and returns it. */
function useDynamicValue(context: ComponentContext, dynamic: unknown): unknown {
  return useSyncExternalStore(
    (onChange) => {
      if (dynamic === undefined) return () => undefined;
      const sub = context.dataContext.subscribeDynamicValue(dynamic, onChange);
      return () => sub.unsubscribe();
    },
    () => (dynamic === undefined ? undefined : context.dataContext.resolveDynamicValue(dynamic)),
  );
}

function dispatchResolved(context: ComponentContext, action: unknown): void {
  const resolved = context.dataContext.resolveAction(action as Record<string, unknown>, { userActivation: true });
  if (resolved === undefined) return;
  void context.dispatchAction(resolved as Record<string, unknown>);
}

const asText = (value: unknown): string => (value === undefined || value === null ? '' : String(value));

const ApprovalForm = createBinderlessComponentImplementation(ApprovalFormApi, ({ context }) => {
  const parsed = ApprovalFormApi.schema.parse(context.componentModel.properties);
  const title = asText(useDynamicValue(context, parsed.title));
  const summary = asText(useDynamicValue(context, parsed.summary));
  const comment = asText(useDynamicValue(context, parsed.comment));
  const headingId = useId();
  const commentId = useId();
  return (
    <section className="genui-form" aria-labelledby={headingId} role="form">
      <h3 id={headingId}>{title}</h3>
      <p>{summary}</p>
      <p><strong>Risk:</strong> {parsed.riskLevel}</p>{/* text, never colour alone */}
      {parsed.comment ? (
        <div className="genui-field">
          <label htmlFor={commentId}>Comment</label>
          <textarea id={commentId} maxLength={1000} value={comment}
            onChange={(e) => parsed.comment && context.dataContext.set(parsed.comment.path, e.target.value)} />
        </div>
      ) : null}
      <button type="button" onClick={() => dispatchResolved(context, parsed.approveAction)}>Approve</button>
      <button type="button" onClick={() => dispatchResolved(context, parsed.rejectAction)}>Reject</button>
    </section>
  );
});

// ActionCard, InputForm and ConfirmationDialog follow the same pattern (InputForm: one <FormField>
// per field so each field's hook call is stable; integer fields write numbers, not strings;
// ConfirmationDialog: role="alertdialog" with dialog.confirm / dialog.cancel server events).
export const canonicalCatalog = new Catalog(CANONICAL_CATALOG_ID, 'v0.9',
  [ApprovalForm /*, ActionCard, InputForm, ConfirmationDialog */],
  [RequiredImplementation, LengthImplementation, EmailImplementation, NumericImplementation]);
```

Catalog mapping (canonical ID → React), all four tested: `ActionCard` → `<article>` + buttons;
`InputForm` → `<form>` with labelled inputs, native `required`/`maxLength`; `ApprovalForm` →
`role="form"` section with labelled comment and two buttons; `ConfirmationDialog` →
`role="alertdialog"` section with confirm/cancel buttons. Unmapped IDs (`DataSummaryTable`,
`SelectionList`, `DetailPanel`, `StatusIndicator`) are rejected as `UNKNOWN_COMPONENT` by the ingest
guard (and by `STRICT_VALIDATION`, `allowUnknownElements: false`) until you implement them; the user
sees an error, never a blank. Each component's controls are `disabled` while its action is in flight
(`PendingActionsContext`, below).

### Guards around the renderer

`STRICT_VALIDATION` checks references, cycles and depth, but not component props or a missing
`version` (see the contract's §5). An app-owned ingest guard runs first and throws the contract's
error codes (`MESSAGE_TOO_LARGE`, `MALFORMED_MESSAGE`, `UNSUPPORTED_VERSION`, `UNSAFE_CONTENT`,
`STRING_TOO_LONG`, `UNSUPPORTED_CATALOG`, `SURFACE_NOT_FOUND`, `UNKNOWN_COMPONENT`,
`FUNCTION_ACTION_FORBIDDEN`, `ACTION_NOT_ALLOWED`, `SCHEMA_INVALID`); processor rejections map to
`MISSING_ROOT` / `CYCLE` / `MAX_DEPTH_EXCEEDED` / `DANGLING_REFERENCE`. The server re-validates and
authorises every action regardless.

```ts
export function ingest(raw: string, ctx: IngestContext): Record<string, unknown> {
  // Size cap on the raw bytes, BEFORE JSON.parse (a test spies on JSON.parse to prove it).
  if (new TextEncoder().encode(raw).byteLength > LIMITS.maxMessageBytes) {
    throw new ContractViolation('MESSAGE_TOO_LARGE', 'message exceeds maxMessageBytes');
  }
  let message: unknown;
  try {
    message = JSON.parse(raw);
  } catch (cause) {
    throw new ContractViolation('MALFORMED_MESSAGE', `message is not JSON: ${String(cause)}`);
  }
  if (message === null || typeof message !== 'object' || Array.isArray(message)) {
    throw new ContractViolation('MALFORMED_MESSAGE', 'message is not an object');
  }
  const msg = message as Record<string, unknown>;
  if (!('version' in msg)) throw new ContractViolation('MALFORMED_MESSAGE', 'message has no version');
  if (msg.version !== 'v0.9') throw new ContractViolation('UNSUPPORTED_VERSION', `unsupported version ${String(msg.version)}`);
  const bodies = BODIES.filter((b) => b in msg);
  if (bodies.length !== 1) throw new ContractViolation('MALFORMED_MESSAGE', 'need exactly one message body');
  scanStrings(msg); // UNSAFE_CONTENT (javascript:, <script, ...) and STRING_TOO_LONG
  const kind = bodies[0]!;
  const body = msg[kind] as { surfaceId?: unknown; catalogId?: unknown; components?: unknown };
  if (kind === 'createSurface') {
    if (body.catalogId !== ctx.catalogId) throw new ContractViolation('UNSUPPORTED_CATALOG', 'unknown catalogId');
    return msg;
  }
  if (!ctx.hasSurface(String(body.surfaceId))) throw new ContractViolation('SURFACE_NOT_FOUND', 'surface not created');
  if (kind === 'updateComponents' && Array.isArray(body.components)) {
    for (const component of body.components as Record<string, unknown>[]) {
      const spec = ctx.components[String(component.component)]; // per-component prop schema + action allowlist
      if (!spec) throw new ContractViolation('UNKNOWN_COMPONENT', `unknown component ${String(component.component)}`);
      const { id: _id, component: _name, ...props } = component;
      checkActions(props, spec.actions); // FUNCTION_ACTION_FORBIDDEN, ACTION_NOT_ALLOWED
      if (!spec.schema.safeParse(props).success) throw new ContractViolation('SCHEMA_INVALID', `invalid ${String(_name)} props`);
    }
  }
  return msg;
}

/** Validates an action emitted by the renderer before anything leaves the browser. */
export function toOutboundAction(action: ActionPayload, newKey: () => string = () => crypto.randomUUID()): OutboundAction {
  if (!isAllowed(action.name)) throw new ContractViolation('ACTION_NOT_ALLOWED', `action ${action.name} is not allowlisted`);
  const spec = ACTIONS[action.name]; // per action: payload zod schema (strict) + idempotent flag
  const parsed = spec.payload.safeParse(action.context);
  if (!parsed.success) throw new ContractViolation('ACTION_PAYLOAD_INVALID', parsed.error.issues[0]?.message ?? 'invalid payload');
  const { name, surfaceId, sourceComponentId, timestamp } = action;
  return {
    body: { version: 'v0.9', action: { name, surfaceId, sourceComponentId, timestamp, context: parsed.data } },
    idempotencyKey: spec.idempotent ? newKey() : undefined, // header only, never in context; newKey is per intent (below)
  };
}
```

Rules: no `dangerouslySetInnerHTML`, no model-supplied URLs in `href`/`src` (the canonical catalog has
none); the model never decides authorisation (the server derives it from the session); high-risk
actions (`approval.*`, `dialog.confirm`) only fire from an explicit user click; the token lives in
memory and goes in `Authorization`, never in the bundle, the URL or `localStorage`.

### Host: processor, stream, actions

Feed per-message (`processMessagesWithErrors`) so one bad message is rejected without losing valid
surfaces. The stream is an external system, so an effect owns it; actions go through a TanStack Query
mutation. SSE runs over `fetch` (not `EventSource`) so it can send `Authorization`, abort via
`AbortSignal` and resume with `Last-Event-ID`.

```tsx
const [processor] = useState(() =>
  new MessageProcessor<ReactCatalogComponent>([canonicalCatalog], (a) => sendRef.current(a), {
    validationConfig: STRICT_VALIDATION,
  }));
useEffect(() => () => processor.dispose(), [processor]);

useEffect(() => {
  const controller = new AbortController();
  abortRef.current = controller; // a Stop button calls abort(); Reconnect bumps runId
  const run = async () => {
    for (let attempt = 0; attempt <= MAX_RECONNECTS; attempt += 1) {
      try {
        setStatus('connecting');
        for await (const event of readSse(endpoints, controller.signal, lastEventIdRef.current)) {
          setStatus('streaming');
          lastEventIdRef.current = event.id ?? lastEventIdRef.current; // a ref: survives Stop → Reconnect
          if (event.event === 'done') break;
          if (event.event === 'error') {
            const code = (JSON.parse(event.data) as { code?: unknown }).code;
            throw new StreamError(typeof code === 'string' ? code : 'UNKNOWN');
          }
          if (event.event === 'resync') {
            // Resume window exceeded: drop local surfaces; a full replay follows.
            for (const id of [...processor.getSurfaces().keys()]) {
              processor.processMessagesWithErrors({ version: 'v0.9', deleteSurface: { surfaceId: id } });
            }
            continue;
          }
          feed(event.data); // ingest + processMessagesWithErrors; reports, never throws
        }
        setStatus('closed');
        return;
      } catch (e) {
        if (controller.signal.aborted) return setStatus('cancelled');
        if (e instanceof HttpError || e instanceof StreamError) { report(e); return setStatus('failed'); } // no retry
        if (attempt === MAX_RECONNECTS) { report(e); return setStatus('failed'); }
        await new Promise((resolve) => setTimeout(resolve, 250 * 2 ** attempt));
      }
    }
  };
  void run();
  return () => controller.abort();
}, [endpoints, processor, report, runId]);
```

Render surfaces from `processor.getSurfaces()` through `useSyncExternalStore` subscribed to
`onSurfaceCreated`/`onSurfaceDeleted`; show `role="status"` for stream state and `role="alert"` for
errors (403 → "You are not allowed to do that."). Never render a surface the processor rejected.

Action responses: a `202 confirmation_required` body carries A2UI messages for a `ConfirmationDialog`
surface; feed them through the same `ingest` + `processMessagesWithErrors` path, render the dialog
(`role="alertdialog"`), and send `dialog.confirm` with its own `Idempotency-Key`. The server executes
the operation it stored under `dialogId`, never one named in the payload.

Idempotency key per user intent, not per call. The intent is component + action + resolved context:
the key is created when the component first triggers it, reused when the user retries after a
failure, and dropped after success. A changed form is a new intent with a new key, so the server
never sees one key with two bodies. While the request is in flight the component's controls are
disabled and a repeat trigger is ignored.

```tsx
const intentKeys = useRef(new Map<string, string>());
const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
const pendingRef = useRef(new Set<string>());
const { mutateAsync } = action;
useEffect(() => {
  const setBusy = (key: string, busy: boolean) => {
    if (busy) pendingRef.current.add(key);
    else pendingRef.current.delete(key);
    setPending(new Set(pendingRef.current));
  };
  sendRef.current = (a) => {
    const componentKey = `${a.surfaceId}/${a.sourceComponentId}`;
    if (pendingRef.current.has(componentKey)) return; // double click while in flight
    const intent = `${componentKey}/${a.name}/${JSON.stringify(a.context)}`;
    let outbound: OutboundAction;
    try {
      outbound = toOutboundAction(a, () => {
        const existing = intentKeys.current.get(intent);
        if (existing) return existing;
        const created = crypto.randomUUID();
        intentKeys.current.set(intent, created);
        return created;
      });
    } catch (e) {
      report(e);
      return;
    }
    setBusy(componentKey, true);
    mutateAsync(outbound)
      .then(() => intentKeys.current.delete(intent))
      .catch(report) // key kept: a retry of the same intent reuses it
      .finally(() => setBusy(componentKey, false));
  };
}, [mutateAsync, report]);
// Render: <PendingActionsContext value={pending}>{surfaces}</PendingActionsContext>; each
// component reads it and sets `disabled` on its buttons while `${surfaceId}/${componentId}` is pending.
```

Late data overwrites edits: an `updateDataModel` that arrives after the user typed replaces the typed
value (seen live with a 300 ms emit delay). Keep inputs read-only or show a pending state until the
stream reports done, or have the agent send the data model before the components.

### Topologies

Only the endpoints differ; the catalog, guards and components do not
([backend topologies](../../genui-contract/reference/backend-topologies.md)).

| Topology | `streamUrl` / `actionUrl` | Notes |
|---|---|---|
| `shared-backend` | same-origin paths (for the reference backend `/a2ui/stream?scenario=…`, `/actions`) behind the app's API gateway (Vite `server.proxy` in dev) | no CORS; same session as the rest of the app |
| `standalone-backend` | GenUI service origin from runtime config (`http://127.0.0.1:8712` in the test) | CORS allow-list on the service (exact app origin); token audience for that service |

Both topologies were run live: identical catalog, guards and components; only `streamUrl`/`actionUrl`
changed. Golden payloads were equal in both.

## B. CopilotKit (optional)

`@copilotkit/react-core@1.90.0` renders A2UI automatically when the CopilotKit runtime reports `a2ui`
configured. The `<CopilotKit>` provider takes `a2ui?: { theme?, catalog?, loadingComponent?,
includeSchema?, recovery? }`; the message renderer options accept
`onAction?: (action, forward) => ...` to intercept actions before they reach the agent. That
interceptor is where the allowlist and idempotency key above belong. `includeSchema` (default `true`)
sends catalog JSON schemas to the agent as context. Source: package `.d.mts`, 2026-11-23.
**DOCUMENTED BUT NOT TESTED:** no CopilotKit runtime or AG-UI agent was run, and `catalog` is typed
`any`, so whether a `@a2ui/react` catalog (above) can be passed unchanged is **UNVERIFIED**.
CopilotKit pulls a large dependency set (Radix, recharts, katex, lit, rxjs); justify it with an ADR.

## Tests (per target: web)

| Check | Tool | Status here |
|---|---|---|
| render, binding, user edit, golden payload equality (canonical form) | Vitest + Testing Library + user-event | PASS (3 goldens) |
| required field blocks submit | Vitest | PASS |
| invalid fixtures rejected with their exact `expectedError` | Vitest | PASS: 17/20 exact; the 3 `DetailPanel` fixtures (dangling-child, over-depth, self-cycle) are out of scope (component not implemented) and are asserted only as `UNKNOWN_COMPONENT` |
| size cap runs before `JSON.parse` | Vitest (spy on `JSON.parse`) | PASS |
| double click sends one request; retry after failure reuses the same `Idempotency-Key`; control disabled in flight | Vitest + mocked `fetch` | PASS (negative controls: new key per retry → fails; no in-flight block and no `disabled` → 2 requests, fails) |
| forged action name (`ACTION_NOT_ALLOWED`) / extra context key (`ACTION_PAYLOAD_INVALID`) rejected client-side | Vitest | PASS |
| partial stream renders progressively | Vitest | PASS |
| live SSE render of ActionCard/InputForm/ApprovalForm; posted body equals golden; `Idempotency-Key` header present only for side-effecting actions | Playwright, both topologies | PASS |
| `approval.approve` → 202 → ConfirmationDialog → `dialog.confirm` → 200 | Playwright, both topologies | PASS |
| user B acting on user A's resource → 403 shown in `role="alert"` | Playwright, both topologies | PASS (negative control: message removed → fails) |
| Stop aborts the stream (status `cancelled`, server logs `stream_stopped`); Reconnect sends `Last-Event-ID` and completes | Playwright, both topologies | PASS |
| version mismatch (`v0.8` frame, mocked with `page.route`) shown to the user, not rendered | Playwright, both topologies | PASS |
| zero serious/critical axe violations on rendered surfaces and the dialog | `@axe-core/playwright` | PASS ("no automated violations; manual checks required") |

Testing Library cleanup is not automatic when Vitest `globals` is off: register
`afterEach(cleanup)` in the setup file or renders leak between tests (found here). Compare payloads in
the contract's canonical form (sorted keys, timestamp normalised) and write them to the parity
directory for cross-platform checks.
