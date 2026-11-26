---
name: terraform-skill
description: "Terraform/OpenTofu best practices, testing strategy, naming conventions, and CI/CD integration. Load BEFORE writing any Terraform module or environment config. Triggers: terraform test, terraform module, terraform naming, IaC best practices, terratest, terraform ci/cd, terraform version, for_each vs count, terraform structure, terraform conventions."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
metadata:
  triggers: ["terraform test", "terraform module", "terraform naming", "IaC best practices", "terratest", "terraform ci/cd", "terraform version", "for_each vs count", "terraform structure", "terraform conventions"]
  related-skills: [gcp-cloud-run, gcp-finops, docker, architecture-design, terraform-module-library]
  domain: backend
  role: specialist
  scope: infrastructure
  output-format: code
last-reviewed: "2026-03-15"
---

# Terraform Skill

> Source: terraform-best-practices.com + enterprise Terraform/OpenTofu experience. GCP-primary for this workspace.

## Iron Law

```
BEFORE writing any Terraform:
1. Load this skill for naming, testing, and code structure conventions
2. Dispatch terraform-specialist agent to provision GCP resources
3. Run tfsec/Checkov BEFORE terraform apply — no exceptions
4. State files NEVER go in git — GCS remote state always
5. GitHub Actions only — never generate cloudbuild.yaml
```

---

## This Skill vs `terraform-specialist` Agent

| Task | Use This Skill | Use `terraform-specialist` Agent |
|------|---------------|----------------------------------|
| Naming conventions (resources, variables, files) | YES | No |
| Testing strategy (native test vs Terratest) | YES | No |
| `count` vs `for_each` decision | YES | No |
| Resource block ordering standards | YES | No |
| Version constraint strategy | YES | No |
| CI/CD pipeline for Terraform (GitHub Actions) | YES | No |
| Provision Cloud Run, Cloud SQL, Artifact Registry | No | YES |
| Multi-environment (staging/prod) setup | No | YES |
| GCS remote state configuration | No | YES |
| Workload Identity Federation | No | YES |
| tfsec/Checkov security scanning | No | YES |

Load this skill for **how to write Terraform**. Dispatch `terraform-specialist` for **what to provision**.

---

## Pattern Selector

```
What do you need?
    |
    +-- Writing or reviewing a Terraform module?
    |   -> Apply § Naming Conventions
    |   -> Apply § Code Structure Standards (resource block ordering)
    |   -> Apply § Count vs For_Each decision
    |
    +-- Adding tests to a Terraform module?
    |   -> Use § Testing Strategy decision tree
    |   -> Terraform 1.6+: native test (preferred for this workspace)
    |   -> Terraform 1.0–1.5: Terratest (Go)
    |
    +-- Setting up CI/CD for Terraform?
    |   -> See § CI/CD Integration
    |   -> GitHub Actions ONLY (workspace rule — never cloudbuild.yaml)
    |
    +-- Choosing module or environment structure?
        -> See § Code Structure Philosophy
        -> See terraform-module-library/references/gcp-modules.md for the GCP layout, state bootstrap and secrets
        -> See terraform-module-library skill for GCP module patterns
```

---

## Code Structure Philosophy

```
terraform/
├── modules/          # Reusable modules — NO provider {}, NO backend {}
│   ├── cloud-run/    # One resource group per module
│   ├── cloud-sql/
│   ├── artifact-registry/
│   ├── secret-manager/
│   └── wif/
├── environments/     # Environment roots — call modules, configure backends
│   ├── staging/
│   │   ├── main.tf         # Module calls only — no raw resource definitions
│   │   ├── variables.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf      # GCS remote state
│   └── production/
│       └── ...
└── examples/         # Usage examples — also serve as integration test fixtures
    └── complete/
```

**Rules:**
- Modules do NOT contain `provider {}` blocks or `backend {}` — only environment roots do
- Environment roots contain module calls only, never raw resource definitions
- `examples/` doubles as documentation AND integration test fixture

---

## Naming Conventions

### Resource Names

```hcl
# Use descriptive names for resources used multiple times in a module
resource "google_cloud_run_v2_service" "api" { }
resource "google_cloud_run_v2_service" "worker" { }

# Use "this" ONLY for singleton resources (exactly one per module)
resource "google_artifact_registry_repository" "this" { }
resource "google_sql_database_instance" "this" { }
```

### Variable Names — Context-Prefixed

```hcl
# Avoid — ambiguous
variable "name" { }
variable "region" { }

# Prefer — context-prefixed
variable "service_name" { }
variable "cloud_run_region" { }
variable "sql_instance_name" { }
```

### File Names

| File | Purpose |
|------|---------|
| `main.tf` | Primary resource definitions |
| `variables.tf` | All input variable declarations |
| `outputs.tf` | All output declarations |
| `versions.tf` | `terraform {}` block + `required_providers` |
| `data.tf` | Data source lookups only |
| `locals.tf` | Local value computations (extract from main.tf when > 5 locals) |

---

## Testing Strategy

### Decision Tree

```
What Terraform version?
    |
    +-- 1.7+ → Use native test WITH mock providers (fastest, no real GCP calls)
    |
    +-- 1.6 → Use native test (terraform test command)
    |          Test files: tests/*.tftest.hcl
    |
    +-- 1.0–1.5 → Use Terratest (Go)
                   Test files: tests/*_test.go
```

### Testing Pyramid

| Layer | Tool | Runs On | Cost |
|-------|------|---------|------|
| Static analysis | `tflint`, `terraform validate`, `tfsec` | Every commit | Free |
| Unit (plan) | Native test (`command = plan`) | PR open/update | Free |
| Integration | Native test (`command = apply`, mock provider) | PR merge to develop | Free |
| E2E | Native test (`command = apply`, real provider) | Release branch only | ~$0.01–$1/run |

**Rule:** Run layers 1–2 on every PR. Layer 3 on merge to develop. Layer 4 on release branches only.

### Native Test — Preferred (Terraform 1.6+)

```hcl
# tests/cloud_run_module.tftest.hcl
mock_provider "google" {
  mock_resource "google_cloud_run_v2_service" {
    defaults = {
      uri = "https://test-api-abc123-uc.a.run.app"
    }
  }
  mock_resource "google_cloud_run_v2_service_iam_member" {}
}

variables {
  service_name          = "test-api"
  project_id            = "test-project"
  region                = "us-central1"
  image_url             = "us-central1-docker.pkg.dev/test-project/registry/api:latest"
  service_account_email = "sa@test-project.iam.gserviceaccount.com"
}

run "verify_service_name" {
  command = apply   # Safe — mock provider, no real GCP calls

  assert {
    condition     = google_cloud_run_v2_service.this.name == "test-api"
    error_message = "Service name should match input variable"
  }

  assert {
    condition     = startswith(output.service_url, "https://")
    error_message = "Service URL must be HTTPS"
  }
}

run "verify_name_validation" {
  command = plan

  variables {
    service_name = "this-name-is-way-too-long-for-cloud-run-service-names-xxxx"
  }

  expect_failures = [var.service_name]
}
```

---

## Code Structure Standards

### Resource Block Ordering

```hcl
resource "google_cloud_run_v2_service" "api" {
  # 1. count / for_each first
  for_each = toset(var.regions)

  # 2. Required arguments (alphabetical within group)
  location = each.key
  name     = "${var.service_name}-${each.key}"
  project  = var.project_id

  # 3. Optional arguments
  template { ... }

  # 4. Labels
  labels = var.labels

  # 5. depends_on (before lifecycle)
  depends_on = [google_project_service.run]

  # 6. lifecycle (last)
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}
```

### Variable Block Ordering

```hcl
variable "service_name" {
  description = "Name of the Cloud Run service"   # 1. description (always required)
  type        = string                             # 2. type
  default     = null                              # 3. default (if any)
  validation {                                    # 4. validation (if any)
    condition     = length(var.service_name) <= 49
    error_message = "Cloud Run service names must be <= 49 chars."
  }
  nullable = false                                # 5. nullable
}
```

---

## Count vs For_Each

### Decision Guide

```
Is the resource conditional (enabled/disabled flag)?
    YES -> count = var.enable_feature ? 1 : 0

Is the set driven by a list that could change order?
    YES -> for_each (stable addressing — prevents destroy/recreate cascade)
    NO (truly static, never reordered) -> count is acceptable

Do items have meaningful identity beyond index?
    YES -> for_each = tomap(...) or toset(...)
    NO  -> count

Example trap: multiple Cloud Run regions
    WRONG: count = 2  (count[0] -> count[1] on reorder = destroy us-central1!)
    RIGHT: for_each = toset(["us-central1", "us-east1"])
```

```hcl
# Conditional resource — count
resource "google_monitoring_alert_policy" "latency" {
  count = var.enable_monitoring ? 1 : 0
  ...
}

# Multi-region stable addressing — for_each
resource "google_cloud_run_v2_service" "regional" {
  for_each = toset(var.regions)
  name     = "${var.service_name}-${each.key}"
  location = each.key
}

# IAM members — for_each (never count — order instability)
resource "google_artifact_registry_repository_iam_member" "readers" {
  for_each   = toset(var.reader_service_accounts)
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${each.key}"
  ...
}
```

---

## Version Management

### Constraint Strategy

| Component | Constraint | Example |
|-----------|-----------|---------|
| Terraform binary | Pin minor | `~> 1.9.0` |
| `google` provider | Pin major, floor at tested minor (8.12.0 latest at review) | `~> 8.12` |
| `google-beta` provider | Same as `google` | `~> 8.12` |
| Internal modules | Pin exact | `= 1.2.3` |
| Registry modules | Pin minor | `~> 2.1` |

```hcl
# versions.tf
terraform {
  required_version = "~> 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.12"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 8.12"
    }
  }
}
```

### Feature Availability by Version

| Feature | Min Version | Use For |
|---------|------------|---------|
| `try()` function | 0.13 | Safely access nested optional attributes |
| `optional()` in object types | 1.3 | Optional object keys with defaults |
| `moved {}` block | 1.1 | Rename resources without destroy |
| `import {}` block | 1.5 | Declarative resource import |
| Native `terraform test` | 1.6 | Module unit testing |
| Mock providers in tests | 1.7 | Offline module testing (no real GCP calls) |
| Cross-variable validation | 1.9 | Validate interdependent variable combinations |

---

## CI/CD Integration (GitHub Actions Only)

> Full workflow: load [`reference/cicd-github-actions.md`](reference/cicd-github-actions.md)

**Stage order:** `validate → test → plan → apply` — never skip test stage.

Key jobs: `validate` (fmt + tflint + tfsec), `test` (native terraform test with mock providers), `plan` (PR only, requires WIF auth), `apply` (main branch only, environment gate).

---

## Reference Files

| Reference | Load When |
|-----------|-----------|
| [reference/index.md](reference/index.md) | Navigation |
| [reference/cicd-github-actions.md](reference/cicd-github-actions.md) | Setting up GitHub Actions CI/CD for Terraform |

---

## Cross-References

- **GCP Infrastructure provisioning**: Dispatch `terraform-specialist` agent
- **GCP module patterns (Cloud Run, Cloud SQL, VPC, WIF)**: Load `terraform-module-library` skill
- **GCP modules, state bootstrap, secret values**: `terraform-module-library/references/gcp-modules.md`
- **Terraform CI/CD (plan on PR, apply on merge)**: `reference/cicd-github-actions.md`
- **Security scanning post-apply**: Dispatch `security-reviewer` agent
- **CI/CD application pipeline**: `deployment-ci-cd` skill (`.claude/skills/deployment-ci-cd/SKILL.md`)
- **Env/infra SSOT** (`.env.example` vs compose vs Terraform vs dart-define, plus local/staging/prod *example* key drift): `python3 .claude/scripts/check-infra-env-ssot.py --root .` — do not inline `check_env_parity.py` in a new Makefile target when the aggregate exists. No Terraform in the repo → that arm is skipped, not FAIL.
