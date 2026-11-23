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

Output: findings categorized by CVSS severity (Critical / High / Medium / Low).

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

### Step 5 -- Backend hardening
Apply hardening across all backend layers:
- **Java/Spring Boot**: Spring Security config, CSRF protection, security headers
- **NestJS**: Helmet middleware, rate limiting (`@nestjs/throttler`), global validation pipes
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
Run security scans on remediated code:
- Execute `/audit-security` on the target path
- Execute dependency audit (`npm audit` / `pip audit` / Maven dependency-check)
- **Fail gate**: any remaining CRITICAL finding blocks completion

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
[PASS/FAIL] Security scan shows no CRITICAL findings
```

$ARGUMENTS
