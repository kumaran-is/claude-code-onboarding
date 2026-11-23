# TDD Patterns — NestJS 11 / TypeScript (Vitest)

NestJS services in this toolkit test with **Vitest** on the **Fastify** adapter. This file covers the
red-green loop only. Configuration (`vitest.config.mts`, `unplugin-swc`, coverage `thresholds`), deep mocks
and the Testcontainers e2e setup are owned by the `nestjs-api` skill:
`nestjs-api/reference/nestjs-testing-unit-basics.md`, `nestjs-testing-unit-mocks.md`,
`nestjs-testing-integration-setup.md`.

## Unit Test (service, mocked dependencies)

```typescript
// src/modules/users/user.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { ConflictException } from '@nestjs/common';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UserService } from './user.service';
import { UserRepository } from './user.repository';

describe('UserService', () => {
  let service: UserService;
  const repository = { findByEmail: vi.fn(), save: vi.fn() };

  beforeEach(async () => {
    vi.clearAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      providers: [UserService, { provide: UserRepository, useValue: repository }],
    }).compile();
    service = module.get(UserService);
  });

  it('throws ConflictException when the email already exists', async () => {
    repository.findByEmail.mockResolvedValue(existingUser());

    await expect(service.createUser(newUserDto())).rejects.toThrow(ConflictException);
    expect(repository.save).not.toHaveBeenCalled();
  });
});
```

## E2E Test (Fastify, `app.inject`)

```typescript
// test/users.e2e-spec.ts
import { Test } from '@nestjs/testing';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { AppModule } from '../src/app.module';

describe('Users (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = moduleRef.createNestApplication<NestFastifyApplication>(new FastifyAdapter());
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  afterAll(() => app.close());

  it('POST /users with a valid body and token returns 201', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/users',
      payload: validCreateUserDto(),
      headers: { authorization: `Bearer ${adminToken()}` },
    });
    expect(res.statusCode).toBe(201);
    expect(res.json().email).toBe('test@example.com');
  });

  it('POST /users without a token returns 401', async () => {
    const res = await app.inject({ method: 'POST', url: '/users', payload: validCreateUserDto() });
    expect(res.statusCode).toBe(401);
  });
});
```

Every protected route gets the negative cases (401, 403, 404, 400) — see `nestjs-api` for the full list.

## Mocking Rules

- `vi.fn()` for method mocks on injected dependencies; `vi.spyOn()` for partial mocks on real instances
- `mockResolvedValue` / `mockRejectedValue(new SomeException())` for async success and error paths
- `vi.clearAllMocks()` in `beforeEach` so call counts do not leak between tests
- Mock only external boundaries (repository, HTTP client, queue) — never the class under test

## RED-GREEN Example

```bash
# RED — run the one new test and see it fail for the right reason
npx vitest run src/modules/users/user.service.spec.ts -t "throws ConflictException"; echo "exit=$?"
# Expected: exit=1, failure names ConflictException (not a compile or import error)

# GREEN — implement, re-run the same command
npx vitest run src/modules/users/user.service.spec.ts -t "throws ConflictException"; echo "exit=$?"
# Expected: exit=0

# Full suite before claiming done
npx vitest run; echo "exit=$?"
```

`-t` is Vitest's `--testNamePattern` shorthand (SOURCE-PROVEN against the vitest 4.1 CLI definition).
