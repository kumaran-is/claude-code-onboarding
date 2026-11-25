# NestJS Production Baseline (runtime-verified)

A small orders API built in a disposable app and verified end-to-end against real PostgreSQL 18 and Redis 8. Every
block below is the file that ran: compiled with strict `tsc` (specs included), linted with `oxlint --type-aware`,
built with `nest build`, exercised by the tests listed at the end and shipped as a non-root Docker image. Use it as the
reference implementation; the other reference files add depth.

**Verified stack (2026-11-24, `npm view`, Node 26.13.1):** NestJS 12.6.0 (`@nestjs/common|core|platform-fastify|testing|websockets|platform-socket.io`),
Fastify 5.12.8, `@nestjs/swagger` 12.1.2, `@nestjs/config` 12.1.1, `@nestjs/terminus` 12.2.0, `@nestjs/throttler` 6.8.0,
`@nestjs/bullmq` 12.0.2 + `bullmq` 6.7.10 + `ioredis` 6.1.0, Zod 4.6.7, `jose` 6.2.18, Prisma 7.10.1 (`prisma`, `@prisma/client`,
`@prisma/adapter-pg`), OpenTelemetry `sdk-node` 0.301.2 + `sdk-trace` 3.1.1, TypeScript 6.0.3, Vitest 5.1.1, oxlint 1.95.0.
Full pins: `nestjs-config-npm-ts.md`.

## What is proven, and how

| Concern | Rule | Proof (test → planted-bug control) |
|---|---|---|
| Authentication | Global `APP_GUARD`; routes are protected unless `@Public()` | no token, expired, untrusted key, wrong `aud` → 401; removing the `audience` check failed 1 unit + 1 e2e test |
| JWT verification | `jose.jwtVerify` with pinned `algorithms`, `issuer`, `audience`, `requiredClaims`; empty issuer/audience refuses to construct | unit suite (4 tests) |
| Authorization | Coarse role check in the guard (403); per-resource check in the service | missing role → 403; disabling the role check failed e2e |
| Tenant scoping | `tenantId` comes only from the verified token; every repository method takes it | tenant B reading A's order → 404 with `errorCode`; removing the tenant filter failed 2 tests |
| Request validation | Global `StandardSchemaValidationPipe`; `@Body({ schema })` with `z.strictObject` | invalid body → 400 with field paths, no input echo, no stack; smuggled `tenantId` → 400; `strictObject` → `object` failed 2 tests |
| Body size | Fastify `bodyLimit` | 4 KB body over a 2 KB limit → 413 |
| Response serialization | Global `StandardSchemaSerializerInterceptor` + `@SerializeOptions({ schema })`; `z.object` strips undeclared fields | `passwordHash` never in `/users/me` although the handler returns the DB row; dropping the serializer failed e2e; a response that breaks the schema → opaque 500 |
| Rate limiting (Fastify) | `ThrottlerGuard` registered before the auth guard; key = hashed bearer token, else IP | 21st request → 429; another credential has its own bucket |
| WebSocket auth | socket.io middleware (`afterInit` → `server.use`), not `handleConnection` | bad token → `connect_error: unauthorized`; valid token → tenant room |
| OpenAPI from Zod | `@nestjs/swagger` 12 reads `{ schema }` and `@ApiOkResponse({ standardSchema })` | `/docs-json` has `CreateOrder` with exactly `sku`, `quantity` and `additionalProperties: false`; `UserResponse` has no `passwordHash` |
| Health | Terminus 12 `HealthIndicatorService` + `PrismaHealthIndicator`, with timeouts | `/health` → `database` and `redis` up |
| Background jobs | BullMQ 6 queue + `WorkerHost`, `jobId` = order id | the e2e waits for the worker to process the created order |
| Decorator metadata | `emitDecoratorMetadata: true` without an SWC plugin | turning it off failed the e2e suite |
| Fail-fast config | Zod env schema as the `ConfigModule` `validationSchema` (Standard Schema) | invalid `DATABASE_URL` + empty `JWT_AUDIENCE` → bootstrap fails with `Config validation error` naming both fields, never their values |
| Tracing | OpenTelemetry `NodeSDK` loaded with `node --import` before the app | 4 HTTP requests → 4 server spans (`kind: 1`) in the console exporter |
| Image | multi-stage, base pinned by digest (`node:26.13.1-alpine3.23@sha256:<index digest>`), prod deps only, `USER node` | `docker build` exit 0 (log kept); the container run with `/health` 200 as `node` was reported by the verification run without a kept log |

Not re-run on 12.6 and therefore not in this file: an RFC 9457 problem+json exception filter (the default Nest error body
`{ statusCode, message, errorCode }` is what the tests assert; for problem+json see `nestjs-rest-upload-errors.md`) and
Redis-backed throttler storage (`nestjs-rate-limiting.md`).

## 1. Fail-fast configuration

```typescript
// src/config/env.ts
import { z } from 'zod';

/** Fail-fast environment contract, passed to ConfigModule as a Standard Schema. */
export const envSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  DATABASE_URL: z.url({ protocol: /^postgres(ql)?$/ }),
  REDIS_URL: z.url({ protocol: /^rediss?$/ }),
  JWT_ISSUER: z.url(),
  JWT_AUDIENCE: z.string().min(1),
  JWT_JWKS_URL: z.url(),
  THROTTLE_LIMIT: z.coerce.number().int().positive().default(100),
  THROTTLE_TTL_MS: z.coerce.number().int().positive().default(60_000),
  BODY_LIMIT_BYTES: z.coerce.number().int().positive().default(65_536),
});

export type Env = z.infer<typeof envSchema>;
```

`ConfigModule.forRoot({ validationSchema: envSchema })` accepts any Standard Schema in `@nestjs/config` 12 (Joi needs v18+
and moves its options under `validationOptions.libraryOptions`). Read values with `ConfigService<Env, true>` and
`get(key, { infer: true })`: typed, and never `undefined` for a validated key.

## 2. Authentication: token verifier and global guard

```typescript
// src/auth/principal.ts
/** The verified caller. Built only from a verified token, never from the request body. */
export interface Principal {
  readonly subject: string;
  readonly tenantId: string;
  readonly roles: ReadonlySet<string>;
}

export interface AuthenticatedRequest {
  headers: Record<string, string | string[] | undefined>;
  principal?: Principal;
}
```

```typescript
// src/auth/token-verifier.ts
import { Inject, Injectable } from '@nestjs/common';
import { errors, jwtVerify, type JWTVerifyGetKey } from 'jose';
import type { Principal } from './principal.js';

export const JWT_KEY_RESOLVER = Symbol('JWT_KEY_RESOLVER');
export const JWT_VERIFY_OPTIONS = Symbol('JWT_VERIFY_OPTIONS');

export interface JwtVerifyOptions {
  readonly issuer: string;
  readonly audience: string;
}

export class InvalidTokenError extends Error {
  constructor(readonly reason: string) {
    super(`invalid token: ${reason}`);
    this.name = 'InvalidTokenError';
  }
}

/** jose against the issuer's JWKS: pinned algorithms, issuer, audience and required claims. */
@Injectable()
export class TokenVerifier {
  constructor(
    @Inject(JWT_KEY_RESOLVER) private readonly keys: JWTVerifyGetKey,
    @Inject(JWT_VERIFY_OPTIONS) private readonly options: JwtVerifyOptions,
  ) {
    if (options.issuer.trim() === '' || options.audience.trim() === '') {
      throw new Error('TokenVerifier requires a non-empty issuer and audience');
    }
  }

  async verify(token: string): Promise<Principal> {
    try {
      const { payload } = await jwtVerify(token, this.keys, {
        issuer: this.options.issuer,
        audience: this.options.audience,
        algorithms: ['RS256', 'ES256'],
        clockTolerance: 5,
        requiredClaims: ['sub', 'exp', 'tenant_id'],
      });
      const tenantId = payload['tenant_id'];
      const roles = payload['roles'];
      if (typeof payload.sub !== 'string' || typeof tenantId !== 'string' || tenantId === '') {
        throw new InvalidTokenError('claims');
      }
      return {
        subject: payload.sub,
        tenantId,
        roles: new Set(Array.isArray(roles) ? roles.filter((r): r is string => typeof r === 'string') : []),
      };
    } catch (error: unknown) {
      if (error instanceof InvalidTokenError) throw error;
      if (error instanceof errors.JOSEError) throw new InvalidTokenError(error.code);
      throw error; // JWKS outage is not "invalid token": surface it as 5xx
    }
  }
}
```

```typescript
// src/auth/auth.decorators.ts
import { createParamDecorator, type ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { AuthenticatedRequest, Principal } from './principal.js';

/** Opt a route OUT of the global auth guard. Authentication is the default. */
export const Public = Reflector.createDecorator<boolean>({ transform: () => true });

/** Roles every caller of the route must hold. */
export const Roles = Reflector.createDecorator<string[]>();

export const CurrentPrincipal = createParamDecorator((_data: unknown, ctx: ExecutionContext): Principal => {
  const request = ctx.switchToHttp().getRequest<AuthenticatedRequest>();
  if (request.principal === undefined) {
    // Reaching a handler without a principal means a route was wired without the guard.
    throw new UnauthorizedException();
  }
  return request.principal;
});
```

```typescript
// src/auth/jwt-auth.guard.ts
import {
  type CanActivate,
  type ExecutionContext,
  ForbiddenException,
  Injectable,
  Logger,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Public, Roles } from './auth.decorators.js';
import type { AuthenticatedRequest } from './principal.js';
import { InvalidTokenError, TokenVerifier } from './token-verifier.js';

/** Global (APP_GUARD) authentication + coarse role check. Per-resource checks live in services. */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  private readonly logger = new Logger(JwtAuthGuard.name);

  constructor(
    private readonly reflector: Reflector,
    private readonly verifier: TokenVerifier,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    if (context.getType() !== 'http') return true; // WS auth happens in the gateway middleware
    const targets = [context.getHandler(), context.getClass()];
    if (this.reflector.getAllAndOverride(Public, targets) === true) return true;

    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    const header = request.headers['authorization'];
    const token = typeof header === 'string' && header.startsWith('Bearer ') ? header.slice(7).trim() : '';
    if (token === '') throw new UnauthorizedException();

    try {
      request.principal = await this.verifier.verify(token);
    } catch (error: unknown) {
      if (error instanceof InvalidTokenError) {
        this.logger.warn('auth rejected', { reason: error.reason }); // never log the token
        throw new UnauthorizedException();
      }
      throw error;
    }

    const required = this.reflector.getAllAndOverride(Roles, targets) ?? [];
    if (!required.every((role) => request.principal?.roles.has(role) === true)) {
      throw new ForbiddenException();
    }
    return true;
  }
}
```

`Reflector.createDecorator()` (what the v12 `decorator` schematic generates) gives a typed key: `getAllAndOverride(Roles, targets)`
returns `string[] | undefined` with no string metadata key to mistype.

## 3. Tenant-scoped feature: schemas, repository, service, controller

```typescript
// src/orders/orders.schemas.ts
import { z } from 'zod';

/** Request: strictObject rejects unknown keys (a smuggled tenantId is a 400, not silently dropped). */
export const CreateOrderSchema = z
  .strictObject({
    sku: z.string().regex(/^[A-Z0-9-]{3,32}$/, 'must be 3-32 chars of A-Z, 0-9 or -'),
    quantity: z.int().min(1).max(1000),
  })
  .meta({ id: 'CreateOrder' });
export type CreateOrder = z.infer<typeof CreateOrderSchema>;

/** Response: z.object strips unknown keys, so tenantId never leaves the service. */
export const OrderResponseSchema = z
  .object({
    id: z.uuid(),
    sku: z.string(),
    quantity: z.int(),
    createdAt: z.iso.datetime(),
  })
  .meta({ id: 'OrderResponse' });
export type OrderResponse = z.infer<typeof OrderResponseSchema>;

export const OrderIdSchema = z.uuid();
```

```typescript
// src/orders/orders.repository.ts
import { Injectable } from '@nestjs/common';
import { PrismaService } from '../database/prisma.service.js';
import type { Order } from '../generated/prisma/client.js';
import type { CreateOrder } from './orders.schemas.js';

/** Every method takes tenantId: a query without it cannot be written by accident. */
@Injectable()
export class OrdersRepository {
  constructor(private readonly prisma: PrismaService) {}

  create(tenantId: string, input: CreateOrder): Promise<Order> {
    return this.prisma.client.order.create({ data: { tenantId, ...input } });
  }

  findById(tenantId: string, id: string): Promise<Order | null> {
    return this.prisma.client.order.findFirst({ where: { id, tenantId } });
  }

  list(tenantId: string, take: number): Promise<Order[]> {
    return this.prisma.client.order.findMany({
      where: { tenantId },
      orderBy: { createdAt: 'desc' },
      take: Math.min(take, 100),
    });
  }
}
```

```typescript
// src/orders/orders.service.ts
import { InjectQueue } from '@nestjs/bullmq';
import { Injectable, NotFoundException } from '@nestjs/common';
import type { Queue } from 'bullmq';
import type { Principal } from '../auth/principal.js';
import type { Order } from '../generated/prisma/client.js';
import { ORDER_EVENTS_QUEUE, type OrderCreatedJob } from '../jobs/order-events.processor.js';
import { OrdersGateway } from '../realtime/orders.gateway.js';
import { OrdersRepository } from './orders.repository.js';
import type { CreateOrder, OrderResponse } from './orders.schemas.js';

@Injectable()
export class OrdersService {
  constructor(
    private readonly orders: OrdersRepository,
    @InjectQueue(ORDER_EVENTS_QUEUE) private readonly events: Queue<OrderCreatedJob>,
    private readonly gateway: OrdersGateway,
  ) {}

  async create(principal: Principal, input: CreateOrder): Promise<OrderResponse> {
    const order = await this.orders.create(principal.tenantId, input);
    // jobId = orderId: a retried request cannot enqueue the event twice.
    await this.events.add('order-created', { tenantId: order.tenantId, orderId: order.id }, { jobId: order.id });
    this.gateway.orderCreated(order.tenantId, order.id);
    return toResponse(order);
  }

  async list(principal: Principal): Promise<OrderResponse[]> {
    return (await this.orders.list(principal.tenantId, 50)).map(toResponse);
  }

  /** Another tenant's order is indistinguishable from a missing one: 404, no existence oracle. */
  async get(principal: Principal, id: string): Promise<OrderResponse> {
    const order = await this.orders.findById(principal.tenantId, id);
    if (order === null) throw new NotFoundException('Order not found', { errorCode: 'ORDER_NOT_FOUND' });
    return toResponse(order);
  }
}

/** Dates become ISO strings here; the response schema then strips every field it does not declare. */
function toResponse(order: Order): OrderResponse & { tenantId: string } {
  return { ...order, createdAt: order.createdAt.toISOString() };
}
```

```typescript
// src/orders/orders.controller.ts
import { Body, Controller, Get, HttpCode, HttpStatus, Param, Post, SerializeOptions } from '@nestjs/common';
import { ApiBearerAuth, ApiCreatedResponse, ApiOkResponse, ApiTags } from '@nestjs/swagger';
import { z } from 'zod';
import { CurrentPrincipal, Roles } from '../auth/auth.decorators.js';
import type { Principal } from '../auth/principal.js';
import {
  type CreateOrder,
  CreateOrderSchema,
  OrderIdSchema,
  type OrderResponse,
  OrderResponseSchema,
} from './orders.schemas.js';
import { OrdersService } from './orders.service.js';

const OrderListSchema = z.array(OrderResponseSchema);

@ApiTags('orders')
@ApiBearerAuth()
@Controller({ path: 'orders', version: '1' })
@SerializeOptions({ schema: OrderResponseSchema })
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @Roles(['orders:write'])
  @ApiCreatedResponse({ standardSchema: OrderResponseSchema })
  create(
    @CurrentPrincipal() principal: Principal,
    @Body({ schema: CreateOrderSchema }) body: CreateOrder,
  ): Promise<OrderResponse> {
    return this.orders.create(principal, body);
  }

  @Get()
  @ApiOkResponse({ standardSchema: OrderListSchema })
  list(@CurrentPrincipal() principal: Principal): Promise<OrderResponse[]> {
    return this.orders.list(principal);
  }

  @Get(':id')
  @ApiOkResponse({ standardSchema: OrderResponseSchema })
  get(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: OrderIdSchema }) id: string,
  ): Promise<OrderResponse> {
    return this.orders.get(principal, id);
  }
}
```

```typescript
// src/users/users.controller.ts
import { Controller, Get, NotFoundException, SerializeOptions } from '@nestjs/common';
import { ApiBearerAuth, ApiOkResponse, ApiTags } from '@nestjs/swagger';
import { z } from 'zod';
import { CurrentPrincipal } from '../auth/auth.decorators.js';
import type { Principal } from '../auth/principal.js';
import { PrismaService } from '../database/prisma.service.js';
import type { User } from '../generated/prisma/client.js';

/** Declares only public fields: the serializer drops passwordHash (and anything else not listed). */
export const UserResponseSchema = z
  .object({ id: z.uuid(), tenantId: z.uuid(), email: z.email() })
  .meta({ id: 'UserResponse' });

@ApiTags('users')
@ApiBearerAuth()
@Controller({ path: 'users', version: '1' })
export class UsersController {
  constructor(private readonly prisma: PrismaService) {}

  /** Returns the full DB row on purpose: the response schema is the only thing that strips passwordHash. */
  @Get('me')
  @SerializeOptions({ schema: UserResponseSchema })
  @ApiOkResponse({ standardSchema: UserResponseSchema })
  async me(@CurrentPrincipal() principal: Principal): Promise<User> {
    const user = await this.prisma.client.user.findFirst({
      where: { id: principal.subject, tenantId: principal.tenantId },
    });
    if (user === null) throw new NotFoundException('User not found', { errorCode: 'USER_NOT_FOUND' });
    return user;
  }
}
```

- Request schemas use `z.strictObject` (unknown keys → 400). Response schemas use `z.object` (unknown keys stripped). `.meta({ id })`
  names the OpenAPI component.
- `@Body({ schema })`, `@Param(name, { schema })` and `@Query({ schema })` are validated by the global pipe; a parameter without
  `schema` is not validated, so every external input declares one.
- `new NotFoundException(message, { errorCode })` (v12) adds a stable machine-readable code to the error body.

## 4. Bootstrap, versioning, Swagger, shutdown

```typescript
// src/main.ts
import 'reflect-metadata';
import { ConsoleLogger, Logger } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from './app.module.js';
import { envSchema, type Env } from './config/env.js';
import { configureApp } from './configure-app.js';

const logger = new ConsoleLogger({ json: true, redact: ['authorization', 'password', 'passwordHash'] });

try {
  // The adapter is built before the container exists. Wait until ConfigModule has loaded .env into process.env
  // (importing AppModule started it), then read the same schema, defaults included, never a second literal.
  await ConfigModule.envVariablesLoaded;
  const bootEnv = envSchema.parse(process.env);
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    // bodyLimit caps request size (413 above it); trustProxy only behind a known proxy.
    new FastifyAdapter({ bodyLimit: bootEnv.BODY_LIMIT_BYTES, trustProxy: false }),
    // v12: fail bootstrap on identical routes, warn on shadowing ones (both default to 'off').
    { logger, routeConflictPolicy: { duplicate: 'error', shadow: 'warn' } },
  );
  const config = app.get<ConfigService<Env, true>>(ConfigService);
  await configureApp(app, { swagger: config.get('NODE_ENV', { infer: true }) !== 'production' });
  // 0.0.0.0: Fastify listens on 127.0.0.1 by default, unreachable from outside a container.
  await app.listen({ port: config.get('PORT', { infer: true }), host: '0.0.0.0' });
} catch (error: unknown) {
  new Logger('Bootstrap').error('startup failed', error instanceof Error ? error.stack : String(error));
  // exitCode alone is not enough: Redis/BullMQ/pg handles opened during init keep the loop alive.
  process.exit(1);
}
```

```typescript
// src/configure-app.ts
import helmet from '@fastify/helmet';
import { VersioningType } from '@nestjs/common';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

/** Shared by main.ts and the e2e tests, so tests exercise the production pipeline. */
export async function configureApp(app: NestFastifyApplication, options: { swagger: boolean }): Promise<void> {
  await app.register(helmet);
  app.setGlobalPrefix('api', { exclude: ['health'] });
  app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1' });
  app.enableShutdownHooks();
  if (options.swagger) {
    const document = SwaggerModule.createDocument(
      app,
      new DocumentBuilder().setTitle('Orders API').setVersion('1').addBearerAuth().build(),
    );
    SwaggerModule.setup('docs', app, document);
  }
}
```

- `NestFactory.create(AppModule, new FastifyAdapter(...))` infers `NestFastifyApplication` from the adapter in 12.6; the explicit
  type argument is kept for readability.
- `routeConflictPolicy` and `ConsoleLogger({ json: true })` are v12 options (`routeResolutionStrategy: 'specificity'` is the other
  opt-in, not exercised here: read the v12.0.0 release notes before enabling it). Structured log params are on by default in v12
  (`structuredParams: false` restores the v11 output).
- `app.enableShutdownHooks()` only — no extra `process.on('SIGTERM')` in `main.ts` (hooks would run twice). v12 runs lifecycle
  hooks by module hierarchy level, so do not rely on the v11 registration order between sibling modules.
- Swagger UI on Fastify needs `@fastify/static`; it is disabled in production by the `swagger` option.

## 5. Module wiring: config, throttling, validation, serialization, guards

```typescript
// src/app.module.ts
import { BullModule } from '@nestjs/bullmq';
import { Inject, Module, type OnApplicationShutdown, StandardSchemaSerializerInterceptor } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { APP_GUARD, APP_INTERCEPTOR, APP_PIPE, Reflector } from '@nestjs/core';
import { StandardSchemaValidationPipe } from '@nestjs/common';
import { TerminusModule } from '@nestjs/terminus';
import { ThrottlerGuard, ThrottlerModule } from '@nestjs/throttler';
import { Redis } from 'ioredis';
import { createRemoteJWKSet } from 'jose';
import { JwtAuthGuard } from './auth/jwt-auth.guard.js';
import { JWT_KEY_RESOLVER, JWT_VERIFY_OPTIONS, TokenVerifier } from './auth/token-verifier.js';
import { throttleTracker } from './common/throttler-tracker.js';
import { type Env, envSchema } from './config/env.js';
import { PrismaService } from './database/prisma.service.js';
import { HEALTH_REDIS, HealthController } from './health/health.controller.js';
import { ORDER_EVENTS_QUEUE, OrderEventsProcessor } from './jobs/order-events.processor.js';
import { OrdersController } from './orders/orders.controller.js';
import { OrdersRepository } from './orders/orders.repository.js';
import { OrdersService } from './orders/orders.service.js';
import { OrdersGateway } from './realtime/orders.gateway.js';
import { UsersController } from './users/users.controller.js';

type Config = ConfigService<Env, true>;

@Module({
  imports: [
    // v12: any Standard Schema (Zod 4 here) validates the environment; failure stops bootstrap.
    ConfigModule.forRoot({ isGlobal: true, cache: true, validationSchema: envSchema }),
    ThrottlerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: Config) => ({
        throttlers: [
          { name: 'default', ttl: config.get('THROTTLE_TTL_MS', { infer: true }), limit: config.get('THROTTLE_LIMIT', { infer: true }) },
        ],
        getTracker: throttleTracker,
        skipIf: (context) => context.getType() !== 'http',
      }),
    }),
    TerminusModule.forRoot({ errorLogStyle: 'json' }),
    BullModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: Config) => ({
        connection: { url: config.get('REDIS_URL', { infer: true }), maxRetriesPerRequest: null },
        defaultJobOptions: {
          attempts: 5,
          backoff: { type: 'exponential', delay: 1_000 },
          removeOnComplete: 1_000,
          removeOnFail: 5_000,
        },
      }),
    }),
    BullModule.registerQueue({ name: ORDER_EVENTS_QUEUE }),
  ],
  controllers: [HealthController, OrdersController, UsersController],
  providers: [
    OrdersService,
    OrdersRepository,
    OrdersGateway,
    OrderEventsProcessor,
    TokenVerifier,
    {
      provide: PrismaService,
      inject: [ConfigService],
      useFactory: (config: Config) => new PrismaService(config.get('DATABASE_URL', { infer: true })),
    },
    {
      provide: HEALTH_REDIS,
      inject: [ConfigService],
      useFactory: (config: Config) =>
        new Redis(config.get('REDIS_URL', { infer: true }), { maxRetriesPerRequest: 1, lazyConnect: true }),
    },
    {
      provide: JWT_KEY_RESOLVER,
      inject: [ConfigService],
      useFactory: (config: Config) => createRemoteJWKSet(new URL(config.get('JWT_JWKS_URL', { infer: true }))),
    },
    {
      provide: JWT_VERIFY_OPTIONS,
      inject: [ConfigService],
      useFactory: (config: Config) => ({
        issuer: config.get('JWT_ISSUER', { infer: true }),
        audience: config.get('JWT_AUDIENCE', { infer: true }),
      }),
    },
    // Global validation: every parameter decorated with { schema } is validated (400 on failure).
    { provide: APP_PIPE, useValue: new StandardSchemaValidationPipe() },
    // Global serialization: a handler's @SerializeOptions({ schema }) shapes (and strips) the response.
    {
      provide: APP_INTERCEPTOR,
      inject: [Reflector],
      useFactory: (reflector: Reflector) => new StandardSchemaSerializerInterceptor(reflector),
    },
    // Guard order = registration order: throttle first (cheap), then auth.
    { provide: APP_GUARD, useClass: ThrottlerGuard },
    { provide: APP_GUARD, useClass: JwtAuthGuard },
  ],
})
export class AppModule implements OnApplicationShutdown {
  constructor(@Inject(HEALTH_REDIS) private readonly redis: Redis) {}

  async onApplicationShutdown(): Promise<void> {
    if (this.redis.status !== 'end' && this.redis.status !== 'wait') await this.redis.quit();
  }
}
```

```typescript
// src/common/throttler-tracker.ts
import { createHash } from 'node:crypto';

/**
 * Throttle key: a fingerprint of the bearer credential when present, else the client IP.
 * The throttler runs BEFORE auth, so the raw token is hashed, never stored as the key.
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

Guard order is registration order: `ThrottlerGuard` first (cheap, rejects floods before any JWKS work), then `JwtAuthGuard`.

## 6. WebSocket gateway authentication

```typescript
// src/realtime/orders.gateway.ts
import { Logger } from '@nestjs/common';
import {
  type OnGatewayInit,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import type { Server, Socket } from 'socket.io';
import type { Principal } from '../auth/principal.js';
import { InvalidTokenError, TokenVerifier } from '../auth/token-verifier.js';

interface SocketData {
  principal?: Principal;
}

/**
 * Authenticate in socket.io middleware (afterInit -> server.use), not in handleConnection:
 * an async handleConnection does not hold back the client's messages.
 * Rooms are per tenant, derived from the verified token.
 */
@WebSocketGateway({ namespace: 'orders', cors: { origin: false } })
export class OrdersGateway implements OnGatewayInit<Server> {
  private readonly logger = new Logger(OrdersGateway.name);
  @WebSocketServer() private readonly server: Server | undefined;

  constructor(private readonly verifier: TokenVerifier) {}

  afterInit(server: Server): void {
    server.use((socket: Socket, next: (err?: Error) => void) => {
      const auth = socket.handshake.auth as Record<string, unknown>;
      const token = typeof auth['token'] === 'string' ? auth['token'] : '';
      this.verifier
        .verify(token)
        .then(async (principal) => {
          (socket.data as SocketData).principal = principal;
          await socket.join(`tenant:${principal.tenantId}`);
          next();
        })
        .catch((error: unknown) => {
          if (!(error instanceof InvalidTokenError)) {
            this.logger.error('ws auth error', error instanceof Error ? error.stack : String(error));
          }
          next(new Error('unauthorized'));
        });
    });
  }

  orderCreated(tenantId: string, orderId: string): void {
    this.server?.to(`tenant:${tenantId}`).emit('order.created', { orderId });
  }

  @SubscribeMessage('whoami')
  whoami(client: Socket): { tenantId: string } {
    const principal = (client.data as SocketData).principal;
    if (principal === undefined) throw new Error('unauthenticated socket reached a handler');
    return { tenantId: principal.tenantId };
  }
}
```

An async `handleConnection()` does not hold back the client's messages: connection-level rejection belongs in `server.use()`
(socket.io) or `verifyClient` (`WsAdapter`). v12.6 adds `gracefulShutdown` / `gracePeriod` (default 10 s) to `WsAdapter` and
request-scoped gateways; neither is needed for this gateway.

- Message payloads are validated like HTTP bodies: `@MessageBody({ schema })` with `StandardSchemaValidationPipe` bound by
  `@UsePipes` with `exceptionFactory: (issues) => new WsException(...)`. A global pipe also runs for gateways, but its
  default `BadRequestException` reaches the client only as `Internal server error`. Verified 3/3 (valid → `pong`, too-short
  text and a smuggled key on a `z.strictObject` → `exception`); removing `{ schema }` failed 2 tests.
- 12.5 limit defaults: socket.io `maxConcurrentMessages` 1000 per client and `maxWaitingMessages` 10000 per event
  (`new IoAdapter(app, { maxConcurrentMessages, maxWaitingMessages })`, `Infinity` lifts them); `WsAdapter` `maxPayload`
  1 MiB (was 100 MiB in `ws`; close code 1009). `handleDisconnect(client, reason?)` receives the disconnect reason.
  Startup now fails on a guard, interceptor or pipe that cannot run and on an invalid `forRoutes()` / `exclude()` entry.

## 7. Prisma 7: client, health, transactions

```typescript
// src/database/prisma.service.ts
import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../generated/prisma/client.js';

/** Composition, not inheritance: expose the client, own its lifecycle. */
@Injectable()
export class PrismaService implements OnModuleDestroy {
  readonly client: PrismaClient;

  constructor(databaseUrl: string) {
    this.client = new PrismaClient({ adapter: new PrismaPg({ connectionString: databaseUrl, max: 10 }) });
  }

  async onModuleDestroy(): Promise<void> {
    await this.client.$disconnect();
  }
}
```

```typescript
// src/health/health.controller.ts
import { Controller, Get, Inject, VERSION_NEUTRAL } from '@nestjs/common';
import { HealthCheck, HealthCheckService, HealthIndicatorService, PrismaHealthIndicator } from '@nestjs/terminus';
import { SkipThrottle } from '@nestjs/throttler';
import type { Redis } from 'ioredis';
import { Public } from '../auth/auth.decorators.js';
import { PrismaService } from '../database/prisma.service.js';

export const HEALTH_REDIS = Symbol('HEALTH_REDIS');

@Controller({ path: 'health', version: VERSION_NEUTRAL })
@Public()
@SkipThrottle()
export class HealthController {
  constructor(
    private readonly health: HealthCheckService,
    private readonly indicators: HealthIndicatorService,
    private readonly prismaIndicator: PrismaHealthIndicator,
    private readonly prisma: PrismaService,
    @Inject(HEALTH_REDIS) private readonly redis: Redis,
  ) {}

  @Get()
  @HealthCheck()
  check() {
    return this.health.check([
      // Built-in Prisma indicator (runs SELECT 1 through $queryRawUnsafe).
      this.prismaIndicator.pingCheck('database', this.prisma.client).withTimeout(1500),
      // Custom indicator with the v12 HealthIndicatorService API (no HealthIndicator base class).
      this.indicators
        .check('redis')
        .attempt(async () => {
          const pong = await this.redis.ping();
          if (pong !== 'PONG') throw new Error(`unexpected reply ${String(pong)}`);
        })
        .withTimeout(1000),
    ]);
  }
}
```

Terminus 12 removed the legacy `HealthIndicator` base class, `HealthCheckError` and `getStatus()` (each is a TS error against
12.2.0). Custom checks use `HealthIndicatorService.check(key)` with `.attempt()`, `.up()` / `.down()`, and `.withTimeout(ms)`
replaces the deprecated `timeout` option. Schema, `prisma.config.ts`, transactions and P2002 handling: `nestjs-config-prisma7.md`.

Downstream HTTP dependencies use `FetchHealthIndicator.pingCheck(key, url, { verify? })` (global `fetch`, no `@nestjs/axios`;
`HttpHealthIndicator` is deprecated). A 2xx is `up` unless `verify(response)` says otherwise. Verified 3/3 against a local
server: 204 → `up`, 503 → `health.check` rejects with 503, `verify: (r) => r.status === 200` on a 204 → 503.

## 8. Background jobs (BullMQ 6)

```typescript
// src/jobs/order-events.processor.ts
import { OnWorkerEvent, Processor, WorkerHost } from '@nestjs/bullmq';
import { Logger } from '@nestjs/common';
import { type Job, UnrecoverableError } from 'bullmq';

export const ORDER_EVENTS_QUEUE = 'order-events';

export interface OrderCreatedJob {
  readonly tenantId: string;
  readonly orderId: string;
}

/** At-least-once delivery: the handler is idempotent and keyed on orderId (jobId = orderId). */
@Processor(ORDER_EVENTS_QUEUE, { concurrency: 5 })
export class OrderEventsProcessor extends WorkerHost {
  private readonly logger = new Logger(OrderEventsProcessor.name);
  readonly handled = new Set<string>();

  async process(job: Job<OrderCreatedJob>): Promise<{ orderId: string }> {
    const { tenantId, orderId } = job.data;
    if (tenantId === '' || orderId === '') {
      throw new UnrecoverableError('malformed order-created job'); // never succeeds on retry
    }
    this.handled.add(orderId);
    this.logger.log('order-created handled', { jobId: job.id, attempt: job.attemptsMade + 1 });
    return Promise.resolve({ orderId });
  }

  @OnWorkerEvent('failed')
  onFailed(job: Job<OrderCreatedJob> | undefined, error: Error): void {
    this.logger.error('order-created job failed', { jobId: job?.id, error: error.message });
  }
}
```

The queue and worker are registered in `AppModule` (§5): `BullModule.forRootAsync` with `connection: { url, maxRetriesPerRequest: null }`.
`ioredis` must be a direct dependency with bullmq 6. Delivery is at-least-once: idempotent handlers keyed on the business id,
`jobId` set to it, bounded `attempts` with backoff, `UnrecoverableError` for payloads that can never succeed. Workers close on
shutdown when shutdown hooks are enabled.

## 9. Tracing (OpenTelemetry)

```typescript
// src/instrumentation.ts
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { ConsoleSpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace';

/**
 * Loaded with `node --import ./dist/instrumentation.js dist/main.js`, before any app module,
 * so the http module is patched before Fastify requires it. Console exporter here; swap in
 * an OTLP exporter for a real collector.
 */
const sdk = new NodeSDK({
  serviceName: 'orders-api',
  spanProcessors: [new SimpleSpanProcessor({ exporter: new ConsoleSpanExporter() })],
  instrumentations: [new HttpInstrumentation({ ignoreIncomingRequestHook: (req) => req.url === '/health' })],
});
sdk.start();

process.once('SIGTERM', () => {
  sdk.shutdown().catch((error: unknown) => {
    process.stderr.write(`otel shutdown failed: ${String(error)}\n`);
  });
});
```

Started with `node --import ./dist/instrumentation.js dist/main.js` so `http` is patched before Fastify loads. In SDK 2.x/3.x
`new Resource(...)` is type-only and the `spanProcessor` option is gone: use `serviceName` and `spanProcessors: [new XSpanProcessor({ exporter })]`.

## 10. Tests

```typescript
// src/auth/token-verifier.spec.ts
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } from 'jose';
import { beforeAll, describe, expect, it } from 'vitest';
import { InvalidTokenError, TokenVerifier } from './token-verifier.js';

const options = { issuer: 'https://issuer.test', audience: 'orders-api' };

describe('TokenVerifier', () => {
  let verifier: TokenVerifier;
  let privateKey: CryptoKey;

  beforeAll(async () => {
    const pair = await generateKeyPair('ES256');
    privateKey = pair.privateKey;
    const jwk = { ...(await exportJWK(pair.publicKey)), kid: 'k1', alg: 'ES256' };
    verifier = new TokenVerifier(createLocalJWKSet({ keys: [jwk] }), options);
  });

  const sign = (claims: Record<string, unknown>, audience = options.audience) =>
    new SignJWT(claims)
      .setProtectedHeader({ alg: 'ES256', kid: 'k1' })
      .setIssuer(options.issuer)
      .setAudience(audience)
      .setSubject('user-1')
      .setExpirationTime('5m')
      .sign(privateKey);

  it('returns the principal for a valid token', async () => {
    const principal = await verifier.verify(await sign({ tenant_id: 't1', roles: ['orders:write', 7] }));
    expect(principal.tenantId).toBe('t1');
    expect([...principal.roles]).toEqual(['orders:write']);
  });

  it('rejects a token minted for another audience', async () => {
    await expect(verifier.verify(await sign({ tenant_id: 't1' }, 'other-api'))).rejects.toBeInstanceOf(InvalidTokenError);
  });

  it('rejects a token without tenant_id', async () => {
    await expect(verifier.verify(await sign({}))).rejects.toBeInstanceOf(InvalidTokenError);
  });

  it('refuses to construct with an empty audience', () => {
    expect(() => new TokenVerifier(createLocalJWKSet({ keys: [] }), { issuer: 'x', audience: ' ' })).toThrow();
  });
});
```

```typescript
// src/orders/orders.service.spec.ts
import { getQueueToken } from '@nestjs/bullmq';
import { NotFoundException, StandardSchemaSerializerInterceptor, type CallHandler, type ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Test } from '@nestjs/testing';
import { lastValueFrom, of } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Principal } from '../auth/principal.js';
import type { Order } from '../generated/prisma/client.js';
import { ORDER_EVENTS_QUEUE } from '../jobs/order-events.processor.js';
import { OrdersGateway } from '../realtime/orders.gateway.js';
import { OrdersRepository } from './orders.repository.js';
import { OrderResponseSchema } from './orders.schemas.js';
import { OrdersService } from './orders.service.js';

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';
const principal = (tenantId: string): Principal => ({ subject: 'u1', tenantId, roles: new Set(['orders:write']) });

const order: Order = {
  id: '33333333-3333-4333-8333-333333333333',
  tenantId: TENANT_A,
  sku: 'SKU-1',
  quantity: 2,
  createdAt: new Date('2026-11-24T10:00:00.000Z'),
};

describe('OrdersService', () => {
  const repo = { create: vi.fn(), findById: vi.fn(), list: vi.fn() };
  const queue = { add: vi.fn() };
  const gateway = { orderCreated: vi.fn() };
  let service: OrdersService;

  beforeEach(async () => {
    vi.resetAllMocks();
    const moduleRef = await Test.createTestingModule({
      providers: [
        OrdersService,
        { provide: OrdersRepository, useValue: repo },
        { provide: getQueueToken(ORDER_EVENTS_QUEUE), useValue: queue },
        { provide: OrdersGateway, useValue: gateway },
      ],
    }).compile();
    service = moduleRef.get(OrdersService);
  });

  it('creates in the caller tenant, enqueues once keyed on the order id, and maps dates', async () => {
    repo.create.mockResolvedValue(order);
    const result = await service.create(principal(TENANT_A), { sku: 'SKU-1', quantity: 2 });
    expect(repo.create).toHaveBeenCalledWith(TENANT_A, { sku: 'SKU-1', quantity: 2 });
    expect(queue.add).toHaveBeenCalledWith('order-created', { tenantId: TENANT_A, orderId: order.id }, { jobId: order.id });
    expect(gateway.orderCreated).toHaveBeenCalledWith(TENANT_A, order.id);
    expect(result.createdAt).toBe('2026-11-24T10:00:00.000Z');
  });

  it('answers 404 with errorCode when the order is not in the caller tenant', async () => {
    repo.findById.mockResolvedValue(null);
    const error = await service.get(principal(TENANT_B), order.id).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(NotFoundException);
    expect((error as NotFoundException).errorCode).toBe('ORDER_NOT_FOUND');
    expect(repo.findById).toHaveBeenCalledWith(TENANT_B, order.id);
  });

  it('does not enqueue when persistence fails', async () => {
    repo.create.mockRejectedValue(new Error('db down'));
    await expect(service.create(principal(TENANT_A), { sku: 'SKU-1', quantity: 1 })).rejects.toThrow('db down');
    expect(queue.add).not.toHaveBeenCalled();
  });
});

describe('StandardSchemaSerializerInterceptor contract', () => {
  const interceptor = new StandardSchemaSerializerInterceptor(new Reflector(), { schema: OrderResponseSchema });
  const context = {
    getType: () => 'http',
    getHandler: () => function handler() {},
    getClass: () => class Controller {},
  } as unknown as ExecutionContext;
  const respond = (body: unknown): CallHandler => ({ handle: () => of(body) });

  it('strips fields the schema does not declare', async () => {
    const body = await lastValueFrom(
      interceptor.intercept(context, respond({ ...order, createdAt: order.createdAt.toISOString() })),
    );
    expect(body).toEqual({ id: order.id, sku: 'SKU-1', quantity: 2, createdAt: '2026-11-24T10:00:00.000Z' });
    expect(body).not.toHaveProperty('tenantId');
  });

  it('fails loudly when a response breaks the contract', async () => {
    await expect(lastValueFrom(interceptor.intercept(context, respond({ id: 'not-a-uuid', sku: 'x' })))).rejects.toThrow(
      /^Serialization failed/,
    );
  });
});
```

```typescript
// test/app.e2e-spec.ts
import { randomUUID } from 'node:crypto';
import type { AddressInfo } from 'node:net';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { Test } from '@nestjs/testing';
import { createLocalJWKSet, exportJWK, generateKeyPair, type JWK, SignJWT } from 'jose';
import { io } from 'socket.io-client';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../src/app.module.js';
import { JWT_KEY_RESOLVER } from '../src/auth/token-verifier.js';
import { configureApp } from '../src/configure-app.js';
import { PrismaService } from '../src/database/prisma.service.js';
import { OrderEventsProcessor } from '../src/jobs/order-events.processor.js';
import { OrdersService } from '../src/orders/orders.service.js';

const ISSUER = 'https://issuer.test';
const AUDIENCE = 'orders-api';
const TENANT_A = randomUUID();
const TENANT_B = randomUUID();
const USER_A = randomUUID();

interface Keys {
  privateKey: CryptoKey;
  jwk: JWK;
}

async function newKeys(kid: string): Promise<Keys> {
  const pair = await generateKeyPair('ES256');
  return { privateKey: pair.privateKey, jwk: { ...(await exportJWK(pair.publicKey)), kid, alg: 'ES256' } };
}

let trusted: Keys;
let untrusted: Keys;

/** Every token gets a fresh jti, so each one has its own throttle bucket. */
function token(opts: { tenantId?: string; sub?: string; roles?: string[]; aud?: string; exp?: string | number; keys?: Keys } = {}) {
  const keys = opts.keys ?? trusted;
  return new SignJWT({ tenant_id: opts.tenantId ?? TENANT_A, roles: opts.roles ?? ['orders:write'] })
    .setProtectedHeader({ alg: 'ES256', kid: keys.jwk.kid ?? 'k' })
    .setIssuer(ISSUER)
    .setAudience(opts.aud ?? AUDIENCE)
    .setSubject(opts.sub ?? USER_A)
    .setJti(randomUUID())
    .setIssuedAt()
    .setExpirationTime(opts.exp ?? '5m')
    .sign(keys.privateKey);
}

async function createApp(overrides: (b: ReturnType<typeof Test.createTestingModule>) => void = () => {}) {
  const builder = Test.createTestingModule({ imports: [AppModule] })
    .overrideProvider(JWT_KEY_RESOLVER)
    .useValue(createLocalJWKSet({ keys: [trusted.jwk] }));
  overrides(builder);
  const moduleRef = await builder.compile();
  const app = moduleRef.createNestApplication<NestFastifyApplication>(
    new FastifyAdapter({ bodyLimit: Number(process.env['BODY_LIMIT_BYTES']) }),
    { logger: ['error', 'warn'] },
  );
  await configureApp(app, { swagger: true });
  await app.init();
  await app.getHttpAdapter().getInstance().ready();
  return app;
}

describe('Orders API (e2e, Fastify inject, real PostgreSQL + Redis)', () => {
  let app: NestFastifyApplication;
  let orderOfA: string;

  beforeAll(async () => {
    trusted = await newKeys('trusted');
    untrusted = await newKeys('untrusted');
    app = await createApp();
    await app.get(PrismaService).client.user.create({
      data: { id: USER_A, tenantId: TENANT_A, email: `a-${USER_A}@example.test`, passwordHash: '$argon2id$v=19$secret-hash' },
    });
  });

  afterAll(async () => {
    await app.close();
  });

  const post = async (body: unknown, auth?: string) =>
    app.inject({
      method: 'POST',
      url: '/api/v1/orders',
      headers: { 'content-type': 'application/json', ...(auth ? { authorization: `Bearer ${auth}` } : {}) },
      payload: typeof body === 'string' ? body : JSON.stringify(body),
    });

  describe('happy path', () => {
    it('creates an order (201), strips tenantId from the response, and the BullMQ worker processes it', async () => {
      const res = await post({ sku: 'SKU-1', quantity: 2 }, await token());
      expect(res.statusCode).toBe(201);
      const body = res.json<Record<string, unknown>>();
      expect(Object.keys(body).sort()).toEqual(['createdAt', 'id', 'quantity', 'sku']);
      orderOfA = String(body['id']);

      const processor = app.get(OrderEventsProcessor);
      const deadline = Date.now() + 10_000;
      while (!processor.handled.has(orderOfA) && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 100));
      }
      expect(processor.handled.has(orderOfA)).toBe(true);
    });

    it('lists and gets the order in the same tenant', async () => {
      const t = await token();
      const list = await app.inject({ method: 'GET', url: '/api/v1/orders', headers: { authorization: `Bearer ${t}` } });
      expect(list.statusCode).toBe(200);
      expect(list.json<{ id: string }[]>().map((o) => o.id)).toContain(orderOfA);
      const one = await app.inject({ method: 'GET', url: `/api/v1/orders/${orderOfA}`, headers: { authorization: `Bearer ${t}` } });
      expect(one.statusCode).toBe(200);
    });

    it('health reports database and redis up', async () => {
      const res = await app.inject({ method: 'GET', url: '/health' });
      expect(res.statusCode).toBe(200);
      const body = res.json<{ status: string; details: Record<string, { status: string }> }>();
      expect(body.status).toBe('ok');
      expect(body.details['database']?.status).toBe('up');
      expect(body.details['redis']?.status).toBe('up');
    });

    it('OpenAPI documents the Zod request and response schemas', async () => {
      const res = await app.inject({ method: 'GET', url: '/docs-json' });
      const doc = res.json<{ paths: Record<string, Record<string, { requestBody?: unknown }>>; components: { schemas: Record<string, { properties: Record<string, unknown>; additionalProperties?: boolean }> } }>();
      expect(doc.paths['/api/v1/orders']?.['post']?.requestBody).toMatchObject({
        content: { 'application/json': { schema: { $ref: '#/components/schemas/CreateOrder' } } },
      });
      expect(Object.keys(doc.components.schemas['CreateOrder']?.properties ?? {}).sort()).toEqual(['quantity', 'sku']);
      expect(doc.components.schemas['CreateOrder']?.additionalProperties).toBe(false);
      expect(Object.keys(doc.components.schemas['UserResponse']?.properties ?? {})).not.toContain('passwordHash');
    });
  });

  describe('authentication (401)', () => {
    const get = (auth?: string) =>
      app.inject({ method: 'GET', url: '/api/v1/orders', headers: auth ? { authorization: `Bearer ${auth}` } : {} });

    it('missing token', async () => {
      expect((await get()).statusCode).toBe(401);
    });
    it('expired token', async () => {
      expect((await get(await token({ exp: Math.floor(Date.now() / 1000) - 60 }))).statusCode).toBe(401);
    });
    it('wrong signature (untrusted key)', async () => {
      expect((await get(await token({ keys: untrusted }))).statusCode).toBe(401);
    });
    it('wrong audience', async () => {
      expect((await get(await token({ aud: 'billing-api' }))).statusCode).toBe(401);
    });
  });

  describe('authorization and tenancy', () => {
    it('wrong role -> 403', async () => {
      expect((await post({ sku: 'SKU-1', quantity: 1 }, await token({ roles: ['orders:read'] }))).statusCode).toBe(403);
    });

    it("other tenant's order -> 404 with errorCode, not 403", async () => {
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/orders/${orderOfA}`,
        headers: { authorization: `Bearer ${await token({ tenantId: TENANT_B })}` },
      });
      expect(res.statusCode).toBe(404);
      expect(res.json()).toMatchObject({ statusCode: 404, errorCode: 'ORDER_NOT_FOUND' });
    });

    it("other tenant's list does not contain the order", async () => {
      const res = await app.inject({ method: 'GET', url: '/api/v1/orders', headers: { authorization: `Bearer ${await token({ tenantId: TENANT_B })}` } });
      expect(res.json<{ id: string }[]>().map((o) => o.id)).not.toContain(orderOfA);
    });
  });

  describe('validation (Standard Schema / Zod)', () => {
    it('invalid body -> 400 with field errors, no stack, no echo of the input', async () => {
      const res = await post({ sku: '<script>alert(1)</script>', quantity: 0 }, await token());
      expect(res.statusCode).toBe(400);
      const body = res.json<{ message: string[] }>();
      expect(body.message).toEqual(expect.arrayContaining([expect.stringMatching(/^sku: /), expect.stringMatching(/^quantity: /)]));
      expect(res.body).not.toContain('<script>');
      expect(res.body).not.toMatch(/stack|at \w+ \(/);
    });

    it('unknown field (smuggled tenantId) is REJECTED with 400, not stripped', async () => {
      const res = await post({ sku: 'SKU-1', quantity: 1, tenantId: TENANT_B }, await token());
      expect(res.statusCode).toBe(400);
      expect(res.json<{ message: string[] }>().message.join(' ')).toMatch(/tenantId/);
    });

    it('invalid path id -> 400', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/v1/orders/123', headers: { authorization: `Bearer ${await token()}` } });
      expect(res.statusCode).toBe(400);
    });

    it('oversized body -> 413', async () => {
      const res = await post({ sku: 'SKU-1', quantity: 1, pad: 'x'.repeat(4096) }, await token());
      expect(res.statusCode).toBe(413);
    });
  });

  describe('serialization', () => {
    it('never leaks passwordHash even though the handler returns the full DB row', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/v1/users/me', headers: { authorization: `Bearer ${await token()}` } });
      expect(res.statusCode).toBe(200);
      expect(res.json()).toEqual({ id: USER_A, tenantId: TENANT_A, email: `a-${USER_A}@example.test` });
      expect(res.body).not.toContain('passwordHash');
      expect(res.body).not.toContain('argon2');
    });
  });

  describe('rate limiting', () => {
    it('the 21st request with the same credential -> 429; another credential is unaffected', async () => {
      const t = await token();
      const codes: number[] = [];
      for (let i = 0; i < 21; i++) {
        codes.push((await app.inject({ method: 'GET', url: '/api/v1/orders', headers: { authorization: `Bearer ${t}` } })).statusCode);
      }
      expect(codes.slice(0, 20).every((c) => c === 200)).toBe(true);
      expect(codes[20]).toBe(429);
      const other = await app.inject({ method: 'GET', url: '/api/v1/orders', headers: { authorization: `Bearer ${await token()}` } });
      expect(other.statusCode).toBe(200);
    });
  });

  describe('WebSocket gateway', () => {
    let url: string;
    beforeAll(async () => {
      await app.listen({ port: 0, host: '127.0.0.1' });
      url = `http://127.0.0.1:${(app.getHttpServer().address() as AddressInfo).port}/orders`;
    });

    it('rejects a bad token at connection time', async () => {
      const socket = io(url, { auth: { token: 'garbage' }, transports: ['websocket'], reconnection: false });
      const error = await new Promise<Error>((resolve) => socket.on('connect_error', resolve));
      socket.close();
      expect(error.message).toBe('unauthorized');
    });

    it('accepts a valid token and scopes the socket to its tenant', async () => {
      const socket = io(url, { auth: { token: await token() }, transports: ['websocket'], reconnection: false });
      await new Promise<void>((resolve, reject) => {
        socket.on('connect', resolve);
        socket.on('connect_error', reject);
      });
      const reply = await socket.emitWithAck('whoami', {});
      socket.close();
      expect(reply).toEqual({ tenantId: TENANT_A });
    });
  });
});

describe('broken response contract (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    trusted ??= await newKeys('trusted');
    app = await createApp((b) => {
      b.overrideProvider(OrdersService).useValue({
        get: () => Promise.resolve({ id: 'not-a-uuid', sku: 'SKU-1', quantity: 'two', tenantId: TENANT_A }),
      });
    });
  });
  afterAll(async () => {
    await app.close();
  });

  it('a handler returning data that violates the response schema -> opaque 500, nothing leaked', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `/api/v1/orders/${randomUUID()}`,
      headers: { authorization: `Bearer ${await token()}` },
    });
    expect(res.statusCode).toBe(500);
    expect(res.json()).toEqual({ statusCode: 500, message: 'Internal server error' });
  });
});
```

Results on 2026-11-24: unit 9/9, integration + e2e 23/23 (JSON reporter; executed count > 0), each planted bug in the table
above failed at least one test and passed again after revert. Integration tests (`test/orders.int-spec.ts`) cover the
repository against PostgreSQL: same-tenant round trip, no cross-tenant read by id or list, non-uuid tenant rejected by the column.

## 11. Container and CI

```dockerfile
# syntax=docker/dockerfile:1
# Base image pinned by multi-arch index digest (node:26.13.1-alpine3.23, resolved 2026-11-24).
# Renovate/Dependabot bump tag and digest together; never a floating tag.
ARG NODE_IMAGE=node:26.13.1-alpine3.23@sha256:39d8c143e60e99ae98f014bebea1e72fc96d3c9bdf9504bc3a27af5c05bfa39f

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.build.json nest-cli.json prisma.config.ts ./
COPY prisma ./prisma
COPY src ./src
# prisma.config.ts reads DATABASE_URL at load; generate never connects, so a placeholder is enough.
RUN DATABASE_URL=postgresql://placeholder@localhost:5432/placeholder npx prisma generate && npx nest build

FROM ${NODE_IMAGE} AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

FROM ${NODE_IMAGE}
ENV NODE_ENV=production
WORKDIR /app
COPY --from=prod-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD wget -qO- http://127.0.0.1:3000/health || exit 1
CMD ["node", "--import", "./dist/instrumentation.js", "dist/main.js"]
```

```yaml
# .github/workflows/ci.yml
name: ci
on:
  pull_request:
  push:
    branches: [develop]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_PASSWORD: ci
          POSTGRES_DB: orders
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 10
      redis:
        image: redis:8
        ports: ['6379:6379']
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:ci@localhost:5432/orders
      REDIS_URL: redis://localhost:6379
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '26.13.1'
          cache: npm
      - run: npm ci
      - run: npm audit --audit-level=high
      - run: npx prisma generate
      - run: npm run typecheck
      - run: npm run lint
      - run: npm test -- --reporter=default --reporter=junit --outputFile=reports/unit.xml
      - run: npx prisma migrate deploy
      - run: npm run test:e2e -- --reporter=default --reporter=junit --outputFile=reports/e2e.xml
      - run: npm run build
      - run: docker build -t orders-api:${{ github.sha }} .
```

## 12. Webhooks

```typescript
// src/common/webhook-signature.ts
import { createHmac, timingSafeEqual } from 'node:crypto';

/** HMAC-SHA256 over the RAW body. A length mismatch returns false instead of throwing (timingSafeEqual throws RangeError). */
export function verifyWebhookSignature(rawBody: Buffer, signatureHex: string, secret: string): boolean {
  if (secret === '') throw new Error('webhook secret must be configured');
  const expected = createHmac('sha256', secret).update(rawBody).digest();
  const received = /^[0-9a-f]+$/i.test(signatureHex) ? Buffer.from(signatureHex, 'hex') : Buffer.alloc(0);
  return received.length === expected.length && timingSafeEqual(received, expected);
}
```

Plain `node:crypto`, independent of the Nest version. Enable `rawBody: true` on `NestFactory.create` and verify over the raw
`Buffer`; a bare `timingSafeEqual` on unequal lengths turns a malformed signature into a 500.
