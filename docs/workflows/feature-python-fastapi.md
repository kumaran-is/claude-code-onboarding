# Feature Development — Python / FastAPI

> **When to use**: Building a new feature or endpoint in a Python 3.14 / FastAPI service
> **Time estimate**: 1–3 hours per feature
> **Prerequisites**: Approved spec in `docs/specs/`, approved plan in `docs/plans/` (see [`ideation-to-spec.md`](ideation-to-spec.md))

## Overview

Full Python/FastAPI feature lifecycle from scaffold through TDD to reviewed, security-cleared PR. Async by default, Pydantic v2 validated at boundaries, ruff-clean throughout.

## Phases

### Phase 1 — Project Scaffold (new projects only)

**Trigger**: No existing FastAPI project
**Command**: `/scaffold-python-api [project-name]`
**What it does** (details in `commands/scaffold-python-api.md`):
1. `uv init --package` on Python 3.14 with exact `==` pins and a committed `uv.lock`
2. `src/<package>/` layout: fail-fast `Settings` (`hide_input_in_errors=True`), structlog, one error envelope, request-id middleware, JWT auth dependency, a sample resource (route → service → repository), `/api/v1/health` and `/api/v1/ready`
3. Alembic with config in `pyproject.toml` and a first revision
4. Tests (happy path, 422, 401 negatives, owner isolation, route order, 500 envelope), OpenAPI snapshot script
5. Digest-pinned multi-stage Dockerfile (non-root, read-only friendly) and a GitHub Actions workflow

**Produces**: FastAPI service scaffold that passes its own gates
**Gate**: the `/verify` Python block exits 0 line by line (lock, sync, ruff, format, mypy, pytest with a database, pip-audit, `alembic check`), plus the command's negative controls

---

### Phase 1.5 — Architecture Decision (new features or unclear approach)

**Trigger**: Framework choice unclear, or async vs sync strategy not confirmed
**Skill**: `python-patterns`
**Decision checklist**:
- Framework: FastAPI (API-only) / Django (full-stack+admin) / Flask (simple/script)
- Async: Use `async def` for all I/O-bound FastAPI routes (workspace default)
- Structure: Layer-based (medium APIs) vs feature-based (5+ domain areas)
- Background tasks: `BackgroundTasks` (fire-and-forget) vs Celery/ARQ (distributed, retry)

**Gate**: Framework, async strategy, and structure confirmed before writing code

---

### Phase 2 — Load Skill

**Trigger**: About to implement any FastAPI feature
**Action**: Load `python-dev` skill (`skills/python-dev/SKILL.md`)
**MCP**: Context7 for FastAPI, Pydantic v2 current APIs

**8 key patterns** (from `skills/python-dev/SKILL.md:45-56`):
- **Type hints** — all function signatures, no implicit `Any`
- **Async by default** — `async def` for all route handlers and services
- **Validation** — Pydantic v2 models at all API boundaries
- **Config** — `pydantic-settings` with `BaseSettings`, env var injection
- **Dependency injection** — `Annotated[..., Depends(...)]` aliases for services, DB sessions and the principal
- **Error handling** — domain exceptions mapped to one error envelope with `requestId` (`fastapi-error-handling.md`); never return raw strings
- **Database** — async SQLAlchemy with `AsyncSession`, or repository pattern
- **Testing** — `pytest-asyncio`, `httpx2.AsyncClient` + `ASGITransport` for app tests (httpx stays for outbound clients), `pytest-cov`

**Gate**: Skill loaded, MCP queried for any API signatures being used

**Also load**: `uv-package-manager` skill if setting up CI/CD or Docker for this service

---

### Phase 3 — TDD: Write Failing Test First

**Iron Law** (from `skills/test-driven-development/SKILL.md:16-21`): `NO IMPLEMENTATION WITHOUT A FAILING TEST FIRST`

**For Python** (from `skills/test-driven-development/references/tdd-patterns-python.md`):
- `pytest-asyncio` for async test functions
- `httpx2.AsyncClient` with `ASGITransport` for endpoint tests, inside `app.router.lifespan_context(app)`
- `pytest.fixture` for shared setup
- `unittest.mock.AsyncMock` for mocking async dependencies

**Red-Green-Refactor**:
1. **Red** — Write pytest test that defines expected behaviour, confirm `FAILED`
2. **Green** — Minimum code to pass
3. **Refactor** — Clean structure (tests still green)

**Produces**: Failing test with correct assertion
**Gate**: `pytest <test_file>` shows `FAILED` (not error)

---

### Phase 3.5 — Test Infrastructure (new projects only)

**Trigger**: No `conftest.py` exists or test suite needs restructuring
**Skill**: `python-testing-patterns`
**Setup**:
1. Create `tests/conftest.py` with `AsyncClient` fixture
2. Configure `pyproject.toml` — `asyncio_mode = "auto"`, testpaths, markers
3. Add test markers: `@pytest.mark.slow`, `@pytest.mark.integration`
4. Set coverage gate: `--cov-fail-under=80`

**Gate**: `pytest -q` passes, `pytest --cov=src --cov-report=term-missing` shows coverage

---

### Phase 4 — Implement Feature

**Build order**:
1. ORM model → `src/<package>/models/db/<name>.py`; Alembic revision in the same change (`alembic check` must pass)
2. Request/Response models → `src/<package>/models/<name>.py`
   - Use `pydantic-models-py` skill for Base/Create/Update/Response model pattern
3. Repository → `src/<package>/repositories/<name>_repository.py` (flush only)
4. Service → `src/<package>/services/<name>_service.py` (owns the commit)
5. Routes → `src/<package>/api/routes/<name>.py`
6. Register the router in `create_app()` (`main.py`) and regenerate the OpenAPI snapshot

**Standards**:
- No `print()` — use the project's structlog logger with structured context; log caught exceptions with `log_exception` (type only)
- No bare `except:` — always catch specific exceptions, log, and either rethrow or raise a domain exception (see `reference/fastapi-error-handling.md`)
- All secrets via environment variables — never hardcoded
- Pydantic v2 `model_validator` for cross-field validation
- Async database sessions via `AsyncSession` context manager

**Produces**: Working feature, `pytest` passes
**Gate**: `/verify full` Python block exits 0 line by line (ruff, format, mypy strict, pytest)

---

### Phase 4.5 — Authentication Setup (when endpoint requires auth)

**Trigger**: Implementing any endpoint that requires user identity (login, protected routes, user-scoped data)
**Skills**: `python-dev` → `reference/fastapi-auth-security.md` (JWT, bcrypt, RBAC, PBAC), `pydantic-models-py` (token schemas), `security-reviewer` agent after implementation

**Auth strategy decision**:
```
Stateless API (microservice, mobile backend)?
└── JWT tokens — access token + refresh token pattern

Full-stack web app with sessions?
└── OAuth2 password flow with session cookies

Third-party login (Google, GitHub)?
└── OAuth2 authorization code flow
```

**Implementation steps**:
1. Choose auth strategy (JWT vs OAuth2 — see decision above)
2. Create auth Pydantic schemas: `TokenResponse`, `LoginRequest`, `UserCreate`
3. Implement `/auth/register` endpoint — hash password with `bcrypt` (cost ≥ 12)
4. Implement `/auth/login` endpoint — verify password, return JWT access + refresh tokens
5. Create `get_current_subject` (verify the JWT: pinned algorithms, `exp`/`iss`/`aud`/`sub`) and `get_current_user` (load the account; disabled or deleted → 401)
6. Apply them to protected routes through an `Annotated` alias (`CurrentUser`); never take the user id from the body
7. Tests: missing token, wrong key, `none` algorithm, expired, wrong audience → 401; another user's object → 404

**Standards** (from `code-standards.md`):
- Passwords MUST be hashed with bcrypt (cost ≥ 12) or argon2 — never store plaintext
- JWT secrets via environment variable — never hardcoded
- Access tokens: short-lived (15 min); refresh tokens: longer-lived (7 days), rotated on use

```python
# get_current_subject: reference/fastapi-auth-security.md §4 (401 + WWW-Authenticate on any token failure)
from typing import Annotated

from fastapi import Depends

from my_service.api.deps import get_current_subject, get_current_user  # get_current_user loads the account by subject

CurrentUser = Annotated[User, Depends(get_current_user)]  # 401 for a deleted or disabled account too


async def create_item(request: ItemCreate, current_user: CurrentUser) -> ItemResponse: ...
```

**Gate**: `pytest` passes for auth endpoints, `security-reviewer` agent run — zero CRITICAL/HIGH on auth code

---

### Phase 5 — Review (run in parallel)

**Agent 1**: `code-reviewer`
- Vibe: *"Finds real bugs, not style preferences — ≥80% confidence before raising an issue"*
- Checks: general quality, patterns, DRY violations, unused imports

**Agent 2**: `silent-failure-hunter`
- Vibe: *"An empty catch block is not error handling — it's a lie to the operator"*
- Checks: bare `except`, `except Exception: pass`, missing error logging, silent fallbacks

**Agent 3**: `security-reviewer`
- Vibe: *"Assumes every input is hostile until the code proves otherwise"*
- Checks: input validation, SQL injection, secrets exposure, SSRF, path traversal

**Gate**: Zero CRITICAL findings; HIGH findings resolved or accepted

---

### Phase 6 — Pre-Commit Validation

**Command**: `/validate-changes`
**Agent**: `output-evaluator`
**Also run**: the `/verify pre-pr` EXPORT + AUDIT lines (`pip-audit` on the exported `uv.lock`; gate on its exit code, it prints no severity)

**Verdicts**: APPROVE → proceed | NEEDS_REVIEW / REJECT → fix and re-run
**Gate**: APPROVE + `pip-audit` exit 0 (or every ignored ID listed with a reason)

---

### Phase 7 — PR Review

**Command**: `/review-pr`
**6 roles**: comment-analyzer + pr-test-analyzer + silent-failure-hunter + type-design-analyzer + code-reviewer + code-simplifier
**Gate**: All CRITICAL + HIGH resolved

---

## Quick Reference

| Phase | What to Run | Produces | Gate |
|-------|-------------|----------|------|
| 1 — Scaffold | `/scaffold-python-api` | Full FastAPI skeleton | `pytest` passes |
| 2 — Load skill | `python-dev` + `uv-package-manager` | Pattern reference | MCP queried |
| 3 — TDD | Write failing pytest | Failing test | `FAILED` status |
| 3.5 — Test infra | `python-testing-patterns` | conftest.py, markers, coverage | `pytest -q` passes |
| 4 — Implement | model → schema → repo → service → router | Working code | `pytest` green |
| 4.5 — Auth setup | `python-dev` Depends pattern + bcrypt | Login/register endpoints, auth deps | `pytest` green, `security-reviewer` APPROVE |
| 5 — Review | `code-reviewer` + `silent-failure-hunter` + `security-reviewer` | Findings | Zero CRITICAL |
| 6 — Pre-commit | `/validate-changes` | APPROVE/NEEDS_REVIEW/REJECT | APPROVE |
| 7 — PR | `/review-pr` | 6-role review | CRITICAL+HIGH resolved |

---

## Common Pitfalls

- **Sync functions in async routes** — blocking calls in `async def` routes block the event loop; use `asyncio.to_thread()` for sync I/O
- **Pydantic v1 syntax** — this stack uses Pydantic v2; `@validator` is replaced by `@field_validator`, `orm_mode` by `model_config = ConfigDict(from_attributes=True)`
- **Missing `await`** — async SQLAlchemy calls without `await` return coroutines, not results
- **Bare `except`** — catches `KeyboardInterrupt` and `SystemExit`; always be specific
- **`print()` in production code** — bypasses log aggregation; use structlog
- **Hardcoded secrets or env fallbacks** — required settings have no defaults (`pydantic-settings`, `SecretStr`); never `os.getenv("X", "literal")`
- **Secrets in a boot traceback** — a settings `ValidationError` prints `input_value`; set `hide_input_in_errors=True` on `Settings`

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — spec and plan before implementation
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — LangGraph/LangChain AI agents on FastAPI
- [`security-audit.md`](security-audit.md) — deeper security audit
- [`pr-shipping.md`](pr-shipping.md) — PR lifecycle after review
- `python-patterns` skill — architecture decisions before implementation
- `pydantic-models-py` skill — API schema design with multi-model pattern
- `fastapi-auth-security.md` reference — JWT, RBAC, PBAC, password hashing, resource ownership (in `python-dev` skill)
- `fastapi-error-handling.md` reference — exception hierarchy, async retry (`tenacity`), circuit breaker (`circuitbreaker`), exception handlers (in `python-dev` skill)
- `uv-package-manager` skill — lockfiles, Docker, CI caching for Python projects
- `python-testing-patterns` skill — pytest infrastructure, fixtures, coverage config
- `python-packaging` skill — internal CLI tools and project structure
