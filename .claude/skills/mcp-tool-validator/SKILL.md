---
name: mcp-tool-validator
description: "Validate every tool of an MCP server end-to-end after a change (tools/list, tools/call, rebuild, health check, fix-and-retest loop) before a PR. Use when building, modifying or deploying an MCP server. Not for non-MCP APIs or unit tests; MCP server design lives in mcp-builder."
metadata:
  triggers: MCP server, MCP tools, tool validation, tools/list, tools/call, validate MCP tools, MCP redeploy and re-test
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# MCP Tool Validator

This skill specifies a test harness for validating MCP server tools after code changes, with a tested implementation in [scripts/](scripts/) (`mcp_test_client.py`, `run_validation.sh`, a self-test and an example `scenarios.yaml`) that you copy into the project; [references/client_skeleton.md](references/client_skeleton.md) explains how it works. It enforces a strict feedback loop: deploy → validate every tool → fix failures → redeploy → re-validate, capped at 5 iterations, before a PR is raised.

Works for both **single-repo** and **monorepo** layouts. Override the defaults table below to match your project structure.

## Iron Law

Never report an MCP server as working because it started: list the tools (`tools/list`), call every one (`tools/call`) and show each result. A tool that was not called is NOT RUN, never PASS.

## Configuration defaults (override per project)

| Setting | Default value | How to override |
|---------|---------------|-----------------|
| Server URL | `http://localhost:8080/mcp` | Set `SERVER_URL` env var (bearer token: `MCP_TOKEN`) |
| Health URL | `http://localhost:8080/health` | Set `HEALTH_URL` env var |
| Transport | Streamable HTTP | `SERVER_URL=stdio://<command> <args>` for stdio. HTTP+SSE is deprecated and unsupported |
| Compose file | `docker-compose.yml` | Set `COMPOSE_FILE` env var |
| Compose service | `mcp-server` | Set `COMPOSE_SERVICE` env var |
| Container name | `<project>-mcp` | Set in docker-compose.yml `container_name:` |
| Scenarios file | `tests/scenarios.yaml` | Set `SCENARIOS_FILE` env var |
| Test client | `tests/mcp_test_client.py` | Set `TEST_CLIENT` env var |
| Orchestrator | `tests/run_validation.sh` | Modify path in CLAUDE.md block |

**Monorepo note:** If your MCP server lives in a subdirectory (e.g. `mcp/<server-name>/`), prefix all paths above with that subdirectory. Example: `SCENARIOS_FILE=mcp/my-server/tests/scenarios.yaml`.

## When to use this skill

Use this skill when ANY of the following are true:
- Code changes were made to your MCP server `src/` and the server has been rebuilt/redeployed
- Health check passes but tool-level behavior is not yet verified
- The user wants autonomous fix-and-retry behavior before raising a PR touching MCP code

Do NOT use this skill for:
- Pure unit testing of internal handler logic (use `npm test` or `pytest` in your MCP server directory)
- Non-MCP HTTP APIs (use standard contract testing)
- Load/performance testing (out of scope)

## Core principle

**A green health check does not mean the tools work.** This skill closes that gap by spawning a real MCP client, calling every tool with declared scenarios, and asserting on protocol shape AND semantic content.

## Quick start (the 5-step procedure)

1. **Copy the harness** — copy `scripts/mcp_test_client.py`, `scripts/run_validation.sh`, `scripts/test_mcp_test_client_self.py` and `scripts/scenarios.yaml` into the project's `tests/`; `uv add --dev mcp==2.3.0 pyyaml==6.0.4`.
2. **Author scenarios** — For each tool, you need: 1 happy path, 1 invalid input, 1 edge case. See `references/scenario_schema.md` to author or extend scenarios.
3. **Check coverage** — `uv run python tests/mcp_test_client.py --server-url $SERVER_URL` lists every tool first and exits 2 (COVERAGE_GAP) before calling anything if a tool lacks scenarios.
4. **Wire the loop** — `bash tests/run_validation.sh` handles build → deploy → wait → validate → report (exit codes in `references/client_skeleton.md`).
5. **Enforce the contract** — Copy the feedback-loop block from `references/feedback_loop.md` into your project's `CLAUDE.md`.

## Lazy-loaded references

Read these only when needed for the current task:

- **`scripts/`** — the tested client, orchestrator, self-test and example scenarios to copy
- **`references/client_skeleton.md`** — how the client and orchestrator work, exit codes, transports (stdio, Streamable HTTP), extending the assertion engine
- **`references/scenario_schema.md`** — Read when authoring scenarios or extending the assertion DSL
- **`references/assertion_library.md`** — Read when a scenario needs an assertion type not in the starter set
- **`references/feedback_loop.md`** — Read when configuring the autonomous fix-redeploy-retest loop in CLAUDE.md
- **`references/docker_orchestration.md`** — Read when health-check waits, port conflicts, or compose-file orchestration cause issues

## Coverage rules (non-negotiable)

Every tool registered via `tools/list` MUST have:
- At least 1 happy-path scenario (name contains `happy_path`)
- At least 1 input-validation/error scenario (name contains `invalid_input`)
- At least 1 edge case (any other name)

The client enforces this before calling any tool: it exits 2 (COVERAGE_GAP) if a listed tool is missing scenarios or a scenario names a tool the server does not list.

## Failure-mode guards

These guards prevent the most common ways autonomous loops produce false-green results:

1. **No silent xfail** — Marking a scenario as expected-fail requires a `# REASON: <one line>` comment AND user approval in the conversation.
2. **No scenario softening** — Edits to `scenarios.yaml` require commit message tag `[scenario-update]` and a one-line justification.
3. **Loop cap** — Default 5 fix-redeploy iterations. After cap, STOP and report with file:line evidence. Do NOT raise PR.
4. **Determinism check** — Each scenario runs twice on first failure. If results differ, the scenario is flaky → fix the scenario or the tool, not the loop.
5. **Coverage gate** — PR creation is blocked unless the validation run exits 0.

## Output contract

After running validation, produce a report with:
- Total tools discovered, total scenarios run, pass/fail counts
- For each failure: tool name, scenario name, expected vs actual, suspected root cause file:line
- Iteration count if loop was used
- Final verdict: GREEN (raise PR) | RED (stop, report) | FLAKY (investigate)
