# Production Incident Runbook (non-AI)

General runbook for a live production bug: users affected, errors spiking, a critical flow broken. Order: **detect → classify → mitigate → diagnose → fix → post-mortem.** Mitigate before diagnosing: users are affected now. AI features (LLM, agent, RAG, model output) use `.claude/skills/ai-incident-response/` instead; it adds kill-switch rungs, AI categories and the incident record.

## 1. Classify

| Severity | Criteria | Target mitigation |
|---|---|---|
| **P0** | All users affected, possible data loss, or a security breach | 15 min |
| **P1** | Major feature broken or > 20% of users affected | 60 min |
| **P2** | Feature degraded, < 20% of users, workaround exists | 4 h |
| **P3** | Minor, workaround exists, no data impact | Next business day |

P0/P1 → mitigate (§3) before any diagnosis. A security breach also follows the security owner's process; preserve logs before changing anything.

## 2. Detect and assess (0–5 min)

Establish: error rate now vs baseline, affected endpoints/features, start time (correlate with the last deploy or config change), users affected.

```bash
# Errors in the last 15 min. Services log structured JSON, so the message is in jsonPayload, not textPayload
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="SERVICE" AND severity>=ERROR' \
  --freshness=15m --limit=100 \
  --format='table(timestamp, resource.labels.revision_name, jsonPayload.message)'

# Revisions and which one serves traffic (did a deploy just happen?)
gcloud run revisions list --service=SERVICE --region=REGION
```

**Error rate.** `gcloud monitoring metrics list` only lists metric *descriptors*; it returns no values. Read the rate from Cloud Monitoring Metrics Explorer: metric `run.googleapis.com/request_count` (resource `cloud_run_revision`), filter `response_code_class = "5xx"`, aligned as a rate, divided by the same metric unfiltered, grouped by `revision_name`. For a CLI count, request logs (log `run.googleapis.com/requests`) carry the standard `httpRequest.status` field:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="SERVICE" AND logName:"run.googleapis.com%2Frequests" AND httpRequest.status>=500' \
  --freshness=15m --format='value(timestamp)' | wc -l
```

Request-count data appears up to ~3 min late (sampled every 60 s, visible after up to 120 s).

## 3. Mitigate (stop the bleeding)

Cloud Run service:

| Option | When | Action |
|---|---|---|
| Roll back | Last deploy or config change caused it | `gcloud run services update-traffic SERVICE --to-revisions=PREVIOUS_REVISION=100 --region=REGION`, then check `/health` on the service URL |
| Scale | Resource exhaustion, healthy code | `gcloud run services update SERVICE --max-instances=N --region=REGION` (check DB connection limits first) |
| Feature flag off | One feature is at fault | Disable it by runtime config; no rebuild |
| Degrade / read-only | Database is the problem | Serve degraded responses visibly and reject writes with an explicit error; never return fake or empty data as success |

Other targets:

| Target | Fastest mitigation | Reference |
|---|---|---|
| Angular / React on static hosting | Promote the previous release (same files, no rebuild), re-run the post-deploy header check | `reference/web-frontend-delivery.md` |
| Flutter Android (Google Play) | Halt the staged rollout; devices that already updated keep the build | `.claude/skills/gpd-build-lifecycle/SKILL.md` |
| Flutter iOS (App Store) | Pause the phased release; a shipped build cannot be recalled, so disable the feature by remote config and ship a fix build | `.claude/skills/asc-release-flow/SKILL.md` |
| MCP server | Roll back the revision or remove the server from client config; revoke any credential it could have leaked | `.claude/skills/mcp-builder/reference/production-deployment-structure.md` |
| GenUI (A2UI) surface | Stop the agent emitting the faulty component/action or remove it from the catalog; renderers show the unknown-component fallback | `.claude/skills/genui-contract/SKILL.md` |
| AI feature | Kill switch / prompt or model rollback | `.claude/skills/ai-incident-response/` |

Verify on the affected target itself (a Flutter fix on a device with Maestro, never a browser: `.claude/rules/testing-tool-selection.md`). **Gate:** user-facing errors have dropped back to baseline before leaving this step.

## 4. Diagnose and find the root cause

Dispatch `error-detective` with: log samples or the log filter, the time range, what changed (deploy SHA, image digest, config) and the services involved. Its output ends in **ROOT CAUSE HYPOTHESIS (ranked)**, each with evidence, plus a recommended action. Then load `systematic-debugging`: read the code at the top hypothesis, trace the path, and explain why production differs from staging.

```bash
# First occurrences in the last 2 h, structured logs
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="SERVICE" AND severity>=ERROR' \
  --freshness=2h --limit=1000 --order=asc --format=json \
  | jq '.[] | {time: .timestamp, rev: .resource.labels.revision_name, msg: .jsonPayload.message, err: .jsonPayload.error}' | head -40
```

| Production-only cause | Check |
|---|---|
| Config difference | Staging vs production env and secrets (names, not values) |
| Data edge case | Inputs of the failing requests |
| Load | Request rate and instance count at failure time |
| Third-party failure | Provider status, timeouts, retry storms |
| Deployment artifact | Image digest of the working vs broken revision |
| Race condition | Concurrent requests at the same timestamp |

## 5. Permanent fix

1. Write a test that reproduces the root cause and fails on the current code.
2. Fix; the test passes; full suite green.
3. Deploy to staging and verify.
4. Deploy to production with `--no-traffic`, then shift traffic in steps (10% → 25% → 100%), watching the 5xx rate for each step before the next; roll back on regression.

## 6. Communication

- Name one incident lead; responders report to that person.
- P0/P1: status update to stakeholders at declaration, then on a fixed cadence (e.g. every 30 min) and at mitigation and resolution; user-facing status page if users are affected.
- Each update states: impact, current action, next update time. No speculation about cause before §4.
- Keep a timestamped timeline as you go; it becomes the post-mortem timeline.

## 7. Blameless post-mortem

Required for P0/P1, within 48 h; recommended for P2. Save as `docs/post-mortems/YYYY-MM-DD-<incident>.md`. Ask what system gap allowed the failure, never who caused it.

```markdown
# Post-Mortem: <incident>
Date · Duration (start → resolution) · Severity · Users affected

## Timeline            (HH:MM UTC: event / action / resolution)
## Root cause          (what failed and why tests and staging did not catch it)
## Contributing factors
## Detection gap       (time from start to detection, and why)
## What went well / what went wrong
## Action items        (item, owner, due date; at least one shortens detection time and one adds the regression test)
```

Load `the-fool` for the review: Which assumption was wrong? What would have caught this in staging? If it recurred in six months, what would catch it earlier? What is the simplest thing that would have prevented it?
