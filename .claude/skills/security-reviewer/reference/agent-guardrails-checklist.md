# Agent Guardrails Checklist

> Scope: review checklist for guardrails around LLM features and agents. For application-layer checks see `security-review-checklist.md`; for infrastructure see `owasp-infrastructure-baseline.md`.
> Canonical guidance: `ai-playbook/playbook.md` §2.4 Output Contract, §2.5 Security Defenses, §2.6 Agent Guardrails; tool safety in `agentic-ai-dev/reference/tool-execution-safety.md`; path-scoped rules in `.claude/rules/ai-engineering.md`. Full AI review: `ai-security-reviewer` agent.

## 1. Deterministic controls vs probabilistic signals

| Control | Kind | May it block on its own? |
|---|---|---|
| Authentication, authorization, tenant/user scope injected by the server | Deterministic | Yes — and nothing else replaces it |
| Tool allowlist per agent/route, argument schema validation, budgets, rate limits | Deterministic | Yes |
| Output schema validation (typed parse; invalid → reject or review) | Deterministic | Yes |
| Human approval for side-effecting or high-risk actions | Deterministic gate | Yes |
| Injection / jailbreak / toxicity / PII classifiers, LLM-as-judge, groundedness scores | Probabilistic | As an extra block or escalation only — never as the authorization decision |

An LLM guardrail is a signal. If removing it would let a user reach data or actions they are not authorized for, the authorization layer is missing.

## 2. Review checklist

- [ ] **Input path:** length/type/format limits before any model call; untrusted content (user text, retrieved documents, tool results, files, URLs) is delimited and passed as data, never concatenated into system instructions.
- [ ] **Indirect injection:** retrieved or tool-returned text cannot grant tool authority; privileged tools require a deterministic check that does not read model-produced claims of permission.
- [ ] **Tool scope:** tenant/user ids come from the authenticated request, are injected server-side, and model-supplied values are ignored or rejected.
- [ ] **Output path:** structured outputs are schema-validated; invalid output is rejected, repaired with a bounded retry, or escalated — never coerced best-effort; free text shown to users is encoded by the UI framework.
- [ ] **PII:** redact or minimise before the model call where the use case allows; never log raw prompts, completions or exception text from request data (use `log_exception` from `deployment-ci-cd/reference/python-observability.md` §2); traces follow `deployment-ci-cd/reference/ai-observability.md` content-capture rules.
- [ ] **Fail closed:** an exception or timeout inside a guardrail is a violation, not a pass. A guardrail that is unavailable blocks or escalates the request (or degrades to a documented safe path), and the failure is logged and alerted.
- [ ] **Audit trail:** each decision records request id, actor, guardrail results and hashed/minimised content. Audit writes may be asynchronous for read-only answers; for side-effecting or regulated actions, a failed audit write blocks the action. Retention follows your data-retention policy (do not invent a number).
- [ ] **Bounded:** every guardrail call has a timeout; every agent run has a deadline, tool-call budget and iteration/recursion limit.
- [ ] **Safety-critical domains:** responses on safety-critical topics bypass answer caches and route to a vetted source or a human; define the topics explicitly instead of relying on a generic content filter.
- [ ] **Configuration:** production cannot disable blocking on CRITICAL findings; any relaxation of HIGH blocking is documented and reviewed.
- [ ] **Evidence:** guardrail behaviour is covered by adversarial eval cases (`eval-guide`), and the review does not claim they pass unless they were executed in the session.

## 3. Anti-patterns to flag

| Severity | Anti-pattern |
|---|---|
| CRITICAL | LLM or classifier output used as the authorization decision; model-supplied tenant/user id trusted; guardrail exception swallowed and treated as pass |
| CRITICAL | Side-effecting tool callable without approval or idempotency key; retrieved/tool text placed in the system instruction |
| HIGH | Output schema failures ignored; PII detected but still sent/logged unredacted; raw prompts or `str(exc)` in logs or traces |
| HIGH | Single regex filter as the only defence; no output-side check at all |
| MEDIUM | Guardrail checks without timeouts; blocking audit writes on a read-only hot path; risk scores computed but never monitored |

## Severity reference

CRITICAL — exploitable now or bypasses authorization/tenant isolation · HIGH — data exposure or unsafe action under realistic conditions · MEDIUM — weakens defence in depth · LOW — hygiene.
