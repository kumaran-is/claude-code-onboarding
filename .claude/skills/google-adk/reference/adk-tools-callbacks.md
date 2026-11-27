# ADK Callbacks

> Tool definitions, `ToolContext`, confirmation and `McpToolset`: `adk-tools-basic.md`. Framework-neutral tool rules (scope injection, typed results, idempotency, approvals): `agentic-ai-dev/reference/tool-execution-safety.md`.

Executed with `google-adk==1.29.0` and re-checked on `2.15.0` with a scripted fake model (`adk-testing.md` §2): all six callbacks below fire, `ruff` and `mypy --strict` are clean, and neither the tool's nor the model's exception text appears in the logs.

## 0. Rules that break at run time

- **Use ADK's canonical parameter names and order.** On 1.29 `async def cb(ctx, request)` raised `TypeError: got an unexpected keyword argument 'callback_context'`. On 2.15 misnamed parameters are adapted **positionally** in canonical order (executed: no error, `ctx` received the `Context`), so a wrong *order* now passes silently. Annotate the parameters and let `mypy --strict` plus a fake-model test catch mistakes. `CallbackContext` and `ToolContext` are aliases of `google.adk.Context` in 2.x.

| Callback | Signature | Return to override |
|---|---|---|
| `before_model_callback` | `(callback_context, llm_request)` | `LlmResponse` skips the model |
| `after_model_callback` | `(callback_context, llm_response)` | `LlmResponse` replaces it |
| `on_model_error_callback` | `(callback_context, llm_request, error)` | `LlmResponse` recovers; `None` re-raises |
| `before_tool_callback` | `(tool, args, tool_context)` | `dict` skips the tool and becomes its result |
| `after_tool_callback` | `(tool, args, tool_context, tool_response)` | `dict` replaces the result |
| `on_tool_error_callback` | `(tool, args, tool_context, error)` | `dict` recovers; `None` re-raises |

- **Model callbacks exist only on `LlmAgent`.** Deprecated orchestrators reject them (`SequentialAgent(before_model_callback=...)` → `extra_forbidden`, executed). Screen input for a `Workflow` in the FastAPI route or a FunctionNode before the first model node.
- **Session id:** `callback_context.session.id` / `tool_context.session.id` (there is no `session_id` attribute).
- **Assert wiring in a test** (`agent.before_model_callback is guard_input`), not in a docstring (`adk-testing.md` §4).

## 1. before_model_callback — deterministic gates

```python
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def _text_response(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


async def guard_input(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Short-circuit the model call when a deterministic policy flag is set."""
    if callback_context.state.get("ai_disabled"):  # kill switch / policy decided by code
        return _text_response("This assistant is temporarily unavailable.")
    return None
```

Rate limits and quotas belong in the API layer or a shared limiter keyed by principal (`python-dev/reference/fastapi-rate-limiting.md`), not in session state: a per-session counter is reset by opening a new session.

## 2. after_model_callback — usage without content

Log counts and finish reasons, never prompt or response text. `thoughts_token_count` matters on thinking models (thinking is billed as output).

```python
async def log_usage(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    usage = llm_response.usage_metadata
    logger.info(
        "model_response",
        agent=callback_context.agent_name,
        session_id=callback_context.session.id,
        prompt_tokens=usage.prompt_token_count if usage else None,
        output_tokens=usage.candidates_token_count if usage else None,
        thinking_tokens=usage.thoughts_token_count if usage else None,
        finish_reason=llm_response.finish_reason.name if llm_response.finish_reason else None,
    )
    return None
```

## 3. on_model_error_callback

```python
async def model_error_fallback(
    callback_context: CallbackContext, llm_request: LlmRequest, error: Exception
) -> LlmResponse | None:
    log_exception(logger, "model_call_failed", error, session_id=callback_context.session.id)
    return _text_response("I could not answer right now. Please try again.")
```

`log_exception` logs the type and ids only (`deployment-ci-cd/reference/python-observability.md` §2). Returning a canned answer hides the failure from the route: also record a metric, or return `None` and let the route map the exception to a typed status (`adk-fastapi-integration.md` §5).

## 4. after_tool_callback / on_tool_error_callback

```python
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext


async def log_tool_result(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, tool_response: dict[str, Any]
) -> dict[str, Any] | None:
    # args and results can carry user data: log the outcome, not the payload
    logger.info("tool_completed", tool=tool.name, ok=tool_response.get("ok"), session_id=tool_context.session.id)
    return None


async def tool_error_result(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, error: Exception
) -> dict[str, Any] | None:
    log_exception(logger, "tool_failed", error, tool=tool.name, session_id=tool_context.session.id)
    return {"ok": False, "error_code": "TOOL_UNAVAILABLE", "data": None}  # no exception text to the model
```

## 5. before_tool_callback — inject scope, fail closed

The model must never choose whose data a tool touches. Keep the authoritative `org_id` in session state (set server-side at session creation from the principal, `adk-fastapi-integration.md` §4) and overwrite whatever the model sent. Missing scope denies the call. Executed: a model call with `org_id="account-1"` reached the tool as the session's `org-real`; with no scope in state the tool did not run and the model received `UNAUTHORIZED`.

```python
SCOPED_TOOLS: dict[str, tuple[str, ...]] = {"get_order": ("org_id",)}  # tool -> scope params


async def inject_scope(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    """Overwrite model-supplied scope with server-side session state; deny if absent."""
    for key in SCOPED_TOOLS.get(tool.name, ()):
        trusted = tool_context.state.get(key)
        if not trusted:
            return {"ok": False, "error_code": "UNAUTHORIZED", "data": None}  # fail closed
        args[key] = trusted  # the tool receives this dict after the callback
    return None
```

Better still, leave the scope parameter out of the tool signature and read `tool_context.state["org_id"]` inside the tool, so the model never sees it. Either way the backend still authorizes the record (tool visibility, caller permission and resource authorization are three separate checks). Test that a forged value is ignored.

## 6. Attaching callbacks

```python
from google.adk.agents import Agent

agent = Agent(
    name="assistant",
    model=settings.agent_model,
    instruction="...",
    tools=[get_order],
    before_model_callback=guard_input,       # a list of callbacks is also accepted
    after_model_callback=log_usage,
    on_model_error_callback=model_error_fallback,
    before_tool_callback=inject_scope,
    after_tool_callback=log_tool_result,
    on_tool_error_callback=tool_error_result,
)
```

Cross-cutting behaviour for every agent of an app (usage logging, scope injection) can instead be registered once as an ADK plugin on `App(plugins=[...])`; check the plugin API in the ADK docs for your pinned version before using it.
