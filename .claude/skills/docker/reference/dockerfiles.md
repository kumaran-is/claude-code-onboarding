````markdown
# Dockerfiles — All Stacks

Copy-ready multi-stage Dockerfiles and .dockerignore for all backend stacks. Every pattern follows: multi-stage build, non-root user (UID 1001), HEALTHCHECK, minimal runtime image.

---

## NestJS 11.x / Node 24 (pnpm + Prisma)

```dockerfile
# my-service — Multi-Stage Production Dockerfile (NestJS 11.x / Node 24)

# ============================================
# Stage 1: Base — node:24-alpine + pnpm + non-root user
# ============================================
FROM node:24-alpine AS base
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

## Spring Boot WebFlux 3.5.x / Java 21

```dockerfile
# my-service — Multi-Stage Production Dockerfile (Spring Boot WebFlux 3.5.x / Java 21)

# ============================================
# Stage 1: Build — Maven + JDK 21 (full build environment)
# ============================================
FROM maven:3.9-eclipse-temurin-21-alpine AS build

WORKDIR /app

# Copy POM first for Maven dependency cache layer
COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 \
    mvn dependency:go-offline -q

# Copy source and build (skip tests — run separately in CI)
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    mvn package -DskipTests -q

# ============================================
# Stage 2: Runtime — JRE only (no JDK, no Maven, no build tools)
# ============================================
FROM eclipse-temurin:21-jre-alpine

# Security: non-root user
RUN addgroup -g 1001 -S spring && \
    adduser -S spring -u 1001 -G spring

WORKDIR /app

# Copy only the application JAR
COPY --from=build --chown=spring:spring /app/target/*.jar app.jar

USER 1001

EXPOSE 8080

# Health check via Spring Actuator — allow 40s startup for JVM + Flyway migrations
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

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
.mvn
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

Executed pieces: `uv sync --locked` on a deps-only layer then the project (non-editable), stale lock fails `--locked` but not `--frozen`, `exec` keeps the server as PID 1, stdlib healthcheck exits 0/1. The `docker build` itself was not run here: build and `docker run` once before trusting it. Pinning rules and resolve commands: `skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

```dockerfile
# my-service — Multi-Stage Production Dockerfile (Python FastAPI 3.14 / uv)
FROM ghcr.io/astral-sh/uv:<x.y.z>@sha256:<digest> AS uv
FROM python:3.14-slim@sha256:<index-digest> AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

# Dependencies layer: cached until the lock changes; --locked fails on a stale lock
RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable      # project layer; only .venv is copied to runtime

FROM python:3.14-slim@sha256:<index-digest> AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8080

# stdlib only: the runtime image needs neither curl nor httpx; LIVENESS path (no dependency calls)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).status == 200 else 1)"]

# `exec` makes uvicorn PID 1 so SIGTERM reaches it (Cloud Run: SIGKILL follows after 10 s); $PORT expanded by the shell
CMD ["sh", "-c", "exec uvicorn my_service.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
```

Mutable `:latest` and `COPY --from=<image>:<tag>` are tag pins; a tag can be re-pointed after review. Non-root UID is numeric so Kubernetes `runAsNonRoot` can verify it.

**.dockerignore (Python):**
```
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.mypy_cache
.ruff_cache
htmlcov
.coverage
dist
build
*.egg-info
.git
.gitignore
.env*
!.env.example
.vscode
.idea
tests/
docs/
*.md
!README.md
*.log
.DS_Store
```

---

## Python Agentic AI (uv + gunicorn workers)

```dockerfile
# my-agent-service — Multi-Stage Production Dockerfile (Python 3.14 / LangGraph / gunicorn)

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.14-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:<x.y.z>@sha256:<digest> /uv /uvx /bin/   # pinned; see python-ci-supply-chain.md

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project       # deps layer; fails on a stale lock

COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

# ============================================
# Stage 2: Runtime — gunicorn + uvicorn workers
# ============================================
FROM python:3.14-slim AS runtime

RUN groupadd -r agent && useradd -r -g agent agent

WORKDIR /app

COPY --from=builder --chown=agent:agent /app/.venv /app/.venv
COPY --from=builder --chown=agent:agent /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"]

EXPOSE 8000

USER agent

# gunicorn + uvicorn workers: 4 workers, 120s timeout, graceful shutdown 30s
# `uvicorn.workers.UvicornWorker` is deprecated (DeprecationWarning, uvicorn 0.54): add the `uvicorn-worker` package;
# `from uvicorn_worker import UvicornWorker` imports cleanly (executed)
# app factory, no module-level `app`: gunicorn calls `create_app()` (executed with uvicorn_worker)
CMD ["gunicorn", "my_agent_service.main:create_app()", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-"]
```

---

## TypeScript / Fastify / Node 24

```dockerfile
# my-service — Multi-Stage Production Dockerfile (TypeScript/Fastify / Node 24)

# ============================================
# Stage 1: Production dependencies
# ============================================
FROM node:24-alpine AS deps

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nodeapp

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# ============================================
# Stage 2: Builder — TypeScript compile
# ============================================
FROM node:24-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ============================================
# Stage 3: Production Runner
# ============================================
FROM node:24-alpine AS runner

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nodeapp

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
USER nodeapp

COPY --from=deps --chown=nodeapp:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodeapp:nodejs /app/dist ./dist
COPY --from=builder --chown=nodeapp:nodejs /app/package.json ./

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

CMD ["node", "dist/index.js"]
```

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
