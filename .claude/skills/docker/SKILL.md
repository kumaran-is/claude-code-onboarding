---
name: docker
description: "Use when writing or reviewing Dockerfiles, docker-compose files, or .dockerignore for any backend service. Covers multi-stage builds, container security hardening, compose orchestration, advanced build patterns, and a Docker review checklist for all 4 stacks: NestJS/Node 24, Spring Boot WebFlux 3.5.x/Java 21, Python FastAPI 3.14, and TypeScript/Fastify and MCP servers on Node 26."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Dockerfile, docker-compose, containerize, docker build, multi-stage build, docker image, container, dockerignore, docker run, docker scout
  related-skills: java-spring-api, nestjs-api, python-dev, agentic-ai-dev, architecture-design
  domain: infrastructure
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-14"
---

## Iron Law

**NO DOCKERFILE WITHOUT READING `reference/dockerfiles.md` FIRST — each stack has specific base images, build tools, and health check patterns that must be used exactly**

# Docker

Production-ready containerization for NestJS/Node 24, Spring Boot WebFlux 3.5.x/Java 21, Python FastAPI 3.14, and TypeScript/Fastify and MCP servers on Node 26. All patterns follow: multi-stage build, non-root user, HEALTHCHECK, .dockerignore.

## When to Use

- Writing a Dockerfile for any backend service
- Writing or updating docker-compose files for local dev or production
- Reviewing an existing Dockerfile for security, size, or correctness
- Adding build cache optimization (`--mount=type=cache`)
- Setting up Docker Compose secrets for production
- Building multi-architecture images (linux/amd64 + linux/arm64)
- Debugging container build failures, slow builds, or large image sizes

## How This Skill Relates to Others

| Skill | Scope |
|-------|-------|
| **docker** (this skill) | Container definitions, compose files, build patterns |
| **java-spring-api** | Java application code — loads docker skill for Dockerfile |
| **nestjs-api** | NestJS templates include Dockerfile — this skill extends those patterns |
| **python-dev** | FastAPI code — loads docker skill for Dockerfile |
| **agentic-ai-dev** | Python agent code — has deployment reference that this skill augments |

## Process

### Step 1: Choose the Right Dockerfile Pattern

Read `reference/dockerfiles.md` for the complete, copy-ready Dockerfile for your stack:

| Stack | Base Image | Build Tool | Port |
|-------|-----------|-----------|------|
| NestJS 11.x / Node 24 | node:24-alpine | pnpm | 3000 |
| Spring Boot WebFlux 3.5.x | maven:3.9-eclipse-temurin-21-alpine → eclipse-temurin:21-jre-alpine | Maven | 8080 |
| Python FastAPI 3.14 | python:3.14.10-slim-trixie@sha256 | uv 0.13.9 | 8080 |
| Python Agentic AI | python:3.14.10-slim-trixie@sha256 | uv 0.13.9 (+ `uvicorn --workers N` off Cloud Run) | 8080 |
| TypeScript/Fastify, MCP servers / Node 26 | node:26.13.1-trixie-slim@sha256 (distroless `nodejs26-debian13` optional) | npm | 3000 |

### Step 2: Set Up Docker Compose

Read `reference/compose-patterns.md` for:
- Development compose (PostgreSQL 17 + Redis 7)
- Production compose with Docker secrets (`_FILE` env pattern)
- Health check dependency ordering (`condition: service_healthy`)
- Network isolation (internal backend network)
- Resource limits and restart policies

### Step 3: Apply Advanced Patterns (if needed)

Read `reference/advanced-patterns.md` for:
- Build cache mounts (`--mount=type=cache`) for Maven, npm, pip/uv — cuts rebuild time significantly
- Multi-architecture builds (`docker buildx`) for linux/amd64 + linux/arm64
- Distroless runtime images for zero-CVE base
- Build-time secrets (BuildKit `--mount=type=secret`)
- Diagnostics: slow builds, large images, networking failures, hot-reload issues

### Step 4: Review with Checklist

Read `assets/docker-review-checklist.md` before committing any Dockerfile or compose file. Covers 6 categories: optimization, security, compose, image size, dev workflow, networking.

## Reference Files

| File | Content | Load When |
|------|---------|-----------|
| `reference/dockerfiles.md` | Copy-ready multi-stage Dockerfiles + .dockerignore for all 5 stack variants | Writing any new Dockerfile |
| `reference/compose-patterns.md` | Dev compose (PostgreSQL+Redis), production compose with Docker secrets, health checks, networks, resource limits | Writing or reviewing docker-compose files |
| `reference/advanced-patterns.md` | Build cache mounts (all stacks), multi-arch buildx, distroless images, build secrets, diagnostics | Optimizing builds or debugging container issues |
| `assets/docker-review-checklist.md` | 30-item Docker review checklist (6 categories) with stack-specific items | Before committing Dockerfile or compose changes |

## Error Handling

**Build fails with "not found" or permission error**: Check .dockerignore is not excluding required files. Verify COPY paths match actual project structure.

**Image too large (>500MB for Node/Python, >300MB for Java runtime)**: Read `reference/advanced-patterns.md` section "Image Size Optimization" — switch to multi-stage if single-stage, or distroless runtime.

**Container exits immediately**: Check HEALTHCHECK target path matches the actual health endpoint. Verify USER directive comes after all COPY operations. Check CMD vs ENTRYPOINT usage.

**docker-compose: service fails to connect to database**: Verify `depends_on: condition: service_healthy` is set. Verify DATABASE_URL credentials match docker-compose environment values exactly.
