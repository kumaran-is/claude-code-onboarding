# NestJS Debugging — Logging & Request Lifecycle

Logging setup, Prisma query debugging, and Fastify request lifecycle tracing for NestJS 12.x with Fastify, Prisma ORM, and TypeScript 6.0.

## 1. NestJS Debug Mode

### Bootstrap with Environment-Aware Logging

```typescript
// src/main.ts
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { Logger, LogLevel } from '@nestjs/common';
import { AppModule } from './app.module.js';
import { Config } from './config/static-config.js';

async function bootstrap() {
  const logLevels: Record<string, LogLevel[]> = {
    development: ['log', 'error', 'warn', 'debug', 'verbose'],
    test: ['error', 'warn'],
    production: ['error', 'warn', 'log'],
  };

  const logger = new Logger('Bootstrap');
  const currentEnv = Config.nodeEnv;
  const levels = logLevels[currentEnv] || logLevels.production;

  logger.log(`Starting application in ${currentEnv} mode with log levels: ${levels.join(', ')}`);

  const fastifyAdapter = new FastifyAdapter({
    // Fastify 5 / pino 10: `prettyPrint` no longer exists; pretty output is a transport (dev only).
    logger: currentEnv === 'development' ? {
      level: 'info',
      transport: {
        target: 'pino-pretty',
        options: { colorize: true, translateTime: 'HH:MM:ss Z', ignore: 'pid,hostname' },
      },
    } : false,
    requestIdHeader: 'x-correlation-id',
    requestIdLogLabel: 'correlationId',
  });

  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    fastifyAdapter,
    {
      logger: levels,
      abortOnError: true, // Fail fast on initialization errors
      bufferLogs: true,
    },
  );

  // Enable Fastify request/response logging in development
  if (currentEnv === 'development') {
    app.getHttpAdapter().getInstance().addHook('onRequest', async (request, reply) => {
      logger.debug(`→ ${request.method} ${request.url}`, 'FastifyRequest');
    });

    app.getHttpAdapter().getInstance().addHook('onResponse', async (request, reply) => {
      logger.debug(
        `← ${request.method} ${request.url} ${reply.statusCode} (${reply.getResponseTime().toFixed(2)}ms)`,
        'FastifyResponse'
      );
    });
  }

  await app.listen(Config.port, '0.0.0.0');
  logger.log(`Application listening on port ${Config.port}`, 'Bootstrap');
}

// ESM entry: top-level await, so a startup failure rejects the module and exits non-zero.
await bootstrap();
```

### Per-Module Logger Instances

```typescript
// src/features/users/users.service.ts
import { Injectable, Logger } from '@nestjs/common';

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name);

  async findById(id: string) {
    this.logger.debug(`Finding user by ID: ${id}`);
    try {
      const user = await this.prisma.user.findUnique({ where: { id } });
      if (!user) {
        this.logger.warn(`User not found: ${id}`);
      }
      return user;
    } catch (error) {
      this.logger.error(`Failed to find user ${id}: ${error.message}`, error.stack);
      throw error;
    }
  }
}
```

### NestJS 12 ConsoleLogger: JSON and structured params

`ConsoleLogger` is enough for most services (verified on `@nestjs/common` 12.6.0):

```typescript
const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter(), {
  logger: new ConsoleLogger({ json: true, redact: ['authorization', 'password', 'passwordHash'] }),
});

// NestJS 12: structured params are ON by default; a plain object after the message is attached to the
// entry (nested under `params` in JSON; `flattenParams: true` spreads it into the root object).
this.logger.log('order created', { orderId, tenantId });
```

Upgrading from 11: a plain object after the message used to be logged as a separate message. Log pipelines that parse
that shape change; `new ConsoleLogger({ structuredParams: false })` restores the v11 behaviour while they migrate.
`redact` masks keys at any depth in params and non-string messages; string messages and stack traces are printed as is,
so never interpolate secrets into the message text.

## 2. Prisma Query Logging & Debugging

### Event-Based Query Logging

```typescript
// src/database/prisma.service.ts
import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient, Prisma } from '../generated/prisma/client.js';
import { Config } from '../config/static-config.js';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(PrismaService.name);
  private readonly SLOW_QUERY_THRESHOLD = 1000; // ms

  constructor() {
    const logLevels: Prisma.LogLevel[] = Config.isDevelopment
      ? ['query', 'info', 'warn', 'error']
      : ['warn', 'error'];

    super({
      log: logLevels.map(level => ({ level, emit: 'event' })),
      errorFormat: 'pretty',
    });

    // Query event logging (development only)
    if (Config.isDevelopment) {
      this.$on('query' as never, (event: Prisma.QueryEvent) => {
        this.logger.debug(
          `Query: ${event.query} | Params: ${event.params} | Duration: ${event.duration}ms`,
          'PrismaQuery'
        );
      });
    }

    // Slow query warning (all environments)
    this.$on('query' as never, (event: Prisma.QueryEvent) => {
      if (event.duration >= this.SLOW_QUERY_THRESHOLD) {
        this.logger.warn(
          `Slow query detected (${event.duration}ms): ${event.query.substring(0, 200)}`,
          'PrismaSlowQuery'
        );
      }
    });

    // Error event logging
    this.$on('error' as never, (event: Prisma.LogEvent) => {
      this.logger.error(`Prisma error: ${event.message}`, 'PrismaError');
    });

    // Info and warn events
    this.$on('info' as never, (event: Prisma.LogEvent) => {
      this.logger.log(event.message, 'PrismaInfo');
    });

    this.$on('warn' as never, (event: Prisma.LogEvent) => {
      this.logger.warn(event.message, 'PrismaWarn');
    });
  }

  async onModuleInit() {
    await this.$connect();
    this.logger.log('Database connection established');
    this.logConnectionPoolMetrics();
  }

  async onModuleDestroy() {
    await this.$disconnect();
    this.logger.log('Database connection closed');
  }

  // Connection pool monitoring
  private logConnectionPoolMetrics() {
    setInterval(() => {
      this.logger.debug(
        `Connection pool active: ${this.$metrics ? JSON.stringify(this.$metrics) : 'N/A'}`,
        'PrismaPool'
      );
    }, 30000); // Every 30 seconds
  }

  // Query profiling helper
  async profileQuery<T>(queryName: string, query: () => Promise<T>): Promise<T> {
    const start = performance.now();
    try {
      const result = await query();
      const duration = performance.now() - start;
      this.logger.log(`${queryName} completed in ${duration.toFixed(2)}ms`, 'PrismaProfile');
      return result;
    } catch (error) {
      const duration = performance.now() - start;
      this.logger.error(
        `${queryName} failed after ${duration.toFixed(2)}ms: ${error.message}`,
        error.stack,
        'PrismaProfile'
      );
      throw error;
    }
  }
}
```

### Prisma Debugging Commands

```bash
# Visual database browser (auto-opens in browser)
npx prisma studio

# Introspect existing database schema
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/db" npx prisma db pull

# Validate schema without migrations
npx prisma validate

# Generate Prisma Client with debug output
npx prisma generate --schema=./prisma/schema.prisma

# Debug connection issues
DEBUG=* npx prisma db push

# View pending migrations
npx prisma migrate status

# Reset database (development only)
npx prisma migrate reset
```

## 3. Fastify Request Lifecycle Debugging

### Lifecycle Hooks for Tracing

```typescript
// src/common/interceptors/lifecycle-debug.interceptor.ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler, Logger } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { FastifyRequest, FastifyReply } from 'fastify';

@Injectable()
export class LifecycleDebugInterceptor implements NestInterceptor {
  private readonly logger = new Logger(LifecycleDebugInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest<FastifyRequest>();
    const reply = context.switchToHttp().getResponse<FastifyReply>();
    const { method, url } = request;
    const correlationId = request.headers['x-correlation-id'] || 'unknown';

    this.logger.debug(`[${correlationId}] → ${method} ${url} | Phase: preHandler`, 'Lifecycle');

    return next.handle().pipe(
      tap({
        next: (data) => {
          this.logger.debug(
            `[${correlationId}] ← ${method} ${url} ${reply.statusCode} | Phase: onSend`,
            'Lifecycle'
          );
        },
        error: (error) => {
          this.logger.error(
            `[${correlationId}] ✗ ${method} ${url} ${error.status || 500} | Phase: onError`,
            error.stack,
            'Lifecycle'
          );
        },
      }),
    );
  }
}
```

### Adding Debug Hooks at Bootstrap

```typescript
// src/main.ts (additional setup)
async function bootstrap() {
  // ... existing setup

  const fastifyInstance = app.getHttpAdapter().getInstance();

  if (Config.isDevelopment) {
    fastifyInstance.addHook('onRequest', async (request, reply) => {
      logger.debug(`[onRequest] ${request.method} ${request.url}`, 'FastifyHook');
    });

    fastifyInstance.addHook('preParsing', async (request, reply, payload) => {
      logger.debug(`[preParsing] Content-Type: ${request.headers['content-type']}`, 'FastifyHook');
    });

    fastifyInstance.addHook('preValidation', async (request, reply) => {
      logger.debug(`[preValidation] Body: ${JSON.stringify(request.body).substring(0, 100)}`, 'FastifyHook');
    });

    fastifyInstance.addHook('preHandler', async (request, reply) => {
      logger.debug(`[preHandler] About to execute handler`, 'FastifyHook');
    });

    fastifyInstance.addHook('onSend', async (request, reply, payload) => {
      logger.debug(`[onSend] Status: ${reply.statusCode}`, 'FastifyHook');
    });

    fastifyInstance.addHook('onResponse', async (request, reply) => {
      logger.debug(`[onResponse] Completed in ${reply.getResponseTime()}ms`, 'FastifyHook');
    });

    fastifyInstance.addHook('onError', async (request, reply, error) => {
      logger.error(`[onError] ${error.message}`, error.stack, 'FastifyHook');
    });

    // Debug route not found
    fastifyInstance.setNotFoundHandler((request, reply) => {
      logger.warn(`Route not found: ${request.method} ${request.url}`, 'FastifyNotFound');
      reply.status(404).send({ error: 'Not Found', path: request.url });
    });
  }
}
```

### Content-Type Parsing Issues

```typescript
// Common issue: JSON parsing fails silently
// Fix: Register content type parser with logging
fastifyInstance.addContentTypeParser('application/json', { parseAs: 'string' }, (req, body, done) => {
  try {
    const json = JSON.parse(body as string);
    done(null, json);
  } catch (error) {
    logger.error(`JSON parse error: ${error.message} | Body: ${body}`, 'ContentTypeParser');
    done(error as Error, undefined);
  }
});
```
