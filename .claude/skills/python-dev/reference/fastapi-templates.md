# FastAPI Templates, Code Patterns, and Project Configuration

Production-ready templates for Python 3.14 + FastAPI. The project template below was assembled and run (5 tests on
PostgreSQL 16, `mypy --strict` clean, ruff baseline clean) on FastAPI 0.165 / Pydantic 2.14 / SQLAlchemy 2.1; nothing in
it needs more than the 0.135 pin except `Depends(scope="function")` (0.121+). The pyproject pins SQLAlchemy 2.0.x (reason
there). Wiring rules: `fastapi-architecture-and-config.md`.

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
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = App(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    register_exception_handlers(app)        # error-handling §2; App: observability §4
    app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
    return app
```

No module-level `app = create_app()` (it runs `Settings()` at import and breaks test collection): run
`uvicorn my_service.main:create_app --factory`; tests call `create_app(test_settings)`
(`fastapi-architecture-and-config.md` §3).

## Pydantic Models Template

Request models forbid unknown keys (a typo or an injected `role` is a 422, not a silent no-op),
passwords are `SecretStr` with a max length, PATCH rejects explicit `null` for non-nullable fields.
Responses stay lenient. More: `.claude/skills/pydantic-models-py/SKILL.md`.

```python
# src/my_service/models/user.py
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator


class RequestModel(BaseModel):
    """Base for request bodies: unknown keys are errors, not silently dropped."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateUserRequest(RequestModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=128)


class UpdateUserRequest(RequestModel):
    """PATCH: omit a field to leave it unchanged; explicit null is rejected."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        nulls = sorted(f for f in self.model_fields_set if getattr(self, f) is None)
        if nulls:
            raise ValueError(f"fields cannot be null: {nulls}")
        return self


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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "My Service"             # operational default
    database_url: SecretStr                  # required, no default
    jwt_secret: SecretStr = Field(min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()      # values come from the environment; mypy plugin note: pyproject below
```

## Route Handler Template

Dependencies are `Annotated` aliases (`SessionDep`, `UserServiceDep`; ruff `FAST002`), list
parameters are bounded, routes never touch the session. Register static routes before
parameterised siblings (Pitfall 7).

```python
# src/my_service/api/deps.py
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session          # closing rolls back anything uncommitted; the SERVICE commits

SessionDep = Annotated[AsyncSession, Depends(get_session)]

def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session), session)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
```

```python
# src/my_service/api/routes/users.py
router = APIRouter()
MAX_PAGE_SIZE = 100

@router.get("/", response_model=list[UserResponse])
async def list_users(
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> list[UserResponse]:
    users = await service.list_page(limit=page_size, offset=(page - 1) * page_size)
    return [UserResponse.model_validate(u) for u in users]

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(body: CreateUserRequest, service: UserServiceDep) -> UserResponse:
    return UserResponse.model_validate(await service.create(body))

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, body: UpdateUserRequest, svc: UserServiceDep) -> UserResponse:
    return UserResponse.model_validate(await svc.update(user_id, body))
```

## SQLAlchemy Async Model

```python
# src/my_service/models/db/user.py
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserEntity(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # A Python-callable onupdate stays readable after the UPDATE. A SERVER-side
    # onupdate=func.now() is expired afterwards: reading it in async code raises
    # MissingGreenlet until you `await session.refresh(obj, ["updated_at"])`.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
```

## Pytest Template

`httpx.ASGITransport` does not run the lifespan: wrap the app in `app.router.lifespan_context(app)`.
Use `create_app(Settings(_env_file=None, ...))` so each test builds an isolated app. Database
fixtures and real-PostgreSQL patterns: `.claude/skills/python-testing-patterns/`.

```python
# tests/test_users.py
@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, database_url=DB_URL, jwt_secret="j" * 32)
    app = create_app(settings)
    async with app.router.lifespan_context(app):            # ASGITransport does not run lifespan
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_create_user(client: AsyncClient) -> None:
    body = {"email": "john@example.com", "name": "John", "password": "p" * 12}
    resp = await client.post("/api/v1/users/", json=body)
    assert resp.status_code == 201
    assert resp.json()["email"] == "john@example.com" and "password" not in resp.json()


async def test_unknown_field_is_rejected(client: AsyncClient) -> None:
    body = {"email": "a@example.com", "name": "T", "password": "p" * 12, "role": "admin"}
    assert (await client.post("/api/v1/users/", json=body)).status_code == 422


async def test_patch_null_is_422_and_duplicate_is_409(client: AsyncClient) -> None:
    body = {"email": "d@example.com", "name": "D", "password": "p" * 12}
    created = await client.post("/api/v1/users/", json=body)
    assert (await client.post("/api/v1/users/", json=body)).status_code == 409
    patched = await client.patch(f"/api/v1/users/{created.json()['id']}", json={"name": None})
    assert patched.status_code == 422
```

## pyproject.toml Template

Pin exact versions and commit `uv.lock`. The versions below are the ones the guides were executed
with (the repository's FastAPI pin is 0.135.x: use it, then re-run the tests); regenerate with `uv lock`.
A floor (`>=`) drifted once to a release that broke an instrumentation package and made `/health` fail.

```toml
[project]
name = "my-service"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi==0.165.0",
    "uvicorn[standard]==0.54.0",
    "pydantic[email]==2.14.4",      # EmailStr needs the email extra
    "pydantic-settings==2.16.3",
    "sqlalchemy[asyncio]==2.0.58",  # OpenTelemetry's SQLAlchemy instrumentation supports < 2.1: keep the span test
    "asyncpg==0.32.0",
    "alembic==1.20.1",
    "pyjwt==2.15.1",
    "pwdlib[argon2]==0.4.2",
    "structlog==26.1.0",            # python-observability.md: JSON logs
    "tenacity==9.2.1",              # fastapi-error-handling.md: transient-only retry
]

[dependency-groups]
dev = [
    "pytest==9.2.0",
    "pytest-asyncio==1.5.0",
    "httpx==0.28.1",
    "ruff==0.17.6",
    "mypy==2.4.1",
    "pytest-timeout==2.4.0",        # the testing guide sets `timeout = 30`
    "asgi-lifespan==2.1.0",
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
asyncio_default_fixture_loop_scope = "session"    # the session-scoped `engine` fixture needs both
asyncio_default_test_loop_scope = "session"       # (else: `AssertionError` in fixture setup, every test errors)
pythonpath = ["src"]
testpaths = ["tests"]
```

Top-level `select` under `[tool.ruff]` is deprecated: keep rules under `[tool.ruff.lint]`.
`S` is noisy in tests (hence the ignores). Dependency audit commands: `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md`.

## Docker Template

Non-root, lockfile-exact install. The canonical digest-pinned multi-stage Dockerfile and scans:
`.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md` §8 and `.claude/skills/docker/`.
The `uv sync --locked` / `--factory` steps ran locally; the image itself was not built.

```dockerfile
# Pin by digest in production: docker buildx imagetools inspect python:3.14.3-slim
FROM python:3.14.3-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/

WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ ./src/
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
CMD ["uvicorn", "--factory", "my_service.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

Never `pip install uv` in an image (unpinned, unverified): copy the pinned binary as above.
`uv sync --locked` fails if `uv.lock` is out of date (a dependency change is not done until the lock
is regenerated). `--factory` makes uvicorn call `create_app()` instead of importing a module-level `app`.
Dockerfile comments go on their own line: a trailing `# ...` after an `ENV` is parsed as more words.

## Common Commands

```bash
uv run uvicorn --factory my_service.main:create_app --reload --port 8000   # dev server
uv run pytest -v                                                           # tests
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/    # lint + format check
uv run mypy src/                                                           # types
uv run alembic revision --autogenerate -m "create users table"             # migrations: see alembic-migration-safety.md
uv run alembic upgrade head
```

## Common Pitfalls & Anti-Patterns

### Pitfall 1: Calling asyncio.run() Inside an Async Context

`asyncio.run()` creates a new event loop and is designed as a top-level entry point. Calling it from inside an `async def` function — including a FastAPI route handler, a dependency, or an async test — raises `RuntimeError: asyncio.run() cannot be called from a running event loop` because an event loop is already running. This is the single most common mistake when transitioning from synchronous to async Python.

```python
# ❌ BAD — raises RuntimeError inside FastAPI route
@router.get("/items/{item_id}")
async def get_item(item_id: int) -> ItemResponse:
    # asyncio.run() cannot be called from a running event loop
    result = asyncio.run(fetch_item(item_id))
    return result
```

```python
# ✅ GOOD — await coroutines directly inside async functions
@router.get("/items/{item_id}")
async def get_item(item_id: int) -> ItemResponse:
    result = await fetch_item(item_id)
    return result

# ✅ GOOD — asyncio.run() is only valid at the top-level entry point
if __name__ == "__main__":
    asyncio.run(main())
```

---

### Pitfall 2: Mixing Sync and Async Route Handlers Incorrectly

FastAPI runs a `def` handler in a thread pool (one thread per request; the pool can be exhausted).
An `async def` handler that calls blocking I/O (`requests`, `time.sleep`, a blocking third-party SDK,
CPU-bound hashing) blocks the event loop and stalls **every** request on that worker.

```python
# ❌ BAD — async def calling blocking I/O blocks the entire event loop
@router.get("/data")
async def get_data() -> dict:
    response = requests.get("https://api.example.com/data")  # blocks event loop
    time.sleep(1)                                             # blocks event loop
    return response.json()
```

```python
# ✅ GOOD — async def with non-blocking async I/O
@router.get("/data")
async def get_data() -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get("https://api.example.com/data")
    return response.json()

# ✅ GOOD — blocking or CPU-bound work off the loop (hashing: await run_in_threadpool(...))
digest = await run_in_threadpool(hasher.hash, plain)
```

Blocking third-party SDKs go through one offload helper with a bounded pool, and the SDK's own
socket timeout must be set: cancelling the awaiting task cannot cancel the thread.
Details: `asyncio-concurrency-and-tasks.md`. Ruff `ASYNC210`/`ASYNC251` flag the obvious calls.

---

### Pitfall 3: SQLAlchemy Async Session Misuse

Creating an `AsyncSession` inside a route gives several sessions per request, broken transaction
boundaries and leaks. A repository that commits prevents the caller from composing operations
atomically. A **dependency that commits after `yield` runs after the response is sent**: a failed
commit still returns 200 (executed on a deferred foreign key: 200 and no row; with
`scope="function"` or a service-owned commit: 500 and no row).

```python
# ❌ BAD — session created manually inside the route
@router.post("/users")
async def create_user(request: CreateUserRequest) -> UserResponse:
    async with AsyncSession(engine) as session:
        user = await user_repo.create(session, request)
        await session.commit()
    return user

# ❌ BAD — commit after yield in a default-scope dependency (client sees 200 even if commit fails)
async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.commit()

# ❌ BAD — repository commits its own transaction
class UserRepository:
    async def add(self, user: UserEntity) -> UserEntity:
        self._session.add(user)
        await self._session.commit()
        return user
```

```python
# ✅ GOOD — dependency opens/closes; the service owns the commit; repositories flush
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

---

### Pitfall 4: Missing await on Async Coroutines

Calling an `async def` function without `await` does not execute it — it returns a coroutine object. No exception is raised at the call site; the call silently does nothing. This is especially dangerous for database writes. Note that `session.add()` is a sync method (no `await`), while `session.commit()`, `session.flush()`, and `session.execute()` are async and must be awaited.

```python
# ❌ BAD — coroutine is created but never executed (silent no-op)
@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, session: SessionDep) -> None:
    user_service.delete(user_id, session)   # missing await; delete never runs

# ❌ BAD — awaiting a sync method raises TypeError
async def save(session: AsyncSession, user: UserEntity) -> None:
    await session.add(user)    # TypeError: add() is not a coroutine
    await session.commit()
```

```python
# ✅ GOOD — await all async calls; do NOT await sync calls
@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, session: SessionDep) -> None:
    await user_service.delete(user_id, session)   # awaited correctly

async def save(session: AsyncSession, user: UserEntity) -> None:
    session.add(user)          # sync — no await
    await session.commit()     # async — must await

# mypy: `unused-coroutine` (executed); pytest warns "coroutine ... was never awaited"
```

---

### Pitfall 5: Passing ORM Objects to Background Tasks

`BackgroundTasks.add_task()` schedules work to run after the HTTP response is sent. By that point, the request's database session has been closed and any ORM objects bound to it are in a detached state. Accessing lazy-loaded attributes or attempting to use them in queries raises `sqlalchemy.exc.DetachedInstanceError`.

```python
# ❌ BAD — user object is detached by the time background task runs
@router.post("/users", status_code=201)
async def create_user(
    request: CreateUserRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> UserResponse:
    user = await user_service.create(session, request)
    background_tasks.add_task(send_welcome_email, user)  # session closed before task runs
    return UserResponse.model_validate(user)

async def send_welcome_email(user: UserEntity) -> None:
    # DetachedInstanceError: accessing user.email after session closed
    await email_client.send(to=user.email, subject="Welcome")
```

```python
# ✅ GOOD — pass only primitive values (IDs, strings) to background tasks
@router.post("/users", status_code=201)
async def create_user(
    request: CreateUserRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> UserResponse:
    user = await user_service.create(session, request)
    background_tasks.add_task(send_welcome_email, str(user.id), user.email)
    return UserResponse.model_validate(user)

async def send_welcome_email(user_id: str, email: str) -> None:
    # Only primitives — no ORM session dependency
    await email_client.send(to=email, subject="Welcome")
```

---

### Pitfall 6: Mutating Pydantic v2 Models Directly

Pydantic v2 models are immutable by default when `model_config = ConfigDict(frozen=True)` is set — direct attribute assignment raises `ValidationError`. Even without `frozen=True`, direct mutation bypasses validators and is considered bad practice. Pydantic v2 replaced the v1 `.copy(update=...)` method with `.model_copy(update=...)`.

```python
# ❌ BAD — direct mutation raises ValidationError on frozen models
class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    email: str
    name: str

user = UserResponse(id=uuid4(), email="old@example.com", name="Alice")
user.email = "new@example.com"   # raises: ValidationError (frozen_instance)

# ❌ BAD — using deprecated Pydantic v1 .copy() method
updated = user.copy(update={"email": "new@example.com"})  # deprecated in v2
```

```python
# ✅ GOOD — use model_copy(update={...}) for Pydantic v2 immutable mutations
class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    email: str
    name: str

user = UserResponse(id=uuid4(), email="old@example.com", name="Alice")
updated = user.model_copy(update={"email": "new@example.com"})
# user is unchanged; updated has the new email
```

---

### Pitfall 7: Static Route Shadowed by a Parameterised Sibling

Routes match in registration order. With `GET /items/{item_id}` registered first, `GET /items/discovery`
is handled by the by-id route (422 for an `int` id, a wrong lookup for a `str` id). Register static
routes first, compare HTTP method sets before calling it a defect, and keep a test that walks
`app.routes` (`fastapi-architecture-and-config.md` §5).

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

    async def get(self, user_id: UUID) -> UserEntity | None:
        return await self._session.get(UserEntity, user_id)

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self._session.execute(select(UserEntity).where(UserEntity.email == email))
        return result.scalar_one_or_none()   # not `session.scalar()`: Any -> mypy no-any-return

    async def list_page(self, *, limit: int, offset: int) -> list[UserEntity]:
        order = (UserEntity.created_at, UserEntity.id)   # unique tiebreak
        stmt = select(UserEntity).order_by(*order).limit(limit).offset(offset)
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
Patch only an allowlist of fields (`model_dump(exclude_unset=True)` of a model that already
forbids unknown keys); hash passwords with `await hash_password(...)` (thread pool).

```python
# src/my_service/services/user_service.py
class UserService:
    """Business rules and the commit. Raises domain errors, never HTTPException."""

    def __init__(self, repo: UserRepository, session: AsyncSession) -> None:
        self._repo, self._session = repo, session

    async def create(self, data: CreateUserRequest) -> UserEntity:
        if await self._repo.get_by_email(data.email):
            raise ConflictError("User already exists")   # sign-up maps this to a uniform response
        user = await self._repo.add(UserEntity(
            email=data.email, name=data.name,
            hashed_password=await hash_password(data.password.get_secret_value()),
        ))
        await self._session.commit()                     # a failed commit raises pre-response
        return user

    async def update(self, user_id: UUID, data: UpdateUserRequest) -> UserEntity:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User", str(user_id))
        await self._repo.apply_changes(user, data.model_dump(exclude_unset=True))
        await self._session.commit()
        return user
```

The get-then-add duplicate check is a convenience, not a guarantee: two concurrent requests both
pass it. The unique constraint is the guard; map its `IntegrityError` to `ConflictError`
(`sqlalchemy-async-sessions-and-transactions.md`).

---

## Authentication Dependency Patterns

Use `Annotated` aliases: optional auth for endpoints that serve anonymous and signed-in callers,
required auth (401) on everything protected. Authorization of the object itself is a separate
step: `fastapi-authorization-boundaries.md`.

```python
CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]   # None: no token
CurrentUser = Annotated[User, Depends(get_current_user)]                          # 401: no token

@router.get("/items", response_model=list[ItemResponse])
async def list_items(user: CurrentUserOptional) -> list[ItemResponse]:
    """Public items for anonymous callers; adds the caller's own items when signed in."""
    ...

@router.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(body: ItemCreate, user: CurrentUser, service: ItemServiceDep) -> ItemResponse:
    return await service.create(body, owner_id=user.id)     # actor id: token, never the body
```
