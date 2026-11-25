# NestJS 12.x Advanced Testing — Circuit Breaker & Request Context

Advanced test patterns for NestJS 12.x including circuit breaker state transitions (CLOSED, OPEN, HALF_OPEN) and AsyncLocalStorage request context propagation with Vitest.

## Circuit Breaker Testing

```typescript
// src/core/circuit-breaker/circuit-breaker.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { CircuitBreaker } from './circuit-breaker.js';
import { CircuitBreakerOpenException } from './circuit-breaker.exception.js';

describe('CircuitBreaker', () => {
  let breaker: CircuitBreaker;

  beforeEach(() => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeout: 1000,
      halfOpenMaxAttempts: 2,
    });
  });

  describe('Happy Path', () => {
    it('should execute operation successfully when circuit is closed', async () => {
      const operation = vi.fn().mockResolvedValue('success');

      const result = await breaker.execute(operation);

      expect(result).toBe('success');
      expect(operation).toHaveBeenCalledTimes(1);
      expect(breaker.getState()).toBe('CLOSED');
    });
  });

  describe('Circuit Open', () => {
    it('should open circuit after threshold failures', async () => {
      const operation = vi.fn().mockRejectedValue(new Error('Service down'));

      // Trigger failures to open circuit
      for (let i = 0; i < 3; i++) {
        await expect(breaker.execute(operation)).rejects.toThrow(
          'Service down',
        );
      }

      expect(breaker.getState()).toBe('OPEN');

      // Next call should fail fast without calling operation
      await expect(breaker.execute(operation)).rejects.toThrow(
        CircuitBreakerOpenException,
      );
      expect(operation).toHaveBeenCalledTimes(3); // Not 4
    });
  });

  describe('Half-Open Recovery', () => {
    it('should transition to half-open after reset timeout', async () => {
      const operation = vi.fn().mockRejectedValue(new Error('Service down'));

      // Open the circuit
      for (let i = 0; i < 3; i++) {
        await expect(breaker.execute(operation)).rejects.toThrow();
      }

      expect(breaker.getState()).toBe('OPEN');

      // Wait for reset timeout
      await new Promise((resolve) => setTimeout(resolve, 1100));

      expect(breaker.getState()).toBe('HALF_OPEN');
    });

    it('should close circuit after successful half-open attempts', async () => {
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new Error('Fail 1'))
        .mockRejectedValueOnce(new Error('Fail 2'))
        .mockRejectedValueOnce(new Error('Fail 3'))
        .mockResolvedValue('success');

      // Open the circuit
      for (let i = 0; i < 3; i++) {
        await expect(breaker.execute(operation)).rejects.toThrow();
      }

      expect(breaker.getState()).toBe('OPEN');

      // Wait for reset timeout
      await new Promise((resolve) => setTimeout(resolve, 1100));

      // Successful call in half-open state
      const result = await breaker.execute(operation);

      expect(result).toBe('success');
      expect(breaker.getState()).toBe('CLOSED');
    });

    it('should reopen circuit if half-open attempt fails', async () => {
      const operation = vi.fn().mockRejectedValue(new Error('Still failing'));

      // Open the circuit
      for (let i = 0; i < 3; i++) {
        await expect(breaker.execute(operation)).rejects.toThrow();
      }

      // Wait for reset timeout
      await new Promise((resolve) => setTimeout(resolve, 1100));

      expect(breaker.getState()).toBe('HALF_OPEN');

      // Fail in half-open state
      await expect(breaker.execute(operation)).rejects.toThrow(
        'Still failing',
      );

      expect(breaker.getState()).toBe('OPEN');
    });
  });

  describe('Fallback Verification', () => {
    it('should execute fallback when circuit is open', async () => {
      const operation = vi.fn().mockRejectedValue(new Error('Service down'));
      const fallback = vi.fn().mockResolvedValue('fallback-value');

      // Open the circuit
      for (let i = 0; i < 3; i++) {
        await expect(breaker.execute(operation)).rejects.toThrow();
      }

      const result = await breaker.executeWithFallback(operation, fallback);

      expect(result).toBe('fallback-value');
      expect(fallback).toHaveBeenCalled();
    });
  });

  describe('Metrics', () => {
    it('should track success and failure counts', async () => {
      const successOp = vi.fn().mockResolvedValue('success');
      const failOp = vi.fn().mockRejectedValue(new Error('fail'));

      await breaker.execute(successOp);
      await breaker.execute(successOp);

      try {
        await breaker.execute(failOp);
      } catch (error) {
        // Expected
      }

      const metrics = breaker.getMetrics();

      expect(metrics.successCount).toBe(2);
      expect(metrics.failureCount).toBe(1);
      expect(metrics.state).toBe('CLOSED');
    });
  });
});
```

## Testing Request Context (AsyncLocalStorage)

```typescript
// src/core/context/request-context.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { describe, it, expect, beforeEach } from 'vitest';
import { RequestContextService } from './request-context.service.js';
import { RequestContextMiddleware } from './request-context.middleware.js';

describe('RequestContextService', () => {
  let service: RequestContextService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [RequestContextService],
    }).compile();

    service = module.get<RequestContextService>(RequestContextService);
  });

  describe('Correlation ID Propagation', () => {
    it('should set and get correlation ID within context', async () => {
      const correlationId = 'test-correlation-id';

      await service.run({ correlationId }, async () => {
        const retrieved = service.getCorrelationId();
        expect(retrieved).toBe(correlationId);
      });
    });

    it('should return undefined when no context is set', () => {
      const correlationId = service.getCorrelationId();
      expect(correlationId).toBeUndefined();
    });

    it('should maintain separate contexts for concurrent operations', async () => {
      const promises = [
        service.run({ correlationId: 'request-1' }, async () => {
          await new Promise((resolve) => setTimeout(resolve, 10));
          return service.getCorrelationId();
        }),
        service.run({ correlationId: 'request-2' }, async () => {
          await new Promise((resolve) => setTimeout(resolve, 5));
          return service.getCorrelationId();
        }),
      ];

      const [id1, id2] = await Promise.all(promises);

      expect(id1).toBe('request-1');
      expect(id2).toBe('request-2');
    });
  });

  describe('User Context', () => {
    it('should store and retrieve user information', async () => {
      const context = {
        correlationId: 'test-id',
        userId: 'user-123',
        userRole: 'ADMIN',
      };

      await service.run(context, async () => {
        expect(service.getUserId()).toBe('user-123');
        expect(service.getUserRole()).toBe('ADMIN');
      });
    });
  });
});

describe('RequestContextMiddleware', () => {
  let middleware: RequestContextMiddleware;
  let contextService: RequestContextService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [RequestContextMiddleware, RequestContextService],
    }).compile();

    middleware = module.get<RequestContextMiddleware>(
      RequestContextMiddleware,
    );
    contextService = module.get<RequestContextService>(RequestContextService);
  });

  it('should generate correlation ID if not present', async () => {
    const req = {
      headers: {},
    };
    const res = {};
    const next = vi.fn();

    await middleware.use(req, res, next);

    expect(req.headers['x-correlation-id']).toBeDefined();
    expect(next).toHaveBeenCalled();
  });

  it('should use existing correlation ID from header', async () => {
    const existingId = 'existing-correlation-id';
    const req = {
      headers: {
        'x-correlation-id': existingId,
      },
    };
    const res = {};
    const next = vi.fn();

    await middleware.use(req, res, next);

    expect(req.headers['x-correlation-id']).toBe(existingId);
  });
});
```
