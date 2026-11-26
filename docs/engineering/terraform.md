# GCP infrastructure (Terraform)

Moved from the public README so the landing page stays short. Content is unchanged except where noted. Provisioning is owned by `@terraform-specialist`; deploying images is owned by `@deployment-engineer`.

## 19b. GCP Infrastructure — Terraform Specialist Agent

The `terraform-specialist` agent provisions and manages all GCP infrastructure as code. It handles what the deployment-engineer doesn't — creating the platform your services run on.

**Rule of thumb:** terraform-specialist runs *once* (or when infra changes). deployment-engineer runs *on every merge*.

```
terraform-specialist          deployment-engineer
─────────────────────────────────────────────────
Creates Cloud Run service  →  Deploys image to it
Creates Artifact Registry  →  Pushes Docker images
Creates Secret Manager     →  Reads secrets at runtime
Sets up Workload Identity  →  Uses it in CI pipeline
Runs rarely                   Runs on every PR merge
```

### What it provisions for your stack

| Resource | Terraform resource |
|---|---|
| Cloud Run services (NestJS, Python, Spring, AI agent) | `google_cloud_run_v2_service` |
| Artifact Registry (Docker images) | `google_artifact_registry_repository` |
| Cloud SQL PostgreSQL 15 | `google_sql_database_instance` |
| Secret Manager (API keys, DB URLs) | `google_secret_manager_secret` |
| Workload Identity (keyless GitHub Actions auth) | `google_iam_workload_identity_pool` |
| GCS bucket (Terraform remote state) | `google_storage_bucket` |
| Firebase project | `google_firebase_project` |

### Example prompts

```
Provision complete GCP infra for our project — Cloud Run services, Artifact Registry,
Cloud SQL, Secret Manager, Workload Identity, GCS state bucket, staging + prod tfvars

Create a reusable Terraform module for Cloud Run used by all our services

Set up Workload Identity Federation so GitHub Actions deploys without JSON keys

Configure Cloud Run for our LangGraph agent with 4Gi memory and 300s timeout

Import our existing Cloud Run services into Terraform state management

Add tfsec and Checkov security scanning to our Terraform CI pipeline
```

### The only workflow you need

```bash
terraform init
terraform workspace new staging        # or: select staging
terraform plan -var-file=staging.tfvars   # always review before apply
terraform apply -var-file=staging.tfvars
```

> If `plan` shows `# will be destroyed` on Cloud SQL or Cloud Run — stop and ask the agent why before applying.

---
