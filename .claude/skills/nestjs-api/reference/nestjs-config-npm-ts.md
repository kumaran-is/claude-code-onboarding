# NestJS Configuration — npm & TypeScript

Package and TypeScript setup for NestJS 12.x on Fastify, verified in a disposable app on 2026-11-24 on Node 26.13.1
(`tsc` strict incl. specs, `oxlint --type-aware`, 9 unit + 23 integration/e2e tests against PostgreSQL 18 and Redis 8,
`nest build`, `npm audit --audit-level=high` exit 0, `docker build` + `/health` 200 as non-root). Prisma schema and client
setup: `nestjs-config-prisma7.md`. Reference implementation: `nestjs-production-baseline.md`.

## Versions

| Line | Pin | Why |
|---|---|---|
| NestJS core (`common`, `core`, `platform-fastify`, `websockets`, `platform-socket.io`, `testing`) | `12.6.0` | latest stable; one version for every core package |
| `@nestjs/cli` / `@nestjs/schematics` | `12.0.15` / `12.0.16` | schematics 12 peer on TypeScript 6 |
| `@nestjs/swagger` / `@nestjs/config` / `@nestjs/terminus` / `@nestjs/bullmq` | `12.1.2` / `12.1.1` / `12.2.0` / `12.0.2` | satellites have their own release lines; all peer on Nest 12 |
| `@nestjs/throttler` | `6.8.0` | still 6.x; peers on Nest 7–12 |
| `bullmq` + `ioredis` | `6.7.10` + `6.1.0` | bullmq 6 made `ioredis` optional: without it the queue fails at runtime ("could not load the optional 'ioredis' package") |
| Prisma | `7.10.1` | npm `latest` for the `prisma` CLI is `8.0.0-rc.35` (a release candidate); pin the stable 7.x line |
| TypeScript | `6.0.3` | `@nestjs/schematics` 12 and `@nestjs/swagger` 12 peer on `^6`; TypeScript 7.0.2 is npm `latest` but not accepted by the Nest toolchain yet |
| Vitest | `5.1.1` | ESM projects: Vitest is what `nest new` 12 generates |
| oxlint + oxlint-tsgolint | `1.95.0` + `7.0.2008` | what `nest new` 12 generates; `--type-aware` gives `no-floating-promises` / `no-misused-promises` |
| Node.js | `26.13.1` (engines `>=26.0.0`) | Nest 12 runs on Node `>=20.19` / `>=22.12`; the CLI generators need `>=22.22.3`, `>=24.15` or `>=26`; this stack standardises on 26 LTS |

Re-check before pinning: `npm view <pkg>@<major> version`, then install with `npm i -E`. Never let a caret range float across a Nest major.

## package.json

```json
{
  "name": "orders-api",
  "version": "0.1.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "engines": {
    "node": ">=26.0.0"
  },
  "scripts": {
    "build": "nest build",
    "start": "node dist/main.js",
    "start:prod": "node --import ./dist/instrumentation.js dist/main.js",
    "typecheck": "tsc --noEmit -p tsconfig.json",
    "lint": "oxlint --type-aware --deny-warnings src/ test/",
    "test": "vitest run",
    "test:e2e": "vitest run --config ./vitest.config.e2e.ts",
    "prisma:generate": "prisma generate",
    "prisma:deploy": "prisma migrate deploy"
  },
  "dependencies": {
    "@fastify/helmet": "13.2.0",
    "@fastify/static": "10.1.12",
    "@nestjs/bullmq": "12.0.2",
    "@nestjs/common": "12.6.0",
    "@nestjs/config": "12.1.1",
    "@nestjs/core": "12.6.0",
    "@nestjs/platform-fastify": "12.6.0",
    "@nestjs/platform-socket.io": "12.6.0",
    "@nestjs/swagger": "12.1.2",
    "@nestjs/terminus": "12.2.0",
    "@nestjs/throttler": "6.8.0",
    "@nestjs/websockets": "12.6.0",
    "@opentelemetry/api": "1.10.0",
    "@opentelemetry/instrumentation-http": "0.301.2",
    "@opentelemetry/sdk-node": "0.301.2",
    "@opentelemetry/sdk-trace": "3.1.1",
    "@prisma/adapter-pg": "7.10.1",
    "@prisma/client": "7.10.1",
    "bullmq": "6.7.10",
    "fastify": "5.12.8",
    "ioredis": "6.1.0",
    "jose": "6.2.18",
    "pg": "8.23.1",
    "reflect-metadata": "0.2.2",
    "rxjs": "7.8.2",
    "socket.io": "4.8.4",
    "zod": "4.6.7"
  },
  "devDependencies": {
    "@nestjs/cli": "12.0.15",
    "@nestjs/schematics": "12.0.16",
    "@nestjs/testing": "12.6.0",
    "@types/node": "26.6.7",
    "@types/pg": "8.23.1",
    "oxlint": "1.95.0",
    "oxlint-tsgolint": "7.0.2008",
    "prisma": "7.10.1",
    "socket.io-client": "4.8.4",
    "typescript": "6.0.3",
    "vite": "8.3.8",
    "vitest": "5.1.1"
  },
  "overrides": {
    "effect": "3.22.5"
  }
}
```

- No `class-validator` / `class-transformer`: validation and response shaping use Standard Schema (Zod) through
  `StandardSchemaValidationPipe` and `StandardSchemaSerializerInterceptor` (both in `@nestjs/common` 12). An existing
  class-validator codebase keeps `ValidationPipe` (still supported in v12); do not register both styles for one route.
- `@fastify/static` is only needed for `SwaggerModule.setup()` (Swagger UI) on Fastify.
- `overrides.effect`: `npm audit` flags GHSA-7589-6fvf-x4pw in `effect` (via `prisma` → `@prisma/config` 7.10.1). The
  override clears it (audit exit 1 → 0); remove it once Prisma ships a fixed `effect`.
- npm is the package manager for this stack (`package-lock.json` committed, `npm ci` in CI).
- `prisma generate` must run before `tsc` (the generated client is gitignored): run it in CI before the typecheck.
- `@nestjs/observe` is not installed: it is the client for a hosted, paid observability service and does nothing
  without its app key. `nest new` 12 enables it (and writes agent skill files) unless you pass `--no-observe --skip-skills`.

## tsconfig.json and tsconfig.build.json (verified)

```json
{
  "compilerOptions": {
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "resolvePackageJsonExports": true,
    "target": "ES2023",
    "lib": ["ES2023"],
    "types": ["node"],
    "outDir": "./dist",
    "rootDir": ".",
    "strict": true,
    "strictPropertyInitialization": false,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "declaration": false,
    "removeComments": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "incremental": true
  },
  "include": ["src/**/*.ts", "test/**/*.ts", "prisma.config.ts", "vitest.config.ts", "vitest.config.e2e.ts"],
  "exclude": ["node_modules", "dist"]
}
```

```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "rootDir": "./src", "incremental": false },
  "include": ["src"],
  "exclude": ["node_modules", "test", "dist", "**/*.spec.ts"]
}
```

`nest-cli.json`: `{ "collection": "@nestjs/schematics", "sourceRoot": "src", "compilerOptions": { "deleteOutDir": true, "tsConfigPath": "tsconfig.build.json" } }`
(builder `tsc`, the default; `--builder rspack` replaces the deprecated webpack builder and is the monorepo default).

## Vitest (verified)

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';

// No SWC plugin: Vite 8's Oxc transform reads experimentalDecorators/emitDecoratorMetadata from tsconfig.
export default defineConfig({
  test: { globals: false, environment: 'node', root: './', include: ['src/**/*.spec.ts'] },
});
```

```typescript
// vitest.config.e2e.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    root: './',
    include: ['test/**/*.e2e-spec.ts', 'test/**/*.int-spec.ts'],
    fileParallelism: false,
    testTimeout: 20_000,
    hookTimeout: 30_000,
    // ConfigModule validates when AppModule is IMPORTED: env must exist at load time.
    // DATABASE_URL and REDIS_URL come from the shell/CI (real PostgreSQL and Redis).
    env: {
      NODE_ENV: 'test',
      JWT_ISSUER: 'https://issuer.test',
      JWT_AUDIENCE: 'orders-api',
      JWT_JWKS_URL: 'https://issuer.test/.well-known/jwks.json',
      THROTTLE_LIMIT: '20',
      THROTTLE_TTL_MS: '60000',
      BODY_LIMIT_BYTES: '2048',
    },
  },
});
```

## oxlint (verified)

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "ignorePatterns": ["src/generated/**", "dist/**"],
  "rules": {
    "typescript/no-explicit-any": "error",
    "typescript/no-floating-promises": "error",
    "typescript/no-misused-promises": "error",
    "no-console": "error"
  },
  "env": { "node": true }
}
```

An existing project on ESLint keeps its flat config (ESLint 10.15.0 + typescript-eslint 8.74.0, `recommendedTypeChecked`,
the same three rules); `typescript-eslint` 8.74 accepts TypeScript `<6.1`.

## Notes

- ESM: relative imports need the `.js` extension (an extensionless import fails `tsc` with TS2307 under `nodenext`);
  use `import.meta.dirname` instead of `__dirname`; `main.ts` uses top-level `await`.
- Decorator metadata: keep `emitDecoratorMetadata: true` and keep one e2e test that resolves a class-typed constructor
  dependency. With the flag off the e2e suite failed (planted-bug control) — it is the check that catches a broken transform.
- Vitest 5 caches transformed modules on disk. After changing `tsconfig.json` run `npx vitest --clearCache` once: a
  stale cache skipped 20 e2e tests in the verification run until it was cleared.
- Jest stays only for existing CommonJS projects: NestJS 12 packages are ESM-only, and Jest loads them only on Node `>=24.9`.
- Upgrading an existing v11 app: `npx @nestjs/cli@12 upgrade --dry-run`, then without `--dry-run`. It bumps every
  `@nestjs/*` package, TypeScript 6 and Jest 30, and applies the mechanical changes; it does not convert the project to ESM.
