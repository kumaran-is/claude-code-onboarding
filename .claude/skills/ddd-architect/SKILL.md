---
name: ddd-architect
allowed-tools: Read, Write, Edit
argument-hint: "[domain or bounded context]"
description: "Comprehensive Domain-Driven Design analysis and architecture generation — use when designing bounded contexts, defining aggregates, creating context maps, or decomposing systems into microservices or modular monolith. Triggers: DDD, domain-driven design, bounded context, aggregate design, context map, subdomain, ubiquitous language, strategic/tactical design, domain model."
metadata:
  triggers: DDD, domain-driven design, bounded context, aggregate design, context map, subdomain, ubiquitous language, strategic design, tactical design, domain model, modular monolith decomposition
  related-skills: architecture-design, architecture-decision-records, database-schema-designer
  domain: api-architecture
  role: architect
  scope: system-design
  output-format: architecture
last-reviewed: "2026-03-15"
---

## Iron Law

Never design domain boundaries without analyzing existing bounded contexts first; always map ubiquitous language before proposing aggregates.


# DDD Architect Skill

Generate comprehensive Domain-Driven Design architecture documentation following industry standards. Tech-stack agnostic — works with any language, framework, or cloud platform.

## How This Skill Works

This skill uses **progressive disclosure**. Read the reference files as needed:

| Phase | Reference File | When to Load |
|-------|---------------|--------------|
| Strategic Design | `reference/strategic-design.md` | Always — start here |
| Tactical Design | `reference/tactical-design.md` | After strategic phase |
| Technical Architecture | `reference/technical-architecture.md` | After tactical phase |
| Implementation | `reference/implementation-guidelines.md` | After architecture phase |
| Output Templates | `assets/templates/` | When generating documents |

## Execution Protocol

### Step 0: Gather Context

Before starting, confirm you have:

1. **Domain description** — what does the business do?
2. **Requirements** — user stories, PRDs, or feature lists (files or description)
3. **Tech stack** — languages, frameworks, databases, cloud platform
4. **Architecture style** — microservices, modular monolith, or undecided
5. **Team structure** — number of teams, ownership boundaries (if known)
6. **Existing system** — greenfield or brownfield? Migration constraints?

If any are missing, ask before proceeding. Do NOT assume.

### Step 1: Strategic Design

Read `reference/strategic-design.md`, then:

1. Identify core, supporting, and generic subdomains
2. Classify by strategic value and complexity
3. Discover bounded contexts using linguistic analysis
4. Define ubiquitous language per context
5. Create context map with relationship patterns
6. Map team ownership (Conway's Law alignment)

**Output:** `docs/ddd/01-strategic-design.md`

### Step 2: Tactical Design

Read `reference/tactical-design.md`, then:

1. Design aggregates with invariants and consistency boundaries
2. Identify entities, value objects, domain events
3. Define repository interfaces and domain services
4. Design sagas for cross-aggregate workflows
5. Apply CQRS if read/write patterns diverge

**Output:** `docs/ddd/02-tactical-design.md`

### Step 3: Technical Architecture

Read `reference/technical-architecture.md`, then:

1. API design aligned with aggregates
2. Database schema per bounded context
3. Integration patterns (events, sync, anti-corruption layers)
4. Cloud-native considerations (containers, scaling, observability)

**Output:** `docs/ddd/03-technical-architecture.md`

### Step 4: Implementation Guidelines

Read `reference/implementation-guidelines.md`, then:

1. Package/module structure following DDD layers
2. Testing strategy (unit, integration, contract, E2E)
3. Security architecture
4. CI/CD and deployment patterns

**Output:** `docs/ddd/04-implementation-guidelines.md`

### Step 5: Final Deliverables

Generate remaining documents:

- `docs/ddd/00-executive-summary.md` — 1-2 page overview with key decisions and risks
- `docs/ddd/05-implementation-roadmap.md` — phased delivery plan
- `docs/ddd/appendix-glossary.md` — ubiquitous language glossary
- `docs/ddd/appendix-adrs.md` — architectural decision records

## Quality Gate

Before marking any phase complete, verify:

- [ ] Business alignment — solution addresses actual business needs
- [ ] Low coupling between contexts, high cohesion within
- [ ] Every aggregate has defined invariants
- [ ] Every domain event has a clear trigger and consumer
- [ ] Context map shows ALL integration points
- [ ] No anemic domain models (logic in services instead of entities)
- [ ] Conway's Law considered — context boundaries match team boundaries
- [ ] Trade-offs documented for every non-obvious decision

## Important Rules

- **Tech-stack agnostic**: Use the project's actual tech stack for code examples, not hardcoded defaults
- **No cargo-culting**: Don't apply patterns just because DDD says so — justify every pattern
- **Right-size aggregates**: Small aggregates (1-3 entities) are almost always better than large ones
- **Events over coupling**: Prefer domain events between contexts over direct calls
- **Ubiquitous language is mandatory**: Every document must use domain language, not technical jargon
- **Diagrams**: Use Mermaid syntax for all diagrams (context maps, sequence, class, C4)

## Error Handling

**Ambiguous bounded contexts**: When domain boundaries are unclear, map the dependencies and ask for clarification before committing to a context map.

**Conflicting ubiquitous language**: When the same term means different things in different contexts, document both meanings and define an anti-corruption layer.
