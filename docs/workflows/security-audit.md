# Security Audit

> **When to use**: Before any production release, after implementing auth/input handling changes, or on demand
> **Time estimate**: 1–2 hours for a focused audit; 4–8 hours for full-stack deep audit
> **Prerequisites**: Code checked in or staged; SAST tools configured (semgrep, bandit, etc.)

## Overview

End-to-end security audit using the four-command pipeline: `/audit-security` (comprehensive OWASP review) → `/security-sast` (4-scanner static analysis) → `/security-dependencies` (CVE scan) → `/xss-scan` (XSS injection patterns). All agents run in read-only mode and produce findings with severity ratings.

---

## Commands and Agents

| Command / Agent | Scope | What it finds |
|----------------|-------|---------------|
| `/audit-security` | Architecture + code | OWASP Top 10, auth flaws, injection, secrets in code |
| `/security-sast` | Static analysis | 4 scanners: Semgrep, Bandit (Python), ESLint security (JS/TS), SpotBugs (Java) |
| `/security-dependencies` | Package manifests | CVE matches against npm/pip/Maven dependencies |
| `/xss-scan` | Frontend code | XSS injection patterns, dangerouslySetInnerHTML, innerHTML, template injection |
| `security-reviewer` agent | Code changes | Targeted review of changed files for OWASP Top 10 |
| `flutter-security-expert` agent | Flutter code | Mobile-specific: secure storage, cert pinning, GDPR/CCPA |
| `threat-modeling-expert` agent | Architecture | STRIDE threat model, attack trees |

---

## Phases

### Phase 1 — Scope Definition

Before running any scanner, define:
1. What changed since last audit? (git diff range)
2. What is the risk profile? (handles auth? PII? payments?)
3. What scanners are applicable? (frontend? backend? mobile?)
4. What is the acceptable finding threshold? (zero CRITICAL, zero HIGH for production)

**Risk profile → depth mapping**:

| Risk Profile | Minimum Audit Depth |
|-------------|---------------------|
| Auth, payments, PII | Full pipeline: all 4 commands + 2 agents |
| New API endpoints | `/audit-security` + `security-reviewer` + `/security-dependencies` |
| UI-only changes | `/xss-scan` + `security-reviewer` |
| Config / infrastructure | `/security-dependencies` + manual secrets check + `owasp-infrastructure-baseline.md` (SECURITY-01 through SECURITY-15) |
| Routine feature | `/audit-security` + `/security-dependencies` |

---

### Phase 2 — `/audit-security` (OWASP Review)

**Command**: `/audit-security`
**Source**: `commands/audit-security.md`
**Skill**: `security-reviewer`

**What it checks** (OWASP Top 10):
1. **A01 Broken Access Control** — authorization checks on every protected route
2. **A02 Cryptographic Failures** — secrets in code, weak crypto, unencrypted PII
3. **A03 Injection** — SQL, LDAP, OS command, NoSQL injection patterns
4. **A04 Insecure Design** — missing rate limiting, no input validation, insecure defaults
5. **A05 Security Misconfiguration** — debug mode on, default passwords, stack traces in responses
6. **A06 Vulnerable Components** — outdated dependencies (also covered by `/security-dependencies`)
7. **A07 Auth Failures** — weak session management, no MFA enforcement, token exposure
8. **A08 Software Integrity Failures** — unsigned updates, unsigned artifacts
9. **A09 Logging Failures** — missing audit log for security events, logging PII
10. **A10 SSRF** — unvalidated URLs in server-side requests

**Produces**: CRITICAL / HIGH / MEDIUM / LOW findings with file:line evidence

**Gate**: Zero CRITICAL findings. Zero HIGH findings for production release.

---

### Phase 3 — `/security-sast` (4 Scanners)

**Command**: `/security-sast`
**Source**: `commands/security-sast.md`
**Skill**: `sast-configuration`

**4 scanners** (from `skills/sast-configuration/SKILL.md`):

| Scanner | Language | What it finds |
|---------|----------|--------------|
| **Semgrep** | All | OWASP rules, injection, secrets, custom rules |
| **Bandit** | Python | Python-specific: shell injection, pickle, yaml.load, hardcoded passwords |
| **ESLint security** | TypeScript/JavaScript | XSS, eval, prototype pollution, regex DoS |
| **SpotBugs + Find Security Bugs** | Java | SQL injection, path traversal, XXE, deserialization |

**Running manually**:
```bash
# Semgrep (all stacks)
semgrep scan --config p/owasp-top-ten --config p/secrets .

# Bandit (Python): pinned, on the project's interpreter (an older one skips 3.14 files and exits 0)
uvx --python "$(cat .python-version)" --from bandit==1.9.4 bandit -r src/ -ll

# ESLint security (TypeScript)
npx eslint --plugin security src/

# SpotBugs (Java — via Maven)
./mvnw spotbugs:check
```

**CI integration** (from `sast-configuration` skill):
```yaml
# GitHub Actions — runs on every PR
- name: SAST Scan
  uses: semgrep/semgrep-action@v1
  with:
    config: p/owasp-top-ten p/secrets
```

**Gate**: All CRITICAL/HIGH findings addressed or accepted with written justification.

---

### Phase 4 — `/security-dependencies`

**Command**: `/security-dependencies`
**What it runs**:

```bash
# Node.js / NestJS / Angular
npm audit --audit-level=high

# Python: audit the locked set, not the interpreter pip-audit runs in
uv export --locked --no-dev --no-hashes --no-emit-project -o /tmp/req.audit.txt
uvx --from pip-audit==2.10.1 pip-audit -r /tmp/req.audit.txt --no-deps --disable-pip

# Java
./mvnw dependency-check:check

# Flutter / Dart
flutter pub get > /tmp/pub-get.log 2>&1; echo "PUB GET EXIT:$?"; grep -i 'advisor' /tmp/pub-get.log
# No `pub audit` subcommand exists: pub prints security advisories during `pub get` (full gate: /security-dependencies)
```

**Triage process**:
1. CRITICAL CVE → block release, patch immediately
2. HIGH CVE → patch before production, document if unavoidable
3. MEDIUM CVE → patch in next sprint
4. LOW CVE → track, patch in quarterly review

**If patching breaks compatibility**:
- Check if a newer minor version patches it
- Check if a fork with the fix exists
- Document the accepted risk with CVE number, justification, and review date

---

### Phase 5 — `/xss-scan` (Frontend-Specific)

**Command**: `/xss-scan`
**Scope**: Angular templates, TypeScript components, Flutter WebView

**Angular patterns checked**:
```typescript
// ❌ DANGEROUS — innerHTML without sanitization
element.innerHTML = userInput;

// ❌ DANGEROUS — bypass DomSanitizer
this.sanitizer.bypassSecurityTrustHtml(userInput);

// ❌ DANGEROUS — template injection
`<div>${userInput}</div>`

// ✅ SAFE — Angular's built-in sanitization
{{ userInput }}               // text interpolation — auto-sanitized
[innerHTML]="safeHtml"        // DomSanitizer.sanitize() applied
```

**Flutter patterns checked**:
- WebView content without `allowsInlineMediaPlayback: false`
- Dynamic URL construction in WebView navigation
- Unvalidated deep link parameters used in WebView

**Gate**: Zero patterns where user input reaches DOM/WebView without sanitization.

---

### Phase 7 — Agentic CI/CD Security (Claude Code Action)

**Skill**: `claude-actions-auditor`
**When**: Any time `.github/workflows/` contains `anthropics/claude-code-action`, or before adding Claude Code Action to a new workflow

**9 attack vectors checked**:

| Vector | What it detects |
|--------|----------------|
| A — Env Var Intermediary | `${{ github.event.* }}` flows through `env:` block into Claude's prompt — looks clean, isn't |
| B — Direct Expression Injection | `${{ github.event.* }}` directly inside `prompt:` or `claude_args:` |
| C — CLI Data Fetch | `gh issue view` / `gh pr view` in prompt fetches attacker content at runtime |
| D — PR Target + Checkout | `pull_request_target` + checkout pointing to PR head — attacker's code runs with base branch secrets |
| E — Error Log Injection | CI logs or `workflow_dispatch` inputs passed to Claude's prompt |
| F — Subshell Expansion | `allowed_tools` lists tools supporting `$()` — exfiltration via `echo $(env)` |
| G — Eval of AI Output | Claude step output consumed by `eval`/`bash -c`/`$()` in a downstream `run:` step |
| H — Dangerous Sandbox Configs | `--dangerously-skip-permissions`, `Bash(*)`, `--yolo` in `claude_args` |
| I — Wildcard Allowlists | `allowed_non_write_users: "*"` — any GitHub user can trigger Claude |

**Gate**: Zero HIGH findings. No `--dangerously-skip-permissions` or wildcard allowlists in production workflows.

---

### Phase 6 — Mobile Security (Flutter)

**Agent**: `flutter-security-expert`
**When**: Before first App Store or Play Store submission, or when handling PII

**Checks** (from `flutter-security-expert` agent description):
- Secure storage: secrets in `flutter_secure_storage`, not `SharedPreferences`
- Certificate pinning: network traffic pinned for production API calls
- GDPR/CCPA compliance: data retention policy, user data deletion path
- Code obfuscation: `flutter build --obfuscate --split-debug-info` in release builds
- Debug flags: no `debugPrintEnabled = true` in release

```bash
# Verify obfuscation is configured
flutter build appbundle --obfuscate --split-debug-info=build/symbols/
flutter build ipa --obfuscate --split-debug-info=build/symbols/
```

---

## Quick Reference

| Phase | Command/Agent | Gate |
|-------|--------------|------|
| 1 — Scope | Define risk profile + depth | Written scope |
| 2 — OWASP | `/audit-security` | Zero CRITICAL / HIGH |
| 3 — SAST | `/security-sast` (4 scanners) | All CRITICAL/HIGH addressed |
| 4 — Dependencies | `/security-dependencies` | Zero CRITICAL CVEs |
| 5 — XSS | `/xss-scan` | Zero unvalidated user → DOM paths |
| 6 — Mobile | `flutter-security-expert` agent | Cert pinning, secure storage confirmed |
| 7 — Agentic CI/CD | `claude-actions-auditor` skill | Zero HIGH findings; no wildcard allowlists or `--dangerously-skip-permissions` |
| — Score | 007 scoring (built into `/audit-security`) | Score ≥ 70 → Approved or Approved with Caveats |

## 007 Score Verdicts

| Score | Verdict | Action |
|-------|---------|--------|
| 90–100 | ✅ Approved | Production-ready — write Lock Document |
| 70–89 | ⚠️ Approved with Caveats | Write Lock Document + document mitigations; fix before next release |
| 50–69 | 🔶 Partially Blocked | Do NOT write Lock Document — fix HIGH/CRITICAL before deploy |
| 0–49 | ❌ Blocked | Do NOT deploy — insecure, requires redesign |

---

## Finding Severity → Action

| Severity | Action | Timeline |
|----------|--------|---------|
| CRITICAL | Block release. Fix now. | Before any deploy |
| HIGH | Fix before production. Document if unavoidable. | Before prod deploy |
| MEDIUM | Fix in current sprint. | Within 2 weeks |
| LOW | Track. Fix in quarterly review. | Within quarter |
| INFO | Note. Fix if trivial. | Best effort |

---

## Common Pitfalls

- **Running audit after deploy** — audit before every production release, not after
- **Dismissing "low severity" without reading** — MEDIUM findings compound; a chain of MEDIUM can enable an attack
- **Not checking dependencies** — most breaches come from vulnerable third-party packages, not custom code
- **Audit without retesting** — after fixing a finding, re-run the scanner to confirm it's resolved
- **Different scanners for dev vs prod** — use the same scanner in CI/CD as you run locally

## Related Workflows

- [`security-hardening.md`](security-hardening.md) — fixing the findings from this audit
- [`threat-modeling.md`](threat-modeling.md) — design-time security before code is written
- [`pre-commit-validation.md`](pre-commit-validation.md) — lightweight security check on every commit
- [`ios-app-store-release.md`](ios-app-store-release.md) — security audit gates for App Store submission
