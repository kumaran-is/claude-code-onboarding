# NestJS Feature Templates — CRUD Module Pattern

Complete feature module templates for NestJS 12.x (ESM) with controller, service, repository and Zod schemas
(Standard Schema validation and serialization). The same shapes are runtime-verified in
`nestjs-production-baseline.md` (orders feature): copy from there when in doubt.

Assumed global wiring (`app.module.ts`, see `nestjs-templates-core.md`): `StandardSchemaValidationPipe` as `APP_PIPE`,
`StandardSchemaSerializerInterceptor` as `APP_INTERCEPTOR`, `ThrottlerGuard` then `JwtAuthGuard` as `APP_GUARD`s.
Feature controllers therefore add no `@UseGuards(JwtAuthGuard)`: authentication is global, `@Public()` opts out.

## Feature Module Template

### Product Feature Module (src/features/products/products.module.ts)

```typescript
import { Module } from '@nestjs/common';
import { ProductsController } from './controllers/products.controller.js';
import { ProductsRepository } from './repositories/products.repository.js';
import { ProductsService } from './services/products.service.js';

@Module({
  controllers: [ProductsController],
  providers: [ProductsService, ProductsRepository],
  exports: [ProductsService],
})
export class ProductsModule {}
```

### Product Schemas (src/features/products/products.schemas.ts)

One file holds the request and response contracts. Request schemas are `z.strictObject` (an unknown key, such as a
smuggled `tenantId`, is a 400, not silently dropped); response schemas are `z.object` (the serializer strips every field
they do not declare). `.meta({ id })` names the OpenAPI component that `@nestjs/swagger` 12 generates from the schema.

```typescript
import { z } from 'zod';

export const CreateProductSchema = z
  .strictObject({
    name: z.string().trim().min(1).max(200),
    description: z.string().max(1000).optional(),
    price: z.number().nonnegative().multipleOf(0.01),
    stock: z.int().min(0).default(0),
    isActive: z.boolean().default(true),
  })
  .meta({ id: 'CreateProduct' });
export type CreateProduct = z.infer<typeof CreateProductSchema>;

// partial() keeps strictness; at least one field must be present.
export const UpdateProductSchema = CreateProductSchema.partial()
  .refine((value) => Object.keys(value).length > 0, { message: 'at least one field is required' })
  .meta({ id: 'UpdateProduct' });
export type UpdateProduct = z.infer<typeof UpdateProductSchema>;

// Query strings arrive as text: coerce explicitly and cap the page size.
export const ListProductsQuerySchema = z
  .strictObject({
    page: z.coerce.number().int().min(1).default(1),
    limit: z.coerce.number().int().min(1).max(100).default(20),
  })
  .meta({ id: 'ListProductsQuery' });
export type ListProductsQuery = z.infer<typeof ListProductsQuerySchema>;

export const ProductIdSchema = z.uuid();

export const ProductResponseSchema = z
  .object({
    id: z.uuid(),
    name: z.string(),
    description: z.string().nullable(),
    price: z.number(),
    stock: z.int(),
    isActive: z.boolean(),
    createdAt: z.iso.datetime(),
    updatedAt: z.iso.datetime(),
  })
  .meta({ id: 'ProductResponse' });
export type ProductResponse = z.infer<typeof ProductResponseSchema>;

export const ProductListSchema = z.array(ProductResponseSchema);
```

### Product Controller (src/features/products/controllers/products.controller.ts)

```typescript
import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  Query,
  SerializeOptions,
} from '@nestjs/common';
import { ApiBearerAuth, ApiCreatedResponse, ApiNoContentResponse, ApiOkResponse, ApiTags } from '@nestjs/swagger';

import { CurrentPrincipal, Roles } from '../../../auth/auth.decorators.js';
import type { Principal } from '../../../auth/principal.js';
import {
  type CreateProduct,
  CreateProductSchema,
  type ListProductsQuery,
  ListProductsQuerySchema,
  ProductIdSchema,
  ProductListSchema,
  type ProductResponse,
  ProductResponseSchema,
  type UpdateProduct,
  UpdateProductSchema,
} from '../products.schemas.js';
import { ProductsService } from '../services/products.service.js';

@ApiTags('products')
@ApiBearerAuth()
@Controller({ path: 'products', version: '1' })
@SerializeOptions({ schema: ProductResponseSchema })
export class ProductsController {
  constructor(private readonly productsService: ProductsService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @Roles(['products:write'])
  @ApiCreatedResponse({ standardSchema: ProductResponseSchema })
  create(
    @CurrentPrincipal() principal: Principal,
    @Body({ schema: CreateProductSchema }) body: CreateProduct,
  ): Promise<ProductResponse> {
    return this.productsService.create(principal, body);
  }

  @Get()
  @SerializeOptions({ schema: ProductListSchema })
  @ApiOkResponse({ standardSchema: ProductListSchema })
  findAll(
    @CurrentPrincipal() principal: Principal,
    @Query({ schema: ListProductsQuerySchema }) query: ListProductsQuery,
  ): Promise<ProductResponse[]> {
    return this.productsService.findAll(principal, query);
  }

  @Get(':id')
  @ApiOkResponse({ standardSchema: ProductResponseSchema })
  findOne(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
  ): Promise<ProductResponse> {
    return this.productsService.findById(principal, id);
  }

  @Patch(':id')
  @Roles(['products:write'])
  @ApiOkResponse({ standardSchema: ProductResponseSchema })
  update(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
    @Body({ schema: UpdateProductSchema }) body: UpdateProduct,
  ): Promise<ProductResponse> {
    return this.productsService.update(principal, id, body);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @Roles(['products:write'])
  @ApiNoContentResponse()
  async delete(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
  ): Promise<void> {
    await this.productsService.delete(principal, id);
  }
}
```

### Product Service (src/features/products/services/products.service.ts)

```typescript
import { Injectable, Logger, NotFoundException } from '@nestjs/common';

import type { Principal } from '../../../auth/principal.js';
import type { Product } from '../../../generated/prisma/client.js';
import type { CreateProduct, ListProductsQuery, ProductResponse, UpdateProduct } from '../products.schemas.js';
import { ProductsRepository } from '../repositories/products.repository.js';

@Injectable()
export class ProductsService {
  private readonly logger = new Logger(ProductsService.name);

  constructor(private readonly repository: ProductsRepository) {}

  async create(principal: Principal, input: CreateProduct): Promise<ProductResponse> {
    const product = await this.repository.create(principal.tenantId, input);
    this.logger.log('product created', { productId: product.id });
    return toResponse(product);
  }

  async findAll(principal: Principal, query: ListProductsQuery): Promise<ProductResponse[]> {
    const products = await this.repository.findMany(principal.tenantId, {
      skip: (query.page - 1) * query.limit,
      take: query.limit,
    });
    return products.map(toResponse);
  }

  /** Another tenant's product is indistinguishable from a missing one: 404, no existence oracle. */
  async findById(principal: Principal, id: string): Promise<ProductResponse> {
    return toResponse(await this.getOwned(principal, id));
  }

  async update(principal: Principal, id: string, input: UpdateProduct): Promise<ProductResponse> {
    const existing = await this.getOwned(principal, id);
    // Optimistic locking: the update matches the version that was read; 0 rows -> someone else won.
    const updated = await this.repository.updateVersioned(principal.tenantId, id, existing.version, input);
    if (updated === null) throw new NotFoundException('Product not found', { errorCode: 'PRODUCT_NOT_FOUND' });
    return toResponse(updated);
  }

  async delete(principal: Principal, id: string): Promise<void> {
    await this.getOwned(principal, id);
    await this.repository.softDelete(principal.tenantId, id);
    this.logger.log('product soft-deleted', { productId: id });
  }

  private async getOwned(principal: Principal, id: string): Promise<Product> {
    const product = await this.repository.findById(principal.tenantId, id);
    if (product === null) throw new NotFoundException('Product not found', { errorCode: 'PRODUCT_NOT_FOUND' });
    return product;
  }
}

/** Dates become ISO strings and Decimal a number; the response schema strips tenantId, version, deletedAt. */
function toResponse(product: Product): ProductResponse {
  return {
    ...product,
    price: product.price.toNumber(),
    createdAt: product.createdAt.toISOString(),
    updatedAt: product.updatedAt.toISOString(),
  };
}
```

### Product Repository (src/features/products/repositories/products.repository.ts)

`PrismaService` exposes the client by composition (`prisma.client`, see `nestjs-config-prisma7.md`). Every method takes
`tenantId` first, so a query without the tenant filter cannot be written by accident, and soft-deleted rows are
excluded in one place.

```typescript
import { Injectable } from '@nestjs/common';

import { PrismaService } from '../../../core/database/prisma.service.js';
import type { Product } from '../../../generated/prisma/client.js';
import type { CreateProduct, UpdateProduct } from '../products.schemas.js';

@Injectable()
export class ProductsRepository {
  constructor(private readonly prisma: PrismaService) {}

  create(tenantId: string, input: CreateProduct): Promise<Product> {
    return this.prisma.client.product.create({ data: { tenantId, ...input } });
  }

  findById(tenantId: string, id: string): Promise<Product | null> {
    return this.prisma.client.product.findFirst({ where: { id, tenantId, deletedAt: null } });
  }

  findMany(tenantId: string, page: { skip: number; take: number }): Promise<Product[]> {
    return this.prisma.client.product.findMany({
      where: { tenantId, deletedAt: null },
      orderBy: { createdAt: 'desc' },
      skip: page.skip,
      take: Math.min(page.take, 100),
    });
  }

  /** Returns null when the row changed since it was read (version mismatch) or is gone. */
  async updateVersioned(tenantId: string, id: string, version: number, input: UpdateProduct): Promise<Product | null> {
    const { count } = await this.prisma.client.product.updateMany({
      where: { id, tenantId, version, deletedAt: null },
      data: { ...input, version: { increment: 1 } },
    });
    return count === 0 ? null : this.findById(tenantId, id);
  }

  async softDelete(tenantId: string, id: string): Promise<void> {
    await this.prisma.client.product.updateMany({
      where: { id, tenantId, deletedAt: null },
      data: { deletedAt: new Date() },
    });
  }
}
```

A version conflict surfaces here as 404 to keep the template short; return `409 Conflict` with
`{ errorCode: 'PRODUCT_VERSION_CONFLICT' }` when clients send the version they edited (`If-Match`).
