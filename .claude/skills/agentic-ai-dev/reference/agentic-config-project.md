# Agentic AI Project Configuration

## pyproject.toml

**File:** `pyproject.toml`

```toml
[project]
name = "my-agent-service"
version = "0.1.0"
description = "Production AI agent service"
requires-python = ">=3.14"
dependencies = [
    # Agent stack: exact pins, upgraded together. langchain 1.5.2 needs langgraph>=1.2.12,<1.3; langgraph 1.2.24 needs
    # langgraph-prebuilt>=1.1.3,<1.2 (prebuilt has its own version line since 1.1).
    # This set was locked and installed together on Python 3.14.10 (uv lock + uv sync --locked exit 0) and its
    # checkpointer, store, HITL and limit paths were exercised with a scripted model; see agentic-testing.md.
    "langchain==1.5.2",
    "langchain-core==1.8.4",
    "langgraph==1.2.24",
    "langgraph-prebuilt==1.1.3",
    "langgraph-checkpoint==4.3.2",
    "langgraph-checkpoint-postgres==3.2.1",
    "psycopg[binary,pool]==3.3.9",
    # Provider integration(s) you use, pinned to the version in uv.lock, e.g. "langchain-anthropic==<x.y.z>"

    # API
    "fastapi[standard-no-fastapi-cloud-cli]==0.165.0",  # standard extras without fastapi-cloud-cli
    "pydantic==2.14.4",
    "pydantic-settings==2.16.3",
    "uvicorn[standard]==0.54.0",

    # Observability
    "langsmith==0.16.1",
    "structlog==26.1.0",
    "prometheus-client",          # exact version comes from uv.lock
    "httpx==0.28.1",             # outbound HTTP clients
]

[dependency-groups]
dev = [
    "pytest==9.2.0",
    "pytest-asyncio==1.5.0",
    "httpx2==2.16.2",            # drives the app in tests (ASGITransport); Starlette 1.10 deprecates httpx there
    "ruff==0.17.6",
    "mypy==2.4.1",
]

# Reproducibility: commit uv.lock; CI and Docker run `uv sync --locked` (fails if the lock is stale).
# Upgrade deliberately: `uv lock --upgrade-package langgraph --upgrade-package langgraph-prebuilt`,
# then run the full test suite and the live golden gate before merging.

[tool.ruff]
target-version = "py314"
line-length = 120
src = ["src"]

[tool.ruff.lint]
# The Python backend select (python-dev/reference/fastapi-architecture-and-config.md) plus W and C4.
# This is the config behind every "ruff clean" claim in agentic-ai-dev references (line-length 120).
# No TC/TCH: FastAPI, Pydantic and LangChain resolve annotations at runtime, so moving imports into
# TYPE_CHECKING blocks breaks them.
select = ["E", "W", "F", "I", "N", "UP", "B", "C4", "SIM", "RUF", "ASYNC", "FAST", "S", "BLE", "T20", "DTZ"]
ignore = ["SIM105"]      # it rewrites try/except/pass into contextlib.suppress, hiding the swallowed error

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]

[tool.ruff.lint.isort]
known-first-party = ["my_agent_service"]
section-order = ["future", "standard-library", "third-party", "first-party", "local-folder"]

[tool.mypy]
python_version = "3.14"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"   # PostgreSQL fixtures are session-scoped (python-testing-patterns/reference/postgres-integration-testing.md)
asyncio_default_test_loop_scope = "session"      # tests must share that loop
testpaths = ["tests"]
```

## Environment Configuration

**File:** `.env.example`

```bash
# === LLM Providers ===
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

# === LangSmith Observability ===
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=my-agent-service
LANGSMITH_TRACING=true

# === Database ===
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/agents
CHECKPOINT_DB_URI=postgresql://postgres:postgres@localhost:5432/agents

# === Vector Store ===
# CHROMA_HOST=localhost
# CHROMA_PORT=8000
# PINECONE_API_KEY=...

# === Redis (optional caching) ===
REDIS_URL=redis://localhost:6379/0

# === Application ===
APP_NAME=my-agent-service
APP_ENV=development
LOG_LEVEL=info
CHAT_MODEL=<provider>:<model-id>      # required; probe each environment before changing
MAX_GRAPH_STEPS=12                    # LangGraph recursion_limit (library default is 10000)
AGENT_TIMEOUT_S=30
MAX_MODEL_CALLS=8
MAX_TOOL_CALLS=20
```

## Configuration Module

**File:** `src/<service>/core/config.py`

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with fail-fast validation.

    All required fields MUST be set via environment variables or .env file.
    Missing values cause immediate startup failure — no silent defaults for secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- LLM Providers (only the ones you use; SecretStr keeps them out of reprs/logs) ---
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None

    # --- LangSmith ---
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "my-agent-service"
    langsmith_tracing: bool = True

    # --- Database ---
    database_url: str
    checkpoint_db_uri: str

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Application ---
    app_name: str = "my-agent-service"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    chat_model: str                              # required, no code default (model ids live in config)
    chat_model_params: dict[str, Any] = {}       # provider-specific sampling/reasoning; no global temperature
    max_graph_steps: int = Field(default=12, ge=2, le=200)
    agent_timeout_s: float = Field(default=30, gt=0)
    max_model_calls: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def provider_key_present(self) -> Settings:
        provider = self.chat_model.split(":", 1)[0]
        keys = {"anthropic": self.anthropic_api_key, "openai": self.openai_api_key, "google_genai": self.google_api_key}
        if provider in keys and keys[provider] is None:
            raise ValueError(f"API key for provider '{provider}' is not configured")
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or "://" not in v:
            raise ValueError("DATABASE_URL must be a valid connection string")
        return v

    @field_validator("checkpoint_db_uri")
    @classmethod
    def validate_checkpoint_uri(cls, v: str) -> str:
        if not v or "://" not in v:
            raise ValueError("CHECKPOINT_DB_URI must be a valid connection string")
        return v


# Singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
```

## Structured Logging

**File:** `src/<service>/core/logging.py`

```python
from __future__ import annotations

import logging
import sys

import structlog

from .config import settings


def setup_logging() -> None:
    """Configure structlog with JSON output and correlation ID support."""

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.app_env == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named logger with correlation ID support."""
    return structlog.get_logger(name)
```

## Exception Hierarchy

**File:** `src/<service>/core/exceptions.py`

```python
from __future__ import annotations


class AgentServiceError(Exception):
    """Base exception for all agent service errors."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class AgentError(AgentServiceError):
    """Error during agent graph execution."""


class ToolError(AgentServiceError):
    """Error during tool execution."""


class LLMProviderError(AgentServiceError):
    """Error from LLM provider (rate limit, auth, timeout)."""


class GuardrailError(AgentServiceError):
    """Input or output failed guardrail validation."""


class RAGError(AgentServiceError):
    """Error during RAG retrieval or indexing."""


class MemoryError(AgentServiceError):
    """Error accessing memory store."""


class ConfigurationError(AgentServiceError):
    """Missing or invalid configuration."""
```

## Docker Configuration

**File:** `Dockerfile`

```dockerfile
# --- Build stage ---
FROM python:3.14-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --locked

COPY src/ src/

# --- Runtime stage ---
FROM python:3.14-slim AS runtime

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Use gunicorn with uvicorn workers for production
# uvicorn.workers.UvicornWorker is deprecated: install the `uvicorn-worker` package and use its class
# (see docker/reference/dockerfiles.md); for a single process per container, run uvicorn --factory instead
CMD ["gunicorn", "my_agent_service.main:create_app()", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
```

**File:** `docker-compose.dev.yml`

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: agents
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```
