# Agentic AI Testing Patterns

Agent-specific tests for LangChain v1 / LangGraph services. Canonical homes, not restated here:

- Test layers (unit / workflow / contract / live golden / E2E), the `ScriptedModel` base and R1–R4 tiers: `eval-guide/reference/pytest-harness.md`.
- Retrieval metric formulas (Recall@K, Precision@K, MRR, nDCG): `llm-evaluation/reference/evaluation-metrics.md` §2.
- Real-PostgreSQL fixtures and pytest-asyncio loop scope: `python-testing-patterns/reference/postgres-integration-testing.md`.
- RAG eval sets and gates: `rag-evaluator`.

Every pattern below was executed (Python 3.14, langchain 1.2.8, langgraph 1.0.7, PostgreSQL 16) with scripted models. Mocked tests prove wiring and control flow; they are never evidence of live-provider behaviour.

REMOVED from the previous version: `AsyncMock` LLMs (they accept any call, so a wrong `bind_tools`/structured-output wiring still passes), a "use `MemorySaver` in tests, never a real DB" rule (checkpointer and store wiring bugs only show against PostgreSQL), state fields `iteration_count`/`thread_id` passed by the test, and a stream test that only checked the content type.

## Scripted model: agent-specific traps

Use `ScriptedModel` from `pytest-harness.md` (subclass of `GenericFakeChatModel` whose `bind_tools` returns `self`). Two traps found while executing these tests:

| Trap | Symptom | Fix |
|---|---|---|
| `GenericFakeChatModel` cannot stream messages that carry `tool_calls` | `stream_mode="messages"` raises "No generation chunks were returned" or drops the tool calls | Construct with `disable_streaming=True` in stream tests (whole messages are emitted); real providers stream chunks, so cover chunk handling with a live smoke test |
| Scripted iterator exhausted | `StopIteration` surfaces as an opaque runtime error mid-graph | Script exactly the calls the test expects; for loop tests use `iter([tool_call() for _ in range(50)])` |

## Workflow tests through the real route

Test through FastAPI with the real lifespan, a real PostgreSQL checkpointer/store, and an overridden principal dependency. This exercises scope injection, thread keys, limits and error mapping in one place.

```python
def make_app(messages: Iterator[AIMessage], *, steps: int = 12, timeout: float = 5.0, stream: bool = True) -> FastAPI:
    def build(cp: AsyncPostgresSaver, store: AsyncPostgresStore) -> Any:
        return create_agent(ScriptedModel(messages=messages, disable_streaming=not stream),
                            tools=[lookup_order], context_schema=RequestCtx, checkpointer=cp, store=store)

    app = create_app(Settings(_env_file=None, database_url=DB, checkpoint_db_uri=DB, chat_model="fake:scripted",
                              agent_timeout_s=timeout, max_graph_steps=steps), build)
    def principal(request: Request) -> Principal:          # typed: FastAPI injects Request by annotation
        return Principal(org_id=request.headers["x-org"], user_id=request.headers["x-user"])

    app.dependency_overrides[get_principal] = principal
    return app


async def call(app: FastAPI, path: str, body: dict[str, Any], user: str = "u1") -> httpx.Response:
    async with app.router.lifespan_context(app):                      # runs the async-with checkpointer setup
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post(path, json=body, headers={"x-org": "org-a", "x-user": user})
```

`create_app`, `Principal`, `RequestCtx`, `get_principal`: `agentic-templates-core.md`; `Settings`: `agentic-config-project.md`. `lookup_order` is a `ToolRuntime[RequestCtx]` tool (`agentic-templates-tools.md`).

| Test | Script | Assert |
|---|---|---|
| Scope injection | tool call, then answer | Tool saw the principal's `org_id`; model-visible schema has only business args |
| Recursion limit | 50 tool calls, `max_graph_steps=5` | `status == "ITERATION_LIMIT"` (not 500, not the last tool-call message) |
| Principal-bound threads | Alice writes to `thread_id=T`; Bob presents `T` | Checkpoint exists for `org-a:alice:T`, none for Bob's key |
| SSE framing | tool call, answer with `\n` | Every `data:` is JSON; exactly one `done`; newline survives; tool output absent |
| No exception text | model raises with a fake SSN in the message | HTTP body `{"detail": {"error_code": "AGENT_UNAVAILABLE"}}`; stream `event: error` with a code; SSN absent from body, stream **and logs**; exception type present in logs (positive control) |
| Deadline | model sleeps past `agent_timeout_s` | `status == "TIMEOUT"` |

All six passed against PostgreSQL 16.

## Control-flow tests (no HTTP)

| Test | How | Executed result |
|---|---|---|
| Model call cap | `ModelCallLimitMiddleware(run_limit=3, exit_behavior="error")`, looping script | `ModelCallLimitExceededError` after 3 calls; with default `"end"` the run ends on a library-text `AIMessage` (assert your route never returns it as an answer) |
| HITL approve/reject | `HumanInTheLoopMiddleware` or `interrupt()`; resume with `Command(resume=...)` on a **new** saver instance | Approve runs the tool once; reject and stale args hash run nothing (`agentic-streaming-hitl.md`) |
| Resume re-runs the node | Counter before `interrupt()` | Counter == 2 after one resume: no side effects before `interrupt()` |
| Idempotent writes | `run_once` with 5 concurrent callers | Effect ran once (`tool-execution-safety.md` §6) |
| Memory isolation | Two principals write/recall | No cross-principal recall; missing scope raises (`agentic-memory-systems.md`) |
| Tool retry failure payload | `ToolRetryMiddleware` default `on_failure` | Exception text reached the `ToolMessage` → use `"error"` or a typed callable (`agentic-templates-tools.md`) |

## Contract tests

- **Tool surface lock:** hash of `convert_to_openai_tool(t)` per tool equals the committed lock file; intentional changes update the lock in the same PR (`tool-execution-safety.md` §11).
- **No scope params** in any model-visible tool schema.
- **Allowlists resolve** for every agent (import the registry; do not regex the source).
- **Prompt ↔ tools:** tool names referenced in prompts are registered tools.
- **Structured output:** the JSON Schema of each response model is committed; a parse failure path exists and returns its typed code.

## Live golden and failure-matrix gate (before release)

Scripted tests cannot tell you whether the model chooses the right tool or grounds its answer. Before a release (and on every model or prompt version change):

1. **Live golden set** (R2/R3): real model, declared trials per case, thresholds per case type, results stored with model id + prompt version (`eval-guide`; ADK services: `adk-eval-guide`).
2. **Failure matrix replay**: with a live model, inject each dependency failure — tool timeout, tool `TOOL_UNAVAILABLE`, empty retrieval, checkpointer unavailable, provider 429/5xx, schema-invalid output — and assert the user-visible outcome is the documented typed status (`INSUFFICIENT_EVIDENCE`, `TIMEOUT`, ...) and never a fabricated answer.
3. A suite that skips for missing credentials reports **NOT RUN**, never PASS.

## pytest configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
testpaths = ["tests"]
markers = [
    "integration: needs PostgreSQL",
    "live: calls a real model provider (R2+); skipped => NOT RUN",
]
```

Run R1 locally and in CI: `uv run pytest -m "not live"`; live suites in their own job with credentials.

## Key Testing Rules

| Rule | Standard |
|------|----------|
| Model | `ScriptedModel` for R1; never `AsyncMock`; live only under the `live` marker |
| Checkpointer/store | Real PostgreSQL for route/HITL/memory tests; `InMemorySaver` only for pure graph-logic unit tests |
| Entry point | Route tests through the lifespan with an overridden principal |
| Required tests | Scope injection, recursion/timeout mapping, principal-bound threads, SSE framing, no exception text, HITL approve/reject, idempotency, contract lock |
| Evidence | Mocked tests prove control flow only; live golden + failure matrix gate releases |
| Metrics | Formulas from `llm-evaluation` §2, not reimplemented |
