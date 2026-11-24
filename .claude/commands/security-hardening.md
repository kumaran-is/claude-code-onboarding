---
description: Full-stack security hardening via coordinated multi-agent orchestration. Runs assessment → remediation → controls → validation across all layers of the stack.
allowed-tools: Bash, Read, Glob, Grep, Task
disable-model-invocation: true
---

# Security Hardening Pipeline

Scope: `$ARGUMENTS` (default: entire project if no argument provided).

This command CHANGES code. Use instead when: `/audit-security` — assess and approve without changing anything; `/security-sast`, `/security-dependencies`, `/xss-scan` — a single scan. Its Phase 4 validation must re-run the scans with their own exit codes; it does not replace `/audit-security` for the Lock Document.

## Phase 1: Assessment

### Step 1 -- Initial vulnerability scan
Dispatch `security-reviewer` agent (model: opus) to perform:
- SAST analysis across changed files
- Secret scanning (API keys, tokens, passwords in source)
- OWASP Top 10 checklist review

Output: findings categorized by CVSS severity (Critical / High / Medium / Low), plus any open findings from `/audit-security`, `/security-sast` and `/security-dependencies`. Triage every finding into this order before fixing anything:

| Priority | Criteria | Action |
|---|---|---|
| P0 | CRITICAL, or exploitable without authentication | Fix before any deploy; stop other work |
| P1 | HIGH, or reachable from the internet | Fix before production deploy |
| P2 | MEDIUM (MEDIUM in auth, session or crypto code is treated as P1) | Fix in the current sprint |
| P3 | LOW | Track in the backlog |

Record each P0/P1 as `### P<n>: <title> — <file:line>` with type (injection, auth, crypto, XSS, ...), exact attack vector and intended fix.

### Step 2 -- Threat modeling
Dispatch `threat-modeling-expert` agent (model: sonnet) to perform:
- STRIDE analysis on the target scope
- Attack surface mapping (entry points, data flows, external integrations)
- Trust boundary identification

Output: threat model document with risk scores per threat.

### Step 3 -- Architecture security review
Dispatch `architect` agent to evaluate:
- Zero-trust architecture compliance
- Defense-in-depth gaps (missing layers)
- Privileged access patterns and service-to-service auth

Output: architecture security assessment with remediation priorities.

## Phase 2: Remediation

### Step 4 -- Critical fix dispatch
Dispatch `security-reviewer` agent (model: opus) to fix all CVSS 7+ findings:
- SQL injection -- parameterized queries / prepared statements
- XSS injection points -- output encoding, sanitization
- Authentication bypass patterns -- secure session validation
- Insecure direct object references -- authorization checks on every access

Fix the root cause, not the instance: when one query, sink or route is vulnerable, grep for every sibling and fix them all. Every P0/P1 fix ships with a regression test that fails on the pre-fix code (e.g. the injection payload, the unauthenticated or other-tenant request) and passes after. Record per finding: root cause, fix `file:line`, regression test `file:line`.

### Step 5 -- Backend hardening
Apply hardening across all backend layers:
- **Java/Spring Boot (WebFlux)**: Spring Security `SecurityWebFilterChain`, CSRF where cookies authenticate, security headers; SQL through R2DBC `DatabaseClient` with bound parameters (`.bind(...)`) or repositories, never blocking `JdbcTemplate` on an event-loop thread and never string-built SQL
- **NestJS (Fastify adapter)**: `@fastify/helmet` registered with `await app.register(helmet)` (Express `app.use(helmet())` does not apply; see `.claude/skills/nestjs-api/reference/nestjs-production-baseline.md` §4), rate limiting (`@nestjs/throttler`), global `ValidationPipe` with `whitelist` + `forbidNonWhitelisted`; other tenants' resources answer 404
- **Python/FastAPI**: Input validation with Pydantic v2, dependency injection for auth guards
- **Common**: AES-256 encryption for PII fields, OAuth2/OIDC integration, secure session config

### Step 6 -- Mobile hardening
Dispatch `flutter-security-expert` agent (model: sonnet) to apply:
- Certificate pinning for all API endpoints
- Flutter Secure Storage for tokens and sensitive data
- Code obfuscation configuration (--obfuscate with --split-debug-info)
- Jailbreak/root detection with runtime integrity checks

## Phase 3: Controls

### Step 7 -- Auth/authz implementation
Verify and implement:
- OAuth2/OIDC with PKCE flow for all client types
- MFA support (TOTP or push-based)
- RBAC with least-privilege roles per service
- Secure session management: rotation on auth, expiry, server-side invalidation

### Step 8 -- Secrets management
Enforce zero hardcoded secrets:
```bash
# Scan for common secret patterns in tracked files
git grep -nE '(password|secret|api_key|token)\s*[:=]\s*["\x27][^"\x27]{8,}' -- ':(exclude)*.md'
git grep -nE 'AKIA[0-9A-Z]{16}' # AWS access keys
git grep -nE '-----BEGIN (RSA |EC )?PRIVATE KEY-----'
```
- Environment variable configuration for all secrets
- Secret rotation policy documented in `docs/security/`
- `.env.example` contains placeholder values only (no real credentials)

## Phase 4: Validation

### Step 9 -- Security scan validation
First dispatch `silent-failure-hunter` over the auth flows and error paths touched in Phases 2-3: no swallowed token/permission failures (`catch` returning `null`, `[]` or a fallback user), every security event (failed login, denied access, token rejection) logged without secrets or PII, and failures surfaced as an explicit error (e.g. `UnauthorizedException`), never a value the caller may not check.

Then re-scan the remediated code, each tool judged by its own exit code:
- Execute `/audit-security` on the target path
- Execute dependency audit: `/security-dependencies` (npm audit / `pip-audit` on the exported `uv.lock` / Maven dependency-check; `pip audit` is not a command)
- Dispatch `security-reviewer` on the files changed during remediation: no new vulnerability introduced by a fix, every P0/P1 marked FIXED
- **Fail gate**: zero CRITICAL **and zero HIGH** unresolved in the re-scan (the same bar as the `/audit-security` Lock Document), no scan BLOCKED or NOT RUN, and every P0/P1 has root cause, fix `file:line`, a passing regression test and a re-scan showing it resolved. Anything else is FAIL, not done

### Step 10 -- Compliance check
Verify against:
- OWASP ASVS Level 2 requirements (authentication, session mgmt, access control)
- Internal release gate checklist:
  - All CVSS 7+ findings remediated
  - No hardcoded secrets in git-tracked files
  - Security headers present (Helmet / Spring Security)
  - Auth endpoints require MFA-capable flow

## Success Criteria

Print at completion:
```
SECURITY HARDENING RESULTS:
[PASS/FAIL] All CVSS 7+ findings remediated
[PASS/FAIL] OWASP Top 10 addressed
[PASS/FAIL] Zero hardcoded secrets in git-tracked files
[PASS/FAIL] Security headers configured (Helmet for NestJS, Spring Security headers for Java)
[PASS/FAIL] MFA-capable authentication implemented
[PASS/FAIL] Re-scan shows zero CRITICAL and zero HIGH unresolved (no scan BLOCKED / NOT RUN)
[PASS/FAIL] Every P0/P1 has root cause, fix file:line and a regression test
[PASS/FAIL] silent-failure-hunter: no swallowed auth/security failures
```

$ARGUMENTS
