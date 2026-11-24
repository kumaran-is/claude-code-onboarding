# Java Coding Standards - Code Examples

## Naming
```java
// Classes/Records: PascalCase
public class MarketService {}
public record Money(BigDecimal amount, Currency currency) {}

// Methods/fields: camelCase
private final MarketRepository marketRepository;
public Market findBySlug(String slug) {}

// Constants: UPPER_SNAKE_CASE
private static final int MAX_PAGE_SIZE = 100;
```

## Immutability
```java
// Favor records and final fields
public record MarketDto(Long id, String name, MarketStatus status) {}

public class Market {
  private final Long id;
  private final String name;
  // getters only, no setters
}

// Exception: R2DBC entities require setters for framework binding
@Table("orders")
public class OrderEntity {
  @Id private UUID id;
  private String name;
  // getters AND setters needed for R2DBC
}
```

## Optional Usage
```java
// Return Optional from find* methods (blocking code)
Optional<Market> market = marketRepository.findBySlug(slug);

// Map/flatMap instead of get()
return market
    .map(MarketResponse::from)
    .orElseThrow(() -> new EntityNotFoundException("Market not found"));

// In reactive code, Mono<T> replaces Optional<T>
return marketRepository.findBySlug(slug)
    .map(MarketResponse::from)
    .switchIfEmpty(Mono.error(new EntityNotFoundException("Market not found")));
```

## Streams Best Practices
```java
// Use streams for transformations, keep pipelines short
List<String> names = markets.stream()
    .map(Market::name)
    .filter(Objects::nonNull)
    .toList();

// Avoid complex nested streams; prefer loops for clarity
```

## Exception Handling
```java
throw new MarketNotFoundException(slug);
```

- Use unchecked exceptions for domain errors; wrap technical exceptions with context
- Create domain-specific exceptions (e.g., `MarketNotFoundException`)
- Avoid broad `catch (Exception ex)` unless rethrowing/logging centrally

## Generics and Type Safety
```java
public <T extends Identifiable> Map<Long, T> indexById(Collection<T> items) { ... }
```

- Avoid raw types; declare generic parameters
- Prefer bounded generics for reusable utilities

## Logging
```java
private static final Logger log = LoggerFactory.getLogger(MarketService.class);
log.info("fetch_market slug={}", slug);
log.error("failed_fetch_market slug={}", slug, ex);
```

## Project Structure (Maven/Gradle)
```
src/main/java/com/company/<service>/
  config/
  controller/
  service/
  repository/
  model/
    entity/
    dto/
  exception/
src/main/resources/
  application.yml
src/test/java/... (mirrors main)
```

## Formatting and Style

- Use 2 or 4 spaces consistently (project standard)
- One public top-level type per file
- Keep methods short and focused; extract helpers
- Order members: constants, fields, constructors, public methods, protected, private

## Code Smells to Avoid

- Long parameter lists -> use DTO/builders
- Deep nesting -> early returns
- Magic numbers -> named constants
- Static mutable state -> prefer dependency injection
- Silent catch blocks -> log and act or rethrow

## Null Handling

- Accept `@Nullable` only when unavoidable; otherwise use `@NonNull`
- Use Bean Validation (`@NotNull`, `@NotBlank`) on inputs

## Testing Expectations

- JUnit 6 (Jupiter API) + AssertJ for fluent assertions
- Mockito for mocking; avoid partial mocks where possible
- `RestTestClient` (`@AutoConfigureRestTestClient`) for MVC endpoint integration tests; `WebTestClient` (`@AutoConfigureWebTestClient`) for WebFlux
- Favor deterministic tests; no hidden sleeps
