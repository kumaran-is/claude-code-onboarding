# Python Backend Service Consistency Patterns

> Every backend service in this repository MUST follow every pattern in this file.
> Violations block PR merge — pre-commit gates enforce each rule automatically.

---

## Why This File Exists

Backend service consistency audits repeatedly find the same drift points appearing across
independent services. Wiring, lifespan, settings and transaction rules are in
`fastapi-architecture-and-config.md`; per-route authorization in `fastapi-authorization-boundaries.md`. These patterns codify hard-learned lessons so they cannot re-appear
in new or modified services.

Load this file BEFORE writing any code in a backend service. Gate paths below assume
`src/<package>/...` inside each service; adjust the globs to your layout.

---

## P1 — Internal Secret Guard (Security-Critical)

**Rule:** Internal endpoints (server-to-server, not user-facing) MUST use timing-safe
comparison, and the guard MUST refuse to be built with an empty secret (`hmac.compare_digest(b"", b"")`
is `True`, so an empty expected secret admits everyone). Never write `!=` or an unguarded string
comparison for secrets. Always `.encode()` before comparing (a non-ASCII `str` raises `TypeError`, i.e. a 500).

```python
# ✅ REQUIRED — timing-safe internal secret dependency; the secret comes from app.state.settings,
# which create_app(settings) set (no module-level settings: fastapi-architecture-and-config.md §3)
import hmac
from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request

# in Settings: internal_api_secret: SecretStr = Field(min_length=32)  -> empty is a boot failure


def require_internal_secret(
    request: Request, x_internal_secret: Annotated[str | None, Header()] = None
) -> None:
    expected = request.app.state.settings.internal_api_secret.get_secret_value().encode()
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret.encode(), expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/internal/action", dependencies=[Depends(require_internal_secret)])
async def internal_action() -> None: ...

# ❌ BANNED — bare != comparison (timing attack)
if x != expected_secret: ...

# ❌ BANNED — route-body secret check (instantiates DB session before auth)
async def handler(request: Request, db=Depends(get_session)):
    secret = request.headers.get("X-Internal-Secret")
    if not secret or ...: raise HTTPException(403)
```

Test every variant: header absent, empty, wrong, non-ASCII, correct; and `Settings(internal_api_secret="")` fails at boot.
The `/internal/` prefix is a convention; the guard is the control. Endpoints with third-party
side effects (send, charge, metered calls) must use it, never an end-user JWT:
`fastapi-authorization-boundaries.md` §3.

**Pre-commit gate:**
```bash
# Bare != comparison against a secret string in service routes
grep -rn "!= settings\.\|!= secret\b" src/*/api/routes/ --include="*.py" \
  | grep -v "test_\|#" → must return 0
```

---

## P2 — Config: Required Fields Have No Default

**Rule:** Every secret or environment-specific value in `core/config.py` has no default.
Secrets are `SecretStr` (with `Field(min_length=N)`). `str | None = None` is forbidden for any field
that must be present — it silently passes `None` downstream and hides misconfiguration until
production. Full template (fail-fast loader that prints field names only, boot-contract test):
`fastapi-architecture-and-config.md` §2.

```python
# ✅ REQUIRED — fails at startup (ValidationError) if the env var is absent
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # enforces length, no default, masked in repr
    internal_api_secret: SecretStr = Field(min_length=32)
    database_url: SecretStr                                  # required, no default
    events_topic: str = "my-service-events"                  # operational default OK
    log_level: str = "INFO"                                  # operational default OK

# ❌ BANNED — silently passes None to DB/messaging
    database_url: str | None = None
# ❌ BANNED — secret with a default
    internal_api_secret: str = "changeme"
```

**Allowed defaults** (non-sensitive operational values that are stable across environments):
- Topic/queue names: `events_topic: str = "my-topic-name"`
- Ports: `port: int = 8080`
- Service names: `service_name: str = "my-service"`
- Log level: `log_level: str = "INFO"`

**Pre-commit gate:**
```bash
grep -rn "str | None = None" src/*/core/config.py → must return 0
grep -rniE "(secret|password|token).*=.*['\"]" src/*/core/config.py → must return 0
```

---

## P3 — Logger Naming: Always `logger`, Never `log`

**Rule:** Every module uses `logger = structlog.get_logger(__name__)`. The name `log` is
forbidden — one name everywhere keeps greps and gates reliable. Never pass `str(exc)`, `exc_info=True`
or a connection URL to a logger on request paths: log the exception type and ids
(`fastapi-error-handling.md` §6).

```python
# ✅ REQUIRED — in every .py file that logs
import structlog
logger = structlog.get_logger(__name__)

# ❌ BANNED
log = structlog.get_logger(__name__)      # wrong name
log = structlog.get_logger("myservice")  # hardcoded name (use __name__)
logger = structlog.get_logger()          # missing __name__
```

**Pre-commit gate:**
```bash
grep -rn "^log = structlog" src/ --include="*.py" → must return 0
grep -rn "structlog.get_logger()" src/ --include="*.py" | grep -v "__name__" → must return 0
```

---

## P4 — Session Ownership: Service Layer Only

**Rule:** Routes NEVER call `session.add()`, `session.commit()`, or `session.rollback()`.
The service layer owns all DB mutations. Routes call service methods and translate
exceptions to HTTP responses. Repositories `flush()` and never commit. A commit placed after
`yield` in a default-scope dependency runs **after the response is sent**: a failed commit still
returns 200 (executed). Dependency chain and the `scope="function"` alternative:
`fastapi-architecture-and-config.md` §4; session internals: `sqlalchemy-async-sessions-and-transactions.md`.

```python
# ✅ REQUIRED — route layer (thin)
@router.post("/entities", status_code=201)
async def create_entity(
    data: EntityCreate,
    svc: ServiceDep,                      # Annotated[EntityService, Depends(get_service)]
) -> EntityResponse:
    entity = await svc.create(data)       # service owns commit
    return EntityResponse.model_validate(entity)

# ✅ REQUIRED — service layer owns commit
class EntityService:
    async def create(self, data: EntityCreate) -> Entity:
        entity = Entity(**data.model_dump())
        self._session.add(entity)
        await self._session.commit()      # ← commit lives here
        return entity

# ❌ BANNED — route calling session directly
@router.post("/entities")
async def create_entity(data: EntityCreate, session: SessionDep):
    entity = Entity(**data.model_dump())
    session.add(entity)
    await session.commit()                # route owns session mutation
```

**Pre-commit gate:**
```bash
grep -rn "session\.add\|session\.commit\|session\.rollback" \
  src/*/api/routes/ --include="*.py" | grep -v "test_\|#.*Session-isolated" → must return 0
```

---

## P5 — Pub/Sub Publisher: `@lru_cache(maxsize=1)` Singleton

**Rule:** Pub/Sub `PublisherClient` is expensive to create. Every service that publishes
events must use a cached singleton factory, not a per-request or module-level mutable global.

```python
# ✅ REQUIRED
from functools import lru_cache
from google.cloud import pubsub_v1

@lru_cache(maxsize=1)
def _build_pubsub_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()

# ❌ BANNED — module-level mutable global
_pubsub_publisher: pubsub_v1.PublisherClient | None = None
def _get_publisher():
    global _pubsub_publisher
    if _pubsub_publisher is None:
        _pubsub_publisher = pubsub_v1.PublisherClient()
    return _pubsub_publisher

# ❌ BANNED — per-request instantiation
async def publish_something():
    publisher = pubsub_v1.PublisherClient()   # new client per call — expensive
    publisher.publish(...)
```

**Pre-commit gate:**
```bash
grep -rn "PublisherClient()" src/ --include="*.py" | grep -v "lru_cache\|test_\|#" → must return 0
```

---

## P6 — Fire-and-Forget Publishes: Retained `create_task()`

**Rule:** Informational publishes (losing one is acceptable) MUST NOT be awaited inside a route or
service method — that couples broker latency to the HTTP response — and MUST NOT call `.result()`
at the call site. Schedule them through ONE helper that keeps a **strong reference** to the task
(the event loop keeps only weak ones, so an un-referenced task can be garbage-collected mid-flight)
and logs failures. Load-bearing events go through a transactional outbox, not a task.

```python
# ✅ REQUIRED — one helper, strong reference, failures logged by type
import asyncio
from collections.abc import Coroutine
from typing import Any

_background: set[asyncio.Task[None]] = set()


def spawn(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    task = asyncio.create_task(coro)
    _background.add(task)                        # strong reference until done
    task.add_done_callback(_background.discard)
    task.add_done_callback(_log_task_failure)
    return task


def _log_task_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("background_task_failed", error_type=type(exc).__qualname__)


spawn(_publish_event({"event_type": "entity.created", "entity_id": str(entity.id)}))

# ❌ BANNED
await _publish_event(...)            # blocks response; broker outage = service outage
publisher.publish(...).result()      # synchronous; raises on failure at call site
asyncio.create_task(_publish_event(...))   # reference dropped; ruff RUF006
```

Executed: a failing task was logged as `error_type=RuntimeError` without its message and removed from
the set. "Never raise on publish" is not enough: a swallowed failure must still be logged.
The canonical `spawn()` (named tasks) and the `drain_background()` call for `lifespan` shutdown live in
`asyncio-concurrency-and-tasks.md`; keep one helper per codebase. See `pubsub-firestore-patterns.md`
for the full Pattern A/B/C decision tree.

---

## P7 — Redis Lifecycle: `lifespan`, Never `on_startup`

**Rule:** Client initialization belongs in the app's `lifespan`. Handlers added with
`app.router.on_startup.append(...)` or `@app.on_event(...)` are **never called** once
`lifespan=` is set (executed on FastAPI 0.165: handler count 0); `on_event` is deprecated in FastAPI and removed from Starlette 1.0. `redis.asyncio.from_url`
is lazy, so a `try/except` around it never detects an outage: call `ping()` at boot. Never log the
URL (it carries credentials).

```python
# ✅ REQUIRED — in the app factory (full version: fastapi-architecture-and-config.md §3)
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cache = aioredis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    try:
        await cache.ping()
        app.state.cache = cache
    # optional dependency: degrade loudly; required one: re-raise
    except aioredis.RedisError as exc:
        logger.error("cache_unavailable", error_type=type(exc).__qualname__)
        await cache.aclose()
        app.state.cache = None
    try:
        yield
    finally:
        if app.state.cache is not None:
            await app.state.cache.aclose()

# ❌ BANNED — startup hook beside lifespan= (silently never runs)
app.router.on_startup.append(_startup_redis)

# ❌ BANNED — module-level pool (crashes on import if Redis is down) / bare except in shutdown
_redis = aioredis.from_url(settings.REDIS_URL)
```

Routes read the client from `request.app.state.cache` — never from a module-level variable.
Executed: with an unreachable host the service booted with `cache is None` and logged
`error_type=ConnectionError` without the host.

---

## P8 — Database Count Queries: `func.count()` Subquery

**Rule:** Never use `len(results)` to count rows — that fetches all rows first. Use SQLAlchemy
`func.count()` in a subquery so counting happens at the DB level.

```python
# ✅ REQUIRED
from sqlalchemy import func, select

count_q = select(func.count()).select_from(
    select(Entity).where(*filters).subquery()
)
total: int = (await session.execute(count_q)).scalar_one()

# ❌ BANNED — fetches all rows then counts in Python
all_rows = (await session.execute(select(Entity).where(*filters))).scalars().all()
total = len(all_rows)
```

---

## P9 — GCS URI Validation: Shared Helper + Bucket Allowlist

**Rule:** Any service that accepts a GCS URI from a client MUST validate it against a
bucket allowlist before using it. Never write the regex + allowlist check inline per service.
Centralize in a shared utility so bug fixes apply everywhere at once.

```python
# ✅ REQUIRED — shared utility + per-service wrapper
from functools import lru_cache
import re
import uuid

_GCS_URI_PATTERN = re.compile(
    r"^gs://(?P<bucket>[a-z0-9][a-z0-9\-]{1,61}[a-z0-9])/(?P<rest>.+)$"
)

@lru_cache(maxsize=1)
def _allowed_buckets() -> frozenset[str]:
    from .core.config import get_settings   # cached Settings; never a module-level instance
    return frozenset({get_settings().gcs_my_bucket})

def validate_gcs_uri(uri: str, path_prefix: str | None = None) -> None:
    """Validate GCS URI against service bucket allowlist.

    Raises ValueError with a descriptive message on any validation failure.
    """
    m = _GCS_URI_PATTERN.match(uri)
    if not m:
        raise ValueError(f"Invalid GCS URI format: {uri!r}")
    bucket = m.group("bucket")
    if bucket not in _allowed_buckets():
        raise ValueError(f"Bucket {bucket!r} not in allowlist")
    if path_prefix and not m.group("rest").startswith(path_prefix):
        raise ValueError(f"URI must start with gs://{bucket}/{path_prefix}")

# ❌ BANNED — inline regex redefined per service file
_GCS_URI_RE = re.compile(r"^gs://...")  # duplicates shared utility
```

---

## P10 — Shared Auth Helpers: No Local Reimplementation

**Rule:** Never define local `_uid()`, `_db_uid()`, `_role()`, or `_actor_id()` functions
in individual service route files. Extract to a shared auth module used across all services.

```python
# ✅ REQUIRED — import from shared module
# your shared package
from shared.auth.route_helpers import get_actor_id, get_db_uid, get_role, get_uid

# ❌ BANNED — local reimplementation per service
def _uid(current_user: dict) -> str:
    uid = current_user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Missing uid")
    return uid
```

**Pre-commit gate:**
```bash
grep -rn "def _uid\|def _db_uid\|def _role\|def _actor_id" \
  src/*/api/routes/ --include="*.py" → must return 0
```

---

## P11 — No Hardcoded URLs, Project IDs, or Bucket Names

**Rule:** Every URL, project ID, or bucket name that differs between environments MUST
come from environment variables. Hardcoded defaults in `core/config.py` silently route to
wrong resources in staging/production.

```python
# ✅ REQUIRED — env-varying values are required, no default (fail at startup if absent);
# anything carrying a credential is SecretStr (P2)
class Settings(BaseSettings):
    database_url: SecretStr     # required — no default; differs per env; holds a password
    google_cloud_project: str   # required — no default
    email_from: str             # required — domain differs per env

# ❌ BANNED — hardcoded GCP project ID silently routes to wrong project
class Settings(BaseSettings):
    google_cloud_project: str = "my-project-dev"

# ❌ BANNED — localhost fails inside Docker Compose (resolves to the container itself)
    redis_url: str = "redis://localhost:6379/0"

# ❌ BANNED — os.getenv sentinel fallback bypasses Pydantic validation
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or "my-project"
```

**Pre-commit gate:**
```bash
# Hardcoded localhost for services that differ between environments
grep -rn '"redis://localhost\|"http://localhost' src/*/core/config.py → must return 0

# os.getenv with sentinel fallback in service code
grep -rn 'os\.getenv.*or\s*"' src/ --include="*.py" \
  | grep -v "test_\|#" → must return 0
```

---

## P12 — DRY Shared Utilities: No Inline Duplication of Shared Logic

**Rule:** Any logic that exists in a shared service library MUST be imported from there.
Never define local copies. Common targets for duplication:

- GCS URI validation (P9 above)
- Pub/Sub `topic_path` builder
- Auth helpers (P10 above)

```python
# ✅ REQUIRED — import shared Pub/Sub topic path builder
from shared.utils.pubsub_utils import topic_path as _build_topic_path   # your shared package

def _topic_path(topic: str) -> str:
    return _build_topic_path(get_settings().google_cloud_project, topic)

# ❌ BANNED — inline f-string that duplicates shared utility
def _topic_path(project_id: str, topic: str) -> str:
    return f"projects/{project_id}/topics/{topic}"
```

---

## New Service Checklist (run before opening any PR adding a new backend service)

```
□ P1: /internal/* endpoints use timing-safe comparison, refuse an empty secret at construction — no bare != against secrets
□ P2: core/config.py — required fields have no default; secrets are SecretStr with Field(min_length=32)
□ P3: Every .py file uses logger = structlog.get_logger(__name__) — zero log = structlog occurrences
□ P4: Routes contain zero session.add/commit/rollback calls — service layer owns all mutations
□ P5: Pub/Sub publisher wrapped in @lru_cache(maxsize=1) factory
□ P6: All fire-and-forget publishes go through the retained-task helper — zero bare create_task, zero await publish at route/service level
□ P7: Redis lifecycle in lifespan with ping() — zero on_startup/on_event/router.on_startup
□ P8: Count queries use func.count() subquery — zero len(results.all()) patterns
□ P9: Any GCS URI input validated against bucket allowlist before use
□ P10: Auth helpers imported from shared module — zero local reimplementations
□ P11: No hardcoded URLs, project IDs, or bucket names in config.py — all from env vars
□ P12: No inline duplication of shared utilities (GCS regex, topic path builders, auth helpers)
□ All pre-commit grep gates above pass before opening PR
```

---

## Modified Service Checklist (run on every PR touching an existing backend service)

```
□ Changed file respects all patterns above — run the relevant grep gates
□ New endpoint with /internal/ → P1 gate (timing-safe secret comparison)
□ New config field that is required → P2 gate (no str|None=None)
□ New module-level logger → P3 gate (logger = structlog.get_logger(__name__))
□ New DB write in route → P4 gate (must move to service layer)
□ New Pub/Sub publish → P5 (singleton) + P6 (retained task) gates
□ New Redis usage → P7 gate (lifespan + ping, app.state)
□ New count query → P8 gate (func.count() subquery)
□ New GCS URI input → P9 gate (validate against allowlist before use)
□ New auth helper → P10 gate (import from shared, not local def)
□ New config field with URL, project ID, or bucket → P11 gate (from env, not hardcoded)
□ New duplication of shared logic → P12 gate (import from shared utilities)
```
