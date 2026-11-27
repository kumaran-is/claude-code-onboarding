# Agentic AI Streaming & Human-in-the-Loop

Patterns for real-time token streaming and durable human approval in LangGraph / LangChain v1 agents.
Every snippet below was executed on langchain 1.2.8 + langgraph 1.0.7 (+ langgraph-checkpoint-postgres 3.2.1 against PostgreSQL 16); HITL approve/reject, resume on a fresh PostgreSQL saver and `Task.cancel()` of an in-flight call re-run on langchain 1.5.2 + langgraph 1.2.24, with a scripted fake model; live-provider streaming was not exercised.

Transport rules (SSE framing, proxy buffering, reconnection, `Last-Event-ID`) live in the `streaming-protocols` skill. This file covers what an **agent** is allowed to put on that transport.

## Token Streaming (internal use)

```python
async def stream_tokens(graph, message: str, config: RunnableConfig):
    async for chunk, metadata in graph.astream(
        {"messages": [HumanMessage(content=message)]}, config=config, stream_mode="messages"
    ):
        # create_agent names its model node "model"; hand-built graphs use your node name
        if isinstance(chunk, AIMessage) and metadata.get("langgraph_node") == "model" and chunk.text:
            yield chunk.text
```

`AIMessageChunk` is a subclass of `AIMessage`; a model with `disable_streaming=True` (or most fake test models) emits whole `AIMessage` objects, so filter on `AIMessage`.

## Event Streaming (debug / internal dashboards only)

`astream_events(version="v2")` exposes `on_tool_start` inputs, `on_tool_end` outputs and every model's tokens, including routers and graders. **Never forward it to an end user**: tool arguments and outputs may contain other records, scope ids or unredacted data, and side-effect confirmations would arrive before the canonical write succeeds. Use it in internal tooling, behind authorization, or reduce tool events to an allow-listed status label (`{"type": "status", "step": "searching"}`).

## State Update Streaming

```python
async for update in graph.astream(inputs, config=config, stream_mode="updates"):
    for node_name, state_update in update.items():   # {node_name: partial_state}
        logger.debug("node_done", node=node_name, keys=list(state_update))
```

## FastAPI SSE Endpoint (agent SSE contract)

Contract: every `data:` line is JSON (raw text with a newline breaks SSE framing); typed events `content` / `done` / `error`; **exactly one** terminal event; `error` carries an opaque code, never `str(exc)`; only user-facing node text is streamed; scoping and safety decisions are made before the `StreamingResponse` is returned. Route-level dependencies (`PrincipalDep`, `scoped_thread_id`, `RequestCtx`, `_run_config`) are defined in `agentic-templates-core.md`.

```python
USER_FACING_NODES = frozenset({"model"})  # never tools, routers, graders


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/agent/stream")
async def stream_agent(
    body: AgentRequest, principal: PrincipalDep, graph: GraphDep, settings: SettingsDep
) -> StreamingResponse:
    # Decide here, not in the generator: it may never run if the client disconnects.
    thread_id = body.thread_id or uuid.uuid4()
    thread_key = scoped_thread_id(principal, thread_id)
    ctx = RequestCtx(org_id=principal.org_id, user_id=principal.user_id)

    frames: asyncio.Queue[str | None] = asyncio.Queue(maxsize=32)   # bounded: backpressure on a slow client

    async def run_graph() -> None:
        try:
            async with asyncio.timeout(settings.agent_timeout_s):
                async for chunk, meta in graph.astream(
                    {"messages": [HumanMessage(body.message)]},
                    _run_config(settings, thread_key),
                    context=ctx,
                    stream_mode="messages",
                ):
                    if (
                        isinstance(chunk, AIMessage)
                        and isinstance(meta, dict)
                        and meta.get("langgraph_node") in USER_FACING_NODES
                        and chunk.text
                    ):
                        await frames.put(sse("content", {"text": chunk.text}))
            await frames.put(sse("done", {"thread_id": str(thread_id)}))
        except GraphRecursionError:
            await frames.put(sse("error", {"code": "ITERATION_LIMIT"}))
        except TimeoutError:
            await frames.put(sse("error", {"code": "TIMEOUT"}))
        except Exception as exc:  # noqa: BLE001 - CancelledError (task.cancel below) is not caught
            log_exception(logger, "agent_stream_failed", exc, thread_id=str(thread_id))
            await frames.put(sse("error", {"code": "STREAM_ERROR"}))
        await frames.put(None)                       # end of stream (not reached when cancelled)

    async def events() -> AsyncIterator[str]:
        run = asyncio.create_task(run_graph())       # owned by this stream (streaming-protocols rule 2)
        try:
            while (frame := await frames.get()) is not None:
                yield frame
        finally:
            run.cancel()   # disconnect / stop: cancels the in-flight model call so it does not finish and bill

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Executed checks (fake model + PostgreSQL checkpointer): a reply containing `\n` arrives intact in one JSON frame; the tool's output string never appears in the stream; the stream ends with one `done`; a model exception whose message contained an SSN produced exactly `event: error` / `data: {"code": "STREAM_ERROR"}` and the log line carried only `error_type`. Local `stream_mode="messages"` on langchain 1.5.2 / langgraph 1.2.24 emitted one `content` frame then `done` with a recording callback (not LangSmith, not a live provider).

- Client disconnect: do NOT iterate `graph.astream(...)` directly inside the response generator and rely on Starlette to cancel it. Starlette cancels a disconnected stream through an anyio cancel scope, and on langgraph 1.0.7 and 1.2.24 that does not reach LangGraph's in-flight model call: the call ran to completion (and would bill) after the client left; only the next node was skipped. Cancelling the task that runs `astream` with `asyncio.Task.cancel()` does cancel the call. Hence the owned task + queue above, cancelled in `finally`. Executed (uvicorn 0.54, Starlette 1.10, slow fake model, client gone at 0.5 s): owned-task pattern → model call cancelled, never completed; naive direct-`astream` generator → model call completed. Keep a disconnect test like this in your suite.
- `CancelledError` is a `BaseException`, so `except Exception` in `run_graph` does not swallow the cancel. Do not catch `BaseException` here.
- Never retry after the first byte was sent: emit `error` and let the client re-request (see `agentic-error-handling.md`).
- `log_exception` is the Phase 2 helper (`deployment-ci-cd/reference/python-observability.md` section 2).

## Human-in-the-Loop (HITL)

Rules:
1. The decision is a **typed value** passed with `Command(resume=...)`, never a substring of a chat message (`"not approved"` contains `"approved"`).
2. Pending approvals live in the **checkpointer** (PostgreSQL in production), never in process memory: an in-process `asyncio.Event` is lost on restart, lives on one replica, and holds an HTTP request open.
3. The approver's identity and authority come from the approver's verified token on a **separate authenticated endpoint**, never from the payload; the approver must hold the authority the action requires.
4. Bind the decision to what was shown: hash the proposed action + args; execute only if the hash still matches.
5. On resume the interrupted node **re-runs from its first line** (verified: a counter before `interrupt()` reached 2). Keep side effects out of the code before `interrupt()`; put them in a later node, idempotency-keyed (`tool-execution-safety.md`).

### Option A — `create_agent` + `HumanInTheLoopMiddleware` (tool-call approval)

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.types import Command

agent = create_agent(
    model, tools=[search_docs, delete_record],
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={"delete_record": {"allowed_decisions": ["approve", "reject"]}},
    )],
    checkpointer=checkpointer,           # durable saver from the app lifespan
)
out = await agent.ainvoke({"messages": [...]}, cfg)
pending = out["__interrupt__"][0].value  # {"action_requests": [{"name": "delete_record", "args": {...}}], ...}
# ... persist an approval record, notify the queue, return 202 to the caller ...

# later, from the approver's authenticated endpoint:
await agent.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg)   # or {"type": "reject"}
```

Executed: `approve` runs the tool exactly once; `reject` never runs it.

### Option B — `interrupt()` inside a gated node (custom graphs)

```python
@dataclass(frozen=True)
class Decision:
    approved: bool
    approver_id: str   # from the approver's verified token
    args_hash: str     # hash of what the approver saw


def request_approval(state: DeleteState) -> Command[str]:
    args = {"record_id": state["record_id"]}
    expected = args_hash("delete_record", args)          # sha256 of canonical JSON
    raw = interrupt({"action": "delete_record", "args": args, "args_hash": expected})
    decision = Decision(**raw)
    if decision.approved is True and decision.args_hash == expected:
        return Command(goto="execute_delete", update={"log": [f"approved_by={decision.approver_id}"]})
    return Command(goto=END, update={"status": "REJECTED"})

# resume: await graph.ainvoke(Command(resume=asdict(decision)), cfg)
```

Executed against PostgreSQL: the run paused, the saver connection and graph object were discarded ("restart"), a new saver + graph resumed the same `thread_id` with `Command(resume=...)` and the delete ran once; a rejection or a stale `args_hash` ran nothing.

Static breakpoints (`compile(interrupt_before=[...])`) are for debugging. Resume them with `graph.ainvoke(None, cfg)`. **Invoking again with a new message does not resume**: it starts a new step from `START`, re-runs the model and pauses again before the same node, so the approved action never executes (verified).

### Approval record, expiry and escalation

Store one row per pending approval next to the checkpoint:

| Field | Purpose |
|---|---|
| `thread_key`, `interrupt_id` | which checkpoint to resume |
| `action`, `args_hash` | what was proposed; resume only if unchanged |
| `required_authority` | role/permission the approver must hold |
| `owner_queue`, `due_at` | who must act and by when |
| `exception_type` | why a human is needed (approval, low confidence, budget exhausted, safety); drives priority |
| `status` | `PENDING` / `APPROVED` / `REJECTED` / `EXPIRED` / `SUPERSEDED` |
| `requested_by`, `decided_by`, `decided_at` | audit trail (ids only) |

- A sweep job marks overdue rows `EXPIRED` and resumes the thread with a rejection, so the run reaches a typed terminal state instead of waiting forever.
- A later human change to the same record marks pending AI approvals `SUPERSEDED` (version check before write).
- Notifications (queue, email, chat) carry ids and a link, never the record content.
- The queue is an operating mode, not an error sink (guardrails G5): it has a named owner, SLA, capacity, priority classes with safety first, overflow and load-shedding rules, and enough context on the record that the reviewer decides without re-running the AI flow. Owner, SLA and capacity are organisational decisions recorded in the Decision Record.

## Streaming Mode Selection Guide

| Mode | Use Case | What You Get | Expose to end users? |
|------|----------|--------------|----------------------|
| `stream_mode="messages"` | Chat UIs | `(chunk, metadata)` per token | Yes, filtered by `langgraph_node` |
| `stream_mode="updates"` | Progress | `{node: partial_state}` | Only allow-listed status labels |
| `stream_mode="values"` | Debugging | Full state after each step | No |
| `astream_events(version="v2")` | Internal tooling | All events incl. tool I/O | No |

## Key Rules

| Rule | Standard |
|------|----------|
| SSE format | `event: <type>` + `data: <json>` + blank line; JSON-encode every payload |
| Terminal event | Exactly one: `done` OR `error`; never `done` after `error` |
| Error events | Opaque code; log type + ids server-side; no exception text |
| Content filter | Only user-facing node text; no tool args/outputs, router or grader tokens |
| HITL | `interrupt()` / `HumanInTheLoopMiddleware` + `Command(resume=typed)`; never new-message "resume" |
| Checkpointing | Durable saver (PostgreSQL) for HITL; `InMemorySaver` only in tests |
| Approvals | Persisted record with owner, authority, due time, args hash; separate authenticated endpoint |
| Deadline | `asyncio.timeout(settings.agent_timeout_s)` around the run; approval waits are NOT request-bound |
| Buffering | Disable proxy buffering (`X-Accel-Buffering: no`); see `streaming-protocols` |
