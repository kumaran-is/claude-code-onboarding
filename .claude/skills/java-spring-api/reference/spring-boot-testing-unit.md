# Spring Boot Unit Testing Guide

> **Stack:** the samples below are mostly **WebFlux** (`StepVerifier`, BlockHound). Spring MVC tests (`@WebMvcTest` + `MockMvcTester`, `RestTestClient`, real RS256 tokens) are in `spring-boot-templates.md` → Spring MVC → Tests.

Unit testing patterns for Java 25 + Spring Boot 4.2 services (MVC and WebFlux) — covering test categories, BlockHound, Resilience4j mocking, and test data builders.

## Test Categories

| Category | Share | Annotation | Use When |
|----------|-------|------------|----------|
| **Unit** | 70-80% | `@ExtendWith(MockitoExtension.class)` | Testing a single class in isolation |
| **Integration** | 15-25% | `@SpringBootTest` + `@Testcontainers` | Testing real DB, critical workflows |
| **Contract** | 5-10% | `@RestClientTest` | Verifying external API client behavior |

### Annotation Selection

```java
// Unit test — fast, isolated, all deps mocked
@ExtendWith(MockitoExtension.class)
class OrderServiceTest { }

// Controller slice — only web layer loaded, @MockitoBean for service deps (@MockBean was removed in Boot 4)
@WebFluxTest(OrderController.class)
class OrderControllerTest {
    @MockitoBean private OrderService orderService;
    @Autowired private WebTestClient webTestClient;
}

// Repository slice — only data layer loaded
@DataR2dbcTest
class OrderRepositoryTest { }

// Full integration — real Spring context + real DB
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Testcontainers
class OrderIntegrationTest { }
```

**Rule**: Never use `@SpringBootTest` for unit tests. Prefer test slices.

## BlockHound — Blocking Detection

BlockHound is a Java agent that detects blocking calls from non-blocking threads in reactive applications. Test scope only — never deploy to production.

### Setup

```xml
<dependency>
    <groupId>io.projectreactor.tools</groupId>
    <artifactId>blockhound</artifactId>
    <scope>test</scope>
</dependency>
```

### Environment Configuration

Control BlockHound activation per environment using `@ConfigurationProperties`:

```java
@Configuration
@ConfigurationProperties(prefix = "blockhound")
public class BlockHoundProperties {
    private boolean enabled = false;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
```

```yaml
# application.yml (base) — disabled by default
blockhound:
  enabled: false

# application-test.yml — always enabled for tests
blockhound:
  enabled: true
```

### Base Test Class

All test classes should extend `BlockHoundTestBase` for automatic blocking detection.

```java
public abstract class BlockHoundTestBase {

    private static boolean blockHoundInstalled = false;

    @BeforeAll
    static void setUpBlockHound() {
        if (!blockHoundInstalled) {
            BlockHound.builder()
                // Load third-party BlockHound integrations via ServiceLoader
                .with(ServiceLoader.load(BlockHoundIntegration.class).stream()
                    .map(ServiceLoader.Provider::get)
                    .toArray(BlockHoundIntegration[]::new))
                // Cryptographic operations — SecureRandom uses native OS calls
                .allowBlockingCallsInside("java.security.SecureRandom", "nextBytes")
                // Jackson 3 (tools.jackson) — ObjectMapper may block during stream deserialization
                .allowBlockingCallsInside("tools.jackson.databind.ObjectMapper", "readValue")
                .allowBlockingCallsInside("tools.jackson.databind.ObjectMapper", "writeValueAsString")
                // JUnit lifecycle — test framework internals
                .allowBlockingCallsInside("org.junit.platform.launcher.core.DefaultLauncher", "execute")
                // Log4j2 async — blocking queues in async appenders
                .allowBlockingCallsInside("org.apache.logging.log4j.core.async.AsyncLogger", "logMessage")
                .install();
            blockHoundInstalled = true;
        }
    }

    protected static boolean isBlockHoundInstalled() {
        return blockHoundInstalled;
    }
}
```

Document every allowlist entry with a comment explaining why it's needed. Add project-specific entries as necessary.

### Verification Tests

```java
class BlockHoundVerificationTest extends BlockHoundTestBase {

    @Test
    @DisplayName("BlockHound should be installed and active")
    void shouldVerifyBlockHoundIsInstalled() {
        assertThat(isBlockHoundInstalled()).isTrue();
    }

    @Test
    @DisplayName("Should detect Thread.sleep() in reactive chain")
    void shouldDetectThreadSleep() {
        Mono<String> blocking = Mono.fromCallable(() -> {
            Thread.sleep(10);
            return "result";
        });

        StepVerifier.create(blocking)
            .expectError(BlockingOperationError.class)
            .verify();
    }

    @Test
    @DisplayName("Should detect .block() in reactive context")
    void shouldDetectBlockCall() {
        StepVerifier.create(Mono.defer(() -> {
            Mono.just("test").block(); // Reactor-side BlockHound integration
            return Mono.just("unreachable");
        })).expectError(BlockingOperationError.class).verify();
    }

    @Test
    @DisplayName("Should allow non-blocking operations")
    void shouldAllowNonBlockingOperations() {
        StepVerifier.create(Mono.just("result").map(String::toUpperCase))
            .expectNext("RESULT")
            .verifyComplete();
    }
}
```

### CI/CD Integration

Run tests with BlockHound enabled in the pipeline:

```bash
# Maven — activate test profile for BlockHound
mvn clean test -Dspring.profiles.active=test

# JVM arg BlockHound needs on JDK 13+ for bytecode instrumentation
./mvnw test   # surefire argLine: -XX:+AllowRedefinitionToAddDeleteMethods -XX:+EnableDynamicAgentLoading (enough on JDK 25)
```

### Troubleshooting

| Issue | Symptom | Fix |
|-------|---------|-----|
| False positive | Blocking detected in legitimate operation | Add to allowlist with justification comment |
| Third-party conflict | Library causes BlockHound errors | Check for library-provided `BlockHoundIntegration` via ServiceLoader, or add allowlist |
| JVM compatibility | Instrumentation errors on startup | Add `-XX:+AllowRedefinitionToAddDeleteMethods` JVM arg |
| Duplicate install | `BlockHound already installed` warning | Use the `blockHoundInstalled` guard in base class |

## Resilience4j Programmatic Testing

For services using programmatic Resilience4j (registry injection, not annotations), tests must verify the resilience chain.

### Mocking Registries

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock private OrderRepository orderRepository;
    @Mock private CircuitBreakerRegistry circuitBreakerRegistry;
    @Mock private RetryRegistry retryRegistry;
    @Mock private TimeLimiterRegistry timeLimiterRegistry;
    @Mock private CircuitBreaker circuitBreaker;
    @Mock private Retry retry;
    @Mock private TimeLimiter timeLimiter;
    @InjectMocks private OrderService orderService;

    @BeforeEach
    void setUp() {
        when(circuitBreakerRegistry.circuitBreaker("database"))
            .thenReturn(circuitBreaker);
        when(retryRegistry.retry("database"))
            .thenReturn(retry);
        when(timeLimiterRegistry.timeLimiter("database"))
            .thenReturn(timeLimiter);
    }
}
```

### Happy Path — Operators Don't Break Normal Flow

```java
@Test
@DisplayName("Should return order when DB call succeeds through resilience chain")
void findById_shouldSucceed_whenDatabaseResponds() {
    UUID id = UUID.randomUUID();
    var entity = new OrderEntity();
    entity.setId(id);

    when(orderRepository.findById(id)).thenReturn(Mono.just(entity));

    StepVerifier.create(orderService.findById(id))
        .expectNextMatches(order -> order.id().equals(id))
        .verifyComplete();

    verify(orderRepository).findById(id);
}
```

### Circuit Breaker Open — CallNotPermittedException

```java
@Test
@DisplayName("Should return service unavailable when circuit breaker is open")
void findById_shouldFail_whenCircuitBreakerOpen() {
    UUID id = UUID.randomUUID();
    when(orderRepository.findById(id))
        .thenReturn(Mono.error(CallNotPermittedException.createCallNotPermittedException(circuitBreaker)));

    StepVerifier.create(orderService.findById(id))
        .expectErrorMatches(t ->
            t instanceof ServiceIntegrationException &&
            t.getMessage().contains("circuit breaker"))
        .verify();
}
```

### Retry — Transient Failures

```java
@Test
@DisplayName("Should retry on transient database error")
void findById_shouldRetry_whenTransientError() {
    UUID id = UUID.randomUUID();
    var entity = new OrderEntity();
    entity.setId(id);

    when(orderRepository.findById(id))
        .thenReturn(Mono.error(new R2dbcTransientException("Connection timeout")))
        .thenReturn(Mono.just(entity));

    StepVerifier.create(orderService.findById(id))
        .expectNextMatches(order -> order.id().equals(id))
        .verifyComplete();

    verify(orderRepository, times(2)).findById(id);
}
```

### Timeout — Slow Operations

```java
@Test
@DisplayName("Should timeout on slow database operation")
void findById_shouldTimeout_whenDatabaseSlow() {
    UUID id = UUID.randomUUID();
    when(orderRepository.findById(id))
        .thenReturn(Mono.delay(Duration.ofSeconds(10)).then(Mono.empty()));

    StepVerifier.create(orderService.findById(id))
        .expectError(TimeoutException.class)
        .verify();
}
```

### Virtual Time — Testing Delays Without Waiting

Use `StepVerifier.withVirtualTime()` for time-dependent logic (retries with backoff, scheduled tasks, timeouts) to avoid real delays in the test suite.

```java
@Test
@DisplayName("Should complete after delay without real waiting")
void shouldHandleDelayedEmission() {
    StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofMinutes(5)).thenReturn("done"))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(5))
        .expectNext("done")
        .verifyComplete();
}

@Test
@DisplayName("Should retry with backoff using virtual time")
void shouldRetryWithBackoff_usingVirtualTime() {
    AtomicInteger attempts = new AtomicInteger(0);

    StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(new RuntimeException("transient"));
            }
            return Mono.just("success");
        }).retryWhen(Retry.backoff(3, Duration.ofSeconds(2))))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(10)) // fast-forward through backoff delays
        .expectNext("success")
        .verifyComplete();
}
```

**Rule**: Always wrap the publisher creation inside the `withVirtualTime(() -> ...)` lambda — creating it outside breaks virtual time scheduling.

### Fallback Verification

```java
@Test
@DisplayName("Should invoke fallback with context when all retries exhausted")
void findById_shouldFallback_whenAllRetriesExhausted() {
    UUID id = UUID.randomUUID();
    when(orderRepository.findById(id))
        .thenReturn(Mono.error(new RuntimeException("DB down")));

    StepVerifier.create(orderService.findById(id))
        .expectErrorMatches(t ->
            t instanceof ServiceIntegrationException &&
            t.getMessage().contains(id.toString()))
        .verify();
}
```

## Test Data Builders

Use the Builder pattern for readable, maintainable test data.

```java
public class OrderTestData {

    public static OrderEntity.OrderEntityBuilder anOrder() {
        return OrderEntity.builder()
            .id(UUID.randomUUID())
            .customerId("cust-001")
            .status(OrderStatus.PENDING)
            .totalAmount(BigDecimal.valueOf(99.99))
            .createdAt(Instant.now())
            .updatedAt(Instant.now());
    }

    public static OrderEntity.OrderEntityBuilder aCancelledOrder() {
        return anOrder()
            .status(OrderStatus.CANCELLED)
            .cancelledAt(Instant.now());
    }

    public static CreateOrderRequest.CreateOrderRequestBuilder aCreateRequest() {
        return CreateOrderRequest.builder()
            .customerId("cust-001")
            .itemId("item-001")
            .quantity(2)
            .amount(BigDecimal.valueOf(49.99));
    }
}

// Usage
@Test
void shouldProcessOrder() {
    var order = OrderTestData.anOrder()
        .customerId("vip-customer")
        .totalAmount(BigDecimal.valueOf(500.00))
        .build();
    // ...
}
```

## Naming Conventions

```java
// Method: methodName_should_expectedBehavior_when_condition
void findById_shouldReturnOrder_whenOrderExists()
void findById_shouldThrowNotFound_whenOrderMissing()
void create_shouldApplyDiscount_whenCustomerIsPremium()

// Always add @DisplayName for readable test reports
@DisplayName("Should return order when valid ID provided")
@DisplayName("Should return 404 when order does not exist")
@DisplayName("Should apply 15% discount for premium customers")
```
