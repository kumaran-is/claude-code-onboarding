# Health Endpoint Patterns

Every deployed service MUST expose health endpoints (liveness; readiness when it has dependencies; NestJS, plain Node and Python use `/health/live` + `/health/ready` below). This is required by:
- Cloud Run health check configuration
- Docker HEALTHCHECK instruction
- Load balancer health probes
- CI/CD deploy verification step

---

## NestJS 11.x — Liveness and Readiness (`@nestjs/terminus` 12.2.0)

Executed 2026-11-23 with `@nestjs/common`/`core`/`platform-fastify` 11.2.11, `@nestjs/terminus` 12.2.0, TypeScript 5.9.3 strict. Plain Node (no Nest) and MCP servers: `../../mcp-builder/reference/production-runtime-shutdown-health.md`.

```typescript
// src/health/health.controller.ts
import { Controller, Get, Inject, Injectable, Logger } from "@nestjs/common";
import { HealthCheck, HealthCheckService, HealthIndicatorService } from "@nestjs/terminus";

/** The slice of PrismaClient the readiness check needs (a real PrismaClient satisfies it). */
export interface SqlPingClient {
  $queryRawUnsafe: (query: string) => Promise<unknown>;
}
export const DB_CLIENT = Symbol("DB_CLIENT");

/** SQL ping that reports up/down WITHOUT the driver's error message (hosts, ports) in the response. */
@Injectable()
export class DatabaseHealthIndicator {
  private readonly logger = new Logger(DatabaseHealthIndicator.name);
  constructor(
    private readonly indicator: HealthIndicatorService,
    @Inject(DB_CLIENT) private readonly db: SqlPingClient,
  ) {}

  async ping(key: string, timeoutMs: number) {
    const session = this.indicator.check(key);
    try {
      await Promise.race([
        this.db.$queryRawUnsafe("SELECT 1"),
        new Promise((_, reject) => setTimeout(() => { reject(new Error("readiness timeout")); }, timeoutMs).unref()),
      ]);
      return session.up();
    } catch (err: unknown) {
      this.logger.warn(`readiness check ${key} failed: ${err instanceof Error ? err.name : "unknown"}`);
      return session.down();
    }
  }
}

@Controller("health")
export class HealthController {
  constructor(
    private readonly health: HealthCheckService,
    private readonly database: DatabaseHealthIndicator,
  ) {}

  /** Liveness: no dependency calls and no HealthCheckService (that reports shutting_down -> 503 after SIGTERM). */
  @Get("live")
  live(): { status: "ok" } {
    return { status: "ok" };
  }

  /** Readiness: bounded dependency checks; 503 when one is down or once shutdown has begun. */
  @Get("ready")
  @HealthCheck()
  ready() {
    return this.health.check([() => this.database.ping("database", 1_000)]);
  }
}
```

```typescript
// src/health/health.module.ts — PrismaService is the composition-style service from the nestjs-api skill (`readonly client`)
import { Module } from "@nestjs/common";
import { TerminusModule } from "@nestjs/terminus";
import { PrismaService } from "./database/prisma.service.js";
import { DB_CLIENT, DatabaseHealthIndicator, HealthController } from "./health.controller.js";

@Module({
  // After SIGTERM every @HealthCheck() endpoint answers 503 "shutting_down" for this long, then Nest closes.
  imports: [TerminusModule.forRoot({ gracefulShutdownTimeoutMs: 5_000 })],
  controllers: [HealthController],
  providers: [
    DatabaseHealthIndicator,
    { provide: DB_CLIENT, inject: [PrismaService], useFactory: (prisma: PrismaService) => prisma.client },
  ],
})
export class HealthModule {}
```

In `main.ts`, call `app.enableShutdownHooks()`. Without it, Terminus never learns about SIGTERM and readiness keeps answering 200 while the app shuts down.

Executed results:

| State | `GET /health/ready` | `GET /health/live` |
|-------|---------------------|--------------------|
| healthy | 200 `{"status":"ok", … "database":{"status":"up"}}` | 200 |
| database down (driver error contained an IP) | 503 `{"status":"error", … "database":{"status":"down"}}`, no message or IP in the body | 200 |
| after SIGTERM (within `gracefulShutdownTimeoutMs`) | 503 `{"status":"shutting_down", …}` | 200 |
| process exit | exit code 143 (Nest re-raises the signal) | |

- **Liveness does not use `HealthCheckService`.** Any `@HealthCheck()` endpoint returns 503 `shutting_down` once shutdown starts, which is right for readiness and wrong for liveness.
- **Why a custom indicator instead of `PrismaHealthIndicator`:** in 12.2.0, `PrismaHealthIndicator.pingCheck` tries the MongoDB `$runCommandRaw` first and falls back to SQL only on a specific error. Its down response includes the driver's error message; with a client that lacked `$runCommandRaw` the body carried `prismaClient.$runCommandRaw is not a function` (executed). The 20-line indicator above pings with SQL, bounds the wait, and returns only up/down. If you do use the built-in one, use `.withTimeout(ms)`; the `timeout` option is deprecated.
- TypeORM's `TypeOrmHealthIndicator` (shown in the previous version of this page) does not apply: the workspace stack is Prisma.

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
# src/my_service/api/health.py
import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

import structlog
from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)
_started = time.monotonic()
CHECK_TIMEOUT_S = 2.0


async def check_database(request: Request) -> None:
    async with request.app.state.session_factory() as session:   # set in lifespan
        await session.execute(text("SELECT 1"))


CHECKS: dict[str, Callable[[Request], Awaitable[None]]] = {"database": check_database}


@router.get("/health/live")
async def live() -> dict[str, str | int]:
    return {"status": "ok", "uptime_seconds": int(time.monotonic() - _started)}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    async def run(
        name: str, check: Callable[[Request], Awaitable[None]]
    ) -> tuple[str, Literal["ok", "error"]]:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_S):
                await check(request)
            return name, "ok"
        except Exception as exc:  # noqa: BLE001 - probe boundary: log the type, report "error"
            logger.warning("health_check_failed", check=name, error_type=type(exc).__qualname__)
            return name, "error"

    results = dict(await asyncio.gather(*(run(n, c) for n, c in CHECKS.items())))
    healthy = all(v == "ok" for v in results.values())
    response.status_code = 200 if healthy else 503
    version = request.app.state.settings.app_version   # from Settings, never os.getenv
    return {"status": "ok" if healthy else "unavailable", "checks": results, "version": version}
```

The old single `/health` that swallowed the exception and returned 200 with `"degraded"` hid outages from both the orchestrator and the logs; do not reintroduce it. Logging, tracing and probe wiring: `python-observability.md`.

**Shutdown.** uvicorn stops accepting connections on SIGTERM, lets in-flight requests finish for up to `--timeout-graceful-shutdown` seconds, then runs the lifespan exit, which disposes the engine (executed on uvicorn 0.54: the shutdown log line appears and the process re-raises SIGTERM: status 143 on a host or with `docker run --init`, 0 as container PID 1; 137 or no log line means it was killed). Close resources in the lifespan `finally`, not `atexit` (it does not run on the 143 path). Keep that timeout below the platform's grace period (Cloud Run sends SIGKILL 10 s after SIGTERM). Probes never touch `app.state.session_factory` outside a request, so they need no shutdown handling of their own.

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

After adding health endpoints, check each probe and the shutdown flip:
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/health/live    # NestJS / Node: 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/health/ready   # 200 healthy, 503 dependency down
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health/liveness   # Spring Boot (probes enabled)
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health/ready   # FastAPI

# Shutdown: send SIGTERM to the process (by PID, not a pattern match), then within the drain window:
kill -TERM "$PID"; curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/health/ready   # expect 503
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/health/live                         # expect 200
```

Negative control: stop the database (or point the URL at a closed port) and confirm readiness returns 503 while liveness stays 200, and that the 503 body contains no host, port or driver message.
