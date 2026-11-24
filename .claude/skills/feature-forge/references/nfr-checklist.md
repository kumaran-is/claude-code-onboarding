# NFR Requirements Checklist

> Load during Phase 2 (Details) or Phase 3 (Edge Cases) of the feature-forge interview.
> Ask NFR questions BEFORE writing the spec — vague NFRs become untestable acceptance criteria.
>
> **Trigger**: Any feature with >100 users, any API endpoint, any shared service, any data-persistence layer.

---

## Overconfidence Prevention

Never accept vague NFR answers. Always follow up:

| Vague Answer | Follow-Up Question | Why |
|-------------|-------------------|-----|
| "it should be fast" | "What is the p95 latency target? For how many concurrent users?" | Untestable without a number |
| "high availability" | "What uptime SLA? 99.9% (8.7h/yr downtime) or 99.99% (52min/yr)?" | Architecture differs significantly |
| "it needs to scale" | "What is the expected load today vs 12 months from now? Orders of magnitude matter." | Horizontal vs vertical scaling choice |
| "it should be secure" | "What data is stored? PII? PCI? PHI? What compliance standard applies?" | Security controls differ by data class |
| "standard logging" | "What retention period? Who needs access to logs? Is this for compliance or debugging?" | Drives infrastructure cost and tooling |
| "should handle failures" | "Define failure: 503 from upstream? DB timeout? Partial write? Recovery time objective?" | Determines retry strategy and circuit breakers |
| "not sure yet" | Stop. Do not proceed. Mark as OPEN NFR — implementation must not start until resolved. | Ambiguous NFRs become unverifiable acceptance criteria |

If no trigger applies (for example a low-traffic internal admin utility), still ask once: "Are there any latency, availability or compliance requirements?" If the answer is "none", write "none" in each NFR section of the spec. An empty section is read as "not asked", not as "no requirement".

---

## NFR Categories

### 1. Performance

**Goal**: Establish measurable latency and throughput targets before implementation.

| Area | Questions |
|------|-----------|
| **Latency** | What is the p50/p95/p99 response time target for this feature? (e.g., API response < 200ms p95) |
| **Throughput** | How many requests per second at peak load? How many concurrent users? |
| **Data volume** | How much data is read/written per operation? Rows, bytes, attachments? |
| **Async vs sync** | Can operations be async (queue + notify) or must they be synchronous end-to-end? |
| **Caching** | Are cache hits acceptable? What is the acceptable staleness window? |

**Tech-stack defaults to confirm or override:**

| Stack | Default | Override Trigger |
|-------|---------|-----------------|
| Java Spring Boot 4.2 | Spring MVC + virtual threads (WebFlux when justified). Target: < 100ms p95 for CRUD | Batch jobs, report generation |
| NestJS / Fastify | < 50ms p95 overhead, Fastify serialization on by default | Heavy CPU tasks → offload to worker |
| Python FastAPI | < 200ms p95 for async endpoints | CPU-bound → use Celery/task queue |
| Angular SPA | < 300ms LCP for initial load; < 100ms for interactions | Data-heavy dashboards |
| Flutter mobile | < 16ms frame render (60fps); < 32ms (30fps acceptable) | Background sync, offline-first |

**AskUserQuestion example (latency tier):**

```
Header: "Latency target"
Question: "What response time target should this feature meet?"
Options (single-select):
- "< 100ms p95 — real-time UX (typeahead, live updates)"
- "< 500ms p95 — interactive (form submit, search)"
- "< 2s p95 — acceptable for complex queries"
- "< 10s p95 — background / report generation"
- "Async only — fire-and-forget with notification"
```

---

### 2. Scalability

**Goal**: Determine how load grows and whether the architecture must scale horizontally.

| Area | Questions |
|------|-----------|
| **Current load** | How many users/requests/records today? |
| **Growth projection** | Expected load in 3 months? 12 months? |
| **Traffic pattern** | Steady load or bursty? (e.g., daily batch, event spikes, seasonal peaks) |
| **Horizontal scaling** | Must the feature run as multiple stateless instances? Shared state? Session affinity needed? |
| **Data growth** | How fast does the dataset grow? Will queries degrade as rows increase? |
| **Rate limiting** | Should this feature be rate-limited per user/tenant? What limits? |

**AskUserQuestion example (scale tier):**

```
Header: "Scale expectations"
Question: "What is the expected usage scale for this feature?"
Options (single-select):
- "< 100 users, low frequency — internal tool"
- "100–10K users, moderate frequency — team product"
- "10K–1M users — consumer product, must scale horizontally"
- "> 1M users — high scale, architecture review required"
```

---

### 3. Availability / Reliability

**Goal**: Establish uptime SLA, failure tolerance, and recovery objectives.

| Area | Questions |
|------|-----------|
| **Uptime SLA** | What uptime is required? 99.9%? 99.95%? 99.99%? |
| **RTO** | Recovery Time Objective — how quickly must the system recover after failure? |
| **RPO** | Recovery Point Objective — how much data loss is acceptable? (e.g., zero, last 5 minutes) |
| **Failover** | Must the feature survive a single-node failure without user impact? |
| **Degraded mode** | If a dependency is unavailable, should the feature degrade gracefully or fail hard? |
| **Scheduled downtime** | Is planned maintenance window acceptable? What window? |

**Quick Reference: SLA Tiers**

| Tier | Uptime | Max Downtime/Month | Typical Use Case |
|------|--------|--------------------|-----------------|
| Standard | 99.9% | 43.8 min | Internal tools, admin panels |
| Business | 99.95% | 21.9 min | Customer-facing APIs |
| High | 99.99% | 4.4 min | Payment flows, auth services |
| Critical | 99.999% | 26 sec | Core infrastructure, safety systems |

**AskUserQuestion example (availability tier):**

```
Header: "Availability requirement"
Question: "What uptime SLA does this feature require?"
Options (single-select):
- "99.9% — standard (< 44 min/month downtime acceptable)"
- "99.95% — business critical (< 22 min/month)"
- "99.99% — high availability (< 5 min/month)"
- "Best effort — internal tool, downtime acceptable"
```

---

### 4. Security

**Goal**: Identify data sensitivity, authentication, authorization, and compliance requirements.

> For deep security review, dispatch the `security-reviewer` agent after spec is written.

| Area | Questions |
|------|-----------|
| **Data classification** | What data does this feature store or transmit? PII? PCI? PHI? Credentials? |
| **Authentication** | Who can access this feature? Public, authenticated users, specific roles? |
| **Authorization** | Is access role-based (RBAC)? Attribute-based (ABAC)? Per-row/resource? |
| **Input surface** | What user-provided input is accepted? File uploads? URLs? Free text? |
| **Audit trail** | Must access and mutations be logged for compliance? Who reviews logs? |
| **Secrets** | Does this feature need API keys, tokens, or credentials? Where are they stored? |
| **Compliance** | Does this feature fall under GDPR, HIPAA, SOC 2, PCI-DSS, or local data residency law? |

**AskUserQuestion example (data sensitivity):**

```
Header: "Data sensitivity"
Question: "What category of data does this feature handle? (select all that apply)"
Options (multi-select):
- "PII — names, emails, addresses, phone numbers"
- "Financial — payment methods, transaction amounts"
- "Health — PHI, medical records"
- "Credentials — passwords, API keys, tokens"
- "Non-sensitive — public or anonymized data only"
```

---

### 5. Observability and Logging

**Goal**: Define what must be logged, traced, and alerted on for this feature.

| Area | Questions |
|------|-----------|
| **Structured logs** | What events must be logged? (request in/out, errors, state transitions, business events) |
| **Distributed tracing** | Does this feature span multiple services? Trace IDs required? |
| **Metrics** | What counters/histograms are needed? (e.g., request rate, error rate, queue depth) |
| **Alerting** | What conditions should trigger a PagerDuty/alert? Error rate threshold? Latency spike? |
| **Log retention** | How long must logs be retained? (compliance may mandate 1–7 years) |
| **Sensitive data in logs** | Are there fields that must be masked or redacted? (PII, tokens) |

**Tech-stack logging standards:**

| Stack | Logging Tool | Standard |
|-------|-------------|---------|
| Java Spring | SLF4J + Logback (structured JSON) | Centralized via centralized logger — never `System.out.println` |
| NestJS | NestJS `Logger` (per-module) | Never `console.log` — use Logger service |
| Python FastAPI | `structlog` or `logging` with JSON formatter | Never `print()` |
| Angular | Custom `ErrorHandler` service | Never `console.error` directly |
| Flutter | `logger` package with level filtering | Never `debugPrint` in production |

---

### 6. Maintainability

**Goal**: Establish code quality, testability, and operational expectations.

| Area | Questions |
|------|-----------|
| **Test coverage** | What test types are required? Unit, integration, E2E? Coverage floor? |
| **API versioning** | Will this API need versioning (v1, v2)? What is the deprecation policy? |
| **Feature flags** | Should this feature be gated behind a flag for gradual rollout? |
| **Documentation** | Is an OpenAPI spec required? Internal README? Architecture diagram? |
| **Operational runbook** | Is a runbook needed for on-call? What failure modes must be documented? |
| **Tech debt** | Are there existing patterns this feature must follow or known tech debt to avoid? |

---

### 7. Compliance and Data Residency

**Goal**: Identify legal and regulatory constraints that affect implementation choices.

| Area | Questions |
|------|-----------|
| **Data residency** | Must data be stored in a specific region or country? (EU, US, AU) |
| **Right to deletion** | Must the system support GDPR Article 17 (right to erasure)? |
| **Data export** | Must users be able to export their data (GDPR portability)? |
| **Consent** | Does the feature collect data requiring explicit user consent? |
| **Retention limits** | Is there a legal maximum retention period? (GDPR: no longer than necessary) |
| **Audit requirements** | Must access logs be immutable and retained for N years? |
| **Third-party data sharing** | Does this feature share data with third parties? DPA required? |

**AskUserQuestion example (compliance):**

```
Header: "Compliance requirements"
Question: "Which compliance standards apply to this feature? (select all that apply)"
Options (multi-select):
- "GDPR — EU personal data"
- "HIPAA — US health data"
- "PCI-DSS — payment card data"
- "SOC 2 — enterprise security audit"
- "None — no regulated data"
- "Not sure — need legal review"
```

---

## Quick Reference: Common SLA Tiers

| Tier | Uptime | Max Downtime/Month | Use Case |
|------|--------|--------------------|---------|
| Best effort | 99% | 7.3 hrs | Dev/staging environments |
| Standard | 99.9% | 43.8 min | Internal tools, admin dashboards |
| Business | 99.95% | 21.9 min | Customer-facing APIs, user workflows |
| High | 99.99% | 4.4 min | Auth, payments, data pipelines |
| Critical | 99.999% | 26 sec | Core infrastructure, safety systems |

---

## NFR Integration with Spec Template

NFR answers must appear as testable acceptance criteria in the spec. Transform answers like this:

| NFR Answer | Acceptance Criterion (EARS format) |
|------------|-----------------------------------|
| "< 500ms p95 response" | WHEN 100 concurrent users submit requests THE SYSTEM SHALL respond within 500ms at the p95 percentile |
| "99.99% uptime" | WHEN a single instance fails THE SYSTEM SHALL failover within 30 seconds without user-visible errors |
| "PII must not appear in logs" | WHEN any request containing user email is logged THE SYSTEM SHALL redact the email field |
| "GDPR right to erasure" | WHEN a user submits a deletion request THE SYSTEM SHALL remove all PII within 30 days |
| "Rate limit per user" | WHEN a user exceeds 100 requests per minute THE SYSTEM SHALL return HTTP 429 with a Retry-After header |

### NFR → Implementation Tasks

Every NFR must own at least one task in the spec's Implementation TODO:

| NFR category | Typical implementation tasks |
|--------------|------------------------------|
| Performance | Caching layer, query index review (`EXPLAIN ANALYZE`), async offload to a queue |
| Scalability | Stateless service design, connection pool sizing, rate limiter middleware |
| Availability | Health check endpoint, circuit breaker config, retry policy |
| Security | Input validation, auth middleware, secrets from env (never code) |
| Observability | Structured logging, trace ID propagation, alert rules |
| Maintainability | OpenAPI spec, feature flag config, migration reversibility check |
| Compliance | PII masking in logs, data retention policy, erasure endpoint |

---

## AskUserQuestion — NFR Batch Pattern

Group related NFR questions to reduce interview fatigue. Example NFR batch for an API feature:

**Batch 1 — Scale and performance:**
1. "What is the expected concurrent user count at peak load?" (open-ended)
2. "What latency target?" (single-select: < 100ms / < 500ms / < 2s / async)
3. "What uptime SLA?" (single-select: 99.9% / 99.95% / 99.99% / best-effort)

**Batch 2 — Data and compliance:**
4. "What data does this feature store?" (multi-select: PII / financial / health / non-sensitive)
5. "Which compliance standards apply?" (multi-select: GDPR / HIPAA / PCI / SOC2 / none)

**Batch 3 — Operations:**
6. "What failure mode is acceptable?" (single-select: fail-fast / degrade gracefully / queue and retry)
7. "Log retention requirement?" (single-select: 30 days / 1 year / 7 years / unknown)
