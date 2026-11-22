# Health Endpoint Patterns

Every deployed service MUST expose health endpoints (liveness; readiness when it has dependencies; Python: `/health/live` + `/health/ready` below). This is required by:
- Cloud Run health check configuration
- Docker HEALTHCHECK instruction
- Load balancer health probes
- CI/CD deploy verification step

---

## NestJS 11.x — Health Controller

```typescript
// src/health/health.controller.ts
import { Controller, Get } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

@Controller('health')
export class HealthController {
  constructor(
    @InjectDataSource() private readonly dataSource: DataSource,
  ) {}

  @Get()
  async check() {
    const dbConnected = this.dataSource.isInitialized;

    if (!dbConnected) {
      throw new Error('Database not connected');
    }

    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      database: dbConnected ? 'ok' : 'error',
      version: process.env['APP_VERSION'] ?? 'unknown',
    };
  }
}
```

For `@nestjs/terminus` (recommended for production):
```typescript
// src/health/health.controller.ts
import { Controller, Get } from '@nestjs/common';
import {
  HealthCheck,
  HealthCheckService,
  TypeOrmHealthIndicator,
} from '@nestjs/terminus';

@Controller('health')
export class HealthController {
  constructor(
    private health: HealthCheckService,
    private db: TypeOrmHealthIndicator,
  ) {}

  @Get()
  @HealthCheck()
  check() {
    return this.health.check([
      () => this.db.pingCheck('database'),
    ]);
  }
}
```

---

## Spring Boot 3.5.x WebFlux — Actuator Health

Spring Boot exposes `/actuator/health` automatically via `spring-boot-starter-actuator`.

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized   # never expose full details publicly
      probes:
        enabled: true                 # enables /actuator/health/liveness and /actuator/health/readiness
  health:
    livenessstate:
      enabled: true
    readinessstate:
      enabled: true
```

Cloud Run health check target: `GET /actuator/health` → 200 with `{"status":"UP"}`

Custom health indicator:
```java
// src/main/java/com/example/health/DatabaseHealthIndicator.java
@Component
public class DatabaseHealthIndicator implements ReactiveHealthIndicator {

    private final R2dbcEntityTemplate template;

    @Override
    public Mono<Health> health() {
        return template.getDatabaseClient()
            .sql("SELECT 1")
            .fetch()
            .first()
            .map(r -> Health.up().withDetail("database", "ok").build())
            .onErrorReturn(Health.down().withDetail("database", "unreachable").build());
    }
}
```

---

## Python FastAPI 3.14 — Liveness and Readiness

Split by purpose: liveness checks the process only (no dependency calls), readiness checks dependencies concurrently with a per-check timeout. Executed against real PostgreSQL: ready -> 200 with `{"database": "ok"}`; unreachable database -> 503 while `/health/live` stays 200, and the response body contains no host or exception text.

```python
# src/api/health.py
import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Literal

import structlog
from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])
log = structlog.get_logger()
_started = time.monotonic()
CHECK_TIMEOUT_S = 2.0


async def check_database(request: Request) -> None:
    async with request.app.state.sessionmaker() as session:
        await session.execute(text("SELECT 1"))


CHECKS: dict[str, Callable[[Request], Awaitable[None]]] = {"database": check_database}


@router.get("/health/live")
async def live() -> dict[str, str | int]:
    return {"status": "ok", "uptime_seconds": int(time.monotonic() - _started)}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    async def run(name: str, check: Callable[[Request], Awaitable[None]]) -> tuple[str, Literal["ok", "error"]]:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_S):
                await check(request)
            return name, "ok"
        except Exception as exc:                      # log the type, report "error"; never leak the message
            log.warning("health_check_failed", check=name, error_type=type(exc).__name__)
            return name, "error"

    results = dict(await asyncio.gather(*(run(n, c) for n, c in CHECKS.items())))
    healthy = all(v == "ok" for v in results.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "unavailable", "checks": results,
            "version": os.getenv("APP_VERSION", "unknown")}
```

The old single `/health` that swallowed the exception and returned 200 with `"degraded"` hid outages from both the orchestrator and the logs; do not reintroduce it. Logging, tracing and probe wiring: `python-observability.md`.

---

## Cloud Run Health Check Configuration

Flags verified against `gcloud run deploy --help` (SDK 560). `--startup-probe` and `--liveness-probe` take `KEY=VALUE,...` (keys: `initialDelaySeconds, timeoutSeconds, periodSeconds, failureThreshold, httpGet.port, httpGet.path, grpc.port, grpc.service, tcpSocket.port`). The flags `--health-check-type`, `--liveness-probe-path`, `--readiness-probe-path`, `--startup-probe-path`, `--startup-probe-initial-delay`, `--startup-probe-timeout` and `--startup-probe-failure-threshold` do NOT exist, and the help has no `--readiness-probe` either; a readiness probe is documented in the service YAML for some launch stages, so verify the current stage first.

```yaml
# In GitHub Actions deploy step:
- name: Deploy to Cloud Run
  run: |
    gcloud run deploy "$SERVICE_NAME" --image "$IMAGE_URL" \
      --startup-probe 'httpGet.path=/health/ready,httpGet.port=8080,periodSeconds=5,failureThreshold=10' \
      --liveness-probe 'httpGet.path=/health/live,httpGet.port=8080,periodSeconds=30,failureThreshold=3'
```

---

## Health Check Anti-Patterns

- **No dependency check anywhere** — a revision that cannot reach its database looks healthy. Put the check in the startup/readiness endpoint, NOT in liveness: a liveness probe that calls dependencies can restart healthy instances during a dependency outage (reasoned risk, not reproduced here)
- **Exposing sensitive info** — never include stack traces, exception messages, connection strings, or internal IPs in health responses; log the exception type instead
- **Slow health checks** — health endpoint must respond in < 3 seconds; never run expensive queries
- **Missing health endpoint entirely** — Cloud Run defaults to TCP port check only; HTTP health check is more reliable

---

## Verify Step

After adding health endpoint:
```bash
# Local verification:
curl http://localhost:3000/health            # NestJS
curl http://localhost:8080/actuator/health   # Spring Boot
curl http://localhost:8000/health            # FastAPI

# Expected: HTTP 200 with JSON body containing "status": "ok"
```
