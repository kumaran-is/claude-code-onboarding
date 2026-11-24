# ADK Structured Output and Session State

> Split from `adk-core-patterns.md`: session state access, structured output, `UserContent` construction. Executed with `google-adk==1.29.0` and re-checked on `2.15.0` with a scripted fake model (invalid output still raises `ValidationError` inside `run_async`). Since 2.14 an agent with both `output_schema` and transfer targets returns its answer through a `set_model_response` tool call (changelog).

## 1. Session state access

Tools read and write session state through `ToolContext`; callbacks through `callback_context.state` (same interface).

**State only persists through events.** The SessionService saves state when it appends an event: changes made through a `Context` (`tool_context.state`, `callback_context.state`) are tracked into the next event's `EventActions.state_delta`; code without a tracked context yields an event with `EventActions(state_delta={...})` itself. Never assign to `state` on a `Session` returned by `session_service.get_session(...)` (or `ctx.session.state` in a custom agent): the docs say it "bypasses the ADK's event tracking and can lead to lost data", and `InMemorySessionService` hides the loss because it shares the object. Test it on the persistent backend you deploy (`DatabaseSessionService` on SQLite in tests): run the agent, fetch the session again from a *new* service instance, assert the key. Prefixes: none = this session; `user:` = all of the user's sessions; `app:` = all users; `temp:` = this invocation only, never persisted. Source: adk.dev/sessions/state and adk.dev/events (fetched 2026-11-24; the pages state no 1.x/2.x difference for this rule).

```python
from google.adk.tools import ToolContext

ALLOWED_PREFERENCES = {"theme", "language"}


def update_user_preference(preference_key: str, preference_value: str, tool_context: ToolContext) -> dict:
    """Store one user preference in session state.

    Args:
        preference_key: 'theme' or 'language'.
        preference_value: The value to store.

    Returns:
        {"ok": bool, "error_code": str | None, "data": {"key": str, "previous": str | None} | None}
    """
    if preference_key not in ALLOWED_PREFERENCES:   # the model picks the key: allowlist it
        return {"ok": False, "error_code": "UNKNOWN_PREFERENCE", "data": None}
    previous = tool_context.state.get(preference_key)
    tool_context.state[preference_key] = preference_value   # visible to later tools in this turn
    return {"ok": True, "error_code": None, "data": {"key": preference_key, "previous": previous}}
```

Never return the whole state (`dict(tool_context.state)`) to the model: state holds server-side scope (`org_id`), flags and earlier outputs that the model must not see or echo. State keys prefixed `user:`, `app:` and `temp:` have different persistence scopes — check the ADK state docs before relying on them.

## 2. Structured output

`output_schema=Model` makes ADK validate the final response; with `output_key` the **validated dict** (not a JSON string) is stored in state (executed: `state["report"]` is a `dict`). Read it with `Model.model_validate(state[key])`. `output_schema` and `tools` can be combined in 1.29.

A schema-invalid or non-JSON final response raises `pydantic.ValidationError` **inside** `run_async` (executed) — the route must catch it.

```python
import os

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.genai import types
from pydantic import BaseModel, Field, ValidationError


class ResearchReport(BaseModel):
    title: str
    key_findings: list[str] = Field(min_length=1, max_length=5)
    next_steps: list[str]


research_agent = Agent(
    name="research_agent",
    model=os.environ["AGENT_MODEL"],   # settings.agent_model in real code
    instruction="Research the topic and produce a structured report.",
    output_schema=ResearchReport,
    output_key="research_report",
)
```

Do not add a model-reported `confidence` field and gate on it: self-reported confidence is not verification. Gate on deterministic validators or tool evidence.

## 3. Malformed output: one retry on a fresh session

Retry once, on a **new session** with the same initial state, so the failed turn is not replayed into context. Only when every tool on the path is read-only or idempotency-keyed (a retry re-issues tool calls). Never retry SAFETY / RECITATION / MAX_TOKENS finishes — fix the prompt, policy or token budget instead. Count retries in a metric. Executed: invalid-then-valid recovers on attempt 2; two invalid outputs raise `StructuredOutputFailed`.

```python
class StructuredOutputFailed(Exception):
    """No schema-valid output after the retry budget."""


async def run_structured(
    runner: Runner, user_id: str, text: str, initial_state: dict, attempts: int = 2
) -> ResearchReport:
    for attempt in range(attempts):
        session = await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, state=dict(initial_state)
        )
        try:
            async for _ in runner.run_async(
                user_id=user_id, session_id=session.id,
                new_message=types.UserContent(parts=[types.Part(text=text)]),
            ):
                pass
        except ValidationError as exc:
            log_exception(logger, "structured_output_invalid", exc, attempt=attempt)  # metric too
            continue
        done = await runner.session_service.get_session(
            app_name=runner.app_name, user_id=user_id, session_id=session.id
        )
        stored = done.state.get("research_report") if done else None
        if stored is not None:
            return ResearchReport.model_validate(stored)
    raise StructuredOutputFailed()   # route maps it to SCHEMA_VALIDATION_FAILED
```

Business rules still run after schema validation (ranges, referenced ids exist, the caller may act on them).

## 4. UserContent construction

```python
from google.genai import types

new_message = types.UserContent(parts=[types.Part(text="Hello, how can you help me?")])

image_message = types.UserContent(
    parts=[
        types.Part(text="Describe this image:"),
        types.Part(inline_data=types.Blob(mime_type=detected_mime, data=image_bytes)),
    ]
)
```

Multimodal input rules: detect the MIME type from magic bytes (not the file extension or client header), cap image count and actual byte size per request, fetch media only from allow-listed storage (never a model- or user-supplied URL), and treat text inside images/PDFs as untrusted data. Send the message with `runner.run_async(...)` as in `adk-core-patterns.md` §2.
