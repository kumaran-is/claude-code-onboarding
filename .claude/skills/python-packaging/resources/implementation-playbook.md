# Python Packaging — Implementation Playbook (Workspace-Scoped)

Validated 2026-11-23: uv 0.13.9, CPython 3.14.10, click 8.5.1, structlog 26.1.0, pytest 9.2.0, mypy 2.4.1 (`--strict`), ruff 0.17.6, hatchling 1.33.0, hatch-vcs 0.5.0. Every snippet below was built, type-checked, linted and tested in a scratch project; exit codes are in the section notes.

## 1. Layout

```
ops-tool/                       # uv init --package --python 3.14 ops-tool
├── .python-version             # 3.14.10 (uv python pin 3.14.10)
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── ops_tool/
│       ├── __init__.py
│       ├── cli.py              # Click entry point
│       └── argcli.py           # argparse entry point (stdlib only)
└── tests/
    ├── test_cli.py
    └── test_argcli.py
```

- `src/` layout: tests import the installed package (uv installs the project into `.venv` on `uv sync`), so a module missing from the build fails the tests instead of passing because the working directory happens to be on `sys.path`.
- Flat layout only for a single-file script; give it inline metadata instead of a project (section 6).
- Workspace member library: `uv init --lib packages/shared` (no entry point, `py.typed` added by `--lib`); layout and lock rules in `uv-package-manager` playbook section 6.

## 2. Full pyproject.toml (service or tool)

```toml
[project]
name = "ops-tool"
version = "0.1.0"
description = "Internal operations CLI"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "click==8.5.1",
    "structlog==26.1.0",
]

[project.scripts]
ops-tool = "ops_tool.cli:main"
ops-args = "ops_tool.argcli:main"

[dependency-groups]
dev = ["pytest==9.2.0", "mypy==2.4.1", "ruff==0.17.6"]

[build-system]
requires = ["uv_build>=0.13.9,<0.14.0"]
build-backend = "uv_build"

[tool.ruff]
target-version = "py314"   # never higher than requires-python: py314 rewrites except (A, B) to the 3.14-only form
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC", "S", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.mypy]
python_version = "3.14"
strict = true

[tool.pytest]                                 # pytest 9 native TOML table
testpaths = ["tests"]
strict = true                                 # unknown config keys and markers are errors
filterwarnings = ["error"]                    # a new DeprecationWarning fails the suite
# Async projects (pytest-asyncio 1.5.0 in the dev group) add:
# asyncio_mode = "auto"
# asyncio_default_fixture_loop_scope = "function"
# asyncio_default_test_loop_scope = "function"
```

Notes:
- `[dependency-groups]` (PEP 735) replaces `[project.optional-dependencies] dev` and the deprecated `[tool.uv] dev-dependencies`. Extras (`[project.optional-dependencies]`) are for optional FEATURES a consumer installs, not for dev tools.
- `requires-python` states the floor (`>=3.14`); the patch you test and deploy lives in `.python-version` and the Docker base tag.
- No `[tool.hatch...]` / `[tool.setuptools...]` tables with `uv_build`: it discovers `src/<normalized_name>/`.
- Use either `[tool.pytest]` or the legacy `[tool.pytest.ini_options]`, never both (executed: pytest exit 4, "Cannot use both"). With `strict = true`, an `asyncio_*` key without pytest-asyncio installed is an unknown-key error (executed: exit 4), so add those keys together with the plugin. pytest-timeout's `timeout` takes a string (`timeout = "30"`).

## 3. Entry points

Click (`src/ops_tool/cli.py`) is in `SKILL.md`. The stdlib alternative:

```python
"""argparse variant (stdlib only): `ops-args deploy staging --dry-run`."""

import argparse
import sys
from collections.abc import Sequence

import structlog

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ops-args", description="Internal deployment tool.")
    sub = parser.add_subparsers(dest="command", required=True)
    deploy = sub.add_parser("deploy", help="Deploy to an environment.")
    deploy.add_argument("environment", choices=["staging", "production"])
    deploy.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger.info("deploy_requested", environment=args.environment, dry_run=args.dry_run)
    sys.stdout.write(f"deploy {args.environment} dry_run={args.dry_run}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`main(argv)` taking an optional argument list makes it testable without patching `sys.argv`; the console script calls it with no arguments and uses the return value as the exit code.

## 4. CLI tests

```python
# tests/test_cli.py
from click.testing import CliRunner

from ops_tool.cli import main


def test_deploy_dry_run() -> None:
    result = CliRunner().invoke(main, ["deploy", "staging", "--dry-run"])
    assert result.exit_code == 0
    assert "deploy staging dry_run=True" in result.output


def test_deploy_rejects_unknown_environment() -> None:
    result = CliRunner().invoke(main, ["deploy", "qa"])
    assert result.exit_code == 2
```

```python
# tests/test_argcli.py
import pytest

from ops_tool.argcli import main


def test_deploy_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deploy", "staging", "--dry-run"]) == 0
    assert "deploy staging dry_run=True" in capsys.readouterr().out


def test_unknown_environment_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["deploy", "qa"])
    assert exc.value.code == 2
```

Executed with the `[tool.pytest]` table above: `uv run pytest -q` 4 passed (exit 0); `uv run mypy --strict src tests` 0; `uv run ruff check .` and `ruff format --check .` 0.

## 5. Versioning

| Need | How | Evidence |
|---|---|---|
| Static version, bumped in a release PR | `uv version --bump minor` (or `patch`/`major`; `--dry-run` to preview) | executed: `ops-tool 0.1.0 => 0.2.0`, `pyproject.toml` rewritten, project reinstalled |
| Read it at runtime | `importlib.metadata.version("ops-tool")` (Click: `@click.version_option(package_name="ops-tool")`) | executed: `ops-tool --version` printed `ops-tool, version 0.1.0` from the installed wheel |
| Version from git tags | `[build-system] requires = ["hatchling==1.33.0", "hatch-vcs==0.5.0"]`, `build-backend = "hatchling.build"`, `[project] dynamic = ["version"]`, `[tool.hatch.version] source = "vcs"`, `[tool.hatch.build.targets.wheel] packages = ["src/<pkg>"]` | executed: tag `v1.4.0` built `dv-1.4.0` wheel and sdist |

`uv_build` does not support a dynamic version (executed: `dynamic = ["version"]` failed with "missing field `version`", exit 2). Services deployed as images usually need no package version at all: tag the image with the commit SHA.

## 6. Single-file scripts

```bash
uv init --script tool.py --python 3.14         # adds a PEP 723 metadata block
uv add --script tool.py "httpx==0.28.1"         # records the dependency in the block
uv lock --script tool.py                        # writes tool.py.lock next to it
uv run tool.py                                  # isolated environment from the block
```

Executed: all four exited 0; the block reads `requires-python = ">=3.14"` and `dependencies = ["httpx==0.28.1"]`.

## 7. Build and smoke-test the artifact

```bash
uv build                                            # dist/ops_tool-0.1.0-py3-none-any.whl + .tar.gz
uv venv --python 3.14.10 /tmp/ops-tool-check
VIRTUAL_ENV=/tmp/ops-tool-check uv pip install dist/ops_tool-0.1.0-py3-none-any.whl
/tmp/ops-tool-check/bin/ops-tool --version          # entry point works outside the project
```

Executed: build 0, install into the clean venv 0, `ops-tool --version` 0. A clean-venv install catches files missing from the wheel that an editable install hides. Do not use `uv tool install` for this check: it installs into the user's tool directory (machine-wide); remove it with `uv tool uninstall <name>` if you did.
