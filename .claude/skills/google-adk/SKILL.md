---
name: google-adk
description: "Google ADK (Agent Development Kit) Python skill. Use when building AI agents with google-adk 2.x, Gemini models, Workflow graphs (and the deprecated SequentialAgent, ParallelAgent, LoopAgent), FunctionTool, McpToolset, session management, memory services, artifact storage, callbacks, or FastAPI integration for ADK agents."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: google-adk, ADK, ADK 2, ADK Workflow, FunctionNode, gemini agent, SequentialAgent, ParallelAgent, LoopAgent, FunctionTool, McpToolset, google genai, adk agent, vertex ai agent
  related-skills: python-dev, agentic-ai-dev, mcp-builder
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

# Google ADK Development Skill — Python + Gemini + FastAPI

## Iron Law

**NEVER call the real Gemini API in unit tests.** `InMemoryRunner` only swaps in in-memory services — it still calls the configured model (verified on 2.15.0: a real model id with no key raises `ValueError`). Tests register a scripted `BaseLlm` (`reference/adk-testing.md` §2). Production agents use `Runner` with persistent session services, created once per process.

**Every run is bounded and every id is owned.** `RunConfig(max_llm_calls=N)` (default 500) + `asyncio.timeout(...)` on each `run_async`; `user_id` is the authenticated principal; scope such as `org_id` lives in session state and is injected into tool args by code, never chosen by the model (`reference/adk-tools-callbacks.md` §5). The model proposes; deterministic code authorizes (`.claude/rules/ai-engineering.md`).

**NEVER connect to external services from a FunctionTool.** All external I/O (HTTP, DB, vector DB, cloud APIs) belongs in MCPTools accessed via `McpToolset`. FunctionTools contain ONLY pure logic or session state access.

**ALWAYS use `McpToolset` for MCP connections** — never instantiate `McpToolset(connection_params=...)` directly in agent code; use the factory provided by your project. Rules:
- **`tool_filter` is MANDATORY and non-empty** in every `McpToolset` call — ADK itself treats `None` and `[]` as "expose all tools", so the project factory must raise `ValueError` on an empty filter (`reference/adk-tools-basic.md` §7)
- **NEVER bypass McpToolset** with direct `httpx`/`requests` calls — all external I/O routes through the MCP server via McpToolset

## Before building

Decide whether this needs an agent at all — `ai-playbook` skill (deterministic code for fixed rules, a single LLM call for one-shot transforms, an agent only for open-ended tool use). Agents do not own multi-step transactions: side effects go through a domain service or durable workflow (`workflow-orchestration-patterns`). Framework-neutral canonical homes: inference and retries `agentic-ai-dev/reference/llm-inference-and-model-routing.md`, tool safety `agentic-ai-dev/reference/tool-execution-safety.md`, memory `agentic-ai-dev/reference/agentic-memory-systems.md`.

## Quick Scaffold (Three Options)

### Option A: agent-starter-pack (Recommended for production)

```bash
uvx agent-starter-pack create my-agent --agent adk --prototype --agent-guidance-filename CLAUDE.md -y
# Templates: adk (default), adk_a2a (A2A protocol), agentic_rag (RAG)
```

Generates project with Terraform, Dockerfile, CI/CD, eval harness. Use `enhance` to add deployment later.

### Option B: Manual setup (Simpler, no deployment scaffold)

```bash
uv init my-adk-service && cd my-adk-service
uv add "google-adk[db,mcp,otel]==2.15.0" "google-genai==2.34.0" "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "uvicorn[standard]==0.54.0" "pydantic-settings==2.16.3" "structlog==26.1.0" "sqlalchemy[asyncio]==2.1.9" "asyncpg==0.32.0"
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "httpx2==2.16.2" "aiosqlite==0.22.1" "ruff==0.17.6" "mypy==2.4.1"
# google-adk 2.15 requires google-genai>=2.34,<3 and websockets>=15.0.1,<16 (PyPI requires_dist):
# never "upgrade" genai to 3.x under ADK; genai 3.x code lives in its own lock (gemini-api-dev skill)
# then pin every dependency exactly (==) and commit uv.lock — reference/adk-project-config.md §1
```

### Option C: Enhance existing project (add deployment to scaffolded project)

```bash
uvx agent-starter-pack enhance .
```

Choose deployment target when prompted: `cloud_run` or `agent_engine`.

## Process

0. **Write DESIGN_SPEC.md** — Before any code, write a spec covering: purpose, example use cases, required tools, safety constraints, success criteria, edge cases. Save as `DESIGN_SPEC.md` in the project root. This is your contract — all implementation must align with it.
1. **Scaffold** — `uv init` + `google-adk[db,mcp,otel]==2.15.0` and `google-genai==2.34.0` (exact pins, committed `uv.lock`, `uv sync --locked`). `McpToolset` needs the `mcp` extra (`ModuleNotFoundError: mcp` without it); `bigquery-analytics` carries pyarrow since 2.7
2. **Configure** — `Settings(BaseSettings)` with a required `agent_model` and the per-environment auth matrix: developer key locally only, keyless ADC on Vertex when deployed (`reference/adk-project-config.md` §2-3)
3. **Define Agent** — `Agent(name, model=settings.agent_model, instruction, tools)`; no model id literal in code; docstrings on every tool; on Gemini 3.x leave sampling params at defaults and size `max_output_tokens` for thinking tokens (`gemini-api-dev` skill)
4. **Compose Agents** — new multi-step flows use a `Workflow` graph run with `Runner(node=...)` (`reference/adk-agent-types.md` §0). `SequentialAgent`/`ParallelAgent`/`LoopAgent` still run on 2.15 but emit `DeprecationWarning` ("deprecated in favor of Workflow"); keep them only where a workflow must sit under an `LlmAgent` (Workflow cannot yet be an LlmAgent sub-agent). Set `output_key` on each sub-agent that passes state downstream
5. **Define Tools** — plain Python functions with type hints and docstrings; use `pydantic.BaseModel` for complex inputs; accept `tool_context: ToolContext` to read/write session state
6. **Add Callbacks** — on `LlmAgent`s only (orchestrators reject them); use the canonical parameter names (`callback_context`, `llm_request`, `tool`, `args`, `tool_context`, ...). On 2.x misnamed parameters are adapted **positionally** instead of raising `TypeError` as 1.29 did, so a swapped order passes silently: type-annotate and test them (`reference/adk-tools-callbacks.md` §0). Rate limiting belongs in the API layer, not a callback
7. **Session Management** — `InMemorySessionService()` for tests; `DatabaseSessionService(db_url="postgresql+asyncpg://...")` for self-hosted Postgres/Cloud SQL; `VertexAiSessionService(project=..., location=..., agent_engine_id=...)` for Agent Engine (`project_id=` is a `TypeError`). `await` every session call (`create_session` is a coroutine); mint session ids server-side
8. **Add Memory** — pass `memory_service` to `Runner`; prefer `load_memory` (tool result). `preload_memory` injects recalled text into the **system instruction** — a stored injection gains system authority (`reference/adk-memory-artifacts.md` §2, §4)
9. **Expose API** — POST routes using `runner.run_async()` under a timeout and call cap; typed failure statuses; SSE per the `streaming-protocols` skill §6a; one `Runner` per process (`reference/adk-fastapi-integration.md`)
10. **Write Tests** — scripted fake model + `InMemoryRunner`; `pytest-asyncio`; tool isolation, routing, loop caps, foreign-session 404 (`reference/adk-testing.md`)
11. **Deploy** — `adk-deploy-guide` skill: keyless ADC on Vertex (no API key in the image or env), eval gate before traffic, model id from config

## Key Patterns

| Pattern | Implementation | Reference |
|---------|---------------|-----------|
| Single Agent | `Agent(name, model, instruction, tools)` | `adk-core-patterns.md` |
| Workflow graph (2.x) | `Workflow(name=..., edges=[("START", agent, fn, agent)])` + `Runner(node=...)`; `FunctionNode(retry_config=..., timeout=...)` | `adk-agent-types.md` §0 |
| Sequential / Parallel / Loop (deprecated) | `SequentialAgent` / `ParallelAgent` / `LoopAgent(max_iterations=N)` + `output_key` | `adk-agent-types.md` |
| Agent Handoff | `transfer_to_agent` built-in + `sub_agents=[...]` on root | `adk-agent-handoff.md` |
| Custom Tools | Plain function with docstring + `ToolContext` for state | `adk-tools-basic.md` |
| MCP Integration | `McpToolset(connection_params=StdioConnectionParams(...))` | `adk-tools-basic.md` |
| Structured Output | `output_schema=PydanticModel` + `output_key="key"` (stores a validated dict) | `adk-structured-output.md` |
| Callbacks | `before_model_callback`, `after_model_callback`, `before_tool_callback` | `adk-tools-callbacks.md` |
| Session State | `tool_context.state["key"]` read/write | `adk-structured-output.md` |
| Memory | `InMemoryMemoryService` + `load_memory` tool | `adk-memory-artifacts.md` |
| Testing | Scripted fake `BaseLlm` + `InMemoryRunner` + pytest-asyncio | `adk-testing.md` |
| FastAPI SSE | `runner.run_async()` + `StreamingResponse` | `adk-fastapi-integration.md` |
| Evaluation | `adk eval` + evalset schema + LLM-as-judge | `adk-eval-guide` skill |
| Deployment | Agent Engine, Cloud Run, CI/CD | `adk-deploy-guide` skill |
| Observability | Cloud Trace, prompt logging, agent analytics | `adk-observability-guide` skill; `deployment-ci-cd/reference/ai-observability.md` |

## R1/R2 Tool Placement Rule

Before writing any tool, apply this binary test:

> "Does this tool perform I/O outside the agent process (DB, HTTP, vector DB, cloud APIs)?"

| Answer | Tool type | Location |
|--------|-----------|----------|
| **YES** | **R1 — MCPTool** | MCP server — agent accesses via `McpToolset` |
| **NO** | **R2 — FunctionTool** | Agent tools directory — pure logic only |

**ToolContext exception:** If a tool needs BOTH external data AND `ToolContext` session state, it MUST be a FunctionTool — only in-process tools can access `ToolContext`. The FunctionTool reads data from session state previously populated by an MCPTool.

**NEVER put `import httpx`, `import sqlalchemy`, or `import requests` in FunctionTool files.**

## Eval-First Development

Write golden test cases BEFORE writing agent code. This prevents writing code that passes no evaluation criteria.

**Order of operations:**
1. Define `tests/golden/agents/<agent_name>/` directory
2. Write at minimum: one happy-path case, one error-path case, one edge-case
3. Each case: input → expected tool trajectory and output assertions (`contains_keywords`, `pattern_*`); never gate on a model-reported confidence
4. Run eval skeleton to confirm test infrastructure works
5. THEN implement the agent
6. Iterate until all golden cases pass

### Eval Skeleton (generate this first, before implementing the agent)

```bash
AGENT=my_agent  # replace with your agent name
mkdir -p tests/golden/agents/$AGENT tests/evals

# Placeholder evalset
cat > tests/evals/$AGENT.evalset.json << 'JSON'
[
  {
    "name": "happy_path_1",
    "input": { "query": "your test input here" },
    "expected_tool_use": [{ "tool_name": "your_tool_name" }],
    "expected_final_response": { "contains": "expected keyword" }
  }
]
JSON

# Eval config with accuracy threshold
cat > tests/evals/eval_config.json << 'JSON'
{
  "criteria": [
    { "type": "tool_trajectory_avg_score", "config": { "match_type": "IN_ORDER" } },
    { "type": "final_response_match_v2", "config": { "threshold": 0.8 } }
  ]
}
JSON
```

## Code Preservation Rules

- **NEVER change the configured model** unless explicitly asked — a model bump is a release: probe the new id on the target endpoint, run evals, roll out gradually (`deployment-ci-cd/reference/llmops-release-and-rollout.md`)
- **NEVER rewrite working agent code** — if the agent works, refactor incrementally
- **NEVER remove tools** from an agent without explicit approval — tools are part of the agent's contract
- **NEVER rename output_key values** — downstream agents reference them by name

## Documentation Sources

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Google ADK Python | `https://context7.com/google/adk-python/llms.txt` | Official ADK API reference |
| Google GenAI types | Context7 MCP — resolve `google-genai` | `types.Part`, `types.Content`, `GenerateContentConfig` |
| Pydantic v2 | Context7 MCP — resolve `pydantic` | `BaseModel`, `Field`, validators |
| ADK Docs MCP | `adk-docs` MCP server (installed) | Live ADK documentation |

## Reference Files

| File | Contents |
|------|----------|
| `reference/adk-core-patterns.md` | Agent config, Runner patterns (async, bounded), App class, session management |
| `reference/adk-structured-output.md` | Session state access, structured output schemas, UserContent construction |
| `reference/adk-agent-types.md` | SequentialAgent, ParallelAgent, LoopAgent, composition patterns |
| `reference/adk-agent-handoff.md` | Agent handoff via transfer_to_agent, output_key state passing rules |
| `reference/adk-tools-basic.md` | FunctionTool, ToolContext, async tools, Pydantic inputs, confirmation round trip, McpToolset with `tool_filter` |
| `reference/adk-tools-callbacks.md` | Callbacks: before/after model, on_model_error, before/after tool, on_tool_error |
| `reference/adk-memory-artifacts.md` | Memory services, load_memory tool, artifact storage, semantic search |
| `reference/adk-fastapi-integration.md` | FastAPI + StreamingResponse SSE, lifespan runner setup, request/response models |
| `reference/adk-testing.md` | InMemoryRunner unit tests, pytest-asyncio patterns, tool isolation, agent routing |
| `reference/adk-project-config.md` | pyproject.toml, .env setup, directory structure, Dockerfile, logging, commands |
| `reference/adk-gemini-prompt-templates.md` | `LlmAgent` instruction templates and ADK `{state}` templating rules — base structure, RAG with citations, generator + reviewer, multi-step analysis |

## Common Commands

```bash
# Run dev server via ADK web UI
adk web

# Run FastAPI app with uvicorn
uvicorn src.main:app --reload --port 8000

# Run tests
uv run pytest tests/ -v

# Type check
uv run mypy src/

# Lint + format
uv run ruff check src/ && uv run ruff format src/

# Install all deps from lockfile (fails on a stale lock)
uv sync --locked
```

## Error Handling

ADK-specific error handling rules:

- **Provider errors** — wrap `runner.run_async()` in `asyncio.timeout`; catch `google.genai.errors.APIError` (classify by `.code`), `LlmCallsLimitExceededError` and `TimeoutError`; map each to a typed status; log with `log_exception(logger, event, exc, **ids)` (type + ids, never `str(e)` — `deployment-ci-cd/reference/python-observability.md` §2). Retries are configured once, in `HttpRetryOptions` (`gemini-api-dev` skill), not stacked in app code
- **Tool errors** — return a typed result `{"ok": False, "error_code": "...", "data": None}`; `on_tool_error_callback` converts unexpected exceptions to the same shape; never raw exception text
- **Loop limits** — `LoopAgent.max_iterations` defaults to `None` (unbounded): always set it plus `RunConfig(max_llm_calls)`; report an iteration-limit exit as a typed status, not a success
- **Callback abort** — returning a non-None value from `before_model_callback` skips the model call; document this explicitly in the callback with a comment
- **Session not found** — `InMemoryRunner`/`Runner` do not auto-create sessions (`SessionNotFoundError`); `await get_session(user_id=principal, ...)` and answer 404 on `None` (it is also what another user's id returns); create new sessions server-side

All error paths must:
1. Log with structured logger (structlog) including `user_id`, `session_id`, `agent_name`
2. Either rethrow or return an error state — no silent empty returns
3. Surface the failure to the user (API error response, SSE error event)

## Post-Code Review

After implementing any ADK agent feature:

1. Dispatch `adk-reviewer` agent (read-only) — pass the agent graph structure and tool implementations; `ai-security-reviewer` for tools with side effects or untrusted content
2. Dispatch `security-reviewer` — flag any tool that calls external APIs or handles user PII
3. Confirm: no hardcoded API keys, all inputs validated, all error paths logged
