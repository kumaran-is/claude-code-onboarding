# Spring Boot Integration Testing Guide

> **Stack:** the client samples below are **WebFlux** (`WebClient`, `StepVerifier`). Spring MVC integration tests (`RestTestClient`, Testcontainers, JWTs with issuer and audience) are in `spring-boot-templates.md` → Spring MVC → Tests.

Integration testing patterns for Java 25 + Spring Boot 4.2 services — covering Testcontainers, contract testing with WireMock, external API resilience testing, and coverage standards.

## Testcontainers — Integration Testing

Use real databases instead of H2 to catch database-specific issues.

### PostgreSQL Setup

```java
// Testcontainers 2: org.testcontainers.postgresql.PostgreSQLContainer (artifact testcontainers-postgresql), no generic.
// @ServiceConnection wires the JDBC datasource (MVC), the R2DBC connection factory and Flyway (WebFlux) — no
// hand-written spring.datasource / spring.r2dbc / spring.flyway properties.
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {
    @Bean
    @ServiceConnection
    PostgreSQLContainer postgresContainer() {
        return new PostgreSQLContainer(DockerImageName.parse("postgres:18.7")); // pinned, never "latest"
    }
}

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import(TestcontainersConfiguration.class)
class OrderRepositoryIntegrationTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    @DisplayName("Should save and retrieve order from real database")
    void shouldSaveAndRetrieve() {
        var order = OrderTestData.anOrder().build();

        StepVerifier.create(
            orderRepository.save(order)
                .then(orderRepository.findById(order.getId())))
            .expectNextMatches(retrieved ->
                retrieved.getCustomerId().equals(order.getCustomerId()))
            .verifyComplete();
    }
}
```

### Maven Dependencies (Testcontainers 2 artifact names; versions from the Boot BOM; plus `spring-boot-testcontainers`)

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-r2dbc</artifactId> <!-- WebFlux only -->
    <scope>test</scope>
</dependency>
```

## Contract Testing — External API Clients

Verify your HTTP client code handles expected response formats without calling real services.

```java
@WebFluxTest
@Import(PaymentServiceClient.class)
class PaymentServiceClientContractTest {

    @Autowired
    private PaymentServiceClient client;

    private static WireMockServer wireMock;

    @BeforeAll
    static void startWireMock() {
        wireMock = new WireMockServer(wireMockConfig().dynamicPort());
        wireMock.start();
    }

    @AfterAll
    static void stopWireMock() { wireMock.stop(); }

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("integration.payment-service.base-url", wireMock::baseUrl);
    }

    @Test
    @DisplayName("Should parse successful payment response")
    void shouldHandleSuccessResponse() {
        wireMock.stubFor(post(urlEqualTo("/api/v1/payments"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"transactionId": "txn-123", "status": "APPROVED"}
                    """)));

        StepVerifier.create(client.processPayment(new PaymentRequest("order-1", BigDecimal.TEN), "idem-order-1"))
            .expectNextMatches(r -> r.status().equals("APPROVED"))
            .verifyComplete();
    }

    @Test
    @DisplayName("Should throw on payment service error")
    void shouldHandleErrorResponse() {
        wireMock.stubFor(post(urlEqualTo("/api/v1/payments"))
            .willReturn(aResponse().withStatus(500)));

        StepVerifier.create(client.processPayment(new PaymentRequest("order-1", BigDecimal.TEN), "idem-order-1"))
            .expectError(ServiceIntegrationException.class)
            .verify();
    }
}
```

## External API Clients — Resilience + WireMock

When an external API call is wrapped with resilience operators, test both the happy path and circuit-open path through WireMock.

```java
@ExtendWith(MockitoExtension.class)
class PaymentServiceClientResilienceTest {

    @Mock private CircuitBreakerRegistry cbRegistry;
    @Mock private RetryRegistry retryRegistry;
    @Mock private CircuitBreaker circuitBreaker;
    @Mock private Retry retry;
    @InjectMocks private PaymentServiceClient client;

    private static WireMockServer wireMock;

    @BeforeAll
    static void startWireMock() {
        wireMock = new WireMockServer(wireMockConfig().dynamicPort());
        wireMock.start();
    }

    @AfterAll
    static void stopWireMock() { wireMock.stop(); }

    @BeforeEach
    void setUp() {
        when(cbRegistry.circuitBreaker("payment-api")).thenReturn(circuitBreaker);
        when(retryRegistry.retry("payment-api")).thenReturn(retry);
    }

    @Test
    @DisplayName("Should process payment through resilience chain when API responds 200")
    void processPayment_shouldSucceed_whenApiResponds() {
        wireMock.stubFor(post(urlEqualTo("/api/v1/payments"))
            .willReturn(aResponse().withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"transactionId": "txn-123", "status": "APPROVED"}
                    """)));

        StepVerifier.create(client.processPayment(new PaymentRequest("order-1", BigDecimal.TEN), "idem-order-1"))
            .expectNextMatches(r -> r.status().equals("APPROVED"))
            .verifyComplete();
    }

    @Test
    @DisplayName("Should fallback when circuit breaker is open for payment API")
    void processPayment_shouldFallback_whenCircuitBreakerOpen() {
        when(cbRegistry.circuitBreaker("payment-api"))
            .thenThrow(CallNotPermittedException.createCallNotPermittedException(circuitBreaker));

        StepVerifier.create(client.processPayment(new PaymentRequest("order-1", BigDecimal.TEN), "idem-order-1"))
            .expectErrorMatches(t ->
                t instanceof ServiceIntegrationException &&
                t.getMessage().contains("payment"))
            .verify();
    }
}
```

## Coverage Standards

| Metric | Minimum | Tool |
|--------|---------|------|
| Line coverage | 90% | JaCoCo |
| Branch coverage | 80% | JaCoCo |
| Mutation score | 70% | PIT (optional) |

Enforce via CI pipeline. PRs below threshold are blocked.

## Testing Checklist

- [ ] Unit tests use `@ExtendWith(MockitoExtension.class)`, NOT `@SpringBootTest`
- [ ] All reactive streams tested with `StepVerifier`
- [ ] No `.block()` calls in any test
- [ ] BlockHound installed in base test class
- [ ] Test data uses builder pattern for readability
- [ ] Resilience registries mocked (`CircuitBreakerRegistry`, `RetryRegistry`, `TimeLimiterRegistry`)
- [ ] Registry instances retrieved by configured name (e.g., `"database"`)
- [ ] Happy path: resilience operators don't break normal flow
- [ ] Circuit breaker open: `CallNotPermittedException` -> fallback with context
- [ ] Retry: transient failure -> success on retry, `verify(repo, times(N))`
- [ ] Timeout: slow operation -> `TimeoutException`
- [ ] Fallback includes context (IDs, error details) in error message
- [ ] External API clients tested with resilience operators + WireMock
- [ ] Integration tests use Testcontainers (not H2)
- [ ] External API clients have contract tests with WireMock
- [ ] `@DisplayName` on every test method
- [ ] 90%+ line coverage, 80%+ branch coverage
