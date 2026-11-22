# ADK Core Patterns

Executed with `google-adk==1.29.0` and a scripted fake model (`adk-testing.md` §2) — no live Gemini call. Decide first whether the capability needs an agent at all (`ai-playbook` skill: deterministic code when rules are fixed; the model proposes, code authorizes).

## 1. Agent configuration

```python
import os

from google.adk.agents import Agent
from google.genai import types
from pydantic import BaseModel, Field

AGENT_MODEL = os.environ["AGENT_MODEL"]  # real code: settings.agent_model — no model id default in code


class AnalysisResult(BaseModel):
    summary: str
    recommendations: list[str] = Field(min_length=1)


def lookup_usage(metric: str) -> dict:
    """Return the current value of one usage metric.

    Args:
        metric: One of 'active_users', 'requests_per_day'.

    Returns:
        {"ok": bool, "error_code": str | None, "data": {"metric": str, "value": int} | None}
    """
    values = {"active_users": 1200, "requests_per_day": 56000}  # real code: a service call
    if metric not in values:
        return {"ok": False, "error_code": "UNKNOWN_METRIC", "data": None}
    return {"ok": True, "error_code": None, "data": {"metric": metric, "value": values[metric]}}


analysis_agent = Agent(
    name="analysis_agent",
    model=AGENT_MODEL,
    description="Analyzes usage metrics and recommends actions.",
    instruction="Use lookup_usage for every number you cite. Return a summary and recommendations.",
    tools=[lookup_usage],
    output_schema=AnalysisResult,   # validated; works together with tools in 1.29
    output_key="analysis_result",   # stores the validated dict in session state
    generate_content_config=types.GenerateContentConfig(max_output_tokens=2048),
)
```

Generation config rules (details: `gemini-api-dev` skill, "Sampling and thinking"):
- Gemini 3.x: leave `temperature`/`top_p`/`top_k` at their defaults; Google documents that values below 1.0 can cause looping or degraded reasoning, and newer generations ignore them. Get determinism from `output_schema`, validators and evals.
- Thinking tokens count against `max_output_tokens`: a small cap returns empty text with finish reason `MAX_TOKENS`. Lower `thinking_level` instead of shrinking the cap: `GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="LOW"))` or `planner=BuiltInPlanner(thinking_config=...)` — not both (the planner wins). Probe each model: some reject some levels.
- Safety settings: set only what the product decision requires; a blocked response is a typed outcome, not an empty answer.

Never put `eval()`/`exec()` behind a tool: tool arguments are model-controlled input.

## 2. Running an agent

`Runner.run_async` is the API for services; `runner.run()` is a blocking wrapper for scripts and notebooks only. Session-service methods are coroutines — `await` them (an un-awaited `create_session` returns a coroutine and `.id` fails).

```python
from google.adk.agents import RunConfig
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import InMemorySessionService


async def run_once(runner: Runner, user_id: str, text: str) -> str:
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id)
    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.UserContent(parts=[types.Part(text=text)]),
        run_config=RunConfig(max_llm_calls=10),   # default is 500: always cap
    ):
        if event.is_final_response() and event.content:
            final_text = "".join(p.text for p in event.content.parts or [] if p.text)
    return final_text


dev_runner = InMemoryRunner(agent=analysis_agent, app_name="my_app")   # in-memory services, REAL model
service_runner = Runner(app_name="my_app", agent=analysis_agent, session_service=InMemorySessionService())
```

`InMemoryRunner` is not a test double: it still calls the configured model. Tests use a scripted model (`adk-testing.md`). In a service, wrap `run_async` in `asyncio.timeout(...)` and map failures to typed statuses (`adk-fastapi-integration.md` §5).

## 3. App class

Use `App` when you need plugins, context caching, events compaction or resumability (fields in 1.29: `name`, `root_agent`, `plugins`, `events_compaction_config`, `context_cache_config`, `resumability_config`):

```python
from google.adk.apps.app import App

app = App(name="my_app", root_agent=analysis_agent)  # plugins=[...] for cross-cutting callbacks
runner = Runner(app=app, session_service=InMemorySessionService())
```

## 4. Session management

```python
async def sessions_demo() -> None:
    svc = InMemorySessionService()
    session = await svc.create_session(app_name="my_app", user_id="user_001", state={"language": "en"})
    same = await svc.get_session(app_name="my_app", user_id="user_001", session_id=session.id)
    listed = await svc.list_sessions(app_name="my_app", user_id="user_001")
    await svc.delete_session(app_name="my_app", user_id="user_001", session_id=session.id)
    assert same is not None and len(listed.sessions) == 1
```

- `get_session` is scoped by `user_id`: another user's id returns `None` (executed). Pass the authenticated principal as `user_id` and treat `None` as 404.
- Create the service once per process. Production backends:
  - self-hosted Postgres / Cloud SQL: `DatabaseSessionService(db_url="postgresql+asyncpg://...")` — needs `sqlalchemy[asyncio]` and an async driver (executed on PostgreSQL 16)
  - managed Agent Engine: `VertexAiSessionService(project=..., location=..., agent_engine_id=...)` — the kwarg is `project`, not `project_id` (`TypeError`, executed)
- Put server-decided values (`org_id`, feature flags) in `state` at creation; tools read them from `tool_context.state`, the model never supplies them (`adk-tools-callbacks.md` §5).

> Structured output parsing, state access and `UserContent` construction: `adk-structured-output.md`.
