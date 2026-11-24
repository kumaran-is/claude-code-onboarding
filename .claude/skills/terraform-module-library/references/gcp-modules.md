# GCP Terraform Module Reference

> GCP-primary module patterns for this workspace. All modules target `google` provider `~> 8.12` (8.12.0 latest at review; no 7.0/8.0 breaking change touches the arguments used here) and Terraform `~> 1.9.0`. Use mock providers in tests — no real GCP calls needed.

---

## Cloud Run v2 Service

### variables.tf

```hcl
variable "service_name" {
  description = "Name of the Cloud Run v2 service (max 49 chars)"
  type        = string
  validation {
    condition     = length(var.service_name) <= 49
    error_message = "Cloud Run service names must be <= 49 characters."
  }
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Cloud Run service"
  type        = string
  default     = "us-central1"
}

variable "image_url" {
  description = "Fully qualified container image URL (Artifact Registry path)"
  type        = string
}

variable "min_instances" {
  description = "Minimum number of instances (0 = scale to zero)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

variable "secrets" {
  description = "Map of env var name to Secret Manager secret ID"
  type        = map(string)
  default     = {}
}

variable "service_account_email" {
  description = "Service account email for the Cloud Run service identity"
  type        = string
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated public access (false = authenticated only)"
  type        = bool
  default     = false
}

variable "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name (project:region:instance) to mount at /cloudsql; null = no mount"
  type        = string
  default     = null
}

variable "labels" {
  description = "Labels applied to the Cloud Run service"
  type        = map(string)
  default     = {}
}
```

### main.tf

```hcl
resource "google_cloud_run_v2_service" "this" {
  name     = var.service_name
  location = var.region
  project  = var.project_id
  labels   = var.labels

  template {
    service_account = var.service_account_email

    # Cloud SQL unix socket: Cloud Run runs the connector; the app dials /cloudsql/<connection_name>
    dynamic "volumes" {
      for_each = var.cloud_sql_connection_name == null ? [] : [var.cloud_sql_connection_name]
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [volumes.value]
        }
      }
    }

    containers {
      image = var.image_url

      dynamic "volume_mounts" {
        for_each = var.cloud_sql_connection_name == null ? [] : [var.cloud_sql_connection_name]
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      dynamic "env" {
        for_each = var.cloud_sql_connection_name == null ? [] : [var.cloud_sql_connection_name]
        content {
          name  = "INSTANCE_UNIX_SOCKET" # the app builds its DSN from this + DB_USER + DB_PASSWORD (secret)
          value = "/cloudsql/${env.value}"
        }
      }

      dynamic "env" {
        for_each = var.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      liveness_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 10
        period_seconds        = 30
        failure_threshold     = 3
      }

      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 10
      }
    }

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }
  }

  lifecycle {
    # CI/CD manages the image URL — Terraform manages config and scaling
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
```

### outputs.tf

```hcl
output "service_url" {
  description = "The HTTPS URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.this.uri
}

output "service_name" {
  description = "The name of the Cloud Run service"
  value       = google_cloud_run_v2_service.this.name
}

output "service_id" {
  description = "The full resource ID of the Cloud Run service"
  value       = google_cloud_run_v2_service.this.id
}
```

### tests/main.tftest.hcl

```hcl
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
  service_account_email = "api-sa@test-project.iam.gserviceaccount.com"
}

run "verify_service_defaults" {
  command = apply

  assert {
    condition     = google_cloud_run_v2_service.this.name == "test-api"
    error_message = "Service name should match input variable"
  }

  assert {
    condition     = google_cloud_run_v2_service.this.location == "us-central1"
    error_message = "Region should match input variable"
  }

  assert {
    condition     = startswith(output.service_url, "https://")
    error_message = "Service URL must be HTTPS"
  }
}

run "verify_name_too_long_fails_validation" {
  command = plan

  variables {
    service_name = "this-name-is-way-too-long-for-cloud-run-service-names-fails"
  }

  expect_failures = [var.service_name]
}
```

### Environment Usage

```hcl
# terraform/environments/staging/main.tf
module "api_service" {
  source = "../../modules/cloud-run"

  service_name              = "my-api-staging"
  project_id                = var.project_id
  region                    = "us-central1"
  image_url                 = "${module.artifact_registry.repository_url}/api:${var.initial_image_tag}" # CI owns later tags
  service_account_email     = google_service_account.api.email
  min_instances             = 0 # Scale to zero in staging
  max_instances             = 5
  cloud_sql_connection_name = module.cloud_sql.connection_name
  labels                    = { environment = "staging", team = "platform" }
  secrets = {
    DB_PASSWORD = module.cloud_sql.db_password_secret_id   # never a password literal in a URL
    JWT_SECRET  = google_secret_manager_secret.jwt.secret_id
  }
}
```

---

## Cloud SQL PostgreSQL

### variables.tf

```hcl
variable "instance_name" {
  description = "Name of the Cloud SQL instance (unique within project + region)"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Cloud SQL instance"
  type        = string
  default     = "us-central1"
}

variable "database_version" {
  description = "PostgreSQL version to use"
  type        = string
  default     = "POSTGRES_18"
  validation {
    condition     = startswith(var.database_version, "POSTGRES_")
    error_message = "database_version must be a POSTGRES_* value (e.g. POSTGRES_18)."
  }
}

variable "edition" {
  description = "ENTERPRISE or ENTERPRISE_PLUS. POSTGRES_16+ defaults to ENTERPRISE_PLUS, which rejects shared-core and db-custom-* tiers"
  type        = string
  default     = "ENTERPRISE"
  validation {
    condition     = contains(["ENTERPRISE", "ENTERPRISE_PLUS"], var.edition)
    error_message = "edition must be ENTERPRISE or ENTERPRISE_PLUS."
  }
}

variable "machine_type" {
  description = "Cloud SQL tier: db-f1-micro (dev) or db-custom-<vCPU>-<MB> (prod) on ENTERPRISE; db-perf-optimized-N-* on ENTERPRISE_PLUS"
  type        = string
  default     = "db-f1-micro"
}

variable "ha_enabled" {
  description = "Enable high availability with REGIONAL availability type"
  type        = bool
  default     = false
}

variable "vpc_id" {
  description = "VPC network self-link for private IP access (no public IP)"
  type        = string
}

variable "database_name" {
  description = "Name of the application database to create"
  type        = string
}

variable "db_user" {
  description = "Database user name for the application"
  type        = string
}

variable "deletion_protection" {
  description = "Prevent accidental deletion of the Cloud SQL instance (set true in production)"
  type        = bool
  default     = true
}
```

### main.tf

```hcl
resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_sql_database_instance" "this" {
  name             = var.instance_name
  database_version = var.database_version
  region           = var.region
  project          = var.project_id

  settings {
    tier              = var.machine_type
    edition           = var.edition
    availability_type = var.ha_enabled ? "REGIONAL" : "ZONAL"

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = var.ha_enabled
      transaction_log_retention_days = var.ha_enabled ? 7 : 1
    }

    ip_configuration {
      ipv4_enabled    = false   # No public IP — use Cloud SQL Auth Proxy or private IP
      private_network = var.vpc_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }
  }

  deletion_protection = var.deletion_protection
}

resource "google_sql_database" "app" {
  name     = var.database_name
  instance = google_sql_database_instance.this.name
  project  = var.project_id
}

resource "google_sql_user" "app" {
  name     = var.db_user
  instance = google_sql_database_instance.this.name
  password = random_password.db_password.result
  project  = var.project_id
}

# Store generated password in Secret Manager — never commit to git or tfvars
resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.instance_name}-db-password"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}
```

### outputs.tf

```hcl
output "connection_name" {
  description = "Cloud SQL connection name for Auth Proxy or Cloud Run sidecar config"
  value       = google_sql_database_instance.this.connection_name
}

output "private_ip" {
  description = "Private IP address of the Cloud SQL instance"
  value       = google_sql_database_instance.this.private_ip_address
}

output "db_password_secret_id" {
  description = "Secret Manager secret ID storing the generated database password"
  value       = google_secret_manager_secret.db_password.secret_id
}

output "db_user" {
  description = "Database user name"
  value       = var.db_user
}
```

---

## Artifact Registry

### main.tf

```hcl
resource "google_artifact_registry_repository" "this" {
  repository_id = var.repository_id
  location      = var.region
  project       = var.project_id
  format        = "DOCKER"
  description   = var.description

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-tagged-releases"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["v", "release-"]
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"   # 7 days
    }
  }
}

# Grant Cloud Run service accounts pull access
resource "google_artifact_registry_repository_iam_member" "cloud_run_reader" {
  for_each   = toset(var.cloud_run_service_accounts)
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.this.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${each.key}"
}

# Grant CI service account push access (GitHub Actions via WIF)
resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  count      = var.ci_service_account != null ? 1 : 0
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.this.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${var.ci_service_account}"
}
```

### outputs.tf

```hcl
output "repository_url" {
  description = "Docker registry URL — use as image URL prefix in Cloud Run and CI"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "repository_id" {
  description = "Artifact Registry repository ID"
  value       = google_artifact_registry_repository.this.repository_id
}
```

---

## Workload Identity Federation

Enables GitHub Actions to authenticate to GCP without service account JSON keys.

### main.tf

```hcl
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.pool_id
  project                   = var.project_id
  display_name              = "GitHub Actions Pool"
  description               = "Workload Identity Pool for GitHub Actions — no static keys"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  project                            = var.project_id

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  # Scope to your GitHub org — prevents cross-org token usage
  attribute_condition = "assertion.repository_owner == '${var.github_org}'"
}

# Bind each service account to specific GitHub repos
resource "google_service_account_iam_member" "wif_binding" {
  for_each           = var.service_accounts  # map: sa_email => "github_org/repo"
  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.key}"
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${each.value}"
}
```

### outputs.tf

```hcl
output "provider_name" {
  description = "Full WIF provider resource name — use as workload_identity_provider in GitHub Actions"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "pool_name" {
  description = "Full WIF pool resource name"
  value       = google_iam_workload_identity_pool.github.name
}
```

### variables.tf

```hcl
variable "pool_id" {
  description = "Workload Identity Pool ID (e.g. 'github-actions-pool')"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "github_org" {
  description = "GitHub organization name — restricts which org can use this pool"
  type        = string
}

variable "service_accounts" {
  description = "Map of service account email to GitHub repo path (org/repo) for WIF binding"
  type        = map(string)
  # Example: { "ci-sa@project.iam.gserviceaccount.com" = "my-org/my-repo" }
}
```

### GitHub Actions Usage

```yaml
# In .github/workflows/*.yml
- name: Authenticate to GCP via Workload Identity
  uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ vars.WIF_PROVIDER }}   # output.provider_name
    service_account: ${{ vars.WIF_SERVICE_ACCOUNT }}
```

---

## VPC + Private Services Access

Required for Cloud SQL private IP access from Cloud Run.

### main.tf

```hcl
resource "google_compute_network" "this" {
  name                    = var.network_name
  project                 = var.project_id
  auto_create_subnetworks = false
  mtu                     = 1460
}

resource "google_compute_subnetwork" "subnets" {
  for_each = var.subnets  # map: name => { region, cidr }

  name          = each.key
  ip_cidr_range = each.value.cidr
  region        = each.value.region
  network       = google_compute_network.this.id
  project       = var.project_id

  private_ip_google_access = true   # Required for Cloud SQL private IP
}

# Private Services Access — required for Cloud SQL private IP
resource "google_compute_global_address" "private_services" {
  name          = "${var.network_name}-private-services"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}
```

### outputs.tf

```hcl
output "network_id" {
  description = "VPC network self-link — pass as vpc_id to cloud-sql module"
  value       = google_compute_network.this.id
}

output "network_name" {
  description = "VPC network name"
  value       = google_compute_network.this.name
}

output "subnet_ids" {
  description = "Map of subnet name to subnet self-link"
  value       = { for k, v in google_compute_subnetwork.subnets : k => v.id }
}
```

---

## Bootstrap Outside Terraform

### Remote-state bucket (once per environment, before `terraform init`)

```bash
gcloud storage buckets create gs://PROJECT_ID-tfstate-staging \
  --project=PROJECT_ID --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://PROJECT_ID-tfstate-staging --versioning   # state rollback
```

```hcl
# environments/staging/backend.tf
terraform {
  backend "gcs" {
    bucket = "PROJECT_ID-tfstate-staging"
    prefix = "staging"
  }
}
```

State holds resource IDs and any secret a resource returns: never commit it, and grant the bucket
only to the CI service account and platform admins.

### Secret values

Terraform creates the secret *container* and its IAM; values that a human or another system owns
(API keys, third-party tokens) are added out of band so they never reach `.tfvars` or state:

```bash
# reads from stdin: nothing in shell history or argv
gcloud secrets versions add staging-jwt-secret --project=PROJECT_ID --data-file=-
```

Reference a pinned version number from Cloud Run when rollouts must be reproducible; `latest` picks up a
new value on the next revision.

---

## Best Practices Summary

| Rule | Why |
|------|-----|
| Pin `google` provider `~> 8.12` | Allows 8.x fixes, blocks the next major; read its upgrade guide before raising |
| `deletion_protection = true` in prod | Prevents accidental destruction of stateful resources |
| `ipv4_enabled = false` on Cloud SQL | No public IP; access via private IP or Auth Proxy only |
| `ssl_mode = "ENCRYPTED_ONLY"` on Cloud SQL | Encrypts all database connections |
| `for_each` for all IAM members | Stable addressing — avoids destroy/recreate on reorder |
| `lifecycle.ignore_changes` on Cloud Run image | CI/CD manages image updates, not Terraform |
| Cleanup policies on Artifact Registry | Prevents unbounded storage cost from untagged images |
| WIF `attribute_condition` scoped to org | Prevents cross-org OIDC token impersonation |
| `random_password` + Secret Manager for DB | Never hardcode or commit database passwords |
| `private_ip_google_access = true` on subnets | Required for Cloud Run to reach Cloud SQL private IP |
| Set `edition` explicitly on Cloud SQL | POSTGRES_16+ defaults to ENTERPRISE_PLUS, which fails on `db-f1-micro` / `db-custom-*` |
| Mock providers in all module tests | No GCP auth needed in CI — safe and free to run |
