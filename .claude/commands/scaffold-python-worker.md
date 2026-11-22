---
description: Scaffold a standalone Python 3.14 background worker service. Use for event-driven or scheduled processing jobs that are NOT FastAPI REST APIs and NOT AI agents.
argument-hint: "[service name]"
allowed-tools: Bash, Read, Write, Edit
---

# Scaffold: Python Background Worker

**Project name:** $ARGUMENTS

Use for services triggered by Pub/Sub, Cloud Scheduler, or GCS events — not for HTTP REST APIs or AI agents.

## Stack
- Python 3.14 + uv workspaces
- Shared service library editable install via `[tool.uv.sources]`
- structlog for logging
- pytest for tests

## Steps

1. **Read existing files** in the target directory before adding anything
2. **Initialize with uv:** `uv init $ARGUMENTS --python 3.14` under the appropriate `services/` subdirectory
3. **Add `[tool.uv.sources]`** with the shared service library as an editable install in `pyproject.toml`
4. **Create directory structure:**
   - `src/config.py` — pydantic-settings config, env vars (required fields have NO defaults)
   - `src/job.py` — `async def run_job(payload: dict) -> JobResult:` entry point
   - `src/processors/` — domain-specific processing modules
   - `src/main.py` — Pub/Sub or Cloud Scheduler handler (parses trigger payload, calls run_job)
   - `tests/test_job.py` — unit tests with mocked external clients
5. **Output:** write results to the database via the shared session factory — never connect directly
6. **Status reporting:** write job status to the canonical status store on completion/failure

## Reliability Contract (apply while scaffolding; reasoning: `.claude/skills/python-dev/reference/reliability-idempotency-retries-outbox.md`)

- **Idempotent handler**: `run_job()` called twice with the same payload yields the same result (idempotency key row + effect in ONE transaction, unique constraint arbitrates; on `IntegrityError` roll back and return the winner)
- **Failure classes**: malformed/poison input -> log, dead-letter/ack (push handlers: 4xx); transient failure -> nack (push: 5xx); attempts exhausted -> publish a "failed" event, then ack
- **Streaming pull**: subscribe through `SubscriptionSupervisor` started from lifespan; never discard the `subscribe()` future; set `FlowControl`; bridge to the loop with `run_coroutine_threadsafe(...).result(timeout=...)` and cancel the future on timeout
- **Tasks**: use `spawn()` (retained, failure logged), never a bare `asyncio.create_task(...)`; `drain_background()` in lifespan shutdown (`.claude/skills/python-dev/reference/asyncio-concurrency-and-tasks.md`)
- **Sessions**: one session per task; compute and call external services first, then open the session, write, commit (`sqlalchemy-async-sessions-and-transactions.md`)
- **Shutdown**: `lifespan` only (`on_event` is ignored when `lifespan=` is set); no custom SIGTERM handler; dispose the engine and close clients last
- **Retries**: transient errors only, jitter, attempts AND total window, never 4xx, POST only with an idempotency key
- **Outbox/claim sweeps**: attempts counter, backoff, `ORDER BY`, batch cap, exhausted state, lease for `SKIP LOCKED` claims

## Critical Constraints
- Never bypass the shared database session factory — use the shared library's `get_session` / `AsyncSession` pattern
- Never use inline AI framework patterns (LangChain, LangGraph, etc.) in a worker service
- All failures must be logged via structlog and surfaced as records — never swallowed silently
- External API clients must be injected (not instantiated inline) to enable test mocking
- Required env vars must have NO defaults in config — missing values must raise `ValidationError` at startup

## Post-Scaffold
- Add the new service to `pyproject.toml` workspace members at repo root
- Verify `uv sync` at repo root resolves without error
- Add deployment configuration for Cloud Run or equivalent compute target
- Dispatch `python-worker-reviewer` after implementation is complete
