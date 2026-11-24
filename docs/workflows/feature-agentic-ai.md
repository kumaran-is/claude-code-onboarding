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

**Coding rules**: the Key Rules table in `skills/agentic-ai-coding-standard/SKILL.md` (canonical; not restated here).

**Guardrails** (`skills/ai-playbook/reference/engineering-guardrails.md`): the Decision Record (`/ai-decision-record`) records the engineering risk tier T0–T3, which fixes the mandatory guardrails. Separate it from the autonomy level A0–A4 (governance) and the playbook's 0–5 tier.

**Gate**: Both skills loaded, MCP queried for LangGraph API, Decision Record exists with a T-tier

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

**Guardrail contract tests**: copy `skills/ai-launch-check/assets/guardrail_contract_tests.py` into the service tests, implement its adapter against the FastAPI routes with a scripted fake model, and mark rows the capability cannot exercise NOT APPLICABLE with a reason. Break one control per family once (approval, schema, idempotency, tenant filter, budget, kill switch) and watch the matching test fail before trusting the green run.

**Gate**: Graph runs end-to-end with test inputs, all tools execute, guardrail contract suite passes (exit code recorded)

---

### Phase 5 — Review (run in parallel)

**Agent 1**: `agentic-ai-reviewer` (sonnet)
- Vibe: *"Finds the infinite loop before production does"*
- Checks: graph correctness, loop termination conditions, guardrail coverage, iteration limits, cost efficiency, production readiness

**Agent 2**: `silent-failure-hunter` (sonnet)
- Vibe: *"An empty catch block is not error handling — it's a lie to the operator"*
- Checks: swallowed tool errors, bare `except`, missing LangSmith logging, silent graph exits

**Agent 3**: `ai-security-reviewer` — injection, isolation, egress, authority; findings tagged with guardrail ids G1–G24

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
| 2 — Load skills | `agentic-ai-dev` + `agentic-ai-coding-standard` + `/ai-decision-record` | Coding standard + T-tier | MCP queried |
| 3 — Design graph | Draw StateGraph | Graph diagram in `docs/diagrams/` | Graph compiles |
| 4 — Implement | tools → state → nodes → graph → API | Working agent | E2E test passes |
| 4 — Guardrail tests | `guardrail_contract_tests.py` adapter | §9 negative tests | Suite exit 0, skips justified |
| 5 — Review | `agentic-ai-reviewer` + `silent-failure-hunter` + `ai-security-reviewer` | Findings | Zero CRITICAL |
| Before production | `/ai-launch-check` | GO / NO-GO | No ❌ |
| 6 — Pre-commit + PR | `/validate-changes` + `/review-pr` | APPROVE + review | Gate passed |

---

## Common Pitfalls

- **No loop termination** — every `while True` equivalent in a graph needs `max_iterations`; infinite loops in prod consume tokens indefinitely
- **Untyped state** — `dict` state is hard to debug; always use `TypedDict`
- **Tools returning raw strings** — parsers downstream break on format changes; return structured `BaseModel`
- **Hardcoded model name** — model ids come from settings via `init_chat_model` (`agentic-ai-coding-standard` rule 5); never a literal or a floating `latest` alias (guardrails G11)
- **Missing checkpointer** — without checkpointing, long-running agents can't resume after failure
- **LangChain API from memory** — versions change rapidly; always query Context7 MCP for current syntax

## Related Workflows

- [`ideation-to-spec.md`](ideation-to-spec.md) — spec and plan first
- [`pgvector-rag-pipeline.md`](pgvector-rag-pipeline.md) — if agent needs vector retrieval
- [`weaviate-collection-pipeline.md`](weaviate-collection-pipeline.md) — Weaviate-backed RAG
- [`deployment-ci-cd.md`](deployment-ci-cd.md) — deploy agent service to Cloud Run
