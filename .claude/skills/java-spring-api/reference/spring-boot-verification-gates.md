# Spring Boot Verification Gates

Pre-PR static analysis gates for Java 25 + Spring Boot 4.2 services (Spring MVC and WebFlux).

---

## SpotBugs

**Run:** `mvn spotbugs:check`

```xml
<plugin>
  <groupId>com.github.spotbugs</groupId>
  <artifactId>spotbugs-maven-plugin</artifactId>
  <version>4.8.6</version>
  <configuration>
    <effort>Max</effort>
    <threshold>High</threshold>
    <failOnError>true</failOnError>
    <includeFilterFile>${project.basedir}/spotbugs-include.xml</includeFilterFile>
    <plugins>
      <plugin>
        <groupId>com.h3xstream.findsecbugs</groupId>
        <artifactId>findsecbugs-plugin</artifactId>
        <version>1.13.0</version>
      </plugin>
    </plugins>
  </configuration>
  <executions>
    <execution>
      <goals><goal>check</goal></goals>
    </execution>
  </executions>
</plugin>
```

`spotbugs-include.xml` — enable CORRECTNESS and SECURITY detector categories:

```xml
<FindBugsFilter>
  <Match>
    <Bug category="CORRECTNESS"/>
  </Match>
  <Match>
    <Bug category="SECURITY"/>
  </Match>
</FindBugsFilter>
```

Build fails on any `HIGH` severity bug. `MEDIUM`/`LOW` are reported but non-blocking.

---

## PMD

**Run:** `mvn pmd:check`

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-pmd-plugin</artifactId>
  <version>3.21.2</version>
  <configuration>
    <rulesets>
      <ruleset>${project.basedir}/pmd-ruleset.xml</ruleset>
    </rulesets>
    <failOnViolation>true</failOnViolation>
    <printFailingErrors>true</printFailingErrors>
  </configuration>
  <executions>
    <execution>
      <goals><goal>check</goal></goals>
    </execution>
  </executions>
</plugin>
```

`pmd-ruleset.xml` — Spring-appropriate rules (excludes JPA / persistence patterns):

```xml
<?xml version="1.0"?>
<ruleset name="Spring WebFlux Rules"
  xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0
    https://pmd.sourceforge.io/ruleset_2_0_0.xsd">
  <description>PMD rules for Spring Boot 4.2 services</description>

  <rule ref="category/java/bestpractices.xml/AvoidDuplicateLiterals"/>
  <rule ref="category/java/bestpractices.xml/UnusedImports"/>
  <rule ref="category/java/design.xml/AvoidDeeplyNestedIfStmts"/>
  <rule ref="category/java/errorprone.xml/NullAssignment"/>
  <rule ref="category/java/errorprone.xml/ConstructorCallsOverridableMethod"/>
  <rule ref="category/java/errorprone.xml/CloseResource"/>
</ruleset>
```

---

## Checkstyle

**Run:** `mvn checkstyle:check`

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-checkstyle-plugin</artifactId>
  <version>3.3.1</version>
  <configuration>
    <configLocation>google_checks.xml</configLocation>
    <suppressionsLocation>${project.basedir}/checkstyle-suppressions.xml</suppressionsLocation>
    <failsOnError>true</failsOnError>
    <consoleOutput>true</consoleOutput>
  </configuration>
  <executions>
    <execution>
      <goals><goal>check</goal></goals>
    </execution>
  </executions>
</plugin>
```

`google_checks.xml` is bundled in the Checkstyle artifact — no separate download needed.

Suppress violations in generated code (e.g., MapStruct, Lombok, Flyway migrations):

```xml
<!-- checkstyle-suppressions.xml -->
<suppressions>
  <suppress files=".*[\\/]generated[\\/].*" checks=".*"/>
  <suppress files=".*[\\/]db[\\/]migration[\\/].*" checks=".*"/>
</suppressions>
```

---

## 6-Phase Verification Loop

Run in order — each phase must pass before advancing.

| Phase | Command | Purpose |
|-------|---------|---------|
| 1 Format | `mvn spotless:apply` | Auto-format — must run before style check |
| 2 Style | `mvn checkstyle:check` | Google Java Style conformance |
| 3 Quality | `mvn pmd:check` | Code quality rules (nulls, duplication, depth) |
| 4 Bugs | `mvn spotbugs:check` | Correctness + security bug patterns |
| 5 Tests | `mvn test` | Unit + reactive stream tests |
| 6 CVEs | `mvn org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=7` | Dependency vulnerability scan — see `spring-boot-security-hardening.md` |

> Phase 6 config (suppression file, NVD API key, report format) is fully documented in
> `reference/spring-boot-security-hardening.md`. Do not duplicate it here.

---

## CI/CD Integration

Chain all phases in a single `mvn verify`:

```xml
<!-- pom.xml — bind all plugins to verify lifecycle -->
<plugin>... spotless ...</plugin>
<plugin>... checkstyle (bound to verify) ...</plugin>
<plugin>... pmd (bound to verify) ...</plugin>
<plugin>... spotbugs (bound to verify) ...</plugin>
```

```bash
mvn verify -DfailBuildOnCVSS=7
```

**GitHub Actions snippet (Java 25):**

```yaml
- name: Static Analysis & Tests
  run: mvn verify -DfailBuildOnCVSS=7 --batch-mode --no-transfer-progress
  env:
    NVD_API_KEY: ${{ secrets.NVD_API_KEY }}
```

Cache `.m2` repository between runs to avoid re-downloading the NVD database on every build.

---

## Output Template

Report gate results in this format after running verification:

```
## Verification Gate Results
Phase 1 Format:    ✅ PASS / ❌ FAIL — [detail]
Phase 2 Style:     ✅ PASS / ❌ FAIL — [N violations]
Phase 3 PMD:       ✅ PASS / ❌ FAIL — [N violations]
Phase 4 SpotBugs:  ✅ PASS / ❌ FAIL — [N HIGH bugs]
Phase 5 Tests:     ✅ PASS / ❌ FAIL — [N/N passed]
Phase 6 CVEs:      ✅ PASS / ❌ FAIL — [see spring-boot-security-hardening.md]
```

All six phases must show ✅ PASS before opening a PR.

---

## Anti-Patterns

**Running only `mvn test` and calling it verified.**
Tests confirm behavior; they do not catch null-assignment bugs, style drift, or CVEs in
transitive dependencies. All 6 phases are required.

**Suppressing all PMD violations with a blanket `@SuppressWarnings("PMD")`.**
Suppress individual rules with `@SuppressWarnings("PMD.RuleName")` and add a comment
explaining why. Blanket suppression defeats the gate.

**Skipping SpotBugs in CI to save ~30s build time.**
SpotBugs with FindSecBugs catches injection paths and null-dereference bugs that tests
rarely cover. The time cost is ~30s; the miss cost is a production incident.
