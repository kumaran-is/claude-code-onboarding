---
name: python-patterns
description: Python architecture decision-making for framework selection (FastAPI/Django/Flask), async vs sync patterns, type hint strategy, project structure, background task selection, and the runtime decision (Python 3.14 vs 3.15, free-threaded build, subinterpreters, workspace vs standalone project). Use BEFORE implementing Python features to choose the right approach for the context.
allowed-tools: Read, Write, Edit
metadata:
  triggers: Python framework choice, FastAPI vs Django, async vs sync Python, Python project structure, Python background tasks, Python architecture decisions, Celery vs BackgroundTasks, Python async libraries, Python 3.15, Python 3.14 upgrade, free-threaded Python, python3.14t, subinterpreters, which Python version
  related-skills: python-dev, agentic-ai-dev, api-design-principles
  domain: backend
  role: advisor
  scope: decision
  output-format: guidance
last-reviewed: "2026-11-23"
---

## Iron Law

**CHOOSE FRAMEWORK AND ASYNC STRATEGY BEFORE WRITING A SINGLE LINE — defaulting to "just use FastAPI" without context analysis produces the wrong architecture for the wrong problem**

# Python Patterns

> Python development principles and decision-making for the Python 3.14 ecosystem (validated 2026-11-23).
> **Learn to THINK about context, not memorize patterns.**

## When to Use

Use this skill when making Python architecture decisions, choosing frameworks, designing async patterns, or structuring Python projects. Load BEFORE `python-dev` when the approach is unclear.

---

## 1. Framework Selection

### Decision Tree

```
What are you building?
│
├── API-first / Microservices
│   └── FastAPI (async, modern, fast) ← workspace default
│
├── Full-stack web / CMS / Admin
│   └── Django (batteries-included)
│
├── Simple / Script / Learning
│   └── Flask (minimal, flexible)
│
├── AI/ML API serving
│   └── FastAPI (Pydantic, async, uvicorn)
│
└── Background workers
    └── Celery + any framework
```

### Comparison

| Factor | FastAPI | Django | Flask |
|--------|---------|--------|-------|
| **Best for** | APIs, microservices | Full-stack, CMS | Simple, learning |
| **Async** | Native | Django 5.0+ | Via extensions |
| **Admin** | Manual | Built-in | Via extensions |
| **ORM** | Choose your own | Django ORM | Choose your own |
| **Learning curve** | Low | Medium | Low |

### Selection Questions to Ask
1. Is this API-only or full-stack?
2. Need admin interface?
3. Team familiar with async?
4. Existing infrastructure constraints?

---

## 2. Async vs Sync Decision

### When to Use Async

```
async def is better when:
├── I/O-bound operations (database, HTTP, file)
├── Many concurrent connections
├── Real-time features
├── Microservices communication
└── FastAPI/Starlette/Django ASGI

def (sync) is better when:
├── CPU-bound operations
├── Simple scripts
├── Legacy codebase
├── Team unfamiliar with async
└── Blocking libraries (no async version)
```

### The Golden Rule

```
I/O-bound → async (waiting for external)
CPU-bound → sync + multiprocessing (computing)

Don't:
├── Mix sync and async carelessly
├── Use sync libraries in async code
└── Force async for CPU-bound work
```

### Async Library Selection

| Need | Async Library |
|------|---------------|
| HTTP client | httpx |
| PostgreSQL | asyncpg |
| Redis | redis-py `redis.asyncio` (the separate aioredis package is archived) |
| File I/O | `anyio.Path` / `asyncio.to_thread` for large files; aiofiles is optional |
| Database ORM | SQLAlchemy 2.1 async: pin `sqlalchemy[asyncio]==2.1.9`. Bare `sqlalchemy` has no greenlet and `create_async_engine` fails at first connect with `ImportError: ... requires that the Python 'greenlet' library is installed` (executed) |

---

## 3. Type Hints Strategy

### When to Type

```
Always type:
├── Function parameters
├── Return types
├── Class attributes
└── Public APIs

Can skip:
├── Local variables (let inference work)
├── One-off scripts
└── Tests (usually)
```

### Common Patterns

```python
# Optional → might be None (use str | None syntax, not Optional[str])
def find_user(id: int) -> User | None: ...

# Union → one of multiple types
def process(data: str | dict) -> None: ...

# Generic collections
def get_items() -> list[Item]: ...
def get_mapping() -> dict[str, int]: ...
```

### Pydantic for Validation

```
When to use Pydantic:
├── API request/response models (always — Iron Law in python-dev)
├── Configuration/settings (pydantic-settings)
├── Data validation at system boundaries
└── Serialization to JSON

Benefits:
├── Runtime validation
├── Auto-generated JSON schema
├── Works with FastAPI natively
└── Clear error messages
```

---

## 4. Project Structure

### Structure Selection

```
Small project / Script:
├── main.py
├── utils.py
└── requirements.txt

Medium API (workspace default):
├── src/
│   └── my_service/
│       ├── api/routes/
│       ├── models/
│       ├── services/
│       └── core/
├── tests/
└── pyproject.toml

Large application (feature-based):
├── src/
│   └── myapp/
│       ├── users/
│       │   ├── routes.py
│       │   ├── service.py
│       │   └── schemas.py
│       └── products/
├── tests/
└── pyproject.toml
```

### FastAPI Layer Organization

```
By layer (workspace default for medium APIs):
├── routes/     (API endpoints — thin, delegate to services)
├── services/   (business logic)
├── models/     (database models)
├── schemas/    (Pydantic request/response models)
└── core/       (config, dependencies, lifespan)

By feature (for large apps with 5+ domains):
├── users/
│   ├── routes.py, service.py, schemas.py
└── products/
    └── routes.py, service.py, schemas.py
```

---

## 5. FastAPI Principles

### async def vs def

```
Use async def when:
├── Using async database drivers (asyncpg, SQLAlchemy async)
├── Making async HTTP calls (httpx)
├── Any I/O-bound operations
└── Want to handle concurrency

Use def when:
├── Blocking operations that cannot be made async
├── CPU-bound work (FastAPI runs sync routes in threadpool)
└── Integrating legacy sync libraries
```

### Dependency Injection

```
Use FastAPI Depends() for:
├── Database sessions
├── Current user / Auth
├── Configuration
└── Shared resources

Benefits:
├── Testability — mock dependencies in tests
├── Clean separation — routes stay thin
└── Automatic cleanup via yield

Rules:
├── Declare dependencies as Annotated aliases (ruff FAST002)
├── Exit code after `yield` runs AFTER the response is sent (default scope):
│   never commit there — the service commits, or use Depends(scope="function")
└── A dependency result is cached per request: copy before narrowing, never mutate
```

Details: `python-dev/reference/fastapi-architecture-and-config.md` §4 and `fastapi-authorization-boundaries.md`.

### Pydantic v2 Integration

```python
# Request validation — user is fully validated before handler runs
# (UserCreate sets model_config = ConfigDict(extra="forbid"): unknown keys are a 422)
@app.post("/users")
async def create(user: UserCreate) -> UserResponse:
    ...

# Response model enforced — extra fields stripped automatically
```

---

## 6. Background Tasks

### Selection Guide

| Solution | Best For |
|----------|----------|
| **BackgroundTasks** | Simple in-process, fire-and-forget |
| **Celery** | Distributed, complex workflows, retry logic |
| **ARQ** | Async Redis-based, simpler than Celery |
| **RQ** | Simple Redis queue |
| **Dramatiq** | Actor-based, simpler than Celery |

### When to Use Each

```
FastAPI BackgroundTasks:
├── Quick operations (< 5s)
├── No persistence needed
├── Fire-and-forget
└── Same process as API

BackgroundTasks run AFTER the response is sent: pass ids/primitives (the request session is
closed), and use an outbox/queue for anything that must not be lost.

Celery/ARQ:
├── Long-running tasks
├── Need retry logic
├── Distributed workers
├── Persistent queue
└── Complex workflows
```

---

## 7. Error Handling Principles

### Exception Strategy

```
In FastAPI:
├── Create custom exception classes per domain
├── Register exception handlers in app factory
├── Return consistent error format (code + message + details)
└── Log without exposing stack traces to client

Pattern:
├── Raise domain exceptions in services
├── Catch and transform in exception handlers
└── Client gets clean error response
```

### Error Response Format

```
Include:
├── Error code (programmatic — e.g., "USER_NOT_FOUND")
├── Message (human readable)
├── Details (field-level when applicable)
└── NOT stack traces (security violation)
```

---

## 8. Testing Strategy

| Type | Purpose | Tools |
|------|---------|-------|
| **Unit** | Business logic in services | pytest |
| **Integration** | API endpoints | pytest + httpx AsyncClient |
| **E2E** | Full workflows including DB | pytest + real test DB |

### Async Testing Pattern

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# pytest-asyncio 1.x with asyncio_mode = "auto" (pyproject): no per-test marker needed
async def test_create_user(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/users", json={"name": "Alice"})
        assert response.status_code == 201
```

---

## 9. Decision Checklist

Before implementing any Python feature:

- [ ] **Framework chosen for THIS context?** (not just default FastAPI)
- [ ] **Async vs sync decided?** (I/O-bound = async, CPU-bound = sync + multiprocessing)
- [ ] **Type hint strategy planned?** (all public APIs + function signatures)
- [ ] **Project structure chosen?** (layer-based vs feature-based)
- [ ] **Error handling pattern decided?** (custom exceptions + handlers)
- [ ] **Background task approach?** (BackgroundTasks vs Celery/ARQ)

---

## 10. Anti-Patterns

### ❌ DON'T
- Default to Django for simple APIs (FastAPI is likely better)
- Use sync libraries in `async def` routes (blocks event loop)
- Skip type hints for public APIs
- Put business logic in route handlers — keep routes thin
- Ignore N+1 queries (use `select_related`/`prefetch_related` or eager loading)
- Mix async and sync carelessly — use `asyncio.to_thread()` for sync I/O in async context

### ✅ DO
- Choose framework based on actual context
- Use `async def` for all I/O-bound FastAPI endpoints
- Use Pydantic v2 for all API boundaries (see `python-dev` Iron Law)
- Separate concerns: routes → services → repositories
- Test critical paths with real async test client

---

## 11. Runtime Decision (Python 3.14 vs 3.15, free-threading, subinterpreters)

Validated 2026-11-23 with uv 0.13.9: core FastAPI/SQLAlchemy/asyncpg/OTel set locked and tested on 3.14.10 and 3.15.2; a wider set (google-adk 2.15, google-cloud-pubsub/firestore/storage, langchain 1.5.2, langgraph 1.2.24, weaviate-client 4.24.1, presidio-analyzer 2.2.366, weasyprint 70.0, redis 8.2.0, pgvector 0.5.1) locked on both.

| Option | Decision | Evidence |
|---|---|---|
| CPython **3.14.10** | **ADOPT (default)** for services, workers and tools | every dependency above installs from `cp314`/pure wheels; `uv sync --locked --no-build` succeeds |
| CPython 3.15.2 | **DEFER** as a default; OPTIONAL forward-compat CI job (`uv run --python 3.15 pytest` with `--no-build`) | the core set syncs from `cp315` wheels, but the wider set needs source builds on 3.15: weaviate-client 4.24.1 caps `grpcio<1.80` (1.78.2 has wheels only up to cp314), presidio-analyzer 2.2.366 caps `numpy<2.5` (2.4.6 has none for cp315) and zstandard 0.25.0 has no cp315 wheel; `uv sync --no-build` fails on 3.15 (exit 2). presidio-analyzer also declares `Requires-Python <3.15`, which uv does not enforce (upper bounds are ignored) |
| CPython 3.13 | Only for a STANDALONE project whose dependency has no cp314 wheel (paddlepaddle 3.3.1: cp39–cp313) | own `uv.lock` and `.python-version`; cannot be a member of a 3.14 workspace (`uv-package-manager` playbook sections 6–7) |
| Free-threaded build (`3.14t`) | **DEFER** for services; OPTIONAL for an isolated CPU-bound pure-Python job | officially supported but optional (PEP 779). Measured, one noisy dev machine: 4 CPU threads 2.6–3.7 s with the GIL vs 0.9–1.5 s free-threaded. Wheel gaps are real: orjson 3.13.0 and grpcio 1.85.3 publish no `cp314t` wheel (orjson failed to build) |
| Subinterpreters (`concurrent.interpreters`, `InterpreterPoolExecutor`) | OPTIONAL | stdlib in 3.14 (PEP 734), executed; C extensions must support them: prove each import in a worker interpreter first |

| Separate lock (same interpreter) | REQUIRED for google-adk 2.15 next to google-genai 3.x users | google-adk 2.15.1 requires `google-genai>=2.34,<3` and `websockets>=15.0.1,<16`; langchain-google-genai 4.5.2 requires `google-genai>=3.3.0`: one workspace lock fails (executed, uv 0.13.9); two projects lock fine (`uv-package-manager` playbook section 7) |

Rules:
- Commit `.python-version` (patch pinned) and match the Docker base tag; `requires-python = ">=3.14"`. uv 0.13 downloads 3.15 when nothing is pinned (executed: a project without `.python-version` or `requires-python` resolved for `>=3.15`).
- uv ignores dependency `Requires-Python` UPPER bounds when resolving (presidio-analyzer `<3.15` locked on 3.15), so a lock that succeeds on 3.15 proves nothing. Base a version decision on wheel availability (`uv sync --locked --no-build`), imports and the test suite on that interpreter.
- Re-evaluate 3.15 when the capped dependencies above ship cp315 wheels; the forward-compat job tells you when.
- 3.14 language/stdlib changes that alter code: `python-dev` `reference/python-idioms.md` section 9 and `reference/asyncio-concurrency-and-tasks.md` sections 5–5b.
