# FastAPI Error Handling Patterns

Production-ready error handling for Python 3.14 + FastAPI. All retry and circuit breaker
patterns are async-safe — no `time.sleep()` in async routes.

> **Workspace rule:** NO silent failures, NO fallbacks, NO mock data on error.
> Every catch block MUST log AND either rethrow or return an explicit error state.
> See `code-standards.md §Error Handling`.
>
> **Logging rule:** on request paths never log `str(exc)`, `%s`/f-string of the exception,
> `exc_info=True` or `logger.exception(...)`: `ValidationError` and `IntegrityError` messages contain
> the submitted values (executed: an e-mail address and a unique-key value appeared in both).
> Log the exception **type** and non-PII ids through the one `log_exception` helper
> (`deployment-ci-cd/reference/python-observability.md` §2; handler-side rules in §6). Logging
> is `structlog` with the stdlib bridge, configured once as described there. Snippets below were
> executed on FastAPI 0.165 / Starlette 1.10 / Pydantic 2.14 / SQLAlchemy 2.1.

---

## Dependencies

```bash
uv add structlog tenacity circuitbreaker httpx   # then pin the resolved versions (templates guide)
```

---

## 1. Custom Exception Hierarchy

Domain-layer exceptions — HTTP translation happens at the FastAPI boundary only.
Services raise typed domain exceptions; never raise `HTTPException` inside services.
Messages are static or contain ids only — never submitted values.

```python
# src/my_service/core/exceptions.py
from typing import Any


class AppError(Exception):
    """Base exception for all application domain errors."""

    def __init__(self, message: str, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message, self.code, self.details = message, code, details or {}


class DomainValidationError(AppError):
    """Business-rule violation. Named to avoid colliding with pydantic.ValidationError."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message, "VALIDATION_ERROR", {"field": field} if field else {})


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} not found", "NOT_FOUND", {"resource": resource, "id": identifier}
        )


class ConflictError(AppError):
    """Operation conflicts with current state (e.g. duplicate)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "CONFLICT", details)


class ExternalServiceError(AppError):
    """A dependency (external API, payment gateway, ...) failed."""

    def __init__(self, message: str, service: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", {"service": service, **(details or {})})
        self.service = service
```

---

## 2. One error envelope for everything

Domain errors, `RequestValidationError`, `HTTPException` (including router 404/405) and a
catch-all `Exception` all use one body shape (same fields as `rest-design-principles.md`
"Error Response Format"), each carrying `requestId`. A custom envelope that covers only domain errors
leaves 422/404/405 in FastAPI's default shape. RFC 9457 `application/problem+json` is an
equally valid choice; pick one per service.

```python
# src/my_service/core/exception_handlers.py
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import AppError
from .logging import log_exception  # python-observability.md §2: the ONE helper

logger = structlog.get_logger(__name__)
_STATUS_BY_CODE = {
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "VALIDATION_ERROR": 422,
    "EXTERNAL_SERVICE_ERROR": 502,
}


def envelope(
    request: Request, status: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    response = JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "details": details,
            "timestamp": datetime.now(UTC).isoformat(),
            "path": request.url.path,
            "requestId": request_id,
        },
    )
    if request_id:
        # belt and braces: a plain FastAPI + add_middleware would miss the 500
        response.headers["X-Request-ID"] = request_id
    return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        status = _STATUS_BY_CODE.get(exc.code, 500)
        log_exception(
            logger, "app_error", exc, level="error" if status >= 500 else "warning", code=exc.code
        )
        return envelope(request, status, exc.code, exc.message, exc.details or None)

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default 422 echoes every offending "input" (passwords, tokens) into responses,
        # proxies and error trackers. Return loc/msg/type only.
        details = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        return envelope(request, 422, "VALIDATION_ERROR", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)  # also covers router 404 / 405
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        resp = envelope(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))
        resp.headers.update(exc.headers or {})  # keep WWW-Authenticate etc.
        return resp

    # catch-all: generic body, detail only in logs
    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # ServerErrorMiddleware runs this AFTER the request-id middleware reset its contextvar:
        # pass the id explicitly or the most important log line cannot be correlated (§6).
        log_exception(
            logger,
            "unhandled_error",
            exc,
            method=request.method,
            request_id=getattr(request.state, "request_id", None),
        )
        return envelope(request, 500, "INTERNAL_ERROR", "Internal server error")
```

Register once in the app factory (`fastapi-architecture-and-config.md` §3): `register_exception_handlers(app)`.
Never catch `AppError` subclasses inside route handlers. A tracebacks-in-responses flag, if you
need one, must be an explicit non-production setting; the default 500 body is generic.

Executed: default 422 body contained the submitted e-mail and password value, ours did not; domain
404, router 404, router 405 and an unhandled `RuntimeError("card ... declined")` all returned the
envelope with `requestId`, and the card text appeared in neither the body nor the logs. Starlette
re-raises after the catch-all responds, so the server still logs a traceback: scrub that sink.
Executed (§6 middleware): a request with a valid `X-Request-ID` that hit an unhandled error got the same id in
the response header, the body and the `unhandled_error` log line.

---

## 3. Service Layer — Using Domain Exceptions

Services raise typed exceptions. Never raise `HTTPException` here.

```python
# src/my_service/services/order_service.py
import structlog
from sqlalchemy.exc import IntegrityError

from .core.exceptions import ConflictError, ExternalServiceError, NotFoundError
from .core.logging import log_exception

logger = structlog.get_logger(__name__)


async def get_order(order_id: str, session: AsyncSession) -> Order:
    order = await session.get(Order, order_id)
    if not order:
        raise NotFoundError("Order", order_id)
    return order


async def create_order(data: CreateOrderRequest, session: AsyncSession) -> Order:
    try:
        order = Order(**data.model_dump())
        session.add(order)
        await session.commit()
        return order
    except IntegrityError as exc:
        await session.rollback()
        # the exception text contains the values
        log_exception(logger, "order_conflict", exc, order_ref=data.reference)
        raise ConflictError("Order already exists", details={"reference": data.reference}) from exc


async def charge_order(order: Order) -> PaymentResult:
    try:
        return await payment_client.charge(order.total)
    except PaymentClientError as exc:
        log_exception(logger, "payment_failed", exc, order_id=str(order.id))
        raise ExternalServiceError(
            "Payment processing failed",
            service="payment_service",
            details={"order_id": str(order.id)},
        ) from exc
```

---

## 4. Async Retry with Tenacity: transient failures only

Use `tenacity` (async-safe; **never `time.sleep()` in async routes**). Retry only what is transient
and make the decorated function raise the RAW client exception: wrapping every `httpx.HTTPError` in
one retried domain exception makes a 404 get retried and a non-idempotent POST get sent three times
(rules and jitter: `reliability-idempotency-retries-outbox.md` §3). Wrap into `ExternalServiceError`
AFTER the retry.

```python
# src/my_service/core/retry.py
from collections.abc import Awaitable, Callable

import httpx
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def _log_retry(state: RetryCallState) -> None:
    """tenacity's before_sleep_log needs a stdlib logger; this keeps the one structlog stack."""
    exc = state.outcome.exception() if state.outcome else None
    logger.warning(
        "retrying", attempt=state.attempt_number, error_type=type(exc).__name__ if exc else None
    )


def is_transient(exc: BaseException) -> bool:
    """Worth repeating: the network or an overloaded dependency, never a 4xx the caller caused."""
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE_STATUS


def with_retry[**P, R](
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: Callable[[BaseException], bool] = is_transient,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception(retry_on),
        before_sleep=_log_retry,
        reraise=True,  # MUST rethrow after max attempts: no silent fallback
    )
```

```python
# src/my_service/core/clients.py
# a structlog logger: log_exception(logger, event, exc, **ids)
logger = structlog.get_logger(__name__)


@with_retry()
async def _get_rate(client: httpx.AsyncClient, currency: str) -> float:
    resp = await client.get(f"/rates/{currency}")
    resp.raise_for_status()
    return float(resp.json()["rate"])


async def fetch_exchange_rate(client: httpx.AsyncClient, currency: str) -> float:
    try:
        return await _get_rate(client, currency)
    except httpx.HTTPError as exc:  # after the retry: a 404 was one call, a 503 three
        log_exception(logger, "exchange_rate_failed", exc, currency=currency)
        raise ExternalServiceError("Rate service unavailable", service="exchange_rate_api") from exc
```

Executed through `httpx.MockTransport` (`mypy --strict` and the lint baseline clean): 404 -> 1 call,
`ExternalServiceError`; `503, 503, 200` -> 3 calls, success. For production load add jitter and a total
window (`wait_exponential_jitter`, `stop_after_delay`: reliability §3).

---

## 5. Async Circuit Breaker

Prevents cascading failures when a dependency is down. Count dependency health only (5xx, transport
errors), never a caller's 4xx, and put the breaker **outside** the retry so one logical call is one count.

```python
# src/my_service/core/circuit.py
from collections.abc import Awaitable, Callable
from http import HTTPStatus

import httpx
from circuitbreaker import circuit  # type: ignore[import-untyped]  # no stubs or py.typed


def is_dependency_failure(exc_type: type[BaseException], exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    return isinstance(exc, httpx.TransportError)


def breaker[**P, R](
    service_name: str, failure_threshold: int = 5, recovery_timeout: int = 60
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    # failure_threshold: failures to open; recovery_timeout: seconds until a HALF_OPEN probe
    return circuit(  # type: ignore[no-any-return]
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=is_dependency_failure,
        name=service_name,
    )
```

```python
@breaker("payment_service")  # outermost: the attempts inside are ONE count
@with_retry()
async def _post_charge(
    client: httpx.AsyncClient, order_id: str, amount: Decimal, idempotency_key: str
) -> httpx.Response:
    resp = await client.post(  # retried only because the key makes a repeat safe:
        "/charge",
        json={"order_id": order_id, "amount": str(amount)},
        # a required parameter, so it cannot be forgotten
        headers={"Idempotency-Key": idempotency_key},
    )
    resp.raise_for_status()
    return resp


async def call_payment_service(
    client: httpx.AsyncClient, order_id: str, amount: Decimal, key: str
) -> PaymentResult:
    try:
        return PaymentResult(**(await _post_charge(client, order_id, amount, key)).json())
    except httpx.HTTPError as exc:
        log_exception(logger, "payment_call_failed", exc, order_id=order_id)
        raise ExternalServiceError(
            "Payment service unavailable", service="payment_service"
        ) from exc
```

Executed (threshold 3, `MockTransport`): three logical calls answered 503 sent 9 requests, all with the
same `Idempotency-Key`, then the breaker opened and the next call sent nothing; five 404s sent five
requests and left the breaker closed. Never put a POST without a key behind `with_retry`.
`circuitbreaker` 2.1.3 calls `asyncio.iscoroutinefunction`, which Python 3.14 reports as a
`DeprecationWarning` at decoration time: a suite run with `-W error` fails on import, so add a targeted
`filterwarnings` ignore for that message and watch for a fixed release.

> **Circuit open state:** `circuitbreaker` raises `CircuitBreakerError`. Add a handler returning `503`.

```python
# Add to register_exception_handlers()
from circuitbreaker import CircuitBreakerError

@app.exception_handler(CircuitBreakerError)
async def circuit_open_handler(request: Request, exc: CircuitBreakerError) -> JSONResponse:
    log_exception(logger, "circuit_open", exc)
    return envelope(request, 503, "SERVICE_UNAVAILABLE", "Service temporarily unavailable")
```

---

## 6. Request id: the handler-side contract

The canonical logging setup, `log_exception` and the pure-ASGI `RequestIdMiddleware` live in
`deployment-ci-cd/reference/python-observability.md` (§1, §2, §4). The handlers depend on three
behaviours of that middleware:

| Behaviour | Why the handlers need it |
|----------|--------------------------|
| It sets `scope["state"]["request_id"]` (so `request.state.request_id` works) | the envelope's `requestId` is `null` without it (executed) |
| It accepts an inbound id only if it parses as a UUID, else generates one | a junk `X-Request-ID: bad\r\nvalue` is replaced by a generated UUID |
| It sets `X-Request-ID` by wrapping `send`, and wraps the whole app in `App.__call__` | covers EVERY response, including the framework's 500 (executed) |

One hole remains on the unhandled-exception path, closed in the §2 handlers: the log line is written after the middleware reset its context, so the catch-all passes
`request_id=request.state.request_id` explicitly. Executed with a valid inbound id: header, body
`requestId` and the `unhandled_error` log line all carried it, and the `RuntimeError("card 4111 ...")`
text appeared in none of them.

Less diagnostic detail in logs is the trade-off; compensate with `requestId`, error type and stable
event names, and send tracebacks only to a scrubbed sink. Allow a documented marker for
infrastructure start-up diagnostics only.

---

## 7. Error Handling Rules

| Rule | Detail |
|------|--------|
| **Never raise `HTTPException` in services** | Services use domain exceptions; HTTP translation is the handler's job |
| **Never swallow exceptions** | Every `except` MUST log AND rethrow or raise domain error |
| **No fallbacks** | Returning empty list/None/default on error is forbidden (`code-standards.md`) |
| **Chain exceptions** | Use `raise NewError(...) from original_exc` to preserve traceback |
| **Async-safe retry** | `tenacity`, transient errors only, POST only with an idempotency key (§4); never `time.sleep()` in async routes |
| **Circuit breaker on external services** | Wrap all third-party HTTP clients |
| **Log at correct level** | 4xx expected errors → `INFO`/`WARNING`; 5xx → `ERROR` |
| **Never log sensitive data** | No passwords, tokens, PII in error details; no `str(exc)`, `exc_info=True` or connection URLs on request paths (`python-observability.md` §2) |
| **One envelope** | Domain, 422, HTTP and catch-all errors share one body; 422 never echoes `input` |

---

## 8. Testing Error Paths

`raise_app_exceptions=False` shows what a real client sees (the catch-all re-raises for the server log).
`Settings` and `create_app(settings)` come from the templates guide (the `settings` fixture below builds
explicit values, never the developer's `.env`); the test-only `/boom` route is added inside the test.

```python
# tests/test_error_handling.py
from collections.abc import AsyncIterator

import httpx
import pytest
import structlog
from httpx import ASGITransport, AsyncClient
from tenacity import wait_none

from my_service.core.exceptions import ExternalServiceError
from my_service.core.clients import _get_rate, fetch_exchange_rate   # the section 4 example
from my_service.main import create_app
from my_service.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    url = "postgresql+asyncpg://u:p@localhost/test"
    return Settings(_env_file=None, database_url=url, jwt_secret="j" * 32)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(settings), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_domain_error_is_404_envelope_not_500(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/orders/does-not-exist")      # the service raises NotFoundError
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"


async def test_422_never_echoes_submitted_values(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/signup", json={"email": "not-an-email", "password": 123456})
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
    assert "not-an-email" not in resp.text and "123456" not in resp.text


async def test_unhandled_error_is_generic_and_carries_the_request_id(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("card 4111 declined")

    rid = "11111111-2222-4333-8444-555555555555"
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    with structlog.testing.capture_logs() as logs:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/boom", headers={"X-Request-ID": rid})
    assert resp.status_code == 500 and resp.json()["code"] == "INTERNAL_ERROR"
    assert resp.headers["x-request-id"] == rid and resp.json()["requestId"] == rid
    logged = next(e for e in logs if e["event"] == "unhandled_error")
    assert logged["request_id"] == rid and "4111" not in str(logs) + resp.text


async def test_transient_failure_is_retried_and_4xx_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    # default backoff sleeps 1 s + 2 s
    monkeypatch.setattr(_get_rate.retry, "wait", wait_none())      # type: ignore[attr-defined]
    statuses = iter([503, 503, 200])
    calls: list[httpx.Request] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(next(statuses), json={"rate": 1.5})

    async with httpx.AsyncClient(transport=httpx.MockTransport(flaky), base_url="http://dep") as c:
        assert await fetch_exchange_rate(c, "USD") == 1.5
    # retried twice, succeeded on the third
    assert len(calls) == 3

    calls.clear()

    def not_found_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    not_found = httpx.MockTransport(not_found_handler)
    async with httpx.AsyncClient(transport=not_found, base_url="http://dep") as c:
        with pytest.raises(ExternalServiceError):
            await fetch_exchange_rate(c, "USD")
    # a 4xx is the caller's error: never repeated
    assert len(calls) == 1
```
