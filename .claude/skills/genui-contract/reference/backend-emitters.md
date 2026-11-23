# Backend emitters: from agent output to validated A2UI on the wire (v1.0 and v0.9)

> **Pins and proven wire version per platform:** see [compatibility-matrix.md](compatibility-matrix.md) (source of truth). Serve each client only the version it declares and is proven on. Every renderer and backend needs a contract gate in front of `@a2ui/web_core` (action allowlist, URL schemes, one version per stream, reject legacy `{"path"}` bindings in 1.0 with `SCHEMA_INVALID`), because web_core 0.16.1 and `@a2ui/agent` 0.2.1 accept these.

An emitter is the server code between the agent and the transport. It takes candidate A2UI messages, validates them against the shared contract, folds them into surface state, records what was rendered for action binding, and frames them for SSE or AG-UI. Whatever framework produced the candidates, they never reach a client unvalidated.

| Part | Evidence |
|---|---|
| FastAPI emitter (contract gate, SSE framing, AG-UI framing) | **DOCUMENTED AND TESTED**: reference backend, 60 pytest passing; ruff and mypy --strict clean |
| Google ADK hand-off | **DOCUMENTED BUT NOT TESTED** here: uses `Runner.run_async` as documented in the [google-adk](../../google-adk/SKILL.md) skill ([adk-core-patterns.md](../../google-adk/reference/adk-core-patterns.md), [adk-fastapi-integration.md](../../google-adk/reference/adk-fastapi-integration.md), ADK 1.29) |
| LangGraph hand-off | **DOCUMENTED BUT NOT TESTED** here: uses `graph.astream(..., stream_mode="updates")` as documented in [agentic-streaming-hitl.md](../../agentic-ai-dev/reference/agentic-streaming-hitl.md) |
| Node / TypeScript emitter | **DOCUMENTED AND TESTED** (Node 26 sandbox): `@a2ui/agent` 0.2.1 + `@ag-ui/encoder` 1.0.5, 21 LIVE-PROTOCOL tests. See section 7 |

## Pinned versions (reference backend)

`fastapi==0.165.0`, `uvicorn==0.54.0`, `sse-starlette==3.7.1`, `pydantic==2.14.4`, `jsonschema==4.26.0`, `ag-ui-protocol==1.0.0`; dev: `pytest==9.2.0`, `pytest-asyncio==1.5.0`, `httpx==0.28.1`, `ruff==0.17.6`, `mypy==2.4.1`; Python 3.14 via `uv`.

## 1. Load the contract once, from the shared files

The emitter binds the official wire schema's `catalog.json` slot to the canonical catalog. A component that is not in the catalog therefore fails schema validation, not just a name check:

```python
registry = Registry().with_resources([
    (server["$id"], Resource.from_contents(server)),                       # vendor/a2ui-v0_9/server_to_client.json
    (A2UI_BASE + "common_types.json", Resource.from_contents(common)),
    (A2UI_BASE + "catalog.json", catalog_resource),                        # "catalog.json#/$defs/anyComponent" -> ours
    (catalog["$id"], catalog_resource),
])
server_validator = Draft202012Validator(server, registry=registry)
```

Action specs (`sideEffect`, `risk`, `requiresIdempotencyKey`, `requiresHumanApproval`, `payloadSchema`), limits and forbidden patterns are read from the catalog's `x-genui` block. They are never retyped in code.

## 2. The gate every message passes

```python
def validate_server_message(self, message: Any) -> None:
    """Gate every A2UI message BEFORE it is streamed. Invalid model output never reaches a client."""
    if not isinstance(message, dict) or sum(k in message for k in MESSAGE_KEYS) != 1:
        raise ContractError("MALFORMED_MESSAGE", "a message is an object with exactly one operation body")
    self.check_version(message)                     # missing -> MALFORMED_MESSAGE, other -> UNSUPPORTED_VERSION
    create = message.get("createSurface")
    if isinstance(create, dict) and create.get("catalogId") != self.catalog_id:
        raise ContractError("UNSUPPORTED_CATALOG", "createSurface names a catalog this server does not serve")
    body = message.get("updateComponents")
    if isinstance(body, dict) and isinstance(body.get("components"), list):
        self._precheck_components(body["components"])  # UNKNOWN_COMPONENT, FUNCTION_ACTION_FORBIDDEN, ACTION_NOT_ALLOWED
    if len(json.dumps(message, separators=(",", ":")).encode()) > self.max_message_bytes:
        raise ContractError("MESSAGE_TOO_LARGE", ...)
    error = next(iter(self.server_validator.iter_errors(message)), None)
    if error is not None:
        raise ContractError("SCHEMA_INVALID", f"{error.json_path}: {error.message[:200]}")
    _check_strings_and_depth(message, self.forbidden, self.max_depth)  # UNSAFE_CONTENT, MAX_DEPTH_EXCEEDED
```

Then `SurfaceStore.apply(message)` checks ordering (`SURFACE_NOT_FOUND`, `DUPLICATE_SURFACE`). At the end of generation, `check_complete()` checks the graph (`MISSING_ROOT`, `DANGLING_REFERENCE`, `CYCLE`). The test `test_every_invalid_fixture_is_rejected` runs all 20 `fixtures/invalid/*.json` through this path and asserts each one's exact `expectedError`.

## 3. Frame it (SSE)

```python
while session.next_index < len(scenario):        # replace `scenario` with the agent's candidate iterator
    if await request.is_disconnected():
        return
    message = scenario[session.next_index]
    contract.validate_server_message(message)      # gate
    session.store.apply(message)                   # order + state (for re-sync)
    rendered.record(message)                       # rendered-by-us registry (for action binding)
    session.next_index += 1
    yield frame(message)                           # ServerSentEvent(data=json.dumps(message), id="<stream>:<seq>")
```

The route returns `EventSourceResponse(gen, ping=15, send_timeout=10, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})`. Authentication and scenario authorization finish before the response is returned. The AG-UI framing of the same messages is in [ag-ui-transport.md](ag-ui-transport.md).

**When the gate fails mid-stream:** send one terminal `event: error` with the contract code and stop. Do not skip the bad message and continue, because later messages may depend on it. Log the code and stream id, never the model output. If the agent can retry, re-run it with the error code as feedback, bounded to N attempts, before any message from that attempt is sent.

## 4. Hand-off from Google ADK (DOCUMENTED BUT NOT TESTED here)

Pattern: the agent produces A2UI through a **tool** or **structured output**, not free text. The emitter takes candidates from the final events and puts them through the gate.

- Run with `runner.run_async(user_id=..., session_id=..., new_message=...)` inside `asyncio.timeout(...)`, as in [adk-fastapi-integration.md](../../google-adk/reference/adk-fastapi-integration.md). `user_id` is the authenticated principal, never a request field.
- Let a render tool (for example a `FunctionTool` whose argument is the list of A2UI messages) be how the agent emits UI. The tool returns its argument, the emitter reads the tool result from the event stream, and each message goes through `validate_server_message`. On a contract error the tool returns the error code, so the model can correct itself within a capped number of retries.
- Forward only those validated messages. Raw tool calls, tool results and internal agents' output never reach the client (rule from the google-adk skill).
- Review with `adk-reviewer`.

## 5. Hand-off from LangGraph (DOCUMENTED BUT NOT TESTED here)

- A node writes candidate messages into a state key (for example `a2ui: list[dict]`). Stream with `graph.astream(inputs, config=config, stream_mode="updates")` ([agentic-streaming-hitl.md](../../agentic-ai-dev/reference/agentic-streaming-hitl.md)) and put each new candidate through the gate before yielding it.
- High-risk actions that need an interrupt map onto the server-held confirmation in [action-security.md](action-security.md). The graph never executes an approval-gated side effect from model output alone.
- Review with `agentic-ai-reviewer`.

## 6. What an emitter must never do

- Stream a message before validating it, or "repair" an invalid one without validating it again.
- Accept a `catalogId` or `version` from the model that the client did not advertise.
- Put secrets, internal ids or exception text in any message or terminal frame.
- Let model text become a URL, HTML, script or authorization input ([action-security.md](action-security.md)).

## 7. Node / TypeScript emitter with `@a2ui/agent` 0.2.1 (v1.0 and v0.9)

The Python reference above is a **v0.9** emitter. For a v1.0 emitter in Node, the official TypeScript agent SDK `@a2ui/agent` 0.2.1 targets v0.9 and v1.0 (its README). APIs below were read from the package and executed:

| API | Use |
|---|---|
| `CatalogConfig.fromPath(path)` | Load a 1.0 catalog (the document states `protocolVersion` and `catalogId`) |
| `CatalogConfig.fromPath(path, [], 'v0.9', catalogId)` | Load a v0.9 catalog (the v0.9 document states neither) |
| `new A2uiGenerator([catalog])` | One generator **per protocol version**; mixing versions on one generator is an error |
| `readRendererCapabilities(metadata, '1.0' \| 'v0.9')` | Read the client's declared capabilities; throws `A2uiCatalogError` when malformed |
| `generator.createProcessor(caps)` → `processor.catalogs` | Catalogs negotiated for this client |
| `validatePayload(processor.catalogs, messages)` | Stateless structural check before streaming; throws `A2uiValidationError` |
| `processor.parseResponse(text)` / `processor.openStream()` | Parse model output (Direct JSON or Express format) into validated messages |
| `RendererToAgentMessageProcessor` | v1.0 only: checks inbound `action`, `error`, `callAgentFunction` messages ("A message whose `version` isn't `'1.0'` is an `A2uiValidationError`") |

Wire shapes the emitter writes (verified by `validatePayload` against the shared catalogs):

```js
// 1.0: one message may create the surface with its components (and dataModel) inline
[{ version: '1.0', createSurface: { surfaceId, catalogId: CATALOG_1_0, components } }]
// v0.9: create first, then components
[{ version: 'v0.9', createSurface: { surfaceId, catalogId: CATALOG_0_9 } },
 { version: 'v0.9', updateComponents: { surfaceId, components } }]
```

```js
import { EventEncoder } from '@ag-ui/encoder';
import { EventType } from '@ag-ui/core';
import { validatePayload } from '@a2ui/agent';
import { A2UIActivityType, A2UI_OPERATIONS_KEY } from '@ag-ui/a2ui-middleware';

validatePayload(negotiated.processor.catalogs, ops);   // fail closed: RUN_ERROR, never a partial surface
const encoder = new EventEncoder({ accept: req.headers.accept });
res.writeHead(200, { 'content-type': encoder.getContentType(), 'cache-control': 'no-store' });
res.write(encoder.encode({ type: EventType.RUN_STARTED, threadId, runId }));
res.write(encoder.encode({ type: EventType.ACTIVITY_SNAPSHOT, messageId: `a2ui-surface-${runId}`,
  activityType: A2UIActivityType, content: { [A2UI_OPERATIONS_KEY]: ops }, replace: true }));
res.end(encoder.encode({ type: EventType.RUN_FINISHED, threadId, runId }));
```

`validatePayload` is structural only: it accepted an off-allowlist action name, a `javascript:` URL and a v0.9 binding inside a 1.0 message ([action-security.md](action-security.md#catalog-validation-is-not-authorization)). Keep the policy gate from section 2 (allowlist, forbidden patterns, depth, size) in front of it.

Supply chain: `@a2ui/agent` 0.2.1 was published on 2026-11-23 by the a2ui-project maintainers (repository `github.com/a2ui-project/a2ui`). It has npm registry signatures but no SLSA provenance attestation, unlike `@ag-ui/*` 1.0.5. Pin it exactly. `npm audit` (2026-11-23) reports GHSA-mrhx-c7xc-m3w5 (high, `zod` < 4.6.6) through `@a2ui/web_core` 0.16.1, which bundles `zod` 3.25.76; no fixed version is available. Pin a top-level `zod` of 4.6.7 or later for your own code and track the advisory.

## Running the reference

```bash
cd <shared>/backend && uv sync
export GENUI_DEMO_TOKEN_USER_A=<random-16+> GENUI_DEMO_TOKEN_USER_B=<random-16+>
uv run pytest -q            # 60 passed
uv run ruff check . && uv run mypy genui_backend
uv run python -m genui_backend --mode shared
```
