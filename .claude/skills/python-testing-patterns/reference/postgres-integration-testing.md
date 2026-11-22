# PostgreSQL Integration Testing (async SQLAlchemy + FastAPI)

Rules and fixtures for tests that touch the database. Every snippet here was executed with Python 3.14, pytest 9.2, pytest-asyncio 1.5, SQLAlchemy 2.0.58/2.1.9, asyncpg 0.32, httpx 0.28, asgi-lifespan 2.1 against PostgreSQL 16. The route examples use FastAPI features present in 0.135; nothing here needs a newer FastAPI.

## 1. Rules

| Rule | Why |
|------|-----|
| Behaviour that depends on the database (unique/FK/check constraints, JSONB, server defaults, `ON CONFLICT`, savepoints, casts) is tested on real PostgreSQL | SQLite accepts SQL PostgreSQL rejects and ignores constraints you rely on |
| SQLite (or no DB at all) is acceptable only for pure-logic tests that never build an ORM session | An "in-memory DB" test of ORM code proves SQLite, not your schema |
| One outer transaction per test, rolled back at teardown (section 3) | Fast, no cleanup code, nothing leaks between tests |
| The outer-transaction fixture CANNOT prove a commit boundary or a cross-connection race (section 5) | Two sessions on one connection see each other's uncommitted rows |
| Missing database = skip locally, FAIL in CI via `REQUIRE_DB_TESTS=1` (section 2) | An all-skipped run exits 0; a green CI that executed nothing is the worst outcome |
| Never assert "the mechanism is wired"; assert the outcome | See section 8 |

## 2. pytest configuration and the skip-vs-fail fixture

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"                        # no @pytest.mark.asyncio / pytest_asyncio.fixture needed for plain coroutines
asyncio_default_fixture_loop_scope = "session"   # set EXPLICITLY: unset emits PytestDeprecationWarning
asyncio_default_test_loop_scope = "session"      # tests share the loop of session-scoped fixtures (engine)
timeout = 30                                 # pytest-timeout: per-test cap; override per test, never raise the floor
testpaths = ["tests"]
addopts = ["--strict-markers", "-ra"]        # -ra prints skip reasons; keep --cov OUT of addopts (run it in the gate)
markers = ["integration: needs a real PostgreSQL"]
```

- Pick ONE mode. `auto` removes the need for `@pytest.mark.asyncio` and `@pytest_asyncio.fixture`; `strict` needs both. Do not mix decorators with `auto` by habit.
- REQUIREMENT: the session-scoped `engine` fixture below only works when `asyncio_default_fixture_loop_scope` AND `asyncio_default_test_loop_scope` are both `"session"` (the scaffold `pyproject.toml` uses these values). Otherwise the engine's connections live on one loop and each test runs on another. Executed with the test scope left at `function`: the first DB test failed with `RuntimeError: Task ... got Future ... attached to a different loop`; with a function-scoped FIXTURE loop the validation app saw bare `AssertionError`s from pytest-asyncio setup (`1 passed, 28 errors`). If you need function-scoped loops, make the engine function-scoped or create it per test.
- Valid scopes: `function`, `class`, `module`, `package`, `session`, and `fixture-scope` (keeps the pre-default behaviour). Verified: leaving the option unset prints the deprecation warning.

```python
# tests/conftest.py
import os
from collections.abc import AsyncIterator
from typing import NoReturn

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db import Base

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REQUIRE_DB = os.environ.get("REQUIRE_DB_TESTS") == "1"


def unavailable(reason: str) -> NoReturn:
    if REQUIRE_DB:
        pytest.fail(reason)                   # CI: absence is a FAILURE
    pytest.skip(reason)                       # local: actionable skip


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    if not TEST_DATABASE_URL:
        unavailable("TEST_DATABASE_URL not set: start the test database and export it")
    eng = create_async_engine(TEST_DATABASE_URL)
    try:
        async with eng.begin() as conn:       # probe the ACTUAL dependency, not /health
            await conn.execute(text("SELECT 1"))
    # refused / DNS / socket / wrong name or role
    except (OSError, DBAPIError, asyncpg.PostgresError) as exc:
        await eng.dispose()
        unavailable(f"database unreachable ({type(exc).__name__}); start it, then re-run")
    async with eng.begin() as conn:
        # or `alembic upgrade head` (see migration skill)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()
```

Executed controls on an 11-test example suite: no env var -> 7 skipped, exit 0; with `REQUIRE_DB_TESTS=1` -> 7 errors, exit 1; unreachable host -> same two outcomes. A wrong database NAME or role is not an `OSError`: it surfaces as `sqlalchemy.exc.DBAPIError` (SQLAlchemy 2.1.9) or as the raw `asyncpg.InvalidCatalogNameError` (SQLAlchemy 2.0.58, executed), hence the three-way `except`; with only `OSError` the run showed `1 passed, 15 errors` instead of a skip. Executed on both versions: wrong name, `REQUIRE_DB_TESTS` unset -> skipped; set -> error; missing socket directory -> skipped. `unavailable()` is annotated `-> NoReturn` (`pytest.fail`/`pytest.skip` both raise), so `mypy --strict` narrows `TEST_DATABASE_URL` to `str`; `asyncpg` ships no type stubs: add `[[tool.mypy.overrides]] module = ["asyncpg", "asyncpg.*"] ignore_missing_imports = true`.

Prefer running migrations to build the test schema when the suite is meant to prove migrations; `create_all` is faster but cannot catch a model/migration mismatch (use a separate drift check, see `alembic-migration-safety.md`).

## 3. Outer transaction + SAVEPOINT session

```python
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker


@pytest_asyncio.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()            # nothing the test did survives, even commit()


@pytest_asyncio.fixture
async def session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as s:
        yield s                               # session.commit() only RELEASEs a SAVEPOINT
```

`join_transaction_mode="create_savepoint"` is what makes application code that calls `commit()`/`rollback()` safe inside the test (SQLAlchemy docs: "Joining a Session into an External Transaction"). Executed: a route that commits, followed by a test asserting the row is gone, both pass; the parametrized pair below runs the same assertion twice, which is the leak check.

```python
# identical assertion twice: proves no rows leaked between tests
@pytest.mark.parametrize("run", [1, 2])
async def test_commit_is_rolled_back(session, run):
    assert await count(session) == 0
    session.add(Account(email=f"a{run}@example.com"))
    await session.commit()
    assert await count(session) == 1
```

Also verify at the end of a CI run that the tables are empty (or the schema dropped): row counts identical across two consecutive runs is the isolation proof.

## 4. HTTP client: dependency override AND lifespan

`httpx.ASGITransport` does NOT run ASGI lifespan. State created in `lifespan` (pools, redis, health checker) is missing in a bare `AsyncClient`. Wrap with `asgi_lifespan.LifespanManager` (or use `with TestClient(app)`, which does run it). Executed: with `LifespanManager` the lifespan body ran (engine built on `app.state`, route served, engine disposed: 0 checked-out connections afterwards). Build the app per test with `create_app(test_settings)` (`sqlalchemy-async-sessions-and-transactions.md` section 2): no module-level app or engine to reset.

```python
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings


@pytest.fixture
def test_settings() -> Settings:                  # explicit settings: never the developer's .env
    url = os.environ["TEST_DATABASE_URL"]
    return Settings(_env_file=None, database_url=url, jwt_secret="j" * 32)


@pytest_asyncio.fixture
async def client(session: AsyncSession, test_settings: Settings) -> AsyncIterator[AsyncClient]:
    from app.api.deps import get_session
    from app.main import create_app

    # explicit settings; `main.py` has no module-level `app`
    app = create_app(test_settings)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield session                         # route commit() releases the SAVEPOINT

    app.dependency_overrides[get_session] = override_db
    try:
        async with LifespanManager(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                yield c
    finally:
        # defensive: the app is per-test, but a shared one would leak this into the NEXT test
        app.dependency_overrides.clear()
```

- Override the dependency callable object itself (`app.dependency_overrides[get_session]`), not its name.
- `client` depends on `session`: the route and the test assertions share one connection, so test code can read what the route wrote.
- If the lifespan opens its own pool you still override the dependency, so request handling uses the test session while the lifespan state (redis, checkers) exists.

## 5. Commit boundaries and races need real connections

Control (executed, passes): two sessions bound to ONE connection see each other's uncommitted rows, so a test using the section 3 fixture passes even if you delete the `commit()` from the code under test.

```python
async def test_outer_transaction_fixture_cannot_see_a_missing_commit(connection):
    maker = async_sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    async with maker() as writer, maker() as reader:
        writer.add(Account(email="never-committed@example.com"))
        await writer.flush()                  # no commit
        seen = (await reader.execute(select(func.count()).select_from(Account))).scalar_one()
    assert seen == 1                          # a second REAL connection would see 0
```

For a commit boundary or a concurrency race use the `engine` directly with one session (own connection) per task, a `asyncio.Barrier` to line the tasks up (no `sleep`), and clean up by a key fixed BEFORE the run:

```python
# fixed up front: cleanup deletes only rows with this key
EMAIL = "race@example.com"


async def test_concurrent_inserts_exactly_one_wins(engine: AsyncEngine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    barrier = asyncio.Barrier(2)

    async def attempt() -> str:
        async with maker() as s:              # AsyncSession per task, never shared
            s.add(Account(email=EMAIL))
            await barrier.wait()              # both reach the INSERT together
            try:
                await s.commit()
            except IntegrityError:
                await s.rollback()
                return "conflict"
            return "created"

    try:
        results = await asyncio.gather(attempt(), attempt())
        assert sorted(results) == ["conflict", "created"]
        async with maker() as s:
            n = (await s.execute(select(func.count()).where(Account.email == EMAIL))).scalar_one()
        assert n == 1
    finally:
        async with maker() as s:
            await s.execute(delete(Account).where(Account.email == EMAIL))
            await s.commit()
```

Add a remove-the-guard control: drop the unique constraint (or the lock) in a scratch run and confirm the test FAILS. Executed: with `unique=True` removed, the result was `['created', 'created']` and the test failed. A race test that cannot fail is decoration. An `asyncio.Barrier` starts the tasks together; it does not guarantee interleaving inside the database. Concurrency design lives in `asyncio-concurrency-and-tasks.md`.

## 6. Singletons, environment and global state

```python
@pytest.fixture(autouse=True)
def _isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # restored at teardown, even if a test raises
    monkeypatch.delenv("DATABASE_URL", raising=False)
```

- Prefer an engine built per app in the lifespan over a module-level engine (`sqlalchemy-async-sessions-and-transactions.md` section 2): there is then nothing global to reset. If a legacy module-level singleton exists, `monkeypatch.setattr` it per test; never assign it bare in `setup_method`, because a leaked mock cached for the whole process turns into unrelated failures far from the cause.
- `os.environ.setdefault(...)` in `conftest.py` is a silent no-op if a plugin or `.env` loader already exported the key. Objects built at import time (rate limiters, clients) then bind the wrong host. Swap storage per test with `monkeypatch.setenv`/`setattr`.
- Run one pytest process per deployable package in a monorepo so one package's conftest environment cannot leak into another's tests; pass the root config explicitly (`-c pyproject.toml`) so `rootdir` does not drift.

## 7. Deterministic tests

| Source of flakiness | Fix (executed unless noted) |
|---------------------|-----------------------------|
| Wall clock | Inject a `clock: Callable[[], datetime]`, or freeze with `time_machine.travel(dt.datetime(2026, 1, 1, tzinfo=dt.UTC), tick=False)` |
| Random / generated ids | Inject an id factory (`itertools.count`); assert on the injected value, never on a pattern |
| Row order | Add an explicit `ORDER BY`; asserting on unordered `SELECT` is a latent flake |
| `sleep()` to "wait for" work | Poll a condition with a deadline, or await the task; a sleep is both slow and still racy |
| Network | Block sockets in non-integration tests (below) |
| Shared state | Function-scoped fixtures; no test reads what another wrote |

```python
@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("integration"):
        return                                # integration tests may reach the test database
    def refuse(self: socket.socket, address: object) -> None:
        raise RuntimeError(f"unit test attempted a network connection to {address!r}")
    monkeypatch.setattr(socket.socket, "connect", refuse)
```

Executed: an unmarked test calling `socket.create_connection` raises the `RuntimeError`; a test marked `integration` reaches the OS (connection refused). Also neutralise cloud SDK clients session-wide in an autouse fixture that is import-safe (`importlib.util.find_spec("google.cloud...")` first): a real client created against an unresolvable host can hang an entire run; `pytest-timeout` is the backstop.

## 8. Assert outcomes, not wiring

- An idempotent replay test asserts ONE side effect and the SAME status/body as the original, not that a "seen" flag was set.
- A request that is "accepted, flagged" asserts the 2xx and the resulting state, not only the flag.
- A test of a concurrency guard asserts the final state after the race (section 5), not that the lock call was made.
- Mock fidelity: use `create_autospec`/`spec_set`; an unset `MagicMock` attribute can coerce into a plausible number inside a Pydantic response. A pinned `side_effect=[...]` list breaks whenever someone adds a query: grep tests after adding one.
- `mock.patch("pkg.mod.symbol")` patches a string path: assert the positive case (patched thing was awaited once) or inject the dependency; otherwise a reload can leave you patching a module nobody calls.

## 9. Gate: proof that tests actually ran

pytest exits 0 when every test is skipped (executed: 3 collected, 3 skipped, `pytest` exit 0). A CI step must therefore assert an executed count and capture pytest's OWN exit code.

```python
# scripts/check_executed.py
"""Gate: tests really ran. usage: check_executed.py junit.xml [max_skipped]"""

import sys
import xml.etree.ElementTree as ET

OK, FAIL, USAGE = 0, 1, 2


def main(argv: list[str]) -> int:
    if len(argv) < USAGE:
        return USAGE
    root = ET.parse(argv[1]).getroot()  # noqa: S314 - our own pytest output
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        sys.stderr.write("no <testsuite> element in the junit file\n")
        return USAGE
    tests, skipped = int(suite.get("tests", "0")), int(suite.get("skipped", "0"))
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    executed = tests - skipped
    sys.stdout.write(f"collected={tests} skipped={skipped} failed={failed} executed={executed}\n")
    max_skipped = int(argv[2]) if len(argv) > USAGE else tests
    return OK if executed > 0 and failed == 0 and skipped <= max_skipped else FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

```bash
export REQUIRE_DB_TESTS=1
uv run pytest -q --junitxml=junit.xml > pytest.log 2>&1; echo "PYTEST EXIT:$?"; tail -20 pytest.log
uv run python scripts/check_executed.py junit.xml 0; echo "EXECUTED GATE EXIT:$?"
```

Positive controls (executed): all 11 ran, `max_skipped=0` -> exit 0; 7 skipped, `max_skipped=0` -> exit 1; a 3-test file where all 3 skip -> exit 1; no argument -> exit 2. The script passes `mypy --strict` and ruff with the toolkit baseline.

xfail trap (executed): pytest's junit file counts an `xfail` as `skipped`. A suite with 1 passed + 1 strict xfail reports `collected=2 skipped=1 executed=1`, so `max_skipped=0` exits 1 for ANY suite with an xfail. Set `max_skipped` to the number of reviewed, intentional `skip`/`xfail` markers (keep that number in the CI step, next to a tracked reason per marker), never to a large value that would also admit a database-less run: with `REQUIRE_DB_TESTS=1` the DB tests error rather than skip, so a small `max_skipped` still catches them.

## 10. Flaky tests

First failure: capture the artifact (log, junit, seed), rerun THAT test once, record it. Never rerun until green. A quarantine lane needs an owner, a root-cause tag, a re-entry criterion (for example 20 consecutive passes) and a maximum duration after which the test is fixed or deleted. Never add a `flaky` marker to hide deterministic logic. Do not re-run unchanged gates; freeze the code before expensive ones.

## 11. Static "architecture tests" in pytest

Cheap invariants (Dockerfile installs from the lock, workflows pin actions by SHA, deployed entrypoints call the logging config) can live as pytest tests that read files. Rules: state the limit in the docstring (a text check proves presence, not behaviour); add a guard test that the inspected file exists (a deleted file must not pass vacuously); derive lists from the real source (AST or glob) instead of hand-copied lists that go stale; give each a known-bad fixture that must be flagged. See `skills/deployment-ci-cd/reference/python-ci-supply-chain.md` for the CI side.
