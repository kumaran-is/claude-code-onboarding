# Workspace Agent Catalog

Complete descriptions of all 42 agents available in this workspace (.claude/agents/). Use this to select the right agent for each orchestration role.

Last verified: 2026-03-15

---

## Implementation Agents (produce code)

| Agent | Trigger Phrases | Key Capabilities |
|-------|----------------|-----------------|
| `java-spring-api` | Java, Spring Boot, WebFlux, reactive | Controllers, services, R2DBC repos, DTOs, WebTestClient tests |
| `nestjs-api` | NestJS, Fastify, Prisma, TypeScript | Modules, controllers, guards, interceptors, Vitest tests |
| `python-dev` | Python, FastAPI, Pydantic, async | Async endpoints, Pydantic schemas, pytest tests |
| `flutter-mobile` | Flutter, Dart, Riverpod, Firebase | Cross-platform screens, providers, Firebase integration |
| `angular-spa` | Angular, standalone, signals, TailwindCSS | Standalone components, lazy routing, daisyUI |
| `agentic-ai-dev` | LangGraph, LangChain, agent, RAG | StateGraph, tool nodes, memory, RAG pipelines |
| `google-adk` | Google ADK, Gemini, SequentialAgent | ADK agents, McpToolset, session management |
| `database-designer` | schema design, ERD, migrations | Flyway migrations, index strategy, Firestore collections |
| `deployment-engineer` | CI/CD, Docker, Cloud Run, GitHub Actions | Multi-stage Dockerfiles, Workload Identity, pipeline |
| `terraform-specialist` | Terraform, GCP, Cloud Run, Cloud SQL | Cloud Run v2, Cloud SQL, Artifact Registry, IAM |
| `frontend-design` | landing page, dashboard, design | Production-grade UI with intentional aesthetics |
| `a2ui-angular` | A2UI, agent UI, Angular renderer | Component catalog, recursive renderer, action handlers |
| `mobile-developer` | React Native, native iOS, Android, Fastlane | EAS Update, Detox testing, Fastlane lanes |

---

## Reviewer Agents (read-only, report findings)

### General Quality
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `code-reviewer` | Quality, security, maintainability — any language | APPROVE / NEEDS_REVIEW / BLOCK + severity counts |
| `code-simplifier` | Unnecessary complexity, over-engineering, premature abstraction | Simplification recommendations |
| `comment-analyzer` | Comment accuracy vs actual implementation | Comment rot findings |
| `type-design-analyzer` | TypeScript, Dart, Java, Pydantic type design quality | Encapsulation score per type |
| `dedup-code-agent` | Duplicate code, unused code, dependency bloat | Duplication map |
| `output-evaluator` | LLM-as-Judge: staged changes quality gate | APPROVE / NEEDS_REVIEW / REJECT with scores |

### Security
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `security-reviewer` | OWASP Top 10, secrets, SSRF, injection, unsafe crypto | Severity-bucketed findings |
| `threat-modeling-expert` | STRIDE analysis, attack trees, security architecture | Threat model + risk assessment |
| `flutter-security-expert` | Flutter-specific: secure storage, cert pinning, GDPR | Mobile security + privacy compliance report |
| `silent-failure-hunter` | Swallowed exceptions, missing error states, fallbacks | Silent failure locations with file:line |

### Framework-Specific
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `spring-reactive-reviewer` | Spring WebFlux reactive correctness, Resilience4j, R2DBC | Blocking calls in reactive chains, circuit breaker gaps |
| `nestjs-reviewer` | NestJS module correctness, JWT security, Prisma, tests | Module structure + security findings |
| `riverpod-reviewer` | Riverpod provider types, ref.watch/read, AsyncValue, lifecycle | Provider correctness report |
| `agentic-ai-reviewer` | LangGraph correctness, guardrails, iteration limits, cost | Graph structure + safety findings |

### Database
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `postgresql-database-reviewer` | Query optimization, schema, security, performance | EXPLAIN ANALYZE recommendations |
| `pgvector-schema-reviewer` | Vector columns, HNSW/IVFFlat indexes, dimension alignment | Vector schema validation |
| `weaviate-schema-reviewer` | Collection definition, vectorizer, multi-tenancy | Collection safety report |
| `rag-implementation-reviewer` | Chunking strategy, model pinning, reranking, error handling | RAG pipeline gaps |

### UI/Accessibility
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `accessibility-auditor` | WCAG 2.1, Semantics, focus management, color contrast | Accessibility violation list |
| `ui-standards-expert` | Design tokens, theming, touch targets, responsive layout | Design system compliance report |
| `reality-checker` | Final validation gate — requires screenshot evidence | APPROVED / NEEDS WORK (binary) |

### Testing
| Agent | What It Reviews | Output |
|-------|----------------|--------|
| `pr-test-analyzer` | Behavioral test coverage — critical paths, edge cases, errors | Coverage gap rating 1-10 |

---

## Planning / Architecture Agents

| Agent | Role | Use For |
|-------|------|---------|
| `architect` | Solution architect | C4 diagrams, API contracts, sequence diagrams, ADRs |
| `plan-challenger` | Adversarial plan reviewer | Attacks plan across 5 dimensions before implementation |
| `mermaid-expert` | Diagram specialist | Flowcharts, sequences, ERDs, architecture diagrams |

---

## Support Agents

| Agent | Role | Use For |
|-------|------|---------|
| `error-detective` | Runtime error investigator | Log analysis, stack traces, root cause from runtime data |
| `browser-testing` | Browser automation (web targets only) | E2E flows, Chrome DevTools, performance testing; Flutter mobile E2E is Maestro via `flutter-mobile` |
| `tutorial-engineer` | Content creator | Onboarding guides, feature tutorials |
| `dx-optimizer` | Dev experience | Setup automation, git hooks, IDE config, README |
| `skill-reviewer` | Skills auditor | Checks .claude/skills/ compliance |

---

## Selecting Agents for Common Orchestration Tasks

### NestJS feature review
```
nestjs-reviewer + security-reviewer + silent-failure-hunter + pr-test-analyzer
```

### Spring Boot feature review
```
spring-reactive-reviewer + security-reviewer + silent-failure-hunter + postgresql-database-reviewer (if DB touched)
```

### Flutter feature review
```
riverpod-reviewer + flutter-security-expert + accessibility-auditor + ui-standards-expert
```

### Python/FastAPI feature review
```
code-reviewer + security-reviewer + silent-failure-hunter + pr-test-analyzer
```

### LangGraph agent review
```
agentic-ai-reviewer + security-reviewer + rag-implementation-reviewer (if RAG) + silent-failure-hunter
```

### Pre-merge full audit
```
[stack-specific reviewer] + security-reviewer + silent-failure-hunter + pr-test-analyzer + output-evaluator
```
