---
name: agentic-ai-dev
description: "This skill provides patterns and templates for building production AI agents with Python 3.14, LangChain v1.5.2, LangGraph v1.2.24, and FastAPI 0.165.0. Use when creating AI agents, RAG systems, graph workflows, tools, memory systems, or agent tests."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: AI agent, LangChain, LangGraph, RAG system, graph workflow, FastAPI, Python 3.14, LangGraph agent, memory system, agent test
  related-skills: agentic-ai-coding-standard, python-dev, mcp-builder
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-26"
---

## Iron Law

**NO AGENT RUN WITHOUT AN EXPLICIT STEP LIMIT, A DEADLINE AND A CUMULATIVE BUDGET, AND NO HIGH-CONSEQUENCE ACTION WITHOUT A DURABLE HUMAN APPROVAL — the model proposes, code authorizes (scope, routes, approvals, limits)**

Before building an agent, confirm an agent is the right tool: a deterministic workflow or a single structured model call is cheaper and safer when the steps are known (`ai-playbook` decision step). Agents *request* business changes; a domain service or durable workflow *commits* them (`workflow-orchestration-patterns`). Then pick the runtime: `create_agent` vs `StateGraph` vs Functional API vs optional Deep Agents vs Google ADK vs deterministic code (`reference/agentic-architecture-choice.md`).

# Agentic AI Development Skill — Python 3.14 + LangChain + LangGraph + FastAPI

## Quick Scaffold

```bash
uv init my-agent-service && cd my-agent-service
uv add "langchain==1.5.2" "langchain-core==1.8.4" "langgraph==1.2.24" "langgraph-prebuilt==1.1.3" \
  "langgraph-checkpoint==4.3.2" "langgraph-checkpoint-postgres==3.2.1" "psycopg[binary,pool]==3.3.9" \
  "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "pydantic==2.14.4" "pydantic-settings==2.16.3" uvicorn structlog httpx
uv add <provider-integration>        # e.g. langchain-anthropic; uv.lock records the exact version
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "httpx2==2.16.2" "ruff==0.17.6" "mypy==2.4.1"
uv sync --locked                     # CI and Docker use the same command
```

Pins are the set locked together for this toolkit (`uv lock` + `uv sync --locked` exit 0 on Python 3.14.10; control flow, HITL and the PostgreSQL checkpointer/store re-run on these versions with a scripted model). `langgraph-prebuilt` no longer shares langgraph's version number: langgraph 1.2.24 requires `langgraph-prebuilt>=1.1.3,<1.2`, and langchain 1.5.2 requires `langgraph>=1.2.12,<1.3` (`agentic-config-project.md`).

## Process

1. **Scaffold** — `uv init` + install dependencies
2. **Configure** — `core/config.py` with pydantic-settings, `.env`, structured logging
3. **Define State** — `TypedDict` with `Annotated[list, add_messages]` for each agent
4. **Build Graph** — `StateGraph` with typed nodes, conditional edges, checkpointing
5. **Define Tools** — typed `ToolResult`, scope via `ToolRuntime`, allowlist, idempotency for writes (`tool-execution-safety.md`)
6. **Add Memory** — `AsyncPostgresSaver` (thread state) + `AsyncPostgresStore` (principal-namespaced long-term memory)
7. **Add Guardrails** — deterministic boundaries + screening of every untrusted channel (`agentic-guardrails-security.md`)
8. **Expose API** — principal from auth, server-scoped thread keys, `recursion_limit` + deadline, typed statuses, JSON SSE
9. **Write Tests** — scripted model through the real route + PostgreSQL; live golden + failure matrix before release
10. **Deploy** — Docker multi-stage, gunicorn + uvicorn, health checks, Prometheus

## Key Patterns

| Pattern | Implementation | Reference |
|---------|---------------|-----------|
| Architecture choice | `create_agent` / `StateGraph`+`Send` / `@entrypoint` / optional Deep Agents / ADK / deterministic | `agentic-architecture-choice.md` |
| Agent Graphs | `create_agent` (tool loop) or `StateGraph` (custom control flow) | `agentic-templates-basic.md` |
| Fan-out | `Send` when items are expensive/resumable; bounded `TaskGroup` for cheap reads; width cap in code | `agentic-templates-advanced.md` Pattern 7 |
| Tools | Typed `ToolResult`, `ToolRuntime` scope, `args_schema`, no exception text | `agentic-templates-tools.md`, `tool-execution-safety.md` |
| Model calls | `init_chat_model` from settings; one retry layer; deadlines; same-tier failover | `llm-inference-and-model-routing.md`, `agentic-llm-routing.md` |
| Routing | `Command(goto=...)` with a code-validated target; `Send` for map-reduce | `agentic-templates-advanced.md` |
| Checkpointing | `async with AsyncPostgresSaver.from_conn_string(...)` in lifespan; `InMemorySaver` in tests | `agentic-templates-core.md`, `agentic-memory-systems.md` |
| Limits | `recursion_limit` + `GraphRecursionError` mapping; call-limit middleware `exit_behavior="error"`; `asyncio.timeout` | `agentic-conventions.md` |
| Streaming | `stream_mode="messages"` filtered to the model node; JSON SSE; one terminal event | `agentic-streaming-hitl.md` |
| Human-in-the-Loop | `HumanInTheLoopMiddleware` or `interrupt()` + `Command(resume=...)` on a durable checkpointer | `agentic-streaming-hitl.md` |
| RAG | LangChain graphs for agentic/corrective flows; hybrid/ACL/citations in `rag-architect` | `agentic-templates-rag.md` |
| Guardrails | Deterministic boundary + probabilistic signals; fail closed | `agentic-guardrails-security.md` |
| Structured Output | Provider schema; `include_raw=True`; one fresh-context retry; typed failure | `llm-inference-and-model-routing.md` §4 |
| Error Recovery | Transient-only retry/failover middleware; typed statuses | `agentic-templates-resilience.md`, `agentic-error-handling.md` |
| Config | pydantic-settings, `SecretStr`, model ids required | `agentic-config-project.md` |
| Caching | Scoped answer keys; safety bypass; no fuzzy promotion | `agentic-caching-patterns.md` |

## Conventions & Rules

> For package layout, LangGraph rules, and FastAPI integration rules, read `reference/agentic-conventions.md`

## Documentation Sources

Before generating code, consult these sources for current syntax and APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| LangChain / LangGraph index | `https://docs.langchain.com/llms.txt` | Authoritative page list; read this first |
| LangChain / LangGraph | `langchain-docs` MCP when connected; else the Python overviews | `create_agent`, middleware, StateGraph, `Send`, Functional API, checkpointers, streaming, interrupts |
| Pydantic v2 | `https://docs.pydantic.dev/latest/llms-full.txt` | Model validation, settings, Field constraints |
| FastAPI / current APIs | `Context7` MCP (fallback, not primary) | FastAPI patterns; version-pin LangChain against installed wheels |

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `agentic-agent-variant-ladder.md` | Capability tier pattern, deterministic shadow agents, NDJSON replay | Multi-agent architecture |
| `agentic-config-project.md` | pyproject.toml, .env, config, Docker, ruff/mypy | Project setup |
| `agentic-templates-core.md` | FastAPI app, main.py, routes, middleware, base state | Creating API layer |
| `agentic-templates-basic.md` | ReAct Agent, Multi-Agent Collaborative patterns | Building basic agents |
| `agentic-architecture-choice.md` | When to use `create_agent`, StateGraph, Send, Functional API, Deep Agents, ADK | Before scaffolding any agent |
| `agentic-templates-advanced.md` | Supervisor, Command, sub-graphs, `Send` map-reduce | Building complex agents |
| `agentic-templates-resilience.md` | Error Recovery Agent, key design decisions | Agent error handling |
| `agentic-templates-rag.md` | 6 RAG architectures + document ingestion pipeline; Pattern 1 enforces `INSUFFICIENT_EVIDENCE` in code | Building RAG systems |
| `assets/r1-golden/` | Offline R1 RAG + tool cases (deterministic; not LangSmith/RAGAS) | Copy into `tests/golden/` |
| `tool-execution-safety.md` | Tool contracts, authority tiers, scope injection, allowlists, evidence gate, idempotency, budgets, approvals, durable resume (canonical) | Any agent with tools, esp. writes |
| `llm-inference-and-model-routing.md` | Model ids/lifecycle, sampling + reasoning, structured output, deadlines/retries/429, failover vs escalation, cache scoping, token budgets, multimodal limits (canonical, framework-neutral) | Any model call |
| `agentic-templates-tools.md` | Typed scoped tool template, external APIs, retries, MCP consumption | Defining agent tools |
| `agentic-guardrails-security.md` | Boundary vs signal, fail-closed screening of all channels | Adding safety layers |
| `../ai-playbook/reference/engineering-guardrails.md` | G1–G24 map: implementation, reviewer, gate, contract test per guardrail | Checking a capability against the guardrails standard |
| `agentic-memory-systems.md` | Checkpointer + principal-scoped Store memory, write pipeline, erasure, trimming | Adding memory to agents |
| `agent-memory-lifecycle.md` | Memory types, item contract + `scripts/validate_memory_item.py`, write policy, isolation, freshness/conflicts, erasure propagation, user controls, memory evals, metrics, cost (framework-neutral) | Designing or auditing any agent memory |
| `agentic-streaming-hitl.md` | Streaming + Human-in-the-Loop patterns | Real-time responses, approval flows |
| `agentic-llm-routing.md` | LangChain wiring: `init_chat_model`, failover, complexity router, prompt caching | Multi-model setups |
| `agentic-observability.md` | LangSmith, Prometheus, structured logging | Monitoring and debugging |
| `agentic-testing.md` | Scripted-model route tests on PostgreSQL, control-flow and contract tests, live release gate | Writing agent tests |
| `agentic-deployment.md` | Docker, docker-compose, production config | Deploying agents |
| `agentic-debugging.md` | Debugging playbook, common issues | Troubleshooting agents |
| `agentic-cost-optimization.md` | Cost management, budget caps, prompt optimization | Reducing LLM costs |
| `agentic-prompt-engineering.md` | Advanced prompting, structured output, templates | Writing better prompts |
| `agentic-error-handling.md` | Agent, tool, LLM provider, and API error handling patterns | Error handling in agents |
| `agentic-review-checklist.md` | Agentic AI review checklist (used by `agentic-ai-reviewer` agent) | Code reviews |
| `agentic-prompt-optimization.md` | Constitutional AI, Tree-of-Thoughts, model-specific templates (Claude/Gemini/GPT), prompt versioning registry, canary rollout, LLM-as-judge | Optimizing prompt quality; multi-model deployments; production prompt lifecycle |
| `llm-judge-advanced.md` | Production LLM-as-Judge: bias taxonomy (position, length, self-enhancement), position swap protocol, rubric generation, PoLL ensemble, hierarchical eval | Evaluating agent outputs with reliability; high-stakes eval decisions |
| `agentic-caching-patterns.md` | Scoped tiered answer cache, safety bypass, tool-result cache, required tests | Adding caching to agents |
| `agentic-makefile-patterns.md` | 40+ Makefile commands for setup, testing, RAG, memory, evaluation, Docker, observability — reference patterns for agentic AI services | Setting up developer workflow automation |

Model selection and routing (FAST/STANDARD/STRONG, approved-model registry, policy gate, escalation vs failover, LiteLLM Router settings): `reference/agentic-llm-routing.md`; registry schema `assets/model-registry.schema.json`, validator `python3 scripts/validate_model_registry.py [--json] FILE` (exit 0/1/2, `--selftest`).

## Common Commands

```bash
uvicorn src.main:create_app --factory --reload        # Run dev server (hot reload; app factory)
uv run pytest -q -m "not live"                         # R1 tests (scripted models, real PostgreSQL)
uv run pytest -q -m "not live" --cov=src --cov-report=term-missing
ruff check --fix .                                     # Lint and auto-fix
ruff format .                                          # Format code
mypy src/                                              # Type check
```

## Error Handling

> For error handling patterns and code examples, read `reference/agentic-error-handling.md`

**LLM provider errors**: One retry layer on transient classes only, inside the run deadline; failover to an approved same-tier model on availability errors only; everything else becomes a typed status at the route.

**Tool execution errors**: Catch classified exceptions in the tool and return `ToolResult` with an `error_code`; never exception text. Unclassified errors propagate to the route's boundary handler.

**Graph infinite loops**: Explicit `recursion_limit` from settings (LangGraph 1.2.x default is **10007**, 1.0.x was 10000 — never rely on it) plus call-limit middleware with `exit_behavior="error"`; map `GraphRecursionError` to `ITERATION_LIMIT`.

## Post-Code Review

After writing agentic AI code, dispatch these reviewer agents:
- `agentic-ai-reviewer` — scope/authority, limits, HITL, errors, streaming, tests
- `ai-security-reviewer` — prompt/tool-output injection, exfiltration, tenant isolation
- `security-reviewer` — general OWASP issues in the API layer
