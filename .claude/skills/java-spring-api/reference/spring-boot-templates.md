# Spring Boot 4.2 Code Templates (Java 25)

Condensed from two reference services built and tested on JDK 25 with PostgreSQL 18.7 (Testcontainers) on 2026-11-24. Imports are omitted when the package is obvious; non-obvious ones are listed. Pick the section for your stack (decision table: `../SKILL.md`).

---

## Spring MVC (default)

### Entity (JPA, optimistic locking, assigned UUID)

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id private UUID id;
    @Column(name = "customer_id", nullable = false, updatable = false, length = 64) private String customerId;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 16) private OrderStatus status;
    @Column(nullable = false, precision = 12, scale = 2) private BigDecimal total;
    // Wrapper type on purpose: a null version tells Spring Data the entity is new (the id is assigned here)
    @Version private @Nullable Long version;                       // org.jspecify.annotations.Nullable
    @Column(name = "created_at", nullable = false, updatable = false) private Instant createdAt;

    protected Order() { }                                          // JPA

    public Order(String customerId, BigDecimal total, Instant createdAt) {
        this.id = UUID.randomUUID();
        this.customerId = customerId;
        this.status = OrderStatus.PENDING;
        this.total = total;
        this.createdAt = createdAt;
    }

    public void update(OrderStatus status, BigDecimal total) { this.status = status; this.total = total; }
    public long getVersion() { return version != null ? version : 0L; }
    // other getters
}
```

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    Page<Order> findByCustomerId(String customerId, Pageable pageable);
}
```

### DTO records

```java
public record CreateOrderRequest(@NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2) BigDecimal total) {}
public record CreateOrdersRequest(@NotEmpty @Size(max = 50) List<@Valid @NotNull CreateOrderRequest> orders) {}
public record UpdateOrderRequest(@NotNull OrderStatus status, @NotNull @DecimalMin("0.00") BigDecimal total) {}

public record OrderResponse(UUID id, String customerId, OrderStatus status, BigDecimal total, long version, Instant createdAt) {
    static OrderResponse from(Order o) {
        return new OrderResponse(o.getId(), o.getCustomerId(), o.getStatus(), o.getTotal(), o.getVersion(), o.getCreatedAt());
    }
}

/** Stable page shape: Spring Data's PageImpl is not a JSON contract. */
public record PageResponse<T>(List<T> content, int page, int size, long totalElements, int totalPages) {
    static <S, T> PageResponse<T> of(Page<S> page, Function<S, T> mapper) {
        return new PageResponse<>(page.getContent().stream().map(mapper).toList(),
            page.getNumber(), page.getSize(), page.getTotalElements(), page.getTotalPages());
    }
}
```

### Sealed domain exceptions

```java
public abstract sealed class OrderException extends RuntimeException
        permits OrderException.NotFound, OrderException.VersionConflict, OrderException.PreconditionRequired {
    private OrderException(String message) { super(message); }
    public static final class NotFound extends OrderException { public NotFound(UUID id) { super("Order " + id + " not found"); } }
    public static final class VersionConflict extends OrderException { public VersionConflict(UUID id) { super("Order " + id + " was modified"); } }
    public static final class PreconditionRequired extends OrderException { public PreconditionRequired() { super("If-Match header required"); } }
}
```

### Service (transaction boundary, ownership, optimistic lock)

```java
@Service
@Transactional(readOnly = true)
public class OrderService {
    private final OrderRepository orders;
    private final Clock clock;

    public OrderService(OrderRepository orders, Clock clock) { this.orders = orders; this.clock = clock; }

    @Transactional
    public OrderResponse create(Caller caller, CreateOrderRequest request) {
        return OrderResponse.from(orders.save(new Order(caller.customerId(), request.total(), clock.instant())));
    }

    /** All or nothing: each insert is flushed, so a later constraint failure rolls back the earlier rows. */
    @Transactional
    public List<OrderResponse> createAll(Caller caller, List<CreateOrderRequest> requests) {
        return requests.stream()
            .map(r -> orders.saveAndFlush(new Order(caller.customerId(), r.total(), clock.instant())))
            .map(OrderResponse::from)
            .toList();
    }

    public PageResponse<OrderResponse> list(Caller caller, Pageable pageable) {
        Page<Order> page = caller.admin() ? orders.findAll(pageable) : orders.findByCustomerId(caller.customerId(), pageable);
        return PageResponse.of(page, OrderResponse::from);
    }

    @Transactional
    public OrderResponse update(Caller caller, UUID id, long expectedVersion, UpdateOrderRequest request) {
        Order order = load(caller, id);
        if (order.getVersion() != expectedVersion) throw new OrderException.VersionConflict(id);
        order.update(request.status(), request.total());
        orders.flush();          // incremented version in the response; a concurrent update fails here
        return OrderResponse.from(order);
    }

    private Order load(Caller caller, UUID id) {
        return orders.findById(id).filter(caller::canAccess).orElseThrow(() -> new OrderException.NotFound(id));
    }
}

/** Token subject = customer id; the orders:admin scope lifts the ownership filter. */
public record Caller(String customerId, boolean admin) {
    public static Caller from(Authentication auth) {
        boolean admin = auth.getAuthorities().stream().map(GrantedAuthority::getAuthority).anyMatch("SCOPE_orders:admin"::equals);
        return new Caller(auth.getName(), admin);
    }
    boolean canAccess(Order order) { return admin || customerId.equals(order.getCustomerId()); }
}
```

### Controller (201 + Location, ETag / If-Match, bounded and whitelisted paging)

```java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    private static final Set<String> SORTABLE = Set.of("createdAt", "total");
    private final OrderService orders;

    OrderController(OrderService orders) { this.orders = orders; }

    @PostMapping
    ResponseEntity<OrderResponse> create(Authentication auth, @Valid @RequestBody CreateOrderRequest request, UriComponentsBuilder uri) {
        OrderResponse created = orders.create(Caller.from(auth), request);
        return ResponseEntity.created(uri.path("/api/v1/orders/{id}").buildAndExpand(created.id()).toUri())
            .eTag("\"" + created.version() + "\"").body(created);
    }

    @GetMapping
    PageResponse<OrderResponse> list(Authentication auth,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable) {
        for (Sort.Order o : pageable.getSort()) {
            if (!SORTABLE.contains(o.getProperty())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported sort property");
        }
        Sort stable = pageable.getSort().and(Sort.by(Sort.Direction.DESC, "id"));   // deterministic tiebreaker
        return orders.list(Caller.from(auth), PageRequest.of(pageable.getPageNumber(), pageable.getPageSize(), stable));
    }

    @PutMapping("/{id}")
    ResponseEntity<OrderResponse> update(Authentication auth, @PathVariable UUID id,
            @RequestHeader(name = HttpHeaders.IF_MATCH, required = false) @Nullable String ifMatch,
            @Valid @RequestBody UpdateOrderRequest request) {
        if (ifMatch == null || ifMatch.isBlank()) throw new OrderException.PreconditionRequired();   // 428
        OrderResponse updated = orders.update(Caller.from(auth), id, parseVersion(id, ifMatch), request);
        return ResponseEntity.ok().eTag("\"" + updated.version() + "\"").body(updated);
    }
    // parseVersion: strip W/ and quotes, Long.parseLong, NumberFormatException -> VersionConflict
}
```

`spring.data.web.pageable.max-page-size=100` caps `size` (a request for 1000 gets 100).

### ProblemDetail advice (sets `instance`, never echoes input)

```java
@RestControllerAdvice
public class ProblemDetailsAdvice extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ProblemDetailsAdvice.class);

    @ExceptionHandler(OrderException.class)
    ProblemDetail handleOrder(OrderException ex, HttpServletRequest request) {
        return switch (ex) {
            case OrderException.NotFound _ -> problem(HttpStatus.NOT_FOUND, "Order not found", "No order with this id is visible to you", request);
            case OrderException.VersionConflict _ -> problem(HttpStatus.CONFLICT, "Version conflict", "Fetch the order again and retry with the new ETag", request);
            case OrderException.PreconditionRequired p -> problem(HttpStatus.PRECONDITION_REQUIRED, "Precondition required", p.getMessage(), request);
        };
    }

    @ExceptionHandler(ObjectOptimisticLockingFailureException.class)   // lost race at flush
    ProblemDetail handleOptimisticLock(ObjectOptimisticLockingFailureException ex, HttpServletRequest request) {
        return problem(HttpStatus.CONFLICT, "Version conflict", "The order was changed by another request", request);
    }

    @ExceptionHandler(RestClientException.class)                         // includes retry exhaustion of the client
    ProblemDetail handleUpstream(RestClientException ex, HttpServletRequest request) {
        log.warn("Upstream call failed on {}", request.getRequestURI(), ex);
        return problem(HttpStatus.BAD_GATEWAY, "Upstream service unavailable", "Retry later", request);
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex, HttpServletRequest request) {
        log.error("Unhandled error on {} {}", request.getMethod(), request.getRequestURI(), ex);
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Internal error", "An unexpected error occurred", request);
    }

    @Override   // field names and messages only, never rejected values
    protected @Nullable ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        List<Map<String, String>> errors = ex.getBindingResult().getFieldErrors().stream()
            .map(e -> Map.of("field", e.getField(), "message", Objects.requireNonNullElse(e.getDefaultMessage(), "invalid")))
            .toList();
        ProblemDetail body = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, "Request validation failed");
        body.setTitle("Invalid request");
        body.setProperty("errors", errors);
        return handleExceptionInternal(ex, body, headers, status, request);
    }

    /** Every Spring MVC exception passes here: Framework 7.1 no longer sets instance. */
    @Override
    protected @Nullable ResponseEntity<Object> handleExceptionInternal(Exception ex, @Nullable Object body,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        ResponseEntity<Object> response = super.handleExceptionInternal(ex, body, headers, status, request);
        if (response != null && response.getBody() instanceof ProblemDetail p && p.getInstance() == null
                && request instanceof ServletWebRequest servlet) {
            p.setInstance(URI.create(servlet.getRequest().getRequestURI()));
        }
        return response;
    }

    private static ProblemDetail problem(HttpStatus status, String title, String detail, HttpServletRequest request) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setTitle(title);
        p.setInstance(URI.create(request.getRequestURI()));
        return p;
    }
}
```

Override `handleHandlerMethodValidationException` the same way for `@PathVariable` / `@RequestParam` constraint failures.

### Security (OAuth2 resource server, scopes, actuator)

```java
@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    // Boot's public-key decoder adds every OAuth2TokenValidator<Jwt> bean; audience comes from jwt.audiences
    @Bean
    OAuth2TokenValidator<Jwt> issuerValidator(@Value("${app.security.jwt.issuer}") String issuer) {
        return new JwtIssuerValidator(issuer);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) {            // build() declares no checked exception in Security 7
        http.authorizeHttpRequests(r -> r
                .requestMatchers(EndpointRequest.to("health", "info")).permitAll()
                .requestMatchers(EndpointRequest.to("prometheus")).hasAuthority("SCOPE_metrics:read")
                .requestMatchers(EndpointRequest.toAnyEndpoint()).denyAll()
                .requestMatchers("/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/**").hasAuthority("SCOPE_orders:read")
                .requestMatchers("/api/**").hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Bearer-token API: browsers never attach the Authorization header, so CSRF cannot ride on it.
            .csrf(c -> c.disable());
        return http.build();
    }
}
```

`EndpointRequest`: `org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest`. Token validation (tested: wrong audience → 401, wrong issuer → 401, foreign key → 401): `public-key-location` gives signature and expiry, `jwt.audiences` adds the audience check, and the `JwtIssuerValidator` bean adds the issuer check. Always require both: a token another service obtained from the same identity provider is otherwise accepted. Use `issuer-uri` only **instead of** `public-key-location`: with both set, Boot 4.2 switches to OIDC discovery and ignores the key.

### Declarative HTTP client with bounded retry and a bulkhead

```java
@HttpExchange(url = "/prices", accept = "application/json")
public interface PricingClient {
    @GetExchange("/{sku}") PriceQuote getPrice(@PathVariable String sku);
    record PriceQuote(String sku, BigDecimal unitPrice, String currency) {}
}

@Configuration(proxyBeanMethods = false)
@EnableResilientMethods                                              // org.springframework.resilience.annotation
@ImportHttpServices(group = "pricing", types = PricingClient.class)  // org.springframework.web.service.registry
class PricingConfig {}

@Service
public class PricingService {
    private final PricingClient client;
    PricingService(PricingClient client) { this.client = client; }

    /** Idempotent GET: retry 5xx and I/O errors only, 2 retries with backoff; at most 10 concurrent calls. */
    @Retryable(includes = { HttpServerErrorException.class, ResourceAccessException.class },
               maxRetries = 2, delay = 100, multiplier = 2, maxDelay = 1000)
    @ConcurrencyLimit(10)
    public PriceQuote quote(String sku) { return client.getPrice(sku); }
}
```

Properties: `spring.http.serviceclient.pricing.base-url`, `.connect-timeout`, `.read-timeout`. After the last retry the original exception is rethrown (map it to 502). Keep remote calls out of `@Transactional` methods.

### Tests

```java
// Shared Testcontainers config (Testcontainers 2)
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {
    @Bean @ServiceConnection
    PostgreSQLContainer postgresContainer() {                       // org.testcontainers.postgresql.PostgreSQLContainer
        return new PostgreSQLContainer(DockerImageName.parse("postgres:18.7"));
    }
}

// Full stack: real Tomcat (virtual threads), real PostgreSQL, real JWT validation. Same config → one cached context.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestcontainersConfiguration.class)
@AutoConfigureRestTestClient   // org.springframework.boot.resttestclient.autoconfigure
@AutoConfigureMetrics          // org.springframework.boot.micrometer.metrics.test.autoconfigure — only if a test needs /actuator/prometheus
public abstract class IntegrationTest {
    @Autowired protected RestTestClient client;                     // org.springframework.test.web.servlet.client.RestTestClient

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.security.oauth2.resourceserver.jwt.public-key-location", TestJwts::publicKeyLocation);
        registry.add("spring.security.oauth2.resourceserver.jwt.audiences", () -> TestJwts.AUDIENCE);
        registry.add("app.security.jwt.issuer", () -> TestJwts.ISSUER);   // TestJwts mints iss/aud with these
    }
}

class OrderApiIntegrationTests extends IntegrationTest {
    @Test
    void createReturns201WithLocationAndEtag() {
        client.post().uri("/api/v1/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + TestJwts.token("alice", "orders:write"))
            .contentType(MediaType.APPLICATION_JSON).body("{\"total\": 25.50}")
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals(HttpHeaders.ETAG, "\"0\"");
    }

    @Test
    void readScopeCannotWrite() {
        client.post().uri("/api/v1/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + TestJwts.token("alice", "orders:read"))
            .contentType(MediaType.APPLICATION_JSON).body("{\"total\": 1}")
            .exchange().expectStatus().isForbidden();
    }
}

// Web slice with the real security rules and a mocked service
@WebMvcTest(OrderController.class)              // org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest
@Import(SecurityConfig.class)
class OrderControllerWebMvcTests {
    @Autowired MockMvcTester mvc;               // org.springframework.test.web.servlet.assertj.MockMvcTester
    @MockitoBean OrderService orderService;     // @MockBean no longer exists

    @DynamicPropertySource                      // the resource-server auto-config still needs a key location
    static void properties(DynamicPropertyRegistry r) {
        r.add("spring.security.oauth2.resourceserver.jwt.public-key-location", TestJwts::publicKeyLocation);
        r.add("spring.security.oauth2.resourceserver.jwt.audiences", () -> TestJwts.AUDIENCE);
        r.add("app.security.jwt.issuer", () -> TestJwts.ISSUER);
    }

    @Test
    void invalidBodyNeverReachesTheService() {
        assertThat(mvc.post().uri("/api/v1/orders")
                .with(jwt().jwt(t -> t.subject("alice")).authorities(() -> "SCOPE_orders:write"))
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
            .hasStatus(HttpStatus.BAD_REQUEST)
            .hasContentType(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyJson().extractingPath("$.errors[0].field").isEqualTo("total");
        then(orderService).should(never()).create(any(), any());
    }
}
```

`TestJwts`: generate an RSA key pair per JVM, write the public key as PEM to a temp file, sign tokens with `NimbusJwtEncoder.withKeyPair(publicKey, privateKey).build()`; never commit a private key. Prove virtual threads once: a test-only filter or endpoint reporting `Thread.currentThread().isVirtual()`.

---

## Spring WebFlux (when justified)

Additional dependencies beyond the WebFlux starter: `spring-boot-starter-webclient` (WebClient-backed HTTP service groups), `io.micrometer:context-propagation`, `spring-jdbc` + `postgresql` (Flyway), `r2dbc-postgresql`; tests: `reactor-test`, `testcontainers-r2dbc`, `io.projectreactor.tools:blockhound` and `blockhound-junit-platform` (not managed by the Boot BOM: pin the version).

### Entity (immutable record) and repository

```java
@Table("orders")
public record Order(@Id @Nullable Long id, String customerId, String sku, int quantity, OrderStatus status,
                    @Version @Nullable Long version, Instant createdAt, Instant updatedAt) {
    static Order newOrder(String customerId, String sku, int quantity, Instant now) {
        return new Order(null, customerId, sku, quantity, OrderStatus.NEW, null, now, now);
    }
    /** Carries the client's expected version, so the UPDATE is guarded by it. */
    Order withChanges(String sku, int quantity, long expectedVersion, Instant now) {
        return new Order(id, customerId, sku, quantity, status, expectedVersion, createdAt, now);
    }
}

public interface OrderRepository extends ReactiveCrudRepository<Order, Long> {
    Flux<Order> findByCustomerIdOrderByIdAsc(String customerId, Pageable pageable);
}
```

### Service: explicit transactions, events after commit, streaming with backpressure

```java
@Service
public class OrderService {
    public static final int MAX_PAGE_SIZE = 100;
    static final int EXPORT_FETCH_SIZE = 64;
    private final OrderRepository repository;
    private final R2dbcEntityTemplate template;
    private final OrderEvents events;
    private final Clock clock;
    private final TransactionalOperator tx;
    private final TransactionalOperator readOnlyTx;

    public OrderService(OrderRepository repository, R2dbcEntityTemplate template, OrderEvents events, Clock clock,
                        ReactiveTransactionManager txManager) {
        this.repository = repository; this.template = template; this.events = events; this.clock = clock;
        this.tx = TransactionalOperator.create(txManager);
        DefaultTransactionDefinition readOnly = new DefaultTransactionDefinition(TransactionDefinition.PROPAGATION_REQUIRED);
        readOnly.setReadOnly(true);
        this.readOnlyTx = TransactionalOperator.create(txManager, readOnly);
    }

    /** All or nothing; events are published only after the commit signal. */
    public Flux<OrderDto> createAll(Caller caller, List<CreateOrderRequest> requests) {
        return Flux.fromIterable(requests)
            .concatMap(r -> repository.save(Order.newOrder(caller.subject(), r.sku(), r.quantity(), clock.instant())))
            .map(OrderDto::from)
            .collectList()
            .as(tx::transactional)
            .flatMapMany(Flux::fromIterable)
            .doOnNext(dto -> events.publish(OrderEvents.Type.CREATED, dto));
    }

    public Mono<OrderDto> update(Caller caller, long id, UpdateOrderRequest request) {
        return findAccessible(caller, id)
            .flatMap(o -> repository.save(o.withChanges(request.sku(), request.quantity(), request.version(), clock.instant())))
            .onErrorMap(OptimisticLockingFailureException.class, ex -> new StaleOrderVersionException(id, ex))   // → 409
            .map(OrderDto::from)
            .as(tx::transactional);
    }

    /** Backpressure reaches the database: cursor with a fetch size (a portal, so inside a read-only transaction). */
    public Flux<OrderDto> export(Caller caller) {
        return template.getDatabaseClient()
            .sql("SELECT * FROM orders WHERE customer_id = :customerId ORDER BY id")
            .bind("customerId", caller.subject())
            .filter(statement -> statement.fetchSize(EXPORT_FETCH_SIZE))
            .map((row, metadata) -> template.getConverter().read(Order.class, row, metadata))
            .all()
            .limitRate(EXPORT_FETCH_SIZE)
            .map(OrderDto::from)
            .as(readOnlyTx::transactional);
    }

    Mono<Order> findAccessible(Caller caller, long id) {
        return repository.findById(id).filter(caller::canAccess)
            .switchIfEmpty(Mono.error(() -> new OrderNotFoundException(id)));
    }
}
```

### Controller: NDJSON export and SSE with heartbeat

```java
@GetMapping(path = "/export", produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<OrderDto> export(@AuthenticationPrincipal Jwt jwt) {
    return service.export(Caller.from(jwt));                      // the client's read rate drives the DB fetches
}

@GetMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<OrderDto>> stream(@AuthenticationPrincipal Jwt jwt) {
    Caller caller = Caller.from(jwt);
    Flux<ServerSentEvent<OrderDto>> changes = events.stream()
        .filter(e -> caller.admin() || caller.subject().equals(e.order().customerId()))
        .map(e -> ServerSentEvent.builder(e.order()).id(e.order().id() + "-" + e.order().version()).event(e.type().name()).build());
    Flux<ServerSentEvent<OrderDto>> keepalive = Flux.interval(Duration.ZERO, Duration.ofSeconds(15))
        .map(tick -> ServerSentEvent.<OrderDto>builder().comment("keepalive").build());
    return Flux.merge(changes, keepalive);                        // cancellation of the response cancels both
}
```

Event fan-out: `Sinks.many().multicast().directBestEffort()` plus a bounded per-subscriber `onBackpressureBuffer(64, onDrop, BufferOverflowStrategy.DROP_OLDEST)`. Not `multicast().onBackpressureBuffer(n)`: it buffers events emitted while nobody listens and replays them to the first subscriber.

### ProblemDetail advice (reactive; sets `instance`, never echoes input)

```java
@RestControllerAdvice   // extends org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler
public class ProblemDetailsAdvice extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ProblemDetailsAdvice.class);

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail notFound(OrderNotFoundException ex, ServerWebExchange exchange) {
        return problem(HttpStatus.NOT_FOUND, "Order not found", exchange);
    }

    @ExceptionHandler(PricingUnavailableException.class)     // the service maps every pricing failure (after retries) with onErrorMap
    ProblemDetail pricingUnavailable(PricingUnavailableException ex, ServerWebExchange exchange) {
        log.warn("pricing call failed path={}", exchange.getRequest().getPath().value(), ex);
        return problem(HttpStatus.SERVICE_UNAVAILABLE, "Pricing is temporarily unavailable", exchange);
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail unexpected(Exception ex, ServerWebExchange exchange) {
        log.error("unhandled error path={}", exchange.getRequest().getPath().value(), ex);
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Unexpected error", exchange);
    }

    @Override   // field + message only: the rejected value is never reflected back
    protected Mono<ResponseEntity<Object>> handleWebExchangeBindException(WebExchangeBindException ex,
            HttpHeaders headers, HttpStatusCode status, ServerWebExchange exchange) {
        ex.getBody().setProperty("errors", ex.getFieldErrors().stream()
                .map(e -> Map.of("field", e.getField(), "message", e.getDefaultMessage() == null ? "invalid" : e.getDefaultMessage()))
                .toList());
        return super.handleWebExchangeBindException(ex, headers, status, exchange);
    }

    @Override   // Framework 7.1 does not set instance on the built-in problems
    protected Mono<ResponseEntity<Object>> handleExceptionInternal(Exception ex, @Nullable Object body,
            @Nullable HttpHeaders headers, HttpStatusCode status, ServerWebExchange exchange) {
        return super.handleExceptionInternal(ex, body, headers, status, exchange).map(entity -> {
            if (entity.getBody() instanceof ProblemDetail p && p.getInstance() == null) p.setInstance(instance(exchange));
            return entity;
        });
    }

    private static ProblemDetail problem(HttpStatus status, String detail, ServerWebExchange exchange) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setInstance(instance(exchange));
        return p;
    }

    private static URI instance(ServerWebExchange exchange) {
        return URI.create(exchange.getRequest().getPath().value());
    }
}
```

### Security (reactive resource server with issuer and audience validation)

```java
@Bean
ReactiveJwtDecoder jwtDecoder(JwtProperties properties) throws IOException {
    RSAPublicKey key;
    try (InputStream pem = properties.publicKeyLocation().getInputStream()) {
        key = RsaKeyConverters.x509().convert(pem);
    }
    NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder.withPublicKey(key)
        .signatureAlgorithm(SignatureAlgorithm.RS256).build();
    decoder.setJwtValidator(JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(properties.issuer()), new JwtAudienceValidator(properties.audience())));
    return decoder;
}

@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .authorizeExchange(x -> x
            .pathMatchers("/actuator/health", "/actuator/health/**").permitAll()
            .pathMatchers("/actuator/**").authenticated()
            .pathMatchers(HttpMethod.GET, "/orders", "/orders/**").hasAnyAuthority("SCOPE_orders:read", "SCOPE_orders:admin")
            .pathMatchers("/orders", "/orders/**").hasAnyAuthority("SCOPE_orders:write", "SCOPE_orders:admin")
            .anyExchange().denyAll())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}
```

### HTTP client: dedicated pool, timeouts, bounded retry

```java
@Configuration(proxyBeanMethods = false)
@EnableResilientMethods
@ImportHttpServices(group = "pricing", types = PricingClient.class, clientType = HttpServiceGroup.ClientType.WEB_CLIENT)
public class PricingConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider pricingConnectionProvider() {
        return ConnectionProvider.builder("pricing").maxConnections(50)
            .pendingAcquireTimeout(Duration.ofSeconds(2)).pendingAcquireMaxCount(200)
            .maxIdleTime(Duration.ofSeconds(30)).maxLifeTime(Duration.ofMinutes(5)).evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClientHttpServiceGroupConfigurer pricingGroupConfigurer(ConnectionProvider pool) {
        HttpClient http = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
            .responseTimeout(Duration.ofSeconds(2));
        return groups -> groups.filterByName("pricing")
            .forEachClient((group, builder) -> builder.clientConnector(new ReactorClientHttpConnector(http)));
    }
}

@Component
public class PricingGateway {
    private final PricingClient client;
    PricingGateway(PricingClient client) { this.client = client; }

    /** On a Mono method, @Retryable re-subscribes with backoff; timeout bounds all attempts together. */
    @Retryable(predicate = TransientPricingFailure.class, maxRetries = 2, delay = 100, jitter = 20,
               multiplier = 2, maxDelay = 1000, timeout = 5000)
    public Mono<PriceQuote> quote(String sku) {
        return client.price(sku).timeout(Duration.ofSeconds(1));     // per attempt
    }

    public static final class TransientPricingFailure implements MethodRetryPredicate {
        @Override
        public boolean shouldRetry(Method method, Throwable failure) {
            return failure instanceof TimeoutException
                || failure instanceof WebClientRequestException
                || (failure instanceof WebClientResponseException r && r.getStatusCode().is5xxServerError());
        }
    }
}
```

Bound concurrency with the connection pool (`maxConnections`, `pendingAcquireMaxCount`), not `@ConcurrencyLimit`: on a `Mono`-returning method its permit is released when the method returns the (unsubscribed) `Mono`, before any request is sent.

### Tests

```java
// BlockHound for the whole test JVM via blockhound-junit-platform; prove detection and the allowed offload
class BlockHoundTest {
    @Test
    void blockingCallOnParallelSchedulerIsDetected() {
        Mono<Long> blocking = Mono.delay(Duration.ofMillis(1)).doOnNext(t -> sleep(10));
        StepVerifier.create(blocking)
            .expectErrorSatisfies(e -> assertThat(e).isInstanceOf(BlockingOperationError.class))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void blockingOnBoundedElasticIsAllowed() {
        StepVerifier.create(Mono.fromCallable(() -> { sleep(10); return "done"; }).subscribeOn(Schedulers.boundedElastic()))
            .expectNext("done").verifyComplete();
    }
}

// SSE: receive own events only, then cancel and prove the subscriber is released
FluxExchangeResult<ServerSentEvent<OrderDto>> result = client.get().uri("/orders/stream")
    .headers(bearer(subject, "orders:read")).accept(MediaType.TEXT_EVENT_STREAM)
    .exchange().expectStatus().isOk()
    .returnResult(new ParameterizedTypeReference<ServerSentEvent<OrderDto>>() {});
StepVerifier.create(result.getResponseBody().filter(e -> e.data() != null))
    .then(() -> createOrder(subject, "SKU-A"))
    .assertNext(e -> assertThat(e.data().sku()).isEqualTo("SKU-A"))
    .thenCancel()
    .verify(Duration.ofSeconds(10));
```

Base class: `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `@Import(TestcontainersConfiguration.class)` + `@AutoConfigureWebTestClient`, `WebTestClient client`.
