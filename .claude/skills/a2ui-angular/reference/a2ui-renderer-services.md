# A2UI Angular — Agent Service, Official SDK, and Unit Tests

## Official SDK: `@a2ui/angular`

The `@a2ui/angular` package is the **official Angular renderer SDK** from Google. Use it for new projects instead of building a custom renderer from scratch.

```bash
npm install --save-exact @a2ui/angular@0.16.0 @a2ui/web_core@0.16.1 zod@3.25.76   # peer: @angular/* ^22.2.3
```

Historical evidence, not re-run on 22.3: verified 2026-11-22 against 0.14.0 in Chromium (Angular 21.2.26); the same exports exist in 0.16.0 (`.d.ts` checked 2026-11-23). Exports used below:
`provideA2Ui`, `MarkdownRenderer`, `A2uiRendererService` (`@a2ui/angular`); `SurfaceComponent`
(selector `a2ui-v09-surface`), `BasicCatalog` (`@a2ui/angular/v0_9`); `STRICT_VALIDATION`, `ActionPayload`
(`@a2ui/web_core/v0_9`). `provideA2uiRenderer` and `@a2ui/angular/catalogs` do not exist in 0.14.0 or 0.16.0. The
package root `BasicCatalog` is the v1.0 catalog — import the v0.9 one from `@a2ui/angular/v0_9`.

### Provider Setup (app.config.ts)

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// app.config.ts excerpt — official renderer, A2UI v0.9 wire format, strict validation
import { EnvironmentProviders, Provider, inject, makeEnvironmentProviders } from '@angular/core';
import { MarkdownRenderer, provideA2Ui } from '@a2ui/angular';
import { BasicCatalog } from '@a2ui/angular/v0_9';
import { STRICT_VALIDATION } from '@a2ui/web_core/v0_9';
import { MarkdownService } from './features/chat/services/markdown.service'; // ai-chat: marked -> DOMPurify
import { AgentActionsService } from './features/a2ui/agent-actions.service';   // your agent client

// The v0.9 Text component binds rendered markdown to [innerHTML]. Route it through the
// marked -> DOMPurify pipeline (ai-chat streaming-patterns.md) instead of the default renderer.
const sanitizedMarkdown: Provider = {
  provide: MarkdownRenderer,
  useFactory: () => {
    const markdown = inject(MarkdownService);
    return { render: async (text: string) => markdown.render(text) };
  },
};

export function provideA2uiStrict(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideA2Ui(() => {
      const agent = inject(AgentActionsService); // factory runs in an injection context
      return {
        catalogs: [new BasicCatalog()],
        // Without a validationConfig the v0.9 processor accepts self-referencing children,
        // unknown component types and unbounded depth (web_core 0.15.0, verified). STRICT rejects them.
        processorOptions: { validationConfig: STRICT_VALIDATION },
        actionHandler: (action) => agent.forward(action), // the server re-authorizes every action
      };
    }),
    sanitizedMarkdown,
  ]);
}
```

### Feeding messages and rendering a surface

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
import { Component, ErrorHandler, inject, signal } from '@angular/core';
import { A2uiRendererService } from '@a2ui/angular';
import { SurfaceComponent } from '@a2ui/angular/v0_9';

@Component({
  selector: 'app-agent-surface',
  imports: [SurfaceComponent],
  template: `
    @if (rejected()) { <p role="alert">This content could not be displayed.</p> }
    <a2ui-v09-surface surfaceId="main" />
  `,
})
export class AgentSurfaceComponent {
  private readonly renderer = inject(A2uiRendererService);
  private readonly errorHandler = inject(ErrorHandler);
  readonly rejected = signal(false);

  /** Call with each validated batch of v0.9 messages from the agent (createSurface, updateComponents, …). */
  ingest(messages: unknown[]): void {
    try {
      this.renderer.processMessages(messages);
      this.rejected.set(false);
    } catch (err) {
      this.errorHandler.handleError(err); // STRICT_VALIDATION throws A2uiRecursionError / A2uiValidationError
      this.rejected.set(true);            // the last good surface stays on screen
    }
  }
}
```

Browser-tested: a valid surface rendered and its Button forwarded
`{"name":"submit","surfaceId":"s","sourceComponentId":"b","timestamp":"…","context":{"orderId":"o-1"}}` to
the agent client; a cycle and an unknown type were rejected with the alert shown.

### Production vs Demo Action Handler

A common demo pattern answers an action inside the browser by calling `processMessages` directly:

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// ⚠️ DEMO-ONLY — do NOT use in production
actionHandler: () => renderer.processMessages([{ version: 'v0.9', updateDataModel: { /* … */ } }]),
```

**This is wrong for production.** It:
- Cuts the agent out of the loop — the agent never sees the action
- Breaks observability — no trace of the action or its result
- Bypasses server-side validation and authorization
- Creates state divergence between client and agent

Production: `actionHandler` forwards to the agent API (as above); the server authorizes the action, validates
its `context` and decides which messages, if any, come back. Apply the response through `ingest()`.

### When to Use SDK vs Custom Renderer

| Scenario | Use |
|----------|-----|
| New project, standard catalog sufficient | `@a2ui/angular` SDK with `BasicCatalog` (v0.9) |
| Need custom component types (chart, map, etc.) or the shared canonical catalog | SDK + an `AngularCatalog` custom catalog (`canonical-catalog-angular.md`) |
| Need a custom security policy | SDK + the ingest guard that runs before `processMessages` (`canonical-catalog-angular.md` § Ingest guard) |
| Agent still emits v0.8 payloads | LEGACY hand-built renderer (`a2ui-renderer-patterns.md`), until the agent moves to v0.9 |

---

## Agent Service (REST + SSE) — LEGACY v0.8

> **LEGACY v0.8.** This service and the unit test template below belong to the hand-built renderer in
> `a2ui-renderer-patterns.md`: `buildSurfaceState` folds v0.8 messages (`surfaceUpdate`, `dataModelUpdate`,
> `beginRendering`) into its `SurfaceState`. With the SDK (above) do not fold state yourself: pass each
> v0.9 message (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`) through the ingest
> guard and then `AgentSurfaceComponent.ingest()`; `processMessages` owns the surface state. Keep the
> transport rules from this section (a malformed frame or a dropped stream is an error, never a silent complete).

*Not recompiled on Angular 22.3 (pre-22 snippet; `@Service()` conversions are mechanical).*

```typescript
// services/a2ui-agent.service.ts

import { Service, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { map } from 'rxjs/operators';
import { A2UIMessage, SurfaceState, UserAction } from '../models/a2ui.model';

@Service()
export class A2UIAgentService {
  private http = inject(HttpClient);

  sendMessage(message: string): Observable<SurfaceState> {
    return this.http.post<A2UIMessage[]>('/api/agent/chat', { message }).pipe(
      map(messages => this.buildSurfaceState(messages)),
    );
  }

  sendUserAction(action: UserAction): Observable<SurfaceState> {
    return this.http.post<A2UIMessage[]>('/api/agent/action', action).pipe(
      map(messages => this.buildSurfaceState(messages)),
    );
  }

  streamMessages(message: string): Observable<A2UIMessage> {
    const subject = new Subject<A2UIMessage>();
    const eventSource = new EventSource(
      `/api/agent/stream?message=${encodeURIComponent(message)}`,
    );
    eventSource.onmessage = (event) => {
      try {
        const line = (event.data as string).trim();
        if (line) subject.next(JSON.parse(line) as A2UIMessage);
      } catch (e) {
        // Fail visibly: the caller logs via ErrorHandler and shows a recoverable error; last good surface stays
        subject.error(new Error('A2UI: malformed stream frame', { cause: e }));
        eventSource.close();
      }
    };
    eventSource.addEventListener('done', () => { subject.complete(); eventSource.close(); });
    eventSource.onerror = () => {
      subject.error(new Error('A2UI: SSE stream error')); // not complete(): a dropped stream is an error state
      eventSource.close();
    };
    return subject.asObservable();
  }

  // Folds a sequence of JSONL protocol messages into a single SurfaceState
  buildSurfaceState(messages: A2UIMessage[]): SurfaceState {
    const state: SurfaceState = {
      surfaceId: '',
      componentMap: new Map(),
      rootComponentId: '',
      dataModel: {},
    };
    for (const msg of messages) {
      if (msg.surfaceUpdate) {
        state.surfaceId = msg.surfaceUpdate.surfaceId;
        // Build map from ARRAY (official format)
        for (const entry of msg.surfaceUpdate.components) {
          state.componentMap.set(entry.id, entry.component);
        }
      }
      if (msg.dataModelUpdate) {
        const base = msg.dataModelUpdate.path ?? '';
        for (const entry of msg.dataModelUpdate.contents) {
          const fullKey = base ? `${base}/${entry.key}` : entry.key;
          if ('valueString' in entry) state.dataModel[fullKey] = entry.valueString;
          else if ('valueNumber' in entry) state.dataModel[fullKey] = entry.valueNumber;
          else if ('valueMap' in entry) state.dataModel[fullKey] = entry.valueMap;
        }
      }
      if (msg.beginRendering) {
        state.surfaceId = msg.beginRendering.surfaceId;
        state.rootComponentId = msg.beginRendering.root;  // field is 'root', not 'rootComponent'
      }
      // deleteSurface: handled at the chat component level, not here
    }

    // Gemini resilience: if agent sent surfaceUpdate with a 'root' component but
    // omitted beginRendering, auto-set rootComponentId so the renderer doesn't silently show nothing.
    if (!state.rootComponentId && state.componentMap.has('root')) {
      state.rootComponentId = 'root';
    }

    return state;
  }
}
```

---

## Unit Test Template — LEGACY v0.8 hand-built renderer

For the SDK path, test the ingest guard and the action gateway instead (`canonical-catalog-angular.md`).

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// components/a2ui-renderer/a2ui-renderer.component.spec.ts

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { A2UIRendererComponent } from './a2ui-renderer.component';
import { SurfaceState, UserAction } from '../../models/a2ui.model';

function makeSurface(overrides: Partial<SurfaceState> = {}): SurfaceState {
  return {
    surfaceId: 'main',
    componentMap: new Map(),
    rootComponentId: 'root',
    dataModel: {},
    ...overrides,
  };
}

describe('A2UIRendererComponent', () => {
  let fixture: ComponentFixture<A2UIRendererComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [A2UIRendererComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(A2UIRendererComponent);
  });

  it('should render a Card with a Text child', () => {
    const surface = makeSurface({
      componentMap: new Map([
        ['root', { type: 'Card', child: 'text-1' }],
        ['text-1', { type: 'Text', text: { literalString: 'Hello World' }, usageHint: 'body' }],
      ]),
    });
    fixture.componentRef.setInput('surface', surface);
    fixture.componentRef.setInput('componentId', 'root');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Hello World');
  });

  it('should skip unknown component types', () => {
    const surface = makeSurface({
      componentMap: new Map([
        ['root', { type: 'malicious-script' }],
      ]),
    });
    fixture.componentRef.setInput('surface', surface);
    fixture.componentRef.setInput('componentId', 'root');
    fixture.detectChanges();
    expect(fixture.nativeElement.innerHTML).not.toContain('malicious-script');
    expect(fixture.nativeElement.children.length).toBe(0);
  });

  it('should emit UserAction with resolved context on button click', () => {
    const surface = makeSurface({
      componentMap: new Map([
        ['btn-book', {
          type: 'Button',
          label: { literalString: 'Book' },
          action: {
            name: 'book_hotel',
            context: [{ key: 'hotelId', value: { literalString: 'H-456' } }],
          },
        }],
      ]),
      dataModel: {},
    });
    fixture.componentRef.setInput('surface', surface);
    fixture.componentRef.setInput('componentId', 'btn-book');
    fixture.detectChanges();

    let emitted: UserAction | undefined;
    fixture.componentInstance.actionTriggered.subscribe(a => (emitted = a));
    fixture.nativeElement.querySelector('button').click();

    expect(emitted).toMatchObject({
      name: 'book_hotel',
      surfaceId: 'main',
      sourceComponentId: 'btn-book',
      context: { hotelId: 'H-456' },
    });
    expect(emitted?.timestamp).toBeTruthy();
  });

  it('should resolve Text content from dataModel via path binding', () => {
    const surface = makeSurface({
      componentMap: new Map([
        ['root', {
          type: 'Text',
          text: { path: '/reservation/date' },
          usageHint: 'body',
        }],
      ]),
      dataModel: { '/reservation/date': '2026-04-01' },
    });
    fixture.componentRef.setInput('surface', surface);
    fixture.componentRef.setInput('componentId', 'root');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('2026-04-01');
  });

  it('should use literalString default when path resolves to nothing', () => {
    const surface = makeSurface({
      componentMap: new Map([
        ['root', {
          type: 'Text',
          text: { path: '/reservation/missing', literalString: 'N/A' },
          usageHint: 'body',
        }],
      ]),
      dataModel: {},
    });
    fixture.componentRef.setInput('surface', surface);
    fixture.componentRef.setInput('componentId', 'root');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('N/A');
  });
});
```
