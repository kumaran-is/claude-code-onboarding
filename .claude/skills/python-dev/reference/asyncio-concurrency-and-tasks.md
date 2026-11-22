# asyncio Concurrency, Tasks and Cancellation

> Task lifetime, fan-out, cancellation, thread bridges and shutdown for Python 3.14 services.
> Every behaviour in the tables was executed on Python 3.14.3 unless marked "docs". Session rules: `sqlalchemy-async-sessions-and-transactions.md`;
> retries and outbox: `reliability-idempotency-retries-outbox.md`.

---

## 1. Fire-and-forget: keep a strong reference, observe the exception

The event loop keeps only weak references to tasks (CPython `asyncio` docs: "save a reference to the result of this function"). A bare
`asyncio.create_task(coro())` statement can be garbage-collected mid-flight, and its exception is only reported when the task is collected.

```python
import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger(__name__)
_background: set[asyncio.Task[Any]] = set()


def _on_done(task: asyncio.Task[Any]) -> None:
    _background.discard(task)
    if task.cancelled():
        return
    if (exc := task.exception()) is not None:          # reading it marks it retrieved
        logger.error("background_task_failed", task=task.get_name(), error_type=type(exc).__name__)


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    """Fire-and-forget with a strong reference; failure is logged, never lost."""
    task = asyncio.create_task(coro, name=name)
    _background.add(task)
    task.add_done_callback(_on_done)
    return task


async def drain_background(timeout_s: float = 5.0) -> None:
    """Lifespan shutdown: bounded wait for in-flight tasks, then cancel the stragglers."""
    pending = set(_background)
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout_s)
    for task in still_running:
        task.cancel()
    await asyncio.gather(*still_running, return_exceptions=True)
```

Executed: a failing task was logged by `_on_done` and left the set empty; `drain_background(0.3)` let a 50 ms task finish and cancelled a 10 s task (set empty afterwards).

Rules:
- Never write a bare `asyncio.create_task(...)` statement. Use `spawn(...)`. Enforce with ruff `RUF006` (executed: it flags the dropped result;
  `TaskGroup.create_task` is exempt). Add `"RUF006"` to `[tool.ruff.lint] select`.
- Fire-and-forget is acceptable only when the work may be lost (informational events) or a durable sweep backstops it (outbox). Load-bearing work goes through the outbox, not `spawn`.
- Drain in lifespan shutdown (`await drain_background()`) BEFORE disposing the engine and closing clients. Tasks must not capture the request's session (open their own).
- Log the exception TYPE, not `str(exc)`: messages can carry URLs, tokens or payload fragments.

---

## 2. Bounded fan-out

`asyncio.gather(*coros)` without `return_exceptions=True` raises the first error but does **not** cancel its siblings (executed: the sibling ran to completion
after `gather` had already raised). `TaskGroup` cancels siblings on the first failure.

```python
async def fetch_all(
    client: httpx.AsyncClient, urls: list[str], *, limit: int = 10, deadline_s: float = 20.0
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(limit)  # bound concurrency, not just count

    async def one(url: str) -> dict[str, Any]:
        async with sem:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    # one wall-clock budget for the whole fan-out
    async with asyncio.timeout(deadline_s), asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(one(u)) for u in urls]
    return [t.result() for t in tasks]
```

| Need | Use |
|------|-----|
| All-or-nothing, cancel on first failure | `TaskGroup` (failures arrive as an `ExceptionGroup`: `except* httpx.HTTPError`) |
| Best effort, collect every result | `gather(..., return_exceptions=True)` then inspect each result |
| Deadline | `asyncio.timeout(s)` around the whole block; when a deadline hits, cancel pending tasks AND await them |
| N unbounded items | A `Semaphore` or a worker queue; never one task per item for an unbounded list |

---

## 3. Cancellation: release in `finally`

`asyncio.CancelledError` is a `BaseException`: `except Exception` does not catch it. Cleanup placed there is skipped on cancellation.

```python
# WRONG: a cancelled half-open probe leaves in_flight True forever (executed: flag stayed True)
try:
    await probe()
except Exception:
    self.in_flight = False
    raise

# RIGHT: executed: flag is False after cancel
try:
    await probe()
finally:
    self.in_flight = False
```

Apply to in-flight flags, semaphores acquired by hand, probe slots, locks, "claimed" markers. Never swallow `CancelledError`; if you must catch it to clean up, re-raise.
A cancellation during `await session.commit()` can leave the outcome unknown: do not report success or failure to the caller from the `finally` block.

---

## 4. Thread-to-loop bridge (callback threads)

Subscriber callbacks, SDK callbacks and signal handlers run on other threads. Capture the loop at startup and bridge with `run_coroutine_threadsafe`.
A `result(timeout)` that times out leaves the coroutine running (executed: it still completed ~0.3 s later) while the message is redelivered. Cancel it.

```python
# captured in lifespan/startup, passed to the callback factory
loop = asyncio.get_running_loop()


def callback(message) -> None:
    fut = asyncio.run_coroutine_threadsafe(dispatch(parse(message.data)), loop)
    try:
        fut.result(timeout=30)
        message.ack()
    except TimeoutError:
        fut.cancel()  # executed: handler did not complete after cancel
        message.nack()
    except Exception as exc:  # noqa: BLE001 - callback boundary: nack
        logger.error("dispatch_failed", error_type=type(exc).__name__)
        message.nack()
```

Always set the timeout (an unbounded `result()` leaks the thread), `ack()` on success, `nack()` otherwise. Never use an undefined or `get_event_loop()` loop.

---

## 5. Blocking code

| Situation | Do |
|-----------|----|
| Sync SDK / file / DNS call | `await asyncio.to_thread(fn, ...)`; also set the SDK's own HTTP timeout. Executed: `asyncio.timeout` cancelled the await at 50 ms but the thread kept running to completion: a thread cannot be cancelled |
| CPU-bound work | A long-lived `ProcessPoolExecutor` created once at startup, used via `asyncio.get_running_loop().run_in_executor(pool, fn, arg)`; shut it down in lifespan |
| Need the loop inside a coroutine | `asyncio.get_running_loop()`, never `get_event_loop()` |
| Per-call executor | Do not create `ProcessPoolExecutor()` inside the request path: pays process start-up every call |

Put an outer deadline (`asyncio.timeout`) around every `to_thread` call; the thread still occupies a default-executor slot until it returns.

---

## 6. Startup and shutdown

- Use `lifespan=`. `app.router.on_startup/on_shutdown` and `@app.on_event` are ignored when `lifespan=` is set
  (executed on FastAPI 0.165: only `lifespan-start` / `lifespan-stop` fired; the `on_startup` hook never ran).
- Redis (`redis.asyncio.from_url`) does not connect at creation: `await client.ping()` in startup to detect an unreachable server, and never log the URL (it may hold credentials).
- Let uvicorn handle SIGTERM: it stops accepting, drains in-flight requests, then runs lifespan shutdown (docs: uvicorn "Graceful Process Shutdown").
  Do not install `signal.signal(SIGTERM, ...sys.exit(0))` handlers; tune `--timeout-graceful-shutdown` below the platform's SIGKILL window.
- Put `yield` inside `try/finally`: without it a failure after the resource exists skips every cleanup line. Shutdown order: stop accepting work, `drain_background()`, stop consumers (`SubscriptionSupervisor.stop()`), close clients, `engine.dispose()`.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # SecretStr -> str; settings stored on app.state by create_app
    app.state.redis = aioredis.from_url(app.state.settings.redis_url.get_secret_value())
    try:
        await app.state.redis.ping()
        yield
    # runs even when startup after the resource was created, or the app body, raised
    finally:
        await drain_background()
        await app.state.redis.aclose()
        # engine built in the lifespan: sqlalchemy-async-sessions-and-transactions.md section 2
        await app.state.engine.dispose()
```

---

## 7. Review checklist

- [ ] No bare `create_task` (ruff `RUF006` on); `spawn()` used; `drain_background()` in lifespan
- [ ] Fan-out bounded by a `Semaphore` and an `asyncio.timeout`; `TaskGroup` unless best-effort is intended
- [ ] Cleanup in `finally`, never only in `except Exception`; `CancelledError` re-raised
- [ ] Thread bridges: loop captured, timeout set, future cancelled on timeout, nack/ack explicit
- [ ] Blocking calls in `to_thread` with SDK timeout and outer deadline; CPU work in a long-lived pool
- [ ] `lifespan=` only; no custom SIGTERM handler; shutdown order documented
