# FastAPI Architecture, Configuration and Lifecycle

Rules for how a FastAPI service is wired: settings, app factory, lifespan, dependency chain,
transaction ownership, route order, idempotent writes. Authentication lives in
`fastapi-auth-security.md` and `fastapi-authorization-boundaries.md`; errors in
`fastapi-error-handling.md`; engine/session internals in `sqlalchemy-async-sessions-and-transactions.md`.

> **Version note:** snippets were executed on Python 3.14, FastAPI 0.165, Pydantic 2.14,
> SQLAlchemy 2.1 and PostgreSQL 16. The only FastAPI feature newer than the 0.135 pin is
> `Depends(scope="function")` (0.121+, already inside the pin). Re-run against your lockfile.

---

## 1. Layering — who owns what

| Layer | Owns | Must not |
|-------|------|----------|
| Route (`api/routes/`) | HTTP shape, auth dependency, calling one service method | touch the session, build SQL, commit, catch domain errors |
| Service | business rules, **commit/rollback**, domain exceptions | raise `HTTPException`, import `fastapi` |
| Repository | queries, `flush()` | `commit()`, business rules |
| `core/` | settings, security primitives, handlers | import from routes |

Domain errors are typed exceptions (`fastapi-error-handling.md` §1). Only handlers and
dependencies raise `HTTPException`.

---

## 2. Settings — fail at startup, never on first request

```python
# src/my_service/core/config.py
from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str  # no default: "local" | "staging" | "production"
    database_url: SecretStr  # no default, no credentials in code
    redis_url: SecretStr  # no default
    jwt_secret: SecretStr = Field(min_length=32)  # no default
    cors_origins: list[str] = []  # empty = no browser origin allowed
    log_level: str = "INFO"  # operational default only


@lru_cache
def get_settings() -> Settings:
    try:
        # values come from the environment (mypy: see the plugin note below)
        return Settings()
    except ValidationError as exc:
        # Default error text echoes the offending INPUT (a secret): print field names only.
        fields = [".".join(map(str, e["loc"])) for e in exc.errors(include_input=False)]
        raise SystemExit(f"invalid configuration, fix these fields: {fields}") from None
```

| Rule | Why |
|------|-----|
| Required values have **no default**; secrets are `SecretStr` (+ `min_length`) | A template default (`"change-me"`, a DB URL with a password) gets copied into real services |
| Defaults only for non-secret values that are identical in every environment | `os.getenv("X") or "fallback"` hides a missing variable |
| `cors_origins` defaults to empty; origins come from config per environment | Dev origins never reach production; native clients are not CORS-gated |
| Never log `settings`, a URL or a DSN | Connection URLs carry credentials; log host-less names |
| `Settings()` is built once (`lru_cache`) and passed to `create_app` | Tests construct their own `Settings(_env_file=None, ...)` |

**mypy:** with `plugins = ["pydantic.mypy"]` under `[tool.mypy]` (the form shown everywhere in this
toolkit) `Settings()` and `Settings(_env_file=None, jwt_secret="...")` type-check with no ignore comment
(executed, `strict = true`). Without the plugin mypy reports `call-arg` and `arg-type` on both and needs
`# type: ignore[call-arg, arg-type]`; with the plugin that same comment becomes an `unused-ignore` error.

`list[str]` fields are read from the environment as JSON: `CORS_ORIGINS='["https://app.example.com"]'`.

### Boot contract test

A container that cannot build `Settings` dies before binding a port, and the cause is in no
application log. Test it from the names your deployment manifest injects:

```python
def test_boot_contract(tmp_path, monkeypatch):
    # your IaC/manifest export: env var names only
    for name in load_names_from_deploy_manifest():
        # placeholder values: only presence is under test
        monkeypatch.setenv(name, "x" * 40)
    # a local .env must not mask a missing variable
    monkeypatch.chdir(tmp_path)
    # raises if the manifest lacks a required field
    Settings()
```

Add the negative control (`monkeypatch.delenv("JWT_SECRET")` → `pytest.raises`) so the test proves it can fail.

---

## 3. App factory and lifespan

```python
# src/my_service/main.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI

# python-observability.md §1: one structlog setup for the whole service
logger = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cache = aioredis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
        try:
            # from_url() is lazy: only ping() makes a dead Redis visible
            await cache.ping()
            app.state.cache = cache
        # optional dependency: degrade loudly (required one: re-raise)
        except aioredis.RedisError as exc:
            logger.error("cache_unavailable", error_type=type(exc).__qualname__)
            await cache.aclose()
            app.state.cache = None
        try:
            yield
        finally:
            if app.state.cache is not None:
                try:
                    await app.state.cache.aclose()
                except aioredis.RedisError as exc:
                    logger.warning("cache_close_failed", error_type=type(exc).__qualname__)

    # App: request-id wrapper, python-observability.md §4
    app = App(title="my-service", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    register_exception_handlers(app)           # fastapi-error-handling.md §2
    app.include_router(api_router, prefix="/api/v1")
    return app
```

**Entrypoint:** no module-level `app = create_app()` in the factory module. Run
`uvicorn my_service.main:create_app --factory` (dev server, Dockerfile, CI). `Settings` fails fast, so a
module-level call runs at import time: a test that does `from my_service.main import create_app` with no
environment dies in collection with `SystemExit: invalid configuration` (executed: `INTERNALERROR`, no
tests ran). If something needs an ASGI object (a server that cannot use `--factory`), put
`app = create_app()` alone in a separate `asgi.py` that tests never import. Tests import `create_app`
and pass explicit settings.

| WRONG | RIGHT |
|-------|-------|
| `app.router.on_startup.append(...)`, `@app.on_event("startup")` beside `lifespan=` | Everything inside `lifespan`. With `lifespan=` set, startup/shutdown handlers are **never called** (verified: handler count 0), and `on_event` is deprecated |
| `try: from_url(...) except:` to detect an outage | `from_url()` never connects; call `ping()` |
| `print()` in lifespan | structured logger, error **type** only |
| `logger.info("redis", url=settings.redis_url)` | never log URLs/DSNs |
| module-level `redis = from_url(...)` | create in lifespan, hang on `app.state`, read via `request.app.state` |
| a factory accepting `on_startup` hooks and storing them | call them from inside `lifespan` |

Middleware order: the **last** `add_middleware` call is the outermost of the `add_middleware` stack, but even that sits INSIDE Starlette's `ServerErrorMiddleware`. The request-id wrapper must be outside everything (so the framework's 500 carries `X-Request-ID`): that is `App.__call__`, not `add_middleware` and not a `build_middleware_stack` override (`python-observability.md` §4). Comment which wraps which.

### Lazily created globals (engine, session factory, clients)

`from db import SessionLocal` freezes the import-time value (usually `None`) into the importer.
Export a getter and have tests patch the getter, never the raw global. Engine/session-factory
lifecycle details: `sqlalchemy-async-sessions-and-transactions.md`.

---

## 4. Dependency chain and transaction ownership

Compose one `Annotated` chain: session → repository(session) → service(repository, session).
No module-level service/repository singletons that take the session per call. Tests override with
`app.dependency_overrides`. Ruff `FAST002` flags non-`Annotated` `Depends`/`Query`.

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session                    # closing rolls back anything uncommitted; no commit here

SessionDep = Annotated[AsyncSession, Depends(get_session)]

class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> Order:
        self._session.add(order)
        await self._session.flush()      # repositories flush (to read generated ids), never commit
        return order

class OrderService:
    def __init__(self, repo: OrderRepository, session: AsyncSession) -> None:
        self._repo, self._session = repo, session

    async def create(self, data: OrderCreate) -> Order:
        order = await self._repo.add(Order(**data.model_dump()))
        await self._session.commit()     # a failed commit raises BEFORE any response byte
        return order

def get_repo(session: SessionDep) -> OrderRepository:
    return OrderRepository(session)

RepoDep = Annotated[OrderRepository, Depends(get_repo)]

def get_service(repo: RepoDep, session: SessionDep) -> OrderService:
    return OrderService(repo, session)

ServiceDep = Annotated[OrderService, Depends(get_service)]
```

**Commit after `yield` is a trap.** A dependency's exit code runs **after the response is sent**
(default `scope="request"`). Executed on a deferred foreign key that fails only at `COMMIT`:

| Where the commit lives | Client sees | Row stored |
|------------------------|-------------|------------|
| after `yield` in a default-scope dependency | **200** | no |
| after `yield` in `Depends(get_db, scope="function")` | 500 | no |
| in the service, before returning | 500 | no |

Default: the **service owns the commit**; the dependency opens, closes (and may roll back).
If a dependency must commit, declare `Annotated[AsyncSession, Depends(get_db, scope="function")]`
(FastAPI 0.121+). Reviewer rule: `yield session` followed by `commit()` in a default-scope
dependency = HIGH.

---

## 5. Route order, pagination bounds

A static route that is a sibling of a parameterised route must be **registered first**; with a
string parameter the static URL silently resolves to the by-id handler (with an `int` parameter
it answers 422). Lint it with a test, not by eye:

```python
from fastapi.routing import APIRoute

def shadowed_static_routes(app: FastAPI) -> list[str]:
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    problems: list[str] = []
    for i, earlier in enumerate(routes):
        if "{" not in earlier.path:
            continue
        for later in routes[i + 1:]:
            if "{" in later.path or not ((earlier.methods or set()) & (later.methods or set())):
                continue                     # compare method sets before calling it a defect
            if earlier.path_regex.match(later.path):
                problems.append(f"{later.path} is shadowed by {earlier.path}")
    return problems

def test_no_shadowed_routes():
    assert shadowed_static_routes(create_app(test_settings)) == []
```

Keep a positive control (a deliberately mis-ordered app returns a finding). List endpoints:
`page: int = Query(1, ge=1)`, `page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE)`, deterministic
`ORDER BY` with a unique tiebreak (see `rest-design-principles.md` Pagination).

---

## 6. Blocking work inside `async def`

A blocking SDK call or CPU-bound call stalls every request on that worker.

| Work | Do |
|------|----|
| Password hashing / verification | `await run_in_threadpool(hasher.hash, ...)` (`fastapi-auth-security.md` §2) |
| Blocking third-party SDK | one offload helper with a bounded pool; set the SDK's own socket timeout (cancelling the await cannot cancel the thread); read its default timeout, do not assume |
| Fire-and-forget task | keep a strong reference + done-callback (`backend-service-patterns.md` P6); load-bearing work goes through an outbox |

Pool sizing, `to_thread`, `TaskGroup` and cancellation: `asyncio-concurrency-and-tasks.md`.
Ruff `ASYNC210`/`ASYNC251` catch the obvious calls.

---

## 7. Idempotent and concurrent writes

**Idempotency must be atomic in the database.** "Read key, then write" lets two concurrent retries
both pass the check. One transaction: claim the key with `INSERT ... ON CONFLICT DO NOTHING
RETURNING`, do the write, store the response, commit. Outcomes (the recommended default, after the
IETF Idempotency-Key header draft; canonical text and its reasoning: `reliability-idempotency-retries-outbox.md` §1):

| Request | Result |
|---------|--------|
| same key, same fingerprint, first request committed | the STORED result with the original status (replay), never re-executed |
| same key, DIFFERENT fingerprint | `422` with code `idempotency_key_reused` (never the first result, never a re-execution) |
| same key while the first request is still in flight | `409` with `Retry-After` |

Executed on PostgreSQL: a replay returned the stored result, a different body under the same key raised
the reuse error, a key claimed by an uncommitted transaction raised the in-flight error, and 8 concurrent
first calls produced exactly one order. A rolled-back first attempt releases the key.

```python
async def create_order(
    session: AsyncSession, account_id: str, key: str, body: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Returns (response, replayed). Key row, write and stored response commit together."""
    request_hash = fingerprint(body)  # sha256 of canonical JSON
    # else the claim WAITS for an in-flight twin
    await session.execute(text("SET LOCAL lock_timeout = '500ms'"))
    try:
        claimed = await session.execute(
            # PK (account_id, key): keys are scoped to the caller
            pg_insert(IdempotencyKey)
            .values(account_id=account_id, key=key, request_hash=request_hash)
            .on_conflict_do_nothing(index_elements=["account_id", "key"])
            .returning(IdempotencyKey.key)
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != "55P03":  # lock_not_available
            raise
        await session.rollback()
        raise IdempotencyInFlightError(retry_after=1) from exc  # 409 + Retry-After
    if claimed.scalar_one_or_none() is None:  # someone else claimed it and has committed
        stored = (
            await session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.account_id == account_id, IdempotencyKey.key == key
                )
            )
        ).scalar_one()
        if stored.request_hash != request_hash:  # same key, different body
            raise IdempotencyKeyReusedError()  # 422, code idempotency_key_reused
        return stored.response, True  # replay the stored result, never re-execute
    order = Order(id=str(uuid.uuid4()), sku=body["sku"])
    session.add(order)
    response = {"order_id": order.id, "sku": order.sku}
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.account_id == account_id, IdempotencyKey.key == key)
        .values(response=response)
    )
    await session.commit()
    return response, False
```

Use one session per concurrent caller. Define both errors as `AppError` subclasses (codes
`idempotency_key_reused` -> 422, `idempotency_in_flight` -> 409 with a `Retry-After` header in the
handler). Add a TTL/cleanup job, and canonicalise any id embedded in a key (fail closed on parse failure). Redis may front this as
a cache but cannot be the only guard for a money or notification write. Retries, outbox and
exactly-once limits: `reliability-idempotency-retries-outbox.md`.

**Optimistic concurrency** for concurrent writers to one entity:

```python
result = await session.execute(
    update(Doc).where(Doc.id == doc_id, Doc.version == expected_version)
    .values(body=body, version=Doc.version + 1))
if result.rowcount != 1:                         # lost the race: fail loudly, never blind-retry
    raise StaleWriteError(f"doc {doc_id} changed since version {expected_version}")
await session.commit()
```

Executed with two concurrent writers: one wins, one raises. A high-impact write that loses must
escalate to a human or a reconciliation job.

---

## 8. Module boundaries

A module writes only the tables it owns; everything else goes through the owner's API. Enforce
with an architecture test whose allowlist can only shrink (each entry argues in writing why):

```python
def forbidden_imports(src: Path, package: str, forbidden: set[str]) -> list[str]:
    hits = []
    for path in (src / package).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            hits += [
                f"{path.name}: imports {n}"
                for n in names
                if any(n.startswith(f) for f in forbidden)
            ]
    return hits


assert forbidden_imports(Path("src"), "billing", {"orders.models"}) == []
```

Ship a positive control (a temp tree with a forbidden import is flagged) and a negative control
(an allowed import is not).

---

## 9. Ruff baseline

Configure under `[tool.ruff.lint]`; top-level `select` is deprecated (ruff warns).

```toml
[tool.ruff]
target-version = "py314"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF", "ASYNC", "FAST", "S", "BLE", "T20", "DTZ"]
ignore = ["SIM105"]      # it rewrites try/except/pass into contextlib.suppress, hiding the swallowed error

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]
```

Executed on a deliberately bad module: `FAST002`, `ASYNC210`, `ASYNC251`, `RUF006`, `T201`, `S110`,
`BLE001` all fired; `DTZ005` flags a naive `datetime.now()`. `S` is noisy in tests (hence the ignore). A clean ruff run does not prove
authorization, rate-limit scope or approval logic: those need review.

---

## Checklist

```
□ No required value has a default; secrets are SecretStr; boot-contract test exists with a negative control
□ create_app(settings); lifespan only (no on_startup/on_event); ping() for lazy clients; no URL logged
□ Dependencies are Annotated; service owns commit; repositories flush; no commit after yield in default scope
□ Static routes registered before parameterised siblings (test_no_shadowed_routes passes)
□ Blocking/CPU work offloaded; no bare create_task
□ Writes that must not repeat use UNIQUE key + ON CONFLICT in one transaction
□ ruff [tool.ruff.lint] baseline clean
```
