---
name: uv-package-manager
description: Comprehensive uv workflows for Python 3.14 — virtual environments, lockfiles, Python version pinning, monorepo workspaces, Docker integration, CI/CD caching, and migration from pip/Poetry/pip-tools. Use when working with uv beyond basic uv add/uv init.
allowed-tools: Read, Write, Edit, Bash
metadata:
  triggers: uv package manager, uv lock, uv sync, uv python, uv workspace, uv Docker, uv CI, uv cache, migrate from pip to uv, migrate from poetry to uv, uv monorepo, uv lockfile, uv run
  related-skills: python-dev, python-packaging, docker
  domain: backend
  role: specialist
  scope: tooling
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**ALWAYS USE `uv sync --locked` IN CI AND DOCKER — it fails when `pyproject.toml` and `uv.lock` disagree; `--frozen` installs a stale lock without complaint (executed: stale lock, `--frozen` exit 0, `--locked` exit 1); plain `uv sync` re-resolves and can pick different versions**

# uv Package Manager

Deep reference for uv — the ultra-fast Python package manager written in Rust. The workspace uses uv as its primary Python package manager. This skill covers everything beyond the 4 basic commands in `python-dev`.

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
| Pin Python version | `uv python pin 3.14` |
| Run without activating | `uv run python script.py` |
| Run tests | `uv run pytest` |
| Upgrade all deps | `uv lock --upgrade` |
| Check outdated | `uv tree --outdated` |
| Remove package | `uv remove <pkg>` |

## Reference File

Load `resources/implementation-playbook.md` for:
- 22 patterns covering all uv workflows
- Virtual environment management (create, activate, uv run)
- Python version management
- Lockfile workflows for reproducible builds
- Monorepo workspace configuration
- Docker multi-stage builds with uv cache mounts
- GitHub Actions CI with uv caching
- Migration guides from pip, Poetry, pip-tools (command-by-command)
- Performance optimization (global cache, parallel install, offline mode)
- Pre-commit hooks and VS Code integration

## Key Patterns Summary

```bash
# New project (from python-dev)
uv init my-service && cd my-service
uv add fastapi uvicorn pydantic pydantic-settings
uv add --dev pytest pytest-asyncio httpx ruff mypy

# Lockfile (add to CI and Docker)
uv lock                          # Generate/update uv.lock
uv sync --locked                 # Install exact versions; fails if the lock is stale

# Python version
uv python pin 3.14               # Write .python-version file
uv python install 3.14           # Install that version

# Run without activating venv
uv run pytest                    # Run pytest
uv run uvicorn src.main:app      # Run server
```

## Docker Pattern (summary — full pattern in playbook)

```dockerfile
FROM python:3.14-slim@sha256:<index-digest> AS builder
COPY --from=ghcr.io/astral-sh/uv:<x.y.z>@sha256:<digest> /uv /uvx /bin/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
```

Monorepo/workspace: plain `uv sync` skips workspace members; use `uv sync --all-packages --locked` and run one pytest process per package with the root config (`-c pyproject.toml --import-mode=importlib`). Dockerfile layering, pinning and audit: `../deployment-ci-cd/reference/python-ci-supply-chain.md`.

## CI Pattern (summary — full pattern in playbook)

```yaml
- uses: astral-sh/setup-uv@<40-hex-sha> # vX.Y.Z (pin by SHA)
  with:
    enable-cache: true
- run: uv lock --check
- run: uv sync --locked
```
