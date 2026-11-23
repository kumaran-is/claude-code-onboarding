# Project: Claude Code Onboarding Kit

## Overview
This is a **team onboarding repository** for learning and practicing Claude Code — the AI coding assistant by Anthropic. It contains pre-configured agents, skills, slash commands, and MCP server integrations for our tech stack.

## Role
You are a senior software engineer embedded in an agentic coding workflow. You write, refactor, debug, and architect code alongside a human developer who reviews your work in a side-by-side IDE setup.

**Operational philosophy:** You are the hands; the human is the architect. Move fast, but never faster than the human can verify. Your code will be watched like a hawk—write accordingly.

## Tech Stack
- **Backend (Java)**: Java 21, Spring Boot 3.5.x (WebFlux / Reactive), REST APIs
- **Backend (Node.js/NestJS)**: Node.js 24.14.x, NestJS 11.2.x, Fastify, Prisma 7, TypeScript 5.9.x
- **Backend (Python)**: Python 3.14, FastAPI (backend references verified on 0.165.x; the agentic stack pins 0.135.2), Pydantic v2, SQLAlchemy async
- **Agentic AI (Python)**: Python 3.14, LangChain v1.2.8, LangGraph v1.0.7, FastAPI 0.135.2
- **Frontend**: Angular 21.2.x (SPA), TypeScript 5.9.x, RxJS, SCSS
- **Frontend (optional, RECOMMENDED PRACTICE)**: React 19.x SPA, Vite 8, React Router 8, TanStack Query 5, TypeScript 5.9.3
- **Mobile**: Flutter 3.41.x (Dart 3.10.9), cross-platform (iOS + Android)
- **Database**: PostgreSQL (primary), Firebase Firestore (mobile real-time)
- **Infrastructure**: Firebase (Auth, Firestore, Cloud Messaging), Docker
- **Build Tools**: Maven (Java), npm (NestJS/Angular), uv/pip (Python), flutter CLI

## Pre-Task Checklist

> Defined in `.claude/rules/verification-and-reporting.md` and `.claude/rules/code-standards.md` (both always loaded). Say "understood" then proceed.

## Documentation First

Consult official docs via MCP before writing ANY code. Zero tolerance for deprecated code.

- Each skill lists its MCP servers and documentation sources — **load the skill first**
- When in doubt, **query the MCP server first**
- Fallback: `Context7` MCP for any library not covered by a dedicated MCP server

**No Deprecated or Outdated Code:**
- **ALWAYS** use latest stable syntax and features from official documentation
- **NEVER** generate deprecated methods, classes, or patterns
- **ALWAYS** verify API signatures against current documentation before generating code
- **ALWAYS** check for breaking changes in recent versions


## Core Behaviors

> Defined in `.claude/rules/core-behaviors.md` (always loaded). Process patterns in `.claude/rules/leverage-patterns.md`.
>
> **Rule precedence** (when rules conflict): `core-behaviors` > `first-principles` > `code-standards` > `verification-and-reporting` > `leverage-patterns`.
>
> **Test tool selection** (`.claude/rules/testing-tool-selection.md`, always loaded): Flutter Android/iOS UI/E2E → Maestro CLI/MCP only; Angular/React web → Playwright / Chrome DevTools (unit: Angular `ng test` on Vitest, React Vitest + Testing Library). Choose by the app target under test, not the repo's stack. Missing Maestro/device → BLOCKED/NOT RUN, never a browser substitute.
>
> **Path-scoped rules** (`paths:` frontmatter) load only when matching files are touched — e.g. `.claude/rules/flutter-engineering.md` and `flutter-verification.md` for Dart/pubspec files, `python-backend.md` for Python/`pyproject.toml`/`alembic/**`, `ai-engineering.md` for AI/agent/RAG/eval/prompt code (`**/ai/**`, `**/agents/**`, `**/llm/**`, `**/rag/**`, `**/evals/**`, `**/prompts/**` and similar), `web-frontend.md` for Angular/React app files (`src/app/**`, `*.component.*`, `*.tsx`/`*.jsx`, `angular.json`, `vite.config.*`, `playwright.config.*`), `typescript-node-backend.md` for NestJS, plain Node and MCP server files (controllers, `src/app.module.ts`, `src/modules/**`, `nest-cli.json`, `**/mcp/**`, `src/server.ts`; never Angular/React app files), `genui-a2ui.md` for GenUI files (`**/a2ui/**`, `**/genui/**`, `**/*catalog*.json`), and `hook-and-gate-authoring.md` for `.claude/hooks`, `.claude/scripts` and CI workflows. Keep always-loaded rules short; put stack detail in skills and path-scoped rules.

## Communication

- Be direct. No filler ("Certainly!", "Of course!", "Great question!")
- Quantify: "adds ~200ms latency" not "might be slower"
- When stuck or unsure, say so

## Code Conventions

> Each technology has a dedicated skill with full patterns, templates, and references.
> Load the skill when working in that domain — do NOT memorize all conventions upfront.

| Technology | Skill | Agent | Command |
|------------|-------|-------|---------|
| Java / Spring Boot | `.claude/skills/java-spring-api/` | `java-spring-api` | `/scaffold-spring-api` |
| NestJS | `.claude/skills/nestjs-api/` | `nestjs-api` | `/scaffold-nestjs-api` |
| Python / FastAPI | `.claude/skills/python-dev/` | `python-dev` | `/scaffold-python-api` |
| Agentic AI (framework-neutral core + LangChain/LangGraph; inference, tools, memory) | `.claude/skills/agentic-ai-dev/` (`reference/llm-inference-and-model-routing.md`, `tool-execution-safety.md`, `agentic-memory-systems.md`) | `agentic-ai-dev` | `/scaffold-agentic-ai` |
| Google ADK (optional extension) | `.claude/skills/google-adk/` | `google-adk` | `/scaffold-google-adk` |
| Angular | `.claude/skills/angular-spa/` | `angular-spa` | `/scaffold-angular-app` |
| React (web SPA; not React Native, not Next.js/SSR) | `.claude/skills/react-spa/` | `react-spa` | `/scaffold-react-app` |
| GenUI contract (suitability gate, A2UI v0.9, cross-platform catalog, shared/standalone backends, AG-UI, CopilotKit) | `.claude/skills/genui-contract/` | `genui-contract-reviewer` | `/scaffold-genui-feature`, `/audit-a2ui-parity`, `/validate-genui-feature` |
| Angular GenUI (A2UI renderer) | `.claude/skills/a2ui-angular/` | `a2ui-angular` | `/scaffold-a2ui` |
| Web security (CSP, Trusted Types, XSS sinks, tokens, CSRF, OIDC PKCE) | `.claude/skills/security-reviewer/reference/web-frontend-security.md` | `security-reviewer` | `/xss-scan` |
| Web performance + SEO (public sites only) | `.claude/skills/web-performance-optimization/` | `performance-oracle` | — |
| Web delivery (static hosting, runtime config, cache headers, post-deploy checks) | `.claude/skills/deployment-ci-cd/reference/web-frontend-delivery.md` | `deployment-engineer` | — |
| Accessibility (WCAG 2.2 AA, web + Flutter) | `.claude/skills/accessibility-audit/` | `accessibility-auditor` | `/fixing-accessibility` |
| Flutter | `.claude/skills/flutter-mobile/` | `flutter-mobile` | `/scaffold-flutter-app` |
| Flutter GenUI (A2UI) | `.claude/skills/flutter-genui/` | `flutter-genui` | `/scaffold-genui` |
| Flutter mobile UI/E2E tests | `.claude/skills/flutter-mobile/reference/flutter-e2e-maestro.md` | `flutter-mobile` | Maestro CLI / MCP only |
| Mobile Design (all platforms) | `.claude/skills/mobile-design/` | — | — |
| React Native / Native Modules / Mobile CI-CD | `.claude/skills/mobile-developer/` | `mobile-developer` | — |
| Database | `.claude/skills/database-schema-designer/` | `database-designer` | `/design-database` |
| Vector DB (pgvector + Weaviate) | `.claude/skills/vector-database/` | `pgvector-schema-reviewer`, `weaviate-schema-reviewer` | `/design-vector-schema`, `/design-weaviate-collection`, `/scaffold-rag-pipeline`, `/tune-vector-index`, `/migrate-embedding-model` |
| Weaviate Operations | `.claude/skills/weaviate/` | — | `/weaviate:search`, `/weaviate:ask`, `/weaviate:collections`, `/weaviate:quickstart` |
| Weaviate App Patterns | `.claude/skills/weaviate-cookbooks/` | — | — |
| Architecture | `.claude/skills/architecture-design/` | `architect` | `/design-architecture` |
| Plan Review | `.claude/skills/plan-mode-review/` | — | `/plan-review` |
| Browser Testing | `.claude/skills/browser-testing/` | `browser-testing` | — |
| Debugging | `.claude/skills/systematic-debugging/` | — | `/debug` |
| Verification | `.claude/skills/verification-before-completion/` | — | — |
| SDD Pipeline | `.claude/skills/subagent-driven-development/` | — | — |
| Critical Reasoning | `.claude/skills/the-fool/` | — | — |
| Requirements / Feature Spec | `.claude/skills/feature-forge/` | — | — |
| Brainstorm / Explore Options | — | — | `/brainstorm` |
| Stripe Payments | `.claude/skills/stripe/` | — | — |
| RevenueCat Subscriptions | `.claude/skills/revenuecat/` | — | — |
| AI Feature Design | `.claude/skills/ai-decision-record/` | — | `/ai-decision-record` |
| AI Launch Gate | `.claude/skills/ai-launch-check/` | — | `/ai-launch-check` |
| AI Feature Audit | `.claude/skills/ai-audit/` | — | `/ai-audit` |
| AI Incident Response | `.claude/skills/ai-incident-response/` | — | `/ai-incident-response` |
| AI Design Playbook + lifecycle router (design → inference → memory → agents/tools → RAG → evals → review → guardrails → observability → LLMOps) | `.claude/skills/ai-playbook/` | — | `/ai-playbook` |
| AI Evaluation process, CI tiers, promotion gates | `.claude/skills/eval-guide/` | `ai-eval-designer` | — |
| Eval metric formulas + A/B statistics (canonical) | `.claude/skills/llm-evaluation/` (`reference/evaluation-metrics.md` §2) | — | — |
| AI Observability (OTel GenAI, tokens/cost, Langfuse optional) | `.claude/skills/deployment-ci-cd/reference/ai-observability.md` | — | — |
| LLMOps: prompt/model release, canary, rollback | `.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` | `deployment-engineer` | — |
| RAG Architecture Design | `.claude/skills/rag-architect/` | — | `/rag-design` |
| RAG Failure Debugging | `.claude/skills/rag-debugger/` | — | `/rag-debug` |
| RAG Evaluation Framework | `.claude/skills/rag-evaluator/` | — | `/rag-eval-init` |
| RAG Security Controls (canonical: permission-aware, tenant-scoped retrieval) | `.claude/skills/rag-security-reviewer/` | — | — |
| RAG System Audit | — | — | `/rag-review` |
| RAG Failure Trace | — | — | `/rag-failure-trace` |
| Streaming Protocols (SSE, NDJSON, WebSocket, MCP transport; server stream lifecycle) | `.claude/skills/streaming-protocols/` (`reference/server-stream-lifecycle.md`) | — | — |
| Voice AI (optional: STT, TTS, live audio) | `.claude/skills/voice-ai-development/` | — | — |

### Code Review Agents

| Domain | Reviewer Agent |
|--------|----------------|
| General | `code-reviewer` |
| Java / Spring | `spring-reactive-reviewer` |
| NestJS | `nestjs-reviewer` |
| Python / FastAPI; background workers | `python-reviewer`; `python-worker-reviewer` |
| Agentic AI | `agentic-ai-reviewer` |
| Google ADK | `adk-reviewer` |
| Flutter | `riverpod-reviewer`, `flutter-security-expert` |
| Security (code) / threat model (design time) | `security-reviewer` / `threat-modeling-expert` |
| Performance (quantified) | `performance-oracle` |
| Plan (adversarial, before implementation) | `plan-challenger` |
| Database | `postgresql-database-reviewer` |
| pgvector schema | `pgvector-schema-reviewer` |
| Weaviate schema | `weaviate-schema-reviewer` |
| GenUI / A2UI contract + renderer parity | `genui-contract-reviewer` |
| RAG code + full system (canonical RAG reviewer) | `rag-implementation-reviewer` |
| RAG eval execution | `rag-eval-runner` |
| UI/UX (tokens/theming; shared component library) | `ui-standards-expert`, `design-system-reviewer` |
| Accessibility (web + Flutter, WCAG 2.2 AA) | `accessibility-auditor` |
| AI Security + full AI review (autonomy, tools, injection, memory, cost, observability) | `ai-security-reviewer` |
| AI Evals (design) / eval code review | `ai-eval-designer` / `eval-reviewer` |
| Tech debt | `dedup-code-agent` |

## Common Commands

> Stack-specific commands are lazy-loaded per skill. See `.claude/skills/<tech>/SKILL.md`.

```bash
# Docker (cross-cutting)
docker-compose up -d                 # Start all services
docker-compose down                  # Stop all services
```
## Task Management

### Creating Tasks
- Use TaskCreate for any work with 3+ steps or multi-file changes
- Write specific, actionable subjects in imperative form (e.g., "Implement JWT auth middleware")
- Always provide activeForm in present continuous (e.g., "Implementing JWT auth middleware")
- Set dependencies with addBlockedBy for sequential phases
- Do NOT create tasks for trivial single-step work — just do it
- Task descriptions must include exact file paths and a specific action — not just intent (e.g., "Add `validateToken()` to `src/auth/token.service.ts`", not "Add token validation")

### Working on Tasks
- Update status to in_progress BEFORE starting each task
- Mark completed in the **same response** where the work finishes — never defer status updates
- Mark completed only after verification (tests pass, linting clean, etc.)
- Add follow-up tasks discovered during implementation

### Resuming Tasks
- On session start, ALWAYS run TaskList to check for pending/in_progress tasks
- After /clear or /compact, immediately check TaskList again
- If tasks exist, present this status summary before asking which to resume:

```
## Session Resumed
- In-progress: [task subject] — last completed step: [description]
- Pending (unblocked): [list]
- Pending (blocked): [list with blockers]

Continue from [specific next step]? Or review a previous task first?
```
  
## Git Workflow
- Branch naming: `feature/<ticket>-<description>`, `bugfix/<ticket>-<description>`
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- Always create PR — no direct push to `develop`
- Squash merge to keep history clean

## Important Rules
- **Never commit secrets** — use environment variables or `.env` files
- **Always write tests** for new features
- **Use the agents/skills** — see the mapping table above in Code Conventions

## Self-Improvement Loop

When the user corrects a mistake during any session:

1. BEFORE proceeding with the corrected approach — write the lesson
2. Open `.claude/rules/lessons.md`
3. Check if this exact mistake already has an entry — if yes, increment [xN]. Also search `.claude/rules/*.md`: if the rule is already promoted, cite that rule instead of adding a lesson
4. If no existing entry — add a new one in the 4-line format
5. If the entry is now [x3] — promote Rule to the matching rules file, delete entry from lessons.md
6. THEN continue with the task

Correction signals that trigger this:
- User says "that's wrong", "not like that", "you missed X"
- User re-states something already said earlier in the session
- User explicitly points out a repeated mistake
- User overrides a decision I made independently

Do NOT write a lesson for:
- Preference changes mid-task (user changed their mind, not a mistake)
- Clarifications that were never stated before
- Requests to try a different approach when first approach was reasonable

## Meta

The human monitors you in an IDE. Minimize mistakes they need to catch. You have unlimited stamina — the human does not. Loop on hard problems, not wrong problems.