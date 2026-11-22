# Cloud Run Infrastructure

> For non-scaffolded projects, fetch `https://google.github.io/adk-docs/deploy/cloud-run/index.md`.

## Session Types

| Type | Configuration | Use Case |
|------|--------------|----------|
| **In-memory** | Default (`session_service_uri = None`) | Local dev only; state lost on instance restart |
| **Cloud SQL** | `--session-type cloud_sql` at scaffold time; in code `DatabaseSessionService(db_url="postgresql+asyncpg://...")` (needs `sqlalchemy[asyncio]` + `asyncpg`) | Production persistent sessions |
| **Agent Engine** | `session_service_uri = agentengine://{resource_name}` | Agent Engine as session backend for Cloud Run deployments |

Cloud SQL session infrastructure (instance, database, Cloud SQL Unix socket volume mount) is configured in `deployment/terraform/service.tf`.

## Dockerfile

Use the canonical multi-stage `uv` Dockerfile in `deployment-ci-cd/reference/python-ci-supply-chain.md` §8. Check a scaffolded `Dockerfile` against it:

- uv image pinned by version **and** digest (`ghcr.io/astral-sh/uv:<x.y.z>@sha256:<digest>`), never `:latest`
- `uv sync --locked --no-dev` (`--frozen` installs a stale lock without checking it)
- base image pinned, non-root user, no `ENV` with keys or credentials (model access is keyless ADC)

## Scaling Defaults

Key settings in `deployment/terraform/service.tf` to review and tune:

| Setting | Description | Default guidance |
|---------|-------------|-----------------|
| `cpu_idle` | CPU allocation strategy — `true` = throttle when idle | Set `false` for latency-sensitive agents |
| `min_instance_count` | Minimum running instances | Set `> 0` to avoid cold starts in production |
| `max_instance_request_concurrency` | Concurrent requests per instance | Lower for memory-heavy agents |
| `session_affinity` | Sticky routing — routes same user to same instance | Required when using in-memory session type |

Check `service.tf` for current values before deploying — scaffold sets these to reasonable defaults.

## Network & Ingress

Default ingress is `INGRESS_TRAFFIC_ALL` (public). Change `ingress` in `service.tf` as needed:

| Ingress Setting | Access |
|----------------|--------|
| `INGRESS_TRAFFIC_ALL` | Public internet (default) |
| `INGRESS_TRAFFIC_INTERNAL_ONLY` | VPC-internal only |
| `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` | Internal + Google Cloud Load Balancer |

VPC connectors are not configured by default. Add them in custom Terraform if the agent needs access to private resources (Cloud SQL in private VPC, Memorystore, etc.). See `reference/terraform-patterns.md`.

## IAP Auth

Identity-Aware Proxy restricts access to authorized Google accounts only — no code changes required.

```bash
# Deploy with IAP
make deploy IAP=true

# Deploy with IAP + custom frontend on different port
make deploy IAP=true PORT=5173
```

After deploying, grant user access via the Cloud Console IAP settings or:

```bash
gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service=SERVICE_NAME \
  --region=REGION \
  --member="user:user@example.com" \
  --role="roles/iap.httpsResourceAccessor"
```

## Testing Cloud Run

```bash
SERVICE_URL="https://SERVICE_NAME-PROJECT_NUMBER.REGION.run.app"
AUTH="Authorization: Bearer $(gcloud auth print-identity-token)"

# Health check
curl -H "$AUTH" "$SERVICE_URL/"

# Create a session (required before sending messages)
curl -X POST "$SERVICE_URL/apps/app/users/test-user/sessions" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{}'
# Returns JSON with "id" — use as SESSION_ID

# Send a message via SSE streaming
curl -X POST "$SERVICE_URL/run_sse" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "app_name": "app",
    "user_id": "test-user",
    "session_id": "SESSION_ID",
    "new_message": {"role": "user", "parts": [{"text": "Hello!"}]}
  }'
```

> **Auth required by default.** Cloud Run deploys with `--no-allow-unauthenticated`. A 403 without the Bearer token is expected. To allow public access, redeploy with `--allow-unauthenticated`.

> **Common 422 mistake:** Using `{"message": "Hello!"}` instead of `{"new_message": {"role": "user", "parts": [{"text": "Hello!"}]}}`. Use the schema shown above.

## Rollback

```bash
# List revisions
gcloud run revisions list --service=SERVICE_NAME --region=REGION

# Shift 100% traffic to a previous revision
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=REVISION_NAME=100 --region=REGION
```
