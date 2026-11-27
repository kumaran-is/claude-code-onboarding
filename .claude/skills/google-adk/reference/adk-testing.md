# ADK Testing Patterns

Install pin: `google-adk==2.15.1`. Scripted `BaseLlm` only.

**Executed on 2.15.1 (local):** FunctionNode graphs; LlmAgent-in-graph `output_key`; `ctx.run_node(LlmAgent)` RetryConfig / `ITERATION_LIMIT` / `Event(state=...)`; FunctionTool and `McpToolset(require_confirmation=True)` (local mock MCP); FastAPI ASGI with `InMemorySessionService` (`adk-fastapi-integration.md` §9); loopback A2A including `partial=None` chunks persisted (`adk-agent-handoff.md`); converter `last_chunk`; `finish_task`; root `single_turn` `ValueError`; `parameter_binding`. Reproduce with this file's `ScriptedLlm` plus those references — the throwaway harness is not in-repo.

**Not tested:** live Gemini, Gemini Live, non-loopback A2A, sqlite `DatabaseSessionService` on 2.15.1 (last 2.15.0). Eval sets: `adk-eval-guide`.

## 1. InMemoryRunner does NOT fake the model

`InMemoryRunner` only swaps the session, artifact and memory services for in-memory ones. The agent still calls whatever `model` it was given: with a real Gemini id and no key the run fails with `ValueError` (executed); with a key it bills and is non-deterministic. Unit tests therefore need a **scripted model** as well.

```toml
# pyproject.toml
[dependency-groups]
dev = ["pytest==9.2.0", "pytest-asyncio==1.5.0", "httpx2==2.16.2", "aiosqlite==0.22.1"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
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
from pydantic import ValidationError
from google.adk import Event, Workflow
from google.adk.agents import Agent, Context, LoopAgent, RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.events import RequestInput
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.adk.workflow import DEFAULT_ROUTE, FunctionNode, JoinNode, node
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


async def test_workflow_pipeline_final_author():
    # Executed google-adk==2.15.1 with ScriptedLlm. SequentialAgent form also ran on 2.15.0.
    ScriptedLlm.script = ["one-line summary", "expanded text"]
    pipeline = Workflow(name="p", edges=[(
        "START",
        Agent(name="researcher", model=MODEL, instruction="Summarize.", output_key="summary"),
        Agent(name="writer", model=MODEL, instruction="Expand on this summary: {summary}"),
    )])
    events = await run_turn(InMemoryRunner(node=pipeline, app_name="t"), "topic")
    assert [e.author for e in events if e.is_final_response()][-1] == "writer"
    assert "one-line summary" in str(ScriptedLlm.requests[-1].config.system_instruction)


def _out(events):
    return [e.output for e in events if e.output is not None]


async def test_join_route_hitl_and_loop_on_function_nodes():
    # Executed google-adk==2.15.1, no model. Join keys = predecessor function names.
    def left(node_input) -> str:
        return "L"
    def right(node_input) -> str:
        return "R"
    def synth(node_input: dict) -> dict:
        return node_input
    gather = JoinNode(name="gather")
    joined = await run_turn(InMemoryRunner(node=Workflow(name="fan_out", edges=[
        ("START", left, gather), ("START", right, gather), (gather, synth),
    ]), app_name="j"), "go")
    assert _out(joined)[-1] == {"left": "L", "right": "R"}

    def router(node_input):
        return Event(route="".join(p.text or "" for p in node_input.parts), output="x")
    def handle_bug():
        return Event(output="BUG_OK")
    def handle_unknown():
        return Event(output="UNKNOWN")
    routed = Workflow(name="r", edges=[("START", router), (router, {"BUG": handle_bug, DEFAULT_ROUTE: handle_unknown})])
    assert _out(await run_turn(InMemoryRunner(node=routed, app_name="rb"), "BUG"))[-1] == "BUG_OK"
    assert _out(await run_turn(InMemoryRunner(node=routed, app_name="ru"), "NOPE"))[-1] == "UNKNOWN"

    def step1():
        yield RequestInput(message="Enter a number:", response_schema=int)
    def step2(node_input):
        return node_input * 2
    hitl = InMemoryRunner(node=Workflow(name="hitl", edges=[("START", step1, step2)]), app_name="h")
    session = await hitl.session_service.create_session(app_name=hitl.app_name, user_id="u1")
    paused = [e async for e in hitl.run_async(user_id="u1", session_id=session.id, new_message=types.UserContent(parts=[types.Part(text="start")]))]
    fc = next(p.function_call for e in paused for p in (e.content.parts if e.content else []) if p.function_call)
    inv = next(e.invocation_id for e in paused if e.long_running_tool_ids)
    resumed = [e async for e in hitl.run_async(
        user_id="u1", session_id=session.id, invocation_id=inv,
        new_message=types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=fc.id, name="adk_request_input", response={"result": 21}))]))]
    assert _out(resumed)[-1] == 42

    @node(name="lint_reviewer")
    async def compile_lint_check(ctx: Context, node_input: str) -> dict:
        return {"findings": "x"}
    @node(rerun_on_resume=True)
    async def code_workflow(ctx: Context, node_input):
        check = {"findings": "x"}
        for _ in range(3):
            check = await ctx.run_node(compile_lint_check, "draft")
            if not check.get("findings"):
                yield Event(output="ok")
                return
        yield Event(output={"ok": False, "error_code": "ITERATION_LIMIT"})
    assert _out(await run_turn(InMemoryRunner(node=Workflow(name="code_refine", edges=[("START", code_workflow)]), app_name="l"), "go"))[-1]["error_code"] == "ITERATION_LIMIT"
    with pytest.raises(ValidationError):
        Workflow(name="bad", edges=[("START", lambda x: x)])
    with pytest.raises(ValueError, match="multiple terminal"):
        await run_turn(InMemoryRunner(node=Workflow(name="two_term", edges=[("START", left), ("START", right)]), app_name="two"), "x")


async def test_confirmation_state_binding_and_task_mode():
    # Executed google-adk==2.15.1, ScriptedLlm. Consume run_async as an async generator — do not await it.
    called: list[str] = []

    def archive_document(document_id: str) -> dict:
        called.append(document_id)
        return {"ok": True, "error_code": None, "data": {"document_id": document_id}}

    agent = Agent(name="arch", model=MODEL, instruction="x", tools=[FunctionTool(archive_document, require_confirmation=True)])
    ScriptedLlm.script = [{"name": "archive_document", "args": {"document_id": "d1"}}, "archived"]
    runner = InMemoryRunner(agent=agent, app_name="c")
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id="u1")
    paused = [e async for e in runner.run_async(user_id="u1", session_id=session.id, new_message=types.UserContent(parts=[types.Part(text="go")]))]
    assert called == []
    e, fc = next((ev, p.function_call) for ev in paused for p in (ev.content.parts if ev.content else []) if p.function_call and p.function_call.name == "adk_request_confirmation")
    resumed = [ev async for ev in runner.run_async(
        user_id="u1", session_id=session.id, invocation_id=e.invocation_id,
        new_message=types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=fc.id, name="adk_request_confirmation", response={"confirmed": True}))]))]
    assert called == ["d1"] and any("archiv" in (p.text or "") for ev in resumed for p in (ev.content.parts if ev.content else []))
    called.clear()
    ScriptedLlm.script = [{"name": "archive_document", "args": {"document_id": "d2"}}, "no"]
    session2 = await runner.session_service.create_session(app_name=runner.app_name, user_id="u1")
    paused2 = [e async for e in runner.run_async(user_id="u1", session_id=session2.id, new_message=types.UserContent(parts=[types.Part(text="go")]))]
    e2, fc2 = next((ev, p.function_call) for ev in paused2 for p in (ev.content.parts if ev.content else []) if p.function_call and p.function_call.name == "adk_request_confirmation")
    _ = [ev async for ev in runner.run_async(
        user_id="u1", session_id=session2.id, invocation_id=e2.invocation_id,
        new_message=types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=fc2.id, name="adk_request_confirmation", response={"confirmed": False}))]))]
    assert called == []

    def greet(name: str, city: str) -> str:
        return f"{name}@{city}"
    assert _out(await run_turn(InMemoryRunner(node=Workflow(name="g", edges=[("START", greet)]), app_name="st"), "x", state={"name": "Ada", "city": "Paris"}))[-1] == "Ada@Paris"
    with pytest.raises(ValueError, match="city"):
        await run_turn(InMemoryRunner(node=Workflow(name="gm", edges=[("START", greet)]), app_name="stm"), "x", state={"name": "Ada"})
    def seed(node_input) -> dict:
        return {"name": "Bob", "city": "Lyon"}
    assert "Bob@Lyon" in _out(await run_turn(InMemoryRunner(node=Workflow(name="ni", edges=[("START", seed, FunctionNode(func=greet, name="greet", parameter_binding="node_input"))]), app_name="ni"), "x"))

    ScriptedLlm.script = [{"name": "specialist", "args": {}}, {"name": "finish_task", "args": {"result": "ok"}}, "done"]
    spec = Agent(name="specialist", model=MODEL, mode="task", instruction="x")
    team = await run_turn(InMemoryRunner(agent=Agent(name="coordinator", model=MODEL, instruction="x", sub_agents=[spec]), app_name="team"), "please")
    names = [p.function_call.name for e in team for p in (e.content.parts if e.content else []) if p.function_call]
    assert "specialist" in names and "finish_task" in names
    with pytest.raises(ValueError, match="single_turn"):
        await run_turn(InMemoryRunner(agent=Agent(name="st", model=MODEL, mode="single_turn", instruction="x"), app_name="stroot"), "hi")


async def test_legacy_loop_is_capped():
    # Deprecated LoopAgent still runs (executed on 2.15.0). New loops: adk-agent-types.md §4
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

Assert callback wiring with an identity check (a docstring claiming "guarded" proves nothing), and exercise the behaviour with the fake model. Callback parameter names must be ADK's canonical names (`callback_context`, `llm_request`); 1.29 raised `TypeError` for `(ctx, request)`, 2.15 adapts them positionally without error, so only a test that runs the callback proves the wiring (executed on both).

```python
def test_callback_is_wired():
    assert build_guarded_agent().before_model_callback is block_when_flagged


async def test_callback_short_circuits_model():
    events = await run_turn(InMemoryRunner(agent=build_guarded_agent(), app_name="t"), "hi", state={"blocked": True})
    assert events[-1].content.parts[0].text == "BLOCKED"
    assert ScriptedLlm.requests == []  # the model was never called
```

## 5. FastAPI tests

Contract tests live in `adk-fastapi-integration.md` §9 (**2.15.1** `InMemorySessionService` + `httpx2` ASGI).

## 6. Test checklist

- [ ] Fake model registered; sessions awaited before `run_async`; no live model id
- [ ] Tool selection from `function_call.name`; pipeline author + `{key}` templating
- [ ] FunctionNode graphs: JoinNode, DEFAULT_ROUTE, RequestInput, ITERATION_LIMIT, two-terminal error
- [ ] `require_confirmation` approve/reject; `parameter_binding='state'`; `finish_task`; loop/`max_llm_calls` caps
- [ ] Callback wiring (identity) + behaviour; forged `org_id` overwritten (`adk-tools-callbacks.md` §5)
- [ ] Foreign session 404; opaque model error; SSE one terminal event
- [ ] `ctx.run_node(LlmAgent)` retry / `ITERATION_LIMIT` / non-retryable; `McpToolset(require_confirmation=True)`; local A2A chunks/fail/timeout

## 7. What not to do

- Do not assert on exact model wording from a live model; with the fake model, exact text is fine because you scripted it
- Do not use `MagicMock` for the session service — the real in-memory/SQLite service catches un-awaited calls and ownership bugs
- Do not call `runner.run()` (sync) inside async tests
