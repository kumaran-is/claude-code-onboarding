# NestJS 11.x Advanced Testing — CI/CD, Coverage & Troubleshooting

Coverage standards, CI/CD pipeline configuration, testing checklist, troubleshooting guide, performance testing, and snapshot testing for NestJS 11.x with Vitest.

## Coverage Standards

| Metric | Minimum | Tool | Configuration |
|--------|---------|------|---------------|
| **Lines** | 90% | @vitest/coverage-v8 | `coverage.lines: 90` |
| **Functions** | 90% | @vitest/coverage-v8 | `coverage.functions: 90` |
| **Branches** | 80% | @vitest/coverage-v8 | `coverage.branches: 80` |
| **Statements** | 90% | @vitest/coverage-v8 | `coverage.statements: 90` |

### Running Coverage

```bash
# Generate coverage report
npm run test:cov

# View HTML report
open coverage/index.html

# Check coverage thresholds (fails if below minimum)
npm run test:cov -- --coverage.thresholds.lines=90
```

### Coverage Configuration in vitest.config.mts

```typescript
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      include: ['src/**/*.ts'],
      exclude: [
        'src/**/*.spec.ts',
        'src/**/*.e2e-spec.ts',
        'src/main.ts',
        'src/**/*.module.ts',
        'src/**/*.dto.ts',
        'src/**/*.entity.ts',
        'src/migrations/**',
      ],
      // Vitest 1+: limits under `thresholds` (top-level `lines` etc. is a type error and is ignored)
      thresholds: { lines: 90, functions: 90, branches: 80, statements: 90 },
    },
  },
});
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '24'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run Prisma migrations
        run: npx prisma migrate deploy
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb

      - name: Run unit tests
        run: npm run test

      - name: Run integration tests
        run: npm run test:e2e
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb

      - name: Generate coverage
        run: npm run test:cov

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/lcov.info
```

### NPM Scripts

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest watch",
    "test:e2e": "vitest run --config vitest.e2e.config.mts",
    "test:e2e:watch": "vitest watch --config vitest.e2e.config.mts",
    "test:cov": "vitest run --coverage",
    "test:debug": "vitest --inspect-brk --no-file-parallelism"
  }
}
```

## Testing Checklist

- [ ] All services have unit tests with mocked dependencies
- [ ] All controllers have unit tests with mocked services
- [ ] CRUD operations have integration tests with real database
- [ ] DTOs have validation tests (invalid inputs trigger 400 errors)
- [ ] Error scenarios are tested (404, 409, 500)
- [ ] Circuit breaker patterns are tested (happy path, open, half-open, fallback)
- [ ] Request context propagation is verified
- [ ] External API calls are mocked or use contract tests
- [ ] Database queries are verified against actual PostgreSQL (Testcontainers)
- [ ] Coverage thresholds are met (90% lines, 80% branches)
- [ ] Tests run in CI/CD pipeline
- [ ] Test data factories are used for entity creation
- [ ] Cleanup happens between tests (database reset, mock reset)
- [ ] Async operations use proper async/await patterns
- [ ] No test pollution (tests don't depend on execution order)

## Troubleshooting

| Issue | Symptom | Fix |
|-------|---------|-----|
| **DI Resolution Failed** | `Nest can't resolve dependencies` | Verify all providers in `providers` array; check imports in module; ensure mocked service uses correct token |
| **Fastify Not Ready** | `app.getHttpServer() returns undefined` | Call `await app.init()` and `await app.getHttpAdapter().getInstance().ready()` before tests |
| **Prisma Connection Error** | `Can't reach database server` | Check `DATABASE_URL` is set; verify Testcontainer is started; run migrations before tests |
| **Test Timeout** | `Test timed out after 5000ms` | Increase `testTimeout` in vitest config; ensure async operations complete; check for unresolved promises |
| **Decorator Metadata Missing** | injected dependency is `undefined` (e.g. `Cannot read properties of undefined (reading 'getAllAndOverride')`) | Set `emitDecoratorMetadata: true` in the tsconfig the runner reads (both `unplugin-swc` and Vite 8's Oxc transform read it); keep `unplugin-swc` as in `nestjs-config-npm-ts.md` |
| **Module Not Found** | `Cannot find module '@/...'` | Add path alias to `resolve.alias` in vitest config matching tsconfig paths |
| **Coverage Threshold Failed** | `Coverage for lines (85%) does not meet threshold (90%)` | Write missing tests; exclude irrelevant files in `coverage.exclude` |
| **Database State Pollution** | Tests fail when run together but pass individually | Reset database in `beforeEach`; ensure transactions rollback; use `vi.clearAllMocks()` |
| **Mock Not Called** | `expect(mock).toHaveBeenCalled()` fails | Verify mock is injected correctly; check if actual implementation is called instead; reset mocks in `beforeEach` |
| **Async Assertion Failure** | Test passes but assertion never runs | Always `await` async test functions; use `expect(...).rejects.toThrow()` for error tests |

### Debugging Tests

```bash
# Run tests in debug mode with Chrome DevTools
npm run test:debug

# Run single test file in debug mode
npm run test:debug users.service.spec.ts

# Run tests with increased timeout
vitest run --testTimeout=120000

# Run tests without threads for easier debugging
vitest run --no-file-parallelism --maxWorkers=1
```

### Common Mock Issues

```typescript
// ❌ WRONG: Mock not properly injected
const mockService = { method: vi.fn() };
// Missing useValue provider registration

// ✅ CORRECT: Properly registered mock
const module = await Test.createTestingModule({
  providers: [
    ServiceUnderTest,
    {
      provide: DependencyService,
      useValue: mockService,
    },
  ],
}).compile();
```

```typescript
// ❌ WRONG: Not resetting mocks between tests
beforeEach(() => {
  // Missing vi.clearAllMocks()
});

// ✅ CORRECT: Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks();
});
```

```typescript
// ❌ WRONG: Forgetting to await async operations
it('should do something', () => {
  service.asyncMethod(); // Missing await
  expect(result).toBe(expected); // Will fail
});

// ✅ CORRECT: Always await async operations
it('should do something', async () => {
  const result = await service.asyncMethod();
  expect(result).toBe(expected);
});
```

## Performance Testing

### Load Testing with autocannon

```typescript
// test/load/users.load.ts
import autocannon from 'autocannon';
import { Test, TestingModule } from '@nestjs/testing';
import { NestFastifyApplication, FastifyAdapter } from '@nestjs/platform-fastify';
import { AppModule } from '@/app.module';

describe('Load Tests', () => {
  let app: NestFastifyApplication;
  let url: string;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );

    await app.init();
    await app.getHttpAdapter().getInstance().ready();

    const address = await app.listen(0); // Random port
    url = address;
  });

  afterAll(async () => {
    await app.close();
  });

  it('should handle 1000 requests/second', async () => {
    const result = await autocannon({
      url: `${url}/api/v1/health`,
      connections: 100,
      duration: 10,
    });

    expect(result.requests.average).toBeGreaterThan(1000);
    expect(result.errors).toBe(0);
  });
});
```

## Snapshot Testing

```typescript
describe('API Response Snapshots', () => {
  it('should match user response snapshot', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/users/123')
      .expect(200);

    expect(response.body).toMatchSnapshot({
      id: expect.any(String),
      createdAt: expect.any(String),
      updatedAt: expect.any(String),
    });
  });
});
```

---

**Key Takeaways:**

1. Test circuit breaker states: CLOSED, OPEN, HALF_OPEN with timeout transitions
2. Verify request context propagation with AsyncLocalStorage across async operations
3. Maintain 90% line coverage, 80% branch coverage
4. Use GitHub Actions with PostgreSQL service for CI/CD
5. Always reset database and mocks between tests to prevent pollution
6. Use `vi.clearAllMocks()` in `beforeEach` hooks
7. Increase `testTimeout` for integration tests (60s recommended)
8. Debug with `--inspect-brk` flag and Chrome DevTools
9. Use autocannon for load testing critical endpoints
10. Upload coverage reports to Codecov for tracking over time
