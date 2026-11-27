# Pattern Selection Guidelines

> Decision trees for choosing architectural patterns. Part of the `architecture-design` skill.
> Load `context-discovery.md` first to classify the project before using these trees.

## The 3 Questions (Before ANY Pattern)

1. **Problem Solved**: What SPECIFIC problem does this pattern solve right now?
2. **Simpler Alternative**: Is there a simpler solution that avoids this pattern?
3. **Deferred Complexity**: Can we add this LATER when the need is proven?

If you cannot answer Question 1 concretely — don't use the pattern.

## Main Decision Tree

```
START: What is your MAIN architectural concern?

+-- Data Access Complexity?
|   +-- HIGH (complex queries, need testability, data source may change)
|   |   -> Repository Pattern + Unit of Work
|   |   VALIDATE: Will data source actually change?
|   |      YES -> Repository worth the indirection
|   |      NO  -> Consider direct ORM access (Prisma, SQLAlchemy, Spring Data)
|   +-- LOW (simple CRUD, single database, no test mocking needed)
|       -> ORM directly
|       Simpler = Better, Faster
|
+-- Business Rules Complexity?
|   +-- HIGH (domain logic varies by context, rich invariants, multiple bounded contexts)
|   |   -> Domain-Driven Design (use ddd-architect skill)
|   |   VALIDATE: Do you have domain experts on the team?
|   |      YES -> Full DDD (Aggregates, Value Objects, Domain Events)
|   |      NO  -> Partial DDD (rich entities, clear service boundaries only)
|   +-- LOW (mostly CRUD, simple validation, no domain experts)
|       -> Transaction Script (procedural service methods)
|       Simpler = Better, Faster
|
+-- Independent Scaling Needed?
|   +-- YES (different components have measurably different scaling needs)
|   |   -> Microservices (use ddd-architect for service boundaries)
|   |   REQUIREMENTS (ALL must be true before choosing microservices):
|   |     - Clear domain boundaries proven from production usage
|   |     - Team > 10 developers with separate ownership
|   |     - Different scaling requirements per service (measured, not assumed)
|   |   IF NOT ALL MET -> Modular Monolith first
|   +-- NO (everything scales together, team < 10)
|       -> Modular Monolith
|       Can extract services later when proven needed from production data
|
+-- Real-time Requirements?
    +-- HIGH (immediate multi-user sync, sub-second updates, live collaboration)
    |   -> Event-Driven Architecture
    |   -> Message Queue: RabbitMQ (simple), Redis Streams (moderate), Kafka (high-volume)
    |   VALIDATE: Can your system handle eventual consistency?
    |      YES -> Event-driven valid
    |      NO  -> Synchronous with optimistic locking
    +-- LOW (eventual consistency acceptable, polling is fine)
        -> Synchronous REST/GraphQL
        Simpler = Better, Faster
```

## Architecture Pattern Quick Reference

| Pattern | When | Cost | Our Stack |
|---------|------|------|-----------|
| Transaction Script | Simple CRUD, small team | Low | All stacks |
| Active Record | Simple entities, rapid dev | Low | Prisma (NestJS), SQLAlchemy (Python) |
| Repository + UoW | Complex queries, testability | Medium | Spring (Java), NestJS, FastAPI |
| Modular Monolith | SaaS, team < 10 | Medium | NestJS modules, Spring Boot modules |
| Clean Architecture | Testable core, framework-agnostic | Medium-High | Python FastAPI, NestJS |
| Hexagonal (Ports/Adapters) | Swap implementations, testing | Medium-High | All stacks |
| DDD + Microservices | Enterprise, team > 10, proven boundaries | High | Spring Boot (primary) |
| CQRS | Read/write diverge significantly | High | Spring + Kafka, NestJS + Redis |
| Event Sourcing | Audit trail required, financial systems | Very High | Spring Boot + Kafka |

## Anti-Pattern Reference

| Anti-Pattern | Symptom | Simpler Alternative |
|-------------|---------|-------------------|
| **Premature Microservices** | Microservices before product-market fit | Start modular monolith, extract later |
| **Over-abstraction** | Repository for simple CRUD that won't change | Direct ORM access |
| **Event Sourcing by Default** | Event sourcing without audit/replay need | Append-only audit log (simpler) |
| **CQRS Everywhere** | CQRS without divergent read/write needs | Single model with optimized queries |
| **Repository for Repository's Sake** | Repository wrapping Prisma 1:1 | Prisma directly in service |
| **Gold-Plated MVP** | K8s + service mesh for < 100 users | Cloud Run, single container |

## Workspace-Specific Guidance

### NestJS
- Default: Service + Prisma (no Repository abstraction unless query complexity demands it)
- Add Repository: when you need unit testing with mocks OR when data source may change
- Add CQRS: only with `@nestjs/cqrs` when command/query handlers diverge meaningfully

### Spring Boot (MVC default, WebFlux when justified)
- Default: Repository interface (Spring Data JPA/JDBC handles it; Spring Data R2DBC on WebFlux)
- Add Domain Services: for complex business logic spanning aggregates
- Add Event-driven: use Spring Application Events for in-process, Kafka for cross-service

### Python FastAPI
- Default: SQLAlchemy session in service (simple)
- Add Repository: when async testing requires injection, or data source flexibility needed
- Add Clean Architecture: when team size or long-term maintenance justifies the layers

### Flutter
- Default: Riverpod providers calling repository
- Repository pattern: always (testability is critical in mobile)
- State: Riverpod 3 `AsyncNotifier` for server state, `Notifier` for local UI state (`StateNotifier`/`StateProvider` are legacy imports in Riverpod 3)

## Monorepo tooling

Not an application pattern — package managers vs task orchestration. Load `polyglot-monorepo` (do not copy Melos/uv/Nx setup here).

```
Multiple packages in one git repo?
  Dart/Flutter     -> pub workspace + Melos 7+ for scripts (never Nx as the Dart PM)
  Python           -> uv workspaces (incompatible requires-python stays outside)
  Angular/Node/MCP -> npm workspaces first; Nx only if JS-heavy + measured CI + human yes
  Cross-language   -> Makefile/Taskfile unless Nx already owns JS CI
  nx.json present  -> keep; do not add a second Flutter affected-test owner
  no nx.json       -> do not add Nx
```
