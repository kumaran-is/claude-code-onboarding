# Runtime lifecycle: surfaces, streams, cancel, reconnect

This file covers what the server and the clients do from stream open to surface delete, including when messages arrive partial, duplicated or out of order. The server-side stream rules (cancel the upstream on disconnect, one terminal frame, shielded writes, heartbeats) live in [server-stream-lifecycle.md](../../streaming-protocols/reference/server-stream-lifecycle.md). This file applies them to A2UI v0.9.

Evidence: the reference backend's stream tests pass. They include a real uvicorn server where the client disconnects mid-stream and then resumes with `Last-Event-ID`. All 20 invalid fixtures are rejected with their expected codes. **DOCUMENTED AND TESTED** unless a row says otherwise.

## Surface lifecycle

| Message | Server-side rule (enforced before streaming) | Error code |
|---|---|---|
| `createSurface` | `catalogId` must be the catalog this server serves; `surfaceId` must not already exist | `UNSUPPORTED_CATALOG`, `DUPLICATE_SURFACE` |
| `updateComponents` | Surface exists; components are upserted by `id`; at most `maxComponentsPerSurface` | `SURFACE_NOT_FOUND`, `TOO_MANY_COMPONENTS` |
| `updateDataModel` | Surface exists; `path` (JSON Pointer, default `/`) set to `value`; no `value` deletes the key | `SURFACE_NOT_FOUND` |
| `deleteSurface` | Surface exists; state and the rendered-by-us entries are removed | `SURFACE_NOT_FOUND` |
| End of generation | Every surface with components has `root`; every `child`/`children` resolves; no cycles; depth ≤ `maxDepth` | `MISSING_ROOT`, `DANGLING_REFERENCE`, `CYCLE`, `MAX_DEPTH_EXCEEDED` |

The server folds each surface's state in a `SurfaceStore`. That one structure orders messages, drives the graph check, produces the re-sync snapshot, and records which actions were rendered.

## Partial, duplicate and out-of-order messages

| Situation | Server | Client |
|---|---|---|
| Partial (progressive) rendering: components arrive across several `updateComponents` | Allowed. Graph completeness is checked at the end of generation, not per message | Render what has arrived; a child that is still missing shows as a placeholder, not an error |
| Truncated frame (half a JSON object) | Never emitted: the gate validates the whole message first | Reject the frame (`INCOMPLETE_FRAME` in `fixtures/streams/truncated-frame.jsonl`) and keep applied surfaces |
| Duplicate `createSurface` | Rejected; send `deleteSurface` first | Reject; do not reset the surface |
| Duplicate `updateComponents` with the same ids | Idempotent upsert | Idempotent upsert |
| Update before create (out of order) | Rejected (`SURFACE_NOT_FOUND`); the server orders messages per surface | Reject; never buffer and reorder (`fixtures/streams/out-of-order.jsonl`) |
| Unknown or wrong version (`v0.8`, `1.0`, `v0.9.1`, missing) | `UNSUPPORTED_VERSION` / `MALFORMED_MESSAGE`; never best-effort | Same; stop applying the stream and show an error with retry |

Clients replay `fixtures/streams/*.jsonl` and compare against `*.expect.json` (errors per line, final state), so all three platforms behave the same.

## Stream framing (plain A2UI over SSE)

```
id: 45d261f755a91c43:1
data: {"version": "v0.9", "createSurface": {...}}

id: 45d261f755a91c43:2
data: {"version": "v0.9", "updateComponents": {...}}

event: done
data: {}
```

- One A2UI message per default `message` event, JSON-encoded. Event ids are `<streamId>:<seq>`, opaque to clients.
- Exactly one terminal frame: `done`, or `error` with `{"code": ...}` (`STREAM_TIMEOUT`, a contract code). Never exception text.
- `resync` (below) is the only other named event.
- **LF-only framing.** sse-starlette 3.7.1 defaults to `\r\n`. Set `sep="\n"` on the response **and** on every `ServerSentEvent`; the response-level `sep` alone does not change `ServerSentEvent` frames. `@ag-ui/client` 1.0.5 `HttpAgent` splits frames on `/\n\n/` only, so CRLF breaks every AG-UI run with a JSON parse error. Tested: the stream test asserts there is no `\r` in the body, and it fails when CRLF is restored.
- Headers `Cache-Control: no-store`, `X-Accel-Buffering: no`; ping every 15 s; `send_timeout=10` s against stuck clients; total budget `stream_budget_s` below the platform request timeout.

## Cancellation

The generation is owned by the response generator. When the client disconnects, sse-starlette closes the generator, generation stops, and the `finally` block records it:

```python
outcome = "cancelled"  # stays "cancelled" if the client leaves (generator closed mid-stream)
try:
    async with asyncio.timeout(budget_s):
        ...
        while session.next_index < len(scenario):
            if await request.is_disconnected():
                return
            ...
            yield frame(message)
        outcome = "complete"
        yield ServerSentEvent(event="done", data="{}")
except ContractError as err:
    outcome = "error"
    yield ServerSentEvent(event="error", data=json.dumps({"code": err.code}))
finally:
    if outcome == "cancelled":
        registry.cancelled += 1  # generation stopped; resumable from session.next_index
```

The test opens a stream on a real server (300 ms per message), reads one event, and closes the connection. It then asserts `registry.cancelled == 1` and that generation stopped before the end. When generation calls a real model, close the model stream in this `finally` block (`await model.aclose()`) so token billing stops too. Never run generation in a detached task.

## Reconnect and re-sync

Each stream session keeps a **bounded** ring buffer of the last `resume_window` events (64 by default) plus the folded `SurfaceStore`. The session table is bounded too (`max_streams`, LRU).

| Client sends | Server does |
|---|---|
| `Last-Event-ID` within the window | Replays the buffered events after that id, then resumes generation from where it stopped. No gap, no duplicates (tested) |
| `Last-Event-ID` older than the window | Sends `event: resync` `{"reason": "RESUME_WINDOW_EXCEEDED"}`, then a **full surface replay**: `createSurface` + one `updateComponents` with every component + `updateDataModel` at `/` for each live surface, then continues |
| Unknown id, expired session, or another user's stream id | Starts a fresh stream from the beginning. A user can never attach to someone else's session (tested) |

Client handling of `resync`: delete every surface owned by this stream, then apply the replay. A browser `EventSource` sends `Last-Event-ID` on its own. A `fetch`-based reader (needed for `Authorization` headers) or the Flutter client must store the last id and send it in the header. Send renderer capabilities again on reconnect ([genui-a2ui-transport.md](../../flutter-genui/reference/genui-a2ui-transport.md)).

## Timeouts and retries

| Where | Setting |
|---|---|
| Server stream budget | `asyncio.timeout(stream_budget_s)` → terminal `error` `STREAM_TIMEOUT` |
| Client connect / idle timeout | No event (data or ping) for 2× the ping interval → reconnect with `Last-Event-ID` |
| Client retry | Exponential backoff with a cap and jitter. Streams retry freely. Actions retry **only** with the same `Idempotency-Key` |
| Action request | Do not retry on 4xx. On a 5xx or network error, retry with the same key; the server replays and does not run the action again |

## Bounded buffers (reference defaults)

| Buffer | Bound |
|---|---|
| Action body | 16 KiB (`413`) |
| AG-UI run input | 64 KiB |
| A2UI message | catalog `maxMessageBytes` (256 KiB) |
| Components per surface | 200; surfaces per stream 32 |
| Resume window | 64 events per stream; 256 streams |
| Rendered-by-us registry | 2048 components per user (LRU) |
| Idempotency store / audit ring | 4096 each |

## Cleanup

- `deleteSurface` removes server state and rendered-by-us entries. The client disposes the surface (Flutter: `processor.dispose()` when the conversation closes).
- Sessions fall out of the bounded table (LRU). A later reconnect gets a fresh stream, never stale state from another session.
- Pending confirmation dialogs leave `pending` once confirmed, cancelled or failed. Production expires them with a TTL as well (**RECOMMENDED PRACTICE**, not in the reference).
- Multi-instance deployments keep session buffers in a shared store, or use sticky routing. The reference is single-process (**RECOMMENDED PRACTICE**).

## Version policy at runtime

The wire version is pinned to `v0.9` (`x-genui.acceptedWireVersions`). Any other version is rejected explicitly, on both the stream gate and the action path, and is tested for `v0.8`, `1.0` and `v0.9.1`. A v1.0 migration is a coordinated catalog and renderer release ([catalog-contract.md](catalog-contract.md)), never a per-message fallback.
