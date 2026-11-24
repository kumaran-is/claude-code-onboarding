# DeepEval Patterns

> Checked against **deepeval 4.3.4** on Python 3.14.10 (classes and signatures introspected; test-case construction and `ToolCorrectnessMetric` scoring executed offline with a counting stub judge; LLM-judged metrics were wired against the stub only, never scored by a real model). **deepeval 2.9.3 is a different API**: no `MCPServer`, `MCPUseMetric`, `ArenaGEval`, `SingleTurnParams`, `ArgumentCorrectnessMetric`, `PIILeakageMetric`. Query Context7 (`deepeval`) for your pinned version before writing code.

## Install

```toml
# pyproject.toml (eval dependency group)
deepeval = "==4.3.4"   # pin exactly; the metric API moves between majors
```

Set `DEEPEVAL_TELEMETRY_OPT_OUT=1` in CI.

## Judge model: always explicit

Every DeepEval metric that uses an LLM falls back to OpenAI when `model=` is omitted. In 4.3.4 even `ToolCorrectnessMetric()` without a model raises `DeepEvalError: OpenAI API key is not configured` at construction. Build the judge once from config:

```python
import os
from deepeval.models import GeminiModel          # or the class for your judge provider (Context7)

def make_judge():
    return GeminiModel(model=os.environ["EVAL_JUDGE_MODEL"])   # no literal model ids in eval code
```

## Test cases: tools and MCP take objects, not strings

```python
from deepeval.test_case import LLMTestCase, MCPServer, ToolCall

# WRONG: mcp_servers=["docs"]  -> TypeError: 'mcp_server' must be None or a list of 'MCPServer'
case = LLMTestCase(
    input="Where is order o-1?",
    actual_output=agent_output,
    retrieval_context=retrieved_chunks,                   # required by Faithfulness/Contextual*
    tools_called=[ToolCall(name="lookup_order", input_parameters={"order_id": "o-1"})],
    expected_tools=[ToolCall(name="lookup_order", input_parameters={"order_id": "o-1"})],
    mcp_servers=[MCPServer(server_name="orders", transport="stdio", available_tools=tools)],
)
```

`mcp_tools_called=[MCPToolCall(name=..., args=..., result=...)]` additionally requires the `mcp` package and `result` must be an `mcp.types.CallToolResult`; record the real MCP result object, do not fabricate one.

## ToolCorrectness does not catch an extra (forbidden) call

Executed (4.3.4): expected `[search_kb]`, called `[search_kb, delete_account]`, threshold 1.0. Default: score **1.0, success True**; `should_consider_ordering=True`: 1.0; `should_exact_match=True`: 0.0. The judge was called 0 times in all three (name matching is deterministic; the `model` is still required at construction). A forbidden or unauthorized tool call is therefore a deterministic gate in your own code (`[c for c in called if c in case.forbidden_tools]` must be empty, asserted on the recorded tool calls and on persisted side effects), never a ToolCorrectness threshold. Ragas `ToolCallF1` on the same calls scored 0.667 (it penalises extras, but a partial score still is not a block).

## Metric map (present in 4.3.4)

| Need | Metric | Notes |
|---|---|---|
| Tool selection + args | `ToolCorrectnessMetric(should_consider_ordering=..., should_exact_match=..., model=judge)` | Assert key args deterministically first. Default scoring ignores EXTRA calls (below) |
| Argument quality | `ArgumentCorrectnessMetric` | LLM-judged |
| Agent outcome / plan | `TaskCompletionMetric`, `GoalAccuracyMetric`, `PlanAdherenceMetric`, `PlanQualityMetric`, `StepEfficiencyMetric`, `ToolUseMetric` | Report path separately from outcome |
| Loops / permissions | `AgentLoopDetectionMetric`, `ToolPermissionMetric` | Permission is enforced in code; the metric only observes |
| MCP | `MCPUseMetric(model=judge)` | Needs `mcp_servers` objects |
| RAG | `FaithfulnessMetric`, `AnswerRelevancyMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric`, `ContextualRelevancyMetric` | `retrieval_context` populated from the real run |
| Multi-turn | `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `ConversationCompletenessMetric`, `RoleAdherenceMetric`, `ConversationalGEval` | Conversational test cases |
| Safety / format | `PIILeakageMetric`, `BiasMetric`, `ToxicityMetric`, `JsonCorrectnessMetric` | Schema validity is better asserted with Pydantic directly |
| Custom rubric | `GEval(name, criteria or evaluation_steps, evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT], model=judge)` | `LLMTestCaseParams` is an alias in 4.3.4 |

## Pytest integration

```python
import pytest
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric

@pytest.mark.r2          # live judge: nightly tier, never R1
@pytest.mark.eval
def test_answer_is_grounded(answer_run, judge):
    case = LLMTestCase(input=answer_run.question, actual_output=answer_run.text,
                       retrieval_context=answer_run.chunks)
    assert_test(case, [FaithfulnessMetric(threshold=0.9, model=judge)])
```

Judge-gated assertions follow the trial and accounting rules in `../SKILL.md` (median-of-3 where variance was observed; a judge error is UNSCORED, never PASS; no `@pytest.mark.flaky` reruns).

## ArenaGEval: pairwise prompt/model comparison

```python
from deepeval.metrics import ArenaGEval
from deepeval.test_case import ArenaTestCase, Contestant, SingleTurnParams

arena = ArenaGEval(name="answer-quality", criteria="Which response answers the question more accurately and concisely?",
                   evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT], model=judge)
case = ArenaTestCase(contestants=[Contestant(name="v3", test_case=case_v3), Contestant(name="v4", test_case=case_v4)])
```

A pairwise judge is one signal. A prompt or model promotion decision uses the paired statistics in `llm-evaluation/reference/ab-testing.md` over the held-out golden set, plus deterministic gates (`langfuse-prompts.md` "Prompt regression").

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| Metric without `model=` | Silent OpenAI default or construction error; always pass the judge |
| Strings in `mcp_servers` / `tools_called` | `MCPServer(...)` / `ToolCall(...)` objects |
| `FaithfulnessMetric` with empty `retrieval_context` | Pass the chunks the agent actually retrieved |
| Examples copied from a different major version | Re-verify imports against the pinned version |
| Async tests | `asyncio_mode = "auto"`; see `pytest-harness.md` |
