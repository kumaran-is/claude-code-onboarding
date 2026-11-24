# Agentic AI Conventions & Rules

## Package Layout

```
src/<service_name>/
├── agents/
│   ├── graphs/          # StateGraph definitions (build_*_agent functions)
│   ├── nodes/           # Node functions (verb_node pattern)
│   ├── tools/           # @tool definitions
│   └── state.py         # TypedDict state schemas
├── rag/
│   ├── chains/          # RAG chain compositions
│   ├── indexing/        # Document loaders, splitters, indexing
│   └── retrieval/       # Retrievers, rerankers
├── memory/
│   └── long_term.py     # Principal-scoped Store memory (checkpointer lives in main.py lifespan)
├── guardrails/
│   ├── input.py         # Input validation pipeline
│   └── output.py        # Output validation pipeline
├── llm/
│   └── client.py        # Model construction from settings, error mapping, retry/failover
├── core/
│   ├── config.py        # pydantic-settings configuration
│   ├── logging.py       # structlog setup
│   └── exceptions.py    # Exception hierarchy
├── observability/
│   ├── metrics.py       # Prometheus metrics
│   └── tracing.py       # LangSmith / OTel tracing setup
├── models/
│   └── schemas.py       # Pydantic request/response models
├── api/
│   ├── routes/
│   │   ├── agent.py     # POST /invoke, POST /stream
│   │   └── health.py    # GET /health
│   └── middleware/
│       └── request_id.py       # Phase 2 RequestIdMiddleware (python-observability.md §4)
├── main.py              # FastAPI app with lifespan
└── py.typed             # PEP 561 marker
```

## LangGraph Rules

1. **State is a `TypedDict`** (or `create_agent`'s `AgentState` extended via `state_schema=`) — never `dict[str, Any]`
2. **Messages use `Annotated[list[BaseMessage], add_messages]`**
3. **Step caps are explicit server config**: pass `recursion_limit` on every run (LangGraph 1.2.x defaults to **10007**, 1.0.x to 10000, overridable via `LANGGRAPH_DEFAULT_RECURSION_LIMIT` — never rely on it), catch `GraphRecursionError`, and map it to a typed `ITERATION_LIMIT` status. With `create_agent`, also use `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` with `exit_behavior="error"`. Hand-built graphs may add `iteration_count` for an earlier typed stop.
4. **`Command(goto=...)` only with code-validated targets** — validate model-proposed routes against a closed enum first
5. **Durable checkpointer in production** — `AsyncPostgresSaver` entered with `async with` in the lifespan; `InMemorySaver` is for tests
6. **Thread ids are principal-scoped** — `{"configurable": {"thread_id": scoped_thread_id(principal, client_id)}}`; never a raw client value
7. **Authority facts live in structured state/context** — scope ids, approvals, safety flags and the user's permissions are injected each turn from authoritative storage (`context=` / state), never left for the model to "remember" across turns, and never dropped by summarization
8. **Every run has a deadline** — `asyncio.timeout(settings.agent_timeout_s)`

## FastAPI Integration Rules

1. **All endpoints are `async def`** — never block the event loop
2. **Graph built once in the lifespan, injected via `Depends()`**
3. **Streaming = SSE with JSON `data:` frames** and one terminal event (`agentic-streaming-hitl.md`)
4. **Liveness/readiness split** per `deployment-ci-cd/reference/python-observability.md` §6 — no LLM call on every probe
5. **Identity from the verified token** — `user_id`/`org_id` never in the body or query; the client may send only its own conversation id, which the server scopes

## Agent Contract (write before code)

Framework-neutral; Google ADK services use the same contract. The design decision itself (agent vs deterministic workflow, autonomy level) is recorded with `ai-decision-record`; principles are in `ai-playbook/playbook.md`.

| Part | Contents |
|---|---|
| Identity | Name, owner, purpose, explicit non-goals, risk/authority class (adding a write tool re-classifies the agent) |
| Input | Typed schema; scope comes from auth, not the payload; max payload size; PII classes allowed |
| Output | `status`, `reason_codes`, `evidence` (ids of grounding records), `next_action`, `prompt_version`, `model_id`, `trace_id` |
| Errors | Closed taxonomy (`agentic-error-handling.md` §Error taxonomy) |
| Tools | Allowlist with authority tier per tool (`tool-execution-safety.md`) |
| Budgets | Steps, model calls, tool calls, tokens, wall-clock — cumulative across sub-agents and retries |
| Fallback | Deterministic degraded behaviour per failure class; no dead ends |

## LangGraph Agent Implementation Checklist

```
□ Model ids come from settings only (no default in code, no literal in tests); probed per environment before a bump
□ Sampling/reasoning params follow the provider's guidance for that model (llm-inference-and-model-routing.md)
□ Embeddings (if RAG): model id in config and in every embedding cache key; dimension matches the schema
□ Tools: docstring, typed args, typed ToolResult, scope via ToolRuntime context, allowlist resolves (tool-execution-safety.md)
□ Side-effecting tools: idempotency key bound to payload hash; high-risk ones behind HITL approval
□ Memory: durable checkpointer in lifespan; long-term memory on a principal-scoped Store (agentic-memory-systems.md)
□ Caps: recursion_limit + call-limit middleware from settings; GraphRecursionError/limit errors -> ITERATION_LIMIT
□ Deadline: asyncio.timeout around every run; sized from measured p99 x 1.5
□ Retry: one layer, transient only, on_failure="error"; failover same-tier, availability errors only
□ Errors: no exception text to clients/streams/model; log_exception with non-PII ids
□ Streaming (if user-facing): JSON SSE frames, user-facing nodes only, one terminal event
□ Tracing: LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT (or OTel, deployment-ci-cd/reference/ai-observability.md); no PII in metadata
□ Caching (if any): answer-cache keys scoped by org + ACL + model + prompt version (agentic-caching-patterns.md)
□ Tests: scripted fake model for routing/tool sequence/caps/errors (agentic-testing.md); live golden + failure cases before release
□ Pins: langchain, langgraph, langgraph-prebuilt, langgraph-checkpoint-postgres pinned with == and a committed uv.lock
```

## Prompt Selection Quick Reference

Model ids are configuration; this table maps a **provider family** to a prompt structure, not to a specific model.

| Provider family | Prompt structure | Reference |
|----------|-----------------|-----------|
| Anthropic (LangChain) | XML tags: `<context>`, `<task>` | `agentic-prompt-engineering.md` |
| Google (ADK) | Markdown sections + numbered steps | `adk-gemini-prompt-templates.md` |
| OpenAI (LangChain) | Markdown/delimited sections + JSON schema output | `agentic-prompt-optimization.md` |

For reasoning-capable models prefer the provider's reasoning/thinking controls over "think step by step" prompting.
