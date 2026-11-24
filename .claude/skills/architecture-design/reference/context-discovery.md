# Context Discovery

> Before suggesting any architecture, gather context. This file is part of the `architecture-design` skill.

## Question Hierarchy (Ask User FIRST)

1. **Scale**
   - How many users? (10, 1K, 100K, 1M+)
   - Data volume? (MB, GB, TB)
   - Transaction rate? (per second/minute)

2. **Team**
   - Solo developer or team?
   - Team size and expertise?
   - Distributed or co-located?

3. **Timeline**
   - MVP/Prototype or long-term product?
   - Time to market pressure?

4. **Domain**
   - CRUD-heavy or business logic complex?
   - Real-time requirements?
   - Compliance/regulations?

5. **Constraints**
   - Budget limitations?
   - Legacy systems to integrate?
   - Technology stack preferences?

## Project Classification Matrix

Use this to calibrate architecture complexity before recommending any pattern.

```
                    MVP              SaaS           Enterprise
+-------------------------------------------------------------------+
| Scale        | <1K           | 1K-100K      | 100K+              |
| Team         | Solo          | 2-10         | 10+                |
| Timeline     | Fast (weeks)  | Medium (months) | Long (years)    |
| Architecture | Simple        | Modular      | Distributed        |
| Patterns     | Minimal       | Selective    | Comprehensive      |
| Example      | FastAPI script | NestJS SaaS | Spring Microservices|
+-------------------------------------------------------------------+
```

### MVP (< 1K users, solo, weeks)
- Simple monolith or modular monolith
- ORM direct access (no Repository abstraction)
- Single PostgreSQL database
- No message queues — synchronous REST
- Deploy to Cloud Run or Railway

### SaaS (1K-100K users, 2-10 team, months)
- Modular NestJS or FastAPI with clear module boundaries
- Repository pattern for testability
- PostgreSQL + Redis cache
- Simple job queue (BullMQ or Celery)
- Firebase Auth or JWT
- Deploy to Cloud Run with autoscaling

### Enterprise (100K+ users, 10+ team, years)
- Microservices with explicit service boundaries (DDD)
- Event-driven with Kafka or Pub/Sub
- Database-per-service
- Service mesh (Istio or Linkerd)
- Full observability (traces, metrics, logs)
- Multi-environment CI/CD with GitOps

## Workspace Tech Stack Mapping

| Classification | Backend | Frontend | Mobile | Database |
|----------------|---------|----------|--------|----------|
| MVP | FastAPI / NestJS | Angular (simple) | Flutter | PostgreSQL |
| SaaS | NestJS + Prisma | Angular + Riverpod | Flutter | PostgreSQL + Redis |
| Enterprise | Spring Boot 4.2 (MVC default, WebFlux when justified) | Angular + state mgmt | Flutter | PostgreSQL + Kafka |

## Contradiction Check

After gathering context, verify:

| If user says... | But also says... | Ask: |
|-----------------|-----------------|------|
| "Quick MVP" | "Need microservices" | Which is the real constraint? |
| "Simple feature" | "Change 5 services" | Is the scope actually bounded? |
| "Low risk" | "Breaking public API" | Which takes precedence? |
| "Solo dev" | "Need Kubernetes" | Is the operational overhead justified? |
