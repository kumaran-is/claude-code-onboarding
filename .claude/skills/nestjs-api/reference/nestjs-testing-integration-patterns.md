# NestJS 12.x Integration Testing — Patterns & Auth Testing

Integration test naming conventions, validation pipe testing, authentication/authorization testing, transaction testing, and common query patterns (pagination, sorting, filtering) for NestJS 12.x.

## Integration Test Naming Conventions

```typescript
// File naming
users.e2e-spec.ts            // Integration test for users feature
auth.e2e-spec.ts             // Integration test for auth feature

// Test structure
describe('Feature API (e2e)', () => {
  describe('/api/v1/resource (POST)', () => {
    it('should create resource successfully', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/resource')
        .send(createDto)
        .expect(201);

      expect(response.body).toMatchObject(expectedShape);
    });
  });

  describe('/api/v1/resource/:id (GET)', () => {
    it('should return 404 for non-existent resource', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/resource/invalid-id')
        .expect(404);
    });
  });
});
```

## Testing Validation Pipes

The global `StandardSchemaValidationPipe` answers 400 with `message: string[]`, one `"path: message"` entry per issue
(verified on `@nestjs/common` 12.6.0). Assert on the entries, not on substrings of the whole body, and check the input
is not echoed. `app.inject()` (Fastify) needs no listening port; supertest works too.
`adminToken()` signs a short-lived test JWT with `jose` against a local JWKS, as the e2e spec in `nestjs-production-baseline.md` does.

```typescript
describe('Validation', () => {
  const post = async (body: unknown) =>
    app.inject({
      method: 'POST',
      url: '/api/v1/users',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${await adminToken()}` },
      payload: JSON.stringify(body),
    });

  it('rejects missing required fields with one entry per field', async () => {
    const res = await post({ name: 'Test User' }); // missing email and role
    expect(res.statusCode).toBe(400);
    expect(res.json<{ message: string[] }>().message).toEqual(
      expect.arrayContaining([expect.stringMatching(/^email: /), expect.stringMatching(/^role: /)]),
    );
  });

  it('rejects invalid field types without echoing the input', async () => {
    const res = await post({ email: 'test@example.com', name: '<script>x</script>'.repeat(20), role: 'USER' });
    expect(res.statusCode).toBe(400);
    expect(res.json<{ message: string[] }>().message).toEqual(
      expect.arrayContaining([expect.stringMatching(/^name: /)]),
    );
    expect(res.body).not.toContain('<script>');
  });

  it('rejects unknown fields (z.strictObject), so a smuggled tenantId never reaches the handler', async () => {
    const res = await post({ email: 'test@example.com', name: 'Test User', role: 'USER', tenantId: 'other' });
    expect(res.statusCode).toBe(400);
    expect(res.json<{ message: string[] }>().message.join(' ')).toMatch(/tenantId/);
  });
});
```

Positive control: change the request schema from `z.strictObject` to `z.object` and the unknown-field test must fail
(it did in the reference app: 2 tests failed). In a class-validator codebase the same test passes only with
`forbidNonWhitelisted: true`; `whitelist: true` alone strips the field and answers 201.

## Testing Authentication/Authorization

```typescript
describe('Protected Endpoints', () => {
  let authToken: string;
  let userId: string;

  beforeEach(async () => {
    // Create user and get token
    const signupResponse = await request(app.getHttpServer())
      .post('/api/v1/auth/signup')
      .send({
        email: 'auth@example.com',
        password: 'SecurePassword123!',
        name: 'Auth User',
      })
      .expect(201);

    authToken = signupResponse.body.accessToken;
    userId = signupResponse.body.user.id;
  });

  it('should return 401 for unauthenticated requests', async () => {
    await request(app.getHttpServer())
      .get('/api/v1/users/profile')
      .expect(401);
  });

  it('should allow access with valid token', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/users/profile')
      .set('Authorization', `Bearer ${authToken}`)
      .expect(200);

    expect(response.body.id).toBe(userId);
  });

  it('should return 403 for insufficient permissions', async () => {
    await request(app.getHttpServer())
      .post('/api/v1/admin/settings')
      .set('Authorization', `Bearer ${authToken}`)
      .send({ key: 'value' })
      .expect(403);
  });
});
```

## Testing Database Transactions

```typescript
describe('Transactional Operations', () => {
  it('should rollback on error in transaction', async () => {
    // Attempt to create user with duplicate email in transaction
    const dto = {
      email: 'transaction@example.com',
      name: 'Transaction User',
      role: 'USER',
    };

    // Create first user
    await request(app.getHttpServer())
      .post('/api/v1/users')
      .send(dto)
      .expect(201);

    // Attempt to create duplicate - should fail and rollback
    await request(app.getHttpServer())
      .post('/api/v1/users/batch')
      .send({
        users: [
          dto, // duplicate email
          { email: 'another@example.com', name: 'Another User', role: 'USER' },
        ],
      })
      .expect(409);

    // Verify second user was not created
    const users = await databaseService.user.findMany({
      where: { email: 'another@example.com' },
    });

    expect(users).toHaveLength(0);
  });
});
```

## Running Integration Tests

```bash
# Run all integration tests
npm run test:e2e

# Run in watch mode
npm run test:e2e:watch

# Run specific integration test
npm run test:e2e users.e2e-spec.ts

# Run with environment variables
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/testdb npm run test:e2e
```

## NPM Scripts

```json
{
  "scripts": {
    "test:e2e": "vitest run --config vitest.e2e.config.ts",
    "test:e2e:watch": "vitest watch --config vitest.e2e.config.ts"
  }
}
```

## Common Integration Test Patterns

### Testing Pagination

```typescript
it('should paginate results correctly', async () => {
  // Create 25 users
  await databaseService.user.createMany({
    data: Array.from({ length: 25 }, (_, i) => ({
      email: `user${i}@example.com`,
      name: `User ${i}`,
      role: 'USER',
    })),
  });

  // Request page 2 with limit 10
  const response = await request(app.getHttpServer())
    .get('/api/v1/users')
    .query({ page: 2, limit: 10 })
    .expect(200);

  expect(response.body.data).toHaveLength(10);
  expect(response.body.meta).toMatchObject({
    total: 25,
    page: 2,
    limit: 10,
    totalPages: 3,
  });
});
```

### Testing Sorting

```typescript
it('should sort users by name ascending', async () => {
  await databaseService.user.createMany({
    data: [
      { email: 'c@example.com', name: 'Charlie', role: 'USER' },
      { email: 'a@example.com', name: 'Alice', role: 'USER' },
      { email: 'b@example.com', name: 'Bob', role: 'USER' },
    ],
  });

  const response = await request(app.getHttpServer())
    .get('/api/v1/users')
    .query({ sortBy: 'name', order: 'asc' })
    .expect(200);

  const names = response.body.data.map((u) => u.name);
  expect(names).toEqual(['Alice', 'Bob', 'Charlie']);
});
```

### Testing Filtering

```typescript
it('should filter users by role', async () => {
  await databaseService.user.createMany({
    data: [
      { email: 'admin1@example.com', name: 'Admin 1', role: 'ADMIN' },
      { email: 'user1@example.com', name: 'User 1', role: 'USER' },
      { email: 'admin2@example.com', name: 'Admin 2', role: 'ADMIN' },
    ],
  });

  const response = await request(app.getHttpServer())
    .get('/api/v1/users')
    .query({ role: 'ADMIN' })
    .expect(200);

  expect(response.body.data).toHaveLength(2);
  expect(response.body.data.every((u) => u.role === 'ADMIN')).toBe(true);
});
```

---

**Key Takeaways:**

1. Use Testcontainers for real PostgreSQL in integration tests
2. Bootstrap full NestJS app with Fastify adapter
3. Run migrations before tests, clean database between tests
4. Use supertest for HTTP request testing
5. Test full CRUD lifecycle and error scenarios
6. Verify database state after operations
7. Test validation, authentication, authorization in integration layer
8. Use realistic timeouts (60s) for container startup
9. Call `await app.init()` and `await app.getHttpAdapter().getInstance().ready()` before tests
10. Always disconnect from database and stop containers in `afterAll`
