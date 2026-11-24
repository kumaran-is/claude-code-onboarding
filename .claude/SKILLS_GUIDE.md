# Skills Guide

> Complete skill catalog for Claude Code Onboarding Kit. Use this to find the right skill for any task.
>
> 158 skills across 10 domains. Each skill is loaded with `/skill-name` or via `Skill` tool.
>
> **Lazy-load pattern:** Each SKILL.md is a routing document only. Detailed patterns live in `reference/` files within each skill directory. Load the reference file explicitly when the detail is needed — do not expect it to be loaded automatically.

---

## Quick Reference by Domain

### Backend (28 skills)
- **adk-deploy-guide**: Used before deploying any ADK agent to Google Cloud — covers Cloud Run, Agent Engine, event-driven (Pub/Sub, Eventarc, BigQuery Remote Function), Terraform, and CI/CD.
- **adk-eval-guide**: Used when evaluating ADK agents, running `adk eval`, writing evalsets and configuring the 13 documented criteria with their score scales and directions (e.g. `hallucinations_v1` is higher-is-better: gate on a minimum). Covers LLM-as-judge config, user simulation, multimodal eval, and the CI trap that `adk eval` does not fail the process on failed cases.
- **llm-evaluation**: Canonical home for metric formulas (`reference/evaluation-metrics.md` §2: Recall@K, Precision@K, MRR, nDCG with executed worked examples and edge cases) and statistics (`ab-testing.md`: paired tests for same-case comparisons, McNemar, power and sample size, fail-closed regression detection), plus trajectory scoring. Eval process and CI tiers live in eval-guide.
- **eval-guide**: AI evaluation process and tooling (DeepEval, Ragas, Giskard, Promptfoo, Langfuse, Phoenix, adk eval): pre-flight, verdict precedence (deterministic checks outrank the judge), every planned case accounted for (skipped is never pass), median-of-3 judge trials with no rerun-until-green, AI test layers with fake models, golden-set discipline and versioning, CI tiers R1-R4, prompt regression and promotion gates, prompt registry (`reference/langfuse-prompts.md`), pytest harness; evaluation-program adoption (inventory, cadences, domain concerns, organisation-owned checklist: `reference/eval-program-adoption.md`).
- **deployment-ci-cd**: CI/CD, health endpoints, env validation and Python supply chain, plus `reference/python-observability.md` (canonical logging, `log_exception`, request id), `reference/ai-observability.md` (OTel GenAI semconv incl. `gen_ai.provider.name`, agent/tool/retrieval/rerank spans, TTFT, token and cost metrics, content-capture redaction, Langfuse v3 optional, SLOs, drift, incident replay) and `reference/llmops-release-and-rollout.md` (prompt/model versioning, eval-gated promotion, canary and rollback for prompt/config changes, provider migration, provenance, feedback loop), plus `reference/flutter-ci.md` (pinned Flutter PR gate; Maestro advisory, BLOCKED without a device). The toolkit itself is gated in CI by `.github/workflows/toolkit-lint.yml` (skill, agent, command and testing-tool lints, `bash -n`, hook selftests).
- **adk-observability-guide**: Used when configuring tracing (Cloud Trace), prompt-response logging, BigQuery Agent Analytics, or SLO-based alerting for ADK agents — covers 4 observability tiers. Reference files: `reference/cloud-trace-and-logging.md` (Tiers 1-2), `reference/bigquery-agent-analytics.md` (Tier 3), `reference/slo-alerting.md` (Tier 4 — burn-rate alerting, error budget tracking, dual-window PromQL patterns).
- **agentic-ai-coding-standard**: Provides coding standards for Python agentic AI services with LangChain/LangGraph, covering state management, tool definitions, graph structure, error handling, and observability.
- **ai-playbook**: AI lifecycle router and design playbook. SKILL.md maps each stage (design → inference → context/memory → agents/tools → RAG → evals/testing → review → guardrails → observability → LLMOps → streaming/voice) to its canonical skill, reference, agent and command; `playbook.md` holds principles, operating controls, the deterministic-vs-probabilistic control table, security and launch/ops; `reference/engineering-guardrails.md` is the canonical home of guardrails G1–G24 and the ten laws L1–L10 (action tiers A0–A4); `reference/data-governance-privacy.md` covers data classes, egress authorization, retention, erasure propagation and purpose limits.
- **ai-decision-record**: 18-question structured questionnaire to document an AI feature before building — problem framing, design choices, eval strategy, rollback plan, risk register. Required input for ai-launch-check. Use at feature kickoff.
- **ai-launch-check**: Pre-flight gate for shipping AI features — 10 questions, 16 artifacts checklist, 8 kill-switch tests. Outputs GO / NO-GO / GO-WITH-EXCEPTIONS. Requires completed Decision Record. Use before any AI feature goes to production.
- **ai-audit**: Orchestrates a 5-phase audit of existing AI features (reverse-engineer Decision Record, security subagent, eval subagent, launch check, remediation plan). Use to audit a shipped AI feature or after an incident.
- **ai-governance**: Enterprise AI governance records and controls: risk classification (Low–Critical), autonomy levels A0–A4 with quantitative promotion gates, human approval records, control register and evidence, AI BOM, production readiness, regulatory register, AI incident records, scorecard KPIs. Ten JSON Schemas plus a stdlib validator (`scripts/validate_governance_record.py --selftest`). Use when assessing AI risk, declaring or promoting autonomy, building governance evidence or auditing governance readiness. Not for eval metrics (eval-guide) or runtime guardrail code (ai-playbook).
- **ai-incident-response**: 4-stage AI incident procedure — stabilize, triage, investigate, learn. Covers rollback decisions, kill-switch firing, crime-scene log capture, root-cause investigation, post-mortem template, eval gap identification; `reference/runbook-playbooks.md` holds incident types I1–I11, SEV1–SEV4, the containment ladder and the organisation-owned adoption checklist. Use when a production AI feature is failing.
- **agentic-ai-dev**: Framework-neutral core for production AI agents with LangChain v1.5.2 / LangGraph v1.2.24 extensions (Python 3.14, FastAPI). Canonical references: `llm-inference-and-model-routing.md` (provider abstraction, sampling/reasoning controls, structured outputs, timeouts/retries/429, fallback traps, cache-key scoping, token budgets, multimodal input limits), `tool-execution-safety.md` (tool contracts, server-injected scope, allowlists, side-effect idempotency, budgets/recursion limits, approval gates via interrupt + `Command(resume=...)`, compensation, durable resume) and `agentic-memory-systems.md` (scoped memory, checkpointers, poisoning defences).
- **multi-agent-patterns**: Architectural reference for multi-agent system design — Supervisor/Orchestrator, Peer-to-Peer/Swarm, and Hierarchical patterns with token economics (~15× cost multiplier), context isolation strategies, telephone game fix (`forward_message`), consensus mechanisms, and failure mitigations. Primary use: LangGraph, ADK, Claude Code orchestration design. Reference files: `architectural-patterns.md`, `token-economics.md`, `failure-modes.md`.
- **google-adk**: Google ADK (Agent Development Kit) Python skill for building AI agents with Gemini models,
  SequentialAgent, ParallelAgent, LoopAgent, FunctionTool, McpToolset, session management, memory, callbacks,
  and FastAPI integration. Reference files: `adk-core-patterns.md`, `adk-structured-output.md`,
  `adk-agent-types.md`, `adk-agent-handoff.md`, `adk-tools-basic.md`, `adk-tools-callbacks.md`,
  `adk-memory-artifacts.md`, `adk-fastapi-integration.md`, `adk-testing.md`, `adk-project-config.md`.
- **gemini-api-dev**: Direct Gemini API development with `google-genai` (Python) and `@google/genai` (TypeScript/NestJS). Use when making direct Gemini model calls without the ADK framework — covers multimodal inputs (image/audio/video), function calling, structured JSON output, context caching, embeddings, and code execution sandbox. Current model: `gemini-3.1-flash` (default), `gemini-3.1-pro`. Iron law: always fetch `https://ai.google.dev/gemini-api/docs/llms.txt` before writing code. Distinct from `google-adk` (framework/agents) — this is the raw API layer.
- **voice-ai-development**: OPTIONAL voice extension (single voice home; absorbed the former voice-ai-engine-development skill). Batch vs streaming STT vs live speech-to-speech, WebSocket voice sessions with auth before accept, caps and backpressure, turn detection and barge-in, text fallback, voice privacy/logging, async worker pipelines, and provider references (Gemini Live API, Gemini TTS, LangGraph, ADK). Model ids and voices come from settings, not hard-coded.
- **prompt-engineering-patterns**: Advanced prompt engineering for LangGraph and Google ADK — few-shot learning, chain-of-thought, Tree-of-Thought, self-consistency, system prompt design, prompt optimization, and reusable templates. Use when designing agent system prompts, optimizing LLM outputs, implementing structured reasoning, or debugging inconsistent model responses. Supports both LangChain/LangGraph (`SystemMessage`) and Google ADK (`instruction=`). Reference files: `reference/chain-of-thought.md` (CoT, ToT, self-consistency + LangGraph/ADK code), `reference/few-shot-learning.md` (dynamic example selection), `reference/system-prompts.md` (role + constraints + format design), `reference/prompt-optimization.md` (A/B testing, versioning, metrics), `reference/prompt-templates.md` (reusable templates), `reference/prompt-template-library.md` (index of 15 copy-paste templates split into `prompt-library-structured-output.md`, `prompt-library-code-and-grounding.md` and `prompt-library-writing-and-advisory.md`); PromptOps lifecycle (prompt cards, model pinning, §15 change matrix, promotion, rollback, drift: `reference/promptops-lifecycle.md`) with a stdlib PromptRegistry runtime and tests in `assets/prompts-scaffold/promptops/`.
- **java-coding-standard**: Activated when reviewing Java code or enforcing coding standards in Spring Boot services, covering naming conventions, immutability patterns, Optional usage, streams, and exception handling.
- **java-spring-api**: Provides patterns and templates for Java 21 Spring Boot 3.5.x WebFlux REST API development, activated when creating controllers, services, repositories, DTOs, or reactive tests.
- **mcp-builder**: Used when building MCP (Model Context Protocol) servers to integrate external APIs or services: Python (MCP SDK v2 `MCPServer`) and Node/TypeScript (MCP SDK v2 on Node 26 LTS, TypeScript 6.0.3, protocol 2026-07-28; stdio or Streamable HTTP on Fastify; OAuth bearer gate and per-tool allowlists; OpenTelemetry JS 3.x). Scaffold a new TypeScript server with `/scaffold-mcp-server` (templates in `mcp-builder/assets/scaffold-templates-core.md` and `scaffold-templates-http-ops.md`; verified end-to-end on Node 26.13.1 / TS 6.0.3, 2026-11-23).
- **nestjs-api**: Provides patterns and templates for NestJS 11.x with Fastify, Prisma ORM, and TypeScript 5.x development, activated when creating modules, controllers, services, DTOs, guards, interceptors, or tests.
- **nestjs-coding-standard**: Activated when reviewing NestJS/TypeScript code or enforcing coding standards in NestJS 11.x services, covering naming conventions, TypeScript strictness, DTO patterns, and module organization.
- **typescript-advanced-types**: Master TypeScript's advanced type system for Angular 22.x, NestJS 11.x, and MCP Builder — covers generics, conditional types, mapped types, template literal types, and custom utility types (DeepPartial, DeepReadonly, Branded). Load alongside nestjs-api (DTO design), angular-spa (service factories), or mcp-builder (Zod schemas). 717-line implementation playbook in `resources/`.
- **typescript-expert**: TypeScript infrastructure specialist for monorepo project references (`composite: true`), tsc performance diagnostics (`--extendedDiagnostics`), ESM/CJS interop, strict mode migration, and `.d.ts` authoring. Use for project-level TypeScript decisions; defer to framework-specific skills for implementation patterns. Ships with `tsconfig-strict.json`, `utility-types.ts`, `typescript-cheatsheet.md`, and `ts_diagnostic.py`.
- **typescript-pro**: Pointer only — merged into typescript-advanced-types (type design, shared contracts) and typescript-expert (tsconfig, type-check commands).
- **python-dev**: Provides patterns and templates for Python 3.14 development with FastAPI and modern tooling, activated when creating Python APIs, scripts, data processing pipelines, or pytest tests. Reference files: `fastapi-templates.md` (project structure, models, routes), `python-advanced-patterns.md` (profiling, benchmarking), `fastapi-rate-limiting.md` (`limits` async dependency, Redis), `fastapi-auth-security.md` (JWT, bcrypt, RBAC, PBAC, OAuth2PasswordBearer), `fastapi-error-handling.md` (exception hierarchy, async retry, circuit breaker). Also: `fastapi-architecture-and-config.md`, `fastapi-authorization-boundaries.md`, `sqlalchemy-async-sessions-and-transactions.md` (canonical session/transaction ownership), `alembic-migration-safety.md`, `reliability-idempotency-retries-outbox.md`, `asyncio-concurrency-and-tasks.md`. Auth is PyJWT + pwdlib (not python-jose/passlib).
- **python-patterns**: Python architecture decision-making for framework selection (FastAPI/Django/Flask), async vs sync patterns, type hint strategy, project structure, and background task selection. Load BEFORE `python-dev` when the approach is unclear or multiple frameworks are viable.
- **pydantic-models-py**: Pydantic v2 multi-model pattern for clean API contracts — Base, Create, Update, Response variants with camelCase aliases and PATCH support. Use when defining FastAPI request/response schemas or data validation models.
- **uv-package-manager**: Comprehensive uv workflows for Python 3.14 — lockfiles (`uv lock`, `uv sync --frozen`), Python version pinning, monorepo workspaces, Docker cache mounts, GitHub Actions CI caching, and migration from pip/Poetry. Load when working with uv beyond the basic `uv init`/`uv add` commands in `python-dev`.
- **python-packaging**: Python project structure patterns — pyproject.toml for services and internal tools, source vs flat layout decision, CLI entry points with Click/argparse, dynamic versioning, and editable installs. Use when structuring a new Python project or building internal CLI tools.
- **docker**: Use when writing or reviewing Dockerfiles, docker-compose files, or .dockerignore for any backend service. Covers multi-stage builds, container security hardening, and Docker Compose orchestration for NestJS/Node 24, Spring Boot WebFlux 3.5.x/Java 21, Python FastAPI 3.14, and TypeScript/Fastify/Node 24. Reference files: `reference/dockerfiles.md` (copy-ready Dockerfiles for all 5 stack variants), `reference/compose-patterns.md` (dev/prod compose, Docker secrets), `reference/advanced-patterns.md` (build cache, multi-arch, distroless, diagnostics), `assets/docker-review-checklist.md`.
- **gcp-cloud-run**: Use for Cloud Run Functions (event-driven Pub/Sub, Storage, HTTP webhooks), cold start optimization, and anti-pattern prevention for all 4 backend stacks. For Cloud Run service deployment use deployment-engineer agent.
- **gcp-finops**: GCP cost optimization, FinOps, and resilience skill. Use for GCP billing budget alerts, committed use discounts (CUD), sustained use discounts (SUD), cost allocation labels, GCP Recommender analysis, Cloud SQL PITR setup, multi-region DR planning, and RTO/RPO target mapping for Cloud Run + Cloud SQL + Firestore workloads.
- **terraform-skill**: Terraform/OpenTofu best practices, testing strategy, naming conventions, code structure standards, and CI/CD integration. Load BEFORE writing any Terraform module or environment config. Covers: testing decision tree (native `terraform test` 1.6+ with mock providers vs Terratest), naming conventions (`this` for singletons, context-prefixed variables), resource/variable block ordering, `count` vs `for_each` decision guide, version constraint strategy (`~> 1.9.0`, `~> 8.12` for google provider), and GitHub Actions pipeline (validate → test → plan → apply). GCP-primary for this workspace. Load before `terraform-module-library` when authoring modules.
- **terraform-module-library**: Reusable GCP Terraform module patterns for Cloud Run v2, Cloud SQL PostgreSQL, Artifact Registry, VPC + Private Services Access, and Workload Identity Federation. Load when creating or consuming reusable Terraform modules for GCP. Reference file: `references/gcp-modules.md` — full HCL for all 6 GCP modules with variables, main, outputs, and native test examples using mock providers. Iron Law: every module needs tests with `mock_provider "google"` (no real GCP auth required). Load after `terraform-skill`.
- **workflow-orchestration-patterns**: Durable workflow orchestration with Temporal for distributed systems. Use when building long-running, failure-resilient distributed business processes in Java 21, Python 3.14, or NestJS 11.x — covers Workflow vs Activity separation, Saga pattern with compensation, Entity workflows (actor model), Fan-out/Fan-in parallel execution, determinism constraints, retry policies, and idempotency. Reference: `reference/implementation-playbook.md` (full workflow + activity code for all 3 SDKs).

### Frontend (19 skills)
- **genui-contract**: Framework-neutral generative UI contract targeting A2UI **1.0** with a v0.9.x compatibility path (dual-version validator). Covers:
  - one canonical catalog (ActionCard, DataSummaryTable, ApprovalForm, SelectionList, DetailPanel, StatusIndicator, InputForm, ConfirmationDialog)
  - action allowlist with golden payloads, plus valid and invalid fixtures and a deterministic validator (`scripts/validate_a2ui_contract.py`)
  - `shared-backend` vs `standalone-backend` topologies, with Mermaid diagrams
  - carrying A2UI over AG-UI (`ACTIVITY_SNAPSHOT` `a2ui-surface`)
  - server-side action security: authz, idempotency, approvals
  - runtime lifecycle: partial delivery, cancel, reconnect
  - the Angular/React/Flutter compatibility matrix
  - when to use A2UI, AG-UI, CopilotKit or Flutter GenUI

  Should this workflow use GenUI at all? Run `reference/genui-suitability.md` before the contract-first workflow.
  Reference files: `catalog-contract.md`, `backend-topologies.md`, `ag-ui-transport.md`, `action-security.md`, `runtime-lifecycle.md`, `backend-emitters.md`, `compatibility-matrix.md`. Reviewer: `genui-contract-reviewer`. Commands: `/scaffold-genui-feature`, `/audit-a2ui-parity`, `/validate-genui-feature`. Rule: `genui-a2ui.md`. Hook: `post-edit-genui-advisory.sh`, an advisory that flags protocol-version drift.
- **a2ui-angular**: A2UI **1.0** target with v0.9.x compatibility (`@a2ui/angular` 0.16.0 + `@a2ui/web_core` 0.16.1; pins in `genui-contract/reference/compatibility-matrix.md`) renderer development for Angular 22.x, direct or with CopilotKit Angular 0.6.0 (optional, v0.9 only). Additional reference files: `canonical-catalog-angular.md`, `canonical-catalog-angular22-components.md`, `canonical-catalog-angular22-session.md`, `copilotkit-angular.md`. Also covers protocol implementation, component catalog, recursive renderer, action handling, streaming A2UI payloads, and security validation. Reference files: `a2ui-protocol.md`, `a2ui-protocol-advanced.md`, `a2ui-security.md`, `a2ui-component-catalog.md`, `a2ui-component-containers.md`, `a2ui-renderer-patterns.md`, `a2ui-renderer-template.md`, `a2ui-chat-template.md`, `a2ui-renderer-services.md`, `a2ui-client-integration.md` (agUiResource service pattern, demo-only vs production action handler warning, rate limits).
- **streaming-protocols**: Three-layer mental model (Transport/Framing/Message) for AI streaming: SSE vs HTTP streaming vs NDJSON vs WebSocket, wire formats, proxy buffering/compression/reconnection pitfalls, and the server-side stream lifecycle (`reference/server-stream-lifecycle.md`: client disconnect cancels the upstream model call, exactly one terminal done/error frame, never persist or act on partial structured output, WebSocket auth before accept).
- **ai-chat**: AI chat interface patterns for Angular 22.x and Flutter 3.50.x — streaming markdown rendering, auto-scroll heuristics, memoized computed(), token context indicators, thumbs up/down feedback, multi-modal input, and AI error states.
- **react-spa**: React 19.3 web SPA (RECOMMENDED PRACTICE) — Vite 8, TypeScript 6.0.3 pinned, React Router 8 data mode (imports from `react-router`), TanStack Query 5 server state with loading/empty/error states, React Hook Form + zod 4, typed API client with runtime validation, auth plumbing (no tokens in Web Storage, allow-listed credential origins, validated `returnUrl`), React Compiler, Vitest + Testing Library + MSW, Playwright + axe. Agent `react-spa` (builder); command `/scaffold-react-app`. Not React Native (`mobile-developer`), not Next.js/SSR.
- **angular-spa**: Angular 22.x SPA development skill with Tailwind CSS 4.3.5 and daisyUI 5.8.2, covering component scaffolding, UI/UX design, accessibility audits, and design systems.
- **angular**: Angular 22.x core API reference — Signals (`signal()`, `computed()`, `effect()`), Standalone components, Zoneless change detection, SSR/Hydration with incremental hydration triggers, functional DI (`inject()`), Component composition (content projection, host directives), Signal-based state management, and testing signal components with `setInput()`. Load alongside `angular-spa` when you need deep API reference or testing patterns.
- **angular-best-practices**: Impact-prioritized Angular 22.x best practices. CRITICAL: OnPush change detection + signals, async waterfall elimination (forkJoin/switchMap), bundle optimization (lazy routes, @defer, no barrel files). HIGH: Rendering performance (virtual scroll CDK, trackBy, pure pipes), SSR hydration (withIncrementalHydration, TransferState). MEDIUM: Template optimization (@if/@for control flow), state colocation. LOW-MEDIUM: Memory management (takeUntilDestroyed). Includes ❌/✅ examples and checklists for new component review and PR review.
- **angular-ui-patterns**: Angular 22.x UI/UX state doctrine. Five non-negotiable principles: never stale UI, always surface errors, optimistic updates, progressive @defer, graceful degradation. Covers: loading states (show ONLY when no data — golden rule), error hierarchy (inline→toast→banner→full-screen), empty states (every list MUST have one), button loading (always disable during async), form patterns with field-level validation, dialog/modal service pattern, and anti-patterns catalog. Integrates with `angular-spa` daisyUI components.
- **flutter-genui**: Flutter agent-driven UI on A2UI **1.0** (v0.9.x compatibility path) with `a2ui_flutter` 0.5.0 + `a2ui_core` 0.9.0 on Flutter >= 3.47 (optional `a2ui_agent` 0.5.0 when the app prompts a model; on Flutter 3.38–3.46, `a2ui_flutter` 0.4.0 + `a2ui_core` 0.8.0 also render 1.0 and v0.9.x); replaces the discontinued `genui` package (migration table in `SKILL.md`). Covers: catalogs (`basicCatalog()`, custom `CatalogImplementation` / `ComponentImplementation` with `CommonSchemas`), state binding (`MessageProcessor`, `A2uiSurface`, per-surface data model, templated lists, semantics boundary, optional Riverpod), transport (SSE/JSONL into `processMessages`, actions back with `a2uiClientCapabilities`), conversation topologies (agent server vs in-app model with `ResponseStream`), the 14 v0.9 basic functions and checks, and security (validation configs, locked-down catalog, `openUrl`, payload limits). Reference files: `genui-catalog-design.md`, `genui-state-binding.md`, `genui-custom-widgets.md`, `genui-a2ui-transport.md`, `genui-conversation-orchestration.md`, `genui-functions.md`, `genui-security.md`.
- **flutter-mobile**: Provides patterns and templates for Flutter 3.50.x / Dart 3.14.0 cross-platform mobile development, activated when building Flutter screens, Riverpod providers, Freezed models, or widget tests. Reference files: `mfri-scoring.md` (risk scoring before any UI implementation), `flutter-templates.md`, `flutter-architecture-patterns.md` (includes mixin-based data source error handler — eliminates duplicate try-catch across repositories), `flutter-performance-ux.md` (includes staged/progressive loading pattern; `context.responsive()` BuildContext extension for adaptive layouts), `flutter-design-polish.md`, `accessibility-audit-checklist.md`, `flutter-security-hardening.md` (includes Crashlytics structured error reporting pattern), `flutter-network-resilience.md` (circuit breaker, retry with exponential backoff, timeout budgets by operation type, Riverpod integration), `flutter-offline-sync.md` (storage-neutral offline queue model and drain loop, tier model, conflict strategies), `flutter-offline-reliability.md` (write path: atomic enqueue, idempotency keys, failure classification, bounded retry, single-drainer lease, upload staging, review checklist), `flutter-offline-cache-and-reads.md` (read path: queued-write display, temp ids, non-destructive refresh, account-bound cache, migrations, backup exclusion), `flutter-navigation-and-auth-boot.md` (redirect/gate semantics, cold-start auth ordering, sheet and Back safety, deep links), `flutter-api-contract-parity.md` (client/server contract checks, network-vs-domain errors, timeouts), `flutter-testing-traps.md` (widget-test traps, vacuous-pass defenses, `fakeAsync`, golden determinism, outcome classification, validation matrix by change type), `flutter-e2e-maestro.md` (Maestro vs `integration_test`, flow conventions, iOS/Android divergences), `flutter-localization.md` (gen-l10n, ICU plurals, parity vs coverage), `flutter-build-and-workspace.md` (Melos 8.10.1 as a workspace dev_dependency run with `dart run melos`, pub workspaces, run-target hosts, Gradle 9.5.0 / AGP 9.3.1 / KGP 2.4.20, `Isolate.run`), `flutter-security-client-trust.md` (what may ship in the binary, fail-closed settings), `flutter-platform-gotchas.md`. Path-scoped rules `.claude/rules/flutter-engineering.md` and `.claude/rules/flutter-verification.md` load only when Dart/pubspec files are touched.
- **flutter-animations**: Enterprise Flutter animation skill for Rive + Lottie dual-engine animations. Use when adding animations to Flutter — interactive state machines (Rive), play-once or looping illustrations (Lottie), onboarding flows, splash screens, empty states, progress rings, micro-interactions, or any animated widget. Reference files: `references/rive.md` (state machines, inputs, data binding, multi-artboard, RivePanel), `references/lottie.md` (composition caching, renderCache, delegates, network), `references/architecture.md` (service layer, DI, preloading, CI/CD size checks, 35-point code review checklist).
- **mobile-design**: Load BEFORE `flutter-mobile` when building any Flutter UI — provides touch psychology (Fitts' Law, thumb zones), MFRI risk scoring, platform conventions (iOS HIG, Material 3), and performance doctrine. Reference files: `reference/touch-psychology.md`, `reference/mobile-performance.md`, `reference/platform-ios.md`, `reference/platform-android.md`, `reference/mobile-backend.md`, `reference/mobile-testing.md`, `reference/mobile-debugging.md`, `reference/flutter-native-capabilities.md` (verified Flutter plugin set for camera, location, maps, files, PDF, audio, contacts, sharing and runtime permissions, with pinned versions, Android/iOS minimums, required permission keys and a CI check for missing iOS usage descriptions).
- **mobile-developer**: Expert skill for React Native, native Swift/SwiftUI, Kotlin/Compose, and mobile CI/CD (Fastlane, Codemagic, Bitrise, EAS Update, CodePush, Detox). **NOT for Flutter** — use `flutter-mobile` for Flutter work. Use when the mobile task is outside Flutter's scope.
- **frontend-design**: Creative frontend design skill for distinctive, production-grade interfaces. Includes DFII scoring (go/no-go gate: must score ≥8 before coding), mandatory Design Thinking Phase (Purpose → Tone → Differentiation Anchor), Required Output Structure (Design Direction Summary + Design System Snapshot + Differentiation Callout), and pre-delivery Operator Checklist. Covers: typography (no Inter/Roboto/Arial), color (CSS variables, one dominant + one accent), spatial composition (intentional grid breaks), motion (sparse + high-impact), texture/depth. Workspace integration: Angular uses daisyUI tokens; Flutter uses `Theme.of(context).colorScheme` + `AppSpacing.*`. Reference file: `reference/frontend-design-principles.md` (includes DFII quick-score card, differentiation anchor examples, framework-specific execution notes).
- **web-design-guidelines**: UI compliance auditor — fetches Vercel's Web Interface Guidelines live, reads specified files, outputs `file:line` findings. Third review layer after `/lint-design-system` (tokens) and `accessibility-auditor` (WCAG). Use when asked to "review my UI", "audit design", "check UX", or run pre-PR design compliance. Triggers: "review UI", "audit design", "check accessibility", "review UX", "check my component". Failure safe: if WebFetch fails, reports error and does not guess rules.
- **web-performance-optimization**: Optimize Angular 22.x SPA performance — Core Web Vitals (LCP, INP, CLS), bundle analysis (`ng build --stats-json` + `webpack-bundle-analyzer`), lazy routes (`loadComponent`/`loadChildren`), `@defer` blocks for below-fold components, `NgOptimizedImage`, OnPush+Signals runtime performance, and SSR TransferState double-fetch prevention. Load alongside `angular-best-practices` for full coverage.
- **fixing-motion-performance**: Audit and fix CSS/WAAPI animation performance in Angular 22.x — layout thrashing, compositor vs paint vs layout tier selection, FLIP technique for layout-like transitions, scroll-linked motion (CSS View Timeline replaces JS scroll listeners), `will-change` surgical use, blur/filter cost limits, and View Transitions API. Works as a file auditor: `/fixing-motion-performance <file>` reports violations with exact line quotes and concrete Angular fixes. Load alongside `angular-spa` when animations stutter or reviewing animation code.
- **riverpod-patterns**: Provides Riverpod state management patterns and best practices for Flutter applications, covering providers, AsyncValue handling, ref usage, and provider lifecycle management.
- **tailwind-patterns**: Tailwind CSS v4 reference for Angular 22.x — CSS-first `@theme` config, container queries (`@container`/`@sm:`/named containers), OKLCH color system for daisyUI custom themes, Bento/asymmetric grid layouts, dark mode strategies, and v3→v4 anti-pattern migration table. Load alongside `angular-spa` when working on Tailwind v4 config or complex layouts.
- **ui-ux-pro-max**: Design intelligence database — 50+ styles, 97 color palettes, 57 font pairings, 99 UX guidelines, BM25 Python search engine. Flutter has a dedicated stack CSV. Angular uses `html-tailwind` stack. Run `--design-system` first to get complete style+palette+typography recommendations. Load before `frontend-design` to inform DFII scoring.
- **screenshot-to-angular**: Pixel-perfect Angular component replication from a screenshot. Use when the user provides a UI screenshot and asks to replicate, clone, implement, or build it in Angular. Enforces daisyUI semantic classes, Tailwind scale, standalone components, and signals. Related skills: `angular-spa`, `angular-ui-patterns`, `ui-standards-tokens`, `tailwind-patterns`. Triggers: screenshot to angular, replicate screen angular, clone UI angular, pixel perfect angular, implement design angular.
- **screenshot-to-flutter**: Pixel-perfect Flutter widget replication from a screenshot. Use when the user provides a UI screenshot and asks to replicate, clone, implement, or build it in Flutter. Enforces ColorScheme tokens, AppSpacing, TextTheme — never raw hex or hardcoded values. Related skills: `flutter-mobile`, `mobile-design`, `ui-standards-tokens`, `riverpod-patterns`. Triggers: screenshot to flutter, replicate screen, clone UI, pixel perfect flutter, implement design flutter.
- **ui-standards-tokens**: Provides design token definitions, theming patterns, and UI standards for Flutter applications, used when auditing UI compliance, implementing design systems, or ensuring consistent token usage.

### Mobile Deployment (14 skills)

**App Store Optimization (1 skill — load BEFORE any release workflow):**
- **app-store-optimization**: Complete ASO toolkit for keyword research, metadata optimization, competitor analysis, A/B test planning, review sentiment analysis, and ASO health scoring (0–100). Load before the iOS or Android release workflow to optimize the store listing. **Gate: ASO score ≥ 70 before submitting.** Scripts: `keyword_analyzer.py`, `metadata_optimizer.py`, `competitor_analyzer.py`, `aso_scorer.py`, `ab_test_planner.py`, `localization_helper.py`, `review_analyzer.py`, `launch_checklist.py`. Covers Apple App Store (30-char title, 30-char subtitle, 100-char keyword field) and Google Play (50-char title, 80-char short description).

**iOS App Store (7 skills — powered by `asc` CLI):**
- **asc-cli-usage**: Command discovery, flags, output formats, auth, and pagination for the `asc` CLI — load first before running any asc command.
- **asc-id-resolver**: Resolve App Store Connect IDs (app, build, version, group, tester, submission) from human-friendly names — use whenever a command requires an ID parameter.
- **asc-signing-setup**: Set up bundle IDs, capabilities, signing certificates, and provisioning profiles — use when onboarding a new app or rotating expired certs.
- **asc-release-flow**: End-to-end TestFlight and App Store release workflow covering upload, processing, version creation, submission, and release — the primary iOS release skill.
- **asc-testflight-orchestration**: Manage TestFlight groups, testers, build distribution, and What to Test notes — use for beta rollout management.
- **asc-submission-health**: Preflight checklist and submission health for App Store review — run all 7 checks before submitting. Reference: `reference/submission-preflight-checklist.md`.
- **asc-crash-triage**: Triage TestFlight crashes, beta feedback, and performance diagnostics — use when investigating crash reports after a build is distributed.

**Android Google Play (6 skills — powered by `gpd` CLI):**
- **gpd-cli-usage**: Command discovery, flags, output formats, auth, and edit lifecycle for the `gpd` CLI — load first before running any gpd command.
- **gpd-id-resolver**: Resolve Google Play identifiers (package names, track names, version codes, product IDs) — use whenever a command requires an exact identifier.
- **gpd-build-lifecycle**: Upload AAB, track build processing, check release status, and manage version codes — primary upload skill.
- **gpd-betagroups**: Manage internal/beta tester groups and build distribution — use for beta testing rollout management.
- **gpd-release-flow**: End-to-end Google Play release workflow covering upload, staged rollout, track promotions, and production release — the primary Android release skill.
- **gpd-submission-health**: Preflight checklist for Google Play production releases — run all 5 checks before promoting to production. Reference: `reference/submission-preflight-checklist.md`.

### Vector Database & RAG (7 skills)
- **vector-database**: Use for all vector database work — pgvector schema design, Weaviate collection creation, RAG pipeline scaffolding, embedding model selection, HNSW vs IVFFlat index tuning, and embedding model migration. Iron law: pin dimensions at model selection. Reference files: `references/pgvector-migration-template.md`, `references/weaviate-collection-patterns.md`, `references/rag-pipeline-patterns.md`, `references/embedding-migration-guide.md`, `references/vector-index-tuning-playbook.md` (quantization strategies, HNSW benchmarking, memory estimation, Qdrant config).
- **weaviate**: Search, query, and manage Weaviate vector database collections — semantic search, hybrid search, keyword search, natural language queries, data import, collection inspection, and filtered fetching. Includes Python scripts in `scripts/`. Required env: `WEAVIATE_URL`, `WEAVIATE_API_KEY`.
- **weaviate-cookbooks**: Build complete AI applications with Weaviate — Query Agent Chatbot, PDF Multimodal RAG, Basic/Advanced/Agentic RAG, Basic Agents with DSPy. High-level blueprints and end-to-end project patterns. Read `references/project_setup.md` and `references/environment_requirements.md` first.
- **rag-architect**: RAG system design decision framework. Use at the start of any RAG project — covers "Is RAG the right tool?" (SQL vs RAG vs hybrid), chunking decision tree (5 Q&A branches), embedding model selection table, multi-tenancy patterns (shared/namespaced/per-tenant), and 5 hard rules (pre-filter, hybrid retrieval, stable chunk IDs, untrusted content, golden set). Command: `/rag-design` (produces ADR).
- **rag-debugger**: RAG failure root-cause diagnosis via 9-layer chain (parsing → chunking → filtering → BM25 → dense → RRF → reranking → context packing → generation). First layer where chunk disappears = root cause. Command: `/rag-debug`.
- **rag-evaluator**: RAG evaluation strategy covering 3 levels (retrieval, answer, operational), golden set design (60/20/20 coverage split), retrieval metrics (Recall@K, NDCG@K, MRR), answer metrics (faithfulness, citation accuracy per-claim, hallucination, abstention quality), LLM-as-judge calibration, eval at scale (synthetic, production-trace, drift detection), and CI gate pattern. Command: `/rag-eval-init`.
- **rag-security-reviewer**: Canonical home for permission-aware, tenant-scoped retrieval (§1–2): filter inside the query (pre-filter) with the engine caveats (pgvector filtered-HNSW recall loss, Weaviate `.with_tenant()`), single retrieval chokepoint, retrieved content treated as untrusted data, cache keys scoped by tenant/permissions/index version, erasure that propagates to caches and derived indexes, audit logging and PII redaction.

### API & Architecture (13 skills)
- **architect-review**: Deep architectural review specialist — assesses system design changes, identifies anti-patterns (Anemic Domain, Fat Controller, Missing Outbox, Distributed Monolith), evaluates distributed systems compliance (Saga, CQRS, service mesh, circuit breaker), and produces prioritized HIGH/MEDIUM/LOW findings with ADR triggers. Use when reviewing architecture before implementation. Distinct from `plan-mode-review` Phase 1 (shallow pass) — this is a full dedicated review. Reference: `reference/architect-review-patterns.md` (anti-pattern catalog, distributed systems checklist).
- **architecture-decision-records**: Used when documenting significant technical decisions, reviewing past architectural choices, or establishing decision processes; provides ADR templates and best practices.
- **architecture-design**: Used when designing system architecture, API contracts, deployment topologies, or making technology decisions for full-stack applications. Reference files include `cloud-service-mapping.md` — GCP-primary cross-cloud service equivalents table (AWS/Azure/GCP compute, storage, database, messaging, security, networking, observability).
- **database-schema-designer**: Used when designing database schemas for SQL or NoSQL databases, providing normalization guidelines, indexing strategies, migration patterns, and performance optimization. (domain: infrastructure)
- **postgres-best-practices**: Supabase PostgreSQL best practices library — 33 impact-rated rules (CRITICAL→LOW) organized in 8 categories. Load when configuring connection pooling (PgBouncer, Prisma, asyncpg, R2DBC), implementing RLS, designing SKIP LOCKED worker queues, preventing deadlocks, tuning VACUUM/autovacuum, or adding full-text search. New rules not covered elsewhere: `conn-*.md` (4 connection rules), `lock-*.md` (4 locking rules), `security-rls-performance.md`, `monitor-vacuum-analyze.md`, `advanced-full-text-search.md`. Rule format: incorrect SQL → correct SQL → impact rating → Supabase reference.
- **postgresql**: PostgreSQL-specific design reference — advanced data types (ENUM, array, range, network, domain, composite, TOAST), 7 PostgreSQL gotchas (MVCC, HOT updates, heap storage, sequence gaps, UNIQUE+NULLs), UNLOGGED tables, EXCLUDE constraints, `fillfactor=90` for HOT updates, volatile DEFAULT causes table rewrite, extensions guide (pg_trgm, timescaledb, postgis, pgvector, pgaudit), and complete DDL examples. Load when you need PostgreSQL-specific depth beyond the generic schema rules.
- **sql-optimization-patterns**: Transform slow PostgreSQL queries into fast operations through systematic EXPLAIN analysis, N+1 elimination, cursor pagination, materialized views, and table partitioning. Load when debugging slow endpoints, replacing OFFSET pagination, or fixing ORM-induced N+1 queries. Reference: `resources/implementation-playbook.md` (full SQL code for all 8 patterns + monitoring queries).
- **sql-pro**: Master modern SQL for cloud-native platforms (BigQuery, Snowflake, Redshift), HTAP systems (CockroachDB, TiDB), time-series (TimescaleDB, InfluxDB), dimensional modeling, and advanced PostgreSQL (recursive CTEs, window functions, SCD Type 2). Load when the workload extends beyond OLTP PostgreSQL — analytics tier, data warehouse, or multi-platform SQL architecture.
- **ddd-architect**: Comprehensive Domain-Driven Design analysis and architecture generation for bounded contexts, domain models, aggregates, context maps, and microservice decomposition.
- **openapi-spec-generation**: Used when creating API documentation, generating SDKs, or ensuring API contract compliance by generating and maintaining OpenAPI 3.1 specifications.
- **api-design-principles**: Use before designing any REST API endpoint — covers URL structure, HTTP method semantics, pagination, caching, idempotency, and bulk operations across Python FastAPI, NestJS 11.x, and Spring Boot WebFlux 3.5.x. Reference files: `reference/rest-design-principles.md` (patterns with examples for all 3 stacks), `assets/api-design-checklist.md` (60-item pre-implementation checklist).
- **mcp-builder**: Used when building MCP servers to integrate external APIs — also listed under Backend as it produces implementation code.
- **nosql-expert**: Expert guidance for distributed NoSQL databases (Cassandra, DynamoDB, ScyllaDB) — query-first modeling, partition key design, hot partition prevention, single-table design (adjacency lists), denormalization patterns, and BASE vs ACID tradeoffs. Load when designing schemas for Cassandra/DynamoDB or troubleshooting hot partitions and high-latency scans.

### Quality & Testing (13 skills)
- **browser-testing** (web targets only; Flutter mobile uses Maestro): Web browser testing: Chrome DevTools MCP for interactive debugging and performance, @playwright/test for E2E suites, playwright-cli for scripted interactive QA.
- **ui-visual-validator**: CI/CD visual regression setup and pre-commit 13-item verification checklist. Scoped complement to `reality-checker` agent — adds Chromatic, Percy, Applitools, BackstopJS, and Playwright Visual tooling setup for GitHub Actions. Use alongside `reality-checker`: this skill provides the methodology and CI tooling; `reality-checker` provides the live browser verdict.
- **accessibility-audit**: WCAG 2.2 AA accessibility audit for web (Angular 22.x, React) and Flutter 3.50.x; owns the canonical checklist `reference/wcag22-checklist.md`. Automated results never prove conformance. Use when auditing UI for accessibility compliance, adding automated axe-core or flutter_test semantic testing, identifying barriers, or integrating accessibility gates into CI/CD. Reference files: `reference/wcag22-checklist.md`, `reference/angular-a11y-automated.md` (applies to React too), `reference/flutter-a11y-automated.md`, `reference/manual-testing-checklist.md`, `reference/cicd-integration.md`. Reviewer: `accessibility-auditor` (read-only, web + Flutter). Command: `/fixing-accessibility <file>` for targeted single-file audits.
- **clean-code**: Language-agnostic code quality skill based on Robert C. Martin's *Clean Code*. Use when writing, reviewing, or refactoring code across any stack — covers naming, functions, comments, formatting, Law of Demeter, error handling, F.I.R.S.T. test principles, classes, and code smells.
- **code-reviewer**: General-purpose code review skill providing checklists for security, code quality, performance, and best practices when reviewing code changes, PRs, or performing quality audits.
- **dedup-code-agent**: Code duplication detection and technical debt analysis skill providing methodology for finding duplicate code, dead code, and dependency bloat.
- **pr-review**: Used when reviewing someone else's PR or preparing review comments for GitHub, implementing a two-stage approval process with internal analysis before any public posting.
- **systematic-debugging**: Used when encountering any bug, test failure, or unexpected behavior, before proposing fixes; always finds root cause before attempting a fix.
- **test-driven-development**: Used when implementing new features or logic that requires tests before writing implementation code, covering Red-Green-Refactor cycle and stack-specific test patterns.
- **python-testing-patterns**: Comprehensive pytest patterns for Python 3.14 / FastAPI — fixtures, parametrize, async testing, database fixtures, test markers, coverage config, monkeypatch, and GitHub Actions CI integration. Load when setting up test infrastructure beyond the basic TDD cycle in `test-driven-development`. Real-PostgreSQL fixtures, race tests, deterministic clocks and skip-vs-fail CI behaviour: `reference/postgres-integration-testing.md`.
- **vibe-code-auditor**: Pre-commit gate for AI-generated and rapidly-prototyped code. Audits across 7 dimensions — architecture, consistency, robustness, production risks, security, dead/hallucinated code (imports that don't exist, API mismatches), and technical debt. Produces a Production Readiness Score (0–100) with severity-bucketed findings. Use before `code-reviewer` when code was AI-assisted or evolved without deliberate architecture.
- **tdd** (`/tdd`): Red-Green-Refactor enforcement slash command. Invokes `tdd-guide` agent. Covers Spring Boot/JUnit5, Python/pytest, NestJS/Vitest, Flutter/flutter_test. 80% coverage gate; 100% required for auth/crypto/payments. Modes: default cycle, focus on named class, coverage-only, test audit.
- **test-coverage** (`/test-coverage`): Multi-stack coverage report — detects Spring Boot (JaCoCo), Python (pytest-cov), NestJS (vitest), Flutter (lcov). Lists files below 80% sorted worst-first. 100% threshold for auth/crypto/payment logic.
- **rules-distill** (`/rules-distill`): Scans `.claude/skills/` for behavioral patterns appearing in 2+ skills. Applies 4 filters (2+ evidence, actionable, violation risk, not already in rules) and presents candidates for promotion to `.claude/rules/` with APPROVE/SKIP/MODIFY per candidate. Agent: `rules-distill`.
- **codebase-onboarding**: Systematically analyzes an unfamiliar codebase using a 4-phase workflow (Reconnaissance → Architecture Mapping → Convention Detection → Artifact Generation). Produces an Onboarding Guide (`docs/ONBOARDING.md`) and a tailored `CLAUDE.md` ≤100 lines. Use when joining a new project or onboarding a developer to an existing repo.

### Security (4 skills)
- **claude-actions-auditor**: Audits GitHub Actions workflows for Claude Code Action security vulnerabilities — detects 9 attack vectors (env var intermediary, direct injection, PR target misuse, dangerous sandbox configs, wildcard allowlists). Run before adding `anthropics/claude-code-action` to any workflow or during a CI/CD security review.
- **sast-configuration**: Static Application Security Testing (SAST) configuration skill for setting up security scanning, configuring Semgrep rules, running SAST in CI/CD, or writing custom security rules.
- **security-reviewer**: Security vulnerability detection and remediation skill providing OWASP Top 10 checklists, secret scanning patterns, and security review methodology. Includes `owasp-infrastructure-baseline.md` (15 OWASP-mapped infra controls: encryption, IAM, network hardening, audit logging) for IaC and cloud config reviews. Includes `agent-guardrails-checklist.md` (12-layer AI agent guardrail pipeline: prompt injection defense, output validation, async audit logging, Constitutional AI) for LangGraph agents and agentic AI services.
- **threat-modeling**: Threat modeling skill for STRIDE analysis, attack tree construction, and security requirement extraction when designing new features or reviewing architecture.

### Payments & Subscriptions (2 skills)
- **stripe**: Use when integrating Stripe payments — subscription billing, customer management, payment links, webhooks, Stripe Connect vendor payouts, or invoicing. Covers 27 MCP tools (read-only, create, modify), webhook patterns, idempotency keys, PCI compliance, and Restricted API Key configuration. Load before writing any Stripe API code.
- **revenuecat**: Use when integrating RevenueCat in-app subscriptions — entitlements, offerings, paywalls, purchases_flutter SDK, or Stripe backend sync. Covers 26 MCP tools, Flutter client patterns (Riverpod providers), server-side entitlement verification, and webhook lifecycle handlers. Load before writing any RevenueCat or IAP code.

### Workflow & Process (24 skills)
- **changelog-generator**: Used when preparing releases, writing app store updates, or maintaining a CHANGELOG.md by parsing conventional commits and outputting polished release notes.
- **documentation-generation**: Documentation generation skill for README creation, docstring patterns, and CI/CD doc pipelines when generating project documentation or creating README files.
- **domain-finder**: Used when starting a new project or brand and needing to find a registrable domain by brainstorming creative names and checking real availability via DNS/WHOIS.
- **plan-mode-review**: Structured plan review with Phase 0 self-review, 5-phase code review, approval scope triage, decision logging, and blast radius assessment for non-trivial changes.
- **receiving-code-review**: Used when receiving code review feedback before implementing any suggestion, requiring verification and technical rigor rather than performative agreement.
- **subagent-driven-development**: 3-role pipeline (Implementer -> Spec Reviewer -> Quality Reviewer) for plan-driven multi-task implementation supporting subagent dispatch and Agent Teams. Reference files: `parallel-dispatch-checklist.md` (independence check + conflict detection before/after parallel dispatch), `implementer-prompt.md`, `spec-reviewer-prompt.md`.
- **verification-before-completion**: Used when about to claim work is complete, fixed, or passing, requiring verification commands and confirmed output before any success claims.
- **writing-skills**: Used when creating a new Claude Code skill from scratch, extending an existing skill, or reviewing a skill for structure compliance.
- **the-fool**: Challenge ideas, plans, and decisions using structured adversarial reasoning — devil's advocate, pre-mortem, red team, Socratic questioning, and evidence falsification.
- **feature-forge**: Used when defining new features, gathering requirements, or writing specifications before implementation starts. Runs PM+Dev dual-perspective interview, produces EARS-format functional requirements and Given/When/Then acceptance criteria saved to `specs/{feature}.spec.md`. Reference files: `references/nfr-checklist.md` (structured NFR elicitation — performance, scalability, availability, security, observability, compliance; load during Phase 2/3 of any feature with >100 users, an API, or compliance requirements), `references/interview-questions.md`, `references/ears-syntax.md`, `references/acceptance-criteria.md`, `references/pre-discovery-subagents.md`.
- **brainstorm** (`/brainstorm`): Divergent exploration before committing to an approach — generates ≥3 distinct alternatives with trade-offs and Mermaid diagram. No code; use before feature-forge or architecture-design when the solution space is still open.
- **new-project** (`/new-project`): Single entry point for starting any new project — detects tech stack from natural language description and routes to the correct scaffold command. Supports all 9 workspace stacks. Flutter requests automatically load mobile-design + flutter-mobile skills.
- **debug** (`/debug`): Slash command entry point for systematic-debugging skill. Enforces root-cause-first investigation with structured Symptom → Root Cause → Fix → Prevention output format.
- **audit-skills** (`/audit-skills`): Periodic health audit of all skills — checks Iron Law, `last-reviewed` staleness (90/180-day thresholds), description quality, `allowed-tools` declaration, and body line count. Outputs aggregate PASS/WARN/FAIL report with recommended actions. Run monthly or after adding multiple skills. Also re-audits settings permissions, hooks and MCP allow entries against `security-reviewer/reference/claude-config-security.md`.
- **iterate-pr**: Autonomous PR completion loop — fetches CI failures and review feedback, fixes and pushes until all checks are green. Classifies feedback by LOGAF scale (high/medium auto-fix, low asks user), polls CI, and posts GitHub thread replies.
- **multi-agent-brainstorming**: Structured design review using 5 constrained sequential roles (Primary Designer, Skeptic, Constraint Guardian, User Advocate, Arbiter) to validate designs before implementation. Produces mandatory Decision Log and APPROVED/REVISE/REJECT verdict. Use after `/brainstorm` and before `/plan-review` for high-stakes or irreversible decisions. Reference files: `agent-role-scripts.md`, `decision-log-template.md`, `exit-criteria-checklist.md`.
- **parallel-agents**: Multi-agent orchestration for Claude Code's native Agent tool — coordinates this workspace's 42 actual agents across 6 orchestration patterns (comprehensive review, pre-deploy audit, Flutter feature, agentic AI review, DB schema review, architecture validation). Includes workspace agent catalog and synthesis protocol. Reference files: `workspace-agent-catalog.md`, `orchestration-patterns.md`, `synthesis-protocol.md`.
- **aside** (`/aside`): Freeze current task state, answer a side question, then resume with mandatory "— Back to task:" footer. Read-only during aside. Handles 3 edge cases: no question, question reveals task problem, question is actually a task redirect.
- **checkpoint** (`/checkpoint`): Named session checkpoints logged to `.claude/checkpoints.log` (timestamp|name|SHA|files). Modes: create, verify (diff against saved SHA), list, clear. Use before risky changes or between implementation phases.
- **update-codemaps** (`/update-codemaps`): Generate `docs/CODEMAPS/` token-lean snapshots (<1000 tokens each) for Spring Boot, NestJS, Angular, Flutter, Python services. 30% diff gate skips unchanged services. Writes diff summary to `.reports/codemap-diff.txt`.
- **verify** (`/verify`): Binary PASS/FAIL build + test verification across all detected stacks. Modes: quick (compile+lint), full (+ tests), pre-commit (+ forbidden pattern scan), pre-pr (+ security + coverage). Reports exact exit codes.
- **skill-create** (`/skill-create`): Analyzes `git log --oneline -n 200` to detect repeated patterns, then generates a new skill matching the `writing-skills` spec (Iron Law, frontmatter, progressive disclosure, ≤500 lines). Rule of Three enforced — pattern must appear 3+ times.
- **java-build-resolver** (agent): Surgical Maven/Spring Boot 3.5.x build error fix — 12-error pattern lookup table (missing bean, R2DBC classpath, dependency conflicts, JDK mismatch, port conflicts). Diagnostic sequence: mvnw compile → dependency:tree → effective-pom. 3-attempt stop condition.
- **python-reviewer** (agent): Python 3.14/FastAPI 0.165 code reviewer. CRITICAL: SQL injection via f-strings, bare `except:`, eval/exec. HIGH: blocking calls in async, missing CORS restriction, broad `Any` types. Runs mypy, ruff, bandit, pytest-cov. Distinct from `agentic-ai-reviewer` (which covers LangChain/LangGraph only).

---

## Product Ideation & Design (9 agents, 9 commands)

> Complete pipeline from idea to published wireframes and presentations. Uses Titan methodology (Elon Musk's first-principles + Steve Jobs' design taste) for evaluation.

### Agents

- **idea-to-backlog**: Transforms one-line product ideas into validated feature backlogs with pain points, competitive analysis, TAM/SAM/SOM, and MVP candidates. Uses Titan Product Strategist persona (Elon + Jobs). Trigger: "create backlog for [idea]", "generate feature backlog". Reference: `.claude/agents/references/idea-to-backlog/output-template.md`
- **mvp-shortlist**: Evaluates feature backlogs using Titan methodology — Elon criteria (Problem Magnitude, 10x Potential, Feasibility, Revenue, Scalability) + Steve criteria (User Delight, Simplicity, Coherence, Wow Factor, Taste). Applies Subtraction Game, maps features to screens. Trigger: "shortlist MVP from backlog", "select MVP features". Reference: `.claude/agents/references/mvp-shortlist/output-template.md`
- **reddit-research**: Mines Reddit threads for real customer pain points, unmet needs, and product gaps. Classifies query intent (PAIN_POINTS/RECOMMENDATIONS/TRENDS/GENERAL), fetches via `scripts/reddit_fetcher.py`, outputs ranked top-10 report with behavioral evidence. Trigger: "find pain points for [topic]", "reddit research [topic]". Reference: `.claude/agents/references/reddit-research/prompts.md`
- **premium-wireframe-2026**: Generates Aurora 2026 dual-theme mobile wireframes — glassmorphism, ambient orbs, iPhone 15 Pro frames, dark/light toggle, Google Fonts (Outfit), zero dependencies. Pure HTML/CSS/JS. Trigger: "generate wireframe for [MVP]", "create premium wireframe". Reference: `.claude/agents/references/premium-wireframe/aurora-design-system.md`
- **wireframe-reviewer**: Dual-persona review using Elon (efficiency, flow, feature coverage) + Steve (simplicity, visual excellence, emotional design) scoring /100. APPROVED ≥80, ITERATE 60-79, REDESIGN <60. Generates Lock Document on approval. Trigger: "review wireframe [path]". Framework: `.claude/skills/titan-methodology/SKILL.md`
- **wireframe-iterator**: Applies review feedback in 3 passes — P0 Critical (blocking), P1 Recommended, P2 Polish — with regression validation after each pass. Decision log tracks Applied/Rejected/Deferred. Trigger: "iterate wireframe [path]".
- **publish-wireframes**: Discovers all wireframe HTML files, classifies by style (Premium/Sketch), regenerates `index.html` landing page with versioning (2 most recent per project), deploys to Firebase Hosting. Trigger: "publish wireframes", "deploy to Firebase".
- **presentation**: Generates animation-rich HTML slide presentations — from scratch, PPT conversion, or from studio artifacts. Mood-based style selection (12 presets), viewport-perfect, zero dependencies. Trigger: "create slides for [topic]", "convert deck.pptx", "create presentation". Reference: `.claude/agents/references/presentation/`

### Commands

| Command | Purpose | Agent |
|---------|---------|-------|
| `/research` | Mine Reddit for customer pain points | `reddit-research` |
| `/backlog` | Generate feature backlog from product idea | `idea-to-backlog` |
| `/shortlist` | Select MVP features from backlog using Titan scoring | `mvp-shortlist` |
| `/wireframe` | Generate premium dual-theme wireframe (Aurora 2026) | `premium-wireframe-2026` |
| `/sketch-wireframe` | Generate hand-drawn lo-fi sketch wireframe | `wireframe-agent` |
| `/review-wireframe` | Score wireframe with Elon+Steve dual-persona /100 | `wireframe-reviewer` |
| `/iterate-wireframe` | Apply review feedback in 3 prioritized passes | `wireframe-iterator` |
| `/publish-wireframes` | Deploy all wireframes to Firebase Hosting | `publish-wireframes` |
| `/slides` | Create HTML slide presentation | `presentation` |

### Titan Methodology

Loaded from the `titan-methodology` skill (`.claude/skills/titan-methodology/SKILL.md`). Dual-lens scoring for product decisions:
- **Elon's Lens (50%)**: Problem Magnitude, 10x Potential, Technical Feasibility, Execution Speed, Scalability
- **Steve's Lens (50%)**: User Delight, Simplicity, Design Quality, Emotional Connection, Market Positioning
- **Threshold**: 8.0+ = BUILD IT, 7.0-7.9 = REFINE, <6.0 = RETHINK

---

## Skill Workflows

> Ordered sequences for common development tasks.

### New Java/Spring API Feature
1. **api-design-principles** — Run checklist, choose pagination/versioning/caching strategy
2. **java-spring-api** — Scaffold controller, service, repository, DTOs
3. **java-coding-standard** — Enforce naming, immutability, Optional patterns
4. **openapi-spec-generation** — Generate OpenAPI 3.1 spec from the new endpoints
5. **database-schema-designer** — Design schema for new entities
6. **code-reviewer** — Final quality and security review

### New NestJS API Feature
1. **api-design-principles** — Run checklist, choose pagination/versioning/caching strategy
2. **nestjs-api** — Scaffold module, controller, service, DTOs, Prisma queries
3. **nestjs-coding-standard** — Enforce TypeScript strictness, DTO patterns
4. **openapi-spec-generation** — Generate API spec
5. **database-schema-designer** — Design Prisma schema
6. **code-reviewer** — Final review

### New Python FastAPI Feature
1. **python-patterns** — Confirm framework (FastAPI/Django/Flask), async vs sync decision, project structure
2. **uv-package-manager** — Set up lockfile, Python version pin, CI caching (new projects)
3. **api-design-principles** — Run checklist, choose pagination/versioning/caching strategy
4. **python-dev** — Scaffold routes, services, Pydantic models, tests
5. **pydantic-models-py** — Define Base/Create/Update/Response model contracts
6. **python-testing-patterns** — Set up test infrastructure, fixtures, coverage config
7. **openapi-spec-generation** — Generate OpenAPI 3.1 spec from the new endpoints
8. **database-schema-designer** — Design schema for new entities
9. **code-reviewer** — Final quality and security review

### TypeScript Type System (NestJS, Angular, React, or MCP Builder)
1. **typescript-advanced-types** — Load for type-level patterns: generics, conditional types, mapped types, utility types
2. **typescript-expert** — tsconfig strictness, type-check commands that actually check (Angular/Vite solution configs), build perf, project refs, ESM/CJS interop
3. **nestjs-coding-standard**, **angular-spa** or **react-spa** — Enforce framework-specific TypeScript standards

### Flutter Mobile Feature
1. **mobile-design** — Complete Mobile Checkpoint, MFRI scoring, read touch-psychology + platform files
2. **flutter-mobile** — Build screens, Riverpod providers, Freezed models
3. **riverpod-patterns** — Review provider types, AsyncValue, ref usage
4. **ui-standards-tokens** — Audit design token compliance
5. **flutter-testing-traps** (reference) — Choose validations for the change type; classify results PASS/FAIL/BLOCKED/NOT RUN/NOT APPLICABLE
6. **code-reviewer** — Final quality review

### React Native / Native Mobile Feature
1. **mobile-design** — Complete Mobile Checkpoint before any UI work
2. **mobile-developer** — Scaffold RN components, native modules, CI/CD
3. **code-reviewer** — Final quality review
4. **security-reviewer** — OWASP MASVS compliance

### iOS App Store Release
1. **flutter-mobile** — Build and archive the iOS app (`flutter build ios --release`)
2. **asc-cli-usage** — Verify asc auth and learn flags before running any command
3. **asc-signing-setup** — Verify bundle ID, capabilities, and provisioning profiles
4. **asc-id-resolver** — Resolve app ID, group IDs, and build IDs
5. **asc-release-flow** — Upload IPA, wait for processing, create version, submit
6. **asc-testflight-orchestration** — Distribute to groups and manage What to Test notes
7. **asc-submission-health** — Run all 7 preflight checks before App Store submission
8. **asc-crash-triage** — Investigate crashes after TestFlight distribution

### Android Google Play Release
1. **flutter-mobile** — Build the Android AAB (`flutter build appbundle --release`)
2. **gpd-cli-usage** — Verify gpd auth and learn flags before running any command
3. **gpd-id-resolver** — Resolve package name, track names, and version codes
4. **gpd-build-lifecycle** — Upload AAB and wait for build processing
5. **gpd-betagroups** — Distribute to internal/beta tester groups
6. **gpd-release-flow** — Staged rollout and promotion to production track
7. **gpd-submission-health** — Run all 5 preflight checks before production release

### Angular SPA Feature
1. **angular-spa** — Build standalone components, services, routes with TailwindCSS
2. **frontend-design** — Apply visual design principles
3. **browser-testing** — E2E test the new flow
4. **code-reviewer** — Final review

### AI Chat UI Feature (Angular or Flutter)
1. **ai-chat** — Streaming messages, auto-scroll, token indicator, feedback, error states
2. **angular-spa** or **flutter-mobile** — Platform-specific component patterns
3. **security-reviewer** — File upload, innerHTML rendering, token exposure

### RAG System — Full Lifecycle
1. **rag-architect** `/rag-design` — Architecture decisions + ADR (chunking, embedding, multi-tenancy, pre-filter)
2. **vector-database** — Design pgvector migration or Weaviate collection (dimensions, index, distance metric)
3. **pgvector-schema-reviewer** agent — Review migration for operator/index alignment, dimension match
4. **agentic-ai-dev** (or **python-dev**) — Implement embedding + retrieval + generation layer
5. **rag-implementation-reviewer** agent — Full code review (ingestion, retrieval, generation, security, audit, eval)
6. **rag-security-reviewer** — Verify pre-filter mode, single chokepoint, audit log, PII redaction
7. **rag-evaluator** `/rag-eval-init` — Bootstrap golden set + metrics infrastructure
8. **rag-eval-runner** agent — Run evals, detect regressions, triage failures
9. `/rag-debug` — Diagnose failures via 9-layer chain when queries miss expected results
10. `/rag-review` — Full system audit (ingestion, retrieval, generation, security, eval, ops MVP checklist)

### SQL Query Optimization (PostgreSQL OLTP)
1. **sql-optimization-patterns** — Run `pg_stat_statements` query to find slowest queries
2. **sql-optimization-patterns** `resources/implementation-playbook.md` — Apply the right pattern (N+1, cursor, batch, materialized view)
3. **postgresql-database-reviewer** agent — Review the index changes and query rewrites
4. **database-schema-designer** — Update schema if partitioning or structural changes are needed

### PostgreSQL Connection & Concurrency Setup
1. **postgres-best-practices** `rules/conn-pooling.md` — Calculate pool size, choose transaction vs session mode
2. **postgres-best-practices** `rules/conn-limits.md` — Set `max_connections` based on available RAM
3. **postgres-best-practices** `rules/conn-idle-timeout.md` — Configure idle timeouts in DB and pooler
4. **postgres-best-practices** `rules/conn-prepared-statements.md` — Resolve prepared statement conflicts in transaction mode
5. **postgres-best-practices** `rules/lock-skip-locked.md` — Implement SKIP LOCKED for job queues
6. **postgresql-database-reviewer** agent — Review connection and locking configuration

### PostgreSQL Schema Design (New Table)
1. **postgresql** — Review gotchas, data type selection, constraints, extensions for new table design
2. **database-schema-designer** — Design normalized schema with FK/index rules
3. **postgres-best-practices** `rules/schema-*.md` — Apply schema rules (PK strategy, FK indexes, data types)
4. **postgresql-database-reviewer** agent — Review final DDL

### Advanced SQL / Analytics Tier
1. **sql-pro** — Classify workload (OLAP / HTAP / time-series / data warehouse)
2. **sql-pro** — Design schema for platform (star schema, data vault, hypertables)
3. **architecture-design** — Plan HTAP read/write path separation or analytics pipeline
4. **database-schema-designer** — Design the PostgreSQL side of the hybrid system

### Weaviate Collection + Application
1. **rag-architect** `/rag-design` — Architecture decisions before implementation
2. **weaviate** — Inspect existing cluster, list collections, explore schema
3. **vector-database** — Design collection schema (vectorizer, named vectors, multi-tenancy)
4. **weaviate-schema-reviewer** agent — Review collection for v4 API, distance metric, multi-tenancy flag
5. **weaviate-cookbooks** — Pick application blueprint (RAG, chatbot, agentic RAG, DSPy agent)
6. **agentic-ai-dev** (or **python-dev**) — Implement FastAPI layer
7. **rag-security-reviewer** — Verify pre-filter, single chokepoint, audit log

### AI Agent Development
1. **agentic-ai-dev** — Build LangGraph agent, RAG system, tools
2. **agentic-ai-coding-standard** — Enforce state management, tool definitions, guardrails
3. **python-dev** — FastAPI layer, Pydantic models, tests
4. **mcp-builder** — Add MCP server integration if needed
5. **security-reviewer** — Review for prompt injection, data exposure

### Google ADK Agent Development
1. **google-adk** — Scaffold agent, define tools, configure session management
2. **adk-eval-guide** — Write evalsets and run `adk eval` before shipping
3. **adk-observability-guide** — Enable Cloud Trace and prompt logging
4. **adk-deploy-guide** — Deploy to Agent Engine or Cloud Run with Terraform
5. **security-reviewer** — Review tools that call external APIs or handle user PII

### Cross-Platform Generative UI (A2UI contract: Angular, React, Flutter)
1. **genui-contract** — Design or extend the canonical catalog and actions, and pick the topology (`/scaffold-genui-feature`)
2. **a2ui-angular** / **react-spa** (`reference/generative-ui-a2ui.md`) / **flutter-genui** — Register the catalog IDs on each declared platform
3. **google-adk** or **agentic-ai-dev** — Agent backend that emits A2UI 1.0, or v0.9.x to clients that declare only v0.9 (`genui-contract/reference/backend-emitters.md`)
4. **genui-contract-reviewer** agent, then `/audit-a2ui-parity` and `/validate-genui-feature`

### A2UI Agent-Driven UI (Angular)
1. **a2ui-angular** — Build A2UI renderer, catalog, and action handler
2. **angular-spa** — Platform-specific Angular component patterns
3. **google-adk** (or **agentic-ai-dev**) — Agent backend that emits A2UI payloads
4. **security-reviewer** — Validate allowlist enforcement and injection prevention

### Cloud Run Event-Driven Function
1. **gcp-cloud-run** — Load skill, select stack pattern from `reference/cloud-run-functions.md`
2. **docker** — Write multi-stage Dockerfile for the chosen stack
3. **gcp-cloud-run** — Apply cold start flags from `reference/cold-start-optimization.md`
4. **deployment-engineer** agent — GitHub Actions deploy pipeline
5. **security-reviewer** agent — WIF and secret handling review

### GCP Cost Optimization & DR Planning
1. **gcp-finops** — Load skill, run GCP Recommender audit, apply cost allocation labels
2. **gcp-finops** `reference/gcp-cost-optimization.md` — CUD analysis, billing budget setup
3. **gcp-finops** `reference/gcp-resilience-dr.md` — DR tier assignment, Cloud SQL HA, multi-region
4. **terraform-specialist** agent — Implement CUD reservations and billing budgets as Terraform
5. **security-reviewer** agent — Review IAM for least-privilege on billing and cost exports

### Payment & Subscription Integration (Stripe + RevenueCat)
1. **stripe** — Load skill, configure Stripe MCP, implement webhook handlers and idempotency
2. **revenuecat** — Load skill, configure RevenueCat MCP, set up entitlements and offerings
3. **python-dev** — Backend webhook endpoints, server-side entitlement verification
4. **flutter-mobile** — Payment Sheet UI, RevenueCat SDK integration, paywall screens
5. **security-reviewer** agent — PCI compliance, webhook signature verification, key management

### Security Hardening Session
1. **threat-modeling** — STRIDE analysis, DFD mapping, risk scoring
2. **sast-configuration** — Configure Semgrep/Bandit/gosec rules
3. **security-reviewer** — OWASP Top 10 review of changed code

### Architecture & Planning Session
1. **ddd-architect** — Domain analysis, bounded contexts, aggregates
2. **architecture-design** — System design, API contracts, deployment topology
3. **architecture-decision-records** — Document key decisions as ADRs
4. **openapi-spec-generation** — Generate API spec before implementation

---

## Decision Trees

> Use `->` to find the right skill for any task.

### What am I building?
- **Java REST API / reactive service** -> java-spring-api
- **NestJS REST API / TypeScript service** -> nestjs-api
- **Python FastAPI service** -> python-dev
- **Python framework or async architecture decision** -> python-patterns
- **Pydantic request/response schema design** -> pydantic-models-py
- **uv lockfiles, Docker, CI, or monorepo setup** -> uv-package-manager
- **Python project structure or internal CLI tool** -> python-packaging
- **pytest infrastructure, fixtures, or coverage config** -> python-testing-patterns
- **AI agent or RAG pipeline** -> agentic-ai-dev
- **Google ADK agent (Gemini-based)** -> google-adk
- **Cross-platform generative UI / A2UI catalog contract** -> genui-contract
- **A2UI agent-driven UI** -> a2ui-angular
- **AI chat UI (streaming, copilot, chatbot)** -> ai-chat
- **Angular SPA** -> angular-spa
- **Flutter mobile app (iOS/Android)** -> flutter-mobile
- **Mobile design thinking / touch psychology / MFRI scoring** -> mobile-design (load before flutter-mobile)
- **React Native app** -> mobile-developer
- **Native Swift/SwiftUI or Kotlin/Compose module** -> mobile-developer
- **Mobile CI/CD (Fastlane, Codemagic, Bitrise, EAS Update, CodePush)** -> mobile-developer
- **iOS App Store release / TestFlight distribution** -> asc-release-flow (+ asc-cli-usage, asc-id-resolver)
- **Android Google Play release / staged rollout** -> gpd-release-flow (+ gpd-cli-usage, gpd-id-resolver)
- **App Store signing / certificates / provisioning** -> asc-signing-setup
- **TestFlight crash investigation** -> asc-crash-triage
- **Stripe payment integration / billing / Connect payouts** -> stripe
- **RevenueCat in-app purchases / entitlements / paywalls** -> revenuecat
- **Full payment stack (Stripe + RevenueCat)** -> stripe + revenuecat + python-dev + flutter-mobile
- **MCP server integration** -> mcp-builder
- **Database schema** -> database-schema-designer
- **Slow PostgreSQL query / N+1 / OFFSET pagination** -> sql-optimization-patterns
- **Connection pooling / PgBouncer / pool size / max_connections** -> postgres-best-practices `rules/conn-*.md`
- **SKIP LOCKED / worker queue / deadlock prevention / advisory lock** -> postgres-best-practices `rules/lock-*.md`
- **RLS row level security / multi-tenant isolation** -> postgres-best-practices `rules/security-rls-*.md`
- **PostgreSQL data types / ENUM / array / range / TOAST / gotchas** -> postgresql
- **PostgreSQL extensions / pg_trgm / timescaledb / postgis / pgaudit** -> postgresql
- **Analytics SQL / BigQuery / Snowflake / HTAP / data warehouse** -> sql-pro
- **Dockerfile / docker-compose for any backend service** -> docker
- **Cloud Run Function (Pub/Sub, Storage trigger, HTTP webhook)** -> gcp-cloud-run
- **GCP cost optimization / billing budgets / CUD / DR planning** -> gcp-finops
- **pgvector schema / vector column migration** -> vector-database → `/design-vector-schema`
- **Weaviate collection creation** -> vector-database → `/design-weaviate-collection`
- **RAG pipeline (chunk → embed → retrieve → rerank)** -> vector-database → `/scaffold-rag-pipeline`
- **Vector index tuning (HNSW vs IVFFlat)** -> vector-database → `/tune-vector-index`
- **Switch embedding model (re-embedding migration)** -> vector-database → `/migrate-embedding-model`
- **Search/query an existing Weaviate cluster** -> weaviate → `/weaviate:search` or `/weaviate:ask`
- **Build a Weaviate-based application (chatbot, RAG app)** -> weaviate-cookbooks
- **TypeScript type-level programming (generics, conditional, mapped types)** -> typescript-advanced-types
- **TypeScript project infrastructure (monorepo, build perf, ESM/CJS, migration)** -> typescript-expert
- **TypeScript architecture design (shared types, decorators)** -> typescript-advanced-types; **strict config / type-check commands** -> typescript-expert

### What review do I need?
- **General code quality** -> code-reviewer
- **Security vulnerabilities / OWASP** -> security-reviewer
- **Static analysis configuration** -> sast-configuration
- **Threat model for new system** -> threat-modeling
- **PR review for GitHub (before merge)** -> pr-review
- **Fix CI failures + feedback loop after PR opened** -> iterate-pr
- **Receiving feedback on my PR** -> receiving-code-review
- **Duplicate code / tech debt** -> dedup-code-agent
- **Plan or architecture review** -> plan-mode-review

### What architecture work?
- **New system design (C4, ADR, sequences)** -> architecture-design
- **Domain-driven design (DDD, bounded contexts)** -> ddd-architect
- **Document architectural decisions** -> architecture-decision-records
- **OpenAPI / Swagger spec** -> openapi-spec-generation
- **Database schema design** -> database-schema-designer

### What testing task?
- **Write tests first (TDD cycle)** -> test-driven-development
- **E2E / UI testing of a web app (Angular, React)** -> browser-testing
- **E2E / UI testing of a Flutter Android/iOS app** -> flutter-mobile (Maestro CLI/MCP only; `.claude/rules/testing-tool-selection.md`)
- **Debug failing test or error** -> `/debug` (loads systematic-debugging)

### What security task?
- **STRIDE threat model** -> threat-modeling
- **Configure SAST tools** -> sast-configuration
- **Code vulnerability review** -> security-reviewer

### What documentation?
- **OpenAPI / Swagger** -> openapi-spec-generation
- **README / docstrings** -> documentation-generation
- **Changelog / release notes** -> changelog-generator
- **Architecture decision records** -> architecture-decision-records

### What workflow / process task?
- **Verify work before claiming done** -> verification-before-completion
- **Debug unexpected behavior** -> `/debug` (loads systematic-debugging)
- **Explore options before committing to an approach** -> `/brainstorm`
- **Multi-agent implementation pipeline** -> subagent-driven-development
- **Iterate PR until CI is green** -> iterate-pr
- **Create a new skill** -> writing-skills
- **Find a domain name** -> domain-finder
- **Invoke a specialist agent** -> name it in the request ("use the nestjs-reviewer agent on ..."); each `.claude/agents/*.md` description lists its triggers and examples
- **Set up team memory sharing (claude-mem-sync)** -> `/setup-team-memory`

---

## Skill Combinations

> Common multi-skill patterns for compound tasks.

### Full Java API Feature
java-spring-api + java-coding-standard + openapi-spec-generation + database-schema-designer + code-reviewer

### Containerize a Backend Service
docker (+ java-spring-api OR nestjs-api OR python-dev — depending on stack)

### Full NestJS API Feature
nestjs-api + nestjs-coding-standard + openapi-spec-generation + database-schema-designer + code-reviewer

### TypeScript Type Hardening (NestJS or Angular)
typescript-advanced-types + typescript-expert + nestjs-coding-standard (or angular-spa / react-spa)

### Flutter Mobile App
mobile-design + flutter-mobile + flutter-animations + riverpod-patterns + ui-standards-tokens + code-reviewer

### React Native App
mobile-design + mobile-developer + code-reviewer + security-reviewer

### iOS App Store Release Pipeline
flutter-mobile + asc-cli-usage + asc-signing-setup + asc-id-resolver + asc-release-flow + asc-testflight-orchestration + asc-submission-health

### Android Google Play Release Pipeline
flutter-mobile + gpd-cli-usage + gpd-id-resolver + gpd-build-lifecycle + gpd-betagroups + gpd-release-flow + gpd-submission-health

### Angular SPA
angular-spa + frontend-design + design-system + browser-testing

### AI Chat UI (Angular or Flutter)
ai-chat + angular-spa (or flutter-mobile) + security-reviewer

### PR Lifecycle (full loop)
pr-review + iterate-pr + verification-before-completion

### pgvector RAG Stack
vector-database + database-schema-designer + agentic-ai-dev + python-dev + pgvector-schema-reviewer agent + rag-implementation-reviewer agent

### Weaviate Application Stack
weaviate + vector-database + weaviate-cookbooks + agentic-ai-dev + weaviate-schema-reviewer agent

### AI Agent Stack
agentic-ai-dev + agentic-ai-coding-standard + python-dev + security-reviewer

### Payment & Subscription Stack
stripe + revenuecat + python-dev + flutter-mobile + security-reviewer

### Complete Security Audit
security-reviewer + sast-configuration + threat-modeling + code-reviewer

### Architecture Session
ddd-architect + architecture-design + architecture-decision-records + openapi-spec-generation

### Code Cleanup Sprint
code-reviewer + dedup-code-agent + systematic-debugging + test-driven-development

### Release Preparation
verification-before-completion + changelog-generator + pr-review

### New Skill Authoring
writing-skills + subagent-driven-development + plan-mode-review

### Google ADK Agent (Full Stack)
google-adk + adk-eval-guide + adk-observability-guide + adk-deploy-guide + security-reviewer

### Cross-Platform Generative UI
genui-contract + a2ui-angular + react-spa + flutter-genui + genui-contract-reviewer + security-reviewer

### A2UI Agent-Driven UI (Angular)
a2ui-angular + angular-spa + google-adk + security-reviewer

---

## Examples

> Real scenarios mapped to skills.

- "Build a Spring Boot REST API for user management" -> java-spring-api + java-coding-standard + openapi-spec-generation
- "Write a Dockerfile for my Spring Boot / NestJS / FastAPI service" -> docker
- "Add JWT auth to my NestJS service" -> nestjs-api + security-reviewer + nestjs-coding-standard
- "Create a Flutter screen with Riverpod state" -> flutter-mobile + riverpod-patterns + ui-standards-tokens
- "Add animations to a Flutter app" -> flutter-animations + flutter-mobile + riverpod-patterns
- "Angular animation is janky or stuttering" -> fixing-motion-performance + angular-spa + web-performance-optimization
- "Audit a file for accessibility violations" -> /fixing-accessibility <file> (dispatches accessibility-auditor agent)
- "Check WCAG compliance on my Angular/Flutter UI" -> /fixing-accessibility + accessibility-audit skill
- "Apply touch psychology before building a Flutter screen" -> mobile-design (load first, then flutter-mobile)
- "Score MFRI before implementing a complex Flutter feature" -> mobile-design
- "Build a React Native screen with offline sync" -> mobile-developer + mobile-design
- "Set up Fastlane + Codemagic CI/CD for iOS builds" -> mobile-developer
- "Create a native Swift camera module for Flutter app" -> mobile-developer (native side) + flutter-mobile (Dart side)
- "Build an Angular dashboard with charts" -> angular-spa + frontend-design + browser-testing
- "Build a LangGraph RAG agent with FastAPI" -> agentic-ai-dev + agentic-ai-coding-standard + python-dev
- "Design the database schema for a SaaS platform" -> database-schema-designer + architecture-design
- "Do a DDD analysis for our e-commerce domain" -> ddd-architect + architecture-decision-records
- "Review this PR for security issues" -> code-reviewer + security-reviewer
- "Fix all CI failures and address review comments" -> iterate-pr
- "Build a streaming chat UI with Angular" -> ai-chat + angular-spa + security-reviewer
- "Build a Flutter chat screen with streaming AI" -> ai-chat + flutter-mobile + riverpod-patterns
- "Debug this NullPointerException in production" -> systematic-debugging + verification-before-completion
- "Set up Semgrep rules for our Python codebase" -> sast-configuration + security-reviewer
- "Generate OpenAPI spec from my Spring controllers" -> openapi-spec-generation + java-spring-api
- "Write a README for our Flutter app" -> documentation-generation + flutter-mobile
- "Generate release notes from our git history" -> changelog-generator
- "Build an MCP server for our internal Jira API" -> mcp-builder + python-dev
- "Model threats for our new auth microservice" -> threat-modeling + security-reviewer + architecture-design
- "Build a Gemini-based ADK agent with tools and sessions" -> google-adk + adk-eval-guide + security-reviewer
- "Deploy an ADK agent to Cloud Run with Terraform" -> adk-deploy-guide + google-adk
- "Build an A2UI renderer for an Angular agent-driven UI" -> a2ui-angular + angular-spa + security-reviewer
- "Evaluate ADK agent quality with rubric-based scoring" -> adk-eval-guide + google-adk
- "Upload my Flutter iOS build to TestFlight" -> asc-cli-usage + asc-id-resolver + asc-release-flow
- "Submit my iOS app to App Store review" -> asc-submission-health + asc-release-flow
- "Rotate expired iOS signing certificate" -> asc-signing-setup + asc-id-resolver
- "Investigate TestFlight crash after beta release" -> asc-crash-triage + asc-id-resolver
- "Upload Android AAB to Google Play internal track" -> gpd-cli-usage + gpd-id-resolver + gpd-build-lifecycle
- "Staged rollout to 10% on Google Play" -> gpd-release-flow + gpd-submission-health
- "Add testers to our Android beta group" -> gpd-betagroups + gpd-id-resolver
- "Run preflight before promoting Android to production" -> gpd-submission-health
- "Add pgvector to Cloud SQL for vendor matching" -> vector-database + database-schema-designer
- "Design a Weaviate collection for scraped reviews" -> vector-database → `/design-weaviate-collection`
- "Build a RAG pipeline for PDF documents" -> vector-database + weaviate-cookbooks + agentic-ai-dev
- "Switch from text-embedding-3-small to voyage-3-large" -> vector-database → `/migrate-embedding-model`
- "Tune HNSW index for 500K vendor embeddings" -> vector-database → `/tune-vector-index`
- "Search Weaviate collection with hybrid search" -> weaviate → `/weaviate:search`
- "Build a Query Agent chatbot on Weaviate" -> weaviate-cookbooks + agentic-ai-dev
- "Review my pgvector migration for correctness" -> pgvector-schema-reviewer agent
- "Set up Weaviate Cloud and load example data" -> weaviate → `/weaviate:quickstart`
- "Set up Stripe subscription billing with webhooks" -> stripe + python-dev + security-reviewer
- "Integrate RevenueCat IAP in Flutter with Riverpod" -> revenuecat + flutter-mobile + riverpod-patterns
- "Build Stripe Connect vendor payout flow" -> stripe + python-dev
- "Check RevenueCat entitlements via MCP" -> revenuecat (MCP tools: list_entitlements, get_customer)
- "Add Stripe + RevenueCat webhook handlers" -> stripe + revenuecat + python-dev + security-reviewer
- "Build a paywall screen in Flutter" -> revenuecat + flutter-mobile + ui-standards-tokens
- "Design type-safe generic DTOs for NestJS with DeepPartial" -> typescript-advanced-types + nestjs-api
- "Set up monorepo TypeScript with shared types between Angular and NestJS" -> typescript-expert + angular-spa + nestjs-api
- "Design type-safe NestJS decorators and strict config hierarchy" -> typescript-advanced-types + typescript-expert + nestjs-coding-standard
- "Debug slow TypeScript compilation in NestJS service" -> typescript-expert
- "Migrate JavaScript NestJS codebase to strict TypeScript" -> typescript-expert + nestjs-coding-standard

---

## Metadata Index

> Filter skills by domain, role, scope, or output type.

| Skill | Domain | Role | Scope | Output |
|-------|--------|------|-------|--------|
| a2ui-angular | frontend | specialist | implementation | code |
| genui-contract | frontend | architect | design | spec |
| adk-deploy-guide | infrastructure | specialist | deployment | code |
| adk-eval-guide | agentic-ai | specialist | evaluation | code |
| adk-observability-guide | backend | specialist | observability | code |
| agentic-ai-coding-standard | backend | specialist | review | report |
| agentic-ai-dev | backend | specialist | implementation | code |
| ai-chat | frontend | specialist | implementation | code |
| angular-spa | frontend | specialist | implementation | code |
| architecture-decision-records | api-architecture | architect | design | document |
| architecture-design | api-architecture | architect | design | architecture |
| browser-testing | quality | specialist | testing | report |
| changelog-generator | workflow | specialist | analysis | document |
| code-reviewer | quality | specialist | review | report |
| database-schema-designer | infrastructure | architect | design | document |
| docker | infrastructure | specialist | implementation | code |
| gcp-cloud-run | backend | specialist | deployment | code |
| gcp-finops | infrastructure | specialist | operations | document |
| ddd-architect | api-architecture | architect | system-design | architecture |
| dedup-code-agent | quality | specialist | analysis | report |
| documentation-generation | workflow | specialist | design | document |
| domain-finder | workflow | specialist | analysis | report |
| flutter-mobile | frontend | specialist | implementation | code |
| mobile-design | frontend | specialist | design | document |
| mobile-developer | frontend | specialist | implementation | code |
| frontend-design | frontend | specialist | design | code |
| google-adk | backend | specialist | implementation | code |
| java-coding-standard | backend | specialist | review | report |
| java-spring-api | backend | specialist | implementation | code |
| mcp-builder | backend | specialist | implementation | code |
| nestjs-api | backend | specialist | implementation | code |
| nestjs-coding-standard | backend | specialist | review | report |
| openapi-spec-generation | api-architecture | specialist | design | specification |
| api-design-principles | api-architecture | specialist | design | specification |
| plan-mode-review | workflow | architect | review | report |
| pr-review | quality | specialist | review | report |
| python-dev | backend | specialist | implementation | code |
| receiving-code-review | workflow | specialist | review | document |
| riverpod-patterns | frontend | specialist | implementation | code |
| claude-actions-auditor | security | specialist | review | report |
| sast-configuration | security | specialist | infrastructure | document |
| security-reviewer | security | specialist | review | report |
| subagent-driven-development | workflow | architect | design | document |
| systematic-debugging | quality | specialist | analysis | analysis |
| test-driven-development | quality | specialist | testing | code |
| threat-modeling | security | architect | design | document |
| ui-standards-tokens | frontend | specialist | design | document |
| verification-before-completion | workflow | specialist | review | report |
| writing-skills | workflow | specialist | design | document |
| the-fool | workflow | expert | review | report |
| iterate-pr | workflow | autonomous | pr-lifecycle | actions |
| feature-forge | workflow | specialist | design | document |
| brainstorm | workflow | specialist | exploration | document |
| debug | quality | specialist | analysis | analysis |
| audit-skills | workflow | specialist | governance | report |
| asc-cli-usage | mobile-deployment | specialist | deployment | commands |
| asc-id-resolver | mobile-deployment | specialist | deployment | commands |
| asc-signing-setup | mobile-deployment | specialist | deployment | commands |
| asc-release-flow | mobile-deployment | specialist | deployment | commands |
| asc-testflight-orchestration | mobile-deployment | specialist | deployment | commands |
| asc-submission-health | mobile-deployment | specialist | deployment | commands |
| asc-crash-triage | mobile-deployment | specialist | deployment | report |
| gpd-cli-usage | mobile-deployment | specialist | deployment | commands |
| gpd-id-resolver | mobile-deployment | specialist | deployment | commands |
| gpd-build-lifecycle | mobile-deployment | specialist | deployment | commands |
| gpd-betagroups | mobile-deployment | specialist | deployment | commands |
| gpd-release-flow | mobile-deployment | specialist | deployment | commands |
| gpd-submission-health | mobile-deployment | specialist | deployment | commands |
| vector-database | vector-db | specialist | implementation | code |
| weaviate | vector-db | specialist | implementation | code |
| weaviate-cookbooks | vector-db | specialist | implementation | code |
| typescript-advanced-types | backend | specialist | implementation | code |
| typescript-expert | backend | specialist | analysis | report |
| typescript-pro | backend | pointer | design | — |
| stripe | payments | specialist | implementation | code |
| revenuecat | payments | specialist | implementation | code |
| rules-distill | workflow | analyst | governance | report |
| codebase-onboarding | quality | specialist | analysis | document |
