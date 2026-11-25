# NestJS Resilience — Request Context & Correlation

Request context propagation using AsyncLocalStorage for NestJS 12.x. For circuit breaker and database fallback patterns, see `nestjs-resilience-circuit-breaker.md`.

## 1. Request Context (AsyncLocalStorage)

Propagates request context through the entire call chain using AsyncLocalStorage, enabling access to correlation ID, user info, and other request metadata from any point in the application without passing through parameters.

### Implementation

```typescript
/**
 * Request Context Service
 *
 * Propagates request context through the entire call chain using AsyncLocalStorage.
 * Enables access to correlation ID, user info, and other request metadata
 * from any point in the application without passing through parameters.
 */

import { AsyncLocalStorage } from 'async_hooks';

export interface RequestContext {
  /** Unique identifier for request tracing */
  correlationId: string;

  /** Request timestamp */
  startTime: number;

  /** Authenticated user ID (if any) */
  userId?: string;

  /** Tenant ID for multi-tenant applications */
  tenantId?: string;

  /** Session ID */
  sessionId?: string;

  /** Client IP address */
  ipAddress?: string;

  /** User agent string */
  userAgent?: string;

  /** Request path */
  path?: string;

  /** HTTP method */
  method?: string;

  /** Custom metadata */
  metadata: Record<string, unknown>;
}

/**
 * AsyncLocalStorage instance for request context
 */
export const requestContext = new AsyncLocalStorage<RequestContext>();

/**
 * Get current request context (if any)
 */
export function getRequestContext(): RequestContext | undefined {
  return requestContext.getStore();
}

/**
 * Get correlation ID from current context
 */
export function getCorrelationId(): string | undefined {
  return requestContext.getStore()?.correlationId;
}

/**
 * Get user ID from current context
 */
export function getUserId(): string | undefined {
  return requestContext.getStore()?.userId;
}

/**
 * Get tenant ID from current context
 */
export function getTenantId(): string | undefined {
  return requestContext.getStore()?.tenantId;
}

/**
 * Run a function within a request context
 */
export function runWithContext<T>(context: RequestContext, fn: () => T): T {
  return requestContext.run(context, fn);
}

/**
 * Run an async function within a request context
 */
export async function runWithContextAsync<T>(
  context: RequestContext,
  fn: () => Promise<T>
): Promise<T> {
  return requestContext.run(context, fn);
}

/**
 * Update current context metadata
 */
export function updateContextMetadata(updates: Record<string, unknown>): void {
  const context = requestContext.getStore();
  if (context) {
    context.metadata = { ...context.metadata, ...updates };
  }
}
```

### Middleware

```typescript
/**
 * Request Context Middleware
 *
 * Initializes request context for every incoming request
 */

import { Injectable, NestMiddleware, Logger } from '@nestjs/common';
import { randomUUID } from 'crypto';
import { requestContext, RequestContext } from './request-context.service.js';

import type { FastifyRequest, FastifyReply } from 'fastify';

@Injectable()
export class RequestContextMiddleware implements NestMiddleware {
  private readonly logger = new Logger(RequestContextMiddleware.name);

  use(req: FastifyRequest['raw'], res: FastifyReply['raw'], next: () => void): void {
    const correlationId =
      (req.headers['x-correlation-id'] as string) ??
      (req.headers['x-request-id'] as string) ??
      randomUUID();

    const context: RequestContext = {
      correlationId,
      startTime: Date.now(),
      ipAddress: req.headers['x-forwarded-for'] as string ?? req.socket.remoteAddress,
      userAgent: req.headers['user-agent'],
      path: req.url,
      method: req.method,
      metadata: {},
    };

    // Set correlation ID in response headers
    res.setHeader('x-correlation-id', correlationId);

    // Run the rest of the request within this context
    requestContext.run(context, () => {
      next();
    });
  }
}
```

### Module Registration

```typescript
import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { RequestContextMiddleware } from './common/context/request-context.middleware.js';

@Module({
  // ...
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer
      .apply(RequestContextMiddleware)
      .forRoutes('*');
  }
}
```

### Usage in Services

```typescript
import { getRequestContext, getCorrelationId, getUserId } from './common/context/request-context.service.js';

export class OrderService {
  async createOrder(data: CreateOrderDto): Promise<Order> {
    const context = getRequestContext();

    // Access correlation ID for logging
    this.logger.log(`Creating order`, { correlationId: getCorrelationId() });

    // Access user ID for auditing
    const userId = getUserId();

    // Custom metadata
    context?.metadata.orderType = data.type;

    return this.orderRepository.create({
      ...data,
      userId,
      createdBy: userId,
    });
  }
}
```

## 2. Best Practices

### Request Context
- Always apply `RequestContextMiddleware` globally to ensure context availability
- Use `getCorrelationId()` in all log statements for distributed tracing
- Store tenant/user info in context for multi-tenant applications
- Avoid storing large objects in metadata to prevent memory overhead
