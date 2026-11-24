# Agentic AI — Error Recovery & Design Decisions

Retry, failover, call caps and graceful degradation for LangChain v1 / LangGraph agents. Error **policy** (what to retry, transport-specific fallbacks, logging) is in `agentic-error-handling.md`; the framework-neutral model-call core (deadline, one retry layer, 429 handling, budgets) is in `llm-inference-and-model-routing.md`.

## Pattern 6: Resilient Agent (`create_agent` + middleware)

Executed on langchain 1.2.8 with scripted fake models (limit-middleware errors and the `ToolRetryMiddleware` default payload re-run on 1.5.2): `ruff` + `mypy --strict` clean; a transient error was retried twice and then answered by the fallback model (3 primary calls); a non-transient `ValueError` raised after 1 call with no failover; the failover emitted one `model_failover` warning, one `app.ai.fallbacks` increment and `app.ai.fallback=true` on the current span (in-memory OTel reader/exporter).

```python
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import structlog
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    ModelResponse,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.language_models import BaseChatModel
from opentelemetry import metrics, trace

logger = structlog.get_logger(__name__)
FALLBACKS = metrics.get_meter(__name__).create_counter("app.ai.fallbacks")   # ai-observability.md §metrics


class TransientFallbackMiddleware(AgentMiddleware[Any, Any]):
    """Fail over to an approved same-tier model ONLY on availability errors."""

    def __init__(self, fallback: BaseChatModel, transient: tuple[type[Exception], ...]) -> None:
        super().__init__()
        self.fallback = fallback
        self.transient = transient

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        try:
            return await handler(request)
        except self.transient as exc:
            # Never fail over silently: log, count and mark the span (error type only, never str(exc)).
            logger.warning("model_failover", error_type=type(exc).__name__, fallback=self.fallback_name)
            FALLBACKS.add(1, {"reason": "transient"})
            span = trace.get_current_span()
            span.set_attribute("app.ai.fallback", True)
            span.set_attribute("app.ai.fallback_model", self.fallback_name)
            return await handler(request.override(model=self.fallback))

    @property
    def fallback_name(self) -> str:
        return str(getattr(self.fallback, "model_name", None) or getattr(self.fallback, "model", None)
                   or type(self.fallback).__name__)


def build_resilient_agent(primary: BaseChatModel, fallback: BaseChatModel, tools: Sequence[Any],
                          transient: tuple[type[Exception], ...], checkpointer: Any) -> Any:
    middleware: list[AgentMiddleware[Any, Any]] = [
        ModelCallLimitMiddleware(run_limit=8, exit_behavior="error"),   # raises ModelCallLimitExceededError
        ToolCallLimitMiddleware(run_limit=20, exit_behavior="error"),
        TransientFallbackMiddleware(fallback, transient),               # outer: runs after retries are exhausted
        ModelRetryMiddleware(max_retries=2, retry_on=transient, on_failure="error"),
    ]
    return create_agent(primary, tools=tools, middleware=middleware, checkpointer=checkpointer)
```

`transient` is the provider SDK's availability error classes (timeouts, connection errors, 5xx, rate-limit-with-short-retry-after), mapped once in the model client (`llm-inference-and-model-routing.md`). The first middleware in the list is the outermost wrapper.

Traps verified by reading/executing langchain 1.2.8 (re-checked on 1.5.2 where marked in `agentic-testing.md`):

| Built-in default | Effect | Use instead |
|---|---|---|
| `ModelRetryMiddleware(on_failure="continue")` (default) | After the last retry it returns an `AIMessage` containing `str(exc)`: executed, a fake host name from the exception reached the final answer | `on_failure="error"`; the route maps the exception to a typed status |
| `ModelRetryMiddleware(retry_on=(Exception,))` (default) | Retries 400s, auth and schema errors | `retry_on=<transient classes>` |
| `ModelFallbackMiddleware(...)` | Catches every `Exception` and switches model (bad request, context overflow, refusal paths too) | `TransientFallbackMiddleware` above, or accept it only where the fallback is an approved equivalent for every error class |
| `ModelCallLimitMiddleware(exit_behavior="end")` (default) | Ends the run with an `AIMessage` "Model call limits exceeded: run limit (3/3)" that looks like an answer (executed) | `exit_behavior="error"` and map `ModelCallLimitExceededError` to `ITERATION_LIMIT` |
| `ToolRetryMiddleware(on_failure="continue")` (default) | Feeds the error text back to the model as a tool message | Retry only read-only/idempotent tools; return a typed `ToolResult` error instead |
| `Runnable.with_fallbacks(...)` | `exceptions_to_handle=(Exception,)` by default | Always pass `exceptions_to_handle=<transient classes>` |

Route mapping (extends `agentic-templates-core.md`):

```python
except (GraphRecursionError, ModelCallLimitExceededError, ToolCallLimitExceededError):
    return AgentResponse(thread_id=thread_id, status="ITERATION_LIMIT", message=SAFE_COPY["ITERATION_LIMIT"])
```

(`ModelCallLimitExceededError` is in `langchain.agents.middleware.model_call_limit`, `ToolCallLimitExceededError` in `langchain.agents.middleware.tool_call_limit`: verified in 1.2.8.)

## Hand-built graphs

Executed (bind → `with_retry` → `with_fallbacks` on fake models): the failing primary was retried and the fallback answered. Configure retry/fallback on the model object, keep exception text out of `messages`, and route exhausted budgets to a typed node:

```python
model = primary.bind_tools(tools).with_retry(
    retry_if_exception_type=transient, stop_after_attempt=3, wait_exponential_jitter=True,
).with_fallbacks([fallback.bind_tools(tools)], exceptions_to_handle=transient)   # bind BEFORE composing


async def agent_node(state: AgentState) -> dict[str, Any]:
    response = await model.ainvoke(state["messages"])   # non-transient errors propagate to the route
    return {"messages": [response], "iteration_count": state["iteration_count"] + 1}


def should_continue(state: AgentState) -> Literal["tools", "limit_reached", "__end__"]:
    if state["iteration_count"] >= settings.max_agent_iterations:
        return "limit_reached"
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else END


async def limit_reached_node(state: AgentState) -> dict[str, Any]:
    return {"status": "ITERATION_LIMIT"}   # the route renders safe copy; no model text is reused
```

REMOVED (wrong): the old template caught the provider error and appended `AIMessage(f"Retrying after error: {e}")`. `should_continue` then saw an AI message without tool calls and returned END, so **no retry happened**, the user received the raw exception text, and that text entered model context (static trace of the old code). It also switched provider after any two errors of any kind.

## Key Design Decisions

| Decision | Recommendation | Reason |
|----------|---------------|--------|
| State typing | `TypedDict` (or `create_agent`'s `AgentState` + `state_schema=`) | Type safety, LangGraph compatibility |
| Routing | `Command(goto=...)` from code-validated values | Never `goto=` a raw model string (`agentic-templates-advanced.md`) |
| Step caps | `recursion_limit` + call-limit middleware, both from settings | Default recursion limit is 10000; caps must produce a typed status |
| Retry | One layer, transient errors only, inside the run deadline | Stacked retries multiply latency and cost |
| Failover | Same tier, approved equivalent, availability errors only | Silent downgrade to an unevaluated model is a quality incident |
| Checkpointing | Durable saver entered in lifespan | Crash recovery and HITL; resumed nodes re-run, so keep them idempotent |
| Model construction | `init_chat_model(settings.chat_model, ...)` in one module | Model ids come from config only |
