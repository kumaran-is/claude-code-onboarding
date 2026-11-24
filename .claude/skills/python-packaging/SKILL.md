---
name: python-packaging
description: Python 3.14 project structure — pyproject.toml (PEP 621) for services, shared libraries and internal tools, src layout with the uv_build backend, CLI entry points (Click/argparse), versioning (uv version --bump, git tags via hatch-vcs), building and installing wheels. Use when structuring a new Python project, a workspace member, or an internal CLI tool.
allowed-tools: Read, Write, Edit, Bash
metadata:
  triggers: pyproject.toml, Python project structure, source layout, flat layout, CLI tool Python, Click entry point, argparse CLI, Python versioning, editable install, Python internal tool, Python script packaging, uv_build, build backend, uv build, wheel, hatch-vcs
  related-skills: python-dev, uv-package-manager, api-design-principles
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**USE SOURCE LAYOUT (`src/`) WITH A DECLARED BUILD BACKEND FOR EVERY SERVICE, SHARED LIBRARY AND TOOL — tests then import the installed package, not the working directory, so a missing file or wrong package name fails in CI instead of in production**

# Python Packaging

Project structure for Python 3.14 services, workspace libraries and internal CLI tools. Validated 2026-11-23 with uv 0.13.9 and CPython 3.14.10: every command below was executed (build, wheel install into a clean venv, entry point run, tests, `mypy --strict`, ruff).

## Scope

- `pyproject.toml` (PEP 621 `[project]`, PEP 735 `[dependency-groups]`) for services, shared workspace libraries and tools
- Layout decision, build backend choice, entry points, versioning, building and installing wheels
- Dependency management, locks and workspaces: `uv-package-manager`. Publishing an open-source library to PyPI is out of scope here (see `uv publish` in `uv-package-manager` playbook section 8 for the command).

## Layout and Backend Decision

```
New project?
├── Service, shared library, internal tool  → uv init --package (src/<pkg>/, backend uv_build)
├── Library inside a workspace              → uv init --lib packages/<name>
├── Version must come from git tags         → hatchling + hatch-vcs (uv_build needs a static version)
└── One-off script                          → single file with inline metadata: uv add --script tool.py <dep>
```

| Backend | Use | Evidence |
|---|---|---|
| `uv_build` (`requires = ["uv_build>=0.13.9,<0.14.0"]`) | Default for pure-Python packages; written by `uv init` | builds wheel + sdist; rejects `dynamic = ["version"]` ("missing field `version`", exit 2) |
| `hatchling==1.33.0` + `hatch-vcs==0.5.0` | Version derived from a git tag | tag `v1.4.0` built `dv-1.4.0` wheel and sdist |
| setuptools | Only for projects with C extensions or legacy config you are not migrating yet | not re-validated here |

## Key pyproject.toml Sections

```toml
[project]
name = "ops-tool"
version = "0.1.0"
requires-python = ">=3.14"          # patch pinned in .python-version, not here
dependencies = ["click==8.5.1", "structlog==26.1.0"]

[project.scripts]
ops-tool = "ops_tool.cli:main"       # console entry point

[dependency-groups]
dev = ["pytest==9.2.0", "mypy==2.4.1", "ruff==0.17.6"]

[build-system]
requires = ["uv_build>=0.13.9,<0.14.0"]
build-backend = "uv_build"
```

`uv_build` finds `src/<normalized_name>/` by convention; no `packages = [...]` table is needed. Tool config (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) is in the playbook.

## CLI Entry Point Pattern

```python
# src/ops_tool/cli.py
"""Click entry point: `ops-tool deploy staging --dry-run`."""

import click
import structlog

logger = structlog.get_logger(__name__)


@click.group()
@click.version_option(package_name="ops-tool")
def main() -> None:
    """Internal deployment tool."""


@main.command()
@click.argument("environment", type=click.Choice(["staging", "production"]))
@click.option("--dry-run", is_flag=True, help="Show what would change without changing it.")
def deploy(environment: str, dry_run: bool) -> None:
    """Deploy to ENVIRONMENT."""
    logger.info("deploy_requested", environment=environment, dry_run=dry_run)
    click.echo(f"deploy {environment} dry_run={dry_run}")
```

Run during development with `uv run ops-tool deploy staging --dry-run` (no activation, no `pip install -e`: `uv sync` installs the project editable). `click.echo` is the CLI's user output; diagnostics go to the logger. Tests use `click.testing.CliRunner` (playbook section 4).

## Services vs Libraries

- A deployed SERVICE pins exactly: framework (and any library that patches its internals, such as tracing instrumentors) with `==`, lock committed, installed with `uv sync --locked` (never from loose `>=` ranges in a Dockerfile). A shared LIBRARY declares compatible ranges and lets each consumer's lock decide; keep its `requires-python` as wide as the consumers you test (a shared contract used by a standalone 3.13 worker declares `>=3.13`).
- Install the project non-editable (`uv sync --locked --no-editable`) in images so only `.venv` is copied to runtime. See `../deployment-ci-cd/reference/python-ci-supply-chain.md` section 8.

## Reference File

Load `resources/implementation-playbook.md` for: the full service/library `pyproject.toml` with ruff/mypy/pytest config, workspace library layout, argparse CLI, CLI tests, versioning (`uv version --bump`, hatch-vcs), and the build → clean-venv install → entry-point smoke test.
