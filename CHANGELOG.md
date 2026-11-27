# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.0.0] - 2026-11-27

Changes on `feat/flutter-mobile-engineering-best-practices` relative to `develop`.

### Added

- **`/next` engineering loop** — pick the next GitHub issue or local plan, implement, verify, and stop at a human merge gate. Optional experimental `/next --auto` coordination, a stricter `--fix-loop`, `/test-partner`, and verify summaries.
- **`/setup-aidlc`** — plan and, after approval, install official AWS AI-DLC (replaces the old `/aidlc` command).
- **Dual-mode `/startup-design`** — standalone G0–G10 from a product brief, or `--mode aidlc --bind-aidlc` to consume official AWS AI-DLC Ideation/Inception files (`aidlc/spaces/<space>/intents/<id>/`), run Stitch → `DESIGN.md` → prototype (G1–G5), and write `design/AIDLC_HANDOFF.md`. Construction stays `/aidlc`. `--approve-production` is refused in AI-DLC mode. AI-DLC remains optional and is never started from this command.
- **React 19.3 SPA path** — `react-spa` skill, builder agent, and `/scaffold-react-app` with Vite 8, Tailwind CSS 4.3, shadcn/ui (CLI 4.23.0, Base UI), React Router 8, TanStack Query 5, plus optional Next.js 16.4 App Router and React Router framework mode.
- **TypeScript MCP servers** — `/scaffold-mcp-server` for MCP TypeScript SDK v2 (`@modelcontextprotocol/server` 2.4.0, protocol 2026-07-28) with Streamable HTTP, auth, and observability references.
- **MONO-ARCH-001 polyglot architecture** — four explicit modes (native-only, Melos-only, Nx-only, Nx + Melos) with a copied spec at `docs/Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md`. Discover recommends a mode and stops for human approval before `nx init`. Flutter, Angular, Python, Spring, and MCP scaffolds can join an existing language workspace. This kit does not register Nx MCP; enable it only in a product repo that already has `nx.json`.
- **Graph audit** — `audit_monorepo_graph.py` fail-closes on missing projects/edges, empty graphs, empty expect files, cached `deploy`/`migrate`/`release`/`docker-push`, cached generated OpenAPI, missing Flutter-bridge inputs, and Python projects listed without explicit edges (plugin name is not proof).
- **Isolated fixture matrix** — `run_fixture_matrix.py` runs real Melos 8.10.1 and Nx 24.1.0 in `$TMPDIR` (never this kit or product repos): Melos `--diff` + dependents, one Flutter Nx bridge, lockfile/toolchain cache invalidation (`package-lock.json`, `pnpm-lock.yaml`, `uv.lock`), Python/uv and `@nx/gradle` inferred-vs-explicit edges, and native uv/Gradle builds after Nx rollback.
- **Flutter engineering pack** — path-scoped engineering and verification rules; Maestro-only Android/iOS UI/E2E routing; offline reliability, localization, build, and mobile security references; Riverpod and silent-failure advisories.
- **Angular UI modes** — daisyUI 5.8.2 (default), Spartan UI 1.10.1, or hybrid, with CLI-first scaffolding and a UI-mode detector.
- **Official UI skills** — vendored daisyUI, Spartan UI, shadcn/ui, and Angular developer skills (MIT).
- **Playwright Test Agents in `/next`** — official Planner / Generator / Healer as conditional specialists for Angular/React journeys (`browser-testing/reference/playwright-test-agents.md`). `/verify` and CI still run `playwright test`. Healer never skips, `test.fixme`s, or weakens assertions to hide application bugs. This toolkit does not vendor the generated agents or add a `playwright-test` MCP server. `init-agents --loop=claude` **replaces** product `.mcp.json`; scaffold docs require backup then `merge-playwright-test-mcp.py`.
- **`/next` E2E quality contract** — Flutter/Maestro and Angular/React/Playwright share the same gates (plan coverage, update tests, run on a real device/browser, classify FAIL vs TEST_DEFECT vs SETUP/INFRA, never weaken assertions, independent review). `--scan-skip-delta` fail-closes on new `test.fixme` / `test.skip` and on Maestro `optional: true`. No Maestro Planner/Generator/Healer agents.
- **Design system gate** — blocking `DESIGN.md` checks (atomic tiers, tokens, async UI states) at write time and in CI-style verification.
- **Accessibility** — WCAG 2.2 AA checklist with i18n/RTL guidance for web and Flutter.
- **A2UI 1.0** — generative UI contract (v0.9.x compatibility path), catalog validator, contract reviewer, and scaffold/parity/validate commands.
- **Python FastAPI depth** — architecture, auth, sessions, Alembic safety, reliability/idempotency, asyncio, uv packaging, and CI/supply-chain/Docker references.
- **Java 25 / Spring Boot 4.2** — Spring MVC + virtual threads as the default, WebFlux when justified, Boot 4.2 skill, scaffold, and `spring-boot-reviewer`.
- **NestJS 12** — Fastify + Prisma 7 skill, agents, scaffold, and verify gate.
- **AI lifecycle** — playbook router (guardrails G1–G24), threat-model attack classes AC-01–AC-18, eval-program validators, RAG response contract, PromptOps / PromptRegistry, and governance records.
- **Path-scoped rules** — Flutter, Python, web frontend, Node/MCP, AI engineering, GenUI, and hook/gate authoring load only when matching files are in play.
- **MCP servers** — Google Cloud (Run, IAM, logging, monitoring, Pub/Sub, Cloud SQL, Storage), Firebase emulator/Firestore, App Store Connect, Google Play, Stitch, Terraform, Spartan UI, mobile-mcp, and Weaviate local.
- **Toolkit CI** — `toolkit-lint` workflow, actionlint, SHA-pinned GitHub Actions, Dependabot, and Agent Skills spec activation checks.

### Changed

- **Stack pins** (guidance and scaffolds now target):
  - Java 21 → **25 LTS**; Spring Boot 3.5.x → **4.2.x** (Spring Framework 7.1)
  - Node.js 24.14.x → **26.13.x**; NestJS 11.17.x → **12.6.x**; TypeScript 5.9.x → **6.0.x**
  - FastAPI 0.135.2 → **0.165.x**; LangChain 1.2.8 → **1.5.2**; LangGraph 1.0.7 → **1.2.24**; Google ADK 1.28.0 → **2.15.1** (`google-genai` 2.34.x for ADK; 3.x stays on a separate lock)
  - Angular 21.2.x → **22.3.x**; Tailwind CSS **4.3.5**
  - Flutter 3.41.x / Dart 3.10.9 → **Flutter 3.50.x / Dart 3.14.0** (`material_ui` instead of deprecated `package:flutter/material.dart`)
  - PostgreSQL **18** + pgvector **0.8**; A2UI v0.8 → **1.0**
- **`startup-design-to-code`** — optional manifest `mode` / `aidlc` bind fields; gate `--bind-aidlc`, `--handoff-aidlc`, `--intent`, `--rebind-aidlc`, `--g5`; skill-spec activation case `startup-aidlc-positive`. Aidlc mode is opt-in (user asked, or already in `/aidlc`) plus a real intent dir — an `aidlc/` folder alone stays standalone. Standalone production approval is unchanged.
- **Polyglot skill** — Melos kit pin **8.10.1** (`dart run melos`, no `melos.yaml`); Nx **24.1.0** task-based affected (`inputs` / `^default`, not project edges alone). Python and Java are not inferred from JS; they need explicit `implicitDependencies` (and a Gradle companion plugin for `@nx/gradle` inference). Git `base` comes from the repo (`origin/HEAD`, then the existing local default), never an assumed `main`.
- **Scaffolds and `/new-project`** — Flutter, Angular, Python, Spring, and MCP still join an existing language workspace; there is still no `/scaffold-monorepo`. `/design-architecture` and `/new-project` route monorepo questions through `polyglot-monorepo`.
- **`/verify` and `/ship`** — impact-aware (run gates for stacks the diff can reach); `/verify` no longer authorizes a PR; merge still needs independent review.
- **Browser testing** — Playwright CLI for interactive web work, `@playwright/test` for regression, Chrome DevTools MCP for performance; official Test Agents are product-repo `/next` specialists, not a second E2E engine; Flutter device E2E stays on Maestro.
- **README** — rewritten as a landing page with current stack badges, a short `/next` path, and `/startup-design` dual-mode (standalone vs AI-DLC).
- **Procedures** — former `docs/workflows/` guides live in the matching skills so agents load one source of truth.
- **Always-loaded context** — core rules shortened and canaried so every session stays under a documented budget; stack details load on demand.
- **Reviewers** — stack reviewers are read-only; `spring-boot-reviewer` replaces `spring-reactive-reviewer`; RAG review is a single `rag-implementation-reviewer`.
- **Command and agent frontmatter** — slash-command YAML matches official Claude Code format (`name:` and `paths:` stripped; invalid descriptions quoted).

### Fixed

- **`/startup-design` dual-mode** — one mode decision tree; tell the human to open `/aidlc` instead of invoking it; `--record-mcp` requires `--evidence-kind` (or `--evidence none|discovered|mocked`) and no longer defaults a mock to `discovered`; bind runs before init writes; a bound `aidlc` object locks production even if `mode` was edited. Writes refuse `--root` or destinations under `aidlc/`. Re-bind after G2+ `PASS` needs `--rebind-aidlc`. Product brief prefers `requirements.md`. G4 requires headings and token data. Handoff and G5 saves run the prototype contract first.
- Angular scaffolding is CLI-first (`ng new` / `ng generate`); exact version pins; async errors surface instead of failing silent.
- React reference sources and UI skill templates pass the design gate; route chunk load failures show an error page instead of a blank screen.
- TypeScript skill examples compile on TypeScript 6.0.3.
- NestJS config is owned by one env schema; Docker images for Node 26 are digest-pinned and lockfile-driven.
- Java Boot 4.2 references (security, tests, and Boot 3 leftovers) corrected for MVC and WebFlux.
- Python `/verify`, scaffold, Alembic parity, and hook false positives.
- pgvector filtered-HNSW / generic-plan traps, Weaviate v4 `vector_config`, and RAG citation/tenant-isolation guidance.
- Agentic AI recursion limits, fail-closed guardrails, ADK session `await`s, and eval rank/A-B statistics.
- Hooks fail closed on unreadable review evidence; runtime state lives under `.git/claude-state`, not the working tree.
- Flutter/web UI skills follow `DESIGN.md`; Playwright suites gate on executed tests, not empty passes.

### Security

- Shared secret-pattern table for edit, prompt, and pre-commit scanners; nested `.env` deny; least-privilege permission examples.
- MCP servers pin packages and keep tokens in `${ENV_VAR}` / `env`, not process argv; Stripe MCP without a blanket `--tools` grant.
- Attack-class negative controls and AI asset gates fail closed (skipped/errored never counts as PASS).
- PII-in-logs advisories for Python and TypeScript; Python settings hide secrets in validation errors.
- MCP OAuth resource-server guidance; web XSS/model-output sanitization advisory; Flutter storage/privacy skill retained as the mobile reviewer.
- Raw `nx init` / `create-nx-workspace` still require `CC_NX_INIT=1`. `nx configure-ai-agents` is blocked on this kit even with that marker (it would rewrite `CLAUDE.md` / MCP). Fixture Nx installs are local `nx@24.1.0` with `npx --no-install`, not `npx --yes`.

### Removed

- **`docs/workflows/`** — content moved into skills (not dropped).
- **`/aidlc`** — use `/setup-aidlc` and the official AWS project.
- **Browser Use MCP** — web automation is Playwright CLI; the `browser-use` server is no longer registered.
- Retired hooks (`smart-suggest`, blackbox stop log, and several overlapping pre/post guards) in favor of parse-based bash guards and targeted advisories.

[Unreleased]: https://github.com/kumaran-is/claude-code-onboarding/compare/feat/flutter-mobile-engineering-best-practices...HEAD
[1.0.0]: https://github.com/kumaran-is/claude-code-onboarding/compare/develop...feat/flutter-mobile-engineering-best-practices
