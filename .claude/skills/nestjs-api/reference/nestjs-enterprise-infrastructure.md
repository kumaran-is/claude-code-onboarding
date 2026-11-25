# NestJS Enterprise Infrastructure

Security, rate limiting, health checks, and API documentation for NestJS 12.x.

## Security Middleware (Helmet)

Comprehensive security headers including CSP, HSTS, CORP, COEP, COOP.

```typescript
// src/common/middleware/security.middleware.ts
/**
 * Security Middleware Configuration
 *
 * Implements comprehensive security headers including:
 * - Content Security Policy (CSP)
 * - HTTP Strict Transport Security (HSTS)
 * - Cross-Origin Resource Policy (CORP)
 * - Cross-Origin Embedder Policy (COEP)
 * - Cross-Origin Opener Policy (COOP)
 */

import helmet from '@fastify/helmet';
import compression from '@fastify/compress';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import type { MiddlewareConfigurationService } from './config/middleware-configuration.service.js';

export async function registerSecurityMiddleware(
  app: NestFastifyApplication,
  config: MiddlewareConfigurationService,
): Promise<void> {
  const environment = config.getEnvironment();
  const isProduction = environment === 'production';

  // Compression middleware
  await app.register(compression, {
    encodings: ['gzip', 'deflate'],
    threshold: 1024, // Only compress responses > 1KB
  });

  // Helmet security middleware with comprehensive headers
  await app.register(helmet, {
    // Content Security Policy
    contentSecurityPolicy: isProduction
      ? {
          directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'"], // Swagger UI needs inline styles
            imgSrc: ["'self'", 'data:', 'https:'],
            fontSrc: ["'self'", 'https:', 'data:'],
            connectSrc: ["'self'"],
            objectSrc: ["'none'"],
            mediaSrc: ["'self'"],
            frameSrc: ["'none'"],
            baseUri: ["'self'"],
            formAction: ["'self'"],
            frameAncestors: ["'none'"],
            upgradeInsecureRequests: [],
          },
        }
      : false, // Disable CSP in development for easier debugging

    // Cross-Origin Embedder Policy
    crossOriginEmbedderPolicy: isProduction ? { policy: 'require-corp' } : false,

    // Cross-Origin Opener Policy
    crossOriginOpenerPolicy: { policy: 'same-origin' },

    // Cross-Origin Resource Policy
    crossOriginResourcePolicy: { policy: 'same-origin' },

    // DNS Prefetch Control
    dnsPrefetchControl: { allow: false },

    // Frameguard (X-Frame-Options)
    frameguard: { action: 'deny' },

    // Hide Powered By
    hidePoweredBy: true,

    // HTTP Strict Transport Security
    hsts: isProduction
      ? {
          maxAge: 31536000, // 1 year
          includeSubDomains: true,
          preload: true,
        }
      : false,

    // IE No Open
    ieNoOpen: true,

    // No Sniff (X-Content-Type-Options)
    noSniff: true,

    // Origin Agent Cluster
    originAgentCluster: true,

    // Permitted Cross-Domain Policies
    permittedCrossDomainPolicies: { permittedPolicies: 'none' },

    // Referrer Policy
    referrerPolicy: { policy: 'strict-origin-when-cross-origin' },

    // Helmet 8 sets `X-XSS-Protection: 0` (disables the legacy auditor, which itself enabled XSS); keep it on
    xssFilter: true,
  });
}
```

## Rate Limiting (ThrottlerModule)

Multi-tier rate limiting with short, medium, and long windows.

```typescript
// src/app.module.ts (excerpt)
import { ThrottlerModule, ThrottlerModuleOptions } from '@nestjs/throttler';

@Module({
  imports: [
    ThrottlerModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService): ThrottlerModuleOptions => {
        const config = configService.get<IThrottlerConfig>('throttler');

        if (!config) {
          throw new Error('Throttler configuration is missing');
        }

        return {
          throttlers: [
            { name: 'short', ttl: config.short.ttl, limit: config.short.limit },
            { name: 'medium', ttl: config.medium.ttl, limit: config.medium.limit },
            { name: 'long', ttl: config.long.ttl, limit: config.long.limit },
          ],
        };
      },
    }),
  ],
})
export class AppModule {}
```

```typescript
// src/config/throttler.config.ts
import { registerAs } from '@nestjs/config';

export interface IThrottlerConfig {
  short: { ttl: number; limit: number };
  medium: { ttl: number; limit: number };
  long: { ttl: number; limit: number };
}

export default registerAs(
  'throttler',
  (): IThrottlerConfig => ({
    short: {
      ttl: 1000, // 1 second
      limit: 10, // 10 requests per second
    },
    medium: {
      ttl: 10000, // 10 seconds
      limit: 50, // 50 requests per 10 seconds
    },
    long: {
      ttl: 60000, // 60 seconds
      limit: 200, // 200 requests per minute
    },
  }),
);
```

## Swagger / OpenAPI Setup

Complete Swagger documentation with authentication and versioning.

```typescript
// src/main.ts (excerpt)
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter(),
  );

  const config = app.get(ConfigService);
  // Defaults (PORT 3000, API_PREFIX 'api', SWAGGER_ENABLED true, SWAGGER_PATH 'api/docs') live in src/config/env.ts;
  // APP_VERSION is required. The `application` registerAs factory maps them with getRequired*().
  const port = config.getOrThrow<number>('application.port');
  const apiPrefix = config.getOrThrow<string>('application.apiPrefix');
  const version = config.getOrThrow<string>('application.version');
  const enableSwagger = config.getOrThrow<boolean>('application.enableSwagger');
  const swaggerPath = config.getOrThrow<string>('application.swaggerPath');

  app.setGlobalPrefix(apiPrefix);

  // Swagger API documentation
  if (enableSwagger === true) {
    const swaggerConfig = new DocumentBuilder()
      .setTitle('NestJS API')
      .setDescription('Enterprise-grade REST API built with NestJS 12.x')
      .setVersion(version)
      .addBearerAuth()
      .addServer(`http://localhost:${port}`, 'Local Development')
      .addServer('https://api.staging.example.com', 'Staging')
      .addServer('https://api.example.com', 'Production')
      .addTag('health', 'Health check endpoints')
      .addTag('auth', 'Authentication endpoints')
      .addTag('users', 'User management')
      .build();

    const document = SwaggerModule.createDocument(app, swaggerConfig);
    SwaggerModule.setup(swaggerPath ?? 'api/docs', app, document, {
      swaggerOptions: {
        persistAuthorization: true,
        displayRequestDuration: true,
        filter: true,
        showExtensions: true,
      },
    });

    logger.log(`Swagger documentation available at: http://localhost:${port}/${swaggerPath}`);
  }

  await app.listen(port, '0.0.0.0');
}

await bootstrap(); // ESM top-level await: a startup failure rejects and exits non-zero
```

## Health Checks (Terminus 12)

Kubernetes-ready liveness, readiness and startup probes with `@nestjs/terminus` 12.2.0. Terminus 12 **removed** the
legacy `HealthIndicator` base class, `HealthCheckError` and `getStatus()` (a probe importing them fails with TS2724);
custom checks use `HealthIndicatorService`. Verified 2026-11-24 on NestJS 12.6.0 (Fastify, PostgreSQL 18, Redis 8):
`/health` 200 with `database` and `redis` up, from the reference app behind `nestjs-production-baseline.md`.

```typescript
// src/health/health.controller.ts
import { Controller, Get, Inject, VERSION_NEUTRAL } from '@nestjs/common';
import { ApiOperation, ApiTags } from '@nestjs/swagger';
import {
  HealthCheck,
  HealthCheckService,
  HealthIndicatorService,
  MemoryHealthIndicator,
  PrismaHealthIndicator,
} from '@nestjs/terminus';
import { SkipThrottle } from '@nestjs/throttler';
import type { Redis } from 'ioredis';
import { Public } from '../auth/auth.decorators.js';
import { PrismaService } from '../database/prisma.service.js';

export const HEALTH_REDIS = Symbol('HEALTH_REDIS');

@ApiTags('health')
@Controller({ path: 'health', version: VERSION_NEUTRAL })
@Public()
@SkipThrottle()
export class HealthController {
  private startedAt: Date | null = null;

  constructor(
    private readonly health: HealthCheckService,
    private readonly indicators: HealthIndicatorService,
    private readonly memory: MemoryHealthIndicator,
    private readonly prismaIndicator: PrismaHealthIndicator,
    private readonly prisma: PrismaService,
    @Inject(HEALTH_REDIS) private readonly redis: Redis,
  ) {}

  /** Liveness: is the process alive? Never checks dependencies (a DB outage must not restart every pod). */
  @Get('live')
  @HealthCheck()
  @ApiOperation({ summary: 'Liveness probe' })
  live() {
    return this.health.check([this.memory.checkHeap('memory_heap', 500 * 1024 * 1024)]);
  }

  /** Readiness: can this instance take traffic? 503 when a dependency is down. */
  @Get('ready')
  @HealthCheck()
  @ApiOperation({ summary: 'Readiness probe' })
  ready() {
    return this.health.check([
      // Built-in Prisma indicator; `.withTimeout()` replaces the deprecated `timeout` option.
      this.prismaIndicator.pingCheck('database', this.prisma.client).withTimeout(1500),
      // Custom check with the v12 API: no base class, no HealthCheckError.
      this.indicators
        .check('redis')
        .attempt(async () => {
          const pong = await this.redis.ping();
          if (pong !== 'PONG') throw new Error(`unexpected reply ${String(pong)}`);
        })
        .withTimeout(1000)
        // Replace the driver's error text in the public body; it is still logged by Terminus.
        .withFailureData({ message: 'unavailable' }),
    ]);
  }

  /** Startup: done initializing? Answers down until markStarted() runs (call it from onApplicationBootstrap). */
  @Get('startup')
  @HealthCheck()
  @ApiOperation({ summary: 'Startup probe' })
  startup() {
    const session = this.indicators.check('startup');
    return this.health.check([
      () =>
        this.startedAt === null
          ? session.down('still starting')
          : session.up({ startedAt: this.startedAt.toISOString() }),
    ]);
  }

  markStarted(): void {
    this.startedAt = new Date();
  }
}
```

Module wiring: `TerminusModule.forRoot({ errorLogStyle: 'json' })` in the imports; provide `HEALTH_REDIS` with a
factory (`new Redis(url, { maxRetriesPerRequest: 1, lazyConnect: true })`) and `quit()` it in `onApplicationShutdown`.

Notes:
- A `down` result makes `health.check` answer **503**; the indicator functions never throw for that.
- `HealthCheckAttempt` also offers `.cacheFor(ttl)` (do not hammer the database from every probe) and
  `.degradedAfter(ms)` (slow but working).
- `PrismaHealthIndicator.pingCheck` can include the driver's error text in its down body; see
  `deployment-ci-cd/reference/health-endpoints.md` for a SQL-only custom indicator when that matters.
- Migration from v11: replace each `extends HealthIndicator` class with an `indicators.check(key).attempt(fn)` call
  (or `.up()` / `.down()`), delete `HealthCheckError`, and move `timeout` options to `.withTimeout()`.
- Downstream HTTP services: `FetchHealthIndicator` (global `fetch`, no `@nestjs/axios`) replaces the deprecated
  `HttpHealthIndicator`. Check them on readiness only when the pod cannot serve without them, never on liveness:
  ```typescript
  constructor(private readonly health: HealthCheckService, private readonly http: FetchHealthIndicator) {}
  // inside readiness(): 2xx = up; verify() overrides that rule
  () => this.http.pingCheck('payments', this.paymentsHealthUrl, { verify: (res) => res.status === 204 }),
  ```
  Verified on Terminus 12.2.0: 204 → `up`, 503 → `health.check` rejects with 503, a failing `verify` → 503.

## Usage Notes

1. **Security**: Helmet middleware provides comprehensive security headers, disabled CSP in development
2. **Rate Limiting**: Three-tier throttling (short/medium/long windows) prevents abuse
3. **Health Checks**: Kubernetes-ready probes (liveness/readiness/startup) for zero-downtime deployments
4. **Swagger**: Full API documentation with authentication, versioning, and multiple environment servers
