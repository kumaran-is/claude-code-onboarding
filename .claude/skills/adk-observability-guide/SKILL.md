---
name: adk-observability-guide
description: "ADK observability, Cloud Trace, prompt logging, agent analytics, BigQuery agent logs, ADK monitoring, ADK telemetry. Use when configuring tracing, logging, or analytics for ADK agents, debugging production agent behavior, or setting up monitoring for a deployed agent."
allowed-tools: Bash, Read, Write, Edit, WebFetch
metadata:
  triggers: ADK observability, Cloud Trace, prompt logging, agent analytics, BigQuery agent logs, ADK monitoring, ADK telemetry
  related-skills: google-adk, agentic-ai-dev, python-dev
  domain: backend
  role: specialist
  scope: observability
  output-format: code
last-reviewed: "2026-11-23"
---

# ADK Observability Guide

## Iron Law

**NEVER ship a production ADK agent without tracing enabled (`get_fast_api_app(..., trace_to_cloud=True)` or `otel_to_cloud=True`) AND message-content capture locked OFF (all three variables in "Content capture" below). Prompt/response logging (`LOGS_BUCKET_NAME`) stores user content: enable it only with a written retention, access and deletion decision.**

Framework-neutral AI tracing (span names, GenAI semconv attributes, token/TTFT metrics, prompt provenance, redaction, alerts) lives in `.claude/skills/deployment-ci-cd/reference/ai-observability.md`; this skill covers the ADK and Google Cloud specifics.

## Reference Files

| File | Contents |
|------|----------|
| `reference/cloud-trace-and-logging.md` | Cloud Trace setup, prompt-response logging infrastructure, environment variables, enabling/disabling locally, verification commands |
| `reference/bigquery-agent-analytics.md` | BigQuery Agent Analytics plugin — enabling, key features, tool provenance tracking |
| `reference/slo-alerting.md` | ADK/Prometheus SLO burn-rate alerting (alert catalog and owners: `ai-observability.md`) (vs threshold alerting), multi-window pattern, error budget tracking, PromQL examples for availability/latency/safety SLOs | Setting up production alerts for agentic AI services |

---

## Observability Tiers

| Tier | What It Does | Default State | Best For |
|------|-------------|---------------|----------|
| **Tier 1: Cloud Trace** | Distributed tracing — execution flow, latency, errors via OpenTelemetry spans | Always-on | Debugging latency, understanding agent execution flow |
| **Tier 2: Prompt-Response Logging** | GenAI interactions exported to GCS, BigQuery, and Cloud Logging | Disabled locally; enabled when deployed | Auditing LLM interactions, compliance |
| **Tier 3: BigQuery Agent Analytics** | Structured agent events (LLM calls, tool use, outcomes) to BigQuery | Opt-in (`--bq-analytics` at scaffold time) | Conversational analytics, custom dashboards, LLM-as-judge evals |
| **Tier 4: SLO Alerting** | SLO-based burn-rate alerts (availability, latency, safety) via Prometheus — fires only when error budget is genuinely at risk | Opt-in — requires Prometheus + Alertmanager stack | Production alerting for agentic AI services; replaces naive threshold alerts |

Ask the user which tier(s) they need — they can be combined. Tier 1 is mandatory; Tiers 2, 3, and 4 are additive.

---

## Quick Setup

### Tier 1: Cloud Trace (Always-On)

```python
# Self-hosted FastAPI app (scaffolded projects have this pre-configured)
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(agents_dir="./agents", web=False, trace_to_cloud=True)
# otel_to_cloud=True exports traces, metrics and logs to Google Cloud (marked experimental in ADK source)
```

`trace_to_cloud` needs `GOOGLE_CLOUD_PROJECT` set, otherwise ADK logs a warning and exports nothing. There is no `google.adk.telemetry.setup_telemetry(...)` in the ADK docs: an earlier version of this skill showed it; use the `get_fast_api_app` options (verified against the ADK `fast_api` guide and `cli/fast_api.py` source on Context7; re-check option names on your pinned ADK version).

### Content capture (lock it in every deployed environment)

```bash
export ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false                  # ADK's own (legacy) spans
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT  # GenAI log records + OTel-spec spans
export ADK_TELEMETRY_IGNORE_RUN_CONFIG=1                           # app code cannot re-enable per request
```

Verified on `google-adk==2.15.0` (fixture model, in-memory exporter; **2.15.1 re-run: NOT TESTED**): with none of these set, the default 1.44 schema recorded no prompt text, but `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY` or the legacy opt-in `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36` (where `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` defaults to `true`) put it into span attributes. Set all three explicitly anyway: the first alone leaves the OpenTelemetry paths at their defaults, and without the third a per-request `capture_message_content` setting overrides the environment (ADK telemetry-config guide; `ADK_TELEMETRY_IGNORE_RUN_CONFIG` is read in `google/adk/telemetry/context.py` on 2.15.0).

View traces: **Cloud Console > Trace > Trace explorer**

### Tier 2: Prompt-Response Logging

```bash
# Enable locally
export LOGS_BUCKET_NAME="your-bucket-name"
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="NO_CONTENT"   # metadata only
```

Stored prompts and responses are sensitive production data: organization isolation, role-based access, a retention TTL, access audit, and deletion that reaches the bucket, BigQuery tables and eval copies.

See `reference/cloud-trace-and-logging.md` for full infrastructure list, env vars, and verification commands.

### Tier 3: BigQuery Agent Analytics

```bash
# Enable at scaffold time
uvx agent-starter-pack create . --bq-analytics
```

See `reference/bigquery-agent-analytics.md` for post-scaffold manual setup and key features.

---

## Process

1. **Confirm tier(s)** — Ask which tiers the user needs before configuring anything
2. **Read reference files** — See `reference/cloud-trace-and-logging.md` (Tier 1 & 2) or `reference/bigquery-agent-analytics.md` (Tier 3) before writing any configuration
3. **Check env vars** — Verify all required environment variables are set (table in `reference/cloud-trace-and-logging.md`)
4. **Verify with commands** — Use the verification commands in `reference/cloud-trace-and-logging.md` to confirm telemetry is flowing
5. **Check costs** — High telemetry volume? Switch to `NO_CONTENT` mode; reduce BigQuery retention; disable unused tiers

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No traces in Cloud Trace | Verify `trace_to_cloud=True`/`otel_to_cloud=True` in `get_fast_api_app`; `GOOGLE_CLOUD_PROJECT` set; SA has `cloudtrace.agent` role |
| Prompt-response data missing | Check `LOGS_BUCKET_NAME` is set; verify SA has `storage.objectCreator`; check app logs |
| Prompt text visible in spans | Set all three content-capture variables above; a per-request `capture_message_content` wins unless `ADK_TELEMETRY_IGNORE_RUN_CONFIG=1` |
| BigQuery Analytics not logging | Verify plugin in `app/agent.py`; check `BQ_ANALYTICS_DATASET_ID` env var |
| Traces missing tool spans | Tool spans appear under `execute_tool` — check trace explorer filters |

---

## Documentation Sources

| Topic | URL |
|-------|-----|
| ADK telemetry config (content capture) | `https://github.com/google/adk-python/blob/main/docs/guides/telemetry/telemetry_config/index.md` |
| Observability overview | `https://google.github.io/adk-docs/observability/index.md` |
| Agent activity logging | `https://google.github.io/adk-docs/observability/logging/index.md` |
| Cloud Trace integration | `https://google.github.io/adk-docs/integrations/cloud-trace/index.md` |
| BigQuery Agent Analytics | `https://google.github.io/adk-docs/integrations/bigquery-agent-analytics/index.md` |
