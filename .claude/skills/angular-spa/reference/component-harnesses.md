# Angular Component Harnesses — Testing UI Interactions

Component harnesses (from `@angular/cdk/testing`) provide a stable testing API that abstracts away DOM details. Use them when testing component interactions in Angular 22.

## When to use harnesses vs direct DOM queries

| Scenario | Use |
|---|---|
| Testing Angular Material / CDK components | Harness (stable API) |
| Testing your own components in isolation | Direct `fixture.nativeElement` |
| Testing component interactions (click, input) | Harness or `HarnessLoader` |
| Checking rendered text or CSS | Direct query (harness is overkill) |

## Setup

```typescript
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { HarnessLoader } from '@angular/cdk/testing';
```

## Writing a Custom Harness for your component

```typescript
// button.harness.ts
import { ComponentHarness } from '@angular/cdk/testing';

export class AppButtonHarness extends ComponentHarness {
  static hostSelector = 'app-button';

  private getButton = this.locatorFor('button');
  private getLabel = this.locatorForOptional('.btn-label');

  async click(): Promise<void> {
    const button = await this.getButton();
    await button.click();
  }

  async getText(): Promise<string> {
    const label = await this.getLabel();
    return label ? label.text() : '';
  }

  async isDisabled(): Promise<boolean> {
    const button = await this.getButton();
    return button.getProperty<boolean>('disabled');
  }

  async isLoading(): Promise<boolean> {
    const host = await this.host();
    return host.hasClass('loading');
  }
}
```

## Using a harness in tests

```typescript
// button.component.spec.ts
import { TestBed, ComponentFixture } from '@angular/core/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { HarnessLoader } from '@angular/cdk/testing';
import { AppButtonComponent } from './button.component';
import { AppButtonHarness } from './button.harness';

describe('AppButtonComponent', () => {
  let fixture: ComponentFixture<AppButtonComponent>;
  let loader: HarnessLoader;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppButtonComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(AppButtonComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
    fixture.detectChanges();
  });

  it('should click button and emit', async () => {
    const harness = await loader.getHarness(AppButtonHarness);
    const emitted: void[] = [];
    fixture.componentInstance.clicked.subscribe(() => emitted.push());

    await harness.click();
    
    expect(emitted.length).toBe(1);
  });

  it('should show loading state', async () => {
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();

    const harness = await loader.getHarness(AppButtonHarness);
    expect(await harness.isLoading()).toBe(true);
  });
});
```

## HarnessLoader for finding child harnesses

```typescript
describe('DataTableComponent', () => {
  let loader: HarnessLoader;

  beforeEach(async () => {
    // ... setup
    loader = TestbedHarnessEnvironment.loader(fixture);
  });

  it('should find all row harnesses', async () => {
    const rows = await loader.getAllHarnesses(TableRowHarness);
    expect(rows.length).toBe(3);
  });

  it('should find harness in child component', async () => {
    const childLoader = await loader.getChildLoader('.data-table-footer');
    const pager = await childLoader.getHarness(PaginatorHarness);
    await pager.goToNextPage();
    // assert page changed
  });
});
```

## Harness for signal-based component

```typescript
// search-bar.harness.ts
export class SearchBarHarness extends ComponentHarness {
  static hostSelector = 'app-search-bar';

  private getInput = this.locatorFor('input[type="search"]');
  private getClearButton = this.locatorForOptional('button[aria-label="Clear search"]');

  async typeQuery(query: string): Promise<void> {
    const input = await this.getInput();
    await input.clear();
    await input.sendKeys(query);
  }

  async getQuery(): Promise<string> {
    const input = await this.getInput();
    return input.getProperty<string>('value');
  }

  async clear(): Promise<void> {
    const btn = await this.getClearButton();
    if (!btn) throw new Error('Clear button not present — is query empty?');
    await btn.click();
  }

  async isClearVisible(): Promise<boolean> {
    return !!(await this.getClearButton());
  }
}
```

## Anti-patterns

```typescript
// ❌ Fragile — breaks if DOM structure changes
const button = fixture.nativeElement.querySelector('.btn-primary');
button.click();

// ✅ Stable — harness abstracts DOM
const harness = await loader.getHarness(AppButtonHarness);
await harness.click();

// ❌ Mixing async/sync in harness tests
harness.click(); // forgot await
fixture.detectChanges();

// ✅ Always await harness methods
await harness.click();
fixture.detectChanges();
```

## Install

```bash
npm install @angular/cdk
```

Harness testing requires `@angular/cdk/testing` — already included if you use Angular CDK.
