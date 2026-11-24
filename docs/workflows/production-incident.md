# Production Incident Response

> **When to use**: A bug is live in production — users are affected, errors are spiking, or a critical feature is broken
> **Time estimate**: Detection to mitigation: 15–60 min; Root cause + permanent fix: 2–8 hours
> **Prerequisites**: Access to production logs, monitoring dashboards, and deployment controls

## Overview

Structured production incident response: Detect → Assess → Mitigate → Diagnose → Fix → Post-mortem. Uses `error-detective` agent for log analysis, `systematic-debugging` skill for root cause, and `the-fool` skill for post-mortem.

---

## P0 vs P1 Classification

| Severity | Criteria | Target Mitigation Time |
|----------|---------|----------------------|
| **P0** | All users affected, data loss possible, security breach | 15 min |
| **P1** | Major feature broken, >20% users affected | 60 min |
| **P2** | Feature degraded, <20% users affected, workaround exists | 4 hours |
| **P3** | Minor issue, workaround exists, not data-impacting | Next business day |

---

## Phase 1 — Detect and Assess (0–5 minutes)

**What happened?**
- Error rate: current vs baseline
- Which endpoints / features are affected?
- When did it start? (correlate with last deployment)
- How many users affected?

**Quick diagnostic commands**:
```bash
# Cloud Run logs (last 15 min)
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit=100 \
  --freshness=15m \
  --format="table(timestamp,textPayload)"

# Error rate from Cloud Monitoring
gcloud monitoring metrics list --filter="metric.type=run.googleapis.com/request_count"

# Recent deployments
gcloud run revisions list --service=my-service --region=us-central1
```

**Classify severity** using the table above. If P0 or P1, immediately go to Phase 2 (mitigate) before diagnosing.

---

## Phase 2 — Mitigate (5–15 minutes for P0/P1)

**Option A — Rollback** (fastest, use when last deploy caused the issue):
```bash
# Cloud Run — revert to previous revision
gcloud run services update-traffic my-service \
  --to-revisions=my-service-00099-PREV=100 \
  --region=us-central1

# Verify rollback
curl -f https://my-service-url/health
```

**Option B — Scale mitigation** (if resource-related):
```bash
# Increase max instances if overloaded
gcloud run services update my-service \
  --max-instances=50 \
  --region=us-central1
```

**Option C — Feature flag off** (if feature-scoped):
- Disable the specific feature via config/env var
- Redeploy without the breaking feature

**Option D — Read-only mode** (if DB is the issue):
- Return cached/degraded responses
- Block write operations temporarily

**Mitigation by target** — the commands above are for Cloud Run services. Other targets stop the bleeding differently:

| Target | Fastest mitigation | Reference |
|---|---|---|
| Angular / React on static hosting | Promote the previous release (same files, no rebuild), then re-run the post-deploy header check | `.claude/skills/deployment-ci-cd/reference/web-frontend-delivery.md` §4 |
| Flutter Android (Google Play) | Halt the staged rollout (`gpd publish halt`); a halted build stops reaching new users but stays on devices that already updated | `.claude/skills/gpd-build-lifecycle/SKILL.md` |
| Flutter iOS (App Store) | Pause the phased release in App Store Connect; a shipped build cannot be recalled, so disable the feature by remote config and ship a fix build | `.claude/skills/asc-release-flow/SKILL.md` |
| AI feature (LLM, agent, RAG) | Pull the AI kill switch or roll back the prompt/model version, then follow the AI runbook; classify as AI-SEC, AI-DATA, AI-TENANT, AI-MEM, AI-ACTION, AI-EVAL, AI-PROVIDER, AI-COST, AI-OVERSIGHT or AI-SUPPLY (a blocked attempt is not automatically as severe as a successful mutation) | `/ai-incident-response`, `.claude/skills/deployment-ci-cd/reference/llmops-release-and-rollout.md`, `incident_record` schema in `.claude/skills/ai-governance/` |
| MCP server | Roll back the server revision (Cloud Run as above) or remove the server from client config; revoke any credential it could have leaked | `.claude/skills/mcp-builder/reference/production-deployment-structure.md` |
| GenUI (A2UI) surface | Stop the agent emitting the faulty component or action, or remove it from the catalog; renderers must already show the unknown-component fallback | `.claude/skills/genui-contract/SKILL.md` |

Verify the mitigation on the affected target itself (a Flutter fix is proven on a device with Maestro, never in a browser — `.claude/rules/testing-tool-selection.md`).

**Gate**: User-facing errors must drop before leaving Phase 2.

---

## Phase 3 — Diagnose (dispatch `error-detective`)

**Agent**: `error-detective`

**Provide to the agent**:
- Log samples (paste directly or provide log filter)
- Time range: when errors started
- What changed: last deployment SHA, config changes
- Which services are involved

**Agent will**:
- Parse logs with regex to find patterns
- Correlate errors across services
- Identify the root cause from runtime data
- Produce: `CAUSE:`, `AFFECTED:`, `TRIGGER:` summary

**Manual log analysis** (while agent runs):
```bash
# Find the first error occurrence
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" \
  --freshness=2h \
  --limit=1000 \
  --format=json | jq '.[] | {time: .timestamp, msg: .textPayload}' | head -20

# Grep for specific error class
gcloud logging read "textPayload=~\"NullPointerException\"" --freshness=1h
```

---

## Phase 4 — Root Cause Analysis

**Skill**: Load `systematic-debugging`

After `error-detective` identifies the pattern:
1. Read the specific code at the identified location
2. Trace the execution path that leads to the error
3. Identify why production exhibits this behavior but staging didn't

**Common production-only causes**:

| Cause | Investigation |
|-------|--------------|
| Config difference | Compare staging vs prod env vars |
| Data edge case | Look at what data the failing request had |
| Load-related | What was the request rate at failure time? |
| Third-party failure | Check external service status pages |
| Deployment artifact | Compare Docker image SHA between working and broken |
| Race condition | Look for concurrent requests at the same timestamp |

---

## Phase 5 — Permanent Fix

Once mitigation is in place and root cause is known:

1. Write a failing test that reproduces the root cause
2. Fix the code
3. Verify the regression test passes
4. Run full test suite
5. Deploy to staging; verify fix works
6. Deploy to production with staged rollout (10% → 25% → 100%)
7. Monitor error rate for 30 min after each rollout step

```bash
# Staged production rollout after fix
gcloud run services update-traffic my-service \
  --to-revisions=my-service-NEW=10 \
  --region=us-central1

# Monitor for 15 min, then:
gcloud run services update-traffic my-service \
  --to-revisions=my-service-NEW=100
```

---

## Phase 6 — Post-Mortem

**Skill**: Load `the-fool` (adversarial questioning)
**Create**: `docs/post-mortems/YYYY-MM-DD-<incident-title>.md`

**Blameless post-mortem structure**:
```markdown
# Post-Mortem: [Incident title]
Date: [YYYY-MM-DD]
Duration: [start] → [resolution]
Severity: P0/P1/P2
Affected users: [N]

## Timeline
[HH:MM] — [Event]
[HH:MM] — [Action taken]
[HH:MM] — [Resolution]

## Root Cause
[One paragraph: what caused it, why it wasn't caught in testing]

## Contributing Factors
- [Factor 1]
- [Factor 2]

## Detection Gap
How long between incident start and detection? Why?

## What Went Well
- [Rollback was fast]
- [Monitoring caught it before users reported]

## What Went Wrong
- [No staging test for this case]
- [Rollback procedure was unclear]

## Action Items
| Item | Owner | Due |
|------|-------|-----|
| Add test for [edge case] | [name] | [date] |
| Add alert for [metric] | [name] | [date] |
| Document rollback procedure | [name] | [date] |
```

**The-fool questions for post-mortem**:
- "What assumption was wrong?"
- "What would have caught this in staging?"
- "If this exact failure happened again in 6 months, what would catch it earlier?"
- "What's the simplest thing that would have prevented this?"

---

## Quick Reference

| Phase | Action | Target Time |
|-------|--------|------------|
| 1 — Detect | Classify severity P0/P1/P2/P3 | 0–5 min |
| 2 — Mitigate | Rollback / scale / feature flag | 5–15 min (P0) |
| 3 — Diagnose | `error-detective` agent + log analysis | 15–60 min |
| 4 — Root cause | `systematic-debugging` skill | 30 min – 2 hours |
| 5 — Fix | Test → fix → staged rollout | 1–4 hours |
| 6 — Post-mortem | `the-fool` + blameless doc | Within 48 hours |

---

## Common Pitfalls

- **Diagnosing before mitigating** — users are affected NOW; rollback first, understand later
- **Full rollout of the fix** — always stage the fix (10% traffic) before 100%; the fix itself can have bugs
- **Skipping post-mortem** — without it, the same class of incident recurs within 3 months
- **Blame-focused post-mortem** — who did what is irrelevant; what system failure allowed it is the question
- **No regression test after fix** — if there's no test, the bug will come back

## Related Workflows

- [`bug-fix.md`](bug-fix.md) — non-production bug fix workflow
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — rollback via Cloud Run traffic splitting
- [`security-audit.md`](security-audit.md) — if incident was security-related
