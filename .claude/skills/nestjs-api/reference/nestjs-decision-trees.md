# NestJS Decision Trees

Architectural decision guides for NestJS 12.x + Fastify + Prisma. Use when the right approach is unclear before implementation.

---

## Module Organization by Feature Complexity

Use this before creating a new module to decide how to structure it:

```
Feature Complexity:
|
+-- Simple CRUD (no domain logic, straightforward data access)
|   -> Single module: controller + service + Prisma repository inline
|   -> No separate domain layer needed
|
+-- Domain logic present (business rules, validation, invariants)
|   -> Separate domain service (business rules) from infrastructure service (Prisma)
|   -> Consider ddd-architect skill for bounded contexts
|
+-- Logic shared across 2+ features
|   -> Create shared module in src/common/ with exports
|   -> Rule of Three: extract only when 3+ features need it
|
+-- Calling external API
|   -> Create dedicated client module with HttpModule
|   -> Add circuit breaker (see nestjs-resilience-circuit-breaker.md)
|
+-- Background processing needed
|   -> Add BullMQ queue (see nestjs-messaging-basics.md)
|   -> Keep queue module separate from feature module
|
+-- This feature will be extracted as a microservice later
    -> Treat module boundaries strictly NOW — no cross-module Prisma access
    -> Use events for cross-module communication, not direct service injection
```

### Module Aggregation Order (workspace standard)

```
ConfigModule -> CommonModule -> CoreModule -> FeaturesModule
```

- `ConfigModule`: environment config, fail-fast validation
- `CommonModule`: shared utilities, guards, interceptors, pipes
- `CoreModule`: database (DatabaseModule), Redis, external clients
- `FeaturesModule`: all feature modules (users, payments, etc.)

---

## Authentication Method Selection

Use when adding auth to a new service or route:

```
What are your security requirements?
|
+-- Stateless API (most REST endpoints)
|   -> JWT with short-lived access token + refresh token
|   -> Workspace standard: RS256, JwtAuthGuard (see nestjs-security-auth.md)
|
+-- Session-based (legacy, SSR, or admin panel)
|   -> Express sessions with Redis store
|   -> Not standard for this workspace — discuss before implementing
|
+-- OAuth / Social login
|   -> Passport.js with provider strategy (Google, GitHub, etc.)
|   -> Add alongside existing JWT guard, not replacing it
|
+-- Multi-tenant SaaS
|   -> JWT with tenant claims in payload
|   -> TenantGuard extracts and validates tenant from token
|
+-- Service-to-service (microservice internal calls)
|   -> mTLS or shared secret in Authorization header
|   -> Never reuse user-facing JWT for service auth
```

---

## Testing Strategy Selection

Use when deciding what level of test to write:

```
What needs to be tested?
|
+-- Business logic in a service (calculations, rules, transformations)
|   -> Unit test with Vitest + mocked DatabaseService
|   -> No real database, no HTTP — pure function testing
|
+-- API contract (request shape, response shape, status codes)
|   -> Integration test with supertest + Testcontainers (real PostgreSQL)
|   -> See nestjs-testing-integration-setup.md
|
+-- Full user flow (login -> action -> result)
|   -> E2E test with supertest against full app instance
|   -> See nestjs-testing-integration-patterns.md
|
+-- Resilience behaviour (circuit breaker, retry, fallback)
|   -> Unit test with mocked external service that throws
|   -> See nestjs-testing-patterns.md
|
+-- Performance / load
|   -> k6 or Artillery against a staging environment
|   -> Not covered in unit/integration test suite
```

---

## Caching Strategy Selection

Use when adding caching to avoid over-engineering:

```
What is the data characteristic?
|
+-- User-specific data (profile, preferences, permissions)
|   -> Redis with user-scoped key: cache:user:{userId}:{resource}
|   -> TTL: 5-15 minutes; invalidate on user update
|
+-- Global/shared data (config, feature flags, lookup tables)
|   -> In-memory cache with TTL (NestJS CacheModule)
|   -> TTL: 1-5 minutes; acceptable eventual consistency
|
+-- Expensive database query result
|   -> Redis cache with query-fingerprint key
|   -> TTL: based on data volatility; invalidate on write
|
+-- Static assets or API responses for public endpoints
|   -> CDN cache headers (Cache-Control, ETag)
|   -> Not handled in NestJS — configure at infrastructure layer
|
+-- Computed/derived values (expensive calculations)
|   -> Memoization in service (in-memory Map with TTL check)
|   -> Only for single-instance deployments; Redis for multi-instance
```

---

## Error Response Strategy

Use when deciding how to surface errors to API consumers:

```
What kind of error occurred?
|
+-- Client sent invalid input
|   -> 400 Bad Request via StandardSchemaValidationPipe (default errorHttpStatusCode; verified on 12.6.0)
|   -> ProblemDetail body with field-level errors
|
+-- Resource not found
|   -> throw new NotFoundException('User not found', { errorCode: 'USER_NOT_FOUND' })
|   -> Global exception filter converts to 404 ProblemDetail
|
+-- Duplicate / conflict
|   -> Catch Prisma P2002 error -> throw new ConflictException()
|   -> 409 Conflict with field that caused conflict
|
+-- Client not authenticated
|   -> JwtAuthGuard throws 401 automatically
|   -> Do not throw 401 manually from service layer
|
+-- Client authenticated but not authorized
|   -> RolesGuard throws 403 automatically
|   -> Do not throw 403 manually from service layer
|
+-- External service failed (third-party API, email, etc.)
|   -> Log error with full context, throw 502 Bad Gateway or 503 Service Unavailable
|   -> Circuit breaker should activate after threshold (see nestjs-resilience-circuit-breaker.md)
|
+-- Unexpected internal error
|   -> Let it propagate — global exception filter catches and returns 500
|   -> Never swallow with empty catch block
```
