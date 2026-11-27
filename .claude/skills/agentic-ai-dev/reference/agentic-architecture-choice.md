# Architecture choice — LangChain, LangGraph, Deep Agents, ADK

Pick the smallest runtime that matches the control flow. Do not wrap a known procedure in an agent, and do not port Google ADK services onto LangGraph by default.

Verified on langchain 1.5.2 / langchain-core 1.8.4 / langgraph 1.2.24 / langgraph-prebuilt 1.1.3 (isolated venv). `deepagents` is **not** in this toolkit pin.

## Decision table

| Need | Use | Do not |
|------|-----|--------|
| Known steps, typed I/O, no tool loop | Deterministic service; timers/compensation → `workflow-orchestration-patterns` | An agent |
| One structured model call | Provider schema + validator (`llm-inference-and-model-routing.md` §4) | A graph |
| Tool-calling loop, middleware, tool HITL | `create_agent` (`agentic-templates-basic.md`) | `create_react_agent` (still importable; do not use in new code) |
| Custom routing, subgraphs, fan-out/fan-in | `StateGraph` + `Command` / `Send` (`agentic-templates-advanced.md`) | One agent per node |
| Agent-adjacent durable function (resume on the next request) | Functional API `@entrypoint` / `@task` **with a checkpointer** | Using it as a cron/timer engine |
| Long-horizon planning, virtual filesystem, subagents | Optional first-party `deepagents` SDK, pinned in that service | Default for every agent; do not add it to this toolkit lock |
| ADK chosen (Gemini Live, A2A, existing ADK service, team standard) | `google-adk` skill | Rewriting ADK graphs as LangGraph |

`create_agent` compiles to a LangGraph graph. Middleware, checkpointers, streaming and interrupts are LangGraph features reached through that API. Hand-build a `StateGraph` only when you need control flow `create_agent` does not give you.

LangGraph resumes when a **caller** invokes the same thread again. It has no timers and does not auto-restart after a process crash. Long waits, scheduled work and saga compensation stay in `workflow-orchestration-patterns`.

## Native vs application vs optional

| Capability | Where it lives |
|------------|----------------|
| `create_agent`, middleware, `ToolRuntime` | Native LangChain 1.5 |
| `StateGraph`, `Command`, `Send`, `interrupt`, reducers | Native LangGraph 1.2 |
| `@entrypoint` / `@task` | Native LangGraph Functional API |
| `AsyncPostgresSaver` / `AsyncPostgresStore` | `langgraph-checkpoint-postgres` (toolkit pin) |
| Deep Agents harness (planner, filesystem, subagents) | Optional first-party `deepagents` SDK on LangGraph |
| Hybrid search, ACL filters, citations, CRAG | Application + `rag-architect` / `vector-database` |
| LangSmith tracing | Optional env (`LANGSMITH_*`); never mutate `os.environ` in-process |
| Approval records, principal-scoped thread keys, typed HTTP statuses | Application (FastAPI + auth) around native `interrupt` |

## `Send` map-reduce (native fan-out)

The worker node receives **`Send.arg` as its state**, not the parent. Return keys merge into the parent through reducers. Scope stays in run `config`/`context` (`ToolRuntime`); never put `org_id`/`user_id`/`thread_id` or a model-proposed dict into `Send.arg`. Build args from code-validated fields only.

`recursion_limit` counts supersteps, **not** branch width — all `Send`s in one step share one superstep. Call-limit middleware on a child `create_agent` is a **fresh** budget unless the parent passes the remainder. Cap width in code and charge one shared request budget (`agentic-llm-routing.md` `max_parallel_branches`, `agentic-cost-optimization.md` semaphore).

Use `Send` when each item is an expensive model call, must survive a resume, or may interrupt. Use a bounded `TaskGroup`/semaphore for cheap, read-only, idempotent I/O inside one node. Per-item persistence requires a **checkpointer**. Catch classified errors in the worker and return a typed per-item status; one uncaught failure fails the whole superstep. No `interrupt()` or writes inside workers — reduce, then gate in one later node (`agentic-streaming-hitl.md`). Merged findings are untrusted retrieval: user/tool content, never a system prompt.

```python
MAX_FANOUT = 8  # settings.max_parallel_branches

def cap(state: ResearchState) -> dict[str, str]:
    if len(state["topics"]) > MAX_FANOUT:
        return {"status": "FANOUT_LIMIT"}
    return {"status": "OK"}

def after_cap(state: ResearchState):
    if state["status"] != "OK":
        return END
    return [Send("research_one", {"topic": t}) for t in state["topics"]]
```

Keep worker/`Send` state schemas at **module scope**. LangGraph resolves node annotations from the function's globals; a nested `TypedDict` on the worker raises `NameError` at compile time (executed). Full graph: `agentic-templates-advanced.md` Pattern 7.

## Functional API

Use for agent-adjacent flows that resume on the next HTTP request, not for timers or crash-auto-recovery. Durability requires `checkpointer=` on `@entrypoint(...)`. On resume the entrypoint body **re-runs from the top**; only `@task` results are restored. Put every side effect and non-deterministic call (`uuid4`, `datetime.now`, notifies, writes) inside a `@task`. HITL uses the same `interrupt()` + `Command(resume=...)` rules as graphs (`agentic-streaming-hitl.md`).

Decorated entrypoints take **one** input (use a dict for several fields). Tasks return futures; call `.result()` (sync) or await them (async).

```python
from langgraph.func import entrypoint, task
from langgraph.checkpoint.memory import InMemorySaver

@task
def add_one(n: int) -> int:
    return n + 1

@entrypoint(checkpointer=InMemorySaver())
def workflow(nums: list[int]) -> list[int]:
    return [add_one(n).result() for n in nums]
```

Executed on langgraph 1.2.24: happy path `[1,2,3]→[2,3,4]`; HITL + `@task` cache on `PostgresSaver` / PostgreSQL 18.7 (same-process resume **and** process restart with a new saver); a write in the entrypoint body ran twice on resume (negative control). `retry=` on `@task` is deprecated; use `retry_policy=`.

## Deep Agents (optional, not pinned)

Official LangChain Deep Agents is a **harness on LangGraph**: planning, a virtual filesystem, and subagents for long-running tasks. Not a replacement for `create_agent` or for ADK. If a service pins it: keep the default in-state virtual filesystem (no host disk / execute backend without `tool-execution-safety.md` sandbox review); explicit tool allowlist per subagent (no inherited writes); `interrupt_on` for every write tool; principal-scoped store namespaces; one cumulative budget + explicit `recursion_limit` across subagents; review with `agentic-ai-reviewer` + `ai-security-reviewer`. Do not silently add `deepagents` to this toolkit lock.

## Subgraphs

Pass the parent's `config: RunnableConfig` into `subgraph.invoke(..., config)` so tracing and `context` propagate. A required `config` typed as `Any` is **not** injected (executed: `TypeError`). Identity stays in `config`/`context`, never in child input state.

Executed on langgraph 1.2.24: both `parent.add_node("child", compiled_subgraph)` and `child.invoke(..., config)` start a **fresh** step counter using the `recursion_limit` **value** from config. They do **not** consume remaining parent steps (discriminator: parent burned 4 steps, child needed 4, parent limit 6 → SUCCESS). A looping child still raises `GraphRecursionError` at that value. To give the child the *remaining* budget, wrap `child.invoke(..., {**config, "recursion_limit": remaining})` where `remaining` is an explicit settings cap or `recursion_limit - langgraph_step` from config metadata — do not hard-code `-2` (executed: parent 8 → rem 6). Uncaught child `RuntimeError` bubbles.

## Docs

Primary index: `https://docs.langchain.com/llms.txt`. Python overviews: `/oss/python/langchain/overview`, `/oss/python/langgraph/overview`. Prefer the `langchain-docs` MCP when connected; Context7 is a fallback. This toolkit's examples were checked against the installed 1.5.2 / 1.2.24 wheels, not against unpinned docs snippets.
