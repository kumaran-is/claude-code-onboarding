---
name: python-packaging
description: Python project structure patterns — pyproject.toml for services and internal tools, source vs flat layout, CLI entry points with Click/argparse, dynamic versioning, and editable installs. Use when structuring a new Python project or building internal CLI tools.
allowed-tools: Read, Write, Edit, Bash
metadata:
  triggers: pyproject.toml, Python project structure, source layout, flat layout, CLI tool Python, Click entry point, argparse CLI, Python versioning, editable install, Python internal tool, Python script packaging
  related-skills: python-dev, uv-package-manager, api-design-principles
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-03-14"
---

## Iron Law

**USE SOURCE LAYOUT (`src/`) FOR ALL SERVICES AND INSTALLABLE TOOLS — flat layout works for scripts but causes import confusion in larger projects and CI environments**

# Python Packaging

Project structure patterns for Python 3.14 services, internal tools, and CLI applications.

## Scope

This skill covers the **workspace-relevant** subset of Python packaging:
- `pyproject.toml` structure for FastAPI services and internal tools
- Source layout vs flat layout decision
- CLI entry points (Click, argparse) for internal tooling
- Dynamic versioning
- Editable installs for development

**Out of scope for this workspace:** PyPI publishing, wheels, namespace packages, C extensions, private package index. The workspace builds services and internal tools, not distributable libraries.

## Layout Decision

```
New project?
│
├── FastAPI service / internal service
│   └── Source layout: src/<package>/ ← default for all services
│
├── Internal CLI tool (deployment scripts, data tools)
│   └── Source layout with [project.scripts] entry point
│
└── Quick one-off script
    └── Flat layout (single .py file or simple directory)
```

## Reference File

Load `resources/implementation-playbook.md` for:
- Source layout pattern (Pattern 1) — full directory structure with __init__.py placement
- Flat layout pattern (Pattern 2) — when appropriate
- Full pyproject.toml template (Pattern 4) — with all modern metadata fields
- Dynamic versioning with `setuptools-scm` (Pattern 5)
- CLI with Click (Pattern 6) — entry points, commands, options
- CLI with argparse (Pattern 7) — subcommands, arguments
- Editable install (Pattern 16) — `uv pip install -e .` for development

## Key pyproject.toml Sections

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-service"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.135.2",
    "pydantic>=2.0.0",
]

[project.scripts]
my-cli = "my_package.cli:main"  # CLI entry point

[tool.hatch.build.targets.wheel]
packages = ["src/my_package"]
```

## CLI Entry Point Pattern

```python
# src/my_tool/cli.py
import click

@click.group()
def main():
    """Internal deployment tool."""
    pass

@main.command()
@click.argument("environment")
@click.option("--dry-run", is_flag=True)
def deploy(environment: str, dry_run: bool):
    """Deploy to environment."""
    click.echo(f"Deploying to {environment} (dry_run={dry_run})")

if __name__ == "__main__":
    main()
```

Install and run: `uv pip install -e .` then `my-cli deploy staging --dry-run`

## Services vs Libraries

- A deployed SERVICE pins exactly: framework (and any library that patches its internals, such as tracing instrumentors) with `==`, lock committed, installed with `uv sync --locked` (never from loose `>=` ranges in a Dockerfile). A published LIBRARY declares compatible ranges and lets the consumer's lock decide; keep its `requires-python` as wide as you actually test.
- Install the project non-editable (`uv sync --locked --no-editable`) in images so only `.venv` is copied to runtime. See `../deployment-ci-cd/reference/python-ci-supply-chain.md` §8.
