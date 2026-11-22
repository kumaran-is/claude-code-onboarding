# ADK Agent Handoff and output_key Rules

Executed with `google-adk==1.29.0` and a scripted fake model. `MODEL` = `settings.agent_model`.

## 1. Handoff (transfer) vs agent-as-tool

| | Transfer (`sub_agents`) | Agent as tool (`AgentTool`) |
|---|---|---|
| Control | Moves to the sub-agent, which answers the user | Parent keeps control and gets the result back |
| Use for | Intent routing to specialists | A bounded sub-task with typed input/output |
| Final author | the sub-agent (executed: `billing_agent`) | the parent (executed: `parent`) |

When `sub_agents` is set, ADK injects the `transfer_to_agent` tool itself (executed: the root's tool list was `['transfer_to_agent']` with no `tools=`). Do not also list it in `tools=`. Each sub-agent's `description` is what the router model sees — keep it specific.

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
- Cross-service agents (A2A) are an optional extension, used only when agents are deployed separately — `multi-agent-patterns` skill.

## 2. output_key state passing

- `output_key="name"` stores the agent's final response in session state after the agent finishes; later agents read it with `{name}` in `instruction`, tools/callbacks via `tool_context.state["name"]`.
- With `output_schema`, the stored value is the **validated dict**, not a JSON string (executed) — read it with `Model.model_validate(state["name"])`. A schema-invalid final response raises inside the run (`adk-structured-output.md` §3).
- Keys must be unique per pipeline. Do not set `output_key` on the agent that calls `exit_loop` (it is overwritten with empty text — `adk-agent-types.md` §3).
- Only set `output_key` where a downstream step needs it.

```python
from google.adk.agents import SequentialAgent

stage_a = Agent(name="stage_a", model=MODEL, instruction="Summarize the topic.", output_key="stage_a_output")
stage_b = Agent(name="stage_b", model=MODEL, instruction="Expand on this summary: {stage_a_output}", output_key="stage_b_output")
pipeline = SequentialAgent(name="pipeline", sub_agents=[stage_a, stage_b])
```
