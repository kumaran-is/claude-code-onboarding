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

## Styling stack (verified 2026-11-24)

The React stack styles with **Tailwind CSS v4 + shadcn/ui** (Base UI primitives): semantic tokens
(`--background`, `--foreground`, `--muted-foreground`, `--destructive`, ...) in OKLCH under `:root` and
`.dark`, mapped to utilities by `@theme inline`. The full `src/index.css`, theme provider and evidence are in
`reference/tailwind-shadcn.md`; token naming and tiers stay framework-neutral in the `ui-standards-tokens`
skill.

Accessibility consequences verified in Chromium at 375 and 1280 px:

- axe (`wcag2a`…`wcag22aa`) reports no violations in light **and** dark mode, on the page, with the dialog
  open and with the menu open. A planted dark `--muted-foreground: oklch(0.32 0 0)` fails `color-contrast`
  in the two dark tests only.
- The shadcn default light `--destructive` (`oklch(0.577 0.245 27.325)`) fails `color-contrast` for
  `text-destructive` on `bg-destructive/10`; the reference app darkens it to `oklch(0.505 0.2 27.5)`. Fix a
  failing token in `index.css`, never per component.
- The base layer keeps 44 px controls (`button`, `[role="button"]`, `[role="menuitem"]`, `[role="menuitemradio"]`, inputs; a new item role
  must be added there, and the theme-menu E2E test measures it). The
  `:focus-visible` outline is unlayered (shadcn's `outline-none` utility beats `@layer base`) and asserted by a
  computed-style test, because axe does not check focus indicators; reduced motion collapses animations and view transitions.
- Axe can flag `color-contrast` on a menu that is still fading in: wait for finite animations before a scan
  (`e2e/support.ts` in `testing.md`).

## React specifics

| Topic | Do |
|---|---|
| Semantics | `<button>` for actions, `<a href>`/`<Link>` for navigation; never `div onClick` |
| Labels | `<label htmlFor>` with ids from `useId()`; placeholders are not labels |
| Errors | `aria-invalid` + `aria-describedby` to the error text; form-level failure in `role="alert"` |
| Async states | loading in `role="status"`, failure in `role="alert"` (see `ProjectList`) |
| Route change | move focus to `<main tabIndex={-1}>` or the page `<h1>`; one `<h1>` per page; set `document.title` per route |
| Dialogs | shadcn `Dialog` (Base UI) with a `DialogTitle`: focus trap, Escape, focus returns to the opener (asserted in Chromium; jsdom cannot test Tab trapping). Without a component library: native `<dialog>` + `showModal()` |
| Targets | at least 24×24 CSS px (WCAG 2.2 AA 2.5.8); this toolkit's web baseline is 44 px (`code-standards.md`) |
| Focus visible | do not remove outlines without a visible replacement; sticky headers must not hide focused elements (2.4.11) |
| Motion | respect `prefers-reduced-motion` (token collapse above; test with `emulateMedia({ reducedMotion: 'reduce' })`) |
| Lint | `eslint-plugin-jsx-a11y-x` `configs.recommended` (0.2.0, ESLint 10; see `tooling.md`) |

## i18n basics

- Set `<html lang>` (and `dir="rtl"` for RTL locales); update both when the locale changes.
- Format with `Intl` (`Intl.DateTimeFormat`, `Intl.NumberFormat`, `Intl.PluralRules`,
  `Intl.RelativeTimeFormat`) and the active locale; never concatenate translated fragments.
- Use logical CSS properties (`margin-inline-start`, `padding-inline`) so RTL works without overrides.
- Keep strings in message catalogs keyed by id; a library such as `react-i18next` (18.x) with `i18next`
  (27.x) is a common choice — **UNVERIFIED in this app; check before use**.
- Test at 200% zoom and with long translations (layouts must wrap, not clip).
