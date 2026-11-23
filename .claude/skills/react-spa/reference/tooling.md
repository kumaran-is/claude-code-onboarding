# Tooling — scaffold pins, TypeScript, Vite, ESLint

> RECOMMENDED PRACTICE. Verified 2026-11-23 with Node 24.13.1. Scaffold steps: `/scaffold-react-app`.

## What `create-vite@9.3.4 --template react-ts` gives you (inspected from the package)

- `typescript: ~7.0.2`, `lint: oxlint`, caret ranges, and `tsconfig.app.json` **without `strict`**.
- `typescript-eslint@8.73.0` peers `typescript >=4.8.4 <6.1.0`, so TS 7 cannot be linted with it.
- Fix: `npm i -DE typescript@5.9.3` (workspace standard), replace oxlint with the ESLint config below,
  add `strict` and `noUncheckedIndexedAccess`, and pin every dependency exactly.

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
    "@hookform/resolvers": "7.0.8",
    "@tanstack/react-query": "5.108.3",
    "dompurify": "3.5.0",
    "react": "19.3.1",
    "react-dom": "19.3.1",
    "react-error-boundary": "6.1.6",
    "react-hook-form": "7.92.0",
    "react-router": "8.5.2",
    "zod": "4.6.7"
  },
  "devDependencies": {
    "@axe-core/playwright": "4.14.0",
    "@babel/core": "8.1.3",
    "@eslint/js": "10.0.1",
    "@playwright/test": "1.65.1",
    "@rolldown/plugin-babel": "0.3.1",
    "@tanstack/eslint-plugin-query": "5.108.3",
    "@testing-library/dom": "10.4.2",
    "@testing-library/jest-dom": "8.0.0",
    "@testing-library/react": "16.3.3",
    "@testing-library/user-event": "14.6.13",
    "@types/node": "24.19.2",
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
    "typescript": "5.9.3",
    "typescript-eslint": "8.73.0",
    "vite": "8.3.8",
    "vitest": "5.1.1"
  },
  "overrides": {
    "eslint-plugin-jsx-a11y-x": { "minimatch": "11.0.9" }
  }
}
```

## TypeScript (solution layout)

`tsconfig.json`

```json
{
  "files": [],
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
  "include": ["vite.config.ts", "vitest.config.ts", "playwright.config.ts", "eslint.config.js"]
}
```

The root `tsconfig.json` has `"files": []`, so `tsc --noEmit` at the root checks nothing. Always use
`tsc -b` (builds every referenced project, including tests and e2e).

## Vite (React Compiler 1.0 + alias)

`vite.config.ts`

```ts
import babel from '@rolldown/plugin-babel'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
```

`react({ compiler: true })` is the experimental native compiler path in plugin-react 6; the Babel preset
above is the stable path. The `@` alias needs both `resolve.alias` and `paths` in `tsconfig.app.json`.

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
  globalIgnores(['dist', 'playwright-report', 'test-results']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
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
])
```

Positive controls run: conditional `useState` → `react-hooks/rules-of-hooks` (exit 1);
`<img>` without `alt` → `jsx-a11y-x/alt-text` (exit 1).

**ESLint 10 and the accessibility plugin:** `eslint-plugin-jsx-a11y@6.10.2` (its latest) peers `eslint ^3 … ^9`
and ESLint 9 is npm-deprecated, so the stack uses `eslint-plugin-jsx-a11y-x@0.2.0`, the es-tooling fork that
peers `eslint ^9 || ^10` (same rules, prefix `jsx-a11y-x/`, config `jsxA11y.configs.recommended`). The fork
depends on `minimatch@10.2.6`, which has a moderate DoS advisory (GHSA-g3hv-75wg-m249, fixed in 11.0.1, no
10.x fix); the `overrides` block above moves it to `11.0.9`, the version ESLint 10 already uses. Verified
(ESLint 10.15.0): `eslint .` exit 0; planted `<img>` without `alt` and a conditional hook → exit 1;
`label-has-associated-control` with a `controlComponents` glob (the `minimatch` path) still matches;
`npm audit` 0 vulnerabilities. Drop the override once the fork ships a patched `minimatch`, and move back
to `eslint-plugin-jsx-a11y` if it adds ESLint 10 support (`npm view eslint-plugin-jsx-a11y peerDependencies`).

## Base stylesheet `src/index.css` (replace the template's)

The template's demo CSS leaves dialog buttons below the 24×24 px WCAG 2.2 AA target size, and the
Playwright axe scan at 375 px fails (`target-size`). Replace it with a base that meets the house 44 px
target and styles the classes the reference components use (`shell-header`, `field`, `field-error`):

```css
:root { font: 16px/1.5 system-ui, sans-serif; color: #1a1a1a; background: #fff; }
body { margin: 0; }
a { color: #0b57d0; }
.shell-header { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; border-bottom: 1px solid #ccc; }
main { padding: 1rem; max-width: 60rem; margin: 0 auto; }
button { min-height: 44px; min-width: 44px; padding: 0 1rem; font: inherit; }
input { min-height: 44px; font: inherit; padding: 0 0.5rem; width: 100%; box-sizing: border-box; }
.field { margin-bottom: 1rem; }
.field-error { color: #b00020; margin: 0.25rem 0 0; }
dialog { width: min(32rem, calc(100vw - 2rem)); box-sizing: border-box; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
```

A design system (Tailwind, CSS modules, a component library) replaces these literals with its tokens;
keep the 44 px control minimum and re-run the axe scan at both widths.
