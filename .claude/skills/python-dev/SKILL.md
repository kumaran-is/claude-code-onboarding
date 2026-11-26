---
name: python-dev
description: This skill provides patterns and templates for Python 3.14 development with FastAPI and modern tooling. It should be activated when creating Python APIs, scripts, data processing pipelines, or pytest tests; also when adding a notification producer (push, email, SMS, in-app) or outbox staging for a user-facing send.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Python, FastAPI, Pydantic, Python API, async Python, Python backend, uv, ruff, Python 3.14, notification, outbox, push notification, transactional email
  related-skills: openapi-spec-generation, database-schema-designer, agentic-ai-dev
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO FASTAPI ENDPOINT WITHOUT A PYDANTIC v2 INPUT MODEL — never trust raw request data; validate at the boundary, always**

# Python 3.14 Development Skill

## Code Conventions
- **Python 3.14** with type hints everywhere; `mypy --strict`
- **FastAPI 0.165** (Starlette 1.10) for REST APIs, **Pydantic 2.14** + pydantic-settings 2.16 for validation and config
- Async by default: `async def` endpoints, SQLAlchemy 2.1 async + `asyncpg` for PostgreSQL
- `uv` for packages and the lockfile, `ruff` for lint and format
- Folder structure: `api/routes/ → services/ → repositories/ → models/`
- Tests: pytest + pytest-asyncio + **httpx2** (`ASGITransport`, `TestClient`); `filterwarnings = ["error"]`
- Outbound HTTP from service code: **httpx 0.28.1** (tracing and mocking libraries target it); httpx2 for outbound calls is deferred until they support it

Versions verified together (uv 0.13.9, CPython 3.14.10): fastapi 0.165.0, starlette 1.10.0, uvicorn 0.54.0,
pydantic 2.14.4, pydantic-settings 2.16.3, sqlalchemy 2.1.9, structlog 26.1.0, pyjwt 2.15.1, httpx2 2.16.2,
pytest 9.2.0, pytest-asyncio 1.5.0, ruff 0.17.6, mypy 2.4.1. Full pin list: `reference/fastapi-templates.md`.

**FastAPI changes that bite (0.136 → 0.165):**
- `app.routes` is a tree since 0.137: walk `fastapi.routing.iter_route_contexts(app.routes)`, never
  `isinstance(r, APIRoute)` over `app.routes` (it silently sees nothing under an included router).
- `FastAPI(max_body_size=...)` (0.164) returns 413 before routing; `Depends(dep, max_concurrency=N)` (0.163).
- Native SSE: `fastapi.sse.EventSourceResponse` / `ServerSentEvent` (0.135).
- Removed or deprecated: `**extra` on params (`TypeError`, 0.155: use `json_schema_extra`), `regex=`
  (use `pattern=`), `FastAPI(root_path=...)` (use the server's `--root-path`), `on_event` / `on_startup`
  (ignored when `lifespan=` is set; removed from Starlette 1.0).
- JSON `null` is no longer the same as an omitted Body field (0.151), and omitted Query/Header/Cookie/Form
  defaults are not validated unless `validate_default=True` (0.148).
- Starlette's `TestClient` warns when only `httpx` is installed; install `httpx2`.
- Native OpenTelemetry (0.142+): `FastAPI(telemetry={...})` replaces `opentelemetry-instrumentation-fastapi`; settings (`"logs": False`, probe exclusion) in `deployment-ci-cd/reference/python-observability.md` §3.2.

## Quick Scaffold — New Python Project

```bash
uv init --package my-service && cd my-service
echo "3.14.10" > .python-version          # keep requires-python = ">=3.14" in pyproject.toml
uv add "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "pydantic==2.14.4" "pydantic-settings==2.16.3" \
  "sqlalchemy[asyncio]==2.1.9" "asyncpg==0.32.0" "structlog==26.1.0"
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "pytest-cov==7.1.0" "httpx2==2.16.2" \
  "ruff==0.17.6" "mypy==2.4.1"
uv sync --locked                           # CI and Docker install from the committed uv.lock
```

Pin exact versions (never bare `uv add fastapi`). pip is not used for services: `uv.lock` is the
reproducible install.

## Reference Files

**Code templates and project config**: Read `reference/fastapi-templates.md` for FastAPI app structure, Pydantic models, route handlers, SQLAlchemy models, pytest fixtures, pyproject.toml template, Docker configuration, and common commands.

**Advanced patterns and profiling**: Read `reference/python-advanced-patterns.md` for performance profiling (cProfile, py-spy, memory_profiler), pytest-benchmark, property-based testing with Hypothesis, structural pattern matching, descriptors, and memory optimization techniques.

**Auth, security and authorization**: Read `reference/fastapi-auth-security.md` for JWT with PyJWT (explicit algorithms, required `exp`/`sub`/`iat`), Argon2id password hashing with `pwdlib` (run off the event loop), `OAuth2PasswordBearer` dependencies, RBAC/permission maps and rate-limit keys. `python-jose` and `passlib` are not used in new code.

**Error handling, retry, and circuit breakers**: Read `reference/fastapi-error-handling.md` for custom exception hierarchy (`AppError` → `NotFoundError`/`ValidationError`/`ExternalServiceError`), FastAPI exception handlers, async retry with `tenacity`, async circuit breaker with `circuitbreaker`, error logging context middleware, and pytest patterns for error paths.

**Backend service consistency patterns**: Read `reference/backend-service-patterns.md` for the mandatory per-service patterns: timing-safe internal secret guard (P1), fail-fast config (P2), structured logging (P3), session and transaction ownership (P4), `lifespan`-only Redis/client lifecycle (P7) and the checklist at the end.

**Live E2E integration testing**: Read `reference/backend-live-e2e-standard.md` for why unit tests (ASGITransport + mocks) miss real integration bugs, the per-service test pattern (health, auth gate, fake JWT rejection, internal secret gate, input validation), auth ordering rules (FastAPI validates auth before Pydantic), HTTP method verification from OpenAPI spec, and the feedback loop for fixing live failures.

**Pub/Sub and Firestore messaging patterns**: Read `reference/pubsub-firestore-patterns.md` for the three canonical messaging patterns: Pattern A (fire-and-forget `asyncio.create_task` for informational events), Pattern B (transactional outbox with `SELECT FOR UPDATE SKIP LOCKED` for load-bearing events), Pattern C (Firestore status bus for real-time mobile UI). Includes decision tree, full implementation templates, subscriber patterns, and hard rules for each.

**Notification producers and channel retry**: Read `reference/notification-producer-and-channel.md` when a write should notify (push, email, SMS, in-app). Every writer of the field must stage the event; never resend when provider acceptance is unknown; a `202` is not delivery.

**Service wiring (settings, app factory, DI chain)**: Read `reference/fastapi-architecture-and-config.md` when wiring a service: fail-fast `Settings`, `create_app` + `lifespan`, session → repository → service chain, commit ownership, route order, atomic idempotent writes, ruff baseline.

**Authorization boundaries**: Read `reference/fastapi-authorization-boundaries.md` when a route acts on behalf of a caller: actor vs subject, object-level scope (404 for foreign objects), service-only side-effect endpoints, account-existence oracles, authorization tests.

**Sessions, transactions, pooling**: Read `reference/sqlalchemy-async-sessions-and-transactions.md` when writing sessions, `get_session` dependencies, services that commit, `IntegrityError` handling or engine/pool configuration. Canonical for transaction ownership.

**Migration safety**: Read `reference/alembic-migration-safety.md` when writing or reviewing an Alembic revision or `env.py`, adding indexes/constraints/enums, backfilling, or fixing multiple heads.

**Reliability (idempotency, locks, retries, outbox)**: Read `reference/reliability-idempotency-retries-outbox.md` when adding idempotency keys, row/advisory locks, retries or circuit breakers, an outbox/claim queue, or a message consumer.

**asyncio correctness**: Read `reference/asyncio-concurrency-and-tasks.md` when using `create_task`/`gather`/`TaskGroup`, `to_thread`, thread-to-loop callbacks, cancellation or lifespan shutdown.

**Testing, CI and observability** (other skills): real-database tests and ASGI clients → `python-testing-patterns/reference/postgres-integration-testing.md`; CI, lockfiles, dependency audit → `deployment-ci-cd/reference/python-ci-supply-chain.md`; logging, OpenTelemetry, probes, readiness → `deployment-ci-cd/reference/python-observability.md`.

**Always-on guardrails**: `.claude/rules/python-backend.md` loads automatically when you touch Python, `pyproject.toml`, `alembic/**` or Dockerfiles; it is the one-line checklist with links to the references above.

## Process

1. **Scaffold project structure** using uv or pip commands above
2. **Read reference files** when you need specific templates or configuration
3. **Create folder structure**: `src/my_service/` with subfolders `api/routes/`, `models/`, `services/`, `core/`
4. **Write main.py** using FastAPI app template with lifespan context manager
5. **Define Pydantic models** for request/response validation in `models/`
6. **Implement route handlers** in `api/routes/` with proper HTTP methods and status codes
7. **Add business logic** in `services/` layer (keep routes thin)
8. **Configure environment** using pydantic-settings in `core/config.py`
9. **Write tests** with pytest-asyncio and an `httpx2.AsyncClient` over `ASGITransport` inside `app.router.lifespan_context(app)`; include 401/403/404/422 negatives
10. **Gate**: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest --cov`, each with its own exit code

## Key Patterns

| Pattern | Implementation |
|---------|---------------|
| **Type hints** | Use everywhere: `def func(x: int) -> str:` |
| **Async by default** | All I/O-bound operations use `async def` and `await` |
| **Validation** | Pydantic models for all API inputs/outputs |
| **Config** | pydantic-settings with `.env` file support |
| **Dependency injection** | FastAPI `Depends()` for services and repositories |
| **Error handling** | Services raise domain errors; only routes, dependencies and exception handlers raise `HTTPException` (`reference/fastapi-error-handling.md`) |
| **Database** | SQLAlchemy 2.1 async, request-scoped `AsyncSession`, service owns the commit, `Mapped[]` types |
| **Body limits** | `FastAPI(max_body_size=...)` app-wide, tighter per route where needed |
| **Streaming** | `EventSourceResponse` or WebSocket; producer cancelled on disconnect (`streaming-protocols/reference/server-stream-lifecycle.md`) |
| **Shutdown** | `lifespan` exit disposes engines/clients; `uvicorn --timeout-graceful-shutdown` below the platform grace period |
| **Testing** | pytest with fixtures, httpx2 `AsyncClient`, negative tests, 80%+ coverage |

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Pydantic v2 | `https://docs.pydantic.dev/latest/llms-full.txt` | Model validation, Field constraints, settings |
| FastAPI / Python | `Context7` MCP | Latest FastAPI endpoints, dependencies, middleware |
| FastAPI release notes | `https://fastapi.tiangolo.com/release-notes/` | Breaking changes per minor version |
| Starlette release notes | `https://raw.githubusercontent.com/Kludex/starlette/main/docs/release-notes.md` | 1.x removals and additions |

## Error Handling

**Layering**: services and repositories raise domain errors (`NotFoundError`, `ConflictError`, ...); one registered exception handler maps them to HTTP responses with a stable error envelope. Raise `HTTPException` only in routes, dependencies and handlers. Full hierarchy, handlers and logging rules: `reference/fastapi-error-handling.md`.

```python
# service layer: no HTTP knowledge
if account is None:
    raise NotFoundError("account")

# route / dependency layer (or the registered handler) decides the status code
raise HTTPException(status_code=404, detail="Account not found")
```

**Validation errors**: Pydantic returns 422 with details. Use `Field()` constraints for business rules and `extra="forbid"` on request models.

**Database errors**: do not map every `IntegrityError` to 409. Inspect the violated constraint (unique vs foreign key vs not-null vs check) and map each deliberately; roll back the session first. Details and the idempotent-insert pattern: `reference/sqlalchemy-async-sessions-and-transactions.md`.

**Logging errors**: never log `str(exc)` or `exc_info` of validation or database errors on request paths: they embed submitted values. Log the exception type, a stable code and a request id (`reference/fastapi-error-handling.md` and `.claude/rules/python-backend.md`).

## Common Commands

```bash
uv run uvicorn my_service.main:create_app --factory --reload   # dev server (factory, no module-level app)
uv run pytest -q --cov --cov-report=term-missing               # tests with coverage
uv run ruff check . && uv run ruff format --check .            # lint + format check
uv run mypy src tests                                          # strict type check
uv run alembic upgrade head                                    # run pending migrations
uv run alembic revision --autogenerate -m "description"        # generate a migration
```

## Hard Prohibitions

- Use `str | None` union syntax (Python 3.10+), not `Optional[str]`
- Use `model_validator` for cross-field Pydantic validation, not ad-hoc `__init__` logic
- No `@app.on_event`, `on_startup=`, `regex=`, `root_path=` on `FastAPI()`, or `**extra` kwargs on params
- No `app.routes` walk with `isinstance(..., APIRoute)`: use `iter_route_contexts()`

## Background Worker Services

For Pub/Sub, Cloud Scheduler, or GCS-triggered workers (NOT FastAPI REST APIs):

- Use the `/scaffold-python-worker` command to create the service structure
- Entry point: `async def run_job(payload: dict) -> JobResult:` in `src/job.py`
- External clients (APIs, cloud services) MUST be injected — never instantiated inline
- All failures MUST be logged via structlog and surfaced as status records — never swallowed
- Required env vars MUST have NO defaults in config — missing values raise `ValidationError` at startup
- After implementation: dispatch `python-worker-reviewer` agent for review

## Post-Code Review

After writing Python code, dispatch these reviewer agents:
- `code-reviewer` — general quality, DRY, error handling
- `python-worker-reviewer` — if this is a background worker service (Pub/Sub/Cloud Scheduler/GCS): silent failures, client injection, DB access patterns, structlog usage, test coverage
- `security-reviewer` — input validation, auth, dependency audit
