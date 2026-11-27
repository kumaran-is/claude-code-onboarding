# ADK Agent Types — Workflow graphs, agents, and composition

Install pin: `google-adk==2.15.1` (`google-genai==2.34.0`). FunctionNode graphs, scripted `LlmAgent`-in-graph (`output_key` → `{key}`), and **`ctx.run_node(LlmAgent)`** (RetryConfig, `ITERATION_LIMIT`, `Event(state=...)`) **executed on 2.15.1**. Live Gemini: **NOT TESTED**. Local loopback `RemoteA2aAgent`: `adk-agent-handoff.md`. `MODEL` is `settings.agent_model` — never a literal id. Run every example with `run_once` from `adk-core-patterns.md` §2 (awaited `create_session`, `RunConfig(max_llm_calls=...)`).

Multi-agent only when it beats a single agent or deterministic code on evals (separate tool/authority scopes, isolation of untrusted input, parallel latency) — `multi-agent-patterns` skill. Agents never own multi-step transactions: side effects go through a domain service or durable workflow (`workflow-orchestration-patterns`).

Official homes: [adk.dev/graphs](https://adk.dev/graphs/) (graph Workflows), [adk.dev/graphs/routes](https://adk.dev/graphs/routes/) (routing, `JoinNode`, nested Workflows), [adk.dev/graphs/dynamic](https://adk.dev/graphs/dynamic/) (`ctx.run_node` loops), [adk.dev/workflows/collaboration](https://adk.dev/workflows/collaboration/) (`mode=` teams), [adk.dev/2.0](https://adk.dev/2.0/) (deprecations). Graph APIs below are copied from those pages and from `google-adk` 2.15.1 source (`google.adk.workflow`: `Workflow`, `JoinNode`, `DEFAULT_ROUTE`, `START`, `FunctionNode`, `node`). FunctionNode and scripted `LlmAgent`-in-graph variants **executed on 2.15.1**.

Architecture choice (when to use `LlmAgent` vs a graph vs a coordinator vs RAG): `google-adk/SKILL.md` → Choose the architecture. Coordinator `mode=` teams and Sequential/Parallel/Loop keep-vs-migrate: `adk-agent-teams-and-migration.md`.

`Runner` takes **exactly one** of `app=`, `agent=`, or `node=` (2.15.1). Graphs: `Runner(app_name=..., node=workflow, session_service=...)` or `App(name=..., root_agent=workflow)`. Tests: `InMemoryRunner(node=workflow, app_name=...)` (`node=` **executed** on 2.15.1; `agent=workflow` also constructs but is typed `BaseAgent`). Function nodes must be **named** functions — a `lambda` fails with `Node name '<lambda>' must be a valid Python identifier` (executed on 2.15.1).

## 0. Sequential graph (preferred pipeline)

Each node's return value is the next node's `node_input` — the parameter **must** be named `node_input` (`_node_input` is looked up in state and fails). Default `parameter_binding='state'` fills every other required argument from session state (**executed** on 2.15.1: `greet(name, city)` with `state={"name","city"}` → `"Ada@Paris"`; missing `city` → `ValueError` subclass, not a public export). `parameter_binding='node_input'` binds those args from a predecessor **dict**. `output_key` is still useful when a later **instruction template** must read `{key}` (scripted `LlmAgent` pipeline **executed**).

```python
from google.adk import Agent, Event, Workflow
from pydantic import BaseModel


class CityTime(BaseModel):
    time_info: str
    city: str


city_generator = Agent(
    name="city_generator_agent",
    model=MODEL,
    instruction="Return the name of one city. Return only the name.",
)


def lookup_time(node_input: str) -> CityTime:
    return CityTime(time_info="10:10 AM", city=node_input.strip())


city_report = Agent(
    name="city_report_agent",
    model=MODEL,
    input_schema=CityTime,
    instruction="You receive a CityTime. Output one line: it is that time in that city.",
)


def completed_message(node_input: str):
    return Event(message=f"{node_input}\n WORKFLOW COMPLETED.")


root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", city_generator, lookup_time, city_report, completed_message),
    ],
)
# Runner(app_name="city", node=root_agent, session_service=session_service)
```

Source: [adk.dev/graphs](https://adk.dev/graphs/). `"START"` and `from google.adk.workflow import START` are equivalent.

At **run time**, at most one terminal node may produce non-`None` output in the same run (`ValueError`: "multiple terminal nodes produced output", 2.15.1; the subclass is not a public export). Several terminals that only emit `message=` (no `output`) are legal. Merge output-producing branches with a `JoinNode` ([adk.dev/graphs/routes](https://adk.dev/graphs/routes/)).

An identifier-like `{name}` in an `instruction` string must exist in session state when that agent runs — a missing key raises `KeyError: Context variable not found` (executed on 2.15.0). Use `{name?}` for optional keys; use `instruction=lambda ctx: TEXT` when the text contains placeholder-like braces (callables bypass templating).

## 0.1 Graph HITL (`RequestInput`)

Official Python pattern ([adk.dev/graphs/human-input](https://adk.dev/graphs/human-input/)): a Workflow node **yields** `RequestInput` and pauses until the user replies. Default `rerun_on_resume` is `False` on `FunctionNode` and `True` on `Workflow` (Python names; 2.15.1 source). The reply is **untrusted user input** — validate it (or pass `response_schema`) before using it. **Executed on 2.15.1:** resume with `FunctionResponse(id=interrupt_id, name="adk_request_input", response={"result": 21})` plus `invocation_id` from the pause event; `step2` received `int` 21 and returned 42.

```python
from google.adk import Workflow
from google.adk.events import RequestInput


def step1():
    yield RequestInput(message="Enter a number:", response_schema=int)


def step2(node_input):
    if not isinstance(node_input, int):
        return {"ok": False, "error_code": "INVALID_INPUT"}
    return node_input * 2


root_agent = Workflow(name="root_agent", edges=[("START", step1, step2)])
```

Never catch `BaseException` in that node: it traps `NodeInterruptedError` and breaks resume ([adk.dev/2.0](https://adk.dev/2.0/)). Tool-level yes/no approval is separate: `FunctionTool(..., require_confirmation=True)` (`adk-tools-basic.md`).

## 1. Parallel fan-out and join

Fan-out from `START` (or any shared source) into independent nodes, then a `JoinNode` waits for every predecessor and emits a `dict` keyed by predecessor **name**.

```python
from google.adk import Agent, Workflow
from google.adk.workflow import JoinNode

technical = Agent(name="technical_analyst", model=MODEL,
                  instruction="Analyze technical feasibility of the user topic.")
market = Agent(name="market_analyst", model=MODEL,
               instruction="Analyze the market for the user topic.")
gather = JoinNode(name="gather")
synthesizer = Agent(
    name="synthesizer",
    model=MODEL,
    instruction="Synthesize a recommendation from the joined analyses.",
)

full_analysis = Workflow(
    name="full_analysis",
    edges=[
        ("START", technical, gather),
        ("START", market, gather),
        (gather, synthesizer),
    ],
)
```

Source: [adk.dev/graphs/routes](https://adk.dev/graphs/routes/) (`JoinNode` exported from `google.adk.workflow` in 2.15.1). Nodes that feed a join must produce output; attach `RetryConfig` on flaky predecessors ([adk.dev/graphs/retry](https://adk.dev/graphs/retry/)). Parallel branches multiply model calls; `RunConfig(max_llm_calls=N)` covers the whole graph.

A routing-map value may itself be a tuple (fan-out on that route): `{"route_x": (node_a, node_b)}` ([adk.dev/graphs/routes](https://adk.dev/graphs/routes/)).

## 2. Route branches

A FunctionNode returns `Event(route=...)`; the next edge row maps each route value to a node. Route values may be `str`, `int`, or `bool`. A list of routes dispatches every matching branch. `DEFAULT_ROUTE` (`"__DEFAULT__"`) matches when no other route on that source matches.

```python
from google.adk import Agent, Event, Workflow
from google.adk.workflow import DEFAULT_ROUTE

process_message = Agent(
    name="process_message",
    model=MODEL,
    instruction='Classify into "BUG", "CUSTOMER_SUPPORT", or "LOGISTICS". '
    "If more than one applies, reply with a comma-separated list.",
)


def router(node_input: str):
    routes = [part.strip() for part in str(node_input).split(",")]
    return Event(route=routes)


def handle_bug():
    return Event(message="Handling bug...")


def handle_support():
    return Event(message="Handling customer support...")


def handle_unknown():
    return Event(message="Could not classify that request.")


root_agent = Workflow(
    name="routing_workflow",
    edges=[
        ("START", process_message, router),
        (
            router,
            {
                "BUG": handle_bug,
                "CUSTOMER_SUPPORT": handle_support,
                DEFAULT_ROUTE: handle_unknown,
            },
        ),
    ],
)
```

Source: [adk.dev/graphs](https://adk.dev/graphs/) + [adk.dev/graphs/routes](https://adk.dev/graphs/routes/). Treat the model's classification as a proposal. A list of routes can fire several branches in one run — those handlers must emit `message=` only, or join before producing `output`. A branch target may be an `Agent`, a function, or a nested `Workflow`.

## 3. Nested / multi-workflows

A `Workflow` is itself a node. Put it on another Workflow's edges to encapsulate a reusable sub-process. Inner node events bubble to the parent for traces; the inner terminal output becomes the nested-workflow node's output ([adk.dev/graphs/routes](https://adk.dev/graphs/routes/)).

```python
from google.adk import Event, Workflow


def a_trim(node_input: str) -> str:
    return node_input.strip()


def router(node_input: str):
    route = "RUN_WORKFLOW_C" if node_input.isupper() else "RUN_WORKFLOW_B"
    return Event(route=route, output=node_input)


def frame_b(node_input: str) -> str:
    return f"[B] {node_input}"


def frame_c(node_input: str) -> str:
    return f"[C] {node_input}"


workflow_b = Workflow(name="workflow_B", edges=[("START", frame_b)])
workflow_c = Workflow(name="workflow_C", edges=[("START", frame_c)])

parent = Workflow(
    name="parent_workflow",
    edges=[
        ("START", a_trim, router),
        (router, {"RUN_WORKFLOW_B": workflow_b, "RUN_WORKFLOW_C": workflow_c}),
    ],
)
```

Do not give the inner Workflow two **output-producing** terminals. Do not nest a Workflow under an `LlmAgent` via `sub_agents=` — that is the remaining SequentialAgent exception (`adk-agent-teams-and-migration.md`).

## 4. Bounded loops (dynamic Workflow)

When control flow is an ordinary loop, use a dynamic node and `ctx.run_node` instead of a graph back-edge ([adk.dev/graphs/dynamic](https://adk.dev/graphs/dynamic/)). The official Python sample uses `while check_resp.findings`; production code **must** also cap iterations and emit a typed `ITERATION_LIMIT` rather than returning the last draft as if it passed. The sample below is illustrative (`MAX_FIX_ROUNDS = 3`, no `retry_config`). **Executed on 2.15.1** (`adk-testing.md`): `for _ in range(2)`; `coder.retry_config=RetryConfig(..., exceptions=[ConnectionError])` retried then succeeded (2 calls); a `RuntimeError` not in `exceptions` was not retried (1 call); persistent lint findings emitted `ITERATION_LIMIT`; dict `node_input` to `fixer` and `yield Event(state={"code", "findings"})` (`state_delta`) both ran.

```python
from google.adk import Context, Event, Workflow
from google.adk.agents import LlmAgent
from google.adk.workflow import node

MAX_FIX_ROUNDS = 3

coder = LlmAgent(name="generator_agent", model=MODEL,
                 instruction="Write Python for the user request. Output code only.")
fixer = LlmAgent(name="fixer_agent", model=MODEL,
                 instruction="Refactor current code. Apply only the listed findings.")


@node(name="lint_reviewer")
async def compile_lint_check(ctx: Context, node_input: str) -> dict:
    return {"findings": ""}  # real code: tests/linter, not an LLM


@node(rerun_on_resume=True)
async def code_workflow(ctx: Context, node_input: str):
    code = await ctx.run_node(coder, node_input)
    check = await ctx.run_node(compile_lint_check, code)
    for _ in range(MAX_FIX_ROUNDS):
        if not check.get("findings"):
            yield Event(output=code)
            return
        yield Event(state={"code": code, "findings": check["findings"]})
        code = await ctx.run_node(fixer, {"code": code, "findings": check["findings"]})
        check = await ctx.run_node(compile_lint_check, code)
    if not check.get("findings"):
        yield Event(output=code)
        return
    yield Event(output={"ok": False, "error_code": "ITERATION_LIMIT", "data": code})


root_agent = Workflow(name="code_refine", edges=[("START", code_workflow)])
```

`FunctionNode(timeout=...)` is a per-node deadline (`NodeTimeoutError`), not a loop cap. Always also set `RunConfig(max_llm_calls=N)`. `rerun_on_resume=True` is required on orchestrators that call `ctx.run_node()`.

Coordinator teams (`mode=`), `AgentTool`, and Sequential/Parallel/Loop keep-vs-migrate: `adk-agent-teams-and-migration.md`.

## 5. Resilience on nodes

| Need | 2.x construct |
|---|---|
| Retry a listed exception | `FunctionNode(func=f, name="f", retry_config=RetryConfig(max_attempts=3, initial_delay=0.5, exceptions=[ConnectionError]))` — same `retry_config` field on `LlmAgent` when it runs as a graph node (`ctx.run_node` **executed** 2.15.1) |
| Per-node deadline | `FunctionNode(..., timeout=10.0)` → `NodeTimeoutError` |
| Skip completed children after HITL | `@node(rerun_on_resume=True)` on orchestrators that call `ctx.run_node` |

Do not wrap tool or node bodies in a broad `except Exception` that turns failures into success-shaped values — that defeats `RetryConfig`. Never catch `BaseException`. Yield events instead of appending to `session.events`. A custom `BaseAgent` subclass that overrides `_run_async_impl` is bypassed in 2.x (`BaseAgent` is a `BaseNode`): port the logic to a `@node` function. App-wide static policy: `GlobalInstructionPlugin` on `App`, not deprecated `global_instruction` on the agent (2.15.1 `LlmAgent.global_instruction` docstring).

## 6. Graph cheat-sheet

| Pattern | Structure |
|---|---|
| Sequential | `Workflow(edges=[("START", a, b, c)])` |
| Parallel + synthesize | `("START", a, join), ("START", b, join), (join, synth)` with `JoinNode` |
| Conditional | `(router, {"BUG": bug, DEFAULT_ROUTE: fallback})` |
| Nested | `(router, {"RUN_B": workflow_b, "RUN_C": workflow_c})` |
| Bounded loop | `@node(rerun_on_resume=True)` + `for _ in range(N): await ctx.run_node(...)` |

Model callbacks exist only on `LlmAgent`. Screen input for a Workflow in the route or a FunctionNode before the first model node. Teams, `AgentTool`, live `mode=`, and Sequential/Parallel/Loop: `adk-agent-teams-and-migration.md`.
