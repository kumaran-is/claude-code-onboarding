---
name: terraform-module-library
description: "Reusable GCP Terraform module patterns for Cloud Run v2, Cloud SQL PostgreSQL, Artifact Registry, VPC, Secret Manager, and Workload Identity Federation. Load when creating or consuming reusable Terraform modules for GCP. Triggers: terraform module, reusable terraform, gcp module, terraform library, cloud run module, cloud sql module, artifact registry module, wif module, terraform module structure."
allowed-tools: Read, Write, Edit, Glob, Grep
metadata:
  triggers: ["terraform module", "reusable terraform", "gcp module", "terraform library", "cloud run module", "cloud sql module", "artifact registry module", "wif module", "terraform module structure"]
  related-skills: [terraform-skill, gcp-cloud-run, gcp-finops, docker]
  domain: backend
  role: specialist
  scope: infrastructure
  output-format: code
last-reviewed: "2026-03-15"
---

# Terraform Module Library (GCP)

> GCP-primary module patterns for this workspace. Modules cover: Cloud Run v2, Cloud SQL PostgreSQL, Artifact Registry, VPC + Private Services, Secret Manager, Workload Identity Federation.

## Iron Law

```
BEFORE creating a Terraform module:
1. Load terraform-skill for naming conventions and code structure standards
2. Every module MUST have: main.tf, variables.tf, outputs.tf, versions.tf, README.md
3. Every module MUST have tests in tests/ using native terraform test (1.6+) with mock providers
4. Sensitive outputs MUST be marked sensitive = true
5. Dispatch terraform-specialist agent to apply/provision — this skill is for authoring only
```

---

## Standard Module Structure

```
modules/
└── <module-name>/
    ├── main.tf              # Resources only — no provider {}, no backend {}
    ├── variables.tf         # All inputs with description, type, validation
    ├── outputs.tf           # All outputs with description and sensitive flag
    ├── versions.tf          # required_version + required_providers
    ├── README.md            # Usage example + variable/output tables
    └── tests/
        └── main.tftest.hcl  # Native terraform test with mock_provider (1.7+)
```

---

## Pattern Selector

```
Which GCP resource are you modularizing?
    |
    +-- Cloud Run v2 service       -> See references/gcp-modules.md § Cloud Run
    +-- Cloud SQL (PostgreSQL)     -> See references/gcp-modules.md § Cloud SQL
    +-- Artifact Registry          -> See references/gcp-modules.md § Artifact Registry
    +-- VPC + Subnets              -> See references/gcp-modules.md § VPC
    +-- Secret Manager             -> See references/gcp-modules.md § Secret Manager
    +-- Workload Identity Fed.     -> See references/gcp-modules.md § Workload Identity Federation
```

---

## Reference Files

| File | Load When |
|------|-----------|
| `references/gcp-modules.md` | Writing or reviewing any GCP Terraform module — has full HCL for all 6 modules |

---

## Module Authoring Checklist

Before submitting any module:

- [ ] `versions.tf` present with `google` provider pinned to `~> 8.12`
- [ ] All variables have `description` and `type` declared
- [ ] All sensitive outputs marked `sensitive = true`
- [ ] `deletion_protection` variable present for stateful resources (Cloud SQL, Artifact Registry)
- [ ] Tests in `tests/main.tftest.hcl` with at least one `command = apply` using `mock_provider "google"`
- [ ] `README.md` has usage example, variable table, and output table
- [ ] `for_each` used (not `count`) for IAM members and multi-instance resources
- [ ] No hardcoded project IDs, regions, or resource names
- [ ] `lifecycle.ignore_changes` on container image for Cloud Run (CI/CD manages image, not Terraform)
- [ ] `ipv4_enabled = false` for Cloud SQL (no public IP)

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `lifecycle.ignore_changes = [image]` on Cloud Run | CI/CD updates the image; Terraform manages config/scaling only. Prevents Terraform drift on every deploy. |
| `ipv4_enabled = false` on Cloud SQL | No public IP; forces Cloud SQL Auth Proxy or private VPC access. Security baseline. |
| `random_password` + Secret Manager for DB | Never hardcode or commit passwords. Secret Manager is the source of truth. |
| `for_each` on IAM members | Stable resource addressing; `count` causes destroy/recreate when list reorders. |
| Cleanup policies on Artifact Registry | Prevents unbounded storage cost from accumulated untagged images. |
| WIF `attribute_condition` scoped to org | Prevents cross-org token impersonation. |

---

## Cross-References

- **Naming and testing conventions**: Load `terraform-skill` skill (load it first)
- **GCP provisioning**: Dispatch `terraform-specialist` agent
- **GCP module patterns, state bootstrap, secret values**: `references/gcp-modules.md`
- **Module testing and Terraform CI/CD**: `terraform-skill` skill (`terraform-skill/reference/cicd-github-actions.md`)
- **Security review post-apply**: Dispatch `security-reviewer` agent
