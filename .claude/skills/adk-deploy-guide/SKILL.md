---
name: adk-deploy-guide
description: "MUST READ before deploying any ADK agent to Google Cloud — covers Cloud Run, Agent Engine, Vertex AI, event-driven agents, and ADK CI/CD pipelines. Use when deploying ADK agents to production, not for agent code patterns (use google-adk) or project scaffolding."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: deploy ADK agent, Cloud Run, Agent Engine, Vertex AI deployment, ADK production, ADK CI/CD
  related-skills: google-adk, agentic-ai-dev, python-dev
  domain: infrastructure
  role: specialist
  scope: deployment
  output-format: code
last-reviewed: "2026-11-23"
---

# ADK Deployment Guide

> **Scaffolded project?** Use `make` commands — they wrap Terraform, Docker, and deployment.
>
> **No scaffold?** See [Quick Deploy](#quick-deploy-adk-cli) below. For production infrastructure, see the `/scaffold-google-adk` command or load the `architecture-design` skill for infrastructure planning.

## Iron Law

**NEVER create GCP resources manually via `gcloud` for production. Define all infrastructure in Terraform.**
Exception: quick experimentation only — console or `gcloud` for throwaway resources is fine.

---

## Reference Files

| File | Contents |
|------|----------|
| `reference/agent-engine.md` | AdkApp pattern, deploy.py CLI, session/artifact services, CI/CD differences |
| `reference/cloud-run.md` | Dockerfile, session types, scaling defaults, networking, ingress, IAP |
| `reference/event-driven.md` | Pub/Sub, Eventarc, BigQuery Remote Function trigger patterns |
| `reference/terraform-patterns.md` | Custom resources, IAM bindings, state management, importing resources |

For agent code patterns and testing strategies, see `google-adk` skill. For evaluations and observability, see `adk-eval-guide` and `adk-observability-guide` skills.

---

## Deployment Target Decision Matrix

| Criteria | Agent Engine | Cloud Run |
|----------|-------------|-----------|
| **Deployment** | Source-based, no Docker | Dockerfile + container image |
| **Scaling** | Managed auto-scaling | Fully configurable (min/max instances) |
| **Session state** | Native `VertexAiSessionService(project=, location=, agent_engine_id=)` | In-memory (dev only), Cloud SQL via `DatabaseSessionService` (`postgresql+asyncpg://`), or Agent Engine backend |
| **Event-driven** | Not supported | Pub/Sub, Eventarc, BigQuery Remote Function via `/invoke` |
| **Cost model** | vCPU-hours + memory-hours (not billed when idle) | Per-instance-second + min instance costs |
| **Setup complexity** | Lower — managed, purpose-built for agents | Medium — Dockerfile, Terraform, networking |
| **Best for** | Minimal ops, managed infrastructure | Event-driven workloads, full infrastructure control |

Ask the user which target fits their needs before proceeding.

---

## Quick Deploy (ADK CLI)

No Makefile, Terraform, or Dockerfile required.

```bash
# Cloud Run
adk deploy cloud_run --project=PROJECT --region=REGION path/to/agent/

# Agent Engine
adk deploy agent_engine --project=PROJECT --region=REGION path/to/agent/
```

Both support `--with_ui` to deploy the ADK dev UI. Cloud Run accepts extra `gcloud` flags after `--`.

---

## Process

1. **Gather requirements** — target (Agent Engine vs Cloud Run), project ID, region, secrets needed
2. **Choose target** — use the decision matrix above; ask if unclear
3. **Scaffold or write Terraform** — run `/scaffold-google-adk` or manually write `deployment/terraform/`
4. **Configure auth and secrets** — model access is keyless (below); remaining credentials in Secret Manager, read at runtime
5. **Gate** — the eval suite passes on the exact image and model id before any traffic (below)
6. **Deploy** — `make deploy` (scaffolded) or `adk deploy <target>` (CLI); gradual traffic with a rollback (`deployment-ci-cd/reference/llmops-release-and-rollout.md`)
7. **Verify** — health check endpoint, a smoke request, then load tests

---

## Keyless model access and config

- Deployed agents call Gemini through Vertex AI with the runtime service account (ADC): `GOOGLE_GENAI_USE_ENTERPRISE=true` (google-genai 2.34 deprecates `GOOGLE_GENAI_USE_VERTEXAI`; set the new name), `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`. No developer API key exists in staging or production — not in the image, env vars or Secret Manager — and app settings fail startup if one is present (`google-adk/reference/adk-project-config.md` §3).
- Grant the runtime service account only the Vertex AI role it needs (e.g. `roles/aiplatform.user`) in Terraform.
- The model id is configuration (`AGENT_MODEL`), set per environment in Terraform/deploy config. A model id proven on the developer API is not proven on Vertex: probe it on the target endpoint before promoting (`gemini-api-dev` skill, "Models").

## Eval gate before traffic

Deploy the candidate revision with no traffic, run the agent eval suite against it, and promote only on pass. Example GitHub Actions job (adapt names; run `actionlint` before committing):

```yaml
  eval-gate:
    needs: deploy-staging-no-traffic
    runs-on: ubuntu-latest
    permissions: { contents: read, id-token: write }
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: google-github-actions/auth@<pinned-sha>
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.EVAL_RUNNER_SA }}
      - uses: astral-sh/setup-uv@<pinned-sha>
      - run: uv sync --locked
      # pytest wrapper around AgentEvaluator.evaluate(...): fails the job on a failed case
      - run: uv run pytest -q tests/evals/test_agent_eval.py
  promote:
    needs: eval-gate          # no promotion without a passing gate
```

Since google-adk 2.13 `adk eval` exits 1 when any case fails or no results were produced (1.29 printed "Tests failed: N" and exited 0, so pin ≥ 2.13 before trusting the exit code). Inside pytest, `AgentEvaluator.evaluate(agent_module, eval_dataset_file_path_or_dir, num_runs=2)` raises on failure; `agent_module` may be a module path, a `Workflow`/agent node or an `App` in 2.x. The gate fails closed: a missing evalset, zero cases run or an errored judge is a failure, not a pass. Criteria and thresholds: `adk-eval-guide` skill; CI tiers: `eval-guide/reference/ci-tiers.md`.

---

## Secret Manager

```bash
# Create / update from a file or stdin prompt — never put the value in shell history
gcloud secrets create MY_SECRET_NAME --data-file=/path/to/secret-file
gcloud secrets versions add MY_SECRET_NAME --data-file=/path/to/secret-file

# Agent Engine: pass at deploy time
make deploy SECRETS="API_KEY=my-api-key,DB_PASS=db-password:2"
```

Grant `secretmanager.secretAccessor` to `app_sa` (Cloud Run) or `service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (Agent Engine).

---

## Documentation Sources

| Source | URL | Purpose |
|--------|-----|---------|
| ADK Deployment | `https://google.github.io/adk-docs/deploy/` | Official deployment docs |
| Cloud Run | `https://google.github.io/adk-docs/deploy/cloud-run/index.md` | Cloud Run specifics |
| Agent Engine | `https://google.github.io/adk-docs/deploy/agent-engine/index.md` | Agent Engine specifics |

---

---

## Production Deployment — CI/CD Pipeline

**Best for:** Production applications, teams requiring staging → production promotion.

**Prerequisites:**
1. Project must NOT be in a gitignored folder
2. User must provide staging and production GCP project IDs
3. GitHub repository name and owner

**Steps:**
1. If prototype, first add Terraform/CI-CD files using the Agent Starter Pack CLI:
   ```bash
   uvx agent-starter-pack enhance . --cicd-runner github_actions -y -s
   ```

2. Ensure you're logged in to GitHub CLI:
   ```bash
   gh auth login  # (skip if already authenticated)
   ```

3. Run setup-cicd:
   ```bash
   uvx agent-starter-pack setup-cicd \
     --staging-project YOUR_STAGING_PROJECT \
     --prod-project YOUR_PROD_PROJECT \
     --repository-name YOUR_REPO_NAME \
     --repository-owner YOUR_GITHUB_USERNAME \
     --auto-approve \
     --create-repository
   ```

4. Push code to trigger deployments

### Key `setup-cicd` Flags

| Flag | Description |
|------|-------------|
| `--staging-project` | GCP project ID for staging environment |
| `--prod-project` | GCP project ID for production environment |
| `--repository-name` / `--repository-owner` | GitHub repository name and owner |
| `--auto-approve` | Skip Terraform plan confirmation prompts |
| `--create-repository` | Create the GitHub repo if it doesn't exist |
| `--cicd-project` | Separate GCP project for CI/CD infrastructure. Defaults to prod project |
| `--local-state` | Store Terraform state locally instead of in GCS |

### Choosing a CI/CD Runner

| Runner | Pros | Cons |
|--------|------|------|
| **github_actions** (Default) | No PAT needed, uses `gh auth`, WIF-based, fully automated | Requires GitHub CLI authentication |
| **google_cloud_build** | Native GCP integration | Requires interactive browser authorization (or PAT + app installation ID for programmatic mode) |

### How Authentication Works (WIF)

Both runners use **Workload Identity Federation (WIF)** — GitHub/Cloud Build OIDC tokens are trusted by a GCP Workload Identity Pool, which grants `cicd_runner_sa` impersonation. No long-lived service account keys needed. Terraform in `setup-cicd` creates the pool, provider, and SA bindings automatically. If auth fails, re-run `terraform apply` in the CI/CD Terraform directory.

### CI/CD Pipeline Stages

The pipeline has three stages:

1. **CI (PR checks)** — Triggered on pull request. Runs lint, type check, unit tests with the fake model (`uv sync --locked`), and the fast eval tier.
2. **Staging CD** — Triggered on merge to `main`. Builds the container, deploys to staging with no traffic, runs the eval gate (above), then shifts traffic and runs load tests.
   > **Path filter:** Staging CD uses `paths: ['app/**']` — it only triggers when files under `app/` change. If nothing happens after the first push after `setup-cicd`, this is why.
3. **Production CD** — Triggered after successful staging deploy. May require **manual approval** before deploying to production.
   > **Approving:** Go to GitHub Actions → the production workflow run → click "Review deployments" → approve the pending `production` environment. This is GitHub's environment protection rules.

**IMPORTANT**: `setup-cicd` creates infrastructure but doesn't deploy automatically. Push code to trigger the pipeline:

```bash
git add . && git commit -m "Initial agent implementation"
git push origin main
```

To approve production deployment:

```bash
# GitHub Actions: Approve via repository Actions tab (environment protection rules)

# Cloud Build: Find pending build and approve
gcloud builds list --project=PROD_PROJECT --region=REGION --filter="status=PENDING"
gcloud builds approve BUILD_ID --project=PROD_PROJECT
```

### Service Account Architecture

Scaffolded projects use two service accounts:

- **`app_sa`** (per environment) — Runtime identity for the deployed agent. Roles defined in `deployment/terraform/iam.tf`.
- **`cicd_runner_sa`** (CI/CD project) — CI/CD pipeline identity (GitHub Actions / Cloud Build). Needs permissions in both staging and prod projects.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent Engine deploy timeout | Check if engine was created; manually populate `deployment_metadata.json` |
| 403 on deploy | `cicd_runner_sa` missing deployment role or SA impersonation in target project |
| 403 testing Cloud Run | Add `Authorization: Bearer $(gcloud auth print-identity-token)` header |
| Secret access denied | Verify `secretAccessor` granted to `app_sa`, not default compute SA |
| Cold starts slow | Set `min_instance_count > 0` in Cloud Run Terraform config |
| Resource already exists | Use `terraform import` — see `reference/terraform-patterns.md` |
