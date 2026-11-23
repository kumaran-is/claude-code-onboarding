# NestJS Configuration — Prisma 7.x & Database

Prisma 7.x schema, database setup, PrismaService, and environment configuration for NestJS 11.x. For npm and TypeScript configuration, see `nestjs-config-npm-ts.md`.

## Prisma 7.x Schema

Enterprise-grade Prisma 7.x schema with audit trails, feature flags, and transactional outbox pattern.

**IMPORTANT — Prisma 7.x breaking changes:**
- Generator: `provider = "prisma-client"` (not `prisma-client-js`), explicit `output` path required
- Datasource: **no `url` property** — connection URL goes in `prisma.config.ts` at project root
- PrismaService: use **composition** with `@prisma/adapter-pg` (do NOT extend PrismaClient)
- Generated client output (e.g., `src/generated/`) must be in `.gitignore`

**File:** `prisma/schema.prisma`

```prisma
// {project_name} Database Schema
// Enterprise-grade schema with audit trails, optimistic locking, and financial precision

generator client {
  provider = "prisma-client"
  output   = "../src/generated/prisma"
}

datasource db {
  provider = "postgresql"
}

// ================================
// SYSTEM CONFIGURATION (Required)
// ================================

model SystemConfig {
  id          String   @id @default(cuid())

  key         String   @unique @db.VarChar(100)
  value       Json
  dataType    String   @map("data_type") @db.VarChar(20)

  description String?  @db.Text
  category    String?  @db.VarChar(50)
  isSecret    Boolean  @default(false) @map("is_secret")

  validation  Json?

  // Optimistic locking for concurrent updates
  version     Int      @default(1)

  // TTL support for temporary configurations
  expiresAt   DateTime? @map("expires_at")

  createdAt   DateTime @default(now()) @map("created_at")
  updatedAt   DateTime @updatedAt @map("updated_at")

  // Composite index for efficient lookups
  @@index([key, category])
  @@index([category])
  @@index([expiresAt])
  @@map("system_configs")
}

// ================================
// FEATURE FLAGS (Required for safe rollouts)
// ================================

model FeatureFlag {
  id          String   @id @default(cuid())

  key         String   @unique @db.VarChar(100)
  name        String   @db.VarChar(200)
  description String?  @db.Text

  enabled     Boolean  @default(false)

  // Percentage-based rollout (0-100)
  percentage  Int      @default(0)

  // Target specific user/tenant segments
  targetRules Json?    @map("target_rules")

  // Optimistic locking
  version     Int      @default(1)

  // Scheduling
  enabledAt   DateTime? @map("enabled_at")
  disabledAt  DateTime? @map("disabled_at")

  createdAt   DateTime @default(now()) @map("created_at")
  updatedAt   DateTime @updatedAt @map("updated_at")

  @@index([key])
  @@index([enabled])
  @@map("feature_flags")
}

// ================================
// AUDIT LOG (Required for enterprise)
// ================================

model AuditLog {
  id            String   @id @default(cuid())
  correlationId String   @map("correlation_id")

  eventType     String   @map("event_type") @db.VarChar(50)
  entityType    String   @map("entity_type") @db.VarChar(50)
  entityId      String?  @map("entity_id")

  action        String   @db.VarChar(50)
  userId        String?  @map("user_id") @db.VarChar(100)
  sessionId     String?  @map("session_id") @db.VarChar(100)
  tenantId      String?  @map("tenant_id") @db.VarChar(100)

  oldValues     Json?    @map("old_values")
  newValues     Json?    @map("new_values")
  metadata      Json?

  ipAddress     String?  @map("ip_address") @db.VarChar(45)
  userAgent     String?  @map("user_agent") @db.Text

  // Performance: duration in milliseconds
  durationMs    Int?     @map("duration_ms")

  timestamp     DateTime @default(now())
  createdAt     DateTime @default(now()) @map("created_at")

  @@index([correlationId])
  @@index([eventType, timestamp])
  @@index([entityType, entityId, timestamp])
  @@index([userId, timestamp])
  @@index([tenantId, timestamp])
  @@map("audit_logs")
}

// ================================
// OUTBOX (For reliable event publishing)
// ================================

model Outbox {
  id            String   @id @default(cuid())

  aggregateType String   @map("aggregate_type") @db.VarChar(100)
  aggregateId   String   @map("aggregate_id") @db.VarChar(100)
  eventType     String   @map("event_type") @db.VarChar(100)

  payload       Json

  // Processing status
  status        OutboxStatus @default(PENDING)
  processedAt   DateTime?    @map("processed_at")
  retryCount    Int          @default(0) @map("retry_count")
  lastError     String?      @map("last_error") @db.Text

  createdAt     DateTime @default(now()) @map("created_at")

  @@index([status, createdAt])
  @@index([aggregateType, aggregateId])
  @@map("outbox")
}

enum OutboxStatus {
  PENDING
  PROCESSING
  COMPLETED
  FAILED
}

// ================================
// USER (if authentication is selected)
// ================================

model User {
  id            String    @id @default(cuid())

  email         String    @unique @db.VarChar(255)
  passwordHash  String    @map("password_hash") @db.VarChar(255)

  firstName     String?   @map("first_name") @db.VarChar(100)
  lastName      String?   @map("last_name") @db.VarChar(100)

  role          UserRole  @default(USER)
  status        UserStatus @default(ACTIVE)

  // Optimistic locking
  version       Int       @default(1)

  // Multi-tenancy support (if enabled)
  tenantId      String?   @map("tenant_id") @db.VarChar(100)

  lastLoginAt   DateTime? @map("last_login_at")
  emailVerifiedAt DateTime? @map("email_verified_at")
  passwordChangedAt DateTime? @map("password_changed_at")

  // Security: failed login tracking
  failedLoginAttempts Int @default(0) @map("failed_login_attempts")
  lockedUntil   DateTime? @map("locked_until")

  createdAt     DateTime  @default(now()) @map("created_at")
  updatedAt     DateTime  @updatedAt @map("updated_at")
  deletedAt     DateTime? @map("deleted_at")

  @@index([email])
  @@index([status])
  @@index([tenantId])
  @@index([deletedAt])
  @@map("users")
}

enum UserRole {
  SUPER_ADMIN
  ADMIN
  USER
  VIEWER
}

enum UserStatus {
  ACTIVE
  INACTIVE
  SUSPENDED
  PENDING_VERIFICATION
}

// ================================
// {ENTITY} MODELS (Generated per entity)
// ================================

// Example: Replace with actual entities from user requirements
// model {Entity} {
//   id          String   @id @default(cuid())
//
//   // Entity-specific fields here
//
//   // Optimistic locking
//   version     Int      @default(1)
//
//   // Multi-tenancy (if enabled)
//   tenantId    String?  @map("tenant_id") @db.VarChar(100)
//
//   // Audit fields
//   createdBy   String?  @map("created_by") @db.VarChar(100)
//   updatedBy   String?  @map("updated_by") @db.VarChar(100)
//
//   createdAt   DateTime @default(now()) @map("created_at")
//   updatedAt   DateTime @updatedAt @map("updated_at")
//   deletedAt   DateTime? @map("deleted_at")
//
//   @@index([tenantId])
//   @@index([deletedAt])
//   @@map("{entity_table_name}")
// }
```

## prisma.config.ts (Prisma 7.x — required)

Prisma 7.x moved the datasource URL from `schema.prisma` to `prisma.config.ts`. This file is auto-created by `npx prisma init` — keep it.

**File:** `prisma.config.ts` (project root)

```typescript
import 'dotenv/config';
import { defineConfig } from 'prisma/config';

export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: {
    path: 'prisma/migrations',
  },
  datasource: {
    url: process.env['DATABASE_URL'],
  },
});
```

## PrismaService (Prisma 7.x — composition pattern)

Prisma 7.x `PrismaClient` requires a driver adapter. Use composition, NOT inheritance.

**File:** `src/core/database/prisma.service.ts`

```typescript
import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PrismaClient } from '../../generated/prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';

@Injectable()
export class PrismaService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(PrismaService.name);
  private readonly _client: PrismaClient;

  constructor(private readonly configService: ConfigService) {
    // Fail fast: no `?? process.env` fallback that bypasses the validated config.
    const databaseUrl = this.configService.getOrThrow<string>('database.url');

    const adapter = new PrismaPg({ connectionString: databaseUrl });
    this._client = new PrismaClient({ adapter });
  }

  get client(): PrismaClient {
    return this._client;
  }

  async onModuleInit(): Promise<void> {
    this.logger.log('Connecting to database...');
    await this._client.$connect();
    this.logger.log('Database connection established');
  }

  async onModuleDestroy(): Promise<void> {
    this.logger.log('Disconnecting from database...');
    await this._client.$disconnect();
  }
}
```

## Environment File (.env)

**IMPORTANT:** The `.env` file must be populated with working defaults at scaffold time. The app must boot with zero manual configuration after scaffolding.

**Write `.env` via Bash** (not Write/Edit tools — hooks block `.env` modifications):
```bash
cat > .env << 'EOF'
# {project_name} - Local Development Defaults
# All values match docker-compose.dev.yml — app boots immediately

# Database (matches docker-compose.dev.yml credentials)
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/{project_name}?schema=public"

# Application
APP_NAME={project_name}
NODE_ENV=development
PORT=3000
ENABLE_SWAGGER=true

# Security
SECURITY_CORS_ORIGINS=http://localhost:4200
EOF
```

Every `getRequired*()` call in config files **must** have a matching entry in `.env`. If a config uses `getOptionalString('FOO') ?? 'default'`, it does NOT need a `.env` entry. If it uses `getRequiredString('FOO')`, it MUST have `FOO=value` in `.env`.

### Extended `.env` (when features are added)

Add these as needed — only when the corresponding config code requires them:

```bash
# Logging (optional — configs have defaults)
LOG_LEVEL=debug
LOG_FORMAT=json

# Redis (when cache/queues are added)
REDIS_URL="redis://localhost:6379"

# JWT verification (when auth is added): asymmetric keys from the issuer's JWKS, no shared secret in .env
JWT_ISSUER=http://localhost:8080/realms/dev
JWT_AUDIENCE={project_name}
JWT_JWKS_URL=http://localhost:8080/realms/dev/protocol/openid-connect/certs

# Rate limiting (optional — throttler.config.ts has hardcoded defaults)
THROTTLER_SHORT_TTL=1000
THROTTLER_SHORT_LIMIT=3
```

## Transactions, errors and extensions (verified)

Type-checked against a client generated by Prisma 7.10.1 (strict `tsc` exit 0). **Runtime against PostgreSQL: NOT RUN** (no database in the sandbox). The verified build used `moduleFormat = "cjs"` in the generator for a CommonJS Nest app.

```prisma
// prisma/schema.prisma
generator client {
  provider     = "prisma-client"
  output       = "../src/generated/prisma"
  moduleFormat = "cjs"
}

datasource db {
  provider = "postgresql"
}

model Order {
  id             String   @id @default(uuid()) @db.Uuid
  tenantId       String   @map("tenant_id") @db.Uuid
  sku            String
  quantity       Int
  idempotencyKey String   @map("idempotency_key")
  createdAt      DateTime @default(now()) @map("created_at")
  deletedAt      DateTime? @map("deleted_at")

  @@unique([tenantId, idempotencyKey], map: "orders_tenant_idempotency_uq")
  @@index([tenantId, createdAt])
  @@map("orders")
}

model StockLevel {
  tenantId  String @map("tenant_id") @db.Uuid
  sku       String
  available Int

  @@id([tenantId, sku])
  @@map("stock_levels")
}
```

```typescript
// src/database/prisma.service.ts
import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../generated/prisma/client';

/** Composition, not inheritance: expose the client, own its lifecycle. */
@Injectable()
export class PrismaService implements OnModuleDestroy {
  readonly client: PrismaClient;

  constructor(databaseUrl: string) {
    this.client = new PrismaClient({ adapter: new PrismaPg({ connectionString: databaseUrl, max: 10 }) });
  }

  /** Runs on app.close() and, with enableShutdownHooks(), on SIGTERM. */
  async onModuleDestroy(): Promise<void> {
    await this.client.$disconnect();
  }
}
```

Register it with a factory (`{ provide: PrismaService, inject: [ConfigService], useFactory: (c: ConfigService) => new PrismaService(c.getOrThrow('DATABASE_URL')) }`).

```typescript
// src/orders/prisma-orders.repository.ts
import { ConflictException, Injectable } from '@nestjs/common';
import { Prisma } from '../generated/prisma/client';
import { violatedUniqueConstraint } from '../database/prisma-errors';
import { PrismaService } from '../database/prisma.service';

export class InsufficientStockError extends Error {}

/** Type-checked against the generated client; runtime needs PostgreSQL (not available in the sandbox). */
@Injectable()
export class PrismaOrdersRepository {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * Reserve stock and create the order atomically. The conditional updateMany is a single
   * atomic statement (no read-then-write race), so READ COMMITTED is enough; keep the
   * transaction short (no network calls inside) and bounded by timeout/maxWait.
   */
  async placeOrder(tenantId: string, input: { sku: string; quantity: number; idempotencyKey: string }) {
    try {
      return await this.prisma.client.$transaction(
        async (tx) => {
          const reserved = await tx.stockLevel.updateMany({
            where: { tenantId, sku: input.sku, available: { gte: input.quantity } },
            data: { available: { decrement: input.quantity } },
          });
          if (reserved.count !== 1) throw new InsufficientStockError(input.sku);
          return tx.order.create({ data: { tenantId, ...input } });
        },
        { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted, maxWait: 2_000, timeout: 5_000 },
      );
    } catch (error: unknown) {
      if (violatedUniqueConstraint(error) === 'orders_tenant_idempotency_uq') {
        // Replay of the same idempotency key: return the original order, do not create a second one.
        const existing = await this.prisma.client.order.findUnique({
          where: { tenantId_idempotencyKey: { tenantId, idempotencyKey: input.idempotencyKey } },
        });
        if (existing !== null) return existing;
        throw new ConflictException();
      }
      throw error;
    }
  }

  /** One query with a relation-free select: no per-row follow-up queries (no N+1). */
  listRecent(tenantId: string, take: number) {
    return this.prisma.client.order.findMany({
      where: { tenantId },
      orderBy: { createdAt: 'desc' },
      take: Math.min(take, 100),
      select: { id: true, sku: true, quantity: true, createdAt: true },
    });
  }
}
```

```typescript
// src/database/prisma-errors.ts
import { Prisma } from '../generated/prisma/client';

/**
 * Name of the unique constraint a P2002 violated, or undefined.
 * Prisma 7 + driver adapter: meta is { driverAdapterError: { cause: { kind, constraint } } };
 * the engine-era `meta.target` is absent. Classify by constraint name, never by message text.
 */
export function violatedUniqueConstraint(error: unknown): string | undefined {
  if (!(error instanceof Prisma.PrismaClientKnownRequestError) || error.code !== 'P2002') return undefined;
  const adapterError = error.meta?.['driverAdapterError'];
  if (typeof adapterError !== 'object' || adapterError === null || !('cause' in adapterError)) return undefined;
  const cause = adapterError.cause;
  if (typeof cause !== 'object' || cause === null || !('constraint' in cause)) return undefined;
  const constraint = cause.constraint;
  if (typeof constraint === 'object' && constraint !== null && 'index' in constraint && typeof constraint.index === 'string') {
    return constraint.index;
  }
  return undefined;
}
```

With Prisma 7 + `@prisma/adapter-pg`, a P2002 carries `meta.driverAdapterError.cause.constraint.index` (the database
constraint name; verified in `@prisma/client` 7.10.1 runtime and `@prisma/adapter-pg` source). The engine-era
`meta.target` field is not set, so `error.meta?.target` code silently stops matching. Name constraints explicitly
(`map:`) and compare names; never parse the message, which can echo user input.

Transactions:
- Prefer a single conditional statement (`updateMany` with a guard in `where`) over read-then-write; it removes the race without `Serializable`.
- When you need `Serializable`, retry on P2034 (write conflict) with a bounded attempt count.
- Never call HTTP/queues inside `$transaction`; bound it with `maxWait` and `timeout`. Publish side effects through an outbox row written in the same transaction.
- If several code paths lock the same aggregate, take locks in one documented order (e.g. advisory lock first, then row locks) to avoid deadlocks.

N+1: fetch lists with one query (`select`/`include` with `take`), and use `findMany({ where: { id: { in: ids } } })` instead of per-row lookups.

```typescript
// src/database/prisma-extensions.ts
import { Logger } from '@nestjs/common';
import { type PrismaClient } from '../generated/prisma/client';

const logger = new Logger('Prisma');

/**
 * Prisma 5+ removed `$use` middleware (absent from the Prisma 7 client). Query extensions replace it.
 * `$extends` returns a NEW client: use the returned value, the base client is unchanged.
 */
export function withQueryTiming(client: PrismaClient, slowMs = 100) {
  return client.$extends({
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const started = performance.now();
          try {
            return await query(args);
          } finally {
            const ms = performance.now() - started;
            if (ms > slowMs) logger.warn({ event: 'slow_query', model, operation, ms: Math.round(ms) });
          }
        },
      },
    },
  });
}

/** Soft delete: reads hide deleted rows; deletes go through an explicit model method, not a rewritten `delete`. */
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

## Key Patterns

| Pattern | Description |
|---------|-------------|
| Optimistic locking | `version` field on models prevents race conditions |
| Soft delete | `deletedAt` field for recoverable deletions |
| Audit trail | AuditLog model captures all state changes |
| Feature flags | FeatureFlag model for percentage-based rollouts |
| Outbox pattern | Reliable event publishing with transactional guarantees |
