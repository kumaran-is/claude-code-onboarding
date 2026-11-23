# Generative UI in React (A2UI 1.0 target, v0.9.x compatibility)

> **Evidence (2026-11-23).** Every snippet below is an excerpt of files that compiled and ran in a
> disposable React SPA on the toolchain pinned by `/scaffold-react-app`
> (`.claude/commands/scaffold-react-app.md`; React Compiler on) against the shared `genui-contract`
> catalogs and samples: `tsc -b` exit 0, ESLint exit 0, `vite build` exit 0, Vitest 39/39, Playwright +
> `@axe-core/playwright` 24/24 in Chromium at 375 and 1280 px (both wire versions).
> Transport was mocked (`page.route`, `vi.fn`); message processing used the real packages
> (LIVE-PROTOCOL). Negative controls: legacy-binding guard removed → 1 failure; in-flight block removed
> → 1 failure; 1.0 stream on the v0.9 catalog → 3 failures; planted type error → `tsc` exit 2;
> conditional hook → ESLint exit 1; low-contrast text → axe `color-contrast` failure.
> **Not run:** a live agent or AG-UI stream, CopilotKit runtime, SSE resume and the two backend
> topologies on 0.16.1 (they were last run on 0.15.0).

The wire contract (catalog IDs, action allowlist, payload schemas, samples, versions) belongs to the
framework-neutral [`genui-contract`](../../genui-contract/SKILL.md) skill. This file covers only how a
React SPA renders it. Never put a React component name on the wire; the catalog maps names to views.

## Choose a path

| Need | Path | Packages (pin exactly) | 1.0 | v0.9.x |
|---|---|---|---|---|
| Render agent surfaces in an existing app | **A. Official renderer** (default) | `@a2ui/react@0.16.1`, `@a2ui/web_core@0.16.1`, `zod@3.25.76` | **PROVEN** (render, bindings, actions, `@accessibility`) | PROVEN |
| Copilot with the `a2ui` provider prop | **B. `@copilotkit/a2ui-renderer@1.90.0`** (bundled by `@copilotkit/react-core@1.90.0`) | as left | **PARTIAL**: renders a 1.0 stream but rejects the `@accessibility` envelope key | default (not re-run) |
| CopilotKit "Components and surfaces" (`createGenerativeUI`, `render_ui` tool) | **C. `@copilotkit/react-core/v2/generative-ui`** | `@copilotkit/react-core@1.90.0` | Experimental upstream (spec revision `cbaa5ee`); **NOT RUN** here | rejected by design |

Roles: A2UI is the UI payload; AG-UI (`@ag-ui/client@1.0.5`) is an agent event transport, needed only
if you use it; CopilotKit is an app framework. None of B or C is required to render A2UI.

**Why path A renders 1.0.** `@a2ui/react` exports only `./v0_8` and `./v0_9` subpaths, but since 0.13
its **package root** is the version-agnostic runtime (`A2uiSurface`, `createComponentImplementation`),
and since 0.16.0 it imports from `@a2ui/web_core` (not `web_core/v0_9`) so 1.0 bundles do not pull v0.9
schemas (package CHANGELOG). The protocol version comes from the catalog: build it with
`new Catalog(id, '1.0', …)` and the 1.0 schemas from `@a2ui/web_core/v1_0`. Import from the root for
both versions; `@a2ui/react/v0_9` only re-exports the root.

### Dependency findings

- `@a2ui/react` 0.16.1 was published 2026-11-23 by the `a2ui-team` npm account with **no provenance
  attestation**; the CopilotKit and AG-UI packages carry SLSA provenance. Pin exact versions and keep
  the lockfile `integrity` hashes.
- `@a2ui/*` and CopilotKit need **zod 3** (`@a2ui/react` peers `zod ^3.25.76`). Install `zod@3.25.76`
  for an A2UI-only app; with zod 4 at the app root for forms, catalog schemas must still use the zod 3
  copy the A2UI packages resolve.
- `npm audit --omit=dev`: 4 high with A2UI alone; with `@copilotkit/react-core@1.90.0` added, 11 high
  (every one traces to GHSA-mrhx-c7xc-m3w5, zod `<4.6.6`, memory exhaustion on oversized constrained
  collections) plus 6 low (KaTeX, via CopilotKit's markdown stack). The fixed zod is 4.x, outside the
  `^3` ranges that `@a2ui/web_core`, `@a2ui/react` and CopilotKit declare, so an `overrides` entry is
  not a valid fix; `npm audit fix` proposes downgrades (`@a2ui/react@0.8.0`,
  `@copilotkit/react-core@1.54.1`), which are not fixes either. The
  `@a2ui/markdown-it` DOMPurify advisory of 0.15.0 is gone: 0.16.1 resolves `dompurify@3.5.0`, so the
  old `overrides` entry is no longer needed. Mitigation for zod: cap every inbound message at
  `maxMessageBytes` **before** `JSON.parse` (`ingest` below), keep the server request limit, record the
  exception in the security review, re-run the audit on every A2UI bump.
- `@copilotkit/react-core`, `@copilotkit/core` and `@copilotkit/a2ui-renderer` 1.90.0 each pin
  `@a2ui/web_core` **0.15.0** exactly, so npm nests three 0.15.0 copies beside the app's 0.16.1
  (`@ag-ui/client`/`@ag-ui/core` 1.0.5 and zod 3.25.76 dedupe to one copy). A test that spies on both
  `MessageProcessor` classes shows the CopilotKit renderer processes messages with its **nested 0.15.0**
  copy; the app's 0.16.1 is never called. Do not mix paths A and B on one surface.
- Bundle: the sandbox app is 670 kB (189 kB gzip) with both catalogs; lazy-load the GenUI route.

## A. Official renderer

### Catalog: one view per component, built for one wire version

```tsx
import { useId } from 'react';
import { z } from 'zod'; // zod 3: the copy @a2ui/web_core resolves
import { createComponentImplementation, type ReactA2uiComponentProps, type ReactCatalogComponent } from '@a2ui/react';
import { Catalog, type ComponentApi, type InferredComponentApiSchemaType, type ResolveA2uiProps } from '@a2ui/web_core';
import * as v09 from '@a2ui/web_core/v0_9';
import * as v10 from '@a2ui/web_core/v1_0';

export type WireVersion = 'v0.9' | '1.0';

/** The wire versions differ in binding syntax: {"path"} (v0.9) vs {"@path"} (1.0). */
function schemasFor(version: WireVersion) {
  return version === 'v0.9'
    ? { Action: v09.ActionSchema, DynamicString: v09.DynamicStringSchema, DataBinding: v09.DataBindingSchema, CheckRule: v09.CheckRuleSchema, accessibility: v09.AccessibilityAttributesSchema }
    : { Action: v10.ActionSchema, DynamicString: v10.DynamicStringSchema, DataBinding: v10.DataBindingSchema, CheckRule: v10.CheckRuleSchema, accessibility: v10.AccessibilityAttributesSchema };
}

// In buildApis(version): actions must use the library's ActionSchema, or the binder does not
// turn them into callables. Allowlists are enforced by the ingest guard, not by these schemas.
ApprovalRequest: {
  name: 'ApprovalRequest',
  schema: z.object({
    accessibility: s.accessibility.optional(), // v0.9 key; 1.0 sends the @accessibility envelope key
    title: s.DynamicString,
    summary: s.DynamicString,
    requestId: ID,
    riskLevel: z.enum(['low', 'medium', 'high']),
    comment: s.DataBinding.optional(),
    approveAction: s.Action,
    rejectAction: s.Action,
  }),
},

// Named PascalCase views: eslint-plugin-react-hooks does not check hooks inside an anonymous
// callback passed to createComponentImplementation (found by a negative control).
type Apis = ReturnType<typeof buildApis>;
type ViewProps<A extends ComponentApi> = ReactA2uiComponentProps<ResolveA2uiProps<InferredComponentApiSchemaType<A>>>;

function ApprovalRequestView({ props }: ViewProps<Apis['ApprovalRequest']>) {
  const headingId = useId();
  const commentId = useId();
  const busy = usePendingActions();
  return (
    <section className="genui-approval" role="form" aria-labelledby={headingId}>
      <h3 id={headingId}>{text(props.title)}</h3>
      <p>{text(props.summary)}</p>
      {/* Risk as text, never colour alone. */}
      <p><strong>Risk:</strong> {props.riskLevel}</p>
      {props.comment !== undefined ? (
        <div className="genui-field">
          <label htmlFor={commentId}>Comment</label>
          <textarea id={commentId} maxLength={1000} value={text(props.comment)}
            onChange={(e) => props.setComment(e.target.value)} />
        </div>
      ) : null}
      <button type="button" disabled={busy} onClick={() => void props.approveAction()}>Approve</button>
      <button type="button" disabled={busy} onClick={() => void props.rejectAction()}>Reject</button>
    </section>
  );
}

export function buildCatalog(version: WireVersion): Catalog<ReactCatalogComponent> {
  const apis = buildApis(version);
  const ActionCard = createComponentImplementation(apis.ActionCard, ActionCardView);
  const EditableForm = createComponentImplementation(apis.EditableForm, EditableFormView);
  const ApprovalRequest = createComponentImplementation(apis.ApprovalRequest, ApprovalRequestView);
  // The shared catalog declares required, length, email and numeric for field checks.
  const functions = version === 'v0.9'
    ? [v09.RequiredImplementation, v09.LengthImplementation, v09.EmailImplementation, v09.NumericImplementation]
    : [...v10.V10_VALIDATION_FUNCTION_IMPLEMENTATIONS].filter((f) => ['required', 'length', 'email', 'numeric'].includes(f.name));
  return new Catalog<ReactCatalogComponent>(CATALOG_IDS[version], version, [ActionCard, EditableForm, ApprovalRequest], functions);
}
```

What the 0.16 binder hands a view (verified at runtime):

| Schema | View receives |
|---|---|
| `DynamicString` (literal, binding or call) | the current value, plus a `setX` setter for two-way binding |
| `ActionSchema` | `() => Promise<void>` that resolves the event context and dispatches |
| a custom zod object shaped like an action | the raw object, **not** callable (`TypeError: … is not a function`) |
| a binding nested in an array item (`fields[].value`) | the value and a `setValue` setter on that item (`field.setValue(…)`) |

Catalog functions referenced by `checks` must be in the catalog, or the processor rejects the surface
with `Unrecognized function 'required'`. Do not use the deprecated `render` / `context` API
(`createBinderlessComponentImplementation` with `context`, deprecated in 0.16.0); use resolved props,
setters and `useA2uiSurface()`.

Mapping (all three rendered and tested): `ActionCard` → `<article>` with one button per action;
`EditableForm` → `<form>` with one labelled input per field, native `required`/`maxLength`, integer
fields write numbers; `ApprovalRequest` → `role="form"` section with a labelled comment and
Approve/Reject buttons. 1.0 `@accessibility.label` lands on the `<a2ui-react-*>` host as `aria-label`
with `role="group"`.

### Guards around the renderer

`STRICT_VALIDATION` checks props, references, cycles and depth. It does **not** cover the contract's
size, string, version, catalog or action rules, and web_core 0.16.1 **accepts a v0.9 `{"path"}`
binding inside a 1.0 message** (the shared `legacy-v0_9-binding` sample rendered until the guard
below was added). An app-owned `ingest` runs first; the server re-validates and authorises every
action regardless.

Unknown components (shared `unknown-component` samples fed straight to the processor, no `ingest`):
`STRICT_VALIDATION` returns a processor error naming the type, which the host shows as an alert. With
`RELAXED_VALIDATION` (`allowUnknownElements: true`) both v0.9 and 1.0 are **silent**: no error, no
console output, an empty surface. Keep `STRICT_VALIDATION`, and use `processMessagesWithErrors`, not
`processMessages`, so the error reaches the UI.

```ts
/** 1.0 bindings are {"@path"}; web_core 0.16.1 still accepts a v0.9 {"path"} binding in a 1.0 message. */
function rejectLegacyBindings(value: unknown): void {
  if (Array.isArray(value)) return value.forEach(rejectLegacyBindings);
  if (value === null || typeof value !== 'object') return;
  const obj = value as Record<string, unknown>;
  if ('path' in obj && !('componentId' in obj)) throw new ContractViolation('SCHEMA_INVALID', 'v0.9 {"path"} binding in a 1.0 message');
  if ('call' in obj && !('@call' in obj)) throw new ContractViolation('SCHEMA_INVALID', 'v0.9 {"call"} in a 1.0 message');
  Object.values(obj).forEach(rejectLegacyBindings);
}

export function ingest(raw: string, expected: WireVersion, stream: StreamState): Record<string, unknown> {
  // Size cap on the raw bytes, before JSON.parse.
  if (new TextEncoder().encode(raw).byteLength > LIMITS.maxMessageBytes) {
    throw new ContractViolation('MESSAGE_TOO_LARGE', 'message exceeds maxMessageBytes');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ContractViolation('MALFORMED_MESSAGE', 'message is not JSON');
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new ContractViolation('MALFORMED_MESSAGE', 'message is not an object');
  }
  const msg = parsed as Record<string, unknown>;
  if (typeof msg.version !== 'string') throw new ContractViolation('MALFORMED_MESSAGE', 'message has no version');
  if (stream.version !== undefined && msg.version !== stream.version) {
    throw new ContractViolation('MIXED_VERSIONS', `stream is ${stream.version}, message is ${msg.version}`);
  }
  if (!ACCEPTED[expected].includes(msg.version)) {
    throw new ContractViolation('UNSUPPORTED_VERSION', `unsupported version ${msg.version}`);
  }
  const bodies = BODIES.filter((b) => b in msg);
  if (bodies.length !== 1 || Object.keys(msg).length !== 2) {
    throw new ContractViolation('MALFORMED_MESSAGE', 'need exactly one supported message body');
  }
  scanStrings(msg); // UNSAFE_CONTENT (javascript:, <script, ...) and STRING_TOO_LONG
  const kind = bodies[0]!;
  const body = msg[kind] as Record<string, unknown>;
  const surfaceId = String(body.surfaceId);
  if (kind === 'createSurface') {
    if (body.catalogId !== CATALOG_IDS[expected]) throw new ContractViolation('UNSUPPORTED_CATALOG', 'unknown catalogId');
    if ('components' in body) checkComponents(body.components, msg.version); // 1.0 single-message init
  } else if (!stream.surfaces.has(surfaceId)) {
    throw new ContractViolation('SURFACE_NOT_FOUND', 'surface not created');
  }
  if (kind === 'updateComponents') checkComponents(body.components, msg.version);
  stream.version ??= msg.version;
  return msg;
}
```

`ACCEPTED` is `{ 'v0.9': ['v0.9', 'v0.9.1'], '1.0': ['1.0'] }`; `checkComponents` throws
`UNKNOWN_COMPONENT` for a name outside the catalog, `FUNCTION_ACTION_FORBIDDEN` for a `functionCall`
action and `ACTION_NOT_ALLOWED` for an event name outside that component's allowlist. The guard
requires `catalogId` on `createSurface` even though 1.0 makes it optional. Outbound, `toOutboundAction`
checks the allowlist and the strict payload schema of each action (`ACTION_PAYLOAD_INVALID`) and adds
an `Idempotency-Key` only for side-effecting actions, beside the message and never inside `context`.

Rules: no `dangerouslySetInnerHTML`, no model-supplied URLs in `href`/`src` (the shared catalog has
none); the model never decides authorisation; high-risk actions (`approval.*`) fire only from an
explicit user click; tokens stay in memory or an HttpOnly cookie, never in the bundle, URL or storage.

### Host: processor, feed, actions

One `MessageProcessor` per session with `STRICT_VALIDATION`; feed each message through `ingest` and
`processMessagesWithErrors` so a rejection becomes an error state, never a blank. The first violation
poisons the stream (later messages are ignored, the first error stays visible) until the user resets.
Actions come from `processor.model.onAction`, subscribed in an effect (passing a ref into the
constructor fails the React Compiler lint rule `react-hooks/refs`).

```tsx
const [processor, setProcessor] = useState(() => createProcessor(version));
useEffect(() => () => processor.dispose(), [processor]);

useEffect(() => {
  const onAction = (a: ActionPayload) => {
    if (inFlight.current) return; // double click while in flight
    let outbound: OutboundAction;
    try {
      outbound = toOutboundAction(a, version);
    } catch (e) {
      setError(describe(e));
      return;
    }
    void transmit(outbound); // on failure keeps `outbound`, so Retry resends the same Idempotency-Key
  };
  const sub = processor.model.onAction.subscribe(onAction);
  return () => sub.unsubscribe();
}, [processor, transmit, version]);

const feed = useCallback((raw: string) => {
  // After a violation the stream is poisoned: ignore it until reset, keep the first error.
  if (streamRef.current.failed) return;
  try {
    const msg = ingest(raw, version, streamRef.current);
    const errors = processor.processMessagesWithErrors(msg);
    if (errors.length > 0) {
      fail(`SCHEMA_INVALID: ${errors.map((x) => `${x.error.code} ${x.error.message}`).join('; ')}`);
      return;
    }
    const created = msg.createSurface as { surfaceId?: unknown } | undefined;
    if (created) streamRef.current.surfaces.add(String(created.surfaceId));
  } catch (e) {
    fail(describe(e));
  }
}, [fail, processor, version]);

function createProcessor(version: WireVersion) {
  // Actions are consumed through processor.model.onAction (subscribed in an effect).
  return new MessageProcessor<ReactCatalogComponent>([buildCatalog(version)], undefined, {
    validationConfig: STRICT_VALIDATION,
  });
}
```

Render surfaces from `processor.getSurfaces()` through `useSyncExternalStore` subscribed to
`onSurfaceCreated`/`onSurfaceDeleted`, one `<A2uiSurface surface={surface} />` each, inside a context
that sets `disabled` on every control while an action is in flight. Show `role="status"` for progress
and `role="alert"` for errors (403 → "You are not allowed to do that."), with **Retry** (same
idempotency key) after a failed action and **Clear and start over** (new processor, empty stream state)
after a bad stream.

Stream transport: an effect owns it. The sandbox read NDJSON over `fetch` with an `AbortController`
(one message per line). For SSE use `fetch` too (not `EventSource`) so it can send `Authorization`,
abort and resume with `Last-Event-ID`; that SSE path, the 202 confirmation-dialog flow and both
[backend topologies](../../genui-contract/reference/backend-topologies.md) were run live on 0.15.0 and
**not re-run on 0.16.1**. Late `updateDataModel` messages overwrite what the user typed: keep inputs
disabled until the stream reports done, or have the agent send the data model first.

## B. CopilotKit `a2ui` renderer

`@copilotkit/a2ui-renderer` works without a CopilotKit runtime: `A2UIProvider` (`catalog`, `onAction`,
`theme`), `useA2UI().processMessages(messages)` and `<A2UIRenderer surfaceId>`. For 1.0, build the
catalog with `createCatalog(definitions, renderers, { catalogId, protocolVersion: '1.0' })` and the
`*SchemaV1` exports (`DynamicStringSchemaV1`, `DataBindingSchemaV1`, `ActionSchemaV1`, …); omitting
`protocolVersion` keeps v0.9 (docs.copilotkit.ai `generative-ui/components/from-a2ui`). In the app,
pass the same catalog to `<CopilotKit a2ui={{ catalog }}>` from `@copilotkit/react-core/v2`
(docs.copilotkit.ai `generative-ui/a2ui`; provider not run here).

Tested (LIVE-PROTOCOL, no runtime): the shared 1.0 `approval-request` stream is **rejected** —
`A2uiValidationError: Unrecognized reserved protocol directive '@accessibility' in v1.0 dynamic
object` (logged with `console.warn`, nothing rendered). The same stream without `@accessibility`
renders and forwards `approval.approve` to `onAction`; a v0.9 stream does not render on the 1.0
catalog. Cause: the renderer pins `@a2ui/web_core` 0.15.0. Until CopilotKit ships a renderer on
web_core ≥ 0.16, either keep this path on v0.9 or have the agent omit `@accessibility` (and lose the
accessible name it carries). An unknown component (shared 1.0 `unknown-component` sample) renders an
inline red `Unknown component: HtmlBlock` placeholder, echoing the agent-supplied type name, with no
console output and no error to the app; guard inbound messages yourself before `processMessages`.
`onAction` is where the allowlist, payload check and idempotency key belong;
`A2UIProviderProps.catalog` is typed `any`, so the compiler does not catch a wrong catalog.

## C. CopilotKit components and surfaces (experimental)

A separate A2UI 1.0 engine: `createGenerativeUI({ id, components })` with zod props and `slots`,
`<CopilotKitProvider runtimeUrl generativeUI={{ ui }}>`, a runtime-injected `render_ui` tool or a
markdown transport, the 69-component `standardUI`, and named page areas. Upstream marks it
experimental on 1.0 spec revision `cbaa5ee`; its support matrix rejects v0.9 operations,
`callRendererFunction` and `callAgentFunction`, and does not enforce `allowedParents`/`allowedChildren`.
**NOT RUN** here (needs a CopilotKit runtime and a model). Adopt it only with an ADR; CopilotKit pulls
a large dependency set.

## Tests (per target: web)

| Check | Tool | Status |
|---|---|---|
| ActionCard, EditableForm, ApprovalRequest render from the shared valid samples, v0.9 and 1.0 | Vitest + Testing Library | PASS (6) |
| two-way binding writes the data model (shared state); approve resolves the bound comment | Vitest | PASS |
| `form.submit`: the object binding `values: {"@path": "/profile"}` (v0.9 `{"path"}`) resolves to the edited object; `approval.reject` sends the bound comment as `reason`; empty reason → `ACTION_PAYLOAD_INVALID`, nothing sent | Vitest + Playwright, both versions | PASS (negative control: pre-fix samples → 4 Vitest + 8 Playwright failures) |
| 12 shared invalid samples rejected with their exact `expectedError`; nothing unsafe in the DOM | Vitest | PASS (12) |
| size cap before `JSON.parse` (spy); v0.8 → `UNSUPPORTED_VERSION`; 1.0 stream on the v0.9 host rejected; forged action name rejected | Vitest | PASS |
| failed action → alert → Retry with the same `Idempotency-Key`; double click sends one request; controls disabled in flight | Vitest | PASS (negative control: in-flight block removed → fails) |
| bad stream → Clear and start over → new stream renders | Vitest | PASS |
| unknown component without the guard: STRICT returns an error; RELAXED is silent (v0.9 and 1.0) | Vitest | PASS (4) |
| CopilotKit renderer: nested web_core 0.15.0 processes; 1.0 `@accessibility` rejected; stripped stream renders and dispatches; v0.9 stream not rendered; unknown component → inline placeholder | Vitest | PASS (5; negative control: nested-copy assertion inverted → fails) |
| approve, submit and reject post the resolved payload with an `Idempotency-Key` header; 403 shown in `role="alert"`; unknown component shown as an error | Playwright, Chromium 375 + 1280 px, both versions | PASS (24) |
| zero axe violations (WCAG 2.0/2.1/2.2 A+AA tags) on all three components | `@axe-core/playwright` | PASS ("no automated violations; manual checks required"; negative control: low contrast → fails) |

Register `afterEach(cleanup)` in the Vitest setup file when `globals` is off, or renders leak between
tests. Hooks inside `createComponentImplementation` callbacks are invisible to `rules-of-hooks`; keep
views as named components.
