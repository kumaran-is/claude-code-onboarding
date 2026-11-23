# NestJS Conventions & Rules

## Code Conventions

- Use **NestJS 11.x** (verified 11.2.11) with the **Fastify** adapter (not Express)
- **Prisma ORM** for database access with PostgreSQL
- Module aggregation: `ConfigModule → CommonModule → CoreModule → FeaturesModule`
- Fail-fast configuration: app crashes at startup if env vars are missing
- `class-validator` + `class-transformer` for DTO validation
- Feature-first modules: `src/features/{entity}/` with module, controller, service, dto, repository
- Circuit breaker pattern for all external calls
- Request context via `AsyncLocalStorage` for correlation ID propagation
- Tests: Vitest; e2e through the production `configureApp()` with `app.inject()` (or supertest)

## Security Rules (verified in `nestjs-production-baseline.md`)

- Authentication is global (`APP_GUARD`); routes opt out with `@Public()`
- Guard order: `ThrottlerGuard` → `JwtAuthGuard` → role/permission checks
- JWT: `jose.jwtVerify` (JWKS) or passport-jwt with pinned `algorithms`, `issuer`, `audience` read via `getOrThrow`
- Tenant/owner ids only from the verified principal; repositories take `tenantId` explicitly; cross-tenant → 404
- `ValidationPipe`: `whitelist` + `forbidNonWhitelisted` + `transform`, `enableImplicitConversion: false`; invalid input → 400
- WebSocket auth in socket.io middleware (`server.use` in `afterInit`)
- `enableShutdownHooks()` is the only signal handler

## Package Layout

```
src/
├── main.ts
├── app.module.ts
├── config/          # Configuration management (fail-fast)
├── common/          # Cross-cutting: exceptions, filters, interceptors, middleware, pipes, context
├── core/            # Infrastructure: database, cache, resilience, health, observability, messaging, feature-flags
├── shared/          # Cross-feature types, utils, constants
├── auth/            # Authentication (guards, strategies, decorators)
└── features/        # Business feature modules
    └── {entity}/    # module, controller, service, dto, repository
```

## NestJS Rules

- Use decorator-based DI (`@Injectable()`, `@Module()`, `@Controller()`)
- Module aggregation pattern: ConfigModule → CommonModule → CoreModule → FeaturesModule
- Fail-fast configuration: app crashes at startup if env vars are missing — all required values live in `.env`, never as `??` defaults in code
- Use class-validator + class-transformer for DTO validation
- Use Prisma 7.x Client for database access (not TypeORM or Sequelize)
- Return structured responses via interceptors (TransformInterceptor)
- Global exception filter produces RFC 9457 ProblemDetail responses
- All external calls wrapped in circuit breaker pattern
- Request context via AsyncLocalStorage for correlation ID propagation

## Prisma 7.x Rules

- Generator: `provider = "prisma-client"` (not `prisma-client-js`), with explicit `output` path
- Datasource: **no `url`** in `schema.prisma` — connection URL goes in `prisma.config.ts`
- PrismaService: Use **composition** (not inheritance) — `new PrismaClient({ adapter })` with `@prisma/adapter-pg`
- Generated client output (e.g., `src/generated/`) must be in `.gitignore`
- Keep `prisma.config.ts` at project root — Prisma CLI reads it for migrations

## Environment File Rules

- `.env` must be populated with working defaults at scaffold time so the app boots immediately
- **Write `.env` via Bash** (not Write/Edit tools) — hooks block direct `.env` modifications
- `DATABASE_URL` must match credentials in `docker-compose.dev.yml`
- All `getRequired*()` env vars must have corresponding entries in `.env`
- After scaffolding, `npm run start:dev` → Swagger UI must be accessible with zero manual config
