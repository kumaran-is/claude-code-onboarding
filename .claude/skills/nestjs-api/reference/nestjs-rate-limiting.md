# Inbound Rate Limiting — NestJS

Verified 2026-11-24 on NestJS 12.6.0 + Fastify 5.12.8 with `@nestjs/throttler` 6.8.0 (peers on Nest 7–12): with
`THROTTLE_LIMIT=20` the 21st request with one credential → 429 while a second credential kept its own bucket (e2e).
Full wiring: `nestjs-production-baseline.md`.

## Layer 1: edge (load balancer / WAF)

Volumetric and IP-reputation limits belong at the edge (cloud WAF / load-balancer policy) so floods never reach Node.
See `java-spring-api/reference/spring-boot-rate-limiting.md` for a Terraform example. Typical baseline: per-IP limit,
OWASP CRS rules, geo restrictions where the product allows them.

## Layer 2: `@nestjs/throttler` (application)

Register `ThrottlerGuard` as the **first** `APP_GUARD` (before authentication) so floods are rejected before token
verification. Because the principal is not known yet, key the bucket on a hash of the bearer credential and fall back
to the IP:

```typescript
// src/common/throttler-tracker.ts
import { createHash } from 'node:crypto';

/**
 * Throttle key: a fingerprint of the bearer credential when present (per caller, survives NAT
 * and rotating IPs), else the client IP. The throttler runs BEFORE auth, so the principal is
 * not available yet; the raw token is hashed, never stored as the key.
 */
export function throttleTracker(req: Record<string, unknown>): Promise<string> {
  const headers = req['headers'] as Record<string, string | string[] | undefined>;
  const auth = headers['authorization'];
  if (typeof auth === 'string' && auth.startsWith('Bearer ') && auth.length > 7) {
    return Promise.resolve('tok:' + createHash('sha256').update(auth.slice(7)).digest('hex').slice(0, 32));
  }
  return Promise.resolve('ip:' + String(req['ip']));
}
```

```typescript
// src/app.module.ts (excerpt)
ThrottlerModule.forRootAsync({
  inject: [ConfigService],
  useFactory: (config: ConfigService<Env, true>) => ({
    throttlers: [{ name: 'default', ttl: config.get('THROTTLE_TTL_MS', { infer: true }), limit: config.get('THROTTLE_LIMIT', { infer: true }) }],
    getTracker: throttleTracker,
    skipIf: (context) => context.getType() !== 'http', // WebSocket and BullMQ contexts are not throttled here
  }),
}),
// providers — order matters: throttle, then authenticate
{ provide: APP_GUARD, useClass: ThrottlerGuard },
{ provide: APP_GUARD, useClass: JwtAuthGuard },
```

`ttl` is in **milliseconds** (v5+). `req.ip` is the socket address unless the Fastify adapter is created with
`trustProxy` set to the proxy hop count/addresses you actually run behind; never `true` on a directly exposed service
(clients could spoof `X-Forwarded-For`).

## Shared storage for multiple instances

In-memory counters are per process: N replicas allow N× the limit. Use Redis storage. The maintained package is
`@nest-lab/throttler-storage-redis` — `@nestjs/throttler-storage-redis` does **not exist** on npm (404).

> **NestJS 12: BLOCKED as of 2026-11-24.** `@nest-lab/throttler-storage-redis` 1.2.0 (latest) peers on
> `@nestjs/common`/`@nestjs/core` `^7 … ^11` only; `npm install -E @nest-lab/throttler-storage-redis@1.2.0` in a
> NestJS 12.6.0 app fails with `ERESOLVE` (exit 1). Do not force it with `--legacy-peer-deps` or `--force`. Until a
> release declares Nest 12: rely on the edge limit (layer 1) for multi-replica totals and per-instance throttling,
> or implement `ThrottlerStorage` from `@nestjs/throttler` 6.8.0 on `ioredis`
> (`increment(key, ttl, limit, blockDuration, throttlerName): Promise<{ totalHits, timeToExpire, isBlocked,
> timeToBlockExpire }>`, using an atomic Lua script) and pass the instance as `storage`. The example below is the
> NestJS 11 configuration, kept for when the package supports Nest 12.

```typescript
// src/common/throttler-redis.options.ts (type-checked; runtime against Redis NOT RUN)
import { ThrottlerStorageRedisService } from '@nest-lab/throttler-storage-redis';
import type { ThrottlerModuleOptions } from '@nestjs/throttler';
import { Redis } from 'ioredis';
import { throttleTracker } from './throttler-tracker.js';

/** Shared counters for multi-instance deployments. In-memory storage is per process. */
export function redisThrottlerOptions(redisUrl: string): ThrottlerModuleOptions {
  if (redisUrl.trim() === '') throw new Error('REDIS_URL is required for shared rate limiting');
  return {
    throttlers: [
      { name: 'burst', ttl: 1_000, limit: 20 },
      { name: 'sustained', ttl: 60_000, limit: 300 },
    ],
    getTracker: throttleTracker,
    errorMessage: 'Too many requests',
    storage: new ThrottlerStorageRedisService(new Redis(redisUrl, { maxRetriesPerRequest: 1, lazyConnect: true })),
  };
}
```

## Stricter limits on credential endpoints

```typescript
@Throttle({ burst: { limit: 5, ttl: 60_000 } }) // 5/min for this route, overriding the 'burst' throttler
@Post('login')
login(@Body() dto: LoginDto): Promise<TokenPair> {
  return this.auth.login(dto);
}
```

Also rate-limit password reset and login **per account** (a second throttler keyed on the normalised username), not
only per IP.

## Key Rules

- Throttler guard first, then authentication, then authorization.
- Shared Redis storage whenever more than one instance serves traffic.
- Hash credentials before using them as keys; never store raw tokens in Redis.
- Use `errorMessage` to customise the 429 body; do not override `throwThrottlingException` with a `void` signature (fails to compile on v6).
- Add `@SkipThrottle()` only to health/readiness probes.
