---
description: Scaffold a new Agentic AI service with Python 3.14, LangChain v1.2.8, LangGraph v1.0.7, FastAPI 0.135.2, and production infrastructure
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Agentic AI Service

**Project name:** $ARGUMENTS (default to "my-agent-service" if not provided)

Delegate to the `agentic-ai-dev` skill for all patterns, templates, and reference files.

## Steps

1. Read the `agentic-ai-dev` skill and its reference files for exact code templates
2. Initialize project — `uv init $ARGUMENTS --python 3.14`
3. Add production + dev dependencies with the exact pins in `agentic-config-project.md` (`langgraph` and `langgraph-prebuilt` together); commit `uv.lock`
4. Create directory structure under `src/<service_name>/` per skill conventions
5. Create core modules (config with required `CHAT_MODEL` and `SecretStr` keys, logging with `log_exception`), model client (`init_chat_model`), agent layer (state, typed scoped tools, graph with `recursion_limit` + call limits), API layer (lifespan with `async with` checkpointer/store, principal dependency, server-scoped thread keys, deadline, typed statuses, JSON SSE), and tests using skill reference templates
6. Add infrastructure (Dockerfile using `uv sync --locked`, docker-compose.dev.yml with PostgreSQL, `.env.example` without real values)
7. Verify and report each with its exit code (PASS / FAIL / NOT RUN):
   - `uv sync --locked`
   - `uv run ruff check src tests`
   - `uv run mypy src`
   - `uv run pytest -q -m "not live"` (needs the dev PostgreSQL; if it is not running, report NOT RUN, not PASS)
