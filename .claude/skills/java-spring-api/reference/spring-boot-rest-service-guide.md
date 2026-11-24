# REST Service Implementation Guide

Step-by-step guide for implementing a REST service from OpenAPI spec + SQL DDL in Spring Boot 4.2 (WebFlux examples; the MVC equivalents are in `spring-boot-templates.md`).

## Workflow

1. **Gather inputs**: OpenAPI 3.x JSON/YAML + SQL DDL file
2. **Analyze**: Infer entities, relationships, endpoints, and DTOs from the specs
3. **Generate layers**: Controller → Service → Repository → Entity → DTO → Mapper
4. **Add integrations**: External service clients with resilience patterns
5. **Write tests**: Unit, integration, and contract tests
6. **Configure**: application.yml, security, and documentation

## OpenAPI-Driven Development

When given an OpenAPI spec and DDL:

1. Parse the OpenAPI spec to extract:
   - Endpoint paths and HTTP methods
   - Request/response schemas → DTO records
   - Validation constraints → `jakarta.validation` annotations
   - Error responses → exception mappings

2. Parse the DDL to extract:
   - Table definitions → R2DBC entity classes
   - Column types and constraints → Java types and annotations
   - Foreign keys → repository query methods
   - Indexes → custom `@Query` methods

3. Cross-reference both to ensure alignment between API contract and data model.

## MapStruct DTO-Entity Mapping

### Maven Setup

```xml
<properties>
    <mapstruct.version>1.6.3</mapstruct.version>
</properties>

<dependency>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct</artifactId>
    <version>${mapstruct.version}</version>
</dependency>

<!-- In maven-compiler-plugin annotationProcessorPaths -->
<path>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct-processor</artifactId>
    <version>${mapstruct.version}</version>
</path>
```

### Mapper Interface

```java
@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.IGNORE)
public interface OrderMapper {

    OrderResponse toResponse(OrderEntity entity);

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "createdAt", ignore = true)
    @Mapping(target = "updatedAt", ignore = true)
    OrderEntity toEntity(CreateOrderRequest request);

    default List<OrderResponse> toResponseList(List<OrderEntity> entities) {
        return entities.stream().map(this::toResponse).toList();
    }
}
```

### Usage in Service

```java
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepository;
    private final OrderMapper orderMapper;

    public Mono<OrderResponse> create(CreateOrderRequest request) {
        OrderEntity entity = orderMapper.toEntity(request);
        entity.setCreatedAt(Instant.now());
        entity.setUpdatedAt(Instant.now());
        return orderRepository.save(entity)
                .map(orderMapper::toResponse);
    }

    public Mono<OrderResponse> findById(UUID id) {
        return orderRepository.findById(id)
                .map(orderMapper::toResponse)
                .switchIfEmpty(Mono.error(new ResourceNotFoundException("Order not found: " + id)));
    }
}
```

## External Service Integration

### Client Pattern

```java
@Service
public class PaymentServiceClient {

    private final WebClient.Builder webClientBuilder;
    private final PaymentServiceProperties config;

    private final CircuitBreaker circuitBreaker;
    private final Retry retry;
    private final TimeLimiter timeLimiter;

    public PaymentServiceClient(WebClient.Builder webClientBuilder,
                                PaymentServiceProperties config,
                                CircuitBreakerRegistry cbRegistry,
                                RetryRegistry retryRegistry,
                                TimeLimiterRegistry tlRegistry) {
        this.webClientBuilder = webClientBuilder;
        this.config = config;
        this.circuitBreaker = cbRegistry.circuitBreaker("paymentService");
        this.retry = retryRegistry.retry("paymentService");
        this.timeLimiter = tlRegistry.timeLimiter("paymentService");
    }

    // A payment POST is NOT idempotent: it is retried only because the provider deduplicates on the
    // Idempotency-Key, generated once per business operation (the caller passes it in, never per attempt).
    // Without such a key, remove the RetryOperator: a timeout after the charge would charge twice.
    public Mono<PaymentResponse> processPayment(PaymentRequest request, String idempotencyKey) {
        return webClientBuilder.build()
            .post()
            .uri(config.baseUrl() + "/api/v1/payments")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + config.apiKey())
            .header("Idempotency-Key", idempotencyKey)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            // Never copy the upstream body into an exception message: the error advice could return it
            .onStatus(HttpStatusCode::is4xxClientError, response ->
                Mono.error(new InvalidInputException("Payment rejected by the provider")))
            .onStatus(HttpStatusCode::is5xxServerError, response ->
                Mono.error(new ServiceIntegrationException("Payment service unavailable", null)))
            .bodyToMono(PaymentResponse.class)
            // transformDeferred: the operator applied LAST is the OUTERMOST. Resilience4j's order is
            // Retry(CircuitBreaker(TimeLimiter(call))): a time limit per attempt, every attempt counted by the
            // breaker; the retry config does not retry CallNotPermittedException (open circuit).
            .transformDeferred(TimeLimiterOperator.of(timeLimiter))
            .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
            .transformDeferred(RetryOperator.of(retry))
            .onErrorResume(CallNotPermittedException.class, ex ->
                Mono.error(new ServiceIntegrationException(
                    HttpStatus.SERVICE_UNAVAILABLE, "PAYMENT_UNAVAILABLE",
                    "Payment service circuit breaker is open", ex)));
    }
}
```

### Type-Safe Configuration

```java
@ConfigurationProperties(prefix = "integration.payment-service")
public record PaymentServiceProperties(
    @NotBlank String baseUrl,
    @NotBlank String apiKey,
    @Min(100) int timeoutMs
) {}
```

```yaml
integration:
  payment-service:
    base-url: ${PAYMENT_SERVICE_URL}
    api-key: ${PAYMENT_SERVICE_API_KEY}
    timeout-ms: 5000
```

### Resilience4j Instance Config

```yaml
resilience4j:
  circuitbreaker:
    instances:
      paymentService:
        base-config: default
        failure-rate-threshold: 60
  retry:
    instances:
      paymentService:
        base-config: default
        max-attempts: 2              # safe only with the Idempotency-Key above
  timelimiter:
    instances:
      paymentService:
        base-config: default
        timeout-duration: 5s
```

## Direct-to-Storage Uploads (Presigned URL)

Large files go browser → Cloud Storage on a 15-minute V4 signed PUT URL; the API issues the URL and
confirms the result. Same contract as FastAPI (`python-dev/reference/fastapi-auth-security.md` §12,
which also covers keyless signing) and NestJS (`nestjs-api/reference/nestjs-rest-upload-errors.md`);
bucket CORS and IAM: `gcp-cloud-run/SKILL.md`. The storage client blocks, so every call runs on
`Schedulers.boundedElastic()`. On Cloud Run the default credentials sign through IAM `signBlob`: the
runtime service account needs `roles/iam.serviceAccountTokenCreator` on itself.

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
    <version>2.69.0</version> <!-- or manage it with com.google.cloud:libraries-bom -->
</dependency>
```

```java
public record PresignedUrlRequest(@NotBlank String contentType, @Min(1) @Max(104_857_600) long size) {}
public record PresignedUrlResponse(String uploadUrl, String objectKey, Instant expiresAt) {}
public record ConfirmUploadRequest(@NotBlank @Size(max = 200) String objectKey) {}
```

```java
import jakarta.validation.Valid;
import java.security.Principal;

@RestController
@RequestMapping("/api/v1/upload")
@RequiredArgsConstructor
public class UploadController {
    private final UploadService uploadService;

    @PostMapping("/presigned-url")
    public Mono<PresignedUrlResponse> presignedUrl(Principal principal,
                                                   @RequestBody @Valid PresignedUrlRequest request) {
        return uploadService.createPresignedUrl(principal.getName(), request);
    }

    @PostMapping("/confirm")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> confirm(Principal principal, @RequestBody @Valid ConfirmUploadRequest request) {
        return uploadService.confirmUpload(principal.getName(), request.objectKey());
    }
}
```

```java
@Service
@Slf4j
public class UploadService {
    private static final Map<String, String> ALLOWED_TYPES = Map.of(
        "image/jpeg", ".jpg", "image/png", ".png", "image/webp", ".webp", "application/pdf", ".pdf");
    private static final long MAX_BYTES = 100L * 1024 * 1024;
    private static final Duration URL_TTL = Duration.ofMinutes(15);

    private final Storage storage;       // one StorageOptions.getDefaultInstance().getService() bean
    private final String bucket;

    public UploadService(Storage storage, @Value("${upload.gcs-bucket}") String bucket) {
        this.storage = storage;
        this.bucket = bucket;
    }

    public Mono<PresignedUrlResponse> createPresignedUrl(String ownerId, PresignedUrlRequest request) {
        String suffix = ALLOWED_TYPES.get(request.contentType());
        if (suffix == null) {
            return Mono.error(new InvalidInputException("Content type not allowed"));
        }
        // Server-chosen key under the owner's directory: the client filename never reaches the key
        String objectKey = "uploads/" + ownerId + "/" + UUID.randomUUID() + suffix;
        return Mono.fromCallable(() -> {
            BlobInfo info = BlobInfo.newBuilder(BlobId.of(bucket, objectKey))
                .setContentType(request.contentType()).build();
            URL url = storage.signUrl(info, URL_TTL.toSeconds(), TimeUnit.SECONDS,
                Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
                Storage.SignUrlOption.withV4Signature(),
                Storage.SignUrlOption.withExtHeaders(Map.of("Content-Type", request.contentType())));
            log.info("upload_url_issued objectKey={}", objectKey); // never log the URL: it is a credential
            return new PresignedUrlResponse(url.toString(), objectKey, Instant.now().plus(URL_TTL));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    public Mono<Void> confirmUpload(String ownerId, String objectKey) {
        int slash = objectKey.lastIndexOf('/');
        // Exact owner-directory match; a foreign key gets the same 404 as a missing one
        if (slash < 0 || !objectKey.substring(0, slash).equals("uploads/" + ownerId)) {
            return Mono.error(new ResourceNotFoundException("Upload not found"));
        }
        return Mono.fromCallable(() -> Optional.ofNullable(storage.get(BlobId.of(bucket, objectKey))))
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(found -> found.map(Mono::just)
                .orElseGet(() -> Mono.error(new ResourceNotFoundException("Upload not found"))))
            .flatMap(blob -> {
                Long size = blob.getSize();
                // The signature fixes the content type, not the size: enforce both after the fact
                if (size == null || size > MAX_BYTES || !ALLOWED_TYPES.containsKey(blob.getContentType())) {
                    log.warn("upload_rejected objectKey={} size={}", objectKey, size);
                    return Mono.fromCallable(blob::delete)
                        .subscribeOn(Schedulers.boundedElastic())
                        .then(Mono.error(new InvalidInputException("Upload rejected")));
                }
                log.info("upload_confirmed objectKey={} size={}", objectKey, size);
                return Mono.empty(); // persist objectKey + owner here; scan content asynchronously
            })
            .then();
    }
}
```

`StorageException` from the client propagates to the global error handler, which logs it and answers
5xx. In a multi-tenant service add the tenant to the key and to the ownership check.

## Testing Patterns

### Controller Test (WebFluxTest)

```java
@WebFluxTest(OrderController.class)
@Import(SecurityConfig.class)
class OrderControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockitoBean
    private OrderService orderService;

    @Test
    @WithMockUser
    void createOrder_shouldReturn201() {
        var request = new CreateOrderRequest("item-1", 2, BigDecimal.valueOf(29.99));
        var response = new OrderResponse(UUID.randomUUID(), "item-1", 2, BigDecimal.valueOf(29.99), Instant.now());

        when(orderService.create(any())).thenReturn(Mono.just(response));

        webTestClient.post().uri("/api/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.itemId").isEqualTo("item-1")
            .jsonPath("$.quantity").isEqualTo(2);
    }

    @Test
    @WithMockUser
    void getOrder_notFound_shouldReturn404() {
        UUID id = UUID.randomUUID();
        when(orderService.findById(id)).thenReturn(Mono.error(new ResourceNotFoundException("Order not found")));

        webTestClient.get().uri("/api/v1/orders/{id}", id)
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

### Service Unit Test (StepVerifier)

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock private OrderRepository orderRepository;
    @Mock private OrderMapper orderMapper;
    @InjectMocks private OrderService orderService;

    @Test
    void findById_existingOrder_shouldReturnResponse() {
        UUID id = UUID.randomUUID();
        var entity = new OrderEntity();
        entity.setId(id);
        var response = new OrderResponse(id, "item-1", 2, BigDecimal.valueOf(29.99), Instant.now());

        when(orderRepository.findById(id)).thenReturn(Mono.just(entity));
        when(orderMapper.toResponse(entity)).thenReturn(response);

        StepVerifier.create(orderService.findById(id))
            .expectNext(response)
            .verifyComplete();
    }

    @Test
    void findById_missingOrder_shouldReturnNotFound() {
        UUID id = UUID.randomUUID();
        when(orderRepository.findById(id)).thenReturn(Mono.empty());

        StepVerifier.create(orderService.findById(id))
            .expectError(ResourceNotFoundException.class)
            .verify();
    }
}
```

### WireMock Integration Test (External Services)

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PaymentIntegrationTest {

    @Autowired private WebTestClient webTestClient;

    private static WireMockServer wireMock;

    @BeforeAll
    static void startWireMock() {
        wireMock = new WireMockServer(WireMockConfiguration.wireMockConfig().dynamicPort());
        wireMock.start();
    }

    @AfterAll
    static void stopWireMock() {
        wireMock.stop();
    }

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("integration.payment-service.base-url", wireMock::baseUrl);
    }

    @Test
    @WithMockUser
    void processPayment_success() {
        wireMock.stubFor(post(urlEqualTo("/api/v1/payments"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"transactionId": "txn-123", "status": "APPROVED"}
                    """)));

        webTestClient.post().uri("/api/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("item-1", 1, BigDecimal.TEN))
            .exchange()
            .expectStatus().isCreated();
    }

    @Test
    @WithMockUser
    void processPayment_serviceDown_shouldReturn503() {
        wireMock.stubFor(post(urlEqualTo("/api/v1/payments"))
            .willReturn(aResponse().withStatus(500)));

        webTestClient.post().uri("/api/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("item-1", 1, BigDecimal.TEN))
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
```

### Maven Test Dependencies

```xml
<dependency>
    <groupId>org.wiremock</groupId>
    <artifactId>wiremock-standalone</artifactId>
    <version>3.10.0</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

## Implementation Checklist

- [ ] All endpoints match OpenAPI spec (paths, methods, status codes)
- [ ] Entities match DDL (column names, types, constraints)
- [ ] DTOs use Java records with `jakarta.validation` annotations
- [ ] MapStruct mappers for all DTO-entity conversions
- [ ] Spring MVC (default): services return values in `@Transactional` methods with no remote call inside; WebFlux: services return `Mono`/`Flux`, no `.block()`
- [ ] External clients: `@HttpExchange` or `RestClient` + Framework `@Retryable` (MVC); `WebClient` + `Retry.backoff` or Resilience4j operators (WebFlux)
- [ ] Retries only on idempotent calls, or with an idempotency key the provider honours
- [ ] Circuit-breaker fallbacks surface an error state (503 `ProblemDetail`), never fake data
- [ ] MVC: `@WebMvcTest` + `MockMvcTester` / `RestTestClient`; WebFlux: `@WebFluxTest` + `WebTestClient`, `StepVerifier` for services
- [ ] WireMock tests for external service integrations
- [ ] Configuration externalized via `@ConfigurationProperties`
