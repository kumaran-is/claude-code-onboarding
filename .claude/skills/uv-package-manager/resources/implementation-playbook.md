# uv Implementation Playbook

Validated 2026-11-23 with uv 0.13.9 (`uvx --from uv==0.13.9 uv`), uv-managed CPython 3.14.10 / 3.13.18 / 3.15.2, Docker Engine 29.8.0. "Executed" means the command ran with its own exit code shown; "docs" means uv's documentation for 0.13.9 (`docs/guides/integration/docker.md`, `docs/concepts/projects/workspaces.md`, `CHANGELOG.md`).

## 1. What changed since uv 0.11.x

| Version | Change | Action |
|---|---|---|
| 0.13.0 | Default stable Python is now **3.15**: with no `.python-version` / `--python`, `uv venv`, `uv python install` and project commands may download 3.15 (changelog). Executed: a project with no `requires-python` locked with "Defaulting to `>=3.15`" | Commit `.python-version` (`uv python pin 3.14.10`) and `requires-python = ">=3.14"` in every project |
| 0.13.0 | `uv_build` upper bound must allow 0.13 (`uv_build>=0.13.0,<0.14`); `uv init` writes `uv_build>=0.13.9,<0.14.0` (executed) | Bump `[build-system]` when you bump uv |
| 0.13.0 | `--require-hashes` honoured in included constraints files; editable requirements rejected in constraints; tar archives read by a stricter backend | Fix hashes/constraints files instead of opting out |
| 0.12.0 | `uv init` defines a build system by default; stable releases preferred before pre-releases; `--require-hashes` in `requirements.txt` honoured; MD5-only hashes rejected | Re-run `uv init` templates; expect stricter installs |
| 0.12.x | `uv audit` (OSV lookups over the lock) and `uv tool audit` added | Still **experimental** in 0.13.9 (warning printed): CI gate stays pip-audit (section 9) |
| 0.12+ | `uv format` (runs ruff's formatter) | Experimental in 0.13.9 (warning printed); keep `uv run ruff format` |

## 2. New project

```bash
uv init --package --python 3.14 my-service      # src/ layout, uv_build backend, .python-version
cd my-service
uv python pin 3.14.10                            # exact patch in .python-version; requires-python stays ">=3.14"
uv add "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "pydantic-settings==2.16.3"
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "ruff==0.17.6" "mypy==2.4.1" "pip-audit==2.10.1"
uv run pytest
```

- `uv init --python 3.14.10` writes `requires-python = ">=3.14.10"` (executed); relax it to `">=3.14"` and keep the patch only in `.python-version` and the Docker base tag.
- `fastapi[standard]` pulls fastapi-cloud-cli 0.28.0 and through it sentry-sdk 3.0.0 plus four more packages; `standard-no-fastapi-cloud-cli` removes those six (executed lock diff).
- Pin exact versions (`==`) for services; libraries you publish declare ranges and let the consumer's lock pin.

## 3. Dependencies

| Need | Command (all executed) | Lands in |
|---|---|---|
| Runtime dependency | `uv add "httpx==0.28.1"` | `[project] dependencies` |
| Dev tools | `uv add --dev "pytest==9.2.0"` | `[dependency-groups] dev` (PEP 735) |
| Another local-only group | `uv add --group lint "ruff==0.17.6"` | `[dependency-groups] lint` |
| Published optional feature | `uv add --optional pdf "pypdf==7.1.1"` | `[project.optional-dependencies] pdf` |
| Import a requirements file | `uv add -r requirements.txt` | `[project] dependencies` |
| Remove | `uv remove httpx` (`--package <member>` in a workspace) | |
| Install everything | `uv sync --locked --all-extras --all-groups` | |
| Only one group | `uv sync --locked --no-default-groups --group lint` | |

- `[tool.uv] dev-dependencies` is deprecated (executed: uv 0.13.9 warns "use `dependency-groups.dev` instead"). Move it to `[dependency-groups] dev`.
- Groups are local (never published); extras are part of the package's public metadata.
- `uv run --with <pkg> ...` adds a throwaway package for one command without touching the lock.

## 4. Lock and sync semantics

| Command | Behaviour (executed) | Use |
|---|---|---|
| `uv lock` | Resolves for every platform and Python in `requires-python`; never installs | After any dependency edit; commit `uv.lock` in the same change |
| `uv lock --check` | Exit 1 when `pyproject.toml` and `uv.lock` disagree | Pre-commit and the first CI step |
| `uv sync --locked` | Exit 1 on a stale lock, otherwise installs exactly the lock | CI, Docker (default) |
| `uv sync --frozen` | Installs the lock without checking it | Only the Docker deps layer when member `pyproject.toml` files are not mounted (workspaces, section 6), followed by a `--locked` sync |
| `uv sync --no-build` / `UV_NO_BUILD=1` | Refuses to compile any third-party sdist; the local project still builds | CI and Docker: a missing wheel fails fast instead of compiling (executed on 3.15: `grpcio==1.78.2 ... marked as --no-build but has no binary distribution`, exit 2) |
| `uv lock --upgrade-package httpx` / `uv lock --upgrade` | Moves one / all pins inside the declared ranges | Deliberate upgrades, then run the gates |
| `uv tree --outdated --depth 1` | Lists direct dependencies with newer releases | Upgrade review |
| `uv sync --locked --offline` | Installs from the cache only | Air-gapped rebuilds |

Resolver facts worth knowing:
- uv ignores the **upper** bound of a dependency's `Requires-Python`: presidio-analyzer 2.2.366 declares `<3.15` yet locked on 3.15 (executed). The upper bound will not protect you; your own `requires-python` and CI interpreter must.
- Conflicting pins surface as a readable derivation (executed: google-adk 2.15.0 requires `google-genai>=2.34,<3`, so pinning google-genai 3.6.1 next to it is unsatisfiable). Do not "fix" with overrides; choose versions that resolve.

## 5. Python versions

```bash
uv python list --only-installed
uv python install            # installs what .python-version names
uv python pin 3.14.10        # writes .python-version
uv run --python 3.15 pytest  # one-off run on another interpreter (forward-compat job)
```

- Variants: `3.14.10+freethreaded` (`python3.14t`) is a separate download; test it only in a dedicated job (`python-patterns` skill, runtime decision).
- `UV_PYTHON_DOWNLOADS=0` in Docker so uv uses the image's interpreter (a downloaded one would not exist in the runtime stage).

## 6. Workspaces (one lock, several packages)

Use a workspace when members share ONE Python and one dependency set: a shared library, a REST service, an AI service and a worker that deploy separately but must agree on contract versions.

```
platform/
├── pyproject.toml          # virtual root: [tool.uv.workspace] + [dependency-groups], no [project]
├── .python-version         # 3.14.10
├── uv.lock                 # the only lock
├── packages/shared/        # uv init --lib
└── services/{api,ai,worker}/   # uv init --package
```

```toml
# root pyproject.toml
[tool.uv.workspace]
members = ["packages/*", "services/*"]

[dependency-groups]
dev = ["pytest==9.2.0", "pytest-asyncio==1.5.0", "ruff==0.17.6", "mypy==2.4.1"]
```

```bash
uv add --package api shared "fastapi==0.165.0"   # writes shared = { workspace = true } under [tool.uv.sources]
uv lock
uv sync --locked --all-packages
uv run --package api pytest services/api/tests
uv build --package shared --out-dir dist
uv export --package api --no-dev --locked --format requirements.txt
```

Executed on this layout (4 members, 41 packages): lock 0, `sync --all-packages` 0, per-member pytest 0, ruff/format/mypy --strict 0, `uv build --package shared` 0 (wheel + sdist), `uv export --package api` listed only api's closure.

| Fact (executed) | Consequence |
|---|---|
| Virtual root (no `[project]`): plain `uv sync` installed every member | Fine locally; CI still uses `--all-packages` to state intent |
| Root WITH `[project]`: plain `uv sync` did NOT install members (`import api` failed) until `--all-packages` | The usual cause of "works locally, ModuleNotFoundError in CI" |
| `uv sync --package worker` installs worker + its deps only, and NOT the root `dev` group | Per-member CI jobs add their test tools to the member or sync the group explicitly |
| A member with `requires-python = ">=3.13,<3.14"` in a 3.14 workspace: `uv lock` exit 2, `Found conflicting Python requirements: - ai: >=3.14 ... - ocr313: >=3.13, <3.14` | A workspace has ONE interpreter (the intersection of all members, docs) |
| A 3.14 member depending on paddlepaddle 3.3.1: `uv lock` exit 1, "no wheels with a matching Python version tag (e.g., `cp314`)"; wheels exist for cp39–cp313 | Runtime-incompatible dependencies go to a standalone project (below) |

Docker image for ONE member (executed: build 0; the image held api + shared, not worker or pytest; a stale lock failed the build with "needs to be updated, but `--locked` was provided"):

```dockerfile
# builder stage (base pins as in deployment-ci-cd/reference/python-ci-supply-chain.md section 8)
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1 UV_NO_BUILD=1
# Only uv.lock is mounted, so --frozen here; the --locked sync below re-checks the lock.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --frozen --no-install-workspace --package api --no-editable
# Every member's pyproject.toml must be present for the lock check (allow-list .dockerignore).
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package api --no-editable
```

## 7. Separate projects: incompatible runtime or incompatible dependency (own lock)

When one deployable needs a different Python (OCR engines without cp314 wheels, a vendor SDK capped below 3.14), make it a separate project with its own `uv.lock` and `.python-version`, outside the workspace `members` globs.

```bash
uv init --package --python 3.13.18 --no-workspace standalone/ocr-worker
cd standalone/ocr-worker
# requires-python = ">=3.13,<3.14"
uv add "paddlepaddle==3.3.1" ../../packages/shared   # path source; shared must declare requires-python ">=3.13"
uv lock --check
```

Executed: own `uv.lock` created next to its `pyproject.toml`, `lock --check` 0, `sync --locked --no-install-package paddlepaddle` 0 (skips the large wheel for a contract test), `import shared` on 3.13.18 0, and the workspace lock was unaffected (`uv lock --check` 0, no paddlepaddle in it).

The same split applies on ONE interpreter when two services need incompatible versions of a dependency: a workspace has one lock, so one version of each package. Executed with uv 0.13.9 on 3.14.10, two members of one workspace:

```
adk-svc: google-adk==2.15.0          lc-svc: langchain-google-genai==4.5.2
uv lock → exit 1: "Because langchain-google-genai>=4.5.2 depends on google-genai>=3.3.0 and
  google-adk>=2.15.0 depends on google-genai>=2.34,<3, ... adk-svc and lc-svc are incompatible."
```

google-adk 2.15.0 also requires `websockets>=15.0.1,<16` (executed: a member pinning `websockets==17.4` beside it fails the same way), and google-cloud-aiplatform 2.10.0 requires `google-genai<3`. Moved out of the workspace as two projects, each locked with exit 0: adk-svc resolved google-genai 2.34.0 / websockets 15.0.1, lc-svc google-genai 3.6.1 / websockets 17.4. Do not force one lock with `override-dependencies`: it installs a version the library declared it does not support. A project inside a member glob is still a member (executed: `uv lock` in `services/adk-svc` resolved the whole workspace), so a separate project lives outside the `members` globs.

Rules:
- The contract between runtimes is the shared package (kept compatible with the lowest interpreter) or a versioned schema (JSON Schema / protobuf) both sides test against; never copy model classes.
- It gets its own CI job (`working-directory`), its own image and its own upgrade cadence. Re-check monthly whether the blocker gained wheels for the main interpreter, then fold it back into the workspace.

## 8. Build, export, publish

| Command (executed) | Notes |
|---|---|
| `uv build` / `uv build --package shared` | `uv_build` backend; wheel + sdist in `dist/` |
| `uv export --locked --no-dev --no-hashes --no-emit-project -o requirements.audit.txt` | Input for pip-audit |
| `uv export --format pylock.toml --package worker --no-dev --locked -o pylock.toml` | PEP 751 lock for tools that consume it |
| `uv publish --dry-run --publish-url https://test.pypi.org/legacy/ dist/*` | Validates files without uploading; publish for real with Trusted Publishing from CI, not a stored token |
| `uv version --bump minor --dry-run` | Reads/bumps `[project] version` |

## 9. CI and Docker

The canonical workflow, Dockerfile, pin-resolution commands and audit gate live in `../../deployment-ci-cd/reference/python-ci-supply-chain.md` (actionlint-clean workflow, image built and run hardened). uv-specific points:

- `astral-sh/setup-uv` with `version: "0.13.9"` and `enable-cache: true`; its default `cache-dependency-glob` already includes `**/uv.lock` and `**/pyproject.toml` (action.yml, v10.4.0).
- Order: `uv python install` → `uv lock --check` → `uv sync --locked --no-build` → ruff → mypy → pytest → `uv export` + `pip-audit`.
- `uv audit --preview-features audit-command --locked` works (executed: exit 1 with three PYSEC IDs on jinja2 3.1.4, exit 0 on the clean lock) but is experimental: run it as a second opinion, not the gate.
- `uv cache prune --ci` before saving a self-managed cache keeps it small; with setup-uv set `prune-cache: true` (its default is `false` in v10.4.0 action.yml).

## 10. Pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: 00eaed0068329eb6ca6bcb8de7b46c372d8d1c19  # 0.13.9
    hooks:
      - id: uv-lock        # keeps uv.lock in step with pyproject.toml
  - repo: local
    hooks:
      - id: ruff
        name: ruff
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
```

Hook ids available at 0.13.9: `pip-compile`, `uv-lock`, `uv-export`, `uv-sync`, `uv-audit` (`.pre-commit-hooks.yaml` at the tag). Black is not used: ruff formats.

## 11. Migration

| From | To | Note |
|---|---|---|
| `pip install -r requirements.txt` | `uv init --bare` then `uv add -r requirements.txt`, `uv lock` | Delete the requirements file afterwards; export one only for tools that need it |
| pip-tools (`pip-compile` / `pip-sync`) | `uv lock` / `uv sync --locked` | `uv pip compile` exists for staged migrations |
| Poetry | Rewrite `[tool.poetry.dependencies]` as PEP 621 `[project] dependencies` and dev groups as `[dependency-groups]`, then `uv lock` | uv does not read `[tool.poetry]`: executed, a Poetry-only `pyproject.toml` "resolved" with zero packages and defaulted to Python `>=3.15` |
| `pip install uv` in images | `FROM ghcr.io/astral-sh/uv:<version>@sha256:<digest> AS uv` + `COPY --from=uv /uv /uvx /bin/` | Never `:latest` |

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `The lockfile at uv.lock needs to be updated, but --locked was provided` | pyproject changed without relock | `uv lock`, commit both files |
| Python 3.15 appears unexpectedly | uv 0.13 default + no `.python-version` | `uv python pin 3.14.10` |
| `ModuleNotFoundError` for a workspace member in CI | non-virtual root + plain `uv sync` | `uv sync --locked --all-packages` or `--package <member>` |
| Build step compiles grpcio/numpy from source | no wheel for your interpreter (e.g. 3.15 + a capped dependency) | `--no-build` in CI to fail fast; pick versions with wheels or stay on 3.14 |
| `Found conflicting Python requirements` | a member needs another interpreter | standalone project (section 7) |
| `tool.uv.dev-dependencies` warning | deprecated field | `[dependency-groups] dev` |
