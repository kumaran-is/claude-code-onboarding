# WCAG 2.2 AA Checklist (canonical, web + Flutter)

This is the single accessibility checklist for the workspace. Other files link here; they do not keep their own copy.
Platform depth lives in: `angular-a11y-automated.md` (web tests), `flutter-a11y-automated.md` (Flutter tests), `manual-testing-checklist.md` (screen-reader and zoom scripts), and `flutter-mobile/reference/accessibility-audit-checklist.md` (Flutter widget specifics).

**Bar:** WCAG 2.2 Level AA. 4.1.1 Parsing is obsolete in 2.2; do not cite it.

**Evidence rule:** automated tools (axe, pa11y, `flutter_test` guidelines) never prove conformance. They catch only part of the issues. In axe-core 4.14.1, `getRules(['wcag22aa'])` returns only `target-size` (2.5.8), and `wcag22a` returns nothing, so axe checks none of the other new 2.2 criteria. A clean automated run is reported as "no automated violations; manual checks required", never as "compliant".

## 1. Target size policy (read this first)

| Requirement | Value | Status |
|---|---|---|
| WCAG 2.5.8 Target Size (Minimum), AA | ≥ 24×24 CSS px, or enough spacing that a 24 px circle on each target does not overlap another | **Normative.** Below this is a WCAG failure |
| WCAG 2.5.5 Target Size (Enhanced), AAA | ≥ 44×44 CSS px | Not required for AA |
| House standard, web (Angular/React) | ≥ 44×44 CSS px for primary controls | Recommendation. Report a miss as MEDIUM, not as a WCAG failure, if it is ≥ 24 px |
| Platform guideline, Flutter | 48×48 dp Android (`androidTapTargetGuideline`), 44×44 pt iOS (`iOSTapTargetGuideline`) | Platform recommendation, asserted in widget tests |

Exceptions under 2.5.8: inline links in a sentence, a size set by the user agent, and a target whose small size is essential.

## 2. Checklist by criterion

Severity guide: **CRITICAL** = blocks a task for a user group; **HIGH** = a WCAG A/AA failure with a workaround; **MEDIUM** = an AA failure with low impact, or a house-standard miss; **ADVISORY** = best practice, not a WCAG failure (never blocks a merge).

| SC (level) | Web (Angular / React) | Flutter (Android / iOS) | Automatable? |
|---|---|---|---|
| 1.1.1 Non-text content (A) | `alt` on informative images, `alt=""` on decorative ones; icon-only buttons carry `aria-label`, and the SVG has `aria-hidden="true"` | `Semantics(label:)` / `semanticLabel`; decorative images use `excludeFromSemantics: true` | Partly (axe `image-alt`, `button-name`) |
| 1.3.1 Info and relationships (A) | Native elements (`button`, `a[href]`, `label for`, `fieldset/legend`, `th scope`, landmarks) before ARIA | `Semantics(header: true)`, `MergeSemantics` for label+control | Partly |
| 1.3.5 Identify input purpose (AA) | `autocomplete` tokens on personal-data fields (`email`, `name`, `tel`, `street-address`) | `autofillHints` | Partly (axe `autocomplete-valid`) |
| 1.4.1 Use of colour (A) | Status and errors carry text or an icon, not only colour | Same | No |
| 1.4.3 Contrast (AA) | ≥ 4.5:1 for body text, ≥ 3:1 for large text (≥ 24 px, or ≥ 18.66 px bold). Measure light **and** dark themes in a real browser (jsdom cannot compute contrast). daisyUI 5 defaults (axe, Chromium): muted text floor `text-base-content/60` on `base-100`, `/70` on `base-300`; light `text-error` on `base-100` is 2.87:1 (fails), so error text uses body colour plus an "Error:" prefix (table: `ui-standards-tokens/reference/ui-design-tokens.md`) | Same ratios; test both `ThemeData` brightness values | Yes, in a real browser |
| 1.4.4 Resize text (AA) | 200 % zoom: nothing clips or overlaps | System font scale at the largest setting: no truncation of amounts, status or actions | No |
| 1.4.10 Reflow (AA) | 320 CSS px wide (= 1280 px at 400 %): no 2-D scrolling except data tables, maps and code | n/a (use font-scale and small-device checks) | No |
| 1.4.11 Non-text contrast (AA) | Focus rings, input borders and icons ≥ 3:1 against adjacent colours | Same | Partly |
| 1.4.12 Text spacing (AA) | Content survives line-height 1.5, letter-spacing 0.12em and word-spacing 0.16em (no fixed-height text boxes) | n/a | No |
| 1.4.13 Content on hover or focus (AA) | Tooltips are dismissible (Esc), hoverable and persistent; essential info is never hover-only (Tailwind 4 `hover:` only fires on hover-capable devices) | n/a | No |
| 2.1.1 Keyboard (A) | Every action is reachable with Tab, Enter and Space; no `div (click)` without a role, `tabindex="0"` and key handlers (prefer `<button>`) | Hardware keyboard and switch access: `FocusTraversalGroup`, `Shortcuts`/`Actions` | Partly |
| 2.1.2 No keyboard trap (A) | Focus can always leave a widget; modals contain focus only while open | Same | Scripted Playwright test |
| 2.2.1 Timing adjustable (A) | A toast with an action (Undo, Retry) does not auto-dismiss, or pauses on hover and focus; session timeouts warn and extend | `SnackBar` with an action: `persist: true`, or a long enough duration | No |
| 2.2.2 Pause, stop, hide (A) | Anything that moves for more than 5 s (carousels, marquees) has a pause control | Same | No |
| 2.3.1 Three flashes (A) | No content flashes more than 3 times per second | Same | No |
| 2.4.1 Bypass blocks (A) | A skip link to `<main id="main-content" tabindex="-1">` | n/a | Partly |
| 2.4.2 Page titled (A) | A unique `<title>` per route (Angular: route `title` or a `TitleStrategy`; React: set `document.title` per route) | `Semantics(scopesRoute/namesRoute)` on routes | Partly |
| 2.4.3 Focus order (A) | DOM order matches visual order; no positive `tabindex`. **SPA route change:** move focus to the new view's `<h1 tabindex="-1">` (or `<main>`) after navigation completes; do not move focus for query-string or fragment-only changes. **Dialogs:** see §3 | Focus order follows reading order; `FocusTraversalOrder` only when needed | Scripted Playwright test |
| 2.4.6 Headings and labels (AA) | Headings and labels describe their purpose. "Exactly one h1" and "no skipped levels" are ADVISORY | Same | Partly |
| 2.4.7 Focus visible (AA) | Never `outline: none` without a replacement; use `:focus-visible` styles | Focus highlight visible in both themes | Partly |
| **2.4.11 Focus not obscured (Min) (AA) — new in 2.2** | Sticky headers, footers, cookie bars and toasts never *fully* hide the focused element. Use `scroll-padding-top` equal to the sticky header height, and keep toasts out of the focus path | Keyboard and bottom sheets do not cover the focused field (scroll it into view) | No (scripted check) |
| 2.5.3 Label in name (A) | The accessible name contains the visible label text (do not override "Save" with `aria-label="Submit form"`) | Same | Partly (axe `label-content-name-mismatch`) |
| **2.5.7 Dragging movements (AA) — new** | Every drag (reorder, slider, map pan, swipe-to-dismiss) has a single-pointer alternative: buttons, a menu, or arrow keys | `ReorderableListView` plus move up/down actions; `Semantics(customSemanticsActions:)` | No |
| **2.5.8 Target size (Min) (AA) — new** | See §1: ≥ 24×24 CSS px | See §1 | Yes: axe `target-size` (tag `wcag22aa`) |
| 3.1.1 / 3.1.2 Language (A/AA) | `<html lang>` per locale; `lang` on inline foreign phrases; translate `aria-label`, alt text, titles and live messages too (see `design-system/reference/i18n-rtl-intl.md`) | `Locale` set; `Semantics` labels localised | Partly |
| 3.2.2 On input (A) | Changing a field does not submit, navigate or move focus unexpectedly | Same | No |
| **3.2.6 Consistent help (A) — new** | Help, contact or chat entry points appear in the same relative order on every page that has them | Same across screens | No |
| 3.3.1 / 3.3.3 Error identification and suggestion (A/AA) | A visible `<label>` (a placeholder is not a label); `aria-invalid="true"` plus `aria-describedby` pointing to the error text; on submit, show a summary that links to the fields and move focus to the first invalid field or the summary | `InputDecoration(errorText:)`; announce the error | Partly |
| 3.3.2 Labels or instructions (A) | The required state is shown in text and with the native `required` attribute; `aria-label` on a `<span>` is ignored (generic role), so do not use it to mark "required" | `Semantics(label: '… required')` | Partly |
| **3.3.7 Redundant entry (A) — new** | Do not ask for data already entered in the same process; pre-fill it or offer "same as billing" | Same | No |
| **3.3.8 Accessible authentication (Min) (AA) — new** | No cognitive test (memorise, transcribe, solve) is the only login path. Allow paste and password managers: `autocomplete="username"`, `"current-password"`, `"new-password"`, `"one-time-code"`; never block `paste` | `autofillHints: [AutofillHints.password]`; allow paste; support platform passkeys and biometrics | Partly (lint for blocked `paste` and missing `autocomplete`) |
| 4.1.2 Name, role, value (A) | Custom widgets expose role, name and state (`aria-expanded`, `aria-selected`, `aria-pressed`); prefer native elements, then vetted headless primitives | `Semantics(button: true, toggled:, selected:)` | Partly |
| 4.1.3 Status messages (AA) | Async results use a persistent `aria-live="polite"` region that exists before the message is inserted; errors use `role="alert"` sparingly | `SemanticsService.announce` (once), or `liveRegion: true` | Partly |
| Reduced motion (2.3.3 is **AAA**; AA motion duties are 2.2.2 and 2.3.1) | Honour `prefers-reduced-motion` per animation: remove movement, keep meaning (opacity and state changes stay) | `MediaQuery.disableAnimationsOf(context)` | No |

## 3. Pattern rules that reviewers check most

- **Native dialog (web).** Open a modal `<dialog>` with `showModal()`. In Chromium this gives initial focus inside the dialog, makes the background inert, closes on Esc and returns focus to the opener (verified with Playwright). Do not add `role="dialog"` to `<dialog>`. Do not hand-roll focus return. `show()` (non-modal) leaves the background focusable; use it only for non-modal panels. Use a focus trap (CDK `cdkTrapFocus`, or an equivalent) only for non-native overlays. Test Tab, Shift+Tab and Esc, and assert that focus returns to the opener.
- **Composite widgets.** Prefer native semantics, then a maintained headless library (Angular CDK or `@angular/aria`, which is a developer preview in v21; React Aria or Radix). Do not write `div role="button" tabindex="0"` dropdown triggers: use `<button>`, `<details>/<summary>` or the popover API.
- **Loading regions.** Use `aria-busy="true"` on the region, one visually hidden "Loading <thing>" label, `aria-hidden="true"` on skeleton bars, and one completion announcement. Never re-announce on a background refresh. Full contract: `design-system/reference/interaction-contracts.md` §6b.
- **Forced colours (web).** Check Windows High Contrast with `@media (forced-colors: active)`: focus rings and borders must stay visible.

## 4. Required manual checks (record each as PASS / FAIL / NOT RUN)

| # | Check | Web | Flutter mobile |
|---|---|---|---|
| M1 | Keyboard-only walk of every changed flow (Tab, Shift+Tab, Enter, Space, Esc, arrows) | Required | Hardware keyboard or switch access, where the app supports it |
| M2 | Screen-reader smoke test | NVDA + Firefox or Chrome (Windows) **and** VoiceOver + Safari (macOS) | TalkBack (Android) **and** VoiceOver (iOS) |
| M3 | Zoom and text size | 200 % text, 400 % zoom | Largest system font scale |
| M4 | Reflow | 320 CSS px wide viewport | Smallest supported device |
| M5 | Both themes | Light and dark contrast | Light and dark |
| M6 | Reduced motion | `prefers-reduced-motion: reduce` | OS "remove animations" |
| M7 | New 2.2 criteria | 2.4.11 (sticky UI), 2.5.7 (drag alternatives), 3.2.6, 3.3.7, 3.3.8 | Same |

Scripts and commands for each: `manual-testing-checklist.md`.

## 5. Tooling by target (canonical rule: `.claude/rules/testing-tool-selection.md`)

| Target | Automated | Notes |
|---|---|---|
| Angular / React web | Playwright + `@axe-core/playwright` with `.withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'])` | Without `wcag22aa`, 16 px icon buttons pass (verified). Component-level axe in jsdom or happy-dom cannot evaluate `color-contrast` |
| Flutter Android / iOS | `flutter test` with `meetsGuideline(androidTapTargetGuideline)`, `iOSTapTargetGuideline`, `labeledTapTargetGuideline` and `textContrastGuideline`; UI/E2E flows with **Maestro** | Never a browser, a Flutter Web build or a resized viewport as evidence about the mobile app |
