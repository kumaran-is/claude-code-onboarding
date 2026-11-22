# Agentic AI Deployment

Docker, docker-compose, production configuration, health checks, and operational patterns.

## Multi-Stage Dockerfile

**File:** `Dockerfile`

```dockerfile
# ============================================
# Stage 1: Builder — install dependencies
# ============================================
FROM python:3.14-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
# Pin uv to an exact release tag or digest (never :latest), same version as CI
COPY --from=ghcr.io/astral-sh/uv:<pinned-version> /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install production dependencies only
RUN uv sync --no-dev --locked

# Copy source code
COPY src/ src/

# ============================================
# Stage 2: Runtime — minimal production image
# ============================================
FROM python:3.14-slim AS runtime

# Security: run as non-root user
RUN groupadd -r agent && useradd -r -g agent agent

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"

EXPOSE 8000

# Switch to non-root user
USER agent

# gunicorn + uvicorn workers for production
# uvicorn.workers.UvicornWorker is deprecated: install the `uvicorn-worker` package and use its class
# (see docker/reference/dockerfiles.md); for a single process per container, run uvicorn --factory instead
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

## Docker Compose (Production-like)

**File:** `docker-compose.yml`

```yaml
services:
  # === Application ===
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - APP_ENV=production
      - LOG_LEVEL=info
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "2.0"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # === PostgreSQL (Checkpointing + Vector Store) ===
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-agents}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 1G

  # === Redis (Caching) ===
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M

  # === Prometheus (Metrics) ===
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml
      - promdata:/prometheus
    depends_on:
      - app

volumes:
  pgdata:
  redisdata:
  promdata:
```

## Prometheus Configuration

**File:** `prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - alerts.yml

scrape_configs:
  - job_name: "agent-service"
    static_configs:
      - targets: ["app:8000"]
    metrics_path: /metrics
    scrape_interval: 10s
```

## Health Checks

Use the readiness/liveness routes in `agentic-templates-core.md` §Health Check Route (executed): liveness returns without touching dependencies; readiness runs `SELECT 1` on the checkpointer pool and returns `503` with per-dependency status names (no error text) when a dependency fails.

- No LLM "ping" in health checks: every probe would bill a model call, and a provider blip would take every replica out of rotation at once. Track provider health with metrics and alerts (`agentic-observability.md`).
- No exception text in health responses (`"error": str(e)` leaks hostnames and driver messages to anything that can reach the probe). Log with `log_exception`, return a status code.

## Graceful Shutdown

The FastAPI lifespan owns shutdown: the `async with` block that opened the checkpointer/store pools closes them when the server stops, after uvicorn/gunicorn stop accepting requests and drain in-flight ones within their graceful timeout. Set the server's graceful timeout above `AGENT_TIMEOUT_S` so a run in progress can finish or hit its own deadline. Don't add `asyncio.sleep(...)` "drain" steps or a second shutdown hook that closes the same pools.

## Rate Limiting for LLM Endpoints

Limit per **verified principal and org** (not IP alone), in shared storage or at the API gateway: an in-process dictionary counts per replica, resets on restart and grows without bound. Pair request-rate limits with the cost/token budgets in `agentic-cost-optimization.md` §Budgets; a few long requests can cost more than many short ones. Return a typed `429` with `Retry-After`.

## Secret Management

- Keys come from the platform secret manager as env vars, typed `SecretStr` in settings (`agentic-config-project.md`); never logged, not even as a prefix. Log `key_configured=True` at startup.
- Rotation: the secret manager holds versions; deploy a new revision (or reload on a signal) to pick up the new version, then revoke the old one after traffic drains. No in-process key-rotation classes.

## Deployment Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Build | `docker build -t agent-service .` | Exit 0 |
| Readiness | `curl -fsS localhost:8000/api/v1/health/ready` | Exit 0 |
| Metrics | `curl localhost:8000/metrics` | Prometheus format |
| Lint | `ruff check src/` | No errors |
| Types | `mypy src/` | No errors |
| Tests | `uv run pytest -m "not live"` | All pass |
| Live gate | Live golden + failure matrix (`agentic-testing.md`) | PASS, or NOT RUN stated |
| Security | No secrets in code or logs | Verified |
