# ADK Agent Types

Executed with `google-adk==2.15.0` (`google-genai==2.34.0`) and a scripted fake model (`adk-testing.md` §2); fixture model, not live. `MODEL` stands for `settings.agent_model` — never a literal id. Run every example with `run_once` from `adk-core-patterns.md` §2 (awaited `create_session`, `RunConfig(max_llm_calls=...)`).

Multi-agent only when it beats a single agent or deterministic workflow on evals (separate tool/authority scopes, isolation of untrusted input, parallel latency) — `multi-agent-patterns` skill. Agents never own multi-step transactions: side effects go through a domain service or durable workflow (`workflow-orchestration-patterns`).

## 0. Workflow graphs (ADK 2.x, preferred for new code)

ADK 2.0 added a graph runtime. `SequentialAgent`, `ParallelAgent` and `LoopAgent` still run on 2.15 but each emits `DeprecationWarning: <Agent> is deprecated in favor of Workflow and will be removed in a future version. Workflow cannot yet be used as an LlmAgent sub-agent.` (executed). Use a `Workflow` for new multi-step flows; keep the old orchestrators only where the flow must sit under an `LlmAgent` (§1-3). Every snippet below was executed.

```python
from google.adk import Context, Event, Workflow
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.workflow import FunctionNode, RetryConfig, node
from pydantic import BaseModel


class CityTime(BaseModel):
    time_info: str
    city: str


def lookup_time(node_input: str) -> CityTime:        # plain function = a node; return value = its output
    return CityTime(time_info="10:10", city=node_input.strip())


pipeline = Workflow(name="city_time", edges=[(
    "START",
    Agent(name="gen", model=MODEL, instruction="Name one city."),
    lookup_time,
    Agent(name="report", model=MODEL, instruction="Report the time.", input_schema=CityTime),
)])
runner = Runner(app_name="city", node=pipeline, session_service=session_service)  # node=, not agent=
```

| Need | 2.x construct (executed) |
|---|---|
| Route on a classification | node returns `Event(route=["BUG"])`; edge `(router, {"BUG": bug_node, "LOGISTICS": logistics_node})` |
| Loop with a hard cap | `@node(rerun_on_resume=True) async def refine(ctx: Context, node_input)` with `for i in range(3): draft = await ctx.run_node(fixer, draft)`, then `yield Event(output=draft)`; never an unbounded `while` |
| Fan-out | `await asyncio.gather(*(ctx.run_node(worker, item, use_sub_branch=True) for item in items))` |
| Retry a transient node error | `FunctionNode(func=f, name="f", retry_config=RetryConfig(max_attempts=3, initial_delay=0.5, exceptions=[ConnectionError]))`; an unlisted exception (e.g. `PermissionError`) is raised after one attempt |
| Per-node deadline | `FunctionNode(..., timeout=10.0)` raises `NodeTimeoutError` |

Agents also take `retry_config` and `timeout` in 2.x. Because the framework catches node exceptions to apply `RetryConfig`, do not wrap tool or node bodies in a broad `except Exception` that turns failures into success-shaped values, and never catch `BaseException` (it traps the interrupt used for human-in-the-loop resume). Yield events instead of appending to `session.events` yourself. A custom `BaseAgent` subclass that overrides `_run_async_impl` is bypassed by the 2.x runtime (`BaseAgent` is now a `BaseNode`): port the logic to a `@node` function. Pass `"START"` as the first edge element; `App(root_agent=...)` accepts a `Workflow`. Run under `RunConfig(max_llm_calls=N)` and `asyncio.timeout` exactly as for agents.

## 1. SequentialAgent — pipeline (deprecated in 2.x)

Sub-agents run in order. Each writes its final text to `output_key`; later agents read it with `{key}` in their `instruction`.

```python
from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent

researcher = Agent(
    name="researcher",
    model=MODEL,
    description="Researches a topic and produces raw findings.",
    instruction="Research the topic provided by the user. Write key facts and context as plain text.",
    output_key="research_findings",
)

writer = Agent(
    name="writer",
    model=MODEL,
    description="Turns findings into a draft.",
    instruction="Write a clear draft article from these findings:\n\n{research_findings}",
    output_key="draft_article",
)

pipeline = SequentialAgent(name="research_pipeline", sub_agents=[researcher, writer])
```

An identifier-like `{name}` in an instruction must exist in session state when the agent runs — a missing key raises `KeyError: Context variable not found` (executed). Use `{name?}` for optional keys; use an instruction provider callable (`instruction=lambda ctx: TEXT`) when the text contains placeholder-like braces such as `{source_name}` in a citation template — callables bypass templating (executed).

## 2. ParallelAgent — fan-out, then synthesize (deprecated in 2.x)

Branches run concurrently and must not depend on each other; each writes its own key. Wrap in a `SequentialAgent` to synthesize.

```python
technical = Agent(name="technical_analyst", model=MODEL,
                  instruction="Analyze technical feasibility of: {topic}", output_key="technical_analysis")
market = Agent(name="market_analyst", model=MODEL,
               instruction="Analyze the market for: {topic}", output_key="market_analysis")
synthesizer = Agent(
    name="synthesizer",
    model=MODEL,
    instruction="Synthesize a recommendation.\n\nTechnical:\n{technical_analysis}\n\nMarket:\n{market_analysis}",
    output_key="executive_summary",
)

full_analysis = SequentialAgent(
    name="full_analysis_pipeline",
    sub_agents=[ParallelAgent(name="analysis_team", sub_agents=[technical, market]), synthesizer],
)
# create the session with state={"topic": ...} so {topic} resolves
```

Parallel branches multiply model calls and cost; the per-request `max_llm_calls` cap covers the whole tree.

## 3. LoopAgent — iterative refinement (deprecated in 2.x)

`LoopAgent.max_iterations` defaults to `None` = **unbounded** (verified on 2.15): always set it, and also pass `RunConfig(max_llm_calls=N)` (default 500; exceeding it raises `LlmCallsLimitExceededError`, executed). The loop stops early when a sub-agent calls `exit_loop`.

On 1.29, `output_key` on the agent that called `exit_loop` was overwritten with empty text; on 2.15 `exit_loop` keeps the previous value and makes no extra model call (executed). Splitting review from rewrite is still the clearer design:

```python
from google.adk.tools import exit_loop

reviewer = Agent(
    name="reviewer",
    model=MODEL,
    instruction="Review this code:\n{current_code}\nIf it has no issues, call exit_loop. Otherwise list the issues.",
    tools=[exit_loop],
    output_key="review_notes",
)
refiner = Agent(
    name="refiner",
    model=MODEL,
    instruction="Fix these issues:\n{review_notes}\n\nCode:\n{current_code}\nReturn only the code.",
    output_key="current_code",
)
refinement_loop = LoopAgent(name="code_refinement_loop", sub_agents=[reviewer, refiner], max_iterations=3)
# session state={"current_code": ...}; executed: issues -> rewrite -> exit_loop, current_code kept
```

When the cap is hit without `exit_loop`, return a typed status (e.g. `ITERATION_LIMIT`) to the caller, not the last draft as if it passed review. A same-model reviewer is not independent verification — gate on deterministic checks (tests, validators) where they exist.

## 4. Composition patterns

| Pattern | Use case | Structure |
|---|---|---|
| Graph (2.x) | Any of the below for new code | `Workflow(name, edges=[...])` + `Runner(node=...)` (§0) |
| Sequential | A feeds B feeds C | `SequentialAgent(sub_agents=[a, b, c])` (deprecated) |
| Parallel + synthesize | Independent perspectives | `SequentialAgent([ParallelAgent([a, b]), synthesizer])` |
| Loop | Refine until a check passes | `LoopAgent(sub_agents=[reviewer, refiner], max_iterations=N)` |
| Handoff | Intent routing; the specialist talks to the user | root `sub_agents=[s1, s2]` (`transfer_to_agent` is injected) |
| Agent as tool | Parent keeps control, typed I/O | `tools=[AgentTool(agent=specialist)]` |

Orchestrators accept no model callbacks (`extra_forbidden`); screen input in the route. Handoff rules: `adk-agent-handoff.md`.
