---
name: java-spring-api
description: Patterns and templates for Java 25 + Spring Boot 4.2 (Spring Framework 7.1) REST services on Spring MVC with virtual threads (default) or Spring WebFlux (when justified). Use when creating controllers, services, JPA/JDBC or R2DBC repositories, DTOs, HTTP clients, security, resilience or tests, or when migrating a Boot 3 service to Boot 4.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Java, Spring Boot, Spring MVC, Spring WebFlux, REST API Java, virtual threads, JPA, R2DBC, Mono, Flux, RestClient, Boot 4 migration
  related-skills: java-coding-standard, openapi-spec-generation, database-schema-designer
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-24"
---

## Iron Law

**CHOOSE THE STACK WITH THE DECISION TABLE BELOW AND READ `reference/spring-boot-conventions.md` BEFORE WRITING CODE. Boot 3 habits (`@MockBean`, `TestRestTemplate`, `RestTemplate`, `com.fasterxml.jackson.databind`, `spring-boot-starter-web`) do not compile or are deprecated on Boot 4; a blocking call on a WebFlux event-loop thread stalls every request on that thread.**

# Java 25 + Spring Boot 4.2 REST API Skill

Baseline (verified 2026-11-24 against the `spring-boot-dependencies` 4.2.0 BOM; decision: `docs/adr/0001-java25-spring-boot-4-mvc-default.md`):

| Component | Version | Component | Version |
|---|---|---|---|
| Java (LTS) | 25 (Temurin 25.0.5.1) | Spring Boot | 4.2.0 |
| Spring Framework | 7.1.0 | Spring Security | 7.2.0 |
| Spring Data | 2026.1.0 | Hibernate ORM | 7.4.15.Final |
| Jackson | 3.1.8 (`tools.jackson.*`) | Reactor | 2026.0.0 |
| Tomcat / Netty | 11.0.27 / 4.2.20 | JUnit Jupiter | 6.1.3 |
| Testcontainers | 2.0.5 | Flyway | 12.11.0 |
| Micrometer | 1.18.0 | springdoc-openapi | 3.2.1 (not in the BOM: pin it) |
| Spring Cloud | 2026.0.0 | Spring Modulith / Spring AI | 2.2.0 / 2.1.0 |
| Maven | 3.10.2 via wrapper 3.3.4 | PostgreSQL image | `postgres:18.7` |

Spring Boot 3.5.x open-source support ended 2026-06-30 and start.spring.io no longer generates it. Migrate, do not start new 3.5 services.

## Choose the stack: Spring MVC or WebFlux

Default is **Spring MVC + virtual threads + Spring Data JPA/JDBC**. WebFlux is never chosen "because it is faster": virtual threads already remove the thread-per-request ceiling for blocking I/O.

| Question | MVC + virtual threads | WebFlux + R2DBC |
|---|---|---|
| Typical CRUD over PostgreSQL with JPA/JDBC | ✅ default | ❌ no JPA; more code for the same result |
| Streaming responses (SSE, long-lived connections, live feeds) | ⚠️ `SseEmitter` works for low counts | ✅ `Flux` + backpressure |
| End-to-end backpressure from DB/broker to client | ❌ | ✅ |
| Fan-out of many concurrent outbound calls per request | ✅ virtual threads + `RestClient` | ✅ `WebClient` + `Mono.zip` |
| Blocking libraries you must call (JDBC drivers, SDKs, file I/O) | ✅ | ❌ each needs `boundedElastic` isolation |
| Team familiarity, debuggability, readable stack traces | ✅ | ⚠️ operator chains, BlockHound needed |
| Transactions | `@Transactional` (thread-bound) | `@Transactional` on reactive methods / `TransactionalOperator` (context-bound) |
| Tests | `RestTestClient`, `MockMvcTester` | `WebTestClient`, `StepVerifier`, BlockHound |

Pick WebFlux only when a ✅ in its column is a stated requirement; record the reason in the service README. Never put `spring-boot-starter-webmvc` and `spring-boot-starter-webflux` in one service (MVC wins and the reactive stack silently does nothing). A blocking MVC service that only needs `WebClient` adds `spring-boot-starter-webclient`, not `-webflux`.

## Process

1. **Scaffold** with `/scaffold-spring-api` (MVC) or `/scaffold-spring-api --webflux`
2. **Configure** `pom.xml` and `application.properties` — `reference/spring-boot-config.md`
3. **Create files** from `reference/spring-boot-templates.md` (MVC section or WebFlux section)
4. **Write tests** — `reference/spring-boot-templates.md` → Tests (MVC and WebFlux, tested), then `reference/spring-boot-testing-unit.md`, `reference/spring-boot-testing-integration.md` for more WebFlux patterns
5. **Verify** — `./mvnw -q verify` (compiler runs with `-Xlint:deprecation -Werror`), then `reference/spring-boot-verification-gates.md`
6. **Review** — `spring-boot-reviewer` (checklist: `reference/spring-boot-review-checklist.md`), `security-reviewer` for auth/input changes

## Boot 4.2 / Framework 7.1 features: adoption decisions

| Feature | Decision | Why |
|---|---|---|
| Virtual threads (`spring.threads.virtual.enabled=true`) | **ADOPT** (MVC) | Blocking code scales without reactive types; proven by the MVC reference app's thread test |
| Modular starters (`-webmvc`, `-restclient`, `-flyway`, `-security-oauth2-resource-server`) + per-technology `-test` starters | **ADOPT** | The Boot 4 layout; classic starters are only a migration aid |
| `RestClient` and `@HttpExchange` clients via `@ImportHttpServices` + `spring.http.serviceclient.<group>.*` | **ADOPT** | Replaces `RestTemplate` (deprecated in 7.1); base URL and timeouts from config |
| `RestTestClient` (`@AutoConfigureRestTestClient`), `MockMvcTester` | **ADOPT** | Replaces `TestRestTemplate` (deprecated in 4.2) |
| `@MockitoBean` / `@MockitoSpyBean` | **ADOPT** (required) | `@MockBean` / `@SpyBean` are removed |
| Framework `@Retryable` / `@ConcurrencyLimit` + `@EnableResilientMethods` | **ADOPT** | Bounded retry and bulkheading without Spring Retry (no longer managed). `@Retryable` on a `Mono` method retries by re-subscribing; `@ConcurrencyLimit` does not bound `Mono` work (bound with the connection pool in WebFlux) |
| RFC 9457 `ProblemDetail` | **ADOPT** | Set `instance` yourself: 7.1 does not fill it, and `type` defaults to unset |
| Jackson 3 (`JsonMapper`, `JsonMapperBuilderCustomizer`) | **ADOPT** (required) | Boot 4 default; `spring-boot-jackson2` is a deprecated stop-gap |
| JSpecify nullability (`org.jspecify.annotations.Nullable`) | **ADOPT** | Framework 7 API is annotated with it |
| Structured logging (`logging.structured.format.console=ecs`) | **ADOPT** | JSON logs without a custom encoder |
| Testcontainers 2 + `@ServiceConnection`, pinned image | **ADOPT** | No hand-written datasource properties in tests |
| API versioning (`spring.mvc.apiversion.*`, `@RequestMapping(version=...)`) | **OPTIONAL** | Use when two API versions must be served side by side; path `/api/v1` stays the simple default |
| `BeanRegistrar` programmatic registration | **OPTIONAL** | For libraries and conditional bean sets; plain `@Bean` for application code |
| OpenTelemetry starter / OTLP (`spring-boot-starter-opentelemetry`, `management.opentelemetry.*`) | **OPTIONAL** | When the platform has an OTLP collector |
| HTTP `QUERY` method | **DEFER** | Clients, proxies and gateways do not support it widely yet |
| GraalVM native image | **DEFER** | Test per service; JVM + CDS is the default (see `reference/java25-features.md`) |
| Java preview features (`StructuredTaskScope`, `StableValue`, primitive patterns) | **DEFER** | Preview in JDK 25; never in production defaults |
| Undertow, `spring-boot-jackson2`, `RestTemplate`, Spring Retry | **NOT APPLICABLE** | Removed or deprecated in Boot 4 / Framework 7 |

## Boot 3 → Boot 4 replacements

| Boot 3 habit | Boot 4.2 |
|---|---|
| `spring-boot-starter-web` / `-aop` / `-oauth2-resource-server` | `-webmvc` / `-aspectj` / `-security-oauth2-resource-server` |
| Flyway works from `flyway-core` alone | Add `spring-boot-starter-flyway` (+ `flyway-database-postgresql`) |
| `spring-boot-starter-test` only | Per-technology test starters (`-webmvc-test`, `-data-jpa-test`, `-security-test`, ...) |
| `RestTemplate`, `TestRestTemplate` | `RestClient` / `@HttpExchange`; `RestTestClient` |
| `@MockBean`, `@SpyBean` | `@MockitoBean`, `@MockitoSpyBean` |
| `@SpringBootTest` provides MockMvc | Add `@AutoConfigureMockMvc` (or use `@WebMvcTest`) |
| `com.fasterxml.jackson.databind.ObjectMapper` bean | `tools.jackson.databind.json.JsonMapper`; customise with `JsonMapperBuilderCustomizer` |
| `spring.jackson.read.*` / `write.*` | `spring.jackson.json.read.*` / `write.*` |
| Spring Retry `@Retryable` | `org.springframework.resilience.annotation.Retryable` |
| `org.springframework.lang.Nullable` | `org.jspecify.annotations.Nullable` |
| `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` (artifact `testcontainers-postgresql`) |
| `server.forward-headers-strategy` | `server.request.header.forwarded.strategy` |

Renamed properties: add `spring-boot-properties-migrator` (runtime scope) for one run, read its warnings, then remove it. Full list: the Spring Boot 4.0 migration guide and the 4.1 / 4.2 release notes (GitHub wiki of spring-projects/spring-boot).

## Reference Files

| File | Content | Load When |
|---|---|---|
| `reference/spring-boot-conventions.md` | Package layout, MVC rules, WebFlux rules, transactions | **Before any code** |
| `reference/spring-boot-config.md` | Tested `pom.xml` (MVC and WebFlux), `application.properties`, Dockerfile | Project setup, dependencies |
| `reference/spring-boot-templates.md` | Entity, repository, service, controller, ProblemDetail advice, HTTP client, tests — MVC and WebFlux | Creating any layer |
| `reference/spring-boot-enterprise-errors-security.md` | Exception hierarchy, OAuth2 resource server, scopes, CORS | Error handling, security |
| `reference/spring-boot-enterprise-resilience-health.md` | Resilience4j circuit breaker/bulkhead, HTTP client timeouts, health groups, OpenAPI | Resilience, health, docs |
| `reference/spring-boot-rest-service-guide.md` | OpenAPI + DDL driven workflow, MapStruct, external clients, WireMock | API design, mapping |
| `reference/spring-boot-testing-unit.md` | WebFlux unit tests: `StepVerifier`, BlockHound, resilience tests, builders (MVC slices: templates → Tests) | Unit and slice tests |
| `reference/spring-boot-testing-integration.md` | Testcontainers 2, `WebTestClient`, WireMock contract tests (MVC `RestTestClient` + JWTs: templates → Tests) | Integration tests |
| `reference/spring-boot-reactive-patterns.md` | WebFlux: SSE, backpressure, timeouts, cancellation, R2DBC transactions, context propagation | WebFlux services only |
| `reference/spring-boot-reactive-debugging.md` | Reactor hooks, checkpoints, BlockHound | Debugging WebFlux pipelines |
| `reference/spring-boot-security-hardening.md` | Dependency scanning, headers, JWT role extraction, secure logging | Security hardening |
| `reference/spring-boot-rate-limiting.md` | Rate limiting | Public or expensive endpoints |
| `reference/spring-boot-caching.md` | Caffeine, `@Cacheable`, eviction | Caching |
| `reference/spring-boot-design-patterns.md` | Builder, Strategy, Observer (events), Decorator, Adapter in Spring | Applying these patterns |
| `reference/java25-features.md` | Java 25 final features, preview features (optional experiments), JVM tuning, native image, Spring Modulith | Language features, JVM tuning, modular monolith |
| `reference/spring-boot-review-checklist.md` | Common + MVC + WebFlux review checklist (used by `spring-boot-reviewer`) | Code review, pre-PR |
| `reference/spring-boot-verification-gates.md` | Build, static analysis, dependency checks, CI gate | Pre-PR verification |
| `reference/gdpr-account-deletion.md` | Account deletion | GDPR work |

## Documentation Sources

| Source | Where | Purpose |
|---|---|---|
| Spring Boot / Framework / Security reference | `Context7` MCP (`/spring-projects/spring-boot`, `/spring-projects/spring-framework`) | Current APIs and properties |
| Migration guide, release notes | github.com/spring-projects/spring-boot/wiki (Spring Boot 4.0 Migration Guide, 4.1/4.2 Release Notes) | Boot 3 → 4 changes |
| Managed versions | `spring-boot-dependencies` 4.2.x POM on Maven Central | Exact BOM versions |
| Spring Initializr | `https://start.spring.io` (`javaVersion=25`, `bootVersion=4.2.0`) | Project skeleton |

If Context7 is unavailable, say so and use the sources above; never fill gaps from memory.

## Common Commands

```bash
./mvnw spring-boot:run                       # Run (needs DB_URL etc. or the Testcontainers dev runner)
./mvnw spring-boot:test-run                  # Run with the TestApplication class: Testcontainers PostgreSQL for local dev
./mvnw -q verify > /tmp/verify.log 2>&1; echo "VERIFY EXIT:$?"   # Compile (-Werror) + all tests
./mvnw dependency:tree -Dincludes='tools.jackson*,com.fasterxml.jackson*'   # Jackson 2 must not appear at runtime
./mvnw -DskipTests package && java -Djarmode=tools -jar target/*.jar extract --layers --launcher --destination target/extracted
```

## Hard Prohibitions

- No `RestTemplate`, `TestRestTemplate`, `@MockBean`, Spring Retry or Jackson 2 `databind` in new code
- No Java preview features in production code
- MVC: no remote calls inside a `@Transactional` method (holds a DB connection during network I/O); `spring.jpa.open-in-view=false`
- WebFlux: no `.block()` / `.toFuture().get()` / blocking I/O on event-loop threads; no JPA; isolate unavoidable blocking calls on `Schedulers.boundedElastic()` and prove the rest with BlockHound
- No unbounded retries; retry only idempotent operations and only on 5xx / I/O errors
- No secrets in `application.properties`: environment variables, no defaults for keys and passwords

## Post-Code Review

- `spring-boot-reviewer` — stack choice, transactions, blocking calls, resilience, Boot 3 leftovers, tests
- `security-reviewer` — auth, input validation, secrets
