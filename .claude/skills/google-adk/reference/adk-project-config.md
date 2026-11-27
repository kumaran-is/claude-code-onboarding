# ADK Project Configuration

## 1. pyproject.toml — exact pins + lockfile

Pin `google-adk` exactly and commit `uv.lock`; CI and Docker install with `uv sync --locked` (refuses a stale lock). A `>=` range lets a fresh resolve pull a different ADK whose APIs differ from these references.

```toml
[project]
name = "my-adk-service"
version = "0.1.0"
requires-python = ">=3.14"          # interpreter patch pinned in .python-version (3.14.10) and the Docker base
dependencies = [
    "google-adk[db,mcp,otel]==2.15.1", # mcp extra: McpToolset; db: DatabaseSessionService; otel: tracing
    "google-genai==2.34.0",           # google-adk 2.15 requires google-genai>=2.34,<3
    "fastapi[standard-no-fastapi-cloud-cli]==0.165.0",  # what google-adk 2.15 resolves; no fastapi-cloud-cli deps
    "uvicorn[standard]==<pin>",
    "pydantic-settings==<pin>",
    "structlog==<pin>",
    "sqlalchemy[asyncio]==<pin>",   # DatabaseSessionService needs the asyncio extra (greenlet)
    "asyncpg==<pin>",               # async Postgres driver for postgresql+asyncpg:// URLs
]

[dependency-groups]
dev = ["pytest==9.2.0", "pytest-asyncio==1.5.0", "httpx2==2.16.2", "aiosqlite==0.22.1", "ruff==0.17.6", "mypy==2.4.1"]
# httpx2 drives the FastAPI app in tests (Starlette 1.10 deprecates httpx for TestClient/ASGITransport)

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.14"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["google.adk.*"]
implicit_reexport = true   # google.adk.tools builds __all__ dynamically; strict mode otherwise rejects its imports

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

Pin `google-genai` to the 2.x line ADK accepts: `google-adk==2.15.1` declares `google-genai>=2.34,<3` and `websockets>=15.0.1,<16` in its PyPI `requires_dist` (uv resolves websockets 15.0.1; a project-wide websockets 17 pin conflicts), so a service that also wants genai 3.x for direct Gemini calls must run that code in a separate environment (`uv lock` is unsatisfiable otherwise, executed). Fill `<pin>` with the versions `uv lock` resolves and you have tested (2.15.0 resolved fastapi 0.165.0, starlette 1.10.0, pydantic 2.14.4, opentelemetry 1.45.2 on Python 3.14.10). Verify `uv sync --locked` on your target Python before adopting a new interpreter. Supply-chain gates (lock check, audit): `deployment-ci-cd/reference/python-ci-supply-chain.md`.

## 2. Environment and auth per environment

| Environment | Model endpoint | Credentials |
|---|---|---|
| local | developer API (Google AI Studio) or Vertex | `GOOGLE_API_KEY` in a local, git-ignored `.env` — or ADC via `gcloud auth application-default login` |
| test / CI | none — scripted fake model (`adk-testing.md`) | none |
| staging / production | Vertex AI (`GOOGLE_GENAI_USE_ENTERPRISE=true`; the older `GOOGLE_GENAI_USE_VERTEXAI` is deprecated but still read) | workload identity / ADC: **no API key exists**; startup fails if one is set |

```
# .env (local only, never committed)
ENVIRONMENT=local
AGENT_MODEL=<model id from the models page, verified on this endpoint>
GOOGLE_API_KEY=<local developer key>
SESSION_DB_URL=sqlite+aiosqlite:///./sessions.db
```

`google-genai` reads `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from the **process environment**; pydantic-settings reading `.env` does not export them. Locally, load `.env` into the process (`uv run --env-file .env ...`) instead of copying secrets into `os.environ` in code. A model id proven on the developer endpoint is not proven on Vertex: probe each backend before changing it (`gemini-api-dev` skill).

## 3. Settings (fail fast, auth matrix enforced)

Executed: production + key → rejected; production with ADC + project/location → accepted; local without key or Vertex → rejected; missing `AGENT_MODEL` → `ValidationError`. `mypy --strict` clean.

```python
# src/config.py
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "test", "staging", "production"]
    agent_model: str                              # no default: fail fast
    google_genai_use_vertexai: bool = False       # True => managed endpoint with ADC
    google_cloud_project: str | None = None
    google_cloud_location: str | None = None
    google_api_key: SecretStr | None = None       # developer key: local only
    session_db_url: SecretStr                     # contains credentials: never log
    agent_timeout_s: float = 30.0
    max_llm_calls: int = 20

    @model_validator(mode="after")
    def check_auth_matrix(self) -> Self:
        deployed = self.environment in ("staging", "production")
        vertex_ready = self.google_genai_use_vertexai and self.google_cloud_project and self.google_cloud_location
        if deployed and self.google_api_key is not None:
            raise ValueError("deployed environments authenticate keylessly (ADC); remove GOOGLE_API_KEY")
        if deployed and not vertex_ready:
            raise ValueError("deployed environments need GOOGLE_GENAI_USE_VERTEXAI=true, project and location")
        if self.environment == "local" and not self.google_genai_use_vertexai and self.google_api_key is None:
            raise ValueError("local developer endpoint needs GOOGLE_API_KEY (or use Vertex with ADC)")
        return self
```

Pass `settings.session_db_url.get_secret_value()` to `DatabaseSessionService`. Generic settings rules: `python-dev/reference/fastapi-architecture-and-config.md`, `deployment-ci-cd/reference/env-config-validation.md`.

## 4. Directory structure

```
my-adk-service/
+-- src/
|   +-- config.py
|   +-- main.py               # FastAPI lifespan: session service + Runner once
|   +-- agents/               # Agent definitions (model from settings)
|   +-- workflows/            # Workflow graphs (edges, JoinNode, nested) — adk-agent-types.md
|   +-- tools/                # Tool functions (typed result envelope)
|   +-- api/routes.py
+-- tests/
|   +-- fakellm.py            # scripted model (adk-testing.md §2)
+-- pyproject.toml
+-- uv.lock                   # committed
+-- Dockerfile
```

## 5. Dockerfile

Use the canonical multi-stage `uv` Dockerfile in `deployment-ci-cd/reference/python-ci-supply-chain.md` §8: uv image pinned by version and digest, `uv sync --locked --no-dev`, non-root user, no secrets in the image (no `ENV GOOGLE_API_KEY=...`, not even empty). Deployed services get model access through the runtime service account (ADC), other secrets from Secret Manager at runtime (`adk-deploy-guide`).

## 6. Logging

One logging stack: `deployment-ci-cd/reference/python-observability.md` §1 (structlog JSON, request-id middleware) and §2 (`log_exception(logger, event, exc, **ids)` — type and non-PII ids only). Never `error=str(e)`, `exc_info=True` or `logger.exception()` in agent code: model and validation errors echo user text. Never log prompts, model output, tool arguments or the session DB URL.

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info("tool_called", tool="get_order", session_id=session_id)
try:
    ...
except errors.APIError as exc:
    log_exception(logger, "model_call_failed", exc, session_id=session_id, status_code=exc.code)
    raise
```

## 7. Common commands

```bash
uv sync --locked                                     # install exactly the lock
uv run --env-file .env uvicorn src.main:app --reload # local dev server
adk web                                              # ADK dev UI (local only)
uv run pytest -q                                     # fake model; no network
uv run ruff check . && uv run mypy src/
```
