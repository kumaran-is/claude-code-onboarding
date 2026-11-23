# Canonical GenUI catalog in Angular (A2UI v0.9; Angular 22 + `@a2ui/angular@0.16.0`)

How the eight canonical catalog IDs from the `genui-contract` skill (`../../genui-contract/reference/catalog-contract.md`) become Angular components in one A2UI v0.9 custom catalog, plus the action gateway, ingest guard, topology adapters and AG-UI adapter around it.

**Evidence (Angular 22, current):** [canonical-catalog-angular22-components.md](canonical-catalog-angular22-components.md) (components, action dispatch) and [canonical-catalog-angular22-session.md](canonical-catalog-angular22-session.md) (stream session, providers, lazy routes) were compiled and tested on Angular 22.3.0 + `@a2ui/angular@0.16.0`.

**Evidence (historical; not re-run on 22.3):** the code blocks in this file are excerpts from an earlier sandbox app (Angular 21.2.26, `@a2ui/angular@0.14.0`, `@a2ui/web_core@0.15.0`, zod 3.25.76, TypeScript 5.9.3 strict + strictTemplates), checked on 2026-11-23 against the contract fixtures and the reference backend in both topologies:

| Check | Result | Negative control |
|---|---|---|
| `npx tsc -p tsconfig.app.json --noEmit` | PASS (exit 0) | — |
| `npx ng build` | PASS (exit 0) | — |
| `npx ng test --no-watch` (Vitest, 33 tests: pre-parse byte cap, one request and one Idempotency-Key per user intent (double click, retry), every valid fixture accepted, every invalid fixture rejected with its `expectedError`, golden action payloads, 202 confirmation, 403) | PASS (exit 0) | Idempotency-Key header removed → exit 1, 3 failed. Pre-parse cap off → exit 1, 1 failed. In-flight guard off + fresh key per call → exit 1, 2 failed. `GENUI_STRICT` off → missing-root and SDK unknown-component tests fail. Unsafe-string scan off → html-script and javascript-url fail |
| `npx playwright test` + `@axe-core/playwright` (18 tests: render, double click sends one request, binding, edit, golden payloads, 403, stop/resume with `Last-Event-ID`, invalid fixtures shown to the user, AG-UI run, zero serious/critical axe violations) | PASS (exit 0) | Unsafe-string scan off → html-script e2e fails (exit 1). In-flight guard and `[disabled]` off → double click sends 2 requests (exit 1) |

## Catalog mapping

Wire IDs are the canonical names. Angular class names never go on the wire.

| Canonical ID | Angular component | Status |
|---|---|---|
| `ActionCard` | `ActionCardComponent` | DOCUMENTED AND TESTED |
| `InputForm` | `InputFormComponent` (two-way bound fields) | DOCUMENTED AND TESTED |
| `ApprovalForm` | `ApprovalFormComponent` (fixed Approve/Reject labels) | DOCUMENTED AND TESTED |
| `ConfirmationDialog` | `ConfirmationDialogComponent` (native `<dialog>`, server-authored) | DOCUMENTED AND TESTED |
| `DataSummaryTable`, `SelectionList`, `DetailPanel`, `StatusIndicator` | Same pattern: one `ComponentApi` + one `CatalogComponent` each | NOT RUN in the sandbox. Build them before you accept fixtures that use them; until then the guard rejects them with `UNKNOWN_COMPONENT` |

## SDK facts the catalog relies on (SOURCE-PROVEN, web_core 0.15.0; Angular 22 notes in the last section)

- `AngularCatalog(id, '0.9', components, functions)` + `createComponentImplementation(api, componentClass)` is the supported way to register components. `BasicCatalogBase({ extraComponents, functions })` is `@deprecated`.
- Catalog functions are separate from components. The basic functions are not inherited: a fixture that calls `required` fails with `Unrecognized function 'required'` unless you register it (filter `BASIC_FUNCTIONS` from `@a2ui/web_core/v0_9/basic_catalog`).
- The generic binder reads each zod prop's `.describe('REF:#/$defs/<Name>')`. `DynamicString` (and the other `Dynamic*` refs) on a scalar becomes a reactive `BoundProperty` (`value()`, `raw`, `onUpdate`). `Action` becomes a ready-to-call closure that dispatches through the surface. A `DataBinding` described on an object stays a static raw object.
- Only top-level props get `onUpdate`. Bindings nested in arrays (form fields) are unwrapped to plain values, so the component writes with `surface.dataModel.set(path, value)` (see `bindDataPaths` below).
- `STRICT_VALIDATION` rejects unknown components, orphans, dangling references, missing root, cycles and over-depth trees. It does **not** validate component props, and `targetVersion` only checks messages that carry a version. An app-level ingest guard is therefore required (see below).

## Component API and catalog

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
import { z } from 'zod';
import { DataBindingSchema, FunctionCallSchema } from '@a2ui/web_core/v0_9';

/** Canonical contract constants (mirrors canonical-catalog.json `x-genui`). */

// The SDK binder (web_core 0.15.0 generic-binder) reads the `REF:#/$defs/<Name>` description of
// each prop: `DynamicString` -> reactive resolved value, `Action` -> ready-to-call closure.
const dynamicString = (max: number) =>
  z.union([z.string().max(max), DataBindingSchema, FunctionCallSchema]).describe('REF:#/$defs/DynamicString');

/** A server event only: v0.9 also allows `functionCall` actions, this catalog forbids them. */
const serverEvent = <const N extends [CanonicalActionName, ...CanonicalActionName[]]>(names: N) =>
  z
    .object({
      event: z
        .object({
          name: z.enum(names),
          context: z
            .record(z.string().regex(KEY_PATTERN), z.union([z.string(), z.number().int(), z.boolean(), DataBindingSchema]))
            .refine((context) => Object.keys(context).length <= 20, 'at most 20 context entries')
            .optional(),
        })
        .strict(),
    })
    .strict()
    .describe('REF:#/$defs/Action');

/** Two-way bound field: read from and written to this data-model path. */
const dataBinding = DataBindingSchema;

```

Each component API is `{ name: '<CanonicalId>', schema: z.object({...}).strict() }`, built from these helpers and the contract's per-component JSON Schema. The catalog registration:

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
import { EnvironmentProviders, InjectionToken, inject, makeEnvironmentProviders } from '@angular/core';
import { AngularCatalog, createComponentImplementation, provideA2Ui, provideMarkdownRenderer } from '@a2ui/angular';
import { STRICT_VALIDATION } from '@a2ui/web_core/v0_9';
import { BASIC_FUNCTIONS } from '@a2ui/web_core/v0_9/basic_catalog';
import { ActionCardApi, ApprovalFormApi, CANONICAL_CATALOG_ID, ConfirmationDialogApi, InputFormApi } from './canonical-catalog';
import { ConfirmationDialogComponent } from './components/confirmation-dialog.component';
import { ActionCardComponent } from './components/action-card.component';
import { ApprovalFormComponent } from './components/approval-form.component';
import { InputFormComponent } from './components/input-form.component';
import { ActionGateway } from './action-gateway';
import { GENUI_BACKEND, type GenuiBackend } from './backend';

/** The canonical catalog declares only these four client-side check functions. */
const CATALOG_FUNCTIONS = BASIC_FUNCTIONS.filter((fn) => ['required', 'length', 'email', 'numeric'].includes(fn.name));

/** Canonical catalog ids -> Angular components, registered as one A2UI v0.9 catalog. */
export function createCanonicalCatalog(): AngularCatalog {
  return new AngularCatalog(CANONICAL_CATALOG_ID, '0.9', [
    createComponentImplementation(ActionCardApi, ActionCardComponent),
    createComponentImplementation(ApprovalFormApi, ApprovalFormComponent),
    createComponentImplementation(InputFormApi, InputFormComponent),
    createComponentImplementation(ConfirmationDialogApi, ConfirmationDialogComponent),
  ], CATALOG_FUNCTIONS);
}

/** Turning this off is a test-only negative control; production always runs strict. */
export const GENUI_STRICT = new InjectionToken<boolean>('GENUI_STRICT', { factory: () => true });

export function provideGenui(backend: GenuiBackend): EnvironmentProviders {
  return makeEnvironmentProviders([
    { provide: GENUI_BACKEND, useValue: backend },
    provideA2Ui(() => {
      const gateway = inject(ActionGateway);
      return {
        catalogs: [createCanonicalCatalog()],
        processorOptions: inject(GENUI_STRICT) ? { validationConfig: { ...STRICT_VALIDATION, targetVersion: 'v0.9' } } : {},
        actionHandler: (action) => gateway.handle(action),
      };
    }),
    // The canonical catalog renders model text as plain text only; no markdown/HTML sink is used.
    provideMarkdownRenderer(async (text: string) => text.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`)),
  ]);
}
```

## A catalog component

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
import { Component, computed } from '@angular/core';
import { CatalogComponent } from '@a2ui/angular';
import { ActionCardApi } from '../canonical-catalog';

interface CardAction {
  readonly label: string;
  readonly variant: 'primary' | 'secondary';
  readonly run: () => Promise<void>;
}

/** Canonical `ActionCard`: title, optional subtitle/body, 1-3 server-event buttons. Text only, never HTML. */
@Component({
  selector: 'app-action-card',
  template: `
    <article class="card" [attr.aria-labelledby]="surfaceId() + '-' + componentId() + '-title'">
      <h3 [id]="surfaceId() + '-' + componentId() + '-title'">{{ title() }}</h3>
      @if (subtitle()) { <p class="subtitle">{{ subtitle() }}</p> }
      @if (body()) { <p>{{ body() }}</p> }
      @if (actions().length) {
        <div class="actions">
          @for (action of actions(); track $index) {
            <button type="button" [class]="action.variant" (click)="action.run()">{{ action.label }}</button>
          }
        </div>
      }
    </article>
  `,
  styles: `
    .card { border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; max-width: 32rem; }
    h3 { margin: 0 0 4px; }
    .subtitle { color: var(--color-muted); margin: 0 0 8px; }
    .actions { display: flex; gap: 8px; }
    button { min-height: 44px; min-width: 44px; padding: 0 16px; border-radius: 6px; border: 1px solid var(--color-primary); cursor: pointer; }
    .primary { background: var(--color-primary); color: var(--color-primary-content); }
    .secondary { background: var(--color-base-100); color: var(--color-primary); }
  `,
})
export class ActionCardComponent extends CatalogComponent<typeof ActionCardApi> {
  protected readonly title = computed(() => this.props().title.value());
  protected readonly subtitle = computed(() => this.props().subtitle?.value());
  protected readonly body = computed(() => this.props().body?.value());

  /** The binder delivers each nested `action` as a ready-to-call closure that dispatches through the surface. */
  protected readonly actions = computed<CardAction[]>(() =>
    (this.props().actions?.value() ?? []).flatMap((item) => {
      const run: unknown = item.action;
      return typeof run === 'function'
        ? [{ label: item.label, variant: item.variant ?? 'secondary', run: run as () => Promise<void> }]
        : [];
    }),
  );
}
```

Two-way binding for nested fields (InputForm, ApprovalForm comment):

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
import { DestroyRef, Signal, effect, inject, signal } from '@angular/core';
import { A2uiRendererService } from '@a2ui/angular';

/**
 * Two-way binding for `DataBinding` props nested inside arrays/objects. The SDK binder only
 * exposes a writer (`onUpdate`) for top-level props, so nested bindings read and write the
 * surface data model directly by path.
 */
export function bindDataPaths(surfaceId: Signal<string>, paths: Signal<readonly string[]>) {
  const renderer = inject(A2uiRendererService);
  const values = signal<Readonly<Record<string, unknown>>>({});

  effect((onCleanup) => {
    const surface = renderer.surfaceGroup.getSurface(surfaceId());
    if (!surface) return;
    const subscriptions = paths().map((path) => {
      values.update((current) => ({ ...current, [path]: surface.dataModel.get(path) }));
      return surface.dataModel.subscribe(path, (value) => values.update((current) => ({ ...current, [path]: value })));
    });
    onCleanup(() => subscriptions.forEach((subscription) => subscription.unsubscribe()));
  });
  inject(DestroyRef).onDestroy(() => values.set({}));

  return {
    values: values.asReadonly(),
    write(path: string, value: unknown): void {
      renderer.surfaceGroup.getSurface(surfaceId())?.dataModel.set(path, value);
    },
  };
}

export function rawPath(raw: unknown): string | undefined {
  return raw !== null && typeof raw === 'object' && 'path' in raw && typeof raw.path === 'string' ? raw.path : undefined;
}
```

Accessibility rules the e2e axe run enforces: DOM ids are scoped as `surfaceId + '-' + componentId` (every surface has a `root`; unscoped ids collided and broke the dialog's accessible name in testing). Labels are bound with `for`/`id`. Validation errors use `role="alert"`. Targets are at least 44px. Colors come from CSS custom properties, never literals.

## Action gateway: allowlist, payload schema, idempotency, server authz

Every `actionHandler` call goes through one gateway. Unknown action names and invalid payloads never leave the browser. Side-effecting actions get an `Idempotency-Key` **header** (never a context field), created once per user intent: a duplicate click while the request is in flight is dropped, a retry after a failure reuses the key, and the key is discarded once the server accepts the action. The SDK dispatches actions without extra arguments, so the intent is identified by its canonical message (without the timestamp). Catalog components bind every action control to `[disabled]="busy()"` (`busy = inject(ActionGateway).busy`). The server re-authorizes from the session and holds every `requiresHumanApproval` action. It answers `202 { status: "confirmation_required", messages }` with a server-authored `ConfirmationDialog` surface, which the app ingests through the same guard.

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
/**
 * Single exit for every A2UI action: allowlist -> payload schema -> idempotency key -> POST.
 * The server re-authorizes from the session (nothing in `context` grants permission) and holds
 * every `requiresHumanApproval` action, answering 202 with a server-authored ConfirmationDialog.
 */
@Injectable({ providedIn: 'root' })
export class ActionGateway {
  private readonly backend = inject(GENUI_BACKEND);
  private readonly auth = inject(AuthSession);
  private readonly errorHandler = inject(ErrorHandler);

  readonly status = signal<ActionStatus>({ state: 'idle' });
  /** Server-authored follow-up messages (e.g. the confirmation dialog) for the session to ingest. */
  readonly followUp = signal<readonly unknown[]>([]);
  /** Catalog components bind `[disabled]` to this, so a second click cannot start a second request. */
  readonly busy = computed(() => this.status().state === 'sending');

  /**
   * One Idempotency-Key per user intent. The SDK dispatches actions without extra arguments and the
   * contract forbids the key in `context`, so the intent is identified by its canonical message
   * (name, surface, source component, resolved context). The key is created on the first send,
   * reused for a duplicate or a retry of the same intent, and dropped once the server accepted it.
   */
  private readonly intentKeys = new Map<string, string>();
  private readonly inFlight = new Set<string>();

  async handle(payload: ActionPayload): Promise<void> {
    const name = payload.name;
    let intent: string | undefined;
    try {
      const message = this.toMessage(payload);
      const policy = ACTION_POLICIES[message.action.name];
      intent = intentOf(message);
      if (this.inFlight.has(intent)) return; // double click: the first request is still running
      this.inFlight.add(intent);
      this.status.set({ state: 'sending', name });
      const headers = this.auth.headers({ 'Content-Type': 'application/json' });
      if (policy.requiresIdempotencyKey) {
        const key = this.intentKeys.get(intent) ?? crypto.randomUUID();
        this.intentKeys.set(intent, key); // kept after a failure, so a retry of this intent reuses it
        headers['Idempotency-Key'] = key;
      }
      const response = await fetch(`${this.backend.baseUrl}/actions`, { method: 'POST', headers, body: JSON.stringify(message) });
      if (!response.ok) throw await backendError(response);
      this.intentKeys.delete(intent); // accepted: a later identical click is a new intent
      const result: unknown = await response.json();
      if (response.status === 202 && isConfirmationRequired(result)) {
        this.status.set({ state: 'confirm', name });
        this.followUp.set(result.messages);
        return;
      }
      this.status.set({ state: 'done', name, replayed: response.headers.get('Idempotent-Replayed') === 'true' });
    } catch (error) {
      this.errorHandler.handleError(error);
      const status = error instanceof BackendError ? error.status : 0;
      const code = error instanceof BackendError ? error.code : error instanceof ActionRejectedError ? error.code : 'NETWORK_ERROR';
      const userMessage = error instanceof ActionRejectedError
        ? 'This action is not allowed here.'
        : USER_MESSAGES[status] ?? 'The action could not be sent. Try again.';
      this.status.set({ state: 'error', name, code, userMessage });
    } finally {
      if (intent !== undefined) this.inFlight.delete(intent);
    }
  }

  /** Allowlist + payload validation; strips SDK-only fields so every client emits the same bytes. */
  toMessage(payload: ActionPayload): ActionMessage {
    if (!isCanonicalAction(payload.name)) throw new ActionRejectedError('ACTION_NOT_ALLOWED', payload.name);
    const parsed = ACTION_POLICIES[payload.name].payload.safeParse(payload.context);
    if (!parsed.success) throw new ActionRejectedError('ACTION_PAYLOAD_INVALID', parsed.error.message);
    return {
      version: PROTOCOL_VERSION,
      action: {
        name: payload.name,
        surfaceId: payload.surfaceId,
        sourceComponentId: payload.sourceComponentId,
        timestamp: payload.timestamp,
        context: parsed.data,
      },
    };
  }

}

/** Canonical identity of a user intent: the message without its timestamp, keys sorted. */
function intentOf(message: ActionMessage): string {
  const sort = (node: unknown): unknown =>
    Array.isArray(node) ? node.map(sort)
      : node !== null && typeof node === 'object'
        ? Object.fromEntries(Object.keys(node).sort().map((key) => [key, sort((node as Record<string, unknown>)[key])]))
        : node;
  const { timestamp: _timestamp, ...identity } = message.action;
  return JSON.stringify(sort(identity));
}

function isConfirmationRequired(body: unknown): body is { status: 'confirmation_required'; messages: unknown[] } {
  return body !== null && typeof body === 'object' && 'status' in body && body.status === 'confirmation_required'
    && 'messages' in body && Array.isArray(body.messages);
}

export class ActionRejectedError extends Error {
  constructor(readonly code: string, detail: string) {
    super(`${code}: ${detail}`);
    this.name = 'ActionRejectedError';
  }
}
```

`ACTION_POLICIES` is generated from the contract's action table (name → sideEffect, risk, requiresIdempotencyKey, requiresHumanApproval, zod payload). Strip the SDK-only fields (for example `catalogId`) so every client emits byte-identical canonical payloads; the golden comparison sorts keys and fixes `timestamp` to `1970-01-01T00:00:00.000Z`.

**Human approval.** Approve/Reject labels are app-authored. The confirmation the user sees comes from the server, which also owns its `dialogId`. A client-side confirm prompt alone is not an approval control, because the server cannot tell it happened.

## Ingest guard (runs before `processMessages`)

Order of checks, each mapped to a contract error code:

0. Raw frame over `maxMessageBytes` → `MESSAGE_TOO_LARGE`, checked on the string **before** `JSON.parse` and before any zod parse (zod 3.25.76 carries an open HIGH advisory). A Vitest case spies on `JSON.parse` to prove it is never called; disabling the cap makes it fail
1. Not valid JSON → `MALFORMED_MESSAGE`
2. Parsed value is not an object, not exactly one body key, or no `version` → `MALFORMED_MESSAGE`
3. `version !== 'v0.9'` → `UNSUPPORTED_VERSION` (closes the SDK's unversioned-message gap)
4. Any string over `maxStringLength` or matching a forbidden pattern (`javascript:`, `vbscript:`, `data:text/html`, `<script`) → `UNSAFE_CONTENT`
5. `createSurface.catalogId` other than the canonical ID → `UNSUPPORTED_CATALOG`
6. Message for a surface that was never created → `SURFACE_NOT_FOUND`
7. `updateComponents`: unknown component → `UNKNOWN_COMPONENT`; a `functionCall` action → `FUNCTION_ACTION_FORBIDDEN`; an action name not allowed on that component → `ACTION_NOT_ALLOWED`; zod `safeParse` failure → `SCHEMA_INVALID`
8. Then `renderer.processMessages([message])` under `STRICT_VALIDATION`; SDK errors map to `MISSING_ROOT`, `CYCLE`, `MAX_DEPTH_EXCEEDED`, `DANGLING_REFERENCE`

A rejected message is logged through `ErrorHandler`, listed in a visible `role="alert"` region with its code, and the last good surface stays.

## Topology adapters (`shared-backend` / `standalone-backend`)

Only the adapter edge differs between topologies; the catalog, guard and gateway are identical. One build serves both by reading public origins from a runtime file (no secrets):

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
export async function loadBackend(topology: Topology): Promise<GenuiBackend> {
  const response = await fetch('/genui-config.json', { cache: 'no-store' });
  if (!response.ok) return GENUI_BACKENDS[topology];
  const config: unknown = await response.json();
  const urls = config !== null && typeof config === 'object' ? (config as Record<string, unknown>) : {};
  const baseUrl = urls[topology];
  if (typeof baseUrl !== 'string' || !/^https?:\/\/[^/]+$/.test(baseUrl)) {
    throw new Error(`genui-config.json: ${topology} must be an origin URL`);
  }
  return { topology, baseUrl };
}
```

```json
{ "shared-backend": "https://genui.example.com", "standalone-backend": "https://angular-bff.example.com" }
```

The stream client reads the topology the server reports (`X-GenUI-Topology`) and shows it. Streaming: `fetch` with an `Authorization` header (not `EventSource`, which cannot send one), parse only complete SSE frames (`\n\n`/`\r\n\r\n`; a truncated tail is `INCOMPLETE_FRAME`), and resume with `Last-Event-ID`. On a server `resync` event, drop every surface before replaying. Contract: `../../genui-contract/reference/backend-topologies.md`.

## AG-UI adapter (optional transport)

`@ag-ui/client@1.0.5` `HttpAgent` against an AG-UI endpoint. A2UI arrives as `ACTIVITY_SNAPSHOT { activityType: 'a2ui-surface', content: { a2ui_operations }, replace: true }`. Snapshots are cumulative per surface, so apply only the new tail. Rewriting the whole surface on each snapshot remounted the surface host and lost bindings in testing. Actions still go through the REST gateway. Contract: `../../genui-contract/reference/ag-ui-transport.md`.

*Not recompiled on Angular 22.3 (historical Angular 21.2.26 excerpt; the compiled 22.3 versions are in the last section).*

```typescript
/**
 * @ag-ui/client 1.0.5 splits SSE frames on /\n\n/ only, but CRLF line endings are valid SSE and
 * are what sse-starlette emits by default. Normalize them before the client parses the stream.
 */
export const crlfNormalizingFetch = async (url: string, init: RequestInit): Promise<Response> => {
  const response = await fetch(url, init);
  if (!response.body) return response;
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const normalized = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(encoder.encode(decoder.decode(chunk, { stream: true }).replace(/\r\n?/g, '\n')));
    },
  }));
  return new Response(normalized, { status: response.status, statusText: response.statusText, headers: response.headers });
};

/**
 * AG-UI adapter: the agent run is the transport, A2UI stays the UI payload. Each snapshot
 * (`replace: true`) holds every operation so far for one surface; the session applies only the
 * new tail, through the same contract guard as the direct SSE path.
 */
@Injectable()
export class AgUiAdapter {
  private readonly backend = inject(GENUI_BACKEND);
  private readonly auth = inject(AuthSession);
  private readonly session = inject(GenuiSession);
  private readonly errorHandler = inject(ErrorHandler);
  private agent: HttpAgent | null = null;

  async run(scenario: string): Promise<void> {
    this.session.beginExternal();
    const agent = new HttpAgent({ url: `${this.backend.baseUrl}/agui`, headers: this.auth.headers(), fetch: crlfNormalizingFetch });
    this.agent = agent;
    try {
      await agent.runAgent(
        { forwardedProps: { scenario } },
        {
          onActivitySnapshotEvent: ({ event }) => {
            if (event.activityType !== A2UI_ACTIVITY_TYPE) return;
            const operations: unknown = event.content[A2UI_OPERATIONS_KEY];
            if (Array.isArray(operations)) this.session.replaySnapshot(operations);
          },
          onRunErrorEvent: ({ event }) => this.session.fail(event.code ?? 'RUN_ERROR', event.message),
        },
      );
      this.session.finishExternal();
    } catch (error) {
      this.errorHandler.handleError(error);
      this.session.fail('AGUI_RUN_FAILED', error instanceof Error ? error.message : String(error));
    }
  }

  cancel(): void {
    this.agent?.abortRun();
    this.session.cancelExternal();
  }
}
```

`@ag-ui/client` 1.0.5 splits SSE frames on `\n\n` only (SOURCE-PROVEN in `dist/index.mjs`), while CRLF framing is valid SSE and is the `sse-starlette` default. Preferred fix: emit LF framing on the server. With `sse-starlette`, set `sep="\n"` on every `ServerSentEvent`, not only on the response; after that server fix the AG-UI tests pass without the normalizing `fetch`. Keep `crlfNormalizingFetch` only for servers you cannot change.
