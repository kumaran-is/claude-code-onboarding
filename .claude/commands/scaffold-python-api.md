---
description: Scaffold a new Python 3.14 FastAPI project with Pydantic, async SQLAlchemy, and proper structure
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Python FastAPI Service

Create a new Python 3.14 / FastAPI project with the following:

**Project name:** $ARGUMENTS (default to "my-python-api" if not provided)

Read `.claude/skills/python-dev/SKILL.md` first; the templates, versions and reasoning are in
`reference/fastapi-templates.md` and `reference/fastapi-architecture-and-config.md`.

## Steps
1. **Create `.gitignore` first** — before any other file. Include: `__pycache__/`, `.env`, `*.pem`, `*.key`, `.venv/`, `dist/`, `*.egg-info/`, `.DS_Store`, `.mypy_cache/`, `.ruff_cache/`
2. Initialize with `uv init` and write `pyproject.toml` from the template: exact pins, dependency groups (runtime `structlog`, `tenacity`; dev `pytest-timeout`, `asgi-lifespan`, `pip-audit`), `[tool.ruff.lint]` baseline exactly as the template (`select` incl. `ASYNC`, `FAST`, `S`, `BLE`, `T20`, `RUF`, `DTZ`; `ignore = ["SIM105"]`), `[tool.mypy] strict = true` with `plugins = ["pydantic.mypy"]`, pytest `asyncio_mode = "auto"` with fixture and test loop scopes both `"session"` and `pythonpath = ["src"]`. Commit `uv.lock` (`uv lock`); no `python -m venv`/bare `pip` workflow
3. Create folder structure (one layout everywhere: `src/<package>/`; tests import `<package>.main`, never `src.<package>` or an `app/` package): `src/<package>/api/routes/`, `models/`, `models/db/`, `services/`, `repositories/`, `core/`, `middleware/`
4. Create `core/config.py`: fail-fast `Settings` (no defaults for secrets or environment-specific values, `SecretStr`, loader that prints field names only) and `.env.example`
5. Create `main.py` with `create_app(settings)`: `lifespan` only (no `on_startup`/`on_event`), exception handlers, request-id middleware (`python-observability.md`), router includes. NO module-level `app = create_app()`: run `uvicorn <package>.main:create_app --factory`
6. Create `core/exceptions.py` + `core/exception_handlers.py`: one error envelope for domain errors, 422 (without echoing `input`), HTTP errors and a catch-all 500, each carrying `requestId`; the one `log_exception` helper from `python-observability.md` (structlog, error type, never `str(exc)`); the catch-all logs `request.state.request_id` and sets `X-Request-ID`
7. Create a sample request model (`extra="forbid"`) and response model, a pagination model with bounded `page`/`page_size`
8. Create a sample route (`Annotated` dependencies, no session in the route), service (owns the commit), and repository (flush only)
9. Add `GET /api/v1/health` (liveness, no dependencies) and `GET /api/v1/ready` (checks the database)
10. Create `tests/conftest.py` with an isolated-app fixture (`create_app(Settings(_env_file=None, ...))`, lifespan run explicitly) and a boot-contract test for `Settings`
11. Add pytest tests: happy path, 422 (unknown field and invalid value), domain error envelope, and a route-order test
12. Add a script that writes the OpenAPI document to a committed snapshot file (regenerate it in the same change as any route/model change)
13. Create a `Dockerfile` (non-root, pinned base, `COPY --from=ghcr.io/astral-sh/uv:<version>` never `pip install uv`, `uv sync --locked --no-dev`, `--factory` CMD) — see `.claude/skills/docker/`
14. Run `ruff check`, `ruff format --check`, `mypy` (strict via pyproject), `pytest`; run the dependency audit per `.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md` (`pip-audit`, not `pip audit`) and fix or document findings
15. Print summary of created files and next steps. Report each check as PASS | FAIL | BLOCKED | NOT RUN with the command and exit code

Use the python-dev skill for patterns and templates.
