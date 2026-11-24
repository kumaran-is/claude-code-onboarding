# Governance Boundary Map (GOV sections → toolkit)

Where each governance section (§n, requirement ids GOV-<section>-<nn>, one id per table row, bullet, checklist item or normative paragraph, in section order) lives in this toolkit. The Primary toolkit file column is the canonical skill-local home of that section's requirements; the per-requirement register is `docs/audits/ai-engineering-standards-coverage.tsv`. Status counts are a snapshot taken 2026-11-23; rerun the checks before relying on them.

**Boundary:** A toolkit implements and tests it · B toolkit provides a template/checklist · C needs enterprise infrastructure or a named organisational owner · D needs legal, regulatory or executive approval.

**Status:** implemented and tested = toolkit file implements it and a test was executed with its own exit code (for governance records: `validate_governance_record.py --selftest` plus negative fixtures) · implemented not tested · partially covered · documented only · missing · not applicable (informative) · requires enterprise adoption (the toolkit can only template it). "Implemented and tested" is used only where the boundary includes A (the toolkit itself enforces and tests it); a tested template or validator rule whose control needs an organisation (boundary B/C/D only) counts as partially covered. It never means an organisation operates the control.

| Section | GOV ids (count) | Boundary | Primary toolkit file | Status mix | Gap / note |
|---|---|---|---|---|---|
| PRE | GOV-PRE-01 … GOV-PRE-10 (10) | C | `ai-governance/reference/operating-model-and-registers.md` §10 (framework ownership and cadence) | 6 not applicable, 4 requires enterprise adoption | Review cadences (quarterly framework, monthly regulatory register and critical controls, annual assurance) are organisation-owned ADAPT defaults |
| ES | GOV-ES-01 … GOV-ES-09 (9) | - | `ai-governance/SKILL.md` | 9 not applicable | INFORMATIVE scope statement |
| GP | GOV-GP-01 … GOV-GP-16 (16) | A/B/C | `ai-governance/reference/operating-model-and-registers.md` §9 | 14 partially covered, 2 requires enterprise adoption | Principle → enforcement table; organisational principles (discovery, ownership) are C |
| 1.1 | GOV-1.1-01 … GOV-1.1-11 (11) | C/D | `ai-governance/reference/operating-model-and-registers.md` | 11 requires enterprise adoption | Organisational functions cannot be created by a toolkit |
| 1.2 | GOV-1.2-01 … GOV-1.2-15 (15) | B/C | `ai-governance/assets/schemas/control_register_entry.schema.json` | 14 partially covered, 1 implemented and tested | Field presence enforced; real owners are C |
| 1.3 | GOV-1.3-01 … GOV-1.3-20 (20) | B/C | `ai-governance/reference/operating-model-and-registers.md` | 20 documented only | Repo convention only (toolkit references vs governance/**/*.json) |
| 2.1 | GOV-2.1-01 … GOV-2.1-11 (11) | C | `ai-governance/reference/operating-model-and-registers.md` | 9 requires enterprise adoption, 2 partially covered | Portfolio/strategy are organisational |
| 2.2 | GOV-2.2-01 … GOV-2.2-09 (9) | C/D | `ai-governance/reference/operating-model-and-registers.md` | 9 requires enterprise adoption | Council, RACI, training are organisational |
| 2.3 | GOV-2.3-01 … GOV-2.3-10 (10) | B/C/D | `ai-governance/reference/operating-model-and-registers.md` | 10 partially covered | Fairness/safety evals exist in eval-guide; prohibited-use list, appeals are org/legal |
| 2.4 | GOV-2.4-01 … GOV-2.4-10 (10) | B/C | `ai-governance/assets/schemas/risk_assessment.schema.json` | 8 partially covered, 1 requires enterprise adoption, 1 implemented and tested | Record checks only; tier decision and register are C |
| 2.5 | GOV-2.5-01 … GOV-2.5-16 (16) | A/B/D | `ai-governance/reference/operating-model-and-registers.md` | 10 requires enterprise adoption, 5 partially covered, 1 implemented and tested | Lineage/deletion enforced in records; consent, residency, licensing are legal/org |
| 2.6 | GOV-2.6-01 … GOV-2.6-19 (19) | A | `ai-governance/reference/runtime-policy-and-isolation.md` | 19 partially covered | Implementation and tests owned by guardrail/MCP skills (GR-* rows) |
| 2.7 | GOV-2.7-01 … GOV-2.7-12 (12) | A/B/C | `ai-governance/reference/operating-model-and-registers.md` | 12 partially covered | Pinning enforced in ai_bom; model catalog/registry are platform |
| 2.8 | GOV-2.8-01 … GOV-2.8-16 (16) | A/B | `ai-governance/reference/operating-model-and-registers.md` | 16 partially covered | Records enforce autonomy/approval; runtime enforcement in agentic skills |
| 2.9 | GOV-2.9-01 … GOV-2.9-14 (14) | A/B | `ai-governance/reference/operating-model-and-registers.md` | 14 partially covered | Gateway, PDP, IaC are platform (C) |
| 2.10 | GOV-2.10-01 … GOV-2.10-16 (16) | A/B | `ai-governance/reference/operating-model-and-registers.md` | 16 partially covered | Owned by eval skills (EVAL-* rows) |
| 2.11 | GOV-2.11-01 … GOV-2.11-14 (14) | A/B/C | `ai-governance/reference/operating-model-and-registers.md` | 14 partially covered | Audit retention/access controls are C |
| 2.12 | GOV-2.12-01 … GOV-2.12-14 (14) | B/C | `ai-governance/reference/operating-model-and-registers.md` | 14 partially covered | Budgets and chargeback are organisational |
| 2.13 | GOV-2.13-01 … GOV-2.13-13 (13) | D | `ai-governance/reference/operating-model-and-registers.md` | 13 requires enterprise adoption | Legal applicability is D; toolkit gives register template |
| 2.14 | GOV-2.14-01 … GOV-2.14-12 (12) | B/C/D | `ai-governance/reference/operating-model-and-registers.md` | 12 requires enterprise adoption | Due diligence, DPAs, exit contracts are org/legal |
| 2.15 | GOV-2.15-01 … GOV-2.15-14 (14) | A/B/C | `ai-governance/reference/operating-model-and-registers.md` | 14 partially covered | Incident/rollback skills exist; DR and periodic reliability tests are C |
| 3.1 | GOV-3.1-01 … GOV-3.1-08 (8) | C | `ai-governance/reference/operating-model-and-registers.md` | 8 requires enterprise adoption | Discovery needs network/identity infra |
| 3.2 | GOV-3.2-01 … GOV-3.2-11 (11) | C | `ai-governance/reference/operating-model-and-registers.md` | 11 requires enterprise adoption | All discovery controls are infrastructure; repo grep finds code-level bypass only |
| 3.3 | GOV-3.3-01 … GOV-3.3-08 (8) | B/C | `ai-governance/assets/schemas/kpi_definition.schema.json` | 8 partially covered | KPI template only; data source is C |
| 3.4 | GOV-3.4-01 … GOV-3.4-12 (12) | B | `ai-governance/reference/operating-model-and-registers.md` | 12 partially covered | Templates/scaffolds exist; pre-approved configs and fast-track approvals are C |
| 4 | GOV-4-01 (1) | - | `ai-governance/reference/runtime-policy-and-isolation.md` §9 | 1 not applicable | Reference architecture as boundary hops; invariants are 4.1 |
| 4.1 | GOV-4.1-01 … GOV-4.1-10 (10) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 7 partially covered, 2 requires enterprise adoption, 1 implemented and tested | App-level patterns exist; enterprise gateways are C |
| 5.1 | GOV-5.1-01 … GOV-5.1-17 (17) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 17 partially covered | App-level hard-stop tests in guardrail/MCP skills; gateway-level stops are C |
| 5.2 | GOV-5.2-01 … GOV-5.2-13 (13) | C | `ai-governance/reference/runtime-policy-and-isolation.md` | 13 requires enterprise adoption | Toolkit ships no PDP |
| 5.3 | GOV-5.3-01 … GOV-5.3-15 (15) | C | `ai-governance/reference/runtime-policy-and-isolation.md` | 15 documented only | No PDP to measure; app fail-closed test is A |
| 6.1 | GOV-6.1-01 … GOV-6.1-07 (7) | B/C | `ai-governance/assets/schemas/risk_assessment.schema.json` | 6 partially covered, 1 implemented and tested | Tier choice is a human decision |
| 6.2 | GOV-6.2-01 … GOV-6.2-05 (5) | B | `ai-governance/assets/schemas/autonomy_declaration.schema.json` | 5 partially covered | - |
| 6.3 | GOV-6.3-01 … GOV-6.3-19 (19) | A/C/D | `ai-governance/scripts/validate_governance_record.py` | 15 implemented and tested, 4 partially covered | Record consistency enforced; numbers not enforced (ADAPT); approvals are C/D |
| 6.4 | GOV-6.4-01 … GOV-6.4-10 (10) | B/C | `ai-governance/assets/schemas/autonomy_declaration.schema.json` | 10 implemented not tested | Template field; automatic demotion is a runtime control (C) |
| 7 | GOV-7-01 (1) | A/C | `ai-governance/reference/risk-autonomy-oversight.md` | 1 partially covered | Record contract enforced; UX quality is C |
| 7.1 | GOV-7.1-01 … GOV-7.1-19 (19) | A/C | `ai-governance/assets/schemas/approval_record.schema.json` | 19 implemented and tested | Schema requires every display field; actual UI rendering untested |
| 7.2 | GOV-7.2-01 … GOV-7.2-09 (9) | A/C | `ai-governance/reference/risk-autonomy-oversight.md` | 3 requires enterprise adoption, 2 documented only, 2 partially covered, 2 implemented and tested | Reviewer competency, sampling, anomaly detection are C |
| 7.3 | GOV-7.3-01 … GOV-7.3-12 (12) | B/C | `ai-governance/reference/risk-autonomy-oversight.md` | 9 partially covered, 3 implemented and tested | Metrics need approval telemetry (C) |
| 8.1 | GOV-8.1-01 … GOV-8.1-11 (11) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 10 partially covered, 1 implemented and tested | Validator requires isolation evidence ref for High/Critical multi-tenant; the tests themselves live in RAG/agent skills |
| 8.2 | GOV-8.2-01 … GOV-8.2-10 (10) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 10 partially covered | No dedicated agent-to-agent identity/delegation test template; tool-level in MCP skills |
| 8.3 | GOV-8.3-01 … GOV-8.3-10 (10) | B | `threat-modeling/SKILL.md` | 10 partially covered | Threat catalogue only; tests live in agentic memory guidance (guardrail rows) |
| 8.4 | GOV-8.4-01 … GOV-8.4-09 (9) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 7 partially covered, 1 requires enterprise adoption, 1 implemented and tested | Validator requires deletion-test refs + source-to-derived map for durable memory; backups are C/D |
| 9.1 | GOV-9.1-01 … GOV-9.1-16 (16) | A/C | `ai-governance/assets/schemas/ai_bom.schema.json` | 16 implemented and tested | Completeness/form only |
| 9.2 | GOV-9.2-01 … GOV-9.2-09 (9) | A/C | `ai-governance/scripts/validate_governance_record.py` | 7 implemented and tested, 1 requires enterprise adoption, 1 partially covered | Digests not recomputed against deployed artifacts (C/project CI) |
| 9.3 | GOV-9.3-01 … GOV-9.3-06 (6) | A/C | `ai-governance/scripts/validate_governance_record.py` | 5 implemented and tested, 1 partially covered | Independent validation of manifest content is project CI/C |
| 10.1 | GOV-10.1-01 … GOV-10.1-11 (11) | A/C | `ai-governance/reference/supply-chain-eval-and-release.md` | 11 partially covered | Per-project eval tooling exists; shared enterprise platform is C |
| 10.2 | GOV-10.2-01 … GOV-10.2-13 (13) | C | `ai-governance/reference/supply-chain-eval-and-release.md` | 13 requires enterprise adoption | Funding is organisational |
| 10.3 | GOV-10.3-01 … GOV-10.3-09 (9) | B/C | `ai-governance/reference/supply-chain-eval-and-release.md` | 9 partially covered | Dataset mechanics owned by eval golden-dataset rows; access restriction is C |
| 10.4 | GOV-10.4-01 … GOV-10.4-12 (12) | A/C | `ai-governance/reference/supply-chain-eval-and-release.md` | 12 partially covered | Gate implementation in eval CI tiers |
| 10.5 | GOV-10.5-01 … GOV-10.5-11 (11) | A/C | `ai-governance/assets/schemas/control_evidence.schema.json`, `unsafe_release_exercise.schema.json` | 8 partially covered, 3 implemented and tested | Scenario recording, acceptance rule and exercise completeness (all 8 scenarios, each executed, passed, unmocked) tested; executing the 8 scenarios against production controls is per project |
| 11.1 | GOV-11.1-01 … GOV-11.1-10 (10) | A | `ai-governance/reference/runtime-policy-and-isolation.md` | 10 partially covered | Implementation/tests in tool-execution-safety (GR rows) |
| 11.2 | GOV-11.2-01 (1) | - | `ai-governance/reference/runtime-policy-and-isolation.md` | 1 not applicable | INFORMATIVE flow |
| 11.3 | GOV-11.3-01 … GOV-11.3-05 (5) | A | `ai-governance/assets/schemas/approval_record.schema.json` | 5 implemented and tested | Classification field enforced; reconciliation is runtime (GR rows) |
| 12.1 | GOV-12.1-01 … GOV-12.1-10 (10) | A/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 10 partially covered | Patterns in llm routing/resilience refs; approved-provider allow-list is C |
| 12.2 | GOV-12.2-01 … GOV-12.2-14 (14) | B/C | `ai-governance/reference/runtime-policy-and-isolation.md` | 14 documented only | No provider-migration test harness template |
| 12.3 | GOV-12.3-01 … GOV-12.3-10 (10) | C/D | `ai-governance/reference/runtime-policy-and-isolation.md` | 10 requires enterprise adoption | Contracts/export rights are legal |
| 13 | GOV-13-01 (1) | B | `ai-incident-response/SKILL.md` | 1 partially covered | - |
| 13.1 | GOV-13.1-01 … GOV-13.1-10 (10) | B | `ai-governance/assets/schemas/incident_record.schema.json` | 10 partially covered | - |
| 13.2 | GOV-13.2-01 … GOV-13.2-12 (12) | B/C | `ai-governance/assets/schemas/incident_record.schema.json` | 12 partially covered | Factor-to-level policy is org (C); S0–S3 ↔ SEV-1–SEV-4 floor crosswalk in `supply-chain-eval-and-release.md` §7.1 (consistency and unblocked AI-TENANT ⇒ S0 validator-enforced) |
| 13.3 | GOV-13.3-01 … GOV-13.3-14 (14) | B | `ai-governance/assets/schemas/incident_record.schema.json` | 14 partially covered | - |
| 14.1 | GOV-14.1-01 … GOV-14.1-10 (10) | B | `ai-governance/reference/operating-model-and-registers.md` | 8 implemented not tested, 1 partially covered, 1 documented only | Scaffolds exist; not executed for this map; multi-tenant starter is a checklist (`ai-playbook/reference/multi-tenant-ai-starter.md`), not a scaffold |
| 14.2 | GOV-14.2-01 … GOV-14.2-10 (10) | A/C | `ai-governance/reference/operating-model-and-registers.md` | 6 partially covered, 3 requires enterprise adoption, 1 implemented and tested | In-repo automation: validator; live IAM/allow-list/region checks are C |
| 14.3 | GOV-14.3-01 … GOV-14.3-10 (10) | B/C | `ai-governance/assets/schemas/kpi_definition.schema.json` | 10 partially covered | KPI template only |
| 15.1 | GOV-15.1-01 … GOV-15.1-15 (15) | B/D | `ai-governance/assets/schemas/regulatory_register_row.schema.json` | 15 partially covered | Applicability is D |
| 15.2 | GOV-15.2-01 … GOV-15.2-08 (8) | D | `ai-governance/reference/operating-model-and-registers.md` | 7 partially covered, 1 implemented and tested | Legal must revalidate; Art.50(2) date secondary-source only |
| 15.3 | GOV-15.3-01 … GOV-15.3-13 (13) | B/C/D | `threat-modeling/SKILL.md` | 13 partially covered | Alignment/certification is C/D |
| 16 | GOV-16-01 (1) | B | `ai-governance/reference/operating-model-and-registers.md` | 1 partially covered | - |
| 16.1 | GOV-16.1-01 … GOV-16.1-14 (14) | B/C | `ai-governance/assets/schemas/control_register_entry.schema.json` | 14 partially covered | Owners/evidence repo are C |
| 16.2 | GOV-16.2-01 … GOV-16.2-13 (13) | A/C | `ai-governance/reference/operating-model-and-registers.md` | 11 partially covered, 2 requires enterprise adoption | Owners/implementations must be assigned by enterprise |
| 17 | GOV-17-01 … GOV-17-31 (31) | B/C | `ai-governance/assets/schemas/kpi_definition.schema.json` | 30 partially covered, 1 implemented and tested | Instrumentation is C |
| 18 | GOV-18.P0-01 … GOV-18.P4-08 (37) | C/D | `ai-governance/reference/operating-model-and-registers.md` §8 | 37 requires enterprise adoption | Phase activities and exit gates; exit decisions are organisational |
| 19 | GOV-19.STRATE-01 … GOV-19.GOVERN-06 (41) | B/C/D | `ai-governance/assets/schemas/production_readiness.schema.json` | 41 partially covered | Checklist + evidence/N-A/verdict rules tested; satisfying each item is per project, sign-off is C/D |
| 20 | GOV-20-01 … GOV-20-20 (20) | A/B/C | `ai-governance/reference/operating-model-and-registers.md` §9 | 20 partially covered | Each principle mapped to its enforcing record or reference |
| CLOSE | GOV-CLOSE-01 … GOV-CLOSE-11 (11) | - | `ai-governance/SKILL.md` | 11 not applicable | INFORMATIVE |

## Known gaps (toolkit side)

- **GOV-14.1-06 multi-tenant AI starter: checklist only.** `ai-playbook/reference/multi-tenant-ai-starter.md` links each §8.1 control to its canonical file; there is no runnable multi-tenant scaffold, and publishing it as the organisation's supported starter is an organisational act (C).
- **§8.2 cross-agent trust:** no dedicated agent-to-agent identity and delegation-scope test template; tool-boundary authorization is covered in `mcp-builder` and `tool-execution-safety.md`.
- **§12.2 provider migration:** no harness that runs the same golden/canary suites against an alternate provider and diffs tool-call schemas; documented only.
- **§9.3 independent validation:** the validator checks AI BOM form; recomputing digests from deployed artifacts must be wired in each project's CI.
- **§15.2:** the Art. 50(2) pre-existing-system date (2 Dec 2026) is confirmed only from a secondary consolidated text; EUR-Lex was not reachable from the verification environment.

## Never claimed

No row in this map means an organisation adopted the standard, appointed an owner, approved a risk or operates a control. Boundary C and D rows stay open until the organisation records its own decisions and evidence.
