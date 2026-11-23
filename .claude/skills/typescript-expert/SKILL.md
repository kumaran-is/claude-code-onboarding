---
name: typescript-expert
description: TypeScript 5.9 infrastructure specialist — tsconfig strict flags, solution-style configs (Angular 21 CLI, create-vite), project references, type-check commands that actually check, type performance diagnostics, ESM/CJS interop, strict mode migration, .d.ts authoring and OpenAPI client codegen. Use for project-level TypeScript decisions, not type-design patterns (typescript-advanced-types).
allowed-tools: Read, Bash
metadata:
  triggers: TypeScript performance, Type diagnostics, ESM CJS interop, TypeScript migration, Monorepo TypeScript, tsc optimization, .d.ts authoring, declaration files, incremental TypeScript, TypeScript project references
  related-skills: typescript-advanced-types, nestjs-api, angular-spa, mcp-builder, nestjs-coding-standard
  domain: frontend, backend
  role: specialist
  scope: analysis
  output-format: report
  risk: safe
  source: "antigravity-awesome-skills (community)"
  date_added: "2026-03-14"
last-reviewed: "2026-11-22"
---

# TypeScript Expert

## Iron Law

Before diagnosing any TypeScript issue, READ the actual tsconfig.json, package.json, and relevant source files first. Do not diagnose from memory — verify with file:line evidence.

> **Note:** This skill focuses on TypeScript infrastructure (monorepo, diagnostics, ESM/CJS, migrations).
> For implementation patterns, load **typescript-advanced-types** first.
> For NestJS patterns, load **nestjs-api** + **nestjs-coding-standard** first.
> For Angular patterns, load **angular-spa** first.

## When to Use

Use this skill for project-level TypeScript decisions:

- Monorepo project references and composite builds
- Type checking performance issues (`tsc --extendedDiagnostics`)
- ESM/CJS interop and module resolution problems
- Strict mode migration strategies
- `.d.ts` authoring and declaration file management
- Incremental compilation configuration
- Migrating from JavaScript to TypeScript

## Do Not Use

- Do not use for Angular/NestJS framework-specific patterns — load `angular-spa` or `nestjs-api` instead
- Do not use for implementation-level type patterns — load `typescript-advanced-types` instead
- Do not use for runtime debugging — load `systematic-debugging` instead

## Strict baseline (TypeScript 5.9)

New web and API projects start from `references/tsconfig-strict.json`. Keep what the Angular 21 CLI generates (`strict`, `noImplicitOverride`, `noPropertyAccessFromIndexSignature`, `noImplicitReturns`, `noFallthroughCasesInSwitch`, and `strictTemplates` under `angularCompilerOptions`) and add `noUncheckedIndexedAccess`. Turn on `exactOptionalPropertyTypes` only after checking that the libraries you pass optional props to accept it. All of these flags compiled together under TS 5.9.3 (2026-11-22). Do not add `baseUrl`: `paths` work without it, and TypeScript 6.0.3 rejects it (TS5101). Pin TypeScript per project: create-vite 9.3.4 templates install `typescript@~7.0`, so pin `typescript@5.9.3` explicitly where the stack is on 5.9.

## Type-check commands that actually check

Angular 21 and create-vite generate a **solution tsconfig**: the root `tsconfig.json` has `"files": []` plus `references`. `tsc --noEmit` at that root type-checks an empty program and exits 0 on any error.

| Project | Command |
|---|---|
| Plain tsconfig (NestJS, libraries, Next.js) | `npx tsc --noEmit` |
| create-vite (references with `noEmit`) | `npx tsc -b` |
| Angular 21 | `npx tsc -p tsconfig.app.json --noEmit` and `-p tsconfig.spec.json`; templates are checked only by `npx ng build` / `ng test` (`tsc -b` would emit into `out-tsc/`, because the app config is not `noEmit`) |
| References between composite projects | `npx tsc -b` |

`.claude/hooks/post-edit-typecheck.sh` and the `/verify` web block apply this table.

## Analysis Workflow

### Step 1: Analyze Project Setup

**Use internal tools first (Read, Grep, Glob) for better performance. Shell commands are fallbacks.**

```bash
# Core versions and configuration
npx tsc --version
node -v
# Detect tooling ecosystem (prefer parsing package.json)
node -e "const p=require('./package.json');console.log(Object.keys({...p.devDependencies,...p.dependencies}||{}).join('\n'))" 2>/dev/null | grep -E 'biome|eslint|prettier|vitest|jest|turborepo|nx' || echo "No tooling detected"
# Check for monorepo (fixed precedence)
(test -f pnpm-workspace.yaml || test -f lerna.json || test -f nx.json || test -f turbo.json) && echo "Monorepo detected"
```

**After detection, adapt approach:**
- Match import style (absolute vs relative)
- Respect existing baseUrl/paths configuration
- Prefer existing project scripts over raw tools
- In monorepos, consider project references before broad tsconfig changes

### Step 2: Identify Problem Category

Identify the specific problem category and complexity level before proceeding.

### Step 3: Apply Solution Strategy

Apply the appropriate solution strategy from the core capabilities below.

### Step 4: Validate

Use the type-check command from the table above for the project's tsconfig layout, and read each command's own exit code:

```bash
npx tsc -b > /tmp/tsc.log 2>&1; echo "TSC EXIT:$?"; head -20 /tmp/tsc.log      # or the -p / --noEmit form from the table
npx vitest run > /tmp/test.log 2>&1; echo "TEST EXIT:$?"; tail -15 /tmp/test.log # Angular: npx ng test --watch=false
npm run build > /tmp/build.log 2>&1; echo "BUILD EXIT:$?"; tail -10 /tmp/build.log
```

Do not chain fallbacks with `||` (`npm run typecheck || npx tsc --noEmit`): when the script fails, the fallback runs, and on a solution tsconfig it exits 0. `--reporter=basic` was removed from Vitest (5.1.1: "Failed to load custom Reporter from basic"). Avoid watch/serve processes in validation.

## Core Capabilities

### Branded Types
Create nominal types to prevent primitive obsession. Use for critical domain primitives, API boundaries, currency/units.

```typescript
type Brand<K, T> = K & { __brand: T };
type UserId = Brand<string, 'UserId'>;
type OrderId = Brand<string, 'OrderId'>;
```

### Advanced Conditional Types
Recursive type manipulation and template literal type magic. Use for library APIs, type-safe event systems, compile-time validation.

```typescript
type DeepReadonly<T> = T extends (...args: any[]) => any
  ? T
  : T extends object
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;
```

Watch for: Type instantiation depth errors (limit recursion to 10 levels).

### Type Inference (satisfies)
```typescript
// Use 'satisfies' for constraint validation (TS 5.0+)
const config = {
  api: "https://api.example.com",
  timeout: 5000
} satisfies Record<string, string | number>;
```

### Performance Optimization
```bash
# Diagnose slow type checking
npx tsc --extendedDiagnostics --incremental false | grep -E "Check time|Files:|Lines:|Nodes:"
```

- Enable `skipLibCheck: true` for library type checking only
- Use `incremental: true` with `.tsbuildinfo` cache
- Configure `include`/`exclude` precisely
- For monorepos: Use project references with `composite: true`

### Error Pattern Resolution
- **"The inferred type of X cannot be named"**: Export required type, use `ReturnType<typeof fn>`, or break circular deps
- **"Excessive stack depth comparing types"**: Limit recursion, use `interface` extends instead of type intersection
- **"Cannot find module"**: Check `moduleResolution`, verify `baseUrl`/`paths`, clear cache

### ESM/CJS Interop
- Set `"type": "module"` in package.json for ESM-first
- Use `"moduleResolution": "bundler"` for modern tools
- Use dynamic imports for CJS: `const pkg = await import('cjs-package')`
- TypeScript paths only work at compile time — not runtime

### Migration Strategies
JavaScript to TypeScript migration — incremental approach:
1. Enable `allowJs` and `checkJs`
2. Rename files gradually (`.js` → `.ts`)
3. Add types file by file
4. Enable strict mode features one by one

### Monorepo Project References
```json
{
  "references": [
    { "path": "./packages/core" },
    { "path": "./packages/ui" },
    { "path": "./apps/web" }
  ],
  "compilerOptions": {
    "composite": true,
    "declaration": true,
    "declarationMap": true
  }
}
```

- Choose **Turborepo** for: simple structure, need speed, <20 packages
- Choose **Nx** for: complex dependencies, need visualization, plugins required

### Shared API contracts (frontend ↔ backend)
Generate client types from the backend's OpenAPI document instead of hand-copying DTOs, pinned, e.g. `npx openapi-typescript@7.13.0 openapi.json -o src/api/schema.d.ts`, and fail CI when regenerating changes the file (`git diff --exit-code src/api/schema.d.ts`). Generated types are still compile-time only: parse responses at runtime (`typescript-advanced-types`, "Boundaries"). Tool choice is RECOMMENDED practice, not verified in a project here.

## Tech Stack Applicability

| Stack | Applicable |
|-------|-----------|
| Angular 21.x | Yes — but load `angular-spa` for framework patterns |
| NestJS 11.x | Yes — but load `nestjs-api` for framework patterns |
| MCP Builder TypeScript | Yes |
| Flutter | No |
| Java | No |
| Python | No |

## Reference Files

| File | Purpose |
|------|---------|
| `references/typescript-cheatsheet.md` | Quick reference for type basics, utility types, generics, type guards, and best practices |
| `references/utility-types.ts` | Production-ready utility type library (branded types, Result/Option types, deep utilities, JSON types) |
| `references/tsconfig-strict.json` | Strict TypeScript 5.9 tsconfig template (single project) with ESM, performance and path alias settings; compiles under 5.9.3 |
| `scripts/ts_diagnostic.py` | Python diagnostic script — analyzes tsconfig, tooling, monorepo setup, any-type usage, and type check performance |

## Validation Commands

Type-check, test and build: the commands in Step 4 above. Then:

```bash
# Performance diagnostics
npx tsc --extendedDiagnostics --incremental false | grep -E "Check time|Files:|Lines:|Nodes:"

# Run project diagnostic script
python3 .claude/skills/typescript-expert/scripts/ts_diagnostic.py
```
