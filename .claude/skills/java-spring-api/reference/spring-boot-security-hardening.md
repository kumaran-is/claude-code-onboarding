# Security Hardening for Spring Boot (MVC and WebFlux)

Security scanning, static analysis patterns, and remediation for Java 25 + Spring Boot 4.2 services.

## OWASP Dependency Scanning

Run the OWASP Dependency-Check Maven plugin to scan for known CVEs in dependencies:

```bash
# Full scan — generates HTML report at target/dependency-check-report.html
mvn org.owasp:dependency-check-maven:check

# Fail build on High/Critical CVEs (CI/CD integration)
mvn org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=7
```

### Maven Plugin Configuration

```xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>10.0.3</version>
    <configuration>
        <failBuildOnCVSS>7</failBuildOnCVSS>
        <suppressionFiles>
            <suppressionFile>dependency-check-suppressions.xml</suppressionFile>
        </suppressionFiles>
    </configuration>
</plugin>
```

Create `dependency-check-suppressions.xml` for false positives with documented justification for each entry.

## Static Analysis — Build-Time Quality Gates

Add these plugins to `pom.xml` under `<build><plugins>`. They run during `mvn verify`.

```xml
<!-- SpotBugs — bytecode bug detection -->
<plugin>
    <groupId>com.github.spotbugs</groupId>
    <artifactId>spotbugs-maven-plugin</artifactId>
    <version>4.8.6.4</version>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- PMD — code style and bad practices -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-pmd-plugin</artifactId>
    <version>3.24.0</version>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- Checkstyle — formatting and naming conventions -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.4.0</version>
    <configuration>
        <configLocation>google_checks.xml</configLocation>
        <failsOnError>true</failsOnError>
    </configuration>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- Spotless — auto-format Java source -->
<plugin>
    <groupId>com.diffplug.spotless</groupId>
    <artifactId>spotless-maven-plugin</artifactId>
    <version>2.43.0</version>
    <configuration>
        <java>
            <googleJavaFormat>
                <version>1.22.0</version>
                <style>AOSP</style>
            </googleJavaFormat>
        </java>
    </configuration>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>
```

**Run individually:**
```bash
mvn spotbugs:check          # Bug detection
mvn pmd:check               # Code style
mvn checkstyle:check        # Formatting
mvn spotless:check          # Auto-format check
mvn spotless:apply          # Auto-apply formatting
```

**CI gate:** Add `mvn verify` to your pipeline — all four plugins run at the `verify` phase.

## Static Analysis Patterns

Grep patterns to identify common security issues in a Spring Boot codebase. Use these during code review or as pre-commit checks.

### CORS & CSRF

```bash
# Overly permissive CORS (wildcard in non-dev config)
grep -rn 'allowed-origins.*\*' src/main/resources/application-prod.yml
grep -rn 'allowedOrigins.*\*' src/main/java/

# CSRF disabled without justification (expected in stateless APIs, flag if session-based)
grep -rn 'csrf.*disable' src/main/java/

# H2 console enabled in non-dev config (should never be enabled in production)
grep -rn 'h2.*console.*enabled.*true' src/main/resources/application-prod.yml
```

### Secrets & Credentials

```bash
# Hardcoded passwords or tokens
grep -rn 'password\s*=\s*"[^$]' src/main/
grep -rn 'apiKey\s*=\s*"' src/main/
grep -rn 'secret\s*=\s*"' src/main/

# Database URLs with embedded credentials
grep -rn 'r2dbc://.*:.*@' src/main/resources/
```

### Authentication & Authorization

```bash
# Controllers missing security annotations
grep -rn '@RestController\|@Controller' src/main/java/ | grep -v '@PreAuthorize\|@Secured'

# JWT implementation patterns
grep -rn 'JWT\|jwt\|Bearer' src/main/java/
```

### Input Validation

```bash
# Request handlers without validation
grep -rn '@RequestBody' src/main/java/ | grep -v '@Valid'

# Input entry points — verify each has validation annotations
grep -rn '@RequestParam\|@PathVariable' src/main/java/

# Potential SQL injection (string concatenation in queries)
grep -rn 'query.*+\s*\|sql.*+\s*' src/main/java/
```

### Logging Security

```bash
# Sensitive data in log statements
grep -rn 'log\.\(info\|debug\|error\|warn\).*\(password\|token\|secret\|ssn\|credit\)' src/main/java/
```

### Actuator Exposure

```bash
# Overly exposed actuator endpoints
grep -rn 'exposure.*include.*\*' src/main/resources/
```

## Security Headers — HSTS

Spring Security already sends `Strict-Transport-Security` (one year, `includeSubDomains`), `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` on HTTPS responses on both stacks. Configure them only to change the values; the method names differ per stack (Security 7.2, checked with `javap`):

```java
// Spring MVC: HttpSecurity
http.headers(headers -> headers
    .frameOptions(frame -> frame.deny())
    .contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'none'; frame-ancestors 'none'"))
    .httpStrictTransportSecurity(hsts -> hsts.maxAgeInSeconds(31_536_000).includeSubDomains(true)));

// Spring WebFlux: ServerHttpSecurity
http.headers(headers -> headers
    .frameOptions(frame -> frame.mode(XFrameOptionsServerHttpHeadersWriter.Mode.DENY))
    .contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'none'; frame-ancestors 'none'"))
    .hsts(hsts -> hsts.maxAge(Duration.ofDays(365)).includeSubdomains(true)));
```

Behind a TLS-terminating proxy, HSTS is only written when the request is seen as secure: set `server.request.header.forwarded.strategy=framework` (`spring-boot-config.md` → Proxy Headers).

## Password Encoding — BCryptPasswordEncoder

Always instantiate with explicit strength=12 (Spring default is 10 — too low for production).

```java
@Bean
public PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12); // strength=12; default=10 is insufficient
}
```

**Rules:**
- Never compare passwords with `.matches()` on raw strings — always use `passwordEncoder.matches(raw, encoded)`
- Never log password fields, even masked
- Argon2 (`Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()`) is acceptable alternative for new services

## JWT Role Extraction

Extract roles from JWT claims for method-level authorization:

```java
private Converter<Jwt, Mono<AbstractAuthenticationToken>> jwtConverter() {
    return jwt -> {
        List<String> roles = jwt.getClaimAsStringList("roles");
        Collection<GrantedAuthority> authorities = roles != null
            ? roles.stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .toList()
            : List.of();
        return Mono.just(new JwtAuthenticationToken(jwt, authorities));
    };
}
```

Wire into SecurityConfig:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter())))
```

## Secure Logging

Mask sensitive data before logging to prevent PII/credential leakage:

```java
@Component
public class LogSanitizer {

    private static final Pattern SENSITIVE = Pattern.compile(
        "(password|token|secret|ssn|creditCard|authorization)",
        Pattern.CASE_INSENSITIVE);

    public String mask(String field, String value) {
        if (value == null || value.length() <= 4) return "****";
        if (SENSITIVE.matcher(field).find()) {
            return value.substring(0, 2) + "****" + value.substring(value.length() - 2);
        }
        return value;
    }
}
```

Usage in service layer:

```java
log.info("Processing payment for customer: {}", logSanitizer.mask("customerId", customerId));
log.debug("Token refreshed for user: {}", logSanitizer.mask("token", token));
```

Rules:
- Never log raw passwords, tokens, API keys, or PII
- Use structured logging with the sanitizer for any potentially sensitive field
- In error handlers, mask request bodies before logging

## Input Validation — Regex Patterns

For DTOs that need stricter validation beyond `@NotBlank` / `@Size`:

```java
public record CreateUserRequest(
    @NotBlank
    @Size(min = 2, max = 50)
    @Pattern(regexp = "^[a-zA-Z\\s'-]+$", message = "Name contains invalid characters")
    String name,

    @NotBlank
    @Email
    String email,

    @NotBlank
    @Pattern(regexp = "^\\+?[1-9]\\d{6,14}$", message = "Invalid phone number format")
    String phone
) {}
```

## Custom Validators

For business rules beyond standard annotations, create reusable custom constraint validators:

```java
// 1. Define the annotation
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = NoProfanityValidator.class)
public @interface NoProfanity {
    String message() default "Input contains prohibited content";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

// 2. Implement the validator
public class NoProfanityValidator implements ConstraintValidator<NoProfanity, String> {

    private static final Set<String> BLOCKED = Set.of("spam", "test123");

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) return true; // use @NotNull for null checks
        return BLOCKED.stream().noneMatch(value.toLowerCase()::contains);
    }
}

// 3. Use on DTOs
public record CreateOrderRequest(
    @NotBlank @NoProfanity String description,
    @NotNull @Min(1) Integer quantity
) {}
```

## Security Checklist

- [ ] OWASP Dependency-Check runs in CI with `failBuildOnCVSS=7`
- [ ] No hardcoded secrets — all credentials via `${ENV_VAR}`
- [ ] CORS scoped to specific origins in production (not `*`)
- [ ] Security headers: CSP, X-Frame-Options DENY, HSTS, X-Content-Type-Options
- [ ] `@Valid` on all `@RequestBody` parameters
- [ ] Sensitive data masked in all log statements
- [ ] Actuator endpoints limited to `health, info, metrics` with auth
- [ ] JWT roles extracted and used for `@PreAuthorize` method security
- [ ] Database credentials externalized via environment variables
