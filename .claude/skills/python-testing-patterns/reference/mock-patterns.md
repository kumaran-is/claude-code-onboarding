# Mock Patterns — Python 3.14 / pytest / unittest.mock

Applies to: Python 3.14, pytest, unittest.mock (stdlib). Stack: FastAPI + SQLAlchemy async.

---

## Section 1 — `autospec=True` — enforce method signatures on mocks

```python
from unittest.mock import create_autospec, MagicMock, patch
import pytest

class UserService:
    def get_user(self, user_id: int, include_deleted: bool = False) -> dict:
        ...

# Without autospec: typos in mock calls pass silently
mock = MagicMock()
mock.get_user(user_id=1, wrong_param=True)  # no error — silent bug

# With autospec: validates against real signature
mock = create_autospec(UserService)
mock.get_user(user_id=1, wrong_param=True)  # raises TypeError — caught immediately
mock.get_user(user_id=1, include_deleted=True)  # correct — passes

# With patch:
with patch('myapp.services.UserService', autospec=True) as MockService:
    instance = MockService.return_value
    instance.get_user.return_value = {'id': 1, 'name': 'Alice'}
```

**Rule:** Use `autospec=True` for all mocks of real classes and functions. Prevents interface drift
between mock and real implementation — if the real signature changes, tests break at the call site
instead of silently passing.

---

## Section 2 — `PropertyMock` — mocking Python `@property`

```python
from unittest.mock import MagicMock, PropertyMock, patch

class DatabaseConnection:
    @property
    def is_connected(self) -> bool:
        return self._socket is not None

# Anti-pattern: won't work for @property
mock = MagicMock()
mock.is_connected = True  # sets attribute, does NOT mock the property descriptor

# Correct: use PropertyMock with type() assignment
mock = MagicMock(spec=DatabaseConnection)
type(mock).is_connected = PropertyMock(return_value=True)
assert mock.is_connected is True  # works correctly

# With patch.object:
db_conn = DatabaseConnection()
with patch.object(type(db_conn), 'is_connected', new_callable=PropertyMock) as mock_prop:
    mock_prop.return_value = False
    assert not db_conn.is_connected
```

**Rule:** Always use `PropertyMock` assigned to `type(mock)` when mocking `@property`. Direct
attribute assignment bypasses the descriptor protocol and does not mock the property getter.

---

## Section 3 — `mock_open` — testing file I/O

```python
from unittest.mock import mock_open, patch
import json

def read_config(path: str) -> dict:
    with open(path) as f:
        return json.loads(f.read())

# Test file reading without touching the filesystem:
config_json = '{"host": "localhost", "port": 5432}'

with patch('builtins.open', mock_open(read_data=config_json)):
    result = read_config('/etc/app/config.json')
    assert result == {'host': 'localhost', 'port': 5432}

# Line-by-line iteration (e.g. CSV readers):
m = mock_open(read_data=config_json)
m.return_value.__iter__ = lambda self: iter(config_json.splitlines(True))
with patch('builtins.open', m):
    result = read_config('/etc/app/config.json')
```

**Rule:** Patch `builtins.open` at the module where it is *used*, not where it is defined.
`patch('myapp.readers.open', mock_open(...))` — not `patch('builtins.open', ...)` when the
reader imports `open` explicitly.

---

## Section 4 — Database-backed tests use real PostgreSQL, not a SQLite parametrization

A `params=['sqlite', 'postgres']` engine fixture proves the SQLite path and silently skips the
behaviour you ship (constraints, JSONB, `ON CONFLICT`, savepoints, casts). Mock the database only
for pure-logic units; for anything that builds an ORM session use the async outer-transaction +
SAVEPOINT fixture, with skip-locally / fail-in-CI semantics, in
[`postgres-integration-testing.md`](postgres-integration-testing.md).

---

## Section 5 — Async mock patterns

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx

async def fetch_user(user_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f'/users/{user_id}')
        return response.json()

@pytest.mark.asyncio
async def test_fetch_user():
    mock_response = MagicMock()
    mock_response.json.return_value = {'id': 1, 'name': 'Alice'}

    with patch('httpx.AsyncClient') as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        result = await fetch_user(1)
        assert result == {'id': 1, 'name': 'Alice'}
```

**Rule:** Use `AsyncMock` (not `MagicMock`) for any coroutine or `async with` context manager.
`MagicMock` does not return awaitables — tests will fail with `TypeError: object MagicMock can't
be used in 'await' expression`.

**`pytest-asyncio` config** (required in `pyproject.toml`; with `auto` drop the `@pytest.mark.asyncio`
decorators above, with the default `strict` keep them and use `@pytest_asyncio.fixture` for async fixtures):
```toml
[tool.pytest]               # pytest 9 native table; `[tool.pytest.ini_options]` is the legacy form
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"   # set explicitly; unset emits a deprecation warning
asyncio_default_test_loop_scope = "session"      # same scope as session-scoped async fixtures (engine)
```

---

## Section 6 — Fidelity traps

```python
from unittest.mock import MagicMock, create_autospec
from pydantic import BaseModel

class Out(BaseModel):
    v: int

Out.model_validate(MagicMock(), from_attributes=True)   # v=1: an UNSET attribute became a plausible value
```

Executed (pydantic 2.14): an unset `MagicMock` attribute validated as `1` (int), `1.0` (float) and
`True` (bool); `str` and `Decimal` fields raised. A test can therefore pass while asserting nothing about the field.

- Pin EVERY field the response model reads in the shared fixture; prefer `create_autospec(Cls, instance=True)` / `spec_set` so a missing or misspelled attribute raises.
- A pinned `side_effect=[a, b]` list raises `StopIteration` on the third call (executed): adding one query to the code under test breaks every such test, so grep tests after adding a query.
- `patch("pkg.mod.symbol")` patches a string path; if the code under test imports the symbol under another path (or after a package reload) you patch a module nobody calls. Assert the positive case (`mock.assert_awaited_once()`) or inject the dependency instead.
- Import exception classes used with `pytest.raises` at module level, not inside the test after the package was reloaded.
- Assert the outcome (one side effect, same status on replay), not that the mock was wired.
