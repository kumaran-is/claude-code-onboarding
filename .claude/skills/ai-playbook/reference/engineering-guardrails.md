# Engineering Guardrails G1–G24 and the Ten Laws L1–L10

Canonical toolkit home of the engineering guardrails (G1–G24, risk tiers T0–T3, sections §1–§12) and the ten laws of agentic AI (L1–L10, action tiers A0–A4). The map below says, per guardrail, where the toolkit implements it, which reviewer checks it, which deterministic check or test proves it, the failure behaviour and the release evidence; the requirement text itself is in [Normative requirements](#normative-requirements) and [Ten laws: statements](#ten-laws-statements) further down. In this file "§n" means the section of that name here, and "principles §n" the ten-laws sections. Organisation-owned items: [Adoption checklist](#adoption-checklist-organisation-owned). Companion jobs: how to measure → `.claude/skills/eval-guide/SKILL.md`, `skills/eval-guide/`; organisational controls → `.claude/skills/ai-governance/SKILL.md`, `skills/ai-governance/`.

Paths are under `.claude/`. "Contract test" = a test in `skills/ai-launch-check/assets/guardrail_contract_tests.py` (Python, adapter-driven, §9 minimum verification tests) or `guardrail-contract.test.ts` (TypeScript + Zod 4 + Vitest, G3/G4 rows). Status words for evidence: PASS / FAIL / BLOCKED / NOT RUN / NOT APPLICABLE.

## Three tier vocabularies — never mix them

| Vocabulary | Values | Source | Answers |
|---|---|---|---|
| **Engineering risk tier** | T0–T3 | §3 below | Which guardrails are mandatory (T0 subset → T3 all + legal) |
| **Autonomy level** | A0–A4 | governance standard §6 (`skills/ai-governance/`) | How much the system may do without a human (per system; not the principles per-action tiers A0–A4 + Emergency, see [Principles action tiers](#principles-action-tiers-and-the-t-tier-floor)) |
| **Blast-radius tier** | 0–5 (3a/3b/3c) | `skills/ai-playbook/playbook.md` §2.2 | Review intensity and auto-commit thresholds inside the playbook |

The Decision Record states all three (plus the principles action tier per tool, always written "principles A2"); a reviewer flags any document that writes "Tier 2" without saying which vocabulary. When unsure between two T-tiers, choose the higher one (§3). T2/T3: every guardrail applies, independent sign-off, feature flag default OFF.

| T-tier | Mandatory guardrails (§3) |
|---|---|
| T0 | G1, G2, G3, G6, G8, G11, G12 |
| T1 | T0 + G7, G9, G14, G15, G16, G17, G20, G21, G22 |
| T2 | G1–G24 (G23 when offline-capable) |
| T3 | T2 + legal/compliance sign-off + regulatory mapping + human accountability per decision |

**Blast-radius tier → minimum T-tier.** §3 does not use the 0–5 scale, so this is a floor derived from the §3 definitions, not an equivalence. Assess the T-tier on its own and take the higher of it and this floor. A T-tier never implies a 0–5 tier.

| 0–5 tier (playbook §2.2) | Minimum T-tier | Basis in §3 |
|---|---|---|
| 0, 1 | T0; T1 if users see or act on the output, or it contains PII | T0 = advisory, reversible, internal, no PII; T1 = user-facing or PII |
| 2 | T2 | Output triggers side effects; "routing" is a named T2 example. §3 has no exemption for reversible side effects |
| 3a, 3b, 3c, 4 | T2 | Side effects or decisions about people, money or access |
| 5 | T3 if sector-regulated or life-safety, else T2 | T3 examples include credit, healthcare and insurance, matching the playbook's prescriptions, loans and claims |

## Guardrail map

Columns: **Impl** = canonical implementation guidance · **Review** = reviewer agent · **Gate** = deterministic enforcement · **Test** = contract test (or other executable check) · **Fails as** = required failure behaviour · **Evidence** = what the launch check demands.

**G1 Deterministic first.** Impl: `skills/ai-playbook/SKILL.md` fast triage, playbook §1.6. Review: `ai-security-reviewer` §1 (AI on an authorization or state decision), `architect`. Gate: Decision Record question 2 (`/ai-decision-record`); design-time, no runtime test. Fails as: NO-GO in `/ai-launch-check` pre-flight Q1. Evidence: Decision Record with the deterministic alternative considered.

**G2 No authority bypass.** Impl: `skills/agentic-ai-dev/reference/tool-execution-safety.md` §2 authority tiers, §7 approval gates; `agentic-streaming-hitl.md` approval record; ADK `skills/google-adk/reference/adk-tools-callbacks.md`; MCP `skills/security-reviewer/reference/mcp-security.md` T1–T8. Review: `ai-security-reviewer` §4, `agentic-ai-reviewer` §1, `adk-reviewer`. Gate: tool allowlist + role check + approval token in code (never a prompt). Test: `test_high_consequence_tool_without_approval_is_not_executed`, `test_role_without_authority_is_forbidden`, `test_tool_outside_capability_allowlist_is_denied`. Fails as: `APPROVAL_REQUIRED` / 403 / `TOOL_NOT_ALLOWED`, zero side effects. Not waivable for T2/T3 (§11).

**G3 Typed, versioned contracts.** Impl: `tool-execution-safety.md` §1 (contract incl. schema version), §11 tool surface lock; `llm-inference-and-model-routing.md` §4 structured outputs; `agentic-guardrails-security.md` fail-closed pipeline; TS: Zod `strictObject`. Review: `agentic-ai-reviewer` §3, `ai-security-reviewer` §1. Gate: boundary order tool exists → version supported → payload valid → authorized. Test: `test_schema_validation_failure_blocks_execution`, `test_unknown_field_is_rejected_not_ignored`, `test_schema_version_mismatch_is_explicit`, `test_registered_tool_schemas_match_deployed` (deploy blocked on drift). Fails as: `SCHEMA_VALIDATION_FAILED` / `SCHEMA_VERSION_MISMATCH`, no execution, route to G6 or human path. Streaming: only validated, authorized content is streamed (`skills/streaming-protocols/`).

**G4 Idempotent side effects.** Impl: `tool-execution-safety.md` §6 (payload-hash binding, replay window, expiry), §9 saga/compensation, §10 durable resume; `skills/python-dev/reference/reliability-idempotency-retries-outbox.md`; Flutter queue `skills/flutter-mobile/reference/flutter-offline-reliability.md` §3. Review: `agentic-ai-reviewer` §3, `python-worker-reviewer`. Gate: idempotency store keyed by org-scoped request scope, persisted payload hash. Test: `test_duplicate_mutation_has_one_side_effect`, `test_same_key_changed_payload_is_rejected`, `test_duplicate_creation_yields_one_canonical_record`. Fails as: same key + same hash → stored result; same key + different hash → `IDEMPOTENCY_PAYLOAD_MISMATCH`, no second effect.

**G5 Bounded autonomy, human exceptions.** Impl: `tool-execution-safety.md` §8 cumulative budgets; `agentic-cost-optimization.md` §Budgets; `agentic-streaming-hitl.md` approval expiry/escalation; ADK run caps in `adk-reviewer`. Review: `agentic-ai-reviewer` §2, `adk-reviewer`, `ai-security-reviewer` §2/§11. Gate: one budget object for the whole execution tree; per-org rate/concurrency caps at the gateway; version/supersedes check before a late write. Test: `test_cumulative_budget_exhaustion_stops_and_routes_to_human`, `test_human_override_rejects_late_ai_retry`, `test_tool_failure_is_bounded_and_routed_not_claimed`. Fails as: stop calls → keep canonical state → `HUMAN_REVIEW_REQUIRED`; `STALE_INTENT_REJECTED`. Queue owner, SLA, capacity and reserved provider capacity are organisational (REQUIRES_ENTERPRISE_ADOPTION).

**G6 Degradation path.** Impl: `llm-inference-and-model-routing.md` §5–§6; `agentic-templates-resilience.md`; UI states `skills/ai-chat/reference/ai-error-handling.md`. Review: `ai-security-reviewer` §10, `agentic-ai-reviewer` §4. Gate: fallback only to an approved config that passed the same safety gate, else non-AI flow. Test: `test_provider_outage_uses_approved_fallback`, `test_fallback_without_safety_gate_degrades_to_non_ai`. Fails as: visible degraded contract ("AI assist is unavailable — continue with the standard form"); no-data vs data-unavailable vs AI-unavailable are distinct states.

**G7 Evals gate releases.** Impl: `skills/eval-guide/` (CI tiers, golden sets, `scripts/eval_gate.py`), `skills/llm-evaluation/`, `skills/rag-evaluator/`, `skills/adk-eval-guide/`. Review: `eval-reviewer`, `ai-eval-designer`. Gate: CI eval gate (thresholds per use case and tier, ADAPT). Test: language routing `test_unsupported_language_routes_to_manual_flow`; isolation negatives are the G9 tests. Fails as: release blocked; unsupported language → `MANUAL_ROUTE`. New T2/T3 paths default OFF.

**G8 Observability and provenance.** Impl: `skills/deployment-ci-cd/reference/ai-observability.md`, `python-observability.md`; ADK `skills/adk-observability-guide/`. Review: `ai-security-reviewer` §12. Gate: required span/trace fields; content capture off in production. Test: `test_every_ai_execution_is_traced_without_raw_sensitive_data`. Fails as: missing field = test failure; raw PII in a trace = test failure. Trace-store isolation, retention and audited access: platform (REQUIRES_ENTERPRISE_ADOPTION).

**G9 Authorize before retrieval; egress minimisation.** Impl: `skills/rag-security-reviewer/` (filter inside the retrieval call), `tool-execution-safety.md` §3 scope injection, §5 untrusted results; `agentic-guardrails-security.md`; vector stores `skills/vector-database/`. Review: `ai-security-reviewer` §5–§7, `rag-implementation-reviewer`, `pgvector-schema-reviewer`/`weaviate-schema-reviewer`. Gate: principal-scoped filter in the query before ranking; per-capability `allowed_data_classes` / `prohibited_data_classes` / `approved_providers` / region checked before the provider call. Test: `test_cross_scope_query_returns_nothing_from_other_org` (results, facets, neighbors), `test_unauthorized_role_cannot_retrieve_restricted_source`, `test_request_for_other_party_data_is_blocked`, `test_secret_bearing_text_is_excluded_from_index`, `test_injected_instruction_in_retrieved_content_triggers_no_tool`, `test_sensitive_data_is_minimized_before_provider_call`. Fails as: nothing returned / redacted or blocked before egress. Not waivable for T2/T3 (§11).

**G10 Kill switch.** Impl: playbook §4.4; `skills/ai-launch-check/` kill-switch tests; `skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` §5; `skills/ai-incident-response/`. Gate: platform + per-capability flag read on every request. Test: `test_kill_switch_disables_ai_and_core_workflow_completes`. Fails as: AI paths off, deterministic workflow completes, degraded messaging. Owner, runbook, drills: organisational.

**G11 Version everything.** Impl: `llm-inference-and-model-routing.md` §2 model ids; `llmops-release-and-rollout.md` §2; prompt registry `skills/eval-guide/reference/langfuse-prompts.md`. Review: `ai-security-reviewer` §13. Gate: no `latest`/`default`/`auto` model alias; prompt name+version on spans. Test: `test_unapproved_or_floating_model_is_rejected[latest|default]`. Fails as: `MODEL_NOT_APPROVED`.

**G12 Cost and latency.** Impl: `agentic-cost-optimization.md`; `llm-inference-and-model-routing.md` §9. Review: `ai-security-reviewer` §11, `performance-oracle`. Gate: budgets (G5); per-capability SLO in the Decision Record (no universal target). Test: budget test (G5); SLO measurement is an eval/ops metric (`.claude/skills/eval-guide/SKILL.md` (EVAL §11)).

**G13 Reuse shared infra; gateway never bypassed.** Impl: playbook §2.3; architecture review via `architect` / `/design-architecture` for any new vector index, provider or agent framework. Gate: AI calls only through the shared client/gateway. Test: `test_gateway_unavailable_degrades_without_bypass`. Fails as: degradation, zero direct provider calls. The gateway itself is a platform prerequisite (§10; REQUIRES_ENTERPRISE_ADOPTION).

**G14 Retrieval ≠ authority.** Impl: `skills/rag-architect/`, `tool-execution-safety.md` evidence gate (`INSUFFICIENT_EVIDENCE`), playbook §2.4 cited ids ⊆ retrieved ids. Review: `rag-implementation-reviewer`, `ai-security-reviewer` §3. Gate: source/version/authorization/freshness checks on candidates; similarity never merges, closes or approves. Test: G17 `NOT_FOUND` test + review; no generic runtime test can prove "similarity never merges" (PARTIALLY_COVERED).

**G15 RAG lifecycle.** Impl: `skills/rag-security-reviewer/` deletion section; `skills/vector-database/` (embedding migration: `/migrate-embedding-model`). Review: `rag-implementation-reviewer`. Gate: ACL metadata per chunk, secret screen at ingest, deletion within SLA. Test: `test_secret_bearing_text_is_excluded_from_index`, `test_deleted_source_not_retrievable_after_sla`. ACL-change propagation SLA: platform.

**G16 Current state beats memory.** Impl: `agentic-memory-systems.md` §Freshness, invalidation and erasure; playbook §2.6 authority order. Review: `agentic-ai-reviewer`, `ai-security-reviewer` §8. Test: `test_canonical_state_beats_stale_memory`. Fails as: canonical value returned, conflict flagged.

**G17 Explicit uncertainty.** Impl: evidence gate (`tool-execution-safety.md`), playbook §2.4 abstain shape; UI states `skills/ai-chat/` (unknown / not found / stale shown as such). Test: `test_no_evidence_returns_not_found_not_a_guess`. Under- and over-escalation rates are eval metrics (`skills/eval-guide/`).

**G18 Role-safe advice (ADAPT).** Impl: Decision Record role-boundary table (`/ai-decision-record`). Gate: deterministic intercept for configured consequential topics routes to a bounded template + escalation; a classifier is a signal that routes to review, never the boundary. Test: `test_consequential_question_gets_bounded_answer_and_escalation` (keyword stand-in; replace with the product's policy). Boundaries per audience are ADAPT content owned by the product.

**G19 Non-discrimination.** Impl: Decision Record fairness question; eval fairness slices (`skills/eval-guide/`). No generic runtime test: protected attributes and proxies are jurisdiction-specific (REQUIRES_ENTERPRISE_ADOPTION, Legal owns policy).

**G20 Model / provider governance.** Impl: `llm-inference-and-model-routing.md` §2, §6 (fallback to approved providers only); AI inventory / BOM in `skills/ai-governance/`. Gate: routing picks only from an approved registry. Test: `test_unapproved_or_floating_model_is_rejected[unlisted-model]`. Vendor risk review and training-data policy: organisational.

**G21 Honest disclosure.** Impl: `skills/ai-chat/` (AI-generated label, canonical fact vs AI explanation vs recommendation vs human decision visually distinct; never "reviewed" unless a review record exists). Review: `ai-security-reviewer` §3, `ui-standards-expert`. Test: component test in the app (no generic contract test).

**G22 Accessibility of AI UX.** Impl: `skills/accessibility-audit/` (WCAG 2.2 AA, stricter than the standard's WCAG 2.1 AA example), `skills/ai-chat/` (`aria-live`, keyboard, degraded/handoff states). Review: `accessibility-auditor`. Test: Playwright + axe (web), `flutter test` guidelines + Maestro (mobile) per `rules/testing-tool-selection.md`.

**G23 Offline (if applicable).** Impl: `skills/flutter-mobile/reference/flutter-offline-reliability.md`, `flutter-offline-sync.md`. Gate: server revalidates queued consequential actions; `FAIL_CLOSED` vs `SAFE_TO_DEFER` per action class. Test: `test_offline_duplicate_operation_applies_once`, `test_offline_action_blocked_by_newer_safety_state`, `test_fail_closed_action_not_applied_when_check_unavailable` (skip with `not_applicable` when there is no offline client).

**G24 Measurable outcome.** Impl: Decision Record `baseline_metric`, `target_metric`, `measurement_method`, `evaluation_window`, `cost_to_serve`, disable trigger; `/ai-launch-check` blocks without them. Measurement after launch: `.claude/skills/eval-guide/SKILL.md` (EVAL §11/§13) (no universal ROI threshold).

## §5 execution hierarchy → code locations

| Step | Where it lives |
|---|---|
| 1 Pre-retrieval authorization | auth dependency + scope injection (`tool-execution-safety.md` §3) |
| 2 Deterministic safety/policy intercepts | before any model call; kill switch, language, consequential-topic routing |
| 3 Structured retrieval | principal-filtered queries (`rag-security-reviewer`) |
| 4 Bounded reasoning | budgets (G5) |
| 5 Typed validation | tool boundary (G3) |
| 6 Payload-hashed idempotent gate | `tool-execution-safety.md` §6 |
| 7 Canonical write | domain service, not the agent (§9 saga) |
| 8 Observability | `ai-observability.md` |

## §6 merge requirements, §8 release checklist, §11 waivers

- §6: applies to every AI change, human or assistant authored. Path-scoped rules (`rules/ai-engineering.md`) and the review commands are the enforcement points; the reviewer agents tag findings with these ids. Item 15 ("never claim production readiness without code + test + runtime evidence") is the same rule as `rules/verification-and-reporting.md`.
- §7 ADR: `/ai-decision-record` (all §7 fields). §8 checklist: `/ai-launch-check` (guardrails section). §9 tests: the contract test template above, run per capability; skipped tests carry a NOT APPLICABLE reason and are listed in the launch report.
- §11 waiver: recorded in the Decision Record (guardrail, reason, compensating controls, T-tier, accountable owner, independent approver, Legal for T3, expiry date). G2 and G9 cannot be waived for T2/T3; `/ai-launch-check` rejects such a waiver.
- §10 platform prerequisites (redaction service, gateway, idempotency store, human-exception capacity, authorization primitives, model registry/inventory, private trace store) need named owners and production evidence: the toolkit supplies patterns and tests, never the evidence that an organisation runs them.

## Ten laws (L1–L10) → control → owner → evidence → failure condition

The ten laws state *what must be true* ([statements and law-to-guardrail mapping](#ten-laws-statements)); this table maps each law to the guardrail controls above that enforce it. Four-element rule (principles §5): a capability complies with a law only when the Decision Record (`/ai-decision-record`, the §7 ADR) names, per applicable law, the **control**, an accountable **owner**, verifiable **evidence** and a **failure condition**; a law with no evidence is **not met**, and `/ai-launch-check` treats it as ❌. The owner column below is the default *role*; the Decision Record names the accountable person (organisational, never filled in by the toolkit).

Evidence locations: **AC** = `skills/security-reviewer/assets/ai-attack-class-fixture/test_attack_classes.py` (reference controls, runs in this repo: `uv run --frozen pytest`, plus `run_negative_controls.sh`, MOCKED model). **GC** = `skills/ai-launch-check/assets/guardrail_contract_tests.py` (template: proves the control only once the service implements the adapter and runs it). **EG** = `skills/eval-guide/scripts/eval_gate.py` rule codes. **GV** = `skills/ai-governance/scripts/validate_governance_record.py` (record structure only, never runtime enforcement). Principles action tiers A0–A4 ([below](#principles-action-tiers-and-the-t-tier-floor)) grade the consequence of one *action*; they are not the governance autonomy levels A0–A4, so always write "principles A2" or "governance A2".

| Law | Control (canonical) | Owner role | Executable evidence | Failure condition (deterministic) |
|---|---|---|---|---|
| L1 Understand before acting | G16 current state wins; G5 stale-intent check; G23 revalidate before apply; G1 | Domain service owner | GC `test_canonical_state_beats_stale_memory`, `test_human_override_rejects_late_ai_retry`, `test_offline_action_blocked_by_newer_safety_state` | A consequential write is applied although the authoritative state version changed after the plan was formed (no `STALE_INTENT_REJECTED`) |
| L2 Authorization and delegation | G2 no authority bypass; G9; G18; G11 | Application security / IAM owner | AC `test_ac07_cross_scope_id_rejected_and_no_violation`, `test_ac04_authority_rederived_each_turn_not_from_history`, `test_ac09_confirmation_bound_to_payload_hash`; GC `test_high_consequence_tool_without_approval_is_not_executed`, `test_role_without_authority_is_forbidden` | Any consequential write executes without server-side authorization: side-effect count > 0 on a 403 / `APPROVAL_REQUIRED` / `TOOL_NOT_ALLOWED` path (four-element rule) |
| L3 Trusted context | G14, G15, G9 (untrusted content); G16, G17 | Retrieval / knowledge-source owner | AC `test_ac02_retrieved_instruction_never_triggers_tool`, `test_ac03_stored_payload_is_quarantined_at_read_time`, `test_ac10_untrusted_contributor_cannot_write_shared_corpus`, `test_ac16_uncited_or_fabricated_citation_is_unsupported`; GC `test_injected_instruction_in_retrieved_content_triggers_no_tool`, `test_no_evidence_returns_not_found_not_a_guess`; EG002 (injection hard blocker) | A tool call is caused by retrieved, stored or tool-output text; or an answer cites an id not in the retrieved, authorized set |
| L4 Agent collaboration | G5 one budget per execution tree; G9; G13; G8 trace correlation | AI platform (agent runtime) owner | AC `test_ac08_readonly_agent_has_no_write_tool`, `test_ac08_tool_description_drift_fails_lock`; GC `test_tool_outside_capability_allowlist_is_denied`, `test_cumulative_budget_exhaustion_stops_and_routes_to_human` | A delegated agent's tool set or data scope is not a subset of its caller's; or a sub-agent call is missing from the root trace |
| L5 Never assume intent | G2 approval gates; G5; G18; G21 | Product owner (tiers) + domain service owner (enforcement) | AC `test_ac09_confirmation_bound_to_payload_hash`, `test_ac09_mass_action_over_batch_limit`; GC `test_high_consequence_tool_without_approval_is_not_executed`; GV approval record (`action_digest`, `expires_at`, `timeout_policy` never auto-approve) | An A2+ action (principles action tier) executes without confirmation, with a confirmation whose payload hash differs from the executed payload, or after the approval expired |
| L6 Explain | G8 observability; G21 disclosure; G17; G3 | AI platform (observability) owner | GC `test_every_ai_execution_is_traced_without_raw_sensitive_data`; AC `test_ac09_every_write_is_audited`, `test_ac16_uncited_or_fabricated_citation_is_unsupported`, `test_ac15_output_scanner_redacts_pii_and_secrets` | A consequential action has no audit record with trace id, policy and source references; or an explanation or trace contains a secret or another party's data |
| L7 Safety over autonomy | G2, G7 safety-recall gate, G10; G5, G6, G19 | Safety taxonomy owner + incident commander | GC `test_consequential_question_gets_bounded_answer_and_escalation`, `test_fallback_without_safety_gate_degrades_to_non_ai`, `test_kill_switch_disables_ai_and_core_workflow_completes`; EG003 / EG013 when safety recall is a mapped release dimension | A safety-capable path is released without a safety-recall result at its ratified threshold; or a safety-classified input reaches a standard queue or a model-only decision |
| L8 Verify outcomes | G3, G4, G7; G24 | Domain service owner | GC `test_tool_failure_is_bounded_and_routed_not_claimed`, `test_duplicate_creation_yields_one_canonical_record` | A "done" message is emitted on a tool success response with no read-back of the business record (four-element rule; async pattern [below](#l8-asynchronous-outcome-read-back)) |
| L9 Fail safely | G4, G5, G6, G10; G12 | AI platform reliability owner (SRE) | GC `test_duplicate_mutation_has_one_side_effect`, `test_same_key_changed_payload_is_rejected`, `test_provider_outage_uses_approved_fallback`, `test_kill_switch_disables_ai_and_core_workflow_completes`; AC `test_ac12_tool_call_budget` | A retry produces a second side effect for the same idempotency key, or accepts a changed payload under it; or the core workflow fails while AI is off |
| L10 Protect data | G9, G15, G20; G8 trace privacy, G19 | Data protection / privacy owner | AC `test_ac07_retrieval_filtered_before_ranking`, `test_ac11_no_global_counts_or_other_scope_hits`, `test_ac15_output_scanner_redacts_pii_and_secrets`, `test_sec13_secret_rejected_at_ingestion`; GC `test_cross_scope_query_returns_nothing_from_other_org`, `test_sensitive_data_is_minimized_before_provider_call`; EG003 (`isolation` is a protected class) | Any cross-tenant isolation test returns another scope's data, snippet or count (four-element rule) |

Not provable by a generic test (stays with the product or the organisation): emergency playbooks and human escalation capacity (L7), scoped expiring and revocable delegation credentials and authenticated inter-agent channels (L2, L4), running the [L8 read-back](#l8-asynchronous-outcome-read-back) against the real system of record (L8), encryption and retention of prompts, embeddings, memory and traces (L10), and the named owner per law.

## Data governance and privacy (expands G9, G15, G20)

Full DGP requirements: `data-governance-privacy.md` (this directory). Toolkit enforcement points:

- **Egress authorization (DGP §4, §6.1, §6.2):** `skills/agentic-ai-dev/assets/reference-router/msr_router.py` (`EgressPolicy`, `request_egress_blocks`, `provider_egress_blocks`); behaviour in `agentic-llm-routing.md` §3. Deterministic, before any provider call; failover and escalation stay inside providers approved for the request's classes and region. Test: `test_msr_router.py::EgressAuthorization` (MOCKED PROVIDER). The production gateway, redaction service and token vault are §10 platform prerequisites (previous section).
- **Synthetic and golden data (DGP §13, §14):** `skills/eval-guide/scripts/validate_golden.py`: real PII in golden files is GD013 (BLOCK); `source: synthetic` needs `synthetic_provenance` (generator, version, seeded-from-real flag, privacy review when seeded, human reviewer), else GD002.

### Erasure propagation inventory (DGP §10.1)

Every store an AI capability writes appears here before it holds personal data; a store missing from the service's copy of this table is a finding (§10.2). Proof is plant → erase → probe after the deletion SLA, asserted by a test, never by reading config.

| Artifact | Toolkit mechanism | Proof |
|---|---|---|
| Prompt / completion logs, traces | content capture off by default; trace store with retention, deletion and legal hold (`skills/deployment-ci-cd/reference/ai-observability.md` §5) | service test: planted subject string absent from log and trace stores |
| Response / semantic / tool caches | scope keys and bump `index_version` or the memory version on erasure (`skills/agentic-ai-dev/reference/llm-inference-and-model-routing.md` §8, `agentic-caching-patterns.md`) | identical query misses after erasure |
| Embeddings, chunks, BM25 / metadata stores | hard delete of all versions (`skills/rag-security-reviewer/` deletion section, `skills/rag-architect/references/versioning-and-freshness.md` §8) | contract test `test_deleted_source_not_retrievable_after_sla` |
| Agent memory and summaries | lineage is the erasure index; summaries rebuilt (`skills/agentic-ai-dev/reference/agent-memory-lifecycle.md` §7); tombstones keep no content (`validate_memory_item.py` `DELETED_RETAINS_CONTENT`) | §7 plant → erase → probe table |
| Eval / golden / red-team datasets | real data prohibited (GD013); remove and replace with synthetic if found | `validate_golden.py` in CI |
| Provider-side stored data (files, threads, hosted stores, managed memory) | provider deletion API; ADK managed memory limits in `skills/google-adk/reference/adk-memory-artifacts.md` §4.2 | provider deletion confirmation recorded |
| User feedback, fine-tuning sets, trained weights, backups | none in the toolkit: the owning service or the organisation (Legal decides the remedy for trained weights, DGP §12.4) | deletion ledger entry |

Deletion ledger (DGP §10.2): subject hash, request id, timestamp, artifacts processed, confirmation per artifact, exceptions. It is replayed after a backup restore and holds no raw personal data. The ledger, purpose register, provider approvals, retention values and residency register are organisational records; the toolkit validates none of them today.

## Normative requirements

Requirement text for §1–§12 and G1–G24. The map above says where each is implemented, reviewed and tested. **must / must not** = mandatory; **should** = default, a deviation needs a recorded reason; **may** = optional.

### §1 Precedence and scope

Horizontal invariants for every team that ships LLM calls, RAG, agents, tool/MCP servers, AI-assisted UX or background AI jobs, whatever the language, framework, model provider or cloud. They do not replace domain Sources of Truth (product specs, domain architecture, legal/compliance, security, UX/design system): **a stricter or more specific Source of Truth wins; a looser one loses to these guardrails.**

### §2 Core authority rule

```text
Canonical structured state (system of record)
  > Authoritative source documents
  > Verified historical outcomes
  > Derived / compiled knowledge (summaries, embeddings, memory)
  > LLM inference
```

AI may explain, summarize, classify, retrieve, rank, recommend and draft. **AI must never silently become the system of record.**

### §3 Risk tiers T0–T3 (ADAPT)

Every capability gets a tier at design time, recorded in the Decision Record and re-assessed when scope changes. When unsure between two tiers, choose the higher. Mandatory guardrails per tier: the T-tier table at the top of this file.

| Tier | Definition | Examples (ADAPT) | Depth beyond the guardrail set |
|---|---|---|---|
| **T0** Assistive / low | Advisory, reversible, internal, no PII | internal summarization, code assist, draft text a human always edits | — |
| **T1** User-facing | Users see or act on the output; may include PII | customer chat, RAG Q&A, search, recommendations | — |
| **T2** Consequential | Output triggers side effects or influences decisions about people, money, access or safety | agents with write tools, triage, routing, eligibility, pricing, approvals | all guardrails; independent sign-off; feature flag default OFF; safety and fairness gates |
| **T3** Regulated / safety-critical | Sector regulation or life-safety impact | credit, employment, housing, healthcare, insurance, critical infrastructure | T2 + legal/compliance sign-off + documented regulatory mapping + human accountability for every decision |

### §4 One-line rules

G1 if structured logic can decide it reliably, don't use AI · G2 AI recommends, policy validates, an authorized action executes · G3 code never consumes free-form model text · G4 every AI-triggered mutation is retry-safe and payload-bound · G5 every loop has budgets, stop conditions and a human path · G6 AI failure never dead-ends a core workflow · G7 no eval pass, no release · G8 every execution is traceable and attributable · G9 isolation is enforced before data reaches the model · G10 AI can be turned off platform-wide without breaking core flows · G11 no `latest` in production; every change has a rollback · G12 per-capability budgets; cheapest model that passes evals · G13 no parallel truth, retrieval, auth or gateway systems · G14 similarity finds candidates, it proves nothing · G15 ingested content keeps its ACLs, freshness and deletion · G16 memory is context, not truth · G17 unknown / conflicted / stale are valid outputs · G18 each audience has explicit "must not" boundaries · G19 no decisions on protected attributes or proxies · G20 only approved models, providers and training data · G21 users can tell fact, AI output and human decision apart · G22 AI UX meets the same accessibility bar · G23 AI never breaks an offline-capable workflow · G24 AI that adds no measurable value is turned off.

### G1 Deterministic first

If a decision can be made reliably from structured state, policy, configuration or deterministic logic, use that first: safety rule → deterministic policy · eligibility → deterministic gates · spend / approval limit → configured policy · workflow status → canonical state machine · payment state → payment system of record · access control → authorization service. Use AI only where ambiguity, language understanding, summarization, semantic retrieval or bounded reasoning **materially** improves the workflow, never because AI can perform the task.

### G2 No authority bypass

AI must never independently override or bypass: safety/emergency policy · eligibility, licensing or compliance gates · spend/approval authority · dispatch or fulfilment authorization · payment/payout authority · verification requirements · case/order closure · access control · organization/tenant/user authorization. Consequential actions: `AI recommendation → deterministic / policy validation → explicit authorized action`; never `AI recommendation → direct irreversible action`.

### G3 Typed contracts

- Any AI output consumed by code has a typed contract (JSON Schema, Pydantic/Zod or equivalent, explicit enums, typed tool and MCP contracts) **with an explicit schema version**. Free-form text is for user-facing explanation only; it never directly drives database mutation, payment, dispatch, authorization or other system actions.
- Validation failure → safe fallback, retry or human review; never best-effort execution.
- Tool boundary, every call: `tool exists → schema version supported → payload conforms to the pinned schema → authorization permits the action`. On failure return `SCHEMA_VERSION_MISMATCH` / `SCHEMA_VALIDATION_FAILED`, do not execute, route to G6 or the human exception path.
- Prompts, tool declarations, MCP contracts, generated clients and backend schemas must not drift independently (deploy-blocking registry-vs-deployed test).
- Compatibility: **major** = breaking; **minor** = additive, backward-compatible fields only; **patch** = docs/validation fixes, no contract change. Enum changes, new required fields and semantic changes need explicit compatibility review; a named platform owner governs the shared schema/tool registry.
- Streaming: stream only content already safe and authorized for display; never unvalidated tool arguments, unauthorized retrieval results, other-scope context, or a side-effect confirmation before the canonical write succeeds.

### G4 Idempotent side effects

Every AI- or agent-triggered mutation (records, messages, financial state, scheduling, workflow starts, external integrations) has a stable idempotency key, payload-hash binding, duplicate detection, retry-safe behaviour, observable status and no double side effect.

```text
payload_hash    = SHA256(canonical_json(payload))
idempotency_key = SHA256(org_id + entity_id + action_name + payload_hash)
creation (no entity_id yet):
idempotency_key = SHA256(org_id + source_channel + client_request_id + payload_hash)

same key + same hash      → return the existing result
same key + different hash → reject IDEMPOTENCY_PAYLOAD_MISMATCH
```

- Persist key and hash. An agent retry never reuses a key with changed financial, scheduling, recipient or authorization parameters.
- Key lifecycle: org-scoped; retained for the action's replay window (longer for payment, fulfilment and creation); durable for consequential actions; auditable; protected against post-expiry replay. An expired key never re-executes blindly: revalidate canonical state first. Network retries, worker crashes, duplicate events, webhook retries and sync replays create no duplicate or mutated business action.
- Multi-step operations are never one atomic AI action unless the domain guarantees atomicity: use the domain's transaction / saga / compensation semantics; budget exhaustion or agent failure never leaves the system silently half-mutated. AI may *request* a workflow; domain services own transaction boundaries and recovery.

### G5 Bounded autonomy and human exceptions

- Every agent or workflow defines: max iterations · max tool calls · per-tool retry limit · latency budget · cumulative token budget · cumulative cost budget · retry policy · stop conditions · human/exception fallback.
- Budgets cover the **whole execution tree** (router, sub-agents, retries and fallback models share one budget). No single enterprise-wide cap: configure per capability, risk tier and environment, calibrated from measured p95/p99 usage. **Never rely on the model to decide when to stop.** Exhausted → stop further model/tool calls → preserve canonical state → `HUMAN_REVIEW_REQUIRED`.
- Noisy neighbour: per-org (tenant / business-unit) request rate limits, concurrency caps, period budgets, queue priority and reserved provider capacity for critical paths; one consumer's runaway workload never starves others.
- Human override cancels stale AI intent: invalidate pending AI intents for the scope, cancel delayed retries, and require a canonical-version / supersedes check before any late write (`STALE_INTENT_REJECTED`). Payload idempotency alone does not stop stale intent.
- Human exception operations are a designed operating mode, not an AI failure: every handoff goes to a real queue with an owner, SLA, escalation path, `exception_type` / required authority and enough context to decide without re-running the AI flow. The queue defines capacity, priority classes, safety-first ordering, overflow behaviour, SLA-degradation policy and load-shedding for non-critical review; track reviewer rework caused by insufficient context.

### G6 Degradation path

No core workflow depends on an AI service being healthy.

| AI failure | Degrades to |
|---|---|
| real-time voice unavailable | typed / form input |
| classification uncertain | clarify / deterministic selector / review |
| semantic retrieval unavailable | structured lookup / keyword search |
| compiled memory unavailable | canonical timeline / record view |
| primary model unavailable | approved fallback model or non-AI workflow |
| background AI job delayed | workflow continues without waiting |

On safety-capable paths a fallback model/config passes the **same safety gate** as the primary, else the flow falls back to deterministic/manual. Degradation is visible and actionable ("AI assist is unavailable — continue with the standard form"), never a silent swap to a weaker path. Every user-facing capability distinguishes **no data exists** vs **data unavailable** vs **AI assist unavailable**.

### G7 Evals gate releases

- Task-specific evaluation before release, dimensions as applicable: accuracy, safety recall, hallucination/unsupported-claim rate, tool-call correctness, schema conformance, authorization/isolation, retrieval quality, grounding/citation, latency, cost, escalation rate, false-positive/negative rates, and quality in **every language the capability can receive**. **No universal threshold**: set per use case and risk tier.
- Isolation negatives: multi-tenant capabilities include cross-scope negative fixtures proving no leak via results, snippets, facets/counts, semantic neighbours or related-entity traversal.
- An input path that can receive an unvalidated language routes deterministically to a supported or manual flow; safety-critical translated output is evaluated in the delivered language.
- **Safety recall** is a mandatory gate for any intake, triage, chat or routing path that can meet life-safety or high-harm conditions; under-routing a configured high-risk class is a release blocker. An unrecognized but potentially severe condition is clarified or escalated, never forced into a routine class.
- The safety taxonomy has a named owner, version, review cadence, change control and an eval-set update requirement; AI never turns it into legal conclusions.
- Eval data governance: provenance, reviewer identity, inter-annotator agreement or equivalent QA, adversarial review, version history, change approval. An AI-generated or weakly reviewed golden set is not release evidence.
- Model, prompt, routing, retrieval and policy changes are evaluated before broad rollout. **New T2/T3 paths default OFF behind a feature flag** until gates pass; use shadow evaluation and periodic re-evaluation of production samples.

### G8 Observability and provenance

- Every execution answers: what happened · model / prompt / policy / tool versions · canonical data and retrieved context used · tool calls · what the AI returned · which gate accepted or rejected it · cost · latency · whether a human was involved.
- Minimum fields: trace/correlation id, capability name, model tier + version, prompt/policy version, retrieval config version, tool calls, tokens, latency, error/fallback path, eval signals, source provenance. Use the existing observability stack (OpenTelemetry recommended). No secrets or unrestricted PII.
- Trace stores are sensitive production data: org isolation, role-based access, retention, redaction/minimization, audited access, legal hold and deletion; no global trace store operators can casually browse across customers.
- Monitoring: per-org cost anomaly alerts · runaway retry/loop detection · abnormal fallback/escalation-rate alerts · scheduled prompt-injection and red-team regression over every untrusted input channel (user text, uploads, image metadata, partner notes, retrieved content) · embedding-leakage and membership-inference probes where practical. Alerts define severity, dedup, owner, routing and suppression.

### G9 Authorize before retrieval

- Authorization is applied **before** retrieval, never after generation: relational queries, vector stores, RAG, memory, federated search, graph traversal, caches, snippets, counts/facets, nearest neighbours, ranking signals, generated briefings. `authorization → source filtering → retrieval → reasoning`; never `global retrieval → LLM filters unauthorized content later`.
- Retrieved text, documents, notes, OCR, web content and tool outputs are **untrusted data, not instructions**; they can never change system policy, tool permissions or authority boundaries.
- Secrets (credentials, access codes, keys, physical access information) never enter semantic memory or embeddings.
- Egress minimization: permission to read data internally does not authorize sending it to an external provider. `authorized source data → classify → minimize → redact / tokenize → provider-policy check → send only required context`. Each capability declares `allowed_data_classes`, `prohibited_data_classes`, `approved_providers`, `region/residency`, `retention/training expectations`, `redaction requirements`. Never send secrets, payment credentials, unnecessary PII or confidential commercial terms because they happen to be in context.
- Minimum-necessary PII is governed by role, workflow stage, purpose, allowed fields, effective time window, revocation/expiry and audit: staged, authorized disclosure with expiry and audit instead of blanket redaction of what is legitimately required.

### G10 Kill switch and incident mode

A platform-level AI kill switch per product (ideally per provider) in addition to per-capability flags, for provider incidents, injection campaigns, cost runaway, widespread bad behaviour, security/privacy incidents and systemic schema/tool drift. ON → disable AI-assisted paths → keep deterministic / canonical workflows running → activate G6 paths → preserve canonical state → clear degraded-mode messaging to users and operators. It has a named owner, audited activation, a runbook, periodic drills, a recovery checklist, incident classification, a communication path and post-incident review, and never disables deterministic safety logic or canonical workflow access.

### G11 Version everything

Version and review: system prompts · agent instructions · tool definitions · output schemas · model versions · embedding models · retrieval config · ranking logic · routing policy · thresholds · compilers/summarizers · redaction policy · eval datasets and thresholds. No production `latest`, `default` or `auto-upgrade` aliases unless their behaviour is explicitly controlled and evaluated. Every consequential behaviour change has a rollback path.

### G12 Cost and latency

Use the least expensive model that passes the capability's eval and safety gates. No universal targets ("all calls < 10 s", "all requests < $0.10"): each capability sets its latency/cost SLO by interaction type, urgency, device/network context and interactive vs batch. Measure cost per capability, interaction, business entity and org; p50/p95/p99 latency; retries; tokens; cache hit rate; fallback rate. New infrastructure is justified by measured need.

### G13 Reuse shared AI infrastructure

- Inspect and reuse existing foundations; never create competing state models, memory stores, embedding or redaction pipelines, authorization layers, search indexes, human-review mechanisms or agent frameworks. Default: extend the existing production architecture before creating a new framework.
- Prefer a shared **AI gateway / policy enforcement layer** for authorization context, schema/tool version validation, idempotency metadata, budget context, trace ids, redaction hooks, provider routing and feature-flag state. It has a named owner, SLO, versioning policy, observability, capacity limits and a documented failure mode. **Gateway down → AI paths degrade (G6), never bypass it.**
- A new vector index, embedding pipeline, retrieval store, model provider or agent framework needs architecture review (`architect`, `/design-architecture`) showing why the existing platform cannot meet the need.
- Before mandating reuse, verify with code/runtime evidence that the shared dependency exists and is production-capable; if it is missing or immature, build or extend it as an explicit platform prerequisite, never as a hidden parallel implementation inside a feature.

### G14 Retrieval is evidence, not authority

`semantic retrieval → candidate context → source / version / authorization / freshness checks → bounded reasoning`. Similarity must not independently link or merge records, declare duplicates or repeat failures, determine responsibility or liability, bypass eligibility gates, approve spend, declare verification or close work. Structured current state always wins.

### G15 RAG data lifecycle

- **Ingestion:** every source has an owner, an approved use, a data classification and a sanitization step (strip secrets, PII beyond policy, and embedded instructions where detectable).
- **ACLs travel with content:** each chunk carries the source's ACL / org / scope metadata; retrieval filters on it (G9); source ACL changes reach the index within a defined SLA.
- **Deletion and retention:** deleting or expiring a source removes its chunks, embeddings and caches within a defined SLA; deletion is testable.
- **Freshness:** chunks carry source version and timestamp; stale or superseded versions are excluded or labelled.
- **Citations:** user-facing answers cite their sources; unsupported claims are flagged or withheld (G17).
- **Embedding changes:** a new embedding model or chunking strategy is a versioned migration with a re-index plan and a re-run of retrieval evals.
- **Poisoning defence:** untrusted contributors cannot write into shared corpora without review; red-team covers indirect injection and embedding poisoning.

### G16 Current state beats memory

Historical memory (RAG, compiled memory, session history, prior outcomes, prior summaries) is context, not current truth: prior diagnosis ≠ current diagnosis · prior performance ≠ current eligibility · old contract summary ≠ current amendment · cached briefing ≠ current safety state. On conflict, **canonical current state wins**.

### G17 Explicit uncertainty

Prefer `known · unknown · not found · conflicted · stale · requires review` over confident guessing; never convert missing evidence into inferred facts: unknown identity → `UNKNOWN` · no current evidence → `NOT_FOUND` / review · conflicting authoritative documents → `CONFLICTED` · no eligible option → `NO_ELIGIBLE_OPTION` / `HUMAN_REQUIRED`. Escalation thresholds (`classification`, `clarification`, `human_review`, `safety_override`) are explicit and versioned; evals measure both under- and over-escalation; never rely on model-verbalized confidence alone.

### G18 Role-safe advice boundaries (ADAPT)

Every AI surface respects its audience's authority and liability boundaries. The Decision Record copies this default table, keeps the rows for its audiences and adapts them; a stricter domain Source of Truth wins.

| Audience | AI may | AI must not |
|---|---|---|
| End customer / consumer | explain their own state, give grounded guidance, route to workflows | give legal, medical, financial or tax advice; admit liability; make eligibility or entitlement determinations; promise outcomes outside canonical state |
| Partner / supplier | explain their own status, requirements, missing items, governed scorecard inputs | reveal competitor data or bids, proprietary ranking weights, others' contact data; negotiate terms autonomously; adjudicate disputes |
| Field / frontline worker | brief, retrieve verified history, explain required steps, route escalations | declare a hazardous situation safe; authorize access, scope changes or safety-step bypasses; override current work-order state |
| Internal operator / manager | surface context, options, trade-offs and evidence | approve/deny spend; decide fairness of commercial terms; make capital or HR decisions; override eligibility or authorization controls |
| Executive / owner | summarize canonical operational and financial data | give legal, tax or individualized investment advice; set prices autonomously |

Legal-, medical- and safety-adjacent questions get approved bounded language and route to the right human/policy workflow when consequential.

### G19 Non-discrimination

AI must not make, recommend or influence decisions about people based on protected characteristics (as defined by the applicable law of each jurisdiction) or prohibited proxies for them: prioritization, eligibility, pricing, service quality, ranking, access or behavioural scoring. Operationally necessary sensitive information (e.g. an accessibility accommodation) is limited to the minimum the authorized workflow requires. T2/T3 capabilities include fairness and bias testing appropriate to the decision surface and jurisdiction. Legal/Compliance owns the policy.

### G20 Model, provider and training-data governance

- New production models and providers need documented approval, evaluation, deployment, monitoring, rollback and retirement criteria, plus a vendor risk / data-processing review. Routing chooses only among **approved** configurations.
- Training or fine-tuning data has a documented source, authorized use, retention/deletion policy, isolation policy, PII handling and auditability. Customer data never trains provider models or our models unless contract and policy explicitly permit it.
- An AI inventory (capability, tier, model, provider, data classes, owner) exists for audit and regulatory reporting (`skills/ai-governance/` AI BOM).

### G21 Honest disclosure and trust UX

Where users interact with generative AI or receive materially AI-generated content, say so clearly enough to avoid deception: role-appropriate, understandable, non-alarming, consistent with legal requirements. Users can tell **canonical fact · AI-generated explanation · AI recommendation · human decision** apart. Never fabricate certainty, hide material limitations, or imply human review that did not happen.

### G22 Accessibility of AI UX

AI-assisted UX meets the accessibility standard (toolkit bar: WCAG 2.2 AA, `skills/accessibility-audit/`): screen-reader support, text scaling, keyboard/focus semantics, contrast, captions/transcripts for audio, understandable error/degradation/handoff states, accessibility in every supported language. AI never creates an inaccessible alternate path for a core workflow.

### G23 Offline and intermittent connectivity (if applicable)

- Offline, AI degrades safely: last-known authorized context with its freshness, permitted writes queued through the existing sync/outbox, never fabricated fresh AI results, never cached AI output treated as current safety authority.
- Operations get stable operation ids at record time; the server defines per-operation conflict rules (dedupe by id, validate transitions against the state machine, append-once, versioned updates; never blind last-write-wins).
- Consequential queued actions are revalidated against current canonical (including safety) state on reconnect. Each queued action class declares `FAIL_CLOSED` or `SAFE_TO_DEFER` and carries `created_at`, `expires_at`, `canonical_version_at_creation`, `required_revalidation_domains[]`.
- No new online-only dependency in an offline-capable core workflow without explicit approval.

### G24 Measurable outcome

Before release define `baseline_metric`, `target_metric`, `measurement_method`, `evaluation_window`, `cost_to_serve` and the rollback/disable trigger. AI that is safe but delivers no measurable benefit is not kept enabled because it works. Use capability-specific operational and customer-value metrics, never one universal ROI threshold.

### §6 Merge requirements

Merge requirements for every AI-related change, human- or assistant-authored (assistants load this file through `rules/ai-engineering.md` and the AI skills). For T2/T3, release sign-off includes an **independent** owner (AI platform and/or domain owner); the implementing team is never the sole approver of its own safety or isolation gate.

1. Read the current production code and applicable Sources of Truth first. 2. Reuse existing frameworks, services and models before creating new ones. 3. Identify the canonical authority for every input and output. 4. Separate deterministic logic from AI reasoning. 5. Define typed, versioned contracts and validate them at runtime boundaries. 6. Define failure, degradation and human-exception behaviour. 7. Apply authorization and isolation before retrieval. 8. Minimize and classify data before any model call. 9. Add observability and provenance. 10. Add evals and regression tests (`skills/eval-guide/`). 11. Enforce payload-hashed idempotency for side effects; reject payload mismatch. 12. Apply cumulative token/cost/retry budgets across the whole execution tree. 13. Verify offline behaviour where an offline-capable workflow is affected. 14. Ship consequential changes behind feature flags with shadow evaluation and rollback. 15. Never claim production readiness without code + test + runtime evidence.

### §12 Final invariant

> We use AI to make work safer, faster, more explainable and more effective — never to create a parallel source of truth or bypass canonical authority.

`canonical truth → deterministic policy and authorization → retrieval / structured context → bounded AI assistance → validation → authorized workflow action → verification → observable outcome`

## Ten laws statements

The laws apply to every AI capability the organisation builds, buys or embeds; they are stable, and new risks become controls and evidence under an existing law, not new laws. A capability complies with a law only when the Decision Record gives it a control, an owner, evidence and a failure condition (four-element table above). A stricter companion rule may tighten a law; nothing weakens one.

| Law | Principle | Required controls | Guardrails: primary · supporting | Rule |
|---|---|---|---|---|
| L1 Understand before acting | Know the current business rules, workflows, permissions and system state before acting | Refresh and validate the authoritative state immediately before every consequential write; reject the action if state changed since the plan was formed | G1, G16 · G23 | Knowledge and fresh context precede action |
| L2 Respect authorization and delegation | Only actions policy permits and an authorized user validly delegated; every agent has its own identity and scoped, revocable authority | Server-side authorization on every action; scoped, expiring, revocable delegation; resource-level access checks; approvals bound to the exact action and parameters | G2, G9 · G18, G11 | Capability ≠ authority |
| L3 Ground decisions in trusted context | Authoritative, current, traceable information; retrieved information is evidence, not permission | Retrieval from approved sources only; provenance and freshness on every piece of context; injection and poisoned-context defences treating documents, emails, web pages and tool outputs as untrusted data | G14, G15, G9 · G16, G17 | Trusted data informs; untrusted content never grants authority |
| L4 Govern agent collaboration | All agents follow the same security, privacy, authorization and audit rules; delegation never expands permissions | Distinct agent identities; least-privilege delegation that only narrows the caller's scope; scoped short-lived credentials; authenticated inter-agent communication; end-to-end trace correlation across the agent tree | G5, G9, G13 · G8 | Delegation never escalates authority |
| L5 Never assume user intent | Distinguish intent, confirmation, organizational authorization and approval; consequential actions need the permission their risk requires | Risk-based confirmation (action tiers below); approvals bound to actor, resource, action, exact parameters and validity period; re-confirmation when parameters change | G2, G5 · G18, G21 | A request is not unlimited permission |
| L6 Explain decisions and actions | Important recommendations, decisions and actions are understandable, traceable and auditable without exposing confidential information | Structured decision records, policy and source references, trace ids, concise user-facing explanations that exclude secrets, other parties' data and sensitive internal logic | G8, G21 · G17, G3 | Transparency builds trust |
| L7 Safety overrides autonomy | Human safety, security and protection from material harm outrank speed, convenience and cost | Deterministic safety classification outside the model; approved emergency playbooks; fail-safe defaults; immediate human escalation; safety-recall release gates | G2, G7 (safety recall), G10 · G5, G6, G19 | Safety > automation > efficiency |
| L8 Verify business outcomes | Confirm the intended business outcome, not merely an API success | Technical, business, operational and semantic verification of results; status checks that handle asynchronous completion and eventual consistency ([read-back pattern](#l8-asynchronous-outcome-read-back)); no "done" message without outcome evidence | G3, G4, G7 · G24 | API success ≠ business success |
| L9 Fail safely and recover | Failures, timeouts, partial execution, retries and uncertain results cause no duplicate or harmful operation | Stable payload-bound idempotency keys; workflow-state reconciliation; bounded retries; documented recovery procedures; human escalation; a degradation path keeping the core workflow usable without AI | G4, G5, G6, G10 · G12 | Fail safely, recover predictably, never duplicate a consequential action |
| L10 Protect data end-to-end | Protect sensitive information through retrieval, reasoning, agent collaboration, tool execution, storage, memory and logging | Tenant/organization isolation, least privilege, authorization before retrieval, minimization before model calls, redaction, encryption, retention limits and audited access across prompts, embeddings, memory, traces and logs | G9, G15, G20 · G8 (trace privacy), G19 | Minimum necessary data, end-to-end protection |

Guiding principle: AI may observe, understand, reason, recommend and execute authorized actions; safety, authorization, consent, critical business rules and consequential writes stay under independently enforceable, auditable controls.

### Principles action tiers and the T-tier floor

Grade every **action** (tool) a capability can take at design time; the Decision Record lists each tool with its action tier. These are per-action consequence tiers, not the governance autonomy levels A0–A4 (per system): write "principles A3" or "governance A3".

| Action tier | Risk | Example | Minimum enforcement | Minimum T-tier of the capability |
|---|---|---|---|---|
| A0 | Read-only | look up an order status; answer a policy question | scoped access, isolation | T0 (T1 if users see the output or it contains PII) |
| A1 | Low | draft an email, open a draft support case | policy validation; human edits before send | T0 (T1 if users see the output or it contains PII) |
| A2 | Moderate | submit a request on the user's behalf | authorization + confirmed intent | T2 |
| A3 | High | approve spend, issue a refund, change access rights | explicit approval bound to exact parameters | T2 |
| A4 | Critical | terminate a contract, irreversible financial or HR action | human decision; dual control where justified | T2; T3 when sector-regulated or life-safety |
| Emergency | Safety-critical | threat to life or physical safety | deterministic safety protocol + immediate human escalation | T2; T3 when the capability's own output has life-safety impact |

Rule: **a capability's T-tier is at least the highest floor of any action it can take** (A2+ actions are side effects, a T2 trigger in §3). Assess the T-tier from §3 on its own too and record the higher. Emergency handling is a special path, not unrestricted authority: it may trigger approved safety workflows and guidance, but never bypasses financial, privacy or access controls because an emergency was declared. `/ai-launch-check` recomputes the floor from the Decision Record's tool list; a declared T-tier below it is ❌.

### Governance pipeline (laws per stage)

```text
User request / event
  ↓ 1. Understand and ground        L1, L3      fresh context, trusted sources, provenance, injection defence
  ↓ 2. Reason, delegate, recommend  L3, L4, L6  scoped agents, explainable recommendations
  ↓ 3. Deterministic enforcement    L2, L5, L7  safety · authorization · consent/approval, outside the model,
  ↓                                             immediately before consequential execution
  ↓ 4. Execute and verify           L2, L8      idempotent tools, business-state verification
  ↓ 5. Recover, audit, explain      L6, L9      safe retries, escalation, audit evidence, user explanation
L10 (data protection) applies across every stage, agent, tool, store and log.
```

### L8 asynchronous outcome read-back

A tool's success response proves the request was accepted, not that the business outcome happened. For any consequential action whose effect settles asynchronously (queued payments and refunds, workflow starts, external integrations, eventually consistent stores):

1. The tool returns `accepted` with an `operation_id` (or the idempotency key), never "done". The agent tells the user `PENDING_CONFIRMATION`, never a completion message.
2. Read back from the **system of record**, not the tool's own status cache: poll by `operation_id` with bounded backoff (ADAPT default: 1 s doubling to 30 s) up to a settle deadline per action class (ADAPT default: 5 min interactive, 24 h batch), or consume the domain's completion event. On an eventually consistent store read from the primary / read-your-writes path, or wait for record version ≥ the write's version; a replica miss means *pending*, never *failed*.
3. Verify all four: **technical** (the record exists), **business** (right entity, customer, amount and parameters: the record matches the approved payload hash), **operational** (exactly one record for the idempotency key, no earlier duplicate), **semantic** (terminal success state, not `queued` / `pending` / `partially_applied`).
4. All four pass → report `CONFIRMED` with the record reference. A mismatch → `OUTCOME_MISMATCH`, route to human review / compensation (G4 saga), never "done". Settle deadline passed with no terminal state → `OUTCOME_UNKNOWN`, route to reconciliation; never re-issue the side effect blindly (G4: revalidate canonical state first).

Executable evidence: contract tests `test_async_action_is_pending_until_outcome_read_back` and `test_unverified_async_outcome_is_never_reported_done` in `skills/ai-launch-check/assets/guardrail_contract_tests.py`. Failure condition: a "done" / `CONFIRMED` message is emitted before the read-back passes.

## Adoption checklist (organisation-owned)

The toolkit supplies patterns, templates and tests; these are decisions and records only the organisation can own. They are never automated enforcement, and `/ai-launch-check` only checks that the Decision Record names them.

- [ ] Ratify the ten laws at executive / architecture-board level and publish G1–G24 as a mandatory standard; absorb new risks as controls and evidence under an existing law, not as new laws.
- [ ] Fill in every ADAPT item: tier examples (§3), audience boundaries (G18), action-tier examples and owners (principles action tiers), regulated domains, eval thresholds per use case (G7), L8 settle deadlines per action class.
- [ ] List the specialised Sources of Truth that win where stricter (§10): AI capability strategy, domain architecture, security and data classification, privacy/retention policy, legal and compliance policy, model/vendor approval process, design system/accessibility, human exception operations, incident management, offline/sync architecture (if any).
- [ ] Name owners and keep production evidence for each §10 platform prerequisite: shared PII/secret redaction service, AI gateway / policy enforcement layer (owner, SLO, versioning, capacity, failure mode), idempotency store and semantics, human exception operations capacity model, shared authorization/isolation primitives, approved model/provider registry and AI inventory, observability stack with trace-privacy controls.
- [ ] Name a person (not a team) per law per capability (four-element rule) and the platform owner of the shared schema/tool registry (G3).
- [ ] Safety taxonomy: owner, version, review cadence, change control (G7); approved emergency playbooks and human escalation capacity (L7); dual control for principles A4 actions.
- [ ] Kill switch: owner, audited activation, runbook, drill cadence, recovery checklist, communication path (G10).
- [ ] Human exception queues: owner, SLA, escalation, capacity, priority classes, overflow and load-shedding policy (G5); reserved provider capacity for critical paths.
- [ ] Model/provider approval and retirement criteria, vendor risk and data-processing review, training-data policy, contractual no-training terms (G20).
- [ ] Protected characteristics and prohibited proxies per jurisdiction, owned by Legal/Compliance (G19); AI disclosure wording checked against legal requirements (G21).
- [ ] Scoped short-lived credentials and authenticated inter-agent channels (L4); encryption, retention values and audited access for prompts, embeddings, memory, traces and logs (L10).
- [ ] Waiver approvers independent of the team (security / AI platform; Legal for T3) and an expiry review routine (§11).
- [ ] Map the laws and guardrails to the external frameworks regulators expect, e.g. NIST AI RMF, OWASP Top 10 for LLM and agentic applications (ADAPT; regulatory register in `skills/ai-governance/`).
