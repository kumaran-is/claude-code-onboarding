#!/usr/bin/env python3
"""Aggregate env/infra SSOT gate.

Delegates code↔.env.example presence to check_env_parity.py. Adds compose
required-interpolation (no ${VAR:-default} for keys the code requires),
Terraform variable / tfvars.example keys, dart-define JSON keys, and
local/staging/production *example* template key-set drift. Never opens a real
.env / .env.staging / .env.production. Docker and Terraform are optional: their
absence is not a FAIL.

Callers: /verify (full|pre-pr), docker skill, terraform-skill. Do not inline
those sub-checks in a Makefile or workflow when this aggregate exists.

Usage:
  check-infra-env-ssot.py [--root DIR] [--selftest]

Exit: 0 ok (warnings allowed), 1 FAIL, 2 NOT APPLICABLE / broken selftest.
Stdlib only. Never opens a real .env (values). Never hardcodes a product path.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import check_env_parity as env_parity  # noqa: E402

COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
# Underscore must stay in the rest-of-name class (DATABASE_URL). Hyphen must not
# sit inside a [] range (`[:-]` is a broken character-class).
COMPOSE_REQUIRED = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
COMPOSE_DEFAULTED = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-[^}]*|-[^}]*)\}")
TF_VAR = re.compile(r'variable\s+"([A-Z_][A-Z0-9_]*)"', re.I)
TF_VAR_SNAKE = re.compile(r'variable\s+"([a-z][a-z0-9_]*)"')
SKIP_DIRS = env_parity.SKIP_DIRS | {"example", "examples"}
NAMED_EXAMPLES = (
    (".env.example", "local"),
    ("env.example", "local"),
    (".env.local.example", "local"),
    (".env.staging.example", "staging"),
    (".env.production.example", "production"),
    (".env.prod.example", "production"),
)
REAL_ENV = {".env", ".env.local", ".env.staging", ".env.production", ".env.prod"}


def walk(root: Path):
    root = root.resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).parts
        if set(rel[:-1]) & SKIP_DIRS:
            continue
        yield p


def example_path(root: Path) -> Path | None:
    for name in (".env.example", "env.example"):
        p = root / name
        if p.is_file():
            return p
    return None


def compose_keys(root: Path) -> tuple[set[str], set[str]]:
    required: set[str] = set()
    defaulted: set[str] = set()
    for p in walk(root):
        if p.name not in COMPOSE_NAMES and "compose" not in p.name:
            continue
        if p.suffix not in {".yml", ".yaml"}:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        required |= set(COMPOSE_REQUIRED.findall(text))
        defaulted |= set(COMPOSE_DEFAULTED.findall(text))
    return required, defaulted


def terraform_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    for p in walk(root):
        if p.suffix != ".tf" and p.name not in {"terraform.tfvars.example", "terraform.tfvars.sample"}:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in TF_VAR.finditer(text):
            keys.add(m.group(1).upper())
        for m in TF_VAR_SNAKE.finditer(text):
            keys.add(m.group(1).upper())
        if p.name.endswith(".example") or p.name.endswith(".sample"):
            for line in text.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    keys.add(line.split("=", 1)[0].strip().upper())
    return keys


def tfvars_file_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            keys.add(line.split("=", 1)[0].strip().upper())
    return keys


def named_example_sets(root: Path) -> dict[str, set[str]]:
    """Key sets from *example* templates only. Never opens REAL_ENV files."""
    found: dict[str, set[str]] = {}
    for name, env in NAMED_EXAMPLES:
        p = root / name
        if p.is_file():
            found.setdefault(env, set()).update(env_parity.example_keys(p))
    root_r = root.resolve()
    for p in walk(root):
        if p.name in REAL_ENV:
            continue
        rel_parts = {x.lower() for x in p.relative_to(root_r).parts}
        if p.name.endswith(".tfvars.example") or p.name.endswith(".tfvars.sample"):
            if "staging" in rel_parts or "stage" in rel_parts:
                env = "staging"
            elif "prod" in rel_parts or "production" in rel_parts:
                env = "production"
            else:
                continue
            found.setdefault(env, set()).update(tfvars_file_keys(p))
    return found


def env_drift_lines(sets: dict[str, set[str]]) -> list[str]:
    if len(sets) < 2:
        return []
    lines: list[str] = []
    names = sorted(sets)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            for key in sorted(sets[a] - sets[b]):
                lines.append(f"FAIL env-drift: {key} in {a} templates, missing from {b}")
            for key in sorted(sets[b] - sets[a]):
                lines.append(f"FAIL env-drift: {key} in {b} templates, missing from {a}")
    return lines


def dart_define_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    for p in walk(root):
        if p.name not in {"dart_define.example.json", "dart_define.json.example", ".dart_define.example.json"}:
            continue
        raw = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"{p.name}: invalid JSON ({e})") from e
        if isinstance(data, dict):
            keys |= {str(k).upper() for k in data}
    return keys


def check(root: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    example = example_path(root)
    compose_req, compose_def = compose_keys(root)
    tf_keys = terraform_keys(root)
    try:
        dart_keys = dart_define_keys(root)
    except ValueError as e:
        return 1, [f"FAIL {e}"]
    env_sets = named_example_sets(root)
    has_any = bool(example or compose_req or compose_def or tf_keys or dart_keys or env_sets)
    if not has_any:
        return 2, ["NOT APPLICABLE: no .env.example, compose interpolation, Terraform variables or dart-define example"]

    code_need: dict[str, str] = {}
    if example:
        _rc, env_lines = env_parity.check(root, example)
        lines.extend(env_lines)
        code_need, _optional = env_parity.read_keys(root)
        have = env_parity.example_keys(example)
        for key in sorted(compose_def & set(code_need)):
            lines.append(
                f"FAIL compose default for required key ${{{key}:-…}} "
                f"(code requires it in {code_need[key]}) — fail closed, no default"
            )
        for key in sorted((compose_req | dart_keys | tf_keys) - have):
            if key in getattr(env_parity, "PLATFORM", set()):
                continue
            src = "compose" if key in compose_req else "dart-define" if key in dart_keys else "terraform"
            lines.append(f"FAIL missing from {example.name}: {key} ({src})")
    else:
        if compose_req or dart_keys or tf_keys:
            lines.append("FAIL infra keys found but no .env.example to be the SSOT")

    drift = env_drift_lines(env_sets)
    lines.extend(drift)

    fail = any(l.startswith("FAIL") for l in lines)
    lines.append(
        f"scanned: example={'yes' if example else 'no'} "
        f"compose_required={len(compose_req)} compose_defaulted={len(compose_def)} "
        f"terraform={len(tf_keys)} dart_define={len(dart_keys)} "
        f"env_templates={','.join(sorted(env_sets)) or 'none'}"
    )
    if fail:
        return 1, lines
    return 0, lines


def selftest() -> int:
    fail = 0

    def ok(cond: bool, name: str, detail: object = "") -> None:
        nonlocal fail
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f" -> {detail}"))
        fail += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        rc, out = check(root)
        ok(rc == 2, "negative: empty tree is NOT APPLICABLE", out)

        (root / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        (root / "docker-compose.yml").write_text(
            "services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL}\n      API_KEY: ${API_KEY}\n"
        )
        (root / "app").mkdir()
        (root / "app" / "settings.py").write_text(
            "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    database_url: str\n    api_key: str\n"
        )
        rc, out = check(root)
        ok(rc == 0 and not any(l.startswith("FAIL") for l in out), "negative: aligned env+compose is clean", out)
        ok(any("compose_required=2" in l for l in out), "aligned scan sees two required compose keys", out)

        (root / "docker-compose.yml").write_text(
            "services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL:-postgres://x}\n      API_KEY: ${API_KEY}\n"
        )
        rc, out = check(root)
        ok(rc == 1 and any("compose default" in l and "DATABASE_URL" in l for l in out),
           "positive: ${VAR:-default} for a required key FAILs", out)
        ok(any("compose_defaulted=1" in l for l in out), "defaulted scan counts DATABASE_URL", out)

        (root / "docker-compose.yml").write_text(
            "services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL-postgres://x}\n      API_KEY: ${API_KEY}\n"
        )
        rc, out = check(root)
        ok(rc == 1 and any("compose default" in l and "DATABASE_URL" in l for l in out),
           "positive: ${VAR-default} (no colon) for a required key FAILs", out)

        (root / "docker-compose.yml").write_text(
            "services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL}\n      API_KEY: ${API_KEY}\n"
        )
        (root / "dart_define.example.json").write_text("{not json\n")
        rc, out = check(root)
        ok(rc == 1 and any("invalid JSON" in l for l in out),
           "positive: invalid dart-define JSON FAILs", out)

        (root / "dart_define.example.json").write_text('{"API_KEY": "", "NEW_DART": ""}\n')
        rc, out = check(root)
        ok(rc == 1 and any("NEW_DART" in l for l in out),
           "positive: dart-define key missing from .env.example FAILs", out)

        (root / "dart_define.example.json").unlink()
        (root / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        (root / "docker-compose.yml").write_text(
            "services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL}\n      API_KEY: ${API_KEY}\n"
        )
        (root / ".env.staging.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        (root / ".env.production.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        (root / ".env.production").write_text("SECRET=do-not-read\nEXTRA=1\n")
        rc, out = check(root)
        ok(rc == 0 and not any("env-drift" in l for l in out) and not any("SECRET" in l or "EXTRA" in l for l in out),
           "negative: matching local/staging/prod examples; real .env.production ignored", out)

        (root / ".env.production.example").write_text("DATABASE_URL=\n")
        rc, out = check(root)
        ok(rc == 1 and any("env-drift" in l and "API_KEY" in l for l in out),
           "positive: staging/prod example key drift FAILs", out)

        (root / "docker-compose.yml").unlink()
        (root / "app" / "settings.py").unlink()
        (root / ".env.example").unlink()
        (root / ".env.staging.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        (root / ".env.production.example").write_text("DATABASE_URL=\nAPI_KEY=\n")
        rc, out = check(root)
        ok(rc == 0 and not any(l.startswith("FAIL") for l in out),
           "negative: no Docker/Terraform, aligned staging/prod examples", out)

    with contextlib.redirect_stderr(io.StringIO()):
        ok(main(["--root"]) == 2, "positive: --root without value exits 2")

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    root = Path(".")
    if argv and argv[0] == "--selftest":
        return selftest()
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("ERROR: --root requires a value", file=sys.stderr)
            return 2
        root = Path(argv[i + 1])
    rc, lines = check(root)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
