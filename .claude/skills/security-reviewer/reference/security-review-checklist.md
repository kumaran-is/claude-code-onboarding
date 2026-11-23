# Security Review Checklist

## Scan Categories

### 1. Secrets Detection (CRITICAL)
- No hardcoded API keys, passwords, tokens, or connection strings in source code
- Secrets loaded from environment variables or secret managers only
- No secrets in git history (check with grep/trufflehog if suspicious)
- **Never paste real API keys, tokens, or credentials into AI chat interfaces** (Cursor, Claude, ChatGPT, Copilot). Use `process.env.VAR_NAME` placeholders in prompts. AI providers may log conversations — treat chat input as a public channel.
- `.env` files in `.gitignore`
- **Frontend bundles are public:** `environment*.ts`, `import.meta.env`/`VITE_*`, `define` values and a served `config.json` ship to every visitor. Only publishable identifiers belong there; scan `dist/` (and any `.map`) in CI (`web-frontend-security.md` §9)

### 2. Injection Prevention (CRITICAL)
- All SQL queries parameterized (no string concatenation with user input)
- No command injection via `exec`/`spawn` with unsanitized input
- No NoSQL injection in MongoDB/Firestore queries
- ORMs used safely (no raw queries with user input)

### 3. Authentication & Authorization (CRITICAL)
- Passwords hashed with bcrypt/argon2 (never plaintext comparison)
- JWT tokens properly validated (signature, expiry, issuer)
- Authorization checked on every route/endpoint (not just authentication)
- **Client-side guards are UX, NOT security.** Angular route guards, Flutter widget visibility checks, and UI-level role hiding do NOT enforce authorization. All authorization MUST be enforced server-side. Anyone can call your API directly.
- No IDOR -- users cannot access other users' resources by changing IDs: object fetches carry the caller's scope (organization/owner) in the query, foreign objects return 404 (not 403), and the actor id comes from the verified token, never the request body (`python-dev/reference/fastapi-authorization-boundaries.md`)
- Side-effect endpoints (send, charge, publish, delete) are reachable only by the identity that owns the action, not by any authenticated user; denials are audit-logged without echoing submitted values
- Rate limiting on auth endpoints (login, register, password reset)
- Session management secure (httpOnly, secure, sameSite cookies)
- **Prefer managed auth providers** (Firebase Auth, Auth0, Clerk) over custom JWT implementations for production apps. Custom auth with bcrypt+Passport is acceptable for learning/demo projects only. Managed providers handle token rotation, MFA, account recovery, and security patches automatically.

### 4. Input Validation & Output Encoding (HIGH)
- All user inputs validated and sanitized server-side
- XSS prevention: output escaped, Content-Security-Policy header set. Browser apps: sinks, CSP, Trusted Types, XSRF scope, token storage, `returnUrl` and `postMessage` rules with severities in `web-frontend-security.md`
- File uploads validated (type, size, content) and stored outside webroot
- URL inputs validated against allowlist to prevent SSRF

### 5. Data Protection (HIGH)
- HTTPS enforced; no mixed content
- PII encrypted at rest; sensitive data not logged
- Error messages do not expose internal details or stack traces
- Security headers set (HSTS, X-Content-Type-Options, X-Frame-Options, CSP)
- CORS configured with specific origins (not wildcard in production)

### 6. Dependencies (HIGH)
- **Verify every package before installing:** Check npm/PyPI download count (>1K weekly), last publish date (<12 months), verify package name matches intended (typosquatting defense: `lodash` not `lodash-utils`). For AI-suggested packages, verify the package actually exists on the registry before running `npm install` / `pip install`.
- `npm audit` / `pip-audit` / dependency-check clean of critical/high CVEs, judged by the tool's own exit code (pip-audit prints no severity, `pip audit` is not a command; see `deployment-ci-cd/reference/python-ci-supply-chain.md`)
- No deprecated or unmaintained packages in critical paths
- Lock files committed; dependencies pinned
- **Dependabot enabled:** `.github/dependabot.yml` committed with weekly updates for all package ecosystems used in this project (npm, maven, pip, pub)
- **Dependabot auto-merge:** Security patch updates (patch-level, no breaking changes) auto-merged via GitHub Actions workflow; minor/major require review

**Dependabot config for this workspace** (`.github/dependabot.yml`):
```yaml
version: 2
updates:
  # NestJS / Angular (npm)
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    groups:
      security-patches:
        applies-to: security-updates
        update-types: ["patch"]

  # Spring Boot (Maven)
  - package-ecosystem: "maven"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  # Python (pip)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  # Flutter (pub)
  - package-ecosystem: "pub"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
```

### 7. Financial/Transaction Security (CRITICAL, when applicable)
- Financial operations use atomic transactions with row locks
- No race conditions in balance checks (check-then-act patterns)
- No floating-point arithmetic for money (use integer cents or Decimal)
- Audit logging for all money movements
- Rate limiting on financial endpoints

### 8. Database Security (HIGH)
- Row Level Security (RLS) enabled on multi-tenant tables
- No direct database access from client
- Database credentials not hardcoded; rotated regularly
- **Secret rotation schedule enforced:** All secrets (API keys, DB passwords, JWT signing keys, service account keys) rotated every 90 days maximum. Use calendar reminders or automated rotation (GCP Secret Manager auto-rotation, AWS Secrets Manager rotation lambdas). Rotation must be zero-downtime: deploy new secret → verify → revoke old secret.
- Parameterized queries only

### 9. Logging & Monitoring (MEDIUM)
- Security events logged (failed logins, authorization failures, input validation errors)
- No sensitive data in logs (passwords, tokens, PII)
- Alerts configured for anomalous patterns
- **Mandatory audit triggers:** Audit log required for: record deletions, role/permission changes, payment events, data exports, account modifications, admin actions. If a critical action has no audit trail, flag it as HIGH severity.

### 10. MCP Servers and Agent Tools (CRITICAL/HIGH, when applicable)
Requirement levels (spec MUST vs practice) and severities S1–S13 / T1–T8: `mcp-security.md`. Minimum checks:
- Remote (HTTP) server: Protected Resource Metadata served, 401 carries `resource_metadata`, tokens validated for `alg`, `iss`, `aud` = this server and `exp`; no token passthrough to upstream APIs
- `Origin` validated (403); local servers bind 127.0.0.1; remote binds list allowed hosts and origins
- Per-tool scopes; tenant and user only from the verified token, never tool arguments or client headers
- Every URL-fetching tool goes through an SSRF guard that classifies resolved addresses with a library, pins them, and re-validates each redirect
- Destructive tools require a server-verified approval; annotations (`destructiveHint`, `readOnlyHint`) are hints, not controls
- MCP client config: no secrets in `args`, no deprecated/archived server packages, versions pinned

## Anti-Patterns to Always Flag

- Hardcoded secrets or credentials
- String-concatenated SQL/commands with user input
- `innerHTML` with unsanitized user input
- Plaintext password storage or comparison
- Missing authorization checks on endpoints
- `fetch(userProvidedUrl)` without URL validation, or validation by hostname string prefix (misses `localhost`, `[::1]`, IPv4-mapped IPv6, DNS names that resolve to private addresses, redirects)
- An MCP server forwarding the client's access token upstream, or reading the tenant from tool arguments
- `GRANT ALL` or overly permissive database roles
- Race conditions in financial operations (check-then-act without locks)
- Disabled security features in production (debug mode, permissive CORS)
- Logging passwords, tokens, or API keys

## Common False Positives

- Credentials in `.env.example` (placeholder values, not real secrets)
- Test credentials clearly marked in test files
- Public/publishable API keys (e.g., Stripe publishable key)
- SHA256/MD5 used for checksums, not password hashing

## Output Format

Report findings grouped by severity (CRITICAL > HIGH > MEDIUM > LOW) with:
- File location and line number
- Vulnerability category (e.g., SQL Injection, XSS, Hardcoded Secret)
- Issue description and impact
- Recommended fix

End with the security checklist showing pass/fail status and an overall risk level (CRITICAL / HIGH / MEDIUM / LOW).
