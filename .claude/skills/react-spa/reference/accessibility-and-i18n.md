# Accessibility and i18n

> RECOMMENDED PRACTICE. Target WCAG 2.2 AA. Canonical checklist: `accessibility-audit` skill
> (`reference/wcag22-checklist.md`, `reference/manual-testing-checklist.md`); its
> `reference/angular-a11y-automated.md` axe + Playwright patterns apply unchanged to React.
> i18n/RTL/Intl canonical reference: `design-system/reference/i18n-rtl-intl.md`.
> Automated scans never prove conformance: report "no automated violations; manual checks required".

## What the validation app proves (Chromium, 375 and 1280 px)

- axe (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) reports no violations on the list, the
  open dialog with validation errors, and the error state.
- Planted violations are detected: low-contrast text → `color-contrast`; an unnamed icon button →
  `button-name`; `<img>` without `alt` → ESLint `jsx-a11y-x/alt-text`.
- Dialog: Escape closes it and focus returns to the opener; the first invalid field receives focus.

## React specifics

| Topic | Do |
|---|---|
| Semantics | `<button>` for actions, `<a href>`/`<Link>` for navigation; never `div onClick` |
| Labels | `<label htmlFor>` with ids from `useId()`; placeholders are not labels |
| Errors | `aria-invalid` + `aria-describedby` to the error text; form-level failure in `role="alert"` |
| Async states | loading in `role="status"`, failure in `role="alert"` (see `ProjectList`) |
| Route change | move focus to `<main tabIndex={-1}>` or the page `<h1>`; one `<h1>` per page; set `document.title` per route |
| Dialogs | native `<dialog>` + `showModal()`; `aria-labelledby` to its heading; focus returns to the opener |
| Targets | at least 24×24 CSS px (WCAG 2.2 AA 2.5.8); this toolkit's web baseline is 44 px (`code-standards.md`) |
| Focus visible | do not remove outlines without a visible replacement; sticky headers must not hide focused elements (2.4.11) |
| Motion | respect `prefers-reduced-motion` |
| Lint | `eslint-plugin-jsx-a11y-x` `configs.recommended` (0.2.0, ESLint 10; see `tooling.md`) |

## i18n basics

- Set `<html lang>` (and `dir="rtl"` for RTL locales); update both when the locale changes.
- Format with `Intl` (`Intl.DateTimeFormat`, `Intl.NumberFormat`, `Intl.PluralRules`,
  `Intl.RelativeTimeFormat`) and the active locale; never concatenate translated fragments.
- Use logical CSS properties (`margin-inline-start`, `padding-inline`) so RTL works without overrides.
- Keep strings in message catalogs keyed by id; a library such as `react-i18next` (18.x) with `i18next`
  (27.x) is a common choice — **UNVERIFIED in this app; check before use**.
- Test at 200% zoom and with long translations (layouts must wrap, not clip).
