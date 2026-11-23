#!/usr/bin/env bash
# Build → deploy → wait for health → validate every tool.
# Exit: 0 GREEN, 1 RED, 2 COVERAGE_GAP, 3 CONNECTION (from the client); 10 build, 11 deploy, 12 health timeout.
# HEALTH_URL="" skips Docker entirely (stdio servers: SERVER_URL="stdio://<command> <args>").
set -euo pipefail

SERVER_URL="${SERVER_URL:-http://localhost:8080/mcp}"
HEALTH_URL="${HEALTH_URL-http://localhost:8080/health}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-mcp-server}"
SCENARIOS_FILE="${SCENARIOS_FILE:-tests/scenarios.yaml}"
TEST_CLIENT="${TEST_CLIENT:-tests/mcp_test_client.py}"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-60}"

if [[ -n "$HEALTH_URL" ]]; then
  docker compose -f "$COMPOSE_FILE" build "$COMPOSE_SERVICE" || exit 10
  docker compose -f "$COMPOSE_FILE" up -d --force-recreate "$COMPOSE_SERVICE" || exit 11
  deadline=$((SECONDS + HEALTH_TIMEOUT_S))
  until curl -fsS "$HEALTH_URL" > /dev/null; do
    if (( SECONDS >= deadline )); then
      echo "health check timed out after ${HEALTH_TIMEOUT_S}s: $HEALTH_URL" >&2
      docker compose -f "$COMPOSE_FILE" logs --tail=100 "$COMPOSE_SERVICE" >&2
      exit 12
    fi
    sleep 1
  done
fi

set +e
uv run python "$TEST_CLIENT" --server-url "$SERVER_URL" --scenarios "$SCENARIOS_FILE"
status=$?
set -e
echo "validation exit code: $status (report: tests/validation_report.json)" >&2
exit "$status"
