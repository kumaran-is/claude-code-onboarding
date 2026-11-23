# Angular 22 GenUI stream session, providers and lazy routes (compiled and tested 2026-11-23)

Same sandbox and versions as [canonical-catalog-angular22-components.md](canonical-catalog-angular22-components.md) (Angular 22.3.0, TypeScript 6.0.3, `@a2ui/angular` 0.16.0, `@a2ui/web_core` 0.16.1); check results and the facts these files depend on are listed there.

## Stream session: contract gate, size cap, cancellation, bounded reconnect

```typescript
// genui-session.ts
import { ErrorHandler, Injectable, InjectionToken, inject, signal } from '@angular/core';
import { A2uiRendererService } from '@a2ui/angular';
import type { RendererErrorMessage } from '@a2ui/web_core';

export type StreamStatus = 'idle' | 'streaming' | 'done' | 'cancelled' | 'error';

/** Contract error codes the adapter raises before a message reaches the renderer. */
export type GateErrorCode =
  | 'MESSAGE_TOO_LARGE'
  | 'UNSUPPORTED_VERSION'
  | 'MIXED_VERSIONS'
  | 'UNSAFE_CONTENT'
  | 'SCHEMA_INVALID';

export interface GenuiStreamConfig {
  /** Wire versions this surface session accepts, e.g. `['1.0']` or `['v0.9', 'v0.9.1']`. */
  acceptedVersions: readonly string[];
  /** Contract `limits.maxMessageBytes`. */
  maxMessageBytes: number;
  /** Contract `forbiddenStringPatterns`, already converted to JS RegExp. */
  forbiddenPatterns: readonly RegExp[];
}

export const GENUI_STREAM_CONFIG = new InjectionToken<GenuiStreamConfig>('GENUI_STREAM_CONFIG');

const MAX_RECONNECTS = 3;
const USER_ERROR = 'Part of this response could not be displayed.';

/** Component definitions of a message (data-model values are excluded: they may hold any keys). */
function componentsOf(message: unknown): unknown {
  const m = message as { updateComponents?: { components?: unknown }; createSurface?: { components?: unknown } };
  return [m.updateComponents?.components, m.createSurface?.components];
}

class GateError extends Error {
  constructor(readonly code: GateErrorCode, detail: string) {
    super(`${code}: ${detail}`);
  }
}

/**
 * Feeds an A2UI JSONL stream (one message per line) into the renderer through the contract
 * gate: size cap before JSON.parse, one wire version per stream, unsafe-string scan.
 * Unknown component types and schema errors are rejected by the SDK (`STRICT_VALIDATION`)
 * and arrive in `reportRendererError`. Owns cancellation and bounded reconnection.
 */
@Injectable()
export class GenuiSession {
  private readonly renderer = inject(A2uiRendererService);
  private readonly errors = inject(ErrorHandler);
  private readonly config = inject(GENUI_STREAM_CONFIG);
  private controller: AbortController | null = null;
  private streamVersion: string | null = null;

  readonly status = signal<StreamStatus>('idle');
  readonly error = signal<string | null>(null);
  /** Last contract or renderer error code, for diagnostics and tests. */
  readonly errorCode = signal<string | null>(null);

  /** Called by the renderer's `processorOptions.errorHandler`. */
  reportRendererError(message: RendererErrorMessage): void {
    const code = (message as { error?: { code?: unknown } }).error?.code;
    this.fail(typeof code === 'string' ? code : 'RENDERER_ERROR', new Error(`A2UI renderer error: ${JSON.stringify(message)}`));
  }

  /** Processes already-parsed messages (tests, replays, AG-UI activity content). */
  ingest(messages: readonly unknown[]): void {
    for (const message of messages) this.process(message, JSON.stringify(message).length);
  }

  async connect(url: string, fetchFn: typeof fetch = fetch): Promise<void> {
    this.cancel();
    const controller = new AbortController();
    this.controller = controller;
    this.status.set('streaming');
    this.error.set(null);
    this.errorCode.set(null);
    for (let attempt = 0; attempt <= MAX_RECONNECTS; attempt++) {
      try {
        await this.read(url, fetchFn, controller.signal);
        this.status.set('done');
        return;
      } catch (e) {
        if (controller.signal.aborted) {
          this.status.set('cancelled');
          return;
        }
        this.errors.handleError(e);
        if (attempt === MAX_RECONNECTS) {
          this.status.set('error');
          this.error.set('The agent stream failed. Try again.');
          return;
        }
        await new Promise((r) => setTimeout(r, 250 * 2 ** attempt));
      }
    }
  }

  cancel(): void {
    this.controller?.abort();
    this.controller = null;
  }

  private process(message: unknown, bytes: number): void {
    try {
      this.gate(message, bytes);
    } catch (e) {
      this.fail(e instanceof GateError ? e.code : 'SCHEMA_INVALID', e);
      return;
    }
    try {
      this.renderer.processMessages([message]);
    } catch (e) {
      // web_core throws for some failures (e.g. an unknown catalogId) instead of calling errorHandler.
      this.fail('RENDERER_ERROR', e);
    }
  }

  private gate(message: unknown, bytes: number): void {
    if (bytes > this.config.maxMessageBytes) throw new GateError('MESSAGE_TOO_LARGE', `${bytes} bytes`);
    const version = (message as { version?: unknown } | null)?.version;
    if (this.streamVersion !== null && version !== this.streamVersion) {
      throw new GateError('MIXED_VERSIONS', `${this.streamVersion} then ${String(version)}`);
    }
    if (typeof version !== 'string' || !this.config.acceptedVersions.includes(version)) {
      throw new GateError('UNSUPPORTED_VERSION', String(version));
    }
    this.streamVersion = version;
    const unsafe = this.findUnsafeString(message);
    if (unsafe !== null) throw new GateError('UNSAFE_CONTENT', unsafe.slice(0, 80));
    // web_core 0.16.1 still accepts a v0.9 `{path}`/`{call}` binding on a 1.0 surface.
    if (version === '1.0' && this.hasLegacyBinding(componentsOf(message))) {
      throw new GateError('SCHEMA_INVALID', 'v0.9 {path}/{call} binding in a 1.0 component');
    }
  }

  private hasLegacyBinding(value: unknown): boolean {
    if (!value || typeof value !== 'object') return false;
    if (!Array.isArray(value) && ('path' in value || 'call' in value)) return true;
    return Object.values(value).some((child) => this.hasLegacyBinding(child));
  }

  private findUnsafeString(value: unknown): string | null {
    if (typeof value === 'string') {
      return this.config.forbiddenPatterns.some((p) => p.test(value)) ? value : null;
    }
    if (value && typeof value === 'object') {
      for (const child of Object.values(value)) {
        const hit = this.findUnsafeString(child);
        if (hit !== null) return hit;
      }
    }
    return null;
  }

  private fail(code: string, cause: unknown): void {
    this.errors.handleError(cause);
    this.errorCode.set(code);
    this.error.set(USER_ERROR);
  }

  private async read(url: string, fetchFn: typeof fetch, signal: AbortSignal): Promise<void> {
    this.streamVersion = null;
    const response = await fetchFn(url, { signal, headers: { Accept: 'application/jsonl' } });
    if (!response.ok || !response.body) {
      throw new Error(`A2UI stream HTTP ${response.status}`);
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;
      let newline: number;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) this.processLine(line);
      }
      // Cap before JSON.parse: a line that never ends must not grow without bound.
      if (buffer.length > this.config.maxMessageBytes) {
        throw new GateError('MESSAGE_TOO_LARGE', `${buffer.length}+ bytes without a newline`);
      }
    }
    if (buffer.trim()) this.processLine(buffer.trim());
  }

  private processLine(line: string): void {
    if (line.length > this.config.maxMessageBytes) {
      this.fail('MESSAGE_TOO_LARGE', new GateError('MESSAGE_TOO_LARGE', `${line.length} bytes`));
      return;
    }
    this.process(JSON.parse(line), line.length);
  }
}
```

## Providers per wire version (SDK validation primary)

```typescript
// genui-providers.ts
import { type EnvironmentProviders, Injector, type Provider, inject } from '@angular/core';
import {
  A2uiRendererService,
  AngularCatalog,
  BASIC_COMPONENTS as BASIC_V10,
  BASIC_FUNCTIONS as FUNCTIONS_V10,
  provideA2Ui,
} from '@a2ui/angular';
import { BASIC_COMPONENTS as BASIC_V09, BASIC_FUNCTIONS as FUNCTIONS_V09 } from '@a2ui/angular/v0_9';
import { STRICT_VALIDATION } from '@a2ui/web_core';
import { GENUI_CATALOG_ID_V09, GENUI_CATALOG_ID_V10, V09_APIS, V10_APIS } from './genui-apis';
import { GenuiActionCard } from './action-card';
import { GenuiApprovalRequest } from './approval-request';
import { GenuiEditableForm } from './editable-form';
import { GENUI_STREAM_CONFIG, GenuiSession } from './genui-session';
import { GenuiOutbox } from './genui-outbox';

export type GenuiWireVersion = '0.9' | '1.0';

/** Contract `forbiddenStringPatterns` ("(?i)" prefix → the JS `i` flag). */
const FORBIDDEN_PATTERNS = [/^\s*javascript:/i, /^\s*vbscript:/i, /^\s*data:text\/html/i, /<\s*script/i];

function createCatalog(version: GenuiWireVersion): AngularCatalog {
  if (version === '1.0') {
    return new AngularCatalog(GENUI_CATALOG_ID_V10, '1.0', [
      ...BASIC_V10,
      { ...V10_APIS.ActionCard, component: GenuiActionCard },
      { ...V10_APIS.EditableForm, component: GenuiEditableForm },
      { ...V10_APIS.ApprovalRequest, component: GenuiApprovalRequest },
    ], FUNCTIONS_V10);
  }
  return new AngularCatalog(GENUI_CATALOG_ID_V09, '0.9', [
    ...BASIC_V09,
    { ...V09_APIS.ActionCard, component: GenuiActionCard },
    { ...V09_APIS.EditableForm, component: GenuiEditableForm },
    { ...V09_APIS.ApprovalRequest, component: GenuiApprovalRequest },
  ], FUNCTIONS_V09);
}

/**
 * Renderer, contract gate and outbox for one wire version. Put it in a lazy route's
 * `providers` so each version gets its own renderer and the catalog code stays out of
 * the initial bundle.
 */
export function provideGenui(version: GenuiWireVersion): (Provider | EnvironmentProviders)[] {
  return [
    // A2uiRendererService is providedIn 'root', where it cannot see this route's
    // A2UI_RENDERER_CONFIG ("Catalog not found"). Re-provide it so the route gets its own.
    A2uiRendererService,
    GenuiSession,
    GenuiOutbox,
    {
      provide: GENUI_STREAM_CONFIG,
      useValue: {
        acceptedVersions: version === '1.0' ? ['1.0'] : ['v0.9', 'v0.9.1'],
        maxMessageBytes: 262_144,
        forbiddenPatterns: FORBIDDEN_PATTERNS,
      },
    },
    provideA2Ui(() => {
      const outbox = inject(GenuiOutbox);
      // GenuiSession depends on the renderer, so resolve it lazily to avoid a DI cycle (NG0200).
      const injector = inject(Injector);
      return {
        catalogs: [createCatalog(version)],
        // The v1.0 basic catalog renders as universal Web Components.
        useUniversalComponents: version === '1.0',
        processorOptions: {
          // Rejects unknown component types and schema violations; reported via errorHandler.
          validationConfig: STRICT_VALIDATION,
          outboundListener: (message) => outbox.push(message),
          unifiedOutbound: true,
          errorHandler: (error) => injector.get(GenuiSession).reportRendererError(error),
          reportErrorsOnly: true,
        },
      };
    }),
  ];
}
```

## Lazy routes: one renderer per version, out of the initial bundle

```typescript
// genui.routes.ts
import { type Routes } from '@angular/router';
import { provideGenui } from './genui-providers';

const SURFACES = ['card-1', 'appr-1', 'form-1'];

/** Lazy GenUI routes: each wire version gets its own renderer instance. */
export const GENUI_ROUTES: Routes = [
  {
    path: '',
    providers: provideGenui('0.9'),
    loadComponent: () => import('./genui-page'),
    data: { version: 'v0.9', streamUrl: '/genui-v0_9.jsonl', surfaceIds: SURFACES },
  },
  {
    path: 'v1',
    providers: provideGenui('1.0'),
    loadComponent: () => import('./genui-page'),
    data: { version: '1.0', streamUrl: '/genui-v1_0.jsonl', surfaceIds: SURFACES },
  },
];
```
