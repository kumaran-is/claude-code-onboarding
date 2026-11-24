---
name: uv-package-manager
description: uv 0.13.x workflows for Python 3.14 — lockfiles, dependency groups, Python pinning, workspaces (shared lib + services) and standalone incompatible-runtime projects, Docker layering, CI caching, build/export/publish, and migration from pip/Poetry/pip-tools. Use when working with uv beyond basic uv add/uv init.
allowed-tools: Read, Write, Edit, Bash
metadata:
  triggers: uv package manager, uv lock, uv sync, uv python, uv workspace, uv Docker, uv CI, uv cache, migrate from pip to uv, migrate from poetry to uv, uv monorepo, uv lockfile, uv run, uv workspace member, dependency groups, uv_build, uv export, uv publish, uv 0.13
  related-skills: python-dev, python-packaging, docker
  domain: backend
  role: specialist
  scope: tooling
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**ALWAYS USE `uv sync --locked` IN CI AND DOCKER — it fails when `pyproject.toml` and `uv.lock` disagree; `--frozen` installs a stale lock without complaint (executed: stale lock, `--frozen` exit 0, `--locked` exit 1); plain `uv sync` re-resolves and can pick different versions**

# uv Package Manager

Deep reference for uv, this workspace's Python package and interpreter manager. Validated with uv 0.13.9 on CPython 3.14.10 (2026-11-23). uv 0.13 downloads Python **3.15** by default when nothing is pinned: every project commits `.python-version`.

## When to Use

Load this skill when:
- Setting up lockfile workflows (`uv lock`, `uv sync --locked`)
- Managing Python version pinning (`uv python pin 3.14`)
- Configuring Docker builds with uv cache mounts
- Setting up GitHub Actions CI with uv dependency caching
- Working in a monorepo with multiple Python packages
- Migrating an existing project from pip, Poetry, or pip-tools
- Using `uv run` to execute scripts without environment activation

The `python-dev` skill covers: `uv init`, `uv add`, basic virtual environment setup. Load THIS skill for everything beyond that.

## Quick Reference

| Task | Command |
|------|---------|
| Create lockfile | `uv lock` |
| Install from lockfile (CI) | `uv sync --locked` |
| Is the lock stale? | `uv lock --check` (exit 1 when stale) |
| Pin Python version | `uv python pin 3.14.10` (`requires-python = ">=3.14"`) |
| Fail instead of compiling a third-party sdist | `uv sync --locked --no-build` |
| Workspace: install every member | `uv sync --locked --all-packages` |
| Run without activating | `uv run python script.py` |
| Run tests | `uv run pytest` |
| Upgrade all deps | `uv lock --upgrade` |
| Check outdated | `uv tree --outdated` |
| Remove package | `uv remove <pkg>` |

## Reference File

Load `resources/implementation-playbook.md` for (every command executed on uv 0.13.9):
- What changed since uv 0.11 (3.15 default download, `uv_build` bound, stricter hashes; `uv audit`/`uv format` still experimental)
- Dependencies: runtime, `[dependency-groups]`, optional extras, `-r requirements.txt` import
- Lock/sync semantics table (`--locked`, `--frozen`, `--no-build`, upgrades) and resolver facts
- Workspaces: virtual root, `--all-packages`, `--package`, per-member Docker image, and why a 3.13-only member cannot join a 3.14 workspace
- Standalone incompatible-runtime worker with its own `uv.lock` and `.python-version`
- Build, export (`requirements.txt`, `pylock.toml`), `publish --dry-run`, `version --bump`
- Pre-commit (`uv-pre-commit` pinned by SHA), migration from pip, pip-tools and Poetry, troubleshooting

## Key Patterns Summary

```bash
# New project (versions: BASELINE pins, PyPI 2026-11-23)
uv init --package --python 3.14 my-service && cd my-service
uv python pin 3.14.10
uv add "fastapi[standard-no-fastapi-cloud-cli]==0.165.0" "pydantic-settings==2.16.3"
uv add --dev "pytest==9.2.0" "pytest-asyncio==1.5.0" "ruff==0.17.6" "mypy==2.4.1" "pip-audit==2.10.1"

# Lockfile (add to CI and Docker)
uv lock                          # Generate/update uv.lock
uv sync --locked                 # Install exact versions; fails if the lock is stale

# Python version
uv python pin 3.14.10            # Write .python-version (uv 0.13 would otherwise pick 3.15)
uv python install                # Install what .python-version names

# Run without activating venv
uv run pytest                    # Run pytest
uv run uvicorn my_service.main:create_app --factory   # Run server
```

## Docker Pattern (summary — full pattern in playbook)

```dockerfile
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1 UV_NO_BUILD=1
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable
```

Digests resolved 2026-11-23 with `docker buildx imagetools inspect`; the full Dockerfile (built and run with `--read-only --cap-drop ALL`) is in `../deployment-ci-cd/reference/python-ci-supply-chain.md` section 8.

Workspaces: with a root that has a `[project]` table, plain `uv sync` skips members (executed); use `uv sync --locked --all-packages`, or `--package <member>` per deployable. A member needing another Python cannot join (`Found conflicting Python requirements`, executed): give it its own project and lock (playbook sections 6–7).

## CI Pattern (summary — full pattern in playbook)

```yaml
- uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
  with:
    version: "0.13.9"
    enable-cache: true
- run: uv python install
- run: uv lock --check
- run: uv sync --locked --no-build
```
