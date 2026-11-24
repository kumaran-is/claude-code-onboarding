# Pub/Sub and Firestore Messaging Patterns

> Three canonical patterns. No ad-hoc alternatives.
> Apply the decision tree below before choosing any pattern.

---

## Quick Decision Tree

```
Crossing a process boundary?
    |
    +-- Is the consumer a mobile app needing real-time UI (e.g. via Firestore)?
    |       YES → Pattern C (Firestore status bus)
    |
    +-- Is the event load-bearing?
    |   (losing it = broken workflow — downstream action never triggered)
    |       YES → Pattern B (transactional outbox)
    |
    +-- Informational event — consumer benefits but caller doesn't depend on delivery
            YES → Pattern A (fire-and-forget Pub/Sub)
```

---

## Pattern A — Direct Fire-and-Forget Pub/Sub

**Use for:** Informational events where the caller does NOT depend on delivery.
Examples: `entity.created`, `entity.status_changed`, `document.uploaded`.

### Required implementation

```python
import asyncio
import json
from datetime import UTC, datetime
from functools import lru_cache

import structlog
from google.cloud import pubsub_v1

from ..core.config import settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_publisher() -> pubsub_v1.PublisherClient:
    """Lazy singleton — SDK is expensive to instantiate."""
    return pubsub_v1.PublisherClient()


def _topic_path(topic: str) -> str:
    return f"projects/{settings.GOOGLE_CLOUD_PROJECT}/topics/{topic}"


async def _publish_event(data: dict) -> None:
    """Fire-and-forget: logs on failure, never raises."""
    try:
        publisher = _get_publisher()
        encoded = json.dumps(data, default=str).encode()
        future = publisher.publish(_topic_path(settings.PUBSUB_MY_TOPIC), encoded)
        # bounded: an unbounded result() pins a worker thread past a cancelled task
        await asyncio.to_thread(future.result, timeout=settings.PUBSUB_PUBLISH_TIMEOUT_S)
        logger.info("pubsub_publish_ok", event_type=data.get("event_type"))
    except Exception as exc:
        logger.error(
            "pubsub_publish_failed",
            event_type=data.get("event_type"),
            error_type=type(exc).__name__,
        )


# In the route/service — always spawn(), never await directly and never a bare create_task
# (spawn keeps a strong reference and logs failures: asyncio-concurrency-and-tasks.md section 1)
spawn(
    _publish_event(
        {
            "event_type": "entity.created",
            "entity_id": str(entity.id),
            "published_at": datetime.now(tz=UTC).isoformat(),
        }
    ),
    name="publish-entity-created",
)
```

### Hard rules

- ALWAYS run it through `spawn()` at the call site (never `await _publish_event()` inside a route or service method: it adds Pub/Sub
  latency to the HTTP response) and NEVER a bare `asyncio.create_task(...)` statement: the loop holds only a weak reference, so the task can be
  garbage-collected mid-flight and its exception is lost. Drain with `drain_background()` in lifespan shutdown
- Log `error_type=type(exc).__name__`, not `str(exc)` or `exc_info=True` (messages can carry URLs, tokens, payload fragments)
- ALWAYS catch all exceptions inside `_publish_event` — log and return, never raise
- NEVER use this pattern for events that trigger cross-service state changes (use Pattern B)
- Use `@lru_cache(maxsize=1)` for the publisher client — the GCP SDK is expensive to instantiate per request
- `publisher.publish(...).result()` blocks a thread: keep `asyncio.to_thread` and set a publish timeout, or the thread outlives a cancelled task

---

## Pattern B — Transactional Outbox

**Use for:** Load-bearing events where losing the event breaks a downstream workflow.
Examples: `order.approved` triggers fulfillment scheduling, `payment.captured` triggers shipping.

### Required implementation

**Step 1 — Outbox SQLAlchemy model** (in shared models):

```python
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MyServiceEventsOutbox(Base):
    __tablename__ = "my_service_events_outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # NULL = unpublished / pending retry; non-NULL = successfully published
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # gave up: alert, never delete
    exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

**Step 2 — Write outbox row inside the state-change transaction**:

```python
async def approve_entity(self, entity_id: uuid.UUID, session: AsyncSession) -> Entity:
    entity = await session.get(Entity, entity_id, with_for_update=True)
    _validate_can_approve(entity)

    entity.status = "approved"
    outbox_row = MyServiceEventsOutbox(
        event_type="entity.approved",
        payload={
            "entity_id": str(entity.id),
            "approved_at": datetime.now(tz=UTC).isoformat(),
        },
        published_at=None,  # NULL = not yet published
    )
    session.add(outbox_row)
    await session.commit()      # both entity update + outbox row in one transaction
    # NO Pub/Sub call here — outbox processor handles it
    return entity
```

**Step 3 — Outbox processor** (called by the scheduler endpoint). Attempts, backoff, `ORDER BY` and an exhausted state are mandatory:
without them one permanently failing row refills every batch and starves the rest (full executed version: `reliability-idempotency-retries-outbox.md` section 4).

```python
async def process_outbox(
    session: AsyncSession, topic: str, *, now: datetime, batch_size: int = 50
) -> list[str]:
    rows = (
        await session.scalars(
            select(MyServiceEventsOutbox)
            .where(
                MyServiceEventsOutbox.published_at.is_(None),
                MyServiceEventsOutbox.exhausted_at.is_(None),
                MyServiceEventsOutbox.next_attempt_at <= now,
            )
            .order_by(MyServiceEventsOutbox.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)  # safe for concurrent sweeps
        )
    ).all()

    published_ids: list[str] = []
    for row in rows:
        row.attempts += 1
        try:
            await publish_outbox_payload(
                topic=topic, event_type=row.event_type, payload=row.payload
            )
        except Exception as exc:
            row.last_error_type = type(exc).__name__
            if row.attempts >= MAX_ATTEMPTS:
                row.exhausted_at = now
                # alert
                logger.error("outbox_exhausted", row_id=str(row.id), error_type=row.last_error_type)
            else:
                # e.g. min(30s * 2**(n-1), 10min)
                row.next_attempt_at = now + backoff(row.attempts)
        else:
            row.published_at = now
            published_ids.append(str(row.id))

    await session.commit()
    return published_ids
```

**Step 4 — publish_outbox_payload RAISES on failure** (unlike Pattern A):

```python
async def publish_outbox_payload(topic: str, event_type: str, payload: dict) -> str:
    """Raises on failure — caller must NOT set published_at if this raises."""
    publisher = _get_publisher()
    data = json.dumps({"event_type": event_type, **payload}, default=str).encode()
    message_id = await asyncio.to_thread(
        lambda: publisher.publish(_topic_path(topic), data).result()
    )
    logger.info("pubsub_outbox_publish_ok", event_type=event_type, message_id=message_id)
    return message_id
```

**Step 5 — Cloud Scheduler endpoint**:

```python
@router.post("/internal/process-outbox", include_in_schema=False)
async def process_outbox_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    _verify_internal_secret(request)
    # one reading of ONE clock (the database) per run
    now = await session.scalar(select(func.now()))
    published_ids = await process_outbox(session, topic=settings.PUBSUB_MY_TOPIC, now=now)
    return {"published_count": len(published_ids), "event_ids": published_ids}
```

Sweep endpoint rules: cap the batch and the wall-clock budget and report what was deferred (never silently); `rollback()` before re-raising so the
shared session is not left in a failed transaction; `commit()` to release `FOR UPDATE` locks on an empty result; stamp with an `IS NULL` guard so a re-run is a no-op.

### Hard rules

- NEVER publish inside the DB transaction (Pub/Sub failure rolls back the entity state)
- NEVER publish after `session.commit()` without an outbox row (event silently lost on failure)
- `publish_outbox_payload` MUST raise — the processor relies on the exception to leave
  `published_at` NULL for retry
- Use `SELECT … FOR UPDATE SKIP LOCKED` in the processor — safe for concurrent scheduler runs
- Delivery is at-least-once: a crash between publish and commit republishes, so consumers MUST be idempotent
- Any consumer-side dedupe TTL must exceed the retry horizon (first wait + summed backoffs + margin); assert it at startup
- The sweep holds row locks across the publish call: give writers touching the same rows a `lock_timeout`
- Optional low latency: queue an after-commit publish (dropped on rollback) and keep the sweep as the backstop (same reference, section 4)
- Outbox table belongs in shared migrations — not per-service

---

## Pattern C — Firestore Status Bus (backend side)

**Use for:** Real-time status updates to mobile clients (Flutter/React Native) that need
live streaming without polling. Only applies when Firestore is part of the stack.

> If your stack does not use Firestore, use WebSockets, SSE, or polling instead.
> Pattern C is Firestore-specific.

### Required implementation

```python
import uuid

import structlog
from google.cloud import firestore

from ..core.config import settings

logger = structlog.get_logger(__name__)


async def write_status_event(
    client: firestore.AsyncClient,  # ONE client from lifespan (app.state.firestore), never one per call
    resource_id: uuid.UUID,
    event_id: uuid.UUID,
    status: str,
    previous_status: str,
    actor_id: uuid.UUID | None,
    actor_type: str,
) -> None:
    """Write resource status change to Firestore (real-time status bus).

    Non-fatal: failures are logged but NEVER raised to the caller.
    The relational DB already committed the canonical state before this runs.
    """
    doc_ref = (
        client.collection("resources")
        .document(str(resource_id))
        .collection("status_events")
        .document(str(event_id))  # deterministic id: a retried write overwrites, never duplicates
    )
    try:
        await doc_ref.set(
            {
                "status": status,
                "previous_status": previous_status,
                "actor_id": str(actor_id) if actor_id else None,
                "actor_type": actor_type,
                "timestamp": firestore.SERVER_TIMESTAMP,  # server clock, orderable in queries
            },
            timeout=settings.FIRESTORE_WRITE_TIMEOUT_S,
        )
    except Exception as exc:
        logger.error(
            "firestore_status_write_failed",
            resource_id=str(resource_id),
            error_type=type(exc).__name__,
        )


# lifespan: app.state.firestore = firestore.AsyncClient(project=settings.GOOGLE_CLOUD_PROJECT)
#           ... yield ...; app.state.firestore.close()
# google-cloud-firestore 2.34.1: AsyncClient.close() is synchronous (returns None):
# `await client.close()` raises TypeError (executed).
# In the route/service — always spawn(), never await
spawn(
    write_status_event(
        request.app.state.firestore,
        resource_id=resource_id,
        event_id=uuid.uuid4(),
        status=new_status,
        previous_status=previous_status,
        actor_id=actor_id,
        actor_type=actor_type,
    ),
    name="firestore-status-event",
)
```

### Hard rules

- NEVER write canonical entity data to Firestore — status_events subcollection ONLY
- ALWAYS `spawn()` it — never `await write_status_event()` at the call site
- ALWAYS catch all exceptions — Firestore failure must never surface to the HTTP caller
- The relational DB (PostgreSQL) remains canonical — Firestore is a write-through feed only
- Mobile clients read via `.snapshots()` stream listener, NOT one-time `.get()` calls

---

## Adding a New Topic — Required Steps

```bash
# 1. Add topic name to service config (operational default allowed)
class Settings(BaseSettings):
    PUBSUB_MY_TOPIC: str = "my-service-events"

# 2. Tri-file sync — all environment config files
# .env.example:    PUBSUB_MY_TOPIC=my-service-events
# .env.staging:    PUBSUB_MY_TOPIC=my-service-events
# .env.production: PUBSUB_MY_TOPIC=my-service-events

# 3. Local emulator init — add to Pub/Sub init script
curl -X PUT "http://pubsub-emulator:8085/v1/projects/$PROJECT/topics/my-service-events"

# 4. Verify
make check-env-sync    # must exit 0
make up                # new topic created on stack start
```

---

## Subscriber Pattern

Executed on google-cloud-pubsub 2.44.0 against the Pub/Sub emulator (worker in `reliability-idempotency-retries-outbox.md` section 7a: duplicates, retry,
dead-letter, SIGTERM drain; 13 tests). `subscribe()` returns a `StreamingPullFuture`; stream errors are set ON that future, so a discarded future is a
consumer that died silently. Inside a FastAPI service, route every subscription through `SubscriptionSupervisor` (section 7) started from lifespan;
a standalone worker process exits non-zero when the stream dies and lets the platform restart it (section 7a).

```python
flow = pubsub_v1.types.FlowControl(
    max_messages=settings.WORKER_MAX_MESSAGES,          # default 1000 in flight: size it to what finishes within the ack deadline
    max_lease_duration=int(settings.HANDLER_TIMEOUT_S * 2),  # default 3600 s: stop extending a hung message's lease
)
future = subscriber.subscribe(
    path, callback=callback, flow_control=flow,
    await_callbacks_on_shutdown=True,  # after cancel(), result() also waits for running callbacks
)
```

**Hard rules for subscribers:**
- ALWAYS `ack()` on success, `nack()` on exception or timeout — no silent drops; cancel the bridged future on timeout
- ALWAYS set a `timeout` on `run_coroutine_threadsafe().result()` — unbounded wait = thread leak
- NEVER process messages synchronously in the callback if the handler is async — use `run_coroutine_threadsafe`
- NEVER discard the `subscribe()` future or swallow a startup failure behind a "fallback": a consumer that never started must fail the readiness check
- Delivery is at-least-once, even with exactly-once enabled (publish-side duplicates): dedupe on an event id in the same transaction as the effect
- Poison input (malformed, schema, permanent business error) -> publish to the dead-letter topic, then `ack()`; transient failure -> `nack()`.
  The subscription's `DeadLetterPolicy` (`max_delivery_attempts` 5–100) is the backstop for messages that keep failing. Push handlers: malformed -> 4xx,
  transient -> 5xx, attempts exhausted -> publish a "failed" event then 2xx; verify the caller's signed identity and keep the write idempotent
- Side effects that must not repeat (e.g. push notifications): commit a `pending` claim row BEFORE the external call (`reliability-idempotency-retries-outbox.md` section 6)
- Trace context crosses the message boundary in attributes (inject on publish, extract on consume; PRODUCER/CONSUMER spans): `deployment-ci-cd/reference/python-observability.md` §3.3. Flush telemetry explicitly on shutdown (§3.1): a signal exit skips `atexit`, and buffered spans are lost
- mypy: `google-cloud-pubsub` ships no `py.typed`; add a `[[tool.mypy.overrides]]` with `module = ["google.cloud.pubsub_v1", "google.cloud.pubsub_v1.*", "google.pubsub_v1", "google.pubsub_v1.*"]` and `follow_untyped_imports = true`
