---
description: Scaffold a new Spring Boot 3.5.x WebFlux REST API project with standard structure, build config, and sample endpoint
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Spring Boot WebFlux API

**Project name:** $ARGUMENTS (default to "my-api" if not provided)

Delegate to the `java-spring-api` skill for all patterns, templates, and reference files. Use the `java-coding-standard` skill for naming, immutability, and style rules.

## Steps

1. **Create `.gitignore` first** — before any other file. Include: `target/`, `.env`, `*.pem`, `*.key`, `.idea/`, `*.iml`, `.DS_Store`, `*.log`
2. Read the `java-spring-api` skill and its reference files for exact code templates
3. Create Maven project via Spring Initializr or manual `pom.xml` per skill config reference
4. Set up package `com.company.<projectname>` with directory structure: `controller/`, `service/`, `repository/`, `model/entity/`, `model/dto/`, `config/`, `exception/`
5. Add `application.yml` with R2DBC + Flyway config (PostgreSQL, Flyway disabled by default via `enabled: ${FLYWAY_ENABLED:false}`)
6. Create `HealthController` at `GET /api/v1/health`, a sample entity, DTO (record), repository, service, and controller
7. Add `GlobalExceptionHandler` with `@ControllerAdvice` returning `ProblemDetail` (RFC 9457)
8. Add `V1__initial_schema.sql` Flyway migration, `Dockerfile`, and `docker-compose.yml` with PostgreSQL
9. Add a basic integration test using `WebTestClient`
10. Add the OWASP dependency-check plugin to `pom.xml`
11. Verify — run each with its OWN exit code and report PASS / FAIL / BLOCKED (use `mvn` where no Maven wrapper was generated):
    ```bash
    ./mvnw -q test > /tmp/mvn-test.log 2>&1; echo "TEST EXIT:$?"            # compiles + runs the WebTestClient test; 0 executed tests is FAIL
    ./mvnw -q dependency-check:check > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"   # NVD unreachable → BLOCKED, not clean
    ```
    Fix or document any critical/high CVE the check reports. The integration test needs PostgreSQL (docker compose); if Docker is not running, the test is BLOCKED — never report the scaffold as passing.
