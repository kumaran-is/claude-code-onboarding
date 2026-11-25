````markdown
# Dockerfiles — All Stacks

Copy-ready multi-stage Dockerfiles and .dockerignore for all backend stacks. Every pattern follows: multi-stage build, non-root user (UID 1001), HEALTHCHECK, minimal runtime image.

---

## NestJS 12.x / Node 26 (pnpm + Prisma)

```dockerfile
# my-service — Multi-Stage Production Dockerfile (NestJS 12.x / Node 26)

# ============================================
# Stage 1: Base — node:26-alpine + pnpm + non-root user
# ============================================
FROM node:26-alpine AS base
RUN corepack enable && corepack prepare pnpm@latest --activate
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nestjs

# ============================================
# Stage 2: Dependencies — layer cache for pnpm installs
# ============================================
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
COPY prisma ./prisma/
RUN pnpm install --frozen-lockfile

# ============================================
# Stage 3: Builder — TypeScript compile + Prisma client + prune
# ============================================
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm prisma generate
RUN pnpm build
RUN pnpm prune --prod

# ============================================
# Stage 4: Runner — minimal production image
# ============================================
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
USER nestjs
COPY --from=builder --chown=nestjs:nodejs /app/dist ./dist
COPY --from=builder --chown=nestjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nestjs:nodejs /app/package.json ./
COPY --from=builder --chown=nestjs:nodejs /app/prisma ./prisma
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health/live || exit 1
EXPOSE 3000
CMD ["node", "dist/main.js"]
```

**.dockerignore (NestJS):**
```
node_modules
.pnpm-store
dist
coverage
test-results
*.md
!README.md
.env*
!.env.example
.git
.gitignore
.vscode
.idea
**/*.spec.ts
**/*.test.ts
**/*.e2e-spec.ts
test/
docs/
*.log
*.tmp
.DS_Store
```

---

## Spring Boot 4.2 / Java 25

```dockerfile
# my-service — Multi-Stage Production Dockerfile (Spring Boot 4.2 / Java 25)

# ============================================
# Stage 1: Build — JDK 25 + Maven wrapper (wrapper pins Maven 3.10.2)
# ============================================
FROM eclipse-temurin:25-jdk AS build

WORKDIR /app

# Copy wrapper + POM first for Maven dependency cache layer
COPY mvnw pom.xml ./
COPY .mvn ./.mvn
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp dependency:go-offline

# Copy source and build (skip tests — run separately in CI)
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -DskipTests package

# ============================================
# Stage 2: Runtime — JRE only (no JDK, no Maven, no build tools)
# ============================================
FROM eclipse-temurin:25-jre

# Ubuntu-based image with no curl or wget: install curl for the HEALTHCHECK
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd --system --gid 1001 spring && \
    useradd --system --uid 1001 --gid spring spring

WORKDIR /app

# Copy only the application JAR
COPY --from=build --chown=spring:spring /app/target/*.jar app.jar

USER 1001

EXPOSE 8080

# Health check via Spring Actuator — allow 40s startup for JVM + Flyway migrations
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8080/actuator/health || exit 1

# JVM tuning: container-aware heap (75% of limit), secure random, active profile from env
ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
```

**.dockerignore (Spring Boot):**
```
target/
.git
.gitignore
*.md
!README.md
.env*
!.env.example
.vscode
.idea
*.iml
src/test/
docs/
*.log
.DS_Store
```

**Note:** `SPRING_PROFILES_ACTIVE` is passed as an environment variable in docker-compose or Cloud Run — not baked into the image.

---

## Python FastAPI 3.14 (uv — multi-stage)

Verified 2026-11-23 against uv 0.13.9, CPython 3.14.10 and Docker Engine 29.8.0: `docker build --check` 0, build 0 (263 MB), run with `--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --memory 256m --pids-limit 128`: `/health/live` 200, uid 10001, write to `/app` refused, `CapEff` 0, `NoNewPrivs` 1, Docker health `healthy`, `docker stop` in under 1 s with exit 0 and the lifespan shutdown logged (exit 0 because uvicorn is PID 1; the same server on a host or behind `--init` exits 143 after a clean shutdown: `deployment-ci-cd/reference/python-ci-supply-chain.md` section 8). Controls: the same server wrapped as `sh -c "uvicorn ...; true"` ignored SIGTERM (stop took the full 5 s timeout, exit 137, no shutdown log); `CMD sleep` turned the health status `unhealthy`. Digests resolved with `docker buildx imagetools inspect` on that date; pinning rules: `skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
# Use the image's Python (a uv-downloaded one would not exist in the runtime stage);
# compile bytecode at build time because the runtime filesystem is read-only.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1 UV_NO_BUILD=1
# Dependencies layer: cached until the lock changes. UV_NO_BUILD: fail instead of compiling a third-party sdist.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --locked --no-install-project --no-editable
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src/ src/
# Project layer: non-editable, so only .venv is copied to the runtime stage.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
# root-owned venv: the app user can read and execute it, not modify it
COPY --from=builder --chown=root:root /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8080
# stdlib only: the runtime image needs neither curl nor httpx; LIVENESS path (no dependency calls)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).status == 200 else 1)"]
# Exec form: uvicorn is PID 1 and receives SIGTERM directly (graceful shutdown runs the lifespan exit).
CMD ["uvicorn", "my_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "8", "--no-access-log"]
```

- Port 8080 is Cloud Run's default `$PORT`. If a platform injects another port, use `CMD ["sh", "-c", "exec uvicorn ... --port ${PORT:-8080}"]`: the `exec` is what keeps uvicorn PID 1 (the control above shows what happens without it). Keep `--timeout-graceful-shutdown` below the platform's SIGKILL window (Cloud Run: 10 s after SIGTERM).
- Run with `--read-only --tmpfs /tmp`: `/tmp` must stay writable because multiprocessing's `forkserver` (the Linux default since 3.14) needs it (`python-dev/reference/asyncio-concurrency-and-tasks.md` section 5).
- Workspace member image (one lock, several services): `uv-package-manager` playbook section 6 (`--frozen --no-install-workspace --package <member>` then `--locked --package <member>`; built and verified).
- Mutable `:latest` and `COPY --from=<image>:<tag>` are tag pins; a tag can be re-pointed after review. Non-root UID is numeric so Kubernetes `runAsNonRoot` can verify it.

**.dockerignore (Python) — allow-list:**
```
*
!pyproject.toml
!uv.lock
!.python-version
!README.md
!src
```

An allow-list keeps tests, `.venv`, `.env*`, caches and `.git` out of the build context without enumerating them; add a line per extra path the build needs (e.g. `!alembic`, `!alembic.ini`).

---

## Python Agentic AI / several workers per container

Use the same Dockerfile. One process per container is the default on Cloud Run (scale with instances and `--concurrency`). Where several worker processes per container are wanted (VMs, fixed-size pods), uvicorn's own process manager is enough:

```dockerfile
CMD ["uvicorn", "my_agent_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--timeout-graceful-shutdown", "8", "--no-access-log"]
```

Executed in the hardened container above (`--read-only --tmpfs /tmp --memory 512m`): two workers served `/health/live`, `docker stop` took 2 s with exit 0 and both workers logged their lifespan shutdown. Size `--workers` from the memory limit (each worker loads the full app, model clients included). Gunicorn (27.0.1) with `uvicorn_worker.UvicornWorker` (uvicorn-worker 0.4.0; `uvicorn.workers.UvicornWorker` is deprecated) is an alternative when you need its `--max-requests` recycling; not re-validated in this pass.

---

## TypeScript / Fastify / MCP server — Node 26

Verified 2026-11-23 against Node 26.13.1, npm 11.20.0 and Docker Engine 29.8.0: built, run with `--read-only --cap-drop ALL --memory 512m`, healthy, called from the host by an MCP SDK client, `docker stop` in 1 s with exit 0. Uses the image's built-in `node` user (uid 1000) instead of creating one. NestJS stays on the Node 26 pattern above.

```dockerfile
# syntax=docker/dockerfile:1
# my-service — Multi-Stage Production Dockerfile (TypeScript/Fastify or MCP server / Node 26, ESM output from tsc)
# Base image pinned by multi-arch index digest (resolved 2026-11-23). Renovate/Dependabot bump it.
ARG NODE_IMAGE=node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts
COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

FROM ${NODE_IMAGE} AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --ignore-scripts

FROM ${NODE_IMAGE} AS runtime
# Heap below the container limit: 320 MiB old space for a 512 MiB limit (384 let RSS pass the limit under load).
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=320
WORKDIR /app
# Root-owned, read-only to the app user. package.json carries "type": "module".
COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER node
EXPOSE 3000
# Docker/Compose only (Kubernetes and Cloud Run use their own probes). Slim has no curl/wget: node's fetch on LIVENESS.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
# Exec form: node is PID 1 and receives SIGTERM. --import preloads the OpenTelemetry bootstrap; drop it without OTel.
CMD ["node", "--import", "./dist/instrumentation.js", "dist/main.js"]
```

- `--ignore-scripts` blocks dependency install scripts; drop it only for a package that needs one (native build), and list that package in the PR.
- An MCP server bound to `0.0.0.0` also needs `MCP_ALLOWED_HOSTS` (hostnames without port, including `127.0.0.1` for the `HEALTHCHECK`) and `MCP_ALLOWED_ORIGINS`: `.claude/skills/mcp-builder/reference/production-deployment-docker.md` §0, which also has the distroless runtime variant.

**.dockerignore (TypeScript/Node):**
```
node_modules
dist
coverage
.git
.gitignore
.env*
!.env.example
*.md
!README.md
.vscode
.idea
**/*.spec.ts
**/*.test.ts
test/
docs/
*.log
.DS_Store
```
````
