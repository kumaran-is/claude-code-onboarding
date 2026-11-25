# Tooling — scaffold pins, TypeScript, Vite, ESLint

> RECOMMENDED PRACTICE. Toolchain verified 2026-11-23 on Node 26.13.1 / npm 11.20.0 (TypeScript 6.0.3); Tailwind CSS
> 4.3.5 + shadcn/ui 4.23.0 layer and the files below re-verified 2026-11-24 (`reference/tailwind-shadcn.md`).
> Scaffold steps and full-stack framework choice: `/scaffold-react-app`.

## What `create-vite@9.3.4 --template react-ts` gives you (inspected from the package)

- `typescript: ~7.0.2`, `lint: oxlint`, caret ranges, and `tsconfig.app.json` **without `strict`**.
- `typescript-eslint@8.74.0` peers `typescript >=4.8.4 <6.1.0` (typescript-eslint.io/users/dependency-versions),
  so TS 7 cannot be linted with it. TypeScript 6.0.3 is the newest version that every tool in the table
  accepts (`msw@3.0.7` `>=5.9.x`, `@tanstack/eslint-plugin-query` `^5.6 || ^6 || ^7`).
- Fix: `npm i -DE typescript@6.0.3`, replace oxlint with the ESLint config below (or pass `--eslint` to the
  creator, which writes a smaller config), add `strict` and `noUncheckedIndexedAccess`, and pin every
  dependency exactly. Move to TypeScript 7 only when `npm view typescript-eslint peerDependencies` allows it.
- TypeScript 7 probe (2026-11-24, report only): `npx -p typescript@7.0.2 tsc -b --noEmit` on the reference app
  exits 0 (a planted TS2322 exits 1), so the code is TS 7-ready; `typescript-eslint@8.74.0` (its `latest`) still
  peers `typescript >=4.8.4 <6.1.0`, and TS 7.0 ships no compiler API for type-aware linting. Decision: 6.0.3.
- Node: 26.13.1 (Active LTS). Every tool's `engines` allows it; the strictest floors are React Router 8
  (`>=22.22.0`) and jsdom 31 (`^22.22.2 || ^24.15.0 || >=26.0.0`).

## package.json (validated app)

`package.json`

```json
{
  "name": "app",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "test": "vitest run",
    "e2e": "playwright test",
    "preview": "vite preview"
  },
  "dependencies": {
    "@base-ui/react": "1.9.0",
    "@fontsource-variable/geist": "5.3.0",
    "@hookform/resolvers": "7.0.8",
    "@tanstack/react-query": "5.108.4",
    "@tanstack/react-table": "9.3.1",
    "class-variance-authority": "0.7.1",
    "cn": "0.5.2",
    "dompurify": "3.5.0",
    "lucide-react": "1.79.0",
    "react": "19.3.1",
    "react-dom": "19.3.1",
    "react-error-boundary": "6.1.6",
    "react-hook-form": "7.92.0",
    "react-router": "8.5.2",
    "zod": "4.6.7"
  },
  "devDependencies": {
    "@axe-core/playwright": "4.14.1",
    "@babel/core": "8.1.3",
    "@eslint/js": "10.0.1",
    "@playwright/test": "1.65.1",
    "@rolldown/plugin-babel": "0.3.1",
    "@tailwindcss/vite": "4.3.5",
    "@tanstack/eslint-plugin-query": "5.108.4",
    "@testing-library/dom": "10.4.2",
    "@testing-library/jest-dom": "8.0.0",
    "@testing-library/react": "16.3.3",
    "@testing-library/user-event": "14.6.13",
    "@types/node": "26.6.6",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.3.0",
    "babel-plugin-react-compiler": "1.0.0",
    "eslint": "10.15.0",
    "eslint-plugin-jsx-a11y-x": "0.2.0",
    "eslint-plugin-react-hooks": "7.1.1",
    "eslint-plugin-react-refresh": "0.5.8",
    "globals": "17.14.0",
    "jsdom": "31.0.1",
    "msw": "3.0.7",
    "shadcn": "4.23.0",
    "tailwindcss": "4.3.5",
    "tw-animate-css": "1.4.0",
    "typescript": "6.0.3",
    "typescript-eslint": "8.74.0",
    "vite": "8.3.8",
    "vitest": "5.1.1"
  },
  "overrides": {
    "eslint-plugin-jsx-a11y-x": {
      "minimatch": "11.0.9"
    },
    "@ts-morph/common": {
      "minimatch": "11.0.9"
    }
  },
  "engines": {
    "node": "^22.22.0 || ^24.15.0 || >=26.0.0"
  }
}
```

## TypeScript (solution layout)

`tsconfig.json`

```json
{
  "files": [],
  "compilerOptions": {
    "paths": { "@/*": ["./src/*"] }
  },
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" },
    { "path": "./tsconfig.e2e.json" }
  ]
}
```

`tsconfig.app.json`

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "esnext",
    "types": ["vite/client"],
    "allowArbitraryExtensions": true,
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "paths": { "@/*": ["./src/*"] },

    /* Linting */
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

`tsconfig.node.json`

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023"],
    "types": ["node"],
    "skipLibCheck": true,

    /* Bundler mode */
    "module": "nodenext",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["vite.config.ts", "vitest.config.ts", "playwright.config.ts", "eslint.config.js", "build-tests"]
}
```

The root `tsconfig.json` has `"files": []`, so `tsc --noEmit` at the root checks nothing. It still carries
`compilerOptions.paths`: the shadcn CLI resolves the `@/*` alias from the **root** file, and without it `init`
reports "Validating import alias ✔" yet writes `./@/lib/utils.ts` into a literal `@` directory (verified). No
`baseUrl` (deprecated in TypeScript 6, removed in 7). Always use
`tsc -b` (builds every referenced project, including tests and e2e).

## Vite (React Compiler 1.0 + alias)

`vite.config.ts`

```ts
import babel from '@rolldown/plugin-babel'
import tailwindcss from '@tailwindcss/vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss(), babel({ presets: [reactCompilerPreset()] })],
  // Enforce Trusted Types on `vite preview` (the E2E server). Production sends the same header from the host.
  preview: { headers: { 'Content-Security-Policy': "require-trusted-types-for 'script'; trusted-types dompurify" } },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
```

This is the setup react.dev documents for `@vitejs/plugin-react` 6 (learn/react-compiler/installation, "Vite")
and what the creator's `react-compiler-ts` template writes. `react({ compiler: true })` is the experimental
native compiler path in plugin-react 6; the Babel preset above is the stable path. Proof that it runs: the validation app's
production bundle contains `react.memo_cache_sentinel` 6 times with the preset and once (React's own) without it.
The `@` alias needs both `resolve.alias` and `paths` in `tsconfig.app.json`.
The `preview` CSP makes the Playwright run enforce Trusted Types (only DOMPurify may create a policy). zod 4 then
needs `z.config({ jitless: true })` in `main.tsx` (`reference/routing.md`, `reference/security.md`). Verified: 12/12 E2E green with the header.

`src/vite-env.d.ts` types the public env vars:

`src/vite-env.d.ts`

```ts
/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

## ESLint flat config

`eslint.config.js`

```js
import js from '@eslint/js'
import pluginQuery from '@tanstack/eslint-plugin-query'
import { defineConfig, globalIgnores } from 'eslint/config'
import jsxA11y from 'eslint-plugin-jsx-a11y-x'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['dist', 'playwright-report', 'test-results', 'reports']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      jsxA11y.configs.recommended,
      pluginQuery.configs['flat/recommended'],
    ],
    languageOptions: { globals: globals.browser },
    rules: {
      // The preset ships this as "warn"; a missing dependency is a stale-closure bug, so fail the lint.
      'react-hooks/exhaustive-deps': 'error',
    },
  },
  {
    // shadcn-generated primitives: they export a cva() variants helper next to the component (fast refresh rule) and
    // Label is a bare <label> wrapper whose consumers supply htmlFor. Scoped to the generated folder only.
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
      'jsx-a11y-x/label-has-associated-control': 'off',
    },
  },
])
```

`flat.recommended` already contains the React Compiler rules (`refs`, `purity`, `immutability`,
`set-state-in-effect`, …), which report code the compiler skips. The plugin README calls
`recommended-latest` "bleeding edge experimental"; in 7.1.1 it adds only `void-use-memo`.

Positive controls run: conditional `useState` → `react-hooks/rules-of-hooks`; reading `ref.current` during
render → `react-hooks/refs` (compiler diagnostic); `<img>` without `alt` → `jsx-a11y-x/alt-text` (exit 1).
Without the `overrides` block, `npm audit` reports 2 moderate advisories; with it, 0. The `@ts-morph/common`
entry covers the same `minimatch@10.2.6` advisory reached through the `shadcn` CLI (`shadcn` → `ts-morph`);
it takes effect only after a clean install (delete `node_modules` and the lockfile). The
`src/components/ui/**` block turns off two rules for CLI-generated files only: they export a `cva` helper
beside the component (`react-refresh/only-export-components`) and `Label` is a bare `<label>` whose callers
pass `htmlFor` (`jsx-a11y-x/label-has-associated-control`).

**ESLint 10 and the accessibility plugin:** `eslint-plugin-jsx-a11y@6.10.2` (its latest) peers `eslint ^3 … ^9`
and ESLint 9 is npm-deprecated, so the stack uses `eslint-plugin-jsx-a11y-x@0.2.0`, the es-tooling fork that
peers `eslint ^9 || ^10` (same rules, prefix `jsx-a11y-x/`, config `jsxA11y.configs.recommended`). The fork
depends on `minimatch@10.2.6`, which has a moderate DoS advisory (GHSA-g3hv-75wg-m249, fixed in 11.0.1, no
10.x fix); the `overrides` block above moves it to `11.0.9`, the version ESLint 10 already uses. Verified
(ESLint 10.15.0): `eslint .` exit 0; planted `<img>` without `alt` and a conditional hook → exit 1;
`label-has-associated-control` with a `controlComponents` glob (the `minimatch` path) still matches;
`npm audit` 0 vulnerabilities. Drop the override once the fork ships a patched `minimatch`, and move back
to `eslint-plugin-jsx-a11y` if it adds ESLint 10 support (`npm view eslint-plugin-jsx-a11y peerDependencies`).

## Stylesheet `src/index.css` (Tailwind v4 + shadcn tokens + the 44 px base)

`npx shadcn@4.23.0 init` writes the imports, `@custom-variant dark`, `@theme inline` and the OKLCH tokens. Merge
the scaffold base into its `@layer base`: 44 px controls (the template CSS fails the axe `target-size` check at
375 px), the page shell, the `<ViewTransition>` classes and reduced motion. The `:focus-visible` outline stays
**outside** `@layer base`: shadcn components carry `outline-none`, a utility that beats any base-layer rule, which left
a 1.5:1 ring as the only focus indicator (independent review, 2026-11-24). Light `--ring` is `oklch(0.556 0 0)`
(3:1 non-text contrast). The light `--destructive` token is darkened because the shadcn default fails axe
`color-contrast`.

`src/index.css`

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/geist";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Geist Variable', sans-serif;
    --color-sidebar-ring: var(--sidebar-ring);
    --color-sidebar-border: var(--sidebar-border);
    --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
    --color-sidebar-accent: var(--sidebar-accent);
    --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
    --color-sidebar-primary: var(--sidebar-primary);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --color-sidebar: var(--sidebar);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
    --color-ring: var(--ring);
    --color-input: var(--input);
    --color-border: var(--border);
    --color-destructive: var(--destructive);
    --color-accent-foreground: var(--accent-foreground);
    --color-accent: var(--accent);
    --color-muted-foreground: var(--muted-foreground);
    --color-muted: var(--muted);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-secondary: var(--secondary);
    --color-primary-foreground: var(--primary-foreground);
    --color-primary: var(--primary);
    --color-popover-foreground: var(--popover-foreground);
    --color-popover: var(--popover);
    --color-card-foreground: var(--card-foreground);
    --color-card: var(--card);
    --color-foreground: var(--foreground);
    --color-background: var(--background);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: oklch(1 0 0);
    --foreground: oklch(0.145 0 0);
    --card: oklch(1 0 0);
    --card-foreground: oklch(0.145 0 0);
    --popover: oklch(1 0 0);
    --popover-foreground: oklch(0.145 0 0);
    --primary: oklch(0.205 0 0);
    --primary-foreground: oklch(0.985 0 0);
    --secondary: oklch(0.97 0 0);
    --secondary-foreground: oklch(0.205 0 0);
    --muted: oklch(0.97 0 0);
    --muted-foreground: oklch(0.556 0 0);
    --accent: oklch(0.97 0 0);
    --accent-foreground: oklch(0.205 0 0);
    /* shadcn default oklch(0.577 0.245 27.325) fails axe color-contrast (text-destructive on bg-destructive/10). */
    --destructive: oklch(0.505 0.2 27.5);
    --border: oklch(0.922 0 0);
    --input: oklch(0.922 0 0);
    /* shadcn default oklch(0.708 0 0) is ~1.5:1 on white: below the 3:1 non-text contrast (WCAG 1.4.11) for the focus indicator. */
    --ring: oklch(0.556 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.556 0 0);
    --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);
    --chart-5: oklch(0.269 0 0);
    --radius: 0.625rem;
    --sidebar: oklch(0.985 0 0);
    --sidebar-foreground: oklch(0.145 0 0);
    --sidebar-primary: oklch(0.205 0 0);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.97 0 0);
    --sidebar-accent-foreground: oklch(0.205 0 0);
    --sidebar-border: oklch(0.922 0 0);
    --sidebar-ring: oklch(0.708 0 0);
}

.dark {
    --background: oklch(0.145 0 0);
    --foreground: oklch(0.985 0 0);
    --card: oklch(0.205 0 0);
    --card-foreground: oklch(0.985 0 0);
    --popover: oklch(0.205 0 0);
    --popover-foreground: oklch(0.985 0 0);
    --primary: oklch(0.922 0 0);
    --primary-foreground: oklch(0.205 0 0);
    --secondary: oklch(0.269 0 0);
    --secondary-foreground: oklch(0.985 0 0);
    --muted: oklch(0.269 0 0);
    --muted-foreground: oklch(0.708 0 0);
    --accent: oklch(0.269 0 0);
    --accent-foreground: oklch(0.985 0 0);
    --destructive: oklch(0.704 0.191 22.216);
    --border: oklch(1 0 0 / 10%);
    --input: oklch(1 0 0 / 15%);
    --ring: oklch(0.556 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.556 0 0);
    --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);
    --chart-5: oklch(0.269 0 0);
    --sidebar: oklch(0.205 0 0);
    --sidebar-foreground: oklch(0.985 0 0);
    --sidebar-primary: oklch(0.488 0.243 264.376);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.269 0 0);
    --sidebar-accent-foreground: oklch(0.985 0 0);
    --sidebar-border: oklch(1 0 0 / 10%);
    --sidebar-ring: oklch(0.556 0 0);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
    }
  body {
    @apply bg-background text-foreground;
    }
  html {
    @apply font-sans;
    }

  /* Scaffold base stylesheet merged into the shadcn base layer: 44px targets, focus styles, page shell. */
  :root { color-scheme: light; }
  .dark { color-scheme: dark; }
  button, [role="button"], [role="menuitem"], [role="menuitemradio"], input, select, textarea { min-height: 44px; }
  button, [role="button"], [role="menuitem"], [role="menuitemradio"] { min-width: 44px; }
  h1 { font-size: var(--text-2xl, 1.5rem); font-weight: 600; }
  h2 { font-size: var(--text-xl, 1.25rem); font-weight: 600; }
  main { padding: 1rem; max-width: 60rem; margin: 0 auto; }
  main:focus { outline: none; }
}

/*
 * Focus indicator (WCAG 2.4.7 / 1.4.11). Deliberately OUTSIDE @layer base: unlayered rules beat every layered one, and
 * shadcn components carry the `outline-none` utility (layer utilities), which would otherwise cancel a base-layer outline.
 * The components' own ring (ring-ring/50) is only a 50% tint, so this outline is the indicator that meets 3:1.
 */
:focus-visible { outline: 3px solid var(--ring); outline-offset: 2px; }

/* <ViewTransition> classes used by SettingsTabs; honour reduced motion. */
::view-transition-old(.slide-to-left) { animation: 180ms ease-in both vt-out-left; }
::view-transition-new(.slide-from-right) { animation: 180ms ease-out both vt-in-right; }
::view-transition-old(.slide-to-right) { animation: 180ms ease-in both vt-out-right; }
::view-transition-new(.slide-from-left) { animation: 180ms ease-out both vt-in-left; }
@keyframes vt-out-left { to { transform: translateX(-2rem); opacity: 0; } }
@keyframes vt-in-right { from { transform: translateX(2rem); opacity: 0; } }
@keyframes vt-out-right { to { transform: translateX(2rem); opacity: 0; } }
@keyframes vt-in-left { from { transform: translateX(-2rem); opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  *, ::before, ::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
}
```

Keep the 44 px control minimum and re-run the axe scan at both widths and in both themes after changing a token.
