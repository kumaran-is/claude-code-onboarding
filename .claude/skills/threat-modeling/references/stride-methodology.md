# STRIDE Methodology Reference

Systematic threat identification using the STRIDE framework applied to data flow diagrams.

## STRIDE Threat Analysis Matrix

| Threat Type | Description | Violated Property | Detection Method | Common Controls |
|-------------|-------------|-------------------|-----------------|-----------------|
| **Spoofing** | Impersonating a user, service, or system | Authentication | Failed login monitoring, token validation logs | MFA, secure session management, certificate pinning |
| **Tampering** | Unauthorized modification of data or code | Integrity | Integrity checks, file monitoring, input validation alerts | Parameterized queries, HMAC signatures, CSP, immutable infra |
| **Repudiation** | Denying an action was performed | Non-repudiation | Audit log gaps, unsigned transaction detection | Comprehensive audit logging, digital signatures, tamper-evident logs |
| **Information Disclosure** | Exposing data to unauthorized parties | Confidentiality | Data access monitoring, error message analysis | Encryption (rest + transit), access controls, error sanitization |
| **Denial of Service** | Disrupting availability of a system | Availability | Resource utilization monitoring, rate limit alerts | Rate limiting, auto-scaling, DDoS protection, circuit breakers |
| **Elevation of Privilege** | Gaining unauthorized access levels | Authorization | Privilege escalation detection, access pattern analysis | RBAC, least privilege, server-side validation, security boundaries |

## Core Threat Questions Per STRIDE Category

### Spoofing
1. Can an attacker impersonate a legitimate user?
2. Are authentication tokens properly validated on every request?
3. Can session identifiers be predicted or stolen?
4. Is multi-factor authentication available for sensitive operations?
5. Can one service impersonate another service?
6. Are API keys or credentials exposed in client-side code?

### Tampering
1. Can data be modified in transit between components?
2. Can data be modified at rest in the database or file system?
3. Are all inputs validated against expected types, ranges, and formats?
4. Can an attacker manipulate application logic via parameter injection?
5. Are database queries parameterized to prevent SQL injection?
6. Can uploaded files contain executable payloads?

### Repudiation
1. Are all security-relevant actions logged with user attribution?
2. Can log entries be tampered with or deleted?
3. Is there sufficient attribution to trace actions to specific users?
4. Are timestamps reliable and synchronized across services?
5. Are financial or critical transactions digitally signed?
6. Can an attacker clear their tracks after an intrusion?

### Information Disclosure
1. Is sensitive data encrypted at rest (PII, credentials, tokens)?
2. Is sensitive data encrypted in transit (TLS 1.2+ for all connections)?
3. Can error messages reveal system internals, stack traces, or paths?
4. Are access controls enforced at every data access point?
5. Is debug information disabled in production builds?
6. Are API responses filtered to exclude fields the caller should not see?

### Denial of Service
1. Are rate limits implemented on all public-facing endpoints?
2. Can malicious input cause unbounded resource consumption (CPU, memory, disk)?
3. Is there protection against amplification attacks?
4. Are there single points of failure in the architecture?
5. Can database queries be crafted to cause full table scans?
6. Are connection pools and thread pools bounded?

### Elevation of Privilege
1. Are authorization checks performed on every request, not just at login?
2. Can users access other users' resources (IDOR)?
3. Can privilege escalation occur through parameter manipulation?
4. Is the principle of least privilege followed for service accounts?
5. Are role assignments validated server-side (not from client tokens)?
6. Can an attacker chain low-privilege bugs to achieve high-privilege access?

## DFD Element to Threat Type Mapping

| DFD Element | Applicable STRIDE Threats | Rationale |
|-------------|--------------------------|-----------|
| **Process** | S, T, R, I, D, E (all) | Processes execute logic; vulnerable to all threat categories |
| **Data Store** | T, R, I, D | Data at rest can be tampered, disclosed; stores can be overwhelmed or lack audit |
| **Data Flow** | T, I, D | Data in transit can be intercepted, modified, or flooded |
| **External Entity** | S, R | External actors can spoof identity or deny actions |

### How to Use This Mapping

For each element in your DFD:
1. Look up the applicable threat types from the table above
2. For each applicable threat type, ask the corresponding core questions
3. If any question answer is "yes" or "unknown," record it as a threat finding
4. Score each finding using the risk matrix below

## Per-Interaction Analysis Pattern

When two DFD elements communicate, analyze the interaction:

```
For each (source, target) pair:
    1. Identify source type and target type
    2. Determine data exchanged and protocol used
    3. Check if interaction crosses a trust boundary
    4. Apply STRIDE threats relevant to BOTH element types
    5. Pay extra attention to trust boundary crossings (higher risk)
    6. Record threats with context: "source -> target: threat description"
```

**Trust boundary crossings** deserve extra scrutiny. Any data flow that crosses from a lower trust zone to a higher trust zone (e.g., external user to internal API) is a primary attack surface.

## Risk Scoring

### Formula

```
risk_score = impact x likelihood
```

Where impact and likelihood are each scored 1-4:

| Score | Impact Level | Likelihood Level |
|-------|-------------|-----------------|
| 1 | Low -- minor inconvenience | Low -- requires significant effort/skill |
| 2 | Medium -- partial data loss or degraded service | Medium -- moderate effort, known technique |
| 3 | High -- significant data breach or service outage | High -- low effort, publicly known exploit |
| 4 | Critical -- full system compromise or mass data breach | Critical -- trivial to exploit, automated tools exist |

### Risk Thresholds

| Risk Score | Severity | Required Action |
|------------|----------|----------------|
| 8-16 | Critical | Immediate remediation required before deployment |
| 6-7 | High | Must be addressed in current sprint |
| 3-5 | Medium | Schedule for near-term remediation |
| 1-2 | Low | Accept with documented justification or address opportunistically |

## Output Document Checklist

Every threat model document MUST include these sections:

- [ ] **Assets** -- Sensitive data inventory with classification (public/internal/confidential/restricted)
- [ ] **Trust Boundaries** -- Zones with different trust levels, every crossing point identified
- [ ] **DFD** -- All processes, data stores, data flows, and external entities mapped
- [ ] **Threat Enumeration** -- Every DFD element analyzed against applicable STRIDE categories
- [ ] **Risk Scores** -- Each threat scored with impact x likelihood, sorted by severity
- [ ] **Mitigations** -- At least one control mapped to each High/Critical threat
- [ ] **Attack Trees** -- One per Critical/High threat; leaves are the attack vectors the security audit tests
- [ ] **Pre-mortem Findings** -- Breach pre-mortem (`the-fool`) answers, each mapped to a mitigation, SR or test
- [ ] **Security Requirements** -- Numbered, testable `SR-NNN` statements, each traced to a threat and to its spec criterion, test and audit item
- [ ] **Residual Risk** -- Risks accepted after mitigation, with justification, owner and review date

### Document Skeleton

Save to `docs/threat-models/<feature>-threat-model.md`:

```markdown
# Threat Model: <Feature>
Date: YYYY-MM-DD · Reviewers: <roles> · Status: draft | approved

## Assets
## Scope and Trust Boundaries      (DFD as Mermaid; every boundary crossing named)
## STRIDE Analysis                 (table per element: threat, STRIDE letter, impact, likelihood, risk, mitigation)
## Attack Trees                    (Critical/High threats only)
## Pre-mortem Findings
## Security Requirements
| ID | Requirement (MUST / MUST NOT + measurable condition) | Threat | Spec criterion | Test | Audit item |
|----|------------------------------------------------------|--------|----------------|------|------------|
| SR-001 | All endpoints except the health and login routes MUST require a valid, server-verified access token | S-03 | AC-4 | `auth.e2e: rejects missing token` | `/audit-security` A01 |
## Residual Risks                  (risk, justification, owner, review date)
```
