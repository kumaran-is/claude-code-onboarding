# Workflow Documentation

Multi-phase workflow guides for every development process in this workspace. Each file covers phases, commands, agents, gates, and common pitfalls.

---

## Ideation & Design

| Workflow | When to Use |
|----------|------------|
| `/brainstorm [topic]` | Solution space still open — explore ≥3 alternatives with trade-offs before committing to an approach |
| [ideation-to-spec.md](ideation-to-spec.md) | Turning an idea into a reviewed spec and plan |
| [architecture-design.md](architecture-design.md) | Designing a new service or system before coding |
| [plan-review.md](plan-review.md) | Structured review + adversarial challenge of an implementation plan |
| [adr-creation.md](adr-creation.md) | Documenting architectural decisions |
| [threat-modeling.md](threat-modeling.md) | STRIDE analysis before building security-sensitive features |

---

## Feature Development

| Workflow | Stack |
|----------|-------|
| [feature-java-spring.md](feature-java-spring.md) | Java 21 / Spring Boot 3.5.x WebFlux |
| [feature-nestjs.md](feature-nestjs.md) | NestJS 11.x / Fastify / Prisma / TypeScript |
| [feature-python-fastapi.md](feature-python-fastapi.md) | Python 3.14 / FastAPI / Pydantic v2 |
| [feature-agentic-ai.md](feature-agentic-ai.md) | LangChain v1.2.8 / LangGraph v1.0.7 |
| [feature-google-adk.md](feature-google-adk.md) | Google ADK / Gemini agents |
| [voice-ai-development.md](voice-ai-development.md) | Gemini Live API real-time voice + TTS — LangGraph and ADK voice pipelines |
| [voice-ai-engine-development.md](voice-ai-engine-development.md) | (skill: `voice-ai-development`, optional) Full voice engine — async worker pipeline, Gemini Live STT, Gemini TTS, interrupt handling, LangGraph or ADK agent |
| [prompt-engineering-patterns.md](prompt-engineering-patterns.md) | Designing agent system prompts, CoT/ToT reasoning, few-shot learning, prompt optimization — LangGraph + ADK |
| [workflow-orchestration-patterns.md](workflow-orchestration-patterns.md) | Temporal durable workflow orchestration — Java 21, Python 3.14, NestJS 11.x |
| [feature-angular-spa.md](feature-angular-spa.md) | Angular 21.x / TailwindCSS / daisyUI; auth plumbing in `angular-spa/reference/web-security.md`, unit tests (Vitest) in `angular-spa/reference/testing-vitest.md` |
| [web-performance-optimization.md](web-performance-optimization.md) | Angular 21.x Core Web Vitals, bundle size, lazy loading, runtime perf |
| [fixing-motion-performance.md](fixing-motion-performance.md) | Angular 21.x CSS animation performance — compositor vs paint, layout thrashing, FLIP, scroll-linked motion |
| [tailwind-v4-patterns.md](tailwind-v4-patterns.md) | Configure Tailwind v4 in Angular — `@theme`, container queries, OKLCH daisyUI themes, Bento layouts, v3→v4 migration |
| [ui-ux-design.md](ui-ux-design.md) | Design system selection — style, palette, typography via ui-ux-pro-max database before writing Angular/Flutter UI |
| [feature-a2ui-renderer.md](feature-a2ui-renderer.md) | Agent-to-UI renderer for Angular |
| [feature-flutter-genui.md](feature-flutter-genui.md) | Flutter GenUI — conversational AI widget rendering via A2UI protocol |
| [feature-flutter-mobile.md](feature-flutter-mobile.md) | Flutter 3.41.x / Riverpod / iOS + Android |
| [flutter-animations.md](flutter-animations.md) | Flutter animations — Rive (interactive state machines) + Lottie (illustrations, loaders) |
| [mobile-developer.md](mobile-developer.md) | React Native / Native Swift-Kotlin / Mobile CI-CD (Fastlane, Codemagic, EAS) |

---

## Database & Vector

| Workflow | When to Use |
|----------|------------|
| [database-schema-design.md](database-schema-design.md) | PostgreSQL schema design, Flyway migrations, ERDs |
| [pgvector-rag-pipeline.md](pgvector-rag-pipeline.md) | pgvector schema + RAG pipeline with PostgreSQL |
| [weaviate-collection-pipeline.md](weaviate-collection-pipeline.md) | Weaviate collection design + RAG pipeline |
| [weaviate-operations.md](weaviate-operations.md) | Day-to-day Weaviate search, Q&A, explore |
| [embedding-model-migration.md](embedding-model-migration.md) | Migrating to a new embedding model (zero downtime) |
| [database-query-optimization.md](database-query-optimization.md) | PostgreSQL query optimization: EXPLAIN analysis, N+1 elimination, cursor pagination, materialized views |
| [postgresql-connection-setup.md](postgresql-connection-setup.md) | PostgreSQL connection pooling (PgBouncer, Prisma, asyncpg, R2DBC), SKIP LOCKED queues, deadlock prevention |

---

## Payments & Subscriptions

| Workflow | When to Use |
|----------|------------|
| [stripe-payment-integration.md](stripe-payment-integration.md) | Stripe subscription billing, payment links, Connect vendor payouts, webhooks |
| [revenuecat-subscription-integration.md](revenuecat-subscription-integration.md) | RevenueCat in-app purchases, entitlements, paywalls, mobile subscription management |

---

## Quality & Testing

| Workflow | When to Use |
|----------|------------|
| [test-driven-development.md](test-driven-development.md) | Red-Green-Refactor TDD cycle, all stacks |
| [test-coverage-audit.md](test-coverage-audit.md) | Multi-stack coverage report, 80% gate, `/tdd` and `/test-coverage` commands |
| [api-testing.md](api-testing.md) | Integration and contract testing for REST APIs |
| [browser-e2e-testing.md](browser-e2e-testing.md) | E2E testing with Chrome DevTools + Browser-Use MCPs |
| [visual-regression-testing.md](visual-regression-testing.md) | Automated visual regression CI/CD for Angular (Playwright/Chromatic/BackstopJS) and Flutter (golden_toolkit) |
| [code-review.md](code-review.md) | Giving code review — `/review-code`, `/review-pr` |
| [receiving-code-review.md](receiving-code-review.md) | Processing and responding to review feedback |
| [pre-commit-validation.md](pre-commit-validation.md) | `/pr-risk`, `/validate-changes` before committing |
| [design-system-compliance.md](design-system-compliance.md) | Design token enforcement, WCAG 2.2 AA audit |
| [accessibility-audit.md](accessibility-audit.md) | WCAG 2.2 AA audit (web + Flutter), axe-core + flutter_test automation, manual keyboard/screen reader testing, CI/CD gate |
| [vibe-code-auditor.md](vibe-code-auditor.md) | Pre-commit audit for AI-generated / prototyped code — hallucination detection, 7-dimension analysis, Production Readiness Score (0-100) |

---

## Security

| Workflow | When to Use |
|----------|------------|
| [security-audit.md](security-audit.md) | OWASP audit, SAST, CVE scan before release |
| [security-hardening.md](security-hardening.md) | Remediating findings from security audit |
| `claude-actions-auditor` skill | Auditing GitHub Actions workflows that invoke `anthropics/claude-code-action` for 9 CI/CD attack vectors |

---

## Shipping & Deployment

| Workflow | When to Use |
|----------|------------|
| [pr-shipping.md](pr-shipping.md) | `/ship`, `/review-pr`, merge, branch cleanup |
| [iterate-pr.md](iterate-pr.md) | Autonomous CI fix loop until green |
| [deployment-ci-cd.md](deployment-ci-cd.md) | GitHub Actions pipeline, Docker, Cloud Run |
| [cloud-run-terraform.md](cloud-run-terraform.md) | GCP infrastructure with Terraform |
| [ios-app-store-release.md](ios-app-store-release.md) | TestFlight → App Store via `asc` CLI |
| [android-google-play-release.md](android-google-play-release.md) | Internal → Play Store via `gpd` CLI |

---

## Operations & Incidents

| Workflow | When to Use |
|----------|------------|
| [bug-fix.md](bug-fix.md) | Structured bug fix with regression test — use `/debug` as entry point |
| [production-incident.md](production-incident.md) | Detect → mitigate → diagnose → post-mortem |
| [tech-debt-cleanup.md](tech-debt-cleanup.md) | Deduplication, dead code removal, dependency audit |
| [documentation-generation.md](documentation-generation.md) | OpenAPI specs, CHANGELOG, diagrams, guides |

---

## Workspace & Tooling

| Workflow | When to Use |
|----------|------------|
| [developer-onboarding.md](developer-onboarding.md) | New developer setup — Claude Code, MCP, stacks |
| [new-skill-creation.md](new-skill-creation.md) | Adding a new skill to `.claude/skills/` |
| [hookify-management.md](hookify-management.md) | Creating and managing Hookify enforcement rules |
| [mcp-server-setup.md](mcp-server-setup.md) | Configuring or building a custom MCP server |
| [subagent-driven-development.md](subagent-driven-development.md) | 3-role SDD pipeline for plan-driven multi-agent work |
| [ralph-loop-autonomous.md](ralph-loop-autonomous.md) | Autonomous iteration loop until completion |
| [build-error-resolution.md](build-error-resolution.md) | Maven/Spring Boot 3.5.x build failures — `java-build-resolver` agent |
| [session-checkpoints.md](session-checkpoints.md) | Named session checkpoints with `/checkpoint` — before/after comparison |
| `rules-distill` command + agent | Promote repeated skill patterns to `.claude/rules/` — `/rules-distill [domain]`, 3-phase pipeline with APPROVE/SKIP/MODIFY per candidate |
