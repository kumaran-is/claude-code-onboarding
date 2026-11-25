# NestJS Debugging — Performance & Memory

Memory leak detection, performance profiling, and circuit breaker state debugging for NestJS 12.x. For production debugging and monitoring, see `nestjs-debugging-production.md`.

## 1. Memory Leak Detection

### Memory Usage Endpoint

```typescript
// src/health/health.controller.ts
import { Controller, Get } from '@nestjs/common';
import { SkipAuth } from '../common/decorators/skip-auth.decorator.js';

@Controller('api/v1/health')
export class HealthController {
  @Get('memory')
  @SkipAuth()
  getMemoryUsage() {
    const usage = process.memoryUsage();
    return {
      rss: `${(usage.rss / 1024 / 1024).toFixed(2)} MB`, // Resident Set Size
      heapTotal: `${(usage.heapTotal / 1024 / 1024).toFixed(2)} MB`,
      heapUsed: `${(usage.heapUsed / 1024 / 1024).toFixed(2)} MB`,
      external: `${(usage.external / 1024 / 1024).toFixed(2)} MB`,
      arrayBuffers: `${(usage.arrayBuffers / 1024 / 1024).toFixed(2)} MB`,
      uptime: `${(process.uptime() / 60).toFixed(2)} minutes`,
    };
  }
}
```

### Common NestJS Memory Leaks

```typescript
// BAD: Unclosed Prisma connections
@Injectable()
export class BadService {
  async getData() {
    const prisma = new PrismaClient(); // Never disconnected - LEAK!
    return prisma.user.findMany();
  }
}

// GOOD: Use singleton PrismaService
@Injectable()
export class GoodService {
  constructor(private readonly prisma: PrismaService) {}

  async getData() {
    return this.prisma.user.findMany();
  }
}

// BAD: EventEmitter listener leak
@Injectable()
export class BadEventService implements OnModuleInit {
  constructor(private readonly eventEmitter: EventEmitter2) {}

  onModuleInit() {
    setInterval(() => {
      this.eventEmitter.on('event', () => {}); // Adds listener every second - LEAK!
    }, 1000);
  }
}

// GOOD: Add listener once
@Injectable()
export class GoodEventService implements OnModuleInit, OnModuleDestroy {
  private handler = () => {};

  constructor(private readonly eventEmitter: EventEmitter2) {}

  onModuleInit() {
    this.eventEmitter.on('event', this.handler);
  }

  onModuleDestroy() {
    this.eventEmitter.off('event', this.handler);
  }
}

// BAD: Circular DI reference leak
@Injectable()
export class ServiceA {
  constructor(private readonly serviceB: ServiceB) {}
}

@Injectable()
export class ServiceB {
  constructor(private readonly serviceA: ServiceA) {} // Circular!
}

// GOOD: Use forwardRef
@Injectable()
export class ServiceA {
  constructor(@Inject(forwardRef(() => ServiceB)) private readonly serviceB: ServiceB) {}
}
```

### Memory Debugging Commands

```bash
# Run with Chrome DevTools inspector
node --inspect dist/main.js
# Then open chrome://inspect in Chrome

# Limit heap size to detect leaks faster
node --max-old-space-size=512 dist/main.js

# Generate heap snapshot programmatically
v8.writeHeapSnapshot('./heap-snapshot.heapsnapshot');

# Analyze heap snapshots: load two snapshots in Chrome DevTools Memory tab and compare
```

## 2. Performance Profiling

### Custom Performance Interceptor

```typescript
// src/common/interceptors/performance.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler, Logger } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { performance, PerformanceObserver } from 'perf_hooks';

@Injectable()
export class PerformanceInterceptor implements NestInterceptor {
  private readonly logger = new Logger(PerformanceInterceptor.name);
  private readonly SLOW_REQUEST_THRESHOLD = 500; // ms

  constructor() {
    const obs = new PerformanceObserver((items) => {
      items.getEntries().forEach((entry) => {
        if (entry.duration > this.SLOW_REQUEST_THRESHOLD) {
          this.logger.warn(
            `Slow request: ${entry.name} took ${entry.duration.toFixed(2)}ms`,
            'Performance'
          );
        }
      });
    });
    obs.observe({ entryTypes: ['measure'] });
  }

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const { method, url } = request;
    const markStart = `${method}-${url}-start`;
    const markEnd = `${method}-${url}-end`;
    const measureName = `${method} ${url}`;

    performance.mark(markStart);

    return next.handle().pipe(
      tap({
        next: () => {
          performance.mark(markEnd);
          performance.measure(measureName, markStart, markEnd);
          const measure = performance.getEntriesByName(measureName)[0];
          this.logger.log(`${measureName} completed in ${measure.duration.toFixed(2)}ms`, 'Performance');
          performance.clearMarks(markStart);
          performance.clearMarks(markEnd);
          performance.clearMeasures(measureName);
        },
        error: () => {
          performance.clearMarks(markStart);
        },
      }),
    );
  }
}
```

### Prisma Query Timing (client extension)

`$use` middleware no longer exists on the Prisma 7 client. Time queries with a query extension (type-checked against Prisma 7.10.1):

```typescript
import { Logger } from '@nestjs/common';
import { type PrismaClient } from '../generated/prisma/client.js';

const logger = new Logger('Prisma');

export function withQueryTiming(client: PrismaClient, slowMs = 100) {
  return client.$extends({
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const started = performance.now();
          try {
            return await query(args);
          } finally {
            const ms = performance.now() - started;
            if (ms > slowMs) logger.warn({ event: 'slow_query', model, operation, ms: Math.round(ms) });
          }
        },
      },
    },
  });
}
```

Log the model and operation, never `args` (they carry user data).

### CPU Profiling Commands

```bash
# Generate CPU profile
node --prof dist/main.js
# Stop after some requests, then process the log
node --prof-process isolate-*.log > profile.txt

# V8 profiling with Chrome DevTools
node --inspect-brk dist/main.js
# Open chrome://inspect, click "inspect", go to Profiler tab

# Trace event profiling
node --trace-event-categories v8,node,node.async_hooks dist/main.js
# Generates node_trace.*.log, open in chrome://tracing
```

## 3. Circuit Breaker State Debugging

### Circuit Breaker Inspection Endpoint

```typescript
// src/resilience/resilience.controller.ts
import { Controller, Get, Post, Param } from '@nestjs/common';
import { CircuitBreakerRegistry } from './circuit-breaker.registry.js';

@Controller('api/v1/resilience')
export class ResilienceController {
  constructor(private readonly registry: CircuitBreakerRegistry) {}

  @Get('circuits')
  getAllCircuits() {
    return this.registry.getAllStates();
  }

  @Get('circuits/:name')
  getCircuitByName(@Param('name') name: string) {
    const state = this.registry.getState(name);
    if (!state) {
      return { error: `Circuit breaker '${name}' not found` };
    }
    return state;
  }

  @Post('circuits/:name/reset')
  resetCircuit(@Param('name') name: string) {
    this.registry.reset(name);
    return { message: `Circuit '${name}' reset to CLOSED` };
  }
}
```

### Circuit Breaker with State Logging

```typescript
// src/resilience/circuit-breaker.registry.ts
import { Injectable, Logger } from '@nestjs/common';

export interface CircuitState {
  name: string;
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failureCount: number;
  successCount: number;
  totalCalls: number;
  lastFailureTime?: number;
  openedAt?: number;
}

@Injectable()
export class CircuitBreakerRegistry {
  private readonly logger = new Logger(CircuitBreakerRegistry.name);
  private readonly circuits = new Map<string, CircuitState>();

  register(name: string): void {
    if (!this.circuits.has(name)) {
      this.circuits.set(name, {
        name,
        state: 'CLOSED',
        failureCount: 0,
        successCount: 0,
        totalCalls: 0,
      });
      this.logger.log(`Circuit breaker '${name}' registered`, 'Registry');
    }
  }

  recordSuccess(name: string): void {
    const circuit = this.circuits.get(name);
    if (circuit) {
      circuit.successCount++;
      circuit.totalCalls++;
      if (circuit.state === 'HALF_OPEN') {
        this.logger.log(`Circuit '${name}' transitioning HALF_OPEN → CLOSED`, 'StateTransition');
        circuit.state = 'CLOSED';
        circuit.failureCount = 0;
      }
    }
  }

  recordFailure(name: string, threshold: number): void {
    const circuit = this.circuits.get(name);
    if (circuit) {
      circuit.failureCount++;
      circuit.totalCalls++;
      circuit.lastFailureTime = Date.now();

      if (circuit.state === 'CLOSED' && circuit.failureCount >= threshold) {
        this.logger.warn(
          `Circuit '${name}' OPENING: failure count ${circuit.failureCount} >= threshold ${threshold}`,
          'StateTransition'
        );
        circuit.state = 'OPEN';
        circuit.openedAt = Date.now();
      } else if (circuit.state === 'HALF_OPEN') {
        this.logger.warn(`Circuit '${name}' transitioning HALF_OPEN → OPEN`, 'StateTransition');
        circuit.state = 'OPEN';
        circuit.openedAt = Date.now();
      }
    }
  }

  tryHalfOpen(name: string, timeout: number): boolean {
    const circuit = this.circuits.get(name);
    if (circuit && circuit.state === 'OPEN' && circuit.openedAt) {
      const elapsed = Date.now() - circuit.openedAt;
      if (elapsed >= timeout) {
        this.logger.log(`Circuit '${name}' transitioning OPEN → HALF_OPEN`, 'StateTransition');
        circuit.state = 'HALF_OPEN';
        return true;
      }
    }
    return false;
  }

  getAllStates(): CircuitState[] {
    return Array.from(this.circuits.values());
  }

  getState(name: string): CircuitState | undefined {
    return this.circuits.get(name);
  }

  reset(name: string): void {
    const circuit = this.circuits.get(name);
    if (circuit) {
      this.logger.log(`Circuit '${name}' manually reset to CLOSED`, 'ManualReset');
      circuit.state = 'CLOSED';
      circuit.failureCount = 0;
      circuit.successCount = 0;
      delete circuit.openedAt;
    }
  }
}
```
