# Spring Boot 4.2 Conventions & Rules (Java 25)

Choose MVC or WebFlux with the decision table in `../SKILL.md` first. The common rules apply to both.

## Common Rules

- **Java 25 (final features only):** records for DTOs and value objects, sealed types + pattern-matching `switch` for closed hierarchies (exhaustive, no `default`), unnamed variables (`case NotFound _ ->`), `ScopedValue` instead of `ThreadLocal` for request-scoped values you own. Preview features stay out (see `java25-features.md`).
- **Packages by feature**, not by layer, once a service has more than one aggregate: `orders/` holds its controller, service, repository, entity, DTOs and exceptions; `config/` and `web/` hold cross-cutting pieces. A single-aggregate service may use the flat `controller/ service/ repository/ model/` layout.
- **Constructor injection**, `final` fields, package-private classes where possible. No field injection, no Lombok requirement.
- **Paths:** `/api/v1/<resource>` (or Framework 7 API versioning when two versions must coexist). Return `201` + `Location` on create, `204` on delete.
- **Validation:** `jakarta.validation` on record components, `@Valid` on `@RequestBody`; method-parameter validation (`@PathVariable`, `@RequestParam` constraints) is built in since Framework 6.1 and reported as `HandlerMethodValidationException`.
- **Errors:** every error is `application/problem+json` (`ProblemDetail`). Set `title`, `detail` and `instance` (Framework 7.1 no longer sets `instance`). Never echo rejected input, exception messages or stack traces to the client.
- **Nullability:** `org.jspecify.annotations.Nullable` on anything that can be null; everything else is non-null.
- **Configuration:** `application.properties` (or `.yml`) with `${ENV_VAR}` placeholders; no default for secrets and keys (startup fails closed).
- **Persistence:** Flyway owns the schema (`spring.jpa.hibernate.ddl-auto=validate` for JPA); migrations in `src/main/resources/db/migration/`.
- **Optimistic locking:** `@Version` column; expose it as an `ETag`, require `If-Match` on updates (`428` when missing, `409` when stale).
- **Paging:** bounded (`spring.data.web.pageable.max-page-size`), whitelisted sort properties, a unique final tiebreaker (`id`), and a stable page DTO (Spring Data's `PageImpl` is not a JSON contract).
- **Outbound HTTP:** `@HttpExchange` interfaces registered with `@ImportHttpServices(group = "...")`; base URL and timeouts from `spring.http.serviceclient.<group>.*`. Always set connect and read timeouts.
- **Resilience:** `@Retryable` only on idempotent calls, only for 5xx / I/O exceptions, bounded (`maxRetries`, `maxDelay`); `@ConcurrencyLimit` to bulkhead a slow dependency. Retry exhaustion rethrows the last original exception (not a `RetryException`), so map it in the advice.
- **Logging:** SLF4J with parameters (`log.info("Order created id={}", id)`), structured JSON in production (`logging.structured.format.console=ecs`), never tokens, passwords or full request bodies.
- **Tests:** JUnit 6 (`org.junit.jupiter.api`), AssertJ, `@MockitoBean`; Testcontainers 2 with `@ServiceConnection` and a pinned image (`postgres:18.7`).

## Package Layout (feature-first)

```
com.company.<service>/
├── <Service>Application.java
├── config/          # SecurityConfig, Clock bean, cross-cutting config
├── web/             # ProblemDetailsAdvice, filters
├── orders/          # one feature: Controller, Service, Repository, Entity, Dtos, sealed Exception
└── pricing/         # outbound client (@HttpExchange) + config (@ImportHttpServices)
src/main/resources/
├── application.properties
└── db/migration/V1__create_orders.sql
```

## Spring MVC Rules (default stack)

- `spring.threads.virtual.enabled=true`: Tomcat requests, `@Async` and scheduling run on virtual threads. Prove it once with a test (`Thread.currentThread().isVirtual()`).
- Avoid long `synchronized` blocks around I/O inside request handling in libraries you own; prefer `ReentrantLock` (JDK 24+ removed most virtual-thread pinning on `synchronized`, but native frames still pin).
- `@Transactional(readOnly = true)` on the service class, `@Transactional` on writing methods. Transactions belong to the **service**, never the controller or repository.
- **No remote calls inside a transaction:** call the HTTP client before or after the transactional method; a transaction held open during network I/O exhausts the connection pool.
- `spring.jpa.open-in-view=false`; map entities to DTO records inside the transaction.
- Multi-row writes that must be all-or-nothing: one `@Transactional` service method; `saveAndFlush` when a later step depends on the database having accepted the earlier one.
- Assigned (application-generated) UUID ids: use a nullable wrapper `@Version Long` so Spring Data can tell new from existing entities.
- Use `RestClient` (fluent) or `@HttpExchange` (declarative). `RestTemplate` is deprecated.

```java
@Service
@Transactional(readOnly = true)
public class OrderService {
    // reads inherit readOnly; writes opt in
    @Transactional
    public OrderResponse create(Caller caller, CreateOrderRequest request) {
        Order order = orders.save(new Order(caller.customerId(), request.total(), clock.instant()));
        return OrderResponse.from(order);
    }
}
```

## Spring WebFlux Rules (only when justified)

- NEVER call `.block()`, `.blockFirst()`, `.toFuture().get()`, `Thread.sleep` or blocking I/O (JDBC, `java.io` files, blocking SDKs) on an event-loop thread. Unavoidable blocking calls: `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. Install BlockHound in tests to prove it.
- R2DBC only (`spring-boot-starter-data-r2dbc` + `org.postgresql:r2dbc-postgresql`); no JPA. Flyway still runs over JDBC (`spring-jdbc` + the JDBC driver at runtime for migrations only).
- `@Transactional` works only on methods returning `Mono`/`Flux` (reactive transaction manager); for multi-statement writes annotate the **service** method, or use `TransactionalOperator`. A method that calls `.subscribe()` itself escapes the transaction.
- Parallel calls: `Mono.zip(...)`; every outbound call gets `.timeout(...)`; retries via `Retry.backoff(n, ...)` with a filter for retryable errors only.
- Not found: `switchIfEmpty(Mono.error(new NotFound(id)))`.
- Streams: return `Flux` with `text/event-stream` for SSE; bound buffers (`limitRate`, `onBackpressureBuffer(n)` with an overflow strategy) and stop work on cancellation (`doOnCancel`).
- Request context (security, tracing, MDC) travels in the Reactor `Context`, not `ThreadLocal`; Boot enables automatic context propagation for Micrometer when `spring.reactor.context-propagation=auto`.
- Use `WebClient` (from `WebClient.Builder`) or `@HttpExchange` interfaces (WebClient-backed in a WebFlux app).

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest req) {
    return orderRepository.save(toEntity(req))
        .flatMap(order -> lineItemRepository.saveAll(toLineItems(order, req))
            .then(Mono.just(order)));
}
```
