# Spring Boot Caching — @Cacheable / @CacheEvict / Caffeine

Caching guide for Java 25 + Spring Boot 4.2. Uses Caffeine as the in-process cache (default for Spring Boot when `spring-boot-starter-cache` + `com.github.ben-manes.caffeine:caffeine` are on the classpath).

## Setup

### pom.xml dependencies

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
```

### Enable caching

```java
@SpringBootApplication
@EnableCaching
public class Application { ... }
```

### application.yml — Caffeine spec

```yaml
spring:
  cache:
    type: caffeine
    caffeine:
      spec: maximumSize=1000,expireAfterWrite=10m
    cache-names:
      - users
      - products
      - permissions
```

### Per-cache tuning (programmatic — overrides yml for fine control)

```java
@Configuration
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.registerCustomCache("users",
            Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(5, TimeUnit.MINUTES)
                .recordStats()
                .build());
        manager.registerCustomCache("permissions",
            Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterAccess(30, TimeUnit.MINUTES)
                .build());
        return manager;
    }
}
```

## Annotations

### @Cacheable — Cache a method's return value

```java
@Service
public class UserService {

    @Cacheable(value = "users", key = "#id")
    public Mono<UserResponse> findById(UUID id) {
        return userRepository.findById(id).map(userMapper::toResponse);
    }

    // Cache unless result is null
    @Cacheable(value = "users", key = "#email", unless = "#result == null")
    public Mono<UserResponse> findByEmail(String email) {
        return userRepository.findByEmail(email).map(userMapper::toResponse);
    }
}
```

### @CacheEvict — Remove entries on write/delete

```java
@CacheEvict(value = "users", key = "#id")
public Mono<UserResponse> updateUser(UUID id, UpdateUserRequest request) {
    return userRepository.findById(id)
        .flatMap(user -> userRepository.save(userMapper.update(user, request)))
        .map(userMapper::toResponse);
}

// Evict ALL entries in a cache (e.g., after bulk update)
@CacheEvict(value = "permissions", allEntries = true)
public Mono<Void> refreshPermissions() {
    return permissionRepository.reloadAll().then();
}
```

### @CachePut — Always update the cache (write-through)

```java
@CachePut(value = "users", key = "#result.id")
public Mono<UserResponse> createUser(CreateUserRequest request) {
    return userRepository.save(userMapper.toEntity(request))
        .map(userMapper::toResponse);
}
```

### @Caching — Combine multiple cache operations

```java
@Caching(evict = {
    @CacheEvict(value = "users", key = "#id"),
    @CacheEvict(value = "permissions", allEntries = true)
})
public Mono<Void> deleteUser(UUID id) {
    return userRepository.deleteById(id);
}
```

## WebFlux / Reactive Caching

Since Framework 6.1, `@Cacheable` on a method returning `Mono<T>` / `Flux<T>` caches the **emitted value** (`CacheAspectSupport$ReactiveCachingHandler`, present in spring-context 7.1), not the publisher, provided the cache supports async retrieval. The `CacheConfig` above is the Spring MVC (synchronous) setup; on WebFlux use an async-mode manager instead (custom caches then need `Caffeine...buildAsync()`):

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("users", "permissions");
    manager.setCaffeine(Caffeine.newBuilder().maximumSize(1_000).expireAfterWrite(Duration.ofMinutes(10)).recordStats());
    manager.setAsyncCacheMode(true);   // required for Mono/Flux return types (checked in spring-context-support 7.1.0)
    return manager;
}

@Cacheable("users")
public Mono<UserResponse> findById(UUID id) {          // the UserResponse is cached, the Mono is rebuilt per call
    return userRepository.findById(id).map(userMapper::toResponse);
}
```

Never call `.block()` inside a cached method to make it synchronous: on a Netty thread it throws `IllegalStateException`. A single process-wide value (reference data) can also be memoised with `Mono.cache(Duration)`.

## Eviction Strategies

| Strategy | Caffeine spec key | When to use |
|---|---|---|
| Time-to-live (TTL) | `expireAfterWrite=10m` | Reference data, permissions, config |
| Time-to-idle (TTI) | `expireAfterAccess=30m` | Session-like data accessed infrequently |
| Size-based LRU | `maximumSize=1000` | High-volume lookups with bounded memory |
| Reference-based | `softValues()` | Memory-sensitive caches (GC can evict) |

## Cache Statistics (Caffeine)

```java
// Enable in CacheManager config: .recordStats()
// Expose via actuator:
management:
  endpoint:
    caches:
      enabled: true
```

```bash
curl http://localhost:8080/actuator/caches        # list all caches
curl http://localhost:8080/actuator/caches/users  # stats for "users" cache
```

## Anti-Patterns

- **@Cacheable on void methods** — nothing to cache; use @CacheEvict instead
- **Caching mutable objects** — always cache immutable DTOs/records, never JPA entities
- **Missing cache eviction** — write operations MUST evict or update the cache
- **`@Cacheable` on `Mono`/`Flux` without `setAsyncCacheMode(true)`** — see WebFlux / Reactive Caching above
- **Large cache entries** — cache fine-grained values (by ID), not entire lists
