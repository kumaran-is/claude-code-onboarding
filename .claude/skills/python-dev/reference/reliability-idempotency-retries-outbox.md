# Reliability: Idempotency, Locks, Retries, Outbox, Consumers

> Python + PostgreSQL patterns for requests that may repeat, race or half-fail. Session/transaction ownership is
> defined in `sqlalchemy-async-sessions-and-transactions.md`; task and cancellation hygiene in `asyncio-concurrency-and-tasks.md`;
> the Pub/Sub messaging patterns in `pubsub-firestore-patterns.md`. Broker, cloud and cache names are examples, not requirements.
> Snippets were executed against PostgreSQL 16 (SQLAlchemy 2.1.9, asyncpg 0.32, tenacity 9.2.1, circuitbreaker 2.1.3, httpx 0.28) unless marked otherwise; section 7a on google-cloud-pubsub 2.44.0 against the Pub/Sub emulator.

---

## 1. Idempotency keys: insert first, let the constraint pick the winner

Get-then-set (`SELECT` the key, `INSERT` if missing) is a race: two concurrent first requests both miss and both create the effect.
Executed control: two coroutines synchronised past the lookup with `asyncio.Barrier(2)` produced **2 rows**; the insert-first flow below produced **1 row** and both callers received the same id.
Executed on the final snippet (PostgreSQL 16): 8 concurrent same-key calls -> 1 order, status 201 for all; changed body -> `IdempotencyKeyReusedError`; first request held uncommitted -> `IdempotencyInFlightError`; the snippet passes `mypy --strict` and ruff with the baseline.

```python
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    # scope by the AUTHENTICATED caller
    caller_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # PRIMARY KEY (caller_id, key) is the arbiter
    key: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # fingerprint of the request that won
    request_hash: Mapped[str] = mapped_column(String(64))
    # status of the original response
    status_code: Mapped[int]
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))


class IdempotencyKeyReusedError(Exception):
    """Same key, different request. Map to 422 with code `idempotency_key_reused`."""


class IdempotencyInFlightError(Exception):
    """Same key, first request still running. Map to 409 with a `Retry-After` header."""


def fingerprint(method: str, path: str, body: bytes) -> str:
    return hashlib.sha256(b"\0".join([method.encode(), path.encode(), body])).hexdigest()


def replay(prior: IdempotencyKey, request_hash: str) -> tuple[uuid.UUID, int]:
    if prior.request_hash != request_hash:
        raise IdempotencyKeyReusedError(str(prior.key))
    # the STORED result, original status; never re-execute
    return prior.order_id, prior.status_code


async def create_order(
    factory: async_sessionmaker[AsyncSession], caller_id: str, key: uuid.UUID, request_hash: str
) -> tuple[uuid.UUID, int]:
    async with factory() as session:
        prior = await session.get(IdempotencyKey, (caller_id, key))
        if prior is not None:
            return replay(prior, request_hash)               # fast path only; never the guard
        order = Order(id=uuid.uuid4(), caller_id=caller_id)
        session.add(order)
        try:
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            # no relationship(): parent first, then FK child
            await session.flush()
            session.add(IdempotencyKey(caller_id=caller_id, key=key, request_hash=request_hash,
                                       status_code=201, order_id=order.id))
            await session.commit()                           # effect + key in ONE transaction
        except IntegrityError:
            # also drops this attempt's staged order
            await session.rollback()
            prior = await session.get(IdempotencyKey, (caller_id, key))
            if prior is None:
                # not our race: a real constraint failure
                raise
            return replay(prior, request_hash)
        except DBAPIError as exc:
            await session.rollback()
            # lock_timeout: first request still in flight
            if getattr(exc.orig, "sqlstate", None) == "55P03":
                raise IdempotencyInFlightError(str(key)) from exc
            raise
        return order.id, 201
```

Rules:
- Key row and effect commit in the **same transaction**; otherwise a crash between them either loses the key or duplicates the effect.
- Scope by the authenticated caller, never by a global key space; one caller must not burn another's key.
- Parse the header to a canonical form (`uuid.UUID(...)`, then `str()`); an unparseable key is treated as absent, never used raw.
  When you add a namespace segment to one key in a family, re-check every sibling for a raw-id path (a forged id can pre-burn a real key).
- Canonical replay policy (recommended default, after the IETF Idempotency-Key header draft; `fastapi-architecture-and-config.md` section 7 uses the same codes):
  same key + same request fingerprint -> return the STORED result with the ORIGINAL status, never re-execute;
  same key + DIFFERENT fingerprint -> `422` with a stable code `idempotency_key_reused` (never the first result, never a re-execution);
  same key while the first request is still in flight -> `409` with `Retry-After`.
  In the single-transaction flow above the in-flight case is the second `INSERT` waiting on the first one's uncommitted key row; `SET LOCAL lock_timeout` bounds the wait and `55P03` becomes the 409.
  If you claim the key in a separate earlier commit instead, store an `in_progress` state and return 409 while it is set.
- A key-less request must still work unless the product explicitly requires the key.
- An endpoint replayed from a durable client queue should accept-and-flag a suspicious but processable payload rather than 4xx it: a
  non-transient 4xx makes the client discard the user's queued write. Reject only malformed, unauthorised or state-conflicting input, and test the non-rejection.
- Every uniqueness invariant also needs the DB constraint (unique or partial unique index). Application pre-checks are optimisations.
- Prove it: a test with two real connections, committed rows and a barrier, plus a control that removes the constraint and must go red
  (see `python-testing-patterns/reference/postgres-integration-testing.md`).

Races without a unique constraint to arbitrate (e.g. "at most one active X per account"): serialise with a transaction advisory lock (section 2) or lock the parent row `FOR UPDATE`.

---

## 2. Locks through a connection pool

A session-level advisory lock belongs to a **connection**, and a pool hands out connections. Executed (two pooled connections A and B):

| Step | Result |
|------|--------|
| `pg_advisory_lock(42)` on A, `pg_advisory_unlock(42)` through B | `False` (nothing unlocked) |
| Both sessions closed (connections back in the pool); another instance tries to lock | `False`: still held |
| `engine.dispose()` closes A | `True`: only closing the owning connection freed it |
| `pg_advisory_xact_lock(43)`: other instance tries to lock inside the transaction / after commit | `False` / `True` |

```python
# RIGHT: transaction-scoped; released at COMMIT or ROLLBACK, whichever connection that is
await session.scalar(
    text("SELECT pg_advisory_xact_lock(hashtext(:k)::bigint)"), {"k": f"order:{order_id}"}
)
```

- Never `pg_advisory_lock` / `pg_try_advisory_lock` / `pg_advisory_unlock` through an application pool (also unsafe behind a transaction-mode pooler).
- Fix one global lock order everywhere: advisory lock first, then row locks (`ORDER BY id FOR UPDATE`). Build keys in one helper from canonical (parsed) ids.
- Fail fast instead of queueing on user-facing statements that may meet rows held by sweeps: `SET LOCAL lock_timeout = '500ms'`
  (reverts at commit/rollback; executed: contender got SQLSTATE `55P03` surfaced as `DBAPIError`) and let the caller retry or return 503/409.
- Default isolation (READ COMMITTED) plus explicit locks and constraints is enough for these patterns. If you choose SERIALIZABLE or REPEATABLE READ, retry SQLSTATE `40001` in a bounded loop.

---

## 3. Retry only what is transient

```python
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE_STATUS


async def call(
    client: httpx.AsyncClient, method: str, url: str, *, idempotency_key: str | None = None
) -> httpx.Response:
    # POST retried only with a key
    retries = method.upper() != "POST" or idempotency_key is not None
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    async for attempt in AsyncRetrying(
        # attempts AND total window
        stop=stop_after_attempt(3 if retries else 1) | stop_after_delay(10),
        wait=wait_exponential_jitter(multiplier=0.2, max=2, jitter=0.2),
        retry=retry_if_exception(is_transient),
        reraise=True,
    ):
        with attempt:
            resp = await client.request(method, url, headers=headers)
            resp.raise_for_status()
            return resp
    raise AssertionError("unreachable")
```

Executed through `httpx.MockTransport`: 404 -> 1 call, raised; `503,503,200` GET -> 3 calls, success; `POST 503` without a key -> 1 call, raised;
`POST 503` with a key -> 2 calls, success; GET 503 forever -> 3 calls, raised.

| Rule | Why |
|------|-----|
| Never retry 4xx (except 429) | The request is wrong; repeating it repeats the failure |
| Never retry a non-idempotent POST without an idempotency key | A timeout does not mean it did not happen |
| Jitter + attempt cap + total window | Synchronised retries are a self-inflicted outage; combine `stop_after_attempt` and `stop_after_delay` with the union operator (as above) and keep the window below the caller's own deadline |
| One retry layer | An SDK that retries plus an outer retry multiplies attempts; disable one |
| Do not wrap every `httpx.HTTPError` in one retried exception | A 4xx would then be retried (the earlier example did exactly that) |

tenacity >= 9.2: `wait_exponential_jitter(initial=...)` emits a `DeprecationWarning`; use `multiplier=`. Pin and verify the version you install.

### Circuit breaker

```python
def is_dependency_failure(exc_type: type[BaseException], exc: BaseException) -> bool:
    """Counts toward opening: dependency health only. A caller error (4xx) must not trip it."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@circuit(failure_threshold=5, recovery_timeout=30, expected_exception=is_dependency_failure)
async def guarded_get(client: httpx.AsyncClient, url: str) -> httpx.Response: ...
```

Executed with `circuitbreaker` 2.1.3: five 404s left the breaker closed; three 503s (threshold 3) opened it. The predicate takes `(exc_type, exc)`.
Put the breaker around the whole retried call (one logical call = one count) and expose its state in readiness output.
`circuitbreaker` 2.1.3 imports `asyncio.iscoroutinefunction`, which Python 3.14 reports as deprecated (removal in 3.16): pin it and watch for a release that fixes it.
If you hand-roll a breaker: release the half-open probe slot in `finally`, never `except Exception` (`asyncio-concurrency-and-tasks.md` section 3).

---

## 4. Transactional outbox

Use it when losing the event breaks a workflow. Write the outbox row in the SAME transaction as the state change; a sweeper publishes it.

```python
# Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
# logger = structlog.get_logger(__name__)   (logging stack: python-observability.md)
MAX_ATTEMPTS = 5
BASE_DELAY, MAX_DELAY = timedelta(seconds=30), timedelta(minutes=10)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_type: Mapped[str | None] = mapped_column(String(100))


def backoff(attempts: int) -> timedelta:
    # `2 ** n` is typed Any: fails mypy --strict
    return min(BASE_DELAY * (1 << (attempts - 1)), MAX_DELAY)


async def sweep(
    session: AsyncSession, publish: Publish, *, now: datetime, batch: int = 50
) -> list[uuid.UUID]:
    rows = (
        await session.scalars(
            select(Outbox)
            .where(
                Outbox.published_at.is_(None),
                Outbox.exhausted_at.is_(None),
                Outbox.next_attempt_at <= now,
            )
            .order_by(Outbox.created_at)
            .limit(batch)
            # concurrent sweepers take different rows
            .with_for_update(skip_locked=True)
        )
    ).all()
    published: list[uuid.UUID] = []
    for row in rows:
        row.attempts += 1
        try:
            await publish(row.topic, row.payload)  # MUST raise on failure
        except Exception as exc:  # noqa: BLE001 - per-row isolation
            # type only: messages can carry secrets
            row.last_error_type = type(exc).__name__
            if row.attempts >= MAX_ATTEMPTS:
                row.exhausted_at = now
                logger.error(
                    "outbox_exhausted", event_id=str(row.id), error_type=row.last_error_type
                )  # alert
            else:
                row.next_attempt_at = now + backoff(row.attempts)
        else:
            row.published_at = now
            published.append(row.id)
    await session.commit()
    return published
```

Executed (3 attempts for the test): one poison row among three healthy rows: the healthy rows published on sweep 0, the poison row
backed off, then was marked exhausted after its last attempt and never retried again; two concurrent sweepers over 20 rows published
12 + 8 with 0 duplicates.

Rules:
- `ORDER BY`, a bounded batch and an attempts counter are mandatory: without them one permanently failing row refills every batch forever.
- Read the clock once per sweep (database `SELECT now()` preferred over mixing app and DB clocks) and cap total sweep wall-clock; report deferred counts, never silently.
- Delivery is **at-least-once**: a crash after `publish` and before `commit` republishes. Consumers must be idempotent (dedupe on a deterministic event id, e.g. `uuid5(namespace, business ids + occurrence)`).
- The sweep holds row locks across the publish call; give writers that touch the same rows a `lock_timeout`.
- A dedupe/"seen" TTL on the consumer must exceed the retry horizon: first sweep wait + sum of backoffs + margin.
  `horizon = sum(backoff(n) for n in range(1, MAX_ATTEMPTS))` = 30+60+120+240 s = 450 s here. Assert `dedupe_ttl > horizon + sweep_interval` at startup.
- Keep sweep cadence identical across app config, scheduler and local compose; pin it with a parity test.
- Exhausted rows are logged at ERROR with the id and error type, kept for replay, never deleted automatically.

### Publish immediately after commit, sweep as the backstop

Never publish inside the transaction. To cut latency, queue the publish for after the commit; a rollback drops it; the sweep still covers a crash or publish failure.
Executed: `committed` fired, `rolled-back` did not.

```python
@event.listens_for(Session, "after_commit")
def _fire(session: Session) -> None:
    for make_coro in session.info.pop("after_commit_callbacks", []):
        # spawn(): asyncio-concurrency-and-tasks.md
        spawn(make_coro(), name="outbox-immediate-publish")


@event.listens_for(Session, "after_rollback")
def _drop(session: Session) -> None:
    session.info.pop("after_commit_callbacks", None)


# in the service, before commit:
# session.sync_session.info.setdefault("after_commit_callbacks", []).append(factory)
```

On success mark the row published only if its payload is unchanged; on failure leave it for the sweep.

---

## 5. Claim queues (`SKIP LOCKED`) need a lease

A worker that flips a row to `processing` and crashes leaves it stuck forever. Use a lease and an attempts cap. Executed:

```sql
UPDATE jobs SET status = 'running', attempts = attempts + 1, locked_until = now() + make_interval(secs => :lease)
WHERE id IN (
    SELECT id FROM jobs
    WHERE attempts < :max_attempts
      AND (status = 'pending' OR (status = 'running' AND locked_until < now()))
    ORDER BY created_at LIMIT :batch FOR UPDATE SKIP LOCKED)
RETURNING id, attempts;
```

Results: first claim returned the row; a second claim during the lease returned nothing; after expiry it was re-claimed with `attempts = 2`, then `3`, then never again.
Completion is `UPDATE ... SET status = 'done' WHERE id = :id AND status = 'running'`.

---

## 6. External side effects and held sessions

- Compute and call the network FIRST, then open the session, write, commit. A session held across a slow call pins a pool slot.
- Pick delivery semantics on purpose:
  - **At-least-once** (default): do the work, then record it; handlers idempotent.
  - **At-most-once** (e.g. a push notification that must not repeat): commit a `pending` claim row BEFORE the call; a redelivery finds it and sends nothing;
    mark it `failed` on any later raise; on cancellation cancel and drain in-flight tasks.
- Classify provider errors: dead target -> deactivate it; permanent -> no retry; transient -> at most one retry inside a window.
- Sync SDK calls go through `asyncio.to_thread` plus the SDK's own HTTP timeout plus an outer deadline (a thread cannot be cancelled): `asyncio-concurrency-and-tasks.md` section 5.

---

## 7. Consumers: supervise them, classify failures

`SubscriberClient.subscribe(...)` returns a `StreamingPullFuture`; stream errors are set ON that future, so a discarded future is a consumer that died silently
(python-pubsub docs: `result()` raises the error, `cancel()` stops the stream). Route every subscription through a supervisor:

```python
# StreamFuture: Protocol with result() -> None and cancel() -> bool (streaming-pull future shape)
class SubscriptionSupervisor:
    """Keeps one streaming-pull subscription alive: re-subscribes with capped backoff."""

    def __init__(
        self,
        subscribe: Callable[[], StreamFuture],
        *,
        name: str,
        initial_backoff_s: float = 1.0,
        max_backoff_s: float = 30.0,
        healthy_after_s: float = 60.0,
    ) -> None:
        self._subscribe, self._name = subscribe, name
        self._initial, self._max, self._healthy_after = (
            initial_backoff_s,
            max_backoff_s,
            healthy_after_s,
        )
        self._stop = threading.Event()
        self._future: StreamFuture | None = None
        self._thread = threading.Thread(target=self._run, name=f"sub-{name}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._future is not None:
            self._future.cancel()
        self._thread.join(timeout)

    def _run(self) -> None:
        delay = self._initial
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._future = self._subscribe()
                # blocks until the stream dies or cancel()
                self._future.result()
                if self._stop.is_set():
                    return
                logger.error("subscription_ended_unexpectedly", name=self._name)
            except Exception as exc:  # noqa: BLE001 - supervisor boundary
                if self._stop.is_set():
                    return
                logger.error("subscription_failed", name=self._name, error_type=type(exc).__name__)
            if time.monotonic() - started >= self._healthy_after:
                # healthy for a while: reset the failure count
                delay = self._initial
            if self._stop.wait(delay):
                return
            delay = min(delay * 2, self._max)
```

Executed against a fake future (two stream failures, then healthy): 3 subscribe calls, thread stopped cleanly. Use the supervisor inside a long-lived service;
a standalone worker (7a) exits non-zero on stream death instead and lets the platform restart it. Add an architecture test (grep) that fails on a bare
`subscriber.subscribe(` whose result is discarded.

### 7a. Standalone streaming-pull worker (google-cloud-pubsub 2.44.0, executed)

Executed on Python 3.14.10 against the Pub/Sub emulator (digest-pinned container): a duplicate event is processed once; a transient failure is retried
in-process then redelivered and succeeds; malformed and permanent events go to the dead-letter topic without retries; an always-failing event is
dead-lettered by the subscription's `DeadLetterPolicy` after 5 attempts; SIGTERM drains an in-flight message and exits 0; SIGTERM past the drain deadline
cancels the handler, exits 0 within 10 s and the message is redelivered. 13 tests, 3 consecutive green runs. Controls: dropping the dedupe key, the SIGTERM
handler, the dead-letter policy, or the cancel-on-deadline each fails its test.

```python
def _callback(self, message: Message) -> None:  # subscriber thread
    if self._stopping.is_set():
        message.nack()  # draining: hand it to another instance now
        return
    cfut = asyncio.run_coroutine_threadsafe(handle(message.data, dict(message.attributes)), self._loop)
    self._track(cfut)
    try:
        result = cfut.result(timeout=self._cfg.handler_timeout_s)
    except TimeoutError:
        cfut.cancel()  # otherwise the handler keeps running while the message is redelivered
        message.nack()
        return
    except concurrent.futures.CancelledError:  # cancelled by drain()
        message.nack()
        return
    except Exception as exc:  # noqa: BLE001 - per-message boundary: log, nack, keep consuming
        logger.error("event_handler_crashed", message_id=message.message_id, error_type=type(exc).__name__)
        message.nack()
        return
    finally:
        self._untrack(cfut)
    if result.outcome is Outcome.RETRY_LATER:  # in-process retry budget exhausted
        message.nack()
    elif result.outcome is Outcome.DEAD_LETTER:  # poison: explicit dead-letter, then ack
        try:
            self._publisher.publish(self._cfg.dead_letter_topic_path, message.data, dlq_reason=result.reason,
                                    source_message_id=message.message_id).result(timeout=self._cfg.publish_timeout_s)
        except Exception as exc:  # noqa: BLE001 - not dead-lettered: nack so it is not lost
            logger.error("dead_letter_publish_failed", error_type=type(exc).__name__)
            message.nack()
            return
        message.ack()
    else:  # PROCESSED or DUPLICATE (insert-first dedupe, section 1)
        message.ack()

async def drain(self, future: StreamingPullFuture) -> None:  # on SIGTERM
    self._stopping.set()  # readiness turns false; new callbacks nack
    future.cancel()  # stop pulling; the client nacks queued and on-hold messages
    try:  # await_callbacks_on_shutdown=True: result() waits for running callbacks
        await asyncio.to_thread(future.result, timeout=self._cfg.drain_timeout_s)  # 7 s
    except TimeoutError:
        for cfut in self._snapshot_inflight():
            cfut.cancel()  # their callbacks nack -> redelivered elsewhere
        await asyncio.to_thread(future.result, timeout=self._cfg.cancel_grace_s)  # 1 s: total < Cloud Run's 10 s
```

Process wiring: `loop.add_signal_handler(signal.SIGTERM, stop.set)` in the worker's `main` (under uvicorn use lifespan shutdown instead: uvicorn owns the
signal); `run()` waits for `stop` or the stream ending, and re-raises the stream error so the process exits non-zero; `finally: subscriber.close();
publisher.stop()`, then flush telemetry (`Telemetry.shutdown()`: force_flush + shutdown, `deployment-ci-cd/reference/python-observability.md` §3.1) after the last ack. A signal exit skips `atexit`, so buffered spans and logs are otherwise lost. Trace propagation through message attributes: same file, §3.3. (Example D emits no spans; its flush path was not exercised.) Readiness = stream up and not draining. Cloud Run sends SIGTERM, then SIGKILL 10 s later.

| Topic | Verified fact (2.44.0 source / Pub/Sub docs) | Rule |
|---|---|---|
| Retry layers | in-process tenacity budget x `max_delivery_attempts` multiply | small in-process budget (3 attempts, 5 s); let redelivery do the rest |
| Dead-letter policy | `DeadLetterPolicy(dead_letter_topic, max_delivery_attempts)`, 5–100, approximate; `message.delivery_attempt` is `None` without it; forwarded messages carry `CloudPubSubDeadLetterSource*` attributes | set it on every subscription; grant the Pub/Sub service agent publisher on the DLQ topic and subscriber on the source; alert on DLQ depth |
| Retry policy | `RetryPolicy(minimum_backoff, maximum_backoff)` on the subscription | backoff between redeliveries instead of an immediate nack loop |
| Lease | `FlowControl.max_lease_duration` default 3600 s, `max_messages` default 1000 | lease = 2x handler timeout; `max_messages` = what finishes within it |
| Exactly-once | `enable_exactly_once_delivery`; pull/StreamingPull only, one region; only the latest ack id is valid; min ack deadline 60 s; `ack_with_response().result()` raises `AcknowledgeError` (`INVALID_ACK_ID`, `FAILED_PRECONDITION`, ...) | still dedupe (publish-side duplicates remain); use `ack_with_response` and treat a failed ack as "will be redelivered"; expect higher latency |
| Ordering | `PublisherOptions(enable_message_ordering=True)`, `publish(..., ordering_key=k)`, subscription `enable_message_ordering`; after a publish error the key pauses until `resume_publish(topic, k)`; publish from one region | order only per key; a nacked message holds back its key |
| Emulator | supports dead-letter topics, retry policies and ordering; no IAM, no UpdateTopic | integration tests on the emulator; IAM and exactly-once behaviour need a real project (not exercised here) |

Push (HTTP) handler semantics:

| Condition | Response | Effect |
|-----------|----------|--------|
| Malformed / poison input | 4xx | Dead-letter or drop; never redelivered forever |
| Transient failure (dependency down, lock timeout) | 5xx | Redelivered with backoff |
| Delivery attempts exhausted (read the attempt count from the envelope body, not a header) | publish a "failed" event, then 2xx | Stop the loop; surface it |
| Always | Verify the caller's signed identity; make the write idempotent | |

---

## 8. Sweep endpoint rules (scheduler-triggered)

- One reading of the DB clock per run; a batch cap and a wall-clock budget; report `deferred` counts.
- `rollback()` before re-raising so a shared session is not left in a failed transaction; `commit()` to release `FOR UPDATE` locks on an empty result.
- Stamp with an `IS NULL` guard (`UPDATE ... WHERE sent_at IS NULL`) so a re-run is a no-op.
- Liveness (process up, no dependency calls) and readiness (dependencies reachable, concurrent checks, each under `asyncio.timeout`) are separate endpoints:
  a liveness probe that queries the database restarts every instance during a database outage.

---

## 9. Review checklist

- [ ] Idempotency: key row + effect in one transaction, unique constraint arbitrates, rollback-and-return-winner, scoped by caller
- [ ] No session-level advisory locks; advisory-then-row lock order; `lock_timeout` on user-facing statements
- [ ] Retries: transient only, no 4xx, POST only with a key, jitter, attempts + window, one retry layer; breaker counts dependency failures only
- [ ] Outbox: attempts, backoff, `ORDER BY`, batch cap, exhausted state, idempotent consumers, TTL > retry horizon
- [ ] Claim queues have a lease and an attempts cap
- [ ] No session held across a network call; delivery semantics chosen and written down
- [ ] Every streaming consumer supervised (service) or exits non-zero on stream death (worker); handlers classify poison vs transient
- [ ] Dead-letter policy on every subscription; SIGTERM drain finishes within the platform's kill window; lease capped
