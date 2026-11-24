---
name: gcp-cloud-run
description: "GCP Cloud Run deployment skill. Use for Cloud Run Functions (event-driven Pub/Sub, Storage, HTTP webhooks), cold start optimization, and Cloud Run anti-pattern prevention. For Cloud Run service deployment use deployment-engineer agent. Triggers: cloud run, cloud function, pub/sub trigger, cold start, serverless, event-driven GCP, cloud storage trigger."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
metadata:
  triggers: ["cloud run", "cloud function", "pub/sub trigger", "cold start", "serverless", "event-driven GCP", "cloud storage trigger"]
  related-skills: [docker, adk-deploy-guide, architecture-design]
  domain: backend
  role: specialist
  scope: deployment
  output-format: code
last-reviewed: "2026-03-14"
---

# GCP Cloud Run

## Iron Law

```
NO CLOUD RUN FUNCTION WITHOUT:
1. A stack-specific health check endpoint (GET /health → 200)
2. GitHub Actions workflow (NEVER cloudbuild.yaml)
3. Workload Identity Federation (NEVER service account JSON keys)
```

---

## This Skill vs `deployment-engineer` Agent

| Task | Use This Skill | Use `deployment-engineer` Agent |
|------|---------------|---------------------------------|
| Pub/Sub consumer function | YES | No |
| Cloud Storage trigger function | YES | No |
| HTTP webhook / short-lived invocation | YES | No |
| Cold start optimization | YES | No |
| Long-running Cloud Run **service** | No | YES |
| CI/CD pipeline design (service) | No | YES |
| Terraform Cloud Run service module | No | YES (`terraform-specialist`) |

**Key distinction:** Cloud Run **Functions** = event-driven, ephemeral, short-lived invocations.
Cloud Run **Services** = long-running, persistent, serve steady traffic → use `deployment-engineer`.

---

## Pattern Selector

```
What are you building?
    |
    +-- Pub/Sub consumer, Storage trigger, HTTP webhook?
    |   -> Load: reference/cloud-run-functions.md
    |   -> Pick your stack section (Python, NestJS, Spring Boot, TypeScript/Fastify)
    |
    +-- Cold start is too slow in staging or prod?
    |   -> Load: reference/cold-start-optimization.md
    |   -> Apply flags from the optimization table
    |
    +-- Reviewing existing Cloud Run code or config?
        -> Load: assets/cloud-run-antipatterns.md
        -> Run through checklist before declaring done
```

---

## Quick Start Checklist

Before writing any Cloud Run Function code:

- [ ] Chose event trigger type: Pub/Sub push | Cloud Storage notification | HTTP
- [ ] Selected target stack: Python FastAPI | NestJS | Spring Boot WebFlux | TypeScript/Fastify
- [ ] Verified runtime version: `python:3.14.10-slim-trixie@sha256:<digest>` | `node:24-alpine` | `eclipse-temurin:21-jre-alpine`
- [ ] Confirmed port binding: `PORT` env var (Cloud Run injects this, default 8080)
- [ ] Health check endpoint planned: `GET /health` → `{ "status": "ok" }`
- [ ] WIF configured or planned (no service account JSON keys)
- [ ] `docker` skill loaded for Dockerfile (multi-stage, non-root user)

---

## Reference Files

| File | Load When |
|------|-----------|
| `reference/cloud-run-functions.md` | Writing a Pub/Sub, Storage, or HTTP trigger function |
| `reference/cold-start-optimization.md` | Function is slow to start or you need `--cpu-boost` flags |
| `assets/cloud-run-antipatterns.md` | Reviewing any Cloud Run code or config for correctness |

---

## Cross-References

- **Dockerfiles**: Load `docker` skill → `reference/dockerfiles.md` for all 4 stack Dockerfiles
- **Cloud Run Service (long-running)**: Dispatch `deployment-engineer` agent
- **Terraform infrastructure**: Dispatch `terraform-specialist` agent
- **ADK agent on Cloud Run**: Use `adk-deploy-guide` skill (has ADK-specific Cloud Run patterns)
- **GitHub Actions pipeline**: `docs/workflows/deployment-ci-cd.md`
- **Security review (WIF, secrets)**: Dispatch `security-reviewer` agent after implementation

---

## GitHub Actions Deploy Snippet (All Stacks)

```yaml
# .github/workflows/deploy-function.yml
name: Deploy Cloud Run Function

on:
  push:
    branches: [develop, main]

env:
  PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}
  REGION: us-central1
  FUNCTION_NAME: my-function
  REGISTRY: ${{ vars.GCP_REGION }}-docker.pkg.dev

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write    # Required for Workload Identity Federation
      contents: read

    steps:
      - uses: actions/checkout@<40-hex-sha> # v4.x.y (pin by SHA; see deployment-ci-cd/reference/python-ci-supply-chain.md)

      - name: Authenticate to GCP
        uses: google-github-actions/auth@<40-hex-sha> # v2.x.y
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.WIF_SERVICE_ACCOUNT }}

      - name: Build and push image
        run: |
          docker build -t $REGISTRY/$PROJECT_ID/$FUNCTION_NAME:${{ github.sha }} .
          gcloud auth configure-docker $REGISTRY --quiet
          docker push $REGISTRY/$PROJECT_ID/$FUNCTION_NAME:${{ github.sha }}

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy $FUNCTION_NAME \
            --image $REGISTRY/$PROJECT_ID/$FUNCTION_NAME:${{ github.sha }} \
            --region $REGION \
            --platform managed \
            --no-allow-unauthenticated \
            --cpu-boost \
            --min-instances 0 \
            --max-instances 10
```

> For cold start flags (`--cpu-boost`, `--min-instances`, memory/CPU ratio), see `reference/cold-start-optimization.md`.
