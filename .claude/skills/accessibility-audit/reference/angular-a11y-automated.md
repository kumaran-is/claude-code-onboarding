# Web Automated Accessibility Testing (Angular 21.x; patterns also apply to React)

Automated accessibility tests for web targets. The criteria they check are defined in [wcag22-checklist.md](wcag22-checklist.md). Tool choice per target: `.claude/rules/testing-tool-selection.md` (web → Playwright; Flutter mobile → `flutter test` + Maestro, never a browser).

**What a green run means:** "no automated violations; manual checks required". axe-core 4.14 automates only one new 2.2 criterion (`target-size`, 2.5.8) and accepts a `placeholder` as an accessible name, so a passing run never establishes WCAG conformance. Record the manual checks (checklist §4) as PASS / FAIL / NOT RUN.

Verified in this repo's validation sandbox: Playwright 1.65.1 + `@axe-core/playwright` 4.14.0 (axe-core 4.14.1) in Chromium; Angular 21.2 with its default Vitest runner.

## 1. Playwright + axe (primary gate, real browser)

```bash
npm install --save-dev @playwright/test @axe-core/playwright   # pin the versions your lockfile resolves
```

```typescript
// e2e/a11y.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const WCAG22_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

for (const path of ['/', '/orders', '/orders/new']) {
  test(`no automated WCAG 2.2 AA violations: ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(WCAG22_AA).analyze();
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
}

test('dark theme contrast', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  const results = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();
  expect(results.violations).toEqual([]);
});
```

- **Include `wcag22aa`.** Without it, 16×16 px icon buttons produce zero violations; with it, axe reports `target-size` (verified). 24×24 px buttons pass.
- Use the `page` fixture from `@playwright/test`. Outside the test runner, create the page with `browser.newContext()` then `context.newPage()`: `@axe-core/playwright` throws "Please use browser.newContext()" for a page from `browser.newPage()`.
- Scan each meaningful state (dialog open, error shown, empty state), not only the initial load.
- `.exclude()` is for third-party widgets you do not control; record each exclusion with a reason.

## 2. Component-level checks (Vitest, jsdom)

Angular 21 runs unit tests with Vitest by default. Call `axe-core` directly on the rendered element. jsdom has no layout or computed colours, so **disable `color-contrast`** there and check contrast in Playwright (§1).

```typescript
// order-form.spec.ts
import { TestBed } from '@angular/core/testing';
import axe from 'axe-core';
import { OrderForm } from './order-form';

describe('OrderForm accessibility', () => {
  it('has no automated WCAG 2.2 AA violations (contrast is checked in Playwright)', async () => {
    const fixture = TestBed.createComponent(OrderForm);
    await fixture.whenStable();
    const results = await axe.run(fixture.nativeElement, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] },
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});
```

## 3. Keyboard, dialog and route-change tests

```typescript
// e2e/keyboard.spec.ts
import { test, expect } from '@playwright/test';

test('modal dialog: focus moves in, Esc closes, focus returns to the opener', async ({ page }) => {
  await page.goto('/dashboard');
  const opener = page.getByRole('button', { name: 'Details' });
  await opener.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => !!document.activeElement?.closest('dialog'))).toBe(true);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => !!document.activeElement?.closest('dialog'))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test('route change moves focus to the new view heading and updates the title', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Orders' }).click();
  await expect(page).toHaveTitle(/Orders/);
  await expect(page.locator('main h1')).toBeFocused();
});

test('skip link moves focus to main content', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: /skip to main content/i })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
});
```

`getByRole('dialog')` matches a native `<dialog>`; do not add `role="dialog"` to it. A `<dialog>` opened with `showModal()` keeps focus inside, makes the page inert, closes on Esc and returns focus to the opener (verified in Chromium).

## 4. Headings (ADVISORY, not a WCAG failure)

"Exactly one `h1`" and "no skipped levels" are best practice. Empty headings are a 2.4.6 failure. Report the rest as ADVISORY so they never block a merge:

```typescript
test('headings: no empty headings (fail); outline issues are advisory', async ({ page }, testInfo) => {
  await page.goto('/');
  const levels = await page.$$eval('h1,h2,h3,h4,h5,h6', (hs) =>
    hs.map((h) => ({ level: Number(h.tagName[1]), empty: !h.textContent?.trim() })));
  expect(levels.filter((h) => h.empty)).toEqual([]);
  const skips = levels.filter((h, i) => i > 0 && h.level > levels[i - 1].level + 1).length;
  const h1s = levels.filter((h) => h.level === 1).length;
  if (skips > 0 || h1s !== 1) {
    testInfo.annotations.push({ type: 'advisory', description: `h1 count ${h1s}, skipped levels ${skips}` });
  }
});
```

## 5. Forced colours and reduced motion (CSS)

```css
/* styles.css: keep focus rings and control borders visible in Windows forced-colors mode */
@media (forced-colors: active) {
  :focus-visible { outline: 2px solid CanvasText; outline-offset: 2px; }
  .btn, .input, .select, .textarea { border: 1px solid ButtonText; }
}
```

Reduced motion: gate each animation (`motion-safe:` / `motion-reduce:` utilities, or `@media (prefers-reduced-motion: no-preference)` around keyframes) instead of a global `* { animation-duration: 0.01ms !important }`, which also breaks code waiting for `animationend`. AA motion duties are 2.2.2 (Pause, Stop, Hide) and 2.3.1 (Three Flashes); 2.3.3 is AAA. Details: `fixing-motion-performance` skill §8b.

## 6. Form pattern (daisyUI 5)

```html
<!-- order-form.html: visible label, native required, error linked to the field -->
<fieldset class="fieldset">
  <legend class="fieldset-legend">Item</legend>
  <label class="label" for="item-id">Item ID (required)</label>
  <input
    id="item-id"
    type="text"
    class="input"
    required
    autocomplete="off"
    [formControl]="itemIdControl"
    [attr.aria-invalid]="itemIdControl.invalid && itemIdControl.touched"
    aria-describedby="item-id-error"
  />
  @if (itemIdControl.invalid && itemIdControl.touched) {
    <p id="item-id-error" class="text-sm"><strong>Error:</strong> Enter a valid item ID (letters, numbers, hyphens only)</p>
  }
</fieldset>

<!-- Persistent live region: present in the DOM before any message is written -->
<div aria-live="polite" aria-atomic="true" class="sr-only">{{ statusMessage() }}</div>

<!-- Icon-only button: name on the button, icon hidden, at least 24×24 px (btn-sm is 32 px) -->
<button type="button" class="btn btn-circle btn-ghost btn-sm" aria-label="Remove item from cart">
  <svg aria-hidden="true" focusable="false">…</svg>
</button>
```

- **Do not put error text in `text-error` on the default light theme**: daisyUI 5.5.5 light `--color-error` on `base-100` measures 2.87:1 (axe, Chromium), an AA failure (1.4.3). Use body text colour with an "Error:" prefix (colour is then decorative, 1.4.1), or define a darker `--color-error` in a custom theme and re-measure. The dark theme passes.
- daisyUI 4 names (`form-control`, `label-text`, `label-text-alt`, `input-bordered`) generate no CSS in daisyUI 5.
- State "required" in visible text plus the native `required` attribute. `aria-label` on a `<span>` is ignored (generic role), and axe does not flag it, so automated scans will not catch that mistake.
- On submit, move focus to an error summary or the first invalid field.

## 7. pa11y (optional second engine)

pa11y's default runner is HTML_CodeSniffer, whose `WCAG2AA` standard predates 2.2. Run it with the axe runner, or rely on §1 as the gate. Coverage of the 2.2 criteria by pa11y runners is UNVERIFIED; check before relying on it.

```bash
# Run pa11y against built Angular app (port 4200)
npx pa11y http://localhost:4200 --runner axe --standard WCAG2AA --threshold 0 --reporter json > a11y-report.json

# Run against multiple routes
npx pa11y-ci --config .pa11yci.json

# .pa11yci.json
{
  "defaults": {
    "standard": "WCAG2AA",
    "runners": ["axe"],
    "threshold": 0,
    "timeout": 30000
  },
  "urls": [
    "http://localhost:4200",
    "http://localhost:4200/orders",
    "http://localhost:4200/orders/new",
    "http://localhost:4200/dashboard"
  ]
}
```
