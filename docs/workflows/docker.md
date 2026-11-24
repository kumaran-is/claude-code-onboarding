# Docker

> **When to use**: When containerizing any backend service, writing or reviewing Dockerfiles, setting up local dev compose, or optimizing container builds.
> **Prerequisites**: Service code written. Stack determined (NestJS / Spring Boot WebFlux / Python FastAPI / TypeScript Fastify).

## Overview

Containerization workflow using the `docker` skill. Covers writing production Dockerfiles (multi-stage, non-root, health check), docker-compose for local dev and production, and advanced patterns (build cache, multi-arch, distroless).

---

## Skills and Commands

| Skill / Command | Scope | What it produces |
|----------------|-------|-----------------|
| `docker` | Dockerfile + compose | Multi-stage Dockerfile, .dockerignore, docker-compose.dev.yml |
| `java-spring-api` | Spring Boot implementation | Application code — docker skill provides the Dockerfile |
| `nestjs-api` | NestJS implementation | Application code — includes Dockerfile template in `nestjs-templates-infrastructure.md` |
| `python-dev` | FastAPI implementation | Application code — docker skill provides multi-stage Dockerfile |
| `agentic-ai-dev` | Python agent deployment | Has `agentic-deployment.md` — docker skill extends those patterns |

---

## Phases

### Phase 1 — Write the Dockerfile

Load skill: `docker` → read `reference/dockerfiles.md`

Pick the matching stack:

| Stack | Base (build) | Base (runtime) | Port |
|-------|-------------|---------------|------|
| NestJS 11.x / Node 24 | `node:24-alpine` | `node:24-alpine` | 3000 |
| Spring Boot WebFlux 3.5.x | `maven:3.9-eclipse-temurin-21-alpine` | `eclipse-temurin:21-jre-alpine` | 8080 |
| Python FastAPI 3.14 | `python:3.14-slim` | `python:3.14-slim` | 8000 |
| TypeScript/Fastify / Node 24 | `node:24-alpine` | `node:24-alpine` | 3000 |
| TypeScript MCP server / Node 26 | `node:26.13.1-trixie-slim` (digest-pinned) | same | 3000 — template in `/scaffold-mcp-server` |

All patterns include: 4-stage multi-stage build, non-root user (UID 1001), HEALTHCHECK, .dockerignore.

**Validate the build:**
```bash
docker build -t myservice:test .
docker images myservice:test   # check size
docker run --rm -p 3000:3000 myservice:test  # smoke test
```

---

### Phase 2 — Set Up Local Dev Compose

Read `reference/compose-patterns.md` → Development Compose section.

```bash
# Start PostgreSQL 17 + Redis 7
docker compose -f docker-compose.dev.yml up -d

# Verify health
docker compose -f docker-compose.dev.yml ps
# postgres and redis should show "healthy"

# Tail logs
docker compose -f docker-compose.dev.yml logs -f
```

Credentials in docker-compose.dev.yml must match `DATABASE_URL` in `.env`:
- NestJS/Prisma: `postgresql://postgres:postgres@localhost:5432/myservice`
- Spring Boot/R2DBC: `r2dbc:postgresql://localhost:5432/myservice`
- Python/asyncpg: `postgresql+asyncpg://postgres:postgres@localhost:5432/myservice`

---

### Phase 3 — Run the Review Checklist

Read `assets/docker-review-checklist.md` before committing. Key gates:

| Gate | Requirement |
|------|------------|
| Multi-stage | Build tools absent from runtime stage |
| Non-root | `USER 1001` set in final stage |
| Health check | `HEALTHCHECK` configured with correct endpoint |
| .dockerignore | `node_modules/`, `.env*`, `.git/` excluded |
| Secrets | No credentials in `ENV`, `ARG`, or `RUN` commands |
| Stack-specific | pnpm for NestJS, JRE not JDK for Spring, uv for Python |

---

### Phase 4 — Optimize (if needed)

Read `reference/advanced-patterns.md` for:

```bash
# Build with cache mounts (requires BuildKit — default in Docker 23+)
DOCKER_BUILDKIT=1 docker build -t myservice:latest .

# Multi-arch build (needed when dev is Apple Silicon, prod is Linux/amd64)
docker buildx build --platform linux/amd64,linux/arm64 -t myservice:latest --push .

# Check image size breakdown
docker history myservice:latest
docker scout quickview myservice:latest
```

---

## Quick Reference

| Phase | Action | Gate |
|-------|--------|------|
| 1 — Dockerfile | `docker` skill → `reference/dockerfiles.md` | Build succeeds, image <500MB |
| 2 — Dev Compose | `docker` skill → `reference/compose-patterns.md` | postgres + redis show healthy |
| 3 — Review | `assets/docker-review-checklist.md` | All checklist items pass |
| 4 — Optimize | `reference/advanced-patterns.md` | Build cache active, multi-arch if required |

---

## Common Issues

- **`depends_on` doesn't wait for database**: Must use `condition: service_healthy` — not just `depends_on: [postgres]`
- **Hot reload not working**: Mount source volume AND add anonymous volume for `node_modules` to prevent host override
- **Spring Boot exits before health check passes**: Set `start-period: 40s` — JVM + Flyway migrations take time
- **Image >1GB**: Check `docker history` — build tools are in the runtime stage; switch to multi-stage
- **Credentials mismatch**: `DATABASE_URL` in `.env` must use `localhost` (host-side); in compose it uses the service name (`postgres`)

---

## Related Workflows

- [`feature-java-spring.md`](feature-java-spring.md) — Full Java Spring Boot feature lifecycle
- [`feature-nestjs.md`](feature-nestjs.md) — Full NestJS feature lifecycle
- [`feature-python-fastapi.md`](feature-python-fastapi.md) — Full Python FastAPI feature lifecycle
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — GitHub Actions CI/CD including Docker build and push
- [`security-audit.md`](security-audit.md) — Security review including container scanning
