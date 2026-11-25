# NestJS 12.x Integration Testing — Setup, E2E and Real Services

Integration and E2E test setup for NestJS 12.x on Fastify: the production `configureApp()`, `app.inject()`, real
PostgreSQL 18 and Redis 8, Standard Schema (Zod) validation and the negative cases every API must prove.

Verified 2026-11-24 on NestJS 12.6.0, Fastify 5.12.8, Vitest 5.1.1, TypeScript 6.0.3, Node 26.13.1, Prisma 7.10.1,
BullMQ 6.7.10, PostgreSQL 18 and Redis 8 in Docker: 23 of 23 integration + E2E tests passed (JSON report), and each
planted bug below made the expected tests fail. Source app: the reference behind `nestjs-production-baseline.md`.

## Vitest configuration — `vitest.config.e2e.ts`

```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    root: './',
    include: ['test/**/*.e2e-spec.ts', 'test/**/*.int-spec.ts'],
    fileParallelism: false,
    testTimeout: 20_000,
    hookTimeout: 30_000,
    // ConfigModule validates when AppModule is IMPORTED: env must exist at load time.
    // DATABASE_URL and REDIS_URL come from the shell/CI (real PostgreSQL and Redis).
    env: {
      NODE_ENV: 'test',
      JWT_ISSUER: 'https://issuer.test',
      JWT_AUDIENCE: 'orders-api',
      JWT_JWKS_URL: 'https://issuer.test/.well-known/jwks.json',
      THROTTLE_LIMIT: '20',
      THROTTLE_TTL_MS: '60000',
      BODY_LIMIT_BYTES: '2048',
    },
  },
});
```

- `ConfigModule.forRoot({ validationSchema })` validates when `AppModule` is **imported**: set test env in `test.env`
  (or a `setupFiles` module). Assigning `process.env` inside `beforeAll` is too late and the import throws.
- `fileParallelism: false` (or `maxWorkers: 1`) serialises suites that share a database; `test.poolOptions` no longer exists.
- No SWC plugin (Vite 8's Oxc transform honours `emitDecoratorMetadata`). After a `tsconfig.json` change run
  `npx vitest --clearCache`: Vitest 5's module cache served stale transforms and skipped 20 tests until cleared.
- Build the app through the same `configureApp()` as `main.ts`; re-declaring pipes or prefixes in a spec lets test and
  production drift.

## Real services, not mocks

`DATABASE_URL` and `REDIS_URL` come from the shell or CI. Locally:

```bash
# DB_USER / DB_PASSWORD: local-only values exported in your shell (never committed)
docker run -d --name orders-pg -e POSTGRES_USER="$DB_USER" -e POSTGRES_PASSWORD="$DB_PASSWORD" -e POSTGRES_DB=orders -p 55432:5432 postgres:18
docker run -d --name orders-redis -p 56379:6379 redis:8
export DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:55432/orders REDIS_URL=redis://localhost:56379
npx prisma migrate deploy && npm run test:e2e
```

In GitHub Actions use `services:` containers (`postgres:18`, `redis:8`) with health checks; see
`nestjs-testing-ci-troubleshooting.md`. A Testcontainers-based `globalSetup` is an alternative when CI has no service
containers (below).

## Verified E2E suite — `test/app.e2e-spec.ts`

Only the JWKS key source is overridden (`JWT_KEY_RESOLVER` → a local JWKS); guard, verifier, Standard Schema pipe,
serializer, throttler, BullMQ worker and gateway are the production ones.

```typescript
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

## Repository against PostgreSQL — `test/orders.int-spec.ts`

```typescript
import { randomUUID } from 'node:crypto';
import { afterAll, describe, expect, it } from 'vitest';
import { PrismaService } from '../src/database/prisma.service.js';
import { OrdersRepository } from '../src/orders/orders.repository.js';

const databaseUrl = process.env['DATABASE_URL'];
if (databaseUrl === undefined || databaseUrl === '') throw new Error('DATABASE_URL is required for integration tests');

describe('OrdersRepository against PostgreSQL', () => {
  const prisma = new PrismaService(databaseUrl);
  const repo = new OrdersRepository(prisma);
  const tenantA = randomUUID();
  const tenantB = randomUUID();

  afterAll(async () => {
    await prisma.onModuleDestroy();
  });

  it('persists an order and reads it back in the same tenant', async () => {
    const created = await repo.create(tenantA, { sku: 'SKU-INT', quantity: 3 });
    const found = await repo.findById(tenantA, created.id);
    expect(found?.quantity).toBe(3);
  });

  it('never returns another tenant order (by id or in a list)', async () => {
    const created = await repo.create(tenantA, { sku: 'SKU-INT', quantity: 1 });
    expect(await repo.findById(tenantB, created.id)).toBeNull();
    expect((await repo.list(tenantB, 50)).map((o) => o.id)).not.toContain(created.id);
  });

  it('rejects a non-uuid tenant at the database (uuid column)', async () => {
    await expect(repo.create('not-a-uuid', { sku: 'SKU-INT', quantity: 1 })).rejects.toThrow();
  });
});
```

## Results and planted-bug controls (2026-11-24)

| Check | Result |
|---|---|
| `tsc --noEmit -p tsconfig.json` (specs included) | exit 0 |
| `oxlint --type-aware --deny-warnings src/ test/` | exit 0 |
| `vitest run` (unit) | 9 / 9 passed |
| `vitest run --config ./vitest.config.e2e.ts` | 23 / 23 passed |

| Planted bug | Tests that failed |
|---|---|
| tenant filter removed from the repository | 2 of 23 (cross-tenant get and list) |
| `z.strictObject` → `z.object` on the request schema | 2 of 23 (smuggled `tenantId` accepted) |
| serializer interceptor removed | 1 of 23 (`passwordHash` leaked) |
| audience check removed from the verifier | 1 of 23 e2e, 1 of 9 unit |
| roles check disabled in the guard | 1 of 23 (403 case) |
| `emitDecoratorMetadata: false` | every e2e test (class-typed injection resolved `undefined`) |

`app.inject()` (Fastify light-my-request) needs no listening port. `supertest(app.getHttpServer())` also works after
`await app.getHttpAdapter().getInstance().ready()`, but adds a dependency for no extra coverage.

## Testcontainers alternative (`globalSetup`) — NOT RUN

Not run in the 2026-11-24 verification (Docker service containers were used instead). Start the database **before**
any spec imports `AppModule`, from a Vitest `globalSetup`, and hand the URL to the workers with `provide`:

```typescript
// test/global-setup.ts  (vitest.config.e2e.ts: test.globalSetup: ['./test/global-setup.ts'])
import { execFileSync } from 'node:child_process';
import { GenericContainer, type StartedTestContainer } from 'testcontainers';
import type { TestProject } from 'vitest/node';

let postgres: StartedTestContainer;

export async function setup(project: TestProject): Promise<void> {
  postgres = await new GenericContainer('postgres:18')
    .withEnvironment({ POSTGRES_PASSWORD: 'test', POSTGRES_DB: 'testdb' })
    .withExposedPorts(5432)
    .start();
  const url = `postgresql://postgres:test@${postgres.getHost()}:${postgres.getMappedPort(5432)}/testdb`;
  execFileSync('npx', ['prisma', 'migrate', 'deploy'], { env: { ...process.env, DATABASE_URL: url }, stdio: 'inherit' });
  project.provide('databaseUrl', url); // read in a setupFiles module with inject('databaseUrl') and copy to process.env
}

export async function teardown(): Promise<void> {
  await postgres.stop();
}
```

- Prisma 7 has no `datasources` constructor option: a test client is `new PrismaClient({ adapter: new PrismaPg({ connectionString: url }) })`
  from the generated client (`src/generated/prisma/client.js`).
- Isolate tests with per-test unique tenant ids (as the suite above does) rather than truncating tables between tests;
  it keeps suites independent and works on a shared CI database.

