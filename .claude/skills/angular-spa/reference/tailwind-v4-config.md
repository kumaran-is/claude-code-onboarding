> **Official Angular+Tailwind guide:** https://angular.dev/guide/tailwind

# Tailwind CSS 4.3.5 Configuration

## Angular Official Setup (from angular.dev)

Angular's official guide (https://angular.dev/guide/tailwind) recommends:

### Automated Setup (recommended)

```bash
ng add tailwindcss
```

This single command installs dependencies, creates `.postcssrc.json`, and imports Tailwind into your styles automatically. Use this for new projects.

### Manual Setup

```bash
npm install tailwindcss @tailwindcss/postcss postcss
```

Create `.postcssrc.json` in project root:
```json
{
  "plugins": {
    "@tailwindcss/postcss": {}
  }
}
```

For CSS projects, add to `src/styles.css`:
```css
@import 'tailwindcss';
```

For SCSS projects, add to `src/styles.scss`:
```scss
@use 'tailwindcss';
```

### Differences from the official guide in a typical project setup

| Angular Official Guide | This project | Reason |
|------------------------|-------------------------------|--------|
| `ng add tailwindcss` | `ng add tailwindcss`, then re-pin exact versions | `ng add` writes caret ranges (`^4.1.12`); `/scaffold-angular-app` pins `tailwindcss@4.3.5` |
| SCSS `@use 'tailwindcss'` supported | CSS only (`src/styles.css`) | Sass intercepts `@import`/`@theme`/`@plugin` — CSS is required |
| `@import "tailwindcss"` | `@import "tailwindcss";` + `@plugin "daisyui";` | daisyUI 5 is a Tailwind 4 plugin |

> Angular 22 does **not** use Tailwind v4 by default — it must be installed explicitly via `ng add tailwindcss` or manual setup. The `ng add` command installs Tailwind v4 when run in Angular 17+ projects using the `@angular/build:application` (esbuild) builder.

## CSS-Native Configuration (No tailwind.config.js)

TailwindCSS v4 is a complete rewrite using CSS-native configuration:

```css
/* src/styles.css (NOT .scss — Tailwind CSS 4.3.5 directives conflict with Sass) */
@import "tailwindcss";

@theme {
  /* Typography */
  --font-sans: "Inter", "system-ui", sans-serif;
  --font-mono: "JetBrains Mono", monospace;

  /* Custom spacing */
  --spacing-18: 4.5rem;
  --spacing-22: 5.5rem;

  /* Custom breakpoints */
  --breakpoint-3xl: 1920px;

  /* Animation durations */
  --duration-instant: 50ms;
  --duration-quick: 150ms;
  --duration-standard: 250ms;
}

@plugin "daisyui" {
  themes: light --default, dark --prefersdark, corporate, business;
}
```
> **Note:** Do NOT add `@import "daisyui"` — daisyUI is loaded via the `@plugin` directive in Tailwind CSS 4.3.5. The global stylesheet must be `.css` (not `.scss`) to avoid Sass intercepting CSS-native directives like `@import`, `@theme`, and `@plugin`.

## Breaking Changes from v3

| v3 Syntax | v4 Syntax | Notes |
|-----------|-----------|-------|
| `tailwind.config.js` | `@theme { }` in CSS | No JS config file |
| `@apply` directive | Still works, but discouraged | Use CSS variables instead |
| `theme.extend` | `@theme { --custom: value }` | CSS custom properties |
| `screens` config | `--breakpoint-*` variables | CSS-native breakpoints |
| `colors` config | `@theme { --color-brand: oklch(…) }` | Brand/app tokens only; UI-library colours come from the mode's theme (daisyUI theme or Spartan variables) |

## PostCSS Configuration

> **CRITICAL:** Angular's `@angular/build:application` builder only reads `.postcssrc.json`. It **ignores** `postcss.config.js` / `.mjs` / `.cjs`. If you use the wrong file name, PostCSS plugins will not run and TailwindCSS utilities + daisyUI components will be missing from the output CSS.

```json
// .postcssrc.json (in project root, next to angular.json)
{
  "plugins": {
    "@tailwindcss/postcss": {}
  }
}
```

## Angular Integration

```json
// angular.json (styles array)
{
  "styles": [
    "src/styles.css"
  ]
}
```

## daisyUI v5 import

```css
/* src/styles.css — all @import lines first */
@import "tailwindcss";
@plugin "daisyui";
```

Install pinned: `npm install --save-exact tailwindcss@4.3.5 @tailwindcss/postcss@4.3.5 postcss@8.5.33 daisyui@5.8.2`.

Verified on Angular CLI 22.3.0 (`ng build` exit 0): with `.postcssrc.json` present, `@plugin "daisyui"` emits
daisyUI component classes (`.btn-primary` found in `dist/<app>/browser/styles-*.css`) and no `@plugin`
text remains. The `@plugin` failure people report is a **wrong PostCSS file**: Angular reads
`.postcssrc.json` or `postcss.config.json`, **not** `postcss.config.js`. Symptom: the build still exits
0, `@plugin` appears verbatim in the output CSS and no daisyUI classes exist.

Keep Tailwind/daisyUI directives in a plain `styles.css`; using them through Sass is UNVERIFIED.

## Class scanning

Tailwind 4 scans the project sources automatically, **including inline templates in `.ts` files**
(verified: utilities used only in an inline `template:` string — `max-w-4xl`, `tracking-widest` — are
emitted). No `@source` lines or hand-written utility safelists are needed. Add `@source` only for
classes that live outside the project (for example a library in `node_modules`).

## Verification Checklist

### DaisyUI + Tailwind v4 — Setup Verification Checklist

After scaffolding, ALWAYS verify these before writing any UI components:

1. **Packages installed** — check package.json:
   - `tailwindcss` `4.3.5`
   - `@tailwindcss/postcss` `4.3.5`
   - `daisyui` `5.8.2` (exact pins, no caret)

2. **CSS entry point** (`src/styles.css`) must contain:
   ```css
   @import "tailwindcss";
   @plugin "daisyui";
   ```
   ❌ Old Tailwind v3 syntax is WRONG for v4:
   ```css
   /* DO NOT USE */
   @tailwind base;
   @tailwind components;
   @tailwind utilities;
   ```

3. **Angular JSON styles** — `angular.json` must reference `src/styles.css`:
   ```json
   "styles": ["src/styles.css"]
   ```

4. **PostCSS config** — `.postcssrc.json` or `postcss.config.json` (never `postcss.config.js`) must exist in the project root:
   ```json
   {
     "plugins": {
       "@tailwindcss/postcss": {}
     }
   }
   ```

5. **Smoke test after scaffold**: Open the app and confirm a `<button class="btn btn-neutral">Test</button>` renders with DaisyUI styling. If it renders as a plain browser button, styles are broken — fix before writing any feature UI.

## Breakpoints

```css
sm:   640px    /* Small tablets */
md:   768px    /* Tablets */
lg:   1024px   /* Small laptops */
xl:   1280px   /* Desktop */
2xl:  1536px   /* Large desktop */
```

Usage:
```html
<div class="p-4 md:p-6 lg:p-8">
  <!-- 16px mobile, 24px tablet, 32px desktop -->
</div>
```
