---
description: Run a security audit on the codebase. Checks for secrets, OWASP Top 10, dependency vulnerabilities, and configuration issues.
allowed-tools: Bash, Read, Glob, Grep, Task
disable-model-invocation: true
---

# Security Audit

Run a comprehensive security audit on the codebase.

## Process

1. **Determine scope** — audit `$ARGUMENTS` if provided, otherwise audit the full project
2. **Delegate to `security-reviewer` agent** with the following checks:
   - Hardcoded secrets, API keys, tokens, passwords
   - OWASP Top 10 vulnerabilities (injection, XSS, SSRF, broken auth, etc.)
   - Unsafe deserialization or eval usage
   - Missing input validation at system boundaries
   - Insecure cryptographic practices
   - Exposed debug endpoints or verbose error messages in production
3. **Check configuration files**:
   - `.env` files not in `.gitignore`
   - Secrets in `docker-compose.yml` or CI config
   - Overly permissive CORS or security headers
4. **Dependency vulnerability scan:** read `.claude/commands/security-dependencies.md` and run its Steps 1–5 on the same scope (it is the single source of the scanner commands and their exit-code rules). Include the top 5 CVEs by priority score; any CVSS 9+ finding blocks approval. Per ecosystem the status is PASS / FAIL / BLOCKED from the scanner's own exit code — a missing scanner or a non-zero exit without findings is **BLOCKED**, never clean. `pip-audit` has no severity column, so grepping it for `CRITICAL|HIGH` is always empty (a false green); caveats: `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.
5. **Agentic CI/CD audit** (if `.github/workflows/` directory exists):

   Load skill: `claude-actions-auditor`

   Glob `.github/workflows/*.yml` and `.github/workflows/*.yaml`. If any workflow file contains `anthropics/claude-code-action`, run the full 5-step audit from the `claude-actions-auditor` skill.

   Add findings to the final report under a new section:
   ```
   ### Agentic CI/CD
   - [workflow-file:line] [vector name] [description]
   ```

   If no workflows or no Claude Code Action steps found: note "No Claude Code Action workflows detected — agentic CI/CD audit skipped."

6. **Compute 007 Security Score** (run after all findings are collected from steps 2–5):

   Calculate a 0–100 weighted score across 8 domains. For each domain, start at 100 and apply deductions:
   - CRITICAL finding in domain: −15 pts
   - HIGH finding in domain: −8 pts
   - MEDIUM finding in domain: −3 pts
   - LOW finding in domain: −1 pt
   - Floor at 0 per domain

   Map findings to domains using this table:

   | Finding Type | Domain |
   |---|---|
   | Hardcoded secrets, API keys, tokens, passwords | Secrets & Credentials (20%) |
   | SQL injection, XSS, SSRF, input validation, eval/exec | Input Validation (15%) |
   | Broken auth, missing authz, session issues, weak tokens | Auth & Authorization (15%) |
   | Unencrypted PII, weak crypto, data exposure | Data Protection (15%) |
   | Missing error handling, no timeouts, swallowed exceptions | Resilience (10%) |
   | Missing audit logs, no security event logging, debug in prod | Monitoring (10%) |
   | CVEs in dependencies, unsafe base images, CI/CD misconfig | Supply Chain (10%) |
   | OWASP violations, compliance gaps (aggregated) | Compliance (5%) |

   **Final score** = Σ(domain_score × weight). Round to integer.

   **Verdict:**
   - 90–100 → ✅ **Approved** — production-ready
   - 70–89 → ⚠️ **Approved with Caveats** — document mitigations, fix before next release
   - 50–69 → 🔶 **Partially Blocked** — fix HIGH/CRITICAL findings before deploy
   - 0–49 → ❌ **Blocked** — insecure, do not deploy

7. **Report findings**:

```
## Security Audit: [scope]

### 007 Security Score: [N]/100 — [Verdict]

| Domain | Weight | Score | Key Findings |
|--------|--------|-------|--------------|
| Secrets & Credentials | 20% | N/100 | [top finding or "None"] |
| Input Validation | 15% | N/100 | [top finding or "None"] |
| Auth & Authorization | 15% | N/100 | [top finding or "None"] |
| Data Protection | 15% | N/100 | [top finding or "None"] |
| Resilience | 10% | N/100 | [top finding or "None"] |
| Monitoring | 10% | N/100 | [top finding or "None"] |
| Supply Chain | 10% | N/100 | [top finding or "None"] |
| Compliance | 5% | N/100 | [top finding or "None"] |
| **Weighted Total** | 100% | **N/100** | **[Verdict]** |

### Critical
- [file:line] [vulnerability type] [description]

### Warning
- [file:line] [vulnerability type] [description]

### Configuration
- [file] [issue]

### Dependencies
- [package@version] [CVE if known]

### Agentic CI/CD
- [findings or "No Claude Code Action workflows detected — agentic CI/CD audit skipped."]

### Summary
- Critical: N | Warning: N | Info: N
- Score: N/100 | Verdict: [Approved / Approved with Caveats / Partially Blocked / Blocked]
```

8. **Write Lock Document** (only when verdict is Approved or Approved with Caveats — 0 CRITICAL, 0 HIGH findings, and no step reported BLOCKED: an approval cannot cover a scan that did not run):

   Write the file `docs/approvals/security-YYYY-MM-DD-<short-commit>.md` where:
   - `YYYY-MM-DD` is today's date
   - `<short-commit>` is the output of `git rev-parse --short HEAD`

   File contents:
   ```markdown
   # Security Audit Approval

   **Date:** YYYY-MM-DD
   **Commit:** <full commit hash> — <commit message>
   **Scope:** <audited path or "full project">
   **Audited by:** security-reviewer agent + /audit-security command

   ## 007 Security Score

   **Score:** N/100 — [Verdict]

   | Domain | Weight | Score |
   |--------|--------|-------|
   | Secrets & Credentials | 20% | N/100 |
   | Input Validation | 15% | N/100 |
   | Auth & Authorization | 15% | N/100 |
   | Data Protection | 15% | N/100 |
   | Resilience | 10% | N/100 |
   | Monitoring | 10% | N/100 |
   | Supply Chain | 10% | N/100 |
   | Compliance | 5% | N/100 |

   ## Findings Summary

   - CRITICAL: 0
   - HIGH: 0
   - WARNING: N (listed below)
   - INFO: N

   ## Warnings (not blocking)

   <!-- List each WARNING finding here with file:line and brief description -->
   <!-- If none: "None" -->

   ## Waivers

   <!-- If any finding was explicitly waived, document it here:
        - Finding: [description]
        - Reason: [why it was waived]
        - Approved by: [who waived it]
   -->
   <!-- If no waivers: "None" -->

   ## Status

   ✅ APPROVED FOR DEPLOY — No critical or high findings. Safe to proceed to production.
   ```

   If the verdict is Partially Blocked or Blocked (score < 70, or any CRITICAL/HIGH findings):
   - Do NOT write the Lock Document
   - State clearly: "Lock Document not written — score [N]/100 ([verdict]). Resolve all CRITICAL and HIGH findings, then re-run /audit-security."

Use instead when: `/security-sast` — static scanners only; `/security-dependencies` — CVEs and SBOM only; `/xss-scan` — Angular/React XSS sinks only; `/security-hardening` — fix findings across layers (writes code). Only this command writes the Lock Document that `/ship` requires.

$ARGUMENTS
