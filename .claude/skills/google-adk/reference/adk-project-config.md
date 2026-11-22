# ADK Project Configuration

## 1. pyproject.toml — exact pins + lockfile

Pin `google-adk` exactly and commit `uv.lock`; CI and Docker install with `uv sync --locked` (refuses a stale lock). A `>=` range lets a fresh resolve pull a different ADK whose APIs differ from these references.

```toml
[project]
name = "my-adk-service"
version = "0.1.0"
requires-python = "==3.14.*"        # the interpreter you deploy; google-adk 1.29 declares >=3.10
dependencies = [
    "google-adk==1.29.0",
    "fastapi==<pin>",
    "uvicorn[standard]==<pin>",
    "pydantic-settings==<pin>",
    "structlog==<pin>",
    "sqlalchemy[asyncio]==<pin>",   # DatabaseSessionService needs the asyncio extra (greenlet)
    "asyncpg==<pin>",               # async Postgres driver for postgresql+asyncpg:// URLs
]

[dependency-groups]
dev = ["pytest==<pin>", "pytest-asyncio==<pin>", "httpx==<pin>", "aiosqlite==<pin>", "ruff==<pin>", "mypy==<pin>"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`google-adk` brings `google-genai`; do not add a second, looser `google-genai` constraint. Fill `<pin>` with the versions `uv lock` resolves and you have tested. Verify `uv sync --locked` on your target Python before adopting a new interpreter (the references here were executed on Python 3.12 with google-adk 1.29.0). Supply-chain gates (lock check, audit): `deployment-ci-cd/reference/python-ci-supply-chain.md`.

## 2. Environment and auth per environment

| Environment | Model endpoint | Credentials |
|---|---|---|
| local | developer API (Google AI Studio) or Vertex | `GOOGLE_API_KEY` in a local, git-ignored `.env` — or ADC via `gcloud auth application-default login` |
| test / CI | none — scripted fake model (`adk-testing.md`) | none |
| staging / production | Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`) | workload identity / ADC: **no API key exists**; startup fails if one is set |

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
