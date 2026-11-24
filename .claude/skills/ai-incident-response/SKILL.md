---
name: ai-incident-response
description: Run the AI incident response procedure when something is going wrong in production AI. Use when the user explicitly runs /ai-incident-response or says "AI incident", "model is broken", "production AI is failing", "we're seeing weird outputs in prod", "hallucination in production", or similar urgent phrasing.
disable-model-invocation: true
allowed-tools: Read, Write, Bash
last-reviewed: 2026-11-24
metadata:
  triggers: AI incident, model is broken, hallucination in production, AI outage, provider quota exhausted
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-audit, ai-governance
---

# AI Incident Response

## Iron Law

**Stabilize before investigating. Pull the kill switch or roll back before debugging root cause. Curiosity about why it broke must never delay stopping the bleeding.**

When AI production behavior degrades, follow the procedure from the AI Playbook (Layer 4 §4.3) and this skill's runbook `reference/runbook-playbooks.md` (types I1–I11 and SEV1–SEV4 criteria §6, containment ladder §2/§7, numbered playbook steps §8, evidence §9, notification decisions D1–D6 §10, recovery verification §11, closure §12, PIR rules §13, organisation adoption checklist §15). The objective: stabilize first, investigate second, learn third. Per-type detection, containment, evidence, recovery and regression test, mapped to toolkit controls: `reference/runbook-playbooks.md` §3.

## Stage 1: Stabilize (first 15 minutes)

Do these in order. Do not investigate root cause yet — that comes after the bleeding stops.

1. **Confirm scope.** Ask the user:
   - What feature is affected?
   - What is the symptom? (Wrong outputs / latency spike / cost spike / refusals / safety violation / user reports)
   - When did it start?
   - Is it ongoing right now?

2. **Decide on rollback or kill.** Check the Decision Record for rollback triggers. Pull the **lowest rung that stops the harm** (`reference/runbook-playbooks.md` §2, §7: 1 capability flag → 2 prompt label rollback → 3 model pin → 4 tool disable → 5 platform kill switch) and climb if it does not; any responder may pull rungs 1–3 when harm is ongoing, rungs 4–5 need the incident commander. Log every pull (who, when, rung, scope, reason). If the symptom matches:
   - **Pull the kill switch** if the feature is causing user-visible harm. Confirm in chat before pulling. The kill switch disables the AI path only; deterministic safety and manual paths keep working.
   - **Roll back to last known good version** (prompt, model, retrieval index, threshold) if the kill switch is too aggressive. Mechanics (move the label/flag back, confirm the old version is served after the cache TTL by reading spans): `.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` §5, §9.
   - **Reduce traffic** (drop the percentage rollout step) if the impact is bounded but worsening.

3. **Capture the crime scene** before anything else changes:
   - Model id per backend (the response model on the span, not the configured alias)
   - Prompt name, label, version and content hash, and which registry tier served it (fresh / last-known-good / bundled)
   - Feature-flag states at the time
   - Retrieval index version (if RAG)
   - Tool versions (if agent)
   - Trace ids of bad outputs (read inputs from your own stores by id; copy samples only after PII scrubbing)
   - The time window
   - Affected users / tenants

4. **Notify.** The Decision Record names an on-call owner. Tell them. If the incident has user impact, the team's incident comms process owns it from here.

## Stage 2: Triage (next 30–60 minutes)

4a. **Classify** by runbook type I1–I11 (run every matching playbook in `reference/runbook-playbooks.md` §3, numbered steps §8; several types ⇒ highest severity) and by governance category (governance standard §13; how factors set S0–S3 is your organisation's severity policy, bounded below by the SEV crosswalk cited further down):

| Category | Example |
|---|---|
| AI-SEC | Prompt injection, model attack, unauthorized tool attempt |
| AI-DATA | Sensitive-data leak, retrieval access violation |
| AI-TENANT | Cross-tenant or cross-product exposure |
| AI-MEM | Memory poisoning or cross-session contamination |
| AI-ACTION | Incorrect or unauthorized state-changing action |
| AI-EVAL | Model quality or safety regression |
| AI-PROVIDER | Provider outage or unsafe fallback |
| AI-COST | Uncontrolled inference or agent execution |
| AI-OVERSIGHT | Approval bypass, ineffective review |
| AI-SUPPLY | Compromised or unverified model artifact |

   Severity factors: actual and potential impact, whether a deterministic control blocked it, data sensitivity, customer exposure, financial impact, regulatory consequences, duration, recoverability, control failure. A blocked unauthorized attempt is a real security event but not automatically as severe as a successful mutation; repeated blocked attempts can mean an active attack and justify escalation. On a governed system, cross-tenant exposure (AI-TENANT), unauthorized agent actions (AI-ACTION), critical memory compromise (AI-MEM) and approval or kill-switch boundary failures (AI-OVERSIGHT) are listed demotion triggers (governance §6.4): they may warrant immediate containment or autonomy reduction (disable the action path), and the risk owner decides the new level.

   AI security findings from red teaming use the playbook SEV-1–SEV-4 matrix (`.claude/skills/security-reviewer/reference/ai-threat-model-attack-classes.md` §6); SEV-1/SEV-2 open an incident here. Map them with the S0–S3 ↔ SEV-1–SEV-4 crosswalk (`.claude/skills/ai-governance/reference/supply-chain-eval-and-release.md` §7.1: one-to-one, stricter obligation wins, the organisation may tighten but not loosen it) and record both in the incident record (`severity`, `security_severity`). The regression case is never deleted (playbook §10.1 rule 8), and the incident closes only when that case fails on pre-fix code and passes on post-fix code.

5. **Quarantine bad outputs.** Decide per the feature's design (Layer 4 §4.3):
   - Recall (remove the output from view)
   - Retract (notify affected users)
   - Mark-as-disputed (annotate in the system)
   - Annotate downstream records (e.g., flag the CRM entries created)

6. **Reverse downstream actions if possible.**
   - For Tier 3+ actions: identify what was committed, who must authorize reversal, and execute.
   - For Tier 0–2 (read-only or post-hoc reversible): may not need active reversal, but log the impact.

7. **Check leading indicators** (Layer 4 §4.3) to detect related cascading issues:
   - "I don't know" / refusal rate
   - Average composite confidence
   - Output-contract validation rejection rate
   - Human override rate
   - p99 latency
   - Cost per task
   - Tool-call failure patterns
   - Retrieval recall@k regression

## Stage 3: Investigate (after stabilization)

8. **Identify root cause.** Common categories:
   - Model regression (provider pushed an update; pinning may have failed)
   - Prompt regression (recent prompt change shipped without canary)
   - Retrieval regression (chunking strategy changed, embeddings stale, ACL break)
   - Tool regression (downstream API changed behavior)
   - Prompt injection (intentional or accidental)
   - Data drift (input distribution changed)
   - Threshold miscalibration (confidence weights no longer fit reality)
   - Cost overrun or runaway loop (budget/call-limit counters, per-organization spend)
   - Provider quota or outage: distinguish billing/quota exhaustion (stop retries, alert the billing owner, report LLM-dependent CI/eval jobs as BLOCKED, not FAILED) from transient 429 rate limits (bounded backoff) and provider 5xx (fallback to an approved provider)
   - Credential leak (key in a prompt, log, trace or repo): revoke and rotate FIRST, then investigate

9. **Identify the eval gap.** Every confirmed incident represents an example your eval set didn't catch. Fetch the trace by id, rebuild the input, and capture:
   - The input that triggered the failure
   - The expected behavior
   - The actual behavior
   - Why the existing evals didn't catch it

## Stage 4: Learn (within 5 business days)

9a. **Write the incident record.** For governed systems, record the incident as JSON matching `.claude/skills/ai-governance/assets/schemas/incident_record.schema.json` (fields from governance §13.3: id, category, severity, affected model/agent, model/tool/prompt versions, policy decision, data and tenant scope, action history, customer impact, containment, recovery, root cause, corrective actions, preventive test cases) and validate it: `python3 .claude/skills/ai-governance/scripts/validate_governance_record.py <file>` (exit 0 valid, 1 invalid). A resolved or closed record without root cause, corrective actions and preventive test cases is rejected. Runbook fields: `incident_types` (I1–I11), `containment_levers` (each pull; rung 4–5 with `authorized_by`), `recovery_verification` (the `reference/runbook-playbooks.md` §11 checklist, each check pass with evidence or not_applicable with a reason) and, before `closed`, `regression_case` (the `production_regressions/INC-YYYY-NNN.yaml` file with fail-before and pass-after run ids, or a signed-off monitored detector when the case cannot be reproduced). Add `--regressions-root tests/golden/production_regressions` to prove the file exists. Lower a rung only after the §11 checks pass, progressively (internal → `<5%>` → `<25%>` → 100%).

10. **Write the post-incident review (PIR).** Blameless; required for SEV1–SEV2, recommended for SEV3, sampled for SEV4; timing, action-owner and escalation rules: `reference/runbook-playbooks.md` §13. Use this template:

```md
# PIR — INC-<YYYY-NNN> — <Feature Name> — <Date>
Severity: <SEVn / Sn> (factors: blocked by a deterministic control? control failure? data sensitivity?) · Types: <I1–I11> · Category: <AI-SEC … AI-SUPPLY>
Capability: <name> (tier <T0–T3>) · IC: <name> · Authors: <names>

## Summary (3–5 sentences, plain language)
## Impact
- Users / tenants affected: <count + how measured> · Data involved: <classes, no raw data>
- Harm downstream: <what happened> · Cost: <incident spend + remediation effort>
- Duration: detect <t> → contain <t> → recover <t>
## Timeline (UTC)
- <time> — <observation / decision / lever pulled (rung, scope)> — <who>
## Versions in force
prompt <name@version/label> · model <id@version> · retrieval <config version> ·
corpus/index <snapshot> · tool surface <hash> · dataset <name@version> · flag states
## Root cause and contributing factors
- Technical cause: the missing or failed control, never "the model hallucinated"
- Which guardrail (G#) or eval gate failed or was missing, and why the gate/canary did not catch it
- Why our controls didn't catch this: Output Contract · evals · adversarial tests · leading indicators · kill switch / rollback
## Detection
- How it was detected; could it have been detected earlier? Which signal was missing?
## Containment review
- Rung pulled, time to effect, worked first time? Levers left in place: owner + review date
## What went well / what was hard
## Action items (named person, due date; at least one targets detection time)
| # | Action | Type (prevent / detect / respond) | Owner (person) | Due | Ticket |
|---|---|---|---|---|---|
## Regression case and eval gap
- INC-<id> case path · fail-before run ID · pass-after run ID (or monitored detector + sign-off)
- <input> → <expected> (was: <actual>)
## Notifications
- D1–D6: decision (including "none"), who decided, when, why, outcome; legal-hold disposition
## Prevention
- Immediate (this week) · Short-term (this month) · Structural (this quarter)
## Owner
<Named human>
```

11. **Update artifacts.**
   - Add new eval cases to the golden dataset through a reviewed PR: run a PII scrubber on anything derived from production traces before commit, and confirm the case FAILS on the pre-fix version and passes after the fix (never edit an existing golden case to make it pass).
   - Add new adversarial cases to the CI test catalog if applicable.
   - Update the Decision Record if assumptions changed.
   - Update kill-switch tests if a new failure mode is now reachable.

12. **Calibrate.** If the incident reveals that composite-confidence weights or thresholds are wrong, schedule a recalibration. Don't change thresholds during the incident.

## Default stance

- **Stabilize before investigating.** Do not let curiosity about root cause delay killing the bleeding.
- **Trust the kill switch.** If it exists and is tested, pulling it is rarely the wrong call. The alternative — letting the incident continue while you debug — almost always is.
- **Capture before changing.** Every change after the incident starts erases evidence. Snapshot versions, logs, and sample outputs first.
- **Don't recalibrate thresholds mid-incident.** Tempting, but you don't have the data yet. Schedule it post-mortem.
- **Every failure is labeled data.** The single most valuable artifact from an incident is the new eval case it generates.

## What this skill does NOT do

- It does not page on-call. Use your incident comms process.
- It does not authorize destructive reversals (refunds, retractions). Those need human approval per the feature's risk tier.
- It does not replace the team's general incident management playbook — it complements it with AI-specific steps.
- It does not cover non-AI production incidents → `.claude/skills/deployment-ci-cd/reference/production-incident-runbook.md`.

## If this skill cannot proceed

```
Abort condition: no Decision Record exists for the feature
→ Cannot determine rollback triggers or named owner.
→ Output: "No Decision Record at docs/ai-decisions/<feature-slug>.md.
  Proceed without it, but rollback decisions must be made manually.
  After the incident, run /ai-audit to retroactively create one."

Abort condition: kill switch location unknown
→ Output: "Kill switch location not documented. Escalate to the engineering team
  to locate the feature flag manually. Do not attempt ad-hoc mitigations."

Abort condition: user wants to recalibrate thresholds during Stage 2/3
→ Hard stop. Output: "Do not recalibrate thresholds mid-incident. You don't have
  reliable data yet. Schedule recalibration in the Stage 4 post-mortem."
```

## Verify (Stage 2 completion check)

After Stage 2, before moving to Stage 3:

```
✅ Feature flag toggled or version rolled back — confirmed in deployment logs
✅ Bad outputs quarantined or retracted — confirmed in system
✅ On-call owner notified — confirmed via comms channel
✅ Crime scene captured — versions, sample inputs/outputs, time window logged
✅ Leading indicators checked — no cascading issues spreading
```

## References

- AI Playbook Layer 4 §4.3 Incident response: `.claude/skills/ai-playbook/playbook.md`
- AI Playbook Layer 4 §4.4 Kill switch tests: `.claude/skills/ai-playbook/playbook.md`
- Post-mortem template: embedded in Stage 4 of this skill
- New evals after incident: dispatch the `ai-eval-designer` agent (it is an agent, not a slash command) with the incident case as input
- AI incident categories, severity factors and evidence fields: `.claude/skills/ai-governance/SKILL.md` (GOV §13); record schema and validator: `.claude/skills/ai-governance/`
- Incident runbook (types I1–I11, SEV1–SEV4 criteria, ladder, playbook steps, evidence privacy, notification decision points D1–D6, recovery, closure, PIR rules, drills, adoption checklist): `reference/runbook-playbooks.md`; severity crosswalk incl. runbook SEV1–SEV4 and P0–P3: `.claude/skills/ai-governance/reference/supply-chain-eval-and-release.md` §7.1
- Trace fields to read during an incident: `.claude/skills/deployment-ci-cd/reference/ai-observability.md` §6, §10
- Rollback, flags/kill switches and incident replay into the golden set before re-promoting: `.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` §5, §8, §9
