---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/uv.lock"
  - "**/alembic/**"
---

# Python backend guardrails

Path-scoped: loads only when Python, packaging or migration files are in play (not on a bare Dockerfile: Java, Node and Flutter repos have those too). These are the always-apply guardrails; each links to the reference holding the reasoning and snippets (`.claude/skills/python-dev/reference/` unless a path is given). Items about a technology apply only **if the project uses** it.

- **Sessions open and close in the dependency; transactions are owned by the service / unit of work.** A `yield` dependency's exit code runs after the response is sent by default, so a failed commit there returns 200 for unsaved data; `Depends(..., scope="function")` (FastAPI 0.121+) runs it before the response. → `sqlalchemy-async-sessions-and-transactions.md`
- **One `AsyncSession` per task; never share the request session with a background task.** Eager-load what the response reads; implicit lazy loads raise `MissingGreenlet` in async code. A server-side `onupdate` column is expired after the UPDATE commit even with `expire_on_commit=False`: `await session.refresh(obj, ["updated_at"])`. A server-generated PK is `None` until flush. → `sqlalchemy-async-sessions-and-transactions.md`
- **Keep a strong reference to every `asyncio.create_task`** (module-level set + `add_done_callback(discard)` + a callback that logs the exception), or use `BackgroundTasks` / `TaskGroup`. Load-bearing events go through an outbox, not a fire-and-forget task. Ruff `RUF006` enforces it. → `asyncio-concurrency-and-tasks.md`, `reliability-idempotency-retries-outbox.md`
- **No blocking calls in `async def`** (`time.sleep`, sync HTTP/DB drivers, file reads on hot paths): use the async API or `asyncio.to_thread`. Ruff `ASYNC` enforces the common cases. → `asyncio-concurrency-and-tasks.md`
- **Never log `str(exc)`, `repr(exc)`, f-string exceptions or `exc_info` for request-derived errors** without a PII policy: a Pydantic `ValidationError` string embeds `input_value`. Log the exception type, a stable event name and non-sensitive ids; use `errors(include_input=False)` if details are needed. → `fastapi-error-handling.md`, `silent-failure-hunter` agent
- **Actor identity comes from the verified token, never from the request body.** A role check alone does not authorize access to a specific object. → `fastapi-authorization-boundaries.md`
- **Raw SQL:** bind parameters, never string-built; write `CAST(:p AS type)`, not `:p::type`, inside `text()` (asyncpg rejects the latter). Run migrations round-trip (upgrade, downgrade, upgrade) and confirm new models are imported where `target_metadata` is built. → `alembic-migration-safety.md`
- **Required config fails at startup;** no `os.getenv("X", "literal")` fallbacks for secrets, URLs or environment-varying values; required fields are bare `str` / `Field(min_length=N)`, not `str | None = None`. → `fastapi-architecture-and-config.md`
- **Never `from module import <lazily-initialised global>`** (engine, client, sessionmaker): the name freezes at import, usually as `None`. Import the accessor; tests patch the accessor.
- **Tests:** an outer-transaction fixture (`join_transaction_mode="create_savepoint"`) cannot prove commit-boundary or two-session race behaviour (both share one connection); use real connections and a remove-the-guard control. Import exception classes used in `pytest.raises` at module level, and confirm a string-target `mock.patch` landed with a positive case. → `.claude/skills/python-testing-patterns/reference/postgres-integration-testing.md`, `.claude/skills/python-testing-patterns/reference/mock-patterns.md`
- **Dependencies:** pin the web framework and its instrumentation library exactly (`==`); a dependency change is not done until `uv lock` is re-run in the same change; CI and images use `uv sync --locked` / `uv export --locked` (fails on a stale lock), never hand-listed `pip install`. Gate on `pip-audit`'s own exit code (it prints no severity; `pip audit` is not a command). → `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`
- **Lint rule set:** ruff `select` includes `B`, `ASYNC`, `RUF006`, `BLE001`, `S110`, `T201` and `DTZ`; justify each `# noqa` with a reason. Do not use `SIM105` (it turns a flagged silent `except: pass` into a silent `suppress`). Use `datetime.now(UTC)`, not naive `datetime.now()`.
- **Never add `ruff check --fix` to an edit hook or agent loop,** and put a new import and its first use in one edit: a fix pass deletes an import (F401) added before its use lands, and `UP037` has stripped quotes inside `Literal[...]`.
- **Do not add `from __future__ import annotations` on 3.14-only code** (annotations are lazy by default; the import is deprecated and can hinder runtime resolution that Pydantic/FastAPI rely on). Use `X | None` and built-in generics.
- **Verification output is the tool's own exit code,** not a pipe's: `uv run pytest -q > log; echo "EXIT:$?"; tail -5 log`. Pytest exit 5 (no tests collected) is a FAIL. See `verification-and-reporting.md`, `hook-and-gate-authoring.md`.
