---
name: architect-review
description: "Deep architectural review specialist — assesses system design changes, identifies anti-patterns, evaluates distributed systems compliance, and produces improvement recommendations. Use when reviewing architecture before implementation, assessing microservice boundaries, or evaluating event-driven system design. Not for producing a new design (architecture-design / architect agent), adversarial attack on an implementation plan (plan-challenger), or recording the decision (architecture-decision-records)."
argument-hint: "[system, feature, or design doc to review]"
allowed-tools: Read, Grep, Glob
context: fork
metadata:
  triggers: review architecture, architectural review, assess design, evaluate system design, microservice boundary, bounded context review, review service design, architecture compliance, scalability review, resilience review
  related-skills: architecture-design, architecture-decision-records, ddd-architect, plan-mode-review, threat-modeling
  domain: api-architecture
  role: architect
  scope: review
  output-format: assessment
last-reviewed: "2026-03-15"
---

## Iron Law

Never approve an architecture without evidence-based analysis; always provide concrete trade-offs with file:line references, not opinions.

# Architect Review Skill

Elite architectural review specialist. Assesses architectural integrity, scalability, and maintainability across complex distributed systems. Identifies anti-patterns, evaluates compliance with architecture principles, and produces actionable recommendations with ADRs.

**Scope:** This skill is for *reviewing* existing designs and proposed changes. For *designing* new architecture, use `architecture-design`. For full DDD analysis, use `ddd-architect`. For 5-phase plan review, use `plan-mode-review`.

## When to Use

- Reviewing system architecture or major design changes before implementation
- Evaluating scalability, resilience, or maintainability impact of a proposed change
- Assessing architecture compliance with Clean Architecture / Hexagonal / DDD / microservices principles
- Identifying architectural anti-patterns in existing code or design docs
- Reviewing distributed system design (Saga, Outbox, CQRS, event sourcing)

## When NOT to Use

- Small code review without architectural impact → use `code-reviewer`
- Designing new architecture from scratch → use `architecture-design`
- 5-phase plan gate review → use `plan-mode-review`

## Review Process

1. **Gather context** — Identify system goals, constraints, and current state
2. **Assess impact** — Rate each concern: HIGH / MEDIUM / LOW
3. **Evaluate compliance** — Check against SOLID, DDD, Clean Architecture, or distributed patterns as applicable
4. **Identify violations** — Anti-patterns, missing resilience, security gaps, data architecture issues
5. **Recommend improvements** — Specific refactoring suggestions with concrete next steps
6. **Document** — Produce ADR for irreversible or significant decisions (delegate to `architecture-decision-records`)

## Output Format

```
## Architecture Review: [System/Feature Name]

### Context
[System goals, constraints, current state]

### Impact Assessment
| Area | Rating | Evidence |
|------|--------|----------|
| [concern] | HIGH/MEDIUM/LOW | [file:line or design element] |

### Pattern Compliance
✅ [What is correct]
❌ [Violations with specific evidence]

### Anti-Patterns Detected
- [Pattern name]: [Description] — [Concrete fix]

### Recommendations
1. [Specific action with implementation guidance]

### ADRs Required
- ADR-XXXX: [Title] — [Decision to document]
```

## Architecture Capabilities

### Modern Patterns
- Clean Architecture and Hexagonal Architecture (Ports & Adapters)
- Microservices with proper service boundaries and data isolation
- Event-driven architecture (EDA), Event Sourcing, CQRS
- Domain-Driven Design — bounded contexts, aggregates, ubiquitous language
- Serverless and Function-as-a-Service patterns
- API-first design (REST, GraphQL, gRPC)

### Distributed Systems
- Service mesh (Istio, Linkerd, Consul Connect)
- Event streaming (Apache Kafka, Pulsar, NATS)
- Distributed data patterns: Saga, Transactional Outbox, Event Sourcing
- Circuit breaker, bulkhead, and timeout patterns
- Distributed caching (Redis Cluster, Hazelcast)
- Distributed tracing and observability architecture

### Design Pattern Compliance
- SOLID principles: SRP, OCP, LSP, ISP, DIP
- Repository, Unit of Work, Specification patterns
- Factory, Strategy, Observer, Command patterns
- Anti-corruption layers and adapter patterns
- Dependency Injection and IoC

### Cloud-Native Architecture
- Kubernetes, Docker Swarm container orchestration
- AWS, Azure, GCP cloud-native patterns
- GitOps and CI/CD pipeline architecture
- Auto-scaling and resource optimization
- Multi-cloud and hybrid cloud strategies

### Security Architecture
- Zero Trust security model
- OAuth2, OpenID Connect, JWT token management
- API security: rate limiting, throttling
- Secret management (Vault, cloud key services)
- Defense in depth strategies

### Performance & Scalability
- Horizontal/vertical scaling patterns
- Multi-layer caching strategies
- Database sharding, partitioning, read replicas
- Asynchronous processing and message queue patterns
- Connection pooling and resource management

### Data Architecture
- Polyglot persistence (SQL + NoSQL)
- Database-per-service in microservices
- Master-slave and master-master replication
- Distributed transactions and eventual consistency
- Real-time processing architectures

## Anti-Pattern Reference

| Anti-Pattern | Symptom | Fix |
|-------------|---------|-----|
| **Anemic Domain** | Entities are data bags, logic in services | Move behavior into domain entities |
| **Fat Controller** | Business logic in controller layer | Extract to use case / service layer |
| **Repository Leakage** | ORM objects exposed to callers | Map to domain entities at boundary |
| **Missing Outbox** | Event published after DB write — not atomic | Add transactional Outbox pattern |
| **No Circuit Breaker** | No fallback on external service failure | Add circuit breaker (Resilience4j, nestjs-resilience4j) |
| **Distributed Monolith** | Microservices sharing a database | Database-per-service with event-based sync |
| **Missing Anti-Corruption Layer** | Domain contaminated by external model | Add ACL/adapter at integration boundary |
| **Over-engineered MVP** | Microservices for early-stage product | Start modular monolith, extract when proven |

## Common Interactions

- "Review this NestJS payment service for Outbox pattern and circuit breaker gaps"
- "Assess whether our bounded context design is correct before we implement"
- "Evaluate this event-driven system for proper decoupling and eventual consistency"
- "Review our API gateway design for security and scalability"
- "Does this database schema support the microservice isolation we need?"
- "Review the architectural trade-offs in this ADR before we accept it"
