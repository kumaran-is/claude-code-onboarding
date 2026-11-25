# Docker Compose Patterns

Compose configurations for development, production, and testing. Covers: PostgreSQL + Redis dev setup, Docker secrets for production, health check ordering, network isolation, resource limits.

---

## Development Compose (PostgreSQL 18 + Redis 7)

Standard dev compose for all backend stacks. Credentials must match the service's `.env` / `DATABASE_URL`.
The `postgres` image 18+ refuses to start with a volume at `/var/lib/postgresql/data`: mount
`/var/lib/postgresql` (data lands in `18/docker`). An existing 17 volume needs dump/restore or
`pg_upgrade`, not a tag bump. For pgvector use `pgvector/pgvector:0.8.7-pg18-trixie` with the same mount.

```yaml
# docker-compose.dev.yml — Local Development Environment
# Start: docker compose -f docker-compose.dev.yml up -d
# Stop:  docker compose -f docker-compose.dev.yml down

services:
  postgres:
    image: postgres:18.7-alpine
    container_name: ${PROJECT_NAME:-myservice}-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: ${PROJECT_NAME:-myservice}
    volumes:
      - postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  redis:
    image: redis:8.2-alpine
    container_name: ${PROJECT_NAME:-myservice}-redis
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

  # ── Email testing ──────────────────────────────────────────────────────────
  # Mailpit catches all outbound email — no real SMTP needed for local dev
  # Configure your app: SMTP_HOST=localhost, SMTP_PORT=1025, SMTP_FROM=test@local
  # View captured emails: http://localhost:8025
  mailpit:                            # Local email testing (web UI: http://localhost:8025)
    image: axllent/mailpit:latest
    container_name: ${PROJECT_NAME:-myservice}-mailpit
    ports:
      - "8025:8025"                   # Web UI — view sent emails at http://localhost:8025
      - "1025:1025"                   # SMTP — configure app SMTP_HOST=localhost SMTP_PORT=1025
    restart: unless-stopped

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local
```

**Connection strings matching the above** (`.env`, gitignored). `.env` files do not expand `${VAR}` (dotenv, `node --env-file` and `@nestjs/config`
without `expandVariables` keep it literally), so write the same value as `POSTGRES_PASSWORD` in place of the placeholder:
```
# NestJS / Prisma
DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD value>@localhost:5432/myservice?schema=public"
REDIS_URL="redis://localhost:6379"

# Python FastAPI / SQLAlchemy async
DATABASE_URL="postgresql+asyncpg://postgres:<POSTGRES_PASSWORD value>@localhost:5432/myservice"

# Spring Boot WebFlux / R2DBC
SPRING_R2DBC_URL=r2dbc:postgresql://localhost:5432/myservice
SPRING_R2DBC_USERNAME=postgres
SPRING_R2DBC_PASSWORD=<POSTGRES_PASSWORD value>
```

---

## Production Compose — with Docker Secrets

Use Docker secrets for production credentials instead of plain environment variables. The `_FILE` suffix tells Postgres, Redis, and most services to read the value from a file path.

```yaml
# docker-compose.prod.yml — Production-like Environment with Docker Secrets

services:
  app:
    build:
      context: .
      target: runner        # targets the final stage in multi-stage Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      NODE_ENV: production
      PORT: "3000"
      # Secrets injected at runtime via files — not visible in env listing
      DATABASE_URL_FILE: /run/secrets/database_url
      REDIS_URL_FILE: /run/secrets/redis_url
    secrets:
      - database_url
      - redis_url
    networks:
      - frontend
      - backend
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    # Resource limits — prevents a single container consuming entire host resources
    # Tune per stack: NestJS/Python=512M, Spring Boot=1G (JVM overhead)
    # cpus: "1.0" = 1 full CPU core equivalent
    deploy:
      resources:
        limits:
          cpus: "1.0"             # Cap at 1 CPU — prevents runaway processes
          memory: 512M            # Adjust per stack: NestJS=512M, Spring=1G, Python=512M
        reservations:
          cpus: "0.25"
          memory: 256M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
    restart: unless-stopped

  postgres:
    image: postgres:18.7-alpine
    environment:
      # _FILE variants read credentials from Docker secrets — not plain env
      POSTGRES_DB_FILE: /run/secrets/db_name
      POSTGRES_USER_FILE: /run/secrets/db_user
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_name
      - db_user
      - db_password
    volumes:
      - postgres-data:/var/lib/postgresql
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $(cat /run/secrets/db_user)"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  redis:
    image: redis:8.2-alpine
    command: redis-server --requirepass-file /run/secrets/redis_password
    secrets:
      - redis_password
    volumes:
      - redis-data:/data
    networks:
      - backend
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true    # backend services not reachable from host directly

volumes:
  postgres-data:
  redis-data:

secrets:
  database_url:
    external: true
  redis_url:
    external: true
  db_name:
    external: true
  db_user:
    external: true
  db_password:
    external: true
  redis_password:
    external: true
```

**Create secrets for local testing:**
```bash
# Values come from your shell environment (or a local .env that is never committed); no literal credentials here.
printf '%s' "$DATABASE_URL" | docker secret create database_url -
printf '%s' "$REDIS_URL" | docker secret create redis_url -
```

---

## Spring Boot — Dev Compose

Spring Boot needs slightly different configuration (JDBC on MVC or R2DBC on WebFlux, Actuator health check).

```yaml
# docker-compose.dev.yml — Spring Boot Development
services:
  postgres:
    image: postgres:18.7-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: myservice
    volumes:
      - postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

volumes:
  postgres-data:
    driver: local
```

**Spring Boot `.env` (matching above):**
```
SPRING_R2DBC_URL=r2dbc:postgresql://localhost:5432/myservice
SPRING_R2DBC_USERNAME=postgres
SPRING_R2DBC_PASSWORD=<POSTGRES_PASSWORD value>
SPRING_FLYWAY_URL=jdbc:postgresql://localhost:5432/myservice
```

---

## Development Override Pattern (hot reload)

Use `docker-compose.override.yml` for dev-specific settings without modifying the base file.

```yaml
# docker-compose.override.yml — automatically merged by docker compose up
services:
  app:
    build:
      target: development     # target dev stage (must exist in Dockerfile)
    volumes:
      - .:/app                # mount source for hot reload
      - /app/node_modules     # keep node_modules from image
      - /app/dist             # keep compiled dist from image
    environment:
      NODE_ENV: development
      DEBUG: "app:*"
    ports:
      - "9229:9229"           # Node.js debug port
    command: npm run dev      # override production CMD
```

---

## Health Check Reference

| Service | Health Check Command | Start Period |
|---------|---------------------|-------------|
| PostgreSQL | `pg_isready -U postgres` | 10s |
| Redis | `redis-cli ping` | 5s |
| NestJS / Fastify | `wget --spider http://localhost:3000/health/live` | 5s |
| Spring Boot | `wget --spider http://localhost:8080/actuator/health` | 40s |
| Python FastAPI | `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).status == 200 else 1)"` (stdlib; no httpx/curl needed in the image; port matches the Dockerfile's 8080) | 15s |

---

## Local / Deployed Parity

- Config keys: compose uses bare `${VAR}` with no `:-default` (a missing value must fail, not silently differ); the key set is identical across local, staging and production templates (check it in CI with a known-bad control).
- Each cloud resource the service uses maps to a local emulator or an explicit "N/A + reason" row. A missing local topic/subscription silently receives nothing, so an event-driven path "works" locally only if the emulator has the subscription.
- A scheduled endpoint is not shipped until the scheduler job that calls it exists in the infrastructure code (grep for the endpoint path with a control).
- Run migrations as a separate one-shot service that the app `depends_on` (`condition: service_completed_successfully`), mirroring the deployed order: migrate, then serve.
