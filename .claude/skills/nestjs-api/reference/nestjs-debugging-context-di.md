# NestJS Debugging — Context, DI & Configuration

AsyncLocalStorage context debugging, dependency injection troubleshooting, environment configuration, and a quick-reference troubleshooting table for NestJS 12.x with Fastify and Prisma ORM.

## 4. AsyncLocalStorage & Request Context Debugging

### Common Context Loss Issues

```typescript
// src/common/context/request-context.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { AsyncLocalStorage } from 'async_hooks';

interface RequestContext {
  correlationId: string;
  userId?: string;
  timestamp: number;
}

@Injectable()
export class RequestContextService {
  private readonly als = new AsyncLocalStorage<RequestContext>();
  private readonly logger = new Logger(RequestContextService.name);

  run<T>(context: RequestContext, callback: () => T): T {
    this.logger.debug(`Creating context: ${JSON.stringify(context)}`, 'ALS');
    return this.als.run(context, callback);
  }

  get(): RequestContext | undefined {
    const context = this.als.getStore();
    if (!context) {
      this.logger.warn('Context not found in current async scope', 'ALS');
    }
    return context;
  }

  // Pattern: wrap async operations to preserve context
  wrapAsync<T>(fn: () => Promise<T>): Promise<T> {
    const context = this.get();
    if (!context) {
      this.logger.error('Cannot wrap async operation: no active context', 'ALS');
      throw new Error('No active request context');
    }

    return this.als.run(context, async () => {
      this.logger.debug(`Wrapped async operation with context: ${context.correlationId}`, 'ALS');
      return fn();
    });
  }

  // Fix for setTimeout/setInterval context loss
  wrapTimeout(callback: () => void, delay: number): NodeJS.Timeout {
    const context = this.get();
    if (!context) {
      this.logger.warn('setTimeout called without context', 'ALS');
      return setTimeout(callback, delay);
    }

    return setTimeout(() => {
      this.als.run(context, callback);
    }, delay);
  }
}
```

### Debugging Context in Prisma Queries

Prisma 7 has no `$use` middleware; warn about context-less queries from a query extension. `AsyncLocalStorage`
context survives `await`, so the extension sees the request's context. Verified (strict `tsc`, ESLint, unit test):

```typescript
// src/common/context/request-context.service.ts
import { AsyncLocalStorage } from 'node:async_hooks';
import { Injectable } from '@nestjs/common';

export interface RequestContext {
  readonly correlationId: string;
  readonly userId: string;
  readonly timestamp: number;
}

@Injectable()
export class RequestContextService {
  private readonly storage = new AsyncLocalStorage<RequestContext>();

  run<T>(context: RequestContext, fn: () => Promise<T>): Promise<T> {
    return this.storage.run(context, fn);
  }

  get(): RequestContext | undefined {
    return this.storage.getStore();
  }
}
```

```typescript
// src/core/database/prisma-context.extension.ts
import { Logger } from '@nestjs/common';
import { type PrismaClient } from '../generated/prisma/client.js';
import { type RequestContextService } from './request-context.service.js';

const logger = new Logger('PrismaContext');

/** Wrap the client once and inject the extended client. ALS context survives `await`. */
export function withContextLogging(client: PrismaClient, context: RequestContextService) {
  return client.$extends({
    query: {
      $allModels: {
        $allOperations({ model, operation, args, query }) {
          if (context.get() === undefined) {
            logger.warn({ event: 'prisma_query_without_context', model, operation });
          }
          return query(args);
        },
      },
    },
  });
}
```

### Context Loss in BullMQ Jobs

Context is not propagated into queue workers. Put the correlation id in `job.data` when enqueuing and re-enter the
context in the worker. Use `@nestjs/bullmq` (`WorkerHost`); the legacy `@nestjs/bull` / `bull` packages are superseded.

```typescript
// src/queues/email.processor.ts
import { Processor, WorkerHost } from '@nestjs/bullmq';
import { Inject, Logger } from '@nestjs/common';
import type { Job } from 'bullmq';
import { RequestContextService } from './request-context.service.js';

export interface EmailJob {
  readonly correlationId: string;
  readonly userId: string;
  readonly templateId: string;
  readonly to: string;
}

export interface EmailSender {
  send(message: { templateId: string; to: string }): Promise<void>;
}
export const EMAIL_SENDER = Symbol('EMAIL_SENDER');

@Processor('email')
export class EmailProcessor extends WorkerHost {
  private readonly logger = new Logger(EmailProcessor.name);

  constructor(
    private readonly contextService: RequestContextService,
    @Inject(EMAIL_SENDER) private readonly sender: EmailSender,
  ) {
    super();
  }

  /** Errors propagate: BullMQ records the failure and retries per the job's attempts/backoff. */
  async process(job: Job<EmailJob>): Promise<void> {
    const { correlationId, userId, templateId, to } = job.data;
    await this.contextService.run({ correlationId, userId, timestamp: Date.now() }, async () => {
      this.logger.log({ event: 'email_job_started', jobId: job.id, correlationId });
      await this.sender.send({ templateId, to });
    });
  }
}
```

```typescript
// src/queues/email.processor.spec.ts
import type { Job } from 'bullmq';
import { describe, expect, it, vi } from 'vitest';
import { EmailProcessor, type EmailJob } from './email.processor.js';
import { RequestContextService } from './request-context.service.js';

describe('EmailProcessor', () => {
  it('runs the send inside the job’s correlation context and propagates failures', async () => {
    const context = new RequestContextService();
    const seen: Array<string | undefined> = [];
    const sender = { send: vi.fn(() => { seen.push(context.get()?.correlationId); return Promise.resolve(); }) };
    const processor = new EmailProcessor(context, sender);
    const job = { id: '1', data: { correlationId: 'c-1', userId: 'u', templateId: 't', to: 'a@b.test' } } as Job<EmailJob>;
    await processor.process(job);
    expect(seen).toEqual(['c-1']);

    sender.send.mockRejectedValueOnce(new Error('smtp down'));
    await expect(processor.process(job)).rejects.toThrow('smtp down');
  });
});
```

## 5. Dependency Injection Debugging

### Common DI Issues and Fixes

```typescript
// Issue: "Cannot resolve dependency" error
// Symptom: Nest can't find a provider

// BAD: Service not in module providers
@Module({
  controllers: [UsersController],
  // Missing: UsersService in providers array
})
export class UsersModule {}

// GOOD: Service registered in module
@Module({
  controllers: [UsersController],
  providers: [UsersService],
  exports: [UsersService], // Export if other modules need it
})
export class UsersModule {}

// Issue: Circular dependency
// Symptom: "A circular dependency has been detected"

// BAD: Direct circular reference
@Injectable()
export class UserService {
  constructor(private readonly postService: PostService) {}
}

@Injectable()
export class PostService {
  constructor(private readonly userService: UserService) {} // Circular!
}

// GOOD: Use forwardRef
@Injectable()
export class UserService {
  constructor(@Inject(forwardRef(() => PostService)) private readonly postService: PostService) {}
}

@Injectable()
export class PostService {
  constructor(@Inject(forwardRef(() => UserService)) private readonly userService: UserService) {}
}

// Issue: Optional dependency
// Symptom: App crashes when optional service is missing

// BAD: Required dependency that might not exist
@Injectable()
export class NotificationService {
  constructor(private readonly smsProvider: SmsProvider) {} // Crashes if SMS not configured
}

// GOOD: Use @Optional() decorator
// NestJS 12: @Optional() is no longer inherited when a subclass REDECLARES its constructor
// (UnknownDependenciesException at bootstrap). Re-declare @Optional() on the subclass parameter.
// 12.1+ restores inheritance only when the subclass has no constructor of its own.
@Injectable()
export class NotificationService {
  constructor(@Optional() private readonly smsProvider?: SmsProvider) {}

  private readonly logger = new Logger(NotificationService.name);

  async send(message: string): Promise<{ sent: boolean }> {
    if (this.smsProvider === undefined) {
      // Visible, not silent: callers learn nothing was sent and can surface it.
      this.logger.warn({ event: 'sms_not_configured' });
      return { sent: false };
    }
    await this.smsProvider.send(message);
    return { sent: true };
  }
}

// Issue: Module import ordering
// Symptom: Provider from Module A not available in Module B

// BAD: Importing module that doesn't export the provider
@Module({
  imports: [DatabaseModule], // DatabaseModule doesn't export PrismaService
  providers: [UserService], // UserService needs PrismaService - ERROR!
})
export class UserModule {}

// GOOD: Ensure DatabaseModule exports PrismaService
@Module({
  providers: [PrismaService],
  exports: [PrismaService], // Now available to importing modules
})
export class DatabaseModule {}
```

## 6. Environment & Configuration Debugging

### Fail-Fast Static Configuration

```typescript
// src/config/static-config.ts
import { Logger } from '@nestjs/common';
import * as dotenv from 'dotenv';

dotenv.config();

const logger = new Logger('StaticConfig');

function getEnv(key: string, defaultValue?: string): string {
  const value = process.env[key];
  if (!value && defaultValue === undefined) {
    logger.error(`Missing required environment variable: ${key}`);
    throw new Error(`Missing required environment variable: ${key}`);
  }
  const result = value || defaultValue!;
  logger.debug(`Loaded ${key}=${result.includes('PASSWORD') ? '***' : result}`);
  return result;
}

export const Config = {
  nodeEnv: getEnv('NODE_ENV', 'development'),
  port: parseInt(getEnv('PORT', '3000'), 10),
  databaseUrl: getEnv('DATABASE_URL'),
  jwtSecret: getEnv('JWT_SECRET'),
  isDevelopment: getEnv('NODE_ENV', 'development') === 'development',
  isProduction: getEnv('NODE_ENV') === 'production',
} as const;

logger.log(`Configuration loaded for environment: ${Config.nodeEnv}`);
```

### Debugging .env File Loading

```bash
# Check which variables are SET — print names and presence only, never values (values are secrets)
node --env-file=.env -e "console.log(Object.keys(process.env).sort().join('\n'))"

# Check one variable is present without echoing it
node --env-file=.env -e "console.log('DATABASE_URL set:', Boolean(process.env.DATABASE_URL))"

# Environment variable precedence (highest to lowest):
# 1. System environment variables (export VAR=value)
# 2. .env.local (not committed to git)
# 3. .env
# 4. Default values in code

# Do NOT dump process.env at startup (it lands in log storage with every secret in it).
# Fail fast instead: validate the environment with a schema and report missing NAMES only
# (validateEnv in nestjs-production-baseline.md §1).
```

## 7. Troubleshooting Table

| Issue | Symptom | Fix |
|-------|---------|-----|
| Route not found | 404 for valid endpoint | Check controller path prefix, ensure module is imported in AppModule |
| Request body is undefined | `req.body` is `{}` | Register `@nestjs/platform-fastify` body parser, ensure `Content-Type: application/json` |
| Validation not working | Invalid data passes through | Register `StandardSchemaValidationPipe` as `APP_PIPE`, and declare `{ schema }` on the parameter (`@Body({ schema })`): a parameter without a schema is not validated |
| `onModuleInit` / shutdown order changed after upgrading to 12 | A provider used another module's resource before it was ready, or after it closed | NestJS 12 calls lifecycle hooks by module hierarchy level; make the dependency explicit (import the module, inject the provider) instead of relying on registration order |
| `ERR_MODULE_NOT_FOUND` / TS2307 on a relative import | ESM project cannot resolve `./x` | Relative imports need the `.js` extension under `nodenext` (`./orders.service.js`) |
| Circular dependency | Module initialization fails | Use `forwardRef(() => Module)` in imports and `@Inject(forwardRef(() => Service))` in constructor |
| Prisma "Connection pool timeout" | Queries hang indefinitely | Increase `connection_limit` in `DATABASE_URL`, check for unclosed transactions, ensure `$disconnect()` in tests |
| Context lost in async operations | `contextService.get()` returns `undefined` | Use `contextService.wrapAsync()` or manually propagate context with `als.run()` |
| Config value is undefined | `Config.someValue` is `undefined` | Check the variable is set in the environment (shell, `node --env-file=.env`, CI, container) and named in the `validationSchema`; `ConfigModule` validates at import time |
| Fastify validation error | `FST_ERR_VALIDATION` in logs | Check route schema matches DTO, ensure JSON schema plugin installed, validate request body manually |
| Middleware not executing | Custom middleware skipped | Ensure middleware applied globally or to specific routes, check execution order |
| JWT authentication fails | 401 Unauthorized for valid token | Check JWT secret matches, verify token not expired, ensure AuthGuard applied correctly |
| Prisma migration fails | `Migration failed` error | Check schema syntax, ensure database accessible, rollback failed migration, check for conflicting migrations |
| BullMQ job fails silently | Job completes but no effect | Check the processor extends `WorkerHost` with `@Processor(name)`, the queue is registered (`BullModule.registerQueue`), and log in `@OnWorkerEvent('failed')`. BullMQ 6: `ioredis` must be a direct dependency or the queue fails at runtime |
