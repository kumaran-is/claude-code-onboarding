---
description: Scaffold a new Java 25 + Spring Boot 4.2 REST API (Spring MVC + virtual threads by default, WebFlux + R2DBC with --webflux) with tested build config, security, Flyway, Testcontainers and a sample endpoint
argument-hint: "[project name] [--webflux]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Spring Boot 4.2 API

**Arguments:** $ARGUMENTS — project name (default `my-api`); add `--webflux` only when the service streams, needs end-to-end backpressure or fans out heavy concurrent I/O (decision table: `java-spring-api` skill, ADR `docs/adr/0001-java25-spring-boot-4-mvc-default.md`). Without `--webflux` the stack is Spring MVC.

Use the `java-spring-api` skill for every template (read `reference/spring-boot-conventions.md`, `reference/spring-boot-config.md`, `reference/spring-boot-templates.md` first) and `java-coding-standard` for style.

## Steps

1. **Create `.gitignore` first**: `target/`, `.env`, `*.pem`, `*.key`, `.idea/`, `*.iml`, `.DS_Store`, `*.log`
2. **Generate the skeleton** from Spring Initializr (Java 25, Boot 4.2.0); `<name>` and `<pkg>` from the arguments:
   ```bash
   # MVC (default)
   curl -fsS -o /tmp/<name>.zip "https://start.spring.io/starter.zip?type=maven-project&language=java&javaVersion=25&bootVersion=4.2.0&groupId=com.company&artifactId=<name>&packageName=com.company.<pkg>&dependencies=web,validation,data-jpa,postgresql,flyway,security,oauth2-resource-server,spring-restclient,actuator,prometheus,testcontainers"; echo "INITIALIZR EXIT:$?"
   # --webflux
   curl -fsS -o /tmp/<name>.zip "https://start.spring.io/starter.zip?type=maven-project&language=java&javaVersion=25&bootVersion=4.2.0&groupId=com.company&artifactId=<name>&packageName=com.company.<pkg>&dependencies=webflux,validation,data-r2dbc,postgresql,flyway,security,oauth2-resource-server,actuator,prometheus,testcontainers"; echo "INITIALIZR EXIT:$?"
   ```
   Unzip into the project directory. Initializr unreachable → write `pom.xml` from `spring-boot-config.md` instead and say so.
3. **Pin the Maven wrapper** to Maven 3.10.2: in `.mvn/wrapper/maven-wrapper.properties` set `distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.10.2/apache-maven-3.10.2-bin.zip`.
4. **Complete `pom.xml`** per `spring-boot-config.md`: springdoc 3.2.1 (`-webmvc-ui` or `-webflux-ui`); MVC adds `spring-boot-resttestclient` (test); WebFlux adds `spring-jdbc` (Flyway over JDBC), `reactor-test` and `blockhound` (test); compiler `-Xlint:deprecation -Werror`; surefire Mockito agent + `--enable-native-access=ALL-UNNAMED`; OWASP `dependency-check-maven` 13.0.0.
5. **Pin the Testcontainers image**: in the generated `TestcontainersConfiguration`, replace `postgres:latest` with `postgres:18.7`.
6. **Feature package** `com.company.<pkg>.<feature>/` with entity (`@Version`), repository, service (transactions on the service), controller (`/api/v1/...`, 201 + `Location`), DTO records, sealed exception; `config/SecurityConfig` (resource server, scopes, actuator rules, deny by default); `web/ProblemDetailsAdvice` (sets `instance`, never echoes input). Templates: `spring-boot-templates.md` (MVC or WebFlux section).
7. **`application.properties`** per `spring-boot-config.md`: MVC sets `spring.threads.virtual.enabled=true` and `spring.jpa.open-in-view=false`; secrets, the JWT key location, `jwt.audiences` and the expected issuer from environment variables with no defaults (audience and issuer are always validated; never `issuer-uri` next to `public-key-location`).
8. **Migration** `src/main/resources/db/migration/V1__create_<feature>.sql`, **`Dockerfile`** (from `spring-boot-config.md`: `eclipse-temurin:25-jdk` build stage running `./mvnw`, `eclipse-temurin:25-jre` runtime, non-root), **`compose.yaml`** with `postgres:18.7` for local runs.
9. **Tests**: one integration test class (Testcontainers + `RestTestClient` for MVC, `WebTestClient` for WebFlux) with the happy path, 400 validation problem, 401 without a token, with a wrong audience and with a wrong issuer, 403 with the wrong scope and 404; WebFlux also a BlockHound test that fails on a blocking call planted on a non-blocking thread (`Mono.delay(...)` runs on the parallel scheduler; the JUnit main thread is not watched).
10. **Verify**, each with its own exit code; report PASS / FAIL / BLOCKED:
    ```bash
    ./mvnw -q verify > /tmp/mvn-verify.log 2>&1; echo "VERIFY EXIT:$?"; tail -20 /tmp/mvn-verify.log   # -Werror compile + all tests
    ls target/surefire-reports/TEST-*.xml >/dev/null 2>&1 && grep -ho 'tests="[0-9]*"' target/surefire-reports/TEST-*.xml   # 0 executed = FAIL
    ./mvnw -q dependency-check:check > /tmp/mvn-dc.log 2>&1; echo "DEPCHECK EXIT:$?"   # NVD unreachable → BLOCKED, not clean
    ```
    Docker not running → the Testcontainers tests are **BLOCKED**; never report the scaffold as passing without them.
