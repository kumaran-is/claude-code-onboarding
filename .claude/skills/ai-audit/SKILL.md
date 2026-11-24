---
name: ai-audit
description: "Audit an existing AI feature or agentic app: engineering audit against the AI Playbook (decision record, security review, eval audit, launch check, remediation plan) or governance mode (risk assessment, governance audit, production readiness review against the ai-governance skill, with validated JSON records). Use for /ai-audit, \"audit my AI app / agent\", \"assess AI risk\", \"governance audit\" or \"AI production readiness\" on existing code, not for building new."
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep, Bash
last-reviewed: 2026-11-23
metadata:
  triggers: audit my AI app, AI playbook audit, agentic system review, AI production readiness, AI risk assessment, AI governance audit
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, ai-governance
---

# AI Application Audit

## Iron Law

**Do not auto-fix. This skill produces reports and a remediation plan — not code changes. Every finding becomes a separate task for a follow-up session.**

Run a comprehensive audit of an existing agentic application or AI feature against the AI Playbook. This is for **verifying existing code**, not designing new features.

The audit runs in five phases with explicit confirmation gates between each. Each phase produces a written artifact in the repo. The final output is a prioritized remediation plan.

## Modes

| Mode | Question | Standard | Output |
|---|---|---|---|
| `engineering` (default) | Is this AI code safe and well-evaluated? | AI Playbook + `.claude/skills/ai-playbook/reference/engineering-guardrails.md` | Phases 0–5 below |
| `risk` | What is this system's governance risk tier and autonomy level? | `ai-governance` §2.4, §6 (`reference/risk-autonomy-oversight.md`) | `risk_assessment` (+ `autonomy_declaration` for A2+) |
| `governance` | Which governance controls exist, who owns them and what proves them? | `ai-governance` §1, §9, §10, §16 (`reference/operating-model-and-registers.md`, `reference/supply-chain-eval-and-release.md`) | Control register entries, evidence gaps, boundary A–D per finding |
| `readiness` | Is the system ready for production under the governance checklist? | `ai-governance` §19 (`assets/schemas/production_readiness.schema.json`) | `production_readiness` record + gap list |

Pick the mode in Phase 0. `risk`, `governance` and `readiness` follow **Governance modes** at the end of this file and do not replace the engineering audit: a High or Critical system needs both.

## When to use this vs. the individual skills

- Use `/ai-audit` when you want a **full pass** against existing code and you're willing to let it run end-to-end.
- Use the individual skills (`/ai-decision-record`, `/ai-launch-check`, `/ai-incident-response`) and subagents (`@ai-security-reviewer`, `@ai-eval-designer`) when you want **finer control** between phases or you're only doing part of the work.

## Operating procedure

Walk through the five phases below in order. **Do not skip phases.** Each phase has an explicit confirmation gate where the user can pause, redirect, or abort.

Before starting, load the `ai-playbook` skill if it isn't already in context.

---

### Phase 0: Scoping (no artifact)

Before any audit work, get clarity on what's being audited. Ask the user:

1. **What is the feature slug?** (Used for directory naming. If unsure, propose one from the repo structure.)
2. **Is this a single feature audit or a multi-feature codebase?** (If multi-feature, ask which feature to audit first — running the full audit on multiple features in one shot is too token-heavy.)
3. **Where is the AI code?** (Path or paths. If unknown, offer to scan and report back before continuing.)
4. **Is there an existing Decision Record?** (Check `docs/ai-decisions/<feature-slug>.md`. If yes, this skips Phase 1 and uses it as input.)
5. **Which mode?** (`engineering`, `risk`, `governance`, `readiness`; see Modes.) For a governance mode also check `governance/<feature-slug>/` for existing records.

After confirming scope, summarize the plan:

```
Audit plan for: <feature-slug>
- AI code location: <paths>
- Phases to run:
  1. Decision Record reverse-engineering (or skip if exists)
  2. Security review via @ai-security-reviewer subagent
  3. Eval audit via @ai-eval-designer subagent
  4. Launch check (gate)
  5. Consolidated remediation plan
- Estimated wall time: 60–120 minutes depending on codebase size
- Estimated token cost: significant (two subagents + main session). Confirm before proceeding.

Proceed? (yes / scope-down / abort)
```

**Do not proceed without explicit confirmation.** This audit consumes meaningful tokens and produces artifacts in the repo.

---

### Phase 1: Decision Record (reverse-engineered)

**Skip this phase if a Decision Record already exists at `docs/ai-decisions/<feature-slug>.md`.** In that case, read it, summarize what it claims, and ask the user to confirm it still reflects reality before moving to Phase 2.

If no Decision Record exists, reverse-engineer one:

1. **Scan the AI code.** Identify every AI surface: LLM calls, agent loops, tool definitions, prompts (system / user / templates), RAG/retrieval, model output handlers, side-effect points (writes, sends, payments).

2. **Determine the pattern** (assistant / workflow / agent / autonomous) based on what the code *does*, not what it's named. Multi-step planning with tools is an agent. A single LLM call wrapped in retries is a workflow.

3. **Propose a risk tier** based on actual blast radius. Sum across a session, not per action. Be honest. If the code can send emails to customers, that's at least Tier 3a regardless of how it's framed.

4. **Ask clarifying questions** for what the code can't tell you. Ask one at a time:
   - Who is the named human owner?
   - What is the user problem this solves?
   - What is the cost ceiling per task?
   - What is the current eval set (if any)?
   - What is the SLA for human review (if any review queue exists)?
   - What is the 12-month AI tax estimate?
   - Where is the kill switch?
   - When was it last tested?

5. **Write the Decision Record** to `docs/ai-decisions/<feature-slug>.md` using the template from the `ai-decision-record` skill / Layer 3 §3.3 of the playbook.

6. **Confirmation gate**: Summarize the Decision Record. Highlight any fields where you had to guess. Ask the user to verify before proceeding.

```
Decision Record drafted at docs/ai-decisions/<feature-slug>.md.

Honest summary:
- Pattern: <X>
- Risk tier: <N>
- Top three risks I identified: ...
- Fields I had to guess (please verify): ...

Proceed to Phase 2 (security review)? (yes / edit-record / abort)
```

---

### Phase 2: Security review

**Confirmation before invoking the subagent.** Subagents consume real tokens. Confirm scope:

```
About to invoke @ai-security-reviewer on:
- <paths>

The subagent will run in its own context. Expected output: structured findings report (Critical / High / Medium).

Proceed? (yes / narrow-scope / abort)
```

After confirmation, invoke:

```
@ai-security-reviewer audit the AI code at <paths> against your full review checklist (architecture, autonomy, grounding, tool permissions and side effects, injection, exfiltration, isolation, memory privacy, eval leakage, fallback/retry safety, cost/latency, observability, production readiness) and the adversarial test catalog (Layer 3 §3.2).

Focus on:
- LLM call sites
- Tool definitions and agent loops
- RAG/retrieval code
- Anywhere user input, retrieved documents, or tool outputs flow into prompts
- Anywhere model output triggers side effects

Output the standard findings report with a status for every checklist area. For each finding, cite file:line with quoted evidence and explain why a prompt-level mitigation is insufficient. Mark any test, eval or runtime check you did not execute as NOT RUN.

Decision Record context: docs/ai-decisions/<feature-slug>.md
```

Write the subagent's report to `docs/ai-audits/<feature-slug>/02-security-review.md`. For framework-specific depth, also dispatch the stack reviewer (`agentic-ai-reviewer` for LangChain/LangGraph, `adk-reviewer` for Google ADK, `rag-implementation-reviewer` for RAG code, `eval-reviewer` for eval code) and append its findings to the same file.

**Confirmation gate**:
```
Security review complete. Summary:
- Critical findings: <N>
- High findings: <N>
- Medium findings: <N>

Top three blockers: ...

Full report: docs/ai-audits/<feature-slug>/02-security-review.md

Proceed to Phase 3 (eval audit)? (yes / pause-to-remediate / abort)
```

If there are Critical findings, **recommend pausing to remediate before continuing**. The launch check (Phase 4) will fail on Criticals anyway; fixing them first makes the rest of the audit more useful.

---

### Phase 3: Eval audit

**Confirmation before invoking the subagent:**

```
About to invoke @ai-eval-designer on:
- Existing tests/evals at: <paths>
- Risk tier from Decision Record: <N>

The subagent will identify eval gaps and generate a starter eval set for the biggest ones.

Proceed? (yes / narrow-scope / abort)
```

After confirmation, invoke:

```
@ai-eval-designer audit eval coverage for this agentic app.

1. Find existing tests and evals at: <paths>
2. Read the Decision Record at docs/ai-decisions/<feature-slug>.md (risk tier: <N>).
3. Compare current eval coverage against the playbook's risk-tiered minimums (Layer 2 §2.14).
4. Identify gaps across happy path, edge cases, adversarial, negative.
5. Generate a starter eval set at evals/<feature-slug>/cases/starter.json filling the most critical gaps — especially adversarial cases from Layer 3 §3.2.
6. Output a gap analysis report.
```

Write the report to `docs/ai-audits/<feature-slug>/03-eval-audit.md`.

**Confirmation gate**:
```
Eval audit complete. Summary:
- Current eval set size: <N>
- Required minimum for Tier <N>: <M>
- Gap: <M-N> cases
- Categories most under-covered: ...

Starter eval set generated at: evals/<feature-slug>/cases/starter.json
Full report: docs/ai-audits/<feature-slug>/03-eval-audit.md

Proceed to Phase 4 (launch check)? (yes / abort)
```

---

### Phase 4: Launch check

This is the audit's accountability moment. The launch check demands evidence for every item — and on existing code, **expect to fail it on the first pass.** That's the audit doing its job.

Run the launch check inline (do not invoke a subagent — this needs to stay in the main session to read Phase 1–3 artifacts):

Apply the unified checklist from Layer 4 §4.1 of the playbook. For each item:
- Try to verify from the codebase directly first.
- Cross-reference Phase 2 (security) and Phase 3 (eval) findings.
- Ask the user for evidence only when code inspection is inconclusive.
- Mark ✅ / ⚠️ / ❌.

**Be strict about evidence.** "We have logging" without pointing to the logging schema doesn't count. "We have a kill switch" without pointing to a tested feature flag doesn't count.

Write the launch check report to `docs/ai-audits/<feature-slug>/04-launch-check.md`. Include:
- Decision: GO / NO-GO / GO-WITH-EXCEPTIONS
- Every checklist item with status and evidence
- Cross-references to Phase 2 and Phase 3 findings

**Confirmation gate**:
```
Launch check complete.

Decision: <GO / NO-GO / GO-WITH-EXCEPTIONS>
- ✅ Verified: <N>
- ⚠️ Partial: <N>
- ❌ Missing: <N>

Top blockers: ...

Full report: docs/ai-audits/<feature-slug>/04-launch-check.md

Proceed to Phase 5 (consolidated remediation plan)? (yes / abort)
```

---

### Phase 5: Consolidated remediation plan

Synthesize findings from all four prior phases into one prioritized backlog. Read the artifacts:
- `docs/ai-decisions/<feature-slug>.md` (Decision Record)
- `docs/ai-audits/<feature-slug>/02-security-review.md`
- `docs/ai-audits/<feature-slug>/03-eval-audit.md`
- `docs/ai-audits/<feature-slug>/04-launch-check.md`

Group every finding into one of four priority tiers:

1. **Critical — fix before any further production traffic.** Security criticals; missing or untested kill switch; missing output contract on Tier-3+ features; missing tenant isolation; secrets in model context.
2. **High — fix within 2 weeks.** High security findings; eval set below risk-tiered floor; missing observability; missing incident response plan; rollback path not tested.
3. **Medium — schedule in the next quarter.** Medium security findings; drift detection gaps; provider abstraction; multi-modal handling refinements; AI tax not estimated.
4. **Structural — design debt to track.** Full reference architecture gaps; eval flywheel not in place; canary deployment infrastructure; full Layer 2 coverage.

For each item, include:
- **Source**: which audit phase surfaced it
- **Playbook reference**: which section/layer
- **Concrete next action**: what to actually do
- **Suggested owner role** (named human in Decision Record; if unspecified, propose the role)
- **Acceptance criteria**: how you'll know it's done

Write to `docs/ai-audits/<feature-slug>/05-remediation-plan.md`.

**Final output to user**:

```
AI Audit Complete

Feature: <feature-slug>
Pattern: <X>
Risk tier: <N>
Launch check decision: <GO / NO-GO / GO-WITH-EXCEPTIONS>

Findings:
- Critical: <N> items
- High: <N> items
- Medium: <N> items
- Structural: <N> items

Top three things to fix this week:
1. ...
2. ...
3. ...

Full artifacts:
- Decision Record: docs/ai-decisions/<feature-slug>.md
- Security review: docs/ai-audits/<feature-slug>/02-security-review.md
- Eval audit: docs/ai-audits/<feature-slug>/03-eval-audit.md
- Launch check: docs/ai-audits/<feature-slug>/04-launch-check.md
- Remediation plan: docs/ai-audits/<feature-slug>/05-remediation-plan.md

Suggested next step:
- If Critical items: pause, fix them, re-run `/ai-audit` to verify
- If High items: schedule with owners, re-run `/ai-audit` in 2 weeks
- If only Medium/Structural: ship with exceptions filed in Decision Record; track in regular planning
```

---

## Default stance

- **Be strict about evidence in Phase 4.** The whole audit's value depends on the launch check being honest. If you accept verbal assertions, the audit produces false confidence.
- **Treat the first run as a baseline, not a verdict.** Existing code rarely passes a fresh audit. The output is a remediation backlog, not a launch decision.
- **Default to recommending pause-to-remediate after Phase 2 if there are Criticals.** Continuing the audit past unfixed Critical security findings makes the rest of the work less useful.
- **Confirmation gates are not optional.** Even if the user said "yes go through everything" at the start, each gate is a chance to course-correct. Honor them.
- **Don't auto-fix.** This skill produces reports and plans, not code changes. Remediation is a separate conversation per finding.

## What this skill does NOT do

- It does not implement fixes. Each finding becomes a task; the human (or a follow-up Claude Code session) does the work.
- It does not replace ongoing eval maintenance, security review, or incident response. It's a snapshot audit; the playbook's lifecycle controls (eval flywheel, drift detection, incident learning) are continuous.
- It does not certify production readiness. The launch check decision is advisory; final ship/no-ship is a human + business call informed by this report.
- It does not run on multiple features in parallel. Audit one feature at a time. Repeat for the next.

## Verify (after Phase 5 is complete)

```
✅ docs/ai-decisions/<feature-slug>.md exists (created or confirmed in Phase 1)
✅ docs/ai-audits/<feature-slug>/02-security-review.md written
✅ docs/ai-audits/<feature-slug>/03-eval-audit.md written
✅ docs/ai-audits/<feature-slug>/04-launch-check.md written with GO/NO-GO decision
✅ docs/ai-audits/<feature-slug>/05-remediation-plan.md written with priority tiers
✅ No audit phase was silently skipped — every abort was explicit and user-confirmed
```

## If this skill cannot proceed

```
Abort condition: user declines scope confirmation at Phase 0
→ Stop. Do not run any phases.
→ Output: "Audit cancelled at scoping. No artifacts written."

Abort condition: Critical security findings in Phase 2
→ Recommend: "Pause audit. Fix Critical findings first. Re-run /ai-audit to continue."
→ Do not mark audit complete — it is paused, not done.

Abort condition: Decision Record missing and user refuses to reverse-engineer one
→ Stop at Phase 1. Output: "Cannot proceed without a Decision Record. Run /ai-decision-record first."
```

## Governance modes (`risk`, `governance`, `readiness`)

Load the `ai-governance` skill first. Its Iron Law applies: a template or a valid record is never evidence that a control works or that anyone approved anything. Label every finding with its boundary: **A** toolkit implements and tests it, **B** toolkit template only, **C** needs enterprise infrastructure or a named organisational owner, **D** needs legal, regulatory or executive approval. Never report that the organisation has adopted the standard or that a control is effective without executed evidence.

Records go to `governance/<feature-slug>/` as JSON (schemas in `.claude/skills/ai-governance/assets/schemas/`). Copy the matching file from `assets/examples/`, replace every value and set `record_status` to `draft`. Facts you cannot read from code are asked one at a time; unanswered fields stay out of the record so the validator flags them, never filled with guesses.

**`risk` mode**
1. Scan the AI surfaces as in Phase 1 step 1 and record the factors: data sensitivity, customer impact, likelihood, severity, reversibility, tenancy, state-changing, durable memory, fine-tuning.
2. Propose a governance risk tier (Low/Medium/High/Critical) and autonomy level (A0–A4) as two separate judgements; record the engineering tier (T0–T3) only as a cross-reference. Never derive one from another.
3. Ask for the named business, technical and risk owners and the value baseline (why AI beats a simpler solution).
4. Write `risk_assessment.json` (`approval_status: pending`; only the risk owner can approve). For A2+ draft `autonomy_declaration.json`; numeric thresholds from the standard are illustrative and need risk-owner approval.

**`governance` mode**
1. Start from the 12 illustrative critical controls (`ai-governance/reference/operating-model-and-registers.md` §6) and the controls the risk tier implies. For each: does code enforce it (file:line), does a test prove it (command + own exit code + negative control), who owns it?
2. Run the seeded unsafe scenarios the project can run locally (`ai-governance/reference/supply-chain-eval-and-release.md` §6: unauthorized tool access, cross-tenant retrieval, stale approval, duplicate mutation, injected retrieved content, invalid artifact manifest, known-bad output, prohibited data transfer). Record each as `control_evidence` with `mocked` set honestly. Scenarios needing a gateway or DLP you do not have are BLOCKED, not passed.
3. Write `control_register_entry` per control. Untested controls are `Not tested` / `not_assessed`; placeholder owners are rejected.
4. Draft `ai_bom.json` from lockfiles, image digests and prompt registry; mark components you cannot hash.

**`readiness` mode**
Fill `production_readiness.json` item by item with evidence references (Phase 4 strictness applies: verbal assertions are not evidence). Verdict READY only if no item is `not_done`; it is still a self-assessment, not sign-off. Cross-check `/ai-launch-check` (engineering release checklist); both must pass.

**Validate and report (all governance modes)**
```bash
python3 .claude/skills/ai-governance/scripts/validate_governance_record.py --json governance/<feature-slug>/*.json > docs/ai-audits/<feature-slug>/governance-validation.json; echo "EXIT:$?"
```
Exit 0 = records complete and consistent; 1 = invalid records (list them as findings); 2 = usage or schema error. Write `docs/ai-audits/<feature-slug>/06-governance.md`: mode, records written, validator exit code, each finding with severity, boundary (A–D), evidence or NOT RUN/BLOCKED, and owner role. Remediation items join the Phase 5 plan.

## References

- AI Playbook: `.claude/skills/ai-playbook/playbook.md` (Layers 1–4)
- Decision Record template: `.claude/skills/ai-decision-record/SKILL.md`
- Launch checklist: `.claude/skills/ai-launch-check/SKILL.md` (Layer 4 §4.1)
- Security adversarial catalog: Layer 3 §3.2 of playbook.md
- Eval sizing table: Layer 2 §2.14 of playbook.md
- Governance records, schemas, validator, boundary map: `.claude/skills/ai-governance/` (`reference/boundary-map.md`)
- OWASP LLM Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
