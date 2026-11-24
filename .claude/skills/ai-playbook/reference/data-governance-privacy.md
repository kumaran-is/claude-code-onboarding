# AI Data Governance and Privacy (DGP)

Engineering controls for data that an AI capability reads, sends, generates or stores: prompts, retrieved context, tool inputs and outputs, completions, traces, caches, embeddings, agent memory, user feedback, fine-tuning sets and eval datasets, in every environment including developer machines and notebooks. Expands guardrails G9, G15 and G20. Requirement IDs `DGP-<section>-<n>` in the coverage register map onto the numbered sections below.

**Not legal advice.** Lawfulness (GDPR, CCPA/CPRA, HIPAA, sector rules, the EU AI Act) is confirmed by Legal and the privacy officer per jurisdiction and use case. Precedence: law and contract > enterprise privacy / classification policy > this reference > team conventions. **must / must not** = mandatory; **should** = default, deviation needs a recorded reason; **may** = optional. `ADAPT` values are defaults the organisation ratifies (§20).

Status legend used below: **[CODE]** enforced by toolkit code with a test; **[GUIDE]** guidance only, no toolkit code (the service implements it); **[ORG]** organisation-owned, never automated by the toolkit.

Related: guardrail map and erasure inventory in [`engineering-guardrails.md`](engineering-guardrails.md#data-governance-and-privacy-expands-g9-g15-g20) (not repeated here); tenant isolation in [`multi-tenant-ai-starter.md`](multi-tenant-ai-starter.md).

## 2. Principles D1–D7

| # | Principle | Consequence |
|---|---|---|
| D1 | **Read permission is not send permission.** | Authorization to read data internally does not authorize sending it to a model provider (G9). |
| D2 | Minimum necessary, every hop. | Each stage receives only the fields its task needs; nothing travels "just in case". |
| D3 | Purpose travels with the data. | Data collected for purpose A is not used for purpose B (incl. training) without a recorded basis. |
| D4 | Every copy is a copy. | A prompt log, trace, cache entry, embedding or memory item holding personal data is personal data, with retention and deletion duties. |
| D5 | Deletion must be provable. | Lineage is a prerequisite: without it you cannot show where a subject's data went or that it was deleted. |
| D6 | Real data stays out of tests. | Golden, eval and red-team datasets are synthetic or sanitized by default. |
| D7 | Governance is code. | Classification, purpose and residency are machine-readable tags enforced deterministically at the AI gateway, never by a PDF and **never by an LLM judge**. |

## 3. Data classification tiers (ADAPT)

| Tier | Definition | AI-relevant examples |
|---|---|---|
| `public` | approved for public release | published docs, marketing copy, public catalogue |
| `internal` | non-public, low harm if disclosed | internal how-tos, non-sensitive runbooks, aggregated metrics |
| `confidential` | business-sensitive, or personal data of ordinary sensitivity | customer records, contact details, contracts, support conversations, commercial terms, **system prompts** |
| `restricted` | high harm; need-to-know | credentials and secrets, authentication data, payment card data, precise location history, security findings, unreleased financials |
| `regulated` | specific legal / contractual regime (ADAPT per jurisdiction) | health, financial account, government identifiers, biometric, children's data, special-category data, customer-contract restrictions |

Rules:
- Classify at **field / document level** at the source; propagate the tag into chunks, embeddings, memory and traces.
- Derived artifacts inherit the **highest** class of their inputs unless a documented de-identification step (§7) lowers it.
- **Unclassified or unknown = `confidential`.** [CODE] `effective_classes()` in `msr_router.py`; test `test_unknown_or_missing_classification_is_confidential`.
- Secrets **must never** be sent to any model, embedded or stored in memory, whatever the provider. [CODE] `SECRET_DETECTED` block in the router; memory records reject them (`validate_memory_item.py` `PROHIBITED_DATA_CLASS`).
- Mapping the enterprise scheme onto these five tiers is [ORG] (§20).

## 4. Classification-to-provider matrix (ADAPT)

Provider types: **self-hosted** (weights on enterprise infrastructure), **approved cloud** (enterprise agreement that passed §5), **third-party API** (anything else, including consumer / click-through terms or an incomplete §5 review).

| Class / Provider | Self-hosted | Approved cloud | Third-party API |
|---|---|---|---|
| public | allowed | allowed | allowed |
| internal | allowed | allowed | only if terms exclude training and retention is acceptable; record in inventory |
| confidential | allowed | allowed after minimization (§6); pseudonymize PII where the task permits | **never** |
| restricted | only the required fields, security approval; **secrets never** | never, except approved exceptions with tokenization + security sign-off | **never** |
| regulated | only with Legal / Privacy approval for the purpose and jurisdiction | Legal / Privacy approval, regime-specific agreement where required, residency pinned | **never** |

Rules:
- Enforced at the gateway by comparing the request's class tags with the provider's approved classes. Exceeding the approval **blocks** the call; never logged-and-allowed. [CODE] `provider_egress_blocks()`: third-party ceiling is `{public, internal}` (`PROVIDER_TYPE_CEILING`); a provider whose terms allow training gets `public` only; restricted / regulated need their own approval line. Tests: `test_third_party_api_never_receives_confidential_even_if_approval_lists_it`, `test_provider_that_may_train_receives_public_only`, `test_regulated_needs_its_own_approval_line`.
- Routing chooses only among providers approved for the request's classes; fallback must be approved for the same classes, else the non-AI path (G6). [CODE] `Registry.candidates(..., egress)`; test `test_failover_only_to_providers_approved_for_the_same_classes`.
- Developer tooling (coding assistants, notebooks, chat tools) follows the same matrix: production `confidential`+ data is not pasted into unapproved tools. [ORG] policy + training.

## 5. Model provider approval

No provider receives non-public data before Privacy, Security and Procurement / Legal approve it, **per provider and per service tier** (consumer, team and enterprise tiers carry different terms).

| Area | Required evidence (ADAPT) | Where recorded in code |
|---|---|---|
| Data processing agreement | signed DPA; provider is processor / service provider | `data_terms.terms_ref` (registry) |
| No-training terms | contract **and** opt-out confirmed in configuration | `data_terms.training_use` (`none` / `opt_out_contracted` / `allowed`) |
| Retention | prompts, outputs, files, abuse logs; zero / minimal retention enabled where available | `data_terms.retention`, `zero_retention` |
| Abuse-monitoring access | can provider staff read content; exemption? | `data_terms.abuse_monitoring_access` |
| Residency | processing / storage regions, pinning, failover behaviour | `regions` |
| Sub-processors; logging and caching (server-side prompt caches, TTL, isolation); security certifications, encryption, keys; breach notification timeframe; regime-specific agreements; deletion of files, fine-tunes, vector stores, threads with confirmation; exit (return / delete at contract end) | evidence per area | [ORG] contract file; not modelled |
| Model change policy | deprecation notice; pinned versions (G11) | `pinned_version`, `deprecation_date` |

Rules:
- Approval is recorded with approved classes, regions and a re-review date ≤ `12 months` (ADAPT). [CODE] `ProviderApproval.review_due`; past it the provider is excluded (`APPROVAL_EXPIRED`, test `test_expired_missing_or_undeclared_provider_approval_excludes_provider`). The registry validator rejects a provider that may train on non-public data: `validate_model_registry.py` (`--selftest` case "training on confidential data").
- A change in terms, sub-processors or regions triggers re-review; the platform owner subscribes to provider change notices. [ORG]
- **Provider features that persist data** (hosted files, assistants / threads, hosted vector stores, fine-tuning, managed memory) need their **own approval line**; stateless-inference approval does not cover them. [GUIDE] record each persisted feature as a separate approval entry (e.g. `provider_id: acme-files`) with its own classes, retention and deletion API; the reference `ProviderApproval` is keyed by provider only and does not model this yet.

## 6. Egress minimization pipeline

Every model call that may carry non-public data passes one pipeline, implemented **once** in the shared gateway (G13), not per feature:

```text
authorized source data (already filtered by G9 authorization)
  1. classify      attach class + purpose tags per field / chunk
  2. minimize      drop fields not in allowed_fields; truncate history
  3. redact/tokenize  detect PII + secrets; mask, pseudonymize or tokenize per profile (§7)
  4. policy check  classes ⊆ provider.approved_classes; purposes ⊆ capability.purposes;
                   region ∈ allowed_regions; secrets_found == 0          (deterministic code)
  5. send          approved provider / region only; emit egress audit event (§16)
  6. re-identify   on the response, only for callers authorized for the originals
```

Step 4 is deterministic code over tags. An LLM never decides whether data may leave; a model-based classifier may *propose* tags in step 1, but the allow/block decision is set comparison. [CODE] `request_egress_blocks()` + `provider_egress_blocks()`; `route_and_execute()` **requires** an `EgressPolicy` and raises before any provider call without one (test `test_missing_egress_policy_fails_closed_before_any_provider_call`). Steps 1–3, 5 audit emission and 6 are [GUIDE]: the reference code receives their result as `EgressTags` (tags only, no payload). Behaviour and wiring: `../../agentic-ai-dev/reference/agentic-llm-routing.md` §3.

### 6.1 Capability egress declaration (version-controlled config)

```yaml
capability: support_reply_draft        # -> EgressDeclaration.capability          [CODE]
risk_tier: T2                          # engineering tier T0–T3                     [GUIDE]
purposes: [support]                    # -> purposes; mismatch = PURPOSE_NOT_DECLARED [CODE]
allowed_data_classes: [public, internal, confidential]   # -> CLASS_NOT_DECLARED     [CODE]
prohibited_data_classes: [restricted, regulated]         # -> PROHIBITED_CLASS       [CODE]
allowed_fields: [ticket.subject, ticket.body, customer.first_name]  # step 2         [GUIDE]
approved_providers: [approved-cloud-a]  # -> PROVIDER_NOT_DECLARED                   [CODE]
allowed_regions: [eu-west]              # -> REGION_NOT_ALLOWED / PROVIDER_REGION    [CODE]
redaction_profile: pii-default-v3       # step 3 profile id                         [GUIDE]
redaction_optional: false               # only public/internal may skip (§6.2)      [CODE]
reidentification: authorized_caller_only   # none | authorized_caller_only           [GUIDE]
provider_retention_expectation: zero    # compare with registry data_terms.retention [GUIDE]
training_use: prohibited                # provider must not be training_use=allowed  [CODE via approval]
```

Every capability has one; it is reviewed with the code change. The **capability owner** maintains it (§18).

### 6.2 Failure behaviour

| Condition | Behaviour | Code |
|---|---|---|
| Policy check fails | **block**; route to G6 degradation; emit `egress_policy_block_total{capability,reason}` | `EgressBlock` codes, outcome `EGRESS_BLOCKED`, reason `EGRESS_POLICY_BLOCK`; metric [GUIDE] |
| Redaction service unavailable | **fail closed** for `confidential`+; `public`/`internal` proceed only if declared `redaction_optional` | `REDACTION_UNAVAILABLE`; test `test_redaction_outage_fails_closed_unless_public_internal_declared_optional` |
| Secret detected | block, alert security, never forward | `SECRET_DETECTED`; alerting [GUIDE] |
| Unknown classification | treat as `confidential` | `effective_classes()` |

The block record carries codes, never payload (test `test_block_record_carries_codes_not_payload`).

## 7. PII handling

### 7.1 Detection layers

1. **Structured knowledge** first: fields the schema marks personal are handled by field, never left to detection ("schema knowledge beats detection"; never NER alone for known-personal fields).
2. **Deterministic patterns**: emails, phones, identifiers, card numbers with Luhn check, IBAN mod-97. Executed example: `../../eval-guide/scripts/validate_golden.py` `pii_hits()`.
3. **NER**: e.g. Presidio analyzer (executed setup: `../../eval-guide/reference/ci-tiers.md` "Privacy blocker with Presidio"); LangChain `PIIMiddleware` with `apply_to_tool_results=True` (`../../agentic-ai-dev/reference/agentic-guardrails-security.md`).

Run detection on: inbound user content, retrieved context, tool outputs, model outputs (before display **and** before storage, AC-15), traces / logs, corpus and memory ingestion, dataset creation.

**Recall [GUIDE]:** measure detector recall per supported language on a labelled set and record it in the inventory (§17 `pii_detector_recall`). A detector with unmeasured recall is not a control. No toolkit harness measures this today.

### 7.2 Techniques

| Technique | Effect | Reversible | Use when |
|---|---|---|---|
| Removal | drop the field | no | the task does not need it (**default**) |
| Masking | `[EMAIL]` type label | no | the model needs to know a value exists, not what |
| Generalization | city not address; age band not birth date; month not day | no | approximate information suffices |
| Pseudonymization | consistent alias per subject within a scope (`PERSON_7`) | via a separately held map | the model must track one entity across a context |
| Reversible tokenization | vault token; vault re-identifies for authorized callers | yes, through the vault | output must contain the real value for an authorized user |
| Format-preserving tokenization | token in the original format | yes | downstream validators need the format |

Rules [GUIDE unless marked]:
- Pseudonymized data is still personal data for retention and rights; only anonymized data (Legal sets the bar) leaves scope. [ORG]
- Token vaults and alias maps are `restricted`, stored apart from the data they protect, scoped per org / tenant, access-logged, covered by deletion (§10). [ORG platform] Anti-pattern: vault next to the data, or shared across tenants.
- **Alias scope is the narrowest that works**: per request or per conversation by default; key the map by `(org_id, conversation_id)`. Cross-session consistent aliases need a recorded reason in the egress declaration.
- **Re-identification happens after the model call, in deterministic code**, only for callers authorized for the originals: replace aliases from the scoped map after output validation; an unauthorized caller sees aliases or masks. Never ask the model to re-identify.
- Scan model output for **new** PII it inferred or reproduced (AC-15; `test_ac15_output_scanner_redacts_pii_and_secrets`).

Negative tests a service should carry: alias map from conversation A does not resolve aliases in conversation B; re-identification for a caller without field permission returns the alias; generalized field never contains the raw value.

## 8. Minimum-necessary disclosure

Personal data is governed by **role, stage, purpose and time**, not blanket redaction or blanket access (G9). The model never decides what personal data a user may see; deterministic context assembly does.

| Dimension | Control (implement in the context assembler) |
|---|---|
| Role | per-audience allowed-field list per entity, enforced before the model call |
| Stage [GUIDE] | a field unlocks only when the workflow state reaches the stage that needs it (e.g. contact details after assignment is confirmed): `allowed = fields_for(role) ∩ fields_for(stage)` |
| Purpose | request purpose tag ∈ field's allowed purposes (§9) |
| Time [GUIDE] | each grant has `effective_from` / `expires_at`; after expiry the field is excluded and the cached value invalidated (cache key includes the grant version) |
| Revocation | revoking a role, consent or assignment removes the field from future contexts and from caches / memory derived for that role |
| Audit [GUIDE] | each disclosure of `confidential`+ personal data to a model or user writes a disclosure record (§16) |

Summaries, briefings and memory items are generated **per audience** from that audience's allowed fields, never once with full data and filtered afterwards. Tests: field absent before stage; field absent after `expires_at`; one disclosure record per disclosure, no payload.

## 9. Consent and purpose limitation

### 9.1 Purpose register (ADAPT, [ORG])

| Purpose ID | Description | Legal basis (Legal confirms) | Classes | Capabilities | Training use |
|---|---|---|---|---|---|
| `service_delivery` | providing the requested service | contract / ... | confidential | listed | prohibited |
| `support` | customer support assistance | ... | confidential | listed | prohibited |
| `product_improvement` | quality evaluation and improvement | consent / legitimate interest / ... | sanitized only | eval pipeline | only if Legal approves and opt-out honoured |
| `security` | abuse and fraud detection | ... | as needed | security tooling | prohibited |

### 9.2 Rules

- Every record that may reach an AI system carries purpose tags or inherits them from its collection point; a capability processes data only for purposes in its declaration. Mismatch blocks. [CODE] `PURPOSE_NOT_DECLARED` (empty purposes also block).
- **Consent is checked at processing time**, not collection time [GUIDE]: read consent state from the system of record inside the request path (short TTL cache ≤ the withdrawal SLA); withdrawal stops new processing within `<SLA>` (ADAPT, e.g. 24 h) and enqueues the §10 cleanup for derived artifacts.
- Reuse for a new purpose (training, fine-tuning, shared corpus, product analytics) needs a Privacy purpose-compatibility review and register update **before** reuse. [ORG]
- Notice of automated processing or AI interaction follows G21 (`../../ai-chat/`); wording is Legal's. [ORG]
- **Opt-out / objection flags are machine-readable** (e.g. `subject.flags.no_model_improvement = true`) and enforced by the dataset build pipeline (§12.4) [GUIDE]; no toolkit dataset builder exists.

## 10. Data subject rights propagation

Access, rectification, erasure, restriction, objection and portability (whichever apply; Legal confirms) reach **every** AI artifact that can hold the subject's data. Toolkit mechanisms and proofs per store: the erasure inventory in `engineering-guardrails.md` (not repeated). Additions for stores the toolkit has no code for:

| Artifact | Access | Erasure | Mechanism [GUIDE] |
|---|---|---|---|
| Source systems of record | export | per domain rules | domain services [ORG] |
| User feedback (ratings, comments) | include | delete, or anonymize free text | feedback rows keyed by `subject_hash`; test: planted comment absent after SLA |
| Fine-tuning / training sets | include whether used | remove; record for next retrain (§12.4) | dataset lineage manifest (§12.2) lists `subject_count` + opt-out snapshot; per-subject index held by the build |
| Trained model weights | disclose that data was used | retrain / unlearn / document: Legal decides case by case | lineage + retrain schedule [ORG] |
| Backups | per backup policy | expire per backup retention; restored data re-applies deletions | deletion ledger replay on restore [ORG] |

Rules:
- Deletion ledger (fields in `engineering-guardrails.md`) is replayed after restores. Every new AI artifact type joins the inventory **before** it stores personal data; a store not listed is a finding.
- Deletion completes within `<N days>` (ADAPT; Legal sets the bound). Vector and cache purges are proven by automated plant → erase → probe tests (G15 `test_deleted_source_not_retrievable_after_sla`).
- **Access exports are assembled by deterministic code** from the stores above [GUIDE]; a model may summarize an export for readability, but the export is the authoritative response.
- **Erasure of one subject must not delete another subject's data** (shared conversations, co-owned records) [GUIDE]: delete or redact only the requesting subject's contributions; items with multiple `subject_ids` are rewritten without the subject, not dropped; ambiguous cases go to Privacy. Test: erase A in an A+B conversation, B's turns remain.

## 11. Retention schedules (ADAPT)

Shortest period that satisfies the purpose. Defaults are placeholders Legal and Privacy ratify [ORG].

| Artifact | Default | Notes |
|---|---|---|
| Raw prompts and completions | `30 days` | longer only for an approved purpose; redact at write time |
| Traces with payload attributes | `30 days` | sampled; payloads redacted at export (content capture off: `../../deployment-ci-cd/reference/ai-observability.md` §5) |
| Traces / metrics without payloads | `13 months` | trends, FinOps |
| Audit records (tool writes, egress decisions, disclosures) | per audit policy, e.g. N years | no free text; hashed IDs |
| Response / semantic caches | TTL ≤ `24 h` and ≤ source freshness | purged on source change or deletion |
| Embeddings / chunks | life of source + propagation SLA `<N days>` | deleted with the source |
| Agent / conversation memory | `<N days>` inactivity or product rule | user-visible and deletable where exposed; `expires_at` required (`validate_memory_item.py` `NO_EXPIRY`) |
| User feedback | `<N months>` | anonymize free text after review window |
| Human-review queue records | per domain record policy | |
| Fine-tuning / training datasets | while the trained model is in use + `<N months>` | manifest kept for the model's life |
| Eval / golden datasets | indefinite while in use | real data prohibited (§14) |
| Red-team findings, restricted payloads | per security policy | restricted access |
| Provider-side retention | as contracted (§5) | zero-retention where available |

Rules: retention is enforced by **automation** (TTL, lifecycle policy, scheduled deletion), never manual clean-up. Legal hold suspends deletion for the held scope only, recorded. **Retention settings live in infrastructure-as-code** [GUIDE] (bucket lifecycle rules, trace-store TTL, cache TTL, vector-store deletion jobs as Terraform / config in the repo) and are reviewed in the PR that changes the store.

## 12. Training and fine-tuning data governance

Applies to fine-tuning, adapters, distillation, RLHF / feedback datasets, reward models and anything that changes weights. The toolkit has **no training pipeline**; everything here is [GUIDE] or [ORG].

**12.1 Pre-conditions.** Recorded purpose and legal basis (§9, [ORG]); customer data only where contract and policy permit (G20, [ORG]); **opt-outs and withdrawals applied at build time** (filter the source extract against the opt-out ledger snapshot and record its id); the trained model **inherits the highest class of its training data** and deploys only where §4 allows that class (set the registry entry's `allowed_data_classes` from the manifest's maximum class).

**12.2 Lineage manifest** (one per dataset version, stored with the data):

```yaml
dataset_id: <id>
version: <semver>
owner: <named person>
purpose_id: <purpose>
sources:
  - {system: <source_system>, query_or_export: <ref>, extracted_at: <ts>, data_classes: [confidential], subject_count: <n>}
licence: <internal | licence id | terms ref>
consent_basis: <ref>
opt_outs_applied: <ledger snapshot id>
sanitization: <profile id + report>
contamination_check: {eval_sets_excluded: [..]}
sha256: <hash of the exact training input>
derived_models: [<model_id@version>]
retention_until: <date>
```

**12.3 External data.** Licence review for commercial use, derivatives and attribution; scraped data needs Legal approval of the collection method [ORG]. Check overlap with eval / golden sets (contamination) before training; contaminated eval results are not release evidence. Record dataset hashes for reproducibility.

**12.4 Opt-out and deletion.** Opted-out or erased subjects are excluded from **future** builds immediately (build reads the latest ledger snapshot). For models already trained on them, Legal and Privacy decide: retrain next cycle, proven targeted unlearning, or documented retention basis; the decision and date go in the deletion ledger [ORG]. Retrain cadence (ADAPT) honours pending removals within `<N months>`.

**12.5 Data / model cards.** Every dataset and trained model ships a card stored with the artifact and linked from the inventory: intended use, out-of-scope use, sources, classes, sanitization, known biases and gaps, languages, eval results, owner, version, retention.

## 13. Synthetic data rules

| Rule | Detail | Code |
|---|---|---|
| Label it | `synthetic: true` + generator version; never mixed unlabelled with real data | eval datasets: `source: synthetic` requires `synthetic_provenance` (`../../eval-guide/assets/schemas/dataset_manifest.schema.json`), else GD002 |
| Seeded generators | output seeded / conditioned on real data is treated as derived from it until a privacy review (nearest-neighbour / memorization check) shows no real record is reproduced | `seeded_from_real_data: true` requires `privacy_review` (same schema) |
| No real identifiers | reserved ranges: example domains, reserved phone ranges, fictitious addresses, sequential IDs | GD013 |
| Distribution honesty [GUIDE] | document which real-world properties are preserved and which are not; eval conclusions state the limit. Record as `preserved_properties` / `not_preserved` in the dataset README or card (no schema field yet) | — |
| Not sole release evidence | AI-generated or weakly reviewed golden sets are not release evidence (G7); a human owner reviews synthetic cases | `synthetic_provenance.reviewed_by` |
| Provider choice | generating synthetic data with a model is a §4 call; seed data is still data | router egress check |
| Fairness | synthetic augmentation of attributes tied to protected characteristics is bias-reviewed (G19) | [ORG] |

## 14. Eval and golden data sanitization

Golden, eval, red-team and regression datasets live in Git and **must not** contain real personal data. Default: author synthetic cases. Production failures become regression cases only after sanitization:

| Element | Treatment |
|---|---|
| Names | aliases (`user_a`, `org_b`) |
| Emails | `@example.com` or another reserved domain |
| Phone numbers | reserved test ranges (`555-01xx`, UK `07700 900xxx`) |
| Addresses | fictitious; only the structure the case needs |
| Identifiers | sequential aliases; never real account, order or government IDs |
| Payment data | removed entirely |
| Free text | reworded; keep the failure pattern, none of the original wording |
| Images / audio / documents | synthetic equivalents; strip EXIF, author, GPS |
| Timestamps [GUIDE] | shift every timestamp in a case by one random offset (same offset per case); relative order and intervals preserved |
| Secrets / tokens | removed; rotate the original if it ever appeared |

Process: (1) sanitize **inside** the production trace store's export pipeline, not on a laptop; (2) a sanitization checklist is signed off in every regression-case PR by someone other than the author [ORG]; (3) CI runs PII and secret scanners over golden data, eval reports and notebooks; a hit fails the build [CODE] `validate_golden.py` GD013 (BLOCK) over manifested case files, `prompt-secret-scan.sh` / repo secret scanning for keys; scanning eval reports and notebooks is [GUIDE]; (4) eval reports and judge outputs are scanned too, they echo staging context; (5) production-sampled evaluation runs inside the production boundary with production retention; raw inputs never go to Git.

## 15. Cross-border transfer and residency (ADAPT)

| Control | Requirement | Status |
|---|---|---|
| Residency register | each org / tenant / dataset records required processing and storage regions | [ORG] |
| Region pinning | model calls, embeddings, vector stores, caches, traces, backups pinned per request; gateway picks endpoints by the request's residency tag | [CODE] model calls: `REGION_NOT_ALLOWED`, `PROVIDER_REGION`; other stores [GUIDE] |
| Failover | only to regions in the same residency set; otherwise degrade (G6), never transfer | [CODE] candidates filtered by region |
| Transfer mechanisms | Legal confirms and records per provider and purpose | [ORG] |
| Sub-processor regions | part of §5 approval | [ORG] |
| Support access | provider and internal support access from other regions is in the transfer assessment | [ORG] |
| Telemetry [GUIDE] | traces and logs follow the residency of the data they contain: export to a collector / trace store in the same region set; only payload-free telemetry (ids, timings, tokens, cost) may be centralized, and only if Legal approves | — |
| Evidence [GUIDE] | a scheduled job (e.g. weekly) lists every AI endpoint in use (registry `regions`, gateway config, IaC) and diffs it against the residency register; any drift is a finding | not implemented |

## 16. Audit and records

Answerable per capability and period: **what personal data went to which model, for what purpose, under which approval, and where it is now.** Audit logs are append-only, access-controlled and free of raw personal data.

| Record | Contents (no payload) | Status |
|---|---|---|
| Egress audit event | capability, provider, region, classes, purpose, redaction profile, decision, trace id, hashed subject / org ids | [CODE] `Decision` carries `egress_blocks` + reason codes; persistence [GUIDE] |
| Disclosure record | role, field classes disclosed, purpose, stage, expiry, timestamp | [GUIDE] emitted by the context assembler (§8) |
| Rights-request ledger | request id, subject hash, artifacts processed, confirmations, exceptions | [ORG] |
| Provider approval record | §5 evidence, classes, regions, expiry | life of contract + N years; [CODE] structure via registry `data_terms` |
| Dataset lineage manifests | §12.2 | life of derived models + N |
| Processing records | purpose register + inventory, exportable for privacy-record obligations | [ORG] |
| Impact assessments | privacy / AI impact assessment per capability where Legal requires | [ORG] |
| Access logs | who accessed traces, vaults, training data, restricted datasets | [ORG platform] |

## 17. AI inventory and register

Every capability, model, provider, corpus and dataset is registered (G20), and the register is **generated from or validated against code / config** so it cannot drift. Toolkit records that cover part of it: model registry (`../../agentic-ai-dev/assets/model-registry.schema.json`, `validate_model_registry.py`) for models, versions, providers, regions, retention and training terms; AI BOM and readiness records (`../../ai-governance/`). Fields with **no schema field yet** [GUIDE]; add them to the service's inventory record:

| Field | Source |
|---|---|
| `purposes` | purpose IDs (§9) |
| `personal_data_categories`, `subject_types` | e.g. contact data; customers, employees |
| `egress_declaration` | path to the §6.1 config |
| `retention` | per-artifact retention (§11) or path to the IaC that sets it |
| `pii_detector_recall` | per language (§7.1) |
| `rights_propagation_coverage` | artifacts covered (§10) |
| `impact_assessment_status`, `security_review_status`, `user_disclosure` (G21), `launch_date` / `last_review` / `next_review`, `retirement_plan` | [ORG] values |

Other fields: capability id / name / description, business and technical owner, risk tier T0–T3, data classes, models and pinned versions (G11), provider type, regions, corpora / vector indexes (classification, ACL model), memory stores (retention), training datasets (id + version), human oversight points.

## 18. Roles and responsibilities (ADAPT, [ORG])

| Role | Owns |
|---|---|
| Data owner (per source system) | classification; which capabilities and purposes may use the data; allowed-field lists |
| AI platform owner | gateway, egress pipeline, redaction service, token vault, residency routing, retention automation, register tooling |
| Capability owner | egress declaration; inventory entry; rights propagation for new artifacts |
| Privacy officer / DPO | purpose register, impact assessments, rights-request process, sanitization standard; approves new purposes and training use |
| Legal | legal basis, regulatory applicability, transfer mechanisms, retention bounds, notification duties, licences |
| Security | restricted-data exceptions, provider security review, secret controls, vault and restricted-dataset access |
| Procurement / vendor risk | contracts, DPAs, sub-processor monitoring, re-review cadence |
| AI quality owner | eval-data sanitization and synthetic-data rules |

| Decision | Data owner | AI platform | Capability owner | Privacy | Legal | Security |
|---|---|---|---|---|---|---|
| New capability uses confidential data | A | C | R | C | I | I |
| New provider approval | I | R | I | A | C | C |
| Regulated data to a model | C | C | R | A | A | C |
| New purpose / training use | C | I | R | A | C | I |
| Retention period change | C | R | I | A | C | I |
| Restricted-data exception | C | C | R | C | I | A |

R responsible · A accountable · C consulted · I informed. Engineers never decide legal basis or regulatory applicability.

## 19. Anti-patterns (review findings)

"We may read it, so we may send it" · whole records or full histories when three fields suffice · consumer / click-through APIs for internal or customer data · assuming no-training because a *different* tier of the vendor says so · redacting at display while storing raw prompts in traces indefinitely · embeddings without class, ACL and source ids in chunk metadata · vaults or alias maps next to the data or shared across tenants · memory with no retention, provenance or deletion path · production traces copied into Git as golden cases "temporarily" · training on customer data because it is "already in the warehouse" · treating synthetic data from real seeds as anonymous · cross-region fallback that leaves the residency set · rights process covering the database but not logs, caches, embeddings, memory, datasets · engineers deciding legal basis · a hand-kept inventory spreadsheet no pipeline checks.

## 20. Adoption checklist (organisation-owned)

None of these is automated enforcement; the toolkit validates none of the resulting records unless marked.

- [ ] §3 tiers mapped to the enterprise scheme; field-level tags at sources
- [ ] §4 matrix ratified; gateway **blocks** (reference: router egress check)
- [ ] Every provider in use approved per §5 (DPA, no-training verified in config, retention, abuse access, sub-processors, breach terms, deletion, exit) with classes, regions, re-review date; persisted provider features approved separately
- [ ] §6 pipeline in the shared gateway; every capability has an egress declaration
- [ ] Redaction fails closed for confidential+; detector recall measured per language
- [ ] Token vault / alias maps isolated per tenant, access-logged, covered by deletion
- [ ] §8 role / stage / time rules in deterministic context assembly; disclosure records emitted
- [ ] §9 purpose register with legal bases (Legal); purpose tags enforced; consent checked at processing time; opt-out flags machine-readable
- [ ] §10 artifact table complete; deletion ledger live; vector / cache deletion tested automatically
- [ ] §11 retention values ratified by Legal and set in IaC
- [ ] §12 manifests, data cards, opt-out application in dataset builds; remedy decisions for trained weights recorded
- [ ] §13 synthetic labelling and seed-data privacy review (eval sets: schema-enforced)
- [ ] §14 PII / secret scanners over golden data (GD013), eval reports and notebooks in CI; second-person sanitization sign-off
- [ ] §15 residency register; transfer mechanisms recorded by Legal; pinning, failover and drift check verified
- [ ] §16 audit records without payloads; access logged; impact assessments where Legal requires
- [ ] §17 register generated from / validated against config
- [ ] §18 roles named as individuals; RACI ratified
- [ ] Legal confirmed applicable regimes and signed off every ADAPT value; Privacy, Security and Legal ratified this reference

**Not implemented in toolkit code (guidance only):** persisted-feature provider approvals (§5), egress steps 1–3, 5–6 and the block metric (§6), detector recall harness (§7.1), generalization / pseudonymization / re-identification code (§7.2), stage / time / audited disclosure (§8), processing-time consent and opt-out enforcement (§9.2), feedback-store and training-set erasure, deterministic access export, shared-subject erasure (§10), IaC retention (§11), all of §12, synthetic distribution-honesty field (§13), timestamp shifting and report / notebook scanning (§14), telemetry residency and endpoint drift check (§15), disclosure records (§16), inventory fields in §17.
