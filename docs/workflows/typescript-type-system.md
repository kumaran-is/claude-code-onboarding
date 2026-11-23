# TypeScript Type System Workflow

> **When to use**: Strengthening TypeScript type safety, designing advanced type patterns, resolving type errors, setting up TypeScript infrastructure for Angular 22.x, React, NestJS 11.x, or MCP Builder projects
> **Prerequisites**: TypeScript project exists with `tsconfig.json` configured

## Overview

Two-skill TypeScript pipeline: **typescript-advanced-types** (canonical for type design: boundary validation vs compile-time types, discriminated unions, typed errors, generics, mapped/conditional types) and **typescript-expert** (tsconfig strictness, solution-style configs, type-check commands that actually check, build performance, ESM/CJS interop). `typescript-pro` is a pointer kept only so old links resolve. Applies to Angular 22.x, React, NestJS 11.x and MCP Builder TypeScript projects — not Flutter, Java, or Python.

## Skill Selection Guide

| Task | Primary Skill | When to Add Others |
|------|---|---|
| Generic DTOs, conditional types, mapped types, utility types | **typescript-advanced-types** | + nestjs-api (NestJS) or angular-spa (Angular) |
| Shared type contracts, boundary validation (Zod), typed errors, decorator metadata types | **typescript-advanced-types** | + nestjs-coding-standard |
| Strict tsconfig flags, which type-check command actually checks your project | **typescript-expert** | + framework skill |
| Monorepo project refs, build perf, ESM/CJS, JS→TS migration | **typescript-expert** | + framework skill |
| Both | Start with **typescript-advanced-types** | Then **typescript-expert** (config and infra) |

---

## Phase 1 — Type Pattern Implementation (typescript-advanced-types)

**Trigger**: Need type-safe generics, conditional types, mapped types, or custom utility types
**Skill**: `typescript-advanced-types`
**Reference**: `resources/implementation-playbook.md` (717 lines of patterns)

### When to load this skill
- Building type-safe DTO hierarchies (NestJS `DeepPartial<CreateUserDto>`)
- Creating generic service factories (Angular type-safe HTTP clients)
- Designing Zod schemas with branded types (MCP Builder tool definitions)
- Implementing `DeepPartial`, `DeepReadonly`, `PickByType`, or `Branded` utility types
- Using template literal types for string-based APIs

### Workflow
1. Load `typescript-advanced-types` skill
2. Open `resources/implementation-playbook.md` for the relevant pattern section
3. Identify which pattern applies: Generics / Conditional Types / Mapped Types / Template Literals / Utility Types
4. Implement with workspace framework (nestjs-api or angular-spa patterns)
5. Validate with the type-check command for your project layout (`typescript-expert` SKILL.md, "type-check commands"): Angular 22 `npx tsc -p tsconfig.app.json --noEmit` plus `npx ng build`; create-vite (React) `npx tsc -b`; plain tsconfig (NestJS) `npx tsc --noEmit`. A bare `tsc --noEmit` at an Angular or Vite root checks an empty program and exits 0.

**Gate**: the type-check exits 0 AND fails on a planted type error; no `any` introduced

---

## Phase 2 — TypeScript Infrastructure (typescript-expert)

**Trigger**: Monorepo setup, build performance issues, ESM/CJS interop, or JS→TS migration
**Skill**: `typescript-expert`
**Reference files**: `references/tsconfig-strict.json`, `references/ts_diagnostic.py`, `references/typescript-cheatsheet.md`

### When to load this skill
- Setting up monorepo with shared types between Angular + NestJS (`composite: true`, project references)
- TypeScript build is slow — run `npx tsc --extendedDiagnostics` first
- MCP Builder (ESM) needs to interop with NestJS (CommonJS)
- Migrating JavaScript service to TypeScript strict mode
- Authoring `.d.ts` declaration files for untyped packages

### Workflow
1. Load `typescript-expert` skill
2. Analyze project setup: read `tsconfig.json`, `package.json`, detect monorepo
3. Identify problem category: perf / interop / migration / monorepo
4. Apply solution strategy from `references/tsconfig-strict.json` or run `scripts/ts_diagnostic.py`
5. Validate:
   ```bash
   npm run -s typecheck   # define it per layout: tsc -b (Vite), tsc -p tsconfig.app.json --noEmit (Angular), tsc --noEmit (plain)
   npm test -s || npx vitest run --reporter=basic --no-watch
   npm run -s build
   ```

**Gate**: the layout-correct type-check exits 0, build succeeds, test suite green (each command's own exit code)

---

## Common Combinations

### NestJS: Type-safe DTO Hierarchy
1. **typescript-advanced-types** — `DeepPartial<T>`, `PickByType<T,U>`, mapped type Update DTOs
2. **nestjs-coding-standard** — Enforce `strict: true`, `unknown` over `any`
3. **nestjs-api** — Wire into controllers and services

### Angular: Generic HTTP Service Factory
1. **typescript-advanced-types** — Conditional + mapped types for `ApiClient<T>`
2. **angular-spa** — Integrate into Angular service layer
3. **browser-testing** — Verify type-safe service in E2E tests

### Monorepo: Shared Types (Angular + NestJS)
1. **typescript-expert** — Set up project references, `composite: true`, shared `tsconfig.base.json`
2. **typescript-advanced-types** — Design the shared type library (DTOs, API responses)
3. **nestjs-api** + **angular-spa** — Consume shared types in each framework

### MCP Builder: Type-safe Tool Definitions
1. **typescript-advanced-types** — Branded types for tool inputs, Zod schema inference
2. **mcp-builder** — Wire into MCP server tool registration
3. **typescript-expert** — Resolve ESM/CJS interop if needed

---

## Troubleshooting

| Problem | Skill | Action |
|---------|-------|--------|
| "Type instantiation is excessively deep" | typescript-expert | Break recursion, use type aliases, split unions |
| "The inferred type of X cannot be named" | typescript-expert | Export the type explicitly or use `ReturnType<>` |
| Slow `tsc` (>5s on medium project) | typescript-expert | Run `--extendedDiagnostics`, enable incremental |
| `any` types leaking through generics | typescript-advanced-types | Apply `unknown` + type guards pattern |
| DTO update type requires 20 `@IsOptional()` | typescript-advanced-types | Use `DeepPartial<T>` mapped type |
| NestJS + Angular can't share DTOs | typescript-expert | Monorepo project references |
| MCP SDK (ESM) breaks NestJS (CJS) build | typescript-expert | ESM/CJS interop patterns |

---

## Related Workflows

- [`feature-nestjs.md`](feature-nestjs.md) — Full NestJS feature with TypeScript
- [`feature-angular-spa.md`](feature-angular-spa.md) — Angular SPA feature development
- [`mcp-server-setup.md`](mcp-server-setup.md) — MCP Builder with TypeScript
