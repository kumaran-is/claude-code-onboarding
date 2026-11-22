---
name: python-dev
description: This skill provides patterns and templates for Python 3.14 development with FastAPI and modern tooling. It should be activated when creating Python APIs, scripts, data processing pipelines, or pytest tests.
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Python, FastAPI, Pydantic, Python API, async Python, Python backend, uv, ruff, Python 3.14
  related-skills: openapi-spec-generation, database-schema-designer, agentic-ai-dev
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-14"
---

## Iron Law

**NO FASTAPI ENDPOINT WITHOUT A PYDANTIC v2 INPUT MODEL — never trust raw request data; validate at the boundary, always**

# Python 3.14 Development Skill

## Code Conventions
- Use **Python 3.14** with type hints everywhere
- **FastAPI** for REST APIs, **Pydantic v2** for validation
- Async by default: `async def` endpoints, `asyncpg` for PostgreSQL
- Use `uv` for package management, `ruff` for linting, `mypy` for types
- Folder structure: `api/routes/ → services/ → repositories/ → models/`
- Tests: pytest + pytest-asyncio + httpx

## Quick Scaffold — New Python Project

```bash
# Using uv (preferred)
uv init my-service
cd my-service
uv add fastapi uvicorn pydantic pydantic-settings
uv add --dev pytest pytest-asyncio httpx ruff mypy

# Or using pip
mkdir my-service && cd my-service
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install fastapi uvicorn pydantic pydantic-settings
pip install -e ".[dev]"
```

## Reference Files

**Code templates and project config**: Read `reference/fastapi-templates.md` for FastAPI app structure, Pydantic models, route handlers, SQLAlchemy models, pytest fixtures, pyproject.toml template, Docker configuration, and common commands.

**Advanced patterns and profiling**: Read `reference/python-advanced-patterns.md` for performance profiling (cProfile, py-spy, memory_profiler), pytest-benchmark, property-based testing with Hypothesis, structural pattern matching, descriptors, and memory optimization techniques.

**Auth, security and authorization**: Read `reference/fastapi-auth-security.md` for JWT with PyJWT (explicit algorithms, required `exp`/`sub`/`iat`), Argon2id password hashing with `pwdlib` (run off the event loop), `OAuth2PasswordBearer` dependencies, RBAC/permission maps and rate-limit keys. `python-jose` and `passlib` are not used in new code.

**Error handling, retry, and circuit breakers**: Read `reference/fastapi-error-handling.md` for custom exception hierarchy (`AppError` → `NotFoundError`/`ValidationError`/`ExternalServiceError`), FastAPI exception handlers, async retry with `tenacity`, async circuit breaker with `circuitbreaker`, error logging context middleware, and pytest patterns for error paths.

**Backend service consistency patterns**: Read `reference/backend-service-patterns.md` for the mandatory per-service patterns: timing-safe internal secret guard (P1), fail-fast config (P2), structured logging (P3), session and transaction ownership (P4), `lifespan`-only Redis/client lifecycle (P7) and the checklist at the end.

**Live E2E integration testing**: Read `reference/backend-live-e2e-standard.md` for why unit tests (ASGITransport + mocks) miss real integration bugs, the per-service test pattern (health, auth gate, fake JWT rejection, internal secret gate, input validation), auth ordering rules (FastAPI validates auth before Pydantic), HTTP method verification from OpenAPI spec, and the feedback loop for fixing live failures.

**Pub/Sub and Firestore messaging patterns**: Read `reference/pubsub-firestore-patterns.md` for the three canonical messaging patterns: Pattern A (fire-and-forget `asyncio.create_task` for informational events), Pattern B (transactional outbox with `SELECT FOR UPDATE SKIP LOCKED` for load-bearing events), Pattern C (Firestore status bus for real-time mobile UI). Includes decision tree, full implementation templates, subscriber patterns, and hard rules for each.

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
9. **Write tests** with pytest-asyncio and AsyncClient fixtures
10. **Format and type-check**: Run `ruff format`, `ruff check --fix`, and `mypy`

## Key Patterns

| Pattern | Implementation |
|---------|---------------|
| **Type hints** | Use everywhere: `def func(x: int) -> str:` |
| **Async by default** | All I/O-bound operations use `async def` and `await` |
| **Validation** | Pydantic models for all API inputs/outputs |
| **Config** | pydantic-settings with `.env` file support |
| **Dependency injection** | FastAPI `Depends()` for services and repositories |
| **Error handling** | Services raise domain errors; only routes, dependencies and exception handlers raise `HTTPException` (`reference/fastapi-error-handling.md`) |
| **Database** | SQLAlchemy 2.0+ with async session and `Mapped[]` types |
| **Testing** | pytest with fixtures, httpx AsyncClient, 80%+ coverage |

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Pydantic v2 | `https://docs.pydantic.dev/latest/llms-full.txt` | Model validation, Field constraints, settings |
| FastAPI / Python | `Context7` MCP | Latest FastAPI endpoints, dependencies, middleware |

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
uvicorn my_service.main:create_app --factory --reload      # Dev server (hot reload; factory, no module-level app)
pytest -q                                              # Run tests (quiet output)
pytest -q --cov=src --cov-report=term-missing          # Tests with coverage
ruff check --fix .                                     # Lint and auto-fix
ruff format .                                          # Format code
mypy src/                                              # Type check
alembic upgrade head                                   # Run pending migrations
alembic revision --autogenerate -m "description"       # Generate new migration
```

## Hard Prohibitions

- Use `str | None` union syntax (Python 3.10+), not `Optional[str]`
- Use `model_validator` for cross-field Pydantic validation, not ad-hoc `__init__` logic

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
