# ADR-0001: Java 25 + Spring Boot 4.2, Spring MVC with virtual threads as the default, WebFlux by justification

## Status
Proposed (2026-11-24). Accept or reject in the PR that carries the toolkit change.

## Context
The toolkit's Java guidance targeted Java 21 and Spring Boot 3.5.x on WebFlux + R2DBC only. As of 2026-11-24:

- Spring Boot 3.5.x open-source support ended 2026-06-30 (spring.io generations API). start.spring.io no longer generates 3.5.x projects (HTTP 400 for `bootVersion=3.5.16`).
- Spring Boot 4.2.0 is current (OSS support to 2027-12-31) and manages Spring Framework 7.1.0, Spring Security 7.2.0, Spring Data 2026.1.0, Jackson 3.1.8, Hibernate ORM 7.4.15, Reactor 2026.0.0, JUnit Jupiter 6.1.3 and Testcontainers 2.0.5 (its `spring-boot-dependencies` BOM).
- Java 25 is the current LTS (Temurin 25.0.5.1). Spring Framework 7.0 release notes recommend it.
- Virtual threads (`spring.threads.virtual.enabled=true`) give blocking Spring MVC + JPA/JDBC code high request concurrency without reactive types.

The toolkit taught every Java service as reactive. That made ordinary CRUD services pay WebFlux's costs (operator chains, no JPA, harder debugging and stack traces, BlockHound to catch blocking calls) without a measured need.

## Decision drivers
1. Supported, patched versions (security fixes).
2. The simplest correct programming model for the common case (CRUD over PostgreSQL).
3. Keep a non-blocking path for workloads that need it (streaming, very high fan-out I/O, backpressure).
4. Guidance proven by executed reference applications, not by memory.

## Options
| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| A. Stay on Boot 3.5 / Java 21, WebFlux only | No migration work | No public security patches since 2026-06-30; Initializr cannot scaffold it; reactive cost for every service | Fails driver 1 outright |
| B. Boot 4.2 / Java 25, WebFlux only | Patched; one model to teach | Keeps reactive complexity for plain CRUD where virtual threads now give the concurrency benefit | Fails driver 2: most services are blocking-JPA CRUD |
| **C. Boot 4.2 / Java 25, MVC + virtual threads default, WebFlux when justified** | Patched; simplest model for the common case; WebFlux kept where it earns its cost | Two models to document and review | **Chosen** |

## Decision
We will target Java 25 LTS and Spring Boot 4.2.x (Spring Framework 7.1). New services default to Spring MVC + virtual threads + Spring Data JPA/JDBC. WebFlux + R2DBC is chosen only when the service streams (SSE, long-lived connections), needs end-to-end backpressure, or fans out many concurrent I/O calls per request, and that need is stated in the service's README or design doc. The `java-spring-api` skill documents both models, `/scaffold-spring-api` scaffolds MVC unless `--webflux` is asked for, and one reviewer (`spring-boot-reviewer`) reviews both.

Preview Java features (`StructuredTaskScope`, `StableValue`, primitive patterns, all still preview in JDK 25 by `javac --release 25`) stay out of production defaults and are documented as optional experiments.

## Consequences
- **Good:** supported versions; RestClient / RestTestClient / HTTP interface clients replace the deprecated RestTemplate and TestRestTemplate; Framework 7 `@Retryable` / `@ConcurrencyLimit` replace Spring Retry; JPA is allowed again for MVC services.
- **Bad:** Boot 4 breaks Boot 3 habits (Jackson 3 `tools.jackson` packages, modular starters, `@MockBean` removed, `@SpringBootTest` no longer adds MockMvc); existing Boot 3.5 services need a migration; two review checklists.
- **Mitigations:** the skill lists every Boot 3 → 4 replacement with the official migration guide; both reference applications were built and tested on JDK 25 with Testcontainers before the guidance was written; `spring-boot-reviewer` checks the blocking-on-event-loop rule for WebFlux and the transaction/JPA rules for MVC.
