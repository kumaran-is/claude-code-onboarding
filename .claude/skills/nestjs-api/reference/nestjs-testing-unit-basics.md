# NestJS 12.x Unit Testing — Basics & Service Tests

Unit testing setup and service test patterns for NestJS 12.x with Vitest 5, TypeScript 6.0, and Prisma 7. Covers Vitest configuration, test categories, and isolated service testing with mocked dependencies.

## Test Categories

| Category | Share | Setup | Use When |
|----------|-------|-------|----------|
| **Unit Tests** | 70-80% | `Test.createTestingModule` with mocked providers | Testing individual services, controllers, guards in isolation |
| **Integration Tests** | 15-25% | Full NestJS app (`configureApp()` + `app.inject()`) against real PostgreSQL | Testing full request/response flow, database interactions, multi-layer integration |
| **Contract Tests** | 5-10% | External API client verification with nock/msw | Verifying external service integrations, API contracts |

## Vitest Configuration for Unit Tests

### vitest.config.ts

Use the verified unit config in `nestjs-templates-infrastructure.md` (Vitest 5.1.1, no SWC plugin, coverage
`thresholds`; verified 2026-11-24 on NestJS 12.6.0, 9 of 9 unit tests). Fixes to older configs found here before:

- Coverage limits live under `coverage.thresholds` (`{ lines, functions, branches, statements }`). Top-level
  `coverage.lines` no longer exists — `tsc` reports `'lines' does not exist in type 'CoverageOptions'` and the limits
  were never enforced.
- `test.poolOptions` was removed in Vitest 4; use top-level `fileParallelism` / `maxWorkers`.
- `unplugin-swc` is no longer needed: Vite 8's Oxc transform honours `emitDecoratorMetadata`. Keep one test that
  resolves a class-typed constructor dependency through `Test.createTestingModule` (it fails if metadata is lost).
- After a `tsconfig.json` change run `npx vitest --clearCache` (Vitest 5's module cache can serve stale transforms).

## Verified Service Spec (NestJS 12.6.0)

DI through `Test.createTestingModule`, a BullMQ queue token, the 404 `errorCode`, and the
`StandardSchemaSerializerInterceptor` contract (strips undeclared fields, fails loudly on a broken response). Ran
2026-11-24: part of 9 of 9 passing unit tests.

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

## Service Unit Test Pattern (mocking style)

The example below shows the broader mocking style; its imports are adapted to ESM (`.js` extensions, no directory
imports) and Prisma 7 generated types.

```typescript
// src/features/users/users.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { UsersService } from './users.service.js';
import { DatabaseService } from '@/core/database/database.service.js';
import { CacheService } from '@/core/cache/cache.service.js';
import type { CreateUserDto, UpdateUserDto } from './dto/index.js'; // ESM: no directory imports
import type { User } from '../../generated/prisma/client.js'; // prisma-client generator output, not @prisma/client
import { NotFoundException, ConflictException } from '@nestjs/common';

describe('UsersService', () => {
  let service: UsersService;
  let databaseService: DatabaseService;
  let cacheService: CacheService;

  const mockUser: User = {
    id: '123e4567-e89b-12d3-a456-426614174000',
    email: 'test@example.com',
    name: 'Test User',
    role: 'USER',
    isActive: true,
    createdAt: new Date('2024-01-01'),
    updatedAt: new Date('2024-01-01'),
  };

  const mockDatabaseService = {
    user: {
      create: vi.fn(),
      findUnique: vi.fn(),
      findMany: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      count: vi.fn(),
    },
    $transaction: vi.fn((callback) => callback(mockDatabaseService)),
  };

  const mockCacheService = {
    get: vi.fn(),
    set: vi.fn(),
    del: vi.fn(),
    delPattern: vi.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        {
          provide: DatabaseService,
          useValue: mockDatabaseService,
        },
        {
          provide: CacheService,
          useValue: mockCacheService,
        },
      ],
    }).compile();

    service = module.get<UsersService>(UsersService);
    databaseService = module.get<DatabaseService>(DatabaseService);
    cacheService = module.get<CacheService>(CacheService);

    // Reset mocks between tests
    vi.clearAllMocks();
  });

  describe('create', () => {
    it('should create a new user successfully', async () => {
      const createUserDto: CreateUserDto = {
        email: 'test@example.com',
        name: 'Test User',
        role: 'USER',
      };

      mockDatabaseService.user.findUnique.mockResolvedValue(null);
      mockDatabaseService.user.create.mockResolvedValue(mockUser);

      const result = await service.create(createUserDto);

      expect(result).toEqual(mockUser);
      expect(mockDatabaseService.user.findUnique).toHaveBeenCalledWith({
        where: { email: createUserDto.email },
      });
      expect(mockDatabaseService.user.create).toHaveBeenCalledWith({
        data: createUserDto,
      });
      expect(mockCacheService.delPattern).toHaveBeenCalledWith('users:*');
    });

    it('should throw ConflictException when email already exists', async () => {
      const createUserDto: CreateUserDto = {
        email: 'test@example.com',
        name: 'Test User',
        role: 'USER',
      };

      mockDatabaseService.user.findUnique.mockResolvedValue(mockUser);

      await expect(service.create(createUserDto)).rejects.toThrow(
        ConflictException,
      );
      expect(mockDatabaseService.user.create).not.toHaveBeenCalled();
    });
  });

  describe('findOne', () => {
    it('should return a user when found in cache', async () => {
      const userId = mockUser.id;
      mockCacheService.get.mockResolvedValue(mockUser);

      const result = await service.findOne(userId);

      expect(result).toEqual(mockUser);
      expect(mockCacheService.get).toHaveBeenCalledWith(`user:${userId}`);
      expect(mockDatabaseService.user.findUnique).not.toHaveBeenCalled();
    });

    it('should return a user from database when not in cache', async () => {
      const userId = mockUser.id;
      mockCacheService.get.mockResolvedValue(null);
      mockDatabaseService.user.findUnique.mockResolvedValue(mockUser);

      const result = await service.findOne(userId);

      expect(result).toEqual(mockUser);
      expect(mockCacheService.get).toHaveBeenCalledWith(`user:${userId}`);
      expect(mockDatabaseService.user.findUnique).toHaveBeenCalledWith({
        where: { id: userId },
      });
      expect(mockCacheService.set).toHaveBeenCalledWith(
        `user:${userId}`,
        mockUser,
        3600,
      );
    });

    it('should throw NotFoundException when user does not exist', async () => {
      const userId = 'non-existent-id';
      mockCacheService.get.mockResolvedValue(null);
      mockDatabaseService.user.findUnique.mockResolvedValue(null);

      await expect(service.findOne(userId)).rejects.toThrow(NotFoundException);
    });
  });

  describe('update', () => {
    it('should update user successfully', async () => {
      const userId = mockUser.id;
      const updateUserDto: UpdateUserDto = {
        name: 'Updated Name',
      };
      const updatedUser = { ...mockUser, name: 'Updated Name' };

      mockDatabaseService.user.findUnique.mockResolvedValue(mockUser);
      mockDatabaseService.user.update.mockResolvedValue(updatedUser);

      const result = await service.update(userId, updateUserDto);

      expect(result).toEqual(updatedUser);
      expect(mockDatabaseService.user.update).toHaveBeenCalledWith({
        where: { id: userId },
        data: updateUserDto,
      });
      expect(mockCacheService.del).toHaveBeenCalledWith(`user:${userId}`);
      expect(mockCacheService.delPattern).toHaveBeenCalledWith('users:*');
    });

    it('should throw NotFoundException when updating non-existent user', async () => {
      const userId = 'non-existent-id';
      const updateUserDto: UpdateUserDto = { name: 'Updated Name' };

      mockDatabaseService.user.findUnique.mockResolvedValue(null);

      await expect(service.update(userId, updateUserDto)).rejects.toThrow(
        NotFoundException,
      );
      expect(mockDatabaseService.user.update).not.toHaveBeenCalled();
    });
  });

  describe('remove', () => {
    it('should soft delete user successfully', async () => {
      const userId = mockUser.id;
      const deactivatedUser = { ...mockUser, isActive: false };

      mockDatabaseService.user.findUnique.mockResolvedValue(mockUser);
      mockDatabaseService.user.update.mockResolvedValue(deactivatedUser);

      await service.remove(userId);

      expect(mockDatabaseService.user.update).toHaveBeenCalledWith({
        where: { id: userId },
        data: { isActive: false },
      });
      expect(mockCacheService.del).toHaveBeenCalledWith(`user:${userId}`);
      expect(mockCacheService.delPattern).toHaveBeenCalledWith('users:*');
    });

    it('should throw NotFoundException when deleting non-existent user', async () => {
      const userId = 'non-existent-id';
      mockDatabaseService.user.findUnique.mockResolvedValue(null);

      await expect(service.remove(userId)).rejects.toThrow(NotFoundException);
      expect(mockDatabaseService.user.update).not.toHaveBeenCalled();
    });
  });

  describe('findAll', () => {
    it('should return paginated users', async () => {
      const users = [mockUser];
      const total = 1;

      mockDatabaseService.user.findMany.mockResolvedValue(users);
      mockDatabaseService.user.count.mockResolvedValue(total);

      const result = await service.findAll({ page: 1, limit: 10 });

      expect(result).toEqual({
        data: users,
        meta: {
          total,
          page: 1,
          limit: 10,
          totalPages: 1,
        },
      });
    });
  });
});
```
