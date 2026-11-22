# Agentic AI Coding Standards — Examples & Anti-Patterns

Concrete good/bad code examples for each coding standard rule.

## Rule 1: State Typing

```python
# BAD — untyped state
def agent_node(state: dict) -> dict:
    messages = state.get("messages", [])
    return {"messages": messages + [response]}

# GOOD — TypedDict with proper annotations
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    iteration_count: int

def agent_node(state: AgentState) -> dict:
    return {"messages": [response], "iteration_count": state["iteration_count"] + 1}
```

## Rule 2: Message Lists

```python
# BAD — manual message management
class BadState(TypedDict):
    messages: list  # No type, no reducer

def node(state):
    return {"messages": state["messages"] + [response]}  # Manual append

# GOOD — add_messages annotation handles merging
class GoodState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def node(state):
    return {"messages": [response]}  # add_messages handles the merge
```

## Rule 3: Loop Protection

```python
# BAD — no iteration limit
def should_continue(state):
    if state["messages"][-1].tool_calls:
        return "tools"
    return END
# Can loop forever if LLM always requests tools

# GOOD — iteration check routes to a typed terminal node; recursion_limit is the hard cap
def should_continue(state: AgentState) -> Literal["tools", "limit_reached", "__end__"]:
    if state["iteration_count"] >= settings.max_agent_iterations:
        logger.warning("max_iterations_reached", count=state["iteration_count"])
        return "limit_reached"   # sets status="ITERATION_LIMIT"; never return the last (tool-call) message as success
    if isinstance(state["messages"][-1], AIMessage) and state["messages"][-1].tool_calls:
        return "tools"
    return END

# and at the call site: config["recursion_limit"] = settings.max_graph_steps; catch GraphRecursionError
# (LangGraph 1.0.x default is 10000, not 25)
```

## Rule 4: Tool Functions

```python
# BAD — no docstring, no error handling, wrong return type
@tool
def search(q):
    return requests.get(f"https://api.example.com/search?q={q}").json()

# GOOD — docstring, typed result with an explicit error field, no exception text, no query in logs
@tool
def search_docs(query: str, runtime: ToolRuntime[RequestCtx]) -> ToolResult:
    """Search the knowledge base for passages about a topic.

    Args:
        query: Specific search query. Be precise for better results.
    """
    try:
        hits = kb.search(query, org_id=runtime.context.org_id)   # scope injected, not model-supplied
    except KnowledgeBaseUnavailable as exc:
        log_exception(logger, "tool_search_failed", exc, tool="search_docs")
        return {"ok": False, "error_code": "TOOL_UNAVAILABLE", "data": None}
    logger.info("tool_search", result_count=len(hits))
    return {"ok": True, "error_code": None, "data": {"passages": [project(h, PASSAGE_FIELDS) for h in hits]}}
```

The route, not the prompt, inspects `ok`/`error_code`: if every grounding tool failed or returned nothing, the answer is `INSUFFICIENT_EVIDENCE` regardless of model text (`agentic-ai-dev/reference/tool-execution-safety.md`).

## Rule 5: LLM Instantiation

```python
# BAD — inline instantiation in node, model id literal in code
async def agent_node(state):
    llm = ChatAnthropic(model="<model-id-literal>", api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}

# GOOD — factory function, injected
def build_react_agent(provider_factory: LLMProviderFactory, checkpointer=None):
    llm = provider_factory.get_default().bind_tools(tools)

    async def agent_node(state: AgentState) -> dict:
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response], "iteration_count": state["iteration_count"] + 1}
    ...
```

## Rule 6: Sampling and reasoning controls

```python
# BAD — one rule for every model: "temperature 0 for facts"
llm = init_chat_model(settings.chat_model, temperature=0)
# Some current models recommend keeping the default (e.g. Gemini 3.x guidance: lower values can
# cause looping or degraded output); some reasoning models reject sampling parameters entirely.

# GOOD — sampling per the provider's guidance for that model generation, set in config;
# determinism comes from schemas, validators and invariant-based evals
llm = init_chat_model(settings.chat_model, **settings.chat_model_params)
```

See `agentic-ai-dev/reference/llm-inference-and-model-routing.md` §Sampling and reasoning controls.

## Rule 7: Checkpointing

```python
# BAD — MemorySaver in production
graph = build_react_agent(factory, checkpointer=MemorySaver())
# State is lost on restart!

# BAD — from_conn_string() is an async context manager; this fails at startup
checkpointer = AsyncPostgresSaver.from_conn_string(settings.checkpoint_db_uri)
await checkpointer.setup()   # AttributeError: no `setup` on the context manager

# GOOD — enter it in the FastAPI lifespan (agentic-templates-core.md)
async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_db_uri) as checkpointer:
    await checkpointer.setup()
    app.state.graph = build_react_agent(factory, checkpointer=checkpointer)
    yield
```

## Rule 8: Error Handling

```python
# BAD — swallowed exception
async def agent_node(state):
    try:
        response = await llm.ainvoke(state["messages"])
    except Exception:
        pass  # Silently swallowed!
    return {"messages": []}

# BAD — exception with empty fallback
async def agent_node(state):
    try:
        response = await llm.ainvoke(state["messages"])
    except Exception:
        return {"messages": []}  # Silent empty return

# BAD — exception text into the conversation (shown to the user, fed back to the model)
except Exception as e:
    return {"messages": [AIMessage(content=f"I encountered an error: {e}")]}

# GOOD — let provider errors propagate to the retry/fallback layer and the route boundary,
# which logs the type and returns a typed status (agentic-error-handling.md)
async def agent_node(state: AgentState) -> dict:
    response = await llm.ainvoke(state["messages"])   # retry/fallback configured on the model or middleware
    return {"messages": [response], "iteration_count": state["iteration_count"] + 1}
```

## Rule 9: Naming

```python
# BAD — inconsistent naming
def my_agent(state): ...           # Not build_*_agent()
def process(state): ...            # Not verb_node()
class State(TypedDict): ...        # Not *State

# GOOD — consistent naming
def build_react_agent(factory, checkpointer=None): ...
def retrieve_node(state: RAGState) -> dict: ...
class RAGState(TypedDict): ...
```

## Rule 10: Configuration

```python
# BAD — os.getenv with silent defaults
model = os.getenv("MODEL", "<model-id-literal>")  # Silent default: wrong model in some environment
api_key = os.getenv("API_KEY", "")  # Empty string → cryptic errors later

# GOOD — pydantic-settings with fail-fast validation
class Settings(BaseSettings):
    chat_model: str          # Required, no default in code; tests compare to settings, never a literal
    anthropic_api_key: SecretStr  # Required — app crashes if missing

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_key(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().startswith("sk-ant-"):
            raise ValueError("Invalid Anthropic API key format")
        return v

settings = Settings()  # Fails immediately if env vars are wrong
```

## Rule 14: Secrets

```python
# BAD — API key in logs
logger.info(f"Using API key: {settings.anthropic_api_key}")
logger.info("Config", extra={"api_key": settings.anthropic_api_key})

# BAD — PII in LangSmith trace metadata
config = {"metadata": {"user_email": "john@example.com"}}

# BAD — even a key prefix narrows the search space and identifies the key
logger.info("llm_configured", key_prefix=settings.anthropic_api_key[:10] + "...")

# GOOD — log that a key is configured, never any part of it; no PII in traces
logger.info("llm_configured", provider="anthropic", key_configured=True)
config = {"metadata": {"user_id": "usr_abc123"}}  # Use opaque IDs
```

## Anti-Patterns Table

| # | Anti-Pattern | Problem | Fix |
|---|-------------|---------|-----|
| 1 | `dict[str, Any]` for state | No type safety, IDE can't help | Use `TypedDict` |
| 2 | No `add_messages` | Messages overwrite instead of merge | Use `Annotated[list, add_messages]` |
| 3 | No step cap | Runaway loops (LangGraph default `recursion_limit` is 10000) | Explicit `recursion_limit` + catch `GraphRecursionError` + typed status |
| 4 | `@tool` without docstring | LLM can't decide when to use tool | Always add descriptive docstring |
| 5 | Inline `ChatAnthropic()` | Scattered config, no fallback | Use `LLMProviderFactory` |
| 6 | One temperature rule for all models | Looping/degraded output or rejected params on some models | Follow provider guidance per model; determinism from schemas + validators |
| 7 | `MemorySaver`/`InMemorySaver` in production, or `from_conn_string()` assigned instead of entered | State lost / startup crash | `async with AsyncPostgresSaver.from_conn_string(...)` in lifespan |
| 8 | `except: pass` | Silent failures | Log + return error state |
| 9 | `os.getenv()` for required vars | Late, cryptic failures | pydantic-settings + validators |
| 10 | API keys (or key prefixes) in logs | Security breach | Log `key_configured=True` only |
| 11 | Sync `def` in FastAPI | Blocks event loop | `async def` for all I/O |
| 12 | No `thread_id` in config | No conversation persistence | Always pass `thread_id` |
