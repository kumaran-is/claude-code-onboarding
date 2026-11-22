# ADK Testing Patterns

Every snippet here was executed with `google-adk==1.29.0`, pytest and `asyncio_mode = "auto"` (12 tests passed; no network, no credentials). Eval sets, judges and golden cases: `adk-eval-guide` and `eval-guide`. Live end-to-end replay against the running service before merge: `agentic-ai-dev/reference/agentic-testing.md`.

## 1. InMemoryRunner does NOT fake the model

`InMemoryRunner` only swaps the session, artifact and memory services for in-memory ones. The agent still calls whatever `model` it was given: with a real Gemini id and no key the run fails with `ValueError` (executed); with a key it bills and is non-deterministic. Unit tests therefore need a **scripted model** as well.

```toml
# pyproject.toml
[dependency-groups]
dev = ["pytest==<pin>", "pytest-asyncio==<pin>", "httpx==<pin>", "aiosqlite==<pin>"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## 2. Scripted fake model

Register a `BaseLlm` subclass for a model-id pattern; tests set the model setting to a matching id (`fake-model`), so production code is unchanged.

```python
# tests/fakellm.py
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from google.genai import types


class ScriptedLlm(BaseLlm):
    """Each call pops one step: str -> text, dict -> function call, exception -> raised."""

    script: ClassVar[list[Any]] = []
    requests: ClassVar[list[LlmRequest]] = []

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"fake-.*"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        ScriptedLlm.requests.append(llm_request)
        step = ScriptedLlm.script.pop(0) if ScriptedLlm.script else "done"
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, dict):
            call = types.FunctionCall(name=step["name"], args=step.get("args", {}))
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))
            return
        if stream:  # mimic SSE mode: partial chunks, then one aggregated final response
            for chunk in step.split(" "):
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=chunk + " ")]), partial=True)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=step)]))


LLMRegistry.register(ScriptedLlm)
```

## 3. Agent tests

Sessions must exist before `run_async`: `InMemoryRunner.auto_create_session` is `False`, and an unknown `session_id` raises `SessionNotFoundError` (executed). `create_session` is a coroutine — await it.

```python
from typing import Any

import pytest
from google.adk.agents import Agent, LoopAgent, RunConfig, SequentialAgent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.runners import InMemoryRunner
from google.genai import types

from tests.fakellm import ScriptedLlm

MODEL = "fake-model"


@pytest.fixture(autouse=True)
def reset_script():
    ScriptedLlm.script.clear()
    ScriptedLlm.requests.clear()


async def run_turn(runner: InMemoryRunner, text: str, state: dict[str, Any] | None = None, **kw: Any) -> list:
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id="u1", state=state)
    return [e async for e in runner.run_async(
        user_id="u1", session_id=session.id, new_message=types.UserContent(parts=[types.Part(text=text)]), **kw)]


async def test_tool_called_with_scripted_args():
    ScriptedLlm.script = [{"name": "add_to_cart", "args": {"item": "apple", "quantity": 2}}, "Added."]
    runner = InMemoryRunner(agent=Agent(name="shop", model=MODEL, instruction="x", tools=[add_to_cart]), app_name="t")
    events = await run_turn(runner, "add two apples")
    calls = [p.function_call.name for e in events for p in (e.content.parts if e.content else []) if p.function_call]
    assert calls == ["add_to_cart"]
    assert events[-1].is_final_response() and events[-1].content.parts[0].text == "Added."


async def test_sequential_pipeline_final_author():
    ScriptedLlm.script = ["one-line summary", "expanded text"]
    pipeline = SequentialAgent(name="p", sub_agents=[
        Agent(name="researcher", model=MODEL, instruction="Summarize.", output_key="summary"),
        Agent(name="writer", model=MODEL, instruction="Expand on this summary: {summary}"),
    ])
    events = await run_turn(InMemoryRunner(agent=pipeline, app_name="t"), "topic")
    assert [e.author for e in events if e.is_final_response()][-1] == "writer"
    assert "one-line summary" in str(ScriptedLlm.requests[-1].config.system_instruction)  # state templating


async def test_loop_is_capped():
    ScriptedLlm.script = ["again"] * 10
    loop = LoopAgent(name="l", sub_agents=[Agent(name="a", model=MODEL, instruction="x")], max_iterations=3)
    events = await run_turn(InMemoryRunner(agent=loop, app_name="t"), "go")
    assert len([e for e in events if e.author == "a"]) == 3
    unbounded = LoopAgent(name="l2", sub_agents=[Agent(name="b", model=MODEL, instruction="x")])
    with pytest.raises(LlmCallsLimitExceededError):
        await run_turn(InMemoryRunner(agent=unbounded, app_name="t"), "go", run_config=RunConfig(max_llm_calls=2))
```

## 4. Tools and callbacks

Tools are plain functions: test them directly. `MagicMock(spec=ToolContext)` with a dict `state` covers state access.

```python
from unittest.mock import MagicMock

from google.adk.tools import ToolContext


def test_stateful_tool_writes_state():
    ctx = MagicMock(spec=ToolContext)
    ctx.state = {}
    assert add_to_cart("apple", 2, ctx)["ok"] is True
    assert ctx.state["cart"] == [{"item": "apple", "quantity": 2}]
```

Assert callback wiring with an identity check (a docstring claiming "guarded" proves nothing), and exercise the behaviour with the fake model. Callback parameter names must be ADK's keyword names (`callback_context`, `llm_request`) — `(ctx, request)` raises `TypeError` at run time (executed).

```python
def test_callback_is_wired():
    assert build_guarded_agent().before_model_callback is block_when_flagged


async def test_callback_short_circuits_model():
    events = await run_turn(InMemoryRunner(agent=build_guarded_agent(), app_name="t"), "hi", state={"blocked": True})
    assert events[-1].content.parts[0].text == "BLOCKED"
    assert ScriptedLlm.requests == []  # the model was never called
```

## 5. FastAPI tests (contract from `adk-fastapi-integration.md`)

Run the real lifespan with a real session service (SQLite via `aiosqlite` in tests, Postgres in integration), the fake model, and an overridden principal dependency.

```python
import json

import pytest
from google.genai import errors
from httpx import ASGITransport, AsyncClient

from src import main
from src.api import routes


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "fake-model")
    monkeypatch.setenv("SESSION_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/sessions.db")
    current = {"p": routes.Principal(user_id="alice", org_id="org-a")}
    main.app.dependency_overrides[routes.get_principal] = lambda: current["p"]
    async with main.lifespan(main.app):
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as c:
            c.as_user = lambda p: current.update(p=p)
            yield c
    main.app.dependency_overrides.clear()


async def test_foreign_session_is_404(client):
    ScriptedLlm.script = ["x"]
    sid = (await client.post("/api/chat", json={"message": "hi"})).json()["session_id"]
    client.as_user(routes.Principal(user_id="mallory", org_id="org-m"))
    assert (await client.post("/api/chat", json={"message": "hi", "session_id": sid})).status_code == 404


async def test_model_error_maps_to_typed_status_without_text(client):
    ScriptedLlm.script = [errors.ServerError(503, {"error": {"message": "secret-detail-123"}})]
    r = await client.post("/api/chat", json={"message": "hi"})
    assert r.json()["status"] == "MODEL_UNAVAILABLE" and "secret-detail-123" not in r.text


async def test_stream_partials_only_one_terminal_event(client):
    ScriptedLlm.script = ["alpha beta"]
    async with client.stream("POST", "/api/stream", json={"message": "hi"}) as r:
        lines = [ln async for ln in r.aiter_lines() if ln]
    events = [ln.split(": ", 1)[1] for ln in lines if ln.startswith("event: ")]
    texts = [json.loads(ln.split(": ", 1)[1]).get("text", "") for ln in lines if ln.startswith("data: ")]
    assert events == ["content", "content", "done"] and "".join(texts) == "alpha beta "


async def test_stream_error_is_opaque_and_terminal(client):
    ScriptedLlm.script = [RuntimeError("db password=hunter2")]
    async with client.stream("POST", "/api/stream", json={"message": "hi"}) as r:
        text = "".join([ln async for ln in r.aiter_lines()])
    assert "event: error" in text and "event: done" not in text and "hunter2" not in text
```

## 6. Test checklist

- [ ] Fake model registered; no test reaches a real model id
- [ ] Sessions created (awaited) before `run_async`
- [ ] Tool selection asserted from events (`function_call.name`), tool logic tested directly
- [ ] Pipeline: final author and `{key}` state templating asserted
- [ ] Loop cap and `max_llm_calls` cap each have a test
- [ ] Callback wiring (identity) + behaviour test
- [ ] Foreign session → 404; model error → typed status with no exception text; SSE → one terminal event
- [ ] Scope injection: a forged `org_id` from the model is overwritten (`adk-tools-callbacks.md` §5)

## 7. What not to do

- Do not assert on exact model wording from a live model; with the fake model, exact text is fine because you scripted it
- Do not use `MagicMock` for the session service — the real in-memory/SQLite service catches un-awaited calls and ownership bugs
- Do not call `runner.run()` (sync) inside async tests
