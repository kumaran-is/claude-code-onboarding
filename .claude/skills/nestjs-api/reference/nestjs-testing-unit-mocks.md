# NestJS 12.x Unit Testing — Mock Patterns & Conventions

Mocking strategies, naming conventions, and test execution for NestJS 12.x unit tests with Vitest. Covers Prisma client mocks, cache mocks, HTTP service mocks with nock, and ConfigService mocks.

## Mocking Patterns

### Prisma Client Mocking

```typescript
// test/mocks/prisma.mock.ts
import { vi } from 'vitest';
import type { PrismaClient } from '../../src/generated/prisma/client.js';
import { mockDeep, mockReset, DeepMockProxy } from 'vitest-mock-extended';

export type MockPrismaClient = DeepMockProxy<PrismaClient>;

export const createMockPrismaClient = (): MockPrismaClient => {
  return mockDeep<PrismaClient>();
};

// Usage
import { createMockPrismaClient } from './mocks/prisma.mock.js';

describe('Service with Prisma', () => {
  let mockPrisma: MockPrismaClient;

  beforeEach(() => {
    mockPrisma = createMockPrismaClient();
  });

  it('should query users', async () => {
    // A complete row from the test factory (nestjs-testing-unit-controllers.md) — no `as any`
    mockPrisma.user.findMany.mockResolvedValue([
      { ...UserFactory.make({ email: 'test@example.com' }).build(), id: '1', createdAt: new Date(), updatedAt: new Date() },
    ]);

    const result = await mockPrisma.user.findMany();
    expect(result).toHaveLength(1);
  });
});
```

### Redis/Cache Mocking

```typescript
// test/mocks/cache.mock.ts
import { vi } from 'vitest';

export const createMockCacheService = () => ({
  get: vi.fn(),
  set: vi.fn(),
  del: vi.fn(),
  delPattern: vi.fn(),
  exists: vi.fn(),
  ttl: vi.fn(),
  keys: vi.fn(),
  flushAll: vi.fn(),
});

// Usage
const mockCache = createMockCacheService();
mockCache.get.mockResolvedValue({ id: '1', name: 'Cached User' });
```

### External HTTP Service Mocking with nock

```typescript
// test/external-api.spec.ts
import nock from 'nock';
import { describe, it, expect, afterEach } from 'vitest';
import { ExternalApiService } from '../services/external-api.service.js';

describe('ExternalApiService', () => {
  afterEach(() => {
    nock.cleanAll();
  });

  it('should fetch data from external API', async () => {
    const mockResponse = { id: 1, data: 'test' };

    nock('https://api.example.com')
      .get('/endpoint')
      .reply(200, mockResponse);

    const service = new ExternalApiService();
    const result = await service.fetchData();

    expect(result).toEqual(mockResponse);
  });

  it('should handle API errors', async () => {
    nock('https://api.example.com').get('/endpoint').reply(500, {
      error: 'Internal Server Error',
    });

    const service = new ExternalApiService();

    await expect(service.fetchData()).rejects.toThrow();
  });

  it('should verify request headers', async () => {
    nock('https://api.example.com', {
      reqheaders: {
        authorization: 'Bearer test-token',
        'content-type': 'application/json',
      },
    })
      .post('/endpoint', { name: 'test' })
      .reply(201, { success: true });

    const service = new ExternalApiService();
    const result = await service.createResource({ name: 'test' });

    expect(result).toEqual({ success: true });
  });
});
```

### ConfigService Mocking

```typescript
// test/mocks/config.mock.ts
import { vi } from 'vitest';

export const createMockConfigService = (values: Record<string, any> = {}) => ({
  get: vi.fn((key: string) => values[key]),
  getOrThrow: vi.fn((key: string) => {
    if (!(key in values)) {
      throw new Error(`Configuration key ${key} not found`);
    }
    return values[key];
  }),
});

// Usage
const mockConfig = createMockConfigService({
  DATABASE_URL: 'postgresql://test',
  JWT_SECRET: 'test-secret',
  PORT: 3000,
});
```

## Naming Conventions

```typescript
// File naming
users.service.spec.ts        // Unit test
users.e2e-spec.ts            // Integration test
circuit-breaker.spec.ts      // Component test

// Test structure
describe('ServiceName', () => {
  describe('methodName', () => {
    it('should return X when Y', async () => {
      // Arrange
      const input = { ... };
      mockService.method.mockResolvedValue(expectedOutput);

      // Act
      const result = await service.methodName(input);

      // Assert
      expect(result).toEqual(expectedOutput);
      expect(mockService.method).toHaveBeenCalledWith(input);
    });

    it('should throw NotFoundException when entity does not exist', async () => {
      mockRepository.findUnique.mockResolvedValue(null);

      await expect(service.methodName('invalid-id')).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
```

## Running Unit Tests

```bash
# Run all unit tests
npm run test

# Run in watch mode
npm run test:watch

# Run specific test file
npm run test users.service.spec.ts

# Run with coverage
npm run test:cov
```

---

**Key Takeaways:**

1. Mock all external dependencies at service boundaries
2. Use `Test.createTestingModule` with `useValue` for mock injection
3. Reset mocks in `beforeEach` to prevent test pollution
4. Test both happy paths and error scenarios
5. Use factories for consistent test data generation
6. Follow Arrange-Act-Assert pattern
7. Maintain 90% line coverage, 80% branch coverage
8. Use descriptive test names that explain the scenario
