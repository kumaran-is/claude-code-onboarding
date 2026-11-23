---
name: tailwind-patterns
description: "Tailwind CSS v4 + daisyUI 5 patterns for Angular 21.x (and other web stacks) — CSS-first @theme tokens, cascade layers, container queries, OKLCH daisyUI 5 themes, dark mode via data-theme, RTL logical utilities, hover/pointer variants, and v3→v4 migration pitfalls. Load alongside angular-spa; setup (PostCSS config) lives in angular-spa/reference/tailwind-v4-config.md."
risk: low
source: community (adapted for Angular 21.x)
date_added: "2026-02-27"
updated: "2026-11-22"
last-reviewed: "2026-11-22"
metadata:
  triggers: tailwind, tailwind v4, @theme, daisyui theme, dark mode, data-theme, container query, oklch, cascade layer, rtl utilities
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
---

## Triggers

Load this skill when: configuring Tailwind v4, writing Angular templates with utility classes, migrating from Tailwind v3, implementing dark mode with daisyUI, or designing container-query-based layouts.

---

## Iron Law

**NO TAILWIND STYLING WITHOUT CHECKING THE PROJECT'S @theme CONFIGURATION FIRST — read the global CSS theme file before applying utility classes**

Load the project's CSS `@theme` configuration and verify daisyUI semantic tokens before writing any template classes.

# Tailwind CSS Patterns (v4 - 2025)

> Modern utility-first CSS with CSS-native configuration.

## When to Use

Use this skill when configuring Tailwind v4, using CSS-first theme and design tokens, implementing container queries, or applying modern Tailwind patterns in Angular 21.x templates.

---

## 1. Tailwind v4 Architecture

### What Changed from v3

| v3 (Legacy) | v4 (Current) |
|-------------|--------------|
| `tailwind.config.js` | CSS-based `@theme` directive |
| `tailwindcss` PostCSS plugin | `@tailwindcss/postcss` (Angular, via `.postcssrc.json`) or `@tailwindcss/vite`; Oxide engine |
| JIT mode | Native, always-on |
| Plugin system | CSS-native features |
| `@apply` directive | Still works, discouraged |

### v4 Core Concepts

| Concept | Description |
|---------|-------------|
| **CSS-first** | Configuration in CSS, not JavaScript |
| **Oxide Engine** | Rust-based compiler, much faster |
| **Native Nesting** | CSS nesting without PostCSS |
| **CSS Variables** | All tokens exposed as `--*` vars |

---

## 2. CSS-Based Configuration

### Theme Definition

```css
@theme {
  /* Colors - use semantic names */
  --color-primary: oklch(0.7 0.15 250);
  --color-surface: oklch(0.98 0 0);
  --color-surface-dark: oklch(0.15 0 0);

  /* Spacing: keep the single multiplier; p-4 = calc(var(--spacing) * 4) */
  --spacing: 0.25rem;
  --spacing-gutter: 1.5rem;   /* named extras use a prefix-free, non-size name */

  /* Typography */
  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

> **Never name spacing tokens `--spacing-xs/sm/md/lg/xl`.** Tailwind 4 resolves `max-w-md` through `--spacing-md` when it exists, so `max-w-md` compiles to `max-width: var(--spacing-md)` (1rem) and every `max-w-*` container collapses (verified, Tailwind 4.3.5). Use the default multiplier and non-size names (`--spacing-gutter`).

### Cascade layers: import legacy CSS into `base`

Tailwind 4 emits utilities inside `@layer utilities`. Any **unlayered** rule beats every layered rule regardless of specificity, so an unlayered reset such as `* { padding: 0 }` silently disables `px-6` (verified in Chromium: computed `padding-left` was `0px`; with `layer(base)` it was `24px`).

```css
/* styles.css: every @import comes first, before @plugin, @theme or any rule */
@import "tailwindcss";
@import "./legacy-global.css" layer(base);
@plugin "daisyui";
```

The same applies to Angular component host styles: a `:host { display: block }` is unlayered and wins over `hidden`. Put the responsive visibility on a wrapper (`<span class="hidden sm:inline-flex"><app-logo /></span>`), not on the host.

### When to Extend vs Override

| Action | Use When |
|--------|----------|
| **Extend** | Adding new values alongside defaults |
| **Override** | Replacing default scale entirely |
| **Semantic tokens** | Project-specific naming (primary, surface) |

---

## 3. Container Queries (v4 Native)

### Breakpoint vs Container

| Type | Responds To |
|------|-------------|
| **Breakpoint** (`md:`) | Viewport width |
| **Container** (`@container`) | Parent element width |

### Container Query Usage

| Pattern | Classes |
|---------|---------|
| Define container | `@container` on parent |
| Container breakpoint | `@sm:`, `@md:`, `@lg:` on children |
| Named containers | `@container/card` for specificity |

### Angular Example

```html
<!-- Angular component template -->
<div class="@container">
  <div class="card @sm:card-side @lg:grid @lg:grid-cols-2">
    <!-- Responds to parent width, not viewport -->
    <!-- Use when same component appears in sidebar AND full-width page -->
  </div>
</div>
```

### When to Use

| Scenario | Use |
|----------|-----|
| Page-level layouts | Viewport breakpoints |
| Component-level responsive | Container queries |
| Reusable Angular components | Container queries (context-independent) |

---

## 4. Responsive Design

### Breakpoint System

| Prefix | Min Width | Target |
|--------|-----------|--------|
| (none) | 0px | Mobile-first base |
| `sm:` | 640px | Large phone / small tablet |
| `md:` | 768px | Tablet |
| `lg:` | 1024px | Laptop |
| `xl:` | 1280px | Desktop |
| `2xl:` | 1536px | Large desktop |

### Mobile-First Principle

1. Write mobile styles first (no prefix)
2. Add larger screen overrides with prefixes
3. Example: `w-full md:w-1/2 lg:w-1/3`
4. Check every layout at **320 CSS px** (WCAG 1.4.10 Reflow, equal to 400 % zoom), then 375/768/1024/1440.

### Hover and touch

- Tailwind 4 wraps `hover:` in `@media (hover: hover)`, so it never fires on touch-only devices. Never put essential information or actions behind hover.
- Use `pointer-coarse:` to enlarge targets on touch screens (`pointer-coarse:p-3`). Target size policy: `accessibility-audit/reference/wcag22-checklist.md` §1.

### RTL-ready layout (logical utilities)

Use logical utilities so the layout mirrors under `dir="rtl"`: `ms-*`/`me-*` (not `ml-*`/`mr-*`), `ps-*`/`pe-*`, `start-*`/`end-*`, `text-start`/`text-end`, `border-s`/`border-e`, `rounded-s`/`rounded-e`. Mirror directional icons with `rtl:rotate-180`. Verified (Tailwind 4.3.5, Chromium): `ms-4` under `dir="rtl"` computes to `margin-right: 16px`. Set `dir` and `lang` on `<html>`; i18n details: `design-system/reference/i18n-rtl-intl.md`.

---

## 5. Dark Mode

The workspace standard is **daisyUI semantic colours switched by `data-theme` on `<html>`**. v3's `darkMode: 'class' | 'media' | 'selector'` config no longer exists in v4.

| Mechanism | Behaviour |
|---|---|
| daisyUI semantic classes (`bg-base-100`, `text-base-content`) | Swap automatically with `data-theme`. **Preferred**: no per-component dark CSS |
| Tailwind `dark:` variant, default | Follows `@media (prefers-color-scheme: dark)`: **ignores** a `data-theme` toggle (verified: compiled output is wrapped in the media query) |
| Tailwind `dark:` variant + `@custom-variant` | Follows `data-theme`: declare it once in `styles.css` (below) |

```css
@import "tailwindcss";
@plugin "daisyui" { themes: light --default, dark --prefersdark; }
/* only if you also use dark: utilities */
@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));
```

```typescript
// theme.service.ts: set the attribute on <html> via DOCUMENT (SSR-safe; a component
// template cannot bind attributes on <html> because the root component lives in <body>)
import { DOCUMENT, Injectable, inject } from '@angular/core';

export type Theme = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly doc = inject(DOCUMENT);

  setTheme(theme: Theme): void {
    this.doc.documentElement.setAttribute('data-theme', theme);
    this.doc.defaultView?.localStorage.setItem('theme', theme); // a preference only; never store sensitive data here
  }
}
```

**Prevent the theme flash.** The service runs after bootstrap, so the first paint uses the default theme. Add a tiny blocking script in `index.html` `<head>` that sets `data-theme` before paint. Under a strict CSP, allow it with a `'sha256-…'` hash, not `'unsafe-inline'`.

```html
<script>
  var t = localStorage.getItem('theme');
  if (t !== 'light' && t !== 'dark') t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
</script>
```

Contrast of secondary text depends on the theme: `text-base-content/60` is the floor on `base-100`; on `base-200`/`base-300` surfaces use `/70` (measured with axe in Chromium; see `ui-standards-tokens/reference/ui-design-tokens.md`).

---

## 6. Modern Layout Patterns

### Flexbox Patterns

| Pattern | Classes |
|---------|---------|
| Center (both axes) | `flex items-center justify-center` |
| Vertical stack | `flex flex-col gap-4` |
| Horizontal row | `flex gap-4` |
| Space between | `flex justify-between items-center` |
| Wrap grid | `flex flex-wrap gap-4` |

### Grid Patterns

| Pattern | Classes |
|---------|---------|
| Auto-fit responsive | `grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))]` |
| Asymmetric (Bento) | `grid grid-cols-3 grid-rows-2` with spans |
| Sidebar layout | `grid grid-cols-[auto_1fr]` |

> **Note:** Prefer asymmetric/Bento layouts over symmetric 3-column grids.

---

## 7. Modern Color System

### OKLCH vs RGB/HSL

| Format | Advantage |
|--------|-----------|
| **OKLCH** | Perceptually uniform, better gradients and hover states |
| **HSL** | Intuitive hue/saturation |
| **RGB** | Legacy compatibility |

### OKLCH for daisyUI 5 Custom Themes

daisyUI 5 defines a custom theme with the `daisyui/theme` plugin. The daisyUI 4 JS-object syntax (`themes: [{ mytheme: { "primary": … } }]`) is a **build error** in v5 (`CssSyntaxError … Missed semicolon`, verified).

```css
@import "tailwindcss";
@plugin "daisyui" { themes: light --default, dark --prefersdark; }
@plugin "daisyui/theme" {
  name: "brand";
  default: false;
  prefersdark: false;
  color-scheme: light;
  --color-primary: oklch(0.55 0.2 250);
  --color-primary-content: oklch(0.98 0.01 250);
  --color-base-100: oklch(0.98 0 0);
  --color-base-content: oklch(0.2 0 0);
}
```

Every `--color-X` needs its `--color-X-content` pair, and each pair must reach 4.5:1 (re-run axe `color-contrast` in light and dark for each custom theme). Activate with `data-theme="brand"`.

### Color Token Architecture

| Layer | Example | Purpose |
|-------|---------|---------|
| **Primitive** | `--blue-500` | Raw color values |
| **Semantic** | `--color-primary` | Purpose-based naming |
| **Component** | `--button-bg` | Component-specific |

> In Angular: use daisyUI semantic classes (`bg-primary`, `text-base-content`) — never primitives directly.

---

## 8. Typography System

### Font Stack Pattern

| Type | Recommended |
|------|-------------|
| Sans | `'Inter', 'SF Pro', system-ui, sans-serif` |
| Mono | `'JetBrains Mono', 'Fira Code', monospace` |
| Display | `'Outfit', 'Poppins', sans-serif` |

### Type Scale

| Class | Size | Use |
|-------|------|-----|
| `text-xs` | 0.75rem | Labels, captions |
| `text-sm` | 0.875rem | Secondary text |
| `text-base` | 1rem | Body text |
| `text-lg` | 1.125rem | Lead text |
| `text-xl`+ | 1.25rem+ | Headings |

---

## 9. Animation & Transitions

### Built-in Animations

| Class | Effect |
|-------|--------|
| `animate-spin` | Continuous rotation |
| `animate-ping` | Attention pulse |
| `animate-pulse` | Subtle opacity pulse |
| `animate-bounce` | Bouncing effect |

### Transition Patterns

| Pattern | Classes |
|---------|---------|
| All properties | `transition-all duration-200` |
| Specific | `transition-colors duration-150` |
| With easing | `ease-out` or `ease-in-out` |
| Hover effect | `hover:scale-105 transition-transform` |

---

## 10. Component Extraction

### When to Extract

| Signal | Action |
|--------|--------|
| Same class combo 3+ times | Extract component |
| Complex state variants | Extract component |
| Design system element | Extract + document |

### Extraction Methods

| Method | Use When |
|--------|----------|
| **Angular component / daisyUI component variant** | Dynamic, needs Angular bindings or daisyUI variant classes |
| **@apply in CSS** | Static, no JS needed |
| **Design tokens** | Reusable values |

---

## 11. Anti-Patterns

| Don't | Do |
|-------|-----|
| Arbitrary values everywhere | Use design system scale |
| `!important` | Fix specificity properly |
| Inline `style=` | Use utilities |
| Duplicate long class lists | Extract component |
| Mix v3 config with v4 | Migrate fully to CSS-first |
| Use `@apply` heavily | Prefer components |
| Use `tailwind.config.js` in v4 | Use `@theme {}` in CSS |
| Copy v3 Stack Overflow examples | Verify against v4 docs |

---

## 12. Performance Principles

| Principle | Implementation |
|-----------|----------------|
| **Purge unused** | Automatic in v4 |
| **Avoid dynamism** | No template string classes |
| **Use Oxide** | Default in v4, 10x faster |
| **Cache builds** | CI/CD caching |

---

## Related Skills

- `angular-spa` — Angular 21.x implementation with full daisyUI v5.5.5 and Tailwind v4 reference files
- `angular-best-practices` — OnPush, Signals, bundle optimization, `@defer`
- `design-system` — token enforcement (Angular + Flutter)
- `web-performance-optimization` — bundle size, CSS purging, LCP

## Additional Resources

- [Tailwind CSS v4 Docs](https://tailwindcss.com/docs)
- [daisyUI v5 Theming](https://daisyui.com/docs/themes/)
- [Container Queries MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries)
- [OKLCH Color Tool](https://oklch.com/)

---

## Verify Step

Before delivering any Tailwind changes:
1. Confirm no `tailwind.config.js` was created — v4 uses `@theme {}` in CSS only
2. Grep changed templates: `grep -n "bg-blue-\|text-blue-\|bg-red-" <file>` — zero raw primitive colors in Angular templates
3. Grep for arbitrary values: `grep -c "\[" <file>` — minimize; each must be justified
4. Confirm dark mode uses `data-theme` (daisyUI). If `dark:` utilities exist, `styles.css` declares the `@custom-variant dark` line
5. No `--spacing-xs/sm/md/lg/xl` tokens in `@theme`; legacy/global CSS is imported with `layer(base)`; every `@import` precedes other rules
6. No daisyUI 4 classes (`input-bordered`, `form-control`, `label-text`, `btn … loading`, `card-bordered`, `btn-group`); v5 equivalents are `input`, `fieldset`/`fieldset-legend`, `label`, `<span class="loading loading-spinner">` inside the button, `card-border`, `join`
7. Run `ng build` and grep the output CSS for one daisyUI class (for example `.btn-primary`). If `@plugin` appears verbatim in the output, PostCSS is misconfigured (`angular-spa/reference/tailwind-v4-config.md`)

---

> **Remember:** Tailwind v4 is CSS-first. Use `@theme {}` not `tailwind.config.js`. Use daisyUI semantic tokens in Angular templates — never raw Tailwind primitives like `bg-blue-500`.
