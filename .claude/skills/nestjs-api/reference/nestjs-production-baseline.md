# NestJS Production Baseline (runtime-verified)

A small orders API built in a disposable sandbox and verified end-to-end. Every block below
was compiled with strict `tsc`, linted with `typescript-eslint` (type-checked rules) and exercised by the tests
shown at the end. Use it as the reference implementation; the other reference files add depth.

**Verified stack (2026-11-23, `npm view`):** NestJS 11.2.11 (`@nestjs/common|core|platform-fastify|testing|websockets|platform-socket.io`),
Fastify 5.12.8, `@nestjs/swagger` 11.4.8, `@nestjs/config` 4.0.4, `@nestjs/throttler` 6.8.0, `@nestjs/bullmq` 11.0.5 + `bullmq` 5.81.6,
`class-validator` 0.15.1, `class-transformer` 0.5.1, `jose` 6.2.18, Prisma 7.10.1 (`prisma`, `@prisma/client`, `@prisma/adapter-pg`),
TypeScript 5.9.3, Vitest 4.1.12, `unplugin-swc` 2.0.0, ESLint 9.39.5 + `typescript-eslint` 8.73.0, Node 24.

> NestJS 12 is GA (12.6.0 on npm). This toolkit targets the 11.x line; moving to 12 is a separate, tested upgrade.
> Do not mix majors: `@nestjs/bullmq@11`, `@nestjs/swagger@11`, `@nestjs/config@4` peer on Nest 11; their `12.x` lines peer on Nest 12 only.

## What is proven, and how

| Concern | Rule | Proof (test → negative control) |
|---|---|---|
| Authentication | Global `APP_GUARD`; routes are protected unless `@Public()` | no token → 401; untrusted key → 401; wrong `aud` → 401 |
| JWT verification | `jose.jwtVerify` with pinned `algorithms`, `issuer`, `audience`, `requiredClaims`; empty issuer/audience refuses to construct | HS256 token rejected; removing the `audience` option fails the unit suite |
| Authorization | Coarse role check in the guard (403); per-resource check in the service | missing role → 403 |
| Tenant scoping | `tenantId` comes only from the verified token; every repository method takes it | tenant B reading tenant A's order → 404; removing the tenant filter fails unit + e2e |
| DTO validation | Global `ValidationPipe` with `whitelist` + `forbidNonWhitelisted`; invalid input is **400** (not 422) | smuggled `tenantId` → 400; removing `forbidNonWhitelisted` fails e2e |
| Rate limiting (Fastify) | `ThrottlerGuard` registered before the auth guard; key = hashed bearer token, else IP | 6th request → 429; another credential has its own bucket |
| WebSocket auth | Authenticate in socket.io middleware (`afterInit` → `server.use`), not in `handleConnection` | bad token → `connect_error: unauthorized`; removing the middleware fails e2e |
| Errors | RFC 9457 `application/problem+json`; 5xx logged, body opaque | content-type asserted on 401 |
| OpenAPI | `@nestjs/swagger` document lists versioned routes + bearer scheme | `/v1/orders` present |
| Fail-fast config | zod-validated env in `ConfigModule.forRoot({ validate })` | missing env → process exits 1 naming the fields (not values) |
| Shutdown | `enableShutdownHooks()` only; no extra `process.on('SIGTERM')` | SIGTERM → hooks run once, exit 143; with an extra handler hooks ran **twice** |
| Prisma | Interactive transaction with isolation + `maxWait`/`timeout`; P2002 classified by constraint name; `$extends` replaces removed `$use` | type-checked against the generated client; `$use` → TS2339. **Runtime NOT RUN: no PostgreSQL in the sandbox** |
| BullMQ | `WorkerHost` processor; idempotent handler; `UnrecoverableError` for poison jobs | type-checked only. **Runtime NOT RUN: no Redis** |

## 1. Fail-fast configuration

```typescript
// src/config/env.ts
import { z } from 'zod';

/** Fail-fast environment contract: the app refuses to start on a missing or empty value. */
export const envSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  JWT_ISSUER: z.url(),
  JWT_AUDIENCE: z.string().min(1),
  JWT_JWKS_URL: z.url(),
  THROTTLE_LIMIT: z.coerce.number().int().positive().default(100),
  THROTTLE_TTL_MS: z.coerce.number().int().positive().default(60_000),
});

export type Env = z.infer<typeof envSchema>;

export function validateEnv(raw: Record<string, unknown>): Env {
  const parsed = envSchema.safeParse(raw);
  if (!parsed.success) {
    // Names only: values may be secrets.
    const fields = parsed.error.issues.map((issue) => issue.path.join('.')).join(', ');
    throw new Error(`Invalid environment configuration: ${fields}`);
  }
  return parsed.data;
}
```

`ConfigModule.forRoot({ validate })` runs when `AppModule` is **imported**, before any `beforeAll`. E2E env must be
set in the Vitest config (`test.env`), not inside the spec — otherwise the import throws.

## 2. Authentication: token verifier and global guard

Use `jose` against the issuer's JWKS (`createRemoteJWKSet`). Pin algorithms; never accept `none` or an HMAC algorithm
when the issuer signs asymmetrically. Reject an empty issuer/audience at construction: an unset audience is a silent
"accept tokens minted for any service" switch (passport-jwt and most libraries skip the check when the option is `undefined`).

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
import type { Principal } from './principal';

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

@Injectable()
export class TokenVerifier {
  constructor(
    @Inject(JWT_KEY_RESOLVER) private readonly keys: JWTVerifyGetKey,
    @Inject(JWT_VERIFY_OPTIONS) private readonly options: JwtVerifyOptions,
  ) {
    // An empty issuer/audience would silently accept tokens minted for another service.
    if (options.issuer.trim() === '' || options.audience.trim() === '') {
      throw new Error('TokenVerifier requires a non-empty issuer and audience');
    }
  }

  async verify(token: string): Promise<Principal> {
    try {
      const { payload } = await jwtVerify(token, this.keys, {
        issuer: this.options.issuer,
        audience: this.options.audience,
        algorithms: ['RS256', 'ES256'], // pin: never accept "none" or an HMAC alg with a public key
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
      throw error; // JWKS outage etc. is not "invalid token": let it surface as 5xx
    }
  }
}
```

```typescript
// src/auth/auth.decorators.ts
import { createParamDecorator, type ExecutionContext, SetMetadata, UnauthorizedException } from '@nestjs/common';
import type { AuthenticatedRequest, Principal } from './principal';

export const IS_PUBLIC = 'auth:isPublic';
export const REQUIRED_ROLES = 'auth:requiredRoles';

/** Opt a route OUT of the global auth guard. Authentication is the default. */
export const Public = (): MethodDecorator & ClassDecorator => SetMetadata(IS_PUBLIC, true);

export const RequireRoles = (...roles: string[]): MethodDecorator & ClassDecorator =>
  SetMetadata(REQUIRED_ROLES, roles);

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
import { IS_PUBLIC, REQUIRED_ROLES } from './auth.decorators';
import type { AuthenticatedRequest } from './principal';
import { InvalidTokenError, TokenVerifier } from './token-verifier';

/** Global (APP_GUARD) authentication + coarse role check. Per-resource checks live in services. */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  private readonly logger = new Logger(JwtAuthGuard.name);

  constructor(
    private readonly reflector: Reflector,
    private readonly verifier: TokenVerifier,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const targets = [context.getHandler(), context.getClass()];
    if (this.reflector.getAllAndOverride<boolean>(IS_PUBLIC, targets) === true) return true;

    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    const header = request.headers['authorization'];
    const token = typeof header === 'string' && header.startsWith('Bearer ') ? header.slice(7).trim() : '';
    if (token === '') throw new UnauthorizedException();

    try {
      request.principal = await this.verifier.verify(token);
    } catch (error: unknown) {
      if (error instanceof InvalidTokenError) {
        this.logger.warn({ event: 'auth_rejected', reason: error.reason }); // never log the token
        throw new UnauthorizedException();
      }
      throw error;
    }

    const required = this.reflector.getAllAndOverride<string[] | undefined>(REQUIRED_ROLES, targets) ?? [];
    if (!required.every((role) => request.principal?.roles.has(role) === true)) {
      throw new ForbiddenException();
    }
    return true;
  }
}
```

**Guard order** — global guards run in `APP_GUARD` registration order, then controller guards, then route guards.
Put the throttler first (cheap, rejects floods before signature verification), then authentication, then authorization.
A guard that reads `request.user`/`request.principal` must run after the guard that sets it.

## 3. Tenant-scoped service, DTO and controller

```typescript
// src/orders/orders.dto.ts
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsInt, IsString, Length, Matches, Max, Min } from 'class-validator';

/** No tenantId field: tenant comes from the verified token. forbidNonWhitelisted rejects a smuggled one. */
export class CreateOrderDto {
  @ApiProperty({ example: 'SKU-1234' })
  @IsString()
  @Length(3, 32)
  @Matches(/^[A-Z0-9-]+$/)
  readonly sku!: string;

  @ApiProperty({ minimum: 1, maximum: 1000 })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(1000)
  readonly quantity!: number;
}

export class OrderResponseDto {
  @ApiProperty() readonly id!: string;
  @ApiProperty() readonly sku!: string;
  @ApiProperty() readonly quantity!: number;
  @ApiProperty() readonly createdAt!: string;
}

export interface OrderRecord {
  readonly id: string;
  readonly tenantId: string;
  readonly sku: string;
  readonly quantity: number;
  readonly createdAt: Date;
}
```

```typescript
// src/orders/orders.repository.ts
import type { OrderRecord } from './orders.dto';

export const ORDERS_REPOSITORY = Symbol('ORDERS_REPOSITORY');

/** Every method takes tenantId: a query without it cannot be written by accident. */
export interface OrdersRepository {
  create(tenantId: string, input: { sku: string; quantity: number }): Promise<OrderRecord>;
  findById(tenantId: string, id: string): Promise<OrderRecord | null>;
}
```

```typescript
// src/orders/orders.service.ts
import { Inject, Injectable, NotFoundException } from '@nestjs/common';
import type { Principal } from '../auth/principal';
import type { CreateOrderDto, OrderRecord, OrderResponseDto } from './orders.dto';
import { ORDERS_REPOSITORY, type OrdersRepository } from './orders.repository';

@Injectable()
export class OrdersService {
  constructor(@Inject(ORDERS_REPOSITORY) private readonly orders: OrdersRepository) {}

  async create(principal: Principal, dto: CreateOrderDto): Promise<OrderResponseDto> {
    return toResponse(await this.orders.create(principal.tenantId, dto));
  }

  /** Another tenant's order is indistinguishable from a missing one: 404, no existence leak. */
  async get(principal: Principal, id: string): Promise<OrderResponseDto> {
    const order = await this.orders.findById(principal.tenantId, id);
    if (order === null) throw new NotFoundException();
    return toResponse(order);
  }
}

function toResponse(order: OrderRecord): OrderResponseDto {
  return { id: order.id, sku: order.sku, quantity: order.quantity, createdAt: order.createdAt.toISOString() };
}
```

```typescript
// src/orders/orders.controller.ts
import { Body, Controller, Get, HttpCode, HttpStatus, Param, ParseUUIDPipe, Post } from '@nestjs/common';
import { ApiBearerAuth, ApiCreatedResponse, ApiOkResponse, ApiTags } from '@nestjs/swagger';
import { CurrentPrincipal, RequireRoles } from '../auth/auth.decorators';
import type { Principal } from '../auth/principal';
import { CreateOrderDto, OrderResponseDto } from './orders.dto';
import { OrdersService } from './orders.service';

@ApiTags('orders')
@ApiBearerAuth()
@Controller({ path: 'orders', version: '1' })
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @RequireRoles('orders:write')
  @ApiCreatedResponse({ type: OrderResponseDto })
  create(@CurrentPrincipal() principal: Principal, @Body() dto: CreateOrderDto): Promise<OrderResponseDto> {
    return this.orders.create(principal, dto);
  }

  @Get(':id')
  @ApiOkResponse({ type: OrderResponseDto })
  get(
    @CurrentPrincipal() principal: Principal,
    @Param('id', new ParseUUIDPipe({ version: '4' })) id: string,
  ): Promise<OrderResponseDto> {
    return this.orders.get(principal, id);
  }
}
```

Rules:
- Tenant/owner ids come from `Principal`, never from the body, query or a path parameter the caller controls.
- Another tenant's resource answers **404**, the same as a missing one (no existence oracle). Use 403 for "authenticated
  but lacks the role/permission for this action".
- Keep the authorization predicate in one shared place; duplicated copies drift.

## 4. Bootstrap, pipes, versioning, Swagger, shutdown

```typescript
// src/configure-app.ts
import helmet from '@fastify/helmet';
import { ValidationPipe, VersioningType } from '@nestjs/common';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';

/** Shared by main.ts and the e2e tests, so tests exercise the production pipeline. */
export async function configureApp(app: NestFastifyApplication): Promise<void> {
  await app.register(helmet);
  app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1' });
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true, // strip unknown properties...
      forbidNonWhitelisted: true, // ...and reject the request instead of silently stripping
      transform: true,
      transformOptions: { enableImplicitConversion: false },
      stopAtFirstError: false,
    }),
  );
  app.enableShutdownHooks();
}
```

```typescript
// src/main.ts
import 'reflect-metadata';
import { Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';
import type { Env } from './config/env';
import { configureApp } from './configure-app';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    // bodyLimit caps request size; trustProxy only when a known proxy sets X-Forwarded-For.
    new FastifyAdapter({ bodyLimit: 1_048_576, trustProxy: false }),
    { bufferLogs: false },
  );
  await configureApp(app);
  const config = app.get<ConfigService<Env, true>>(ConfigService);
  if (config.get('NODE_ENV', { infer: true }) !== 'production') {
    const document = SwaggerModule.createDocument(
      app,
      new DocumentBuilder().setTitle('Orders API').setVersion('1').addBearerAuth().build(),
    );
    SwaggerModule.setup('docs', app, document);
  }
  // 0.0.0.0: Fastify listens on 127.0.0.1 by default, unreachable from outside a container.
  await app.listen({ port: config.get('PORT', { infer: true }), host: '0.0.0.0' });
}

bootstrap().catch((error: unknown) => {
  new Logger('Bootstrap').error('startup failed', error instanceof Error ? error.stack : String(error));
  process.exit(1);
});
```

`ValidationPipe` notes (verified in `@nestjs/common` 11.2.11 source): the default `errorHttpStatusCode` is **400**;
`whitelist` alone silently strips unknown fields, `forbidNonWhitelisted` rejects them. Prefer
`enableImplicitConversion: false` plus explicit `@Type(() => Number)`: implicit conversion turns the string `"false"` into `true`
for a `boolean` property.

**Shutdown**: `app.enableShutdownHooks()` re-raises the signal after `onModuleDestroy` → `beforeApplicationShutdown` →
`onApplicationShutdown` complete (exit 143 on SIGTERM). Do **not** also register `process.on('SIGTERM', …)` that calls
`app.close()`: reproduced, hooks run twice (second call with `signal=undefined`) and the process exits 0.
Pass `{ useProcessExit: true }` only when an async logger transport must flush on exit.

## 5. Module wiring, rate limiting, error filter

```typescript
// src/app.module.ts
import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { APP_FILTER, APP_GUARD } from '@nestjs/core';
import { ThrottlerGuard, ThrottlerModule } from '@nestjs/throttler';
import { createRemoteJWKSet } from 'jose';
import { JwtAuthGuard } from './auth/jwt-auth.guard';
import { JWT_KEY_RESOLVER, JWT_VERIFY_OPTIONS, TokenVerifier } from './auth/token-verifier';
import { ProblemDetailsFilter } from './common/problem-details.filter';
import { throttleTracker } from './common/throttler-tracker';
import { type Env, validateEnv } from './config/env';
import { HealthController } from './health.controller';
import { InMemoryOrdersRepository } from './orders/in-memory-orders.repository';
import { OrdersController } from './orders/orders.controller';
import { ORDERS_REPOSITORY } from './orders/orders.repository';
import { OrdersService } from './orders/orders.service';
import { OrdersGateway } from './realtime/orders.gateway';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, validate: validateEnv, cache: true }),
    ThrottlerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService<Env, true>) => ({
        throttlers: [{ name: 'default', ttl: config.get('THROTTLE_TTL_MS', { infer: true }), limit: config.get('THROTTLE_LIMIT', { infer: true }) }],
        getTracker: throttleTracker,
      }),
    }),
  ],
  controllers: [HealthController, OrdersController],
  providers: [
    OrdersService,
    OrdersGateway,
    TokenVerifier,
    { provide: ORDERS_REPOSITORY, useClass: InMemoryOrdersRepository },
    {
      provide: JWT_KEY_RESOLVER,
      inject: [ConfigService],
      useFactory: (config: ConfigService<Env, true>) => createRemoteJWKSet(new URL(config.get('JWT_JWKS_URL', { infer: true }))),
    },
    {
      provide: JWT_VERIFY_OPTIONS,
      inject: [ConfigService],
      useFactory: (config: ConfigService<Env, true>) => ({
        issuer: config.get('JWT_ISSUER', { infer: true }),
        audience: config.get('JWT_AUDIENCE', { infer: true }),
      }),
    },
    // Guard order = registration order: throttle first (cheap, rejects floods before crypto), then auth.
    { provide: APP_GUARD, useClass: ThrottlerGuard },
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_FILTER, useClass: ProblemDetailsFilter },
  ],
})
export class AppModule {}
```

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
// src/common/problem-details.filter.ts
import { type ArgumentsHost, Catch, type ExceptionFilter, HttpException, HttpStatus, Logger } from '@nestjs/common';
import type { FastifyReply, FastifyRequest } from 'fastify';

/** RFC 9457 problem+json for every error. Unknown errors are logged and returned as an opaque 500. */
@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
  private readonly logger = new Logger(ProblemDetailsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const http = host.switchToHttp();
    const reply = http.getResponse<FastifyReply>();
    const request = http.getRequest<FastifyRequest>();

    const status: number = exception instanceof HttpException ? exception.getStatus() : HttpStatus.INTERNAL_SERVER_ERROR;
    if (status >= 500) {
      this.logger.error({ event: 'unhandled_error', path: request.url }, exception instanceof Error ? exception.stack : undefined);
    }
    const body = exception instanceof HttpException ? exception.getResponse() : undefined;
    const errors = typeof body === 'object' && body !== null && 'message' in body && Array.isArray(body.message) ? body.message : undefined;

    void reply
      .status(status)
      .header('content-type', 'application/problem+json')
      .send({
        type: 'about:blank',
        title: status >= 500 ? 'Internal Server Error' : (exception as HttpException).message,
        status,
        instance: request.url,
        ...(errors !== undefined && status === 400 ? { errors } : {}),
      });
  }
}
```

Multi-instance deployments need shared counters. The maintained storage is `@nest-lab/throttler-storage-redis`
(1.2.0; `@nestjs/throttler-storage-redis` does **not exist** on npm — installing an unregistered scoped name is a typosquat risk):

```typescript
// src/common/throttler-redis.options.ts
import { ThrottlerStorageRedisService } from '@nest-lab/throttler-storage-redis';
import type { ThrottlerModuleOptions } from '@nestjs/throttler';
import { Redis } from 'ioredis';
import { throttleTracker } from './throttler-tracker';

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

To customise the 429 message use the `errorMessage` option. Overriding `throwThrottlingException(context)` with a
`void` return no longer compiles on v6 (`TS2416`: the base method is `(context, throttlerLimitDetail) => Promise<void>`).

## 6. WebSocket gateway authentication

```typescript
// src/realtime/orders.gateway.ts
import { Logger } from '@nestjs/common';
import { type OnGatewayInit, SubscribeMessage, WebSocketGateway } from '@nestjs/websockets';
import type { Server, Socket } from 'socket.io';
import type { Principal } from '../auth/principal';
import { InvalidTokenError, TokenVerifier } from '../auth/token-verifier';

interface SocketData {
  principal?: Principal;
}

/**
 * Authenticate in socket.io middleware (afterInit → server.use), NOT in handleConnection:
 * an async handleConnection does not hold back the client's messages, so handlers could run
 * before the check finishes. Rooms are per tenant, derived from the verified token.
 */
@WebSocketGateway({ namespace: 'orders', cors: { origin: false } })
export class OrdersGateway implements OnGatewayInit<Server> {
  private readonly logger = new Logger(OrdersGateway.name);

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
          if (!(error instanceof InvalidTokenError)) this.logger.error({ event: 'ws_auth_error' }, error instanceof Error ? error.stack : undefined);
          next(new Error('unauthorized'));
        });
    });
  }

  @SubscribeMessage('whoami')
  whoami(client: Socket): { tenantId: string } {
    const principal = (client.data as SocketData).principal;
    if (principal === undefined) throw new Error('unauthenticated socket reached a handler');
    return { tenantId: principal.tenantId };
  }
}
```

From the `@nestjs/websockets` 11.2.11 typings: an async `handleConnection()` does **not** hold back the client's
messages. Guards on `@SubscribeMessage` handlers check each message; connection-level rejection belongs in
`server.use()` (socket.io) or `verifyClient` (`WsAdapter`).

## 7. Prisma 7: transactions, errors, extensions

Verified Prisma 7 code (interactive transaction with isolation and bounds, P2002 classification under the driver adapter,
`$extends` replacing the removed `$use`) lives in `nestjs-config-prisma7.md` → "Transactions, errors and extensions (verified)".
Tooling (package.json pins, tsconfig, Vitest, ESLint flat config, audit override) is in `nestjs-config-npm-ts.md`;
the full unit + e2e suite with its negative controls is in `nestjs-testing-integration-setup.md`.

## 8. Background jobs (BullMQ)

```typescript
// src/jobs/order-events.processor.ts
import { Logger } from '@nestjs/common';
import { Processor, WorkerHost } from '@nestjs/bullmq';
import { UnrecoverableError, type Job } from 'bullmq';

export const ORDER_EVENTS_QUEUE = 'order-events';

export interface OrderCreatedJob {
  readonly tenantId: string;
  readonly orderId: string;
}

/**
 * BullMQ is at-least-once: a job can run twice (stalled worker, retry after a timeout).
 * The handler must be idempotent, keyed on orderId; enqueue with jobId = orderId to dedupe.
 */
@Processor(ORDER_EVENTS_QUEUE, { concurrency: 5 })
export class OrderEventsProcessor extends WorkerHost {
  private readonly logger = new Logger(OrderEventsProcessor.name);

  async process(job: Job<OrderCreatedJob>): Promise<void> {
    const { tenantId, orderId } = job.data;
    if (tenantId === '' || orderId === '') {
      // A malformed payload never succeeds on retry: fail permanently instead of burning attempts.
      throw new UnrecoverableError('malformed order-created job');
    }
    this.logger.log({ event: 'order_created_handled', jobId: job.id, attempt: job.attemptsMade + 1 });
    await Promise.resolve();
  }
}
```

```typescript
// src/jobs/jobs.module.ts
import { BullModule } from '@nestjs/bullmq';
import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ORDER_EVENTS_QUEUE, OrderEventsProcessor } from './order-events.processor';

/** Not imported by AppModule in the sandbox: no Redis available. Type-checked only. */
@Module({
  imports: [
    BullModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        connection: { url: config.getOrThrow<string>('REDIS_URL') },
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
  providers: [OrderEventsProcessor],
})
export class JobsModule {}
```

Delivery is at-least-once: make handlers idempotent (key on the business id, enqueue with `jobId` set to it), bound
`attempts` with backoff, throw `UnrecoverableError` for payloads that can never succeed, and close workers on shutdown
(`@nestjs/bullmq` does this in `onApplicationShutdown` when shutdown hooks are enabled).

## 9. Webhooks

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

`crypto.timingSafeEqual` throws `RangeError` when lengths differ; a bare call turns a malformed signature into a 500.
Enable `rawBody: true` on `NestFactory.create` and verify over the raw `Buffer`.

