# Supply Chain, Evaluation Governance, Release and Incidents (governance §9, §10, §13, §19)

Evaluation **methods** (datasets, metrics, judges, CI tiers, red teaming) belong to the evaluation standard and live in `eval-guide` (`reference/golden-dataset.md`, `reference/ci-tiers.md`, `reference/red-teaming.md`). This file covers only the governance obligations around them: funding, protection, release blocking and proof that gates block unsafe releases.

## 1. AI bill of materials (§9.1) and integrity (§9.2)

AI BOM scope: foundation model; model/provider identifier; weights where accessible; fine-tuned adapters/LoRA; tokenizer; prompt templates; embedding models; training datasets; evaluation datasets; judge models; retrieval dependencies; MCP servers; tool packages; container images; software libraries; licenses and usage rights.

Integrity: cryptographic hashes; verified provenance; approved artifact registries; dataset snapshots; version pinning; signed attestations where supported; reproducible deployment manifests; dependency vulnerability scanning. For managed APIs with inaccessible weights, record the vendor model identifier, provider attestations, deployment configuration and documented visibility limitations.

How the `ai_bom` record maps:

| Requirement | Field | Validator (boundary A) |
|---|---|---|
| Component inventory | `components[].component_type` (14 types; provider id lives in `vendor_model_id`) | foundation model and prompt template required |
| Version pinning | `components[].version` | rejects `latest`, `*`, `x`, `^`, `~`, `<`, `>`, `.x`, `||` |
| Cryptographic hashes | `components[].digest` | required for weights, adapters, images, datasets, prompts, MCP servers, tool packages; length matches algorithm |
| Managed API limits | `vendor_model_id`, `visibility_limitations` | required for managed foundation/judge/embedding models and tokenizers without a digest |
| Licenses / rights | `license`, `usage_rights` | license required |
| Provenance / attestations | `provenance.source`, `registry`, `attestation_ref` | source required |
| Vulnerability scanning | `vulnerability_scan_ref` | required |
| Reproducible manifest | `deployment_manifest_ref` | required |

Producing the hashes: container digests from the registry (`docker buildx imagetools inspect`), lockfile hashes for libraries (`uv.lock`, `package-lock.json`), sha256 of the prompt template content as served by the registry, dataset snapshot hashes from the manifest (`eval-guide/reference/golden-dataset.md`). SBOM tooling for software libraries: `deployment-ci-cd/reference/python-ci-supply-chain.md`.

## 2. Release blocking (§9.3)

For systems that fine-tune or keep durable memory: AI BOM completeness is a release gate; artifact integrity must pass; dataset and memory lineage documented; applicable deletion-propagation tests pass; exceptions need authorized, time-bound risk acceptance (`exceptions[]` with `expires`).

"A manifest is not sufficient if its content cannot be independently validated." The validator checks completeness and form only. Independent validation means recomputing each digest from the deployed artifact in CI and comparing (boundary A when the project wires it; C for registry attestations).

## 3. Evaluation platform and economics (§10.1, §10.2)

Shared evaluation capability: golden datasets, held-out sets, canary evaluations, RAG retrieval evaluations, LLM-as-judge, human evaluation, safety and adversarial testing, agent task evaluations, CI/CD integration, evaluation versioning, results and evidence retention. The toolkit gives per-project implementations (`eval-guide`, `rag-evaluator`, `adk-eval-guide`) [A/B]; a shared enterprise platform and its retention store are boundary C.

Evaluation needs explicit funding (§10.2): dataset creation and labeling, domain expert review, human evaluators, judge inference, adversarial testing, canary refresh, infrastructure, statistical analysis, regression testing, independent assurance. Track evaluation cost by use case and risk tier (`kpi_definition`, domain "Evaluations" or "FinOps"). Do not reduce essential high-risk evaluation coverage merely to cut token spend [C].

## 4. Protected canary datasets (§10.3)

Controls: restricted access; separate training and evaluation pipelines; hidden labels; dataset versioning; contamination monitoring; periodic refresh; provenance recording; independent access review. Recommended baseline (ADAPT): review canary relevance quarterly and refresh on contamination, material drift or new capabilities. Dataset mechanics and manifests: `eval-guide/reference/golden-dataset.md`. Access restriction and access review are boundary C (the repository is not a protected store: a canary committed to a shared repo is not hidden).

## 5. Release gates (§10.4)

Block release when required thresholds are violated. Evaluate correctness, groundedness, hallucination, sensitive-data leakage, tool authorization, agent task success, idempotency, recovery, safety, latency, cost. Gate implementation: `eval-guide/reference/ci-tiers.md` and `eval-guide/scripts/eval_gate.py` (`check`, `route`); thresholds are project-approved ADAPT values. Record each gate run as `control_evidence` (control AI-EVAL-001).

## 6. Forced unsafe release exercise (§10.5)

Before declaring the AI control plane operational, seed each unsafe scenario and record the intended independent control's decision. Eval-side seeded tests and how to run them: `eval-guide/reference/red-teaming.md` ("Forced unsafe release exercise"); each scenario result is one `control_evidence` record (`method: seeded_unsafe_scenario`), validated with this skill's script:

| # | Scenario (`control_evidence.scenario`) | Intended independent control | Typical test home |
|---|---|---|---|
| 1 | `known_bad_model_output` | Output contract validation / eval gate | `eval-guide` CI gate, output schema tests |
| 2 | `unauthorized_tool_access` | Tool authorization (AI-SEC-002) | `tool-execution-safety.md`, `mcp-builder` contract tests |
| 3 | `cross_tenant_retrieval` | Tenant-filtered retrieval (AI-DATA-001) | `rag-security-reviewer` tests |
| 4 | `stale_human_approval` | Approval binding + expiry (AI-HUM-001) | approval executor test; `approval_record` validator |
| 5 | `prohibited_sensitive_data_transfer` | DLP / egress policy | gateway test [C]; app redaction tests [A] |
| 6 | `duplicate_financial_mutation` | Idempotency ledger | `tool-execution-safety.md` idempotency tests |
| 7 | `prompt_injection_in_retrieved_content` | Deterministic action gate (not a classifier) | `eval-guide/reference/red-teaming.md` |
| 8 | `invalid_artifact_manifest` | Deployment manifest / AI BOM gate (AI-SUP-001) | `validate_governance_record.py` on `ai_bom` in CI |

Record the exercise itself as one `unsafe_release_exercise` (`assets/schemas/unsafe_release_exercise.schema.json`) listing each of the 8 scenarios exactly once with its `evidence_id`, and validate it **in the same run** as its evidence: `python3 "$V" governance/<system-id>/exercise.json governance/<system-id>/evidence/*.json`. The validator rejects a missing or duplicated scenario, evidence that is absent, invalid or for another scenario, and a `passed` verdict over any scenario that was not run, failed, did not end blocked/quarantined/contained, or was mocked. An exercise file validated alone always fails.

Acceptance (§10.5): each scenario is **blocked, quarantined or safely contained by the intended independent control**; the validator rejects a seeded scenario that expects `allowed`. A control never tested against known-bad conditions cannot be presumed effective, which is why `control_register_entry` rejects `effective` without a Pass result. Record mocked runs as `mocked: true`; they prove application logic, not the production control. Declaring the control plane operational is an organisational decision [C].

## 7. AI incident classification (§13)

Categories: AI-SEC (prompt injection, model attack, unauthorized tool attempt), AI-DATA (sensitive-data leak, retrieval access violation), AI-TENANT (cross-tenant or cross-product exposure), AI-MEM (memory poisoning, cross-session contamination), AI-ACTION (incorrect or unauthorized state change), AI-EVAL (quality or safety regression), AI-PROVIDER (outage or unsafe fallback), AI-COST (uncontrolled inference or agent execution), AI-OVERSIGHT (approval bypass, ineffective review), AI-SUPPLY (compromised or unverified artifact).

Severity depends on actual and potential impact, whether unsafe behaviour was blocked, data sensitivity, customer exposure, financial impact, regulatory consequences, duration, recoverability and control failure (`incident_record.severity_factors`). A blocked attempt is a meaningful security event but not automatically the severity of a successful mutation; repeated blocked attempts may indicate an active attack (`repeated_blocked_attempts`). How factors become a level is the organisation's severity policy [C]; §7.1 fixes the floor it may not go below. Procedure: `ai-incident-response`. Incident evidence (§13.3) → `incident_record` fields: incident id, category and severity, affected model/agent and model/tool versions (`affected`), policy decision, data scope, tenant scope, action history, customer impact, containment actions, recovery outcome, root cause, corrective actions, preventive test cases; the validator requires the last three once resolved.

### 7.1 Severity crosswalk: S0–S3 ↔ SEV-1–SEV-4

Governance §13.2 (the factors in §7 above) lists severity factors but names no levels; S0–S3 is this toolkit's `incident_record.severity` scale (S0 most severe). `.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md` (SEC §8.2) defines SEV-1–SEV-4 with §9.1 SLAs. The crosswalk is one-to-one, and every row carries the **stricter** obligation of the two sources, so neither standard is weakened:

| Level | Meets this level when (any one suffices; the §13.2 factor triggers are toolkit defaults that only escalate) | Acknowledge / stabilize | Mitigate · permanent fix | Severity set by · downgrade needs | Notify |
|---|---|---|---|---|---|
| **S0 = SEV-1** | Playbook SEV-1 (cross-scope data at any ASR, unauthorized write or financial side effect, secret disclosure, code execution via output, supply-chain compromise); or §13.2 factors show an unblocked control failure with irreversible, broad or restricted-data impact | Runbook Stage 1 now (first 15 min; playbook allows ≤ 1 h, the shorter wins) | ≤ 24 h (never prompt-only) · ≤ 7 days | Security owner sets; risk owner confirms (§6.4 demotion decision) · both, disagreement to the AI risk forum | Security, AI platform, capability owner and risk owner at once; Legal at triage when `regulatory_consequence` or customer exposure |
| **S1 = SEV-2** | Playbook SEV-2, or any bypass of a primary (●) control; or §13.2 factors show limited exposure of confidential data or a compensatable state change | Stage 1 now (15 min; playbook ≤ 1 business day) | ≤ 72 h (never prompt-only) · ≤ 30 days | Security owner sets; risk owner confirms · both | As S0 |
| **S2 = SEV-3** | Playbook SEV-3; or a blocked attempt or reversible, in-scope impact | Stage 1 now (15 min; playbook ≤ 3 business days) | — · ≤ 90 days | Security owner · security owner + risk owner | Security and capability owner per severity routing; Legal when `regulatory_consequence` |
| **S3 = SEV-4** | Playbook SEV-4; no data, tool or sink impact | Stage 1 now (15 min) once an incident is opened | — · next planning cycle | Security owner · security owner | Capability owner; Legal when `regulatory_consequence` |

Rules (validator-enforced where marked ✓):

- ✓ A record carrying both `severity` and `security_severity` must match this table row for row.
- ✓ An unblocked cross-tenant exposure (`AI-TENANT`, `blocked_by_deterministic_control: false`) is S0 / SEV-1: isolation is never downgraded (playbook §8.2).
- When the factors (§13.2) and the playbook definition point to different rows, take the more severe row and record both values.
- A blocked attempt is not automatically the severity of a successful mutation (§13.2); repeated blocked attempts may justify escalation, never de-escalation.
- Every level records the §13.3 evidence; `resolved`/`closed` needs root cause, corrective actions and preventive test cases (✓), and the regression case must fail on pre-fix code and pass on post-fix code (playbook §9.1).
- Times are the playbook's ADAPT placeholders, the `ai-incident-response` stage times and the runbook defaults below. **The organisation may tighten this crosswalk (shorter times, a more severe row, more approvers) but may not loosen it**: no longer time, no shifted mapping, no removed approver.

**Runbook levels on the same rows.** `.claude/skills/ai-incident-response/reference/runbook-playbooks.md` (IR §3) SEV1–SEV4 and the eval flywheel P0–P3 (runbook §3, eval strategy §7.9; `regression_case.severity`) map one-to-one onto these rows: S0 = SEV-1 = SEV1 = P0 … S3 = SEV-4 = SEV4 = P3. Where the runbook (§3, §10.1, §13, §14) is stricter than the table above it governs; the playbook's mitigate and permanent-fix limits still bound what the runbook leaves open:

| Level | Page · IC named | Contain (runbook rung pulled; playbook "mitigate" by flag/kill switch) | Detection → regression dataset · → green CI | Mitigate / permanent fix | Update cadence · PIR |
|---|---|---|---|---|---|
| **S0** | immediately 24×7 · ≤ 15 min; Security, Privacy, Legal engaged at declaration | ≤ 30 min (playbook ≤ 24 h) | ≤ 24 h · ≤ 24 h | never prompt-only · ≤ 7 days | every 30 min until contained, then 2 h · ≤ 5 business days |
| **S1** | business hours, 24×7 for T2/T3 · ≤ 30 min | ≤ 2 h (playbook ≤ 72 h) | ≤ 72 h · ≤ 72 h | never prompt-only · ≤ 30 days | every 2 h · ≤ 10 business days |
| **S2** | ticket, owning team same business day | ≤ 1 business day | ≤ 1 week · ≤ 1 sprint | mitigate ≤ 3 business days · permanent fix bounded by green CI ≤ 1 sprint (playbook ≤ 90 days) | daily · recommended |
| **S3** | backlog with owner | — | ≤ 1 sprint · next sprint | fix ≤ 1 sprint (playbook: next planning cycle) | in ticket · sampled |

Runbook escalation rules that apply on top (escalate only): isolation and egress events start at S0 until the scope is proven smaller (✓ for unblocked `AI-TENANT` and unblocked `I3`); a T3 capability is at least one row more severe than the same event on T0/T1; declare high and downgrade only with evidence logged on the ticket. Runbook defaults are `<placeholders>` to ratify; ratifying them longer than this table is loosening.

## 8. Production readiness (§19)

`production_readiness` encodes all 41 checklist items in six groups (strategy and accountability 5, security and data 7, model and evaluation 8, agentic AI 8, production operations 7, governance and compliance 6). A READY verdict is a self-assessment with evidence references; production sign-off by named owners is boundary C/D. Cross-check the engineering release checklist in `ai-launch-check` (guardrails §8): both must pass; neither substitutes for the other.
