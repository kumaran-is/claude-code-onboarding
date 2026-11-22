# Python Advanced Patterns — Reference

> Selective content from the python-pro skill for performance profiling, property-based testing,
> and advanced Python language features. Load when optimizing, benchmarking, or using advanced idioms.

---

## Performance Profiling

### Tool Selection

| Tool | Use Case |
|------|---------|
| `cProfile` | CPU profiling — finds slow functions in pure Python code |
| `py-spy` | Sampling profiler — attaches to running process, zero overhead |
| `memory_profiler` | Line-by-line memory usage — finds memory leaks |
| `pytest-benchmark` | Micro-benchmarking — measure and compare function performance |

### cProfile Usage

```python
import cProfile
import pstats
import io

def profile_function():
    pr = cProfile.Profile()
    pr.enable()

    # --- code to profile ---
    result = my_expensive_function()
    # -----------------------

    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(20)  # Top 20 functions
    print(s.getvalue())
    return result
```

### py-spy — Attach to Running Process

```bash
# Install
uv add --dev py-spy

# Profile a running FastAPI server (no code changes needed)
py-spy top --pid <PID>

# Generate flame graph
py-spy record -o profile.svg --pid <PID> --duration 30
```

### memory_profiler — Line-by-Line Memory

```python
from memory_profiler import profile

@profile
async def load_large_dataset(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)
```

```bash
# Run with memory profiling
uv add --dev memory-profiler
python -m memory_profiler my_script.py
```

### pytest-benchmark

```python
import pytest

def test_query_performance(benchmark, db_session):
    result = benchmark(lambda: db_session.execute(query))
    assert result is not None

# Run: pytest --benchmark-only
# Compare: pytest --benchmark-compare
```

---

## Optimization Techniques

### Async I/O — Concurrent Requests

```python
import asyncio
import httpx

async def fetch_all(client: httpx.AsyncClient, urls: list[str], limit: int = 10) -> list[dict]:
    sem = asyncio.Semaphore(limit)                        # bound concurrency

    async def one(url: str) -> dict:
        async with sem:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    # one deadline; first failure cancels siblings
    async with asyncio.timeout(20), asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(one(u)) for u in urls]
    return [t.result() for t in tasks]
```

Plain `asyncio.gather(*coros)` does NOT cancel siblings after the first failure (verified: the sibling ran to completion); use `TaskGroup`,
or `gather(..., return_exceptions=True)` for best-effort. Fire-and-forget, cancellation and thread bridges: `asyncio-concurrency-and-tasks.md`.

### Caching with functools

```python
from functools import lru_cache, cache

@lru_cache(maxsize=128)
def expensive_computation(n: int) -> int:
    return sum(i ** 2 for i in range(n))

# Python 3.9+ — unbounded cache
@cache
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
```

### Generator Expressions — Memory Efficient

```python
# ❌ Loads entire list into memory
total = sum([x ** 2 for x in range(1_000_000)])

# ✅ Generator — processes one at a time
total = sum(x ** 2 for x in range(1_000_000))
```

### CPU-Bound Work

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

# create ONCE at startup, shut down in lifespan; never per call
pool = ProcessPoolExecutor(max_workers=4)

async def process_large_dataset(items: list[dict]) -> list[dict]:
    loop = asyncio.get_running_loop()           # get_event_loop() is the legacy spelling
    # fn must be a picklable top-level function
    return await loop.run_in_executor(pool, cpu_intensive_transform, items)
```

Blocking sync SDK calls use `await asyncio.to_thread(fn, ...)` plus the SDK's own timeout and an outer `asyncio.timeout`: a thread cannot be cancelled.

---

## Property-Based Testing with Hypothesis

Use Hypothesis when you want to test invariants across a large space of inputs automatically.

```python
# Install
# uv add --dev hypothesis

from hypothesis import given, strategies as st
from hypothesis import settings

@given(st.lists(st.integers()))
def test_sort_is_idempotent(xs: list[int]):
    """Sorting twice should equal sorting once."""
    assert sorted(sorted(xs)) == sorted(xs)

@given(st.text(min_size=1))
def test_user_name_roundtrip(name: str):
    """Name should survive JSON serialization round-trip."""
    user = UserCreate(name=name, email="test@example.com", password="securepass")
    data = user.model_dump()
    restored = UserCreate(**data)
    assert restored.name == user.name

@settings(max_examples=500)
@given(st.integers(min_value=1, max_value=1000))
def test_price_calculation_never_negative(quantity: int):
    assert calculate_price(quantity) >= 0
```

---

## Advanced Python Language Features

### Structural Pattern Matching (Python 3.10+)

```python
def handle_event(event: dict) -> str:
    match event:
        case {"type": "user_created", "id": user_id}:
            return f"New user: {user_id}"
        case {"type": "order_placed", "total": total} if total > 1000:
            return f"High-value order: {total}"
        case {"type": str(event_type)}:
            return f"Unknown event: {event_type}"
        case _:
            return "Invalid event"
```

### Descriptors — Reusable Attribute Logic

```python
class ValidatedString:
    """Descriptor that validates string length on assignment."""

    def __init__(self, min_len: int = 0, max_len: int = 255):
        self.min_len = min_len
        self.max_len = max_len
        self.attr_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: object | None, objtype: type | None = None) -> str | None:
        if obj is None:
            return self  # type: ignore
        return getattr(obj, f"_{self.attr_name}", None)

    def __set__(self, obj: object, value: str) -> None:
        if not (self.min_len <= len(value) <= self.max_len):
            raise ValueError(f"{self.attr_name}: length must be {self.min_len}–{self.max_len}")
        setattr(obj, f"_{self.attr_name}", value)


class User:
    name = ValidatedString(min_len=1, max_len=100)
    email = ValidatedString(min_len=5, max_len=255)
```

### Context Managers — Resource Management

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@asynccontextmanager
async def unit_of_work(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Fresh session per unit: commit on clean exit, rollback on exception, close always."""
    async with factory() as session, session.begin():
        yield session


async def create_user_with_audit(
    payload: UserCreate, factory: async_sessionmaker[AsyncSession]
) -> uuid.UUID:
    async with unit_of_work(factory) as session:
        user = User(**payload.model_dump(exclude={"password"}))
        session.add(user)
        await session.flush()  # server-generated id is None until here
        session.add(AuditLog(action="user_created", entity_id=user.id))
        # read ids before the block exits (commit/rollback may expire state)
        return user.id
```

Never call `session.begin()` on a session that already ran a statement (`InvalidRequestError: A transaction is already begun`), and do not
add `rollback()` inside `begin()`. Ownership rules: `sqlalchemy-async-sessions-and-transactions.md`.

---

## When to Load This Reference

- About to profile a slow endpoint or query
- Need to write property-based tests for a critical algorithm
- Using pattern matching for command dispatch or event routing
- Building custom descriptors for reusable validation logic
- Optimizing memory usage in data processing pipelines
- Bounding async fan-out or offloading blocking/CPU work (then read `asyncio-concurrency-and-tasks.md` for task lifetime and cancellation)

---

## Additional Optimization Patterns

> Extended from python-performance-optimization skill — patterns not covered in the profiling section above.

### line_profiler — Line-by-Line CPU Profiling

Use when `cProfile` identifies a slow function and you need to pinpoint which lines are expensive.

```bash
# Install
uv add --dev line-profiler
```

**Decorator approach:**
```python
# Add @profile decorator (line_profiler injects this at runtime)
@profile
def process_data(data):
    """Process data with line profiling."""
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result

# Run with:
# kernprof -l -v script.py
```

**Programmatic approach (no decorator needed):**
```python
from line_profiler import LineProfiler

def process_data(data):
    """Function to profile."""
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result

if __name__ == "__main__":
    lp = LineProfiler()
    lp.add_function(process_data)

    data = list(range(100000))

    lp_wrapper = lp(process_data)
    lp_wrapper(data)

    lp.print_stats()
```

Output shows hits, time per line, and percentage — use it to decide which loop body to optimize.

### `__slots__` — Memory Optimization for High-Instance-Count Objects

Use when creating thousands of instances of a class (e.g., event objects, data records, value objects in a tight loop). `__slots__` eliminates the per-instance `__dict__`, reducing memory by ~40–60%.

```python
import sys

class RegularClass:
    """Regular class with __dict__ — flexible but memory-heavy."""
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

class SlottedClass:
    """Class with __slots__ — fixed attributes, lower memory."""
    __slots__ = ['x', 'y', 'z']

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

# Memory comparison
regular = RegularClass(1, 2, 3)
slotted = SlottedClass(1, 2, 3)

print(f"Regular class size: {sys.getsizeof(regular)} bytes")
print(f"Slotted class size: {sys.getsizeof(slotted)} bytes")

# Significant savings with many instances
regular_objects = [RegularClass(i, i+1, i+2) for i in range(10000)]
slotted_objects = [SlottedClass(i, i+1, i+2) for i in range(10000)]
```

**Trade-offs:**
- Cannot add arbitrary attributes after `__init__`
- Cannot use `__weakref__` unless explicitly added to `__slots__`
- Inheritance from slotted classes requires care — subclass must also define `__slots__` or it gains a `__dict__` anyway

**When NOT to use:** General application models, Pydantic models (already optimized), SQLAlchemy ORM models.

### SQLAlchemy Bulk Operations — Batch Insert/Update

On SQLAlchemy 2.x the unit of work already batches plain `session.add()` calls into one multi-row INSERT at flush; the real slowdown is flushing or committing per row.
`session.execute(insert(Model), records)` is the bulk form.

```python
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User

# Slow: a flush (round-trip) per record
async def slow_bulk_create(session: AsyncSession, records: list[dict]) -> None:
    for record in records:
        session.add(User(**record))
        await session.flush()
    await session.commit()

# Fast: one executemany-style statement
async def fast_bulk_create(session: AsyncSession, records: list[dict]) -> None:
    await session.execute(insert(User), records)
    await session.commit()

# Bulk update: each dict carries the PK plus the changed fields
async def fast_bulk_update(session: AsyncSession, updates: list[dict]) -> None:
    # e.g. [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    await session.execute(update(User), updates)
    await session.commit()
```

**Measured (PostgreSQL 16 over a local socket, 1000 rows, one run, SQLAlchemy 2.1.9 + asyncpg):** flush per row 101 ms; plain `add` x1000 then one commit 15 ms;
`insert(User), records` 8 ms. Network latency widens the per-row gap; re-measure on your infrastructure.

**Constraints:**
- `insert()` with `executemany` skips ORM events (`before_insert`, `after_insert`) — acceptable for bulk data loads, not for business-logic-heavy creates
- Does not return ORM instances — use `returning()` clause if you need inserted IDs
- For very large datasets (100k+ rows), chunk into batches of 1000–5000 to avoid memory pressure
