---
name: google-adk
description: "Google ADK (Agent Development Kit) Python skill. Use when building or choosing architecture for Gemini AI agents with google-adk 2.x: LlmAgent, ADK Workflows, JoinNode, Event routes, nested/dynamic ADK Workflows, coordinator teams (mode=chat/task/single_turn), RequestInput HITL, RAG tools, FunctionTool, McpToolset, sessions, memory, FastAPI. SequentialAgent, ParallelAgent, and LoopAgent still run but are deprecated."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: google-adk, ADK, ADK 2, ADK Workflow, JoinNode, FunctionNode, RequestInput, LlmAgent, gemini agent, SequentialAgent, ParallelAgent, LoopAgent, FunctionTool, McpToolset, google genai, adk agent, vertex ai agent
  related-skills: python-dev, agentic-ai-dev, mcp-builder, rag-architect, adk-eval-guide, adk-observability-guide, adk-deploy-guide, multi-agent-patterns
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-26"
---

# Google ADK Development Skill — Python + Gemini + FastAPI

## Iron Law

**NEVER call the real Gemini API in unit tests.** `InMemoryRunner` only swaps in in-memory services — it still calls the configured model (verified on 2.15.0: a real model id with no key raises `ValueError`). Tests register a scripted `BaseLlm` when an `LlmAgent` is in the graph. Production agents use `Runner` with persistent session services, created once per process. Pin `google-adk[db,mcp,otel]==2.15.1`. Executed 2.15.1 local coverage (not Gemini Live): `adk-testing.md` header.

**Every run is bounded and every id is owned.** `RunConfig(max_llm_calls=N)` (default 500) + `asyncio.timeout(...)` on each `run_async`; `user_id` is the authenticated principal; scope such as `org_id` lives in session state and is injected into tool args by code, never chosen by the model (`reference/adk-tools-callbacks.md` §5). The model proposes; deterministic code authorizes (`.claude/rules/ai-engineering.md`).

**Model-chosen tools: no external I/O in a FunctionTool.** HTTP, DB, vector DB, and cloud APIs belong in MCPTools via `McpToolset`. FunctionTools contain ONLY pure logic or session state access. **Deterministic graph steps are different:** a `FunctionNode` or FastAPI route calls the owning service/repository directly, with `RetryConfig` and a `timeout` — do not wrap a fixed path in MCP (`adk-reviewer`).

**ALWAYS build `McpToolset` through the project factory** (`reference/adk-tools-basic.md` §7), never inline `McpToolset(connection_params=...)` in agent modules. Rules:
- **`tool_filter` is MANDATORY and non-empty** — ADK treats `None` and `[]` as "expose all tools"; the factory must raise `ValueError` on an empty filter
- **NEVER bypass McpToolset from a FunctionTool** with direct `httpx`/`requests` — model-chosen external I/O routes through MCP

## Before building

Decide whether this needs an agent at all — `ai-playbook` skill (deterministic code for fixed rules, a single LLM call for one-shot transforms, an agent only for open-ended tool use). Agents do not own multi-step transactions: side effects go through a domain service or durable workflow (`workflow-orchestration-patterns`). Framework-neutral canonical homes: inference and retries `agentic-ai-dev/reference/llm-inference-and-model-routing.md`, tool safety `agentic-ai-dev/reference/tool-execution-safety.md`, memory `agentic-ai-dev/reference/agentic-memory-systems.md`.

## Choose the architecture (do not default to a graph)

ADK offers **three complementary** multi-step styles ([adk.dev/graphs](https://adk.dev/graphs/)): a **graph** `Workflow` (deterministic nodes/edges), a **dynamic** `@node` + `ctx.run_node` (loops/recursion a static graph cannot express), and **prebuilt** `SequentialAgent` / `ParallelAgent` / `LoopAgent` (still run on 2.15, `DeprecationWarning`, scheduled for removal; keep working code; new code uses a graph unless the flow **must** sit under an `LlmAgent`).

| Requirement | Preferred ADK approach | Reference |
|---|---|---|
| Simple tool-calling assistant | `LlmAgent` / `Agent` — no graph | `adk-core-patterns.md` |
| Predictable multi-step process | Graph `Workflow` with deterministic stages | `adk-agent-types.md` §0 |
| Concurrent independent tasks | Parallel graph branches + `JoinNode` | `adk-agent-types.md` §1 |
| Dynamic specialist selection | Closed labels → `Event(route=...)`. Specialist talks to the user → coordinator `mode=`. Parent keeps control → `AgentTool` | `adk-agent-types.md` §2; `adk-agent-teams-and-migration.md` |
| Complex branching and rework | Graph routes + bounded `ctx.run_node` loop | `adk-agent-types.md` §2, §4 |
| Approval before sensitive operations | `yield RequestInput(...)` or `FunctionTool(require_confirmation=True)` | `adk-agent-types.md` §0.1, `adk-tools-basic.md` §5 |
| Knowledge-intensive assistant | Ground every answer → retrieve in a graph step. Optional retrieve → model-chosen RAG tool + ACL + citations | `rag-architect`, `adk-gemini-prompt-templates.md` §2 |
| Existing Sequential/Parallel/Loop that still passes evals | Keep until you need routes, `JoinNode`, HITL, or live; then migrate | `adk-agent-teams-and-migration.md` |

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
uv add "google-adk[db,mcp,otel]==2.15.1" "google-genai==2.34.0" "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "uvicorn[standard]==0.54.0" "pydantic-settings==2.16.3" "structlog==26.1.0" "sqlalchemy[asyncio]==2.1.9" "asyncpg==0.32.0"
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
1. **Scaffold** — `uv init` + `google-adk[db,mcp,otel]==2.15.1` and `google-genai==2.34.0` (exact pins, committed `uv.lock`, `uv sync --locked`). `McpToolset` needs the `mcp` extra (`ModuleNotFoundError: mcp` without it); `bigquery-analytics` carries pyarrow since 2.7
2. **Configure** — `Settings(BaseSettings)` with a required `agent_model` and the per-environment auth matrix: developer key locally only, keyless ADC on Vertex when deployed (`reference/adk-project-config.md` §2-3)
3. **Define Agent** — `Agent(name, model=settings.agent_model, instruction, tools)`; no model id literal in code; docstrings on every tool; on Gemini 3.x leave sampling params at defaults and size `max_output_tokens` for thinking tokens (`gemini-api-dev` skill)
4. **Choose composition** — pick from **Choose the architecture** above. Graphs: `Runner(node=...)` (mutually exclusive with `agent=` / `app=`). Root `LlmAgent` `mode` must be `chat` (default) or `task`; `single_turn` as root raises `ValueError` (executed). Set `task`/`single_turn` on specialist **leaves** (`task` agents cannot have `sub_agents`). Typed node I/O is the next node's `node_input`; `output_key` is for instruction `{key}` templates. Details: `reference/adk-agent-types.md`.
5. **Define Tools** — plain Python functions with type hints and docstrings; use `pydantic.BaseModel` for complex inputs; accept `tool_context: ToolContext` to read/write session state. RAG retrieval is an MCP tool (or a FunctionTool that only reads MCP-populated session state) plus `rag-architect` citation/ACL gates — never interpolate retrieved text into `instruction`
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
| Sequential graph | `Workflow(edges=[("START", a, fn, b)])` + `Runner(node=...)` | `adk-agent-types.md` §0 |
| Parallel + join | `JoinNode` + multiple `("START", branch, join)` edges | `adk-agent-types.md` §1 |
| Route / nested Workflow | `Event(route=...)` + `{DEFAULT_ROUTE: ...}`; a `Workflow` is a node | `adk-agent-types.md` §2–§3 |
| Bounded loop | `@node(rerun_on_resume=True)` + `ctx.run_node` inside `for _ in range(N)` | `adk-agent-types.md` §4 |
| Graph HITL | `yield RequestInput(message=..., response_schema=...)` | `adk-agent-types.md` §0.1 |
| Coordinator team | `Agent(sub_agents=[...])`; root `chat`/`task`; `task`/`single_turn` on leaves | `adk-agent-teams-and-migration.md` |
| Sequential / Parallel / Loop | keep if evals pass; new code only as an `LlmAgent` sub-agent | `adk-agent-teams-and-migration.md` |
| Agent Handoff | `transfer_to_agent` injected + `sub_agents=[...]` on root | `adk-agent-handoff.md` |
| Custom Tools | Plain function with docstring + `ToolContext` for state | `adk-tools-basic.md` |
| MCP Integration | project factory → `McpToolset` + non-empty `tool_filter` | `adk-tools-basic.md` §7 |
| Structured Output | `output_schema=PydanticModel` + `output_key="key"` (stores a validated dict) | `adk-structured-output.md` |
| Callbacks | `before_model_callback`, `after_model_callback`, `before_tool_callback` | `adk-tools-callbacks.md` |
| Session State | `tool_context.state["key"]` read/write | `adk-structured-output.md` |
| Memory | `InMemoryMemoryService` + `load_memory` tool | `adk-memory-artifacts.md` |
| Testing | Scripted fake `BaseLlm` + `InMemoryRunner` + pytest-asyncio | `adk-testing.md` |
| FastAPI SSE | `runner.run_async()` + `StreamingResponse` | `adk-fastapi-integration.md` |
| RAG | MCP/tool retrieve + ACL in the query; cite only retrieved ids; retrieved text is data not instructions | `rag-architect`, `adk-gemini-prompt-templates.md` §2 |
| Evaluation | `adk eval` + evalset schema + LLM-as-judge | `adk-eval-guide` skill |
| Deployment | Agent Engine, Cloud Run, CI/CD | `adk-deploy-guide` skill |
| Observability | Cloud Trace, prompt logging, agent analytics | `adk-observability-guide` skill; `deployment-ci-cd/reference/ai-observability.md` |

## R1/R2 Tool Placement Rule

Before writing any tool, apply this binary test:

> "Does this tool perform I/O outside the agent process (DB, HTTP, vector DB, cloud APIs)?"

| Answer | Tool type | Location |
|--------|-----------|----------|
| **YES** (model-chosen tool) | **R1 — MCPTool** | MCP server via `McpToolset` |
| **YES** (deterministic graph/route step) | **FunctionNode / service call** | Owning repository; `RetryConfig` + `timeout`; not MCP |
| **NO** | **R2 — FunctionTool** | Agent tools directory — pure logic only |

**ToolContext exception:** If a **model-chosen** tool needs BOTH external data AND `ToolContext` session state, it MUST be a FunctionTool. It reads data from session state previously populated by an MCPTool.

**NEVER put `import httpx`, `import sqlalchemy`, or `import requests` in FunctionTool files.**

## Eval-First Development

Write golden test cases BEFORE writing agent code. This prevents writing code that passes no evaluation criteria.

**Order of operations:**
1. Create golden cases under `tests/golden/features/<feature>/` (kit layout; `eval-guide`)
2. Write at minimum: one happy-path case, one error-path case, one edge-case
3. Each case: input → expected tool trajectory and output assertions; never gate on a model-reported confidence
4. Confirm eval infrastructure with the offline smoke fixture in `adk-eval-guide` (schema, `judge_model`, `adk eval` exit codes)
5. THEN implement the agent
6. Iterate until all golden cases pass

Evalset schema, criteria dict (`extra="forbid"`), and the scripted-model smoke test: `adk-eval-guide`. Do not invent a second eval JSON shape.

## Code Preservation Rules

- **NEVER change the configured model** unless explicitly asked — a model bump is a release: probe the new id on the target endpoint, run evals, roll out gradually (`deployment-ci-cd/reference/llmops-release-and-rollout.md`)
- **NEVER rewrite working agent code** — if the agent works, refactor incrementally
- **NEVER remove tools** from an agent without explicit approval — tools are part of the agent's contract
- **NEVER rename output_key values** — downstream agents reference them by name

## Documentation Sources

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| ADK 2.0 | `https://adk.dev/2.0/` | Workflow runtime, deprecations, Event schema |
| ADK workflows / patterns | `https://adk.dev/workflows/` `https://adk.dev/workflows/patterns/` | Multi-agent patterns; Sequential/Parallel/Loop still run, deprecated in Python |
| ADK graphs | `https://adk.dev/graphs/` | Three styles: graph, dynamic, prebuilt; sequential edges |
| ADK graph routes | `https://adk.dev/graphs/routes/` | JoinNode, Event(route), nested Workflows |
| ADK dynamic graphs | `https://adk.dev/graphs/dynamic/` | ctx.run_node loops |
| ADK collaboration | `https://adk.dev/workflows/collaboration/` | mode=chat/task/single_turn |
| ADK graphs HITL | `https://adk.dev/graphs/human-input/` | RequestInput |
| Google ADK Python | `https://github.com/google/adk-python` (pin `2.15.1`) | Releases, changelog |
| Google GenAI types | Context7 MCP — resolve `google-genai` | `types.Part`, `types.Content`, `GenerateContentConfig` |
| Pydantic v2 | Context7 MCP — resolve `pydantic` | `BaseModel`, `Field`, validators |
| ADK Docs MCP | `adk-docs` MCP server (installed) | Live ADK documentation |

## Reference Files

| File | Contents |
|------|----------|
| `reference/adk-core-patterns.md` | Agent config, Runner patterns (async, bounded), App class, session management |
| `reference/adk-structured-output.md` | Session state access, structured output schemas, UserContent construction |
| `reference/adk-agent-types.md` | Workflow graphs, JoinNode, routes, nested Workflows, dynamic loops, HITL |
| `reference/adk-agent-teams-and-migration.md` | Coordinator `mode=`, AgentTool vs route, Sequential/Parallel/Loop keep-vs-migrate |
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

**ADK built-in vs application-level** (do not invent framework features): ADK provides `RunConfig(max_llm_calls)`, `FunctionNode(retry_config=..., timeout=...)`, `RequestInput`, `require_confirmation`, session/memory/artifact services, and the `otel` extra. **Not** built-in: API rate limits, tenant ACL on retrieval, idempotency keys, circuit breakers, dollar/token product budgets, durable business transactions — those stay in the FastAPI layer, MCP servers, and `workflow-orchestration-patterns`.

ADK-specific error handling rules:

- **Provider errors** — wrap `runner.run_async()` in `asyncio.timeout`; catch `google.genai.errors.APIError` (classify by `.code`), `LlmCallsLimitExceededError` and `TimeoutError`; map each to a typed status; log with `log_exception(logger, event, exc, **ids)` (type + ids, never `str(e)` — `deployment-ci-cd/reference/python-observability.md` §2). Retries are configured once, in `HttpRetryOptions` (`gemini-api-dev` skill), not stacked in app code
- **Tool errors** — return a typed result `{"ok": False, "error_code": "...", "data": None}`; `on_tool_error_callback` converts unexpected exceptions to the same shape; never raw exception text
- **Loop limits** — dynamic `@node` loops use `for _ in range(N)` and a typed `ITERATION_LIMIT` exit (`adk-agent-types.md` §4); `FunctionNode(timeout=...)` is a per-node deadline, not a loop cap. Deprecated `LoopAgent.max_iterations` defaults to `None` (unbounded). Always also set `RunConfig(max_llm_calls)`
- **Callback abort** — returning a non-None value from `before_model_callback` skips the model call; document this explicitly in the callback with a comment
- **Session not found** — `InMemoryRunner`/`Runner` do not auto-create sessions (`SessionNotFoundError`); `await get_session(user_id=principal, ...)` and answer 404 on `None` (it is also what another user's id returns); create new sessions server-side

All error paths must:
1. Log with structured logger (structlog) including `user_id`, `session_id`, `agent_name`
2. Either rethrow or return an error state — no silent empty returns
3. Surface the failure to the user (API error response, SSE error event)

## Verify

Run: `uv run pytest tests/ -v`  # exit 0; scripted fake model only — no Gemini credentials

- [ ] Fake `BaseLlm` registered; tests do not use a live model id
- [ ] Every `run_async` has `RunConfig(max_llm_calls=N)` and `asyncio.timeout`
- [ ] `McpToolset` factory rejects an empty `tool_filter`
- [ ] Chosen architecture matches **Choose the architecture** (no graph for a single tool-calling agent)

## Post-Code Review

After implementing any ADK agent feature:

1. Dispatch `adk-reviewer` agent (read-only) — pass the agent graph structure and tool implementations; `ai-security-reviewer` for tools with side effects or untrusted content
2. Dispatch `security-reviewer` — flag any tool that calls external APIs or handles user PII
3. Confirm: no hardcoded API keys, all inputs validated, all error paths logged
