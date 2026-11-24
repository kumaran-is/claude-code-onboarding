# Docker Review Checklist

Pre-commit checklist for Dockerfiles, docker-compose files, and .dockerignore. Run before every Docker-related PR. Covers all stacks: NestJS/Node 24, Spring Boot 4.2 / Java 25, Python FastAPI, TypeScript/Fastify and MCP servers on Node 26.

---

## Dockerfile Optimization

- [ ] Dependencies copied before source code (layer cache preserved on code changes)
- [ ] Multi-stage build: build/compile stage separate from runtime stage
- [ ] Production stage contains ONLY runtime artifacts — no build tools, no dev dependencies
- [ ] `.dockerignore` present and excludes: `node_modules/`, `dist/`, `target/`, `.git/`, `.env*`, `**/*.test.*`, `docs/`
- [ ] Base image selection matches stack:
  - NestJS: `node:24-alpine` (not node:18, not node:22)
  - TypeScript/Fastify services and MCP servers: `node:26.13.1-trixie-slim` (or `node:26.13.1-alpine3.23` when every native dependency ships musl builds; runtime may be `gcr.io/distroless/nodejs26-debian13:nonroot`); builder and runtime on the same Node major and libc
  - Spring Boot: `eclipse-temurin:25-jre` runtime (JRE, not JDK)
  - Python: `python:3.14.10-slim-trixie@sha256:<index-digest>` (patch tag matches `.python-version`; not the full image, not bookworm/bullseye)
- [ ] RUN commands that modify the same layer are consolidated (avoids layer bloat)
- [ ] Package manager cache cleaned in the same RUN layer (or use `--mount=type=cache`)

## Container Security

- [ ] Non-root user created with specific UID/GID and a numeric `USER` (the Node/Java patterns use 1001, the Python pattern 10001)
- [ ] `USER` directive set before `EXPOSE` and `CMD`
- [ ] `COPY --chown=user:group` used when copying files to non-root-owned directories
- [ ] No secrets, API keys, or passwords in `ENV`, `ARG`, or `RUN` commands
- [ ] Base images pinned to a minor version AND a multi-arch index digest (`image:tag@sha256:...`); no `:latest`; no `COPY --from=<image-ref>` (use a pinned `FROM ... AS stage`); `# syntax=` pinned
- [ ] `HEALTHCHECK` configured with appropriate interval, timeout, start-period, and retries
  - NestJS (alpine has busybox wget): `wget --spider http://localhost:3000/health/live`
  - Node 26 slim / distroless (no curl or wget): exec-form `node -e "fetch('http://127.0.0.1:3000/health/live')..."` (distroless: `/nodejs/bin/node`)
  - Spring Boot (`eclipse-temurin:25-jre` ships no curl or wget; install curl in the runtime stage): `curl -fsS http://localhost:8080/actuator/health`
  - Python: stdlib only, on the LIVENESS path: `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).status == 200 else 1)"` (a slim image has no curl, and httpx may not be a runtime dependency)
- [ ] Configuration is not baked into the image: no `ENV` for env-varying values, no secrets in `ARG`; required settings have no code default
- [ ] `.dockerignore` is an ALLOW-list (`*` then `!src`, `!pyproject.toml`, `!uv.lock`) and the build-context size is checked; image file list compared before/after the change
- [ ] `CMD` is exec form, or a shell form that `exec`s the server, so PID 1 receives SIGTERM

## Docker Compose

- [ ] `depends_on` uses `condition: service_healthy` (not just `depends_on: [db]`)
- [ ] Every data service (PostgreSQL, Redis) has a `healthcheck` defined
- [ ] Custom networks configured — backend services on internal network, not exposed directly
- [ ] Volume names are explicit (named volumes, not anonymous)
- [ ] `restart: unless-stopped` or appropriate restart policy set
- [ ] Resource limits defined for production compose (`memory`, `cpus`)
- [ ] Environment variables use `.env` file — no hardcoded credentials in compose file
- [ ] Production compose uses Docker secrets (`_FILE` suffix env vars) — not plain env vars

## Image Size

- [ ] Final image size verified: Node <200MB, Python <300MB, Java JRE <250MB
- [ ] Build tools absent from runtime stage (no Maven, no npm devDependencies, no gcc)
- [ ] Package manager cache not in final layer
- [ ] Only necessary files copied to runtime stage
- [ ] Consider distroless for zero-CVE baseline (see `reference/advanced-patterns.md`)

## Development Workflow

- [ ] Development and production build targets are separate (`target: development` vs `target: runner`)
- [ ] Dev compose mounts source code volume for hot reload
- [ ] Debug port exposed in dev compose (Node: 9229, Python: 5678)
- [ ] Test compose isolated from dev compose (separate file or profile)
- [ ] `.env.example` committed — `.env` in `.gitignore`

## Networking

- [ ] Only necessary ports exposed (`EXPOSE` matches actual service port)
- [ ] Service names follow convention matching application connection strings
- [ ] Backend network marked `internal: true` (database not reachable from host directly in production)
- [ ] Health check endpoints do not require authentication
- [ ] Load balancer / reverse proxy considered for multi-replica setups

## Stack-Specific Checks

### NestJS / Node 24
- [ ] Uses `pnpm` (not npm) — `corepack enable && corepack prepare pnpm@latest --activate`
- [ ] Prisma client generated in builder stage (`pnpm prisma generate`)
- [ ] `pnpm prune --prod` run before copying node_modules to runner

### Spring Boot 4.2 / Java 25
- [ ] Runtime stage uses `eclipse-temurin:25-jre` (JRE, not JDK); build stage `eclipse-temurin:25-jdk` running `./mvnw` (copy `mvnw` + `.mvn/`; never the `maven:*` image, which has no arm64 build)
- [ ] JVM flags include `-XX:+UseContainerSupport` and `-XX:MaxRAMPercentage=75.0`
- [ ] `ENTRYPOINT` uses `-Djava.security.egd=file:/dev/./urandom` for faster startup
- [ ] `start-period` in HEALTHCHECK is at least 40s (Spring Boot startup time)

### Python FastAPI 3.14
- [ ] Uses `uv` (not pip) — from a pinned stage `FROM ghcr.io/astral-sh/uv:<x.y.z>@sha256:... AS uv`, never `:latest`, never `pip install uv`
- [ ] `uv sync --locked` with `UV_NO_DEV=1` (fails on a stale lock; `--frozen` installs it silently); deps layer uses `--no-install-project`, project layer `--no-editable`
- [ ] `UV_PYTHON_DOWNLOADS=0` so the venv uses the image's Python, which exists in the runtime stage; `UV_NO_BUILD=1` so a missing wheel fails the build instead of compiling
- [ ] `UV_COMPILE_BYTECODE=1` (the runtime runs `--read-only`; bytecode cannot be written later)
- [ ] Exec-form `CMD ["uvicorn", ...]` (or `sh -c 'exec uvicorn ...'`): uvicorn is PID 1; `docker stop` exits 0 with the lifespan shutdown logged, not 137
- [ ] Runs with `--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges` and a memory limit (`/tmp` needed by the 3.14 `forkserver` default)
- [ ] Framework (and any instrumentation library) pinned `==` in `pyproject.toml`; a test asserts spans are emitted
- [ ] `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1` set

### TypeScript/Fastify and MCP servers / Node 26
- [ ] Production deps stage uses `npm ci --omit=dev --ignore-scripts` (`--only=production` is legacy: npm 11 warns `Use --omit=dev`)
- [ ] TypeScript compiled to `dist/` in builder stage; `package.json` (with `"type": "module"`) copied to the runtime stage
- [ ] Exec-form `CMD ["node", "--import", "./dist/instrumentation.js", "dist/main.js"]` when OpenTelemetry is used (not `ts-node`, not `npm start`, no shell form)
- [ ] `NODE_OPTIONS=--max-old-space-size` at ~60–65% of the container memory limit (320 for 512 MiB)
- [ ] MCP over HTTP bound to `0.0.0.0`: `MCP_ALLOWED_HOSTS` (hostnames, no port; include `127.0.0.1` for the `HEALTHCHECK`) and `MCP_ALLOWED_ORIGINS` set, and orchestrator probes send an allowed `Host`
