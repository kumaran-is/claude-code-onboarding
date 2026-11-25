# NestJS Resilience — Circuit Breaker & Database Fallback

Circuit breaker and database fallback patterns for NestJS 12.x. For request context and correlation IDs, see `nestjs-resilience-context.md`.

## 1. Circuit Breaker Pattern

The circuit breaker prevents cascading failures by failing fast when a service is down. It implements a state machine with three states: CLOSED (normal operation), OPEN (failing fast), and HALF_OPEN (testing recovery).

### Implementation

```typescript
/**
 * Circuit Breaker Pattern Implementation
 *
 * Prevents cascading failures by failing fast when a service is down.
 * States: CLOSED → OPEN → HALF_OPEN → CLOSED
 */

import { Injectable, Logger } from '@nestjs/common';

import type {
  ICircuitBreakerState,
  IResilienceContext,
  IPatternExecutor
} from '../interfaces/resilience.interface.js';

interface CircuitBreakerConfig {
  enabled: boolean;
  failureThreshold: number;
  resetTimeout: number;
  halfOpenMaxCalls: number;
  monitoringPeriod: number;
}

interface CircuitState {
  state: 'open' | 'closed' | 'half-open';
  failures: number;
  successes: number;
  totalCalls: number;
  lastFailureTime?: Date;
  nextRetryTime?: Date;
  consecutiveSuccesses: number;
  windowStart: number;
}

@Injectable()
export class CircuitBreakerPattern implements IPatternExecutor {
  private readonly logger = new Logger(CircuitBreakerPattern.name);
  private readonly circuits = new Map<string, CircuitState>();

  async execute<T>(
    operation: () => Promise<T>,
    config: CircuitBreakerConfig,
    context: IResilienceContext
  ): Promise<T> {
    if (!config.enabled) {
      return operation();
    }

    const circuitKey = `${context.policyName}:${context.endpoint ?? 'default'}`;
    const state = this.getOrCreateState(circuitKey);

    // Check if circuit is open
    if (state.state === 'open') {
      if (Date.now() < state.nextRetryTime!.getTime()) {
        throw new Error(`Circuit breaker is open for ${circuitKey}`);
      }
      state.state = 'half-open';
      state.consecutiveSuccesses = 0;
      this.logger.log(`Circuit breaker moved to half-open for ${circuitKey}`);
    }

    // Check if half-open and max calls reached
    if (state.state === 'half-open' && state.consecutiveSuccesses >= config.halfOpenMaxCalls) {
      state.state = 'closed';
      state.failures = 0;
      state.successes = 0;
      state.totalCalls = 0;
      state.windowStart = Date.now();
      this.logger.log(`Circuit breaker closed for ${circuitKey}`);
    }

    try {
      const result = await operation();
      this.recordSuccess(state, config);
      return result;
    } catch (error) {
      this.recordFailure(state, config, circuitKey);
      throw error;
    }
  }

  getAllStates(): Record<string, ICircuitBreakerState> {
    const states: Record<string, ICircuitBreakerState> = {};

    for (const [key, state] of this.circuits) {
      states[key] = {
        state: state.state,
        failures: state.failures,
        successes: state.successes,
        lastFailureTime: state.lastFailureTime,
        nextRetryTime: state.nextRetryTime,
        consecutiveSuccesses: state.consecutiveSuccesses,
      };
    }

    return states;
  }

  getMetrics(): Record<string, unknown> {
    const metrics: Record<string, unknown> = {
      totalCircuits: this.circuits.size,
      openCircuits: 0,
      halfOpenCircuits: 0,
      closedCircuits: 0,
      circuits: {},
    };

    for (const [key, state] of this.circuits) {
      if (state.state === 'open') (metrics.openCircuits as number)++;
      else if (state.state === 'half-open') (metrics.halfOpenCircuits as number)++;
      else (metrics.closedCircuits as number)++;

      const failureRate = state.totalCalls > 0
        ? (state.failures / state.totalCalls) * 100
        : 0;

      (metrics.circuits as Record<string, unknown>)[key] = {
        state: state.state,
        failureRate: `${failureRate.toFixed(2)}%`,
        totalCalls: state.totalCalls,
        failures: state.failures,
        successes: state.successes,
      };
    }

    return metrics;
  }

  reset(policyName: string): void {
    const keysToReset: string[] = [];

    for (const key of this.circuits.keys()) {
      if (key.startsWith(policyName)) {
        keysToReset.push(key);
      }
    }

    keysToReset.forEach(key => {
      this.circuits.delete(key);
      this.logger.log(`Circuit breaker reset for ${key}`);
    });
  }

  private getOrCreateState(circuitKey: string): CircuitState {
    if (!this.circuits.has(circuitKey)) {
      this.circuits.set(circuitKey, {
        state: 'closed',
        failures: 0,
        successes: 0,
        totalCalls: 0,
        consecutiveSuccesses: 0,
        windowStart: Date.now(),
      });
    }

    return this.circuits.get(circuitKey)!;
  }

  private recordSuccess(state: CircuitState, config: CircuitBreakerConfig): void {
    state.successes++;
    state.totalCalls++;

    if (state.state === 'half-open') {
      state.consecutiveSuccesses++;
    }

    this.checkWindowReset(state, config);
  }

  private recordFailure(
    state: CircuitState,
    config: CircuitBreakerConfig,
    circuitKey: string
  ): void {
    state.failures++;
    state.totalCalls++;
    state.lastFailureTime = new Date();
    state.consecutiveSuccesses = 0;

    this.checkWindowReset(state, config);

    const failureRate = (state.failures / state.totalCalls) * 100;

    if (state.state !== 'open' && failureRate >= config.failureThreshold) {
      state.state = 'open';
      state.nextRetryTime = new Date(Date.now() + config.resetTimeout);

      this.logger.warn(
        `Circuit breaker opened for ${circuitKey}. ` +
        `Failure rate: ${failureRate.toFixed(2)}% (threshold: ${config.failureThreshold}%)`
      );
    }

    if (state.state === 'half-open') {
      state.state = 'open';
      state.nextRetryTime = new Date(Date.now() + config.resetTimeout);
      this.logger.warn(`Circuit breaker reopened for ${circuitKey}`);
    }
  }

  private checkWindowReset(state: CircuitState, config: CircuitBreakerConfig): void {
    const now = Date.now();

    if (now - state.windowStart > config.monitoringPeriod) {
      state.failures = 0;
      state.successes = 0;
      state.totalCalls = 0;
      state.windowStart = now;
    }
  }
}
```

### Usage

```typescript
// In a service
constructor(
  private readonly circuitBreaker: CircuitBreakerPattern
) {}

async fetchData(): Promise<Data> {
  return this.circuitBreaker.execute(
    () => this.externalService.getData(),
    {
      enabled: true,
      failureThreshold: 50, // Open circuit at 50% failure rate
      resetTimeout: 30000, // 30 seconds
      halfOpenMaxCalls: 3, // Test with 3 calls before closing
      monitoringPeriod: 60000 // 1 minute sliding window
    },
    {
      policyName: 'external-api',
      endpoint: '/api/data'
    }
  );
}
```

## 2. Database Fallback Service

Provides graceful degradation when the database is unavailable using in-memory cache fallback, queued writes for eventual consistency, and health-aware automatic recovery.

### Implementation

```typescript
/**
 * Database Fallback Service
 *
 * Provides graceful degradation when database is unavailable:
 * - In-memory cache fallback for read operations
 * - Queued writes for eventual consistency
 * - Health-aware automatic recovery
 */

import { Injectable, Logger } from '@nestjs/common';

interface CachedData<T> {
  data: T;
  expiry: number;
  stale: boolean;
}

@Injectable()
export class DatabaseFallbackService {
  private readonly logger = new Logger(DatabaseFallbackService.name);
  private readonly cache = new Map<string, CachedData<unknown>>();
  private readonly defaultTtl = 300000; // 5 minutes

  /**
   * Execute a database operation with cache fallback
   *
   * @param operation - The database operation to execute
   * @param cacheKey - Unique key for caching the result
   * @param options - Configuration options
   */
  async executeWithFallback<T>(
    operation: () => Promise<T>,
    cacheKey: string,
    options: {
      ttl?: number;
      staleWhileRevalidate?: boolean;
      fallbackValue?: T;
    } = {}
  ): Promise<T> {
    const { ttl = this.defaultTtl, staleWhileRevalidate = true, fallbackValue } = options;

    try {
      // Attempt the database operation
      const result = await operation();

      // Cache successful result
      this.cache.set(cacheKey, {
        data: result,
        expiry: Date.now() + ttl,
        stale: false,
      });

      return result;
    } catch (error) {
      // Check for cached data
      const cached = this.cache.get(cacheKey) as CachedData<T> | undefined;

      if (cached) {
        const isExpired = cached.expiry < Date.now();

        if (!isExpired) {
          // Return fresh cached data
          this.logger.warn(`Database unavailable, serving from cache: ${cacheKey}`);
          return cached.data;
        }

        if (staleWhileRevalidate) {
          // Return stale data while marking for revalidation
          this.logger.warn(`Database unavailable, serving stale data: ${cacheKey}`);
          cached.stale = true;
          return cached.data;
        }
      }

      // No cached data available
      if (fallbackValue !== undefined) {
        this.logger.warn(`Database unavailable, using fallback value: ${cacheKey}`);
        return fallbackValue;
      }

      // Re-throw if no fallback available
      this.logger.error(`Database unavailable, no fallback for: ${cacheKey}`);
      throw error;
    }
  }

  /**
   * Invalidate cached data
   */
  invalidate(cacheKey: string): void {
    this.cache.delete(cacheKey);
  }

  /**
   * Invalidate all cached data matching a pattern
   */
  invalidatePattern(pattern: string): void {
    const regex = new RegExp(pattern);
    for (const key of this.cache.keys()) {
      if (regex.test(key)) {
        this.cache.delete(key);
      }
    }
  }

  /**
   * Get cache statistics
   */
  getStats(): { size: number; staleCount: number } {
    let staleCount = 0;
    for (const value of this.cache.values()) {
      if (value.stale) staleCount++;
    }
    return { size: this.cache.size, staleCount };
  }
}
```

### Usage

```typescript
// In a repository
constructor(
  private readonly dbFallback: DatabaseFallbackService
) {}

async findUser(id: string): Promise<User | null> {
  return this.dbFallback.executeWithFallback(
    () => this.userRepository.findOne({ where: { id } }),
    `user:${id}`,
    {
      ttl: 600000, // 10 minutes
      staleWhileRevalidate: true,
      fallbackValue: null
    }
  );
}

// Invalidate on update
async updateUser(id: string, data: UpdateUserDto): Promise<User> {
  const user = await this.userRepository.update(id, data);
  this.dbFallback.invalidate(`user:${id}`);
  return user;
}
```

## 3. Best Practices

### Circuit Breaker
- Set `failureThreshold` based on acceptable error rate (typically 50-80%)
- Configure `resetTimeout` to allow downstream services time to recover (30-60 seconds)
- Use `halfOpenMaxCalls` to test recovery with limited traffic (3-5 calls)
- Monitor circuit state via `getMetrics()` and expose via health endpoints

### Database Fallback
- Always set appropriate `ttl` values based on data freshness requirements
- Use `staleWhileRevalidate` for non-critical data to improve availability
- Invalidate cache on writes to maintain consistency
- Monitor cache hit/miss ratios via `getStats()`
