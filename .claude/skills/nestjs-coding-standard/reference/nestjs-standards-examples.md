# NestJS + TypeScript Coding Standards Examples

Concrete code examples for NestJS 11.x services following team standards.

---

## 1. Naming Conventions

### Classes

```typescript
// Services: PascalCase + "Service" suffix
export class ProductsService { }

// Controllers: PascalCase + "Controller" suffix
export class ProductsController { }

// DTOs: PascalCase + operation + "Dto" suffix
export class CreateProductDto { }
export class UpdateProductDto { }
export class ProductResponseDto { }

// Exceptions: PascalCase + "Exception" suffix
export class ProductNotFoundException extends BaseException { }
```

### Files

```typescript
// Files: kebab-case matching class name
// products.service.ts → ProductsService
// create-product.dto.ts → CreateProductDto
// product-not-found.exception.ts → ProductNotFoundException
```

### Interfaces & Types

```typescript
// Interfaces: PascalCase, use "I" prefix ONLY for DI tokens
export interface IProductRepository {
  findById(id: string): Promise<Product | null>;
}

// Type aliases: PascalCase
export type ProductStatus = 'active' | 'inactive' | 'archived';
```

### Constants

```typescript
// Constants: UPPER_SNAKE_CASE
export const MAX_PRODUCT_NAME_LENGTH = 255;
export const DEFAULT_PAGE_SIZE = 20;

// Frozen objects for complex constants
export const API_RATE_LIMITS = Object.freeze({
  PER_MINUTE: 60,
  PER_HOUR: 1000,
} as const);
```

### Enums

```typescript
// Enum names: PascalCase
// Members: PascalCase (not UPPER_CASE)
export enum OrderStatus {
  Pending = 'pending',
  Processing = 'processing',
  Shipped = 'shipped',
  Delivered = 'delivered',
  Cancelled = 'cancelled',
}
```

---

## 2. TypeScript Strictness

### No `any` — Use `unknown`

```typescript
// Bad
function productName(data: any): string {
  return data.name; // No type safety
}

// Good
function productName(data: unknown): string {
  if (!isProduct(data)) throw new BadRequestException('Not a product');
  return data.name; // Type-safe after guard
}

function isProduct(value: unknown): value is Product {
  return typeof value === 'object' && value !== null && 'id' in value;
}
```

### Explicit Return Types

```typescript
// Bad
async findAll() {
  return this.prisma.product.findMany();
}

// Good
async findAll(): Promise<Product[]> {
  return this.prisma.product.findMany();
}
```

### Discriminated Unions

```typescript
// Good: Use discriminated unions for type safety
type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: string };

async function fetchProduct(id: string): Promise<ApiResponse<Product>> {
  try {
    const product = await prisma.product.findUnique({ where: { id } });
    if (!product) {
      return { success: false, error: 'Product not found' };
    }
    return { success: true, data: product };
  } catch (error: unknown) {
    // Error state, not a swallow: log with context, return a typed failure the caller must handle
    logger.error({ event: 'fetch_product_failed', productId: id }, error instanceof Error ? error.stack : undefined);
    return { success: false, error: 'Database error' };
  }
}

// Usage
const result = await fetchProduct('123');
if (result.success) {
  return toResponse(result.data); // TypeScript knows `data` exists
}
throw new ServiceUnavailableException(result.error); // TypeScript knows `error` exists
```

---

## 3. Immutability Patterns

### Readonly Injected Dependencies

```typescript
@Injectable()
export class ProductsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly logger: Logger,
  ) {}
}
```

### Readonly DTO Properties

```typescript
export class CreateProductDto {
  @IsString()
  @IsNotEmpty()
  readonly name: string;

  @IsNumber()
  @Min(0)
  readonly price: number;
}
```

### Object.freeze for Constants

```typescript
export const DATABASE_CONFIG = Object.freeze({
  MAX_POOL_SIZE: 10,
  CONNECTION_TIMEOUT: 5000,
  QUERY_TIMEOUT: 30000,
} as const);
```

### Spread Operator for Updates

```typescript
// Bad: Mutation
function updateProduct(product: Product, price: number): void {
  product.price = price; // Mutates original object
}

// Good: Return new object
function updateProduct(product: Product, price: number): Product {
  return { ...product, price };
}
```

---

## 4. DTO Patterns

### Create DTO

```typescript
export class CreateProductDto {
  @ApiProperty({ example: 'Laptop' })
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  readonly name: string;

  @ApiProperty({ example: 999.99 })
  @IsNumber()
  @Min(0)
  readonly price: number;

  @ApiProperty({ example: 'active', enum: ['active', 'inactive'] })
  @IsEnum(['active', 'inactive'])
  readonly status: string;
}
```

### Update DTO

```typescript
// Use PartialType for optional updates
export class UpdateProductDto extends PartialType(CreateProductDto) {}
```

### Response DTO

```typescript
export class ProductResponseDto {
  @ApiProperty()
  readonly id: string;

  @ApiProperty()
  readonly name: string;

  @ApiProperty()
  readonly price: number;

  @ApiProperty()
  readonly createdAt: Date;

  @ApiProperty()
  readonly updatedAt: Date;
}
```

### Nested Validation

```typescript
export class AddressDto {
  @IsString()
  @IsNotEmpty()
  readonly street: string;

  @IsString()
  @IsNotEmpty()
  readonly city: string;
}

export class CreateCustomerDto {
  @IsString()
  @IsNotEmpty()
  readonly name: string;

  @ValidateNested()
  @Type(() => AddressDto)
  readonly address: AddressDto;
}
```

---

## 5. Module Organization

### Feature Module

```typescript
@Module({
  imports: [PrismaModule],
  controllers: [ProductsController],
  providers: [ProductsService, ProductsRepository],
  exports: [ProductsService], // Explicit exports
})
export class ProductsModule {}
```

### Core Module (Global)

```typescript
@Global()
@Module({
  providers: [
    {
      provide: Logger,
      useValue: new Logger('App'),
    },
  ],
  exports: [Logger],
})
export class CoreModule {}
```

### Module Aggregation

```typescript
// features.module.ts
@Module({
  imports: [ProductsModule, OrdersModule, CustomersModule],
})
export class FeaturesModule {}

// app.module.ts
@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    CommonModule,
    CoreModule,
    FeaturesModule,
  ],
})
export class AppModule {}
```

---

## 6. Error Handling

### Custom Exception Base Class

```typescript
export abstract class BaseException extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = this.constructor.name;
    Error.captureStackTrace(this, this.constructor);
  }
}
```

### Domain Exception

```typescript
export class ProductNotFoundException extends BaseException {
  constructor(productId: string) {
    super(
      `Product with ID ${productId} not found`,
      404,
      { productId, operation: 'findById' },
    );
  }
}
```

### Service Error Handling

```typescript
@Injectable()
export class ProductsService {
  private readonly logger = new Logger(ProductsService.name);

  async findById(id: string): Promise<Product> {
    try {
      const product = await this.prisma.product.findUnique({ where: { id } });
      if (!product) {
        throw new ProductNotFoundException(id);
      }
      return product;
    } catch (error) {
      this.logger.error('Failed to fetch product', { id, error: error.message });
      throw error; // Re-throw after logging
    }
  }
}
```

### Never Swallow Exceptions

```typescript
// Bad
try {
  await this.externalApi.call();
} catch (error) {
  // Silent failure
}

// Good: Log and rethrow
try {
  await this.externalApi.call();
} catch (error) {
  this.logger.error('External API call failed', { error: error.message });
  throw new ServiceUnavailableException('External API unavailable');
}
```

---

## 7. Service Patterns

### Single Responsibility

```typescript
@Injectable()
export class ProductsService {
  constructor(
    private readonly repository: ProductsRepository,
    private readonly logger: Logger,
  ) {}

  async create(dto: CreateProductDto): Promise<Product> {
    this.logger.log('Creating product', { name: dto.name });
    return this.repository.create(dto);
  }

  async findAll(): Promise<Product[]> {
    return this.repository.findAll();
  }
}
```

### Transaction Pattern

```typescript
@Injectable()
export class OrdersService {
  async createOrder(dto: CreateOrderDto): Promise<Order> {
    return this.prisma.$transaction(async (tx) => {
      const order = await tx.order.create({ data: dto });
      await tx.inventory.updateMany({
        where: { productId: { in: dto.productIds } },
        data: { quantity: { decrement: 1 } },
      });
      return order;
    });
  }
}
```

---

## 8. Controller Patterns

### Thin Controllers

```typescript
@ApiTags('products')
@Controller('products')
export class ProductsController {
  constructor(private readonly service: ProductsService) {}

  @Get()
  @ApiOperation({ summary: 'Get all products' })
  @ApiResponse({ status: 200, type: [ProductResponseDto] })
  async findAll(): Promise<ProductResponseDto[]> {
    return this.service.findAll();
  }

  @Post()
  @HttpCode(201)
  @ApiOperation({ summary: 'Create a new product' })
  @ApiResponse({ status: 201, type: ProductResponseDto })
  async create(@Body() dto: CreateProductDto): Promise<ProductResponseDto> {
    return this.service.create(dto);
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get product by ID' })
  @ApiResponse({ status: 200, type: ProductResponseDto })
  @ApiResponse({ status: 404, description: 'Product not found' })
  async findById(@Param('id') id: string): Promise<ProductResponseDto> {
    return this.service.findById(id);
  }
}
```

### Route Naming

```typescript
// Good: Plural nouns, RESTful
@Controller('products')   // /products
@Controller('orders')     // /orders
@Controller('customers')  // /customers

// Bad: Singular, verbs
@Controller('product')
@Controller('getOrders')
```

---

## 9. Logging Standards

### Logger Per Class

```typescript
@Injectable()
export class ProductsService {
  private readonly logger = new Logger(ProductsService.name);

  async create(dto: CreateProductDto): Promise<Product> {
    this.logger.log('Creating product', { name: dto.name, price: dto.price });
    return this.repository.create(dto);
  }
}
```

### Log Levels

```typescript
// ERROR: Operation failures
this.logger.error('Failed to create product', { error: error.message, productId });

// WARN: Degraded state, fallback used
this.logger.warn('Cache miss, falling back to database', { key });

// LOG: Normal operations
this.logger.log('Product created successfully', { productId });

// DEBUG: Detailed debugging info
this.logger.debug('Query execution', { query, params });
```

### Never Log Sensitive Data

```typescript
// Bad
this.logger.log('User login', { password: dto.password });

// Bad: email is PII
this.logger.log('User login attempt', { email: dto.email });

// Good: an opaque id, never credentials or PII
this.logger.log({ event: 'login_attempt', userId: user.id });
```

---

## 10. Testing Standards

### Test Structure

```typescript
import { beforeEach, describe, expect, it, vi, type Mocked } from 'vitest';

describe('ProductsService', () => {
  let service: ProductsService;
  let repository: Mocked<Pick<ProductsRepository, 'findAll' | 'create'>>;

  beforeEach(() => {
    // Vitest (not Jest): vi.fn(), typed with Mocked<> — no `as any`
    repository = { findAll: vi.fn(), create: vi.fn() };
    service = new ProductsService(repository);
  });

  describe('findAll', () => {
    it('should return all products', async () => {
      // Arrange
      const mockProducts = [{ id: '1', name: 'Product 1' }];
      repository.findAll.mockResolvedValue(mockProducts);

      // Act
      const result = await service.findAll();

      // Assert
      expect(result).toEqual(mockProducts);
      expect(repository.findAll).toHaveBeenCalledTimes(1);
    });
  });

  describe('create', () => {
    it('should create product when valid DTO provided', async () => {
      // Arrange
      const dto = { name: 'New Product', price: 99.99 };
      const expected = { id: '1', ...dto };
      repository.create.mockResolvedValue(expected);

      // Act
      const result = await service.create(dto);

      // Assert
      expect(result).toEqual(expected);
      expect(repository.create).toHaveBeenCalledWith(dto);
    });
  });
});
```

---

## 11. Code Smells to Avoid

### Long Parameter Lists

```typescript
// Bad
function createOrder(
  customerId: string,
  productId: string,
  quantity: number,
  price: number,
  discount: number,
) { }

// Good: Use DTO
function createOrder(dto: CreateOrderDto) { }
```

### Deep Nesting

```typescript
// Bad
if (user) {
  if (user.isActive) {
    if (user.hasPermission('write')) {
      // do something
    }
  }
}

// Good: Early returns
if (!user) return;
if (!user.isActive) return;
if (!user.hasPermission('write')) return;
// do something
```

### Magic Strings

```typescript
// Bad
if (status === 'active') { }

// Good
const STATUS_ACTIVE = 'active';
if (status === STATUS_ACTIVE) { }
```

---

## 12. Formatting

### Indentation & Quotes

```typescript
// 2-space indent
export class ProductsService {
  constructor(
    private readonly repo: ProductsRepository,
  ) {}
}

// Single quotes for strings
const message = 'Product created';

// Trailing commas
const config = {
  host: 'localhost',
  port: 3000,  // Trailing comma
};
```

### Line Length

```typescript
// Max 120 characters per line
export class ReallyLongClassNameThatShouldBeShorter {
  reallyLongMethodName(
    parameterOne: string,
    parameterTwo: number,
  ): Promise<SomeReallyLongReturnType> {
    // Implementation
  }
}
```

### Semicolons

```typescript
// Always use explicit semicolons
const name = 'Product';
const price = 99.99;
```
