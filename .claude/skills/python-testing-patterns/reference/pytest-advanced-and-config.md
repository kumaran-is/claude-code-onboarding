# pytest: Advanced Patterns, Markers, Coverage and Configuration

Advanced test patterns (async, monkeypatch, temporary files, conftest fixtures, property-based) and the tooling around them: markers, coverage, the real-PostgreSQL fixture, CI, pytest 9 configuration and static analysis. Fundamental patterns, test organization and naming: [`../resources/implementation-playbook.md`](../resources/implementation-playbook.md).

## Advanced Patterns

### Pattern 6: Testing Async Code

```python
# test_async.py
import pytest
import pytest_asyncio
import asyncio

async def fetch_data(url: str) -> dict:
    """Fetch data asynchronously."""
    await asyncio.sleep(0.1)
    return {"url": url, "data": "result"}


@pytest.mark.asyncio
async def test_fetch_data():
    """Test async function."""
    result = await fetch_data("https://api.example.com")
    assert result["url"] == "https://api.example.com"
    assert "data" in result


@pytest.mark.asyncio
async def test_concurrent_fetches():
    """Test concurrent async operations."""
    urls = ["url1", "url2", "url3"]
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert all("data" in r for r in results)


@pytest_asyncio.fixture   # strict mode (default) needs this decorator; asyncio_mode = "auto" does not
async def async_client():
    """Async fixture."""
    client = {"connected": True}
    yield client
    client["connected"] = False


@pytest.mark.asyncio
async def test_with_async_fixture(async_client):
    """Test using async fixture."""
    assert async_client["connected"] is True
```

### Pattern 7: Monkeypatch for Testing

```python
# test_environment.py
import os
import pytest

def get_database_url() -> str:
    """Get database URL from environment."""
    return os.environ.get("DATABASE_URL", "sqlite:///:memory:")


def test_database_url_default():
    """Test default database URL."""
    # Will use actual environment variable if set
    url = get_database_url()
    assert url


def test_database_url_custom(monkeypatch):
    """Test custom database URL with monkeypatch."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    assert get_database_url() == "postgresql://localhost/test"


def test_database_url_not_set(monkeypatch):
    """Test when env var is not set."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == "sqlite:///:memory:"


class Config:
    """Configuration class."""

    def __init__(self):
        self.api_key = "production-key"

    def get_api_key(self):
        return self.api_key


def test_monkeypatch_attribute(monkeypatch):
    """Test monkeypatching object attributes."""
    config = Config()
    monkeypatch.setattr(config, "api_key", "test-key")
    assert config.get_api_key() == "test-key"
```

### Pattern 8: Temporary Files and Directories

```python
# test_file_operations.py
import pytest
from pathlib import Path

def save_data(filepath: Path, data: str):
    """Save data to file."""
    filepath.write_text(data)


def load_data(filepath: Path) -> str:
    """Load data from file."""
    return filepath.read_text()


def test_file_operations(tmp_path):
    """Test file operations with temporary directory."""
    # tmp_path is a pathlib.Path object
    test_file = tmp_path / "test_data.txt"

    # Save data
    save_data(test_file, "Hello, World!")

    # Verify file exists
    assert test_file.exists()

    # Load and verify data
    data = load_data(test_file)
    assert data == "Hello, World!"


def test_multiple_files(tmp_path):
    """Test with multiple temporary files."""
    files = {
        "file1.txt": "Content 1",
        "file2.txt": "Content 2",
        "file3.txt": "Content 3"
    }

    for filename, content in files.items():
        filepath = tmp_path / filename
        save_data(filepath, content)

    # Verify all files created
    assert len(list(tmp_path.iterdir())) == 3

    # Verify contents
    for filename, expected_content in files.items():
        filepath = tmp_path / filename
        assert load_data(filepath) == expected_content
```

### Pattern 9: Custom Fixtures and Conftest

```python
# conftest.py
"""Shared fixtures for all tests."""
import pytest

@pytest.fixture(scope="session")
def database_url():
    """Provide database URL for all tests."""
    return "postgresql://localhost/test_db"


@pytest.fixture(autouse=True)
def reset_database(database_url):
    """Auto-use fixture that runs around each test (real cleanup goes here, never print)."""
    yield


@pytest.fixture
def sample_user():
    """Provide sample user data."""
    return {
        "id": 1,
        "name": "Test User",
        "email": "test@example.com"
    }


@pytest.fixture
def sample_users():
    """Provide list of sample users."""
    return [
        {"id": 1, "name": "User 1"},
        {"id": 2, "name": "User 2"},
        {"id": 3, "name": "User 3"},
    ]


# Parametrized fixture
@pytest.fixture(params=["sqlite", "postgresql", "mysql"])
def db_backend(request):
    """Fixture that runs tests with different database backends."""
    return request.param


def test_with_db_backend(db_backend):
    """This test will run 3 times with different backends."""
    assert db_backend in ["sqlite", "postgresql", "mysql"]
```

### Pattern 10: Property-Based Testing

```python
# test_properties.py
from hypothesis import given, strategies as st
import pytest

def reverse_string(s: str) -> str:
    """Reverse a string."""
    return s[::-1]


@given(st.text())
def test_reverse_twice_is_original(s):
    """Property: reversing twice returns original."""
    assert reverse_string(reverse_string(s)) == s


@given(st.text())
def test_reverse_length(s):
    """Property: reversed string has same length."""
    assert len(reverse_string(s)) == len(s)


@given(st.integers(), st.integers())
def test_addition_commutative(a, b):
    """Property: addition is commutative."""
    assert a + b == b + a


@given(st.lists(st.integers()))
def test_sorted_list_properties(lst):
    """Property: sorted list is ordered."""
    sorted_lst = sorted(lst)

    # Same length
    assert len(sorted_lst) == len(lst)

    # All elements present
    assert set(sorted_lst) == set(lst)

    # Is ordered
    for i in range(len(sorted_lst) - 1):
        assert sorted_lst[i] <= sorted_lst[i + 1]
```


## Markers, coverage, database, CI and configuration

### Test Markers

```python
# test_markers.py
import pytest

@pytest.mark.slow
def test_slow_operation():
    """Mark slow tests."""
    import time
    time.sleep(2)


@pytest.mark.integration
def test_database_integration():
    """Mark integration tests."""
    pass


@pytest.mark.skip(reason="Feature not implemented yet")
def test_future_feature():
    """Skip tests temporarily."""
    pass


@pytest.mark.skipif(os.name == "nt", reason="Unix only test")
def test_unix_specific():
    """Conditional skip."""
    pass


@pytest.mark.xfail(reason="Known bug (tracker id here)")
def test_known_bug():
    """Mark expected failures."""
    assert False


# Run with:
# pytest -m slow          # Run only slow tests
# pytest -m "not slow"    # Skip slow tests
# pytest -m integration   # Run integration tests
```

### Coverage Reporting

```bash
# Install coverage
pip install pytest-cov

# Run tests with coverage
pytest --cov=myapp tests/

# Generate HTML report
pytest --cov=myapp --cov-report=html tests/

# Fail if coverage below threshold
pytest --cov=myapp --cov-fail-under=80 tests/

# Show missing lines
pytest --cov=myapp --cov-report=term-missing tests/
```

## Testing Database Code

ORM and SQL behaviour is tested on real PostgreSQL, not SQLite (SQLite accepts SQL PostgreSQL rejects and ignores constraints). Full, executed fixtures (skip-vs-fail with `REQUIRE_DB_TESTS`, outer transaction + SAVEPOINT, ASGI client with lifespan and dependency overrides, race tests with barriers) are in [`../reference/postgres-integration-testing.md`](../reference/postgres-integration-testing.md). The core fixture:

```python
# tests/conftest.py (engine fixture: see the reference for the skip-vs-fail version)
@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()                        # outer transaction
        maker = async_sessionmaker(bind=conn, expire_on_commit=False,
                                   join_transaction_mode="create_savepoint")
        async with maker() as s:
            yield s                                       # commit() only releases a SAVEPOINT
        await outer.rollback()                            # nothing persists
```

Do NOT use this fixture to prove a commit boundary or a cross-connection race (two sessions on one connection see each other's uncommitted rows); use two connections and a remove-the-commit control.

## CI/CD Integration

Pinned actions, locked installs, executed-count gate, dependency audit and path filters: [`deployment-ci-cd/reference/python-ci-supply-chain.md`](../../deployment-ci-cd/reference/python-ci-supply-chain.md) (workflow validated with `actionlint`). Test the Python you deploy (`.python-version`), not a matrix of old interpreters; install with `uv sync --locked`, never `pip install -e` from loose ranges; a tag-pinned `actions/*@v3` is not a pin.

## Configuration Files

pytest 9 reads a native TOML table, `[tool.pytest]` (typed lists and booleans). The string-based `[tool.pytest.ini_options]` still works, but a file with BOTH tables fails at startup (executed, pytest 9.2.0: `Cannot use both [tool.pytest] ... and [tool.pytest.ini_options]`, exit 4). Use one `pyproject.toml` table, not a separate `pytest.ini`.

```toml
# pyproject.toml
[tool.pytest]
minversion = "9.0"
testpaths = ["tests"]
strict = true            # strict_config + strict_markers + strict_xfail + strict_parametrization_ids
addopts = ["-ra", "--tb=short"]
# coverage runs in the gate (pytest --cov=myapp --cov-fail-under=80), not in addopts:
# it slows every run and interferes with debuggers
markers = [
    "slow: marks tests as slow",
    "integration: needs a real service",
    "e2e: end-to-end tests",
]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"   # set explicitly; unset emits PytestDeprecationWarning
asyncio_default_test_loop_scope = "session"
timeout = "30"                                   # pytest-timeout backstop; a STRING: native int 30 fails startup (exit 4)
filterwarnings = ["error"]                       # add targeted "ignore:...:DeprecationWarning:pkg" lines for third-party noise

[tool.coverage.run]
source = ["myapp"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

### Static analysis: ruff, mypy, vulture

Executed on Python 3.14.10 with ruff 0.17.6, mypy 2.4.1 and vulture 2.16 (each tool's own exit code: 0 on the clean example; planted violations below made each exit non-zero).

```toml
[tool.ruff]
line-length = 100
target-version = "py314"          # also enables py314 upgrades, e.g. UP037 drops quoted annotations (PEP 649)

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "ASYNC", "S", "BLE", "LOG", "G", "T20", "PT", "RUF", "SIM", "TRY"]
ignore = ["TRY003"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.mypy]
python_version = "3.14"
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]       # pydantic 2.14 still ships the plugin; it types model __init__ and fields
# scoped escape hatch for third-party classes without annotations, never a global relaxation
untyped_calls_exclude = ["presidio_anonymizer"]

[tool.vulture]
paths = ["src", "vulture_whitelist.py"]
min_confidence = 60               # 80+ reports only unused imports; unused functions are 60
```

- `ruff check` and `ruff format --check` are separate gates; run both. `T20` blocks `print()`, `BLE` blind `except Exception`, `ASYNC` blocking calls in coroutines.
- vulture at 60 % flags framework entry points (route handlers, `create_app` used via `--factory`). Generate `vulture_whitelist.py` with `vulture src --make-whitelist`, review it, commit it; a planted unused function then fails with exit 3.
- **Stub packages can hide the real types.** cachetools 8 ships its own annotations (`py.typed` plus `.pyi` files with `ParamSpec`-preserving `cached` wrappers). PEP 561 gives a `*-stubs` package priority over inline types, so `types-cachetools` 7.x silently replaces them. Executed: a `@cached` function called with a `str` for an `int` parameter passed `mypy --strict` with `types-cachetools==7.0.0.20260713` installed (exit 0) and failed without it (`arg-type`, exit 1). Remove `types-cachetools` when you pin `cachetools>=8`; on every upgrade check `ls site-packages/<pkg>/py.typed` before adding a `types-*` package.
