# Specification Template

## Full Template

```markdown
# Feature: [Name]

## Overview
[2-3 sentence description of the feature and its value to users]

## Functional Requirements

### FR-001: [Requirement Name]
While <precondition>, when <trigger>, the system shall <response>.

### FR-002: [Requirement Name]
While <precondition>, when <trigger>, the system shall <response>.

## Non-Functional Requirements

### Performance
- Response time: < 200ms p95
- Throughput: 1000 requests/minute
- Data volume: Up to 1M records

### Security
- Authentication: JWT required
- Authorization: Role-based (admin, user)
- Data protection: PII encrypted at rest

### Scalability
- Concurrent users: 10,000
- Peak load handling: Auto-scale to 3x
- Data retention: 90 days

### Availability
- Uptime SLA: 99.9%
- RTO: 30 minutes
- RPO: 5 minutes of data loss (or zero)

### Observability
- Events logged: [business events that must appear in logs]
- PII masking: [fields redacted in logs]
- Alerting: [conditions that page on-call]
- Log retention: [N days / N years]

### Open NFR Items
- [Unresolved NFR: implementation must not start until it is resolved]

<!-- Write "none" in any NFR section that genuinely has no requirement; never leave it blank or "TBD". -->

## Acceptance Criteria

### AC-001: [Scenario Name]
Given [context/precondition]
When [action taken]
Then [expected result]

### AC-002: [Scenario Name]
Given [context/precondition]
When [action taken]
Then [expected result]

## Error Handling

| Error Condition | HTTP Code | User Message |
|-----------------|-----------|--------------|
| Invalid input | 400 | "Please check your input" |
| Unauthorized | 401 | "Please log in to continue" |
| Forbidden | 403 | "You don't have permission" |
| Not found | 404 | "Resource not found" |
| Conflict | 409 | "This already exists" |

## Implementation TODO

### Backend
- [ ] Create database migration for X table
- [ ] Implement X service with Y method
- [ ] Add API endpoint POST /api/x
- [ ] Add input validation schema
- [ ] Add authorization check

### Frontend
- [ ] Create X component
- [ ] Add form with validation
- [ ] Implement API integration
- [ ] Add loading/error states
- [ ] Add success feedback

### Testing
- [ ] Unit tests for X service
- [ ] Integration tests for API endpoint
- [ ] E2E test for complete user flow

## Out of Scope
- [Feature/capability explicitly not included]
- [Future enhancement to consider later]

## Open Questions
- [ ] [Question needing stakeholder input]
- [ ] [Technical decision pending]
```

## Save Location

Save as: `specs/{feature_name}.spec.md`

## Required Sections Checklist

| Section | Purpose | Required |
|---------|---------|----------|
| Overview | Quick understanding | Yes |
| Functional Requirements | What it does | Yes |
| Non-Functional Requirements | How well it does it | Yes |
| Acceptance Criteria | How to verify | Yes |
| Error Handling | Failure cases | Yes |
| Implementation TODO | Action items | Yes |
| Out of Scope | Prevent scope creep | Recommended |
| Open Questions | Track decisions | As needed |

---

## Pre-Build Product Brief (Run BEFORE writing the EARS spec)

Use this template when a feature is being defined from scratch or touches multiple stack layers. Complete it before starting the main specification. Output as `specs/{feature_name}-brief.md`.

The brief answers "Should we build this at all?" — the EARS spec answers "How do we build it?"

```markdown
# Product Brief: [Feature Name]
**Date:** [YYYY-MM-DD]
**Status:** DRAFT → GO / NO-GO

---

## 1. Who has this problem?
[Specific user type — not "users" in general. E.g. "Flutter mobile users on iOS 17+ who have >50 items in their list"]

## 2. What is the pain?
[Concrete friction point with severity. E.g. "Loading 50+ items causes >3s freeze on mid-range Android, measured in Sentry"]

## 3. Why now?
[What changed that makes this urgent? Options: new user feedback spike / competitor shipped it / compliance deadline / tech debt unblocking / growth milestone]

## 4. What layer does this land on?
- [ ] REST API only (NestJS 12.x endpoint + Prisma DTO)
- [ ] REST API + Angular UI (NestJS + Angular 22.3.x component)
- [ ] REST API + Flutter mobile (NestJS + Flutter 3.50.x screen)
- [ ] Full stack (NestJS + Angular + Flutter + DB migration)
- [ ] Background/agent only (LangGraph + FastAPI)
- [ ] Database schema change only (PostgreSQL migration)

## 5. What is the minimum stack slice for MVP?
[Name the exact layers. E.g. "NestJS endpoint + Prisma query + Flutter list widget. NO Angular web version in this iteration."]

## 6. Anti-Goal: What are we explicitly NOT building?
[List at least 2 explicit exclusions. E.g.:
- NOT building bulk export in this iteration
- NOT supporting web (Angular) — mobile-only MVP
- NOT adding admin controls — user-facing only]

## 7. Success metric
[Single measurable outcome. E.g. "p95 list load time <500ms on mid-range Android within 2 weeks of release"]

---

## Risk Register

| Risk | Likelihood (H/M/L) | Impact (H/M/L) | Mitigation |
|------|-------------------|----------------|------------|
| [e.g. Prisma query too slow at scale] | M | H | Add DB index + EXPLAIN ANALYZE before shipping |
| [e.g. Flutter widget rebuild storm] | L | M | Profile with Flutter DevTools before release |

---

## Recommendation

**Verdict: [ GO ✅ | NO-GO ❌ | NEEDS MORE DATA ⚠️ ]**

**Rationale:** [2–3 sentences. Why this verdict?]

**If GO:** Proceed to EARS specification using `feature-forge` skill.
**If NO-GO:** [What would need to change to make this a GO?]
**If NEEDS MORE DATA:** [Specific question to answer + who answers it + deadline]
```

## When to use the Product Brief

| Situation | Use Brief? |
|-----------|-----------|
| New feature touching 2+ stack layers | ✅ Required |
| Bug fix or refactor | ❌ Skip — go straight to EARS spec |
| Single-endpoint API change | ❌ Skip |
| New Flutter screen + API | ✅ Required |
| Performance optimisation with no new user-facing feature | ❌ Skip |
| Anything with a DB schema migration | ✅ Required |
