# Agentic AI — Basic Agent Patterns

Start with the least machinery that works: a deterministic workflow or one structured model call when the steps are known; `create_agent` for a tool loop; a custom `StateGraph` only when you need control flow `create_agent` doesn't give you. Every run gets `recursion_limit`, a deadline and typed status mapping at the route (`agentic-templates-core.md`).

Executed (langchain 1.2.8 / langgraph 1.0.7, scripted models, `ruff` + `mypy --strict` clean, 2 tests): Pattern 2 answered after one tool call and raised `GraphRecursionError` at `recursion_limit=6` with a looping model; Pattern 3 ran only the planned specialists in code-defined order and rejected an unknown specialist name at schema validation.

REMOVED from the previous version: `iteration_count` in state with an `END` route on reaching the cap (the run ended on an unanswered tool call that the route returned as the answer); a hard-coded plan with "Simplified; parse from LLM response"; specialist outputs and research text interpolated into `SystemMessage`s; a `provider_factory` dependency.

## Pattern 1: `create_agent` (default for tool-using agents)

```python
agent = create_agent(
    chat_model("standard"),
    tools=resolve_allowlist(TOOL_REGISTRY, settings.support_agent_tools),
    system_prompt=SUPPORT_POLICY,                      # static text, versioned
    context_schema=RequestCtx,                         # verified scope for ToolRuntime
    middleware=[
        ModelCallLimitMiddleware(run_limit=settings.max_model_calls, exit_behavior="error"),
        ToolCallLimitMiddleware(run_limit=settings.max_tool_calls, exit_behavior="error"),
    ],
    checkpointer=saver,                                # from the lifespan
)
```

HITL, retry/failover, screening and metrics are added as middleware (`agentic-streaming-hitl.md`, `agentic-templates-resilience.md`, `agentic-guardrails-security.md`, `agentic-observability.md`). Put a **deterministic pre-gate** in the route before the agent when some requests must never reach it (unsupported capability, safety-critical intent that goes to a human, missing account linkage): code decides, then the agent runs.

## Pattern 2: custom ReAct `StateGraph`

```python
AGENT_POLICY = "You answer questions about the user's documents. Use tools for facts."


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def build_react_graph(model: BaseChatModel, tools: Sequence[BaseTool], checkpointer: Any = None) -> Any:
    bound = model.bind_tools(tools)

    async def agent(state: AgentState) -> dict[str, Any]:
        response = await bound.ainvoke([SystemMessage(AGENT_POLICY), *state["messages"]])
        return {"messages": [response]}

    def route(state: AgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "__end__"

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(list(tools)))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route)
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=checkpointer)
```

- The hard loop bound is `recursion_limit` in the run config (each agent→tools round trip is 2 super-steps); the route maps `GraphRecursionError` to `ITERATION_LIMIT`.
- An optional `iteration_count` for an earlier, graceful stop is fine only if reaching it routes to a `limit_reached` node that returns a typed status (`agentic-templates-resilience.md`), never to `END` on a pending tool call.
- The system prompt is static; per-request facts go in `HumanMessage`/state, never interpolated into `SystemMessage`.

## Pattern 3: planned specialists with a validated plan

```python
Specialist = Literal["researcher", "analyst", "writer"]
ORDER: tuple[Specialist, ...] = ("researcher", "analyst", "writer")
PROMPTS: dict[Specialist, str] = {
    "researcher": "You gather relevant facts. Cite sources from the provided material only.",
    "analyst": "You identify patterns in the provided research. Do not invent data.",
    "writer": "You write the final answer from the provided research and analysis.",
}


class Plan(BaseModel):
    specialists: list[Specialist] = Field(min_length=1, max_length=3)    # closed enum


class TeamState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[Specialist]
    outputs: dict[str, str]


def build_team_graph(model: BaseChatModel, planner: Any, checkpointer: Any = None) -> Any:
    async def plan_node(state: TeamState) -> dict[str, Any]:
        plan: Plan = await planner.ainvoke([SystemMessage("Choose which specialists are needed."), *state["messages"]])
        ordered = [s for s in ORDER if s in set(plan.specialists)]      # code fixes order, drops duplicates
        return {"plan": ordered, "outputs": {}}

    def make_specialist(name: Specialist) -> Any:
        async def node(state: TeamState) -> dict[str, Any]:
            material = "\n\n".join(f"<{k}>\n{v}\n</{k}>" for k, v in state["outputs"].items())
            question = state["messages"][0].content
            response = await model.ainvoke([SystemMessage(PROMPTS[name]), HumanMessage(f"{material}\n\nTask: {question}")])
            return {"outputs": {**state["outputs"], name: response.text}}
        return node

    def next_step(state: TeamState) -> str:
        return next((s for s in state["plan"] if s not in state["outputs"]), "finish")

    async def finish(state: TeamState) -> dict[str, Any]:
        last = next(s for s in reversed(ORDER) if s in state["outputs"])
        return {"messages": [AIMessage(state["outputs"][last])]}

    g = StateGraph(TeamState)
    g.add_node("plan", plan_node)
    for s in ORDER:
        g.add_node(s, make_specialist(s))
        g.add_conditional_edges(s, next_step, [*ORDER, "finish"])
    g.add_node("finish", finish)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", next_step, [*ORDER, "finish"])
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
```

`planner` is `chat_model("fast").with_structured_output(Plan)`. Planner timeout or invalid output → a conservative default plan chosen by code (e.g. `["researcher", "writer"]`) with a logged reason code. Earlier specialists' outputs are model-generated text: pass them as delimited data in the user turn, never as instructions. When specialists need different tools or permissions, see `multi-agent-patterns`.

## Choosing

| Need | Pattern |
|---|---|
| Fixed steps, no tool choice | Plain code / workflow, or one structured call |
| Tool loop with standard controls | Pattern 1 |
| Custom routing, extra nodes, non-message state | Pattern 2 |
| Several roles over one task | Pattern 3, or supervisor/handoff patterns in `agentic-templates-advanced.md` |
