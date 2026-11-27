---
description: Scaffold a new Agentic AI service with Python 3.14, LangChain v1.5.2, LangGraph v1.2.24, FastAPI 0.165.0, and production infrastructure
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Agentic AI Service

**Project name:** $ARGUMENTS (default to "my-agent-service" if not provided)

Delegate to the `agentic-ai-dev` skill for all patterns, templates, and reference files.

## Steps

1. Read the `agentic-ai-dev` skill, then `reference/agentic-architecture-choice.md`, and pick `create_agent` / `StateGraph` / Functional API / deterministic / ADK before copying templates. Do not add `deepagents` unless the service explicitly needs that harness.
2. Initialize project — `uv init $ARGUMENTS --python 3.14`
3. Add production + dev dependencies with the exact pins in `agentic-config-project.md` (`langgraph` and `langgraph-prebuilt` together); commit `uv.lock`
4. Create directory structure under `src/<service_name>/` per skill conventions
5. Create core modules (config with required `CHAT_MODEL` and `SecretStr` keys, logging with `log_exception`), model client (`init_chat_model`), agent layer (state, typed scoped tools, graph with `recursion_limit` + call limits), API layer (lifespan with `async with` checkpointer/store, principal dependency, server-scoped thread keys, deadline, typed statuses, JSON SSE), and tests using skill reference templates
6. Add infrastructure (Dockerfile using `uv sync --locked`, docker-compose.dev.yml with PostgreSQL, `.env.example` without real values)
7. Evals and guardrails: record the risk tier (T0–T3, guardrails §3; unsure → the higher tier) and eval plan in the ADR from `/ai-decision-record`; add `tests/golden/features/<feature>/` with a `dataset_manifest.yaml` (`eval-guide/reference/golden-dataset.md` "Layout" and "Manifest, versioning and run metadata", schema and starter files in the `eval-guide` skill, no real PII); add `@pytest.mark.r1` tests on the scripted fake model for tool allowlist resolution, server-side scope injection, schema-invalid output → no tool call, budget exhaustion → typed fallback, and idempotency-key reuse with a changed payload rejected for every write tool (guardrails §9)
8. Verify and report each with its exit code (PASS / FAIL / NOT RUN):
   - `python3 .claude/scripts/check-ai-assets.py --root $ARGUMENTS` (from the workspace root that holds `.claude/`) (exit 0 required; 3 = BLOCKED)
   - `uv run pytest -m r1 -q` (executed count > 0)
   - `uv sync --locked`
   - `uv run ruff check src tests`
   - `uv run mypy src`
   - `uv run pytest -q -m "not live"` (needs the dev PostgreSQL; if it is not running, report NOT RUN, not PASS)
