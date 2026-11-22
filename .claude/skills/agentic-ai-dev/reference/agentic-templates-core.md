# Agentic AI Core Templates

FastAPI entry point, agent routes, base state and request models for a LangGraph / LangChain v1 service.
The lifespan and both routes below were executed together (langchain 1.2.8, langgraph 1.0.7, langgraph-checkpoint-postgres 3.2.1, FastAPI 0.135.2, PostgreSQL 16) with a scripted fake model: `ruff` and `mypy --strict` clean, 7 tests passing (OK answer, recursion limit, timeout, principal-bound threads, SSE framing, no exception text in responses or logs, negative control for the old checkpointer snippet).

Generic FastAPI concerns are NOT repeated here; use the Phase 2 references:
- Auth dependency (verified token → principal): `python-dev/reference/fastapi-auth-security.md` §4 and `fastapi-authorization-boundaries.md`.
- Request-id middleware, PII-safe `log_exception`, liveness/readiness probes: `deployment-ci-cd/reference/python-observability.md` §2, §4, §6.
- Error envelope and exception handlers: `python-dev/reference/fastapi-error-handling.md`.

## FastAPI Application Entry Point

**File:** `src/<service>/main.py`

```python
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from .agents.graphs.support_agent import build_support_agent
from .api.routes import agent, health
from .core.config import Settings

GraphFactory = Callable[[AsyncPostgresSaver, AsyncPostgresStore], Any]


def default_graph(checkpointer: AsyncPostgresSaver, store: AsyncPostgresStore) -> Any:
    return build_support_agent(checkpointer=checkpointer, store=store)


def create_app(app_settings: Settings | None = None, build: GraphFactory = default_graph) -> FastAPI:
    """App factory: `uvicorn my_agent_service.main:create_app --factory` (no module-level app).
    Tests pass their own settings and a `build` that uses a scripted model (agentic-testing.md)."""
    cfg = app_settings or Settings()  # type: ignore[call-arg]  # values come from the environment

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # from_conn_string() is an ASYNC CONTEXT MANAGER. Assigning it and calling .setup()
        # fails at startup (the returned object has no `setup`). Enter it here; it closes on shutdown.
        async with (
            AsyncPostgresSaver.from_conn_string(cfg.checkpoint_db_uri) as checkpointer,
            AsyncPostgresStore.from_conn_string(cfg.checkpoint_db_uri) as store,
        ):
            await checkpointer.setup()   # idempotent migrations; or run once from a deploy job
            await store.setup()
            app.state.graph = build(checkpointer, store)
            app.state.settings = cfg
            yield

    app = FastAPI(title=cfg.app_name, lifespan=lifespan,
                  docs_url="/api/docs" if cfg.app_env != "production" else None, redoc_url=None)
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    return app
```

- Multiple workers or high concurrency: build the saver from a `psycopg_pool.AsyncConnectionPool(conninfo, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})` opened in the same lifespan, and pass `AsyncPostgresSaver(pool)`. Size the pool against the database's connection limit.
- `InMemorySaver` is for tests only. `MemorySaver` is the older alias; do not use it in new code.

## Agent Routes

**File:** `src/<service>/api/routes/agent.py`

```python
import asyncio
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field

from ...core.config import Settings
from ...core.logging import log_exception   # python-observability.md section 2
from ..deps import Principal, get_principal  # verified token -> (org_id, user_id)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["agent"])


@dataclass(frozen=True)
class RequestCtx:
    """Runtime context for tools (ToolRuntime[RequestCtx]); never model-visible."""
    org_id: str
    user_id: str


def scoped_thread_id(principal: Principal, client_thread_id: uuid.UUID) -> str:
    """A client-supplied thread id only ever addresses the caller's own checkpoints."""
    return f"{principal.org_id}:{principal.user_id}:{client_thread_id}"


def _run_config(settings: Settings, thread_key: str) -> RunnableConfig:
    # recursion_limit is server config, never a request field.
    # LangGraph 1.0.x defaults to 10000 (env LANGGRAPH_DEFAULT_RECURSION_LIMIT): always set it.
    return {"configurable": {"thread_id": thread_key}, "recursion_limit": settings.max_graph_steps}


Status = Literal["OK", "ITERATION_LIMIT", "TIMEOUT"]
SAFE_COPY: dict[Status, str] = {
    "OK": "",
    "ITERATION_LIMIT": "I could not finish this request. Please narrow it down and try again.",
    "TIMEOUT": "This is taking longer than expected. Please try again.",
}


@router.post("/agent/invoke")
async def invoke_agent(
    body: AgentRequest, principal: PrincipalDep, graph: GraphDep, settings: SettingsDep
) -> AgentResponse:
    thread_id = body.thread_id or uuid.uuid4()
    thread_key = scoped_thread_id(principal, thread_id)
    ctx = RequestCtx(org_id=principal.org_id, user_id=principal.user_id)
    try:
        async with asyncio.timeout(settings.agent_timeout_s):    # env-driven deadline
            result = await graph.ainvoke(
                {"messages": [HumanMessage(body.message)]},
                _run_config(settings, thread_key),
                context=ctx,
            )
    except GraphRecursionError:            # raises; it does not END gracefully
        logger.warning("agent_step_limit", thread_id=str(thread_id))
        return AgentResponse(thread_id=thread_id, status="ITERATION_LIMIT", message=SAFE_COPY["ITERATION_LIMIT"])
    except TimeoutError:
        logger.warning("agent_timeout", thread_id=str(thread_id))
        return AgentResponse(thread_id=thread_id, status="TIMEOUT", message=SAFE_COPY["TIMEOUT"])
    except Exception as exc:  # noqa: BLE001 - route boundary: log type, return opaque code
        log_exception(logger, "agent_invoke_failed", exc, thread_id=str(thread_id))
        raise HTTPException(status_code=503, detail={"error_code": "AGENT_UNAVAILABLE"}) from None
    final = result["messages"][-1]
    if not isinstance(final, AIMessage) or final.tool_calls:
        # never present an unanswered tool call as success
        return AgentResponse(thread_id=thread_id, status="ITERATION_LIMIT", message=SAFE_COPY["ITERATION_LIMIT"])
    return AgentResponse(thread_id=thread_id, status="OK", message=final.text)
```

`PrincipalDep`, `GraphDep` and `SettingsDep` are `Annotated[..., Depends(...)]` aliases over `get_principal`, `request.app.state.graph` and `request.app.state.settings`. The streaming route (`POST /agent/stream`) and its SSE contract are in `agentic-streaming-hitl.md`.

Rules this route encodes:

| Concern | Rule |
|---|---|
| Identity | `org_id`/`user_id` come from the verified token, never the body or query |
| Threads | Checkpoint key is namespaced by principal (executed: user B presenting user A's thread id got an empty thread of his own). Alternative: an ownership table checked before resume, returning 404 for foreign ids |
| Tool scope | Passed as runtime `context=`; tools read `runtime.context` (see `tool-execution-safety.md`) |
| Step cap | `recursion_limit` from settings + `GraphRecursionError` mapped to `ITERATION_LIMIT` |
| Deadline | `asyncio.timeout(settings.agent_timeout_s)`, sized from measured p99 × 1.5 per call class |
| Degraded outcomes | Typed `status` + safe copy (HTTP 200) so clients render a deterministic message |
| Unexpected errors | `log_exception` (type + ids) and an opaque `error_code`; never `detail=f"...{e}"` |

Queue/push consumers differ on purpose: return non-2xx so the broker redelivers (`agentic-error-handling.md`).

## Health Check Route

Use the Phase 2 split (`python-observability.md` §6): liveness = process only; readiness = dependencies, each with its own timeout. Do **not** call the LLM on every probe (cost, rate limits, provider outage restarts healthy pods), and never put exception text in the body.

```python
@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        async with asyncio.timeout(2), request.app.state.db_pool.connection() as conn:
            await conn.execute("SELECT 1")   # psycopg_pool.AsyncConnectionPool from the lifespan
        checks["checkpoint_db"] = "healthy"
    except Exception as exc:  # noqa: BLE001
        log_exception(logger, "readiness_db_failed", exc)
        checks["checkpoint_db"] = "unhealthy"
    healthy = all(v == "healthy" for v in checks.values())
    if not healthy:
        response.status_code = 503          # probes act on the status code, not the body
    return {"status": "healthy" if healthy else "unhealthy", "checks": checks}
```

## Base State Schemas

**File:** `src/<service>/agents/state.py`

```python
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Hand-built graphs only; create_agent ships its own AgentState (extend via state_schema=)."""

    messages: Annotated[list[BaseMessage], add_messages]
    iteration_count: int   # checked in routing for a typed early stop; recursion_limit is the hard cap
    error_count: int


class RAGState(AgentState):
    query: str
    documents: list[dict[str, Any]]
    generation: str
    is_grounded: bool


class MultiAgentState(AgentState):
    current_agent: str
    agent_outputs: dict[str, str]
    task_plan: list[str]
    completed_tasks: list[str]
```

Scope ids (`org_id`, `user_id`) and the thread id are **not** state fields the model or client can write: they travel in `context=` and `config`.

## Request/Response Models

**File:** `src/<service>/models/schemas.py`

```python
class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    thread_id: uuid.UUID | None = None   # omit to start a conversation; scoped server-side


class AgentResponse(BaseModel):
    thread_id: uuid.UUID
    status: Literal["OK", "ITERATION_LIMIT", "TIMEOUT"]
    message: str
```

No `user_id`, `org_id`, `max_iterations` or model name in the request body: they are server decisions.
