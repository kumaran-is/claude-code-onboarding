# Skills Guide

> Routing for the Claude Code Onboarding Kit: which skill, builder agent, scaffold command and reviewer agent own each technology. This is the table `CLAUDE.md`, `writing-skills` (step 7, REGISTER) and the orchestration reference point to.
>
> It deliberately holds only routing. What each skill or agent does is its own `description` (listed by Claude Code at session start) and its `SKILL.md` / agent file; a second catalog of those drifted, so it was removed.
>
> **Lazy-load pattern:** Each SKILL.md is a routing document only. Detailed patterns live in `reference/` files within each skill directory. Load the reference file explicitly when the detail is needed — do not expect it to be loaded automatically.

---

## Routing: technology → skill, agent, command

> Canonical routing table (moved from CLAUDE.md so it loads on demand). Load the skill BEFORE writing code in that domain; dispatch the domain's reviewer after.

| Technology | Skill | Agent | Command |
|------------|-------|-------|---------|
| Java / Spring Boot | `.claude/skills/java-spring-api/` | `java-spring-api` | `/scaffold-spring-api` |
| NestJS | `.claude/skills/nestjs-api/` | `nestjs-api` | `/scaffold-nestjs-api` |
| MCP servers (TypeScript, SDK v2, Node 26 LTS) | `.claude/skills/mcp-builder/` | — | `/scaffold-mcp-server` |
| Python / FastAPI | `.claude/skills/python-dev/` | `python-dev` | `/scaffold-python-api` |
| Agentic AI (framework-neutral core + LangChain/LangGraph; inference, tools, memory) | `.claude/skills/agentic-ai-dev/` (`reference/agentic-architecture-choice.md`, `llm-inference-and-model-routing.md`, `tool-execution-safety.md`, `agentic-memory-systems.md`) | `agentic-ai-dev` | `/scaffold-agentic-ai` |
| Google ADK (optional extension) | `.claude/skills/google-adk/` | `google-adk` | `/scaffold-google-adk` |
| Angular (UI mode `daisyui` default, `spartan`, `hybrid`: `angular-spa/reference/ui-mode-selection.md`; official `daisyui` and `spartan` skills by mode; official Angular team skill `angular-developer`, with `angular-new-app` as reference only) | `.claude/skills/angular-spa/` | `angular-spa` | `/scaffold-angular-app [--ui=…]` |
| React (web SPA; Tailwind CSS v4 + shadcn/ui on Base UI, official `shadcn` skill vendored; full-stack choice in `/scaffold-react-app`; not React Native) | `.claude/skills/react-spa/` (`reference/tailwind-shadcn.md`), `.claude/skills/shadcn/` | `react-spa` | `/scaffold-react-app` |
| GenUI contract (suitability gate, A2UI 1.0 target + v0.9.x compatibility, cross-platform catalog, shared/standalone backends, AG-UI, CopilotKit) | `.claude/skills/genui-contract/` | `genui-contract-reviewer` | `/scaffold-genui-feature`, `/audit-a2ui-parity`, `/validate-genui-feature` |
| Angular GenUI (A2UI renderer) | `.claude/skills/a2ui-angular/` | `a2ui-angular` | `/scaffold-a2ui` |
| Web security (CSP, Trusted Types, XSS sinks, tokens, CSRF, OIDC PKCE) | `.claude/skills/security-reviewer/reference/web-frontend-security.md` | `security-reviewer` | `/xss-scan` |
| Web performance + SEO (public sites only) | `.claude/skills/web-performance-optimization/` | `performance-oracle` | — |
| Web delivery (static hosting, runtime config, cache headers, post-deploy checks) | `.claude/skills/deployment-ci-cd/reference/web-frontend-delivery.md` | `deployment-engineer` | — |
| Design system (all UI stacks: project `DESIGN.md` discovery and precedence, tokens, icons, motion, Atomic tiers, smart/dumb, async states, refresh strategy) | `.claude/skills/design-system/` (`reference/design-md-governance.md`, `atomic-decision-tree.md`, `token-governance.md`, `interaction-contracts.md` §6b–6c), Flutter token scales `.claude/skills/ui-standards-tokens/` | `ui-standards-expert`, `design-system-reviewer` | `/lint-design-system` (`.claude/scripts/check-design-system.py`) |
| Startup idea → Stitch → DESIGN.md → prototype → production UI (G0–G10) | `.claude/skills/startup-design-to-code/` | existing UI reviewers (`ui-standards-expert`, `design-system-reviewer`, `accessibility-auditor`); no new agent | `/startup-design` |
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
| Polyglot monorepo (Dart/Melos, uv, npm, optional Nx, Makefile — decision only) | `.claude/skills/polyglot-monorepo/` | `architect` (no new agent) | `/design-architecture` (no `/scaffold-monorepo`) |
| Plan Review | `.claude/skills/plan-mode-review/` | — | `/plan-review` |
| Browser Testing | `.claude/skills/browser-testing/` | `browser-testing` | — |
| Next work item (`/next`, GitHub issues/project, local plans, blockers, verification, implementation notes; opt-in `/next --auto`) | `.claude/skills/next-issue/` (`references/implementation-notes.md`, `references/auto-loop.md`) | — | `/next` |
| AWS AI-DLC (optional; official `aidlc` CLI + `/aidlc`; not a copy of the engine; independent of `/next`) | `.claude/skills/aws-aidlc-integration/` | — | `/setup-aidlc` |
| Partner testing (paired manual QA, findings ledger, fix/retest) | `.claude/skills/test-partner/` | — | `/test-partner` |
| Session wrap (checkpoint snapshot + lessons + failed approaches + dirty/unpushed + resume prompt) | `/checkpoint` then `/promote-lessons` then handoff | — | `/end-session` |
| Debugging | `.claude/skills/systematic-debugging/` | — | `/debug` |
| Verification | `.claude/skills/verification-before-completion/` | — | — |
| SDD Pipeline (execution ledger + task briefs + independent review package; not AWS AI-DLC) | `.claude/skills/subagent-driven-development/` (`reference/execution-ledger.md`) | stack reviewers in the skill | — |
| Critical Reasoning | `.claude/skills/the-fool/` | — | — |
| Requirements / Feature Spec | `.claude/skills/feature-forge/` | — | — |
| Brainstorm / Explore Options (optional; never a gate on `/next` or an approved plan) | — | — | `/brainstorm` |
| Git worktree isolation (optional; collision detect; do not stash) | `.claude/scripts/check-worktree-isolation.py` | — | `/worktree-sync` |
| Stripe Payments | `.claude/skills/stripe/` | — | — |
| RevenueCat Subscriptions | `.claude/skills/revenuecat/` | — | — |
| AI Feature Design | `.claude/skills/ai-decision-record/` | — | `/ai-decision-record` |
| AI Launch Gate | `.claude/skills/ai-launch-check/` | — | `/ai-launch-check` |
| AI Feature Audit | `.claude/skills/ai-audit/` | — | `/ai-audit` |
| Enterprise AI governance (risk tier Low–Critical, autonomy A0–A4, approval records, control register/evidence, AI BOM, readiness, regulatory register, incident records; validator) | `.claude/skills/ai-governance/` | — | `/ai-audit` (governance modes) |
| AI engineering domains (eval, guardrails G1–G24, ten laws L1–L10, governance, incident response, security/red team AC-01–AC-18, data governance/privacy, model routing, PromptOps, RAG, memory) | Router: `.claude/skills/ai-playbook/` (Lifecycle router). Homes not named there: guardrails + ten laws `ai-playbook/reference/engineering-guardrails.md`, data governance `ai-playbook/reference/data-governance-privacy.md`, attack classes `security-reviewer/reference/ai-threat-model-attack-classes.md`, routing `agentic-ai-dev/reference/agentic-llm-routing.md`, memory `agentic-ai-dev/reference/agent-memory-lifecycle.md`, PromptOps `prompt-engineering-patterns/reference/promptops-lifecycle.md`. Section labels (`DGP §6.2`, `PRM §8`, `guardrails §3`) are numbered sections of those homes; governance §n → `ai-governance/reference/boundary-map.md`. Stricter security/domain rule wins; proposed AI commands → existing: `ai-playbook/SKILL.md` "Proposed AI commands" | — | — |
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

### Reviewer agents by domain

| Domain | Reviewer Agent |
|--------|----------------|
| General | `code-reviewer` |
| Java / Spring | `spring-boot-reviewer` |
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
