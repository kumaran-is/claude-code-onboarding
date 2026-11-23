# Tailwind v4 Patterns & Configuration

> **When to use**: Setting up Tailwind CSS v4 in Angular 21.x, implementing container queries, creating OKLCH daisyUI themes, building Bento layouts, or migrating from v3 patterns
> **Time estimate**: 30–60 min for new setup; 1–2 hours for v3→v4 migration with existing components
> **Prerequisites**: Angular project scaffolded; `@angular/core` 21.x installed

## Overview

Configure and use Tailwind CSS v4 in Angular 21.x projects. Covers CSS-first `@theme {}` configuration (no `tailwind.config.js`), container queries for context-responsive components, OKLCH custom daisyUI themes, Bento/asymmetric dashboard grid layouts, and safe migration from v3 patterns. Uses the `tailwind-patterns` skill and `angular-spa` skill in tandem.

---

## Iron Law (from `skills/tailwind-patterns/SKILL.md`)

> **USE `@theme {}` IN CSS — NOT `tailwind.config.js`**
> Never use `@tailwind base/components/utilities` (v3 directives). Always use daisyUI semantic tokens in Angular templates.

---

## Phases

### Phase 1 — Load Skills

**Skills to load**:
- `tailwind-patterns` — v4 CSS-first config, container queries, OKLCH, layout patterns
- `angular-spa` — Angular-specific implementation, daisyUI v5.5.5 reference files

**Cross-check**: After loading both skills, verify they reference the same Tailwind v4 setup. If there is any conflict, `angular-spa` takes precedence for Angular-specific configuration.

**Reference file**: Read `angular-spa/reference/tailwind-v4-config.md` before writing any styles.

---

### Phase 2 — Identify the Task

Determine which phase applies before proceeding:

- New project setup → Phase 3 (Configure)
- Container query implementation → Phase 4 (Container Queries)
- Custom daisyUI theme with OKLCH → Phase 5 (Theming)
- Bento/asymmetric grid layout → Phase 5 (Theming) + Phase 4 (Container Queries)
- v3→v4 migration → Anti-patterns table in `tailwind-patterns` skill §11

---

### Phase 3 — Configure Tailwind v4

**Verify `.postcssrc.json` exists** (not `postcss.config.js`, which the Angular builder ignores):
```json
{
  "plugins": {
    "@tailwindcss/postcss": {}
  }
}
```

**Verify global styles use v4 import** (`src/styles.css`; keep Tailwind and daisyUI directives in a plain `.css` file, not Sass):
```css
/* v4 — correct. Every @import comes first; legacy CSS goes into the base layer */
@import "tailwindcss";

/* Define custom tokens in @theme — NOT in tailwind.config.js */
@theme {
  --color-brand-primary: oklch(55% 0.22 260);
  --color-brand-secondary: oklch(70% 0.18 180);
  --font-sans: "Inter", sans-serif;
  --spacing-section: 4rem;
}

/* daisyUI plugin (custom "brand" theme defined in Phase 5) */
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}
```

Never name spacing tokens `--spacing-sm/md/lg/xl`: they shadow `max-w-sm/md/lg/xl` (`--spacing-section` above is safe).

**Symptom of a wrong PostCSS setup:** `ng build` succeeds, but the output CSS contains `@plugin "daisyui"` verbatim and no `.btn-primary` rule. Check with `grep -c 'btn-primary' dist/*/browser/styles-*.css` (verified: `.postcssrc.json` → classes emitted; `postcss.config.js` only → 0 classes, `@plugin` left in output).

**Verify no v3 directives remain**:
```css
/* v3 — FORBIDDEN in v4 projects */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Gate**: Run `ng build` and verify zero Tailwind errors before moving on.

---

### Phase 4 — Implement Container Queries

Container queries respond to the parent container size, not the viewport. Use them for components that render in variable-width columns.

**Parent wrapper** — add `@container`:
```html
<div class="@container">
  <div class="grid grid-cols-1 @sm:grid-cols-2 @lg:grid-cols-3 gap-4">
    <!-- children respond to container width, not viewport -->
  </div>
</div>
```

**Named containers** — use when nested containers would conflict:
```html
<div class="@container/sidebar">
  <nav class="flex-col @sm/sidebar:flex-row">...</nav>
</div>
```

**Available breakpoints** (Tailwind v4 defaults):
| Prefix | Container min-width |
|--------|-------------------|
| `@xs:` | 20rem (320px) |
| `@sm:` | 24rem (384px) |
| `@md:` | 28rem (448px) |
| `@lg:` | 32rem (512px) |
| `@xl:` | 36rem (576px) |

**Test**: Resize the parent container element (not the browser viewport) and verify the layout responds correctly.

---

### Phase 5 — Custom daisyUI Theme with OKLCH

**Define theme in global styles** (`src/styles.css`; daisyUI 5 syntax. The v4 `themes: [{ brand: {…} }]` object is a build error):
```css
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}

@plugin "daisyui/theme" {
  name: "brand";
  default: false;
  prefersdark: false;
  color-scheme: light;

  --color-primary: oklch(55% 0.22 260);
  --color-primary-content: oklch(98% 0.01 260);
  --color-secondary: oklch(70% 0.18 180);
  --color-secondary-content: oklch(10% 0.02 180);
  --color-accent: oklch(80% 0.20 85);
  --color-accent-content: oklch(10% 0.02 85);
  --color-base-100: oklch(98% 0.005 240);
  --color-base-200: oklch(94% 0.008 240);
  --color-base-300: oklch(88% 0.010 240);
  --color-base-content: oklch(20% 0.02 240);
}
```

Each `--color-X` / `--color-X-content` pair must reach 4.5:1; re-run axe `color-contrast` for the theme (muted text floor: `ui-standards-tokens/reference/ui-design-tokens.md`).

**OKLCH format**: `oklch(lightness chroma hue)` — use https://oklch.com/ to pick values and verify they are in-gamut for sRGB.

**Apply theme** in `index.html`:
```html
<html data-theme="brand">
```

**Verify semantic tokens resolve** in Angular templates:
```html
<!-- Correct — semantic tokens -->
<button class="btn btn-primary">Save</button>
<div class="bg-base-100 text-base-content p-4">...</div>

<!-- Forbidden — primitive colors -->
<button class="bg-blue-500 text-white">Save</button>
```

**Test**: Toggle between light/dark/brand themes and verify all semantic tokens resolve correctly in each.

---

### Phase 6 — Verify

Run all gates before marking the task done:

```bash
# 1. Production build — zero errors
ng build --configuration=production

# 2. Design system lint — zero violations
# (no primitive colors, no raw spacing, no hardcoded hex values)
```

**Manual checks**:
- [ ] No `tailwind.config.js` file exists in the project root (v4 projects must not have one)
- [ ] No `@tailwind base`, `@tailwind components`, or `@tailwind utilities` directives remain
- [ ] All colors in Angular templates use daisyUI semantic tokens (`bg-primary`, `text-base-content`, `border-secondary`, etc.)
- [ ] All spacing uses Tailwind scale (`p-4`, `gap-6`) — no arbitrary values (`p-[16px]`) in production templates
- [ ] Container query parents have `@container` class; children use `@sm:` / `@md:` / `@lg:` prefixes

**Run `/lint-design-system`** — must return zero violations before proceeding to review.

**Agent**: Dispatch `ui-standards-expert` after Phase 6 to review design token compliance across all changed component files.

---

## Quick Reference

| Phase | Action | Agent / Command | Gate |
|-------|--------|----------------|------|
| 1 — Load Skills | `tailwind-patterns` + `angular-spa` skills | — | Both skills loaded; no config conflict |
| 2 — Identify | Determine task type | — | Correct phase selected |
| 3 — Configure | `@theme {}` in CSS, `.postcssrc.json` | — | `ng build` zero errors |
| 4 — Container Queries | `@container` parent, `@sm:` children | — | Layout responds to container resize |
| 5 — Theming | OKLCH tokens in `@plugin "daisyui/theme"` | — | All themes render; semantic tokens resolve |
| 6 — Verify | `/lint-design-system`, production build | `ui-standards-expert` | Zero violations; zero build errors |

---

## Common Pitfalls

- **Using `tailwind.config.js` alongside `@theme {}`** — v3 config file conflicts with v4 CSS-first setup; remove the config file entirely
- **Using `@tailwind base/components/utilities`** — v3 directives; replace with `@import "tailwindcss"` in v4
- **Primitive colors in Angular templates** (`bg-blue-500`, `text-gray-700`) — use daisyUI semantic tokens (`bg-primary`, `text-base-content`) for theme-awareness
- **Container query children without `@container` on the parent** — `@sm:` prefixes are silently ignored if no `@container` ancestor exists
- **OKLCH values outside sRGB gamut** — use https://oklch.com/ to verify values before committing; out-of-gamut colors display incorrectly in some browsers
- **`postcss.config.js` instead of `.postcssrc.json`** — the Angular builder ignores it; the build passes and emits no Tailwind/daisyUI classes
- **Unlayered global CSS** — an unlayered reset beats every utility (`px-6` computes to 0); import it with `@import "./legacy.css" layer(base);`
- **daisyUI 4 class names** (`input-bordered`, `form-control`, `label-text`, `btn-group`) — emit nothing in daisyUI 5; see `/lint-design-system`
- **`dark:` utilities with a `data-theme` toggle** — `dark:` follows the OS unless you declare `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));`
- **`tailwind.config.js` left as an orphan** — if migrating from v3, delete the config file after migrating all tokens to `@theme {}`; leaving both causes unpredictable merge behavior

## Related Workflows

- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular 21.x feature development end-to-end
- [`web-performance-optimization.md`](web-performance-optimization.md) — Angular Core Web Vitals, bundle size
- [`design-system-compliance.md`](design-system-compliance.md) — design token enforcement; accessibility (WCAG 2.2 AA) via `accessibility-auditor`
