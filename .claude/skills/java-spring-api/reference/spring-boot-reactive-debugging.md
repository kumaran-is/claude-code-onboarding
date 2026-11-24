# Reactive Stream Debugging & Observability

Runtime observability patterns for Java 25 + Spring Boot 4.2 WebFlux reactive streams.

## Reactor Hooks Configuration

Global hooks for monitoring reactive stream behavior. Production-safe hooks have low overhead; debug mode is restricted to dev/local environments.

### Configuration Class

```java
@Configuration
@RequiredArgsConstructor
public class ReactorHooksConfiguration {

    private final MeterRegistry meterRegistry;

    @Value("${spring.profiles.active:prod}")
    private String activeProfile;

    @Value("${reactor.debug.enabled:false}")
    private boolean debugEnabled;

    @PostConstruct
    public void configureReactorHooks() {
        configureDebugHooks();
        configureProductionHooks();
    }

    /**
     * Debug mode — dev/local ONLY. 10-20% performance overhead + high memory usage.
     * NEVER enable in QA or Production.
     */
    private void configureDebugHooks() {
        if (debugEnabled && ("local".equals(activeProfile) || "dev".equals(activeProfile))) {
            Hooks.onOperatorDebug();
            log.warn("Reactor debug mode ENABLED — development only, high overhead");
        }
    }

    /**
     * Production-safe hooks — low overhead, safe for all environments.
     */
    private void configureProductionHooks() {
        // Error monitoring — intercepts all operator errors for logging + metrics
        Hooks.onOperatorError((error, data) -> {
            String correlationId = MDC.get("correlationId");
            log.error("Reactive operator error — correlationId: {}, data: {}",
                correlationId, data, error);

            meterRegistry.counter("reactor.operator.error",
                "errorType", error.getClass().getSimpleName(),
                "environment", activeProfile
            ).increment();

            return error;
        });

        // Backpressure overflow — values dropped because downstream can't keep up
        Hooks.onNextDropped(dropped -> {
            log.warn("Dropped next signal (backpressure overflow): {}", dropped);
            meterRegistry.counter("reactor.dropped.next",
                "valueType", dropped != null ? dropped.getClass().getSimpleName() : "null"
            ).increment();
        });

        // Unhandled errors — errors not consumed by any operator in the chain
        Hooks.onErrorDropped(error -> {
            log.error("Dropped error signal (not handled in reactive chain)", error);
            meterRegistry.counter("reactor.dropped.error",
                "errorType", error.getClass().getSimpleName()
            ).increment();
        });
    }
}
```

### Environment Configuration

```yaml
# application.yml (base) — debug disabled by default
reactor:
  debug:
    enabled: false

# application-local.yml — enable for local development
reactor:
  debug:
    enabled: true

# application-dev.yml — enable for dev environment
reactor:
  debug:
    enabled: true

# application-prod.yml — ALWAYS disabled
reactor:
  debug:
    enabled: false
```

## Manual Checkpoints

Checkpoints mark critical stages in reactive chains for debugging without the overhead of `Hooks.onOperatorDebug()`. They appear in error stack traces, identifying exactly where in a chain a failure occurred.

### Pattern

```java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository orderRepository;
    private final PaymentServiceClient paymentClient;
    private final EventPublisher eventPublisher;

    public Mono<OrderResponse> createOrder(CreateOrderRequest request) {
        return validateRequest(request)
            .checkpoint("OrderService.createOrder — validation")
            .flatMap(this::toEntity)
            .flatMap(orderRepository::save)
            .checkpoint("OrderService.createOrder — database save")
            .flatMap(order -> paymentClient.charge(order)
                .thenReturn(order))
            .checkpoint("OrderService.createOrder — payment processing")
            .flatMap(eventPublisher::publishOrderCreated)
            .checkpoint("OrderService.createOrder — event publication")
            .map(orderMapper::toResponse);
    }

    public Mono<OrderResponse> findById(UUID id) {
        return orderRepository.findById(id)
            .checkpoint("OrderService.findById — database query")
            .switchIfEmpty(Mono.error(() ->
                new ResourceNotFoundException("Order not found: " + id)))
            .map(orderMapper::toResponse);
    }
}
```

### Naming Convention

```
ClassName.methodName — operation description
```

Guidelines:
- Place checkpoints **after** operations that might fail or change state
- Limit to 3-5 per complex method — too many creates noise
- Use descriptive operation names that appear clearly in stack traces

## Testing Hooks

```java
@ExtendWith(MockitoExtension.class)
class ReactorHooksConfigurationTest {

    @Mock private MeterRegistry meterRegistry;
    @Mock private Counter counter;
    private ReactorHooksConfiguration config;

    @BeforeEach
    void setUp() {
        when(meterRegistry.counter(anyString(), any(String[].class)))
            .thenReturn(counter);
        config = new ReactorHooksConfiguration(meterRegistry);
    }

    @AfterEach
    void tearDown() {
        Hooks.resetOnOperatorError();
        Hooks.resetOnNextDropped();
        Hooks.resetOnErrorDropped();
    }

    @Test
    @DisplayName("Should increment error counter when operator error occurs")
    void shouldTrackOperatorErrors() {
        config.configureReactorHooks();

        Mono.error(new RuntimeException("test"))
            .onErrorResume(e -> Mono.empty())
            .block();

        verify(counter, atLeastOnce()).increment();
    }
}
```

Always call `Hooks.resetOn*()` in `@AfterEach` to prevent hook leakage between tests.

## Troubleshooting

| Issue | Symptom | Fix |
|-------|---------|-----|
| MDC context lost | `correlationId` is null in hook logs | Configure context propagation via `WebFilter` that writes to `Reactor.Context` |
| Debug mode in prod | 10-20% performance degradation | Verify `application-prod.yml` has `reactor.debug.enabled: false` |
| Checkpoints too verbose | Noisy stack traces | Reduce to key state transitions only (3-5 per method) |
| Hook not triggering | Expected hooks not called | Check `@PostConstruct` runs (startup logs), ensure no `Hooks.resetOn*()` elsewhere |
| Metrics not appearing | No `reactor.operator.error` in `/actuator/metrics` | Verify `MeterRegistry` bean is injected, check actuator endpoint |
| Duplicate hook install | Hooks fire multiple times | Guard with a `boolean` flag or use `@ConditionalOnProperty` |
