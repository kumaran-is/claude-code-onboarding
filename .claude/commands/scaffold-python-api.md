---
description: Scaffold a new Python 3.14 FastAPI service with uv, typed settings, async SQLAlchemy + Alembic, JWT auth, structlog, OpenTelemetry, tests, Docker and CI
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit
disable-model-invocation: true
---

# Scaffold Python FastAPI Service

**Project name:** $ARGUMENTS (default `my-python-api`). Package = the name with `-` → `_` (`orders-api` → `orders_api`).

For a FastAPI HTTP service only. Django, Flask, CLIs and workers are not converted to FastAPI (`/scaffold-python-worker`,
`python-dev` skill). Read `.claude/skills/python-dev/SKILL.md` first. The code templates live in its references (this
command lists files and gates, it does not repeat them): `fastapi-templates.md`, `fastapi-architecture-and-config.md`,
`fastapi-error-handling.md`, `fastapi-auth-security.md`, `alembic-migration-safety.md`; Docker and CI:
`.claude/skills/deployment-ci-cd/reference/python-ci-supply-chain.md` §7–8.

## 0. Toolchain (BLOCKED if missing, never substituted)

```bash
uv --version            # verified with 0.13.9; any uv that understands the lock works, CI pins the version
uv python find 3.14     # else: uv python install 3.14   (uv-managed; no brew, no global pip, no python -m venv)
docker --version        # Docker steps only; without it they are BLOCKED, the rest still runs
```

## 1. Project and pins

```bash
uv init --package --name <name> --python 3.14.10 --no-readme --vcs git <name> && cd <name>   # newest 3.14.x patch
```
- **Join an existing uv workspace** (do this instead of a nested `uv.lock` when the human is adding a service to a monorepo): `HOST=$(python3 .claude/skills/polyglot-monorepo/scripts/discover_monorepo.py --find-host <target parent>)` (exit 1 = no host). Then `python3 …/discover_monorepo.py --root "$HOST"`. If `join.uv` is true, create the package as a **member directory** (still `uv init --package` in that path). Append the path to `[tool.uv.workspace].members` **only if it is not already listed**. Add `[tool.uv.sources]` `{ workspace = true }` for shared libs, and `uv lock` + `uv sync --locked --all-packages` at the **host**. Do not write a member `uv.lock` unless `requires-python` cannot join the host (then keep it standalone — `uv-package-manager`). Do not add Nx. Details: `polyglot-monorepo/reference/discover-and-migrate.md`.
- `--python 3.14.10` pins the patch in `.python-version` (CI and the Docker base use the same patch) but also writes
  `requires-python = ">=3.14.10"`: relax it to `">=3.14"`. Delete the generated `[project.scripts]` entry (it points at a
  `main()` that will not exist).
- Append to the generated `.gitignore` before writing any other file: `.env *.pem *.key .DS_Store .mypy_cache/ .ruff_cache/ .pytest_cache/ .coverage`.
- `uv add` with exact `==` pins from the `fastapi-templates.md` pyproject template (runtime:
  `fastapi[standard-no-fastapi-cloud-cli]` (brings uvicorn[standard]), pydantic, pydantic-settings,
  `sqlalchemy[asyncio]` (greenlet only via the extra), asyncpg, alembic (≥ 1.20.1 with SQLAlchemy 2.1), structlog,
  `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` (never `opentelemetry-instrumentation-fastapi`), `pyjwt[crypto]` (add `pwdlib[argon2]` only when the service hashes passwords); `uv add --dev`: pytest, pytest-asyncio, pytest-cov, pytest-timeout, **httpx2** (Starlette 1.10's
  TestClient deprecates httpx; app-driving tests import `httpx2`), ruff, mypy, pip-audit). Never a floor (`>=`) or an
  unpinned name. Commit `uv.lock`.
- Tool config from the template: ruff `target-version = "py314"` with the `[tool.ruff.lint]` baseline (incl. `ASYNC`,
  `FAST`, `S`, `BLE`, `T20`, `RUF`, `DTZ`; `ignore = ["SIM105"]`); `[tool.mypy] strict = true`,
  `plugins = ["pydantic.mypy"]`, `files = ["src", "tests", "scripts", "migrations"]`; pytest `asyncio_mode = "auto"`,
  `asyncio_default_fixture_loop_scope = "function"` (a session-scoped async fixture declares `loop_scope="session"`),
  `filterwarnings = ["error"]` (also fails on Starlette's httpx deprecation), `timeout`, `--cov-fail-under`.
- No `from __future__ import annotations` (3.14 annotations are lazy already).

## 2. Files (one layout: `src/<package>/`; tests import `<package>.…`, never `src.<package>`)

| File | Must do |
|---|---|
| `core/config.py` | `Settings(BaseSettings)`: `env_prefix`, `frozen=True`, **`hide_input_in_errors=True`** (otherwise the boot traceback prints secret values); no defaults for secrets or environment-specific values; `SecretStr`; `get_settings()` logs failing field names only and re-raises; `forwarded_allow_ips` (`validation_alias="FORWARDED_ALLOW_IPS"`, uvicorn's own variable, default `127.0.0.1,::1`) rejects `*` so boot fails on a wildcard |
| `core/telemetry.py` | `is_probe(scope)` (health paths → no spans) and `build_tracer_provider(settings)`: resource `service.name`; a `BatchSpanProcessor(OTLPSpanExporter(...))` only when the optional OTLP endpoint setting is set (`python-observability.md` §3.2) |
| `core/logging.py` | structlog JSON to stdout + contextvars; the one `log_exception(logger, event, exc, **ids)` (error type, never `str(exc)`) |
| `core/exceptions.py`, `core/exception_handlers.py` | The flat envelope of `fastapi-error-handling.md` §2 (`{code, message, details, timestamp, path, requestId}`, `code` is `HTTP_<status>` for HTTP errors incl. 401/403, UPPER_SNAKE only for a domain error class) for domain errors, router 404/405, 422 (`loc`/`msg`/`type` only, never `input`), HTTP errors and a catch-all 500 that logs via `log_exception` and sets `X-Request-ID`; register with `@app.exception_handler(...)` inside `register_exception_handlers(app)` |
| `core/security.py` | Token verification exactly as `fastapi-auth-security.md`: algorithms pinned, `exp`/`iat`/`iss`/`aud`/`sub` required, `type == "access"`, any failure → 401 with `WWW-Authenticate` |
| `models/db/base.py` | `class Base(MappedAsDataclass, DeclarativeBase)`: typed `__init__`, so mypy catches a wrong constructor argument; `init=False` on PK/server-default columns |
| `models/`, `repositories/`, `services/` | Request models `extra="forbid"`; bounded pagination (`page_size` ≤ 100); repository flushes only; the service owns the commit; owner comes from the verified principal; another owner's id → 404 |
| `api/deps.py`, `api/routes/` | `Annotated` aliases (`SessionDep`, `PrincipalDep`, `<X>ServiceDep`); EVERY route except `/health/*` takes `PrincipalDep` and its service scopes by the principal (copy no unauthenticated route from a template); no session in a route; static paths before `/{id}` siblings; `GET /health/live` (no dependencies) and `GET /health/ready` (`SELECT 1` through `app.state.session_factory`, 2 s timeout, 503 with `{"checks": {"database": "error"}}`) as in `.claude/skills/deployment-ci-cd/reference/health-endpoints.md` |
| `main.py` | `create_app(settings: Settings \| None = None)` as in `fastapi-templates.md`: `App(FastAPI)` (in `core/request_id.py`) whose `__call__` wraps the pure-ASGI request-id middleware (inbound id accepted only if it is a UUID, else minted; `python-observability.md` §4); `max_body_size=settings.max_body_bytes` (default 1 MiB, 413 above it); `create_app(settings, tracer_provider=None, logger_provider=None)` passes native `telemetry={"tracer_provider": provider, "logger_provider": logger_provider, "logs": False, "operation_spans": False, "exclude": is_probe}` (`logs=True` records `exception.message`, i.e. request data); the lifespan `finally` calls `provider.force_flush()` and shuts down only a provider it built; `lifespan` only (engine + `app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)`, dispose in `finally`); NO module-level `app`; run `uvicorn <package>.main:create_app --factory` |
| `scripts/export_openapi.py` | Writes `openapi.json` (sorted keys); `--check` exits 1 when the committed snapshot is stale |
| `tests/` | `conftest.py`: isolated app per test via `create_app(Settings(_env_file=None, ...))` under `app.router.lifespan_context`; DB tests need `<PREFIX>_TEST_DATABASE_URL` and `pytest.fail` (BLOCKED) without it, never skip. Tests: live; request id; ready 503 (unreachable DB) and 200; create/get; list scoped + `page_size=101` → 422; unknown field → 422 without echoing the value; invalid value → 422; other owner → 404; `/stats` route order; unhandled → 500 envelope; router 404 → same envelope; missing token, `Basic` scheme, wrong key, `none`, other HMAC alg, expired, no `exp`, wrong `aud`/`iss`, missing `sub`, `type` ≠ `access` → 401; every non-`/health/*` operation in `/openapi.json` → 401 without a token; body over the limit → 413; telemetry with an in-memory exporter: probes + one 401 request give exactly one SERVER span (scope `fastapi`, `http.route` set), a 60 s `BatchSpanProcessor` span is exported by lifespan exit, and a route raising with a secret in its message leaves no log record containing it (in-memory `LoggerProvider`); `X-Forwarded-For` honoured only from a trusted peer (uvicorn's `ProxyHeadersMiddleware` with the setting, `ASGITransport(client=...)` as proxy and as outsider) and `FORWARDED_ALLOW_IPS=*` fails boot; boot contract (missing settings name fields, secret not in the exception text) |
| `.env.example`, `.dockerignore` | Placeholders only; `.dockerignore` excludes `.venv`, `.env`, `.git`, caches, `tests` |

## 3. Migrations (Alembic, config in pyproject)

```bash
uv run --no-sync alembic init -t pyproject_async migrations && rm alembic.ini   # keeps [tool.alembic] in pyproject.toml
```
- `migrations/env.py` = the runner in `alembic-migration-safety.md` §1 (lock timeout, `transaction_per_migration`,
  `compare_type`, NullPool, URL from `<PREFIX>_DATABASE_URL` with no default and an explicit driver (`postgresql+asyncpg://`;
  SQLAlchemy 2.1 maps a bare `postgresql://` to psycopg 3); import every model module).
- `script.py.mako`: `from collections.abc import Sequence`, `str | Sequence[str] | None`, no blank line between the
  `${imports ...}` line and `# revision identifiers` (it renders empty, and the extra line fails ruff I001), and add
  `[[tool.alembic.post_write_hooks]]` `name = "ruff_format"`, `type = "module"`, `module = "ruff"`,
  `options = "format REVISION_SCRIPT_FILENAME"`.
- First revision: `uv run --no-sync alembic revision --autogenerate -m "create <table>"` against an EMPTY database; read it
  (CHECK constraints and naming: `alembic-migration-safety.md`). Migrations run as a one-shot job with the service image
  before rollout, never from the app's startup.

## 4. Docker and CI

- `Dockerfile` = `python-ci-supply-chain.md` §8: digest-pinned `ghcr.io/astral-sh/uv` and `python:3.14.x-slim-trixie`
  (resolve with `docker buildx imagetools inspect <image:tag>`, never from memory), `UV_NO_BUILD=1`, `uv sync --locked
  --no-editable` in the build stage, root-owned `.venv` in the runtime stage, uid 10001, exec-form `uvicorn ... --factory
  --timeout-graceful-shutdown 8`, `HEALTHCHECK` on `/health/live`. Also `COPY pyproject.toml` and `migrations/` into the runtime stage so the same image runs `alembic upgrade head`; drop
  §8's `README.md` from the `COPY` (`uv init --no-readme` creates none). No `--forwarded-allow-ips` in the CMD: unset,
  uvicorn trusts only `127.0.0.1,::1` and ignores `X-Forwarded-For`. Set `FORWARDED_ALLOW_IPS` to your load balancer's
  address range per deployment, and check what `request.client.host` shows behind your platform before keying on it.
  **Workspace member:** build from the **host** context (`docker build -f <member>/Dockerfile <host>`). Install with
  `uv sync --locked --package <member>` (playbook §6); do not `COPY` a nested `uv.lock`. Standalone services keep §8 as written.
- `.github/workflows/ci.yml` = §7 (actions pinned by commit SHA, `setup-uv` with an explicit `version`, `UV_LOCKED=1`)
  plus a digest-pinned `postgres` service, `scripts/export_openapi.py --check`, the migration gate (one head, upgrade,
  downgrade -1, upgrade, `alembic check`) as one command per step, `pip-audit` on the exported lock, `docker build`.

## 5. Verify (report each PASS | FAIL | BLOCKED | NOT RUN with its command and own exit code)

Run the `/verify` Python block (`MODE=pre-pr`): lock check, `uv sync --locked`, ruff, format, mypy, pytest (with a
database), executed-test count, export + pip-audit, `alembic check`. Then:

```bash
uv run --no-sync python scripts/export_openapi.py --check; echo "OPENAPI EXIT:$?"
# migration gate on an empty database: alembic-migration-safety.md §7 (one command per line)
docker build -t <name>:local . > /tmp/build.log 2>&1; echo "BUILD EXIT:$?"
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges:true -e <PREFIX>_DATABASE_URL=... <name>:local alembic upgrade head; echo "MIGRATE EXIT:$?"
docker run -d --name <name>-smoke --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true -p 127.0.0.1:<port>:8080 --env-file .env <name>:local
curl -fsS http://127.0.0.1:<port>/health/ready; echo "READY EXIT:$?"
docker stop <name>-smoke; echo "STOP EXIT:$?"; echo "APP EXIT:$(docker inspect -f '{{.State.ExitCode}}' <name>-smoke)"
docker logs <name>-smoke 2>&1 | grep -c '"event": "shutdown"'; docker rm <name>-smoke
# PASS = the lifespan shutdown line is logged AND APP EXIT is 0 (exec-form uvicorn as PID 1 ignores its own re-raised
# SIGTERM, checked) or 143 (host, --init/tini, shared PID namespace, checked); 137 or no shutdown line = FAIL
```

Negative controls before calling it done (each must make its gate FAIL, then restore): token check bypassed → pytest;
JWT algorithm list widened → pytest; `type` check removed → pytest; `max_body_size` removed → pytest; telemetry `exclude` removed, `operation_spans` on, `force_flush` removed, provider not passed, `logs: True` → pytest; owner filter removed → pytest; a route without `PrincipalDep` (placed before `/{id}`) → pytest; 422 that returns `input` → pytest; `str` into an
`int` model field → mypy; `print()` + unused import → ruff; model column without a revision → `alembic check`;
`hide_input_in_errors` removed → pytest; `*` guard removed, `validation_alias` removed, `ProxyHeadersMiddleware(trusted_hosts="*")` → pytest. A run with no database is BLOCKED for the DB tests, not PASS.

Print the created files and next steps: set real secrets via the platform's secret manager, add the first real
resource, `/scaffold-alembic-migration` for schema changes, `/verify pre-pr` before every PR.
