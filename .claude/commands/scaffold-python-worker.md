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
- **Failure classes**: malformed/poison input -> log, publish to the dead-letter topic, then ack (push handlers: 4xx); transient failure -> nack (push: 5xx); attempts exhausted -> publish a "failed" event, then ack
- **Subscription**: `DeadLetterPolicy` (`max_delivery_attempts` 5–100) and `RetryPolicy` on every subscription; small in-process retry budget (it multiplies with delivery attempts); exactly-once delivery does not replace the dedupe key
- **Streaming pull** (google-cloud-pubsub 2.44.0, executed: `reliability-idempotency-retries-outbox.md` section 7a): standalone worker awaits the `subscribe()` future and exits non-zero when the stream dies (inside a FastAPI service: `SubscriptionSupervisor` from lifespan); `FlowControl(max_messages=..., max_lease_duration=2x handler timeout)`; `await_callbacks_on_shutdown=True`; bridge to the loop with `run_coroutine_threadsafe(...).result(timeout=...)` and cancel the future on timeout
- **Tasks**: use `spawn()` (retained, failure logged), never a bare `asyncio.create_task(...)`; `drain_background()` in lifespan shutdown (`.claude/skills/python-dev/reference/asyncio-concurrency-and-tasks.md`)
- **Sessions**: one session per task; compute and call external services first, then open the session, write, commit (`sqlalchemy-async-sessions-and-transactions.md`)
- **Shutdown**: standalone worker: `loop.add_signal_handler(SIGTERM, stop.set)` -> readiness false -> `future.cancel()` -> `result(timeout=drain)` -> cancel in-flight handlers (callbacks nack) -> `subscriber.close()` -> flush telemetry (`deployment-ci-cd/reference/python-observability.md` §3.1; trace propagation §3.3), all inside the platform's kill window (Cloud Run: SIGKILL 10 s after SIGTERM). Worker hosted in a FastAPI app: `lifespan` only (uvicorn owns SIGTERM; `on_event` is ignored when `lifespan=` is set). Dispose the engine and close clients last
- **Runtime boundary**: a processor whose wheels lack the service's Python (e.g. paddlepaddle 3.3.1: cp39–cp313 only, so OCR runs on Python 3.13) is its own uv project with its own `.python-version` and `uv.lock`, outside the 3.14 workspace; the message contract is a versioned JSON Schema checked in BOTH runtimes' tests. Pin it as `.python-version` 3.13.18, `requires-python = ">=3.13,<3.14"` (a 3.13-only member makes a 3.14 workspace fail to resolve); image per `deployment-ci-cd/reference/python-ci-supply-chain.md` §8 on `python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90` (digest from `docker buildx imagetools inspect`, 2026-11-23; image not built here)
- **Retries**: transient errors only, jitter, attempts AND total window, never 4xx, POST only with an idempotency key
- **Outbox/claim sweeps**: attempts counter, backoff, `ORDER BY`, batch cap, exhausted state, lease for `SKIP LOCKED` claims

## Critical Constraints
- Never bypass the shared database session factory — use the shared library's `get_session` / `AsyncSession` pattern
- Never use inline AI framework patterns (LangChain, LangGraph, etc.) in a worker service
- All failures must be logged via structlog and surfaced as records — never swallowed silently
- External API clients must be injected (not instantiated inline) to enable test mocking
- Required env vars must have NO defaults in config — missing values must raise `ValidationError` at startup

## Post-Scaffold
- Add the new service to `pyproject.toml` workspace members at repo root (not a different-runtime worker: it keeps its own lock)
- Verify with each command's OWN exit code: `uv sync` at repo root, then in the service `uv run ruff check .`, `uv run mypy .` and `uv run pytest -q` (zero executed tests is FAIL) — report PASS / FAIL / BLOCKED per check
- Add deployment configuration for Cloud Run or equivalent compute target
- Dispatch `python-worker-reviewer` after implementation is complete
