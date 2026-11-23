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

## Styling stack (verified 2026-11-23, Vite 8.3.8)

The default React stack uses **CSS Modules + CSS custom-property tokens**: no CSS framework and no extra
dependency (Vite supports `*.module.css` natively and `vite/client` types the import). Token naming, tiers and
review rules are framework-neutral: `ui-standards-tokens` skill (`reference/ui-design-tokens.md`); do not
redefine them here.

`src/index.css`: tokens in `:root`, a dark set under `prefers-color-scheme`, motion collapsed under
`prefers-reduced-motion`; components use only `var(--…)`.

```css
:root {
  color-scheme: light dark;
  --color-bg: #ffffff;
  --color-fg: #1a1a1a;
  --color-muted: #4a4a4a;
  --color-accent: #0b57d0;
  --color-accent-fg: #ffffff;
  --color-danger: #b00020;
  --target-min: 44px;
  --duration-fast: 150ms;
  color: var(--color-fg);
  background: var(--color-bg);
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #121212;
    --color-fg: #ececec;
    --color-muted: #b8b8b8;
    --color-accent: #8ab4f8;
    --color-accent-fg: #0b1a33;
    --color-danger: #ff8a80;
  }
}
@media (prefers-reduced-motion: reduce) {
  :root { --duration-fast: 0ms; }
}
:focus-visible { outline: 3px solid var(--color-accent); outline-offset: 2px; }
```

`App.module.css` (imported as `import styles from './App.module.css'`, used as `className={styles.button}`):

```css
.button {
  min-height: var(--target-min);
  min-width: var(--target-min);
  padding-inline: 1rem;
  background: var(--color-accent);
  color: var(--color-accent-fg);
  transition: background-color var(--duration-fast) ease;
}
```

Verified in Chromium at 375 and 1280 px: axe (`wcag2a`…`wcag22aa`) reports no violations in light mode
and with `page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })`. Under reduced motion the
computed `transition-duration` is `0s`. A planted `#bbb` text on white fails `color-contrast`.

Tailwind is optional. Add it only when the design system is Tailwind-based: `tailwindcss` and
`@tailwindcss/vite` 4.3.5 (peer `vite ^5.2 || ^6 || ^7 || ^8`; registry-checked, not installed in the
validation app). Patterns live in the `tailwind-patterns` skill. Never ship two styling systems for the same
components.

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
