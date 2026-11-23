# NestJS 11.x Unit Testing — Controllers & Test Data Factories

Controller unit testing patterns and test data factory setup for NestJS 11.x with Vitest and Prisma ORM. Covers controller tests with mocked services, builder-pattern factories, and seed helpers.

## Controller Unit Test Pattern

```typescript
// src/features/users/users.controller.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { CreateUserDto, UpdateUserDto } from './dto';
import { User } from '@prisma/client';
import { NotFoundException } from '@nestjs/common';

describe('UsersController', () => {
  let controller: UsersController;
  let service: UsersService;

  const mockUser: User = {
    id: '123e4567-e89b-12d3-a456-426614174000',
    email: 'test@example.com',
    name: 'Test User',
    role: 'USER',
    isActive: true,
    createdAt: new Date('2024-01-01'),
    updatedAt: new Date('2024-01-01'),
  };

  const mockUsersService = {
    create: vi.fn(),
    findAll: vi.fn(),
    findOne: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [UsersController],
      providers: [
        {
          provide: UsersService,
          useValue: mockUsersService,
        },
      ],
    }).compile();

    controller = module.get<UsersController>(UsersController);
    service = module.get<UsersService>(UsersService);

    vi.clearAllMocks();
  });

  describe('create', () => {
    it('should create a user and return 201', async () => {
      const createUserDto: CreateUserDto = {
        email: 'test@example.com',
        name: 'Test User',
        role: 'USER',
      };

      mockUsersService.create.mockResolvedValue(mockUser);

      const result = await controller.create(createUserDto);

      expect(result).toEqual(mockUser);
      expect(service.create).toHaveBeenCalledWith(createUserDto);
    });
  });

  describe('findAll', () => {
    it('should return paginated users', async () => {
      const paginatedResult = {
        data: [mockUser],
        meta: {
          total: 1,
          page: 1,
          limit: 10,
          totalPages: 1,
        },
      };

      mockUsersService.findAll.mockResolvedValue(paginatedResult);

      const result = await controller.findAll({ page: 1, limit: 10 });

      expect(result).toEqual(paginatedResult);
      expect(service.findAll).toHaveBeenCalledWith({ page: 1, limit: 10 });
    });
  });

  describe('findOne', () => {
    it('should return a single user', async () => {
      mockUsersService.findOne.mockResolvedValue(mockUser);

      const result = await controller.findOne(mockUser.id);

      expect(result).toEqual(mockUser);
      expect(service.findOne).toHaveBeenCalledWith(mockUser.id);
    });

    it('should throw NotFoundException for invalid ID', async () => {
      const invalidId = 'invalid-id';
      mockUsersService.findOne.mockRejectedValue(new NotFoundException());

      await expect(controller.findOne(invalidId)).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe('update', () => {
    it('should update a user', async () => {
      const updateUserDto: UpdateUserDto = { name: 'Updated Name' };
      const updatedUser = { ...mockUser, name: 'Updated Name' };

      mockUsersService.update.mockResolvedValue(updatedUser);

      const result = await controller.update(mockUser.id, updateUserDto);

      expect(result).toEqual(updatedUser);
      expect(service.update).toHaveBeenCalledWith(mockUser.id, updateUserDto);
    });
  });

  describe('remove', () => {
    it('should delete a user', async () => {
      mockUsersService.remove.mockResolvedValue(undefined);

      await controller.remove(mockUser.id);

      expect(service.remove).toHaveBeenCalledWith(mockUser.id);
    });
  });
});
```

## Test Data Factories

```typescript
// test/factories/user.factory.ts
// Prisma 7 `prisma-client` generator: types come from the generated output, not '@prisma/client'
import type { PrismaClient, Role, User } from '../../src/generated/prisma/client';
import { faker } from '@faker-js/faker';

export class UserFactory {
  private data: Partial<User> = {
    email: faker.internet.email(),
    name: faker.person.fullName(),
    role: 'USER' as Role,
    isActive: true,
  };

  with(overrides: Partial<User>): this {
    this.data = { ...this.data, ...overrides };
    return this;
  }

  build(): Omit<User, 'id' | 'createdAt' | 'updatedAt'> {
    return this.data as Omit<User, 'id' | 'createdAt' | 'updatedAt'>;
  }

  async create(prisma: PrismaClient): Promise<User> {
    return prisma.user.create({
      data: this.build(),
    });
  }

  static make(overrides?: Partial<User>): UserFactory {
    const factory = new UserFactory();
    if (overrides) {
      factory.with(overrides);
    }
    return factory;
  }
}

// Usage in tests
import { UserFactory } from './factories/user.factory';

describe('User Tests', () => {
  it('should create test user with factory', async () => {
    const user = await UserFactory.make()
      .with({ email: 'specific@example.com', role: 'ADMIN' })
      .create(databaseService);

    expect(user.email).toBe('specific@example.com');
    expect(user.role).toBe('ADMIN');
  });

  it('should create multiple users', async () => {
    const users = await Promise.all([
      UserFactory.make().create(databaseService),
      UserFactory.make().create(databaseService),
      UserFactory.make().create(databaseService),
    ]);

    expect(users).toHaveLength(3);
  });
});
```

### Prisma Seed Helpers

```typescript
// test/helpers/seed.ts
import { PrismaClient } from '@prisma/client';
import { UserFactory } from '../factories/user.factory';

export class TestSeeder {
  constructor(private readonly prisma: PrismaClient) {}

  async seedUsers(count: number = 10) {
    const users = [];
    for (let i = 0; i < count; i++) {
      users.push(await UserFactory.make().create(this.prisma));
    }
    return users;
  }

  async seedAdminUser() {
    return UserFactory.make()
      .with({
        email: 'admin@example.com',
        role: 'ADMIN',
      })
      .create(this.prisma);
  }

  async clean() {
    await this.prisma.user.deleteMany();
  }
}

// Usage
beforeEach(async () => {
  const seeder = new TestSeeder(databaseService);
  await seeder.clean();
  await seeder.seedUsers(5);
});
```
