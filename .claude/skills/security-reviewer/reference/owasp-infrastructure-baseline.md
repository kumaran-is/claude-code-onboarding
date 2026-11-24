# OWASP Infrastructure Security Baseline

> **Scope:** Infrastructure-layer controls — network configuration, encryption at rest/transit,
> access logging, IAM, and system-level hardening. For application-layer checks see
> `security-review-checklist.md`.
>
> **OWASP mapping:** 2021 edition (A01–A10)

## How to Use

Load this reference when reviewing:
- Infrastructure-as-code (Terraform, CloudFormation, Pulumi)
- Cloud configuration (GCP, AWS, Azure)
- Network architecture and firewall rules
- Secret management and rotation setup
- Audit logging infrastructure
- CI/CD pipeline security configuration

Complement with `security-review-checklist.md` for application-layer controls. Both files
apply on full-stack security reviews — neither replaces the other.

---

## Rules

### SECURITY-01 — Encryption at Rest and Transit (CRITICAL)

**OWASP:** A02:2021 – Cryptographic Failures

**Rule:** Every data persistence store (databases, object storage, file systems, caches) MUST have:
- Encryption at rest enabled using a managed key service or customer-managed keys
- Encryption in transit enforced (TLS 1.2+ for all data movement in and out of the store)

**Verification:**
- No storage resource is defined in IaC without an encryption configuration block
- No database connection string uses an unencrypted protocol
- Object storage enforces encryption at rest and rejects non-TLS requests via bucket policy
- Database instances have storage encryption enabled and enforce TLS connections

**When to apply:** Any Terraform/CloudFormation resource defining RDS, Cloud SQL, S3, GCS, Redis, Elasticsearch, or equivalent.

---

### SECURITY-02 — Access Logging on Network Intermediaries (HIGH)

**OWASP:** A09:2021 – Security Logging and Monitoring Failures

**Rule:** Every network-facing intermediary that handles external traffic MUST have access logging enabled:
- Load balancers → access logs to a persistent store
- API gateways → execution logging and access logging to a centralized log service
- CDN distributions → standard logging or real-time logs

**Verification:**
- No load balancer resource is defined without access logging enabled
- No API gateway stage is defined without access logging configured
- No CDN distribution is defined without logging configuration

**When to apply:** Any IaC defining ALB, NLB, API Gateway, Cloud Endpoints, CloudFront, Cloud CDN, or equivalent.

---

### SECURITY-03 — Application-Level Structured Logging (HIGH)

**OWASP:** A09:2021 – Security Logging and Monitoring Failures

**Rule:** Every deployed application component MUST include structured logging infrastructure:
- A logging framework MUST be configured (not ad-hoc print/console.log statements)
- Log output MUST be directed to a centralized log service (CloudWatch, GCP Cloud Logging, etc.)
- Logs MUST include: timestamp, correlation/request ID, log level, and message
- Sensitive data (passwords, tokens, PII) MUST NOT appear in log output

**Verification:**
- Every service/function entry point includes a configured logger
- Log configuration routes output to a centralized log service — not local disk only
- No secrets, tokens, or PII are logged

**When to apply:** All service deployments, Lambda/Cloud Functions, container workloads. Complements application-layer logging rules in `security-review-checklist.md §9`.

---

### SECURITY-04 — HTTP Security Headers for Web Applications (HIGH)

**OWASP:** A05:2021 – Security Misconfiguration

**Rule:** The following HTTP response headers MUST be set on all HTML-serving endpoints:

| Header | Required Value |
|--------|----------------|
| `Content-Security-Policy` | Restrictive policy — at minimum `default-src 'self'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` (or `SAMEORIGIN` if framing is required) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

Note: `X-XSS-Protection` is deprecated — use `Content-Security-Policy` instead.

**Verification:**
- Middleware or CDN response policy sets all required headers
- CSP policy does not use `unsafe-inline` or `unsafe-eval` without documented justification
- HSTS max-age is at least 31536000 (1 year)

**When to apply:** Any service serving HTML — web frontends, API gateways with web UIs, admin panels.

---

### SECURITY-05 — Input Validation on All API Parameters (CRITICAL)

**OWASP:** A03:2021 – Injection

**Rule:** Every API endpoint (REST, GraphQL, gRPC, WebSocket) MUST validate all input parameters before processing:
- **Type checking:** Reject unexpected types
- **Length/size bounds:** Enforce maximum lengths on strings, maximum sizes on arrays and payloads
- **Format validation:** Use allowlists (regex or schema) for structured inputs (emails, dates, IDs)
- **Sanitization:** Escape or reject HTML/script content in user-supplied strings
- **Injection prevention:** Use parameterized queries for all database operations — never string concatenation

**Verification:**
- Every API handler uses a validation library or schema (Pydantic, Joi, class-validator, etc.)
- No raw user input is concatenated into SQL, NoSQL, or OS commands
- String inputs have explicit max-length constraints
- Request body size limits are configured at the framework or gateway level

**When to apply:** All API services. Aligns with `security-review-checklist.md §2` (Injection) and §4 (Input Validation) — this rule covers the infrastructure-level enforcement (gateway limits, framework config).

---

### SECURITY-06 — Least-Privilege IAM Access Policies (CRITICAL)

**OWASP:** A01:2021 – Broken Access Control

**Rule:** Every IAM policy, role, or permission boundary MUST follow least privilege:
- Use specific resource identifiers — NEVER use wildcard resources unless the API does not support resource-level permissions (document the exception)
- Use specific actions — NEVER use wildcard actions
- Scope conditions where possible (source IP, VPC, MFA)
- Separate read and write permissions into distinct policy statements

**Verification:**
- No policy contains wildcard actions (`*`) or wildcard resources (`*`) without a documented exception
- No service role has broader permissions than what the service actually calls
- Inline policies are avoided in favor of managed policies
- Every role has a trust policy scoped to the specific service or account

**When to apply:** All IaC defining IAM roles, service accounts, GCP IAM bindings, or AWS managed policies.

---

### SECURITY-07 — Restrictive Network Configuration (CRITICAL)

**OWASP:** A05:2021 – Security Misconfiguration

**Rule:** All network configurations (security groups, network ACLs, firewall rules) MUST follow deny-by-default:
- Only open specific ports required by the application
- No inbound rule with source `0.0.0.0/0` except for public-facing load balancers on ports 80/443
- No outbound rule with `0.0.0.0/0` on all ports unless explicitly justified
- Private subnets MUST NOT have direct internet gateway routes
- Use private endpoints for cloud service access where available

**Verification:**
- No firewall rule allows inbound `0.0.0.0/0` on any port other than 80/443 on a public load balancer
- Database and application firewall rules restrict source to specific CIDR blocks or security group references
- Private subnets route through a NAT gateway (not an internet gateway)
- Private endpoints are used for high-traffic cloud service calls

**When to apply:** All VPC/VNet definitions, security group resources, Cloud Armor rules, GCP firewall rules.

---

### SECURITY-08 — Application-Level Access Control (CRITICAL)

**OWASP:** A01:2021 – Broken Access Control

**Rule:** Every application endpoint that accesses or mutates a resource MUST enforce authorization checks at the application layer:
- **Deny by default:** All routes/endpoints MUST require authentication unless explicitly marked public
- **Object-level authorization:** Every request referencing a resource by ID MUST verify the requesting user owns or has permission to access that resource (prevent IDOR)
- **Function-level authorization:** Administrative operations MUST check caller's role server-side — never rely on client-side hiding
- **CORS policy:** Cross-origin resource sharing MUST restrict to explicitly allowed origins — never `Access-Control-Allow-Origin: *` on authenticated endpoints
- **Token validation:** JWTs or session tokens MUST be validated server-side on every request (signature, expiration, audience, issuer)

**Verification:**
- Every controller/handler has an authorization middleware or guard applied
- No endpoint returns data for a resource ID without verifying caller ownership or permission
- Admin/privileged routes have explicit role checks enforced server-side
- CORS configuration does not use wildcard origins on authenticated endpoints
- Token validation occurs server-side on every request

**When to apply:** All API services. Complements `security-review-checklist.md §3` (Authentication & Authorization) — this rule adds IDOR and deny-by-default infrastructure framing.

---

### SECURITY-09 — Security Hardening and Misconfiguration Prevention (HIGH)

**OWASP:** A05:2021 – Security Misconfiguration

**Rule:** All deployed components MUST follow a hardening baseline:
- **No default credentials:** Default usernames/passwords MUST be changed or disabled before deployment
- **Minimal installation:** Remove or disable unused features, sample applications, and documentation endpoints
- **Error handling:** Production error responses MUST NOT expose stack traces, internal paths, framework versions, or database details
- **Directory listing:** Web servers MUST disable directory listing
- **Cloud storage:** Cloud object storage MUST block public access unless explicitly required and documented
- **Patch management:** Runtime environments, frameworks, and OS images MUST use current, supported versions

**Verification:**
- No default credentials exist in configuration files, environment variables, or IaC templates
- Error responses in production return generic messages (no stack traces or internal details)
- Cloud object storage has public access blocked unless a documented exception exists
- No sample/demo applications or default pages are deployed
- Framework and runtime versions are current and supported

**When to apply:** All IaC defining compute instances, container images, cloud storage buckets, and managed services.

---

### SECURITY-10 — Software Supply Chain Security (HIGH)

**OWASP:** A06:2021 – Vulnerable and Outdated Components

**Rule:** Every project MUST manage its software supply chain:
- **Dependency pinning:** All dependencies MUST use exact versions or lock files
- **Vulnerability scanning:** A dependency vulnerability scanner MUST be configured in CI/CD
- **No unused dependencies:** Remove packages that are not actively used
- **Trusted sources only:** Dependencies pulled from official registries or verified private registries — no unvetted third-party sources
- **SBOM:** Projects MUST generate a Software Bill of Materials for production deployments
- **CI/CD integrity:** Build pipelines MUST use pinned tool versions and verified base images — no `latest` tags in production Dockerfiles or CI configurations

**Verification:**
- A lock file exists and is committed to version control
- A dependency vulnerability scanning step is included in CI/CD
- No unused or abandoned dependencies are included
- Dockerfiles and CI configs do not use `latest` or unpinned image tags for production
- Dependencies are sourced from official or verified registries

**When to apply:** All projects with `package.json`, `requirements.txt`, `pubspec.yaml`, `pom.xml`, or equivalent. Complements `security-review-checklist.md §6` (Dependencies).

---

### SECURITY-11 — Secure Design Principles (HIGH)

**OWASP:** A04:2021 – Insecure Design

**Rule:** Application design MUST incorporate security from the start:
- **Separation of concerns:** Security-critical logic (authentication, authorization, payment processing) MUST be isolated in dedicated modules — not scattered across the codebase
- **Defense in depth:** No single control should be the sole line of defense — layer controls (validation + authorization + encryption)
- **Rate limiting:** Public-facing endpoints MUST implement rate limiting or throttling to prevent abuse
- **Business logic abuse:** Design MUST consider misuse cases — not just happy-path scenarios

**Verification:**
- Security-critical logic is encapsulated in dedicated modules or services
- Rate limiting is configured on public-facing APIs (at gateway or application level)
- Design documentation addresses at least one misuse/abuse scenario

**When to apply:** Architecture reviews, new service design, API gateway configuration.

---

### SECURITY-12 — Authentication and Credential Management (CRITICAL)

**OWASP:** A07:2021 – Identification and Authentication Failures

**Rule:** Every application with user authentication MUST implement:
- **Password policy:** Minimum 8 characters; check against breached password lists
- **Credential storage:** Passwords MUST be hashed using adaptive algorithms (bcrypt cost>=12 or argon2) — never weak or non-adaptive hashing
- **Multi-factor authentication:** MFA MUST be supported for administrative accounts and SHOULD be available for all users
- **Session management:** Sessions MUST have server-side expiration, be invalidated on logout, and use `Secure`/`HttpOnly`/`SameSite` cookie attributes
- **Brute-force protection:** Login endpoints MUST implement account lockout, progressive delays, or CAPTCHA after repeated failures
- **No hardcoded credentials:** No passwords, API keys, or secrets in source code or IaC templates — use a secrets manager

**Verification:**
- Password hashing uses adaptive algorithms (bcrypt/argon2 — not MD5 or SHA1)
- Session cookies set `Secure`, `HttpOnly`, and `SameSite` attributes
- Login endpoints have brute-force protection (lockout, delay, or CAPTCHA)
- No hardcoded credentials in source code or configuration files
- MFA is supported for admin accounts
- Sessions are invalidated on logout and have a defined expiration

**When to apply:** All authentication flows. Complements `security-review-checklist.md §3` with the full credential management surface including MFA and brute-force protection.

---

### SECURITY-13 — Software and Data Integrity Verification (HIGH)

**OWASP:** A08:2021 – Software and Data Integrity Failures

**Rule:** Systems MUST verify the integrity of software and data:
- **Deserialization safety:** Untrusted data MUST NOT be deserialized without validation — use safe deserialization libraries or allowlists of permitted types
- **Artifact integrity:** Downloaded dependencies, plugins, and updates MUST be verified via checksums or digital signatures
- **CI/CD pipeline security:** Build pipelines MUST restrict who can modify pipeline definitions — separate duties between code authors and deployment approvers
- **CDN and external resources:** Scripts or resources loaded from external CDNs MUST use Subresource Integrity (SRI) hashes
- **Data integrity:** Critical data modifications MUST be auditable (who changed what, when)

**Verification:**
- No unsafe deserialization of untrusted input
- External scripts include SRI integrity attributes when loaded from CDNs
- CI/CD pipeline definitions are access-controlled and changes are auditable
- Critical data changes are logged with actor, timestamp, and before/after values

**When to apply:** Any service deserializing external data, any frontend loading CDN resources, all CI/CD pipeline definitions.

---

### SECURITY-14 — Alerting and Monitoring (HIGH)

**OWASP:** A09:2021 – Security Logging and Monitoring Failures

**Rule:** In addition to logging (SECURITY-02, SECURITY-03), systems MUST include:
- **Security event alerting:** Alerts MUST be configured for: repeated authentication failures, privilege escalation attempts, access from unusual locations, and authorization failures
- **Log integrity:** Logs MUST be stored in append-only or tamper-evident storage — application code MUST NOT be able to delete or modify its own audit logs
- **Log retention:** Logs MUST be retained for a minimum of 90 days (or longer per compliance requirements)
- **Monitoring dashboards:** A monitoring dashboard or alarm configuration MUST be defined for key operational and security metrics

**Verification:**
- Alerting is configured for authentication failures and authorization violations
- Application log groups have retention policies set (minimum 90 days)
- Application roles do not have permission to delete their own log groups/streams
- Security-relevant events (login failures, access denied, privilege changes) generate alerts

**When to apply:** All production deployments. Complements `security-review-checklist.md §9` (Logging & Monitoring) with infrastructure-level retention, tamper-evidence, and alert configuration.

---

### SECURITY-15 — Exception Handling and Fail-Safe Defaults (HIGH)

**OWASP:** A05:2021 – Security Misconfiguration

**Rule:** Every application MUST handle exceptional conditions safely:
- **Catch and handle:** All external calls (database, API, file I/O) MUST have explicit error handling — no unhandled promise rejections or uncaught exceptions in production
- **Fail closed:** On error, the system MUST deny access or halt the operation — never fail open
- **Resource cleanup:** Error paths MUST release resources (connections, file handles, locks) — use try/finally, using statements, or equivalent patterns
- **User-facing errors:** Error messages shown to users MUST be generic — no internal details or system information
- **Global error handler:** Applications MUST have a global/top-level error handler that catches unhandled exceptions, logs them, and returns a safe response

**Verification:**
- All external calls (DB, HTTP, file I/O) have explicit error handling (try/catch, .catch(), error callbacks)
- A global error handler is configured at the application entry point
- Error paths do not bypass authorization or validation checks (fail closed)
- Resources are cleaned up in error paths (connections closed, transactions rolled back)
- No unhandled promise rejections or uncaught exception warnings in application code

**When to apply:** All application services. Reinforces `code-standards.md` error handling rules with explicit fail-closed and resource cleanup requirements.

---

### SECURITY-16 — Cloud SQL Backup and Deletion Protection
**OWASP Mapping:** A05:2021 Security Misconfiguration / A09:2021 Security Logging and Monitoring Failures
**Risk:** Unprotected databases can be permanently deleted (accidental or malicious), or backup gaps create unrecoverable data loss windows.

**Required controls:**

```hcl
# Terraform — Cloud SQL instance hardening
resource "google_sql_database_instance" "main" {
  deletion_protection = true   # Prevents accidental Terraform destroy

  settings {
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true   # PITR — recover to any second in retention window
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30          # 30 days of daily backups
        retention_unit   = "COUNT"
      }
    }
  }
}
```

**Checklist:**
- [ ] `deletion_protection = true` on all Cloud SQL instances (staging + prod)
- [ ] Automated daily backups enabled with ≥ 30 backup retention count
- [ ] Point-in-time recovery (PITR) enabled — required for RPO < 24 hours
- [ ] Backup location set to a different region than primary instance
- [ ] Quarterly restore test: provision a restore, verify data integrity, document RTO/RPO achieved
- [ ] Backup success/failure alerts configured in Cloud Monitoring

**Common misconfiguration:**
```hcl
# BAD — database can be deleted with terraform destroy
resource "google_sql_database_instance" "main" {
  deletion_protection = false   # default is false — must be set explicitly
}
```

**Verify:**
```bash
# Check deletion protection on all instances
gcloud sql instances list --format="table(name,settings.deletionProtectionEnabled)"

# Check backup config
gcloud sql instances describe <INSTANCE_NAME> --format="yaml(settings.backupConfiguration)"
```

**When to apply:** Any IaC defining `google_sql_database_instance`. Complements `terraform-module-library` deletion_protection variable pattern.

---

### SECURITY-17 — GCP Secret Manager Rotation Policy
**OWASP Mapping:** A02:2021 Cryptographic Failures / A05:2021 Security Misconfiguration
**Risk:** Long-lived secrets that are never rotated increase blast radius of any credential compromise indefinitely.

**Required controls:**
- All secrets in GCP Secret Manager MUST have a rotation period configured
- Maximum rotation period: 90 days for service account keys and database passwords, 365 days for API keys with low blast radius
- Recommended: 30 days for database passwords, JWT signing keys

```hcl
# Terraform — Secret Manager with rotation notification
resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password"

  replication {
    auto {}
  }

  rotation {
    next_rotation_time = "2026-06-01T00:00:00Z"   # Set to 90 days from creation
    rotation_period    = "7776000s"                 # 90 days in seconds
  }

  topics {
    name = google_pubsub_topic.secret_rotation.id  # Pub/Sub notification for rotation events
  }
}
```

**Checklist:**
- [ ] All production secrets have `rotation.rotation_period` set (≤ 90 days for credentials)
- [ ] Pub/Sub topic configured to receive rotation notifications
- [ ] Cloud Function or workflow handles automatic secret version creation on rotation event
- [ ] Application reads latest secret version (not a pinned version ID)
- [ ] Old secret versions disabled after rotation confirmed working (keep 1 previous version for rollback)

**Verify:**
```bash
# List secrets without rotation configured
gcloud secrets list --format="table(name,rotation.nextRotationTime)" | grep -v "nextRotation"
```

**When to apply:** All GCP projects using Secret Manager. Extends SECURITY-12 (credential management) with rotation enforcement at the infrastructure layer.

---

## OWASP 2021 Coverage Summary

| OWASP Category | Covered By |
|----------------|------------|
| A01:2021 – Broken Access Control | SECURITY-06, SECURITY-08 |
| A02:2021 – Cryptographic Failures | SECURITY-01, SECURITY-17 |
| A03:2021 – Injection | SECURITY-05 |
| A04:2021 – Insecure Design | SECURITY-11 |
| A05:2021 – Security Misconfiguration | SECURITY-04, SECURITY-07, SECURITY-09, SECURITY-15, SECURITY-16, SECURITY-17 |
| A06:2021 – Vulnerable and Outdated Components | SECURITY-10 |
| A07:2021 – Identification and Authentication Failures | SECURITY-12 |
| A08:2021 – Software and Data Integrity Failures | SECURITY-13 |
| A09:2021 – Security Logging and Monitoring Failures | SECURITY-02, SECURITY-03, SECURITY-14, SECURITY-16 |
| A10:2021 – Server-Side Request Forgery | — (covered by `security-review-checklist.md §4`) |
