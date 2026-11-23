# A2UI Renderer & Chat Component Templates

> **LEGACY v0.8 payload shape** (see `a2ui-renderer-patterns.md`). Compiled on Angular 21.2.26 (not re-run on 22.3) (`strictTemplates`) and browser-tested in Chromium 2026-11-22 with the models, catalog and sanitizer from `a2ui-renderer-patterns.md`:
> - `root → a → root`, `root.child = root` and a 41-level tree each render one placeholder and log `A2UI: cycle or depth > 32 …`; the tab stays responsive.
> - An unknown type (`Iframe`) renders the placeholder and logs `component type "Iframe" is not in the catalog`.
> - Tabs are `button role="tab"` with `aria-selected` and roving `tabindex`; ArrowLeft/ArrowRight move selection and focus, and the active child renders in `role="tabpanel"`.
> - Negative control: the previous version of this file (no guard) crashed the tab on the cycle (`Maximum call stack size exceeded`).

## Renderer Component

*Not recompiled on Angular 22.3 (pre-22 snippet).*

```typescript
// components/a2ui-renderer/a2ui-renderer.component.ts

import { Component, ErrorHandler, computed, effect, inject, input, output, signal } from '@angular/core';
import { A2UIComponentDef, A2UIValue, SurfaceState, UserAction } from '../../models/a2ui.model';
import { A2UICatalogService } from '../../services/a2ui-catalog.service';
import { A2UISanitizerService } from '../../services/a2ui-sanitizer.service';

/** Deeper trees and any component that appears among its own ancestors render a placeholder. */
const MAX_DEPTH = 32;

@Component({
  selector: 'app-a2ui-renderer',
  imports: [A2UIRendererComponent],
  template: `
    @let comp = getComponent();
    @if (problem()) {
      <p class="text-sm text-base-content/70" role="note">This content can't be displayed.</p>
    } @else if (comp) {
      @switch (comp.type) {

        @case ('Column') {
          <div class="flex flex-col gap-2" [class.items-center]="comp.alignment === 'center'"
               [class.items-start]="comp.alignment === 'start'" [class.items-end]="comp.alignment === 'end'">
            @for (childId of explicitChildIds(); track childId) {
              <app-a2ui-renderer [surface]="surface()" [componentId]="childId"
                [depth]="depth() + 1" [ancestors]="lineage()"
                (actionTriggered)="actionTriggered.emit($event)" />
            }
          </div>
        }

        @case ('Row') {
          <div class="flex flex-row gap-2 flex-wrap" [class.justify-center]="comp.alignment === 'center'"
               [class.justify-start]="comp.alignment === 'start'" [class.justify-end]="comp.alignment === 'end'">
            @for (childId of explicitChildIds(); track childId) {
              <app-a2ui-renderer [surface]="surface()" [componentId]="childId"
                [depth]="depth() + 1" [ancestors]="lineage()"
                (actionTriggered)="actionTriggered.emit($event)" />
            }
          </div>
        }

        @case ('Card') {
          <div class="card bg-base-100 shadow-md mb-4">
            <div class="card-body">
              @if (comp.child) {
                <app-a2ui-renderer [surface]="surface()" [componentId]="comp.child"
                  [depth]="depth() + 1" [ancestors]="lineage()"
                  (actionTriggered)="actionTriggered.emit($event)" />
              }
            </div>
          </div>
        }

        @case ('Text') {
          @switch (comp.usageHint) {
            @case ('h1') { <h1 class="text-4xl font-bold">{{ resolveText(comp.text) }}</h1> }
            @case ('h2') { <h2 class="text-3xl font-bold">{{ resolveText(comp.text) }}</h2> }
            @case ('h3') { <h3 class="text-2xl font-semibold">{{ resolveText(comp.text) }}</h3> }
            @case ('h4') { <h4 class="text-xl font-semibold">{{ resolveText(comp.text) }}</h4> }
            @case ('h5') { <h5 class="text-lg font-medium">{{ resolveText(comp.text) }}</h5> }
            @case ('h6') { <h6 class="text-base font-medium">{{ resolveText(comp.text) }}</h6> }
            @case ('caption') { <p class="text-sm text-base-content/60">{{ resolveText(comp.text) }}</p> }
            @default { <p>{{ resolveText(comp.text) }}</p> }
          }
        }

        @case ('Image') {
          @if (safeUrl(comp.url); as src) {
            <img [src]="src" alt="" class="max-w-full max-h-64 object-contain rounded-lg" />
          }
        }

        @case ('Icon') {
          <span class="material-icons">{{ resolveText(comp.name) }}</span>
        }

        @case ('Button') {
          <button [class]="comp.primary ? 'btn btn-primary' : 'btn'"
                  (click)="onAction(comp, componentId())">
            @if (comp.child) {
              <app-a2ui-renderer [surface]="surface()" [componentId]="comp.child"
                [depth]="depth() + 1" [ancestors]="lineage()"
                (actionTriggered)="actionTriggered.emit($event)" />
            }
          </button>
        }

        @case ('TextField') {
          <!-- daisyUI 5: inputs are bordered by default; label[for] names the control -->
          @let fieldId = 'a2ui-' + surface().surfaceId + '-' + componentId();
          <div class="flex w-full flex-col gap-1">
            @if (comp.label) {
              <label class="label" [for]="fieldId">{{ resolveText(comp.label) }}</label>
            }
            @if (comp.textFieldType === 'longText') {
              <textarea class="textarea w-full" [id]="fieldId"></textarea>
            } @else {
              <input class="input w-full" [id]="fieldId"
                     [type]="comp.textFieldType === 'email' ? 'email' : 'text'"
                     [placeholder]="resolveText(comp.label)" />
            }
          </div>
        }

        @case ('Checkbox') {
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" class="checkbox" />
            <span>{{ resolveText(comp.label) }}</span>
          </label>
        }

        @case ('DateTimeInput') {
          <input class="input"
                 [type]="comp.enableDate && comp.enableTime ? 'datetime-local' : comp.enableDate ? 'date' : 'time'" />
        }

        @case ('Divider') {
          @if (comp.axis === 'vertical') {
            <div class="divider divider-horizontal"></div>
          } @else {
            <div class="divider"></div>
          }
        }

        @case ('List') {
          <ul class="menu bg-base-200 rounded-box">
            @for (childId of explicitChildIds(); track childId) {
              <li>
                <app-a2ui-renderer [surface]="surface()" [componentId]="childId"
                  [depth]="depth() + 1" [ancestors]="lineage()"
                  (actionTriggered)="actionTriggered.emit($event)" />
              </li>
            }
          </ul>
        }

        @case ('Tabs') {
          @let tabs = asTabs(comp);
          <div role="tablist" class="tabs tabs-box">
            @for (tab of tabs; track tab.child; let i = $index) {
              <button type="button" role="tab" class="tab" [class.tab-active]="i === selectedTab()"
                      [attr.aria-selected]="i === selectedTab()" [attr.tabindex]="i === selectedTab() ? 0 : -1"
                      (click)="selectedTab.set(i)" (keydown)="onTabKey($event, tabs.length)">{{ resolveText(tab.title) }}</button>
            }
          </div>
          @if (tabs[selectedTab()]; as active) {
            <div role="tabpanel">
              <app-a2ui-renderer [surface]="surface()" [componentId]="active.child"
                [depth]="depth() + 1" [ancestors]="lineage()"
                (actionTriggered)="actionTriggered.emit($event)" />
            </div>
          }
        }

        @case ('Modal') {
          @if (comp.entryPointChild) {
            <app-a2ui-renderer [surface]="surface()" [componentId]="comp.entryPointChild"
              [depth]="depth() + 1" [ancestors]="lineage()"
              (actionTriggered)="actionTriggered.emit($event)" />
          }
        }

      }
    }
  `,
})
export class A2UIRendererComponent {
  surface = input.required<SurfaceState>();
  componentId = input.required<string>();
  depth = input(0);
  ancestors = input<ReadonlySet<string>>(new Set());
  actionTriggered = output<UserAction>();

  private catalog = inject(A2UICatalogService);
  private sanitizer = inject(A2UISanitizerService);
  private errorHandler = inject(ErrorHandler);

  readonly selectedTab = signal(0);
  readonly lineage = computed(() => new Set([...this.ancestors(), this.componentId()]));

  /** Why this node is not rendered, or null. Unknown type, dangling id, cycle and depth all show a placeholder. */
  readonly problem = computed(() => {
    const id = this.componentId();
    if (this.depth() > MAX_DEPTH || this.ancestors().has(id)) return `cycle or depth > ${MAX_DEPTH} at "${id}"`;
    const comp = this.surface().componentMap.get(id);
    if (!comp) return `missing component "${id}"`;
    if (!this.catalog.isAllowed(comp.type)) return `component type "${comp.type}" is not in the catalog`;
    return null;
  });

  getComponent = computed(() => (this.problem() ? null : this.surface().componentMap.get(this.componentId()) ?? null));

  constructor() {
    effect(() => {
      const problem = this.problem();
      if (problem) this.errorHandler.handleError(new Error(`A2UI: ${problem}`)); // logged, never silent
    });
  }

  // For Row, Column, List: children via explicitList
  explicitChildIds = computed(() => {
    const comp = this.getComponent();
    if (!comp?.children) return [];
    return 'explicitList' in comp.children ? comp.children.explicitList : [];
  });

  resolveText(value: A2UIValue | undefined): string {
    if (!value) return '';
    if ('path' in value) {
      const data = this.surface().dataModel[value.path as string];
      if (data != null) return this.sanitizer.sanitizeText(String(data));
      // Fall back to literalString default if path resolves to nothing
      if ('literalString' in value) return this.sanitizer.sanitizeText(value.literalString as string);
      return '';
    }
    if ('literalString' in value) return this.sanitizer.sanitizeText(value.literalString as string);
    return '';
  }

  safeUrl(value: A2UIValue | undefined): string {
    const text = value && 'literalString' in value ? (value.literalString as string) : '';
    return this.sanitizer.sanitizeUrl(text);
  }

  onTabKey(event: KeyboardEvent, count: number): void {
    if (count === 0 || (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft')) return;
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = (this.selectedTab() + step + count) % count;
    this.selectedTab.set(next);
    const tablist = (event.currentTarget as HTMLElement).closest('[role="tablist"]');
    tablist?.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  }

  asTabs(comp: A2UIComponentDef): { title: A2UIValue; child: string }[] {
    return Array.isArray(comp.tabItems) ? comp.tabItems as { title: A2UIValue; child: string }[] : [];
  }

  onAction(comp: A2UIComponentDef, componentId: string): void {
    if (!comp.action?.name) return;
    const action = comp.action;
    this.actionTriggered.emit({
      name: action.name,
      surfaceId: this.surface().surfaceId,
      sourceComponentId: componentId,
      timestamp: new Date().toISOString(),
      context: Object.fromEntries(
        (action.context ?? []).map(c => [c.key, this.resolveActionValue(c.value)]),
      ),
    });
  }

  private resolveActionValue(value: A2UIValue): unknown {
    if ('path' in value) return this.surface().dataModel[value.path as string];
    if ('literalString' in value) return value.literalString;
    return null;
  }
}
```

> Chat page component, streaming variant, and wire format reference are in `a2ui-chat-template.md`.
