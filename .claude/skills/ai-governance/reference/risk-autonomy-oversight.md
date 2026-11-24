# Risk, Autonomy and Human Oversight (governance §6, §7)

Records: `risk_assessment`, `autonomy_declaration`, `approval_record`. Boundary per item in brackets.

## 1. Risk classification (§6.1, §2.4)

| Risk | Example | Minimum control posture | Toolkit check |
|---|---|---|---|
| Low | Internal non-sensitive summarization | Approved model, registry, logging | `risk_assessment` [B]; approved provider is a runtime control [C] |
| Medium | Customer-facing RAG assistant | Grounding, evaluations, privacy controls | `eval-guide` golden + canary sets [A/B]; `rag-security-reviewer` [A] |
| High | Agent modifying customer records | Tool restrictions, approval, transaction ledger | `approval_record` [A/C]; `tool-execution-safety.md` idempotency/ledger patterns [A] |
| Critical | Safety-critical or consequential autonomous action | Specialized independent review, strong human control | validator: Critical ⇒ `independent_review.required` [A]; the review itself [C/D] |

Assessment inputs the schema requires (§2.4): data sensitivity, customer impact, likelihood, severity, reversibility, tenancy, state-changing, durable memory, fine-tuning, threat model reference, value baseline (§2.1: AI must beat a simpler solution), named business, technical and risk owners, next reassessment date.

Do not compute the tier from a formula in code. The factors are recorded so a risk owner can justify the tier; the tier is a human decision [C].

## 2. Autonomy levels (§6.2)

| Level | Definition | Typical evidence before declaring |
|---|---|---|
| A0 | AI provides information | Risk assessment |
| A1 | AI recommends; human executes | Owner approval + representative evaluations |
| A2 | AI prepares action; human approves execution | Quantitative gate + working `approval_record` flow |
| A3 | AI executes bounded pre-authorized actions | Quantitative gate + recovery, security, independent risk approval |
| A4 | Extended workflows under explicit enterprise authorization | Quantitative gate + independent assurance + executive risk approval |

## 3. Quantitative promotion gates (§6.3)

"Quantitative gates are mandatory for A2 and higher." The standard's numbers are **illustrative review-entry criteria that risk owners must approve** (ADAPT):

| Transition | Illustrative evidence | Additional requirements |
|---|---|---|
| A0 → A1 | 200 representative evaluations, 95% recommendation correctness | Owner approval |
| A1 → A2 | 500 shadow/assisted decisions, 14 days, 98% correct proposals | Human approval controls |
| A2 → A3 | 1,000 production tasks, 30 days, 99.5% task success | Recovery, security, independent risk approval |
| A3 → A4 | 10,000 tasks, 90 days, 99.9% task success | Independent assurance and executive risk approval |

What the validator enforces (boundary A, structure only): evidence present for A2+ and every promotion; one level per promotion; metric matches the target level (`recommendation_correctness`, `correct_proposals`, `task_success`); `unauthorized_actions_observed == 0`; `unresolved_critical_incidents == 0`; confidence interval brackets the observed rate; all ten additional criteria `met` with evidence refs; final records use `thresholds_source: risk-owner-approved` and name `threshold_approved_by`; approval roles per level. It does **not** enforce 200/500/1,000/10,000 or the percentages.

### Statistics the evidence must carry

- **Confidence bounds, not point estimates.** Record a Wilson or Clopper-Pearson interval. With 1,000 tasks and 995 successes the 95% Wilson interval is about [0.988, 0.998]: its lower bound is below 99.5%, so "99.5% observed" alone does not show the system is at 99.5%.
- **Zero events is not zero risk** (§6.3 "Important"). With 0 unauthorized actions in n independent trials, the one-sided 95% upper bound on the rate is about 3/n (rule of three): 0 in 1,000 still allows up to ~0.3%.
- **Representativeness.** Shadow and production samples must cover the traffic mix and adversarial cases (`eval-guide/reference/golden-dataset.md`); a large but narrow sample does not justify promotion.
- **Count alone never promotes.** The ten additional criteria (§6.3): zero observed unauthorized actions, no unresolved critical safety incidents, successful red-team testing, verified tool authorization, successful failure-injection exercises, defined recovery-success threshold, reliable audit evidence, human takeover capability, business-value evidence, statistically justified sample size and confidence bounds.

Evidence sources: eval runs (`eval-guide`, `llm-evaluation` for interval formulas), red team (`eval-guide/reference/red-teaming.md`), failure injection and tool authorization tests (`control_evidence`), production audit logs [C].

## 4. Demotion triggers (§6.4)

Immediate containment or autonomy reduction may be triggered by: unauthorized agent action; critical authorization bypass; cross-tenant data exposure; severe customer or financial harm; critical memory compromise; significant uncontained drift; missing audit evidence; recovery-control failure; unapproved model/tool changes; kill-switch or approval-boundary failure.

`autonomy_declaration.demotion_triggers_monitored` lists which triggers have a detector. Wiring a trigger to an automatic level reduction is a runtime control (feature flag or policy attribute `agent_autonomy_level` in §5.2) [C]; the incident path is `ai-incident-response` (categories AI-ACTION, AI-OVERSIGHT, AI-TENANT, AI-MEM).

## 5. Approval UX (§7.1)

Every consequential approval displays: proposed action, exact affected resource, customer/business impact, current authoritative state, source evidence, uncertainty and limitations, policy warnings, expected side effects, reversibility, alternatives, approval expiration. Approvers can approve, reject, modify, request evidence, escalate, defer.

`approval_record` carries each field, so a missing field is a schema error. Binding and freshness rules (boundary A):

- `action_digest` = sha256 of the canonical proposed action. The executor recomputes it and refuses to run anything whose digest differs (§4.1 invariant 6: approvals are tied to specific proposed actions). A `modify` decision records `modified_action_digest`.
- `authoritative_state.version` is the etag/version read for the approval screen; the executor re-reads state and rejects if it changed (§5.3: never reuse stale authorization decisions for high-impact actions; §10.5 scenario 4).
- Approve after `expires_at` is invalid. On timeout the system applies `timeout_policy` (hold, reject, safe_degrade) and **never auto-approves** (§7.3).

UI patterns for the approval card and keyboard/screen-reader access: `ai-chat` skill and `agentic-ai-dev/reference/agentic-streaming-hitl.md`.

## 6. Automation-bias controls (§7.2)

| Control | How to implement | Boundary |
|---|---|---|
| No default-approve for high-risk actions | No pre-selected Approve; no Enter-to-approve on irreversible actions | A (UI review) |
| No misleading confidence indicators | Show calibrated uncertainty text, not a raw model score | B |
| No concealed material warnings | `policy_warnings` rendered above the action buttons | A (schema) / C (UX) |
| No silent bulk approval | `bulk: true` requires every bound `operation_id` + digest | A |
| Risk-dependent acknowledgment | `risk_acknowledged: true` required for irreversible or warned actions | A |
| Reviewer competency validation | Reviewer role/training records | C |
| Independent sampling of approvals | Second-reviewer sample of decided approvals | C |
| Complexity-adjusted review-time anomaly detection | Flag reviews far faster than the action's complexity baseline. Avoid arbitrary minimum review times (§7.2). | C |

## 7. Approval operations metrics (§7.3)

Approval and rejection rates, approval modifications, incorrect approval rate, reviewer disagreement, approval override anomaly rate, queue latency, escalation SLA adherence, reviewer workload, stale-state approval attempts, downstream incidents. Derive them from `approval_record` streams; define each as a `kpi_definition` (domain "Human Oversight") [B/C].
