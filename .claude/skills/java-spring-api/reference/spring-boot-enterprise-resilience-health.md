# Spring Boot Enterprise Patterns — Resilience, Health & Monitoring

Production-ready resilience, health check, and infrastructure patterns for Java 25 + Spring Boot 4.2. The code samples are the **WebFlux** variant; on Spring MVC (the default) use the Framework `@Retryable`/`@ConcurrencyLimit` and `RestClient`/`@HttpExchange` patterns in `spring-boot-templates.md`.

**Start with Spring Framework 7's built-in `@Retryable` / `@ConcurrencyLimit` (`@EnableResilientMethods`)** for bounded retry and bulkheading — templates in `spring-boot-templates.md`. Add Resilience4j when you need a circuit breaker, rate limiter or time-based bulkhead.

## Resilience4j Configuration

### application.yml

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        sliding-window-type: COUNT_BASED
        sliding-window-size: 100
        minimum-number-of-calls: 20
        failure-rate-threshold: 50
        slow-call-rate-threshold: 100
        slow-call-duration-threshold: 5s
        wait-duration-in-open-state: 30s
        permitted-number-of-calls-in-half-open-state: 10
        automatic-transition-from-open-to-half-open-enabled: true
        register-health-indicator: true
  retry:
    configs:
      default:
        max-attempts: 3
        wait-duration: 500ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        exponential-max-wait-duration: 5s
        retry-exceptions:
          - java.io.IOException
          - java.util.concurrent.TimeoutException
          - org.springframework.web.reactive.function.client.WebClientRequestException
        ignore-exceptions:
          - com.company.service.exception.InvalidInputException
          - com.company.service.exception.BusinessRuleException
  ratelimiter:
    configs:
      default:
        limit-for-period: 100
        limit-refresh-period: 1s
        timeout-duration: 1s
  timelimiter:
    configs:
      default:
        timeout-duration: 3s
        cancel-running-future: true
  bulkhead:
    configs:
      default:
        max-concurrent-calls: 25
        max-wait-duration: 0ms
```

### Maven Dependency

```xml
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-spring-boot4</artifactId>
    <version>2.4.0</version> <!-- not managed by the Boot BOM; built against Boot 4.0, not exercised in the 4.2 reference apps: run your tests -->
</dependency>
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-reactor</artifactId> <!-- WebFlux only -->
    <version>2.4.0</version>
</dependency>
```

## WebClient Connection Pool

```java
@Configuration
public class WebClientConfig {

    @Bean
    public WebClient.Builder webClientBuilder(
            @Value("${webclient.pool.max-connections:100}") int maxConnections,
            @Value("${webclient.pool.acquire-timeout-millis:5000}") int acquireTimeout,
            @Value("${webclient.pool.response-timeout-millis:10000}") int responseTimeout) {

        ConnectionProvider provider = ConnectionProvider.builder("app-pool")
            .maxConnections(maxConnections)
            .pendingAcquireTimeout(Duration.ofMillis(acquireTimeout))
            .build();

        HttpClient httpClient = HttpClient.create(provider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000)
            .responseTimeout(Duration.ofMillis(responseTimeout))
            .doOnConnected(conn -> conn
                .addHandlerLast(new ReadTimeoutHandler(responseTimeout, TimeUnit.MILLISECONDS))
                .addHandlerLast(new WriteTimeoutHandler(responseTimeout, TimeUnit.MILLISECONDS)));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
```

### application.yml

```yaml
webclient:
  pool:
    max-connections: 100
    acquire-timeout-millis: 5000
    response-timeout-millis: 10000
```

## Reactive Health Indicators

```java
@Component("applicationHealth")
@ConditionalOnProperty(name = "health.application.enabled", havingValue = "true", matchIfMissing = true)
public class ApplicationHealthIndicator implements ReactiveHealthIndicator {

    @Override
    public Mono<Health> health() {
        return Mono.just(Health.up()
                .withDetail("name", "application")
                .withDetail("timestamp", Instant.now().toString())
                .build())
            .onErrorResume(ex -> Mono.just(Health.down(ex)
                .withDetail("error", ex.getMessage())
                .build()));
    }
}
```

### Actuator Configuration

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health, info, prometheus     # never metrics, loggers, env, heapdump in production
  endpoint:
    health:
      show-details: never                     # details leak dependency names and versions
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState, db         # r2dbc on WebFlux
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Security: `health` and `info` public, `prometheus` behind a scope, every other endpoint denied with `EndpointRequest` (`spring-boot-enterprise-errors-security.md` → Actuator exposure). Boot 4 replaces the `enabled` flags with access levels (`management.endpoint.<id>.access`, `management.endpoints.access.default`); exposure plus the security rules above is enough.

## Method-Level Metrics — @Timed and ObservationRegistry

### @Timed (annotation-driven timer)

Add `micrometer-core` (already included via `spring-boot-starter-actuator`) and enable `@Timed` with `TimedAspect`:

```java
@Configuration
public class MicrometerConfig {

    @Bean
    public TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Annotate service methods:

```java
@Service
public class OrderService {

    @Timed(value = "orders.create", description = "Time to create an order",
           percentiles = {0.5, 0.95, 0.99})
    public Mono<OrderResponse> createOrder(CreateOrderRequest request) {
        return orderRepository.save(orderMapper.toEntity(request))
            .map(orderMapper::toResponse);
    }

    @Timed(value = "orders.find", description = "Time to fetch an order by ID",
           extraTags = {"tier", "standard"})
    public Mono<OrderResponse> findById(UUID id) {
        return orderRepository.findById(id).map(orderMapper::toResponse);
    }
}
```

**Metric naming:** `orders.create.timer{exception, method, result}` — tags are added automatically.

### Programmatic timer (for conditional or complex cases)

```java
@Service
@RequiredArgsConstructor
public class PaymentService {

    private final MeterRegistry registry;

    public Mono<PaymentResponse> processPayment(PaymentRequest request) {
        Timer.Sample sample = Timer.start(registry);
        return paymentGateway.charge(request)
            .doOnSuccess(r -> sample.stop(
                Timer.builder("payment.charge")
                    .tag("provider", request.provider())
                    .tag("result", "success")
                    .register(registry)))
            .doOnError(e -> sample.stop(
                Timer.builder("payment.charge")
                    .tag("provider", request.provider())
                    .tag("result", "error")
                    .tag("error", e.getClass().getSimpleName())
                    .register(registry)));
    }
}
```

### Prometheus scrape verification

```bash
# After running the app, confirm the metric is being scraped:
curl http://localhost:8080/actuator/prometheus | grep "orders_create"
# Expected output: orders_create_seconds_count{...} and orders_create_seconds_sum{...}
```

**application.yml — enable percentile histograms:**

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        orders.create: true
        payment.charge: true
      percentiles:
        orders.create: 0.5, 0.95, 0.99
```

## R2DBC Connection Pool

```yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 1h
      max-acquire-time: 2s
      max-create-connection-time: 5s
      validation-query: SELECT 1
```

## Swagger / OpenAPI Configuration

```java
@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .addSecurityItem(new SecurityRequirement().addList("BearerAuth"))
            .components(new Components()
                .addSecuritySchemes("BearerAuth", new SecurityScheme()
                    .name("BearerAuth")
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")));
    }
}
```

### Maven Dependency

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId> <!-- MVC: springdoc-openapi-starter-webmvc-ui -->
    <version>3.2.1</version> <!-- the springdoc line for Boot 4.2 -->
</dependency>
```

### application.yml

```yaml
springdoc:
  pre-loading-enabled: true   # WebFlux: build the model at startup, not with blocking classpath scanning on an event loop
  api-docs:
    enabled: ${OPENAPI_DOCS_ENABLED:false}   # off in production unless explicitly enabled
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
    display-request-duration: true
    operations-sorter: alpha
```
