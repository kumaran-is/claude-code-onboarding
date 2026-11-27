# Agentic AI — Advanced Agent Patterns

Supervisor routing, `Command`-based routing, sub-graph composition and native `Send` map-reduce. Rule for supervisor/`Command` flows: **the model proposes a route, code validates it** against a closed enum *and* code-owned transition rules before `Command(goto=...)`, with a hop cap and a conservative fallback. Fan-out uses `Send`, not a model-chosen node list.

Executed: supervisor path on langgraph 1.0.7 (scripted deciders, `ruff` + `mypy --strict` clean): researcher → coder → reviewer → FINISH (`OK`); `ROUTE_REJECTED` / `HOP_LIMIT` / `ROUTER_INVALID`; triage fallback to `general`. Pattern 6 (subgraph + `RunnableConfig`) and Pattern 7 (`Send` map-reduce) executed on langchain 1.5.2 / langgraph 1.2.24. Nested `TypedDict`s for `Send` routing functions raise `NameError` — keep schemas at module scope.

REMOVED from the previous version: `goto=parse_category(analysis.content)` (free-text parsing straight into a node name), a supervisor with no hop cap that could loop until the recursion limit, `iteration_count`/`thread_id` passed into sub-graph state, and the final answer written by the supervisor's routing call.

## Pattern 4: Supervisor with validated routes and a hop cap

```python
Worker = Literal["researcher", "coder", "reviewer"]
MAX_HOPS = 6


class SupervisorDecision(BaseModel):
    route: Literal["researcher", "coder", "reviewer", "FINISH"]        # closed enum


class TeamState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    hops: int
    visited: list[str]
    status: str


def allowed_next(visited: list[str]) -> set[str]:
    """Code-owned transition rules: the model's choice must also be permitted here."""
    allowed = {"researcher", "coder", "FINISH"}
    if "coder" in visited:
        allowed.add("reviewer")
    return allowed


def build_supervisor(model: BaseChatModel, decider: Any, checkpointer: Any = None) -> Any:
    async def supervisor(state: TeamState) -> Command[Literal["researcher", "coder", "reviewer", "__end__"]]:
        if state["hops"] >= MAX_HOPS:
            return Command(goto="__end__", update={"status": "HOP_LIMIT"})
        try:
            decision: SupervisorDecision = await decider.ainvoke([SystemMessage(SUPERVISOR_PROMPT), *state["messages"]])
        except ValidationError:
            logger.warning("supervisor_invalid_route")
            return Command(goto="__end__", update={"status": "ROUTER_INVALID"})
        if decision.route not in allowed_next(state["visited"]):
            logger.warning("supervisor_route_rejected", route=decision.route)
            return Command(goto="__end__", update={"status": "ROUTE_REJECTED"})
        if decision.route == "FINISH":
            return Command(goto="__end__", update={"status": "OK"})
        return Command(goto=decision.route, update={"hops": state["hops"] + 1})

    def make_worker(name: Worker) -> Any:
        async def worker(state: TeamState) -> Command[Literal["supervisor"]]:
            response = await model.ainvoke([SystemMessage(WORKER_PROMPTS[name]), *state["messages"]])
            return Command(goto="supervisor", update={
                "messages": [AIMessage(response.text, name=name)], "visited": [*state["visited"], name]})
        return worker

    g = StateGraph(TeamState)
    g.add_node("supervisor", supervisor)
    for w in ("researcher", "coder", "reviewer"):
        g.add_node(w, make_worker(w))
    g.add_edge(START, "supervisor")
    return g.compile(checkpointer=checkpointer)
```

- `decider` = `chat_model("fast").with_structured_output(SupervisorDecision)`; out-of-enum output raises at validation.
- `Command[Literal[...]]` return annotations tell LangGraph the possible destinations (needed for graph rendering and validation without explicit edges).
- `MAX_HOPS` is a business limit with its own typed status; `recursion_limit` stays the hard backstop. Map every non-`OK` status at the route.
- Workers that hold different tools or permissions: give each its own allowlist and pass scope through `context`, never through messages (`multi-agent-patterns`).
- Workers' outputs are model text; another worker reads them as data. A worker never gains authority because the supervisor "approved" its output.

## Pattern 5: `Command` triage with a deterministic fallback

```python
Category = Literal["technical", "billing", "general"]


class Triage(BaseModel):
    category: Category


async def triage(state: TriageState) -> Command[Category]:
    try:
        async with asyncio.timeout(timeout_s):
            result: Triage = await classifier.ainvoke(state["messages"])
        return Command(goto=result.category, update={"category": result.category, "reason_code": "MODEL"})
    except (TimeoutError, ValidationError) as exc:
        logger.warning("triage_fallback", error_type=type(exc).__name__)
        return Command(goto="general", update={"category": "general", "reason_code": "FALLBACK"})
```

Put deterministic rules before the classifier (`agentic-llm-routing.md` §Complexity router) and choose the fallback destination as the *safest* handler, not the most common one. When the same message could route to several handlers, an embedding router with threshold + margin (`agentic-llm-routing.md` §Intent routing) avoids a generation call.

## Pattern 6: Sub-graph composition

```python
rag_graph = build_rag_subgraph(...)          # compiled, no checkpointer of its own


async def rag_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    org_id = config["configurable"]["org_id"]  # server-set; never from messages
    result = await rag_graph.ainvoke(
        {"query": latest_user_text(state), "org_id": org_id}, config
    )
    if result.get("status") != "OK":
        return {"status": result.get("status", "INSUFFICIENT_EVIDENCE"), "messages": []}
    text = result.get("answer") or result.get("generation") or ""
    return {"messages": [AIMessage(text)]}
```

Or add the compiled sub-graph directly as a node when parent and child share state keys: `parent.add_node("rag", rag_graph)`.

- Pass the parent's `config: RunnableConfig` so callbacks, tracing and `context` propagate. A required `config` typed as `Any` is not injected (executed: `TypeError`).
- Budget (executed, langgraph 1.2.24): both `add_node(compiled_subgraph)` and `child.invoke(..., config)` get a **fresh** step counter at the config's `recursion_limit` *value*, not the parent's remaining steps. Pass `{**config, "recursion_limit": remaining}` when the child must not get a full fresh allowance. Uncaught child errors bubble.
- The sub-graph does not get its own checkpointer unless it needs independent persistence; it inherits the parent's.
- No `thread_id`, `user_id` or counters in sub-graph input state: identity flows through `config`/`context`.
- A sub-graph's typed failure (e.g. `INSUFFICIENT_EVIDENCE`) is mapped by the parent, not re-interpreted from text.

## Pattern 7: `Send` map-reduce (native fan-out)

The worker receives **`Send.arg` as its state**. Returned keys merge into the parent through a reducer. Use `Send` for expensive/resumable per-item work; a bounded `TaskGroup` for cheap read-only I/O (`agentic-architecture-choice.md`). `recursion_limit` does not cap branch width.

```python
from typing import Annotated, TypedDict
import operator
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

class ResearchState(TypedDict):
    topics: list[str]
    findings: Annotated[list[str], operator.add]
    status: str

class TopicState(TypedDict):
    topic: str

MAX_FANOUT = 8  # settings.max_parallel_branches


def cap(state: ResearchState) -> dict[str, str]:
    if len(state["topics"]) > MAX_FANOUT:
        return {"status": "FANOUT_LIMIT"}
    return {"status": "OK"}

def after_cap(state: ResearchState):
    if state["status"] != "OK":
        return END
    return [Send("research_one", {"topic": t}) for t in state["topics"]]  # topic only; never org/user/thread ids

def research_one(state: TopicState) -> dict[str, list[str]]:
    return {"findings": [f"notes:{state['topic']}"]}

g = StateGraph(ResearchState)
g.add_node("cap", cap)
g.add_node("research_one", research_one)
g.add_edge(START, "cap")
g.add_conditional_edges("cap", after_cap, ["research_one", END])
g.add_edge("research_one", END)
```

Executed (langgraph 1.2.24): two topics produced both findings; nine topics ended `FANOUT_LIMIT` with no worker runs. Never let the model supply node names. Workers return a typed per-item status on classified errors (one uncaught failure fails the superstep). No `interrupt()` or writes in workers — reduce, then gate. Charge fan-out to the shared request budget (`agentic-cost-optimization.md`). Keep `TopicState` at module scope (nested worker annotations → `NameError`).
