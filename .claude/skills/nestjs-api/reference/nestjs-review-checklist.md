# NestJS Code Review Checklist

## Issue Severity

| Level | Label | Criteria | Action |
|-------|-------|----------|--------|
| **P0** | CRITICAL | Production blocker: no validation, security holes, data loss | Must fix before merge |
| **P1** | HIGH | Major impact: missing resilience, <90% coverage, no error handling | Fix in current sprint |
| **P2** | MEDIUM | Code quality: duplication, complexity >10, missing docs | Fix in next sprint |
| **P3** | LOW | Style: naming, optional optimizations, minor improvements | Backlog |

## 10 Review Areas

### P0 — Review First

**1. Module Correctness**
- Proper `@Module()` decorators with correct imports/providers/exports
- No circular dependencies between modules
- `@Global()` only on CoreModule and ConfigModule
- Constructor injection (not property injection)
- `@Injectable()` on all services

**2. Authentication, authorization and tenant isolation** (verified patterns: `nestjs-production-baseline.md`)
- Auth guard is global (`APP_GUARD`); public routes opt out with `@Public()`. A controller without a guard and without `@Public()` is a CRITICAL finding only if the global guard is missing
- JWT verification pins `algorithms`, checks `issuer` + `audience`, requires `exp` and the tenant claim; issuer/audience read with `getOrThrow` (an `undefined` audience silently disables the check in `jsonwebtoken`/`passport-jwt`)
- Tenant/owner/role comes from the verified principal only — never from body, query, path or a client header (CRITICAL)
- Every repository/Prisma query on tenant data filters by `tenantId`; cross-tenant reads answer 404, not 403 or 200
- Role/permission checks → 403; per-resource ownership checks live in the service, in one shared predicate (no copies)
- Guard order: throttler → authentication → authorization; a guard reading `request.principal` runs after the one that sets it
- WebSocket gateways authenticate in `server.use()` (socket.io) / `verifyClient` (`WsAdapter`), not in an async `handleConnection`
- Guards/secrets built from config refuse empty values at startup (an empty expected secret admits a present-but-empty header)

**2b. Input and transport security**
- Input validation: every `@Body()`, `@Param()` and `@Query()` declares `{ schema }` (Zod 4, Standard Schema); a parameter without a schema is NOT validated by the global `StandardSchemaValidationPipe` (CRITICAL on a write endpoint)
- Request schemas are `z.strictObject` (a `z.object` silently drops a smuggled `tenantId`; verified: changing one made 2 negative tests fail); every string/array bounded; query numbers via `z.coerce`
- Responses that return entities declare `@SerializeOptions({ schema })` with a `z.object` response schema, and the global `StandardSchemaSerializerInterceptor` is registered (otherwise `passwordHash`/`tenantId` leak)
- Invalid input returns 400 (both pipes' default); a doc or test expecting 422 is wrong unless `errorHttpStatusCode` is set
- class-validator codebase (still supported in NestJS 12): global `ValidationPipe` with `whitelist`, `forbidNonWhitelisted`, `transform`, `enableImplicitConversion: false`; a module mixing class-validator DTOs and Zod schemas is a P2 finding
- `Public` / `Roles` built with `Reflector.createDecorator<T>()`; `routeConflictPolicy: { duplicate: 'error' }` set on `NestFactory.create` (NestJS 12 opt-in)
- Domain errors carry a stable `errorCode` (`new NotFoundException('…', { errorCode: 'ORDER_NOT_FOUND' })`), not a parsed message
- No hardcoded secrets, API keys, or passwords
- Helmet middleware registered with CSP, HSTS, X-Frame-Options
- CORS properly scoped (not wildcard `*` in production)
- Rate limiting configured (`@nestjs/throttler`): shared storage when >1 instance (`@nest-lab/throttler-storage-redis` 1.2.0 does not install on NestJS 12: see `nestjs-rate-limiting.md` for the interim options); tracker hashes credentials
- Webhooks verified over the raw body with a length check before `timingSafeEqual`
- Dependencies exist on npm (`npm view`), are pinned, and `npm audit --audit-level=high` is clean (or the override is documented)

**3. Error Handling**
- Custom exceptions extend `BaseException`
- Global exception filter produces structured ProblemDetail responses
- Prisma errors handled (P2002 → 409, P2025 → 404). Prisma 7 + driver adapter: P2002 has no `meta.target`; code reading it silently never matches. Never echo `meta` to clients
- No swallowed exceptions (empty catch blocks)
- All async operations in try-catch or with proper error propagation

**4. Testing**
- Unit tests for services with mocked dependencies
- E2E tests through the production `configureApp()` (`app.inject()` or supertest) with negative cases: no token 401, wrong audience 401, missing role 403, other tenant 404, unknown field 400, throttled 429
- Test env for `ConfigModule.forRoot({ validationSchema })` set in the Vitest config, not in `beforeAll` (the module validates when it is imported)
- No Jest APIs, no `poolOptions` (removed in Vitest 4; still absent in Vitest 5.1), no `retry`/`passWithNoTests` hiding failures
- `@nestjs/testing` Test.createTestingModule for DI setup
- Circuit breaker tested: happy path + open state + fallback
- Coverage >= 90% line, 80% branch

**5. TypeScript Strictness**
- `strict: true` in tsconfig
- No `any` types (use `unknown` and narrow)
- Proper use of generics and type inference
- Interface segregation for service contracts

### P1 — Review Second

**6. Resilience Patterns**
- All external calls (DB, HTTP, Redis) have circuit breaker protection
- Timeout configured on all external calls
- Database fallback service used for critical reads
- Request context propagated via AsyncLocalStorage

**7. Performance**
- Prisma queries optimized (select specific fields, use `include` sparingly)
- No N+1 queries (use `include` or batch queries)
- Redis caching for frequently accessed data
- Connection pools configured (Prisma, Redis)
- Interactive transactions set `isolationLevel`, `maxWait`, `timeout`; no HTTP/queue calls inside; conditional `updateMany` instead of read-then-write
- `$extends` instead of `$use` (removed in Prisma 5; absent from the Prisma 7 client)

**8. Observability**
- Structured logging with correlation IDs
- Meaningful log messages at appropriate levels
- Health indicators for critical dependencies (DB, Redis, external APIs) with `@nestjs/terminus` 12 `HealthIndicatorService` (`check(key).up()/.down()/.attempt()`, `.withTimeout()`); `HealthIndicator` / `HealthCheckError` no longer exist (compile error)
- OpenTelemetry configured for distributed tracing, loaded with `node --import ./dist/instrumentation.js` (SDK 3.x: `spanProcessors: [...]`, `new SimpleSpanProcessor({ exporter })`, `resourceFromAttributes`)
- `app.enableShutdownHooks()` is the only signal handler (an extra `process.on('SIGTERM')` makes shutdown hooks run twice); `onModuleDestroy` closes Prisma/Redis/workers. NestJS 12 orders lifecycle hooks by module hierarchy level: code that relied on v11 sibling order is a finding
- BullMQ handlers idempotent (job id = business id), bounded attempts with backoff, `UnrecoverableError` for poison payloads; `ioredis` is a direct dependency (BullMQ 6 made it optional: missing → runtime failure)

### P2 — Review Last

**9. Architecture**
- Module aggregation: ConfigModule → CommonModule → CoreModule → FeaturesModule
- Feature modules are self-contained (own controller, service, repository, schemas)
- No business logic in controllers
- Configuration externalized via `@nestjs/config` with fail-fast validation
- `.env` file contains ALL required env vars with working defaults — no `??` fallbacks in config code
- Every `getRequired*()` call in config files has a matching entry in `.env`
- `DATABASE_URL` in `.env` matches `docker-compose.dev.yml` credentials
- Prisma 7.x: `provider = "prisma-client"` (not `prisma-client-js`), no `url` in schema, `prisma.config.ts` present
- PrismaService uses composition with `@prisma/adapter-pg` (not `extends PrismaClient`)
- ESM package (`"type": "module"`): relative imports end in `.js`, no `__dirname`/`require()`; a missing extension is a TS2307 under `nodenext`

**10. Documentation**
- Public APIs have Swagger decorators (`@ApiTags`, `@ApiOperation`, error `@ApiResponse`s); success bodies come from the route schemas (`@ApiOkResponse({ standardSchema })`), not hand-written `@ApiProperty` copies
- Non-obvious logic has comments explaining WHY
- CHANGELOG updated for user-facing changes

## Output Format

For each issue found, report:

```
[P0] Missing input validation
File: src/features/products/controllers/products.controller.ts:25
Problem: @Body() declares no schema, so the global StandardSchemaValidationPipe passes the raw body through
Current:
    @Post()
    create(@Body() body: CreateProduct) {
Fix:
    @Post()
    create(@Body({ schema: CreateProductSchema }) body: CreateProduct) {
```

And confirm `{ provide: APP_PIPE, useValue: new StandardSchemaValidationPipe() }` is registered in app.module.ts.

## Summary Template

After reviewing all files, provide:

```
## Review Summary

**Files reviewed**: [count]
**Issues found**: P0: [n] | P1: [n] | P2: [n] | P3: [n]

### Decision
- [ ] APPROVE — no P0/P1 issues
- [ ] APPROVE WITH CONDITIONS — P1 issues documented
- [ ] BLOCK — P0 issues must be fixed

### Critical Issues (if any)
1. [file:line] — [one-line description]

### Positive Highlights
- [what's done well]
```

## Reference

For code patterns and correct implementations, read the `nestjs-api` skill reference files:
- `nestjs-production-baseline.md` — runtime-verified auth, tenancy, validation, throttling, WebSocket, shutdown and test patterns
- `nestjs-rate-limiting.md` — throttler order, tracker, Redis storage
- `nestjs-config-basics.md` — Static config reader, config module aggregation, fail-fast validation
- `nestjs-config-npm-ts.md` — package.json, tsconfig.json
- `nestjs-config-prisma7.md` — Prisma 7.x schema, prisma.config.ts, .env template
- `nestjs-templates-core.md` — main.ts, AppModule, CoreModule templates
- `nestjs-templates-features.md` — Feature module, controller, service, schema templates
- `nestjs-templates-infrastructure.md` — Dockerfile, docker-compose, Vitest config
- `nestjs-enterprise-patterns.md` — Exception hierarchy, validation pipe, API versioning
- `nestjs-enterprise-infrastructure.md` — Security middleware (Helmet), rate limiting, Swagger, health checks
- `nestjs-resilience-circuit-breaker.md` — Circuit breaker, retry, timeout, database fallback
- `nestjs-resilience-context.md` — Request context with AsyncLocalStorage, correlation IDs
- `nestjs-feature-flags.md` — Feature flags service, Redis fallback, gradual rollout
- `nestjs-observability.md` — OpenTelemetry tracing/metrics, structured logging, cloud logging
- `nestjs-messaging-basics.md` — BullMQ queues, background job processing
- `nestjs-messaging-queues.md` — RabbitMQ reliable messaging, dead letter queues
- `nestjs-messaging-streaming.md` — Kafka event streaming, high-throughput patterns
- `nestjs-testing-unit-basics.md` — Unit testing with Vitest, service test patterns
- `nestjs-testing-unit-controllers.md` — Controller unit tests, test data factories
- `nestjs-testing-unit-mocks.md` — Prisma/Redis/HTTP mocking, ConfigService mocking
- `nestjs-testing-integration-setup.md` — E2E testing setup, Testcontainers, supertest
- `nestjs-testing-integration-patterns.md` — Auth testing, validation, pagination patterns
- `nestjs-testing-patterns.md` — Circuit breaker testing, AsyncLocalStorage testing
- `nestjs-testing-ci-troubleshooting.md` — Coverage standards, CI/CD, troubleshooting
- `nestjs-rest-workflow.md` — REST workflow, OpenAPI/Swagger controller setup
- `nestjs-rest-dto-pagination.md` — Response mapping, pagination, filter schemas
- `nestjs-rest-upload-errors.md` — File uploads, API versioning, ProblemDetail errors
- `nestjs-rest-services.md` — Service patterns, external API clients, bulk operations, soft delete
- `nestjs-security-auth.md` — JWT authentication (RS256), password hashing, token management
- `nestjs-security-scanning.md` — OWASP scanning, security headers, static analysis
- `nestjs-security-validation-logging.md` — Input validation, PII masking, Prisma security
- `nestjs-debugging-logging.md` — Debug mode, Prisma query logging, Fastify lifecycle
- `nestjs-debugging-context-di.md` — AsyncLocalStorage context, DI debugging, config
- `nestjs-debugging-performance.md` — Memory leaks, performance profiling
- `nestjs-debugging-production.md` — Production debugging, structured logging, tracing
