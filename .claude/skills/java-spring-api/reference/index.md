# Java Spring API References (Java 25, Spring Boot 4.2)

## Quick Navigation

| Reference | When to Load | Key Content |
|-----------|-------------|-------------|
| [spring-boot-conventions.md](spring-boot-conventions.md) | **Before any code** — Iron Law | Package layout, common rules, MVC rules, WebFlux rules, transactions |
| [spring-boot-config.md](spring-boot-config.md) | Project setup or configuring dependencies | Tested pom.xml (MVC + WebFlux deltas), application.properties, Dockerfile, structured logging |
| [spring-boot-templates.md](spring-boot-templates.md) | Creating entities, services, controllers, clients, tests | MVC and WebFlux templates from the tested reference apps |
| [spring-boot-enterprise-errors-security.md](spring-boot-enterprise-errors-security.md) | Error handling, auth, CORS | Exception hierarchy, OAuth2 resource server, CORS |
| [spring-boot-enterprise-resilience-health.md](spring-boot-enterprise-resilience-health.md) | Resilience, health checks, API docs | Resilience4j, HTTP client timeouts, health groups, OpenAPI |
| [spring-boot-rest-service-guide.md](spring-boot-rest-service-guide.md) | Designing REST APIs, mapping DTOs, calling external services | OpenAPI+DDL workflow, MapStruct, WireMock |
| [spring-boot-reactive-patterns.md](spring-boot-reactive-patterns.md) | WebFlux services only | SSE, backpressure, timeouts, R2DBC transactions, context propagation |
| [spring-boot-reactive-debugging.md](spring-boot-reactive-debugging.md) | Debugging WebFlux pipelines | Reactor hooks, checkpoints, debug mode |
| [spring-boot-testing-unit.md](spring-boot-testing-unit.md) | Unit and slice tests | MockMvcTester, StepVerifier, BlockHound, resilience tests, builders |
| [spring-boot-testing-integration.md](spring-boot-testing-integration.md) | Integration tests | Testcontainers 2, RestTestClient, WebTestClient, contract tests |
| [spring-boot-security-hardening.md](spring-boot-security-hardening.md) | Security hardening | Dependency scanning, headers, JWT role extraction, secure logging |
| [spring-boot-rate-limiting.md](spring-boot-rate-limiting.md) | Rate limiting endpoints | Rate limiting patterns |
| [spring-boot-caching.md](spring-boot-caching.md) | Caching | Caffeine, @Cacheable/@CacheEvict, eviction |
| [spring-boot-design-patterns.md](spring-boot-design-patterns.md) | Applying classic patterns in Spring | Builder, Strategy, Observer, Decorator, Adapter |
| [java25-features.md](java25-features.md) | Language features, JVM tuning, native image, modular monolith | Java 25 final vs preview features, virtual threads, JVM flags, Spring Modulith |
| [spring-boot-review-checklist.md](spring-boot-review-checklist.md) | Code review or pre-PR check (used by `spring-boot-reviewer`) | Common, MVC and WebFlux checklists |
| [spring-boot-verification-gates.md](spring-boot-verification-gates.md) | Pre-PR verification | Build, static analysis, dependency checks, CI gate |
| [gdpr-account-deletion.md](gdpr-account-deletion.md) | Account deletion or GDPR compliance | GDPR account deletion patterns |
