# A2UI over AG-UI

A2UI and AG-UI solve different problems. A2UI v0.9 is the **payload**: the surfaces, components, data model and user actions defined in the catalog. AG-UI is an **agent event protocol** covering runs, text messages, tool calls, state and activities. AG-UI can carry A2UI messages. It does not replace them, and the catalog and validation rules do not change.

## Versions and sources

| Item | Version | How it was verified |
|---|---|---|
| `ag-ui-protocol` (Python) | 1.0.0 (`PROTOCOL_VERSION = "1.0"`) | Wheel source read: `ag_ui/_generated/models.py`, `ag_ui/core/version.py`, `ag_ui/encoder/encoder.py` |
| `@ag-ui/core`, `@ag-ui/client`, `@ag-ui/encoder` | 1.0.5 | `npm view` (2026-11-23) |
| `@ag-ui/a2ui-middleware` | 0.0.16 (peer `@ag-ui/client >=1.0.0`) | `npm pack`; `dist/index.d.ts` and `dist/index.js` read |
| Reference backend `/agui` | uses `ag-ui-protocol==1.0.0` | pytest: every emitted event parses back as `ag_ui.core.Event` |

## When AG-UI is not needed

Use plain A2UI over SSE (`GET/POST /a2ui/stream`, one A2UI JSON message per `data:` line) when any of these is true:

- The client is a renderer only (it shows surfaces and posts actions) with no chat transcript, tool-call UI or shared agent state.
- The client is Flutter. `a2ui_flutter` consumes A2UI messages directly ([genui-a2ui-transport.md](../../flutter-genui/reference/genui-a2ui-transport.md)), and reading AG-UI would mean an adapter that you build and test yourself.
- The backend does not already speak AG-UI.

Use AG-UI when a web client already runs a CopilotKit or AG-UI client, or needs runs, text deltas, tool calls and A2UI surfaces on one stream.

| Transport | Fits | Notes |
|---|---|---|
| SSE (A2UI per event) | Default for all three platforms | `Last-Event-ID` resume; see [runtime-lifecycle.md](runtime-lifecycle.md) |
| SSE (AG-UI events) | Web clients on CopilotKit or `@ag-ui/client` | A2UI goes inside `ACTIVITY_SNAPSHOT` (below) |
| WebSocket | Server push to an idle client, or full duplex | Authenticate before `accept`; see the [streaming-protocols](../../streaming-protocols/SKILL.md) skill |
| Plain HTTP JSON | Action responses, one-shot surfaces | `POST /actions` returns JSON, not a stream |
| NDJSON | Replay, eval and debugging fixtures | `fixtures/streams/*.jsonl` |

## AG-UI events the adapter uses

All names were read from `ag_ui/_generated/models.py` (`EventType` enum). Fields are snake_case in Python and camelCase on the wire (`model_dump_json(by_alias=True)`).

| Event | Fields set | Purpose |
|---|---|---|
| `RUN_STARTED` | `thread_id`, `run_id`, `protocol_version=PROTOCOL_VERSION` | Opens the run. The SDK does not fill `protocol_version`; its docstring says producers must send it explicitly |
| `ACTIVITY_SNAPSHOT` | `message_id`, `activity_type`, `content`, `replace` | Carries A2UI messages |
| `CUSTOM` | `name`, `value` | App extension: the action result (`genui.action_result`) |
| `RUN_FINISHED` | `thread_id`, `run_id` | Closes a successful run |
| `RUN_ERROR` | `message`, `code` | Closes a failed run with a fixed code, never exception text |

The 1.0 SDK no longer has the `THINKING_*` events (`ag_ui/core/events.py` docstring). Do not emit them.

## The A2UI-in-AG-UI mapping (official, SOURCE-PROVEN)

An official mapping exists in `@ag-ui/a2ui-middleware` 0.0.16. These are the exported constants and the behaviour of `createA2UIActivityEvents`:

| Constant | Value |
|---|---|
| `A2UIActivityType` | `"a2ui-surface"` |
| `A2UI_OPERATIONS_KEY` | `"a2ui_operations"` |
| messageId | `a2ui-surface-<surfaceId>` (or with a tool-call id when the middleware wraps a render tool) |
| User action inbound | `RunAgentInput.forwardedProps.a2uiAction.userAction` = `{name, surfaceId, sourceComponentId, context, timestamp}` |

Each snapshot has `replace: true`, and its `content.a2ui_operations` holds **every** operation so far for that surface, not a delta. A consumer can replay any single snapshot into a fresh renderer. The middleware defaults to `version: "v0.9"` unless the registered catalog declares `protocolVersion: "1.0"`. This contract pins v0.9, so never declare 1.0 in the catalog context.

The reference backend writes the same shape directly, without the TypeScript middleware (Python, tested):

```python
from ag_ui.core import PROTOCOL_VERSION, ActivitySnapshotEvent, RunFinishedEvent, RunStartedEvent

A2UI_ACTIVITY_TYPE = "a2ui-surface"      # @ag-ui/a2ui-middleware 0.0.16: A2UIActivityType
A2UI_OPERATIONS_KEY = "a2ui_operations"  # @ag-ui/a2ui-middleware 0.0.16: A2UI_OPERATIONS_KEY

yield _encode(RunStartedEvent(thread_id=thread_id, run_id=run_id, protocol_version=PROTOCOL_VERSION))
ops: dict[str, list[dict[str, Any]]] = {}
for message in scenario:                       # the agent's validated A2UI output
    contract.validate_server_message(message)  # same gate as the plain SSE path
    store.apply(message)
    key = next(iter(k for k in message if k != "version"))
    surface_id = message[key]["surfaceId"]
    ops.setdefault(surface_id, []).append(message)
    yield _encode(ActivitySnapshotEvent(
        message_id=f"a2ui-surface-{surface_id}",
        activity_type=A2UI_ACTIVITY_TYPE,
        content={A2UI_OPERATIONS_KEY: ops[surface_id]},
        replace=True,
    ))
yield _encode(RunFinishedEvent(thread_id=thread_id, run_id=run_id))
```

`_encode` writes `data: <event.model_dump_json(by_alias=True, exclude_none=True)>` as `ServerSentEvent(sep="\n", ...)`. Frames must be LF-only: `@ag-ui/client` 1.0.5 `HttpAgent` splits on `/\n\n/` (SOURCE-PROVEN, `dist/index.mjs`), so sse-starlette's default `\r\n` breaks every run with "Unexpected non-whitespace character after JSON". This is the wire form of `ag_ui.encoder.EventEncoder` (`text/event-stream`, one JSON event per `data:` line). The test `test_agui_stream_carries_a2ui_as_activity_snapshots` parses every frame with `TypeAdapter(ag_ui.core.Event)`. It checks that the run opens with `RUN_STARTED` (`protocolVersion "1.0"`) and closes with `RUN_FINISHED`, and that the last snapshot's operations equal the fixture.

## Actions over AG-UI: the same pipeline

`forwardedProps.a2uiAction.userAction` is wrapped as `{"version": "v0.9", "action": userAction}`. It goes through the same `ActionService.handle` as `POST /actions`, with `runId` as the idempotency key. A forged action on the AG-UI path gets the same `403 FORBIDDEN` as on `/actions` (test `test_agui_forwarded_action_uses_same_pipeline`). This wiring is **RECOMMENDED PRACTICE**. The middleware only converts the action into a user message for the agent, and it does no authorization. Never let a model-visible message stand in for the server's authorization decision.

## Flutter and AG-UI

Flutter does not consume AG-UI or CopilotKit streams. If a backend speaks only AG-UI, build an app-owned adapter that:

1. reads `ACTIVITY_SNAPSHOT` with `activityType == "a2ui-surface"`;
2. because snapshots replace, diffs or re-creates the surface (delete it and replay `a2ui_operations`); and
3. feeds the messages to `MessageProcessor`.

Test that adapter with `flutter test` against recorded AG-UI fixtures. Device UI tests use Maestro only. Until that adapter exists and is tested, point Flutter at the plain A2UI SSE endpoint.

## Transport authentication

- Bearer token on every stream and action request. 401 includes `WWW-Authenticate: Bearer`. Native `EventSource` cannot set headers, so web clients use `fetch`-based SSE readers, or a same-site cookie session with CSRF protection on `POST`.
- Decide authentication and authorization before the streaming response is returned. A generator that is never iterated cannot enforce anything.
- CORS lists exact origins per topology (`allow_origins`, never `*` with credentials). Native mobile clients send no `Origin`.
- The AG-UI `threadId` and `runId` come from the client. They are correlation ids, not identity, and are never used for authorization.
