# Spring Boot 4.2 Configuration (Java 25)

Everything in this file was built and tested on 2026-11-24: JDK 25.0.5.1 (`eclipse-temurin:25-jdk`), the Maven wrapper 3.3.4 pinned to Maven 3.10.2, Spring Boot 4.2.0, PostgreSQL 18.7 via Testcontainers. MVC reference app: `./mvnw -q verify` exit 0, 29 tests; jar and container image boot to `/actuator/health` UP.

## pom.xml — Spring MVC (default)

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>25</java.version>
    <springdoc.version>3.2.1</springdoc.version> <!-- not managed by the Boot BOM -->
    <argLine></argLine>                           <!-- lets @{argLine} below resolve when no agent sets it -->
</properties>

<dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-webmvc</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-flyway</artifactId></dependency>
    <dependency><groupId>org.flywaydb</groupId><artifactId>flyway-database-postgresql</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-security</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-restclient</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>io.micrometer</groupId><artifactId>micrometer-registry-prometheus</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId><scope>runtime</scope></dependency>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>

    <!-- Per-technology test starters (Boot 4): add the one for each main starter you use -->
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-webmvc-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-flyway-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-security-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-security-oauth2-resource-server-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-restclient-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator-test</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-resttestclient</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-testcontainers</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.testcontainers</groupId><artifactId>testcontainers-junit-jupiter</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.testcontainers</groupId><artifactId>testcontainers-postgresql</artifactId><scope>test</scope></dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <!-- Deprecated API use fails the build: keeps Boot 3 leftovers out -->
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <compilerArgs><arg>-Xlint:deprecation</arg><arg>-Werror</arg></compilerArgs>
            </configuration>
        </plugin>
        <plugin>
            <!-- Exposes ${org.mockito:mockito-core:jar} for the surefire agent below -->
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <executions><execution><goals><goal>properties</goal></goals></execution></executions>
        </plugin>
        <plugin>
            <!-- JDK 21+ warns about Mockito self-attaching; load it as an agent. Testcontainers' JNA needs native access on JDK 24+. -->
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar} -Xshare:off --enable-native-access=ALL-UNNAMED</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Check: `./mvnw dependency:tree -Dincludes='com.fasterxml.jackson.core:jackson-databind'` prints nothing (no Jackson 2 at runtime; `jackson-annotations` 2.x is expected, Jackson 3 uses it).

## pom.xml — WebFlux deltas

Replace the web, persistence and client starters; keep security, actuator, Flyway and the test infrastructure:

| MVC | WebFlux |
|---|---|
| `spring-boot-starter-webmvc` (+ `-test`) | `spring-boot-starter-webflux` (+ `-test`) |
| `spring-boot-starter-data-jpa` (+ `-test`) | `spring-boot-starter-data-r2dbc` (+ `-test`) and `org.postgresql:r2dbc-postgresql` (runtime) |
| `postgresql` (runtime) | keep it (runtime) **and** add `org.springframework:spring-jdbc`: Flyway migrates over JDBC |
| `spring-boot-starter-restclient` | `spring-boot-starter-webclient` (WebClient-backed `@ImportHttpServices` groups) |
| `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webflux-ui` |
| `spring-boot-resttestclient` | not needed: `WebTestClient` comes with `-webflux-test` |
| — | `io.micrometer:context-propagation` (Reactor `Context` → MDC/tracing; with `spring.reactor.context-propagation=auto`) |
| — | test: `io.projectreactor:reactor-test`, `org.testcontainers:testcontainers-r2dbc`, `io.projectreactor.tools:blockhound` + `blockhound-junit-platform` (not in the Boot BOM: pin the version) |

## application.properties — MVC

```properties
spring.application.name=orders
spring.threads.virtual.enabled=true

spring.datasource.url=${DB_URL:jdbc:postgresql://localhost:5432/orders}
spring.datasource.username=${DB_USERNAME:orders}
spring.datasource.password=${DB_PASSWORD:}
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false

spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100

# No default: startup fails if the key is missing (fail closed)
spring.security.oauth2.resourceserver.jwt.public-key-location=${JWT_PUBLIC_KEY_LOCATION}
# Audience is always required (Boot adds the validator); the issuer is checked by a JwtIssuerValidator bean (spring-boot-templates.md).
spring.security.oauth2.resourceserver.jwt.audiences=${JWT_AUDIENCE}
app.security.jwt.issuer=${JWT_ISSUER}
# With an identity provider use ...jwt.issuer-uri=${JWT_ISSUER_URI} INSTEAD of public-key-location, never both:
# Boot 4.2 then uses OIDC discovery and ignores the key (an unreachable issuer = 500 on every request, tested).

# @ImportHttpServices(group = "pricing")
spring.http.serviceclient.pricing.base-url=${PRICING_BASE_URL}
spring.http.serviceclient.pricing.connect-timeout=2s
spring.http.serviceclient.pricing.read-timeout=3s

management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.show-details=never
management.endpoint.health.probes.enabled=true

logging.structured.format.console=ecs

springdoc.api-docs.enabled=${OPENAPI_DOCS_ENABLED:false}
springdoc.swagger-ui.enabled=${OPENAPI_DOCS_ENABLED:false}
```

WebFlux (from the reference app): replace the `spring.datasource.*` block with `spring.r2dbc.url` / `username` / `password` and bounded pool settings (`spring.r2dbc.pool.max-size`, `max-acquire-time`, `max-create-connection-time`); give Flyway its JDBC URL with `spring.flyway.url`, `spring.flyway.user`, `spring.flyway.password`; drop `spring.jpa.*` and `spring.threads.virtual.enabled`. Add `spring.reactor.context-propagation=auto`, `server.shutdown=graceful`, Netty limits (`server.netty.connection-timeout`, `server.netty.idle-timeout`, `server.netty.max-initial-line-length`), `spring.http.codecs.max-in-memory-size=256KB`, and `springdoc.pre-loading-enabled=true` (otherwise springdoc scans the classpath, blocking, on the first `/v3/api-docs` request on an event-loop thread).

## Proxy Headers

Behind a trusted load balancer (Cloud Run, an ingress), honour `X-Forwarded-*`:

```properties
# Boot 4 name of server.forward-headers-strategy (.properties has no trailing comments: keep them on their own line)
server.request.header.forwarded.strategy=framework
```

Only when every request comes through the proxy: otherwise a client can spoof its IP and scheme.

## Type-Safe Configuration Properties

```java
@ConfigurationProperties(prefix = "integration.payment-service")
@Validated
public record PaymentServiceProperties(@NotBlank String baseUrl, @Min(100) int timeoutMs) {}

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

## Structured Logging and Tracing

`logging.structured.format.console=ecs` (or `logstash`, `gelf`) writes one JSON object per line. ECS output is nested: `{"@timestamp":"...","log":{"level":"INFO","logger":"..."},"message":"...","ecs":{"version":"8.11"}}` — assert on `log.level` as a nested key, not a dotted key.

Trace and span ids come from Micrometer Tracing: add `spring-boot-starter-opentelemetry` (or `micrometer-tracing-bridge-otel` + an exporter) and they appear in every log line and in the `traceparent` header of `RestClient`/`WebClient` calls built from the auto-configured builders. Do not hand-roll an MDC filter: in WebFlux, MDC on the event loop leaks between requests.

## Dockerfile (tested)

```dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:25-jdk AS build
WORKDIR /src
COPY mvnw pom.xml ./
COPY .mvn ./.mvn
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -DskipTests package \
 && java -Djarmode=tools -jar target/*.jar extract --layers --launcher --destination /extracted

FROM eclipse-temurin:25-jre
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /extracted/dependencies/ ./
COPY --from=build /extracted/spring-boot-loader/ ./
COPY --from=build /extracted/snapshot-dependencies/ ./
COPY --from=build /extracted/application/ ./
USER 10001:10001
EXPOSE 8080
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

The build stage uses the Maven wrapper on `eclipse-temurin:25-jdk` instead of a `maven:*` image: the wrapper pins the Maven version, and `maven:3.10.2-eclipse-temurin-25` has no arm64 build. Do not list `mvnw` or `.mvn/` in `.dockerignore`. Tests run in CI (Testcontainers needs Docker), not in the image build. Pin the base images by digest in production pipelines.

Pin the wrapper in `.mvn/wrapper/maven-wrapper.properties`: `distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.10.2/apache-maven-3.10.2-bin.zip` (Initializr generates 3.10.1).
