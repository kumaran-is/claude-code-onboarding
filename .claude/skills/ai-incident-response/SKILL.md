---
name: ai-incident-response
description: Run the AI incident response procedure when something is going wrong in production AI. Use when the user explicitly runs /ai-incident-response or says "AI incident", "model is broken", "production AI is failing", "we're seeing weird outputs in prod", "hallucination in production", or similar urgent phrasing.
disable-model-invocation: true
allowed-tools: Read, Write
last-reviewed: 2026-11-22
metadata:
  triggers: AI incident, model is broken, hallucination in production, AI outage, provider quota exhausted
  related-skills: ai-playbook, ai-decision-record, ai-launch-check, ai-incident-response, ai-audit
---

# AI Incident Response

## Iron Law

**Stabilize before investigating. Pull the kill switch or roll back before debugging root cause. Curiosity about why it broke must never delay stopping the bleeding.**

When AI production behavior degrades, follow the procedure from the AI Playbook (Layer 4 §4.3). The objective: stabilize first, investigate second, learn third.

## Stage 1: Stabilize (first 15 minutes)

Do these in order. Do not investigate root cause yet — that comes after the bleeding stops.

1. **Confirm scope.** Ask the user:
   - What feature is affected?
   - What is the symptom? (Wrong outputs / latency spike / cost spike / refusals / safety violation / user reports)
   - When did it start?
   - Is it ongoing right now?

2. **Decide on rollback or kill.** Check the Decision Record for rollback triggers. If the symptom matches:
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

10. **Write the post-mortem.** Use this template:

```md
# Post-Mortem: <Feature Name> — <Date>

## Summary
- What happened (one paragraph)
- Severity (S0 / S1 / S2 / S3)
- User impact
- Duration: <detection time> → <stabilization time> → <full recovery>

## Timeline
- <time>: <event>
- <time>: <event>
- ...

## Root cause
<the actual cause, not the symptom>

## Why our controls didn't catch this
- Output Contract: ...
- Evals: ...
- Adversarial tests: ...
- Leading indicators: ...
- Kill switch / rollback: ...

## Eval gap — new test cases to add
- <input> → <expected> (was: <actual>)
- ...

## Prevention
- Immediate (this week): ...
- Short-term (this month): ...
- Structural (this quarter): ...

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
- Trace fields to read during an incident: `.claude/skills/deployment-ci-cd/reference/ai-observability.md` §6, §10
- Rollback, flags/kill switches and incident replay into the golden set before re-promoting: `.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md` §5, §8, §9
