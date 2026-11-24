# Operating Model, Registers, Scorecard and Roadmap (governance §1–§3, §14–§18, §20)

Most of this is organisational (boundary C/D). The toolkit contributes templates, validators and golden paths; it cannot create a council, appoint owners or adopt the standard. Never describe a project as "governed" or "compliant" because these files exist.

## 1. Accountability and control ownership (§1)

Functions (§1.1): Executive AI Governance Council (strategy, risk appetite, policy approval, material exceptions) [D]; AI Center of Excellence (standards, platforms, patterns) [C]; Principal AI Architect [C]; AI Platform Engineering (LLM gateway, model catalog, policy enforcement, evaluation infrastructure) [C]; Business/Product Owner [C]; Security Engineering [C]; Privacy & Legal [D]; Responsible AI / Model Risk [C]; SRE [C]; FinOps [C]; Internal Audit [C].

Every control (§1.2) needs: unique control id, description and risk, named accountable owner, implementation owner, enforcement location, test methodology, evidence repository, test frequency, last successful test date, effectiveness status, exception and remediation records, next review date. These are the required fields of `control_register_entry`; the validator also rejects placeholder owners (`TBD`, `unassigned`, `<name>`).

**Activation rule (§1.2):** the framework cannot be declared operational until every mandatory control has an accountable owner, a test method, an evidence location and an initial effectiveness assessment. A policy document alone is not evidence. The toolkit can show which register entries are missing those fields [A]; declaring operation is [C/D].

Two systems of record (§1.3): the **framework** (policies, standards, risk classes, decision rights, required outcomes, principles, review and exception processes: stable, owned by governance) and the **living control effectiveness register** (owners, control ids, implementations, test results, last-tested dates, evidence links, findings, exceptions, remediation SLAs, trends: changes continuously). In a repository: the framework is the organisation's adopted policy set, which this skill expresses as references, schemas and checklists; `governance/**/*.json` holds register entries and evidence, validated in CI. Keep them apart: editing a register entry never changes policy, and changing policy text is never control evidence.

## 2. The fifteen pillars (§2) → toolkit pointers

| Pillar | Required elements (each is a requirement; [C]/[D] items are organisation-owned, see §10) | Toolkit support | Boundary |
|---|---|---|---|
| 2.1 Strategy and business value | Vision and roadmap [C]; use-case identification and prioritisation [C]; business justification and expected ROI; AI-versus-deterministic architecture decision; investment portfolio [C]; maturity assessments [C]; adoption strategy [C]; productivity and customer-experience measurement; revenue, savings and risk reduction; post-deployment value verification. **Rule: do not introduce AI into a workflow unless it creates measurable value relative to a simpler solution.** | `risk_assessment.use_case` (why AI over deterministic, value metric, baseline); `ai-decision-record` | B / C |
| 2.2 Governance organization | Executive council [D]; AI CoE [C]; charter and RACI [C]; policy and control ownership; approval authority by risk tier [D]; separation of duties (approver ≠ implementer); exception and waiver management (time-bound); AI literacy and developer training [C]; continuous governance improvement [C] | Register templates; council, RACI, training are organisational | C / D |
| 2.3 Responsible AI and ethics | Fairness and bias mitigation; transparency and explainability; human oversight (§7); accountability for AI decisions; accessibility and inclusion; content provenance and disclosures; prohibited use cases [D]; human contestability and appeals [C]; automation-bias prevention (§7.2); independent safety assessments [C] | `eval-guide` fairness/safety dimensions; `accessibility-audit`; prohibited-use list is organisational | B / C / D |
| 2.4 Risk management | Per-system risk assessment; enterprise risk register [C]; Low/Medium/High/Critical tier; data sensitivity and customer impact; agent autonomy risk; likelihood, severity, reversibility; threat model; risk acceptance and mitigation [C/D]; periodic reassessment; independent review for consequential systems | `risk_assessment`, `threat-modeling` | B / C |
| 2.5 Data, privacy and IP | Classification and ownership; PII/PHI protection; consent and lawful processing [D]; minimisation; residency and sovereignty; retention and deletion; lineage and provenance; training-data authorisation [D]; RAG access control; vector and embedding security; synthetic-data provenance and rights; fine-tuning and weight licensing [D]; prompt and output IP [D]; vendor termination and deletion obligations [D]. **MUST: durable memory, embedding storage or fine-tuning ⇒ lineage manifest and demonstrated deletion, retention and data-rights controls before release.** | `ai_bom` lineage + deletion tests; `rag-security-reviewer`; licensing is legal | A / B / D |
| 2.6 Security and agent authorization | LLM application security; prompt injection; sensitive-data disclosure; system-prompt and secrets exposure; model poisoning; AI supply-chain attacks; identity and authentication; authorisation and least privilege; agent tool permissions; MCP gateway security; agent-to-agent trust; memory poisoning; exfiltration; cross-tenant isolation; runtime policy enforcement; adversarial testing; security incident response. **Boundary principle: the model proposes; deterministic services authorise and execute. Prompts, model-generated JSON and probabilistic classifiers are never authorisation boundaries.** | `ai-security-reviewer`, `security-reviewer`, `tool-execution-safety.md`, `mcp-builder` | A |
| 2.7 Model and provider lifecycle | Approved foundation-model catalogue [C]; model selection and risk assessment; registry and model cards; provider region and data terms [D]; version pinning; artifact integrity and provenance; fine-tuning governance; evaluation and regression testing; upgrade and rollback; retirement; provider migration and portability (§12.2); fallback compatibility certification (the fallback passes the same eval gate) | `ai_bom` pinning; `llmops-release-and-rollout.md`; model catalog is platform | A / B / C |
| 2.8 Agentic governance | Agent inventory and identity; autonomous action classification; least agency; tool authorisation; MCP gateway policies; human approval checkpoints; execution budgets; memory access and retention; multi-agent communication boundaries; multi-tenant isolation; task-level evaluation; idempotency and transaction safety; SAGA compensation; recovery and reconciliation; kill switch and human takeover; autonomy promotion and demotion | `autonomy_declaration`, `approval_record`; `agentic-ai-dev`, `google-adk` | A / B |
| 2.9 Architecture and engineering | Approved reference architectures (§4); enterprise LLM gateway [C]; centralised identity and policy control [C]; RAG security and retrieval standards; tool/MCP gateway; prompt and policy versioning; deterministic business services; secure AI SDLC; CI/CD evaluation gates; infrastructure as code; environment isolation; policy-as-code; observability and resilience; developer self-service platform [C] | `ai-playbook`, scaffolds, `architecture-design` | A / B |
| 2.10 Quality and evaluation | Golden, held-out and protected rotating canary datasets (§10.3); retrieval quality; RAG groundedness and faithfulness; answer correctness; hallucination; prompt-injection evaluation; tool-selection accuracy; agent task success; state-change correctness; human evaluation; LLM-as-judge calibration; regression; statistical confidence; release-blocking thresholds (§10.4) | `eval-guide`, `llm-evaluation`, `rag-evaluator`, `adk-eval-guide` | A / B |
| 2.11 Observability and audit | End-to-end tracing; prompt and response metadata; model/provider/version attribution; RAG source provenance; agent execution traces; tool-call auditing; authorisation decisions; human approval evidence; memory read/write events; quality and drift monitoring; cost attribution; privacy-aware logging; audit retention and access controls [C]; incident correlation | `deployment-ci-cd/reference/ai-observability.md` | A / B / C |
| 2.12 FinOps | Budgets [C]; cost by product and department [C] and by model, agent and tenant; token consumption controls; agent execution limits; cost per business transaction and per successful task; evaluation infrastructure cost; model-routing optimisation; caching and batching; cost anomaly detection; vendor and infrastructure cost; ROI. **Principle: tokens, evaluation cost, inference latency and operational recovery are governed architectural cost dimensions** (one `kpi_definition` each, domain FinOps) | `agentic-cost-optimization.md`, `gcp-finops`; budgets are organisational | B / C |
| 2.13 Legal and regulatory | NIST AI RMF and ISO/IEC 42001 alignment; ISO/IEC 23894 guidance; EU AI Act applicability; GDPR and relevant US privacy laws; HIPAA where applicable; industry obligations; AI-generated content transparency; IP; vendor DPAs; audit and recordkeeping; regulatory change tracking; named jurisdictional responsibility (all [D], §10) | `regulatory_register_row` template only | D |
| 2.14 Third-party and vendor | Due diligence; security and privacy reviews; provider data-use restrictions; subprocessor assessments; model and data ownership rights; availability and contractual SLAs; concentration risk; regional restrictions; portability; exit and migration planning (§12); termination and deletion evidence; independent vendor reassessment ([C/D], §10) | `ai_bom` provider/region/licence; due diligence and DPAs are organisational | B / C / D |
| 2.15 Operations, resilience, incidents | Production readiness (§19); SLOs; circuit breakers; rate limiting and load shedding; model fallback; canary deployment; feature flags; kill switches; agent execution recovery; disaster recovery [C]; human takeover; AI-specific severity mapping (§13); postmortems and corrective actions; periodic reliability testing [C] | `ai-incident-response`, `incident_record`, `llmops-release-and-rollout.md` | A / B / C |

## 3. Shadow AI discovery (§3)

Voluntary registration misses developer-owned keys, unapproved SaaS AI features, unregistered integrations, AI calls from scripts, external plugins, direct provider calls and unapproved automation agents. Mandatory discovery controls (§3.2): egress monitoring, CASB/SSE and SaaS discovery, provider allow-lists, DNS/proxy filtering, central API gateway, cloud account and billing inspection, enterprise secrets management, workload identity, inventory reconciliation, automated exception reporting, all applied within employee-privacy and jurisdictional limits. **All boundary C** (network and identity infrastructure).

What a repository can do [A, advisory]: grep for direct provider SDK imports and hard-coded endpoints outside the approved client module, and for provider keys in code (secret scanning). That finds code-level bypass only; it is not discovery coverage and must never be reported as such. Metrics (§3.3, as `kpi_definition` domain "Shadow AI" / "Discovery"): percentage of discovered systems registered, managed traffic attributable to approved systems, unapproved provider usage, gateway bypass attempts, mean/median time to detect, mean time to remediate, coverage and blind spots, developer adoption of approved paths.

Developer-friendly adoption (§3.4): security must offer a practical sanctioned alternative. Provide self-service AI registration (a `risk_assessment` record in the repo), automated preliminary risk classification (validator + reviewers), pre-approved low-risk model configurations [C], ready-to-use RAG templates (`/scaffold-rag-pipeline`), approved MCP server templates (`/scaffold-mcp-server`), standardised authentication libraries and managed AI gateway SDKs [C: the organisation publishes them; the scaffolds wire a single model client], built-in evaluation pipelines (`eval-guide`), automated policy checks (hooks and CI) and fast-track low-risk approvals [C]. Outcome: fewer unauthorised adoptions and less incentive to bypass controls.

## 4. Golden paths and automated governance (§14)

| §14.1 golden path | Toolkit starter |
|---|---|
| Approved chatbot starter | `/scaffold-agentic-ai`, `/scaffold-google-adk`, `ai-chat` |
| Secure RAG starter | `/scaffold-rag-pipeline`, `rag-architect`, `rag-security-reviewer` |
| Tool-enabled agent starter | `/scaffold-agentic-ai` + `tool-execution-safety.md` |
| MCP integration starter | `/scaffold-mcp-server` |
| Multi-tenant AI starter | `ai-playbook/reference/multi-tenant-ai-starter.md` (checklist linking each control to its canonical file; no scaffold) |
| Evaluation pipeline starter | `eval-guide`, `/rag-eval-init` |
| Observability template | `deployment-ci-cd/reference/ai-observability.md` |
| Deployment template | `deployment-ci-cd`, `adk-deploy-guide` |
| Cost-control template | `agentic-cost-optimization.md`, `gcp-finops` |

Automate where practical (§14.2): use-case registration, preliminary risk classification, model allow-list verification, IAM policy checks, provider-region validation, AI BOM verification, evaluation execution, release-gate enforcement, evidence collection, control effectiveness reporting. In-repo automation: AI BOM, readiness and register validation via `validate_governance_record.py` in CI; eval gates via `eval-guide`. IAM, allow-list and region checks against live infrastructure are boundary C. Adoption metrics (§14.3), each a `kpi_definition` (domain "Developer Experience", or "Shadow AI" for the discovery rate): time to register a use case; time to obtain low-risk approval; time to deploy an approved AI application; percentage using standard templates; developer satisfaction; policy exception rate; shadow AI discovery rate; governance-related delivery delays; repeated manual approval steps. **Principle: make the secure path the easiest path for legitimate development.**

## 5. Regulatory register (§15)

Register fields (§15.1) are the required fields of `regulatory_register_row`. Applicability, provider/deployer role and interpretation are **boundary D**: the toolkit never decides them.

EU AI Act reference milestones (§15.2). Verification for this toolkit was done on 2026-11-23; Legal must revalidate before relying on any date.

| Requirement (standard §15.2) | Reference date | Verification status |
|---|---|---|
| AI literacy and certain prohibited practices | 2 Feb 2025 | Confirmed: European Commission AI Act page (application timeline) and Art. 113(a) |
| GPAI-related obligations | 2 Aug 2025 | Confirmed: Commission page; Art. 113(b) |
| General application, most Art. 50 duties | 2 Aug 2026 | Confirmed: Commission page ("became applicable on 2 August 2026"); Art. 113 |
| Pre-existing Art. 50(2) systems | 2 Dec 2026 | Secondary source only (consolidated Art. 111(4) as amended by the AI Omnibus); EUR-Lex not reachable from the verification environment |
| Annex III high-risk (amended timeline) | 2 Dec 2027 | Confirmed: Commission page; consolidated Art. 113(c)(i) |
| Annex I product-related high-risk (amended timeline) | 2 Aug 2028 | Confirmed: Commission page; consolidated Art. 113(c)(ii) |

The Commission page states the AI Omnibus (Regulation (EU) 2026/1744 per secondary sources) entered into force on 27 July 2026. Primary text: `https://eur-lex.europa.eu/eli/reg/2024/1689/oj`; Commission timeline: `https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai`. Keep proposed and enacted law apart: a row with `date_legal_status` other than `enacted` must have `treated_as_binding: false` (validator rule).

Reference frameworks (§15.3): NIST AI RMF (https://www.nist.gov/itl/ai-risk-management-framework), ISO/IEC 42001 (https://www.iso.org/standard/42001), ISO/IEC 23894, OWASP Top 10 for LLM Applications and OWASP Agentic AI security guidance (https://genai.owasp.org/), MITRE ATLAS (https://atlas.mitre.org/), applicable sector and jurisdictional regulations. Toolkit reviewers map findings to OWASP LLM and agentic categories (`ai-security-reviewer`) and threats to MITRE ATLAS (`threat-modeling`); alignment or certification against NIST/ISO is boundary C/D.

## 6. Control effectiveness register (§16)

Record structure (§16.1) = `control_register_entry`. Illustrative critical controls (§16.2), each needing real owners and implementations before activation:

| Control id | Control | Required evidence | Toolkit can produce evidence? |
|---|---|---|---|
| AI-SEC-001 | Approved model gateway enforcement | Gateway bypass test | App-level only (direct SDK call grep); gateway [C] |
| AI-SEC-002 | Tool authorization | Unauthorized tool invocation test | Yes, app/MCP contract tests [A] |
| AI-DATA-001 | Tenant isolation | Cross-tenant retrieval test | Yes [A] |
| AI-MEM-001 | Memory deletion propagation | Deletion verification | Yes for app stores; backups [C] |
| AI-SUP-001 | AI BOM integrity | Artifact verification report | Validator + digest recomputation [A] |
| AI-EVAL-001 | Release evaluation gate | Seeded unsafe release test | Yes, `eval-guide` gate [A] |
| AI-AUTO-001 | Autonomy promotion | Approved quantitative evidence | Record validation [A]; approval [C/D] |
| AI-HUM-001 | Human approval effectiveness | Approval UX and anomaly tests | Binding/expiry tests [A]; anomaly analytics [C] |
| AI-OPS-001 | Agent recovery | Failure-injection exercise | Yes [A] |
| AI-OPS-002 | Model fallback safety | Provider failover simulation | Mocked simulation [A]; live failover [C] |
| AI-POL-001 | Runtime policy correctness | Policy decision tests | App-level fail-closed tests [A]; PDP [C] |
| AI-DISC-001 | Shadow AI discovery | Discovery reconciliation report | No [C] |

## 7. Scorecard (§17)

Domain → primary KPI: Discovery → % of AI workloads registered; Shadow AI → mean time to detect unapproved AI; Risk → % of systems risk-assessed; Ownership → % of controls with named owners; Control Testing → % of required controls tested on schedule; Security → unauthorized action attempts and successful violations; Data Privacy → cross-tenant leakage and deletion compliance; Model Quality → task success and safety-eval pass rate; Evaluations → eval-gate block rate; Canary Hygiene → canary freshness and contamination findings; Agent Autonomy → promotion, demotion and unauthorized action rates; Agent Recovery → successful recovery / safe containment rate; Human Oversight → incorrect approval and approval anomaly rates; Supply Chain → % of artifacts with verified AI BOM; Policy Engine → p95/p99 authorization decision latency; SRE → availability, latency, MTTR, fallback success; FinOps → fully loaded cost per successful task; Vendor → provider concentration and tested exit readiness; Developer Experience → time to approved deployment; Governance → overdue findings and policy exceptions; Business Value → measurable ROI and outcome improvements. Every KPI defines numerator, denominator, measurement window, data source, instrumentation owner, target threshold, escalation threshold, last measurement date (`kpi_definition`, domain enum = the 21 domains). A zero incident or block count is not proof of effectiveness without independent control testing and detection coverage; the validator enforces both references when a violation/block KPI reads 0.

## 8. Roadmap (§18) and principles (§20)

Phases, activities and exit gates [C/D]: **0 Discovery and containment**: discover shadow AI, establish inventory, identify owners, centralise credentials, apply provider and egress controls, create fast-track onboarding; exit = managed AI discovery coverage + a functioning remediation process. **1 Governance control plane**: establish council and RACI, approve risk tiers, implement LLM gateway, implement tool authorisation, establish policy decision services, create the control effectiveness register; exit = mandatory controls have ownership, implementation evidence and test methods. **2 Evaluation and supply chain**: deploy a shared evaluation platform, fund evaluation programmes, protect held-out canaries, establish AI BOM, implement release gates, verify memory deletion controls; exit = seeded unsafe releases blocked and required provenance controls pass. **3 Autonomy and resilience**: implement A0–A4 governance, enforce quantitative promotion gates, engineer human approval, implement stateful agent execution, test SAGA recovery and idempotency, validate tenant isolation, test fallback and incident response; exit = real control evidence supports the approved autonomy level. **4 Scale and continuous assurance**: independent control testing, multi-product governance, provider exit exercises, business ROI tracking, policy optimisation, developer-experience improvements, regulatory reassessment; exit = effectiveness shown by ongoing operational and audit evidence. Each exit gate is an organisational decision; the toolkit's records (`unsafe_release_exercise`, `control_register_entry`, `autonomy_declaration`, `kpi_definition`) are inputs to it.

Principles: §9 below lists the governing statement, the 15 core engineering principles and the 20 final principles with the place each is enforced or recorded; the most toolkit-relevant are 4 (model output and memory untrusted), 5 (authorization outside the model), 6 (separate autonomy from risk), 7 (quantitative evidence for promotion), 10 (auditable, recoverable actions), 17 (living tested evidence) and 18 (adversarial validation of governance).

## 9. Governing principles (GP, §20)

Governing statement: **govern AI by risk; grant autonomy through evidence; enforce policy at trusted system boundaries; measure business outcomes, not just model activity.** Final principle: the model proposes, deterministic services authorize and execute, humans provide meaningful oversight, autonomy is earned through evidence, and governance is continuously tested, measurable and accountable.

| §20 | Principle | Core principle (GP) | Enforced or recorded by |
|---|---|---|---|
| 1 | Discover before governing | GP1 discover every AI system | §3 discovery [C]; code-level bypass grep [A] |
| 2 | Assign ownership before declaring compliance | GP2 explicit business, technical, risk and control ownership | `risk_assessment.owners`, `control_register_entry` owners (placeholders rejected); activation rule §1 |
| 3 | Govern business outcomes, not simply model outputs | GP3 use AI only where it delivers measurable value | `risk_assessment.use_case` value baseline; KPI domain Business Value |
| 4 | Treat model output and memory as untrusted | GP4 model output is untrusted input | `runtime-policy-and-isolation.md` §1 invariant 3, §5, §6 |
| 5 | Enforce authorization outside the model | GP5 deterministic authorization outside the model | `runtime-policy-and-isolation.md` §2 hard stops |
| 6 | Separate agent autonomy from business risk | — | SKILL.md three dimensions; validator rejects a T-tier in a risk slot |
| 7 | Require quantitative evidence for autonomy promotion | GP7 measurable evidence before more autonomy | `autonomy_declaration` (validator) |
| 8 | Engineer human oversight instead of assuming it works | GP8 meaningful, auditable oversight | `approval_record`; `risk-autonomy-oversight.md` §5–§7 |
| 9 | Protect multi-tenant and cross-product boundaries | — | `runtime-policy-and-isolation.md` §4; control AI-DATA-001 |
| 10 | Make every consequential action auditable and recoverable | GP9 idempotent, recoverable state-changing agents | `runtime-policy-and-isolation.md` §7; control AI-OPS-001 |
| 11 | Verify model and data supply-chain provenance | GP10 govern data, memory, models and supply-chain artifacts | `ai_bom` (validator); control AI-SUP-001 |
| 12 | Fund evaluations and protect independent canaries | — | `supply-chain-eval-and-release.md` §3–§4; §10 below |
| 13 | Test provider exit and operational resilience | — | `runtime-policy-and-isolation.md` §8; control AI-OPS-002 |
| 14 | Measure policy enforcement latency and reliability | GP12 quality, latency, cost and policy enforcement are architecture dimensions | KPI domain Policy Engine; `runtime-policy-and-isolation.md` §3 |
| 15 | Classify and investigate AI-specific incidents | — | `incident_record`; `ai-incident-response` |
| 16 | Make secure development faster and easier than workarounds | GP14 low-friction secure development paths | §3 developer-friendly adoption, §4 golden paths |
| 17 | Maintain living, tested control evidence | GP15 validate controls through independent testing | `control_evidence`, `control_register_entry` (effective ⇒ Pass) |
| 18 | Continuously validate governance through adversarial exercises | GP15 | `unsafe_release_exercise` (all 8 scenarios) |
| 19 | Measure full lifecycle cost and real business value | GP3, GP12 | KPI domains FinOps, Business Value |
| 20 | Govern the governance framework itself | — | §10 cadences and change log [C] |

GP6 (least privilege and least agency): `agentic-ai-dev/reference/tool-execution-safety.md`, `mcp-builder`. GP11 (continuously evaluate, monitor and reassess): `eval-guide` CI tiers, `risk_assessment.next_reassessment`. GP13 (regulatory compliance by actual jurisdictional applicability): `regulatory_register_row` [D].

## 10. Adoption checklist (organisation-owned)

Nothing here is automated enforcement. The toolkit can template and validate records; only the organisation can tick these boxes, each with a dated record of its own decision (minutes, signed register entry, contract reference). Until the approving authority records adoption, the framework's status is "pending formal adoption", and a project may say only that its records validate. Cadences below are ADAPT defaults: an organisation may shorten them, never lengthen them without a recorded risk acceptance.

**Framework ownership and cadence (front matter, §20.20)**
- [ ] Document owner (governance lead), technical custodian (principal AI platform architect) and approving authority (executive AI governance council) named
- [ ] Framework review: quarterly and event-driven, with a change log
- [ ] Regulatory register review: monthly (§15.1 `next_review`)
- [ ] Control effectiveness review: monthly for critical controls (`control_register_entry.test_frequency`, `next_review`)
- [ ] Independent assurance: at least annually, more often for higher risk (Internal Audit)

**Accountability (§1.1, §1.2, §2.2)**
- [ ] Each function named: executive council (strategy, risk appetite, policy approval, material exceptions); AI CoE (standards, common platforms, approved patterns, enablement); principal AI architect; AI platform engineering (LLM gateway, model catalogue, policy enforcement, eval infrastructure); business/product owner (value, use-case accountability, acceptance criteria); security engineering (threat modelling, IAM, DLP, agent security, incident controls); privacy and legal (data rights, regulatory applicability, contracts); responsible AI / model risk (fairness, explainability, safety, validation); SRE (SLOs, reliability, observability, incidents); FinOps (budgets, token economics); internal audit (independent assurance, remediation verification)
- [ ] Charter and RACI approved; approval authority per risk tier recorded, including independent risk approval for A3 and independent assurance plus executive risk approval for A4 (§6.3)
- [ ] Separation of duties: approvers are not the implementers of the control or change they approve
- [ ] Exception and waiver process: every exception has an approver and an expiry (`exceptions[].expires`)
- [ ] AI literacy and developer training programme (EU AI Act literacy duty applies from 2 Feb 2025, §5)
- [ ] Activation rule met: every mandatory control has an accountable owner, test method, evidence location and initial effectiveness assessment before the framework is declared operational
- [ ] Continuous improvement: findings from incidents, exercises and audits feed framework changes

**Strategy, responsible AI and data rights (§2.1, §2.3, §2.5)**
- [ ] AI vision, roadmap, use-case prioritisation, investment portfolio, maturity assessment and adoption strategy owned by named people
- [ ] Prohibited AI use-case list published; contestability and appeals route for people affected by AI decisions; independent safety assessments scheduled for consequential systems
- [ ] Consent and lawful basis, training-data authorisation, fine-tuning and weight licensing, prompt/output IP and vendor termination/deletion obligations confirmed by Legal/Privacy per system

**Regulatory (§2.13, §15)**
- [ ] Named owner per jurisdiction; NIST AI RMF / ISO/IEC 42001 alignment decision; ISO/IEC 23894 use; EU AI Act, GDPR and US privacy, HIPAA and sector applicability decided by Legal
- [ ] Every `regulatory_register_row` verified by Legal; dates revalidated against enacted law; proposals never treated as binding
- [ ] Regulatory change tracking with a trigger per row (`change_trigger`)

**Vendors and provider exit (§2.14, §12.3)**
- [ ] Per provider: due diligence; security and privacy review; data-use restrictions; subprocessor assessment; model and data ownership rights; availability SLAs; concentration risk; regional restrictions; portability terms; exit and migration plan; termination and deletion evidence; periodic independent reassessment
- [ ] Contractual export rights and a business continuity plan; alternate provider identified and its exit exercise scheduled (§18 phase 4)

**Discovery infrastructure (§3.2)**
- [ ] Egress monitoring; CASB/SSE and SaaS discovery; approved provider allow-lists; DNS/proxy filtering; central API gateway; cloud account and billing inspection; enterprise secrets management; workload identity; inventory reconciliation; automated exception reporting
- [ ] Monitoring reviewed against employee-privacy, jurisdictional and organisational requirements before it runs

**Evaluation funding and protection (§10.1–§10.3)**
- [ ] Budget lines: dataset creation and labelling, domain-expert review, human evaluators, judge inference, adversarial testing, canary refresh, eval infrastructure, statistical analysis, regression testing, independent assurance
- [ ] Evaluation cost tracked by use case and risk tier; essential high-risk coverage never cut merely to reduce token spend
- [ ] Shared evaluation platform with results and evidence retention; canary store with restricted access and independent access review

**Platform controls (§4, §5.2, §5.3, §16.2)**
- [ ] Enterprise LLM gateway, retrieval authorisation boundary, tool/MCP gateway and policy decision service operated by named owners, with versioned and auditable policies
- [ ] Policy decision SLOs, error budgets and emergency revocation propagation agreed
- [ ] Owner and implementation assigned for each of the 12 critical controls (§6) before any is reported active

**Release sign-off (§19)**
- [ ] Named owners sign the `production_readiness` record (a READY verdict alone is a self-assessment); exceptions are time-bound; next review scheduled
