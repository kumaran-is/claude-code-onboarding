# Docker Orchestration Reference

Read when health-check waits, port conflicts, or compose-file orchestration cause issues.

## Required project layout

```
your-mcp-project/
├── docker-compose.yml           # service: mcp-server with healthcheck
├── Dockerfile                   # builds the MCP server
├── tests/
│   ├── mcp_test_client.py       # copied from the skill's scripts/
│   ├── scenarios.yaml           # the spec
│   ├── run_validation.sh        # copied from the skill's scripts/
│   └── validation_report.json   # generated
└── CLAUDE.md                    # includes feedback_loop.md block
```

## docker-compose.yml minimum

```yaml
services:
  mcp-server:
    build: .
    ports:
      - "8080:8080"
    environment:
      - LOG_LEVEL=debug
      # auth tokens, DB URLs, etc.
    healthcheck:
      # Python images with curl. Node slim/distroless images have no curl or wget: use
      # ["CMD", "node", "-e", "fetch('http://127.0.0.1:8080/health/live').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 5s
      timeout: 3s
      retries: 6
      start_period: 10s
```

A TypeScript SDK v2 server bound to `0.0.0.0` in the container also needs `MCP_ALLOWED_HOSTS` (hostnames without
port, e.g. `127.0.0.1,localhost`) and `MCP_ALLOWED_ORIGINS`; a `Host` outside the list gets 403 on every route,
health included ([production-deployment-docker.md](../../mcp-builder/reference/production-deployment-docker.md) §0).

The `healthcheck` block is what `run_validation.sh` polls indirectly (it
hits the URL itself, but Docker's healthcheck affects `docker compose ps`
output, useful for diagnostics).

## Wait strategies (ranked best to worst)

1. **HTTP poll on `/health`** (current default in `run_validation.sh`)
2. **Docker healthcheck status poll** — `docker inspect ... --format '{{.State.Health.Status}}'`
3. **Fixed `sleep 10`** — fragile, never use this in a feedback loop

## Common failure modes

### Port already in use
Symptom: `bind: address already in use` during `docker compose up`.
Fix: orchestrator's `--force-recreate` handles re-creating the container,
but if another process owns the port, you'll need to stop it. Check:
```bash
lsof -i :8080
```

### Health endpoint missing
If your MCP server doesn't expose `/health`, add one next to the `/mcp` route of the
ASGI or HTTP app that serves it (for example a Starlette `Route("/health", ...)` beside
`mcp.streamable_http_app()`, or an Express/Fastify route beside the TypeScript handler).
Keep it unauthenticated and free of MCP calls, so it reports process health only.

### Container exits immediately
The validator will time out on health check. Diagnose with:
```bash
docker compose logs --tail=100 mcp-server
```
The orchestrator dumps these logs automatically on health-check timeout.

### Auth secrets in containers
Use `.env` file referenced from `docker-compose.yml`:
```yaml
env_file:
  - .env.test
```
Never commit `.env.test`. Add to `.gitignore`. The validator
reads `SERVER_URL` etc. from environment, so the same `.env.test` can be
sourced before running `bash tests/run_validation.sh`.

### stdio transport (for MCP servers without HTTP)

If your MCP server only supports stdio, skip Docker entirely for testing:
```bash
SERVER_URL="stdio://python -m mcp_server" \
HEALTH_URL="" \
bash tests/run_validation.sh
```
The reference `run_validation.sh` skips every Docker step when `HEALTH_URL` is empty.
