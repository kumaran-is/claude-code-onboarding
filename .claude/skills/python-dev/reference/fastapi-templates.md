# FastAPI Templates, Code Patterns, and Project Configuration

Production-ready templates for Python 3.14 + FastAPI, executed on CPython 3.14.10, FastAPI 0.165.0, Starlette 1.10.0,
Pydantic 2.14.4, SQLAlchemy 2.1.9, uvicorn 0.54.0 (reference app: 44 tests, `mypy --strict` and ruff clean, 20 negative
controls). Wiring rules: `fastapi-architecture-and-config.md`.

## FastAPI App Template

Build the app in a factory; lifecycle lives in `lifespan` only (never `on_startup`/`on_event`), logging is structured
(no `print`). Full version with cache ping, handlers and middleware: `fastapi-architecture-and-config.md` §3.

```python
# src/my_service/main.py
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url.get_secret_value())
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = App(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        max_body_size=settings.max_body_bytes,   # 0.164+: 413 before routing
    )
    register_exception_handlers(app)        # error-handling §2; App: observability §4
    app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
    return app
```

No module-level `app = create_app()` (it runs `Settings()` at import): run `uvicorn my_service.main:create_app
--factory`; tests call `create_app(test_settings)` (`fastapi-architecture-and-config.md` §3).

## Pydantic Models Template

Request models forbid unknown keys (a typo, an injected `role` or `email` is a 422, not a silent
no-op); a non-optional field also rejects explicit `null`. Responses stay lenient. More:
`.claude/skills/pydantic-models-py/SKILL.md` (PATCH with several optional fields: its null guard).

```python
# src/my_service/models/user.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RequestModel(BaseModel):
    """Base for request bodies: unknown keys are errors, not silently dropped."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateUserRequest(RequestModel):
    """Admin invite: no password here; the invited user sets one through the emailed link."""
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)


class UpdateMeRequest(RequestModel):
    """Self-service PATCH. No email: changing it re-verifies the NEW address first (a plain
    field update plus a password reset to the new address is an account takeover)."""
    name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    created_at: datetime
    updated_at: datetime
```

## Config with pydantic-settings

No defaults for secrets or environment-specific values; secrets are `SecretStr`. Loader that prints
field names only and the boot-contract test: `fastapi-architecture-and-config.md` §2.

```python
# src/my_service/core/config.py
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_name: str = "My Service"             # operational default
    max_body_bytes: int = 1_048_576          # operational default
    database_url: SecretStr                  # required; postgresql+asyncpg:// (validator: architecture §2)
    jwt_secret: SecretStr = Field(min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()      # values come from the environment; mypy plugin note: pyproject below
```

## Route Handler Template

Every route takes an authenticated caller: `CurrentUser` (401 without a valid token) or `AdminUser`
(403 without the role), both from `fastapi-auth-security.md` §4 and §6. Admin routes take the tenant
from the verified token and put it in the query, so a foreign id is a 404 like a missing one
(`fastapi-authorization-boundaries.md` §2). Self-service is `/me` only. Public sign-up is the uniform-202
`/register` (`fastapi-auth-security.md` §5), never this router: a 409 there tells anyone which emails
exist. Dependencies are `Annotated` aliases (ruff `FAST002`), list parameters are bounded, routes never
touch the session. Optional auth (`User | None`) is only for routes that also serve anonymous callers. The return annotation is the response model
(filtering and OpenAPI); add `response_model=` only when the annotation must differ. Register static
routes before parameterised siblings (Pitfall 7).

```python
# src/my_service/api/deps.py
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session          # closing rolls back anything uncommitted; the SERVICE commits

SessionDep = Annotated[AsyncSession, Depends(get_session)]

def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session), session)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]           # auth-security §4: 401
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]     # auth-security §6: 403
```

```python
# src/my_service/api/routes/users.py
router = APIRouter()
MAX_PAGE_SIZE = 100

@router.get("/me")                                          # static /me BEFORE /{user_id}
async def get_me(user: CurrentUser, svc: UserServiceDep) -> UserResponse:
    return UserResponse.model_validate(await svc.get(user.tenant_id, user.id))

@router.patch("/me")
async def update_me(body: UpdateMeRequest, user: CurrentUser, svc: UserServiceDep) -> UserResponse:
    return UserResponse.model_validate(await svc.update(user.tenant_id, user.id, body))

@router.get("/")
async def list_users(
    admin: AdminUser,
    svc: UserServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> list[UserResponse]:
    users = await svc.list_page(admin.tenant_id, limit=page_size, offset=(page - 1) * page_size)
    return [UserResponse.model_validate(u) for u in users]

@router.get("/{user_id}")
async def get_user(user_id: UUID, admin: AdminUser, svc: UserServiceDep) -> UserResponse:
    return UserResponse.model_validate(await svc.get(admin.tenant_id, user_id))

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest, admin: AdminUser, svc: UserServiceDep
) -> UserResponse:
    return UserResponse.model_validate(await svc.create(admin.tenant_id, body))  # tenant: token
```

## SQLAlchemy Async Model

```python
# src/my_service/models/db/user.py
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class Base(AsyncAttrs, MappedAsDataclass, DeclarativeBase):
    """Typed constructors: mypy --strict rejects UserEntity(name=123); a plain base accepts it."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserEntity(Base):
    __tablename__ = "users"

    tenant_id: Mapped[UUID]   # leads the unique index below, which serves tenant filters
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str | None] = mapped_column(String(255), default=None, repr=False)
    id: Mapped[UUID] = mapped_column(primary_key=True, init=False, default_factory=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, default_factory=_utcnow
    )
    # A Python-callable onupdate stays readable after the UPDATE. A SERVER-side
    # onupdate=func.now() is expired afterwards: reading it in async code raises
    # MissingGreenlet until you `await session.refresh(obj, ["updated_at"])`.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, default_factory=_utcnow, onupdate=_utcnow
    )



# One account per address per tenant, any casing; login compares the same SQL lower() expression
# (fastapi-auth-security.md §5), never a Python casefold() (differs on "ß"). Column objects, not
# strings: func.lower("email") indexes the constant 'email' and a tenant's 2nd user collides.
Index("uq_users_tenant_email", UserEntity.tenant_id, func.lower(UserEntity.email), unique=True)
```

## Pytest Template

`ASGITransport` does not run the lifespan: wrap the app in `app.router.lifespan_context(app)`.
Use `create_app(Settings(_env_file=None, ...))` so each test builds an isolated app. Test clients use
**httpx2** (the maintained HTTPX continuation): Starlette 1.10's `TestClient` warns
`StarletteDeprecationWarning` when only `httpx` is installed, which fails a `-W error` suite (executed).
`TestClient` closes an unfinished stream by cancelling that request's app call, so prove stream cancellation against a real
uvicorn (`streaming-protocols/reference/server-stream-lifecycle.md`). Database fixtures and
real-PostgreSQL patterns: `.claude/skills/python-testing-patterns/`.

```python
# tests/test_users.py
@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, database_url=DB_URL, jwt_secret="j" * 32)
    app = create_app(settings)
    async with app.router.lifespan_context(app):            # ASGITransport does not run lifespan
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# `token(...)` mints a signed test token (fastapi-auth-security.md §11); seed admins and members
async def test_every_users_route_needs_a_token(client: httpx2.AsyncClient) -> None:
    for method, path in [("GET", "/"), ("POST", "/"), ("GET", "/me"), ("PATCH", "/me"),
                         ("GET", f"/{uuid4()}")]:
        resp = await client.request(method, f"/api/v1/users{path}", json={})
        assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"


async def test_member_403_and_foreign_tenant_404(client, member, admin, other_tenant_user) -> None:
    assert (await client.get("/api/v1/users/", headers=token(member))).status_code == 403
    foreign = await client.get(f"/api/v1/users/{other_tenant_user.id}", headers=token(admin))
    missing = await client.get(f"/api/v1/users/{uuid4()}", headers=token(admin))
    assert foreign.status_code == missing.status_code == 404


async def test_patch_me_rejects_email_and_null(client, member) -> None:
    for body in ({"name": "N", "email": "attacker@example.com"}, {"name": None}):
        resp = await client.patch("/api/v1/users/me", json=body, headers=token(member))
        assert resp.status_code == 422
```

Executed in the reference app (same routes, tenant as a token claim): 6 users tests (every route 401
without a token, member 403, foreign tenant 404 = missing, `/me` rejects `email`, another casing of an
address is a 409 while another tenant may reuse it, the address is stored as typed); 8 negative
controls (tenant predicate dropped, list unfiltered, list or create without the admin dependency,
`email` in the PATCH model, case-sensitive index, `func.lower("email")`, index without `tenant_id`)
each turned a test red.

## pyproject.toml Template

Pin exact versions and commit `uv.lock`; regenerate with `uv lock`, install with `uv sync --locked`.
The versions below were resolved together (uv 0.13.9, CPython 3.14.10; the patch lives in
`.python-version` and the Docker base, `requires-python` stays `>=3.14`). A floor (`>=`) drifted once
to a release that broke an instrumentation package and made `/health` fail.
`fastapi[standard-no-fastapi-cloud-cli]` brings uvicorn[standard], python-multipart, email-validator
and pydantic-settings without the FastAPI Cloud CLI (`fastapi[standard]` adds it and sentry-sdk).
FastAPI 0.165 itself requires `opentelemetry-api`. Tracing uses the native `FastAPI(telemetry={...})`
(`"logs": False`, `"operation_spans": False`, probe `exclude`), not `opentelemetry-instrumentation-fastapi`:
see `deployment-ci-cd/reference/python-observability.md` §3.2.

```toml
[project]
name = "my-service"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi[standard-no-fastapi-cloud-cli]==0.165.0",
    "pydantic[email]==2.14.4",      # EmailStr needs the email extra
    "pydantic-settings==2.16.3",
    "sqlalchemy[asyncio]==2.1.9",   # OTel instrumentation declares <2.1: per-engine skip_dep_check + span test (python-observability.md)
    "asyncpg==0.32.0",
    "alembic==1.20.1",
    "pyjwt[crypto]==2.15.1",
    "pwdlib[argon2]==0.4.2",
    "structlog==26.1.0",            # python-observability.md: JSON logs
    "tenacity==9.2.1",              # fastapi-error-handling.md: transient-only retry
]

[dependency-groups]
dev = [
    "pytest==9.2.0",
    "pytest-asyncio==1.5.0",
    "pytest-cov==7.1.0",
    "httpx2==2.16.2",               # TestClient / ASGITransport (httpx triggers a Starlette deprecation)
    "ruff==0.17.6",
    "mypy==2.4.1",
    "pytest-timeout==2.4.0",        # the testing guide sets `timeout = 30`
    "pip-audit==2.10.1",
]

[tool.ruff]
target-version = "py314"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF", "ASYNC", "FAST", "S", "BLE", "T20", "DTZ"]
ignore = ["SIM105"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]

[tool.mypy]
python_version = "3.14"
strict = true
plugins = ["pydantic.mypy"]         # with it, Settings() needs no `type: ignore[call-arg]`; without it, it does

[tool.pytest.ini_options]
asyncio_mode = "auto"
filterwarnings = ["error"]                        # a deprecation fails the suite, not production
asyncio_default_fixture_loop_scope = "session"    # the session-scoped `engine` fixture needs both
asyncio_default_test_loop_scope = "session"       # (else: `AssertionError` in fixture setup, every test errors)
pythonpath = ["src"]
testpaths = ["tests"]
```

Top-level `select` under `[tool.ruff]` is deprecated: keep rules under `[tool.ruff.lint]`.
`S` is noisy in tests (hence the ignores). Dependency audit commands: `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

## Docker Template

Use the canonical digest-pinned multi-stage Dockerfile in
`.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md` §8 (base image digest, pinned uv
binary, `uv sync --locked --no-dev`, non-root user, `uvicorn ... --factory` behind `exec`). Add
`--timeout-graceful-shutdown 8` to its `uvicorn` command so in-flight requests drain before the
platform kills the container (Cloud Run: SIGKILL 10 s after SIGTERM). Never `pip install uv` in an image.

## Common Pitfalls & Anti-Patterns

### Pitfall 1: `asyncio.run()` inside a running loop

`asyncio.run()` is a top-level entry point only. Inside an `async def` route, dependency or async test it
raises `RuntimeError: asyncio.run() cannot be called from a running event loop`: `await` the coroutine.

### Pitfall 2: Blocking work inside `async def`

FastAPI runs a `def` handler in a thread pool; an `async def` handler that calls blocking I/O
(`requests`, `time.sleep`, a blocking SDK, CPU-bound hashing) stalls **every** request on that worker.

```python
requests.get(url, timeout=5)                              # ❌ blocks every request on the worker
response = await request.app.state.http.get("/data")      # ✅ one async client, created in lifespan
digest = await run_in_threadpool(hasher.hash, plain)      # ✅ blocking/CPU work off the loop
```

Blocking SDKs go through one offload helper with a bounded pool and the SDK's own socket timeout
(cancelling the await cannot cancel the thread): `asyncio-concurrency-and-tasks.md`. Ruff
`ASYNC210`/`ASYNC251` flag the obvious calls. A scarce dependency can be capped with
`Depends(..., max_concurrency=N)` (`fastapi-architecture-and-config.md` §4).

### Pitfall 3: SQLAlchemy Async Session Misuse

Three defects, one fix. (1) An `AsyncSession(engine)` opened inside a route: several sessions per
request, no shared transaction, leaks. (2) A repository that commits: callers cannot compose
operations atomically. (3) A **default-scope dependency that commits after `yield`** runs after the
response is sent, so a failed commit still returns 200 (executed on a deferred foreign key: 200 and
no row; with `scope="function"` or a service-owned commit: 500 and no row).

```python
# ❌ commit after yield in a default-scope dependency (client sees 200 even if commit fails)
async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.commit()

# ✅ dependency opens/closes; the service owns the commit; repositories only flush
class UserService:
    async def create(self, data: CreateUserRequest) -> UserEntity:
        user = await self._repo.add(UserEntity(...))   # add() = add + flush
        await self._session.commit()                    # failure raises before any response byte
        return user

# ✅ ACCEPTABLE — a dependency that must commit exits BEFORE the response (FastAPI 0.121+)
SessionDep = Annotated[AsyncSession, Depends(get_db, scope="function")]
```

Ownership rules and session internals: `fastapi-architecture-and-config.md` §4 and
`sqlalchemy-async-sessions-and-transactions.md`.

### Pitfall 4: Missing `await`

Calling an `async def` without `await` returns a coroutine and does nothing (a delete that never runs).
`session.add()` is sync; `commit()`, `flush()`, `execute()` are awaited. mypy reports
`unused-coroutine`; pytest warns "coroutine ... was never awaited" (an error under `filterwarnings = ["error"]`).

### Pitfall 5: ORM objects in background tasks

`BackgroundTasks` run after the response, when the request session is closed: a passed ORM object is
detached (`DetachedInstanceError` on lazy attributes). Pass primitives (`str(user.id)`, `user.email`);
load-bearing work goes through an outbox (`reliability-idempotency-retries-outbox.md`).

### Pitfall 6: Mutating Pydantic models

Assigning to a `frozen=True` model raises `ValidationError` (`frozen_instance`); mutation of a
non-frozen model skips validation unless `validate_assignment=True`. Use
`model.model_copy(update={...})`, never v1 `.copy(update=...)`.

### Pitfall 7: Static Route Shadowed by a Parameterised Sibling

Routes match in registration order. With `GET /items/{item_id}` registered first, `GET /items/discovery`
is handled by the by-id route (422 for an `int` id, a wrong lookup for a `str` id). Register static
routes first and keep a test that walks `iter_route_contexts(app.routes)`: since FastAPI 0.137 a plain
`app.routes` walk does not see included routers and passes vacuously (`fastapi-architecture-and-config.md` §5).

---

## Repository Pattern Template

The repository owns SQLAlchemy queries and `flush()`; the service owns business rules and the
commit. One concrete repository per entity with UUID ids: introduce a generic base only at three or
more repositories (Rule of Three). Never `commit()` here.

```python
# src/my_service/repositories/user_repository.py
class UserRepository:
    """Queries and flush() only: the service owns commit/rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_tenant(self, user_id: UUID, tenant_id: UUID) -> UserEntity | None:
        # the tenant is IN the query: never get(id) and compare afterwards
        stmt = select(UserEntity).where(UserEntity.id == user_id, UserEntity.tenant_id == tenant_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()  # not session.scalar(): Any

    async def list_page(self, tenant_id: UUID, *, limit: int, offset: int) -> list[UserEntity]:
        order = (UserEntity.created_at, UserEntity.id)   # unique tiebreak
        stmt = (select(UserEntity).where(UserEntity.tenant_id == tenant_id)
                .order_by(*order).limit(limit).offset(offset))
        return list((await self._session.scalars(stmt)).all())

    async def add(self, user: UserEntity) -> UserEntity:
        self._session.add(user)
        await self._session.flush()      # generated values are available; nothing is committed
        return user

    async def apply_changes(self, user: UserEntity, changes: dict[str, Any]) -> UserEntity:
        for field, value in changes.items():
            setattr(user, field, value)
        await self._session.flush()
        return user
```

---

## Service Layer Template

The service coordinates business rules, calls repositories, raises domain exceptions and commits.
Routes stay thin. No module-level service singleton: the session is injected per request.
Every method takes the caller's tenant. Patch only an allowlist of fields (`model_dump(exclude_unset=True)`
of a model that forbids unknown keys). The unique constraint decides duplicates: map its `IntegrityError`
to `ConflictError` (a get-then-add check races; `sqlalchemy-async-sessions-and-transactions.md`).

```python
# src/my_service/services/user_service.py
class UserService:
    """Business rules and the commit. Raises domain errors, never HTTPException."""

    def __init__(self, repo: UserRepository, session: AsyncSession) -> None:
        self._repo, self._session = repo, session

    async def create(self, tenant_id: UUID, data: CreateUserRequest) -> UserEntity:
        try:
            user = await self._repo.add(UserEntity(tenant_id=tenant_id, **data.model_dump()))
            await self._session.commit()                 # a failed commit raises pre-response
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("User already exists") from exc   # admin-only: same tenant
        return user

    async def get(self, tenant_id: UUID, user_id: UUID) -> UserEntity:
        user = await self._repo.get_in_tenant(user_id, tenant_id)
        if user is None:                                 # missing and foreign: the same 404
            raise NotFoundError("User", str(user_id))
        return user

    async def update(self, tenant_id: UUID, user_id: UUID, data: UpdateMeRequest) -> UserEntity:
        user = await self.get(tenant_id, user_id)
        await self._repo.apply_changes(user, data.model_dump(exclude_unset=True))
        await self._session.commit()
        return user
```

`list_page(tenant_id, ...)` passes straight through to the repository.
