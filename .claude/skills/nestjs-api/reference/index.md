# NestJS API References

## Quick Navigation

| Reference | When to Load | Key Content |
|-----------|-------------|-------------|
| [nestjs-conventions.md](nestjs-conventions.md) | **Before any module** — Iron Law | Package layout, Fastify quirks, Prisma 7.x patterns, DTO validation rules, env file rules |
| [nestjs-production-baseline.md](nestjs-production-baseline.md) | **Before any feature** — Iron Law; auth/tenancy/validation reviews | Runtime-verified JWT guard, tenant scoping, ValidationPipe, Fastify throttling, WebSocket auth, shutdown, BullMQ, webhooks |
| [nestjs-config-basics.md](nestjs-config-basics.md) | Project setup or initial configuration | Static config reader, config module aggregation, fail-fast validation |
| [nestjs-config-npm-ts.md](nestjs-config-npm-ts.md) | Setting up package.json or tsconfig | Verified pins, package.json, tsconfig, Vitest + ESLint config |
| [nestjs-config-prisma7.md](nestjs-config-prisma7.md) | Setting up database or writing Prisma queries | Prisma 7.x schema, prisma.config.ts, PrismaService, .env template |
| [nestjs-templates-core.md](nestjs-templates-core.md) | Bootstrapping app or creating the core module | main.ts, app.module, core.module templates |
| [nestjs-templates-features.md](nestjs-templates-features.md) | Creating modules, controllers, or services | Feature module, controller, service, DTO templates |
| [nestjs-templates-infrastructure.md](nestjs-templates-infrastructure.md) | Containerizing app or configuring test runner | Dockerfile, docker-compose, Vitest config |
| [nestjs-enterprise-patterns.md](nestjs-enterprise-patterns.md) | Implementing error handling, input validation, or API versioning | Exception hierarchy, validation pipe, API versioning |
| [nestjs-enterprise-infrastructure.md](nestjs-enterprise-infrastructure.md) | Adding security headers, rate limiting, or API documentation | Helmet, rate limiting, Swagger, health checks |
| [nestjs-resilience-circuit-breaker.md](nestjs-resilience-circuit-breaker.md) | Adding resilience or handling service failures | Circuit breaker, retry, timeout, database fallback |
| [nestjs-resilience-context.md](nestjs-resilience-context.md) | Adding request tracing or correlation IDs | AsyncLocalStorage request context, correlation IDs |
| [nestjs-feature-flags.md](nestjs-feature-flags.md) | Implementing feature flags or gradual rollout | Feature flags service, Redis fallback, gradual rollout |
| [nestjs-observability.md](nestjs-observability.md) | Adding observability, structured logging, or tracing | OpenTelemetry tracing/metrics, structured logging, cloud logging |
| [nestjs-rate-limiting.md](nestjs-rate-limiting.md) | Adding rate limiting to endpoints | Throttler guard order, credential-hash tracker, `@nest-lab/throttler-storage-redis` |
| [nestjs-messaging-basics.md](nestjs-messaging-basics.md) | Adding background jobs or queue processing | BullMQ queues, background job processing |
| [nestjs-messaging-queues.md](nestjs-messaging-queues.md) | Implementing RabbitMQ messaging or dead letter queues | RabbitMQ reliable messaging, dead letter queues |
| [nestjs-messaging-streaming.md](nestjs-messaging-streaming.md) | Implementing Kafka streaming or high-throughput events | Kafka event streaming, high-throughput patterns |
| [nestjs-rest-workflow.md](nestjs-rest-workflow.md) | Designing REST endpoints or setting up Swagger | REST workflow, OpenAPI/Swagger controller setup |
| [nestjs-rest-dto-pagination.md](nestjs-rest-dto-pagination.md) | Creating DTOs or implementing pagination | DTO mapping, pagination, filter patterns |
| [nestjs-rest-upload-errors.md](nestjs-rest-upload-errors.md) | Implementing file uploads or error responses | File uploads, API versioning, ProblemDetail errors |
| [nestjs-rest-services.md](nestjs-rest-services.md) | Writing service logic or calling external APIs | Service patterns, external API clients, bulk ops, soft delete |
| [nestjs-security-auth.md](nestjs-security-auth.md) | Implementing JWT auth or writing guards | JWT authentication (RS256), password hashing, token management |
| [nestjs-security-scanning.md](nestjs-security-scanning.md) | Security auditing or dependency scanning | OWASP scanning, security headers, static analysis |
| [nestjs-security-validation-logging.md](nestjs-security-validation-logging.md) | Securing input handling or masking sensitive data | Input validation, PII masking, Prisma security |
| [nestjs-testing-unit-basics.md](nestjs-testing-unit-basics.md) | Writing unit tests for services | Vitest service test patterns |
| [nestjs-testing-unit-controllers.md](nestjs-testing-unit-controllers.md) | Writing unit tests for controllers | Controller unit tests, test data factories |
| [nestjs-testing-unit-mocks.md](nestjs-testing-unit-mocks.md) | Mocking dependencies in unit tests | Prisma/Redis/HTTP mocking, ConfigService mocking |
| [nestjs-testing-integration-setup.md](nestjs-testing-integration-setup.md) | Writing integration or E2E tests | E2E testing setup, Testcontainers, supertest |
| [nestjs-testing-integration-patterns.md](nestjs-testing-integration-patterns.md) | Testing auth flows, pagination, or validation | Auth testing, validation, pagination patterns |
| [nestjs-testing-patterns.md](nestjs-testing-patterns.md) | Testing resilience patterns or context propagation | Circuit breaker testing, AsyncLocalStorage testing |
| [nestjs-testing-ci-troubleshooting.md](nestjs-testing-ci-troubleshooting.md) | Configuring CI pipelines or coverage thresholds | Coverage standards, CI/CD, troubleshooting |
| [nestjs-debugging-logging.md](nestjs-debugging-logging.md) | Debugging requests or tracing Prisma queries | Debug mode, Prisma query logging, Fastify lifecycle |
| [nestjs-debugging-context-di.md](nestjs-debugging-context-di.md) | Debugging DI issues or context propagation | AsyncLocalStorage context, DI debugging, config |
| [nestjs-debugging-performance.md](nestjs-debugging-performance.md) | Diagnosing memory leaks or profiling performance | Memory leaks, performance profiling |
| [nestjs-debugging-production.md](nestjs-debugging-production.md) | Debugging production issues or structured logging | Production debugging, structured logging, tracing |
| [nestjs-decision-trees.md](nestjs-decision-trees.md) | Architecture decisions before implementation | Module org, auth method, testing strategy, caching, error responses |
| [nestjs-real-world-issues.md](nestjs-real-world-issues.md) | Debugging DI errors, circular deps, JWT config, memory leaks | 9 framework-level issues from GitHub/SO with frequency ratings |
| [nestjs-review-checklist.md](nestjs-review-checklist.md) | Code review or pre-PR check (used by `nestjs-reviewer`) | NestJS review checklist |
| [transactional-email-setup.md](transactional-email-setup.md) | Setting up transactional email sending | Transactional email integration patterns |
| [gdpr-account-deletion.md](gdpr-account-deletion.md) | Implementing account deletion or GDPR compliance | GDPR account deletion patterns |
