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
4. **Check dependencies** (if applicable):
   - Node.js: `npm audit --audit-level=high > audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -30 audit.log`
   - Python: `pip-audit --strict -r requirements.txt > audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -30 audit.log`, where `requirements.txt` is a pinned file (for a uv project, export it with `uv export --locked --no-hashes`). `pip audit` is not a command; commands and caveats: `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`
   - Flag known CVEs in `pom.xml` dependencies
   - **Status comes from the tool's own exit code, never from grepping the output.** `pip-audit` prints no severity column, so `| grep -E "CRITICAL|HIGH"` is always empty and always "green". Exit 0 = PASS; exit 1 = FAIL (known vulnerabilities, or an audit error under `--strict`); tool missing, offline or unparseable lockfile = **BLOCKED**, not clean. Never report "scan completed with errors" as a pass. A severity policy needs `--format json` plus a stated rule.
5. **Dependency vulnerability scan** (deep scan):

   Run the dependency scanner for a comprehensive CVE analysis with priority scoring:

   ```
   /security-dependencies $ARGUMENTS
   ```

   Include the top 5 highest-priority CVEs (by priority score) in the final report.
   Flag any CVSS 9+ findings as blocking -- do not approve the release until resolved.

6. **Agentic CI/CD audit** (if `.github/workflows/` directory exists):

   Load skill: `claude-actions-auditor`

   Glob `.github/workflows/*.yml` and `.github/workflows/*.yaml`. If any workflow file contains `anthropics/claude-code-action`, run the full 5-step audit from the `claude-actions-auditor` skill.

   Add findings to the final report under a new section:
   ```
   ### Agentic CI/CD
   - [workflow-file:line] [vector name] [description]
   ```

   If no workflows or no Claude Code Action steps found: note "No Claude Code Action workflows detected — agentic CI/CD audit skipped."

7. **Compute 007 Security Score** (run after all findings are collected from steps 2–6):

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

8. **Report findings**:

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

9. **Write Lock Document** (only when verdict is Approved or Approved with Caveats — 0 CRITICAL, 0 HIGH findings):

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

$ARGUMENTS
