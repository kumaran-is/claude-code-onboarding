# NestJS Infrastructure Templates — Docker, Compose, Testing

Production-ready Docker, Docker Compose, and testing configuration templates for NestJS 12.x.

## Dockerfile

npm-based (the stack's package manager), non-root, production dependencies only. Verified 2026-11-24 on NestJS 12.6.0,
Node 26.13.1 and Docker Engine 29.8.0: `docker build` exit 0, the container ran as `node`, `/health` answered 200,
then the container and image were removed. Pin the base image by digest in CI (`node:26-alpine@sha256:…`).

```dockerfile
# syntax=docker/dockerfile:1
FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.build.json nest-cli.json prisma.config.ts ./
COPY prisma ./prisma
COPY src ./src
# prisma.config.ts reads DATABASE_URL at load; generate never connects, so a placeholder is enough.
RUN DATABASE_URL=postgresql://placeholder@localhost:5432/placeholder npx prisma generate && npx nest build

FROM node:26-alpine AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

FROM node:26-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY --from=prod-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD wget -qO- http://127.0.0.1:3000/health || exit 1
# exec form: node is PID 1 and receives SIGTERM, so enableShutdownHooks() runs.
# --import loads the OpenTelemetry entry before the app (nestjs-observability.md); drop it if tracing is off.
CMD ["node", "--import", "./dist/instrumentation.js", "dist/main.js"]
```

- `package.json` must keep `"type": "module"` in the runtime image (it is copied): NestJS 12 builds emit ESM.
- A separate `prod-deps` stage with `npm ci --omit=dev --ignore-scripts` keeps dev tools (Prisma CLI, Vitest, oxlint)
  out of the final image; `npm prune --omit=dev` does not remove the `prisma` CLI, which `@prisma/client` 7.10.1 peers on.
- Migrations run as a separate release step (`npx prisma migrate deploy` in a job/init container), not at container start where several replicas would race. Note: `npm prune --omit=dev` does **not** remove the `prisma` CLI — `@prisma/client` 7.10.1 declares it as a peer, so npm keeps it.
- `main.ts` must listen on `0.0.0.0`; Fastify's default `127.0.0.1` is unreachable from outside the container.
- Secrets come from the platform's secret store as env vars at runtime; never `COPY .env`.

## Docker Compose (Development)

```yaml
# docker-compose.dev.yml - Development Environment (the top-level `version:` key is obsolete in Compose v2)

services:
  # PostgreSQL Database
  # NOTE: Credentials here must match DATABASE_URL in .env
  # .env: DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/{project_name}?schema=public"
  postgres:
    image: postgres:18
    container_name: {project_name}-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myservice
    volumes:
      # PostgreSQL 18 images keep data under /var/lib/postgresql/<major>; mount the parent directory
      - postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Redis Cache
  redis:
    image: redis:8
    container_name: {project_name}-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local
```

## Docker Ignore (.dockerignore)

```
# Dependencies
node_modules

# Build outputs
dist
coverage
test-results

# Development files
*.md
!README.md
.env*
!.env.example
.git
.gitignore
.vscode
.idea

# Test files
**/*.spec.ts
**/*.test.ts
**/*.e2e-spec.ts
test/

# Documentation
docs/

# Misc
*.log
*.tmp
.DS_Store
Thumbs.db
```

## Vitest Configuration (vitest.config.ts)

Vitest 5.1.1 in an ESM package (`"type": "module"`), verified 2026-11-24 on NestJS 12.6.0 (9 unit + 23 e2e tests).
No SWC plugin: Vite 8's Oxc transform reads `experimentalDecorators` and `emitDecoratorMetadata` from `tsconfig.json`.
With `emitDecoratorMetadata` turned off the e2e suite failed (class-typed constructor injection resolved `undefined`), so keep
one test that resolves a class-typed dependency as the canary. Coverage thresholds failed an unmet run on Vitest 4.1
(30% vs 80% → exit 1); with `@vitest/coverage-v8` 5.1.1 that negative check was NOT RUN, so prove it once per project.

```typescript
import { defineConfig } from 'vitest/config';

// No SWC plugin: Vite 8's Oxc transform reads experimentalDecorators/emitDecoratorMetadata from tsconfig.
export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    root: './',
    include: ['src/**/*.spec.ts'],
    // No passWithNoTests and no retry: an empty or flaky suite must fail, not pass.
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.spec.ts', 'src/generated/**', 'src/main.ts', 'src/instrumentation.ts'],
      reporter: ['text', 'lcov'],
      thresholds: { lines: 80, branches: 70, functions: 80, statements: 80 },
    },
  },
});
```

- Plain `.ts` config files: the package is ESM, so the `.mts` names used for CommonJS packages are unnecessary.
  Use `import.meta.dirname` instead of `__dirname`.
- After changing `tsconfig.json`, run `npx vitest --clearCache` (clears the caches, runs no tests): Vitest 5's file-system
  module cache served stale transforms, and 20 e2e tests were skipped until the cache was cleared.
- `retry` hides flaky tests and `passWithNoTests` turns an empty suite into a pass — leave both out.
- E2E config: `nestjs-testing-integration-setup.md`.
