# NestJS REST Controllers — Schemas, Mapping & Pagination

Response mapping, pagination, filtering and sorting for NestJS 12.x REST APIs with Prisma 7 and TypeScript 6.0.
Contracts are Zod 4 schemas (Standard Schema): the global `StandardSchemaValidationPipe` validates requests declared
with `{ schema }`, and the global `StandardSchemaSerializerInterceptor` applies `@SerializeOptions({ schema })` to
responses. `@nestjs/swagger` 12 documents both from the same schemas. Runtime-verified wiring:
`nestjs-production-baseline.md`.

## 3. Response Mapping Patterns

The response schema is the contract; mapping code only converts types (Prisma `Decimal` → number, `Date` → ISO string).
`z.object` strips every field it does not declare (`tenantId`, `passwordHash`, `deletedAt`), so a forgotten field
cannot leak; a value that breaks the schema throws `Serialization failed` and the client gets an opaque 500.

### Pattern 1: Response schema + mapping function (default)

```typescript
// src/features/products/products.schemas.ts
import { z } from 'zod';

export const ProductStatusSchema = z.enum(['ACTIVE', 'INACTIVE', 'ARCHIVED']);

export const ProductResponseSchema = z
  .object({
    id: z.uuid(),
    name: z.string(),
    sku: z.string(),
    price: z.number(),
    status: ProductStatusSchema,
    createdAt: z.iso.datetime(),
    updatedAt: z.iso.datetime(),
  })
  .meta({ id: 'ProductResponse' });
export type ProductResponse = z.infer<typeof ProductResponseSchema>;
```

```typescript
// src/features/products/products.mapper.ts
import type { Product } from '../../generated/prisma/client.js';
import type { ProductResponse } from './products.schemas.js';

/** Converts types only; the response schema decides which fields leave the service. */
export function toProductResponse(entity: Product): ProductResponse {
  return {
    ...entity,
    price: entity.price.toNumber(), // Prisma Decimal -> number
    createdAt: entity.createdAt.toISOString(),
    updatedAt: entity.updatedAt.toISOString(),
  };
}
```

```typescript
// Controller: the class-level schema applies to every handler; a handler can override it.
@Controller({ path: 'products', version: '1' })
@SerializeOptions({ schema: ProductResponseSchema })
export class ProductController {
  @Get(':id')
  @ApiOkResponse({ standardSchema: ProductResponseSchema })
  findOne(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: z.uuid() }) id: string,
  ): Promise<ProductResponse> {
    return this.productService.findOne(principal, id);
  }
}
```

### Pattern 2: Request schema → Prisma input (dedicated mapper)

Use a mapper when the persistence shape differs from the request (Decimal construction, derived columns, nested
writes). The tenant always comes from the verified principal, never from the body.

```typescript
import { Injectable } from '@nestjs/common';
import { z } from 'zod';
import { Prisma } from '../../generated/prisma/client.js';
import { ProductStatusSchema } from './products.schemas.js';

export const CreateProductSchema = z
  .strictObject({
    name: z.string().trim().min(1).max(200),
    sku: z.string().regex(/^[A-Z0-9-]{3,32}$/),
    price: z.number().nonnegative().multipleOf(0.01),
    status: ProductStatusSchema.default('ACTIVE'),
    description: z.string().max(1000).optional(),
  })
  .meta({ id: 'CreateProduct' });
export type CreateProduct = z.infer<typeof CreateProductSchema>;

export const UpdateProductSchema = CreateProductSchema.omit({ sku: true })
  .partial()
  .meta({ id: 'UpdateProduct' });
export type UpdateProduct = z.infer<typeof UpdateProductSchema>;

@Injectable()
export class ProductMapper {
  toCreateInput(tenantId: string, input: CreateProduct): Prisma.ProductCreateInput {
    return { ...input, tenantId, price: new Prisma.Decimal(input.price) };
  }

  toUpdateInput(input: UpdateProduct): Prisma.ProductUpdateInput {
    const { price, ...rest } = input;
    return price === undefined ? rest : { ...rest, price: new Prisma.Decimal(price) };
  }
}
```

### Existing class-validator codebases

Response DTO classes with `class-transformer` `@Exclude()`/`@Expose()` and `ClassSerializerInterceptor` remain
supported in NestJS 12. In such a codebase keep one style per module; for new modules use the schema patterns above.
The class-based form fails open (a field without `@Exclude()` leaks); `z.object` strips by default.

---

## 4. Pagination, Filtering & Sorting

### Generic pagination query schema

Query strings arrive as text: coerce explicitly with `z.coerce`, bound every value, and allow-list sort fields (a free
`sortBy: string` passed to Prisma's `orderBy` lets a client sort by any column, including private ones).

```typescript
// src/common/schemas/pagination.schemas.ts
import { z } from 'zod';

export const SortOrderSchema = z.enum(['asc', 'desc']);

/** Builds a pagination query schema whose sortBy is restricted to the given columns. */
export function paginationQuery<const TSort extends readonly [string, ...string[]]>(sortable: TSort) {
  return z.strictObject({
    page: z.coerce.number().int().min(1).default(1),
    limit: z.coerce.number().int().min(1).max(100).default(20),
    sortBy: z.enum(sortable).default(sortable[0]),
    sortOrder: SortOrderSchema.default('desc'),
  });
}

export function toSkipTake(query: { page: number; limit: number }): { skip: number; take: number } {
  return { skip: (query.page - 1) * query.limit, take: query.limit };
}
```

### Generic paginated response

```typescript
// src/common/schemas/pagination.schemas.ts (continued)
export const PaginationMetaSchema = z.object({
  page: z.int(),
  limit: z.int(),
  total: z.int(),
  totalPages: z.int(),
  hasNextPage: z.boolean(),
  hasPreviousPage: z.boolean(),
});

/** Wraps an item schema in the { data, meta } envelope; give the result its own .meta({ id }). */
export function paginated<TItem extends z.ZodType>(item: TItem) {
  return z.object({ data: z.array(item), meta: PaginationMetaSchema });
}

export function toPage<T>(data: T[], total: number, page: number, limit: number) {
  const totalPages = Math.ceil(total / limit);
  return {
    data,
    meta: { page, limit, total, totalPages, hasNextPage: page < totalPages, hasPreviousPage: page > 1 },
  };
}
```

### Product filter schema

```typescript
// src/features/products/products.schemas.ts (continued)
import { paginated, paginationQuery } from '../../common/schemas/pagination.schemas.js';

export const ProductFilterSchema = paginationQuery(['createdAt', 'name', 'price'])
  .extend({
    search: z.string().trim().min(1).max(100).optional(),
    status: ProductStatusSchema.optional(),
    minPrice: z.coerce.number().nonnegative().optional(),
    maxPrice: z.coerce.number().nonnegative().optional(),
  })
  .refine((f) => f.minPrice === undefined || f.maxPrice === undefined || f.minPrice <= f.maxPrice, {
    message: 'minPrice must not exceed maxPrice',
    path: ['minPrice'],
  })
  .meta({ id: 'ProductFilter' });
export type ProductFilter = z.infer<typeof ProductFilterSchema>;

export const ProductPageSchema = paginated(ProductResponseSchema).meta({ id: 'ProductPage' });
export type ProductPage = z.infer<typeof ProductPageSchema>;
```

```typescript
// Controller
@Get()
@SerializeOptions({ schema: ProductPageSchema })
@ApiOkResponse({ standardSchema: ProductPageSchema })
findAll(
  @CurrentPrincipal() principal: Principal,
  @Query({ schema: ProductFilterSchema }) filter: ProductFilter,
): Promise<ProductPage> {
  return this.productService.findAll(principal, filter);
}

// Service
async findAll(principal: Principal, filter: ProductFilter): Promise<ProductPage> {
  const [rows, total] = await this.repository.findManyWithPagination(principal.tenantId, filter);
  return toPage(rows.map(toProductResponse), total, filter.page, filter.limit);
}
```

### Repository with pagination

```typescript
import { Injectable } from '@nestjs/common';
import { toSkipTake } from '../../common/schemas/pagination.schemas.js';
import { PrismaService } from '../../core/database/prisma.service.js';
import { Prisma, type Product } from '../../generated/prisma/client.js';
import type { ProductFilter } from './products.schemas.js';

@Injectable()
export class ProductRepository {
  constructor(private readonly prisma: PrismaService) {}

  async findManyWithPagination(tenantId: string, filter: ProductFilter): Promise<[Product[], number]> {
    const where = this.buildWhereClause(tenantId, filter);
    // sortBy is one of the allow-listed columns, so this cannot address an arbitrary field.
    const orderBy: Prisma.ProductOrderByWithRelationInput = { [filter.sortBy]: filter.sortOrder };

    // One snapshot for rows and count; Promise.all on two queries can see different data.
    return this.prisma.client.$transaction([
      this.prisma.client.product.findMany({ where, orderBy, ...toSkipTake(filter) }),
      this.prisma.client.product.count({ where }),
    ]);
  }

  private buildWhereClause(tenantId: string, filter: ProductFilter): Prisma.ProductWhereInput {
    const where: Prisma.ProductWhereInput = { tenantId, deletedAt: null };

    if (filter.search !== undefined) {
      where.OR = [
        { name: { contains: filter.search, mode: 'insensitive' } },
        { sku: { contains: filter.search, mode: 'insensitive' } },
        { description: { contains: filter.search, mode: 'insensitive' } },
      ];
    }

    if (filter.status !== undefined) {
      where.status = filter.status;
    }

    if (filter.minPrice !== undefined || filter.maxPrice !== undefined) {
      where.price = {
        ...(filter.minPrice !== undefined && { gte: new Prisma.Decimal(filter.minPrice) }),
        ...(filter.maxPrice !== undefined && { lte: new Prisma.Decimal(filter.maxPrice) }),
      };
    }

    return where;
  }
}
```

Offset pagination degrades on deep pages (`OFFSET 100000` still scans the skipped rows). For feeds and exports use
keyset pagination on an indexed `(tenant_id, created_at, id)` with a `cursor` query parameter.
