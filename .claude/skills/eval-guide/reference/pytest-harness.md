# Pytest Harness for AI Code and Evals

> Generic pytest/pytest-asyncio and real-database fixtures: `python-testing-patterns/reference/postgres-integration-testing.md` and `.claude/rules/python-backend.md`. This file covers what is specific to AI code.

## Test layers: split by what needs a live model

| Layer | Model | What it proves | Tier |
|---|---|---|---|
| Unit | none / fake | prompt rendering, tool schemas and arg validation, output parsing incl. malformed JSON, routing given a label, retry/timeout, error mapping | R1 |
| Workflow | scripted fake model | executed tool sequence + args, state transitions, authorization on tool calls, idempotency, persisted state | R1 |
| Contract | none | tool/MCP surface hash, structured-output JSON Schema, prompt variables present, tool names in prompt == registered tools | R1 |
| Golden (live) | real model + judge | grounding, refusal quality, tool *choice*, semantic quality (declared k/N trials) | R2 / R3 |
| E2E / canary | deployed | wiring, telemetry, latency, authorization end to end; no destructive effects | R3 / R4 |

R1 never calls a live model. A live suite that skips for missing credentials reports **NOT RUN**, never PASS. A mocked test is never evidence of live-provider behaviour.

## Scripted model: deterministic agent workflow test (LangChain v1)

Executed (pytest 1 passed, `mypy --strict` clean) on both the toolkit pin langchain 1.2.8 / langgraph 1.0.7 and langchain 1.5.2 / langgraph 1.2.24.

```python
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool


class ScriptedModel(GenericFakeChatModel):
    """GenericFakeChatModel.bind_tools raises NotImplementedError; agents need it bound."""

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self


def test_agent_calls_lookup_with_scoped_args() -> None:
    calls: list[dict[str, str]] = []

    @tool
    def lookup_order(order_id: str) -> dict[str, Any]:
        """Look up an order's shipping status."""
        calls.append({"order_id": order_id})
        # ToolResult shape {ok, error_code, data}: agentic-ai-dev/reference/tool-execution-safety.md §1
        return {"ok": True, "error_code": None, "data": {"status": "shipped"}}

    model = ScriptedModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "lookup_order", "args": {"order_id": "o-1"}, "id": "c1"}]),
        AIMessage("Order o-1 has shipped."),
    ]))
    # explicit annotation: on langchain 1.2.8 mypy --strict cannot infer the graph type parameters
    agent: Runnable[Any, dict[str, Any]] = create_agent(model, tools=[lookup_order])
    out = agent.invoke({"messages": [{"role": "user", "content": "Where is order o-1?"}]})

    assert calls == [{"order_id": "o-1"}]                       # executed tool + args
    assert out["messages"][-1].content == "Order o-1 has shipped."
```

Extend the same test with a scripted *wrong* call (another account's id) and assert the tool layer rejects it and nothing is persisted. Agent-side patterns: `agentic-ai-dev/reference/agentic-testing.md`.

## ADK agents in tests

Checked against the adk-python Runner docs via Context7 (not executed here; verify on your pinned google-adk).

```python
# tests/eval/conftest.py
import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from my_agent_package.agent import root_agent   # your agent


@pytest.fixture
def runner() -> InMemoryRunner:
    return InMemoryRunner(agent=root_agent)        # agent= or app=App(...) is required


async def run_case(runner: InMemoryRunner, text: str, user_id: str = "eval-user") -> list:
    # run_async on a session that does not exist raises SessionNotFoundError: create it first
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id)
    msg = types.Content(role="user", parts=[types.Part.from_text(text=text)])
    return [ev async for ev in runner.run_async(user_id=user_id, session_id=session.id, new_message=msg)]
```

One session per case (no cross-case memory). Live-model ADK runs and `adk eval` are R2+; R1 uses a scripted or fake model.

## Parametrize over golden cases

```python
# tests/eval/test_answer_evals.py
import json
import pathlib

import pytest

CASES = json.loads(pathlib.Path("tests/golden/answer/cases.json").read_text())["cases"]

@pytest.mark.r2
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_answer_case(case, runner):
    events = await run_case(runner, case["input"])
    ...   # deterministic assertions first, then judge (see ../SKILL.md verdict precedence)
```

Load cases at module level (a fixture cannot be called like a function inside `parametrize`). Critical cases live in their own file and gate at 100%.

## Failure injection (fallback tests)

```python
@pytest.mark.r1
async def test_tool_outage_returns_safe_state(agent_under_test, order_repo, mocker):
    mocker.patch("my_agent_package.tools.lookup.call", side_effect=TimeoutError("injected"))
    result = await agent_under_test.handle("Cancel order o-1")
    assert result.status == "needs_review"              # the domain's declared safe state
    assert result.confirmed is False                    # no false success message
    assert await order_repo.get("o-1") == ORIGINAL      # no side effect happened
```

Every AI stage owes evaluated cases for timeout, empty output, invalid schema, provider failure and low confidence. A missing model result never authorizes continuation. Inject failures deterministically; a case named for a failure that asserts an exact error against a healthy live dependency will flap (see `ci-tiers.md`).

## Credentials in eval tests

Offline eval tests resolve credentials exactly as the application does (same settings object). When credentials are absent they **skip with a reason** and the tier report counts them NOT RUN; they never read real secrets in R1. Otherwise a test passes alone and 403s only in the full sweep.

## Per-case thresholds belong to the case type

```python
# WRONG: one confidence floor for every case type
assert case["expected_output"].get("confidence_min", 0) >= 0.80

# RIGHT: scope the rule to the case type the contract covers
if "label" in case["expected_output"]:      # clear-cut classification cases only
    assert case["expected_output"].get("confidence_min", 0) >= 0.80
```

Probabilistic case types (pattern detection, root-cause hypotheses) legitimately use lower floors; asserting a floor the product contract never promised is a TEST error.

## pyproject.toml

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
  "r1: deterministic PR gate, no live model",
  "r2: nightly live golden replay",
  "r3: pre-release full held-out + safety set",
  "r4: deployed canary probes",
  "eval: calls a live model or judge",
]
```

`asyncio_mode = "auto"` removes the per-test `@pytest.mark.asyncio`. Without an async plugin, pytest 9.2 **fails** an `async def` test ("async def functions are not natively supported"), verified here; it does not silently pass. Do not install `pytest-rerunfailures` reruns on LLM assertions.

## CI commands

```bash
uv run pytest -m r1 --tb=short --junit-xml=reports/pytest-r1.xml        # PR gate
uv run pytest -m "r2" --tb=long --junit-xml=reports/pytest-r2.xml       # nightly (serial for live suites)
uv run pytest -m r1 --cov=<agent_package> --cov-report=term-missing
```
