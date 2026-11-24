---
name: ai-launch-check
description: Run the unified pre-production launch checklist for an AI feature before shipping it. Use when the user explicitly runs /ai-launch-check or asks to "review my AI feature for launch", "is this ready to ship", "pre-production review", or similar ritual phrasing.
disable-model-invocation: true
allowed-tools: Read, Write
last-reviewed: 2026-11-22
metadata:
  triggers: AI launch check, ready to ship AI feature, pre-production AI review, AI kill switch test
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, ai-audit
---

# AI Feature Launch Check

## Iron Law

**Do not output GO if any checklist item is ❌. A written exception in the Decision Record with an owner and deadline is required for every ⚠️ item. Verbal assertions do not count as evidence for any item.**

Run the unified pre-production launch checklist from the AI Playbook (Layer 4 §4.1). This consolidates the pre-flight questions, pre-production gate, kill-switch tests, and adversarial test catalog into one launch review. It is also the §8 production release checklist of the engineering guardrails (rows applied by the capability's T-tier) and runs the §9 minimum verification tests. Requirement text for G1–G24, T0–T3 and the ten laws, plus the guardrail map: `.claude/skills/ai-playbook/reference/engineering-guardrails.md`.

## Procedure

1. Ask the user for the feature slug. Look for the Decision Record at `docs/ai-decisions/<feature-slug>.md`.
   - If it does not exist: **stop**. Tell the user to run `/ai-decision-record` first. Do not proceed without one.
2. Read the Decision Record. Cross-check every item below against what the record says.
3. For each checklist item below, ask the user to **show evidence**, not assert compliance. Examples of evidence:
   - "Output Contract implemented" → point to the validation code; read it.
   - "Eval set" → point to the file; show the size and a sample.
   - "Kill switch tested" → show the test run log.
4. Mark each item: PASS (✅, evidence shown) / EXCEPTION (⚠️, written exception) / FAIL (❌, missing or failing) / NOT RUN (a test that was not executed counts as FAIL for kill-switch, output-contract and security items) / NOT APPLICABLE (state why, e.g. the streaming block for a text-only feature).
5. **Do not pass the launch check if any item is ❌.** Partial is allowed only when the user provides a written exception in the Decision Record with an owner and a deadline.
6. Produce a launch decision: **GO / NO-GO / GO-WITH-EXCEPTIONS** with a written rationale.

## The pre-flight (10 questions)

Walk through these first. Any "no" or "I don't know" is a NO-GO.

- [ ] 1. Can deterministic code solve this reliably? (If yes → why are we shipping AI?)
- [ ] 2. Is the input genuinely unstructured or ambiguous?
- [ ] 3. Does AI measurably beat code on accuracy, speed, cost, or UX?
- [ ] 4. Is the decision reversible, or is there a downstream verifier?
- [ ] 5. Off the critical latency path, or fast fallback exists?
- [ ] 6. What's the cost when AI is wrong, and who absorbs it?
- [ ] 7. Is human approval required for high-impact outcomes?
- [ ] 8. Can every AI output be audited and explained later?
- [ ] 9. Enough labeled examples for risk-tiered evaluation?
- [ ] 10. Deterministic fallback when AI fails or times out?

## The artifacts checklist

Each item must point to a file, a log, or a running piece of code. Verbal assertions do not count.

- [ ] Decision Record signed off (`docs/ai-decisions/<feature-slug>.md`)
- [ ] Risk-tiered eval set with target metrics (size matches Layer 2 §2.14 for the declared risk tier)
- [ ] Output Contract implemented: schema → types → business rules → permissions → confidence → audit → route (Layer 2 §2.4)
- [ ] Adversarial tests in CI (Layer 3 §3.2): prompt injection, tool misuse, retrieval poisoning, bad schema outputs
- [ ] RAG requirements met if applicable (Layer 2 §2.7): hybrid search, metadata filtering, ACLs at query time, citations, no-answer test, separate retrieval/answer grading, chunk provenance
- [ ] Multi-modal handling reviewed if applicable (Layer 2 §2.8): each modality validated, cost recalculated, sandboxes for code execution
- [ ] Model and routing strategy decided (Layer 2 §2.9)
- [ ] Cost & latency budget filled (Layer 3 §3.4): max calls, max tokens, p50/p95/p99, cost ceiling, fallback after timeout, cache strategy, rate limit. Budgets are enforced per run/session across sub-agents, retries and fallback models, plus a per-organization period budget; values calibrated from measured p95/p99 (shadow), and exhaustion leaves no half-applied side effect
- [ ] 12-month AI tax estimated and approved (Layer 2 §2.11)
- [ ] Provider abstraction in place; model and prompt versions pinned (Layer 2 §2.12)
- [ ] Observability implemented (Layer 3 §3.5, `.claude/skills/deployment-ci-cd/reference/ai-observability.md`): one trace per request across agent/model/tool/retrieval spans, prompt name/version/hash and model id on model spans, no exception text or content in traces/logs (test with a positive control), content capture off in production, alerts with owners
- [ ] Human review queue defined: what goes, who reviews, SLA per Layer 2 §2.1
- [ ] Data governance review completed (Layer 2 §2.13): context contents, logging, retention, training-use, tenant isolation, deletion propagation, redaction
- [ ] Security review completed (Layer 2 §2.5): `ai-security-reviewer` report with no unresolved CRITICAL/HIGH; the two questions answered with code, not prompts
- [ ] Prompt/model release path defined: eval-gated promotion, label/flag rollback with the registry cache TTL stated (`.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md`)
- [ ] Rollout plan with promotion criteria (Layer 4 §4.2): offline → dogfood → shadow → beta → percentage → full
- [ ] Incident response plan (Layer 4 §4.3): named on-call, rollback triggers with thresholds, affected-user identification, quarantine, reversal, post-mortem template, leading indicators
- [ ] **Kill-switch tests passing** (Layer 4 §4.4): all eight tests in staging or shadow, with logs; platform kill switch has a named owner, a runbook and a recorded drill (G10)

## Kill-switch tests — must all pass

Demand the test logs. If they don't exist, fail the launch check.

- [ ] Disable via flag → the endpoint returns its normal contract in degraded form (JSON: documented fallback fields set; stream: exactly one terminal `error` frame with a fixed code), HTTP status unchanged, within 1 s; deterministic safety and manual paths still work. New consequential AI paths ship default-OFF until this gate passes. Evidence: test log with response body
- [ ] Force model downgrade → output contract still passes or routes to review
- [ ] Simulate provider outage → timeout fires, fallback serves, no infinite retry; simulate quota/billing exhaustion → distinct error surfaced, retries stop, alert reaches the billing owner
- [ ] Simulate retrieval poisoning → contract/security rejects; provenance logs source
- [ ] Simulate cost spike (10× tokens) → rate limit + cost ceiling fire; alerts route correctly
- [ ] Simulate prompt injection from user input AND from a retrieved doc → least-privilege scope prevents harm
- [ ] Roll back one prompt or model version → traffic shifts cleanly; metrics return to baseline
- [ ] Verify deletion propagation → user-deleted data gone from embeddings, caches, logs, evals within SLA

## Guardrail contract tests (§9 + L8 read-back) — must run

The service implements the adapter in `assets/guardrail_contract_tests.py` (Python, pytest) or uses `assets/guardrail-contract.test.ts` (TypeScript + Zod 4 + Vitest, G3/G4 rows) and runs it in CI. Both templates were executed against a reference adapter and against deliberately broken adapters (every test red at least once): pytest 9.2.0 on Python 3.14.10; Vitest 5.1.1 + Zod 4.6.7 + TypeScript 6.0.3 on Node 26.13.1. Demand:

- [ ] The command and its own exit code; pass / fail / skip counts. Any FAIL → ❌.
- [ ] Every skipped test carries a NOT APPLICABLE reason (e.g. no offline client; no asynchronously settling action for the L8 `async_outcome` tests) listed in the report. A skip without a reason counts as FAIL.
- [ ] At least one negative control per guardrail family (authority, contract, idempotency, isolation, budget, degradation): the control was disabled, the matching test went red, then restored. A suite never seen failing is not evidence.
- [ ] Tests run against the real service boundary (HTTP or tool server) with a fake/scripted model; label it MOCKED. It is not live-provider evidence.

## Release checklist (§8) rows not covered above (apply by T-tier)

Governance readiness (enterprise governance §19) is a separate checklist: `.claude/skills/ai-governance/assets/schemas/production_readiness.schema.json` (validate with `.claude/skills/ai-governance/scripts/validate_governance_record.py`). Both must pass.


- [ ] T-tier recorded (T0–T3, not the playbook 0–5 tier or A0–A4) and ≥ the floor of the highest principles action tier among the Decision Record's tools (A0/A1 → T0, T1 if user-facing or PII; A2, A3, A4, Emergency → T2; A4 or Emergency in a regulated or life-safety domain → T3; table: `engineering-guardrails.md` "Principles action tiers"), else ❌; canonical authority named for every input and output, AI vs deterministic steps separated, safety / authorization / spend / verification boundaries preserved (G2); T2/T3: independent sign-off named in the Decision Record (implementing team is never sole approver); T3: Legal/compliance sign-off and regulatory mapping
- [ ] Outcome defined (G24): baseline, target, measurement method, evaluation window, cost to serve, disable trigger
- [ ] Ten laws (four-element rule, `engineering-guardrails.md` "Ten laws"): the Decision Record's ten-laws table gives every applicable law a control, owner, evidence and failure condition (defaults: `engineering-guardrails.md` "Ten laws"); a law with no evidence → ❌. L8: every consequential action that settles asynchronously reports `PENDING_CONFIRMATION` until the system-of-record read-back passes (contract tests `test_async_action_is_pending_until_outcome_read_back`, `test_unverified_async_outcome_is_never_reported_done`)
- [ ] Per-org rate, concurrency and period budget controls verified; stale AI intent cancelled by human override (test); idempotency keys org-scoped, payload-hash bound, replay window and retention defined; multi-step operations use the domain's saga / compensation, never half-mutated on budget exhaustion (G4)
- [ ] Human exception queue: owner, SLA, capacity, priority classes, overflow behaviour
- [ ] AI gateway / shared model client failure mode verified: degradation, no bypass (test); no parallel source of truth or retrieval store introduced
- [ ] Cross-scope isolation tests include snippets, counts/facets, nearest neighbours and related entities; RAG ingestion ACLs travel with chunks and ACL changes propagate within SLA, deleted sources gone within SLA, stale versions excluded or labelled (G15)
- [ ] Model-call egress: allowed/prohibited data classes, approved providers and region checked before the call (test); minimum-necessary PII; secrets excluded from embeddings and memory (test)
- [ ] Trace-store privacy: org isolation, role-based access, retention, redaction
- [ ] Safety-recall gate for safety-capable paths and out-of-distribution escalation defined; eval dataset provenance and review QA recorded; every production input language evaluated or routed to a manual flow (test)
- [ ] Fairness / bias testing done where the output influences decisions about people (G19)
- [ ] Feature flag default OFF until gates pass (T2/T3)
- [ ] Role-safe advice boundaries reviewed (G18); AI disclosure reviewed (G21); accessibility reviewed by `accessibility-auditor` (G22)
- [ ] Offline behaviour verified if any client is offline-capable (G23)
- [ ] Model and provider approved and listed in the AI inventory (G20; `ai-governance` skill)
- [ ] Waivers (§11): each has reason, compensating controls, owner, independent approver, unexpired date. A waiver of G2 or G9 at T2/T3 is invalid → ❌

## If streaming, voice or multimodal (skip for text-only features)

- [ ] Client disconnect cancels the upstream model/graph call (test)
- [ ] Every stream ends with exactly one terminal frame (done or error); no action taken on partial output
- [ ] WebSocket: authentication before accept; message size and rate caps
- [ ] Audio/image capture: explicit consent, retention TTL, deletion reaching traces, caches and eval sets; text fallback path

Detail: `.claude/skills/streaming-protocols/`, `.claude/skills/voice-ai-development/`.

## Decision output

After running through every item, output:

```md
# Launch Check: <Feature Name>

**Decision**: GO | NO-GO | GO-WITH-EXCEPTIONS
**Reviewer**: <Claude Code session> — <date>
**Decision Record**: docs/ai-decisions/<feature-slug>.md

**Guardrail contract suite**: `<command>` → exit <code>; <N> pass / <N> fail / <N> skipped (reasons listed); negative controls: <list>
**Tiers**: T<0-3> (§3) · A<0-4> (governance §6) · playbook tier <0-5>

## Verified (✅)
- ...

## Partial — exceptions filed (⚠️)
- <item>: exception in Decision Record, owner <name>, deadline <date>

## Missing — blockers (❌)
- ...

## Recommendation
<one paragraph: ship, scope down, or stop>

## If GO-WITH-EXCEPTIONS: follow-up SLAs
- ...
```

## Default stance

- Bias toward NO-GO. A launch check is a forcing function; if the team passes too easily, the check isn't doing its job.
- Do not let "we'll fix it after launch" pass for kill-switch tests, output contract, or security review. Those are pre-launch by definition.
- A guardrail contract suite that was not run is NOT RUN, and NOT RUN counts as FAIL for authority (G2), contract (G3), idempotency (G4), isolation (G9) and kill-switch (G10) rows.
- Tier-3+ features with no human approval gate are an automatic NO-GO unless the Decision Record has a written domain-risk exception.

## If this skill cannot proceed

```
Abort condition: Decision Record missing
→ Hard stop. Output: "Run /ai-decision-record first. The launch check
  cross-references the Decision Record for every checklist item. Cannot proceed without it."

Abort condition: user provides verbal assertions instead of file:line evidence
→ Mark item ⚠️ at best, ❌ if critical (kill switch, output contract, security review).
→ Output: "Verbal assertions are not evidence. Point to the file, log, or test output."

Abort condition: all 8 kill-switch tests have no logs
→ Automatic NO-GO regardless of other items.
→ Output: "Kill-switch tests must be run in staging or shadow with logs. 'We tested it
  manually once' does not satisfy this requirement."
```

## Verify (after producing the launch decision)

```
✅ Every checklist item has a status: ✅ / ⚠️ / ❌ — no blanks
✅ Every ⚠️ item has a named owner and a written deadline in the Decision Record
✅ Decision (GO / NO-GO / GO-WITH-EXCEPTIONS) matches the item statuses — no ❌ items in a GO
✅ Launch check report written to docs/ai-audits/<feature-slug>/04-launch-check.md
```

## References

- AI Playbook Layer 4 §4.1 Unified launch checklist: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 4 §4.2 Rollout strategy: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 4 §4.4 Kill-switch tests: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 2 §2.14 Eval size floors: `.claude/skills/ai-playbook/playbook.md`
- Guardrail requirements (§3 tiers, G1–G24, §11 waivers, ten laws, action tiers, adoption checklist): `.claude/skills/ai-playbook/reference/engineering-guardrails.md`
- Contract test templates: `.claude/skills/ai-launch-check/assets/`
- Prerequisite: `/ai-decision-record` (must exist before launch check runs)
