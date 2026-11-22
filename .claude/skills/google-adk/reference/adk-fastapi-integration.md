# ADK FastAPI Integration

Verified against `google-adk==1.29.0` + FastAPI with a scripted fake model (no live Gemini call): the module below and the tests in `adk-testing.md` §5 pass (`pytest`: 6 passed), `ruff` and `mypy --strict` (pydantic plugin) are clean. Generic FastAPI rules (auth dependency, error envelope, request id) live in `python-dev/reference/fastapi-auth-security.md`, `fastapi-authorization-boundaries.md` and `fastapi-error-handling.md` — this file covers only what ADK adds.

## 1. Project structure

```
src/
+-- main.py           # lifespan: settings, session service, Runner (once per process)
+-- config.py         # Settings (pydantic-settings) - model id, DB url, caps
+-- agents/assistant.py
+-- tools/
+-- api/routes.py     # /chat (final answer) and /stream (SSE)
tests/                # fake model, see adk-testing.md
```

## 2. Settings and agent

```python
# src/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    agent_model: str               # required: no model id default in code (fail fast at startup)
    session_db_url: str            # postgresql+asyncpg://... - never log it
    agent_timeout_s: float = 30.0  # size from measured p99 x 1.5, per call class
    max_llm_calls: int = 20        # per request; ADK default is 500


# src/agents/assistant.py
from google.adk.agents import Agent

ROOT_AGENT = "assistant"


def build_agent(settings: Settings) -> Agent:
    return Agent(
        name=ROOT_AGENT,
        model=settings.agent_model,
        description="Answers account and usage questions.",
        instruction="Answer the user's question using the available tools.",
        tools=[...],
    )
```

## 3. Lifespan: build the session service and Runner once

```python
# src/main.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

APP_NAME = "support-assistant"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    session_service = DatabaseSessionService(db_url=settings.session_db_url)  # builds an engine: once
    app.state.settings = settings
    app.state.runner = Runner(app_name=APP_NAME, agent=build_agent(settings), session_service=session_service)
    yield
    await app.state.runner.close()  # closes MCP toolsets and plugins


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api")
```

Session backends (verified on 1.29):

| Backend | Construct | Notes |
|---|---|---|
| Tests / local | `InMemorySessionService()` | Lost on restart; never in production |
| Self-hosted Postgres (Cloud SQL) | `DatabaseSessionService(db_url="postgresql+asyncpg://...")` | Needs `sqlalchemy[asyncio]` (greenlet) and an async driver (`asyncpg`); without greenlet the import fails. Executed against PostgreSQL 16. |
| Managed Agent Engine | `VertexAiSessionService(project=..., location=..., agent_engine_id=...)` | `project_id=` raises `TypeError` |

## 4. Session ownership: ids come from the principal

`user_id` is the authenticated principal, never a body or query field. The session id is minted by the server (`create_session` without `session_id`) and returned to the client; a client-supplied id is resumed only through `get_session(user_id=principal.user_id, ...)`, which returns `None` for another user's session (executed) — answer 404 in both cases. Scope the agent needs (`org_id`) goes into session state server-side, where `adk-tools-callbacks.md` §5 injects it into tool arguments.

```python
# src/api/routes.py
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from google.adk.sessions import BaseSessionService, Session
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Principal:
    user_id: str
    org_id: str


PrincipalDep = Annotated[Principal, Depends(get_principal)]  # your verified-token dependency


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None   # resume request; ownership checked below


class ChatResponse(BaseModel):
    status: Literal["ANSWERED", "TIMEOUT", "LIMIT_REACHED", "MODEL_UNAVAILABLE", "AGENT_ERROR"]
    message: str
    session_id: str


async def owned_session(svc: BaseSessionService, principal: Principal, session_id: str | None) -> Session:
    if session_id is None:
        return await svc.create_session(
            app_name=APP_NAME, user_id=principal.user_id, state={"org_id": principal.org_id}
        )
    session = await svc.get_session(app_name=APP_NAME, user_id=principal.user_id, session_id=session_id)
    if session is None:  # unknown id or another user's session: same answer
        raise HTTPException(status_code=404, detail={"error_code": "SESSION_NOT_FOUND"})
    return session
```

## 5. POST /chat: bounded run, typed outcome

Every run has a wall-clock deadline (`asyncio.timeout`) and an LLM-call cap (`RunConfig(max_llm_calls=...)`; exceeding it raises `LlmCallsLimitExceededError`, executed). Each failure class maps to a typed status; the exception text never reaches the client or the log (`log_exception` is the toolkit helper, `deployment-ci-cd/reference/python-observability.md` §2).

```python
import asyncio

from fastapi import Request
from google.adk.agents import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.runners import Runner
from google.genai import errors, types

FailureStatus = Literal["TIMEOUT", "LIMIT_REACHED", "MODEL_UNAVAILABLE", "AGENT_ERROR"]


def failure_status(exc: Exception) -> FailureStatus:
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, LlmCallsLimitExceededError):
        return "LIMIT_REACHED"
    if isinstance(exc, errors.APIError):  # google-genai errors, not google.api_core
        return "MODEL_UNAVAILABLE"
    return "AGENT_ERROR"


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, principal: PrincipalDep) -> ChatResponse:
    runner: Runner = request.app.state.runner
    settings: Settings = request.app.state.settings
    session = await owned_session(runner.session_service, principal, body.session_id)
    text = ""
    try:
        async with asyncio.timeout(settings.agent_timeout_s):
            async for event in runner.run_async(
                user_id=principal.user_id,
                session_id=session.id,
                new_message=types.UserContent(parts=[types.Part(text=body.message)]),
                run_config=RunConfig(max_llm_calls=settings.max_llm_calls),
            ):
                if event.is_final_response() and event.author == ROOT_AGENT and event.content:
                    text = "".join(p.text for p in event.content.parts or [] if p.text)
    except Exception as exc:  # every failure maps to a typed status
        status = failure_status(exc)
        log_exception(logger, "agent_run_failed", exc, session_id=session.id, status=status)
        return ChatResponse(status=status, message="", session_id=session.id)
    return ChatResponse(status="ANSWERED", message=text, session_id=session.id)
```

Transport semantics: a synchronous route returns the typed fallback body (no bare 500 dead end); a queue/push consumer returns non-2xx on purpose so the broker redelivers — keep the difference documented so nobody "fixes" it. If the answer must be grounded, also apply the deterministic evidence gate (`agentic-ai-dev/reference/tool-execution-safety.md`).

## 6. POST /stream: SSE

The message goes in a POST body (a GET query string lands in access logs). Token streaming needs `RunConfig(streaming_mode=StreamingMode.SSE)`; ADK's Gemini model then emits partial events followed by one aggregated final event with the same text (`google/adk/models/google_llm.py`, read in 1.29) — forward partials only. Forward only the user-facing agent's text: tool calls, tool results and internal agents' output never reach the client. Ownership and other security decisions run before the `StreamingResponse` is returned. One terminal event: `error` (opaque code) OR `done`. The canonical agent SSE contract is `streaming-protocols` skill §6a.

```python
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import StreamingMode


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def stream(body: ChatRequest, request: Request, principal: PrincipalDep) -> StreamingResponse:
    runner: Runner = request.app.state.runner
    settings: Settings = request.app.state.settings
    session = await owned_session(runner.session_service, principal, body.session_id)  # before streaming

    async def events() -> AsyncIterator[str]:
        try:
            async with asyncio.timeout(settings.agent_timeout_s):
                async for event in runner.run_async(
                    user_id=principal.user_id,
                    session_id=session.id,
                    new_message=types.UserContent(parts=[types.Part(text=body.message)]),
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=settings.max_llm_calls),
                ):
                    if event.partial and event.author == ROOT_AGENT and event.content:
                        for part in event.content.parts or []:
                            if part.text:
                                yield sse("content", {"text": part.text})
        except Exception as exc:
            status = failure_status(exc)
            log_exception(logger, "agent_stream_failed", exc, session_id=session.id, status=status)
            yield sse("error", {"code": status})  # no "done" after an error
            return
        yield sse("done", {"session_id": session.id})

    return StreamingResponse(events(), media_type="text/event-stream")
```

`CancelledError` (client disconnect) is not an `Exception`, so it propagates and cancels the agent run. Executed on google-adk 1.29.0 with a slow fake `BaseLlm`: both `asyncio.Task.cancel()` and an anyio cancel scope (what Starlette uses on disconnect) cancelled the in-flight model call (completed=0, cancelled=1). LangGraph differs: see `agentic-ai-dev/reference/agentic-streaming-hitl.md`. Re-check after an ADK upgrade. Never retry a stream after the first byte; the client re-requests. Partial-event behaviour against a live Gemini endpoint was not executed here (fake model reproduces the documented partial + aggregated shape).

## 7. Memory

Pass `memory_service=` to `Runner` and prefer the `load_memory` tool. Read `adk-memory-artifacts.md` §2 before adding `preload_memory`: it places recalled text in the system instruction.

## 8. Error-handling checklist

- [ ] No `detail=str(e)`, `f"...{e}"` or exception text in SSE `data:`; no `error=str(exc)` / `exc_info=True` in logs
- [ ] Every `run_async` inside `asyncio.timeout` with `RunConfig(max_llm_calls=...)`
- [ ] Each failure class has a typed status and a metric; the client always gets a terminal answer
- [ ] `user_id` from the principal; session ids minted server-side or ownership-checked
