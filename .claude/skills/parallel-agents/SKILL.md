---
name: parallel-agents
description: "Patterns for dispatching several Claude Code subagents in parallel (multi-perspective review, cross-domain features, parallel analysis) using only agents that exist in .claude/agents/. Use when coordinating 2+ agents. Plan-driven sequential work → subagent-driven-development."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: comprehensive review, multi-perspective analysis, parallel agents, orchestrate agents, coordinate agents, run multiple agents, full audit, cross-domain implementation
  related-skills: subagent-driven-development, multi-agent-patterns, multi-agent-brainstorming, architecture-design
  domain: workflow
  role: architect
  scope: design
  output-format: report
last-reviewed: "2026-03-15"
---

## Iron Law

**USE THIS WORKSPACE'S ACTUAL AGENTS — never reference placeholder agents (security-auditor, backend-specialist) that don't exist here; always dispatch from the agents that exist in .claude/agents/ (check with `ls .claude/agents`)**

**Explanation:** Dispatching a non-existent agent silently fails. Every agent name in this skill maps to a real .md file in .claude/agents/.

# Parallel Agents Orchestration

Orchestration guide for coordinating multiple specialized agents through Claude Code's native Agent tool. Keeps all orchestration within Claude's control using the built-in Agent tool and TeamCreate.

---

## When to Use Orchestration

**Good for:**
- Complex tasks requiring multiple expertise domains (security + code quality + tests)
- Comprehensive reviews (architecture + security + accessibility)
- Feature implementation needing backend + frontend + database work
- Full pre-deploy audits across all stack layers

**Not for:**
- Simple, single-domain tasks (use the relevant specialist agent directly)
- Quick fixes or small changes within one file
- Tasks where one agent suffices

**Decision rule:** If dispatching more than 1 agent, use this skill for orchestration patterns and synthesis protocol.

---

## Workspace Agent Catalog

Load `references/workspace-agent-catalog.md` for full descriptions. Quick reference:

| Agent | Domain | Use For |
|-------|--------|---------|
| `code-reviewer` | General | Quality, security, maintainability for any language |
| `security-reviewer` | Security | OWASP Top 10, input validation, secret scanning |
| `threat-modeling-expert` | Security | STRIDE analysis, attack trees, security architecture |
| `silent-failure-hunter` | Error Handling | Swallowed exceptions, missing error states |
| `spring-reactive-reviewer` | Java/Spring | Reactive correctness, Resilience4j, R2DBC |
| `nestjs-reviewer` | NestJS | Module correctness, JWT, Prisma patterns |
| `riverpod-reviewer` | Flutter | Provider types, ref usage, AsyncValue handling |
| `agentic-ai-reviewer` | LangGraph | Graph correctness, guardrails, cost, production readiness |
| `postgresql-database-reviewer` | PostgreSQL | Query optimization, schema, security, performance |
| `pgvector-schema-reviewer` | pgvector | Vector schema, index alignment, embedding model |
| `weaviate-schema-reviewer` | Weaviate | Collection definition, vectorizer, multi-tenancy |
| `rag-implementation-reviewer` | RAG | Chunking, model pinning, reranking, error handling |
| `accessibility-auditor` | Accessibility (web + Flutter) | WCAG 2.2 AA, semantics, focus management |
| `ui-standards-expert` | UI/UX | Design tokens, theming, touch targets |
| `flutter-security-expert` | Flutter | Secure storage, certificate pinning, GDPR |
| `dedup-code-agent` | Tech Debt | Duplication, unused code, dependency bloat |
| `plan-challenger` | Planning | Adversarial plan review (5 attack dimensions) |
| `output-evaluator` | Quality Gate | LLM-as-Judge: APPROVE / NEEDS_REVIEW / REJECT |
| `pr-test-analyzer` | Testing | Behavioral coverage gaps, critical paths |
| `architect` | Architecture | C4 diagrams, API contracts, ADRs |
| `java-spring-api` | Java | Spring Boot WebFlux implementation |
| `nestjs-api` | NestJS | NestJS modules, controllers, services |
| `python-dev` | Python | FastAPI services, async patterns |
| `flutter-mobile` | Flutter | Cross-platform mobile features |
| `angular-spa` | Angular | Standalone components, signals, routing |
| `agentic-ai-dev` | Agentic AI | LangChain/LangGraph agents |
| `google-adk` | ADK | Google ADK agents, Gemini integration |
| `database-designer` | Database | Schema design, ERD, migrations |
| `deployment-engineer` | CI/CD | GitHub Actions, Docker, Cloud Run |
| `terraform-specialist` | GCP Infra | Cloud Run, Cloud SQL, Artifact Registry |
| `frontend-design` | Design | Landing pages, dashboards, visual identity |
| `a2ui-angular` | A2UI | Agent-to-User Interface Angular renderers |
| `mobile-developer` | React Native | React Native, native iOS/Android, Fastlane |
| `browser-testing` | Testing | Web targets only: Chrome DevTools, E2E flows, performance (Flutter mobile E2E = Maestro via `flutter-mobile`) |
| `error-detective` | Debugging | Log analysis, stack traces, root cause |
| `comment-analyzer` | Documentation | Comment accuracy vs implementation |
| `code-simplifier` | Refactoring | Complexity reduction, over-engineering |
| `type-design-analyzer` | Types | TypeScript, Dart, Java type design quality |
| `mermaid-expert` | Diagrams | Flowcharts, sequences, ERDs |
| `tutorial-engineer` | Education | Onboarding guides, feature tutorials |
| `dx-optimizer` | Dev Experience | Tooling, automation, local dev setup |
| `skill-reviewer` | Skills | Skill file compliance audit |
| `reality-checker` | Validation | Visual evidence gate before PR merge |

---

## Orchestration Patterns

Load `references/orchestration-patterns.md` for full pattern details.

### Pattern 1: Comprehensive Feature Review

For any feature touching security-sensitive code, database, or multiple services:

```
Step 1: code-reviewer          → overall quality gate
Step 2: [stack-specific reviewer] → framework-specific patterns
Step 3: security-reviewer      → OWASP + auth + input validation
Step 4: silent-failure-hunter  → error handling completeness
Step 5: pr-test-analyzer       → behavioral test coverage
Step 6: Synthesize all findings
```

### Pattern 2: Pre-Deploy Audit

Before merging any significant feature branch:

```
Parallel:
  security-reviewer     → security findings
  [stack reviewer]      → framework correctness
  pr-test-analyzer      → test coverage gaps
Sequential:
  output-evaluator      → APPROVE / NEEDS_REVIEW / REJECT verdict
```

### Pattern 3: Full Flutter Feature

```
riverpod-reviewer         → state management
flutter-security-expert   → secure storage, GDPR
accessibility-auditor     → WCAG 2.2 AA (web + Flutter)
ui-standards-expert       → design tokens, touch targets
silent-failure-hunter     → error handling in async code
```

### Pattern 4: Agentic AI System Review

```
agentic-ai-reviewer       → graph correctness, guardrails
security-reviewer         → prompt injection, input validation
rag-implementation-reviewer     → chunking, model pinning (if RAG used)
silent-failure-hunter     → tool error handling
```

---

## Synthesis Protocol

Load `references/synthesis-protocol.md` for the full template.

After all agents complete:

```markdown
## Orchestration Synthesis

### Task Summary
[What was accomplished]

### Agent Contributions
| Agent | Key Finding |
|-------|------------|
| [agent] | [finding] |

### Consolidated Recommendations (severity-ordered)
1. **CRITICAL** — [issue] — must fix before merge
2. **HIGH** — [issue] — should fix before merge
3. **MEDIUM** — [issue] — fix in follow-up PR
4. **LOW** — [issue] — note for tech debt backlog

### Verdict
[APPROVE | NEEDS_REVIEW | BLOCK] — based on finding severity
```

---

## Constraints

### MUST DO
- Only dispatch agents that exist in `.claude/agents/` (the catalog above is a subset; `ls .claude/agents` is authoritative)
- Pass explicit context to every agent — agents do NOT inherit CLAUDE.md or conversation history
- Produce a single synthesized report, not separate outputs per agent
- Include test coverage review (pr-test-analyzer) for any code-modifying orchestration

### MUST NOT DO
- Dispatch agents with only "review this code" — always pass specific context and scope
- Run more agents than needed — match agent count to actual coverage gaps
- Skip synthesis — raw agent outputs are not a deliverable

---

## Knowledge Reference

Agent orchestration, multi-agent coordination, parallel dispatch, reviewer agents, synthesis protocol, pre-deploy gate, Claude Code Agent tool, TeamCreate, context passing
