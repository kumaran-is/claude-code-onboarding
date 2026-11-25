# NestJS 12.x Advanced Testing — CI/CD, Coverage & Troubleshooting

Coverage standards, CI/CD pipeline configuration, testing checklist, troubleshooting guide, performance testing, and snapshot testing for NestJS 12.x with Vitest 5.

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

### Coverage Configuration in vitest.config.ts

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
      // Limits go under `thresholds` (top-level `lines` etc. is a type error and is ignored)
      thresholds: { lines: 90, functions: 90, branches: 80, statements: 90 },
    },
  },
});
```

## CI/CD Integration

### GitHub Actions Workflow

Same command sequence as the NestJS 12.6.0 reference app (each step was run locally there, exit 0); the workflow file
itself was not executed on GitHub. Actions are pinned by commit SHA.

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [develop]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_PASSWORD: ci
          POSTGRES_DB: orders
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 10
        ports:
          - 5432:5432
      redis:
        image: redis:8
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s --health-timeout 5s --health-retries 10
        ports:
          - 6379:6379

    env:
      DATABASE_URL: postgresql://postgres:ci@localhost:5432/orders
      REDIS_URL: redis://localhost:6379

    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Setup Node.js
        uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: '26.13.1'
          cache: 'npm'

      - run: npm ci
      - run: npm audit --audit-level=high
      - run: npx prisma generate          # the generated client is gitignored; tsc needs it
      - run: npm run typecheck            # tsconfig.json: includes specs (the build config does not)
      - run: npm run lint                 # oxlint --type-aware --deny-warnings
      - run: npx vitest run --coverage --reporter=default --reporter=junit --outputFile=reports/unit.xml
      - run: npx prisma migrate deploy
      - run: npm run test:e2e -- --reporter=default --reporter=junit --outputFile=reports/e2e.xml
      - run: npm run build

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5 # v7.1.1
        with:
          files: ./coverage/lcov.info
```

- The CI user and password are throwaway service-container values, not secrets.
- Vitest exits 0 when every test is skipped: the JUnit report gives a countable executed total (`/verify` checks it).

### NPM Scripts

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest watch",
    "test:e2e": "vitest run --config ./vitest.config.e2e.ts",
    "test:e2e:watch": "vitest watch --config ./vitest.config.e2e.ts",
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
- [ ] Database queries are verified against actual PostgreSQL (CI service container or Testcontainers)
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
| **Decorator Metadata Missing** | injected dependency is `undefined` (e.g. `Cannot read properties of undefined (reading 'getAllAndOverride')`) | Set `emitDecoratorMetadata: true` in `tsconfig.json`; Vite 8's Oxc transform reads it, so no SWC plugin is needed (verified on Vitest 5.1.1) |
| **Stale results after a tsconfig change** | tests skipped or old behaviour after editing `tsconfig.json` | `npx vitest --clearCache`: Vitest 5's file-system module cache served stale transforms (20 tests skipped until cleared) |
| **`ERR_REQUIRE_ASYNC_MODULE` under Jest** | Jest cannot load the ESM-only NestJS 12 packages | Use Vitest; NestJS docs say Jest loads them only on Node >= 24.9 (CommonJS projects) |
| **Module Not Found** | `Cannot find module '../app.module'` (TS2307) | ESM with `nodenext`: relative imports need the `.js` extension (`'./app.module.js'`) |
| **Path alias not found** | `Cannot find module '@/...'` | Add the alias to `resolve.alias` in the vitest config matching tsconfig `paths` |
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
