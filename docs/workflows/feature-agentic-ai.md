# Feature Development — Agentic AI (LangChain / LangGraph)

> **When to use**: Building an AI agent, RAG system, or graph workflow with Python 3.14, LangChain v1.5.2, LangGraph v1.2.24, FastAPI 0.165.0
> **Time estimate**: 2–6 hours per agent depending on graph complexity
> **Prerequisites**: Approved spec in `docs/specs/`, approved plan in `docs/plans/`

## Overview

Full agentic AI feature lifecycle from scaffold through LangGraph StateGraph design to reviewed, production-ready service. Includes guardrails, cost awareness, observability, and loop protection by default.

---

## Phases

### Phase 1 — Project Scaffold (new projects only)

**Trigger**: No existing agentic AI service
**Command**: `/scaffold-agentic-ai [project-name]`
**Source**: `commands/scaffold-agentic-ai.md`
**7-step process**:
1. Read `agentic-ai-dev` skill reference files
2. Initialize project via `uv init`
3. Add production + dev dependencies (LangChain, LangGraph, FastAPI, Pydantic v2, LangSmith)
4. Create directory structure under `src/<service_name>/`
5. Create core modules, agent layer, LLM providers, API layer, tests
6. Add infrastructure (Dockerfile, `docker-compose.dev.yml`, `.env`)
7. Verify with `ruff` and `mypy`

**Produces**: Production-ready agentic AI service scaffold
**Gate**: `ruff check .` clean, `mypy .` clean, `pytest` passes

---

### Phase 2 — Load Skills

**Trigger**: About to design or implement any agent
**Action 1**: Load `agentic-ai-dev` skill (`skills/agentic-ai-dev/SKILL.md`)
**Action 2**: Load `agentic-ai-coding-standard` skill (`skills/agentic-ai-coding-standard/SKILL.md`)
**MCP**: Context7 (or the `langchain-docs` MCP) for LangChain v1.5.2 and LangGraph v1.2.24 current APIs (not from memory — always query)

**17 mandatory coding rules** (from `skills/agentic-ai-coding-standard/SKILL.md:20-36`):
1. State typed with `TypedDict` — no untyped dicts in StateGraph
2. Message list handled with `add_messages` reducer
3. Loop protection — every graph has max iteration limit
4. Tool functions decorated with `@tool`, typed signatures
5. LLM instantiated via factory, not hardcoded
6. Checkpointing for resumable workflows
7. Structured error handling — no bare `except`
8. Logging with LangSmith integration
9. Guardrails on all user-facing inputs
10. Cost-aware: token budgets on LLM calls
11. No streaming without `astream_events` or `astream`
12. Tools return structured data — not raw strings
13. Human-in-the-loop nodes use `interrupt_before`
14. Agent memory via `MemorySaver` or external store
15. Model selection via config — not hardcoded in graph
16. Tests cover happy path, tool failure, and loop termination
17. FastAPI endpoints use `BackgroundTasks` for long-running agents

**Gate**: Both skills loaded, MCP queried for LangGraph API

---

### Phase 3 — Design StateGraph

**Trigger**: Skills loaded
**Pattern** (from `skills/agentic-ai-dev/SKILL.md`):

```
Define TypedDict state
         │
    Define nodes (Python functions)
         │
    Build StateGraph
    - add_node() for each node
    - add_edge() / add_conditional_edges()
    - set_entry_point()
    - set_finish_point() or END
         │
    Add checkpointer (MemorySaver or PostgresSaver)
         │
    Compile graph
```

**Required elements**:
- `max_iterations` guard on any loop
- Error node for tool failures
- At least one `interrupt_before` if human approval needed

**Produces**: StateGraph design (draw it in `docs/diagrams/` with mermaid-expert agent)
**Gate**: Graph compiles without error, no unreachable nodes

---

### Phase 4 — Implement (Tools → Graph → API)

**Build order**:
1. Tool definitions → `src/<service>/tools/<name>.py` (use `@tool` decorator)
2. State definition → `src/<service>/agent/state.py` (`TypedDict`)
3. Node functions → `src/<service>/agent/nodes.py`
4. Graph assembly → `src/<service>/agent/graph.py`
5. Guardrails → `src/<service>/guardrails/`
6. LLM provider → `src/<service>/llm/provider.py`
7. FastAPI endpoints → `src/<service>/api/routes.py`
8. Memory/persistence → `src/<service>/memory/`

**Error handling** (from `skills/agentic-ai-coding-standard/SKILL.md`):
- Every `except` must log the error AND either raise or return error state
- Never `return []` on tool failure — return `ToolError` or raise
- Graph errors surface via `RunnableConfig` error handling

**Gate**: Graph runs end-to-end with test inputs, all tools execute

---

### Phase 5 — Review (run in parallel)

**Agent 1**: `agentic-ai-reviewer` (sonnet)
- Vibe: *"Finds the infinite loop before production does"*
- Checks: graph correctness, loop termination conditions, guardrail coverage, iteration limits, cost efficiency, production readiness

**Agent 2**: `silent-failure-hunter` (sonnet)
- Vibe: *"An empty catch block is not error handling — it's a lie to the operator"*
- Checks: swallowed tool errors, bare `except`, missing LangSmith logging, silent graph exits

**Gate**: Zero CRITICAL findings; HIGH findings resolved or accepted

---

### Phase 6 — Pre-Commit + PR

**Command**: `/validate-changes` → must return APPROVE
**Command**: `/review-pr` → 6-role review

**Gate**: APPROVE verdict + all CRITICAL/HIGH resolved

---

## Quick Reference

| Phase | What to Run | Produces | Gate |
|-------|-------------|----------|------|
| 1 — Scaffold | `/scaffold-agentic-ai` | Full project skeleton | `ruff` + `mypy` clean |
| 2 — Load skills | `agentic-ai-dev` + `agentic-ai-coding-standard` | 17-rule standard | MCP queried |
| 3 — Design graph | Draw StateGraph | Graph diagram in `docs/diagrams/` | Graph compiles |
| 4 — Implement | tools → state → nodes → graph → API | Working agent | E2E test passes |
| 5 — Review | `agentic-ai-reviewer` + `silent-failure-hunter` | Findings | Zero CRITICAL |
| 6 — Pre-commit + PR | `/validate-changes` + `/review-pr` | APPROVE + review | Gate passed |

---

## Common Pitfalls

- **No loop termination** — every `while True` equivalent in a graph needs `max_iterations`; infinite loops in prod consume tokens indefinitely
- **Untyped state** — `dict` state is hard to debug; always use `TypedDict`
- **Tools returning raw strings** — parsers downstream break on format changes; return structured `BaseModel`
- **Hardcoded model name** — use `ChatOpenAI(model=config.model_name)` not `ChatOpenAI(model="gpt-4")` directly
- **Missing checkpointer** — without checkpointing, long-running agents can't resume after failure
- **LangChain API from memory** — versions change rapidly; always query Context7 MCP for current syntax

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — spec and plan first
- [`pgvector-rag-pipeline.md`](pgvector-rag-pipeline.md) — if agent needs vector retrieval
- [`weaviate-collection-pipeline.md`](weaviate-collection-pipeline.md) — Weaviate-backed RAG
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — deploy agent service to Cloud Run
