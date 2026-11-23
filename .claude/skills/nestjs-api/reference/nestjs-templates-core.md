# NestJS Core Templates — Main Entry & Root Modules

Production-ready core templates for NestJS 11.x application bootstrapping and module architecture.

## Main Entry Point (src/main.ts)

```typescript
/**
 * my-service - Main Application Entry Point
 *
 * NestJS backend service
 *
 * NestJS 11.x with enhanced shutdown hooks and logging
 */

import 'dotenv/config';
import { readFileSync } from 'fs';
import { join } from 'path';

import { Logger, VersioningType, LogLevel } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

import { AppModule } from './app.module';
import { MiddlewareConfigurationService } from './common/middleware/config/middleware-configuration.service';
import { registerSecurityMiddleware } from './common/middleware/security.middleware';
import { requestContext } from './common/context/request-context.service';

import type { NestFastifyApplication } from '@nestjs/platform-fastify';

interface IPackageJson {
  version?: string;
  name?: string;
}

let app: NestFastifyApplication | null = null;

/**
 * Determine log levels based on environment
 */
function getLogLevels(environment: string): LogLevel[] {
  if (environment === 'production') {
    return ['error', 'warn', 'log'];
  }
  if (environment === 'test') {
    return ['error', 'warn'];
  }
  return ['error', 'warn', 'log', 'debug', 'verbose'];
}

async function bootstrap(): Promise<void> {
  // NestJS 11.x: Enhanced Logger with timestamp option
  const logger = new Logger('Bootstrap', { timestamp: true });

  logger.log('Starting my-service with STRICT configuration mode');

  // Read version from package.json
  let version = '0.0.0';
  let serviceName = 'my-service';
  try {
    const packageJsonPath = join(process.cwd(), 'package.json');
    const packageJsonContent = readFileSync(packageJsonPath, 'utf8');
    const packageJson = JSON.parse(packageJsonContent) as unknown as IPackageJson;
    version = packageJson.version ?? '0.0.0';
    serviceName = packageJson.name ?? 'my-service';
  } catch (error) {
    logger.error('Failed to read version from package.json', error);
    throw new Error('Package.json must be accessible for version information');
  }

  // Determine environment early for log levels
  const nodeEnv = process.env.NODE_ENV ?? 'development';

  try {
    // Create NestJS application with Fastify adapter
    app = await NestFactory.create<NestFastifyApplication>(
      AppModule,
      new FastifyAdapter({
        logger: false,
        trustProxy: true,
        maxParamLength: 500,
        bodyLimit: 1048576, // 1MB
        keepAliveTimeout: 72000,
        connectionTimeout: 10000,
        caseSensitive: false,
        ignoreTrailingSlash: true,
        // Fastify request ID for correlation
        genReqId: (req) => {
          return req.headers['x-correlation-id'] as string ?? crypto.randomUUID();
        },
      }),
      {
        // NestJS 11.x: Configure log levels at creation
        logger: getLogLevels(nodeEnv),
        bufferLogs: true, // Buffer logs until logger is ready
      },
    );

    // Use buffered logger
    app.useLogger(app.get(Logger));

    const configService = app.get(ConfigService);

    // STRICT MODE: Validate required configuration
    const port = configService.get<number>('application.port');
    const environment = configService.get<string>('application.environment');
    const apiPrefix = configService.get<string>('application.apiPrefix');
    const enableSwagger = configService.get<boolean>('application.enableSwagger');
    const swaggerPath = configService.get<string>('application.swaggerPath');

    if (port === undefined) {
      throw new Error('Missing required configuration: PORT');
    }
    if (!environment) {
      throw new Error('Missing required configuration: NODE_ENV');
    }
    if (!apiPrefix) {
      throw new Error('Missing required configuration: API_PREFIX');
    }

    // Security & Performance middleware
    const middlewareConfigService = app.get(MiddlewareConfigurationService);
    await registerSecurityMiddleware(app, middlewareConfigService);

    // CORS configuration
    const corsOrigins = configService.get<string[]>('security.cors.origins');
    const corsCredentials = configService.get<boolean>('security.cors.credentials');

    if (!corsOrigins || corsOrigins.length === 0) {
      throw new Error('Missing required configuration: SECURITY_CORS_ORIGINS');
    }

    app.enableCors({
      origin: corsOrigins,
      credentials: corsCredentials ?? true,
      methods: configService.get<string[]>('security.cors.methods'),
      allowedHeaders: configService.get<string[]>('security.cors.allowedHeaders'),
      exposedHeaders: configService.get<string[]>('security.cors.exposedHeaders'),
      maxAge: configService.get<number>('security.cors.maxAge'),
    });

    // Single owner of signal handling: runs onModuleDestroy → beforeApplicationShutdown →
    // onApplicationShutdown, then re-raises the signal (exit 143 on SIGTERM).
    // Do NOT add process.on('SIGTERM') handlers that call app.close(): hooks then run twice.
    app.enableShutdownHooks();

    // API Versioning
    app.enableVersioning({
      type: VersioningType.URI,
      defaultVersion: '1',
      prefix: 'v',
    });

    app.setGlobalPrefix(apiPrefix);

    // Swagger API documentation
    if (enableSwagger === true) {
      const config = new DocumentBuilder()
        .setTitle('my-service API')
        .setDescription('NestJS backend service')
        .setVersion(version)
        .addBearerAuth()
        .addServer(`http://localhost:${port}`, 'Local Development')
        .addTag('health', 'Health check endpoints')
        .addTag('config', 'Configuration management')
        .build();

      const document = SwaggerModule.createDocument(app, config);
      SwaggerModule.setup(swaggerPath ?? 'api/docs', app, document, {
        swaggerOptions: {
          persistAuthorization: true,
          displayRequestDuration: true,
          filter: true,
          showExtensions: true,
        },
        customSiteTitle: `${serviceName} API Documentation`,
      });

      logger.log(`API Documentation available at http://localhost:${port}/${swaggerPath}`);
    }

    // Start the application
    await app.listen(port, '0.0.0.0', () => {
      logger.log(`Server is listening on all network interfaces`);
    });

    logger.log(`my-service started successfully`);
    logger.log(`Server running on http://localhost:${port}`);
    logger.log(`Environment: ${environment}`);
    logger.log(`API Prefix: /${apiPrefix}/v1`);
    logger.log(`Version: ${version}`);

  } catch (error) {
    logger.error('Failed to start my-service', error);
    if (app) {
      await app.close();
    }
    process.exit(1);
  }
}

function registerProcessHandlers(): void {
  const logger = new Logger('ProcessHandlers', { timestamp: true });

  process.on('uncaughtException', (error: Error, origin: string) => {
    logger.error(`Uncaught Exception (${origin}):`, error);
    // Allow some time for logging before exit
    setTimeout(() => process.exit(1), 1000);
  });

  process.on('unhandledRejection', (reason: unknown, promise: Promise<unknown>) => {
    logger.error('Unhandled Rejection at:', promise);
    logger.error('Reason:', reason);
    // Allow some time for logging before exit
    setTimeout(() => process.exit(1), 1000);
  });

  // SIGTERM/SIGINT: owned by app.enableShutdownHooks(). Before bootstrap finishes the default
  // signal behaviour (terminate) is correct; no extra signal handlers here.
}

registerProcessHandlers();
void bootstrap();
```

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
import { Module, ValidationPipe, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { APP_FILTER, APP_INTERCEPTOR, APP_PIPE } from '@nestjs/core';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { ScheduleModule } from '@nestjs/schedule';
import { TerminusModule } from '@nestjs/terminus';
import { ThrottlerModule, ThrottlerModuleOptions } from '@nestjs/throttler';

// Aggregated modules
import { AuthModule } from './auth/auth.module';
import { CommonModule } from './common/common.module';
import { GlobalExceptionFilter } from './common/filters/global-exception.filter';
import { LoggingInterceptor } from './common/interceptors/implementations/logging.interceptor';
import { TransformInterceptor } from './common/interceptors/implementations/transform.interceptor';
import { ConfigModule } from './config/config.module';
import { CoreModule } from './core/core.module';
import { FeaturesModule } from './features/features.module';

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
    // Global validation pipe
    {
      provide: APP_PIPE,
      useFactory: (configService: ConfigService) => {
        const environment = configService.get<string>('application.environment');
        return new ValidationPipe({
          whitelist: true,
          forbidNonWhitelisted: true,
          transform: true,
          transformOptions: {
            // Implicit conversion turns the string "false" into true for boolean properties.
            // Convert explicitly with @Type(() => Number) / @Transform on the DTO instead.
            enableImplicitConversion: false,
            enableCircularCheck: true,
          },
          disableErrorMessages: environment === 'production',
          forbidUnknownValues: true,
          stopAtFirstError: false,
          validationError: {
            target: false,
            value: environment !== 'production',
          },
        });
      },
      inject: [ConfigService],
    },
    // Global interceptors
    { provide: APP_INTERCEPTOR, useClass: LoggingInterceptor },
    { provide: APP_INTERCEPTOR, useClass: TransformInterceptor },
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
import { Global, Module, Logger, OnModuleInit } from '@nestjs/common';

import { ApiModule } from './api/api.module';
import { CacheModule } from './cache/cache.module';
import { DatabaseModule } from './database/database.module';
import { DynamicConfigurationModule } from './dynamic-configuration/dynamic-configuration.module';
import { HealthModule } from './health/health.module';
import { ResilienceModule } from './resilience/resilience.module';

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
