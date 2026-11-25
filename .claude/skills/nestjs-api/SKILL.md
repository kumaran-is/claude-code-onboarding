---
name: nestjs-api
description: Patterns and runtime-verified templates for NestJS 12.x (12.6.0) on Fastify, ESM, with Zod Standard Schema validation, Prisma 7 and TypeScript 6. Use when creating or changing NestJS modules, controllers, services, schemas/DTOs, guards, interceptors, exception filters, JWT auth and tenant scoping, rate limiting, WebSocket gateways, BullMQ jobs, health checks, OpenTelemetry, Prisma transactions, OpenAPI docs, or Vitest unit/e2e tests, or upgrading a NestJS 11 app to 12. Optional for plain Node services (see typescript-expert).
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: NestJS, Nest, NestJS module, NestJS controller, NestJS service, NestJS guard, StandardSchemaValidationPipe, ValidationPipe, ThrottlerGuard, WebSocketGateway, BullMQ, Terminus, Prisma transaction, Fastify adapter, nest upgrade
  related-skills: nestjs-coding-standard, openapi-spec-generation, database-schema-designer
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-24"
---

## Iron Law

**NO NESTJS MODULE WITHOUT READING `reference/nestjs-conventions.md` AND `reference/nestjs-production-baseline.md` FIRST — the baseline is the runtime-verified reference for auth, tenant scoping, validation, rate limiting, WebSockets, shutdown and tests; every rule there has a negative test**

# NestJS 12.x + Fastify + Prisma REST API Skill

**Versions (verified 2026-11-24 with `npm view`, Node 26.13.1):** NestJS `12.6.0`, Fastify `5.12.8`, Zod `4.6.7`, Prisma `7.10.1`
(8.x is a release candidate), TypeScript `6.0.3` (7.x is not accepted by `@nestjs/schematics` 12), Vitest `5.1.1`, oxlint `1.95.0`.
Satellites have their own lines (`@nestjs/swagger` 12.1.2, `@nestjs/config` 12.1.1, `@nestjs/terminus` 12.2.0, `@nestjs/bullmq` 12.0.2,
`@nestjs/throttler` 6.8.0). Pins and rationale: `reference/nestjs-config-npm-ts.md`.

## NestJS 12 at a glance

| Feature | Status here | Why |
|---|---|---|
| ESM (`"type": "module"`, `.js` relative imports) | ADOPT | v12 packages ship as ESM; new projects start ESM |
| `StandardSchemaValidationPipe` + `@Body({ schema })` (Zod) | ADOPT | one schema validates, types and documents (Swagger 12 reads it) |
| `StandardSchemaSerializerInterceptor` + `@SerializeOptions({ schema })` | ADOPT | response allowlist: undeclared fields (e.g. `passwordHash`) never leave |
| `HttpException` `errorCode` | ADOPT | stable machine-readable error codes |
| `routeConflictPolicy: { duplicate: 'error', shadow: 'warn' }` | ADOPT | duplicate routes fail at bootstrap |
| `ConsoleLogger({ json: true })`, structured params (default on) | ADOPT | JSON logs without a logging library |
| Terminus `HealthIndicatorService` | ADOPT (required) | legacy `HealthIndicator` / `HealthCheckError` were removed |
| Terminus `FetchHealthIndicator` | ADOPT | replaces the deprecated `HttpHealthIndicator` (no `@nestjs/axios`); `verify` overrides the 2xx rule |
| `@MessageBody({ schema })` / `@Payload({ schema })` | ADOPT for gateways / microservices | same Zod schemas; bind `StandardSchemaValidationPipe` with a `WsException` / `RpcException` `exceptionFactory` |
| 12.5 limit defaults (WS `maxPayload` 1 MiB, socket.io `maxWaitingMessages` 10000, `maxConcurrentMessages` 1000, multipart `parts` 1000) | ADOPT (defaults) | raise per adapter only with a measured need; startup now fails on a guard/pipe that cannot run or an invalid `forRoutes()` |
| Fastify `FileInterceptor` (`@nestjs/platform-fastify/multipart`, 12.1+) | ADOPT | multer-shaped file, `ParseFilePipe` + `FileTypeValidator` (magic bytes) |
| `Reflector.createDecorator()` for metadata decorators | ADOPT | typed keys; what the v12 schematic generates |
| Vitest (ESM) / oxlint `--type-aware` | ADOPT | `nest new` 12 defaults; Jest only for existing CommonJS apps |
| `nest upgrade` | ADOPT for v11 apps | applies the mechanical changes; ESM conversion stays manual |
| `ValidationPipe` + class-validator | OPTIONAL | still supported and documented as an equal option; Zod-first is this toolkit's choice (one schema for validation, types, OpenAPI and MCP tools). Keep class-validator in existing codebases; do not mix both on one route |
| `--builder rspack` | OPTIONAL | monorepo default; `tsc` is enough for a single service |
| Request-scoped WebSocket gateways; `WsAdapter` `gracefulShutdown` (12.6) | OPTIONAL | only when per-connection state or the `ws` adapter is used |
| `@nestjs/observe` | DEFER | 0.3.x client for a hosted, paid service; no function without its app key; scaffold with `--no-observe` |
| `@nestjs/mcp` (MCP server inside a Nest app) | OPTIONAL (pre-1.0, 0.0.4) | official, SDK v2 2.4.0; for tools on an existing service. Standalone servers: `/scaffold-mcp-server`. Not a docs server |
| NestJS Observe MCP server | DEFER | Observe data for agents; paid plans only; never added to `.mcp.json` without the MCP security scan and approval |
| `nest deploy` (Mau) | NOT APPLICABLE | this stack deploys containers to Cloud Run via GitHub Actions |
| GraphQL `graphql-ws`, NATS v3 changes | NOT APPLICABLE | not used by this stack; see the migration guide if added |

## Conventions & Rules

> For code conventions, package layout, NestJS rules, Prisma 7.x rules, and environment file rules, read `reference/nestjs-conventions.md`
>
> Framework-neutral Node rules apply here too: config and secrets validated at startup ([node-service-engineering.md §3](../typescript-expert/references/node-service-engineering.md#3-configuration-and-secrets)), unhandled-rejection and shutdown policy (§11). `npm run build` uses `tsconfig.build.json`, which excludes specs: type-check them with `tsc -p tsconfig.json --noEmit`.

## Quick Scaffold — New NestJS Project

Run `/scaffold-nestjs-api <name>` in the main session. Running the Nest CLI creator directly is blocked by the
scaffold hook. The project is written from `reference/nestjs-config-npm-ts.md` and `reference/nestjs-production-baseline.md`
(Fastify, ESM, Zod, Prisma, Vitest, oxlint), which is what `nest new` 12 would need several rewrites to reach (Express default,
`@nestjs/observe` and agent-skill files enabled unless `--no-observe --skip-skills`).

**Upgrading a v11 app:** `npx @nestjs/cli@12 upgrade --dry-run`, review, then run it; fix the manual items it reports (Terminus
health indicators, `@Optional()` on redeclared subclass constructors, lifecycle-hook ordering assumptions, NATS/GraphQL if used).

## Process

1. **Scaffold** with `/scaffold-nestjs-api` (main session only)
2. **Configure** package.json and tsconfig — read `reference/nestjs-config-basics.md`, `reference/nestjs-config-npm-ts.md`, and `reference/nestjs-config-prisma7.md`
3. **Create files** using templates — read `reference/nestjs-templates-core.md` for main.ts, AppModule, CoreModule; read `reference/nestjs-templates-features.md` for feature modules, controllers, services, DTOs
4. **Follow conventions** below for package layout and NestJS rules
5. **Write tests** with Vitest: unit specs plus e2e through the production `configureApp()` using `app.inject()` against real PostgreSQL and Redis — include negative tests (401, 403, cross-tenant 404, 400 for unknown fields, 413, 429, no `passwordHash` in responses, schema-breaking response → 500)
6. **Format and check**: `npm run lint && npm run typecheck`

## Key Patterns

| Pattern | Implementation |
|---------|---------------|
| **Modules** | `@Module()` with imports/providers/exports, aggregation pattern |
| **Controllers** | `@Controller('api/v1/...')` with route decorators |
| **Services** | `@Injectable()` with constructor injection |
| **Schemas** | Zod `z.strictObject` request schemas via `@Body({ schema })`; `z.object` response schemas via `@SerializeOptions({ schema })`; no tenant/owner fields — those come from the token |
| **Repositories** | Prisma Client via `DatabaseService` wrapper |
| **Error handling** | Nest exceptions with `errorCode`; an RFC 9457 filter is optional (`nestjs-rest-upload-errors.md`) |
| **Config** | Zod env schema as `ConfigModule.forRoot({ validationSchema })`; `ConfigService<Env, true>` with `{ infer: true }` |
| **Migrations** | Prisma Migrate in `prisma/migrations/` |
| **Guards** | Global `APP_GUARD`s in order: `ThrottlerGuard` → `JwtAuthGuard` (opt out with `@Public()`); missing role → 403 |
| **Authorization** | Per-resource checks in services; repositories take `tenantId` from the verified principal; cross-tenant → 404 |
| **WebSockets** | Authenticate in socket.io middleware (`afterInit` → `server.use`), not `handleConnection` |
| **Transactions** | `$transaction(fn, { isolationLevel, maxWait, timeout })`; no network calls inside; outbox for side effects |
| **Shutdown** | `app.enableShutdownHooks()` only — no extra `process.on('SIGTERM')` |
| **Interceptors** | Global `StandardSchemaSerializerInterceptor`; logging via `ConsoleLogger({ json: true })` |
| **Pipes** | Global `StandardSchemaValidationPipe` (`APP_PIPE`); every external input declares a `schema` |
| **Health** | Terminus 12 `HealthIndicatorService` + `PrismaHealthIndicator`, each with `.withTimeout()` |

## Reference Files

| File | Content | Load When |
|------|---------|-----------|
| `reference/nestjs-production-baseline.md` | **Runtime-verified** reference: JWT verifier + global guards, tenant scoping, DTO validation, Fastify throttling, WebSocket auth, problem+json filter, shutdown, BullMQ, webhooks | **Before any feature work**; when reviewing auth, validation or tenancy |
| `reference/nestjs-rate-limiting.md` | Throttler order, credential-hash tracker, shared Redis storage (`@nest-lab/throttler-storage-redis` 1.2.0 peers on Nest ≤ 11: BLOCKED on 12, interim options there) | Adding or reviewing rate limits |
| `reference/nestjs-config-basics.md` | Static config reader, config module aggregation, fail-fast validation | Project setup, initial configuration |
| `reference/nestjs-config-npm-ts.md` | Verified pins, package.json (ESM), tsconfig (`nodenext`), Vitest 5, oxlint, audit override | Project setup, configuring dependencies |
| `reference/nestjs-config-prisma7.md` | Prisma 7.x schema, prisma.config.ts, PrismaService, transactions, P2002 under driver adapters, `$extends` | Setting up database, writing Prisma queries or transactions |
| `reference/nestjs-templates-core.md` | main.ts, app.module, core.module templates | Bootstrapping app, creating core module |
| `reference/nestjs-templates-features.md` | Feature module, controller, service, DTO templates | Creating modules, controllers, services |
| `reference/nestjs-templates-infrastructure.md` | Dockerfile, docker-compose, Vitest config | Containerizing app, configuring test runner |
| `reference/nestjs-enterprise-patterns.md` | Exception hierarchy, validation pipe, API versioning | Implementing error handling, input validation, API versioning |
| `reference/nestjs-enterprise-infrastructure.md` | Security middleware (Helmet), rate limiting, Swagger, health checks | Adding security headers, rate limiting, API documentation |
| `reference/nestjs-resilience-circuit-breaker.md` | Circuit breaker, retry, timeout, database fallback | Adding resilience patterns, handling service failures |
| `reference/nestjs-resilience-context.md` | Request context with AsyncLocalStorage, correlation IDs | Adding request tracing, correlation IDs |
| `reference/nestjs-feature-flags.md` | Feature flags service, Redis fallback, gradual rollout | Implementing feature flags, gradual rollout |
| `reference/nestjs-observability.md` | OpenTelemetry tracing/metrics, structured logging, cloud logging | Adding observability, structured logging, tracing |
| `reference/nestjs-messaging-basics.md` | BullMQ queues, background job processing | Adding background jobs, queue processing |
| `reference/nestjs-messaging-queues.md` | RabbitMQ reliable messaging, dead letter queues | Implementing RabbitMQ messaging, dead letter queues |
| `reference/nestjs-messaging-streaming.md` | Kafka event streaming, high-throughput patterns | Implementing Kafka streaming, high-throughput events |
| `reference/nestjs-testing-unit-basics.md` | Unit testing with Vitest, service test patterns | Writing unit tests for services |
| `reference/nestjs-testing-unit-controllers.md` | Controller unit tests, test data factories | Writing unit tests for controllers |
| `reference/nestjs-testing-unit-mocks.md` | Prisma/Redis/HTTP mocking, ConfigService mocking | Mocking dependencies in unit tests |
| `reference/nestjs-testing-integration-setup.md` | E2E testing setup, Testcontainers, supertest | Writing integration tests, E2E tests |
| `reference/nestjs-testing-integration-patterns.md` | Auth testing, validation, pagination patterns | Testing auth flows, pagination, validation |
| `reference/nestjs-testing-patterns.md` | Circuit breaker testing, AsyncLocalStorage testing | Testing resilience patterns, context propagation |
| `reference/nestjs-testing-ci-troubleshooting.md` | Coverage standards, CI/CD, troubleshooting | Configuring CI pipelines, coverage thresholds |
| `reference/nestjs-rest-workflow.md` | REST workflow, OpenAPI/Swagger controller setup | Designing REST endpoints, setting up Swagger |
| `reference/nestjs-rest-dto-pagination.md` | DTO mapping, pagination, filter patterns | Creating DTOs, implementing pagination |
| `reference/nestjs-rest-upload-errors.md` | File uploads, API versioning, ProblemDetail errors | Implementing file uploads, error responses |
| `reference/nestjs-mcp-server.md` | `@nestjs/mcp` tools on an existing Nest 12 app (runtime-verified), Observe MCP server (DEFER) | Exposing a Nest service's operations to MCP clients |
| `reference/nestjs-rest-services.md` | Service patterns, external API clients, bulk operations, soft delete | Writing service logic, calling external APIs |
| `reference/nestjs-security-auth.md` | JWT authentication (RS256), password hashing, token management | Implementing JWT auth, implementing guards |
| `reference/nestjs-security-scanning.md` | OWASP scanning, security headers, static analysis | Security auditing, dependency scanning |
| `reference/nestjs-security-validation-logging.md` | Input validation, PII masking, Prisma security | Securing input handling, masking sensitive data |
| `reference/nestjs-debugging-logging.md` | Debug mode, Prisma query logging, Fastify lifecycle | Debugging requests, tracing Prisma queries |
| `reference/nestjs-debugging-context-di.md` | AsyncLocalStorage context, DI debugging, config | Debugging DI issues, context propagation |
| `reference/nestjs-debugging-performance.md` | Memory leaks, performance profiling | Diagnosing memory leaks, profiling performance |
| `reference/nestjs-debugging-production.md` | Production debugging, structured logging, tracing | Debugging production issues, structured logging |
| `reference/nestjs-review-checklist.md` | NestJS review checklist (used by `nestjs-reviewer` agent) | Code review, pre-PR checklist |
| `reference/nestjs-real-world-issues.md` | 9 framework-level issues from GitHub/SO with frequency ratings and Vitest-adapted solutions | Debugging DI errors, circular deps, JWT config, memory leaks |
| `reference/nestjs-decision-trees.md` | Decision trees for module organization, auth method, testing strategy, caching, error responses | Architecture decisions before implementation |

## Common Commands

```bash
npm run start:dev                           # Run in dev mode (watch)
npm test                                    # Run unit tests (Vitest)
npm run test:e2e                            # Run integration/E2E tests
npm run test:cov                            # Run tests with coverage report
npm run lint                                # oxlint --type-aware
npm run typecheck                           # TypeScript type-check only
npm run build                               # nest build (tsc builder)
npx vitest --clearCache                     # after a tsconfig change (Vitest 5 module cache)
npx prisma migrate dev --name <migration>   # Create and run migration
npx prisma generate                         # Regenerate Prisma client after schema change
npx prisma studio                           # Open Prisma Studio GUI
```

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Prisma ORM | `https://www.prisma.io/docs/llms.txt` | Prisma schema, migrations, client API |
| NestJS / TypeScript | `Context7` MCP, else `https://docs.nestjs.com` (migration-guide, faq/versions, techniques/validation) | Latest NestJS decorators, modules, patterns |
| Installed package source | `npm view <pkg>@<major> version`; `npm pack <pkg>@<ver>` then grep the `.d.ts` | Ground truth for signatures and defaults when docs lag (e.g. `ValidationPipe` default status, P2002 `meta` shape) |

## Error Handling

**Validation errors**: Zod schemas through the global `StandardSchemaValidationPipe` return **400** with `path: message` entries and never echo the input (verified in `@nestjs/common` 12.6.0). Unknown fields → 400 with `z.strictObject`.

**Not-found errors**: Throw `new NotFoundException('Order not found', { errorCode: 'ORDER_NOT_FOUND' })` from services; another tenant's record is a 404 too.

**Duplicate errors**: Catch Prisma `P2002` and map to `409 Conflict` (or replay the original for an idempotency key). With Prisma 7 driver adapters the constraint name is in `meta.driverAdapterError.cause.constraint.index`; `meta.target` is not set.

## Hard Prohibitions

- No unvalidated input — every `@Body`, `@Param` and `@Query` declares a Standard Schema (or, in an existing class-validator codebase, a DTO class under `ValidationPipe`)
- No response returned without a response schema when the source object holds fields the client must not see
- No tenant, owner or role taken from the body, query or headers — only from the verified token
- No JWT verification without pinned `algorithms`, `issuer` and `audience` read with `getOrThrow` (an undefined audience disables the check)
- Authentication is global (`APP_GUARD`); public routes opt out with `@Public()` — never opt in per route
- No raw SQL unless performance-critical (document why); never string-built SQL
- No `jest` in new code — Vitest only (Jest stays only in existing CommonJS apps)
- No legacy Terminus `HealthIndicator` / `HealthCheckError` (removed in 12); no `@nestjs/observe` without an approved hosted account
- No `$use` Prisma middleware (removed) — use `$extends`
- No `process.on('SIGTERM')` next to `enableShutdownHooks()` (hooks run twice)
- No floating version ranges across a Nest major; no package that `npm view` cannot find
- No extensionless relative imports in ESM code (`./x.js`); no `__dirname` (use `import.meta.dirname`)

## Post-Code Review

After writing TypeScript code, dispatch these reviewer agents:
- `nestjs-reviewer` — module correctness, Prisma usage, resilience patterns
- `code-reviewer` — general quality, DRY, error handling
- `security-reviewer` — auth, input validation, OWASP Top 10
