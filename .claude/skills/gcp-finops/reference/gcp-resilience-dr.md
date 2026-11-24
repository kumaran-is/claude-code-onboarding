# GCP Resilience & Disaster Recovery Reference

## RTO/RPO Targets by Tier

| Tier | RTO | RPO | GCP Pattern |
|------|-----|-----|-------------|
| Critical (payments, auth) | < 1 hour | < 15 min | Multi-region Cloud Run + Cloud SQL HA + Firestore multi-region |
| Standard (core APIs) | < 4 hours | < 1 hour | Single-region Cloud Run + Cloud SQL with PITR |
| Non-critical (batch, reporting) | < 24 hours | < 4 hours | Single-region, manual recovery acceptable |

**Assign tier before designing DR.** Tier determines which patterns below to apply.

---

## Cloud SQL High Availability

HA mode (`REGIONAL`) places a standby instance in a different zone. Failover is automatic (< 60s).
PITR provides a 7-day recovery window for point-in-time restores.

```hcl
resource "google_sql_database_instance" "primary" {
  database_version = "POSTGRES_16"
  region           = "us-central1"
  deletion_protection = true

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL"  # HA — standby in different zone; ZONAL = no HA

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true  # PITR — 7-day window
      transaction_log_retention_days = 7
      start_time                     = "03:00"  # UTC — low traffic window

      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    insights_config {
      query_insights_enabled = true
    }
  }
}
```

**Note:** `REGIONAL` availability type doubles instance cost (primary + standby).
Only use for Critical and Standard tiers. Non-critical → `ZONAL`.

---

## PITR Recovery (Cloud SQL)

Use when data was corrupted or accidentally deleted. Creates a clone at a past point in time.

```bash
# Step 1 — Identify the target recovery time (before the incident)
# Format: RFC 3339 timestamp in UTC
RECOVERY_TIME="2026-03-14T10:30:00Z"

# Step 2 — Clone the instance to a recovery instance
gcloud sql instances clone SOURCE_INSTANCE RECOVERY_INSTANCE \
  --point-in-time="$RECOVERY_TIME"

# Step 3 — Validate data in the recovery instance
gcloud sql connect RECOVERY_INSTANCE --user=postgres

# Step 4 — If validated, update app connection string to point to recovery instance
# (Update Secret Manager secret or env var — do NOT hardcode connection strings)

# Step 5 — After validation window, delete the original or promote recovery instance
gcloud sql instances delete SOURCE_INSTANCE --quiet
gcloud sql instances patch RECOVERY_INSTANCE --database-flags=""  # clear any test flags
```

**Warning:** PITR clone is NOT the same as a promotion. The clone is a new instance — you must
redirect traffic manually. Test PITR quarterly; do not wait for an incident.

---

## Multi-Region Cloud Run (Active-Passive)

Deploy to primary and DR region. Primary handles 100% of traffic; DR region is warm (min-instances=1).
On failover, update Global Load Balancer to send traffic to DR region.

```yaml
# .github/workflows/deploy-multi-region.yml
name: Deploy Multi-Region

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    strategy:
      matrix:
        include:
          - region: us-central1
            min_instances: 1
          - region: us-east1
            min_instances: 1   # warm standby — set to 0 for cost savings if cold start is acceptable

    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Authenticate to GCP
        uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093 # v3.0.0
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.WIF_SERVICE_ACCOUNT }}

      - name: Deploy to ${{ matrix.region }}
        run: |
          gcloud run deploy ${{ vars.SERVICE_NAME }} \
            --region ${{ matrix.region }} \
            --image ${{ vars.IMAGE }} \
            --min-instances ${{ matrix.min_instances }} \
            --no-traffic  # traffic controlled by Global LB, not Cloud Run traffic splits
```

---

## Global Load Balancer for Failover

Routes traffic to primary region; automatically fails over to secondary if health checks fail.

```hcl
resource "google_compute_backend_service" "api_backend" {
  name                  = "api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"

  backend {
    group           = google_compute_region_network_endpoint_group.primary.id  # us-central1
    capacity_scaler = 1.0   # receives 100% of traffic when healthy
  }

  backend {
    group           = google_compute_region_network_endpoint_group.secondary.id  # us-east1
    capacity_scaler = 0.0   # standby — GCP activates automatically on primary health failure
  }

  health_checks = [google_compute_health_check.api_health.id]

  outlier_detection {
    consecutive_errors = 5
    interval {
      seconds = 10
    }
    base_ejection_time {
      seconds = 30
    }
  }
}

resource "google_compute_health_check" "api_health" {
  name               = "api-health-check"
  check_interval_sec = 10
  timeout_sec        = 5
  healthy_threshold  = 2
  unhealthy_threshold = 3

  https_health_check {
    port         = 443
    request_path = "/health"
  }
}

resource "google_compute_region_network_endpoint_group" "primary" {
  name                  = "api-neg-primary"
  network_endpoint_type = "SERVERLESS"
  region                = "us-central1"

  cloud_run {
    service = var.service_name
  }
}

resource "google_compute_region_network_endpoint_group" "secondary" {
  name                  = "api-neg-secondary"
  network_endpoint_type = "SERVERLESS"
  region                = "us-east1"

  cloud_run {
    service = var.service_name
  }
}
```

---

## Firestore Multi-Region

Multi-region Firestore replicates data across two US regions with automatic failover.
**Choose location at creation — this cannot be changed after the database is created.**

```hcl
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = "nam5"    # US multi-region (Iowa + South Carolina)
  type        = "FIRESTORE_NATIVE"

  # nam5 = multi-region (HA, ~2x cost of single region)
  # us-central1 = single-region (cheaper, no automatic geo-redundancy)
  # eur3 = Europe multi-region (Belgium + Netherlands)
}
```

**Cost:** Multi-region Firestore costs ~2x single-region. Use for Critical tier services only.

---

## DR Runbook Template

Customize per service. Store in `docs/runbooks/<service>-dr.md`.

```markdown
## Incident: [SERVICE] outage in [REGION]

### Declare Incident
- Incident commander: @[name]
- Notify: #[slack-channel], [pagerduty-policy]

### Assess Scope
1. Check Cloud Run: `gcloud run services list --region [PRIMARY_REGION]`
2. Check Cloud SQL: `gcloud sql instances describe [INSTANCE] --format='value(state)'`
3. Check Firestore: GCP Console → Firestore → Monitor tab
4. Check Global LB health: GCP Console → Load Balancing → Backend Services

### Cloud SQL Recovery
- If Cloud SQL is down and REGIONAL HA did not auto-failover:
  1. `gcloud sql instances failover [INSTANCE]` (triggers manual HA failover)
  2. If data loss suspected: initiate PITR clone (see gcp-resilience-dr.md)
  3. Update Secret Manager connection string if instance name changed

### Cloud Run Traffic Failover
- If primary region is unhealthy and Global LB has not auto-failed over:
  1. `gcloud compute backend-services update api-backend --global` — verify backend health
  2. If manual failover needed: update `capacity_scaler` in Terraform and apply

### Communicate
- Update status page within 15 minutes of incident start
- Notify stakeholders at RTO/2 mark if not resolved

### Post-Incident
- Root cause analysis within 48 hours
- Update this runbook with any gaps found
- Schedule PITR / failover drill if not tested in last 90 days
```

---

## DR Testing Schedule

| Test | Frequency | Procedure |
|------|-----------|-----------|
| PITR clone + data validation | Quarterly | Clone to test instance, verify row counts and recent data |
| Cloud Run DR region smoke test | Monthly | Send 1% traffic to DR region, verify health check passes |
| Global LB failover drill | Semi-annually | Manually disable primary backend, confirm traffic shifts to DR |
| Runbook walkthrough | Annually | Tabletop exercise with on-call team |
