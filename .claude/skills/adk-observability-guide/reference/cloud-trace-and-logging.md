# Cloud Trace & Prompt-Response Logging

> **Assumes scaffolded project.** Observability infrastructure is provisioned by Terraform in scaffolded projects. For manual setup, fetch `https://google.github.io/adk-docs/integrations/cloud-trace/index.md`.

## Cloud Trace

Distributed tracing via `get_fast_api_app(..., trace_to_cloud=True)` (or `otel_to_cloud=True`, experimental) in the FastAPI app. Tracks every agent invocation through LLM calls and tool executions with latency analysis and error visibility.

```python
# Scaffolded projects — pre-configured. Manual projects — add this:
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(agents_dir="./agents", web=False, trace_to_cloud=True)
```

View traces: **Cloud Console > Trace > Trace explorer**

### Span Hierarchy

```
invoke_workflow <root>
  └── invoke_agent <agent>
        ├── generate_content <model>
        ├── execute_tool <tool>
        └── generate_content <model>
```

Captured on `google-adk==2.15.0` with an in-memory exporter (fixture model, not live). Since 2.13 the default is the OTel GenAI semantic conventions 1.44 schema: the old `call_llm` span is gone, so dashboards and alerts keyed on it go silent after the upgrade. `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=otel_semconv_1_36` restores the legacy schema temporarily; migrate queries instead.

No additional configuration required. Works in local dev (`make playground`) and all deployed environments.

## Prompt-Response Logging Infrastructure

All provisioned automatically by `deployment/terraform/telemetry.tf`:

- **Cloud Logging bucket** — analytics enabled, dedicated to GenAI telemetry. Read the retention in `telemetry.tf` (template defaults have been very long) and set it to your written retention decision: this bucket can hold user content
- **Log sinks** — Route GenAI inference logs and feedback logs to the telemetry bucket
- **Linked dataset** — Cloud Logging bucket linked to BigQuery for SQL access
- **GCS logs bucket** — Stores completions as NDJSON
- **BigQuery dataset** — External tables over GCS data, linked dataset from Cloud Logging
- **BigQuery connection** — Service account for GCS access from BigQuery

Check `deployment/terraform/telemetry.tf` for exact configuration. IAM bindings are in `iam.tf`.

## Environment Variables

Set automatically by Terraform on the deployed service:

| Variable | Purpose |
|----------|---------|
| `LOGS_BUCKET_NAME` | GCS bucket for completions and logs. Required to enable prompt-response logging |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Content capture mode; `NO_CONTENT` in deployed environments (lock with the two ADK variables in `SKILL.md` "Content capture") |
| `BQ_ANALYTICS_DATASET_ID` | BigQuery dataset for telemetry |
| `BQ_ANALYTICS_CONNECTION_ID` | BigQuery connection for GCS access |
| `GENAI_TELEMETRY_PATH` | Optional: override upload path within bucket (default: `completions`) |

## Enabling / Disabling

### Enable Locally

Set these before running `make playground`:

```bash
export LOGS_BUCKET_NAME="your-bucket-name"
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="NO_CONTENT"
```

### Disable in Deployed Environments

Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT` in `deployment/terraform/service.tf` and re-apply Terraform.

## BigQuery Dataset Naming Convention

BigQuery dataset names cannot contain hyphens. Terraform automatically converts hyphens to underscores:

- Project name `my-agent` → BQ dataset `my_agent_telemetry`

Two datasets are created:

- **`{name}_telemetry`** — External tables over GCS completions data (NDJSON)
- **`{name}_genai_telemetry_logs`** — Linked dataset from Cloud Logging bucket

To discover actual dataset names in your project:

```bash
bq ls --project_id=${PROJECT_ID}
```

## Verification Commands

After deploying, verify prompt-response logging is working:

```bash
PROJECT_ID="your-dev-project-id"
PROJECT_NAME="your-app-name"  # starter pack project name, not GCP project ID

# Check GCS data
gsutil ls gs://${PROJECT_ID}-${PROJECT_NAME}-logs/completions/

# Check Cloud Logging bucket
gcloud logging buckets describe ${PROJECT_NAME}-genai-telemetry \
  --location=us-central1 --project=${PROJECT_ID}

# Query BigQuery
bq query --use_legacy_sql=false \
  "SELECT * FROM \`${PROJECT_ID}.${PROJECT_NAME}_telemetry.completions\` LIMIT 10"
```

If data is not appearing: check `LOGS_BUCKET_NAME` is set; verify SA has `storage.objectCreator` on the bucket; check application logs for telemetry setup warnings.
