# Angular 22 GenUI components on the shared contract (compiled and tested 2026-11-23)

Angular 22.3.0, TypeScript 6.0.3, `@a2ui/angular` 0.16.0, `@a2ui/web_core` 0.16.1, zod 3.25.76, Vitest 5.1.1, Playwright 1.65.1 Chromium + `@axe-core/playwright` 4.14.0. The catalogs are the shared `genui-contract` catalogs: v1.0 `https://catalogs.example.com/genui/shared-runtime-a2ui-1_0/v1/catalog.json` (target) and v0.9 `https://catalogs.example.com/genui/shared-runtime/v1/catalog.json` (compatibility path).

| Check | Result |
|---|---|
| `ng build` / `ng lint` / `tsc --strict` (app + spec) | exit 0 / 0 / 0 |
| `ng test` | exit 0, 28 passed + 1 LIVE test skipped without `GENUI_LIVE_URL` |
| Shared samples, both versions (LIVE-PROTOCOL, real renderer) | 3 valid samples render with no error; every invalid sample (except the renderer-to-agent `bad-action-payload`) shows the error state with the code below |
| Playwright Chromium (production build, MOCK agent = static JSONL) | exit 0, 7 passed: v0.9 and 1.0 full flow + axe (WCAG 2.2 AA tags, 0 violations), unknown component, `javascript:` URL, HTTP 503 |
| LIVE backend (AG-UI SSE `ACTIVITY_SNAPSHOT` `a2ui-surface`, 1.0) | exit 0: surface rendered, `item.open` sent back in `forwardedProps.a2uiAction.userAction`, `RUN_FINISHED`; negative control (404 URL) fails |
| Negative controls | removing `STRICT_VALIDATION` fails 3 tests (unknown component v0.9 + 1.0, `createsurface-theme`); removing the unsafe-string gate fails 2; removing the dispatch allowlist fails 2 |

Which layer rejects each invalid shared sample:

| Sample | Code | Layer |
|---|---|---|
| `unknown-component` (v0.9, 1.0) | `VALIDATION_FAILED` | SDK: `STRICT_VALIDATION` → `processorOptions.errorHandler` |
| `action-not-allowed` (v0.9, 1.0) | `VALIDATION_FAILED` | SDK: the component's zod schema (`z.enum` of allowed event names); also refused at dispatch |
| `createsurface-theme` (1.0) | `INTEGRITY_ERROR` | SDK |
| `javascript-url` (v0.9, 1.0) | `UNSAFE_CONTENT` | app gate (`forbiddenStringPatterns`) |
| `version-mismatch` (v0.9, 1.0) | `MIXED_VERSIONS` | app gate (one version per stream) |
| `legacy-v0_9-binding` (1.0) | `SCHEMA_INVALID` | app gate: web_core 0.16.1 accepts `{"path": …}` on a 1.0 surface |
| `bad-action-payload` | n/a (renderer→agent) | the test asserts the sent approval carries `requestId` and no extra keys; the server must reject it anyway |

Facts these files depend on (all tested):

- The SDK binder resolves **nested** bindings: `fields[i].value` arrives as the current value and re-emits on every data-model change. To write an edit back, read the raw binding from `surface.componentsModel.get(componentId).properties` and call `new DataContext(surface, dataContextPath).set(path, value)`.
- `A2uiRendererService` is `providedIn: 'root'`. Put `provideA2Ui` in a lazy route and the root instance never sees that config (browser error `Catalog not found`). Re-provide `A2uiRendererService` in the same `providers` array.
- On 1.0 with `useUniversalComponents: true`, custom components render as `a2ui-ng-<name>` custom elements, not under the Angular selector. Select them in tests with a host attribute (`data-genui`).
- The v1.0 basic components are Lit elements with open shadow roots; text assertions must walk `shadowRoot`.
- `ComponentHostComponent.reportUnresolved` only writes to the console. It is **not** an error signal: nothing reaches `errorHandler` and the user sees an empty slot unless `validationConfig: STRICT_VALIDATION` is set.
- Bundle: with GenUI behind `loadChildren`, the initial bundle is 287.25 kB raw (74.57 kB transfer) and the GenUI route chunk is 669.86 kB raw (143.37 kB transfer). Eager wiring was 916.12 kB initial. The remaining build warning is `validate-color` (CommonJS, used by `web_core` `universal/basic_catalog/theme.js`); it is not added to `allowedCommonJsDependencies`.

## Component APIs for both wire versions (zod 3, same copy as web_core)

```typescript
// genui-apis.ts
import { z } from 'zod';
import * as v09 from '@a2ui/web_core/v0_9';
import * as v10 from '@a2ui/web_core/v1_0';

/** Catalog ids from the shared GenUI contract (one per wire version). */
export const GENUI_CATALOG_ID_V09 = 'https://catalogs.example.com/genui/shared-runtime/v1/catalog.json';
export const GENUI_CATALOG_ID_V10 = 'https://catalogs.example.com/genui/shared-runtime-a2ui-1_0/v1/catalog.json';

/** Per-component action allowlist (contract `allowedActions`). */
export const ALLOWED_ACTIONS = {
  ActionCard: ['item.open', 'item.dismiss'],
  EditableForm: ['form.submit', 'form.cancel'],
  ApprovalRequest: ['approval.approve', 'approval.reject'],
} as const;

interface VersionSchemas {
  DynamicStringSchema: z.ZodTypeAny;
  DataBindingSchema: z.ZodTypeAny;
  CheckRuleSchema: z.ZodTypeAny;
  /** v0.9 declares `accessibility` per component; v1.0 uses the `@accessibility` envelope key. */
  common: z.ZodRawShape;
}

const identifier = /^[a-z][a-zA-Z0-9_]{0,63}$/;
const entityId = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

/**
 * Builds the three shared components for one wire version. The props are identical in
 * v0.9 and v1.0; only the binding/check schemas differ (`path` vs `@path`).
 */
function buildApis<S extends VersionSchemas>(s: S) {
  // Contract ServerEvent: server events only (no functionCall), names from the allowlist.
  const serverEvent = <T extends readonly [string, ...string[]]>(names: T) =>
    z
      .object({
        event: z
          .object({
            name: z.enum(names),
            context: z
              .record(
                z.string().regex(identifier),
                z.union([z.string(), z.number().int(), z.boolean(), s.DataBindingSchema]),
              )
              .optional(),
          })
          .strict(),
      })
      .strict();

  const ActionCard = {
    name: 'ActionCard',
    schema: z
      .object({
        ...s.common,
        title: s.DynamicStringSchema,
        subtitle: s.DynamicStringSchema.optional(),
        body: s.DynamicStringSchema.optional(),
        actions: z
          .array(
            z
              .object({
                label: z.string().min(1).max(40),
                variant: z.enum(['primary', 'secondary']).optional(),
                action: serverEvent(ALLOWED_ACTIONS.ActionCard),
              })
              .strict(),
          )
          .min(1)
          .max(3),
      })
      .strict(),
  };

  const EditableForm = {
    name: 'EditableForm',
    schema: z
      .object({
        ...s.common,
        title: s.DynamicStringSchema,
        formId: z.string().regex(entityId),
        fields: z
          .array(
            z
              .object({
                name: z.string().regex(identifier),
                label: z.string().min(1).max(80),
                inputType: z.enum(['text', 'email', 'integer', 'multiline', 'date']),
                value: s.DataBindingSchema,
                required: z.boolean().optional(),
                maxLength: z.number().int().min(1).max(10000).optional(),
                checks: z.array(s.CheckRuleSchema).max(5).optional(),
              })
              .strict(),
          )
          .min(1)
          .max(20),
        submitLabel: z.string().min(1).max(40).optional(),
        submitAction: serverEvent(['form.submit']),
        cancelAction: serverEvent(['form.cancel']).optional(),
      })
      .strict(),
  };

  const ApprovalRequest = {
    name: 'ApprovalRequest',
    schema: z
      .object({
        ...s.common,
        title: s.DynamicStringSchema,
        summary: s.DynamicStringSchema,
        requestId: z.string().regex(entityId),
        riskLevel: z.enum(['low', 'medium', 'high']),
        /** Contract: a DataBinding. Typed as DynamicString so the binder hands over a writable BoundProperty. */
        comment: s.DynamicStringSchema.optional(),
        approveAction: serverEvent(['approval.approve']),
        rejectAction: serverEvent(['approval.reject']),
      })
      .strict(),
  };

  return { ActionCard, EditableForm, ApprovalRequest };
}

export const V09_APIS = buildApis({
  DynamicStringSchema: v09.DynamicStringSchema,
  DataBindingSchema: v09.DataBindingSchema,
  CheckRuleSchema: v09.CheckRuleSchema,
  common: { accessibility: v09.AccessibilityAttributesSchema.optional() },
});
export const V10_APIS = buildApis({
  DynamicStringSchema: v10.DynamicStringSchema,
  DataBindingSchema: v10.DataBindingSchema,
  CheckRuleSchema: v10.CheckRuleSchema,
  common: {},
});

export type ActionCardApi = typeof V09_APIS.ActionCard;
export type EditableFormApi = typeof V09_APIS.EditableForm;
export type ApprovalRequestApi = typeof V09_APIS.ApprovalRequest;
```

## Action dispatch: allowlist, then resolve and dispatch

```typescript
// genui-action.ts
import { A2uiRendererService } from '@a2ui/angular';
import { DataContext } from '@a2ui/web_core';

/** Identifies the catalog component that dispatches an action. */
export interface ActionSource {
  surfaceId: string;
  componentId: string;
  dataContextPath: string;
}

/** Thrown when an action is outside the component's allowlist (contract `ACTION_NOT_ALLOWED`). */
export class ActionNotAllowedError extends Error {
  constructor(readonly actionName: string) {
    super(`ACTION_NOT_ALLOWED: "${actionName}"`);
  }
}

function eventName(action: unknown): string | undefined {
  const event = (action as { event?: { name?: unknown } } | null)?.event;
  return typeof event?.name === 'string' ? event.name : undefined;
}

/**
 * Checks the action against the component's allowlist, resolves its context against the
 * surface data model and dispatches it. Nested actions (e.g. `actions[].action`) arrive raw.
 * Throws on a disallowed action or a missing surface so the caller can show an error state.
 */
export async function dispatchA2uiAction(
  renderer: A2uiRendererService,
  source: ActionSource,
  action: unknown,
  allowed: readonly string[],
): Promise<void> {
  const name = eventName(action);
  if (!name || !allowed.includes(name)) {
    throw new ActionNotAllowedError(String(name));
  }
  const surface = renderer.surfaceGroup.getSurface(source.surfaceId);
  if (!surface) {
    throw new Error(`A2UI surface "${source.surfaceId}" no longer exists`);
  }
  const resolved = await new DataContext(surface, source.dataContextPath).resolveAction(
    action as Record<string, unknown>,
    { userActivation: true },
  );
  if (resolved === undefined) {
    throw new Error(`A2UI action from "${source.componentId}" failed to resolve`);
  }
  await surface.dispatchAction(resolved, source.componentId);
}

/** Reads `{ path }` (v0.9) or `{ '@path' }` (v1.0) from a raw binding object. */
export function bindingPath(binding: unknown): string | undefined {
  const b = binding as { path?: unknown; '@path'?: unknown } | null;
  const path = b?.path ?? b?.['@path'];
  return typeof path === 'string' ? path : undefined;
}
```

## ActionCard

```typescript
// action-card.ts
import { Component, ErrorHandler, computed, inject, signal } from '@angular/core';
import { A2uiRendererService, CatalogComponent } from '@a2ui/angular';
import { ALLOWED_ACTIONS, type ActionCardApi } from './genui-apis';
import { dispatchA2uiAction } from './genui-action';

@Component({
  selector: 'app-genui-action-card',
  host: { 'data-genui': 'ActionCard', role: 'article', class: 'card bg-base-100 shadow-sm block' },
  template: `
    <div class="card-body">
      <h3 class="card-title">{{ title() }}</h3>
      @if (subtitle()) {
        <p class="text-sm">{{ subtitle() }}</p>
      }
      @if (body()) {
        <p>{{ body() }}</p>
      }
      @if (error()) {
        <p role="alert" class="text-error">{{ error() }}</p>
      }
      <div class="card-actions justify-end">
        @for (item of actions(); track $index) {
          <button
            type="button"
            class="btn min-h-11"
            [class.btn-primary]="item.variant === 'primary'"
            [disabled]="pending()"
            (click)="run(item.action)"
          >
            {{ item.label }}
          </button>
        }
      </div>
    </div>
  `,
})
export class GenuiActionCard extends CatalogComponent<ActionCardApi> {
  private readonly renderer = inject(A2uiRendererService);
  private readonly errors = inject(ErrorHandler);
  protected readonly title = computed(() => this.props().title?.value() ?? '');
  protected readonly subtitle = computed(() => this.props().subtitle?.value());
  protected readonly body = computed(() => this.props().body?.value());
  protected readonly actions = computed(() => this.props().actions?.value() ?? []);
  protected readonly pending = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async run(action: unknown): Promise<void> {
    if (this.pending()) return;
    this.pending.set(true);
    this.error.set(null);
    try {
      await dispatchA2uiAction(
        this.renderer,
        { surfaceId: this.surfaceId(), componentId: this.componentId(), dataContextPath: this.dataContextPath() },
        action,
        ALLOWED_ACTIONS.ActionCard,
      );
    } catch (e) {
      this.errors.handleError(e);
      this.error.set('This action could not be sent. Try again.');
    } finally {
      this.pending.set(false);
    }
  }
}
```

## ApprovalRequest (human-in-the-loop, one decision, bound comment)

```typescript
// approval-request.ts
import { Component, ErrorHandler, computed, inject, signal } from '@angular/core';
import { A2uiRendererService, CatalogComponent } from '@a2ui/angular';
import { ALLOWED_ACTIONS, type ApprovalRequestApi } from './genui-apis';
import { dispatchA2uiAction } from './genui-action';

type Decision = 'approve' | 'reject';

/** Human-in-the-loop approval. One decision per request; the server re-authorizes it. */
@Component({
  selector: 'app-genui-approval-request',
  host: { 'data-genui': 'ApprovalRequest', role: 'group', '[attr.aria-labelledby]': 'headingId()', class: 'block space-y-2' },
  template: `
    <h3 [id]="headingId()" class="text-lg font-semibold">{{ title() }}</h3>
    <p>{{ summary() }}</p>
    <p>Risk level: <strong>{{ riskLevel() }}</strong></p>
    @if (hasComment()) {
      <label class="block" [for]="commentId()">Comment (optional)</label>
      <textarea
        class="textarea min-h-11 w-full"
        [id]="commentId()"
        [value]="comment()"
        [disabled]="!!sent()"
        (input)="onComment($event)"
      ></textarea>
    }
    @if (error()) {
      <p role="alert" class="text-error">{{ error() }}</p>
    }
    @if (sent(); as decision) {
      <p role="status">Decision sent: {{ decision }}</p>
    } @else {
      <div class="flex gap-2">
        <button type="button" class="btn btn-primary min-h-11" [disabled]="pending()" (click)="decide('approve')">
          Approve
        </button>
        <button type="button" class="btn min-h-11" [disabled]="pending()" (click)="decide('reject')">
          Reject
        </button>
      </div>
    }
  `,
})
export class GenuiApprovalRequest extends CatalogComponent<ApprovalRequestApi> {
  private readonly renderer = inject(A2uiRendererService);
  private readonly errors = inject(ErrorHandler);
  protected readonly title = computed(() => this.props().title?.value() ?? '');
  protected readonly summary = computed(() => this.props().summary?.value() ?? '');
  protected readonly riskLevel = computed(() => this.props().riskLevel?.value() ?? 'high');
  protected readonly hasComment = computed(() => !!this.props().comment);
  protected readonly comment = computed(() => this.props().comment?.value() ?? '');
  protected readonly headingId = computed(() => `approval-${this.surfaceId()}-${this.componentId()}`);
  protected readonly commentId = computed(() => `${this.headingId()}-comment`);
  protected readonly pending = signal(false);
  protected readonly sent = signal<Decision | null>(null);
  protected readonly error = signal<string | null>(null);

  protected onComment(event: Event): void {
    // Two-way binding: writes the comment to its data-model path.
    this.props().comment?.onUpdate((event.target as HTMLTextAreaElement).value);
  }

  protected async decide(decision: Decision): Promise<void> {
    if (this.pending() || this.sent()) return;
    this.pending.set(true);
    this.error.set(null);
    const action =
      decision === 'approve' ? this.props().approveAction?.value() : this.props().rejectAction?.value();
    try {
      await dispatchA2uiAction(
        this.renderer,
        { surfaceId: this.surfaceId(), componentId: this.componentId(), dataContextPath: this.dataContextPath() },
        action,
        ALLOWED_ACTIONS.ApprovalRequest,
      );
      this.sent.set(decision);
    } catch (e) {
      this.errors.handleError(e);
      this.error.set('The decision could not be sent. Try again.');
    } finally {
      this.pending.set(false);
    }
  }
}
```

## EditableForm (Signal Forms, nested bindings)

```typescript
// editable-form.ts
import { Component, ErrorHandler, computed, inject, linkedSignal, signal } from '@angular/core';
import { FormField, applyEach, form, maxLength, required } from '@angular/forms/signals';
import { A2uiRendererService, CatalogComponent } from '@a2ui/angular';
import { DataContext } from '@a2ui/web_core';
import { ALLOWED_ACTIONS, type EditableFormApi } from './genui-apis';
import { bindingPath, dispatchA2uiAction } from './genui-action';

function toText(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

const INPUT_TYPES: Record<string, string> = {
  text: 'text',
  email: 'email',
  integer: 'number',
  date: 'date',
};

/**
 * Agent-defined form rendered with Signal Forms. Each field's `value` is a data-model
 * binding; edits are written there, and the submit action's context binds the same paths.
 */
@Component({
  selector: 'app-genui-editable-form',
  imports: [FormField],
  host: { 'data-genui': 'EditableForm', class: 'block' },
  template: `
    <form (submit)="onSubmit($event)" [attr.aria-labelledby]="headingId()" novalidate class="space-y-2">
      <h3 [id]="headingId()" class="text-lg font-semibold">{{ title() }}</h3>
      @for (field of fields(); track field.name) {
        <label class="block" [for]="inputId(field.name)">
          {{ field.label }}@if (field.required) {<span aria-hidden="true"> *</span>}
        </label>
        @if (field.inputType === 'multiline') {
          <textarea
            class="textarea min-h-11 w-full"
            [id]="inputId(field.name)"
            [formField]="valuesForm[field.name]"
            [attr.aria-invalid]="showError(field.name) ? 'true' : null"
            [attr.aria-describedby]="showError(field.name) ? inputId(field.name) + '-error' : null"
            (input)="write(field.name)"
          ></textarea>
        } @else {
          <input
            class="input min-h-11 w-full"
            [id]="inputId(field.name)"
            [type]="inputType(field.inputType)"
            [formField]="valuesForm[field.name]"
            [attr.aria-invalid]="showError(field.name) ? 'true' : null"
            [attr.aria-describedby]="showError(field.name) ? inputId(field.name) + '-error' : null"
            (input)="write(field.name)"
          />
        }
        @if (showError(field.name)) {
          <p class="text-error" [id]="inputId(field.name) + '-error'">{{ errorText(field.name) }}</p>
        }
      }
      @if (error()) {
        <p role="alert" class="text-error">{{ error() }}</p>
      }
      <div class="flex gap-2">
        <button type="submit" class="btn btn-primary min-h-11" [disabled]="pending()">{{ submitLabel() }}</button>
        @if (hasCancel()) {
          <button type="button" class="btn min-h-11" [disabled]="pending()" (click)="cancel()">Cancel</button>
        }
      </div>
    </form>
  `,
})
export class GenuiEditableForm extends CatalogComponent<EditableFormApi> {
  private readonly renderer = inject(A2uiRendererService);
  private readonly errors = inject(ErrorHandler);
  protected readonly title = computed(() => this.props().title?.value() ?? '');
  protected readonly fields = computed(() => this.props().fields?.value() ?? []);
  protected readonly submitLabel = computed(() => this.props().submitLabel?.value() ?? 'Submit');
  protected readonly hasCancel = computed(() => !!this.props().cancelAction?.value());
  protected readonly headingId = computed(() => `form-${this.surfaceId()}-${this.componentId()}`);
  private readonly requiredNames = computed(
    () => new Set(this.fields().filter((f) => f.required).map((f) => f.name)),
  );
  private readonly maxLengths = computed(
    () => new Map(this.fields().map((f) => [f.name, f.maxLength] as const)),
  );
  /**
   * Local form model. The SDK binder resolves each field's nested `value` binding, so
   * `fields()` re-emits on every data-model change and this model follows it.
   */
  protected readonly model = linkedSignal<Record<string, string>>(() =>
    Object.fromEntries(this.fields().map((f) => [f.name, toText(f.value)])),
  );
  protected readonly valuesForm = form(this.model, (p) => {
    applyEach(p, (item) => {
      required(item, { when: ({ key }) => this.requiredNames().has(key()) });
      maxLength(item, ({ key }) => this.maxLengths().get(key()));
    });
  });
  protected readonly pending = signal(false);
  protected readonly error = signal<string | null>(null);
  private readonly submitted = signal(false);

  protected inputId(name: string): string {
    return `${this.headingId()}-${name}`;
  }

  protected inputType(type: string): string {
    return INPUT_TYPES[type] ?? 'text';
  }

  protected showError(name: string): boolean {
    const field = this.valuesForm[name];
    return !!field && field().invalid() && (this.submitted() || field().touched());
  }

  protected errorText(name: string): string {
    const field = this.fields().find((f) => f.name === name);
    const checkMessage = (field?.checks?.[0] as { message?: unknown } | undefined)?.message;
    return typeof checkMessage === 'string' ? checkMessage : `${field?.label ?? name} is required.`;
  }

  /** Writes an edit to the field's data-model path, read from the raw (unresolved) component. */
  protected write(name: string): void {
    const surface = this.renderer.surfaceGroup.getSurface(this.surfaceId());
    const rawFields: unknown = surface?.componentsModel.get(this.componentId())?.properties['fields'];
    const rawField = Array.isArray(rawFields)
      ? (rawFields as { name?: unknown; value?: unknown }[]).find((f) => f.name === name)
      : undefined;
    const path = bindingPath(rawField?.value);
    if (!surface || !path) {
      this.errors.handleError(new Error(`EditableForm field "${name}" has no data binding`));
      this.error.set('This field could not be saved.');
      return;
    }
    const raw = this.model()[name] ?? '';
    const field = this.fields().find((f) => f.name === name);
    new DataContext(surface, this.dataContextPath()).set(path, field?.inputType === 'integer' && raw !== '' ? Number(raw) : raw);
  }

  protected async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    this.submitted.set(true);
    if (this.valuesForm().invalid()) return;
    await this.send(this.props().submitAction?.value());
  }

  protected async cancel(): Promise<void> {
    await this.send(this.props().cancelAction?.value());
  }

  private async send(action: unknown): Promise<void> {
    if (this.pending()) return;
    this.pending.set(true);
    this.error.set(null);
    try {
      await dispatchA2uiAction(
        this.renderer,
        { surfaceId: this.surfaceId(), componentId: this.componentId(), dataContextPath: this.dataContextPath() },
        action,
        ALLOWED_ACTIONS.EditableForm,
      );
    } catch (e) {
      this.errors.handleError(e);
      this.error.set('The form could not be sent. Try again.');
    } finally {
      this.pending.set(false);
    }
  }
}
```

Stream session, providers per wire version and lazy routes: [canonical-catalog-angular22-session.md](canonical-catalog-angular22-session.md).
