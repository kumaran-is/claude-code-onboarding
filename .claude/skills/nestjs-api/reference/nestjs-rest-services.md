# NestJS REST Services

Service layer patterns, external API integration, and data transformation for NestJS 12.x with circuit breaker resilience.

## 1. Service Layer Implementation

### Service with Pagination

```typescript
import { Injectable } from '@nestjs/common';
import type { Principal } from '../../auth/principal.js';
import { toPage } from '../../common/schemas/pagination.schemas.js';
import { toProductResponse } from './products.mapper.js';
import type { ProductFilter, ProductPage } from './products.schemas.js';
import { ProductRepository } from './product.repository.js';

@Injectable()
export class ProductService {
  constructor(private readonly repository: ProductRepository) {}

  async findAll(principal: Principal, filter: ProductFilter): Promise<ProductPage> {
    const [products, total] = await this.repository.findManyWithPagination(principal.tenantId, filter);
    return toPage(products.map(toProductResponse), total, filter.page, filter.limit);
  }
}
```

Schemas, `toPage` and `toProductResponse`: `nestjs-rest-dto-pagination.md`.

---

## 2. External Service Client Pattern

### Complete HTTP Client with Circuit Breaker

```typescript
import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ResilienceOrchestratorService } from '../../core/resilience/resilience-orchestrator.service.js';
import { HttpStatusError, mapPaymentError } from '../../common/http/http-errors.js';

export interface PaymentRequest {
  orderId: string;
  amount: number;
  currency: string;
  customerId: string;
}

export interface PaymentResponse {
  transactionId: string;
  status: 'SUCCESS' | 'PENDING' | 'FAILED';
  amount: number;
  currency: string;
  processedAt: Date;
}

@Injectable()
export class PaymentServiceClient {
  private readonly logger = new Logger(PaymentServiceClient.name);
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly timeout: number;

  constructor(
    private readonly resilienceOrchestrator: ResilienceOrchestratorService,
    private readonly configService: ConfigService,
  ) {
    this.baseUrl = this.configService.getOrThrow<string>('paymentService.baseUrl');
    this.apiKey = this.configService.getOrThrow<string>('paymentService.apiKey');
    this.timeout = this.configService.getOrThrow<number>('paymentService.timeout');
  }

  async processPayment(request: PaymentRequest): Promise<PaymentResponse> {
    return this.resilienceOrchestrator.execute(
      'payment-service',
      () => this.doProcessPayment(request),
    );
  }

  private async doProcessPayment(request: PaymentRequest): Promise<PaymentResponse> {
    const url = `${this.baseUrl}/v1/payments`;

    try {
      // fetch has no default timeout: every outbound call carries a deadline (typescript-expert `references/node-service-engineering.md` §5).
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${this.apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: AbortSignal.timeout(this.timeout),
      });
      if (!response.ok) throw new HttpStatusError(response.status);
      // Parse with the response's Zod schema in real code (boundary rule); the cast keeps the example short.
      const payment = (await response.json()) as PaymentResponse;

      this.logger.log(`Payment processed: ${payment.transactionId}`);
      return payment;

    } catch (error: unknown) {
      mapPaymentError(error); // typed mapping below; never forward the upstream body
    }
  }

  async getPaymentStatus(transactionId: string): Promise<PaymentResponse> {
    return this.resilienceOrchestrator.execute(
      'payment-service',
      () => this.doGetPaymentStatus(transactionId),
    );
  }

  private async doGetPaymentStatus(transactionId: string): Promise<PaymentResponse> {
    const url = `${this.baseUrl}/v1/payments/${transactionId}`;

    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${this.apiKey}` },
        signal: AbortSignal.timeout(this.timeout),
      });
      if (!response.ok) throw new HttpStatusError(response.status);
      return (await response.json()) as PaymentResponse;

    } catch (error: unknown) {
      if (error instanceof HttpStatusError && error.status === 404) {
        throw new NotFoundException('Payment transaction not found');
      }
      mapPaymentError(error);
    }
  }
}
```

---

## 3. Type-Safe Configuration for External Services

### Configuration Schema

```typescript
import { registerAs } from '@nestjs/config';
import { getRequiredInt, getRequiredString } from './static-config-reader.js';

export interface PaymentServiceConfig {
  baseUrl: string;
  apiKey: string;
  timeout: number;
  retryAttempts: number;
}

// src/config/env.ts entries: required URL and key (no default), optional tuning with its default declared once:
//   PAYMENT_SERVICE_BASE_URL: z.url({ protocol: /^https$/ }),
//   PAYMENT_SERVICE_API_KEY: z.string().min(1),
//   PAYMENT_SERVICE_TIMEOUT: z.coerce.number().int().positive().default(5_000),
//   PAYMENT_SERVICE_RETRY_ATTEMPTS: z.coerce.number().int().min(0).max(5).default(3),
export default registerAs('paymentService', (): PaymentServiceConfig => ({
  baseUrl: getRequiredString('PAYMENT_SERVICE_BASE_URL'),
  apiKey: getRequiredString('PAYMENT_SERVICE_API_KEY'),
  timeout: getRequiredInt('PAYMENT_SERVICE_TIMEOUT'),
  retryAttempts: getRequiredInt('PAYMENT_SERVICE_RETRY_ATTEMPTS'),
}));
```

---

## 4. Bulk Operations

### Bulk Create

```typescript
@Injectable()
export class ProductService {
  // Body schema: z.strictObject({ items: z.array(CreateProductSchema).min(1).max(500) })
  async bulkCreate(principal: Principal, items: CreateProduct[]): Promise<{ count: number }> {
    const data = items.map((item) => ({
      tenantId: principal.tenantId,
      name: item.name,
      sku: item.sku,
      price: new Prisma.Decimal(item.price),
      status: item.status,
    }));

    const result = await this.prisma.client.product.createMany({
      data,
      skipDuplicates: true, // Skip records with duplicate unique fields
    });

    return { count: result.count };
  }
}
```

### Bulk Update with Transaction

```typescript
@Injectable()
export class ProductService {
  async bulkUpdateStatus(principal: Principal, ids: string[], status: ProductStatus): Promise<{ count: number }> {
    const result = await this.prisma.client.product.updateMany({
      where: { tenantId: principal.tenantId, id: { in: ids } },
      data: { status, updatedAt: new Date() },
    });

    return { count: result.count };
  }

  async bulkUpdatePrices(principal: Principal, updates: Array<{ id: string; price: number }>): Promise<void> {
    // All-or-nothing: a row from another tenant (count 0) aborts the whole batch.
    await this.prisma.client.$transaction(async (tx) => {
      for (const { id, price } of updates) {
        const { count } = await tx.product.updateMany({
          where: { id, tenantId: principal.tenantId },
          data: { price: new Prisma.Decimal(price) },
        });
        if (count === 0) throw new NotFoundException('Product not found', { errorCode: 'PRODUCT_NOT_FOUND' });
      }
    });
  }
}
```

---

## 5. Soft Delete Pattern

### Soft Delete with a Prisma Client Extension

Prisma removed `$use` middleware (it does not exist on the Prisma 7 client: `TS2339`). Use a query extension for
reads and an explicit model method for deletes — rewriting `delete` into `update` inside an extension is not supported.
Type-checked against a Prisma 7.10.1 generated client (runtime against PostgreSQL NOT RUN):

```typescript
import { type PrismaClient } from '../generated/prisma/client.js';

export function withOrderSoftDelete(client: PrismaClient) {
  return client.$extends({
    query: {
      order: {
        findMany({ args, query }) {
          return query({ ...args, where: { ...args.where, deletedAt: null } });
        },
        findFirst({ args, query }) {
          return query({ ...args, where: { ...args.where, deletedAt: null } });
        },
      },
    },
    model: {
      order: {
        softDelete(tenantId: string, id: string) {
          return client.order.updateMany({ where: { id, tenantId, deletedAt: null }, data: { deletedAt: new Date() } });
        },
      },
    },
  });
}

export type ExtendedClient = ReturnType<typeof withOrderSoftDelete>;
```

- `$extends` returns a new client; inject the extended client (factory provider), not the base one.
- `findUnique` cannot take a non-unique `deletedAt` filter; route reads that must hide deleted rows through `findFirst`.
- Unique constraints on soft-deleted tables need a partial unique index (`WHERE deleted_at IS NULL`), written in a SQL migration.

### Restore and Hard Delete

```typescript
@Injectable()
export class ProductService {
  async restore(principal: Principal, id: string): Promise<ProductResponse> {
    const { count } = await this.prisma.client.product.updateMany({
      where: { id, tenantId: principal.tenantId, deletedAt: { not: null } },
      data: { deletedAt: null },
    });
    if (count === 0) throw new NotFoundException('Product not found', { errorCode: 'PRODUCT_NOT_FOUND' });
    return this.findOne(principal, id);
  }

  async hardDelete(principal: Principal, id: string): Promise<void> {
    await this.prisma.client.product.deleteMany({ where: { id, tenantId: principal.tenantId } });
  }
}
```

---

## 6. Multi-Service Orchestration

### Service Composition Pattern

```typescript
@Injectable()
export class OrderService {
  constructor(
    private readonly paymentClient: PaymentServiceClient,
    private readonly inventoryClient: InventoryServiceClient,
    private readonly notificationClient: NotificationServiceClient,
    private readonly orderRepository: OrderRepository,
  ) {}

  async createOrder(principal: Principal, input: CreateOrder): Promise<OrderResponse> {
    // 1. Validate inventory availability
    const inventoryCheck = await this.inventoryClient.checkAvailability({
      items: input.items,
    });

    if (!inventoryCheck.available) {
      throw new BadRequestException('Insufficient inventory');
    }

    // 2. Create order in pending state
    const order = await this.orderRepository.create(principal.tenantId, {
      ...input,
      status: 'PENDING',
    });

    try {
      // 3. Reserve inventory
      await this.inventoryClient.reserveItems({
        orderId: order.id,
        items: input.items,
      });

      // 4. Process payment
      const paymentResult = await this.paymentClient.processPayment({
        orderId: order.id,
        amount: order.totalAmount,
        currency: 'USD',
        customerId: principal.subject,
      });

      // 5. Update order status
      const confirmedOrder = await this.orderRepository.update(order.id, {
        status: 'CONFIRMED',
        paymentTransactionId: paymentResult.transactionId,
      });

      // 6. Send notification (fire-and-forget)
      this.notificationClient.sendOrderConfirmation({
        orderId: order.id,
        customerId: principal.subject,
      }).catch((error: unknown) => {
        // Log but don't fail the order
        this.logger.error('Failed to send notification', error);
      });

      return toOrderResponse(confirmedOrder);

    } catch (error) {
      // Rollback: cancel order and release inventory
      await this.orderRepository.update(order.id, { status: 'CANCELLED' });
      await this.inventoryClient.releaseItems({ orderId: order.id });
      throw error;
    }
  }
}
```

---

## 7. Retry Logic with Exponential Backoff

### Retry Decorator

Typed error mapping and a `Retry` decorator: 4xx → 502, 5xx/network/timeout → 503, retry rethrows the last error.
Outbound calls use `fetch` (no `@nestjs/axios`, per the nestjs-api skill); a non-2xx response is raised as
`HttpStatusError` so the mapping sees the status.

```typescript
// src/common/http/http-errors.ts
import { BadGatewayException, Logger, ServiceUnavailableException } from '@nestjs/common';

const logger = new Logger('PaymentClient');

/** A non-2xx upstream response; carries only the status, never the upstream body. */
export class HttpStatusError extends Error {
  constructor(readonly status: number) {
    super(`upstream responded ${status}`);
    this.name = 'HttpStatusError';
  }
}

/** Map an outbound HTTP failure to a typed error. Never forward the upstream body to clients. */
export function mapPaymentError(error: unknown): never {
  if (error instanceof HttpStatusError) {
    const status = error.status;
    logger.error({ event: 'payment_http_error', status });
    if (status >= 400 && status < 500) throw new BadGatewayException('Payment request rejected');
    throw new ServiceUnavailableException('Payment service is unavailable');
  }
  logger.error({ event: 'payment_network_error' }, error instanceof Error ? error.stack : undefined);
  throw new ServiceUnavailableException('Failed to connect to payment service');
}

export function Retry(options: { maxAttempts: number; delayMs: number; exponentialBackoff?: boolean }) {
  return function (_target: object, _propertyKey: string, descriptor: PropertyDescriptor): PropertyDescriptor {
    const original = descriptor.value as (...args: unknown[]) => Promise<unknown>;
    descriptor.value = async function (this: unknown, ...args: unknown[]): Promise<unknown> {
      let lastError: unknown;
      for (let attempt = 1; attempt <= options.maxAttempts; attempt++) {
        try {
          return await original.apply(this, args);
        } catch (error: unknown) {
          lastError = error;
          if (attempt < options.maxAttempts) {
            const delay = options.exponentialBackoff ? options.delayMs * 2 ** (attempt - 1) : options.delayMs;
            await new Promise((resolve) => setTimeout(resolve, delay));
          }
        }
      }
      throw lastError;
    };
    return descriptor;
  };
}
```

### Usage

```typescript
@Injectable()
export class ExternalServiceClient {
  @Retry({ maxAttempts: 3, delayMs: 1000, exponentialBackoff: true })
  async fetchData(): Promise<Data> {
    return this.httpService.get('/api/data');
  }
}
```

---

## 8. Caching Strategy

### Service-Level Caching

```typescript
import { Injectable } from '@nestjs/common';
import { CACHE_MANAGER } from '@nestjs/cache-manager';
import { Cache } from 'cache-manager';
import { Inject } from '@nestjs/common';

@Injectable()
export class ProductService {
  constructor(
    @Inject(CACHE_MANAGER) private cacheManager: Cache,
    private readonly productRepository: ProductRepository,
  ) {}

  async findOne(principal: Principal, id: string): Promise<ProductResponse> {
    // Tenant in the key: a shared cache must never serve one tenant's row to another.
    const cacheKey = `product:${principal.tenantId}:${id}`;

    // Try cache first
    const cached = await this.cacheManager.get<ProductResponse>(cacheKey);
    if (cached) {
      return cached;
    }

    // Fetch from database
    const product = await this.productRepository.findById(principal.tenantId, id);
    if (product === null) {
      throw new NotFoundException('Product not found', { errorCode: 'PRODUCT_NOT_FOUND' });
    }

    const response = toProductResponse(product);

    // Cache for 5 minutes
    await this.cacheManager.set(cacheKey, response, 300_000);

    return response;
  }

  async update(principal: Principal, id: string, input: UpdateProduct): Promise<ProductResponse> {
    const updated = await this.productRepository.update(principal.tenantId, id, input);

    // Invalidate cache on update
    await this.cacheManager.del(`product:${principal.tenantId}:${id}`);

    return toProductResponse(updated);
  }
}
```

---

## 9. Implementation Checklist

- [ ] Prisma schema designed with proper relations and indexes
- [ ] Database migrations created and tested
- [ ] Feature module, controller, and service generated
- [ ] Request schemas (`z.strictObject`) declared on every `@Body`/`@Param`/`@Query` with `{ schema }`
- [ ] Response schemas (`z.object`) applied with `@SerializeOptions({ schema })`; Swagger generated from them
- [ ] Pagination, filtering, and sorting implemented (sort fields allow-listed)
- [ ] Response mapping converts types only (Decimal, Date); the response schema decides the fields
- [ ] Repository layer with Prisma queries
- [ ] Service layer with business logic
- [ ] External service clients with circuit breaker
- [ ] Type-safe configuration for external APIs
- [ ] File upload endpoint with validation
- [ ] Bulk operations for create/update/delete
- [ ] Soft delete via a `$extends` query extension (Prisma `$use` middleware no longer exists)
- [ ] API versioning strategy applied
- [ ] Swagger decorators on all endpoints
- [ ] OpenAPI JSON exported for API gateway
- [ ] Error responses follow RFC 9457 ProblemDetail
- [ ] Prisma errors mapped to HTTP status codes
- [ ] Unit tests for service methods
- [ ] Integration tests with supertest
- [ ] Contract tests for external APIs
- [ ] Environment variables validated at startup
- [ ] Logging added for audit trail
- [ ] Health check endpoint created
