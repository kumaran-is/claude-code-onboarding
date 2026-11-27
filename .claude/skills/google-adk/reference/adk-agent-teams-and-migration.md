# ADK coordinator teams and prebuilt-orchestrator migration

Install pin: `google-adk==2.15.1`. FunctionNode graphs, scripted `LlmAgent`-in-graph, `mode=task` `finish_task`, and chat-coordinator + task-specialist **executed on 2.15.1** (`adk-testing.md` §3). `LoopAgent`/`ParallelAgent` `run_live()` raise `NotImplementedError` (**executed**). Live Gemini bidirectional: **NOT TESTED**. Architecture choice: `google-adk/SKILL.md` → Choose the architecture. Graph APIs: `adk-agent-types.md`.

## 1. When to use a coordinator vs a graph route vs AgentTool

| Situation | Construct |
|---|---|
| Closed label set; **code** picks the branch | `Event(route=...)` + routing map (`adk-agent-types.md` §2) |
| Specialist must **talk to the user** (clarify, negotiate) | Coordinator `Agent(sub_agents=...)` with `mode=` on specialists |
| Parent keeps control and needs typed I/O | `AgentTool(agent=...)` (`adk-agent-handoff.md`) |
| Every answer must be grounded | RAG retrieve as a **graph FunctionNode / MCP step**, then generate |
| Retrieval is optional | RAG as a **model-chosen tool** with ACL in the query (`rag-architect`) |

## 2. Collaborative agent teams (`mode=`)

Root `mode` must be `chat` (default) or `task`; `single_turn` as root raises `ValueError` (**executed** on 2.15.1). Set `task`/`single_turn` on specialist **leaves** — a `task` agent cannot have `sub_agents` ([adk.dev/workflows/collaboration](https://adk.dev/workflows/collaboration/)). ADK injects a delegation tool named after each sub-agent. Verified on 2.15.1: `LlmAgent.mode` is `Literal['chat', 'task', 'single_turn'] | AgentMode | None`.

| Mode | User talk | Return to parent | Parallel |
|---|---|---|---|
| `chat` (default as sub-agent) | Free conversation | Manual `transfer_to_agent` | No |
| `task` | Clarifying questions | Automatic via `finish_task` | No |
| `single_turn` (default as a Workflow **node**) | None | Automatic with result | Yes |

```python
from google.adk import Agent
from google.adk.tools import FunctionTool
# Lookups/booking are MCP tools from the project factory (SKILL.md Iron Law). Placeholders:

weather_agent = Agent(
    name="weather_checker",
    model=MODEL,
    mode="single_turn",
    instruction="Look up weather. Return a short factual summary.",
    tools=[get_weather],
)
flight_agent = Agent(
    name="flight_booker",
    model=MODEL,
    mode="task",
    instruction="Find and book a flight. Call finish_task when done.",
    tools=[search_flights, FunctionTool(book_flight, require_confirmation=True)],
)
root = Agent(
    name="travel_planner",
    model=MODEL,
    instruction="Plan the trip. Delegate weather to weather_checker and flights to flight_booker.",
    sub_agents=[weather_agent, flight_agent],
)
```

Rules ([adk.dev/workflows/collaboration](https://adk.dev/workflows/collaboration/), 2.15.1 source):
- `task` agents are **leaves** (no `sub_agents`).
- As a **Workflow node**, an unset mode is `single_turn`. Set `mode="task"` or `"chat"` only when that node must speak on a **live** connection ([adk.dev/live/workflows](https://adk.dev/live/workflows/)). 2.15.1 source accepts `task`/`chat`/`single_turn` on node agents; **not executed**. Prefer `single_turn` for request/response hops until a fixture proves `task` on a graph node. **Live + mixed-mode teams: NOT TESTED.**
- Same principal, `org_id`, and trace id flow through every hop. `RunConfig(max_llm_calls=...)` covers the tree.
- A2A: `adk-agent-handoff.md`. Chat coordinator + `task` specialist `finish_task`: **executed** (`adk-testing.md` §3). `single_turn` specialist + `transfer_to_agent` coexistence: **NOT TESTED**.

## 3. Prebuilt orchestrators — keep vs migrate

They **still run** on 2.15.1 ([adk.dev/workflows/patterns](https://adk.dev/workflows/patterns/): “the examples below still run”). Import-checked: constructing each emits `DeprecationWarning: <Agent> is deprecated in favor of Workflow and will be removed in a future version. Workflow cannot yet be used as an LlmAgent sub-agent.`

| Keep (for now) | Migrate now |
|---|---|
| Pipeline already passes golden evals; no routes/HITL/live needed | New multi-step service, or you need `JoinNode`, `Event(route=)`, `RequestInput`, or nested Workflows |
| Must be listed in `LlmAgent.sub_agents` | Top-level `Runner` root (`node=workflow`) |
| — | Live path: `LoopAgent` and `ParallelAgent` raise `NotImplementedError` under `run_live()` (**executed** on 2.15.1; [adk.dev/live/workflows](https://adk.dev/live/workflows/)) |

| Prebuilt | Graph 2.x (`adk-agent-types.md`) |
|---|---|
| `SequentialAgent(sub_agents=[a, b])` | `Workflow(edges=[("START", a, b)])` |
| `SequentialAgent(sub_agents=[ParallelAgent(sub_agents=[a, b]), synth])` | `JoinNode` fan-out/fan-in |
| `LoopAgent(..., max_iterations=N)` + `exit_loop` | `@node` + `for _ in range(N)` and typed `ITERATION_LIMIT` |

`LoopAgent.max_iterations` defaults to `None` = **unbounded** (executed on 2.15.0). Always set it. When the cap is hit without `exit_loop`, return typed `ITERATION_LIMIT`, not the last draft as a pass.
