# NestJS Configuration — npm & TypeScript

Package and TypeScript setup for NestJS 11.x on Fastify, verified in a disposable app on 2026-11-23
(strict `tsc`, ESLint, 19 unit + 11 e2e tests, `npm audit --audit-level=high` exit 0). Prisma schema and client
setup: `nestjs-config-prisma7.md`. Reference implementation: `nestjs-production-baseline.md`.

## Versions

| Line | Pin | Why |
|---|---|---|
| NestJS core packages | `11.2.11` | latest 11.x. There is no `11.17.x`; NestJS 12 (12.6.0) is GA but its satellites (`@nestjs/swagger@12`, `@nestjs/config@12`, `@nestjs/bullmq@12`) peer on Nest 12 only |
| `@nestjs/swagger` / `@nestjs/config` / `@nestjs/terminus` / `@nestjs/bullmq` | `11.4.8` / `4.0.4` / `11.1.1` / `11.0.5` | latest majors that peer on Nest 11 |
| `@nestjs/throttler` | `6.8.0` | peers on Nest 7–12 |
| Prisma | `7.10.1` | npm `latest` for the `prisma` CLI is `8.0.0-rc.35` (a release candidate); pin the stable 7.x line explicitly |
| TypeScript | `5.9.3` | `typescript-eslint` 8.73 supports `>=4.8.4 <6.1.0`; TypeScript 7 is not supported by the lint stack yet |
| ESLint | `9.39.5` | flat config; the `--ext` flag no longer exists |

Re-check before pinning: `npm view <pkg>@<major> version`, then install with `npm i -E`. Never let a caret range float across a Nest major.

## package.json

```json
{
  "name": "orders-api",
  "version": "0.1.0",
  "private": true,
  "type": "commonjs",
  "engines": {
    "node": ">=24.0.0"
  },
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "start": "node dist/main.js",
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "test": "vitest run",
    "test:e2e": "vitest run --config vitest.e2e.config.mts",
    "prisma:generate": "prisma generate"
  },
  "dependencies": {
    "@fastify/helmet": "13.2.0",
    "@fastify/static": "10.1.12",
    "@nest-lab/throttler-storage-redis": "1.2.0",
    "@nestjs/bullmq": "11.0.5",
    "@nestjs/common": "11.2.11",
    "@nestjs/config": "4.0.4",
    "@nestjs/core": "11.2.11",
    "@nestjs/platform-fastify": "11.2.11",
    "@nestjs/platform-socket.io": "11.2.11",
    "@nestjs/swagger": "11.4.8",
    "@nestjs/terminus": "11.1.1",
    "@nestjs/throttler": "6.8.0",
    "@nestjs/websockets": "11.2.11",
    "@prisma/adapter-pg": "7.10.1",
    "@prisma/client": "7.10.1",
    "bullmq": "5.81.6",
    "class-transformer": "0.5.1",
    "class-validator": "0.15.1",
    "fastify": "5.12.8",
    "ioredis": "5.11.1",
    "jose": "6.2.18",
    "pg": "8.23.1",
    "reflect-metadata": "0.2.2",
    "rxjs": "7.8.2",
    "socket.io": "4.8.3",
    "zod": "4.6.7"
  },
  "devDependencies": {
    "@eslint/js": "9.39.5",
    "@nestjs/testing": "11.2.11",
    "@swc/core": "1.16.22",
    "@types/node": "24.19.2",
    "@types/supertest": "7.2.1",
    "eslint": "9.39.5",
    "globals": "17.14.0",
    "prisma": "7.10.1",
    "socket.io-client": "4.8.4",
    "supertest": "7.3.2",
    "typescript": "5.9.3",
    "typescript-eslint": "8.73.0",
    "unplugin-swc": "2.0.0",
    "vitest": "4.1.12"
  },
  "overrides": {
    "effect": "3.22.5"
  }
}
```

- `@fastify/static` is only needed for `SwaggerModule.setup()` (Swagger UI) on Fastify.
- `ioredis` is pinned to the 5.x line that `bullmq` 5 depends on, so the app has one Redis client copy.
- `overrides.effect`: `npm audit` flagged GHSA-7589-6fvf-x4pw in `effect` (via `prisma` → `@prisma/config` 7.10.1). The override cleared it (audit exit 1 → 0); remove it once Prisma ships a fixed `effect`.
- npm is the package manager for this stack (`package-lock.json` committed, `npm ci` in CI). Do not add a `packageManager: pnpm` field.
- The Nest CLI is optional. `nest new` scaffolds Express + Jest; this stack replaces both, so a hand-written `package.json` + `main.ts` is as short. Run `nest new` only through `/scaffold-nestjs-api` (the scaffold hook blocks a raw call).
- `prisma generate` must run before `tsc` (the generated client is gitignored): run it in CI before the typecheck.

## tsconfig, Vitest and ESLint (verified)

```json
{
  "compilerOptions": {
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "target": "ES2023",
    "lib": ["ES2023"],
    "types": ["node"],
    "outDir": "./dist",
    "rootDir": ".",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "useUnknownInCatchVariables": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "incremental": true,
    "tsBuildInfoFile": "./dist/.tsbuildinfo"
  },
  "include": ["src/**/*.ts", "test/**/*.ts", "prisma.config.ts"],
  "exclude": ["node_modules", "dist"]
}
```

```typescript
import swc from 'unplugin-swc';
import { defineConfig } from 'vitest/config';

// SWC (not esbuild) compiles the tests: esbuild drops emitDecoratorMetadata, so Nest
// constructor injection by class type would resolve `undefined` at runtime.
export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['src/**/*.spec.ts'],
    root: './',
  },
  plugins: [swc.vite({ module: { type: 'es6' } })],
});
```

```typescript
import swc from 'unplugin-swc';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['test/**/*.e2e-spec.ts'],
    root: './',
    fileParallelism: false,
    // ConfigModule.forRoot({ validate }) runs when AppModule is IMPORTED, before any beforeAll:
    // test env must exist at load time, so it is set here, not in the spec.
    env: {
      NODE_ENV: 'test',
      JWT_ISSUER: 'https://issuer.test',
      JWT_AUDIENCE: 'orders-api',
      JWT_JWKS_URL: 'https://issuer.test/.well-known/jwks.json',
      THROTTLE_LIMIT: '5',
      THROTTLE_TTL_MS: '60000',
    },
  },
  plugins: [swc.vite({ module: { type: 'es6' } })],
});
```

```javascript
// @ts-check
import eslint from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**', 'src/generated/**', 'eslint.config.mjs', 'vitest*.config.mts'] },
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.node },
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      'no-console': 'error',
    },
  },
);
```

Notes:
- `module`/`moduleResolution: "nodenext"` with a CommonJS `package.json` (the Nest 11 CLI template uses the same pair).
- Name Vitest configs `.mts` in a CommonJS package: a `.ts` config with ESM syntax triggers Vite 8's "ESM syntax in a file loaded as CommonJS" warning.
- Decorator metadata: both `unplugin-swc` and Vite 8's built-in Oxc transform read `emitDecoratorMetadata` from tsconfig.
  With Vitest 4.1 the suite passed **without** the SWC plugin; with `emitDecoratorMetadata: false` every e2e test failed
  (`Cannot read properties of undefined (reading 'getAllAndOverride')`). Keep the flag on and keep one e2e test that
  resolves a class-typed constructor dependency — it is the check that catches a broken transform.
- `npm audit --audit-level=high` flagged `effect` (GHSA-7589-6fvf-x4pw, via `prisma` → `@prisma/config`) on Prisma 7.10.1.
  `"overrides": { "effect": "3.22.5" }` cleared it (audit exit 1 → 0). Re-check on every Prisma upgrade and drop the override once Prisma ships the fix.

