# SQLAlchemy Async: Sessions, Transactions, Pooling (canonical)

> One rule set for session and transaction ownership. Other references (`fastapi-templates.md`,
> `backend-service-patterns.md`, `python-advanced-patterns.md`) link here instead of restating it.
> Validated against SQLAlchemy 2.1.9 + asyncpg 0.32.0 + Alembic 1.20.1 on Python 3.14.10 and PostgreSQL 18.7, FastAPI 0.165.
> FastAPI behaviour below needs >= 0.118 (exit-after-response) and >= 0.121 (`scope="function"`).
> Install `sqlalchemy[asyncio]`: from 2.1 `greenlet` (needed by `sqlalchemy.ext.asyncio`) is only in that extra.

---

## 1. Ownership rule (the single source of truth)

| Layer | Opens session | Flushes | Commits / rolls back |
|-------|---------------|---------|----------------------|
| Dependency / worker entrypoint | Yes (`async with factory()`) | No | Never commits. Closing the session discards uncommitted work |
| Route handler | No | No | Never touches the session |
| Service / use case | No | When it needs a server-generated value | **Commits once, at the end of the unit of work.** Rolls back on a handled conflict |
| Repository | No | Yes (to surface constraint errors early) | Never |

Why the service commits: the client must see 2xx only after the commit succeeded. A commit in the
dependency teardown runs after the response (section 3).

---

## 2. Engine and session factory

One engine per application instance, built in the lifespan and stored on `app.state`. A module-level singleton ignores a second URL
(executed: `get_session_factory(a) is get_session_factory(b)`), which breaks tests that call `create_app(test_settings)`.

```python
# from fastapi import FastAPI, Request
# from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
# from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
def build_session_factory(url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        url, pool_size=5, max_overflow=5, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine, factory = build_session_factory(app.state.settings.database_url.get_secret_value())
    app.state.engine, app.state.session_factory = engine, factory
    try:
        yield
    finally:  # still runs if code after the engine exists raises
        # also close clients; see asyncio-concurrency-and-tasks.md section 6
        await engine.dispose()


def create_app(settings: Settings) -> FastAPI:  # tests pass their own settings: one engine per app
    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    return app
```

`database_url` is a `SecretStr` (`fastapi-architecture-and-config.md` section 2): pass `.get_secret_value()`, never the `SecretStr` (`ArgumentError: Expected string or URL object`). Executed: two apps with different URLs reached two different databases; both pools had 0 checked-out connections after shutdown; `mypy --strict` and ruff clean.
Workers and scripts call `build_session_factory(url)` themselves and `await engine.dispose()` in `finally`.

WRONG: `from app.db import SessionLocal` where `SessionLocal` is `None` until startup (freezes `None`), or
an undefined `AsyncSessionLocal` in examples. RIGHT: read the factory from `app.state` at use time (section 3).

---

## 3. Request dependency: no commit after `yield`

On FastAPI >= 0.118 the code after `yield` in a default (`scope="request"`) dependency runs AFTER the
response is sent. A commit there can fail while the client already received 200.

```python
# WRONG: the client sees 2xx before this commit runs (executed: handler, response sent, exit)
async def get_db() -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
        await session.commit()


# RIGHT: open, yield, close. Uncommitted work is rolled back when the context closes.
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
```

If a dependency must run teardown before the response, use `Depends(get_session, scope="function")`
(>= 0.121). Prefer the explicit service commit anyway: it makes the transaction boundary visible in the diff.
Exceptions raised after `yield` cannot change the response (docs: fastapi.tiangolo.com, "Dependencies with yield").

---

## 4. Service pattern

```python
class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: OrderCreate) -> Order:
        order = Order(**data.model_dump())
        self._session.add(order)
        await self._session.flush()                    # server_default PK is None until here
        self._session.add(AuditLog(entity_id=order.id, action="order_created"))
        await self._session.commit()                   # one commit; 2xx only after it succeeds
        return order
```

Rules:
- A server-generated id (`server_default`, identity) is `None` until `flush()`. Executed: `id before flush: None`.
  Or generate it client-side (`uuid.uuid4()`).
- Two tables linked only by a `ForeignKey` column (no `relationship()`) are NOT ordered by the unit of work:
  `flush()` the parent before adding the child, or declare the relationship.
- `async with session.begin():` only on a session that has not run a statement yet. On an autobegun session it
  raises `InvalidRequestError: A transaction is already begun`. Do not add `rollback()` inside `begin()`: it rolls back on error itself.
- Workers and scripts that own the whole unit: `async with factory() as session, session.begin(): ...` (commit on clean exit, rollback on exception).

---

## 5. One session per task

An `AsyncSession` is not safe for concurrent use. Never pass the request session to `asyncio.gather` branches,
`BackgroundTasks` or `spawn()`ed coroutines (it is closed when the request ends). Open a new session inside the task.
Executed on 2.1.9: three `asyncio.gather` branches on one session -> two raised `InvalidRequestError: This session is provisioning
a new connection; concurrent operations are not permitted`; closing the session while a branch still ran raised `IllegalStateChangeError`.
Five tasks, each with its own `async with factory() as session, session.begin():`, all succeeded.

```python
async def refresh_one(factory: async_sessionmaker[AsyncSession], account_id: uuid.UUID) -> None:
    async with factory() as session:          # own session, own transaction
        ...
        await session.commit()
```

Do not hold a session (a pool slot, often an open transaction) across a slow network call: compute first,
then open the session, write, commit. See `reliability-idempotency-retries-outbox.md` section 6.

---

## 6. Expiry and lazy-load traps (`MissingGreenlet`)

`expire_on_commit=False` protects the commit only. Executed results:

| Situation | Result | Fix |
|-----------|--------|-----|
| Read an attribute after `await session.rollback()` | `MissingGreenlet` (every instance is expired) | Capture ids/values BEFORE rollback, or re-select |
| Read a server-side `onupdate` column (e.g. `updated_at`) after an UPDATE commit | `MissingGreenlet` | `await session.refresh(obj, ["updated_at"])` |
| Read an unloaded relationship | `MissingGreenlet` / `InvalidRequestError` | `selectinload(...)`, `await obj.awaitable_attrs.rel` (needs `AsyncAttrs` on `Base`), or `lazy="raise"` |

```python
class Base(AsyncAttrs, DeclarativeBase): ...

# implicit lazy load now fails loudly
lines: Mapped[list["Line"]] = relationship(back_populates="order", lazy="raise")
orders = (await s.scalars(select(Order).options(selectinload(Order.lines)))).all()
```

Find hazards: `inspect(obj).unloaded` after commit/rollback lists what would trigger IO.

Typed constructors: with a plain `DeclarativeBase`, `mypy --strict` accepts `Order(quantity=str(x))` for a `Mapped[int]` column
(executed on 2.1.9: exit 0). `class Base(AsyncAttrs, MappedAsDataclass, DeclarativeBase)` makes it an `arg-type` error (exit 1);
mark PK/server-default columns `init=False` (`mapped_column(primary_key=True, server_default=func.uuidv7(), init=False)`).

---

## 7. Classify `IntegrityError` by constraint, not by type or message

asyncpg exposes the constraint name on `exc.orig.__cause__`, not on `exc.orig` (executed: `orig.constraint_name` absent,
`__cause__.constraint_name == "uq_orders_ref"`, SQLSTATE `23505` on both).

```python
from sqlalchemy.exc import IntegrityError

def violated_constraint(exc: IntegrityError) -> str | None:
    cause = getattr(exc.orig, "__cause__", None)
    return getattr(cause, "constraint_name", None)

try:
    await session.flush()
except IntegrityError as exc:
    await session.rollback()                      # the failed transaction is unusable until this
    if violated_constraint(exc) == "uq_users_email":
        raise ConflictError("email_taken") from None
    raise                                         # FK / NOT NULL / CHECK are not "already exists"
```

WRONG: map every `IntegrityError` to 409 "already exists" with no rollback and no log. For race arbitration
(return the winner instead of an error) see `reliability-idempotency-retries-outbox.md` section 1.
Name every constraint explicitly (naming convention in `MetaData`) so the string you compare is stable.

---

## 8. Pooling: size from a connection budget

```python
create_async_engine(
    url, pool_size=5, max_overflow=5, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800
)
```

| Parameter | Rule |
|-----------|------|
| Budget | `instances x (pool_size + max_overflow)`, summed over every service and worker, must stay under ~80% of `max_connections` minus a reserve for migrations/admin. Add a pooler when it does not |
| `pool_timeout` | Small (5-10 s). Exhaustion raises `sqlalchemy.exc.TimeoutError` (executed: after 0.5 s with `pool_timeout=0.5`); map it to 503 + `Retry-After`, do not queue requests for 30 s |
| `pool_pre_ping` | On. Cheap; survives server/proxy-closed idle connections |
| `pool_recycle` | Below any proxy/server idle limit |
| `(cores*2)+spindles` | Sizes server-side active connections, not an application pool. Do not use it for `pool_size` |

Behind a transaction-mode pooler (PgBouncer-style) prepared statements break. Options that execute against the
asyncpg dialect: `...&prepared_statement_cache_size=0` in the URL plus `connect_args={"statement_cache_size": 0}`,
or unique statement names (`connect_args={"prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__"}`) with
`NullPool` and `DISCARD` on return (SQLAlchemy asyncpg dialect docs). Not verified against a live pooler: test in staging.
Session-level state (`SET`, advisory locks, temp tables) is also unsafe there: see `reliability-idempotency-retries-outbox.md` section 2.

---

## 9. Raw SQL and upserts

- In `text()` write `CAST(:p AS uuid)`, never `:p::uuid`: the `:p::uuid` form loses the bind and fails with a syntax error (executed).
  Verify raw SQL by running it through the real session, not by EXPLAIN on a hand-substituted copy.
- `on_conflict_do_update` on a **partial** unique index needs `index_where=` written the same way as the index predicate
  (executed: no `index_where` -> "no unique or exclusion constraint matching"; `index_where=t.c.live` works, `.is_(True)` did not match a `WHERE live` index).
  The `set_` dict touches only the columns it names: `onupdate` defaults do NOT run (set `updated_at` yourself), omitted columns keep old values.
- Idempotent re-ingest: add `where=Model.content_hash.is_distinct_from(stmt.excluded.content_hash)` so an unchanged row is not rewritten
  (executed: the same upsert twice -> one row, `updated_at` unchanged; changed content -> updated in place; a plain `insert` twice -> `IntegrityError`).

---

## 10. SQLAlchemy 2.0 -> 2.1 changes that affect this toolkit

Source: SQLAlchemy "What's New in 2.1" (docs.sqlalchemy.org/en/21/changelog/migration_21.html). Rows marked *executed*
were run on 2.1.9 + PostgreSQL 18.7.

| Change | Impact | Do |
|--------|--------|----|
| `greenlet` no longer installed by default | `ImportError`/`ValueError` on first async call | Depend on `sqlalchemy[asyncio]==2.1.9` |
| Python >= 3.11 | Older runtimes cannot install 2.1 | Toolkit target is 3.14 |
| Autoflush runs before every execution, including `text()` / Core (*executed*: a pending `add()` was counted by `text("SELECT count(*) ...")`) | Raw SQL now sees pending ORM objects; a bad pending object raises at the `text()` call | Flush deliberately; do not rely on `text()` skipping the flush |
| `postgresql://` URLs default to psycopg 3, not psycopg2 | A driverless URL changes driver | Always name the driver: `postgresql+asyncpg://` (or `postgresql+psycopg://`) |
| `Computed(...)` without `persisted` renders VIRTUAL on PostgreSQL (*executed*: DDL had no `STORED`). PostgreSQL 18 makes VIRTUAL the default and rejects indexes on it (*executed*: `indexes on virtual generated columns are not supported`) | A generated `tsvector` with a GIN index (hybrid search) fails to migrate | `Computed("to_tsvector('english', content)", persisted=True)` for any indexed generated column |
| `func.uuidv7(monotonic=True)` as `server_default` (PostgreSQL 18 `uuidv7()`) | Batched ORM `INSERT ... RETURNING` (insertmanyvalues) can keep row order with server-generated ids (docs; *executed* here only as the `server_default` of a 20,000-row multi-VALUES upsert, not the RETURNING path) | Prefer it over client `uuid4()` for time-ordered keys on PG18 |
| `tstring(t"... {value}")` (Python 3.14 t-strings) | Interpolated values become bound parameters (*executed*: rendered `:param_1`) | Allowed for raw SQL; never use f-strings for values |
| `Select[int, str]` / `Row[int, str]` typing (PEP 646) replaces `Tuple[...]` | Drop `Row._t` workarounds; needs mypy >= 1.7 | - |
| Named types (`Enum`, `DOMAIN`) belong to `MetaData`, inherit its schema; `inherit_schema` deprecated | Enum DDL lands in `MetaData(schema=...)` | Set `Enum(..., schema=...)` explicitly when it differs |
| `execution_options=` on `Session` / `async_sessionmaker` | Options apply to flushes and eager loads too | Use for `schema_translate_map` per tenant schema instead of per-statement options |

---

## 11. Review checklist

- [ ] No `commit()` after `yield` in a dependency; routes do not touch the session
- [ ] Engine built in the lifespan (on `app.state`, `try/finally` dispose), pool sized from a documented budget
- [ ] No session shared across tasks; no session held across network calls
- [ ] Nothing reads attributes after `rollback()`; `onupdate` columns refreshed; relationships eager-loaded or `lazy="raise"`
- [ ] `IntegrityError` handled by constraint name, after `rollback()`
- [ ] `text()` uses `CAST(...)`; partial-index upserts set `index_where`
- [ ] `sqlalchemy[asyncio]` pinned; URLs name the driver; indexed `Computed` columns set `persisted=True`
