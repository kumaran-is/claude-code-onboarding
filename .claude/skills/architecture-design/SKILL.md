---
name: architecture-design
description: "Full-stack system architecture skill for designing C4 diagrams, API contracts, sequence diagrams, deployment topologies, and ADRs. Use when designing new systems, choosing tech stacks, defining service boundaries, or producing architecture documentation before implementation starts."
argument-hint: "[system or feature to design]"
allowed-tools: Bash, Read, Write, Edit
agent: architect
context: fork
metadata:
  triggers: system architecture, design architecture, API contract, deployment topology, tech stack decision, C4 diagram, sequence diagram
  related-skills: ddd-architect, architecture-decision-records, database-schema-designer, openapi-spec-generation
  domain: api-architecture
  role: architect
  scope: design
  output-format: architecture
last-reviewed: "2026-03-15"
---

## Iron Law

Never start implementation without an approved architecture plan; always produce API contracts and sequence diagrams before code.

# Architecture Design Skill

Design system architecture, API contracts, deployment topologies, and technology decisions for full-stack applications.

**Supported Design Artifacts:**
- System context diagrams (C4 model, Mermaid)
- Sequence diagrams (service interactions)
- API contracts (OpenAPI 3.x)
- Deployment topologies (Docker Compose)
- Architecture Decision Records (ADRs)

**Process:**

1. **Analyze Request**
   - Identify which artifacts the user needs
   - Determine scope: single service, multi-service, full system

2. **Load Templates**
   - Read [reference/architecture-templates.md](reference/architecture-templates.md) for diagram and deployment templates
   - For detailed ADR workflows: delegate to the `architecture-decision-records` skill
   - For full OpenAPI spec generation: delegate to the `openapi-spec-generation` skill

3. **Generate Artifacts**
   - Use loaded templates as starting points
   - Adapt to the project's tech stack (Spring Boot, Node.js, Angular, Flutter, PostgreSQL, Firebase)
   - Follow conventions from CLAUDE.md (package structure, naming, reactive patterns)

4. **Present and Iterate**
   - Show generated artifacts with explanations
   - Offer refinement options (add services, change patterns, adjust topology)

## Documentation Sources

Before making architecture decisions, consult these sources:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Docker | `https://docs.docker.com/llms.txt` | Container config, Compose, multi-stage builds |
| MCP Protocol | `https://modelcontextprotocol.io/llms-full.txt` | MCP integration architecture and patterns |
| All libraries | `Context7` MCP | Latest API references for any technology |

## Error Handling

**Unclear artifact type**: Ask user to specify (diagram, API contract, deployment, ADR).

**Ambiguous tech stack**: Default to project conventions in CLAUDE.md or ask for clarification if multiple options exist.

## Reference Files

| File | When to Load |
|------|-------------|
| [reference/architecture-templates.md](reference/architecture-templates.md) | Always — diagram and deployment templates |
| [reference/context-discovery.md](reference/context-discovery.md) | Before recommending any architecture — gather scale, team, timeline context first |
| [reference/pattern-selection.md](reference/pattern-selection.md) | When choosing between architectural patterns — decision trees per concern |
| [reference/implementation-patterns.md](reference/implementation-patterns.md) | When implementing Clean Architecture or Hexagonal Architecture — Python examples |
| [reference/cloud-service-mapping.md](reference/cloud-service-mapping.md) | GCP-primary cross-cloud service equivalents |

**Load order for new system design:**
1. `context-discovery.md` — classify the project (MVP / SaaS / Enterprise)
2. `pattern-selection.md` — choose the right pattern for the complexity
3. `architecture-templates.md` — generate diagrams and deployment topology
4. `implementation-patterns.md` — if Clean Arch or Hexagonal is chosen
