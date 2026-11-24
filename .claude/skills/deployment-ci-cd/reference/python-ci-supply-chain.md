# Python CI Gates and Supply Chain

Canonical reference for Python CI gate design, build-input pinning, locked installs and dependency auditing. Commands below were executed with uv 0.11.3 and re-run on uv 0.13.9 / CPython 3.14.10 (sections 1, 3, 7 and 8, 2026-11-23), pip-audit 2.10.1, actionlint 1.7.12 and gcloud 560 unless marked "verify".

## 1. Dependency audit: canonical commands

`pip-audit` reports name, version, advisory ID and fix versions. It prints NO severity, so `pip-audit | grep -E "CRITICAL|HIGH"` matches nothing and is a permanent false green (executed: 10 findings on one pinned old package, severity grep count 0, exit 1). `pip audit` is not a command (executed with pip 26.3: `ERROR: unknown command "audit"`).

```bash
uv lock --check; echo "LOCK EXIT:$?"
uv export --locked --no-dev --no-hashes --no-emit-project -o requirements.audit.txt; echo "EXPORT EXIT:$?"
uv run pip-audit -r requirements.audit.txt --no-deps --disable-pip > audit.log 2>&1; echo "AUDIT EXIT:$?"; tail -20 audit.log
```

| Exit | Meaning | Gate status |
|------|---------|-------------|
| 0 | No known vulnerabilities in the audited set | PASS |
| 1 | One or more findings (executed) | FAIL, unless every ID is on the accepted list |
| 2 | Usage error (executed: an invalid flag combination exits 2); collection/network failures: verify the exit code on your version | BLOCKED, never PASS |

- Gate on the exit code. Accept a known finding explicitly with `--ignore-vuln <ID>` (executed: ignoring all 5 IDs of a package gave exit 0) and record the reason and an expiry next to the ID. Never delete the audit step to get green.
- `--no-deps --disable-pip` audits exactly the exported lock set instead of re-resolving; pip-audit warns that unhashed `--no-deps` input is less strict (use `uv export` without `--no-hashes` plus `--require-hashes` when you need that).
- `pip-audit --locked` only works with a project path argument (executed: `--locked` combined with `-r` was rejected with "can only be used with a project path"); prefer the explicit export above unless you verify your lock format is supported.
- `uv audit` exists in uv 0.13 but is experimental (executed: `uv audit --preview-features audit-command` reported the same findings and printed a preview warning). Keep the pip-audit gate until it is stable.
- Need severity (CVSS) prioritisation? Use a severity-aware scanner (or read each advisory) and say which one; do not simulate severity by grepping.
- Also audit the container base image (Trivy/Grype/`docker scout`), because OS packages are not in the Python lock.
- A zero-finding scan is evidence only after a positive control: a known-vulnerable pin must make the same command exit 1 (keep one in the gate's selftest or a scheduled job).

## 2. Locked installs

| Command | Stale lock behaviour (executed) | Use |
|---------|---------------------------------|-----|
| `uv sync --locked` | exit 1: refuses when `pyproject.toml` and `uv.lock` disagree | CI, Docker builds (default) |
| `uv sync --frozen` | exit 0: installs the stale lock without checking it | avoid; acceptable only where `pyproject.toml` is unavailable AND a later `--locked` step re-checks (the Dockerfile in section 8 bind-mounts both files and uses `--locked` throughout) |
| `uv lock --check` | exit 1 on a stale lock | pre-commit and CI, no install needed |

- A dependency change is not done until the lock is regenerated and committed in the same change.
- Never `pip install uv`, never a hand-copied `>=` dependency list inside a Dockerfile: the image drifts from the lock (an instrumentation library silently became a no-op that way, section 6).
- Monorepo/workspace: plain `uv sync` skips workspace members; use `uv sync --all-packages --locked`. Run pytest with the root config (`-c pyproject.toml`), `--import-mode=importlib`, one process per deployable package.
- Pin the interpreter the gate needs: commit `.python-version`, run `uv python install` (runner images ship their own Python), and fail with a message naming the cause when `sys.version_info` is below the project's `requires-python`.

## 3. Pin every third-party build input by content

| Input | Pin | Resolve |
|-------|-----|---------|
| GitHub Action | 40-hex commit SHA + `# vX.Y.Z` comment | `git ls-remote https://github.com/<owner>/<repo> 'refs/tags/<tag>' 'refs/tags/<tag>^{}'` (the `^{}` line is the commit for annotated tags; executed for `actions/checkout`) |
| Base image | `image:tag@sha256:<digest>` | `docker buildx imagetools inspect python:3.14-slim` prints the multi-arch INDEX digest (executed); pin that, not a per-platform digest |
| Tool binary image (uv) | `FROM ghcr.io/astral-sh/uv:<x.y.z>@sha256:<digest> AS uv` then `COPY --from=uv /uv /uvx /bin/` (uv Docker guide) | same command |
| Tool in CI | explicit version (`setup-uv` `version:`) | read the release page |
| Runner | `ubuntu-24.04`, not `-latest` | |
| `# syntax=` line | pinned frontend image | |
| Scanner action/image | never `latest`; a scanner step that fails to RUN must fail the job | |

A mutable tag can be re-pointed after review (tag hijack of a CI action is a known supply-chain pattern); a SHA cannot. Enable update tooling (Dependabot/Renovate) for each pinned file type, otherwise pins rot silently. Replace `COPY --from=<image-ref>` with a pinned `FROM ... AS stage`.

Gate: `bash .claude/scripts/check-pins.sh <workflow and Dockerfile paths>` (copy it into a consuming repo's `scripts/`). Exit 0 clean, 1 violations with `file:line`, 2 when given no files (scanning nothing is a failure). `--selftest` covers a SHA-pinned and a local action (clean), a tag-pinned action, an undigested `FROM` and a `COPY --from=<image>` (flagged), and zero files (exit 2); the toolkit's own CI runs it on `.github/workflows/*.yml`.

Runs on macOS bash 3.2. Limit: a multi-stage `FROM builder AS runtime` (stage reference, no image) is flagged; allow-list it by name if you use it. Run `--selftest` in CI before the real scan.

## 4. Gate design rules

- **Positive control**: every zero-findings check ships a known-bad input it must flag, plus a "files scanned > 0" assertion.
- **Own exit code**: `cmd > log 2>&1; echo "EXIT:$?"; tail log`. `cmd | tail; echo $?` reports `tail` (executed: `false | tail; echo $?` prints 0). In zsh read `$pipestatus`, in bash `${PIPESTATUS[0]}`.
- **No `producer | grep -q` under `pipefail`**: `grep -q` exits early, the producer gets SIGPIPE, the pipeline reports failure on a match. Capture to a variable, then test it.
- **Executed count > 0**: a green run with everything skipped proves nothing (`postgres-integration-testing.md` section 9).
- **A sentinel proves the gate ran, not that every step passed**; do not write a success file after a swallowed sub-step failure.
- **Run on committed work**: a diff-aware check on uncommitted changes sees nothing and passes vacuously.
- **Ceilings only ratchet**: split goal (warns) from ceiling (fails); never raise a budget to get green.
- `actionlint` (it runs shellcheck on `run:` blocks when shellcheck is installed) over every workflow: an unparseable workflow fails the PR instead of failing later (executed: a typo `github.evnt.name` -> exit 1; the full example workflow below -> exit 0).
- More on authoring gate scripts/hooks: `.claude/rules/hook-and-gate-authoring.md`.

## 5. Path filters and required checks

- A path-filtered workflow that runs pytest lists EVERY file the run loads: sources, tests, root `conftest.py`, `pyproject.toml`, the lock, `.python-version`, the workflow itself. Anything omitted is a way to break CI without CI noticing; exempt a path only with a reasoned comment.
- A REQUIRED status check must not rely on trigger-level `paths:` filters: a workflow that never starts leaves the check pending forever. Use an always-run job that detects changes itself and reports success explicitly when nothing relevant changed, and fails on cancellation or unexpected skip.
- `pull_request`-only gates never run on the merge commit; add `push` on the default branch for gates that must hold there.
- Least privilege: `permissions: contents: read` at the top, widen per job; `persist-credentials: false` on checkout unless the job pushes; never `pull_request_target` with checkout of PR code.

## 6. Framework pin and instrumentation coupling

Pin the web framework EXACTLY (`==`) in every `pyproject.toml` and Dockerfile wherever an instrumentation library patches its internals (metrics/tracing instrumentors). A floor (`fastapi>=x`) drifts on rebuild; a new minor can change router internals and break the instrumentor at import or on `/health`. Take upgrades deliberately: relock, run the span test (`python-observability.md` section 3), smoke-test the health endpoint.

Executed demonstration of the silent-no-op failure class: with SQLAlchemy 2.1.9 installed, `SQLAlchemyInstrumentor().instrument(...)` logged "only instruments sqlalchemy >= 1.0.0, < 2.1.0 ... nothing can be instrumented" and produced no database span while every functional test stayed green. Downgrading to 2.0.58 produced the span. The installed instrumentation packages also declare their supported ranges (`fastapi~=0.92` for the FastAPI instrumentor, `sqlalchemy<2.1.0,>=1.0.0` for the SQLAlchemy one at the versions installed here). A test that asserts the spans exist is the only reliable guard. Template pairing: `sqlalchemy==2.0.x` with a one-line comment that DB-span instrumentation currently supports `< 2.1`; this is a limit of the instrumentation release pinned today, not a verdict on SQLAlchemy 2.1.

Gate idea: grep every `pyproject.toml` and Dockerfile for `fastapi` specs that do not match `==` (include a known-bad control).

## 7. Example workflow (actionlint exit 0)

Every pin below was resolved on 2026-11-23: action SHAs with `git ls-remote` (both tags are non-prerelease releases), the Postgres INDEX digest with `docker buildx imagetools inspect postgres:18.7-trixie`. Executed: actionlint 1.7.12 exit 0 (a planted `github.reff` typo exits 1); `check-pins.sh` (section 3) exit 0; every `run:` step replayed locally against a uv 0.13.9 project, each exit 0. `setup-uv` caches keyed on `**/uv.lock` and `**/pyproject.toml` by default; `prune-cache` defaults to `false` in v10.

```yaml
name: python-ci

on:
  pull_request:
    paths:                       # EVERY file the test run loads
      - "src/**"
      - "tests/**"
      - "conftest.py"
      - "pyproject.toml"
      - "uv.lock"
      - ".python-version"
      - ".github/workflows/python-ci.yml"
  push:
    branches: [main]             # a pull_request-only gate never runs on the merge commit

permissions:
  contents: read

concurrency:
  group: python-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    services:
      postgres:
        image: postgres:18.7-trixie@sha256:f5cbc081c25690710f3fc6f4c61a7565382bae01ca0d0f2028a53d7926b85a20
        env:
          POSTGRES_PASSWORD: ${{ secrets.TEST_DB_PASSWORD }}
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      REQUIRE_DB_TESTS: "1"
      TEST_DATABASE_URL: postgresql+asyncpg://postgres:${{ secrets.TEST_DB_PASSWORD }}@localhost:5432/postgres
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
        with:
          version: "0.13.9"
          enable-cache: true
      - run: uv python install       # reads .python-version
      - run: uv lock --check
      - run: uv sync --locked --no-build
      - name: Lint and types
        run: |
          uv run ruff check .
          uv run ruff format --check .
          uv run mypy src tests
      - name: Tests (own exit code, then executed-count gate)
        run: |
          set +e
          uv run pytest -q --junitxml=junit.xml > pytest.log 2>&1
          code=$?
          tail -30 pytest.log
          [ "$code" -eq 0 ] || exit "$code"
          uv run python scripts/check_executed.py junit.xml 0
      - name: Dependency audit
        run: |
          uv export --locked --no-dev --no-hashes --no-emit-project -o requirements.audit.txt
          uv run pip-audit -r requirements.audit.txt --no-deps --disable-pip
```

- `uv sync --locked --no-build`: a dependency without a wheel for the runner fails the job instead of compiling an sdist (the local project is still built).
- `scripts/check_executed.py` is the executed-count gate (`python-dev/reference/backend-live-e2e-standard.md`): a run that collected zero tests must not pass.

Add `pip-audit` and every plugin/library the gates use (`pytest-timeout`, `httpx2` for app-driving tests (Starlette 1.10 `TestClient` imports it first and warns with `StarletteDeprecationWarning` when only httpx is present; keep `filterwarnings = ["error"]` so that warning fails the suite), `structlog`, `tenacity` where the references' snippets are adopted) to the project's dependency groups so `uv sync --locked` installs them from the lock. Do not test a matrix of old Pythons for a service pinned to one (`requires-python`); test the interpreter you deploy.

## 8. Dockerfile for a uv project

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
# Use the image's Python (a uv-downloaded one would not exist in the runtime stage);
# compile bytecode at build time because the runtime filesystem is read-only.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1 UV_NO_BUILD=1
# Dependencies layer: cached until the lock changes. UV_NO_BUILD: fail instead of compiling a third-party sdist.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --locked --no-install-project --no-editable
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src/ src/
# Project layer: non-editable, so only .venv is copied to the runtime stage.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=root:root /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).status == 200 else 1)"]
# Exec form: uvicorn is PID 1 and receives SIGTERM directly (graceful shutdown runs the lifespan exit).
CMD ["uvicorn", "my_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "8", "--no-access-log"]
```

Executed 2026-11-23 (uv 0.13.9, CPython 3.14.10, Docker Engine 29.8.0): `docker build --check .` 0; build 0 (263 MB); run with `--read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --memory 256m --pids-limit 128`: `/health/live` 200, uid 10001, a write to `/app` refused, `CapEff` 0, `NoNewPrivs` 1, `.cpython-314.pyc` files present, Docker health `healthy`, `docker stop` returned in under 1 s with exit 0 and the lifespan `shutdown_complete` log line. Controls: `sh -c "uvicorn ...; true"` (uvicorn not PID 1) made `docker stop` wait the full timeout and exit 137 with no shutdown log; a `sleep` CMD turned health `unhealthy`; a stale lock failed the `--locked` build step. `check-pins.sh` exits 0 on this file.

- Digests: INDEX digests from `docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.13.9` and `... python:3.14.10-slim-trixie` on that date (`python:3.14-slim` pointed at the same index). Re-resolve when you bump a tag and let Dependabot/Renovate update them. The patch tag matches `.python-version`.
- `UV_NO_DEV=1` replaces `--no-dev` on each command; `UV_NO_BUILD=1` fails the build when a third-party package has no wheel (the local project is still built); `UV_COMPILE_BYTECODE=1` because the read-only runtime cannot write bytecode later.
- The venv is copied `root:root`: the app user can run it, not modify it.
- Exec-form `CMD` makes uvicorn PID 1. When the platform injects `$PORT`, use `CMD ["sh", "-c", "exec uvicorn ... --port ${PORT:-8080}"]`; the `exec` is mandatory. Keep `--timeout-graceful-shutdown` below the platform's SIGKILL window (Cloud Run: 10 s).
- Exit code after SIGTERM (uvicorn 0.54.0, executed): after its graceful shutdown uvicorn restores the default handler and re-raises the signal (`Server.capture_signals` in `uvicorn/server.py`). As container PID 1 (exec-form `CMD`, `sh -c 'exec ...'`, `python -m uvicorn` or programmatic `uvicorn.run`) the kernel ignores that default-action signal, so the process exits 0 and `atexit` hooks run. On a host, under `docker run --init`/tini, or with a shared PID namespace it dies from the signal: exit 143 (`-15` from `subprocess`), and `atexit` does NOT run. A stop check passes on the lifespan shutdown log line PLUS exit 0 or 143; 137 or a missing log line is a failure. Flush telemetry and close clients in the lifespan `finally`, never in `atexit` or after `uvicorn.run()`.
- Comments sit on their own lines: a trailing `# ...` after an `ENV` line is parsed as more key/value words. The app is started with `--factory` (no module-level `app = create_app()`). `/uv /uvx /bin/`, `--no-editable` and `UV_PYTHON_DOWNLOADS=0` follow the uv Docker guide.
- Workspace member images (`--package <member>`): `uv-package-manager` playbook section 6.
- If the application is not an installable package (no `[build-system]`, or `tool.uv.package = false`), drop the second `uv sync` and `COPY` the source instead.
- The healthcheck uses the standard library, so it does not depend on `httpx`/`curl` being in the runtime image.
- Keep the Docker `HEALTHCHECK` on the LIVENESS path (process alive); the orchestrator's readiness/startup probes check dependencies (`health-endpoints.md`).
- `.dockerignore` as an ALLOW-list for the build context (`*` then `!src`, `!pyproject.toml`, `!uv.lock`): a deny-list admitted large unrelated directories into the context in one real repo. Verify the image file list is identical before and after.
- Configuration is never baked into the image (no `ENV` for env-varying values, no secrets in `ARG`); required settings have no code default so startup fails loudly (`env-config-validation.md`).
- Add a test that a lock-derived instrumentation package is not a no-op (`python-observability.md` section 3), and run the image scan on the final image.

## 9. Deploy and rollback hygiene (architecture-neutral)

- Deploy by immutable image digest or commit-SHA tag, never `latest`. Record the running digest/revision after each deploy.
- Order: migration job (non-zero aborts the whole release) -> APIs -> workers -> edge. Record a PARTIAL state if a mid-rollout step fails; move the "current" pointer only after verified reconciliation.
- Rollback is a traffic pin to the previous revision; "redeploy the old SHA" is unproven until rehearsed.
- Least-privilege test: no runtime identity holds a project-wide secret-accessor role; grants derive from what each service mounts; a `latest` secret version is a rollout risk to review.
- Every env var read by code and present in a deploy template must also be wired in the infrastructure code for each deployed service; a grep gate cannot see `BaseSettings` fields or computed names, so verify by hand with a control grep (known-present var count = 1).
- The first real apply of infrastructure-as-code finds what `validate` cannot (platform limits, tier defaults, name-length limits); pin each such platform rule with a test that fails when the fix is reverted.

## 10. Contract drift: snapshot and diff the OpenAPI document

Commit the generated OpenAPI document (`json.dump(app.openapi(), ...)`) and diff it from the CONSUMER's side in CI. Breaking: operation removed, response field removed, response field type changed or made nullable, request field became required, request/response enum value removed. NOT breaking: adding an optional field or a new operation. The script below checks the first three (executed, `mypy --strict` and ruff clean: identical documents exit 0; a modified document produced `operation removed: GET /gone`, `request field became required: POST /accounts.age`, `response field removed: GET /accounts 200 .email` and the same for POST, exit 1; every line names its method). It is a minimal checker (top-level `$ref` and `application/json` only): extend it for types/nullability/enums or use an established OpenAPI diff tool, and keep its known-bad fixture in CI.

```python
"""Compare two OpenAPI documents from the CONSUMER's side. usage: check_openapi_breaking.py old.json new.json"""
import json
import sys
from pathlib import Path
from typing import Any

Doc = dict[str, Any]
METHODS = {"get", "put", "post", "delete", "patch"}


def ops(doc: Doc) -> dict[tuple[str, str], Doc]:
    return {(m, p): o for p, item in doc.get("paths", {}).items() for m, o in item.items() if m in METHODS}


def resolve(doc: Doc, schema: Doc) -> Doc:
    ref = schema.get("$ref")
    return doc["components"]["schemas"][ref.rsplit("/", 1)[-1]] if ref else schema


def breaking(old: Doc, new: Doc) -> list[str]:
    out: list[str] = []
    o_ops, n_ops = ops(old), ops(new)
    for key in o_ops.keys() - n_ops.keys():
        out.append(f"operation removed: {key[0].upper()} {key[1]}")
    for key in o_ops.keys() & n_ops.keys():
        o_body = o_ops[key].get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
        n_body = n_ops[key].get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
        if o_body and n_body:
            o_req = set(resolve(old, o_body).get("required", []))
            n_req = set(resolve(new, n_body).get("required", []))
            out += [f"request field became required: {key[0].upper()} {key[1]}.{p}" for p in sorted(n_req - o_req)]
        for status, o_resp in o_ops[key].get("responses", {}).items():
            o_s = o_resp.get("content", {}).get("application/json", {}).get("schema")
            n_resp = n_ops[key].get("responses", {}).get(status, {})
            n_s = n_resp.get("content", {}).get("application/json", {}).get("schema")
            if o_s and n_s:
                o_p = set(resolve(old, o_s).get("properties", {}))
                n_p = set(resolve(new, n_s).get("properties", {}))
                out += [f"response field removed: {key[0].upper()} {key[1]} {status} .{p}" for p in sorted(o_p - n_p)]
    return sorted(out)


if __name__ == "__main__":
    found = breaking(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
    sys.stdout.write("".join(f"{line}\n" for line in found))
    sys.exit(1 if found else 0)
```
