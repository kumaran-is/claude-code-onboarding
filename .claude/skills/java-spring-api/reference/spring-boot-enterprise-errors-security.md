# Spring Boot Enterprise Patterns — Error Handling & Security

Error handling and security rules for Java 25 + Spring Boot 4.2, Spring MVC (default) and WebFlux. The tested code for both stacks is in `spring-boot-templates.md`; this file states the rules and the traps.

## Exception Hierarchy

New services prefer the **sealed** domain exceptions in `spring-boot-templates.md` (exhaustive `switch` in the advice). The open hierarchy below suits a codebase that already has one.

### Base Exception

```java
package com.company.service.exception;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;

public abstract class ApplicationException extends RuntimeException {

    private final HttpStatus httpStatus;
    private final String errorCode;
    private final List<String> errors;
    private final Map<String, Object> details;

    protected ApplicationException(HttpStatus httpStatus, String errorCode, String message) {
        this(httpStatus, errorCode, message, null, List.of(), Map.of());
    }

    protected ApplicationException(HttpStatus httpStatus, String errorCode, String message, Throwable cause) {
        this(httpStatus, errorCode, message, cause, List.of(), Map.of());
    }

    protected ApplicationException(HttpStatus httpStatus, String errorCode, String message, List<String> errors) {
        this(httpStatus, errorCode, message, null, errors, Map.of());
    }

    protected ApplicationException(HttpStatus httpStatus, String errorCode, String message,
                                   Throwable cause, List<String> errors, Map<String, Object> details) {
        super(message, cause);
        this.httpStatus = httpStatus;
        this.errorCode = errorCode;
        this.errors = errors != null ? Collections.unmodifiableList(errors) : List.of();
        this.details = details != null ? Collections.unmodifiableMap(details) : Map.of();
    }

    public HttpStatus getHttpStatus() { return httpStatus; }
    public String getErrorCode() { return errorCode; }
    public List<String> getErrors() { return errors; }
    public Map<String, Object> getDetails() { return details; }
}
```

### Concrete Exceptions

```java
// 400 Bad Request — validation failures
public class InvalidInputException extends ApplicationException {
    public InvalidInputException(String message) {
        super(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message);
    }
    public InvalidInputException(String message, List<String> errors) {
        super(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message, errors);
    }
}

// 404 Not Found
public class ResourceNotFoundException extends ApplicationException {
    public ResourceNotFoundException(String message) {
        super(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", message);
    }
}

// 409 Conflict — business rule violations
public class BusinessRuleException extends ApplicationException {
    public BusinessRuleException(String message) {
        super(HttpStatus.CONFLICT, "BUSINESS_RULE_VIOLATION", message);
    }
    public BusinessRuleException(HttpStatus status, String errorCode, String message) {
        super(status, errorCode, message);
    }
}

// 500/502/503 — external service failures
public class ServiceIntegrationException extends ApplicationException {
    public ServiceIntegrationException(String message, Throwable cause) {
        super(HttpStatus.INTERNAL_SERVER_ERROR, "INTEGRATION_ERROR", message, cause);
    }
    public ServiceIntegrationException(HttpStatus status, String errorCode, String message, Throwable cause) {
        super(status, errorCode, message, cause);
    }
}
```

### Global error handling: `ProblemDetail` on both stacks

Use the `ProblemDetailsAdvice` from `spring-boot-templates.md` (one per stack: Spring MVC → ProblemDetail advice, Spring WebFlux → ProblemDetail advice): it extends `ResponseEntityExceptionHandler` (MVC: `org.springframework.web.servlet.mvc.method.annotation`; WebFlux: `org.springframework.web.reactive.result.method.annotation`).

- Every error is `application/problem+json`; set `instance` from the request path (Framework 7.1 no longer does).
- Never return exception messages, upstream bodies or rejected values: validation errors list the field and a generic message; a test asserts that an injected `<script>` marker is absent from the 400 body.
- The catch-all handler logs at ERROR with a correlation id and returns a generic 500.
- Do not register an `AbstractErrorWebExceptionHandler` for API errors on WebFlux: it bypasses the controller advice and does not produce `ProblemDetail`.

## Security configuration

Both stacks: `SecurityFilterChain` (MVC) and `SecurityWebFilterChain` (WebFlux) in `spring-boot-templates.md`, tested with real RS256 tokens.

### Actuator exposure

```properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.show-details=never
management.endpoint.health.probes.enabled=true
```

```java
// MVC: org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest
.requestMatchers(EndpointRequest.to("health", "info")).permitAll()
.requestMatchers(EndpointRequest.to("prometheus")).hasAuthority("SCOPE_metrics:read")
.requestMatchers(EndpointRequest.toAnyEndpoint()).denyAll()
// WebFlux: ...actuate.web.reactive.EndpointRequest with .pathMatchers/.matchers(...) in authorizeExchange
```

Never `permitAll()` the actuator base path: a public `loggers` endpoint lets anyone switch logging to TRACE (and leak tokens), and `env`/`heapdump` leak secrets. `metrics` and `loggers` are not exposed in production.

### Tokens and authorization

- Signature, expiry, **issuer and audience** are always validated (`spring-boot-templates.md` → Security; never `issuer-uri` next to `public-key-location`).
- Authorize with the token's scopes (`hasAuthority("SCOPE_orders:write")`); end with `anyRequest().denyAll()` / `anyExchange().denyAll()`.
- OpenAPI and Swagger UI are disabled in production (`springdoc.api-docs.enabled=false`, `springdoc.swagger-ui.enabled=false`) or require authentication.

### Ownership checks

Enforce ownership in the service query (`findByIdAndCustomerId(...)` → 404 for another customer's record, an admin scope may read all). Both reference apps test this. On WebFlux never call `.block()` in a security bean or `@PreAuthorize` expression: on a Netty thread Reactor throws `IllegalStateException` and every request fails.

### CORS

Only for browser clients on another origin. Bind the origins from configuration (register the record with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(CorsProperties.class)`) and expose one `CorsConfigurationSource` bean; `http.cors(Customizer.withDefaults())` picks it up.

```java
@ConfigurationProperties("app.cors")
public record CorsProperties(List<String> allowedOrigins) {}

@Bean
CorsConfigurationSource corsConfigurationSource(CorsProperties cors) {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(cors.allowedOrigins());          // exact origins, never "*"
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "If-Match"));
    config.setExposedHeaders(List.of("Location", "ETag"));
    config.setMaxAge(3600L);
    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

MVC: `org.springframework.web.cors.UrlBasedCorsConfigurationSource`; WebFlux: `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` (same constructor and method). Bearer-token APIs do not need `allowCredentials(true)`: leave it off.
