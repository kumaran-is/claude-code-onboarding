# Spring Boot Design Patterns

Quick reference for the six design patterns used in Java 25 + Spring Boot 4.2 services.
The patterns apply to both stacks; the samples are written for WebFlux.

> **Stack:** the code samples here are **Spring WebFlux** (use it only when justified: `docs/adr/0001-java25-spring-boot-4-mvc-default.md`). Spring MVC, the default, is covered by the tested code in `spring-boot-templates.md` → Spring MVC.

---

## Builder

### When to Use
- Domain object or DTO has ≥ 4 fields, several optional
- Callers should not depend on constructor argument order
- Object must be immutable after construction

### Code Example

```java
// A record covers simple DTOs — use a manual builder when construction logic is needed
public final class OrderRequest {
    private final String customerId;   // required
    private final String productId;    // required
    private final int quantity;        // required
    private final String couponCode;   // optional
    private final String deliveryNote; // optional

    private OrderRequest(Builder b) {
        this.customerId   = b.customerId;
        this.productId    = b.productId;
        this.quantity     = b.quantity;
        this.couponCode   = b.couponCode;
        this.deliveryNote = b.deliveryNote;
    }

    public static Builder of(String customerId, String productId, int quantity) {
        return new Builder(customerId, productId, quantity);
    }

    public static final class Builder {
        private final String customerId;
        private final String productId;
        private final int    quantity;
        private String couponCode;
        private String deliveryNote;

        private Builder(String customerId, String productId, int quantity) {
            this.customerId = Objects.requireNonNull(customerId);
            this.productId  = Objects.requireNonNull(productId);
            this.quantity   = quantity;
        }

        public Builder couponCode(String couponCode) {
            this.couponCode = couponCode;
            return this;
        }

        public Builder deliveryNote(String note) {
            this.deliveryNote = note;
            return this;
        }

        public OrderRequest build() {
            if (quantity <= 0) throw new IllegalArgumentException("quantity must be > 0");
            return new OrderRequest(this);
        }
    }

    // accessors omitted for brevity
}

// Caller
var request = OrderRequest.of("cust-1", "prod-42", 3)
    .couponCode("SAVE10")
    .build();
```

### Anti-Pattern

```java
// ❌ Telescoping constructor — position-dependent, impossible to read at call site
public OrderRequest(String customerId, String productId, int qty,
                    String couponCode, String deliveryNote) { ... }

// Caller has to count positional args and pray the order hasn't changed
new OrderRequest("cust-1", "prod-42", 3, null, "Leave at door");
```

---

## Factory (Spring @Configuration / @Bean)

### When to Use
- Object type is determined by environment / configuration at startup
- Multiple implementations exist behind a common interface
- Callers should never `new` a dependency directly — let the IoC container provide it

### Code Example

```java
// Common interface
public interface StorageClient {
    Mono<String> upload(String key, byte[] bytes);
}

// Implementations
@Component("gcsStorage")
public class GcsStorageClient implements StorageClient { ... }

@Component("s3Storage")
public class S3StorageClient  implements StorageClient { ... }

// Factory via @Configuration — selects implementation based on environment property
@Configuration
public class StorageConfig {

    @Bean
    @ConditionalOnProperty(name = "storage.provider", havingValue = "gcs")
    public StorageClient gcsStorageClient(GcsProperties props) {
        return new GcsStorageClient(props);
    }

    @Bean
    @ConditionalOnProperty(name = "storage.provider", havingValue = "s3")
    public StorageClient s3StorageClient(S3Properties props) {
        return new S3StorageClient(props);
    }
}

// Service receives the correct implementation via injection — never calls new
@Service
@RequiredArgsConstructor
public class FileService {
    private final StorageClient storageClient; // injected by Spring

    public Mono<String> store(String key, byte[] data) {
        return storageClient.upload(key, data);
    }
}
```

### Anti-Pattern

```java
// ❌ Manual factory inside a service — bypasses IoC, untestable
@Service
public class FileService {
    public Mono<String> store(String key, byte[] data) {
        StorageClient client = System.getenv("STORAGE").equals("gcs")
            ? new GcsStorageClient()   // hard dependency, impossible to mock
            : new S3StorageClient();
        return client.upload(key, data);
    }
}
```

---

## Strategy (Spring @Component map injection)

### When to Use
- Multiple algorithms/behaviours for the same operation
- Algorithm must be selected at runtime from a stable set of implementations
- Adding a new variant should not require modifying existing code (Open/Closed)

### Code Example

```java
// Strategy interface
public interface NotificationSender {
    String channel(); // "EMAIL" | "SMS" | "PUSH"
    Mono<Void> send(String recipientId, String message);
}

// Implementations — each registers itself by returning its channel name
@Component
public class EmailSender implements NotificationSender {
    public String channel() { return "EMAIL"; }
    public Mono<Void> send(String recipientId, String message) { ... }
}

@Component
public class SmsSender implements NotificationSender {
    public String channel() { return "SMS"; }
    public Mono<Void> send(String recipientId, String message) { ... }
}

// Registry — Spring injects ALL NotificationSender beans; we index by channel()
@Service
@RequiredArgsConstructor
public class NotificationService {

    private final Map<String, NotificationSender> senders;

    // Spring constructor injection with List<NotificationSender>
    public NotificationService(List<NotificationSender> senderList) {
        this.senders = senderList.stream()
            .collect(Collectors.toUnmodifiableMap(
                NotificationSender::channel,
                Function.identity()
            ));
    }

    public Mono<Void> notify(String channel, String recipientId, String message) {
        var sender = Optional.ofNullable(senders.get(channel.toUpperCase()))
            .orElseThrow(() -> new IllegalArgumentException("Unknown channel: " + channel));
        return sender.send(recipientId, message);
    }
}
```

### Anti-Pattern

```java
// ❌ if/switch inside service — adding a new channel requires modifying this class
public Mono<Void> notify(String channel, String recipientId, String message) {
    return switch (channel) {
        case "EMAIL" -> new EmailSender().send(recipientId, message);
        case "SMS"   -> new SmsSender().send(recipientId, message);
        default      -> Mono.error(new IllegalArgumentException("Unknown: " + channel));
    };
}
```

---

## Observer (Spring ApplicationEventPublisher / @EventListener)

### When to Use
- A domain action should trigger side-effects in other modules without coupling them
- Side-effects are fire-and-forget or can be processed asynchronously
- Decoupling publisher from subscriber is architecturally required (e.g., domain vs. infra layer)

### Code Example

```java
// Event — a record is ideal: immutable, concise
public record OrderPlacedEvent(String orderId, String customerId, BigDecimal total) {}

// Publisher — domain service, knows nothing about listeners
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository       orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public Mono<Order> placeOrder(OrderRequest request) {
        return orderRepository.save(Order.from(request))
            .doOnNext(saved -> eventPublisher.publishEvent(
                new OrderPlacedEvent(saved.id(), saved.customerId(), saved.total())
            ));
    }
}

// Listener 1 — inventory module, synchronous
@Component
public class InventoryListener {
    private final InventoryService inventoryService;

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        inventoryService.reserve(event.orderId());
    }
}

// Listener 2 — email module, async (does not block the publisher's thread)
@Component
public class OrderConfirmationMailer {

    @EventListener
    @Async
    public void onOrderPlaced(OrderPlacedEvent event) {
        // send confirmation email — runs on a separate thread pool
    }
}
```

### Anti-Pattern

```java
// ❌ Direct service calls from OrderService — OrderService now depends on every side-effect
@Service
@RequiredArgsConstructor
public class OrderService {
    private final InventoryService      inventoryService;
    private final EmailService          emailService;
    private final AnalyticsService      analyticsService;   // keeps growing

    public Mono<Order> placeOrder(OrderRequest request) {
        return orderRepository.save(Order.from(request))
            .doOnNext(saved -> {
                inventoryService.reserve(saved.id());       // coupling
                emailService.sendConfirmation(saved);       // coupling
                analyticsService.track(saved);              // coupling
            });
    }
}
```

---

## Decorator (@Primary bean wrapping)

### When to Use
- Cross-cutting behaviour (caching, logging, metrics, retry) must be added to an existing bean
  without modifying its implementation
- The decoration must be transparent to callers — they depend on the interface, not the impl
- Only one additional behaviour needs wrapping; deeper chains → prefer AOP

### Code Example

```java
public interface ProductRepository extends ReactiveCrudRepository<Product, UUID> {
    Mono<Product> findBySku(String sku);
}

// Core implementation (existing)
@Repository
public class R2dbcProductRepository implements ProductRepository { ... }

// Caching decorator — wraps the real repo, adds Redis caching
@Primary   // ← Spring injects this wherever ProductRepository is requested
@Component
@RequiredArgsConstructor
public class CachingProductRepository implements ProductRepository {

    private final R2dbcProductRepository delegate;
    private final ReactiveRedisTemplate<String, Product> redis;

    @Override
    public Mono<Product> findBySku(String sku) {
        var key = "product:sku:" + sku;
        return redis.opsForValue().get(key)
            .switchIfEmpty(
                delegate.findBySku(sku)
                    .flatMap(p -> redis.opsForValue()
                        .set(key, p, Duration.ofMinutes(10))
                        .thenReturn(p))
            );
    }

    // Delegate all other methods to the real repo
    @Override
    public <S extends Product> Mono<S> save(S entity) { return delegate.save(entity); }
    // ... remaining ReactiveCrudRepository methods delegated
}
```

### Anti-Pattern

```java
// ❌ Caching logic inlined into the service — violates Single Responsibility
@Service
public class ProductService {
    public Mono<Product> getProduct(String sku) {
        return redis.opsForValue().get("product:sku:" + sku)
            .switchIfEmpty(
                productRepository.findBySku(sku)
                    .flatMap(p -> redis.opsForValue().set("product:sku:" + sku, p)
                        .thenReturn(p))
            );
        // Service now owns caching AND business logic AND must be changed if cache strategy changes
    }
}
```

---

## Adapter (External API integration)

### When to Use
- Integrating with a third-party or legacy API whose interface differs from the domain model
- The external API should be completely hidden behind a domain-facing interface
- Swapping the external provider (e.g., payment gateway) should not ripple through the codebase

### Code Example

```java
// Domain interface — expressed in terms of our domain, not the external API
public interface PaymentGateway {
    Mono<PaymentResult> charge(String customerId, Money amount, String currency);
}

// External SDK DTO (third-party, we do not own this)
record StripeChargeRequest(String customer, long amountCents, String currency) {}
record StripeChargeResponse(String id, String status) {}

// Adapter — translates between domain model and Stripe's API
@Component
@RequiredArgsConstructor
public class StripePaymentAdapter implements PaymentGateway {

    private final WebClient stripeClient;    // configured with base URL + auth header

    @Override
    public Mono<PaymentResult> charge(String customerId, Money amount, String currency) {
        var request = new StripeChargeRequest(
            customerId,
            amount.toCents(),
            currency.toLowerCase()
        );

        return stripeClient.post()
            .uri("/v1/charges")
            .bodyValue(request)
            .retrieve()
            .onStatus(HttpStatusCode::is4xxClientError,
                resp -> resp.bodyToMono(String.class)
                    .flatMap(body -> Mono.error(new PaymentDeclinedException(body))))
            .bodyToMono(StripeChargeResponse.class)
            .map(resp -> new PaymentResult(resp.id(), "succeeded".equals(resp.status())));
    }
}

// Service depends only on the domain interface — Stripe details are invisible
@Service
@RequiredArgsConstructor
public class CheckoutService {
    private final PaymentGateway paymentGateway;  // swap providers without touching this class

    public Mono<OrderConfirmation> checkout(Cart cart) {
        return paymentGateway.charge(cart.customerId(), cart.total(), "USD")
            .filter(PaymentResult::success)
            .switchIfEmpty(Mono.error(new PaymentDeclinedException("payment declined")))
            .map(result -> new OrderConfirmation(result.transactionId()));
    }
}
```

### Anti-Pattern

```java
// ❌ Stripe SDK calls scattered directly in the service — swap provider = rewrite service
@Service
public class CheckoutService {
    public Mono<OrderConfirmation> checkout(Cart cart) {
        // Stripe types leak into the domain layer
        var req = new StripeChargeRequest(cart.customerId(), cart.total().toCents(), "usd");
        return stripeClient.post().uri("/v1/charges").bodyValue(req)
            .retrieve().bodyToMono(StripeChargeResponse.class)
            .map(r -> new OrderConfirmation(r.id()));
    }
}
```
