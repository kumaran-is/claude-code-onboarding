# Spring Boot 4.2 Review Checklist (MVC and WebFlux)

Used by `spring-boot-reviewer`. Review the **Common** section for every change, then the section for the detected stack (`spring-boot-starter-webmvc` → MVC, `spring-boot-starter-webflux` → WebFlux). Cite `file:line` for every finding.

## Severity

| Severity | Criteria | Verdict effect (`.claude/rules/verification-and-reporting.md`) |
|---|---|---|
| **CRITICAL** | Security hole, data loss or corruption, blocking call on an event-loop thread, auth bypass, secret in code | BLOCK |
| **HIGH** | Missing authorization check, remote call inside a DB transaction, unbounded retry/page size, missing timeout, no test for a new endpoint's error path, deprecated/removed Boot 3 API, both web stacks on the classpath | NEEDS_REVIEW |
| **MEDIUM** | Missing optimistic locking on a concurrently edited aggregate, N+1 query, weak test assertions, missing metrics/logs on a failure path | APPROVE with advisory (track) |
| **LOW** | Naming, style, minor simplifications | APPROVE with advisory |

## Common (both stacks)

**Boot 4 / Java 25 hygiene**
- No `RestTemplate`, `TestRestTemplate`, `@MockBean`/`@SpyBean`, Spring Retry, `com.fasterxml.jackson.databind` imports, `org.springframework.lang.Nullable`, `javax.*` (HIGH)
- Boot 4 starters: `-webmvc`/`-webflux`, `-restclient`, `-flyway`, `-security-oauth2-resource-server`, per-technology `-test` starters; compiler runs with `-Xlint:deprecation -Werror`
- No Java preview features (`StructuredTaskScope`, `StableValue`, primitive patterns) in production code (HIGH)
- Records for DTOs; sealed types + exhaustive `switch` for closed hierarchies; no `default` branch hiding a missing case

**Security**
- Every endpoint has an explicit authorization rule; `anyRequest().denyAll()` (or `authenticated()`) as the last matcher (CRITICAL if a write endpoint is open)
- Ownership enforced in the service (another tenant's/customer's record → 404, not data)
- Actuator: only `health`/`info` public; metrics need a scope; everything else denied; `show-details=never` publicly
- JWT: issuer or public key from configuration with no default; signature algorithm not widened; tokens never logged
- CSRF disabled only for stateless bearer-token APIs, with the reason in a comment
- `@Valid` on request bodies, constraints on record components; bounded collections (`@Size(max=...)`)
- No secrets or keys in `application.properties` defaults; OpenAPI/Swagger UI disabled by default in production

**Errors**
- All errors are `application/problem+json`; `instance` set (Framework 7.1 no longer sets it); no exception messages, stack traces or rejected values in responses
- Sealed domain exceptions mapped exhaustively; a catch-all handler logs at ERROR and returns a generic 500
- Retry exhaustion maps to 502/503 (`@Retryable` rethrows the last original exception)
- No swallowed exceptions (`catch {}`, `onErrorResume(e -> Mono.empty())`)

**Outbound calls and resilience**
- `@HttpExchange` client or `RestClient`/`WebClient` from the auto-configured builder; connect and read timeouts set (HIGH if missing)
- `@Retryable` / `Retry.backoff` only on idempotent operations, only for 5xx / I/O errors, bounded attempts and `maxDelay` (HIGH if unbounded)
- A bulkhead around slow dependencies (`@ConcurrencyLimit` in MVC; connection-pool limits in WebFlux); circuit breaker where failures cascade

**Data**
- Flyway migration for every schema change; `ddl-auto=validate` (JPA)
- `@Version` on aggregates edited concurrently; `If-Match` → 428 missing / 409 stale
- Paging bounded (`max-page-size`), sort properties whitelisted, unique tiebreaker
- Indexes for the queries the endpoints run

**Tests**
- Each new endpoint: happy path + at least one error path (400/401/403/404/409 as applicable), security rules tested with real tokens or `jwt()`
- Testcontainers with a pinned image (`postgres:18.x`), never `latest`; `@ServiceConnection`
- `@MockitoBean`; no `Thread.sleep`; time from an injected `Clock`
- `./mvnw -q verify` exit code and executed test count reported (0 executed = FAIL)

**Observability**
- SLF4J parameterised logs with ids, not bodies; structured JSON output; health probes enabled; business metrics for important operations

## Spring MVC

- `spring.threads.virtual.enabled=true` (or a documented reason not to)
- `@Transactional` on service methods only; `readOnly = true` for reads (MEDIUM)
- **No HTTP/remote call inside a `@Transactional` method** — holds a DB connection during network I/O (HIGH)
- `spring.jpa.open-in-view=false`; entities mapped to DTOs inside the transaction; no entity returned from a controller
- No N+1: fetch joins / entity graphs / projections for list endpoints
- Assigned UUID ids use a nullable `@Version Long` (otherwise every save is treated as an update)
- Long `synchronized` blocks around I/O in hot paths flagged (pinning diagnosis: JFR `jdk.VirtualThreadPinned`)
- Tests: `RestTestClient` (`@AutoConfigureRestTestClient`) or `MockMvcTester`; `@SpringBootTest` that uses MockMvc has `@AutoConfigureMockMvc`

## Spring WebFlux

- Stack choice justified in the README (streaming, backpressure, fan-out); otherwise recommend MVC (MEDIUM)
- **No `.block()`, `.blockFirst()`, `.blockLast()`, `.toFuture().get()`, `Thread.sleep`, JDBC or blocking file/SDK I/O on event-loop threads** (CRITICAL); unavoidable blocking isolated with `subscribeOn(Schedulers.boundedElastic())`
- BlockHound installed in tests and a test proves it detects a planted blocking call
- R2DBC repositories only, no JPA; Flyway over JDBC for migrations only
- No `.subscribe()` inside services or controllers (escapes transactions, errors and cancellation)
- `@Transactional` only on methods returning `Mono`/`Flux`, or `TransactionalOperator`; everything inside the returned chain runs in the transaction
- Every outbound call has `.timeout(...)`; retries via `Retry.backoff(n, ...).filter(retryable)`
- `Flux` endpoints: bounded buffering (`limitRate`, `onBackpressureBuffer(n, ...)`), cancellation stops upstream work, SSE heartbeats for idle streams
- `@ConcurrencyLimit` is not used to bound `Mono`/`Flux` work (its permit is released at assembly); concurrency is bounded by the client connection pool or `flatMap(…, concurrency)`
- Context (security, tracing) via Reactor `Context` / context propagation; no `ThreadLocal`/MDC set on the event loop
- Tests: `WebTestClient`, `StepVerifier` (including `thenCancel()` and virtual time for timeouts), no `.block()` in tests except at the outermost assertion

## Output Format

```
[CRITICAL] Blocking call on event-loop thread
File: src/main/java/com/company/orders/OrderService.java:42
Problem: .block() inside a WebFlux handler stalls the Netty event loop for every connection on it
Fix: return the Mono; let the framework subscribe
```

End the report with:

```
VERDICT: [APPROVE|NEEDS_REVIEW|BLOCK] — CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N
```
