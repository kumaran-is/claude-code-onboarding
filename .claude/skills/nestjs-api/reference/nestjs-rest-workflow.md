# NestJS REST Controllers — Workflow & Swagger Setup

REST service development workflow and OpenAPI/Swagger-driven controller patterns for NestJS 12.x with Fastify and TypeScript 6.0.

## 1. REST Service Development Workflow

### Step-by-Step Process

1. **Gather Requirements**
   - Parse OpenAPI spec or requirement documents
   - Extract entities, relationships, and endpoint definitions
   - Identify DTOs, validation rules, and business logic

2. **Database Schema**
   - Design Prisma schema with proper relations
   - Run migrations: `npx prisma migrate dev`
   - Generate Prisma Client: `npx prisma generate`

3. **Generate Feature Module**
   ```bash
   nest g module features/products
   nest g controller features/products
   nest g service features/products
   ```

4. **Create schemas**
   - Request schemas with Zod 4 `z.strictObject(...)`, bound with `@Body({ schema })`, `@Param(name, { schema })`, `@Query({ schema })`
   - Response schemas with `z.object(...)` and `@SerializeOptions({ schema })`; `.meta({ id })` names the OpenAPI component
   - Reusable pagination and filter schemas (query strings coerced explicitly with `z.coerce`)

5. **Implement Layers**
   - Repository: Prisma database access
   - Service: Business logic + external service calls with circuit breaker
   - Controller: HTTP endpoints with Swagger documentation

6. **Add Integrations**
   - External service clients with circuit breaker pattern
   - Type-safe configuration for API endpoints
   - Error mapping and retry logic

7. **Write Tests**
   - Unit tests for services and repositories
   - Integration tests with supertest
   - Contract tests for external APIs

8. **Configure Documentation**
   - Swagger decorators on controllers
   - Export OpenAPI JSON for API gateway
   - Add example requests/responses

---

## 2. OpenAPI/Swagger-Driven Development

### Controller with Complete Swagger Documentation

`@nestjs/swagger` 12 generates the request body, path/query parameters and response schemas from the Zod schemas
declared on the route (verified on 12.1.2: the generated `/docs-json` lists the `CreateOrder` properties with
`additionalProperties: false`). `@ApiOperation` and error-status `@ApiResponse`s stay hand-written.

```typescript
import { Body, Controller, Delete, Get, HttpCode, HttpStatus, Param, Post, Put, Query, SerializeOptions } from '@nestjs/common';
import {
  ApiBadRequestResponse,
  ApiConflictResponse,
  ApiCreatedResponse,
  ApiNoContentResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiTags,
} from '@nestjs/swagger';

import { CurrentPrincipal } from '../../auth/auth.decorators.js';
import type { Principal } from '../../auth/principal.js';
import {
  type CreateProduct,
  CreateProductSchema,
  type ProductFilter,
  ProductFilterSchema,
  ProductIdSchema,
  ProductPageSchema,
  type ProductPage,
  type ProductResponse,
  ProductResponseSchema,
  type UpdateProduct,
  UpdateProductSchema,
} from './product.schemas.js';
import { ProductService } from './product.service.js';

@ApiTags('Products')
@Controller({ path: 'products', version: '1' })
@SerializeOptions({ schema: ProductResponseSchema })
export class ProductController {
  constructor(private readonly productService: ProductService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({ summary: 'Create a new product' })
  @ApiCreatedResponse({ standardSchema: ProductResponseSchema })
  @ApiBadRequestResponse({ description: 'Invalid input data' })
  @ApiConflictResponse({ description: 'Product with SKU already exists' })
  create(
    @CurrentPrincipal() principal: Principal,
    @Body({ schema: CreateProductSchema }) body: CreateProduct,
  ): Promise<ProductResponse> {
    return this.productService.create(principal, body);
  }

  @Get()
  @ApiOperation({ summary: 'List products with pagination and filters' })
  @SerializeOptions({ schema: ProductPageSchema })
  @ApiOkResponse({ standardSchema: ProductPageSchema })
  findAll(
    @CurrentPrincipal() principal: Principal,
    @Query({ schema: ProductFilterSchema }) filter: ProductFilter,
  ): Promise<ProductPage> {
    return this.productService.findAll(principal, filter);
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get product by ID' })
  @ApiOkResponse({ standardSchema: ProductResponseSchema })
  @ApiNotFoundResponse({ description: 'Product not found (or owned by another tenant)' })
  findOne(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
  ): Promise<ProductResponse> {
    return this.productService.findOne(principal, id);
  }

  @Put(':id')
  @ApiOperation({ summary: 'Update product' })
  @ApiOkResponse({ standardSchema: ProductResponseSchema })
  @ApiNotFoundResponse({ description: 'Product not found' })
  update(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
    @Body({ schema: UpdateProductSchema }) body: UpdateProduct,
  ): Promise<ProductResponse> {
    return this.productService.update(principal, id, body);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Delete product (soft delete)' })
  @ApiNoContentResponse({ description: 'Product deleted' })
  @ApiNotFoundResponse({ description: 'Product not found' })
  async remove(
    @CurrentPrincipal() principal: Principal,
    @Param('id', { schema: ProductIdSchema }) id: string,
  ): Promise<void> {
    await this.productService.remove(principal, id);
  }
}
```

Schemas for this controller follow `nestjs-templates-features.md` (`products.schemas.ts`); the paginated envelope and
filter schema are in `nestjs-rest-dto-pagination.md`.

### Swagger Setup in main.ts

Validation and serialization are global providers in `AppModule` (`APP_PIPE` / `APP_INTERCEPTOR`, see
`nestjs-templates-core.md`), so `main.ts` registers no pipe.

```typescript
import { writeFileSync } from 'node:fs';
import { VersioningType } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module.js';
import type { Env } from './config/env.js';

const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter());

app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1' });

const config = new DocumentBuilder()
  .setTitle('Product Service API')
  .setDescription('REST API for product management')
  .setVersion('1.0')
  .addTag('Products')
  .addBearerAuth()
  .build();

const document = SwaggerModule.createDocument(app, config);
// Swagger routes are public (guards do not protect them): serve the UI only outside production.
if (process.env['NODE_ENV'] !== 'production') {
  SwaggerModule.setup('api/docs', app, document);
}

// Export OpenAPI JSON for the API gateway (run with EXPORT_OPENAPI=1 in CI, not on every start).
if (process.env['EXPORT_OPENAPI'] === '1') {
  writeFileSync('./openapi.json', JSON.stringify(document, null, 2));
}

// PORT's default lives in the env schema; ConfigService returns the parsed number.
await app.listen({ port: app.get<ConfigService<Env, true>>(ConfigService).get('PORT', { infer: true }), host: '0.0.0.0' });
```
