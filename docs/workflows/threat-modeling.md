# Threat Modeling

> **When to use**: Before implementing any security-sensitive feature (auth, payments, PII handling, external integrations) — design-time is cheaper than post-release remediation
> **Time estimate**: 2–4 hours for a focused feature; 1–2 days for a new service or system
> **Prerequisites**: Feature spec or architecture diagram exists; `docs/specs/` or `docs/plans/` has context

## Overview

Threat modeling using the STRIDE methodology, attack tree construction, and security requirement extraction. Dispatches `threat-modeling-expert` agent for STRIDE analysis and `the-fool` skill for adversarial pre-mortem. Outputs security requirements that feed into feature implementation before code is written.

---

## Iron Law (from `skills/threat-modeling/SKILL.md`)

> **DO THREAT MODELING BEFORE IMPLEMENTATION, NOT AFTER**
> A threat identified at design time costs 1x to mitigate. At code review: 10x. In production: 100x.

---

## STRIDE Framework

| Threat | Meaning | Example |
|--------|---------|---------|
| **S**poofing | Impersonating another user or system | Using another user's JWT token |
| **T**ampering | Modifying data in transit or at rest | Changing order amount in DB |
| **R**epudiation | Denying an action was taken | No audit log of order creation |
| **I**nformation Disclosure | Exposing data to unauthorized parties | Returning other user's PII in API response |
| **D**enial of Service | Making the system unavailable | Flooding login endpoint without rate limiting |
| **E**levation of Privilege | Gaining higher access than authorized | User accessing admin endpoint |

---

## Phases

### Phase 1 — Load Skill and Define Scope

**Skill**: Load `threat-modeling` (`.claude/skills/threat-modeling/SKILL.md`)
**Agent**: `threat-modeling-expert`

**Define scope before starting**:
1. What system or feature is being modeled?
2. What are the trust boundaries? (where does data cross from trusted to untrusted)
3. Who are the actors? (user types, external systems, admins)
4. What data flows through the system? (PII, credentials, payment data)
5. What is the threat profile? (public internet-facing? internal only? high-value target?)

**Output**: Data Flow Diagram (DFD) — processes, data stores, external entities, trust boundaries.

```
[User Browser] → [API Gateway] → [Auth Service] → [User DB]
                              → [Order Service] → [Orders DB]
                              → [Payment Service] → [Stripe API]
```

Trust boundaries:
- Internet → API Gateway (untrusted to DMZ)
- API Gateway → Services (DMZ to internal network)
- Services → DB (internal to data store)

**AI features (LLM, RAG, agents, MCP):** add the model gateway, retrieval store, tool/MCP gateway, business APIs behind each tool, operation ledger, memory store, approval service and any other agent to the DFD. Model output, retrieved content, tool results, agent messages and memory reads cross a trust boundary inward: they are untrusted. Run the AI threat table in the `threat-modeling` skill ("AI, RAG and Agent Systems"). For governed systems the finished threat model is referenced by the `ai-governance` risk assessment (`threat_model_ref`).

---

### Phase 2 — STRIDE Analysis Per Component

**Agent**: Dispatch `threat-modeling-expert` with scope + DFD

For each component in the data flow, apply all 6 STRIDE categories:

**Example: Auth Service STRIDE analysis**

| Threat | Specific Threat | Likelihood | Impact | Mitigation |
|--------|----------------|-----------|--------|-----------|
| Spoofing | Stolen JWT used by attacker | High | Critical | Short expiry (15min), refresh rotation |
| Tampering | JWT payload modified | Medium | Critical | RS256 signing, server-side verification |
| Repudiation | No log of login events | Medium | High | Audit log: user ID, IP, timestamp, outcome |
| Information Disclosure | Error message reveals user existence | Medium | Medium | Generic error: "Invalid credentials" |
| Denial of Service | Brute force login attempts | High | High | Rate limiting: 10 attempts/min/IP |
| Elevation of Privilege | Regular user accessing admin endpoints | Medium | Critical | RBAC on every protected route |

**Risk scoring**:
```
Risk = Likelihood × Impact
CRITICAL (12+): Immediate mitigation required
HIGH (8–11): Mitigate before production
MEDIUM (4–7): Mitigate within sprint
LOW (1–3): Track and monitor
```

---

### Phase 3 — Attack Trees

For each CRITICAL/HIGH threat, build an attack tree:

```
Goal: Steal user data from Orders DB
├── SQL Injection via order search
│   ├── Find unparameterized query [likely: findByCustomer]
│   └── Inject UNION SELECT to extract users table
├── Auth token theft
│   ├── XSS in frontend → steal localStorage token
│   └── Man-in-the-middle (requires no HTTPS enforcement)
└── Direct DB access
    ├── Exposed DB port (check security group rules)
    └── Credentials in environment logs
```

**Attack tree output** → becomes a checklist of attack vectors to test during security audit.

---

### Phase 4 — Pre-Mortem with `the-fool`

**Skill**: Load `the-fool` (`.claude/skills/the-fool/SKILL.md`)

The-fool asks: *"Assume the system was breached 6 months after launch. What went wrong?"*

**Pre-mortem question set**:
1. What's the most likely way an attacker gets in?
2. What's the highest-value data they could reach?
3. What would we wish we had logged?
4. What would have been the earliest warning sign?
5. Which team assumption was wrong?

**Example pre-mortem findings**:
- "We assumed HTTPS was enforced — it wasn't on the health check endpoint"
- "We assumed JWT expiry was short — it was 24h in the config that was never changed from dev"
- "We assumed the DB wasn't reachable from internet — the security group had a wildcard rule"

Each pre-mortem finding → becomes a security control or a test.

---

### Phase 5 — Security Requirements Extraction

Convert STRIDE findings and pre-mortem into concrete, testable security requirements:

```
## Security Requirements — [Feature Name]

### Authentication
- SR-001: All API endpoints except /health and /auth/login MUST require a valid JWT
- SR-002: JWT access tokens MUST expire in ≤ 15 minutes
- SR-003: Login failures MUST be logged with IP address and timestamp

### Authorization
- SR-004: Users MUST only be able to read their own orders
- SR-005: Admin endpoints MUST verify the admin role claim in JWT
- SR-006: Authorization MUST be checked server-side; client claims MUST NOT be trusted

### Input Validation
- SR-007: All user input MUST be validated before reaching the database
- SR-008: Search queries MUST use parameterized statements; string concatenation is forbidden

### Rate Limiting
- SR-009: /auth/login MUST be rate-limited to 10 requests/minute per IP
- SR-010: /api/search MUST be rate-limited to 100 requests/minute per user

### Logging
- SR-011: All auth events (login, logout, token refresh, failed auth) MUST be logged
- SR-012: Log entries MUST include: timestamp, user ID, IP, action, outcome
- SR-013: PII MUST NOT appear in logs
```

These requirements become:
1. Acceptance criteria in the feature spec
2. Test cases in the integration test suite
3. Checklist items in the security audit gate

---

### Phase 6 — Output to `docs/`

**Save to**: `docs/threat-models/<feature>-threat-model.md`

**Structure**:
```
# Threat Model: [Feature Name]
Date: [YYYY-MM-DD]
Author: Claude Code + [developer name]

## Scope and Trust Boundaries
[DFD diagram — Mermaid]

## STRIDE Analysis
[Table per component]

## Attack Trees
[For each CRITICAL/HIGH threat]

## Pre-mortem Findings
[List of failure scenarios]

## Security Requirements
[SR-001 through SR-N]

## Residual Risks
[Accepted risks with justification and review date]
```

---

## Quick Reference

| Phase | Action | Output |
|-------|--------|--------|
| 1 — Scope | Define system boundary, actors, data flows | DFD diagram |
| 2 — STRIDE | `threat-modeling-expert` agent per component | Risk-scored threat table |
| 3 — Attack trees | Build attack paths for CRITICAL/HIGH | Attack vector checklist |
| 4 — Pre-mortem | `the-fool` skill adversarial session | Failure scenarios |
| 5 — Requirements | Extract testable security requirements | SR-001 through SR-N |
| 6 — Document | Save to `docs/threat-models/` | Signed-off threat model doc |

---

## Common Pitfalls

- **Threat modeling after implementation** — at that point it's a security audit, not threat modeling; findings cost 10x more to fix
- **Only STRIDE-ing the happy path** — threat modeling is about adversarial scenarios; start with "how would an attacker abuse this?"
- **Vague mitigations** — "use authentication" is not a mitigation; "require JWT with RS256 in Authorization header, verified server-side" is
- **No residual risk section** — some threats can't be fully mitigated; accept them explicitly with a review date, don't silently ignore them
- **Threat model not updated** — when the feature changes significantly, the threat model must be updated; treat it like code

## Related Workflows

- [`security-audit.md`](security-audit.md) — post-implementation audit that validates the threat model's security requirements
- [`security-hardening.md`](security-hardening.md) — remediating findings from the audit
- [`ideation-to-spec.md`](ideation-to-spec.md) — threat modeling fits after spec, before design
- [`architecture-design.md`](architecture-design.md) — architectural decisions should reflect threat model outputs
