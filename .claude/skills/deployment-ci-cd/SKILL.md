---
name: deployment-ci-cd
description: CI/CD pipeline design and deployment automation for all stacks — GitHub Actions workflows, Docker multi-stage builds, Cloud Run deployments, Flutter distribution, and Firebase rule deployments. Use when setting up or reviewing CI/CD pipelines, deployment workflows, or automated release processes.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
agent: deployment-engineer
context: fork
metadata:
  triggers: CI/CD, github actions, deploy, pipeline, cloud run deploy, firebase deploy, flutter build pipeline, docker build, deployment workflow, automated release
  related-skills: docker, gcp-cloud-run, terraform-skill, flutter-mobile
  domain: infrastructure
  role: specialist
  scope: implementation
  output-format: implementation
last-reviewed: "2026-11-22"
---

## Iron Law

Never design a deployment pipeline without knowing the rollback strategy — every deploy step must be reversible or have an explicit break-glass procedure.

# Deployment CI/CD

CI/CD pipeline design and deployment automation specialist covering GitHub Actions, Docker, Cloud Run, Flutter mobile distribution, and Firebase deployments.

## When to Use

- Setting up a new GitHub Actions CI/CD pipeline
- Reviewing an existing deployment workflow
- Designing Docker multi-stage build optimization
- Setting up Cloud Run progressive delivery (traffic splitting)
- Automating Flutter builds and distribution to Firebase App Distribution
- Configuring Firebase Hosting, Firestore rules, or Functions deployment

## Pipeline Patterns by Stack

| Stack | Build | Test | Deploy |
|-------|-------|------|--------|
| **NestJS** | Docker multi-stage | Vitest | Cloud Run (canary → prod) |
| **Spring Boot** | Maven + Docker | JUnit | Cloud Run (health check gate) |
| **Python/FastAPI** | Docker + uv (`--locked`, `reference/python-ci-supply-chain.md`) | pytest | Cloud Run service; Cloud Run Functions only for single-purpose event handlers |
| **Angular** | `npm ci` + `ng build` (production is the default; `--prod` was removed), Node pinned via `.nvmrc` | `ng test` (Vitest, the default since v21) + Playwright E2E | Static hosting: preview → promote same files → post-deploy header check (`reference/web-frontend-delivery.md`) |
| **React** | `npm ci` + `npm run build` (`tsc -b && vite build`), Node pinned via `.nvmrc` | `vitest run` + Playwright E2E (+ axe) | Static hosting, same flow as Angular (`reference/web-frontend-delivery.md`) |
| **Flutter** | `flutter build appbundle/ipa` | `flutter analyze` + `flutter test`; device UI/E2E with Maestro only (missing device → BLOCKED, never a browser) | Firebase App Distribution → Google Play staged rollout / App Store (`reference/flutter-ci.md`) |
| **MCP server (Node/Python)** | Docker, non-root pinned image | protocol conformance, tool contracts, authn/authz negative cases | Cloud Run service (`reference/node-ci-and-observability.md`) |
| **AI / RAG** | as the host service | deterministic + contract tests on every PR; eval tiers gate promotion | Eval-gated canary for prompt/model changes (`reference/llmops-release-and-rollout.md`) |
| **GenUI (A2UI)** | as each renderer | contract schema + fixtures, declared-platform parity | with the host apps (`reference/genui-contract-ci.md`) |

## Key Principles

- **Multi-stage Docker**: separate build and runtime stages; never ship dev dependencies
- **Health check gate**: Cloud Run deploy must pass health check before traffic shift
- **Secret management**: use Workload Identity Federation (not service account keys)
- **Progressive delivery**: canary → 10% → 50% → 100% with automated rollback on error rate spike
- **Container scanning**: Trivy scan before push to Artifact Registry

## Process

1. Identify target stack and deployment environment
2. Load `docker` skill for Dockerfile patterns (if containerizing)
3. Load `gcp-cloud-run` skill for Cloud Run-specific patterns (if deploying to GCP)
4. Design pipeline stages: build → test → security scan → push → deploy → verify
5. Define rollback strategy for each stage
6. Output GitHub Actions workflow YAML + deployment configuration

## Reference Files

| File | Load when |
|------|-----------|
| `reference/python-ci-supply-chain.md` | Python CI gate design, SHA/digest pins, `--locked` installs, dependency audit commands, path filters, uv Dockerfile, deploy hygiene |
| `reference/node-ci-and-observability.md` | Node 26 / TypeScript 6.0 services and MCP servers: OpenTelemetry JS 3.x bootstrap (sync ESM hook) and shutdown order, pino with trace ids and redaction, GitHub Actions gates (tsc, lint, tests with executed > 0, `npm ci`, `npm audit` + `npm audit signatures`), non-root pinned image |
| `reference/python-observability.md` | JSON logs, PII-safe exception logging, OpenTelemetry wiring and span test, request ids, metrics, probes, readiness checklist |
| `reference/ai-observability.md` | LLM/agent/RAG tracing (OTel GenAI semconv), token/cost/TTFT metrics, content-capture redaction, Langfuse (optional), AI SLOs, drift, incident replay |
| `reference/llmops-release-and-rollout.md` | Prompt/model versioning, eval-gated promotion, canary + rollback for prompt/config changes, provider migration, feedback loop |
| `reference/health-endpoints.md` | Liveness/readiness endpoints per stack; Cloud Run probe flags |
| `reference/env-config-validation.md` | Fail-fast configuration |
| `reference/web-frontend-delivery.md` | Browser apps on static hosting: `npm ci` + Node pin, runtime `config.json` validated at boot (fail closed), hashed-immutable vs `no-cache` caching, previews, promote/rollback, private source maps, post-deploy header check script, error monitoring, OTel browser (experimental) + `traceparent` CORS |
| `reference/flutter-ci.md` | Flutter PR gate (GitHub Actions example): SDK pinned via `flutter-version-file`, `--enforce-lockfile`, codegen before analyze, format/analyze/test/release build, separate advisory Maestro device job, signing only in the release workflow |
| `reference/genui-contract-ci.md` | GenUI A2UI v0.9 contract CI (GitHub Actions example): path-filtered catalog schema + fixtures, action payload compatibility, protocol version, declared-platform parity, tsc/analyze/unit, security negative controls, Playwright + axe (web), hook selftest, link check |

## Production Readiness Checklist

Before any production deploy, verify ALL of the following. If any item is NO → do not deploy.

### Application
- [ ] Liveness endpoint (process only) AND, for services with dependencies, a startup/readiness endpoint that checks them with a per-check timeout; a liveness probe must not call dependencies (see `reference/health-endpoints.md`)
- [ ] Python: JSON logs, PII-safe exception logging, request-id/trace-id join, spans proven emitted (`reference/python-observability.md`)
- [ ] All required env vars validated at startup — app fails fast if missing (see `reference/env-config-validation.md`)
- [ ] No secrets hardcoded in source code or committed config files
- [ ] `.env.example` committed with all keys, placeholder values only
- [ ] Error handling: all catch blocks log + rethrow or return error state (no silent failures)

### Container / Docker
- [ ] Multi-stage Dockerfile — dev deps not in production image
- [ ] Non-root user in Dockerfile (`USER appuser`)
- [ ] Base image pinned `tag@sha256:<index digest>`; no `:latest`; no `COPY --from=<image-ref>`; Python installs `uv sync --locked`
- [ ] Config is not baked into the image (no `ENV` for env-varying values); required settings fail loudly at startup
- [ ] HEALTHCHECK instruction in Dockerfile
- [ ] `.dockerignore` excludes: `node_modules`, `.git`, `.env`, `dist`, `coverage`
- [ ] `docker scout` or `trivy image` scan — zero CRITICAL CVEs

### CI/CD Pipeline
- [ ] Tests pass (all: unit + integration) AND executed count > 0 (an all-skipped run exits 0); infra-dependent tests FAIL, not skip, in CI (`REQUIRE_<X>=1`)
- [ ] Linting + type-check pass (zero errors)
- [ ] Container image pushed to Artifact Registry with commit SHA tag; deploy by digest and record the running digest/revision
- [ ] Every `uses:` pinned to a 40-hex SHA (`# vX.Y.Z` comment); runner image and tool versions pinned; `actionlint` green
- [ ] Path filters list every file the test run loads (`conftest.py`, `pyproject.toml`, lock, `.python-version`); required checks do not rely on trigger-level path filters
- [ ] Dependency audit gated on the tool's EXIT CODE (`pip-audit` prints no severity; `pip audit` is not a command): `reference/python-ci-supply-chain.md`
- [ ] Health check gate passes before any traffic shift (startup probe: `gcloud run deploy --startup-probe 'httpGet.path=...'`; the `--*-probe-path` flags do not exist)
- [ ] Migration job runs first and aborts the whole release on failure; order: migration -> APIs -> workers -> edge
- [ ] Rollback strategy defined and tested for this deploy (Cloud Run: traffic pin to the previous revision; "redeploy the old SHA" is unproven until rehearsed)

### Cloud Run (GCP Stack)
- [ ] Workload Identity Federation configured — no service account key files
- [ ] Deploy uses `--no-traffic` first → canary 10% → verify → 100%
- [ ] Memory limits set (`--memory` flag matches actual service requirements)
- [ ] Concurrency configured (`--concurrency` — default 80, tune per service)
- [ ] Min instances = 0 for cost (or 1+ for latency-sensitive services)

### Security
- [ ] `security-reviewer` agent verdict: no CRITICAL or HIGH findings
- [ ] Code-review verdict per the Review Severity Policy (`.claude/rules/verification-and-reporting.md`): no CRITICAL; each HIGH fixed or justified in the PR; MEDIUM/LOW tracked as advisories
- [ ] All API endpoints require authentication (no accidental public exposure)
- [ ] CORS policy explicitly configured (not wildcard `*` in production)
- [ ] Secrets stored in Secret Manager, not Cloud Run env vars directly

### Post-Deploy Verification
- [ ] Health endpoint returns 200 on new revision URL
- [ ] Smoke test: critical user flow works end-to-end
- [ ] Error rate < 0.1% for 5 minutes post-deploy
- [ ] Rollback procedure verified working (test once per quarter)
