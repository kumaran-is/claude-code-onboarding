# Reactive Patterns for Spring Boot WebFlux

Advanced reactive patterns for Java 25 + Spring Boot 4.2 WebFlux services

## Blocking traps found by BlockHound in the Boot 4.2 reference app

| Trap | Symptom | Fix |
|---|---|---|
| `UUID.randomUUID()` in a `WebFilter` | `/dev/urandom` read on the event loop → 500 under BlockHound | Build ids from `ThreadLocalRandom`, or generate them off the event loop |
| First Bean Validation error loads Hibernate Validator's message `ResourceBundle` from the jar | One-time blocking read per locale | Narrow test-scope BlockHound allowance on `PlatformResourceBundleLocator.loadBundle`, nothing broader |
| springdoc builds the OpenAPI model on the first `/v3/api-docs` request | Classpath scan on the event loop → 500 | `springdoc.pre-loading-enabled=true` + `springdoc.packages-to-scan` |
| SSE response headers held until the first element | Clients and proxies think the stream hangs | Emit a keepalive comment at once: `Flux.interval(Duration.ZERO, 15s)` merged into the stream |
| `Sinks.many().multicast().onBackpressureBuffer(n)` | Replays events emitted before anyone subscribed to the first subscriber | `multicast().directBestEffort()` + per-subscriber bounded `onBackpressureBuffer(n, onDrop, DROP_OLDEST)` |
| `@Retryable` on a `Mono` method | Exhaustion surfaces as Reactor's retry-exhausted error (`Exceptions.isRetryExhausted(e)`), cause = last failure — unlike MVC, which rethrows the original | Map it in the advice (503/502) by unwrapping the cause |
| JWT: `issuer-uri` and `public-key-location` both set | Boot uses OIDC discovery and ignores the key; an unreachable issuer → 500 on every request | Pick one; for offline keys build `NimbusReactiveJwtDecoder` with issuer and audience validators |

Client properties: `spring.http.client.*` and `spring.http.reactiveclient.*` are deprecated in Boot 4 → `spring.http.clients.*`. covering Resilience4j operators, Redis, SSE, Spring Cloud Stream, and custom operators.

## Resilience4j Reactive Operators

When using programmatic Resilience4j (not annotation-based), apply operators via `.transformDeferred()`. This ensures the operator wraps each subscription, not just the assembly.

### Operator Usage

```java
// CircuitBreaker — wraps calls, opens on failure threshold
return orderRepository.findById(id)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));

// Retry — retries on transient failures with backoff
return orderRepository.findById(id)
    .transformDeferred(RetryOperator.of(retry));

// TimeLimiter — cancels if operation exceeds timeout
return orderRepository.findById(id)
    .timeout(Duration.ofSeconds(5))
    .transformDeferred(TimeLimiterOperator.of(timeLimiter));

// RateLimiter — throttles call rate
return orderRepository.findById(id)
    .transformDeferred(RateLimiterOperator.of(rateLimiter));

// Bulkhead — limits concurrent executions
return externalService.call()
    .transformDeferred(BulkheadOperator.of(bulkhead));
```

### Combined Chain — Correct Order

```java
// Order: Retry → CircuitBreaker → RateLimiter → TimeLimiter → Bulkhead
return externalService.call(request)
    .transformDeferred(RetryOperator.of(retry))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .transformDeferred(RateLimiterOperator.of(rateLimiter))
    .timeout(Duration.ofSeconds(5))
    .transformDeferred(BulkheadOperator.of(bulkhead));
```

### Common Mistakes

```java
// WRONG — blocking decorator, not reactive
CircuitBreaker.decorateSupplier(cb, () -> service.call());

// WRONG — blocking retry with Thread.sleep
Retry.decorateSupplier(retry, () -> service.call());

// WRONG — blocking rate limiter
rateLimiter.acquirePermission(); // blocks the thread

// CORRECT — always use reactive operators
service.call()
    .transformDeferred(CircuitBreakerOperator.of(cb))
    .transformDeferred(RetryOperator.of(retry))
    .transformDeferred(RateLimiterOperator.of(rateLimiter));
```

## Redis Reactive

Use `ReactiveRedisTemplate` — never `RedisTemplate` in a WebFlux application.

### Configuration

```java
@Configuration
public class RedisConfig {

    @Bean
    public ReactiveRedisTemplate<String, Object> reactiveRedisTemplate(
            ReactiveRedisConnectionFactory factory) {
        var keySerializer = new StringRedisSerializer();
        var valueSerializer = new GenericJackson2JsonRedisSerializer();
        var context = RedisSerializationContext.<String, Object>newSerializationContext(keySerializer)
            .value(valueSerializer)
            .build();
        return new ReactiveRedisTemplate<>(factory, context);
    }
}
```

### CRUD Operations

```java
@Service
@RequiredArgsConstructor
public class CacheService {

    private final ReactiveRedisTemplate<String, Object> redisTemplate;

    public Mono<Object> get(String key) {
        return redisTemplate.opsForValue().get(key);
    }

    public Mono<Boolean> set(String key, Object value, Duration ttl) {
        return redisTemplate.opsForValue().set(key, value, ttl);
    }

    public Mono<Boolean> delete(String key) {
        return redisTemplate.delete(key).map(count -> count > 0);
    }
}
```

### Cache-Aside Pattern

```java
public Mono<User> getUserWithCache(String id) {
    String key = "user:" + id;
    return redisTemplate.opsForValue().get(key)
        .cast(User.class)
        .switchIfEmpty(
            userRepository.findById(id)
                .flatMap(user -> redisTemplate.opsForValue()
                    .set(key, user, Duration.ofMinutes(10))
                    .thenReturn(user))
        );
}
```

### Reactive Pub/Sub

```java
// Publisher
public Mono<Long> publish(String channel, String message) {
    return redisTemplate.convertAndSend(channel, message);
}

// Subscriber
public Flux<String> subscribe(String channel) {
    return redisTemplate.listenToChannel(channel)
        .map(ReactiveSubscription.Message::getMessage)
        .map(Object::toString);
}
```

## Server-Sent Events (SSE)

Use `Flux<ServerSentEvent<T>>` — never `SseEmitter` (blocking, Servlet-based).

### Endpoint Pattern

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<EventData>> streamEvents() {
    return eventService.getEventStream()
        .map(data -> ServerSentEvent.<EventData>builder()
            .id(data.getId())
            .event("update")
            .data(data)
            .build())
        .onErrorResume(error -> Flux.just(
            ServerSentEvent.<EventData>builder()
                .event("error")
                .data(new EventData("Connection error"))
                .build()));
}
```

### Heartbeat to Keep Connection Alive

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> streamWithHeartbeat() {
    Flux<ServerSentEvent<String>> events = eventService.getStream()
        .map(e -> ServerSentEvent.<String>builder().data(e).build());

    Flux<ServerSentEvent<String>> heartbeat = Flux.interval(Duration.ofSeconds(30))
        .map(i -> ServerSentEvent.<String>builder().comment("heartbeat").build());

    return Flux.merge(events, heartbeat);
}
```

## Spring Cloud Stream — Reactive Functions

Use reactive function signatures for stream processing — never `@StreamListener` (deprecated).

### Processor (Transform)

```java
@Bean
public Function<Flux<OrderEvent>, Flux<ProcessedOrder>> processOrders() {
    return orderFlux -> orderFlux
        .flatMap(event -> orderService.processOrder(event))
        .onErrorResume(ProcessingException.class, ex -> {
            log.error("Order processing failed", ex);
            return Mono.empty();
        });
}
```

### Consumer (Sink)

```java
@Bean
public Consumer<Flux<NotificationEvent>> consumeNotifications() {
    return notificationFlux -> notificationFlux
        .flatMap(notificationService::send)
        .subscribe();
}
```

### Supplier (Source)

```java
@Bean
public Supplier<Flux<HealthCheckEvent>> produceHealthChecks() {
    return () -> Flux.interval(Duration.ofSeconds(30))
        .map(tick -> new HealthCheckEvent(Instant.now(), "UP"));
}
```

Non-reactive signatures like `Function<Message, Message>` block the event loop.

## Custom Operators

### Wrapping Unavoidable Blocking I/O

When blocking is unavoidable (legacy library, file I/O), isolate it on `boundedElastic`. On Java 21+ (virtual threads are final), virtual threads are an alternative for blocking I/O isolation:

```java
// Option 1: boundedElastic (default, always works)
public Mono<byte[]> readLegacyFile(String path) {
    return Mono.fromCallable(() -> Files.readAllBytes(Path.of(path)))
        .subscribeOn(Schedulers.boundedElastic());
}

// Option 2: Virtual threads (Java 21+) — better for high-concurrency blocking I/O
private static final Scheduler VIRTUAL = Schedulers.fromExecutor(
    Executors.newVirtualThreadPerTaskExecutor());

public Mono<byte[]> readLegacyFileVT(String path) {
    return Mono.fromCallable(() -> Files.readAllBytes(Path.of(path)))
        .subscribeOn(VIRTUAL);
}
```

Use virtual threads when you have many concurrent blocking calls (e.g., hundreds of simultaneous legacy API calls). Stick with `boundedElastic` for low-concurrency cases or when predictable thread limits are needed.

### Context Propagation

Propagate request context (correlation IDs, tenant) through reactive chains:

```java
public Mono<Order> processOrder(Order order) {
    return Mono.deferContextual(ctx -> {
        String correlationId = ctx.getOrDefault("correlationId", "unknown");
        log.info("[{}] Processing order: {}", correlationId, order.id());
        return orderRepository.save(order);
    });
}

// Set context in WebFilter
@Component
public class CorrelationIdFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String correlationId = exchange.getRequest().getHeaders()
            .getFirst("X-Correlation-ID");
        if (correlationId == null) correlationId = UUID.randomUUID().toString();
        return chain.filter(exchange)
            .contextWrite(Context.of("correlationId", correlationId));
    }
}
```

## Dependency Verification

Ensure the project uses reactive starters, not blocking equivalents:

| Correct (Reactive) | Wrong (Blocking) |
|---|---|
| `spring-boot-starter-webflux` | `spring-boot-starter-webmvc` (Boot 3 name: `-web`) |
| `spring-boot-starter-data-r2dbc` | `spring-boot-starter-data-jpa` |
| `spring-boot-starter-data-redis-reactive` | `spring-boot-starter-data-redis` |
| `resilience4j-reactor` | `resilience4j-spring-boot4` alone |
| Netty (default with webflux) | Tomcat (`spring-boot-starter-tomcat`) |

Check for accidental blocking dependencies:

```bash
# Servlet API should not be on classpath
grep -rn 'javax.servlet\|jakarta.servlet' pom.xml

# JPA should not be present alongside R2DBC
grep -rn 'spring-boot-starter-data-jpa' pom.xml

# Blocking Redis
grep -rn 'spring-boot-starter-data-redis"' pom.xml | grep -v reactive
```

## N+1 Query Anti-Pattern (R2DBC)

With R2DBC there is no lazy-loading proxy — every nested `flatMap(repo::findById)` inside a `Flux` fires a separate query per row.

```java
// WRONG — N+1: 1 query for orders + N queries for users
return orderRepository.findAll()
    .flatMap(order -> userRepository.findById(order.getUserId())
        .map(user -> new OrderWithUser(order, user)));

// CORRECT — batch fetch, then join in memory
return orderRepository.findAll().collectList()
    .flatMap(orders -> {
        var userIds = orders.stream().map(Order::getUserId).distinct().toList();
        return userRepository.findByIdIn(userIds).collectMap(User::getId)
            .map(userMap -> orders.stream()
                .map(o -> new OrderWithUser(o, userMap.get(o.getUserId())))
                .toList());
    })
    .flatMapMany(Flux::fromIterable);

// CORRECT — single join query in repository
@Query("SELECT o.*, u.name AS user_name FROM orders o JOIN users u ON o.user_id = u.id")
Flux<OrderWithUserProjection> findAllWithUser();
```

Detect N+1: any `Flux.flatMap()` that calls a repository method inside the lambda is suspect.

## Threading Anti-Patterns

Beyond `.block()`, these also stall reactive threads:

```java
// WRONG — all of these block the event loop
CompletableFuture.get();           // blocks waiting for result
Thread.sleep(1000);                // blocks thread
CountDownLatch.await();            // blocks thread
synchronized (lock) { ... }       // can block thread

// WRONG — @Async creates thread pool, doesn't integrate with reactive
@Async
public CompletableFuture<Order> getOrder(String id) { ... }

// CORRECT — use reactive operators instead
Mono.delay(Duration.ofSeconds(1))  // non-blocking delay
Mono.fromFuture(completableFuture) // bridge to reactive
Schedulers.boundedElastic()        // isolate unavoidable blocking
```

## Patterns

### WebFlux Security Filter

`JwtAuthFilter implements WebFilter` — set via `.addFilterAt(jwtAuthFilter, SecurityWebFiltersOrder.AUTHENTICATION)`.
Principal name must be the userId string; extract with `ctx.getAuthentication().getName()`.
The filter must call `chain.filter(exchange).contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`.

### SecurityConfig for H2 Console

Must add `.headers(headers -> headers.frameOptions(fo -> fo.disable()))` to allow H2 iframe.
Use `.allowedOriginPatterns(List.of("*"))` not `.allowedOrigins("*")` when `allowCredentials` is false.

### GlobalExceptionHandler in WebFlux

Use `@ControllerAdvice` with `@ExceptionHandler` returning `Mono<ResponseEntity<ProblemDetail>>` — this works correctly in WebFlux (not only in MVC). Do NOT use `AbstractErrorWebExceptionHandler` unless you need to handle errors from non-controller paths.

### R2DBC Entity Design

R2DBC entities need full getters+setters (Lombok `@Data` on entities causes issues with auditing). Use `@CreatedDate` + `@LastModifiedDate` — requires `@EnableR2dbcAuditing` on the application class.

### R2DBC Repository Patterns

Use `@Query` for custom SQL on `ReactiveCrudRepository`. Named parameters work: `:paramName`.
`findByUserIdOrderByStartedAtDesc(UUID userId, Pageable pageable)` — Spring Data derives this correctly.
