# ADK Agent Handoff and output_key Rules

`transfer_to_agent` snippets executed with `google-adk==1.29.0` and re-checked on `2.15.0`. Workflow `output_key` pipeline and **loopback A2A** (`RemoteA2aAgent` ↔ `A2aAgentExecutor`) **executed on 2.15.1** with a scripted `BaseLlm`. `MODEL` = `settings.agent_model`.

## 1. Handoff (transfer) vs agent-as-tool

| | Transfer (`sub_agents`) | Agent as tool (`AgentTool`) |
|---|---|---|
| Control | Moves to the sub-agent, which answers the user | Parent keeps control and gets the result back |
| Use for | Intent routing to specialists | A bounded sub-task with typed input/output |
| Final author | the sub-agent (executed: `billing_agent`) | the parent (executed: `parent`) |

When `sub_agents` is set, ADK injects the `transfer_to_agent` tool itself (executed: the root's tool list was `['transfer_to_agent']` with no `tools=`). Collaborative `mode="task"` / `"single_turn"` specialists also get a **delegation tool named after the sub-agent**; `task` returns via `finish_task` (`adk-agent-teams-and-migration.md` §2). Do not also list those tools in `tools=`. Each sub-agent's `description` is what the router model sees — keep it specific. Root `mode` is `chat` (default) or `task`; `single_turn` as root raises `ValueError`.

```python
from google.adk.agents import Agent
from google.adk.tools import AgentTool

billing_agent = Agent(
    name="billing_agent",
    model=MODEL,
    description="Handles invoices, payments, refunds and subscription changes.",
    instruction="You are a billing specialist. If the question is not about billing, transfer back to router_agent.",
)
technical_agent = Agent(
    name="technical_agent",
    model=MODEL,
    description="Handles bugs, setup problems, API questions and feature usage.",
    instruction="You are a technical support specialist. If the question is about billing, transfer back to router_agent.",
)
router_agent = Agent(
    name="router_agent",
    model=MODEL,
    description="Routes support requests to the right specialist.",
    instruction="Route billing questions to billing_agent and technical questions to technical_agent.",
    sub_agents=[billing_agent, technical_agent],
)

# agent as tool: the parent stays in charge
summarizer = Agent(name="summarizer", model=MODEL, description="Summarizes text.", instruction="Summarize.")
parent = Agent(name="parent", model=MODEL, instruction="Use summarizer for long inputs.", tools=[AgentTool(agent=summarizer)])
```

Routing rules:
- Treat the model's route as a proposal. Deterministic policy runs first (safety phrases, authoritative-state questions answered from records), and the route a model may pick is a closed set.
- A sub-agent never gains authority or scope the caller lacks: the same principal, `org_id` (session state) and trace id flow through every hop.
- Hop and call budgets cover the whole tree (`RunConfig(max_llm_calls=...)`).
- Cross-service agents (A2A) are an optional extension (`multi-agent-patterns`). **Converter path** ([v2.15.1](https://github.com/google/adk-python/releases/tag/v2.15.1)): `last_chunk=False` → `partial=True`; `True` → `partial=False`; the runner skips persist only when `partial is True`. **v2 task-snapshot path (loopback executed 2.15.1):** every chunk is persisted (`partial is None`; session stored both `alpha ` and `alpha beta`). `is_final_response()` is True for each (`not self.partial`) — do not use it as the terminator, and do not use FastAPI §6 (`if event.partial`) for a `RemoteA2aAgent` root. Drain `run_async` and take the last non-error content, or `event.output` after a terminal A2A task state in `custom_metadata["a2a:response"].status.state`. Token streaming needs `A2aAgentExecutorConfig.request_converter` to set `RunConfig(streaming_mode=StreamingMode.SSE)` (the default converter does not). Peer failures are opaque (`Agent execution failed. (error_id: …)`). Client-side `event.error_message` is **not** opaque (`A2A request failed: {e}`) — map it to a typed status; never put it in HTTP/SSE. `timeout=1.0` → `Client Request timed out`. Whether persisted chunks are replayed into the next turn: **NOT TESTED**. Non-loopback A2A and live Gemini: **NOT TESTED**.

## 2. output_key state passing

- `output_key="name"` stores the agent's final response in session state after the agent finishes; later agents read it with `{name}` in `instruction`, tools/callbacks via `tool_context.state["name"]`.
- With `output_schema`, the stored value is the **validated dict**, not a JSON string (executed) — read it with `Model.model_validate(state["name"])`. A schema-invalid final response raises inside the run (`adk-structured-output.md` §3).
- Keys must be unique per pipeline. Do not set `output_key` on a deprecated `LoopAgent` member that calls `exit_loop` (`adk-agent-teams-and-migration.md`).
- Only set `output_key` where a later **instruction template** needs `{name}`. Graph hops pass typed `node_input` without `output_key` (`adk-agent-types.md` §0).

```python
from google.adk import Workflow
from google.adk.agents import Agent

stage_a = Agent(name="stage_a", model=MODEL, instruction="Summarize the topic.", output_key="stage_a_output")
stage_b = Agent(name="stage_b", model=MODEL, instruction="Expand on this summary: {stage_a_output}", output_key="stage_b_output")
pipeline = Workflow(name="pipeline", edges=[("START", stage_a, stage_b)])
# SequentialAgent still runs on 2.15 (DeprecationWarning). New pipelines use Workflow.
# Workflow + output_key executed on 2.15.1 with ScriptedLlm (`adk-testing.md`).
```
