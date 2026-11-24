# Server-Side Stream Lifecycle (SSE and WebSocket)

> OPTIONAL extension. Load only when your service streams model output (SSE / HTTP streaming) or proxies a realtime session (WebSocket). A one-shot JSON endpoint needs none of this.

The protocol choice lives in `../SKILL.md`. This file covers what the SERVER must do so a stream never leaks money, data or half-finished actions. Principles first (any stack), then a Python/FastAPI implementation that was executed.

---

## 1. Rules (any stack)

| # | Rule | Why |
|---|------|-----|
| 1 | The upstream model call is owned by the stream: when the client goes away, the model call is cancelled on every exit path (`finally`). | A model call that outlives its client keeps billing tokens. |
| 2 | Never run the upstream call in a detached task (`create_task` with no owner, a queue pump, a thread) unless the stream's `finally` cancels it. | Executed: a detached pump kept producing tokens after disconnect (section 4). |
| 3 | Never catch `BaseException` / `CancelledError` without re-raising. Catch `Exception` at the stream boundary. | Cancellation is how the server tells your code the client left. |
| 4 | Every stream ends with exactly ONE terminal frame: `done` or `error`. Errors are in-band with a fixed code (the HTTP 200 is already sent). Never put `str(exc)` or provider text in a frame. | Clients need one unambiguous end; exception text leaks internals. |
| 5 | JSON-encode every `data:` payload. | Raw text containing a newline breaks SSE framing. |
| 6 | Make authentication, authorization, kill-switch and safety decisions, and log them, in the route BEFORE returning the response. | The generator may never be iterated (client gone before first byte). |
| 7 | Give the stream its own total time budget below the platform request timeout (Cloud Run's default request timeout is 300 s, max 3600 s, per its docs). | The platform cuts the connection without a terminal frame. |
| 8 | Do not act on partial structured output. Tool calls, JSON and side effects come only from the finalized, schema-validated message. A stopped or disconnected answer is stored `status="incomplete"` (or dropped) and never feeds actions, memory or eval sets as a completed answer. | Half a JSON object or half an instruction is not a smaller correct answer. |
| 9 | Writes in a `finally` that runs during cancellation must be shielded. | Executed: an unshielded `await` in `finally` was cancelled and the record was lost (section 4). |
| 10 | Heartbeat (SSE comment) at ≤ 15 s and below the tightest proxy idle timeout; send `X-Accel-Buffering: no`; detect stuck clients with a send timeout. | Proxies close idle streams and buffer by default. |
| 11 | A BFF / proxy hop authenticates, derives identity server-side (never from the body), holds the internal credential, propagates the request id, passes frames through as bytes, and maps ANY upstream connect/read/non-200 failure to one terminal `error` frame. | The browser must see the same contract whichever hop failed. |
| 12 | Kill switch: the disabled path returns the same contract in degraded form (one `error` frame with a fixed code), not a 5xx or a hang. | Clients handle one contract. |

---

## 2. SSE endpoint (FastAPI native `fastapi.sse`)

Default: FastAPI's own SSE (0.135+). Executed on Python 3.14.10, FastAPI 0.165.0, Starlette 1.10.0,
uvicorn 0.54.0 (`ruff`, `ruff format --check`, `mypy --strict` clean; tests run in-process and
against a real uvicorn). Names are substituted (`ChatRequest`, `model_stream`, `save_answer`, `ChatDelta`;
the kill-switch branch and `model.aclose()` are illustrative, the rest is the executed shape);
`log_exception` is the shared helper (`deployment-ci-cd/reference/python-observability.md` section 2).

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent

ChatUser = Annotated[Principal, Depends(require_scope("chat:write"))]   # 401/403 before the 200


@router.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(request: Request, req: ChatRequest, user: ChatUser) -> AsyncIterator[ServerSentEvent]:
    if not request.app.state.settings.chat_enabled:                    # kill switch: same contract
        yield ServerSentEvent(data={"code": "DISABLED"}, event="error")
        return
    model = model_stream(req)                      # async generator wrapping the provider stream
    parts: list[str] = []
    status = "incomplete"                          # stays incomplete on stop / disconnect / cancel
    try:
        async with asyncio.timeout(STREAM_BUDGET_S):          # < platform request timeout
            async for chunk in model:
                parts.append(chunk)
                yield ServerSentEvent(data=ChatDelta(delta=chunk), event="content")   # JSON-encoded
        status = "complete"                        # only now validate and act on the full message
        yield ServerSentEvent(data={}, event="done")
    except Exception as exc:  # noqa: BLE001 - stream boundary; NOT BaseException
        status = "error"
        log_exception(logger, "stream_failed", exc, subject=user.subject)
        yield ServerSentEvent(data={"code": "STREAM_ERROR"}, event="error")  # never str(exc)
    finally:
        await model.aclose()                       # cancels/finalizes the provider call
        with anyio.CancelScope(shield=True):       # this await runs while being cancelled
            await save_answer(req.message_id, "".join(parts), status)
```

The route is an async generator with `response_class=EventSourceResponse`. Dependencies (authn, authz)
run before the response starts, so a rejected caller gets a 401/403 status, not a stream (executed). No
`request.is_disconnected()` polling: on disconnect FastAPI cancels the producer task group and the
`finally` runs (executed against uvicorn: the producer counter stopped and the record was `incomplete`).

Native SSE facts (read from the installed 0.165.0 source and executed): `data` is always JSON-encoded
(`raw_data=` sends text as-is), the response sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`,
an idle stream gets a `: ping` comment every 15 s (fixed), the generator runs at most one item ahead of
the socket (buffer of 1), and a sync generator runs in a thread pool, where cancellation cannot reach it:
use `async def`. Typed items (`-> AsyncIterator[ChatDelta]`) are validated and documented in OpenAPI.

`model_stream` must cancel the provider HTTP stream when it is closed or cancelled: wrap the SDK's async iterator in `async with` / `try/finally` per the SDK docs. If the SDK only offers a blocking iterator, run it so that cancellation reaches it; a thread cannot be cancelled.

**When to use `sse-starlette` (3.7.1) instead:** you need a configurable ping interval or a
`send_timeout=` that tears down a stuck client (read from its installed source: default ping 15 s,
`ping=0` disables, always sets `X-Accel-Buffering: no`, a disconnect listener cancels the generator's task
group). Return `EventSourceResponse(event_stream(...), ping=..., send_timeout=...)` from a normal route and
keep the same `try/except/finally` body.

Starlette's `GZipMiddleware` excludes `text/event-stream` by default in Starlette 1.10 (`DEFAULT_EXCLUDED_CONTENT_TYPES`). Other compressors, CDNs and older pinned Starlette versions may still buffer: check yours.

**Testing cancellation.** Starlette 1.9+ `TestClient` cancels the request's app call (its cancel scope, `cancel_if_incomplete` in 1.10.0) when a client closes an
unfinished stream, so an in-process test cannot show a producer that outlives its client. Run the
disconnect test against a real uvicorn (a thread or subprocess on a free port) and assert that a
producer counter stops (section 4).

---

## 3. WebSocket admission and caps (realtime / voice)

Executed fixture, condensed (7 pytest cases pass with Starlette's `TestClient`; `ruff` and `mypy --strict` clean on the full module; `reauthorize_or_end` and `upstream_final` are placeholders that were not part of the run). Under uvicorn 0.54 a close before `accept()` reaches the client as an HTTP 403 handshake rejection (executed with the `websockets` client).

```python
@app.websocket("/ws/voice")
async def voice(ws: WebSocket) -> None:
    if PROTOCOL not in ws.scope.get("subprotocols", []):
        await ws.close(code=1008); return
    try:                                            # authenticate BEFORE accept: no paid session for anonymous callers
        principal = await authenticate(ws.headers.get("authorization", ""))
    except AuthError:
        await ws.close(code=1008); return
    if principal in ACTIVE:                         # one open stream per actor;
        await ws.close(code=1008); return
    ACTIVE.add(principal)                           # no await between check and claim
    try:
        await ws.accept(subprotocol=PROTOCOL)
        await run_attempt(Attempt(ws, attempt_id=new_attempt_id()))
    finally:
        ACTIVE.discard(principal)


async def run_attempt(att: Attempt) -> None:
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=QUEUE_MAX)      # bounded
    sender = asyncio.create_task(forward_upstream(queue))
    deadline, total = loop.time() + MAX_STREAM_S, 0
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                await att.end("LIMIT_EXCEEDED"); return
            try:
                async with asyncio.timeout(min(IDLE_S, remaining)):
                    msg = await att.ws.receive()
            except TimeoutError:
                await att.end("IDLE_TIMEOUT"); return
            if msg["type"] == "websocket.disconnect":
                return
            if (audio := msg.get("bytes")) is not None:           # audio = binary frames only
                total += len(audio)
                if len(audio) > MAX_FRAME_BYTES or total > MAX_STREAM_BYTES:
                    await att.end("LIMIT_EXCEEDED", close_code=1009); return
                try:
                    queue.put_nowait(audio)
                except asyncio.QueueFull:
                    await att.end("BACKPRESSURE", close_code=1013); return
            elif json.loads(msg.get("text") or "{}").get("type") == "stop":   # control = text frames
                await reauthorize_or_end(att)                     # token may have expired mid-stream
                await att.send("final", text=await upstream_final())
                await att.ws.close(code=1000); return
    finally:
        sender.cancel()                                           # upstream ends with the socket
```

`Attempt.send` adds `attempt` id and a monotonic `seq` to every server message so the client drops stale or out-of-order messages; `Attempt.end` sends one `error` frame with a fixed code (the client switches to text input) and closes.

| Control | Verified behaviour |
|---------|-------------------|
| No credential / wrong subprotocol | closed 1008 before accept |
| Second concurrent stream, same actor | closed 1008 |
| Frame > `MAX_FRAME_BYTES` | `error` `LIMIT_EXCEEDED` (seq 1), close 1009 |
| Upstream slower than input, queue full | `error` `BACKPRESSURE`, close 1013 |
| No frame for `IDLE_S` | `error` `IDLE_TIMEOUT` |
| `{"type":"stop"}` | `final` message, close 1000, claim released |

Cancel the producer from the receive loop, not from a failed send: run the producer in a task group
(or a task the handler owns), loop on `receive()` until `websocket.disconnect`, then cancel it in
`finally`. A producer that only notices `WebSocketDisconnect` at its next send keeps paying for upstream
work until then (Starlette 1.7+ raises `WebSocketDisconnected` for operations after a disconnect).

Notes:
- Browsers cannot set an `Authorization` header on a WebSocket. Issue a single-use ticket from an authenticated HTTP call (stored with a 30 s TTL), then in the handshake check `Origin` against an allowlist and consume the ticket atomically (`GETDEL`) before `accept()`: `python-dev/reference/fastapi-auth-security.md` §3a. Never put a bearer token in the query string (it lands in access logs).
- `ACTIVE` is per process. With more than one instance, claim in a shared store (atomic set-if-absent with a TTL) and release in `finally`.
- No in-band sentinels such as `b"END"` inside the audio channel: a stop is a text control frame.
- Logs carry attempt id, fixed code, byte counts and durations only: never transcript text, audio, provider error text or `str(exc)`.

---

## 4. Evidence from the executed fixture

Client disconnects after the first content frame; the fake model records cancellation. Rows 1-7: sse-starlette 3.7.1 fixture; the rows after them: native `fastapi.sse` and WebSocket fixture.

| Case | Upstream cancelled | Tokens produced after disconnect | Answer record |
|------|-------------------|----------------------------------|---------------|
| `EventSourceResponse` + pattern above (token gap 0.2 s and 3 s) | yes, ~10 ms | 0 | `incomplete` |
| Plain `StreamingResponse` generator (token gap 0.2 s and 3 s) | yes, ~10 ms | 0 | (not persisted) |
| Same pattern, unshielded `await save_answer(...)` in `finally` | yes | 0 | **lost** (write cancelled) |
| ANTI-PATTERN: upstream in a detached `create_task` feeding a queue | **no** (never) | 6 in 1 s, still running | — |
| LangGraph `graph.astream` iterated directly in a `StreamingResponse` generator (langgraph 1.0.7 and 1.2.24, slow fake model) | **no**: the in-flight model call completed after disconnect | — | — |
| Same, `astream` in a task the generator owns, `task.cancel()` in `finally` (`agentic-ai-dev/reference/agentic-streaming-hitl.md`) | yes | — | — |
| Fake model raises mid-stream | — | — | frames: 2 `content` + exactly 1 `error` `{"code":"STREAM_ERROR"}`; exception text absent from frames and logs |
| Native `fastapi.sse` route above, real uvicorn, client closes after frame 1 (FastAPI 0.165.0) | yes | 0 (counter constant for 0.3 s) | `incomplete` |
| Same, upstream moved into a detached `create_task` | **no** | counter kept rising | test fails (negative control) |
| WebSocket producer cancelled from the receive loop, real uvicorn | yes | 0 | `cancelled` |
| WebSocket producer NOT cancelled on disconnect: in-process `TestClient` | — | 0 (the test client cancelled the app call) | test **passed**: a false green |
| Same mutation against real uvicorn | **no** | kept producing | test fails (negative control) |

What this does NOT prove: behaviour behind your proxy/CDN, other ASGI servers (uvicorn 0.54 advertises ASGI spec 2.3, so Starlette uses a disconnect listener; servers on spec ≥ 2.4 surface the disconnect when the next send fails), or a real provider SDK's cancellation. Re-run the same test against your stack: start a stream against a slow fake model, close the client after the first chunk, assert the fake's cancel flag is set within 2 s and its token counter stops.
