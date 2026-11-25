# NestJS Core Templates — Main Entry & Root Modules

Production-ready core templates for NestJS 12.x application bootstrapping and module architecture.

## Main Entry Point (src/main.ts)

ESM entry (`"type": "module"`): top-level `await`, relative imports with `.js`, no `dotenv` import (the shell, CI or
container sets the environment; `ConfigModule` validates it). The runtime-verified minimal form is in
`nestjs-production-baseline.md`; this is the larger template with CORS, Swagger options and versioning.

```typescript
/**
 * my-service - Main Application Entry Point (NestJS 12.x, Fastify, ESM)
 */
import 'reflect-metadata';
import { readFileSync } from 'node:fs';
import type { IncomingHttpHeaders } from 'node:http';
import { join } from 'node:path';

import { ConsoleLogger, Logger, type LogLevel, VersioningType } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

import { AppModule } from './app.module.js';
import { envSchema } from './config/env.js';
import { MiddlewareConfigurationService } from './common/middleware/config/middleware-configuration.service.js';
import { registerSecurityMiddleware } from './common/middleware/security.middleware.js';

interface IPackageJson {
  version?: string;
  name?: string;
}

function getLogLevels(environment: string): LogLevel[] {
  if (environment === 'production') return ['error', 'warn', 'log'];
  if (environment === 'test') return ['error', 'warn'];
  return ['error', 'warn', 'log', 'debug', 'verbose'];
}

// import.meta.dirname replaces __dirname in ESM (dist/main.js -> ../package.json).
const packageJson = JSON.parse(
  readFileSync(join(import.meta.dirname, '..', 'package.json'), 'utf8'),
) as IPackageJson;
const version = packageJson.version ?? '0.0.0';
const serviceName = packageJson.name ?? 'my-service';
// Logger options are needed before the container exists: wait until ConfigModule has loaded .env (importing
// AppModule started it), then read the env schema (its NODE_ENV default applies).
await ConfigModule.envVariablesLoaded;
const nodeEnv = envSchema.parse(process.env).NODE_ENV;

// NestJS 12: JSON lines; structured params (logger.log('msg', { key })) are on by default.
const logger = new ConsoleLogger({
  json: nodeEnv === 'production',
  logLevels: getLogLevels(nodeEnv),
  redact: ['authorization', 'password', 'passwordHash'],
});
const bootstrapLog = new Logger('Bootstrap');

try {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter({
      logger: false,
      trustProxy: false, // true only behind a known proxy (it makes req.ip client-controlled otherwise)
      maxParamLength: 500,
      bodyLimit: 1_048_576, // 1 MB; larger bodies -> 413
      keepAliveTimeout: 72_000,
      connectionTimeout: 10_000,
      genReqId: (req: { headers: IncomingHttpHeaders }) => { // HTTP/1 or HTTP/2 request
        const header = req.headers['x-correlation-id'];
        return typeof header === 'string' && /^[\w-]{8,64}$/.test(header) ? header : crypto.randomUUID();
      },
    }),
    {
      logger,
      // NestJS 12 opt-in: fail bootstrap on identical routes, warn when one route shadows another.
      routeConflictPolicy: { duplicate: 'error', shadow: 'warn' },
    },
  );

  const configService = app.get(ConfigService);
  // Values were validated by ConfigModule at import time; getOrThrow documents that they are required.
  const port = configService.getOrThrow<number>('application.port');
  const apiPrefix = configService.getOrThrow<string>('application.apiPrefix');
  const enableSwagger = configService.getOrThrow<boolean>('application.enableSwagger');
  const swaggerPath = configService.getOrThrow<string>('application.swaggerPath');

  await registerSecurityMiddleware(app, app.get(MiddlewareConfigurationService));

  app.enableCors({
    origin: configService.getOrThrow<string[]>('security.cors.origins'),
    credentials: configService.getOrThrow<boolean>('security.cors.credentials'),
    methods: configService.getOrThrow<string[]>('security.cors.methods'),
    allowedHeaders: configService.getOrThrow<string[]>('security.cors.allowedHeaders'),
    exposedHeaders: configService.getOrThrow<string[]>('security.cors.exposedHeaders'),
    maxAge: configService.getOrThrow<number>('security.cors.maxAge'),
  });

  // Single owner of signal handling: runs onModuleDestroy -> beforeApplicationShutdown ->
  // onApplicationShutdown (NestJS 12: ordered by module hierarchy level), then re-raises the signal.
  // Do NOT add process.on('SIGTERM') handlers that call app.close(): hooks then run twice.
  app.enableShutdownHooks();
  app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1', prefix: 'v' });
  app.setGlobalPrefix(apiPrefix, { exclude: ['health'] });

  if (enableSwagger) {
    const config = new DocumentBuilder()
      .setTitle(`${serviceName} API`)
      .setVersion(version)
      .addBearerAuth()
      .addTag('health', 'Health check endpoints')
      .build();
    // Swagger 12 builds request/response schemas from the Zod schemas on the routes.
    SwaggerModule.setup(swaggerPath, app, SwaggerModule.createDocument(app, config), {
      swaggerOptions: { persistAuthorization: true, displayRequestDuration: true },
      customSiteTitle: `${serviceName} API Documentation`,
    });
  }

  // 0.0.0.0: Fastify listens on 127.0.0.1 by default, unreachable from outside a container.
  await app.listen({ port, host: '0.0.0.0' });
  bootstrapLog.log('started', { service: serviceName, version, environment: nodeEnv, port });
} catch (error: unknown) {
  bootstrapLog.error('startup failed', error instanceof Error ? error.stack : String(error));
  // exitCode alone is not enough: Redis/BullMQ/pg handles opened during init keep the loop alive.
  process.exit(1);
}
```

`uncaughtException` / `unhandledRejection` policy (log, then exit non-zero) is in
`../../typescript-expert/references/node-service-engineering.md` §11; SIGTERM/SIGINT stay owned by `enableShutdownHooks()`.

## Root Module (src/app.module.ts)

```typescript
/**
 * my-service - Root Application Module
 *
 * Architecture Pattern: Module Aggregation
 * - ConfigModule aggregates all configuration files
 * - CommonModule aggregates all common utilities
 * - CoreModule aggregates all core infrastructure
 * - FeaturesModule aggregates all business feature modules
 */
import {
  Logger,
  Module,
  type OnModuleInit,
  StandardSchemaSerializerInterceptor,
  StandardSchemaValidationPipe,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { APP_FILTER, APP_INTERCEPTOR, APP_PIPE, Reflector } from '@nestjs/core';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { ScheduleModule } from '@nestjs/schedule';
import { TerminusModule } from '@nestjs/terminus';
import { ThrottlerModule, type ThrottlerModuleOptions } from '@nestjs/throttler';

// Aggregated modules
import { AuthModule } from './auth/auth.module.js';
import { CommonModule } from './common/common.module.js';
import { GlobalExceptionFilter } from './common/filters/global-exception.filter.js';
import { LoggingInterceptor } from './common/interceptors/implementations/logging.interceptor.js';
import { TransformInterceptor } from './common/interceptors/implementations/transform.interceptor.js';
import { ConfigModule } from './config/config.module.js';
import { CoreModule } from './core/core.module.js';
import { FeaturesModule } from './features/features.module.js';

interface IThrottlerConfig {
  short: { ttl: number; limit: number };
  medium: { ttl: number; limit: number };
  long: { ttl: number; limit: number };
}

@Module({
  imports: [
    // Configuration Module - Aggregates ALL configuration files
    ConfigModule,

    // Core NestJS modules
    ScheduleModule.forRoot(),
    EventEmitterModule.forRoot({
      wildcard: true,
      delimiter: '.',
      newListener: false,
      removeListener: false,
      maxListeners: 50,
      verboseMemoryLeak: true,
      ignoreErrors: false,
    }),
    ThrottlerModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService): ThrottlerModuleOptions => {
        const config = configService.get<IThrottlerConfig>('throttler');

        if (!config) {
          throw new Error('Throttler configuration is missing');
        }

        return [
          { name: 'short', ttl: config.short.ttl, limit: config.short.limit },
          { name: 'medium', ttl: config.medium.ttl, limit: config.medium.limit },
          { name: 'long', ttl: config.long.ttl, limit: config.long.limit },
        ];
      },
    }),
    TerminusModule,

    // Core infrastructure modules
    CommonModule,
    CoreModule,

    // Business Features
    FeaturesModule,

    // Cross-cutting concerns
    AuthModule,
  ],
  providers: [
    // Global exception filter
    {
      provide: APP_FILTER,
      useClass: GlobalExceptionFilter,
    },
    // Global validation: every parameter declared with { schema } (Zod / any Standard Schema) is
    // validated; failure -> 400. Parameters without a schema pass through untouched.
    { provide: APP_PIPE, useValue: new StandardSchemaValidationPipe() },
    // Global interceptors
    { provide: APP_INTERCEPTOR, useClass: LoggingInterceptor },
    { provide: APP_INTERCEPTOR, useClass: TransformInterceptor },
    // Registered LAST = innermost: it validates the handler's own return value against
    // @SerializeOptions({ schema }) (stripping undeclared fields) BEFORE TransformInterceptor wraps it.
    {
      provide: APP_INTERCEPTOR,
      inject: [Reflector],
      useFactory: (reflector: Reflector) => new StandardSchemaSerializerInterceptor(reflector),
    },
  ],
})
export class AppModule implements OnModuleInit {
  private readonly logger = new Logger(AppModule.name);

  public onModuleInit(): void {
    this.logger.log('my-service Application Module initialized');
    this.logger.log('Architecture: ConfigModule → CommonModule → CoreModule → FeaturesModule → AuthModule');
  }
}
```

## Core Module (src/core/core.module.ts)

```typescript
import { Global, Logger, Module, type OnModuleInit } from '@nestjs/common';

import { ApiModule } from './api/api.module.js';
import { CacheModule } from './cache/cache.module.js';
import { DatabaseModule } from './database/database.module.js';
import { DynamicConfigurationModule } from './dynamic-configuration/dynamic-configuration.module.js';
import { HealthModule } from './health/health.module.js';
import { ResilienceModule } from './resilience/resilience.module.js';

/**
 * Unified Core Module
 *
 * THE CENTRAL MODULE that aggregates all core infrastructure.
 *
 * Architecture Principles:
 * 1. SINGLE ENTRY POINTS: Each module has ONE orchestrator service
 * 2. AUTOMATIC EVERYTHING: Resilience, metrics, health tracking
 * 3. ZERO DUPLICATION: No duplicate code or functionality
 * 4. POLICY-BASED: Configuration through policies
 */
@Global()
@Module({
  imports: [
    DynamicConfigurationModule,
    ResilienceModule,
    DatabaseModule,
    CacheModule,
    ApiModule,
    HealthModule,
  ],
  exports: [
    DynamicConfigurationModule,
    DatabaseModule,
    CacheModule,
    ApiModule,
  ],
})
export class CoreModule implements OnModuleInit {
  private readonly logger = new Logger(CoreModule.name);

  public onModuleInit(): void {
    this.logger.log('Core Module initialized with 6 infrastructure modules');
    this.logger.log('Available: DynamicConfiguration, Resilience, Database, Cache, Api, Health');
  }
}
```
