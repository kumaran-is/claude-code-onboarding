# NestJS Infrastructure Templates — Docker, Compose, Testing

Production-ready Docker, Docker Compose, and testing configuration templates for NestJS 11.x.

## Dockerfile

npm-based (the stack's package manager), non-root, production dependencies only. **Docker build NOT RUN in the
toolkit sandbox** (no Docker daemon); the same commands were run directly on Node 24 (`npm ci`, `prisma generate`,
`npm run build`, `npm prune --omit=dev` all exit 0; `node dist/main.js` served `/health/live` 200, kept Swagger off in
production (`/docs-json` 404) and exited 143 on SIGTERM). Pin the base image by digest in CI (`node:24-alpine@sha256:…`).

```dockerfile
# syntax=docker/dockerfile:1
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY prisma ./prisma/
COPY prisma.config.ts ./
RUN npm ci

FROM deps AS builder
COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
# prisma.config.ts reads DATABASE_URL via env(); generate needs only a syntactically valid value
RUN DATABASE_URL=postgresql://build:build@localhost:5432/build npx prisma generate \
 && npm run build \
 && npm prune --omit=dev

FROM node:24-alpine AS runner
ENV NODE_ENV=production PORT=3000
WORKDIR /app
COPY --from=builder --chown=node:node /app/package.json ./
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/dist ./dist
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:3000/health/live || exit 1
# exec form: node is PID 1 and receives SIGTERM, so enableShutdownHooks() runs
CMD ["node", "dist/main.js"]
```

- Migrations run as a separate release step (`npx prisma migrate deploy` in a job/init container), not at container start where several replicas would race. Note: `npm prune --omit=dev` does **not** remove the `prisma` CLI — `@prisma/client` 7.10.1 declares it as a peer, so npm keeps it.
- `main.ts` must listen on `0.0.0.0`; Fastify's default `127.0.0.1` is unreachable from outside the container.
- Secrets come from the platform's secret store as env vars at runtime; never `COPY .env`.

## Docker Compose (Development)

```yaml
# docker-compose.dev.yml - Development Environment
version: '3.9'

services:
  # PostgreSQL Database
  # NOTE: Credentials here must match DATABASE_URL in .env
  # .env: DATABASE_URL="postgresql://postgres:postgres@localhost:5432/{project_name}?schema=public"
  postgres:
    image: postgres:17-alpine
    container_name: {project_name}-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myservice
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Redis Cache
  redis:
    image: redis:7-alpine
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

## Vitest Configuration (vitest.config.mts)

Verified with Vitest 4.1.12 + `@vitest/coverage-v8` 4.1.12: thresholds fail the run when unmet (unit-only coverage 30% vs 80% → exit 1; thresholds lowered to 25% → exit 0).

```typescript
import swc from 'unplugin-swc';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.spec.ts'],
    root: './',
    // No passWithNoTests and no retry: an empty or flaky suite must fail, not pass.
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.spec.ts', 'src/generated/**', 'src/main.ts'],
      reporter: ['text', 'lcov'],
      thresholds: { lines: 80, branches: 70, functions: 80, statements: 80 },
    },
  },
  plugins: [swc.vite({ module: { type: 'es6' } })],
});
```

- `.mts`: the package is CommonJS; a `.ts` config with ESM syntax triggers Vite 8's CommonJS warning, and `__dirname` is not defined in ESM — use `import.meta.dirname` if you need paths.
- Vitest 4 removed `test.poolOptions`; `retry` hides flaky tests and `passWithNoTests` turns an empty suite into a pass — leave both out.
- E2E config: `nestjs-testing-integration-setup.md`.
