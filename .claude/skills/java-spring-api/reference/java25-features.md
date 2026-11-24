# Java 25 Features for Spring Services

Java 25 is the current LTS. Every feature in §1 compiled and ran with `javac --release 25` and no preview flag (Temurin 25, 2026-11-24). §2 features need `--enable-preview` on JDK 25 and are **optional experiments only**: never in production defaults, never in a scaffold.

## 1. Final features (use them)

| Feature | Use for |
|---|---|
| Records, record patterns | DTOs, value objects, deconstruction in `switch` |
| Sealed types + exhaustive pattern-matching `switch` | Closed error/result hierarchies mapped without a `default` branch |
| Unnamed variables and patterns (`_`) | `case NotFound _ ->`, ignored lambda parameters |
| Virtual threads | Blocking Spring MVC + JPA/JDBC at high concurrency (`spring.threads.virtual.enabled=true`) |
| `ScopedValue` | Immutable per-request values you own, inherited by child tasks; replaces `ThreadLocal` there |
| Flexible constructor bodies | Validate or compute arguments before `super(...)` / `this(...)` |
| Module import declarations (`import module java.base;`) | Scripts, tests, prototypes; prefer explicit imports in production code for readability |
| Compact source files + instance `main` (`void main() { IO.println(...); }`) | One-file tools and teaching; not application code |
| Sequenced collections (`getFirst()`, `getLast()`, `reversed()`) | Ordered collections without index arithmetic |
| Compact object headers (`-XX:+UseCompactObjectHeaders`, product flag) | Smaller heaps for object-heavy services; measure before adopting |

### Sealed errors with an exhaustive switch (from the MVC reference app)

```java
public abstract sealed class OrderException extends RuntimeException
        permits OrderException.NotFound, OrderException.VersionConflict, OrderException.PreconditionRequired {
    private OrderException(String message) { super(message); }
    public static final class NotFound extends OrderException { public NotFound(UUID id) { super("Order " + id + " not found"); } }
    public static final class VersionConflict extends OrderException { public VersionConflict(UUID id) { super("Order " + id + " was modified"); } }
    public static final class PreconditionRequired extends OrderException { public PreconditionRequired() { super("If-Match required"); } }
}

@ExceptionHandler(OrderException.class)
ProblemDetail handleOrder(OrderException ex, HttpServletRequest request) {
    return switch (ex) {                       // compiler error if a permitted subclass is missing
        case OrderException.NotFound _ -> problem(HttpStatus.NOT_FOUND, "Order not found", request);
        case OrderException.VersionConflict _ -> problem(HttpStatus.CONFLICT, "Version conflict", request);
        case OrderException.PreconditionRequired _ -> problem(HttpStatus.PRECONDITION_REQUIRED, "Precondition required", request);
    };
}
```

### ScopedValue

```java
static final ScopedValue<String> TENANT = ScopedValue.newInstance();

ScopedValue.where(TENANT, tenantId).run(() -> service.process(command)); // TENANT.get() inside, unbound outside
```

Spring Security and Micrometer still use their own context holders; do not replace those. In WebFlux use the Reactor `Context` instead.

### Flexible constructor body

```java
public final class Money extends Amount {
    public Money(BigDecimal value, Currency currency) {
        if (value.scale() > currency.getDefaultFractionDigits()) {   // runs before super(...)
            throw new IllegalArgumentException("too many decimals");
        }
        super(value);
        this.currency = currency;
    }
}
```

## 2. Preview features on JDK 25 (optional experiments)

| Feature | Status on JDK 25 | Why not in production |
|---|---|---|
| Structured concurrency (`StructuredTaskScope.open()`, joiners) | Preview (API changed again from JDK 21–24) | Preview APIs change between releases; code needs `--enable-preview` at compile and run time |
| Stable values (`StableValue`) | Preview | Same |
| Primitive types in patterns (`case int i when i > 0`) | Preview | Same |

String templates were withdrawn after JDK 22 and do not exist in JDK 25.

To experiment in a branch: add `--enable-preview` to the compiler arguments, to the surefire `argLine` and to the runtime `JAVA_TOOL_OPTIONS`; the classes then run only on JDK 25 exactly. For parallel calls in production today: virtual threads with an `ExecutorService` (`Executors.newVirtualThreadPerTaskExecutor()`) in MVC, `Mono.zip` in WebFlux.

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Price> price = executor.submit(() -> pricing.quote(sku));
    Future<Stock> stock = executor.submit(() -> inventory.stock(sku));
    return new Offer(price.get(2, TimeUnit.SECONDS), stock.get(2, TimeUnit.SECONDS));
}
```

## 3. Virtual threads in practice

- Enable with `spring.threads.virtual.enabled=true`; it covers Tomcat request threads, `@Async`, `@Scheduled` and `SimpleAsyncTaskExecutor` beans Boot creates.
- Virtual threads remove the thread-pool limit, not the downstream limits: the DB connection pool (HikariCP `maximum-pool-size`) and remote rate limits still cap throughput. Bulkhead slow dependencies with `@ConcurrencyLimit`.
- JDK 24+ no longer pins a virtual thread inside `synchronized`; native frames and some JNI calls still pin. Diagnose with JFR event `jdk.VirtualThreadPinned`.
- Do not pool virtual threads, and do not cache expensive objects in `ThreadLocal` per thread (millions of threads → millions of copies).

## 4. JVM settings for containers

| Setting | Recommendation |
|---|---|
| Heap | `-XX:MaxRAMPercentage=75` (container-aware); never a fixed `-Xmx` copied between environments |
| GC | G1 (default) for most services; Generational ZGC (`-XX:+UseZGC`) when p99 pause time matters and memory headroom exists |
| OOM | `-XX:+ExitOnOutOfMemoryError` so the orchestrator restarts the container |
| Object headers | `-XX:+UseCompactObjectHeaders`: test with your workload, keep it if heap and latency improve |
| Startup | Class Data Sharing / AOT cache and Spring AOT shorten startup; measure first-request latency before and after |

Set them in `JAVA_TOOL_OPTIONS` in the image (see `spring-boot-config.md` Dockerfile).

## 5. GraalVM native image (DEFER by default)

Boot 4 supports GraalVM 25 native images (`./mvnw -Pnative native:compile` with the Boot parent's `native` profile; native-build-tools 1.1.18 is managed). Benefits: ~10× faster startup and lower memory. Costs: long builds, reflection/proxy hints for libraries Spring does not cover, no runtime agents, different performance profile. Adopt per service only after a measured need (scale-to-zero cold starts) and with the full test suite run against the native binary (`./mvnw -PnativeTest test`).

## 6. Spring Modulith 2.2 — modular monolith

For a service with several bounded contexts that do not yet justify separate deployments.

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.modulith</groupId>
      <artifactId>spring-modulith-bom</artifactId>
      <version>2.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
<!-- dependencies: spring-modulith-starter-core; test: spring-modulith-starter-test -->
```

- Each direct sub-package of the application package is a module (`orders/`, `payments/`); its sub-packages (`orders/internal/`) are hidden from other modules.
- Modules talk through events, not each other's services:

```java
// orders module
@Transactional
public Order place(PlaceOrder command) {
    Order order = orders.save(Order.from(command));
    events.publishEvent(new OrderPlaced(order.getId(), order.getTotal())); // ApplicationEventPublisher
    return order;
}

// payments module: runs after the orders transaction commits, in its own transaction, asynchronously
@ApplicationModuleListener
void on(OrderPlaced event) { payments.charge(event.orderId(), event.total()); }
```

- With `spring-modulith-starter-jpa` (or `-jdbc`) the event publication registry stores events in the same transaction and retries incomplete ones: a transactional outbox without a broker.
- Boundary test, run in CI:

```java
class ModularityTests {
    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(OrdersApplication.class).verify();
    }
}
```

## 7. Micro-benchmarks (JMH)

Benchmark only a profiled hot spot, in a separate Maven module with `org.openjdk.jmh:jmh-core` and the annotation processor, `@Fork(2)`, `@Warmup` and `@Measurement` set explicitly, results compared before and after on the same machine. Never benchmark inside `@SpringBootTest`.
