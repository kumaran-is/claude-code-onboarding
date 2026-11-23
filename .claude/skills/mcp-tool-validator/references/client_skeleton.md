# MCP Test Client — Reference Implementation

Copy the files from `scripts/` into your project's `tests/` (`mcp_test_client.py`, `run_validation.sh`, `test_mcp_test_client_self.py`, `scenarios.yaml`). They are shipped as tested files in [`../scripts/`](../scripts/); this page documents how they work.

> Verified 2026-11-23 with `mcp==2.3.0` and `pyyaml==6.0.4` on CPython 3.14: GREEN (exit 0) against a stdio server; a changed expectation gave RED (exit 1) with `json_path: total_cents expected 1501, got 1500`; a tool with two cases gave COVERAGE_GAP (exit 2); an unreachable URL gave CONNECTION (exit 3); over Streamable HTTP it listed the server's tools and reported each one missing a scenario (exit 2). The orchestrator passed `bash -n` and the stdio and build-failure (exit 10) paths; its Docker path was not run.

## Dependencies

```bash
uv add --dev mcp==2.3.0 pyyaml==6.0.4
```

## How it connects

- `mcp.Client` (SDK v2) negotiates the protocol era itself: `server/discover` for 2026-07-28 servers, falling back to `initialize` for 2025-era servers. The report records `protocol_version`.
- `--server-url http(s)://…/mcp` → Streamable HTTP. A bearer token is read from `MCP_TOKEN` and set on the `httpx2.AsyncClient` (v2 moved headers, timeouts and auth from the transport to the HTTP client).
- `--server-url "stdio://<command> <args>"` → the client spawns the server as a subprocess.
- The deprecated HTTP+SSE transport is not supported. Migrate the server to Streamable HTTP.
- One `Client` serves the whole run. There are no protocol sessions in 2026-07-28, so nothing needs cleaning up between scenarios.
- Transport failures arrive wrapped in an `ExceptionGroup` (the SDK runs transports in a task group), so the client uses `except*`. A plain `except httpx2.HTTPError` misses them and the run crashes with exit 1 (RED) instead of 3 (CONNECTION). This was observed, then fixed.

## Exit codes

| Code | Verdict | Meaning |
|---|---|---|
| 0 | GREEN | every scenario passed |
| 1 | RED | at least one assertion failed (details in `tests/validation_report.json`) |
| 2 | COVERAGE_GAP | a listed tool lacks a `happy_path` case, an `invalid_input` case or a third case, or a scenario names a tool the server does not list |
| 3 | CONNECTION | transport or protocol failure |
| 10 / 11 / 12 | infra (orchestrator) | Docker build / start / health-check timeout |

## `tests/mcp_test_client.py`

Shipped as [`scripts/mcp_test_client.py`](../scripts/mcp_test_client.py) (verified 2026-11-23: mcp 2.3.0, Python 3.14). Copy it to `tests/mcp_test_client.py` in your project.

## `tests/run_validation.sh`

Shipped as [`scripts/run_validation.sh`](../scripts/run_validation.sh) (verified 2026-11-23: mcp 2.3.0, Python 3.14). Copy it to `tests/run_validation.sh` in your project.

## Example `tests/scenarios.yaml`

Shipped as [`scripts/scenarios.yaml`](../scripts/scenarios.yaml).

## Extending

- **New assertion:** add `_assert_<name>(self, expected, result, duration_ms) -> str | None` to `AssertionEngine`. Return `None` to pass or a message to fail. Document it in [scenario_schema.md](scenario_schema.md) and [assertion_library.md](assertion_library.md). An unknown assertion key fails the scenario, so a typo cannot pass silently.
- **Hanging tools:** wrap `client.call_tool(...)` in `anyio.fail_after(seconds)` and record the timeout as a failure.
- **Results are v2 objects:** use snake_case attributes (`is_error`, `structured_content`, `content[i].type` / `.text`), not v1 `isError`.

## Testing the client itself

Shipped as [`scripts/test_mcp_test_client_self.py`](../scripts/test_mcp_test_client_self.py): three unit tests of `AssertionEngine` (pass, missing content, unknown assertion). Run `uv run pytest -q tests/test_mcp_test_client_self.py` after copying.
