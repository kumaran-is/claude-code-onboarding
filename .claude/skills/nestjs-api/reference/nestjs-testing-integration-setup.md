# NestJS 11.x Integration Testing — Setup & Testcontainers

Integration test configuration, full app bootstrapping with supertest and Fastify, and Testcontainers PostgreSQL setup for NestJS 11.x.

## Vitest Configuration for Integration Tests

### vitest.e2e.config.mts (verified, Vitest 4.1.12)

```typescript
import swc from 'unplugin-swc';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['test/**/*.e2e-spec.ts'],
    root: './',
    fileParallelism: false,
    // ConfigModule.forRoot({ validate }) runs when AppModule is IMPORTED, before any beforeAll:
    // test env must exist at load time, so it is set here, not in the spec.
    env: {
      NODE_ENV: 'test',
      JWT_ISSUER: 'https://issuer.test',
      JWT_AUDIENCE: 'orders-api',
      JWT_JWKS_URL: 'https://issuer.test/.well-known/jwks.json',
      THROTTLE_LIMIT: '5',
      THROTTLE_TTL_MS: '60000',
    },
  },
  plugins: [swc.vite({ module: { type: 'es6' } })],
});
```

- Vitest 4 removed `test.poolOptions` (`poolOptions.threads.singleThread` → TS2769 and a runtime "removed in Vitest 4" notice). Use top-level `fileParallelism: false` / `maxWorkers: 1` to serialise suites that share a database.
- `ConfigModule.forRoot({ validate })` runs when `AppModule` is imported. Set test env in `test.env` (or a `setupFiles` module) — assigning `process.env` inside `beforeAll` is too late and the import throws.
- Build the app through the same `configureApp()` as `main.ts`; re-declaring `ValidationPipe` in each spec lets test and production config drift.

## Verified suite: guard, tenant, validation, throttling, WebSocket

```typescript
// test/jwt-fixture.ts
import { createLocalJWKSet, exportJWK, generateKeyPair, type JWTVerifyGetKey, SignJWT } from 'jose';

export const ISSUER = 'https://issuer.test';
export const AUDIENCE = 'orders-api';

export interface JwtFixture {
  readonly keys: JWTVerifyGetKey;
  sign(claims: Record<string, unknown>, opts?: { audience?: string; issuer?: string; expiresIn?: string; foreignKey?: boolean }): Promise<string>;
}

/** Real RS256 keys and a local JWKS: the verifier runs unmocked. */
export async function createJwtFixture(): Promise<JwtFixture> {
  const trusted = await generateKeyPair('RS256');
  const foreign = await generateKeyPair('RS256');
  const jwk = { ...(await exportJWK(trusted.publicKey)), kid: 'k1', alg: 'RS256' };
  return {
    keys: createLocalJWKSet({ keys: [jwk] }),
    sign: (claims, opts = {}) =>
      new SignJWT(claims)
        .setProtectedHeader({ alg: 'RS256', kid: 'k1' })
        .setIssuer(opts.issuer ?? ISSUER)
        .setAudience(opts.audience ?? AUDIENCE)
        .setIssuedAt()
        .setExpirationTime(opts.expiresIn ?? '5m')
        .sign(opts.foreignKey === true ? foreign.privateKey : trusted.privateKey),
  };
}
```

```typescript
// src/auth/token-verifier.spec.ts
import { SignJWT } from 'jose';
import { beforeAll, describe, expect, it } from 'vitest';
import { AUDIENCE, createJwtFixture, ISSUER, type JwtFixture } from '../../test/jwt-fixture';
import { InvalidTokenError, TokenVerifier } from './token-verifier';

describe('TokenVerifier', () => {
  let jwt: JwtFixture;
  let verifier: TokenVerifier;

  beforeAll(async () => {
    jwt = await createJwtFixture();
    verifier = new TokenVerifier(jwt.keys, { issuer: ISSUER, audience: AUDIENCE });
  });

  it('returns the principal from a valid token', async () => {
    const token = await jwt.sign({ sub: 'u1', tenant_id: 't1', roles: ['orders:write', 7] });
    const principal = await verifier.verify(token);
    expect(principal.subject).toBe('u1');
    expect(principal.tenantId).toBe('t1');
    expect([...principal.roles]).toEqual(['orders:write']);
  });

  it.each([
    ['wrong audience', { audience: 'other-api' }],
    ['wrong issuer', { issuer: 'https://evil.test' }],
    ['expired', { expiresIn: '-1m' }],
    ['signed by an untrusted key', { foreignKey: true }],
  ])('rejects a token with %s', async (_label, opts) => {
    const token = await jwt.sign({ sub: 'u1', tenant_id: 't1' }, opts);
    await expect(verifier.verify(token)).rejects.toBeInstanceOf(InvalidTokenError);
  });

  it('rejects a token without tenant_id', async () => {
    await expect(verifier.verify(await jwt.sign({ sub: 'u1' }))).rejects.toBeInstanceOf(InvalidTokenError);
  });

  it('rejects an HS256 token (algorithm pinning)', async () => {
    const token = await new SignJWT({ sub: 'u1', tenant_id: 't1' })
      .setProtectedHeader({ alg: 'HS256' })
      .setIssuer(ISSUER)
      .setAudience(AUDIENCE)
      .setExpirationTime('5m')
      .sign(new TextEncoder().encode('a-shared-secret-of-at-least-32-bytes!!'));
    await expect(verifier.verify(token)).rejects.toBeInstanceOf(InvalidTokenError);
  });

  it('refuses to build with an empty audience', () => {
    expect(() => new TokenVerifier(jwt.keys, { issuer: ISSUER, audience: ' ' })).toThrow(/non-empty/);
  });
});
```

```typescript
// test/app.e2e-spec.ts
import type { AddressInfo } from 'node:net';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { Test } from '@nestjs/testing';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { io } from 'socket.io-client';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../src/app.module';
import { JWT_KEY_RESOLVER } from '../src/auth/token-verifier';
import { configureApp } from '../src/configure-app';
import { createJwtFixture, type JwtFixture } from './jwt-fixture';

async function bootApp(jwt: JwtFixture): Promise<NestFastifyApplication> {
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] })
    .overrideProvider(JWT_KEY_RESOLVER)
    .useValue(jwt.keys) // only the key source is swapped; guard, verifier and pipes are real
    .compile();
  const app = moduleRef.createNestApplication<NestFastifyApplication>(new FastifyAdapter());
  await configureApp(app);
  await app.init();
  await app.getHttpAdapter().getInstance().ready();
  return app;
}

describe('orders API (Fastify, real guard + ValidationPipe)', () => {
  let jwt: JwtFixture;
  let app: NestFastifyApplication;
  let writerA: string;
  let readerB: string;
  let readerA: string;

  beforeAll(async () => {
    jwt = await createJwtFixture();
    app = await bootApp(jwt);
    writerA = await jwt.sign({ sub: 'u1', tenant_id: 'tenant-a', roles: ['orders:write'] });
    readerA = await jwt.sign({ sub: 'u3', tenant_id: 'tenant-a', roles: [] });
    readerB = await jwt.sign({ sub: 'u2', tenant_id: 'tenant-b', roles: ['orders:write'] });
  });
  afterAll(async () => {
    await app.close();
  });

  const post = (token: string | undefined, payload: unknown) =>
    app.inject({ method: 'POST', url: '/v1/orders', payload: payload as Record<string, unknown>, headers: token === undefined ? {} : { authorization: `Bearer ${token}` } });

  it('public health route works and carries helmet headers', async () => {
    const res = await app.inject({ method: 'GET', url: '/health/live' });
    expect(res.statusCode).toBe(200);
    expect(res.headers['x-content-type-options']).toBe('nosniff');
  });

  it('401 without a token, as problem+json', async () => {
    const res = await post(undefined, { sku: 'SKU-1', quantity: 1 });
    expect(res.statusCode).toBe(401);
    expect(res.headers['content-type']).toContain('application/problem+json');
  });

  it('401 for a token signed by an untrusted key and for a wrong audience', async () => {
    expect((await post(await jwt.sign({ sub: 'x', tenant_id: 'tenant-a', roles: ['orders:write'] }, { foreignKey: true }), { sku: 'SKU-1', quantity: 1 })).statusCode).toBe(401);
    expect((await post(await jwt.sign({ sub: 'x', tenant_id: 'tenant-a', roles: ['orders:write'] }, { audience: 'other' }), { sku: 'SKU-1', quantity: 1 })).statusCode).toBe(401);
  });

  it('403 when the role is missing', async () => {
    expect((await post(readerA, { sku: 'SKU-1', quantity: 1 })).statusCode).toBe(403);
  });

  it('400 for an unknown field (tenantId smuggled in the body) and for invalid values', async () => {
    const smuggled = await post(writerA, { sku: 'SKU-1', quantity: 1, tenantId: 'tenant-b' });
    expect(smuggled.statusCode).toBe(400);
    expect(JSON.stringify(smuggled.json())).toContain('property tenantId should not exist');
    expect((await post(writerA, { sku: 'SKU-1', quantity: 0 })).statusCode).toBe(400);
    expect((await post(writerA, { sku: 'bad sku!', quantity: 1 })).statusCode).toBe(400);
  });

  it('creates for tenant A; tenant A reads it, tenant B gets 404', async () => {
    const created = await post(writerA, { sku: 'SKU-1', quantity: 3 });
    expect(created.statusCode).toBe(201);
    const { id } = created.json<{ id: string }>();
    const own = await app.inject({ method: 'GET', url: `/v1/orders/${id}`, headers: { authorization: `Bearer ${readerA}` } });
    expect(own.statusCode).toBe(200);
    const other = await app.inject({ method: 'GET', url: `/v1/orders/${id}`, headers: { authorization: `Bearer ${readerB}` } });
    expect(other.statusCode).toBe(404);
  });

  it('400 for a malformed id (ParseUUIDPipe)', async () => {
    const res = await app.inject({ method: 'GET', url: '/v1/orders/not-a-uuid', headers: { authorization: `Bearer ${readerA}` } });
    expect(res.statusCode).toBe(400);
  });

  it('works through supertest against the Fastify server too', async () => {
    await request(app.getHttpServer()).get('/v1/orders/not-a-uuid').expect(401);
  });

  it('OpenAPI document lists the versioned route with bearer auth', () => {
    const doc = SwaggerModule.createDocument(app, new DocumentBuilder().addBearerAuth().build());
    expect(Object.keys(doc.paths)).toContain('/v1/orders');
    expect(doc.components?.securitySchemes).toHaveProperty('bearer');
  });
});

describe('rate limiting with Fastify', () => {
  it('returns 429 after the limit, keyed per credential', async () => {
    const jwt = await createJwtFixture();
    const app = await bootApp(jwt) // THROTTLE_LIMIT=5 from vitest.e2e.config.mts;
    try {
      const token = await jwt.sign({ sub: 'u1', tenant_id: 'tenant-a', roles: [] });
      const codes: number[] = [];
      for (let i = 0; i < 6; i += 1) {
        codes.push((await app.inject({ method: 'GET', url: '/v1/orders/00000000-0000-4000-8000-000000000000', headers: { authorization: `Bearer ${token}` } })).statusCode);
      }
      expect(codes).toEqual([404, 404, 404, 404, 404, 429]);
      const other = await jwt.sign({ sub: 'u2', tenant_id: 'tenant-a', roles: [] });
      const fresh = await app.inject({ method: 'GET', url: '/v1/orders/00000000-0000-4000-8000-000000000000', headers: { authorization: `Bearer ${other}` } });
      expect(fresh.statusCode).toBe(404); // separate bucket for a different credential
    } finally {
      await app.close();
    }
  });
});

describe('WebSocket gateway auth (socket.io over Fastify)', () => {
  it('rejects a handshake without a valid token and admits a valid one', async () => {
    const jwt = await createJwtFixture();
    const app = await bootApp(jwt);
    await app.listen({ port: 0, host: '127.0.0.1' });
    const { port } = app.getHttpServer().address() as AddressInfo;
    const url = `http://127.0.0.1:${port}/orders`;
    try {
      const rejected = await new Promise<string>((resolve) => {
        const socket = io(url, { transports: ['websocket'], auth: { token: 'garbage' }, reconnection: false });
        socket.on('connect_error', (err) => { socket.close(); resolve(err.message); });
        socket.on('connect', () => { socket.close(); resolve('connected'); });
      });
      expect(rejected).toBe('unauthorized');

      const token = await jwt.sign({ sub: 'u1', tenant_id: 'tenant-a' });
      const reply = await new Promise<unknown>((resolve, reject) => {
        const socket = io(url, { transports: ['websocket'], auth: { token }, reconnection: false });
        socket.on('connect_error', (err) => { socket.close(); reject(err); });
        socket.on('connect', () => {
          socket.emit('whoami', {}, (ack: unknown) => { socket.close(); resolve(ack); });
        });
      });
      expect(reply).toEqual({ tenantId: 'tenant-a' });
    } finally {
      await app.close();
    }
  });
});
```

`app.inject()` (Fastify light-my-request) needs no listening port; `supertest(app.getHttpServer())` also works after
`await app.getHttpAdapter().getInstance().ready()`. Only the key source is overridden — guard, verifier, pipe and filter are the production ones.

### Sandbox results (2026-11-23)

| Check | Result | Negative control |
|---|---|---|
| `tsc --noEmit` (strict) | exit 0 | planted type error → exit 2 |
| `eslint .` | exit 0 | `console.log`, `as any`, floating promise → exit 1 (3 errors) |
| `vitest run` (unit) | 19 passed | audience check removed → 1 failed; tenant filter removed → 1 failed |
| `vitest run --config vitest.e2e.config.mts` | 11 passed | `forbidNonWhitelisted` removed → 1 failed; WS middleware removed → 1 failed; `emitDecoratorMetadata: false` → 11 failed |
| `node dist/main.js` | `/health/live` 200, unauthenticated POST 401, `/docs-json` lists 3 paths, SIGTERM exit 143 | empty env → exit 1 |
| `npm audit --audit-level=high` | exit 0 with override | exit 1 without |
| Prisma transaction / BullMQ worker against real services | NOT RUN | no PostgreSQL or Redis available |

## Full App Bootstrap with supertest and Testcontainers

> Not re-run in this toolkit's sandbox (no Docker). Two fixes apply to the example below: provide `DATABASE_URL` before `AppModule` is imported (start the container in a Vitest `globalSetup` and pass the URL through `provide`/env), and call the shared `configureApp(app)` instead of re-creating the pipe.

```typescript
// test/users.e2e-spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import request from 'supertest';
import { AppModule } from '@/app.module';
import { ValidationPipe } from '@nestjs/common';
import { DatabaseService } from '@/core/database/database.service';
import { GenericContainer, StartedTestContainer } from 'testcontainers';

describe('Users API (e2e)', () => {
  let app: NestFastifyApplication;
  let databaseService: DatabaseService;
  let postgresContainer: StartedTestContainer;

  beforeAll(async () => {
    // Start PostgreSQL container
    postgresContainer = await new GenericContainer('postgres:16-alpine')
      .withEnvironment({
        POSTGRES_USER: 'test',
        POSTGRES_PASSWORD: 'test',
        POSTGRES_DB: 'testdb',
      })
      .withExposedPorts(5432)
      .start();

    const port = postgresContainer.getMappedPort(5432);
    const databaseUrl = `postgresql://test:test@localhost:${port}/testdb`;

    // Set environment variable for Prisma
    process.env.DATABASE_URL = databaseUrl;

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );

    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        forbidNonWhitelisted: true,
        transform: true,
      }),
    );

    databaseService = app.get<DatabaseService>(DatabaseService);

    // Run migrations
    const { execSync } = await import('child_process');
    execSync('npx prisma migrate deploy', {
      env: { ...process.env, DATABASE_URL: databaseUrl },
    });

    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  afterAll(async () => {
    await databaseService.$disconnect();
    await app.close();
    await postgresContainer.stop();
  });

  beforeEach(async () => {
    // Clean database before each test
    await databaseService.user.deleteMany();
  });

  describe('/api/v1/users (POST)', () => {
    it('should create a new user', async () => {
      const createUserDto = {
        email: 'test@example.com',
        name: 'Test User',
        role: 'USER',
      };

      const response = await request(app.getHttpServer())
        .post('/api/v1/users')
        .send(createUserDto)
        .expect(201);

      expect(response.body).toMatchObject({
        email: createUserDto.email,
        name: createUserDto.name,
        role: createUserDto.role,
        isActive: true,
      });
      expect(response.body.id).toBeDefined();
      expect(response.body.createdAt).toBeDefined();

      // Verify in database
      const user = await databaseService.user.findUnique({
        where: { id: response.body.id },
      });
      expect(user).not.toBeNull();
      expect(user?.email).toBe(createUserDto.email);
    });

    it('should return 400 for invalid email', async () => {
      const invalidDto = {
        email: 'invalid-email',
        name: 'Test User',
        role: 'USER',
      };

      const response = await request(app.getHttpServer())
        .post('/api/v1/users')
        .send(invalidDto)
        .expect(400);

      expect(response.body.message).toContain('email');
    });

    it('should return 409 for duplicate email', async () => {
      const createUserDto = {
        email: 'duplicate@example.com',
        name: 'Test User',
        role: 'USER',
      };

      // Create first user
      await request(app.getHttpServer())
        .post('/api/v1/users')
        .send(createUserDto)
        .expect(201);

      // Try to create duplicate
      await request(app.getHttpServer())
        .post('/api/v1/users')
        .send(createUserDto)
        .expect(409);
    });
  });

  describe('/api/v1/users (GET)', () => {
    it('should return paginated users', async () => {
      // Create test users
      await databaseService.user.createMany({
        data: [
          { email: 'user1@example.com', name: 'User 1', role: 'USER' },
          { email: 'user2@example.com', name: 'User 2', role: 'ADMIN' },
        ],
      });

      const response = await request(app.getHttpServer())
        .get('/api/v1/users')
        .query({ page: 1, limit: 10 })
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.meta).toMatchObject({
        total: 2,
        page: 1,
        limit: 10,
        totalPages: 1,
      });
    });
  });

  describe('CRUD Flow', () => {
    it('should complete full CRUD lifecycle', async () => {
      // CREATE
      const createResponse = await request(app.getHttpServer())
        .post('/api/v1/users')
        .send({
          email: 'crud@example.com',
          name: 'CRUD User',
          role: 'USER',
        })
        .expect(201);

      const userId = createResponse.body.id;

      // READ
      const getResponse = await request(app.getHttpServer())
        .get(`/api/v1/users/${userId}`)
        .expect(200);

      expect(getResponse.body.email).toBe('crud@example.com');

      // UPDATE
      const updateResponse = await request(app.getHttpServer())
        .patch(`/api/v1/users/${userId}`)
        .send({ name: 'Updated CRUD User' })
        .expect(200);

      expect(updateResponse.body.name).toBe('Updated CRUD User');

      // Verify update in database
      const updatedUser = await databaseService.user.findUnique({
        where: { id: userId },
      });
      expect(updatedUser?.name).toBe('Updated CRUD User');

      // DELETE
      await request(app.getHttpServer())
        .delete(`/api/v1/users/${userId}`)
        .expect(200);

      // Verify soft delete
      const deletedUser = await databaseService.user.findUnique({
        where: { id: userId },
      });
      expect(deletedUser?.isActive).toBe(false);
    });
  });
});
```

## Testcontainers — Real PostgreSQL

```typescript
// test/helpers/testcontainers.ts
import { GenericContainer, StartedTestContainer } from 'testcontainers';

export class PostgresTestContainer {
  private container: StartedTestContainer | null = null;

  async start(): Promise<string> {
    this.container = await new GenericContainer('postgres:16-alpine')
      .withEnvironment({
        POSTGRES_USER: 'test',
        POSTGRES_PASSWORD: 'test',
        POSTGRES_DB: 'testdb',
      })
      .withExposedPorts(5432)
      .withStartupTimeout(120000)
      .start();

    const host = this.container.getHost();
    const port = this.container.getMappedPort(5432);

    return `postgresql://test:test@${host}:${port}/testdb`;
  }

  async stop(): Promise<void> {
    if (this.container) {
      await this.container.stop();
    }
  }

  async reset(databaseUrl: string): Promise<void> {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient({
      datasources: {
        db: {
          url: databaseUrl,
        },
      },
    });

    // Get all table names
    const tables = await prisma.$queryRaw<Array<{ tablename: string }>>`
      SELECT tablename FROM pg_tables WHERE schemaname='public'
    `;

    // Truncate all tables
    for (const { tablename } of tables) {
      if (tablename !== '_prisma_migrations') {
        await prisma.$executeRawUnsafe(
          `TRUNCATE TABLE "${tablename}" CASCADE`,
        );
      }
    }

    await prisma.$disconnect();
  }
}

// Usage in test setup
import { PostgresTestContainer } from './helpers/testcontainers';

describe('Integration Tests', () => {
  const postgres = new PostgresTestContainer();
  let databaseUrl: string;

  beforeAll(async () => {
    databaseUrl = await postgres.start();
    process.env.DATABASE_URL = databaseUrl;

    // Run migrations
    const { execSync } = await import('child_process');
    execSync('npx prisma migrate deploy', {
      env: { ...process.env, DATABASE_URL: databaseUrl },
    });
  });

  afterAll(async () => {
    await postgres.stop();
  });

  beforeEach(async () => {
    await postgres.reset(databaseUrl);
  });
});
```
