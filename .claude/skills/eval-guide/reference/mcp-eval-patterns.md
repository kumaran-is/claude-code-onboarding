# MCP and Tool-Server Eval Patterns

> Agent eval tells you whether the model reasoned correctly; tool eval tells you whether its tools are safe, scoped and correct. You need both. When agents reach external systems through an MCP server, that server is the enforcement point: a cross-scope input ID accepted, an unauthorized tool call that succeeds, or a write tool without an audit-log call is a hard blocker (R1 and R3), never a tracked regression.

Implementation code these tests exercise: `mcp-builder/reference/security-core.md` (auth, per-tool scopes, tenant from the token), `security-middleware-attacks.md` (side effects, idempotency, approvals), `security-pii-compliance.md` (audit record, redaction). Reviewer severities: `security-reviewer/reference/mcp-security.md`.

## Five layers per tool (per-tool ship gate)

Every tool covers all five layers before it ships. A tool missing a layer is NOT RUN for that layer, never PASS.

| Layer | What the tests prove | How | Tier |
|---|---|---|---|
| L1 Protocol contract | server starts; `tools/list` equals the expected set (no surprise tools); unknown tool → protocol error; tool failures are structured (`isError` + stable code) | contract tests through a real client + tool-surface lock (below) + Inspector CLI | R1 |
| L2 Schema validity | unknown field, missing required field, bad enum, out-of-range value, unsupported `schema_version` major, cross-scope id: each rejected **with no side effect**; output matches `outputSchema` | negative cases through the client, assert state unchanged | R1 |
| L3 Authorization + isolation | no/invalid token → 401; missing scope → 403 before the handler; a scope-A principal cannot read or write scope-B objects; foreign id answers exactly like a missing id | **deterministic tests only — never an LLM judge** | R1, block on any failure |
| L4 Security | injection via tool descriptions, resources and retrieved documents; privilege escalation; SQL/shell injection; path traversal; SSRF; mass action | red-team runner with an MCP target + scenario scans (red-team configs live with the red-team corpus) | R1 critical subset (path-routed), R2 full |
| L5 Trajectory through tools | right tools, right order, right inputs; forbidden tools never called; redundant calls within budget | framework trajectory eval (`adk eval`, DeepEval MCP metrics) + the redundant-call metric below | R1 smoke, R2 full |

**Minimum cases per tool (default, ADAPT upward):** 5 — happy path, auth failure, schema-invalid, scope mismatch, downstream timeout/failure. Tool cases live in `tools/contract_cases.jsonl` and `tools/schema_negative_cases.jsonl` with the shape `id, tool, caller {role, scope_id}, input, expected {result, audit_log_required}, risk_level, tags` (golden-dataset layout: [golden-dataset.md](golden-dataset.md)).

**Graceful degradation:** every tool with a fallback has a failure-injection test (100% of such tools) proving the failure yields a safe, visible, typed result (`UPSTREAM_UNAVAILABLE`, retry hint) and never fabricated data such as an empty list or `0`.

## Contract tests (Python, any server language)

Deterministic, no model. Verified 2026-11-23 with `mcp` 2.3.0, `httpx2` 2.16.2, pytest 9.2.0 on Python 3.14.10 against a TypeScript SDK v2 (`@modelcontextprotocol/server` 2.4.0) server over Streamable HTTP: 4 passed; with the server's tenant filter removed, the cross-scope test failed (negative control).

```python
# tests/eval/mcp/test_tool_contract.py  (R1: deterministic, no model, no judge)
import json
import os

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

URL = os.environ["MCP_URL"]                      # e.g. http://127.0.0.1:8080/mcp
TOKEN_A = os.environ["MCP_TOKEN_SCOPE_A"]        # test principals from your test IdP
TOKEN_B = os.environ["MCP_TOKEN_SCOPE_B"]
OWN_ID_A, MISSING_ID = "ord_001", "ord_999"      # ADAPT: fixture ids; OWN_ID_A belongs to scope A
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def call(token: str, tool: str, args: dict):
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
        async with Client(streamable_http_client(URL, http_client=http)) as client:
            return await client.call_tool(tool, args)


def text(result) -> str:
    return "\n".join(block.text for block in result.content if block.type == "text")


async def test_cross_scope_input_id_is_refused_like_a_missing_id() -> None:
    """Hard blocker: a tool accepts a cross-scope input ID."""
    foreign = await call(TOKEN_B, "orders_get", {"schema_version": "1.0", "order_id": OWN_ID_A})
    missing = await call(TOKEN_B, "orders_get", {"schema_version": "1.0", "order_id": MISSING_ID})
    assert foreign.is_error and missing.is_error
    assert text(foreign) == text(missing)        # no existence oracle across scopes


async def test_invalid_token_is_401_with_resource_metadata() -> None:
    async with httpx2.AsyncClient() as http:
        response = await http.post(URL, headers={"Authorization": "Bearer forged"}, json={})
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


async def test_reused_idempotency_key_with_changed_payload_is_rejected() -> None:
    base = {"schema_version": "1.0", "order_id": OWN_ID_A, "reason": "late", "expected_order_version": 1,
            "idempotency_key": "contract-key-0000000001"}
    first = await call(TOKEN_A, "refunds_create", {**base, "amount_cents": 100})
    replay = await call(TOKEN_A, "refunds_create", {**base, "amount_cents": 100})
    changed = await call(TOKEN_A, "refunds_create", {**base, "amount_cents": 900})
    assert not first.is_error
    assert replay.structured_content["refund_id"] == first.structured_content["refund_id"]
    assert changed.is_error and "IDEMPOTENCY_PAYLOAD_MISMATCH" in text(changed)


def redundant_calls(trajectory: list[dict]) -> int:
    """Tool-call efficiency: repeats of an identical (tool, args) pair within one trajectory."""
    seen: set[str] = set()
    repeats = 0
    for step in trajectory:
        key = json.dumps([step["tool"], step["args"]], sort_keys=True)
        repeats += key in seen
        seen.add(key)
    return repeats


def test_redundant_call_metric() -> None:
    trajectory = [{"tool": "orders_get", "args": {"order_id": "a"}}, {"tool": "orders_get", "args": {"order_id": "a"}}]
    assert redundant_calls(trajectory) == 1      # budget: <= 1 per trajectory (ADAPT)
```

- A side-effect test asserts **state** (no row written, no message sent), not only `is_error`: a rejected-but-executed call is the failure that matters. Read the canonical store or a test double of the downstream system.
- Tests that need the server's internals (audit store, side-effect counter, fault switches) run in the server's own language through a real client. Reference implementation: [`mcp-builder/scripts/contract-test/`](../../mcp-builder/scripts/contract-test/) (`server.ts` + `contract.test.ts`, exact pins and lockfile; `npm ci && npm run typecheck && npm test`). 18 tests: schema, auth, isolation, idempotency, stale intent, audit fields, metrics, cancellation in both protocol eras, failure injection; 10 planted defects each failed the suite.
- `mcp-builder/scripts/evaluation.py` (LLM-driven task eval, live model) reports `redundant_tool_calls` per task and the number of tasks over the budget, using the same repeat rule.

## Tool-surface lock

Hash each tool's `name + description + input schema`, commit the hashes, and fail CI when they differ. An intentional change regenerates the file and is justified in the PR: an auditable record of every tool-surface change. The lock covers **added and removed** tools as well as changed ones (a surprise tool is a surface change).

The tested implementation is the `mcp-tool-validator` client (`mcp-tool-validator/scripts/mcp_test_client.py`):

```bash
# write (intentional change only; review the diff and justify it in the PR)
uv run python tests/mcp_test_client.py --server-url "$SERVER_URL" --surface-lock tests/tool-surface.lock.json --update-surface-lock
# check (CI, R1): exit 4 SURFACE_DRIFT before any tool is called; report lists added/removed/changed
uv run python tests/mcp_test_client.py --server-url "$SERVER_URL" --surface-lock tests/tool-surface.lock.json
```

Verified 2026-11-23: lock written (exit 0), unchanged server (exit 0, GREEN, 12 scenarios), server with one silently edited description (exit 4, `{"changed": ["refunds_create"]}`). The GREEN report carries `tool_surface_hash`; record it with every eval result next to prompt, model and dataset versions.

## Audit log for write tools

Every write tool emits one audit record per decision (allowed **and** denied), written **before** the effect; a failed audit write blocks the effect. Required fields:

`tool_name, caller_role, caller_id_hash, scope_id_hash, request_id, session_id, input_schema_valid, authorization_result, side_effect_type, prompt_version, model_name, audit_log_id, latency_ms, error_code`

Recommended for reads that return PII, financial data or documents. Tests: every field present; identifiers hashed, not raw; a denied call (payload mismatch, scope, stale intent) also has a record; audit store down → no side effect. Field sources and the session/version caveats: `mcp-builder/reference/security-pii-compliance.md` §3.

## Tool metrics

| Metric | Labels | Alert |
|---|---|---|
| `tool_calls_total` | `tool, role, result` | error-rate SLO per tool |
| `tool_duration_seconds` | `tool` | P95/P99 vs budget |
| `tool_auth_denials_total` | `tool, reason` | spike |
| `isolation_violations_total` | — | **always 0; page on any** |
| `audit_writes_total` | `tool` | must track write-tool calls 1:1 |
| `input_validation_failures_total` | `tool, field` | spike (probing or prompt drift) |
| `rate_limit_blocks_total` | `tool` | spike |

Validation failures that the SDK rejects before your handler runs (TypeScript SDK v2 `inputSchema`) are not visible to handler code: count them from the result (`isError` with the SDK's input-validation text) in middleware or from traces. Map onto OpenTelemetry MCP metrics where you already export them (`mcp-builder/reference/observability-metrics.md`). `isolation_violations_total` comes from canaries and post-hoc checks, never from the code path that would have to detect its own bypass.

## Promptfoo against an MCP server

The `mcp` provider calls tools directly (no model), so it suits deterministic L2/L3 cases and the red-team `mcp`, `bola`, `bfla` plugins. Config shape from the promptfoo provider docs (`site/docs/providers/mcp.md`). Verified 2026-11-23 with promptfoo 0.126.0 against an SDK v2 2.4.0 server: `promptfoo eval` exit 0 (2 passed: this case plus an own-scope read); with the server's tenant filter removed, the cross-scope case failed (exit 100). The install is ~680 MB, so run it in CI or a disposable directory, not as a project dependency.

```yaml
# tests/eval/promptfoo/mcp-contract.yaml
providers:
  - id: mcp
    config:
      enabled: true
      server:
        url: http://127.0.0.1:8080/mcp
        auth:
          type: bearer
          token: '{{env.MCP_TOKEN_SCOPE_B}}'   # scope B principal
prompts:
  - '{{prompt}}'
tests:
  - description: scope B cannot read a scope A order (hard blocker)
    vars:
      prompt: '{"tool": "orders_get", "args": {"schema_version": "1.0", "order_id": "ord_001"}}'
    assert:
      - type: contains
        value: NOT_FOUND
```

Prompts are JSON tool calls `{"tool": ..., "args": ...}`. To assert on the tools a **model** chose, run a chat provider with `mcp.enabled: true` and assert on `metadata.toolCalls` (`{ id, name, input, output, is_error }` per call). Red-team plugins and strategies: [red-teaming.md](red-teaming.md).

## MCP Inspector CLI (scripted check)

Pinned `@modelcontextprotocol/inspector@2.16.0`, verified 2026-11-23 against a Streamable HTTP server:

```bash
npx -y @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8080/mcp --method tools/list \
  --header "Authorization: Bearer $MCP_TOKEN"
npx -y @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8080/mcp --method tools/call \
  --tool-name orders_get --tool-arg 'schema_version="1.0"' order_id=ord_001 --header "Authorization: Bearer $MCP_TOKEN"
```

- Exit 0 on success, **5** when the tool result has `isError: true` (cross-scope call), **3** `auth_required` when the token is missing or rejected (it then tries interactive OAuth; non-interactive runs fail instead of prompting).
- `--tool-arg` parses values as JSON: `schema_version=1.0` arrives as the number `1` and fails a string schema. Quote string values (`'key="1.0"'`).

## Known gotchas

| Gotcha | Fix |
|---|---|
| MCP auth layer checks the token but not the caller's scope against the tool's input ids | Do not run MCP evals in staging until scope filtering from the verified token is merged |
| `@modelcontextprotocol/client` 2.4.0 defaults to the 2025 (legacy) era; on a stateless `createMcpHandler`, a legacy client's abort never reaches the handler (it ran 10/10 batches) | Test cancellation with `versionNegotiation: { mode: { pin: '2026-07-28' } }` (handler stopped early) and test both eras if you serve both |
| Restarting a test server on the same port between suites | Kept-alive sockets reset (`ECONNRESET`); use one port per server instance |
| Tool-surface lock hash mismatch after an intended schema change | Regenerate with `--update-surface-lock`, review the diff, justify it in the PR |
| A rejected call that still executed | Assert canonical state, not only `is_error` |
