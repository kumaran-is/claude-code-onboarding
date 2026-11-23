# Accessibility Audit

> **When to use**: After building any web (Angular, React) or Flutter UI — before PR review, or when auditing against WCAG 2.2 AA
> **Time estimate**: 30–60 min automated setup; 1–2 hours for a full manual audit session
> **Prerequisites**: Web or Flutter UI written; Playwright e2e (web) or `test/accessibility/` (Flutter) directory created
> **Skill**: `accessibility-audit`

## Overview

5-phase audit pipeline: automated scan → agent review → manual checks → remediation → CI/CD gate. The bar is WCAG 2.2 AA; the canonical checklist is `.claude/skills/accessibility-audit/reference/wcag22-checklist.md`. The read-only `accessibility-auditor` agent reviews web (Angular, React) and Flutter; `ui-standards-expert` covers tokens and interaction contracts (no accessibility verdicts). Works for Angular 22.x, React and Flutter 3.50.x. Tool choice per target: `.claude/rules/testing-tool-selection.md` (Flutter Android/iOS device flows use Maestro only).

**Evidence rule:** automated results never prove conformance. Report a clean run as "no automated violations; manual checks required", and record each manual check as PASS / FAIL / NOT RUN.

---

## When to Use vs. Related Workflows

| Situation | Workflow |
|-----------|----------|
| UI component just built — quick a11y pass | This workflow (Phase 1 + 2 only) |
| Full feature audit before PR | This workflow (all phases) |
| Design token violations | [`design-system-compliance.md`](design-system-compliance.md) |
| Security audit | [`security-audit.md`](security-audit.md) |
| Full pre-merge gate | [`pr-shipping.md`](pr-shipping.md) |
| E2E browser testing | [`browser-e2e-testing.md`](browser-e2e-testing.md) |

---

## Phase 1 — Automated Scan

**Skill**: Load `accessibility-audit` (`.claude/skills/accessibility-audit/SKILL.md`)

### Web (Angular / React) — Playwright + axe-core

```bash
# Install (one-time setup; pin the versions your lockfile resolves)
npm install --save-dev @playwright/test @axe-core/playwright axe-core

# Run the Playwright axe suite (tags include wcag22aa)
npm run test:a11y

# Optional second engine, with the axe runner
npx pa11y-ci --config .pa11yci.json
```

**Reference**: `.claude/skills/accessibility-audit/reference/angular-a11y-automated.md`

What axe catches automatically (with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`):
- Missing alt text on images; icon-only buttons without a name
- Form inputs without any accessible name (a `placeholder` counts as a name for axe, so a missing visible label is **not** caught)
- Color contrast (1.4.3), in a real browser only (jsdom cannot compute it)
- Target size below 24×24 CSS px (2.5.8), only when `wcag22aa` is included
- Missing `lang` attribute on `<html>`

What axe does **not** catch: keyboard traps and focus order (use the scripted Playwright tests in `angular-a11y-automated.md` §3), route-change focus, focus not obscured (2.4.11), dragging alternatives (2.5.7), consistent help (3.2.6), redundant entry (3.3.7), accessible authentication (3.3.8), and anything a screen reader user hears.

### Flutter — flutter_test SemanticsController

```bash
# Run accessibility widget tests
flutter test test/accessibility/ --reporter=expanded
```

**Reference**: `.claude/skills/accessibility-audit/reference/flutter-a11y-automated.md`

What flutter_test catches:
- Interactive elements without `Semantics(label:)`
- Missing button semantics
- Text overflow at 2x font scale
- Tap targets below the platform guidelines (`androidTapTargetGuideline` 48×48 dp, `iOSTapTargetGuideline` 44×44 pt)
- Text contrast (`textContrastGuideline`) and labelled tap targets (`labeledTapTargetGuideline`)

Device-level flows (navigation, dialogs, TalkBack/VoiceOver smoke tests) run on an emulator, simulator or device with **Maestro**, never a browser.

**Gate**: Zero automated violations before proceeding to Phase 2. This is not a conformance claim.

---

## Phase 2 — Agent: `accessibility-auditor`

**Agent**: `accessibility-auditor` (read-only WCAG 2.2 AA review, web and Flutter)

Dispatch after the automated scan passes. The agent detects the target from file types and checks against:
- `.claude/skills/accessibility-audit/reference/wcag22-checklist.md` (canonical, web + Flutter)
- `.claude/skills/flutter-mobile/reference/accessibility-audit-checklist.md` (Flutter widget depth)

It reports severity + file:line + remediation, lists the manual checks still open, and ends with `VERDICT: NO BLOCKING FINDINGS | FINDINGS | BLOCK`. It never outputs "compliant".

**Angular findings the agent checks:**

```html
<!-- ❌ CRITICAL — icon button without label -->
<button class="btn btn-circle"><mat-icon>delete</mat-icon></button>

<!-- ✅ FIX — aria-label on icon-only button -->
<button class="btn btn-circle" aria-label="Delete order ORD-001">
  <mat-icon aria-hidden="true">delete</mat-icon>
</button>

<!-- ❌ CRITICAL — form input without label -->
<input type="email" placeholder="Email" />

<!-- ✅ FIX — visible associated label, native required, autocomplete token -->
<label class="label" for="email">Email address</label>
<input id="email" class="input" type="email" required autocomplete="email" />

<!-- ❌ IMPORTANT — no live region for dynamic content -->
<div>{{ orderStatus() }}</div>

<!-- ✅ FIX — live region -->
<div aria-live="polite" aria-atomic="true">{{ orderStatus() }}</div>
```

**Flutter findings the agent checks:**

```dart
// ❌ CRITICAL — icon without semantic label
IconButton(icon: Icon(Icons.delete), onPressed: _deleteOrder)

// ✅ FIX — tooltip becomes the button's semantics tooltip (read by screen readers) and shows on long press
IconButton(
  icon: const Icon(Icons.delete),
  tooltip: 'Delete order',
  onPressed: _deleteOrder,
)

// ❌ IMPORTANT — fixed height clips at 200% text scale
SizedBox(height: 40, child: Text(title))

// ✅ FIX — flexible height
ConstrainedBox(
  constraints: const BoxConstraints(minHeight: 40),
  child: Text(title),
)
```

**Color contrast**: >= 4.5:1 for normal text, >= 3:1 for large text (>= 24 CSS px, or >= 18.66 px bold), in light and dark themes

**Target size**: >= 24×24 CSS px is the WCAG 2.5.8 AA requirement. 44 px (web) and 48 dp (Flutter Android) are house/platform recommendations; a miss that is still >= 24 px is MEDIUM, not a WCAG failure.

---

## Phase 3 — Manual Testing

**Reference**: `.claude/skills/accessibility-audit/reference/manual-testing-checklist.md`

Run in this order — each takes 5–10 minutes:

### 3a. Keyboard (Both Platforms)

1. Tab through the entire UI — every interactive element must receive focus
2. Activate each element with Enter or Space
3. Open any modal — focus moves inside, the page behind is inert, Esc closes and focus returns to the trigger
4. No keyboard trap anywhere
5. Web: after each route change, the title changes and focus lands on the new view's heading or `<main>`
6. Sticky headers, toasts and cookie bars never fully cover the focused element (2.4.11)

### 3b. Screen Reader

| Platform | Tool | Shortcut |
|----------|------|---------|
| macOS (web, Safari) / iOS | VoiceOver | Cmd+F5 |
| Windows (web, Firefox or Chrome) | NVDA | Free download |
| Android | TalkBack | Hold both volume keys |

Minimum: one screen reader per platform you ship (web: NVDA **and** VoiceOver; mobile: TalkBack **and** VoiceOver).

Navigate by headings -> navigate to forms -> trigger errors -> confirm announcements.

### 3c. Visual

```bash
# In Chrome DevTools -> Rendering tab:
# - Enable "Emulate CSS media feature prefers-color-scheme"
# - Enable "Emulate CSS media feature prefers-contrast: more"
# - Enable "Emulate CSS media feature forced-colors: active"
# Zoom to 200% (text) and 400% / 320 CSS px wide — verify no overflow or 2-D scrolling
# Enable grayscale — verify all information still conveyed
```

### 3d. Cognitive and new 2.2 criteria

- Every error message says what went wrong AND how to fix it
- Destructive actions (delete, cancel) have a confirmation step
- No form loses user input without warning
- Navigation order is consistent across all screens; help/contact appears in the same place (3.2.6)
- Data already entered in the flow is not asked for again (3.3.7)
- Login allows paste and password managers; no cognitive-test-only step (3.3.8)
- Every drag has a button or keyboard alternative (2.5.7)

Record each row as PASS / FAIL / NOT RUN.

**Gate**: No CRITICAL findings. HIGH findings documented with file:line and fix.

---

## Phase 4 — Remediation and Re-test

For each CRITICAL or HIGH finding:

1. Apply exact code fix (file:line)
2. Re-run automated scan: `npm run test:a11y` or `flutter test test/accessibility/`
3. Confirm finding no longer appears
4. Add regression test to prevent recurrence

**Regression test pattern (Angular, Vitest + axe-core; contrast is checked in Playwright)**:
```typescript
import { TestBed } from '@angular/core/testing';
import axe from 'axe-core';
import { OrderList } from './order-list';

it('delete button has an accessible name', async () => {
  const fixture = TestBed.createComponent(OrderList);
  await fixture.whenStable();
  const results = await axe.run(fixture.nativeElement, { runOnly: { type: 'rule', values: ['button-name'] } });
  expect(results.violations).toEqual([]);
});
```

**Regression test pattern (Flutter)**:
```dart
// import 'package:material_ui/material_ui.dart';  (material.dart is deprecated since Flutter 3.47)
testWidgets('delete button is an announced, tappable button', (tester) async {
  final handle = tester.ensureSemantics();
  await tester.pumpWidget(const MaterialApp(home: OrderListScreen()));
  // isSemantics checks only the properties given; containsSemantics is deprecated (3.40)
  // and matchesSemantics fails on every flag you leave out. IconButton.tooltip lands in
  // the node's tooltip, not its label.
  expect(
    tester.getSemantics(find.byTooltip('Delete order')),
    isSemantics(tooltip: 'Delete order', isButton: true, hasTapAction: true),
  );
  handle.dispose();
});
```

---

## Phase 5 — CI/CD Gate

Add automated a11y tests to the existing CI pipeline.

**Reference**: `.claude/skills/accessibility-audit/reference/cicd-integration.md`

```yaml
# Add to existing .github/workflows/ci.yml
- name: Run accessibility tests
  run: npm run test:a11y  # Angular
  # or: flutter test test/accessibility/  # Flutter
```

**Gate rule**: `--threshold 0` (pa11y) and `expect(violations).toEqual([])` (axe). Any automated violation fails the PR. No exceptions without explicit justification in PR description. A green gate is "no automated violations", not conformance.

---

## Quick Reference

| Phase | Action | Tool | Gate |
|-------|--------|------|------|
| 1 — Automated | Playwright + axe (`wcag22aa`) (web) / flutter_test guidelines (Flutter) | CLI | Zero automated violations |
| 2 — Agent | WCAG 2.2 AA code review (web + Flutter) | `accessibility-auditor` | No CRITICAL/HIGH (`VERDICT` ≠ BLOCK) |
| 3 — Manual | Keyboard, screen reader, zoom/reflow, forced colours, new 2.2 criteria | Human + DevTools / devices | Each row PASS; NOT RUN rows listed |
| 4 — Remediate | Fix findings, add regression tests | Code + tests | All CRITICAL/HIGH resolved |
| 5 — CI/CD | Automated gate on every PR | GitHub Actions | Build green |

---

## Common Pitfalls

- **Axe passes but screen reader fails** — axe catches structural violations; screen reader testing catches announcement timing and reading order
- **Fixing the symptom not the cause** — adding `aria-label` to a `<div>` when it should be a `<button>`
- **Decorative images missed** — `<img>` without `alt=""` fails axe; Flutter `Image` without `ExcludeSemantics` adds noise to screen readers
- **Focus not returning after modal close** — must explicitly return focus to the trigger element
- **Cognitive check skipped** — automated tools cannot catch unhelpful error messages or missing confirmation dialogs
- **Re-test skipped after fix** — mark finding as resolved only after re-running the automated scan

## Related Workflows

- [`design-system-compliance.md`](design-system-compliance.md) — token enforcement + accessibility combined gate
- [`feature-angular-spa.md`](feature-angular-spa.md) — Phase 7 runs `accessibility-auditor` as part of feature workflow
- [`feature-flutter-mobile.md`](feature-flutter-mobile.md) — Phase 5 runs `accessibility-auditor` as part of feature workflow
- [`browser-e2e-testing.md`](browser-e2e-testing.md) — E2E flows include keyboard navigation as part of user journey
- [`clean-code-review.md`](clean-code-review.md) — code quality baseline before a11y review
