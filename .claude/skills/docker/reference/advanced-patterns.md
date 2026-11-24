# Advanced Docker Patterns

Build cache mounts, multi-architecture builds, distroless images, build-time secrets, and diagnostic guides. Load this file when optimizing build performance or debugging container issues.

---

## Build Cache Mounts (`--mount=type=cache`)

Persists package manager caches across builds — eliminates re-downloading dependencies on every build. Requires BuildKit (enabled by default in Docker 23+).

### Maven (Spring Boot)

```dockerfile
# Cache ~/.m2 across builds — Maven never re-downloads unchanged deps
RUN --mount=type=cache,target=/root/.m2 \
    mvn dependency:go-offline -q

RUN --mount=type=cache,target=/root/.m2 \
    mvn package -DskipTests -q
```

### npm (Node.js / NestJS / Fastify)

```dockerfile
# Cache ~/.npm across builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev
```

### pnpm (NestJS)

```dockerfile
# Cache pnpm store across builds
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
```

### pip / uv (Python)

```dockerfile
# Cache uv download cache across builds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
```

**Impact:** Maven cold build ~3 min -> cached ~15 sec. npm cold ~90 sec -> cached ~5 sec.

---

## Multi-Architecture Builds (linux/amd64 + linux/arm64)

Required for Apple Silicon development targeting Linux/amd64 production, or when building for ARM cloud instances.

```bash
# One-time setup: create a multi-arch builder
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap

# Build and push both architectures simultaneously
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/myservice:latest \
  --tag registry.example.com/myservice:1.2.3 \
  --push \
  .

# Build locally without pushing (for testing)
docker buildx build \
  --platform linux/amd64 \
  --tag myservice:test \
  --load \
  .
```

**In GitHub Actions:**
```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@<40-hex-sha> # v3.x.y (pin by SHA)

- name: Build and push
  uses: docker/build-push-action@<40-hex-sha> # v5.x.y (pin by SHA)
  with:
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

---

## Distroless Runtime Images

Distroless images contain only the application runtime — no shell, no package manager, no OS utilities. Eliminates entire classes of CVEs. Trade-off: harder to debug (no `docker exec bash`).

### Node.js Distroless

Builder and runtime must share the Node major and libc (an alpine/musl builder with a glibc distroless runtime breaks native modules). Verified 2026-11-23: the image below runs healthy as uid 65532 with no shell (296 MB vs 418 MB on slim for the same app).

```dockerfile
ARG NODE_IMAGE=node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.json ./
COPY src ./src
RUN npm run build && npm prune --omit=dev

# Distroless runtime — no shell; the entrypoint is already node, so CMD lists only node arguments
FROM gcr.io/distroless/nodejs26-debian13:nonroot@sha256:ffa8a7545403036c94ec76674b5dbac2d425af2d679147cdf3e30180071487b7
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY package.json ./
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["/nodejs/bin/node", "-e", "fetch('http://127.0.0.1:3000/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["dist/main.js"]
```

### Java Distroless

```dockerfile
FROM maven:3.9-eclipse-temurin-21-alpine AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -DskipTests -q

# Distroless Java 21 runtime
FROM gcr.io/distroless/java21-debian12
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
CMD ["app.jar"]
```

**When to use distroless:**
- Production images that pass a container scanning gate (e.g., Trivy, Docker Scout)
- Services where `docker exec` debugging is done via sidecar or log-only
- Regulated environments (PCI-DSS, HIPAA) requiring minimal attack surface

**When NOT to use distroless:**
- Development images (you lose the ability to exec into the container)
- Images that need shell scripts in CMD/ENTRYPOINT

---

## Build-Time Secrets (BuildKit)

Never pass secrets as `ENV` or `ARG` — they remain in layer history. Use `--mount=type=secret` instead.

```dockerfile
# Access a secret during build without leaving it in any layer
FROM alpine AS build
RUN --mount=type=secret,id=npm_token \
    NPM_TOKEN=$(cat /run/secrets/npm_token) \
    npm config set //registry.npmjs.org/:_authToken=$NPM_TOKEN && \
    npm install --ignore-scripts
```

```bash
# Build with secret passed from local file or env var
docker buildx build \
  --secret id=npm_token,src=$HOME/.npm_token \
  --tag myservice:latest \
  .

# Or from environment variable
docker buildx build \
  --secret id=npm_token,env=NPM_TOKEN \
  --tag myservice:latest \
  .
```

---

## Diagnostics

### Slow Builds (>5 min)

**Symptoms:** Every build re-downloads dependencies even when `package.json` / `pom.xml` unchanged.

**Root cause:** Source code copied before dependency files — any source change invalidates the dependency layer.

**Fix:**
```dockerfile
# Wrong — source copied before deps, cache busted on every code change
COPY . .
RUN npm install

# Correct — deps layer cached independently of source
COPY package*.json ./
RUN npm ci
COPY . .         # only invalidates build stage, not deps stage
```

---

### Image Too Large (>500MB for Node/Python, >400MB for Java runtime)

**Symptoms:** `docker images` shows unexpectedly large image, slow pushes/pulls.

**Diagnosis:**
```bash
docker history myservice:latest --no-trunc
docker scout quickview myservice:latest
```

**Root causes + fixes:**

| Cause | Fix |
|-------|-----|
| Build tools in runtime stage | Multi-stage build — only COPY artifacts to runner |
| `node_modules` in runtime stage includes devDependencies | Run `npm prune --production` or `pnpm prune --prod` in builder before COPY |
| `.git` directory in build context | Add `.git` to `.dockerignore` |
| `target/` or `dist/` from previous build in context | Add `target/` and `dist/` to `.dockerignore` |
| Python `__pycache__` and `.pyc` files | Set `PYTHONDONTWRITEBYTECODE=1`, add `__pycache__` to `.dockerignore` |

---

### Container Exits Immediately

**Symptoms:** `docker run` exits with code 0 or 1 with no output.

**Diagnosis:**
```bash
docker run --rm myservice:latest  # see exit code
docker logs <container-id>        # see stdout/stderr
docker run --rm -it --entrypoint sh myservice:latest  # shell into image
```

**Common causes:**
- `CMD` path wrong — verify `dist/main.js` or `app.jar` exists: `docker run --rm -it --entrypoint ls myservice:latest /app`
- `USER` directive before files are copied — COPY uses the user at time of execution; switch USER after all COPYs
- Health check runs before app is ready — increase `start-period`

---

### Service Cannot Connect to Database in Compose

**Symptoms:** App container exits with connection refused on startup.

**Root cause:** App starts before database is healthy.

**Fix:**
```yaml
# Wrong
depends_on:
  - postgres          # only waits for container start, not health

# Correct
depends_on:
  postgres:
    condition: service_healthy   # waits for healthcheck to pass
```

Verify the `healthcheck` is defined on the `postgres` service — `condition: service_healthy` has no effect without it.

---

### Hot Reload Not Working in Dev Container

**Symptoms:** File changes in host not reflected in running container.

**Root cause:** Volume not mounted, or node_modules override not set.

**Fix:**
```yaml
volumes:
  - .:/app                # mount host source into container
  - /app/node_modules     # keep image's node_modules (not host's)
  - /app/dist             # keep compiled output
```

The anonymous volumes for `node_modules` and `dist` prevent the host directory from shadowing the image's installed packages.

---

## Container Inspection Commands

```bash
# Process inspection
docker compose top                    # Show processes running inside each container
docker stats                          # Live CPU/memory/network/disk usage per container
docker stats --no-stream              # One-time snapshot (useful in scripts)

# Container internals
docker compose exec app sh            # Shell into running app container
docker compose exec db psql -U postgres  # Direct psql into postgres container
docker compose exec app env           # Dump all env vars in container

# Image and layer inspection
docker image inspect <image>          # Full image metadata
docker history <image>                # Layer-by-layer build history + sizes
```

## Network Debugging

```bash
# DNS resolution inside container
docker compose exec app nslookup db         # Verify "db" resolves to postgres container
docker compose exec app nslookup redis      # Verify service name DNS works

# Connectivity checks
docker compose exec app wget -qO- http://api:3000/health  # Test inter-service HTTP

# Network inspection
docker network ls                           # List all Docker networks
docker network inspect <project>_default    # Full network config, connected containers, IPs
```

## Cleanup Commands

```bash
# Progressive cleanup (safe to running containers)
docker compose down                   # Stop and remove containers (keep volumes)
docker compose down -v                # ⚠️ Also removes named volumes (DATA LOSS)
docker compose down --rmi local       # Also removes locally-built images

# System-wide cleanup (reclaim disk space)
docker system prune                   # Remove stopped containers, unused networks, dangling images
docker system prune -a                # ⚠️ Also removes unused images (not just dangling)
docker volume prune                   # ⚠️ Remove all unused volumes

# Check disk usage
docker system df                      # Show Docker disk usage breakdown
```
