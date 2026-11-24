---
name: ai-governance
description: "Enterprise AI governance records and controls: risk classification (Low-Critical), autonomy levels A0-A4 with quantitative promotion gates, human approval records, control effectiveness register, control evidence, AI BOM, production readiness, regulatory register, AI incident records, scorecard KPIs. Use when assessing AI risk, declaring or promoting autonomy, building governance evidence, auditing governance readiness or validating governance JSON records. Not for eval metrics (eval-guide) or runtime guardrail code (ai-playbook)."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
last-reviewed: 2026-11-23
metadata:
  triggers: AI governance, risk assessment, autonomy level, A0-A4, promotion gate, control register, control evidence, AI BOM, production readiness, regulatory register, governance audit, forced unsafe release, shadow AI
  related-skills: ai-audit, ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, eval-guide, threat-modeling, security-reviewer
---

# AI Governance

This skill is the toolkit's home for enterprise AI governance requirements (prefix GOV). Section ids §1–§20 and requirement ids GOV-<section>-<nn> are stable identifiers kept from the source framework; each §n cited in this skill resolves to its skill-local home in `reference/boundary-map.md` (Primary toolkit file column). The skill turns the requirements into machine-checkable records, organisation-owned adoption checklists (`reference/operating-model-and-registers.md` §10) and an honest boundary between what the toolkit can do and what only an organisation can do. Scope: predictive ML, generative AI and foundation models, RAG, assistants and copilots, autonomous and multi-agent systems, MCP and tool-enabled agents, AI platforms and third-party AI services.

## Iron Law

**A template, a schema or a valid record is never evidence that a control works, or that anyone adopted, owns or approved anything.** Governance claims need executed control evidence (command + own exit code + negative control) and named human decisions recorded by the people who made them. "The record validates" means only "the record is complete and internally consistent".

## Keep the three concerns separate

| Concern (requirement prefix) | Question it answers | Toolkit home |
|---|---|---|
| Evaluation (EVAL) | How do we measure quality, safety and reliability? | `eval-guide`, `llm-evaluation`, `rag-evaluator` |
| Engineering guardrails (GR) | Which runtime/engineering invariants must code satisfy? | `ai-playbook`, `ai-decision-record`, `ai-launch-check`, reviewer agents |
| Enterprise governance (GOV) | Who is accountable, what risk is accepted, which controls exist, what evidence proves them? | **this skill**, `ai-audit` (governance mode), `ai-incident-response` |

Three different classifications. Never derive one from another mechanically:

| Dimension | Values | Source | Field in records |
|---|---|---|---|
| Governance risk tier | Low / Medium / High / Critical | §6.1, `reference/risk-autonomy-oversight.md` §1 | `risk_tier` |
| Autonomy level | A0 / A1 / A2 / A3 / A4 | §6.2, `reference/risk-autonomy-oversight.md` §2 | `autonomy_level`, `declared_level` |
| Engineering risk tier | T0 / T1 / T2 / T3 | guardrails §3 | `engineering_risk_tier` (cross-reference only) |

An A1 recommender can be Critical risk; a bounded A3 workflow can be Low (§6.1). The validator rejects a T-tier in a risk-tier slot.

## Boundary labels (every requirement carries one)

| Label | Meaning | Example |
|---|---|---|
| **A** | Toolkit implements and tests it directly | Validator rejects a stale approval, a floating AI BOM version, a READY verdict with open items |
| **B** | Toolkit generates a template, schema or checklist; humans fill it | Risk assessment, regulatory register row, KPI definition |
| **C** | Needs enterprise infrastructure or a named organisational owner | LLM gateway, policy decision point, CASB/egress discovery, evidence repository, council |
| **D** | Needs legal, regulatory or executive approval | Regulatory applicability, risk appetite, A3→A4 executive approval |

Full section-by-section map with GOV IDs: `reference/boundary-map.md`.

## Proportionality (when NOT to demand enterprise governance)

Governance scales with risk. Do not impose this skill's records on a prototype or an internal Low-risk tool unless asked.

| Situation | Minimum records |
|---|---|
| Low risk, A0/A1, no customer data (§6.1 "approved model, registry, logging") | `risk_assessment` only |
| Medium (customer-facing RAG) | + `ai_bom`, `production_readiness`, `control_register_entry` for grounding/privacy/eval controls |
| High (state-changing agent) | + `autonomy_declaration`, `approval_record` per consequential action, `control_evidence` for tool authorization, idempotency, tenant isolation |
| Critical | + independent review (`independent_review.required: true`), full forced unsafe release exercise (§10.5, `unsafe_release_exercise`), regulatory rows |
| Any production incident | `incident_record` |

## Record types

All schemas: `assets/schemas/<record_type>.schema.json` (JSON Schema 2020-12). Fictional examples: `assets/examples/<record_type>.example.json` (`record_status: "example"`, rejected until you copy and edit them).

| record_type | Standard | Boundary | Validator enforces (deterministic) | Cannot prove |
|---|---|---|---|---|
| `risk_assessment` | §2.1, §2.4, §2.5, §6.1, §8.1 | B / C | Critical ⇒ independent review; High/Critical multi-tenant ⇒ isolation evidence ref; memory/fine-tuning ⇒ lineage manifest; approved ⇒ approver and completed review | That the tier is right |
| `autonomy_declaration` | §6.2–§6.4 | B / C / D | A2+ or any promotion ⇒ quantitative evidence and all 10 additional criteria met; one level per promotion; zero unauthorized actions and unresolved critical incidents; CI brackets the rate; metric matches level; final ⇒ risk-owner-approved thresholds; A3 ⇒ independent risk, A4 ⇒ independent assurance + executive risk approvals | That the sample is representative or the numbers are real |
| `approval_record` | §4.1(6), §5.3, §7 | A / C | Approval bound to `action_digest`; approve after `expires_at` is stale and invalid; state read before decision; irreversible or warned ⇒ explicit risk acknowledgment; timeout never approves; bulk approval lists every bound action | That the UX showed the fields or the reviewer understood them |
| `control_register_entry` | §1.2, §16.1 | B / C | Tested ⇒ date + evidence; untested ⇒ `not_assessed`; effective ⇒ Pass; Fail/Partial ⇒ remediation; exceptions time-bound | That the owner exists or accepted |
| `control_evidence` | §1.3, §10.5 | A / C | Seeded unsafe scenario ⇒ expects blocked/quarantined/contained; pass ⇔ observed == expected; executed ⇒ command + own exit code; `mocked` recorded | That the test exercised the production control |
| `ai_bom` | §2.5, §9 | A / C | Pinned versions (no `latest`, ranges, wildcards); digests for weights, adapters, images, datasets, prompts, MCP servers, tool packages; managed models ⇒ vendor id + visibility limitations; foundation model + prompt template present; fine-tuning/durable memory ⇒ lineage + deletion tests | That hashes match the deployed artifacts (§9.3: needs independent validation) |
| `production_readiness` | §19 | B / C-D | All 41 items present; done ⇒ evidence; N/A ⇒ justification; owners/risk/provider/versions/review never N/A; READY only with zero `not_done` | That the evidence is genuine; READY is a self-assessment, not sign-off |
| `regulatory_register_row` | §2.13, §15 | D / B | Proposed/guidance/unverified dates never `treated_as_binding`; compliant ⇒ evidence and a determined role; https source | Legal applicability |
| `incident_record` | §13 | B / C | 10 AI categories; contained/resolved ⇒ timestamps in order; resolved ⇒ root cause, corrective actions, preventive test cases; AI-TENANT ⇒ tenant scope; optional `security_severity` must match the S0–S3 ↔ SEV-1–SEV-4 crosswalk; unblocked AI-TENANT or I3 exposure ⇒ S0; runbook fields: resolved ⇒ I1–I11 `incident_types`, ≥ 1 logged lever pull and a §11 `recovery_verification` with no failed check; rung 4–5 ⇒ IC authorization; closed ⇒ every lever restored or left in place with owner, plus a `regression_case` (production_regressions/INC-YYYY-NNN.yaml, two distinct runs, listed in preventive tests; existence checked with `--regressions-root`) or a signed-off monitored detector | That the severity was assessed correctly (crosswalk: `reference/supply-chain-eval-and-release.md` §7.1) |
| `unsafe_release_exercise` | §10.5 | A / C | All 8 scenarios exactly once, one evidence record each; validated **with** its `control_evidence` files: every evidence present, matching scenario, and for `passed` executed, `pass`, blocked/quarantined/contained and not mocked | That the production controls work, or that the control plane may be declared operational (C) |
| `kpi_definition` | §17 | B / C | All 8 definition fields; a zero count of violations/blocks ⇒ independent control test + detection coverage refs | That the instrumentation is complete |

Thresholds marked illustrative (§5.3 latency targets, §6.3 sample sizes and success rates, §10.3 quarterly canary review) are **ADAPT defaults**. The validator never enforces those numbers; it enforces that a risk owner approved whatever numbers are used.

## Validate records

```bash
V=.claude/skills/ai-governance/scripts/validate_governance_record.py
python3 "$V" --selftest                      # 84 checks (examples, assets/fixtures/negative-cases.json, s10.5 exercise batch), exit 0 = PASS
python3 "$V" governance/<system-id>/*.json   # exit 0 all valid, 1 any invalid, 2 usage/IO/JSON/schema error
                                             # an unsafe_release_exercise is checked against the control_evidence files in the same run
python3 "$V" --json governance/<system-id>/*.json > governance-report.json
python3 "$V" --list-types
```

Stdlib only (Python ≥ 3.9; selftest verified on 3.9.6 and 3.14). The schema engine implements a declared JSON Schema 2020-12 keyword subset and **fails closed** on any other keyword. Schemas are also checked against the official 2020-12 metaschema with `jsonschema` 4.26.0 during toolkit maintenance. Suggested location in a consuming project: `governance/<system-id>/<record_type>[-<id>].json`, committed and reviewed like code.

## Workflow

1. **Classify** (§6.1, §2.4): write `risk_assessment`. Run `threat-modeling` for the threat model it references (AI threats: `threat-modeling/SKILL.md` AI section). Decide proportionality from the table above.
2. **Declare autonomy** (§6.2–§6.4): `autonomy_declaration` for A2+ or any promotion. Evidence comes from eval runs (`eval-guide`) and production telemetry, never from the model's self-report. Details: `reference/risk-autonomy-oversight.md`.
3. **Map controls** (§1.2, §16): one `control_register_entry` per applicable control. Start from the 12 illustrative critical controls (§16.2) in `reference/operating-model-and-registers.md`; assign real owners (boundary C) before calling any control active.
4. **Prove controls** (§10.5, §1.3): run the forced unsafe release exercise and the control tests; record each as `control_evidence` with the tool's own exit code and a negative control, and the exercise as one `unsafe_release_exercise` validated together with its 8 evidence records. Scenario-to-test mapping: `reference/supply-chain-eval-and-release.md`.
5. **Inventory the supply chain** (§9): `ai_bom`; for fine-tuning or durable memory it is a release gate.
6. **Runtime approvals** (§7): the application writes one `approval_record` per consequential decision (the schema is the contract; storage is the application's audit store).
7. **Readiness** (§19): `production_readiness`; NOT_READY until every item has evidence or a justified N/A.
8. **Operate**: `incident_record` per AI incident (`ai-incident-response`), `kpi_definition` per scorecard KPI (§17), `regulatory_register_row` per obligation (owned by Legal, boundary D).
9. **Validate** all records with the script; wire it into CI (exit code gates the job).

## Runtime controls this skill does not implement

Runtime policy enforcement (§5), the reference architecture (§4), tenant isolation, cross-agent trust and memory security (§8), transaction safety (§11) and provider failover (§12) are engineering controls. Their governance requirements and the toolkit files that implement them: `reference/runtime-policy-and-isolation.md`. Implementation lives in `ai-playbook`, `agentic-ai-dev/reference/tool-execution-safety.md`, `rag-security-reviewer`, `mcp-builder`.

## References

| File | Covers | Load when |
|---|---|---|
| `reference/boundary-map.md` | Every governance section → GOV IDs → boundary A–D → toolkit artifact → status | Auditing coverage, answering "does the toolkit do X?" |
| `reference/operating-model-and-registers.md` | §1–§3, §14–§18, §20: ownership, 15 pillars with required elements, shadow AI, golden paths, regulatory register (verified dates), control register, scorecard KPIs, roadmap, principles, **adoption checklist (organisation-owned)** | Setting up a governance programme or registers; listing what only the organisation can decide |
| `reference/risk-autonomy-oversight.md` | §6, §7: risk tiers, A0–A4, promotion gates, statistics, demotion, approval UX and operations | Risk assessment, autonomy promotion, approval design |
| `reference/runtime-policy-and-isolation.md` | §4, §5, §8, §11, §12: reference architecture, invariants, hard stops, PDP/PEP, policy latency, tenancy, agent trust, memory, transactions, provider exit | Designing or reviewing runtime enforcement |
| `reference/supply-chain-eval-and-release.md` | §9, §10, §13, §19: AI BOM, integrity, release blocking, eval platform, canaries, forced unsafe release, incidents, readiness | Release gates, AI BOM, governance exercises |

## Verify

```
✅ python3 .claude/skills/ai-governance/scripts/validate_governance_record.py --selftest  → exit 0
✅ Every governance record in the project validates (exit 0) and none has record_status "example"
✅ Every control marked effective has control_evidence with an executed command, own exit code and a negative control
✅ Report states boundary (A/B/C/D) per requirement and never claims organisational adoption or approval
```

## What this skill does NOT do

- It does not approve anything, appoint owners or adopt the standard for an organisation.
- It does not determine legal applicability; regulatory rows are drafts until Legal verifies them (boundary D).
- It does not replace runtime enforcement: a record describing a gateway is not a gateway.
- It does not measure model quality; that is `eval-guide`.
