# Python Service Observability (logs, traces, metrics, probes)

Non-AI FastAPI services. Snippets were executed with Python 3.14, structlog 26.1, opentelemetry-sdk 1.45.2 and instrumentation 0.66b2, SQLAlchemy 2.0.58 (2.1.9 where stated), FastAPI 0.165 and httpx 0.28 (nothing here needs more than FastAPI 0.135). For ADK agent tracing use `adk-observability-guide`.

## 1. Structured JSON logs

Deployed environments emit exactly ONE JSON object per line on stdout; local runs keep console rendering. Managed log platforms only parse single-line JSON into structured fields, and alerts filter on a stable event name. If no service configures JSON, every log-based alert can never match while nothing visibly fails.

| Field | Source |
|-------|--------|
| `event` | stable snake_case name; alerts and tests filter on it |
| `message` | copy of `event` for platforms that expect it |
| `severity` | mapped from level (`INFO`, `WARNING`, `ERROR`, ...) |
| `timestamp` | ISO-8601 UTC |
| `request_id`, `correlation_id` | `structlog.contextvars` (section 4) |
| `trace_id`, `span_id` | current OpenTelemetry span (section 3) |
| `error_type` | exception class name only (section 2) |

```python
# my_service/logging_setup.py
import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace
from structlog.typing import EventDict, WrappedLogger

_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
}


def add_trace_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def add_severity_and_message(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["severity"] = _SEVERITY.get(event_dict.pop("level", "info"), "DEFAULT")
    event_dict["message"] = event_dict["event"]  # `event` stays: alerts filter on it
    return event_dict


def exception_type_only(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace exc_info with the exception TYPE: str(exc) can echo request bodies (PII)."""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info:
        if isinstance(exc_info, BaseException):
            exc: BaseException | None = exc_info
        # stdlib records carry (type, value, traceback)
        elif isinstance(exc_info, tuple):
            exc = exc_info[1]
        else:  # exc_info=True
            exc = sys.exc_info()[1]
        event_dict["error_type"] = type(exc).__name__ if exc else "unknown"
    return event_dict


def configure_logging(*, json_logs: bool, level: str = "INFO") -> None:
    """structlog API + stdlib bridge: structlog and stdlib records render alike."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_trace_context,
        add_severity_and_message,
        exception_type_only,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,  # tests can reconfigure
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,  # stdlib records get the same fields
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # uvicorn installs its own handlers: hand them to root
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
```

Executed (real `uvicorn my_service.main:create_app --factory` run, `mypy --strict` and ruff clean): every line on stdout, including uvicorn's startup and access lines and a stdlib `logger.exception(...)`, parsed as ONE JSON object with `severity`, `message`, `event`, UTC `timestamp` and (inside a request) `request_id`; the exception text never appeared (only `error_type`). Processors are typed with `structlog.typing.EventDict`; the processor lists are `list[Any]` because structlog's `configure` does not accept the narrower list type under `mypy --strict`.

- Every deployed entrypoint must call `configure_logging(json_logs=True)`, at the top of `create_app()` (executed: with `--factory` every uvicorn line was JSON; called inside `lifespan` the first two startup lines stayed plain text). Add an architecture test that each `main.py` does (read the file or AST; give it a known-bad fixture), plus a rendered-line test that reads real stdout (`capsys`).
- Never log secrets, tokens or PII; never log a request body.
- This is the ONE logging stack of the toolkit: `structlog.get_logger(__name__)` with keyword fields everywhere, stdlib loggers bridged through `ProcessorFormatter` (the `foreign_pre_chain` gives them the same fields). Other references link here; do not add a second `log_exception` or a stdlib `log.error("... %s", ...)` style next to it. Calling a structlog-style `logger.error("evt", k=v)` on a plain stdlib logger raises `TypeError`.
- Re-check the uvicorn logger names against your pinned uvicorn: the loop that hands `uvicorn*` handlers to the root logger is what makes its lines JSON.

## 2. PII-safe exception logging

`str(exc)`, `repr(exc)`, `f"{exc}"`, `exc.args[0]`, `exc_info=True` and `logger.exception()` all put the exception MESSAGE in the log. Validation errors echo the offending request body. Log the type and non-PII identifiers through one helper:

```python
def log_exception(
    logger: Any, event: str, exc: BaseException, *, level: str = "error", **ids: Any
) -> None:
    """The one sanctioned way to log a handled exception: type + non-PII ids only."""
    getattr(logger, level)(event, error_type=type(exc).__name__, **ids)
```

`level` defaults to `error`: pass `"warning"` (or `"info"`) for an expected 4xx domain error so alerts on ERROR count only real faults (`fastapi-error-handling.md` section 2 does this for `AppError` below 500).

Executed: an exception carrying a fake SSN is logged through the helper and through `exc_info=True`; the SSN appears nowhere in the output (positive control: the SSN WAS in the exception).

AST gate covering every syntactic form (executed: `mypy --strict` and ruff clean; clean file exit 0; a file with `str(exc)`, `%s`, f-string, `exc.args[0]`, `logger.exception`, `exc_info=True` produced 6 findings, exit 1; no files exit 2):

```python
"""Flag a stringified exception reaching a logger call. usage: check_log_pii.py <file.py>..."""
import ast
import sys
from pathlib import Path

LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "msg"}


def findings(path: str) -> list[str]:
    tree = ast.parse(Path(path).read_text(), path)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}
    out: list[str] = []
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        f = call.func
        if not (isinstance(f, ast.Attribute) and f.attr in LOG_METHODS):
            continue
        if f.attr == "exception":
            out.append(f"{path}:{call.lineno}: logger.exception() logs the message and traceback")
        for kw in call.keywords:
            if kw.arg == "exc_info":
                out.append(f"{path}:{call.lineno}: exc_info= attaches the exception text")
        for arg in [*call.args, *(k.value for k in call.keywords if k.arg != "exc_info")]:
            safe = {id(a) for c in ast.walk(arg) if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name) and c.func.id == "type" for a in c.args}
            for n in ast.walk(arg):
                if isinstance(n, ast.Name) and n.id in names and id(n) not in safe:
                    out.append(f"{path}:{call.lineno}: exception '{n.id}' passed to a log call")
                    break
    return out


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(2)                                  # scanning nothing is a failure
    found = [line for p in sys.argv[1:] for line in findings(p)]
    sys.stdout.write("".join(f"{line}\n" for line in found))
    sys.exit(1 if found else 0)
```

Limit: it tracks names bound by `except ... as name` (`msg = str(exc); logger.error(msg)` is NOT caught: executed, 2 of 3 forms found); an exception passed around under another name is not seen. Allow-list genuinely infrastructure-only sites (no user input) with a marker comment and review each. Do not rely on grep for this: the forms differ too much.

## 3. Tracing: wire explicitly, then PROVE spans exist

```python
# anchored: probes and metrics produce no spans
EXCLUDED = r"^[a-z]+://[^/]+/(health|metrics)$"

# section 4; inside create_app(), after the app is built
app = App(lifespan=lifespan)
# None = global provider
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls=EXCLUDED)
# async engines: pass .sync_engine
SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
HTTPXClientInstrumentor().instrument()
```

- Instrument the app INSTANCE at construction, and give `create_app()` a `tracer_provider` parameter so the test below can inspect the REAL stack. Global instrumentors only affect objects created after the call.
- Exclude probes and metrics with an anchored regex (executed: with `excluded_urls` set, `/health` produced no span and `/n` did).
- Propagate W3C trace context across async boundaries: `opentelemetry.propagate.inject(carrier)` into message attributes on publish, `extract(carrier)` on consume. HTTP clients get it from the httpx instrumentor. Set explicit timeouts on outbound clients; retry only idempotent calls.
- Version coupling is the trap. The instrumentation packages declare the framework versions they support. Executed: with SQLAlchemy 2.1.9 and instrumentation 0.66b2, `instrument()` logged `SQLAlchemyInstrumentor only instruments "sqlalchemy >= 1.0.0, < 2.1.0" ... nothing can be instrumented` and emitted NO database span, while the HTTP span still appeared and every functional test stayed green. With SQLAlchemy 2.0.58 the database span appeared. Pin the framework and the instrumentors together in the lock and test for spans. Template pairing: `sqlalchemy==2.0.x` (2.0.58 was the latest 2.0 patch when validated) with a one-line comment in `pyproject.toml` that DB-span instrumentation currently supports `< 2.1`; move to 2.1 only when the instrumentation release you pin supports it, and let this test say so:

```python
@pytest.fixture
def exporter() -> tuple[InMemorySpanExporter, TracerProvider]:
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    return exp, provider


async def test_real_app_emits_http_span_and_500_carries_request_id(
    exporter: tuple[InMemorySpanExporter, TracerProvider], test_settings: Settings
) -> None:
    exp, provider = exporter
    # the REAL factory, never a bare FastAPI()
    app = create_app(test_settings, tracer_provider=provider)

    # test-only route, added inside the test
    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("test")

    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/boom")
        assert resp.status_code == 500 and resp.headers["x-request-id"]
        assert trace.SpanKind.SERVER in {s.kind for s in exp.get_finished_spans()}, (
            "no HTTP server span"
        )
    finally:
        FastAPIInstrumentor.uninstrument_app(app)


async def test_db_span_is_emitted(exporter: tuple[InMemorySpanExporter, TracerProvider]) -> None:
    exp, provider = exporter
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        assert any(
            (s.attributes or {}).get("db.system") or (s.attributes or {}).get("db.system.name")
            for s in exp.get_finished_spans()
        ), "no DB span"
    finally:
        await engine.dispose()
```

`test_settings` is the fixture of `python-testing-patterns/reference/postgres-integration-testing.md` section 4. Executed (SQLAlchemy 2.0.58, FastAPI 0.165, real `create_app()`): both tests pass; the DB-span test goes red on 2.1.9 (`no DB span`); the HTTP test goes red when the app class overrides `build_middleware_stack` (`no HTTP server span`, instrumentation skipped) and when `X-Request-ID` is not wired at all (`KeyError`); `mypy --strict` clean. Engine-scoped `instrument(engine=...)` needs no `uninstrument()` in teardown (calling it after a no-op instrument only logs a warning). Span names with SQLAlchemy 2.0.58: `connect`, `SELECT`, `GET /n http send` (x2), `GET /n`. The attribute key (`db.system` vs `db.system.name`) depends on the semantic-convention version; the test accepts both. Run this test in the same environment/image that ships: a test against a different lock than the image proves nothing.

## 4. Join the id namespaces (canonical request-id middleware)

`trace_id` (tracing), `request_id` (HTTP edge) and `correlation_id` (cross-service/message) must all appear in logs. This is the ONE request-id middleware of the toolkit
(`fastapi-error-handling.md` section 6 links here). It is pure ASGI, accepts an inbound id ONLY if it parses as a UUID (otherwise a client can inject fake fields into logs),
binds it to `structlog.contextvars`, stores it in `scope["state"]` (so `request.state.request_id` works), and sets `X-Request-ID` on EVERY response by wrapping `send`.

Three traps, all executed. (1) `app.add_middleware(...)` places the middleware INSIDE Starlette's `ServerErrorMiddleware`, which sends the framework's 500 with its own `send`:
the header is missing on exactly the responses you debug. (2) Overriding `FastAPI.build_middleware_stack` to wrap the stack fixes the header but makes `FastAPIInstrumentor.instrument_app(app)`
skip silently (`Skipping FastAPI instrumentation due to unexpected middleware stack`, ZERO server spans, every functional test green). Wrap in `__call__` instead: the instrumentor still finds
its expected stack, and the id middleware stays outermost. (3) `ServerErrorMiddleware` logs after an inner middleware has reset the contextvar; the catch-all handler therefore logs `request.state.request_id` explicitly.

```python
def _valid(raw: bytes | None) -> str | None:
    try:
        return str(uuid.UUID(raw.decode("ascii"))) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _valid(dict(scope["headers"]).get(b"x-request-id")) or str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id       # request.state.request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.clear_contextvars()


class App(FastAPI):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # outermost; do NOT override build_middleware_stack
        await RequestIdMiddleware(super().__call__)(scope, receive, send)
```

The catch-all handler (`unhandled`, registered with `add_exception_handler(Exception, ...)`) lives in `fastapi-error-handling.md` section 2: ONE body (the `INTERNAL_ERROR` envelope), it logs through `log_exception` with `request.state.request_id`.

Executed with a real `uvicorn ... --factory` process: `/ok` -> 200 with a fresh UUID in `X-Request-ID`; a route raising `RuntimeError("<fake SSN>")` -> 500 with `X-Request-ID` set, the body `requestId` equal to it, the `unhandled_error` line carrying the same `request_id` and `error_type=RuntimeError`, no SSN anywhere in the log; a valid inbound UUID was echoed, `not-a-uuid` replaced; `mypy --strict` and ruff clean. Build the app with `class App(FastAPI)` above and use `App(...)` in `create_app()`. Executed (SQLAlchemy 2.0.58, FastAPI 0.165): the real `create_app()` with this wrapper produced the HTTP server span AND `X-Request-ID` on the framework 500; the `build_middleware_stack` override produced zero spans.


## 5. Metrics

- Register custom metrics through one idempotent helper: a duplicate registration raises `ValueError` when modules are re-imported in a test process.
- Prefix names; label ONLY with bounded values (enums: outcome, role, tool). Never ids, emails or raw paths (unbounded cardinality). Use the route template, not the URL.
- One gate that every deployed service is actually scraped: a service with metrics code and no scrape config is unmonitored. Pin the instrumentator with the framework (section 3).

## 6. Probes and health: split by purpose

| Probe | Checks | Why |
|-------|--------|-----|
| Liveness | process only (event loop answers) | a dependency outage must not restart healthy instances |
| Startup | may include dependencies, generous `failureThreshold` | gates traffic until the app can serve |
| Readiness / dependency health | dependencies, each with its own timeout, run concurrently | pulls an unhealthy instance out of rotation without killing it |

Restart-storm behaviour for a dependency-checking liveness probe is a reasoned risk (not reproduced here). Health bodies carry a tri-state (`healthy`/`degraded`/`unhealthy`) and NEVER raw exception text, connection strings or hostnames.

Cloud Run flags, verified against `gcloud run deploy --help` (SDK 560): `--startup-probe` and `--liveness-probe` take `KEY=VALUE,...` with keys `initialDelaySeconds, timeoutSeconds, periodSeconds, failureThreshold, httpGet.port, httpGet.path, grpc.port, grpc.service, tcpSocket.port`. There is NO `--readiness-probe`, `--health-check-type`, `--liveness-probe-path`, `--startup-probe-path` or `--startup-probe-initial-delay` flag in that help output (searched `run deploy`, `beta`, `alpha`, `run services update`). The platform documents a readiness probe in the service YAML for some launch stages: verify the current stage before relying on it.

```bash
gcloud run deploy "$SERVICE" --image "$IMAGE" \
  --startup-probe 'httpGet.path=/health/ready,httpGet.port=8080,periodSeconds=5,failureThreshold=10' \
  --liveness-probe 'httpGet.path=/health/live,httpGet.port=8080,periodSeconds=30,failureThreshold=3'
```

## 7. Alert signals need a contract test

- Every alert filters on an event name: assert in CI that each such name is emitted by code (parse the infrastructure definition, grep the source, with a known-present control).
- Must-page events use a threshold of 0 (any occurrence); "silence" alerts bound their absence window by the platform maximum.
- Pin platform policy limits that `validate` cannot see (name lengths, window limits) with text-parsing tests that fail when the fix is reverted.

## 8. Production-readiness checklist (observability + operability)

- [ ] Web framework pinned `==`; lock fresh (`uv lock --check`); image installs `--locked`; base image by digest
- [ ] JSON logs in deployed envs; every entrypoint configures them (test); `severity`, `event`, `timestamp`, ids present
- [ ] No stringified exceptions in logs (AST gate green, known-bad control fails)
- [ ] Span test proves an HTTP span AND a DB span in the shipped environment
- [ ] `request_id` validated, echoed on every response (including the 500), bound to logs; contextvars cleared; catch-all handler logs `request.state.request_id`
- [ ] Liveness is process-only; readiness/startup cover dependencies; probe flags verified against the CLI help
- [ ] Alert event names emitted and tested; metrics labels bounded; service is scraped
- [ ] Shared (not per-process) storage for rate limits and other cross-instance state
- [ ] Migration job runs before the rollout and aborts the release on failure
- [ ] Running image digest/revision recorded; rollback = traffic pin, rehearsed
- [ ] No performance claim without a measurement; per-feature budgets as CI thresholds where feasible; say which perf/fuzz checks are NOT automated
