# AI incident runbook: types I1–I11, playbooks and toolkit map

This file is the canonical AI incident runbook. It sits on top of the enterprise incident process (ticket, paging, status page) and maps each element to the toolkit control, test or record that carries it: types and severity (§1, §6), containment ladder and drills (§2, §7), playbooks with numbered steps (§3, §8), evidence (§9), notification decisions D1–D6 (§10), recovery verification (§11), closure (§4, §12), post-incident review (§13), anti-patterns (§14) and the organisation adoption checklist (§15). Section numbers below refer to this file. Paths are under `.claude/` unless they start with `docs/`.

## 1. Types, categories and severity

| Runbook type (§6) | Governance category (`incident_record.category`, §13.1) | Severity floor (§6) |
|---|---|---|
| I1 harmful / unsafe output | AI-EVAL (AI-SEC when adversarial) | S2 single user on T0/T1, contained; S0 on a safety-critical (T3) path |
| I2 hallucination with impact | AI-EVAL | S1 when acted on at scale; a canonical write driven by the claim ⇒ S1 minimum (G2/G3 failure) |
| I3 data leakage / cross-tenant | AI-TENANT or AI-DATA | **S0** until scope is proven smaller (validator: unblocked AI-TENANT or I3 ⇒ S0) |
| I4 prompt-injection campaign | AI-SEC | S2 rising without success; S0 with confirmed success |
| I5 unauthorized tool action | AI-ACTION (AI-OVERSIGHT if an approval was bypassed) | S0 for a write with external or financial effect; S1 contained before effect |
| I6 cost runaway | AI-COST | S1 above `<5×>` budget rate; S2 `<1.5–5×>` |
| I7 quality regression / drift | AI-EVAL | S1 on a critical sub-threshold breach; else S2 |
| I8 provider outage | AI-PROVIDER | S0 platform-wide on T2/T3 with no working degradation; S1 with a working fallback |
| I9 bias / discrimination complaint | AI-EVAL (+ Legal) | S0 for T2/T3 decisions about people until assessed |
| I10 model / prompt deployment error | AI-EVAL (AI-SUPPLY when an unverified artifact shipped) | S1 on a T1+ path |
| I11 RAG index corruption / poisoning | AI-DATA (AI-SEC when malicious, AI-MEM for memory stores) | S1 for a user-facing corpus |

S0–S3 = SEV-1–SEV-4 (playbook) = SEV1–SEV4 (runbook) = P0–P3 (eval flywheel), with the stricter time of each source per row: `skills/ai-governance/reference/supply-chain-eval-and-release.md` §7.1. A T3 capability is one row more severe. Several types ⇒ highest severity, every matching playbook (record all in `incident_types`).

## 2. Containment ladder (§7) and kill-switch drills (§15)

| Rung | Toolkit mechanism | Tested by the toolkit (template, run in your service) | Organisation adopts |
|---|---|---|---|
| 1 capability flag | flag read server-side per request, recorded on the span: `skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` §5 | `test_kill_switch_disables_ai_and_core_workflow_completes` (per-capability scope), degraded contract `test_provider_outage_uses_approved_fallback` | flag per T1+ capability, owner |
| 2 prompt label rollback | move the registry label, never edit the production prompt: `skills/eval-guide/reference/langfuse-prompts.md` (Lifecycle and promotion); confirm served version on spans (`llmops-release-and-rollout.md` §9) | prompt regression test (`langfuse-prompts.md`), eval gate before re-promotion | label rights, drill |
| 3 model pin | pinned ids, no floating alias: `skills/agentic-ai-dev/reference/llm-inference-and-model-routing.md` §2, §6 | `test_unapproved_or_floating_model_is_rejected` | approved-model registry, drill |
| 4 tool disable | capability allowlist / gateway deny: `skills/agentic-ai-dev/reference/tool-execution-safety.md` §2, §11 | `test_tool_outside_capability_allowlist_is_denied` | gateway deny path, drill |
| 5 platform kill switch | G10: `skills/ai-playbook/reference/engineering-guardrails.md` G10, playbook §4.4 | `test_kill_switch_disables_ai_and_core_workflow_completes` | per-product switch, named owner, audited activation |

Contract tests live in `skills/ai-launch-check/assets/guardrail_contract_tests.py` (and `guardrail-contract.test.ts`). They are adapter-driven templates: they prove a lever in **your** service only after you wire the adapter and break the control once (negative control). Drill cadence, production drills, time-to-effect targets (`<5 min>`, `<15 min>`), tabletop rotation through I1–I11 and the drill record are **organisation adoption**; a failed drill is an S2 incident. Lever pulls are logged in `incident_record.containment_levers` (who, when, rung, scope, reason; rung 4–5 needs `authorized_by`).

## 3. Playbooks

Every row inherits: open the ticket, name the IC, capture evidence (§9) **before** any purge, rollback, re-index or rotation, decide notifications (§10). Recovery always runs the §11 checklist (`incident_record.recovery_verification`) and progressive re-enable.

| # | Detection signal | Contain (rung) | Evidence to capture | Recovery verification | Permanent regression test (§12) |
|---|---|---|---|---|---|
| I1 | user report, safety-classifier flag, canary | 1 (2–3 if shared prompt/model) | output, input, trace id, prompt/model versions, classifier verdicts | safety recall 100% on the critical set; fail-before/pass-after | safety / compliance adversarial set: `skills/eval-guide/reference/red-teaming.md`, `redteam_case.schema.json` with `source: incident:<id>` |
| I2 | user report, `hallucination_flag_rate`, override spike | 1 or forced cite-or-decline | output, retrieved context ids, citations, canonical state at the time | faithfulness ≥ threshold (`skills/rag-evaluator/`); groundedness sampling raised for the window | RAG golden set with `required_context_ids` / `forbidden_context_ids` (`rag_case.schema.json`); abstain test `test_no_evidence_returns_not_found_not_a_guess` |
| I3 | `isolation_violation_total > 0`, isolation canary | 1; 5 when the cause is shared (cache, retrieval, gateway, memory) | leak channel, exposed records, tenants, window, the scope query | isolation suite + red-team isolation set green; canary green `<24 h>` | deterministic cross-scope test for the exact channel: `test_cross_scope_query_returns_nothing_from_other_org`; cache keys `llm-inference-and-model-routing.md` §8 |
| I4 | `injection_attempt_rate` spike, red-team canary | gateway block / rate limit; quarantine source; 4 or 5 on generic success | attempt traces clustered by payload, channel, target; attempts vs successes | zero successes on the new payload set in R1 and R2 | red-team corpus (payload + channel), regression forever (GD021); `test_injected_instruction_in_retrieved_content_triggers_no_tool` |
| I5 | tool-auth denial anomaly, audit-log review, canary | 4 (5 for several tools); freeze stale AI intents | tool audit log entries (caller, scope, input, authz result, side effect, idempotency key) | contract + auth + security layers green; audit log reconciles with canonical state | tool suite case (`tool_case.schema.json` `auth_fail` / `scope_mismatch` / `unsafe_call`); `test_high_consequence_tool_without_approval_is_not_executed`, `test_human_override_rejects_late_ai_retry` |
| I6 | cost anomaly, budget burn, quota warning | gateway budget/rate cut; 1 for the top spender; 5 if unbounded | spend by capability, org, model, route, tool | cost per successful outcome ≤ `<1.2×>` baseline for `<24 h>` | budget/loop test `test_cumulative_budget_exhaustion_stops_and_routes_to_human`; budgets `llm-inference-and-model-routing.md` §9 |
| I7 | eval drift vs anchor, SLO burn, override rise | 2 or 3 when a change correlates; else 1 per segment | online-eval scores vs current / previous / anchor baselines; versions bisected | nightly R2 green; online eval in tolerance `<7 days>` | feature golden set slice for the new distribution (`skills/eval-guide/reference/golden-dataset.md`); baseline gate `scripts/eval_gate.py` |
| I8 | error / latency alerts, provider status, fallback rise | confirm G6 degradation; else 1 or approved fallback that passed the same safety gate | provider, region, model, capability scope; silent version change? (→ I7/I10) | golden smoke set on the primary path; fallback rate at baseline | failure-injection test: `test_provider_outage_uses_approved_fallback`, `test_fallback_without_safety_gate_degrades_to_non_ai` |
| I9 | complaint, fairness monitor | 1 and route to the human path; Legal first | complainant interaction and decision record under legal hold | fairness metrics within ratified bounds; Legal/Compliance approval | paired-input cases differing only in the protected attribute or proxy (eval fairness slices); protected attributes are jurisdiction-specific (Legal) |
| I10 | post-deploy canary, Git ↔ registry drift, error spike after a change | 2 or 3 or routing rollback; freeze promotions | Git ↔ registry content hash ↔ `production` label; traces by `prompt_version` / `model_version` | drift check clean; post-deploy canary green; re-promoted through the pipeline only | pipeline / promotion-gate test that blocks the error class (`llmops-release-and-rollout.md` §3, `langfuse-prompts.md` prompt regression test) |
| I11 | retrieval-eval drop, `rag_no_answer_rate`, poisoning canary, ingestion audit | quarantine source; 1 for capabilities on the corpus | index snapshot id, ingestion logs, chunk ids served and recipients | retrieval evals at baseline; blue/green index swap, old index read-only until verified | forbidden-context-id cases; deletion test `test_deleted_source_not_retrievable_after_sla`; ingestion screen `test_secret_bearing_text_is_excluded_from_index`; triage `skills/rag-debugger/`, controls `skills/rag-security-reviewer/` |

Trace and version fields to read: `skills/deployment-ci-cd/reference/ai-observability.md` §6, §10. Evidence privacy (access-controlled store, redaction, legal hold, sanitized regression cases): §9, `.claude/skills/ai-playbook/reference/data-governance-privacy.md`, eval strategy §7.11 (`skills/eval-guide/reference/golden-dataset.md`).

## 4. Closure and record

Closure (§12) is enforced on `incident_record` by `skills/ai-governance/scripts/validate_governance_record.py`: a closed record needs a `regression_case` that is either the `production_regressions/INC-YYYY-NNN.yaml` file (fails on `pre_fix_run_id`, passes on `post_fix_run_id`, listed in `preventive_test_cases`) or, only when not reproducible, a monitored detector with a reason and owner sign-off. Pass `--regressions-root tests/golden/production_regressions` to prove the file exists and declares the same `incident_id`. The file itself is validated by `skills/eval-guide/scripts/validate_golden.py` (schema `regression_case.schema.json`, GD017 naming and SLA, GD021 never deleted). No LLM judge decides closure or authorizes a lever.

Organisation adoption (not provable by the toolkit): named rotas and the IC ≠ AI on-call rule (§15), detection-source routing (§15), notification decisions D1–D6 and every deadline (§10, Legal owns), PIR publication and action owners (§13, §15), incident metrics MTTD / MTTC / MTTR (§15), runbook ownership and review cadence (§15).

## 5. Purpose, precedence and lifecycle

- **Precedence:** where the enterprise incident policy, security incident policy or privacy breach procedure is stricter, it wins. Security and privacy incidents run under their owning procedure **and** this runbook, never only one of them. **Must / must not** = mandatory; **should** = default, a deviation needs a recorded reason; **may** = optional.
- **First principle: stop the harm first, explain it second.** Containment (§7) is authorized before root cause is known. A wrongly pulled lever costs degraded UX; a wrongly delayed one costs users, data or trust.
- **Scope:** every production AI capability of risk tier T0–T3, including background AI jobs, tool/MCP servers and AI-assisted UX.

```text
DETECT → TRIAGE/DECLARE → CONTAIN → ASSESS → MITIGATE → RECOVER → VERIFY → CLOSE → REVIEW
                             ↑_________ re-contain if verification fails _________|
```

| Phase | Goal | Exit criterion |
|---|---|---|
| Detect | signal reaches a human | alert acknowledged or report triaged |
| Triage / declare | AI incident? assign type(s) and severity (§6) | ticket open, IC named, channel open |
| Contain | stop ongoing harm, even at the cost of capability | harm rate zero or bounded; lever recorded |
| Assess | scope: who, what data, which versions, since when, how many | blast radius written down with evidence |
| Mitigate | remove the cause (fix, rollback, re-index, block) | candidate fix verified offline |
| Recover | restore capability safely and progressively | capability back at normal exposure |
| Verify | prove it is fixed (§11) | evals green, canaries clean, metrics at baseline |
| Close | closure criteria (§12) | regression case merged; notifications decided |
| Review | learn and prevent (§13) | review published; actions owned and dated |

**Timeline discipline:** the scribe records, in UTC, every observation, hypothesis, decision and lever pull with who did it. Lever pulls also appear in the flag/registry audit log; the two must reconcile at review.

## 6. Incident taxonomy and severity criteria

An **AI incident** is any event in which an AI capability causes, or credibly could cause, harm to users, customers, third parties, the enterprise or its data, or in which an AI control (guardrail, eval gate, isolation boundary, budget, kill switch) fails. A **near-miss caught by a control is still recorded** (SEV4 unless criteria say otherwise).

| # | Definition |
|---|---|
| I1 | output that is toxic, dangerous, self-harm-enabling, illegal, or unsafe advice inside a G18 "must not" boundary |
| I2 | an unsupported claim that a user, operator or downstream system acted on, or that contradicts canonical state |
| I3 | data from one tenant, org, user or classification scope reaches an unauthorized party (answer, snippet, count, citation, log, trace, cache) |
| I4 | repeated or coordinated attempts (direct, or indirect via content) to steer the model, with or without success |
| I5 | a tool call executed outside its authorization, scope, transition rules or intended trajectory |
| I6 | token, request or spend rate far above budget: loops, retries, abuse, misrouting to an expensive model |
| I7 | a sustained drop in task success, grounding or escalation correctness vs baseline, with or without a deploy |
| I8 | model, embedding or managed AI service unavailable, degraded, rate-limited or silently changed |
| I9 | a credible claim that output treated people differently on a protected characteristic or proxy (G19) |
| I10 | wrong model, prompt version, label, routing rule, schema or config reached production |
| I11 | corpus holds wrong, stale, malicious, mis-scoped or deleted-but-retained content, or an embedding/index mismatch |

**ADAPT:** add product-specific types (generated-UI abuse, voice/OCR injection, mis-routed outbound message) with the same columns. **Not an AI incident:** a non-AI outage the AI merely depends on (enterprise process); a single low-quality answer with no impact and no pattern (quality feedback queue).

Severity is set by the **worst credible impact**, not by what is confirmed so far. Any one criterion is enough (ADAPT; defaults to ratify; response times are in the crosswalk `skills/ai-governance/reference/supply-chain-eval-and-release.md` §7.1):

| Level | AI-specific criteria |
|---|---|
| SEV1 (S0, P0) | any confirmed cross-tenant / cross-scope exposure · personal or regulated data sent to an unapproved provider · harmful output in a safety-critical (T3) path · unauthorized **write** tool action with external or financial effect · injection campaign with confirmed success · platform-wide AI outage on a T2/T3 path with no working degradation · credible discrimination in a T2/T3 decision |
| SEV2 (S1, P1) | hallucination acted on at scale or in a consequential decision · unauthorized tool action contained before external effect · cost runaway > `<5×>` budget rate or projected over the monthly budget within `<24 h>` · drift breaching a critical sub-threshold · deployment error on a T1+ path · provider outage with degraded but working fallback · poisoned or mis-scoped content in a user-facing corpus |
| SEV3 (S2, P2) | regression within aggregate tolerance but outside SLO · injection attempts rising without success · cost overrun `<1.5–5×>` budget rate · stale or incorrect content in a low-impact corpus · single-user harmful output on a T0/T1 path, contained |
| SEV4 (S3, P3) | near-miss caught by a control · isolated low-impact error · drill finding · eval flake with an incident-worthy pattern |

Rules: **declare high, downgrade only with evidence, never the reverse**; isolation and egress events start at SEV1 until scope is proven smaller; a T3 capability is at least one level higher than the same event on T0/T1; one incident spanning several types takes the highest severity and runs every playbook; every severity change is logged in the ticket with its evidence; use one vocabulary in tooling and record the SEV ↔ P mapping if both are kept.

## 7. Containment rules and supplementary levers

Pull the **lowest rung (§2) that stops the harm**; climb when it does not. Each rung must be operable in minutes, without a code deploy, by the AI on-call.

- Every rung **must** exist for every T1+ capability before it goes live (verified by §15 readiness and drills).
- Any responder **may** pull rungs 1–3 without waiting for the IC when harm is ongoing and informs the IC at once; rungs 4–5 need IC authorization, or the documented delegate when the IC is unreachable for > `<10 min>` (`incident_record.containment_levers[].authorized_by`).
- Every pull **must** be logged: who, when, rung, scope, reason, incident ID.
- A pull **must not** disable deterministic safety logic, canonical workflow access or audit logging.
- Degradation **must** be visible to users (G6); never silently swap in a weaker path.
- After a pull, watch the harm signal for at least `<one alert window>` before moving to Assess.
- Lowering a rung happens only in Recover, after §11.

**Supplementary levers** (alongside any rung): tenant/user/IP rate limits or blocks at the gateway · lower per-org budgets · quarantine a corpus or source from retrieval · purge caches (response, retrieval, semantic) after evidence capture · revoke/rotate credentials · switch to the approved fallback provider only if it passed the same safety gate (G6).

## 8. Playbook steps I1–I11

Each playbook runs Contain → Assess → Mitigate → Recover → Verify; steps are numbered so the scribe can write "I3 step 4 done 14:22 UTC". All inherit: open the ticket, name the IC, preserve evidence (§9) before any purge, decide notifications (§10).

- **I1 harmful output:** 1 rung 1 for the capability, tenant or segment (rungs 2–3 if a shared prompt/model) · 2 capture output, input, trace ID, versions, classifier verdicts · 3 single case or pattern? query similar traces over `<7 days>`; adversarial input ⇒ also I4 · 4 name the failed control (missing intercept, classifier miss, G18 boundary not encoded, fallback without safety gate) · 5 affected users; anyone acted on unsafe advice ⇒ Legal + capability owner outreach · 6 strengthen deterministic intercept or classifier, tighten prompt, add to the safety set · 7 re-enable internal → `<5%>` → full, watching safety flags · 8 safety recall 100% on the critical set; fail-before/pass-after.
- **I2 hallucination with impact:** 1 rung 1 if it can recur (or force cite-or-decline) · 2 capture output, context IDs, citations, canonical state · 3 root type: retrieval miss, grounding failure, stale content (G16), unsupported generation · 4 who acted, what changed; a canonical write driven by the claim is a G2/G3 failure ⇒ SEV2 minimum · 5 fix retrieval, freshness or grounding; enforce citations or abstention (G17) · 6 correct downstream effects through normal authorized workflows, **never an AI-driven bulk fix** · 7 progressive re-enable with groundedness sampling `<10%>` for `<72 h>` · 8 faithfulness ≥ threshold; case in the RAG golden set.
- **I3 leakage / cross-tenant:** 1 declare SEV1; Security, Privacy, Legal at once · 2 rung 1; rung 5 if the cause is shared (retrieval, cache, gateway, memory) · 3 purge/quarantine caches (response, retrieval, semantic, session memory) **after** evidence capture · 4 leak channel: answer, snippets, citations, counts/facets, nearest neighbours, related-entity traversal, logs, traces, exports (G9) · 5 enumerate records, owning tenants, recipients and window; keep the re-runnable query · 6 personal/regulated data ⇒ Privacy runs the breach procedure in parallel · 7 fix authorization-before-retrieval **in code, never by prompt**; add the missing filter at store or gateway · 8 isolation suite + red-team isolation set green; isolation canary green `<24 h>` on staging-shaped traffic · 9 `isolation_violation_total` = 0 since fix; cross-scope negative fixture for the exact channel · 10 notification decisions confirmed with Legal.
- **I4 injection campaign:** 1 block or rate-limit attacking identities, tenants, sources at the gateway; any tool steered ⇒ also I5 · 2 stored/retrieved payload ⇒ quarantine source documents · 3 non-zero success with a generic vector ⇒ rung 4 or 5 · 4 cluster attempt traces by payload, channel (user text, upload, retrieved content, tool output, OCR/voice), target; count attempts vs successes · 5 attacker objective (exfiltration, tool misuse, policy bypass, cost amplification) and what resulted · 6 harden instruction hierarchy, filters and tool authorization in code; payloads into the red-team corpus · 7 lift blocks gradually; elevated injection canary for `<7 days>` · 8 zero successes on the new payloads in R1 and R2; `injection_attempt_rate` at baseline.
- **I5 unauthorized tool action:** 1 rung 4 (gateway deny); several tools ⇒ rung 5 · 2 freeze pending AI intents and delayed retries (human override cancels stale AI intent, G5) · 3 from the tool audit log list every call: caller, scope, input, authz result, side effect, idempotency key · 4 classify: authorization bug, scope-ID confusion, missing transition check, injection-steered, idempotency failure (G4) · 5 reverse or compensate **through the domain's compensation workflow with a human approver, never another autonomous agent run** · 6 fix the check in code; negative case into the tool suite · 7 re-enable behind the flag for internal scope first · 8 contract + auth + security layers green; canary clean; audit log reconciles with canonical state.
- **I6 cost runaway:** 1 lower the org/capability budget or rate limit at the gateway; unbounded and unknown source ⇒ rung 1 for the top spender, then rung 5 · 2 break spend down by capability, org, model, route, tool · 3 cause: loop (budget not enforced), retry storm, expensive routing, context bloat, cache failure, abuse · 4 spend to date and projected if uncontained; FinOps engages the provider for quota/credit · 5 enforce cumulative execution-tree budgets, fix routing, restore cache, block abuse · 6 restore limits stepwise watching burn rate · 7 cost per successful outcome ≤ `<1.2×>` baseline for `<24 h>`; a test proves the budget stops the loop.
- **I7 quality drift:** 1 change correlates ⇒ rung 2 or 3; else rung 1 per segment when a critical sub-threshold breaches · 2 compare online-eval and outcome metrics with current, previous and anchor baselines · 3 bisect prompt, model, retrieval config, corpus, tool surface, routing, upstream data, input-language mix · 4 sample failing traces to human review; label failure modes · 5 fix; for distribution shift extend the golden set **before** any fix · 6 progressive rollout with shadow evaluation · 7 nightly R2 green, online eval in tolerance `<7 days>`, SLO burn normal.
- **I8 provider outage:** 1 confirm G6 degradation engaged; else rung 1 or the approved fallback **only if it passed the same safety gate** · 2 shed non-critical AI load (batch, low priority) to protect critical capacity · 3 scope provider, region, model, capability; silent behaviour/version change ⇒ also I7/I10 · 4 track provider status; FinOps records SLA credit eligibility · 5 broken degradation path ⇒ a follow-up of equal severity · 6 restore gradually; watch error rate, latency and cost (recovery retries spike cost) · 7 golden smoke set on the primary path; fallback rate at baseline.
- **I9 bias / discrimination:** 1 Legal/Compliance immediately; SEV1 for T2/T3 decisions about people until assessed · 2 credible + decisions about people ⇒ rung 1, route to the human path · 3 complainant interaction and decision record under legal hold · 4 reproduce with paired inputs differing only in the protected attribute or proxy; run the fairness evaluation (G19) · 5 look for proxies in retrieved content, ranking features, prompts, tool outputs, not only the model · 6 remove proxy/feature, add a deterministic detector, strengthen the rubric; Legal decides remediation for individuals · 7 recover only after fairness tests pass and Legal/Compliance approve · 8 paired-input regression cases; fairness metrics in ratified bounds on the full set.
- **I10 deployment error:** 1 rung 2 or 3 or roll back routing/config; freeze promotions · 2 compare Git ↔ registry content hash ↔ `production` label and deployed routing/config · 3 why gates missed it: skipped eval, wrong dataset version, label moved manually, `latest` alias, untested config path · 4 scope traces by `prompt_version` / `model_version` · 5 fix the change and the gate · 6 re-promote through the normal pipeline, **never a manual label move during the incident** · 7 drift check clean, post-deploy canary green, a pipeline test proves the gate blocks the class.
- **I11 index corruption / poisoning:** 1 quarantine source(s) or corpus; cannot filter ⇒ rung 1 for capabilities using it · 2 snapshot index state and ingestion logs before re-indexing · 3 classify: malicious insertion, ACL metadata loss, stale versions, deleted-but-retrievable, embedding/version mismatch, chunking bug · 4 ingestion path and contributor; poisoning ⇒ Security leads, also I4 · 5 answers served from bad chunks and recipients; mis-scoped ⇒ also I3 · 6 fix ingestion validation, ACL or deletion propagation (G15); versioned re-index from authoritative sources · 7 blue/green swap; old index read-only until verified · 8 retrieval evals at baseline; forbidden-context-ID cases pass; deletion test proves removal.

## 9. Evidence preservation

Preserve **before** purge, rollback, re-index or rotation; collect by reference (IDs, hashes, versions), not by copying content.

| Evidence | Capture | Source |
|---|---|---|
| Traces | trace IDs, full span tree, timing, error and fallback path | trace store |
| Versions | prompt name/version/label, model + version, routing policy, retrieval config, embedding model, tool-surface hash, schema versions, flag states | registry, config history, span attributes |
| Datasets | golden/eval dataset version in force; last green eval run IDs | eval reports |
| Retrieval | chunk IDs, source document versions, index snapshot ID | retrieval logs, index |
| Tool actions | audit-log entries for every call in scope | tool audit log |
| Lever pulls | flag, label, pin and kill-switch change log | flag service / registry audit |
| Cost | spend by capability/org/model for the window | billing export, cost metrics |
| User reports | report text, timestamps, linked trace IDs | support tooling |

Privacy constraints (mandatory): evidence stays in the **access-controlled incident store**, scoped to responders, never pasted into chat channels, broad tickets or external tools · apply minimization and redaction (G8, G9); raw personal data is retained only when Privacy/Legal decide it is necessary, with access audited · legal hold suspends normal trace/log retention deletion for the scoped records and is lifted explicitly at closure · data copied from a tenant stays under that tenant's isolation and residency rules · regression cases derived from evidence are sanitized before entering Git (`skills/eval-guide/reference/golden-dataset.md`).

## 10. Communication and notification

Internal update cadence per level is in the crosswalk (`supply-chain-eval-and-release.md` §7.1: SEV1 every `<30 min>` until contained then `<2 h>`; SEV2 every `<2 h>`; SEV3 daily; SEV4 in ticket). SEV1 audience: exec sponsor, Security, Privacy, Legal, Comms, capability owners; SEV2: engineering leads, capability owners; SEV3/4: owning team. Each update states what is known, what is not, current lever, user impact, next update time; no root-cause speculation in broad channels.

The IC drives external decisions; **Legal/Compliance owns the outcome for anything regulatory or contractual**. Windows vary by jurisdiction, sector and contract: **confirm every deadline with Legal; this runbook asserts none.**

| Decision | Question | Decides | Inputs |
|---|---|---|---|
| D1 status page | customer-visible capability degraded or disabled? | Comms + IC | §7 lever state |
| D2 affected users | identifiable users received harmful, false-and-acted-on, or other-party data? | capability owner + Legal | §9 scope query |
| D3 customers (tenants) | a customer's data, users or contracted service affected? | customer success + Legal | contract notification terms |
| D4 regulators / authorities | meets a regulatory reporting definition (breach, AI-specific, sector)? | **Legal / Privacy only** | data classes, jurisdictions, counts |
| D5 providers / partners | provider caused it or must act (deletion request, abuse report)? | AI platform + Legal | DPA terms |
| D6 public / media | holding statement required? | Comms + Legal + exec | external visibility |

Rules: record each decision, **including "no notification"**, with who, when and why · describe the system failure and corrective action, never "the AI decided" (G21) · Legal reviews customer and user messages before sending for SEV1/SEV2 and every I3/I9 · never promise a root cause, timeline or remedy the IC has not confirmed.

## 11. Recovery verification

Lowering a rung requires **all** applicable checks (record each in `incident_record.recovery_verification` as pass with evidence or not_applicable with a reason):

```text
□ Fix merged through the normal pipeline (no manual production edits left in place)
□ R1 gates green for the affected paths
□ Full R2 suite green for the affected capability, incl. critical sub-thresholds
□ New regression case fails on pre-fix version, passes on post-fix version (§12)
□ Canaries for the incident type clean for ≥ <one canary cycle> (isolation, injection, tool, compliance)
□ Online-eval sampling raised for the recovery window; scores within tolerance
□ Error, fallback, override, cost and latency metrics at baseline
□ Progressive re-enable: internal → <5%> → <25%> → 100%, with a hold period at each step
□ Capability owner approves; Security/Legal approve where they were engaged
□ Degraded-mode messaging removed; status page updated
```

Any check failing during re-enable ⇒ return to the previous rung immediately and re-enter Assess.

## 12. Closure criteria

**No AI incident closes without a regression case** (mechanics and validator: §4): evidence → sanitized case → `production_regressions/INC-YYYY-NNN.<ext>` → fails on pre-fix (run ID) → passes on post-fix (run ID) → permanently in the CI matrix for the area. Landing set per type is the last column of §3 (I1/I9 safety-compliance-fairness set · I2/I11 RAG golden set · I3 isolation set + deterministic cross-scope test · I4 red-team corpus · I5 tool suite · I6 budget/loop test · I7 feature golden slice · I8 failure-injection test · I10 pipeline/promotion-gate test).

Also required: every lever restored or deliberately left in place with an owner and review date · notification decisions recorded (§10) · legal-hold disposition recorded · PIR scheduled (§13) · incident cost recorded. A case that cannot be reproduced deterministically still gets a regression entry (a monitored detector or canary with a documented reason); "could not reproduce" closes only with Security/AI-quality owner sign-off.

## 13. Post-incident review

Blameless; **required for SEV1–SEV2, recommended for SEV3, sampled for SEV4**; published within `<5 business days>` of closure (SEV1) / `<10>` (SEV2). Template: SKILL.md Stage 4 step 10 (summary, impact, UTC timeline, versions in force, root cause and contributing factors, detection, containment review, what went well/hard, action items, regression case, D1–D6 notifications). Rules: every action item has a **named person** and a due date (never a team) · at least one action targets **detection** time · repeat incidents of the same class escalate the review to the AI governance forum.

## 14. Anti-patterns

Waiting for root cause before pulling a lever · fixing a leak or authorization gap with a prompt instead of code · purging caches, re-indexing or rotating before evidence capture · pasting raw user data, traces or leaked content into broad channels or tickets · rolling back by editing the production prompt instead of moving the label · re-enabling at 100% in one step · using an autonomous agent to remediate damage an agent caused · treating a fallback model as safe without the same safety gate · downgrading before scope is proven, or upgrading only after customers complain · closing without a fail-before/pass-after case · "the model hallucinated" as root cause (the root cause is the missing control) · kill switches never drilled · committing to notification timelines without Legal · PIR actions owned by teams instead of people.

## 15. Adoption checklist (organisation-owned)

The toolkit cannot enforce these; the organisation ratifies them, replaces every `<placeholder>`, links the runbook from on-call tooling and runs the first kill-switch drill before declaring adoption. It sits on top of the existing incident ticket, paging and status-page tooling.

**Detection routing** (every source has a documented route into the ticket system; support triages a report mentioning another person's data, a dangerous instruction or discrimination as a **candidate SEV1/SEV2**, not feedback):

| Source | Owner | Expected lag |
|---|---|---|
| real-time alerts (isolation, hallucination flags, fallback, cost, latency) | platform on-call | minutes |
| canaries (isolation and injection/unauthorized-tool hourly, compliance daily, post-deploy golden replay) | security / AI platform | ≤ canary interval |
| online evaluation (sampled judge/rubric, groundedness drift, escalation correctness) | AI quality owner | hours |
| eval drift (nightly R2 vs current / previous / anchor baseline) | AI quality owner | ≤ 24 h |
| user reports (report-this-answer, thumbs-down with reason, support, social) | support → AI on-call | variable |
| customer / partner reports (account managers, contractual channels) | customer success | variable |
| red team (scheduled R2/R3, external researchers, bug bounty) | security | per cadence |
| audit / access review (tool audit log, trace access, ingestion audit) | security / data governance | periodic |
| provider notices (status, deprecation, incident, quota) | AI platform | variable |
| finance (invoice or billing anomaly, cloud budget alert) | FinOps owner | hours–days |
| regulator / legal (complaint, inquiry, legal hold) | Legal | variable |

**Roles** (named rota, not a team name): Incident Commander (owns severity, decisions, containment authorization, comms cadence, hand-offs, closure; does not debug) · AI on-call (traces, versions, flags, eval replay; operates the ladder) · platform on-call (infrastructure, gateway, provider connectivity, deploy rollback, capacity) · Security lead (required for I3, I4, I5, I11 poisoning and any SEV1; attacker analysis, credential rotation, forensic scope) · Privacy (whenever personal data may be involved; breach procedure) · Legal/Compliance (I3, I9, any T3 capability, every external notification decision) · Communications lead (status page, customer and internal messaging from IC-confirmed facts) · capability owner (per AI inventory; approves user-visible degradation and recovery) · scribe (assigned by IC) · FinOps owner (I6; spend, quota, credits). Rules: **IC and AI on-call are different people for SEV1/SEV2**; shift hand-offs are written in the ticket (current severity, active levers, open questions, next decision).

**Drill program** (staging by default; a production kill-switch drill at least annually in a low-traffic window with announced messaging; each drill records date, lever, time-to-effect, issues, fix owner; **a failed drill is a SEV3 incident**; new T2/T3 capabilities drill rung 1 at minimum before first production exposure):

| Drill | Scope | Cadence | Pass criterion |
|---|---|---|---|
| capability flag off/on | each T1+ capability | quarterly | degradation works; user messaging shown; core workflow completes |
| prompt label rollback | each production prompt family | quarterly | served within `<5 min>`, no deploy |
| model pin | each model route | semi-annually | previous approved model serving within `<15 min>` |
| tool disable | each write tool | semi-annually | gateway denies; agent takes human/read-only path |
| platform kill switch | each product (and provider) | semi-annually + after major architecture change | all AI paths off within `<5 min>`; deterministic workflows complete; audit entry written |
| provider failover | each fallback pair | semi-annually | fallback passes safety smoke set |
| tabletop | one type per session, rotating I1–I11 | quarterly | roles, notification decisions and evidence steps walked end to end |

**Flywheel SLAs and metrics.** Contain, detection→dataset, dataset→green CI and PIR times per level: crosswalk §7.1. Action items done: SEV1 prevent-class ≤ `<2 weeks>` · SEV2 ≤ `<1 month>` · SEV3 ≤ `<1 quarter>` · SEV4 backlog. Report monthly in the AI operations review, including SLA breaches: MTTD (start → detection, by source) · MTTC (detection → lever effective) · MTTR (detection → fully recovered) · regression-case SLA adherence · repeat rate (same class + capability within 90 days) · detection mix (alerts/canaries vs users vs external; goal: shrinking user/external share) · lever effectiveness (stopped harm on first pull) · PIR action closure by due date.

**Ownership and cadence:** runbook: `<AI platform owner>` (named person), quarterly, after every SEV1 and after any new incident type · severity criteria: AI governance forum + Security + Legal, semi-annually · contact rota: incident management owner, monthly verification · containment lever inventory: AI platform owner, on every new capability, tool or model route · notification decision table: Legal/Privacy, semi-annually and on regulatory change · drill schedule: AI platform owner, quarterly. Version the runbook in Git; changes need Security and incident-management review. A 404 runbook link or a rota with a departed person is a SEV4 finding.

**Readiness checklist (adoption gate):**

- [ ] Incident types (§6) adopted; product-specific types added
- [ ] Severity matrix ratified with Security and Legal; SEV ↔ P mapping recorded
- [ ] Every detection source routes into the incident ticket system; support triage guide updated
- [ ] Named rotas for IC, AI on-call, Security, Privacy, Legal, Comms, FinOps; contacts verified this month
- [ ] For every T1+ capability: capability flag, prompt-label rollback, model pin, tool disable exist and are documented
- [ ] Platform kill switch per product (and provider), named owner, audited activation
- [ ] Containment lever changes audit-logged and visible to responders
- [ ] Evidence store with access control, redaction and legal-hold support
- [ ] Traces carry prompt / model / retrieval / tool-surface versions (`skills/deployment-ci-cd/reference/ai-observability.md`)
- [ ] Notification decision table (§10) approved by Legal; message templates drafted
- [ ] Recovery verification checklist (§11) linked from the incident ticket template
- [ ] Regression-case closure rule enforced in the incident workflow (§12)
- [ ] PIR template (SKILL.md step 10) in the incident ticket system
- [ ] Flywheel SLAs ratified and reported monthly
- [ ] First kill-switch drill and first tabletop done; drill calendar published
- [ ] Runbook owner and review cadence set
