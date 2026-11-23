# NestJS 11.x Unit Testing — Basics & Service Tests

Unit testing setup and service test patterns for NestJS 11.x with Vitest, TypeScript 5.x, and Prisma ORM. Covers Vitest configuration, test categories, and isolated service testing with mocked dependencies.

## Test Categories

| Category | Share | Setup | Use When |
|----------|-------|-------|----------|
| **Unit Tests** | 70-80% | `Test.createTestingModule` with mocked providers | Testing individual services, controllers, guards in isolation |
| **Integration Tests** | 15-25% | Full NestJS app with Testcontainers PostgreSQL | Testing full request/response flow, database interactions, multi-layer integration |
| **Contract Tests** | 5-10% | External API client verification with nock/msw | Verifying external service integrations, API contracts |

## Vitest Configuration for Unit Tests

### vitest.config.mts

Use the verified unit config in `nestjs-templates-infrastructure.md` (Vitest 4.1.12, `unplugin-swc`, coverage
`thresholds`). Two fixes to older configs found here before:

- Coverage limits live under `coverage.thresholds` (`{ lines, functions, branches, statements }`). Top-level
  `coverage.lines` no longer exists — `tsc` reports `'lines' does not exist in type 'CoverageOptions'` and the limits
  were never enforced.
- `test.poolOptions` was removed in Vitest 4; use top-level `fileParallelism` / `maxWorkers`.

## Service Unit Test Pattern

```typescript
// src/features/users/users.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { UsersService } from './users.service';
import { DatabaseService } from '@/core/database/database.service';
import { CacheService } from '@/core/cache/cache.service';
import { CreateUserDto, UpdateUserDto } from './dto';
import { User } from '@prisma/client';
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
