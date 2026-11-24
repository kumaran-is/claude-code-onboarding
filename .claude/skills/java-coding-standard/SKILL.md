---
name: java-coding-standard
description: This skill should be activated when reviewing Java code or enforcing coding standards in Java 25 / Spring Boot 4.2 services (Spring MVC or WebFlux). It covers naming conventions, immutability patterns, Optional usage, sealed types and pattern matching, streams, nullability, and exception handling.
allowed-tools: Read
metadata:
  triggers: Java coding standard, Java code review, Java best practices, Spring Boot Java, Java style, Java review
  related-skills: java-spring-api, code-reviewer, security-reviewer
  domain: backend
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-24"
---

## Iron Law

Always load the java-spring-api skill and consult current Spring docs before writing Java code; never generate Spring Boot 4 / Framework 7 APIs from memory (Boot 3 habits such as `@MockBean` or `RestTemplate` no longer compile or are deprecated).

# Java Coding Standards

Standards for readable, maintainable Java 25 code in Spring Boot 4.2 services (Spring MVC by default, WebFlux where justified).

## Core Principles

- Prefer clarity over cleverness
- Immutable by default; minimize shared mutable state
- Fail fast with meaningful exceptions
- Consistent naming and package structure

## Key Rules

| Rule | Standard |
|------|----------|
| **Naming** | Classes: `PascalCase`, methods/fields: `camelCase`, constants: `UPPER_SNAKE_CASE` |
| **Immutability** | Favor records and final fields; getters only, no setters. JPA entities: protected no-arg constructor + intention-revealing methods (`update(...)`) instead of setters; R2DBC entities may need setters or a persistence constructor |
| **Optional** | Return `Optional` from `find*` methods; use `map`/`filter`/`orElseThrow`, never `.get()`. In WebFlux code, `Mono<T>` replaces `Optional<T>` — use `switchIfEmpty()` instead |
| **Streams** | Short pipelines for transforms; prefer loops for complex logic |
| **Exceptions** | Unchecked domain exceptions; avoid broad `catch (Exception)` |
| **Generics** | No raw types; prefer bounded generics for reusable utilities |
| **Null handling** | Non-null by default; mark nullable values with `org.jspecify.annotations.Nullable` (Framework 7 uses JSpecify); Bean Validation on inputs |
| **Logging** | SLF4J with structured key=value pairs |
| **Closed hierarchies** | Sealed interfaces/classes + exhaustive pattern-matching `switch` without `default`; unnamed patterns (`case X _ ->`) for unused bindings |
| **Language level** | Java 25 final features only; no preview features (`StructuredTaskScope`, `StableValue`, primitive patterns) in production code |
| **Testing** | JUnit 6 (Jupiter API) + AssertJ + Mockito (`@MockitoBean` in Spring tests) + `RestTestClient`/`MockMvcTester` (MVC) or `WebTestClient`/`StepVerifier` (WebFlux); deterministic, injected `Clock`, no sleeps |

## Project Structure

```
src/main/java/com/company/<service>/
  config/ → controller/ → service/ → repository/ → model/entity/ → model/dto/ → exception/
src/main/resources/application.yml
src/test/java/... (mirrors main)
```

## Code Examples & Detailed Patterns

For naming examples, immutability patterns, Optional usage, streams, exception handling, generics, logging, formatting, code smells, and testing expectations, Read `reference/java-standards-examples.md`.

**Remember**: Keep code intentional, typed, and observable. Optimize for maintainability over micro-optimizations unless proven necessary.

## Error Handling

**Checked vs unchecked exceptions**: Use unchecked (`RuntimeException` subclasses) for programming errors. Use checked exceptions only for recoverable conditions the caller must handle.

**Optional misuse**: Never call `.get()` without `.isPresent()` or use `.orElseThrow()`. Prefer `map`/`flatMap` chains.