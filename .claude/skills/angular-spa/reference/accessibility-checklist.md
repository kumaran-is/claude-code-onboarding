# Accessibility — Angular pointer (WCAG 2.2 AA)

The canonical WCAG 2.2 AA checklist, manual test protocol and automated checks live in the
`accessibility-audit` skill:

- Checklist: `../../accessibility-audit/reference/wcag22-checklist.md`
- Manual protocol: `../../accessibility-audit/reference/manual-testing-checklist.md`
- axe + Playwright for Angular: `../../accessibility-audit/reference/angular-a11y-automated.md`
- i18n, RTL and `Intl` formatting: `../../design-system/reference/i18n-rtl-intl.md`

Automated tools never prove conformance: report "no automated violations; manual checks required".

## Angular-only notes

- Route changes: give every route a `title` and move focus to the new `<h1>` — `angular-aria.md`
  §Route-change focus management (compiled + tested).
- Dialogs: use the native `<dialog>` element opened with `showModal()` (daisyUI `modal`), or CDK
  `Dialog`. Do not add `role="dialog"` to a `<dialog>` — the role is implicit. Label it with
  `aria-labelledby`, return focus to the trigger on close.
- Dynamic results (filter, sort, save): `LiveAnnouncer` or a `role="status"` region; failures in
  `role="alert"` (`angular-ui-patterns`).
- Field errors: `aria-invalid` + `aria-describedby` pointing at the message; do not rely on colour
  (`text-error` alone fails AA contrast on the default light theme — see `daisyui-v5-components.md`).
- Icon-only buttons need `aria-label`; prefer native `<button>`, `<a routerLink>`, `<details>` over
  `div role="button"`.
- Target size: WCAG 2.2 AA minimum 24×24 CSS px; house standard 44×44 px for web touch targets.
- Motion: `prefers-reduced-motion` handled in `angular-animations.md`.
