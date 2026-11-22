---
name: agentic-ai-coding-standard
description: "This skill provides coding standards for Python agentic AI services with LangChain/LangGraph. Use when reviewing or writing Python agentic AI code. Covers state management, tool definitions, graph structure, error handling, and observability."
allowed-tools: Read
metadata:
  triggers: LangChain, LangGraph, agentic AI, Python AI agent, FastAPI agent, state management, tool functions, guardrails, AI agent coding standard
  related-skills: agentic-ai-dev, code-reviewer, security-reviewer
  domain: backend
  role: specialist
  scope: review
  output-format: report
last-reviewed: "2026-11-22"
---

# Agentic AI Coding Standards

## Iron Law

**THE MODEL PROPOSES, CODE AUTHORIZES — scope, routing targets, approvals, budgets and limits are computed by code, never taken from model output; and no agent pattern is written from memory: verify it against the agentic-ai-dev references and the LangChain docs MCP first.**

Mandatory coding standards for all Python agentic AI services using LangChain, LangGraph, and FastAPI.

## Key Rules

| # | Rule | Standard |
|---|------|----------|
| 1 | State typing | Always `TypedDict`; never `dict[str, Any]` |
| 2 | Message lists | `Annotated[list[BaseMessage], add_messages]` |
| 3 | Loop protection | Explicit `recursion_limit` from settings on every run (library default is 10000); `GraphRecursionError` → typed `ITERATION_LIMIT`; call-limit middleware with `exit_behavior="error"` |
| 4 | Tool functions | `@tool` + docstring (incl. degradation mode) + `args_schema` bounds; scope via `ToolRuntime`; return typed `ToolResult` (`ok`/`error_code`/`data`); no exception text; no stub tools with synthetic data |
| 5 | LLM instantiation | `init_chat_model` in one module, model ids from settings; never inline `ChatX()` in nodes |
| 6 | Sampling | Per provider guidance per model (e.g. Gemini 3.x: keep default temperature); no global "temperature 0" rule; output limit covers reasoning tokens |
| 7 | Checkpointing | `AsyncPostgresSaver` entered with `async with ... from_conn_string()` (or built on a pool) in the lifespan; `InMemorySaver` only in tests |
| 8 | Error handling | Classified exceptions → typed status; `log_exception` (type + ids); never exception text to clients, streams or the model |
| 9 | Naming | `build_<name>_agent()`, `<verb>_node()`, `<Name>State` |
| 10 | Config | pydantic-settings with fail-fast; no `os.getenv()` with silent defaults |
| 11 | Type hints | `mypy --strict`; `Literal` for routing return types |
| 12 | Async | `async def` for all I/O; `ainvoke`/`astream` in API routes |
| 13 | Logging | structlog with trace id, feature, model id, prompt version, hashed thread key; no message text |
| 14 | Secrets | Never log API keys; redact PII before logging |
| 15 | Testing | Scripted model: scope injection, limits, principal-bound threads, SSE framing, no exception text, HITL, idempotency; live golden + failure matrix before release |
| 16 | Cost | Cumulative per-request budgets; meter reasoning and cache-read tokens; cheapest tier that passes evals |
| 17 | Imports | Group: stdlib → third-party → langchain/langgraph → local |

## Import Ordering

```python
# 1. Standard library
from __future__ import annotations
import json
from typing import Annotated, Literal

# 2. Third-party
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# 3. LangChain / LangGraph
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# 4. Local
from ..core.config import settings
from ..core.logging import get_logger
```

## Naming Conventions

| Element | Pattern | Example |
|---------|---------|---------|
| State | `<Name>State` | `AgentState`, `RAGState`, `MultiAgentState` |
| Graph builder | `build_<name>_agent()` | `build_react_agent()`, `build_rag_agent()` |
| Node function | `<verb>_node()` | `agent_node()`, `retrieve_node()`, `grade_node()` |
| Tool function | `<verb>_<noun>()` | `search_knowledge_base()`, `get_shipment_status()`, `propose_refund()` |
| Model client | `chat_model(tier)` | One module wrapping `init_chat_model`; ids from settings |
| Config | `Settings` | pydantic-settings, singleton `settings` instance |
| Exception | `<Name>Error` | `AgentError`, `ToolError`, `LLMProviderError` |

## File Structure

```
src/<service>/
├── agents/
│   ├── graphs/          # build_*_agent() functions
│   ├── nodes/           # *_node() functions
│   ├── tools/           # @tool functions
│   └── state.py         # TypedDict state schemas
├── rag/                 # RAG-specific code
├── memory/              # Checkpointing + semantic memory
├── guardrails/          # Input/output validation
├── llm/client.py        # chat_model(tier) via init_chat_model
├── core/
│   ├── config.py        # pydantic-settings
│   ├── logging.py       # structlog setup
│   └── exceptions.py    # Exception hierarchy
├── observability/       # Metrics + tracing
├── models/schemas.py    # Pydantic request/response
├── api/routes/          # FastAPI routes
└── main.py              # FastAPI app + lifespan
```

## Reference

For concrete code examples and anti-patterns, Read [reference/agentic-standards-examples.md](reference/agentic-standards-examples.md).

## Error Handling

**Import errors**: Verify LangChain/LangGraph package versions match `pyproject.toml` constraints.

**State type mismatches**: Ensure all graph state fields use `TypedDict` with proper `Annotated` types — never `dict[str, Any]`.

**Graph recursion errors**: `GraphRecursionError` means the run hit `recursion_limit` (super-steps, not model calls). Map it to `ITERATION_LIMIT`, then inspect the trajectory for a routing loop before raising the limit.
