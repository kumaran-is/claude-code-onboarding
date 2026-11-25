# NestJS Debugging — Production Monitoring

Production debugging patterns, structured logging, health checks, and request tracing for NestJS 12.x. For performance profiling and memory debugging, see `nestjs-debugging-performance.md`.

## 1. Structured Logging with Context

```typescript
// src/common/logging/logger.service.ts
import { Injectable, Logger, LoggerService } from '@nestjs/common';
import { getCorrelationId, getUserId } from '../context/request-context.service.js';

@Injectable()
export class StructuredLogger implements LoggerService {
  private readonly logger = new Logger();

  log(message: string, context?: string, metadata?: Record<string, any>) {
    this.logger.log(this.formatMessage(message, metadata), context);
  }

  error(message: string, trace?: string, context?: string, metadata?: Record<string, any>) {
    this.logger.error(this.formatMessage(message, metadata), trace, context);
  }

  warn(message: string, context?: string, metadata?: Record<string, any>) {
    this.logger.warn(this.formatMessage(message, metadata), context);
  }

  debug(message: string, context?: string, metadata?: Record<string, any>) {
    this.logger.debug(this.formatMessage(message, metadata), context);
  }

  verbose(message: string, context?: string, metadata?: Record<string, any>) {
    this.logger.verbose(this.formatMessage(message, metadata), context);
  }

  private formatMessage(message: string, metadata?: Record<string, any>): string {
    const correlationId = getCorrelationId();
    const userId = getUserId();

    const logObject = {
      message,
      correlationId,
      userId,
      timestamp: new Date().toISOString(),
      ...metadata,
    };

    return JSON.stringify(logObject);
  }
}
```

## 2. Health Check with Dependency Monitoring

```typescript
// src/health/health.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../database/prisma.service.js';
import { CircuitBreakerRegistry } from '../resilience/circuit-breaker.registry.js';

type CheckStatus = 'healthy' | 'degraded' | 'unhealthy';
interface DatabaseCheck { status: CheckStatus; latency?: number; error?: string }
interface MemoryCheck { status: CheckStatus; heapUsed: string; heapTotal: string }
interface CircuitsCheck { status: CheckStatus; openCount: number; open: string[] }

interface HealthStatus {
  status: CheckStatus;
  timestamp: string;
  uptime: number;
  checks: { database: DatabaseCheck; memory: MemoryCheck; circuits: CircuitsCheck };
}

@Injectable()
export class HealthService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly circuitRegistry: CircuitBreakerRegistry,
  ) {}

  async getHealth(): Promise<HealthStatus> {
    const checks = {
      database: await this.checkDatabase(),
      memory: this.checkMemory(),
      circuits: this.checkCircuits(),
    };

    const status = this.determineOverallStatus(checks);

    return {
      status,
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      checks,
    };
  }

  private readonly logger = new Logger(HealthService.name);

  private async checkDatabase(): Promise<DatabaseCheck> {
    const start = performance.now();
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      const latency = performance.now() - start;
      return {
        status: latency < 100 ? 'healthy' : 'degraded',
        latency: Math.round(latency),
      };
    } catch (error: unknown) {
      // Log the detail; the (often unauthenticated) health response carries no driver text
      this.logger.error({ event: 'health_db_failed' }, error instanceof Error ? error.stack : undefined);
      return { status: 'unhealthy', error: 'database unreachable' };
    }
  }

  private checkMemory(): MemoryCheck {
    const usage = process.memoryUsage();
    const heapUsedMB = usage.heapUsed / 1024 / 1024;
    const heapTotalMB = usage.heapTotal / 1024 / 1024;
    const heapPercentage = (heapUsedMB / heapTotalMB) * 100;

    return {
      status: heapPercentage < 80 ? 'healthy' : heapPercentage < 95 ? 'degraded' : 'unhealthy',
      heapUsed: `${heapUsedMB.toFixed(2)} MB`,
      heapTotal: `${heapTotalMB.toFixed(2)} MB`,
    };
  }

  private checkCircuits(): CircuitsCheck {
    const states = this.circuitRegistry.getAllStates();
    const openCount = states.filter(s => s.state === 'OPEN').length;

    return {
      status: openCount === 0 ? 'healthy' : openCount < 3 ? 'degraded' : 'unhealthy',
      openCount,
      open: states.filter(s => s.state === 'OPEN').map(s => s.name),
    };
  }

  private determineOverallStatus(checks: HealthStatus['checks']): CheckStatus {
    const statuses = [checks.database.status, checks.memory.status, checks.circuits.status];

    if (statuses.includes('unhealthy')) return 'unhealthy';
    if (statuses.includes('degraded')) return 'degraded';
    return 'healthy';
  }
}
```

## 3. Request Tracing with Distributed Context

```typescript
// src/common/interceptors/tracing.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler, Logger } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { getCorrelationId, updateContextMetadata } from '../context/request-context.service.js';

@Injectable()
export class TracingInterceptor implements NestInterceptor {
  private readonly logger = new Logger(TracingInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const { method, url } = request;
    const correlationId = getCorrelationId();
    const startTime = Date.now();

    this.logger.log(`[${correlationId}] → ${method} ${url}`, 'Tracing');

    return next.handle().pipe(
      tap(() => {
        const duration = Date.now() - startTime;
        updateContextMetadata({ requestDuration: duration });
        this.logger.log(
          `[${correlationId}] ← ${method} ${url} (${duration}ms)`,
          'Tracing'
        );
      }),
      catchError((error) => {
        const duration = Date.now() - startTime;
        this.logger.error(
          `[${correlationId}] ✗ ${method} ${url} (${duration}ms): ${error.message}`,
          error.stack,
          'Tracing'
        );
        throw error;
      })
    );
  }
}
```

## 4. Debugging Best Practices

### Development Environment

- Use `logger.debug()` liberally for detailed flow tracing
- Enable Prisma query logging to identify N+1 queries
- Use Fastify lifecycle hooks to track request processing stages
- Leverage Chrome DevTools for memory profiling and CPU profiling

### Production Environment

- Use structured JSON logging with correlation IDs
- Implement comprehensive health checks with dependency monitoring
- Monitor circuit breaker states via dedicated endpoints
- Track request duration and slow query warnings
- Use external APM tools (DataDog, New Relic, Sentry) for distributed tracing

### Common Pitfalls

- Never log sensitive data (passwords, tokens, PII)
- Avoid excessive logging in hot paths (use sampling)
- Clean up event listeners and timers in `OnModuleDestroy`
- Use connection pooling for database and external services
- Implement graceful shutdown to avoid connection leaks
