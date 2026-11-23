---
name: ui-visual-validator
description: "Visual regression in CI (Playwright visual, Chromatic, Percy, Applitools, BackstopJS) and a pre-PR visual verification checklist for web targets. Use when setting up screenshot-diff pipelines. Final evidence gate → reality-checker agent; Flutter mobile → Maestro."
risk: low
source: community (adapted for workspace)
date_added: "2026-02-27"
updated: "2026-03-15"
allowed-tools: Read, Bash
metadata:
  triggers: visual regression, screenshot testing, visual diff, Chromatic, Percy, Applitools, BackstopJS, Playwright visual, visual testing CI, pixel diff, visual QA, UI looks wrong, before and after screenshot
  related-skills: browser-testing, accessibility-audit, web-design-guidelines, design-system
  domain: quality
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-03-15"
---

## Iron Law

**DO NOT REPLACE `reality-checker` — USE IT FIRST for live browser screenshots and binary APPROVED/NEEDS WORK verdict. This skill adds: (1) visual regression tooling setup for CI/CD pipelines, (2) the 13-item mandatory verification checklist for systematic pre-PR checks, (3) automated screenshot diff configuration. Use both together.**

# UI Visual Validator

> Systematic visual verification methodology + CI/CD visual regression tooling. Skeptic-first: the modification goal has NOT been achieved until proven with visual evidence.

## Scope vs `reality-checker`

| Capability | `reality-checker` agent | `ui-visual-validator` (this skill) |
|---|---|---|
| Live browser screenshot | ✅ Chrome DevTools MCP | ❌ (use reality-checker for this) |
| Binary APPROVED/NEEDS WORK verdict | ✅ | ❌ (defer to reality-checker) |
| Visual regression tool setup (CI/CD) | ❌ | ✅ Chromatic, Percy, Applitools, BackstopJS |
| GitHub Actions visual diff workflow | ❌ | ✅ |
| 13-item mandatory verification checklist | ❌ | ✅ |
| Accessibility visual compliance checklist | ❌ | ✅ |
| Pre-commit systematic analysis protocol | ❌ | ✅ |

**Workflow:** Run `ui-visual-validator` checklist → gather screenshots → pass to `reality-checker` for final verdict.

## When to Use This Skill

- **Setting up** Chromatic, Percy, or Playwright Visual in a CI/CD pipeline
- **Before a PR** that touches Angular components or Flutter screens — run through the 13-item checklist
- **Investigating** "it looks different on CI than locally" — visual regression diagnosis
- **New Angular component** needs visual baseline established for regression testing
- **Flutter screen** needs screenshot test added to CI

## When NOT to Use This Skill

- For live browser screenshots — use `browser-testing` skill + Chrome DevTools MCP
- For the final APPROVED/NEEDS WORK gate — use `reality-checker` agent
- For WCAG compliance audit — use `accessibility-audit` skill

---

## Core Principle

> The modification goal has NOT been achieved until proven by visual evidence.
> Ignore code hints. Base judgments solely on visual output.

**Forbidden behaviors:**
- Assuming code changes automatically produce correct visual results
- Quick conclusions without systematic analysis
- Accepting "looks different" as "looks correct"
- Using expectation to replace direct observation

**Required output format (when performing visual analysis):**
Always start with: *"From the visual evidence, I observe..."*

---

## 13-Item Mandatory Verification Checklist

Run through ALL 13 items before declaring a UI change complete:

### Structural
- [ ] **1. Objective description** — Described actual visual content without assumptions?
- [ ] **2. Goal verification** — Compared each element against stated modification goals systematically?
- [ ] **3. Measurement validation** — For rotation/position/size changes: verified through actual visual measurement (not assumed from code)?

### Visual Quality
- [ ] **4. Responsive breakpoints** — Verified at 320px (WCAG 1.4.10 reflow floor = 400 % zoom), 375px, 768px, 1024px, 1440px?
- [ ] **5. Dark/light mode** — Both themes validated (if applicable)?
- [ ] **6. Loading and transition states** — Skeleton/spinner shown correctly? Transitions smooth?
- [ ] **7. Error and edge cases** — Empty states, error states, disabled states all verified?

### Accessibility (Visual)
- [ ] **8. Color contrast** — WCAG 4.5:1 minimum for normal text verified visually?
- [ ] **9. Focus indicators** — Visible focus rings on interactive elements?
- [ ] **10. Touch targets** — Interactive elements ≥ 24×24 CSS px (WCAG 2.5.8 AA); house standard 44px (web) / 48dp (Flutter)?

### Design System
- [ ] **11. Token compliance** — No hardcoded colors visible that should use semantic tokens?
- [ ] **12. Design system alignment** — Component matches design system spec?

### Regression
- [ ] **13. Reverse validation** — Actively looked for evidence the modification FAILED (not just succeeded)?

---

## Visual Regression Tool Setup

### Option 1: Playwright Visual (Recommended for Angular)

```bash
# Install
npm install -D @playwright/test

# angular.json — add e2e target
```

```typescript
// visual.spec.ts
import { test, expect } from '@playwright/test';

test('dashboard visual regression', async ({ page }) => {
  await page.goto('/dashboard');
  // Wait for content, not 'networkidle' (discouraged: polling, SSE and analytics keep the network busy)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  // Full page snapshot. maxDiffPixelRatio = share of pixels allowed to differ (0.01 = 1 %);
  // threshold = per-pixel colour tolerance (YIQ, default 0.2), NOT a percentage of pixels.
  await expect(page).toHaveScreenshot('dashboard.png', {
    fullPage: true,
    maxDiffPixelRatio: 0.01,
    animations: 'disabled',
  });
});

test('mobile breakpoint', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/dashboard');
  await expect(page).toHaveScreenshot('dashboard-mobile.png');
});
```

```yaml
# .github/workflows/visual-regression.yml
name: Visual Regression
on: [pull_request]
jobs:
  visual-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx ng build --configuration=production
      - run: npx playwright test --reporter=html
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-visual-report
          path: playwright-report/
```

### Option 2: Chromatic (Storybook-based, component-level)

```bash
npm install --save-dev chromatic
npx chromatic --project-token=<token> --auto-accept-changes main
```

```yaml
# GitHub Actions
- name: Publish to Chromatic
  uses: chromaui/action@latest
  with:
    projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
    onlyChanged: true  # Only test changed components
```

**Best for:** Angular component libraries with Storybook stories.

### Option 3: BackstopJS (Config-based, no Storybook needed)

```bash
npm install -g backstopjs
backstop init
```

```json
// backstop.json
{
  "viewports": [
    { "label": "mobile", "width": 375, "height": 812 },
    { "label": "tablet", "width": 768, "height": 1024 },
    { "label": "desktop", "width": 1440, "height": 900 }
  ],
  "scenarios": [
    {
      "label": "Dashboard",
      "url": "http://localhost:4200/dashboard",
      "selectors": ["#main-content"],
      "delay": 500,
      "misMatchThreshold": 0.1
    }
  ],
  "engine": "playwright"
}
```

```bash
backstop reference  # Create baseline screenshots
backstop test       # Compare against baseline
backstop approve    # Approve changes as new baseline
```

### Option 4: Percy (Cross-browser, cloud-based)

```bash
npm install --save-dev @percy/cli @percy/playwright
```

```typescript
// In Playwright test
import percySnapshot from '@percy/playwright';

test('dashboard', async ({ page }) => {
  await page.goto('/dashboard');
  await percySnapshot(page, 'Dashboard');
});
```

---

## Flutter Visual Testing

```dart
// test/golden/dashboard_golden_test.dart — golden file testing with flutter_test only
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:your_app/features/dashboard/dashboard_screen.dart';

void main() {
  const devices = {'phone': Size(390, 844), 'tablet': Size(820, 1180)};
  const states = {
    'default': DashboardScreen(),
    'loading': DashboardScreen(isLoading: true),
  };

  for (final MapEntry(key: device, value: size) in devices.entries) {
    for (final MapEntry(key: state, value: screen) in states.entries) {
      testWidgets('DashboardScreen $state on $device', (tester) async {
        // Fixed surface: the render must not depend on the machine.
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(MaterialApp(home: screen));
        // Not pumpAndSettle: a progress indicator never settles.
        await tester.pump();

        await expectLater(
          find.byType(DashboardScreen),
          matchesGoldenFile('goldens/dashboard_${state}_$device.png'),
        );
      });
    }
  }
}
```

`matchesGoldenFile` ships with `flutter_test`, so no extra dependency is needed. `golden_toolkit` is discontinued on pub.dev (last release 0.15.0, 2023-02): it still resolves but gets no fixes, so do not add it. For multi-scenario grids or cross-platform tolerance use `alchemist`; the canonical guidance is `flutter-mobile/reference/flutter-testing-patterns.md` §5.

```bash
# Generate golden files (baseline)
flutter test --update-goldens

# Run comparison
flutter test
```

---

## Analysis Protocol

When performing visual analysis:

1. **Describe first** — What is literally visible? (shapes, colors, positions, text)
2. **Verify goals** — Does each element match the stated change?
3. **Measure** — For rotation/size/position: measure actual pixels, don't estimate
4. **Reverse-validate** — What would failure look like? Is that what I see?
5. **Accessibility** — Is contrast sufficient? Are focus rings visible?
6. **Cross-platform** — Same breakpoints, same themes?
7. **Edge cases** — Long text, empty states, error states?
8. **Conclude** — "From the visual evidence, I observe [X]. The goal [is/is not] achieved because [Y]."

---

## How This Fits the Review Stack

| Layer | Tool | What It Catches |
|---|---|---|
| **Layer 1 — Design tokens** | `/lint-design-system` | Hardcoded colors, raw spacing |
| **Layer 2 — WCAG** | `accessibility-auditor` agent | Contrast, ARIA, keyboard nav |
| **Layer 3 — Interaction patterns** | `web-design-guidelines` | Loading/empty/error states |
| **Layer 4 — Live screenshot** | `reality-checker` agent | Binary pass/fail with visual evidence |
| **Layer 5 — CI regression** | `ui-visual-validator` (this skill) | Baseline regression, cross-browser |

---

## Related Skills and Agents

- `reality-checker` agent — **run BEFORE this skill** for live browser verdict (Chrome DevTools MCP)
- `browser-testing` skill — Chrome DevTools MCP + Browser-Use for live UI interaction
- `accessibility-audit` skill — canonical WCAG 2.2 AA checklist (beyond visual checks); visual checks never establish conformance
- `web-design-guidelines` skill — Vercel Web Interface Guidelines audit (loading/error/empty state patterns)
- `design-system` skill — token compliance enforcement

## Additional Resources

- [Playwright Visual Comparisons](https://playwright.dev/docs/test-screenshots)
- [Chromatic Docs](https://www.chromatic.com/docs/)
- [BackstopJS GitHub](https://github.com/garris/BackstopJS)
- [Flutter golden tests (`matchesGoldenFile`)](https://api.flutter.dev/flutter/flutter_test/matchesGoldenFile.html)
- [Percy Docs](https://docs.percy.io/)
