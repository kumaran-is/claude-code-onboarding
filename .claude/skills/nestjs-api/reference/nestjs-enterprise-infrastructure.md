# NestJS Enterprise Infrastructure

Security, rate limiting, health checks, and API documentation for NestJS 11.x.

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
import type { MiddlewareConfigurationService } from './config/middleware-configuration.service';

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
  const port = config.get<number>('application.port', 3000);
  const apiPrefix = config.get<string>('application.apiPrefix', 'api');
  const version = config.get<string>('application.version', '1.0.0');
  const enableSwagger = config.get<boolean>('application.enableSwagger', true);
  const swaggerPath = config.get<string>('application.swaggerPath', 'api/docs');

  app.setGlobalPrefix(apiPrefix);

  // Swagger API documentation
  if (enableSwagger === true) {
    const swaggerConfig = new DocumentBuilder()
      .setTitle('NestJS API')
      .setDescription('Enterprise-grade REST API built with NestJS 11.x')
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

bootstrap();
```

## Health Checks (Terminus)

Kubernetes-ready health checks with liveness, readiness, and startup probes.

```typescript
// src/core/health/controllers/health.controller.ts
import { Controller, Get } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import {
  HealthCheck,
  HealthCheckService,
  HealthCheckResult,
  MemoryHealthIndicator,
  DiskHealthIndicator,
} from '@nestjs/terminus';
import { DatabaseHealthIndicator } from '../indicators/database.health-indicator';
import { RedisHealthIndicator } from '../indicators/redis.health-indicator';
import { ApplicationHealthIndicator } from '../indicators/application.health-indicator';

@Controller('health')
@ApiTags('health')
export class HealthController {
  private startupComplete = false;
  private startupTime: Date | null = null;

  constructor(
    private readonly health: HealthCheckService,
    private readonly memory: MemoryHealthIndicator,
    private readonly disk: DiskHealthIndicator,
    private readonly database: DatabaseHealthIndicator,
    private readonly redis: RedisHealthIndicator,
    private readonly application: ApplicationHealthIndicator,
  ) {}

  /**
   * Liveness probe - Is the application running?
   * Should return 200 if the app is alive (even if dependencies are down)
   */
  @Get('live')
  @HealthCheck()
  @ApiOperation({ summary: 'Liveness probe - is the application running?' })
  @ApiResponse({ status: 200, description: 'Application is alive' })
  @ApiResponse({ status: 503, description: 'Application is not responding' })
  async checkLive(): Promise<HealthCheckResult> {
    return this.health.check([
      // Only check if the process is running and has enough memory
      () => this.memory.checkHeap('memory_heap', 500 * 1024 * 1024), // 500MB
    ]);
  }

  /**
   * Readiness probe - Can the application accept traffic?
   * Should return 200 only if all dependencies are healthy
   */
  @Get('ready')
  @HealthCheck()
  @ApiOperation({ summary: 'Readiness probe - can the application accept traffic?' })
  @ApiResponse({ status: 200, description: 'Application is ready to accept traffic' })
  @ApiResponse({ status: 503, description: 'Application is not ready' })
  async checkReady(): Promise<HealthCheckResult> {
    return this.health.check([
      () => this.database.isHealthy('database'),
      () => this.redis.isHealthy('redis'),
      () => this.application.isHealthy('application'),
    ]);
  }

  /**
   * Startup probe - Has the application finished initializing?
   * Kubernetes uses this to know when to start liveness/readiness checks
   */
  @Get('startup')
  @HealthCheck()
  @ApiOperation({ summary: 'Startup probe - has the application finished initializing?' })
  @ApiResponse({ status: 200, description: 'Application startup complete' })
  @ApiResponse({ status: 503, description: 'Application still starting up' })
  async checkStartup(): Promise<HealthCheckResult> {
    if (!this.startupComplete) {
      return {
        status: 'error',
        info: {},
        error: {
          startup: {
            status: 'down',
            message: 'Application still starting up',
          },
        },
        details: {},
      };
    }

    return {
      status: 'ok',
      info: {
        startup: {
          status: 'up',
          startupTime: this.startupTime?.toISOString(),
        },
      },
      error: {},
      details: {
        startup: {
          status: 'up',
          startupTime: this.startupTime?.toISOString(),
        },
      },
    };
  }

  /**
   * Mark application as fully started
   */
  markStartupComplete(): void {
    this.startupComplete = true;
    this.startupTime = new Date();
  }

  /**
   * Detailed health check for monitoring dashboards
   */
  @Get()
  @HealthCheck()
  @ApiOperation({ summary: 'Full health check with all indicators' })
  async checkAll(): Promise<HealthCheckResult> {
    return this.health.check([
      () => this.memory.checkHeap('memory_heap', 500 * 1024 * 1024),
      () => this.memory.checkRSS('memory_rss', 1024 * 1024 * 1024), // 1GB
      () => this.database.isHealthy('database'),
      () => this.redis.isHealthy('redis'),
      () => this.application.isHealthy('application'),
    ]);
  }
}
```

### Custom Health Indicators

```typescript
// src/core/health/indicators/database.health-indicator.ts
import { Injectable } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult, HealthCheckError } from '@nestjs/terminus';
import { PrismaService } from '../../database/services/prisma.service';

@Injectable()
export class DatabaseHealthIndicator extends HealthIndicator {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async isHealthy(key: string): Promise<HealthIndicatorResult> {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      return this.getStatus(key, true, { status: 'up' });
    } catch (error) {
      throw new HealthCheckError(
        'Database check failed',
        this.getStatus(key, false, { status: 'down', error: error.message }),
      );
    }
  }
}

// src/core/health/indicators/redis.health-indicator.ts
import { Injectable } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult, HealthCheckError } from '@nestjs/terminus';
import { RedisService } from '../../cache/services/redis.service';

@Injectable()
export class RedisHealthIndicator extends HealthIndicator {
  constructor(private readonly redis: RedisService) {
    super();
  }

  async isHealthy(key: string): Promise<HealthIndicatorResult> {
    try {
      await this.redis.ping();
      return this.getStatus(key, true, { status: 'up' });
    } catch (error) {
      throw new HealthCheckError(
        'Redis check failed',
        this.getStatus(key, false, { status: 'down', error: error.message }),
      );
    }
  }
}

// src/core/health/indicators/application.health-indicator.ts
import { Injectable } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult } from '@nestjs/terminus';

@Injectable()
export class ApplicationHealthIndicator extends HealthIndicator {
  async isHealthy(key: string): Promise<HealthIndicatorResult> {
    return this.getStatus(key, true, {
      name: 'application',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
    });
  }
}
```

## Usage Notes

1. **Security**: Helmet middleware provides comprehensive security headers, disabled CSP in development
2. **Rate Limiting**: Three-tier throttling (short/medium/long windows) prevents abuse
3. **Health Checks**: Kubernetes-ready probes (liveness/readiness/startup) for zero-downtime deployments
4. **Swagger**: Full API documentation with authentication, versioning, and multiple environment servers
