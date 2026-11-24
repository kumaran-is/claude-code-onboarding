#!/usr/bin/env python3
"""Env-key parity (presence only, never values) between `.env.example` and what the project reads.

Required keys (FAIL when absent from `.env.example`): `${VAR}` / `${VAR:?...}` in docker-compose files (a
`${VAR:-default}` is optional), `os.environ["X"]`, and fields of Pydantic `BaseSettings` classes with no default
(`x: str`, `x: str = Field(min_length=32)`; upper-cased, a literal `env_prefix` honoured).
Optional reads (WARN only): `os.getenv("X")`, `os.environ.get("X")`, `process.env.X`, `process.env["X"]`; platform
variables (`CI`, `NODE_ENV`, `HOME`, ...) are ignored. WARN also: a `.env.example` key nothing reads (stale).
Never opens `.env` itself: only `.env.example` (or `--example PATH`).

Usage: check_env_parity.py [ROOT] [--example .env.example]  |  --selftest
Exit: 0 clean, 1 findings, 2 cannot run (no .env.example).
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 10):  # `X | None` annotations below need 3.10; say so instead of a TypeError
    sys.exit(f"{Path(__file__).name} needs Python 3.10+, found {sys.version.split()[0]}")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".dart_tool", "__pycache__", ".claude"}
SRC_EXT = {".py", ".ts", ".js", ".mjs", ".cjs"}
COMPOSE_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(:?[-?+][^}]*)?\}")
REQUIRED_RES = [re.compile(r"os\.environ\[\s*['\"]([A-Z_][A-Z0-9_]*)['\"]\s*\]")]
OPTIONAL_RES = [re.compile(p) for p in (
    r"os\.(?:getenv|environ\.get)\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]",
    r"process\.env\.([A-Z_][A-Z0-9_]*)",
    r"process\.env\[\s*['\"]([A-Z_][A-Z0-9_]*)['\"]\s*\]",
)]
PLATFORM = {"CI", "NODE_ENV", "HOME", "PATH", "PWD", "USER", "SHELL", "TZ", "LANG", "TERM", "HOSTNAME", "TMPDIR",
            "GITHUB_ACTIONS", "VITEST", "JEST_WORKER_ID", "PYTEST_CURRENT_TEST", "DEBUG"}
SETTINGS_CLASS_RE = re.compile(r"^class\s+\w+\([^)]*\bBaseSettings\b[^)]*\)\s*:", re.M)
FIELD_RE = re.compile(r"^\s{4}([a-z_][a-z0-9_]*)\s*:\s*([^=\n]+?)\s*(?:=\s*(.+))?$", re.M)


def field_required(default: str | None) -> bool:
    """`x: str` and `x: str = Field(min_length=3)` are required; any literal default or default= is not."""
    if default is None:
        return True
    d = default.strip()
    if not d.startswith("Field("):
        return False
    inner = d[len("Field("):].lstrip()
    return not (re.search(r"\bdefault(?:_factory)?\s*=", inner) or (inner and not inner.startswith(")") and
                                                                  not re.match(r"[A-Za-z_]\w*\s*=", inner)
                                                                  and not inner.startswith("...")))
PREFIX_RE = re.compile(r"env_prefix\s*=\s*['\"]([A-Za-z0-9_]*)['\"]")


def walk(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS):
            yield p


def example_keys(path: Path) -> set[str]:
    keys = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            keys.add(m.group(1))
    return keys


def read_keys(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(required key -> where, optional key -> where)."""
    found: dict[str, str] = {}
    optional: dict[str, str] = {}
    for p in walk(root):
        rel = str(p.relative_to(root))
        if p.name.startswith(("docker-compose", "compose")) and p.suffix in (".yml", ".yaml"):
            for m in COMPOSE_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
                if not (m.group(2) or "").lstrip(":").startswith(("-", "+")):
                    found.setdefault(m.group(1), rel)
        elif p.suffix in SRC_EXT and ".example" not in p.name:
            text = p.read_text(encoding="utf-8", errors="replace")
            for rx in REQUIRED_RES:
                for m in rx.finditer(text):
                    found.setdefault(m.group(1), rel)
            for rx in OPTIONAL_RES:
                for m in rx.finditer(text):
                    if m.group(1) not in PLATFORM:
                        optional.setdefault(m.group(1), rel)
            if p.suffix == ".py":
                for cls in SETTINGS_CLASS_RE.finditer(text):
                    body = re.split(r"^\S", text[cls.end():], maxsplit=1, flags=re.M)[0]
                    prefix = (PREFIX_RE.search(body) or [None, ""])[1].upper()
                    for m in FIELD_RE.finditer(body):
                        if m.group(1) != "model_config" and field_required(m.group(3)):
                            found.setdefault(prefix + m.group(1).upper(), rel)
    return found, {k: v for k, v in optional.items() if k not in found}


def used_anywhere(root: Path, keys: set[str]) -> set[str]:
    used = set()
    for p in walk(root):
        if p.name.startswith(".env") or p.suffix not in SRC_EXT | {".yml", ".yaml", ".tf", ".toml", ".json", ".sh"}:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        used |= {k for k in keys - used if re.search(rf"\b(?:{k}|{k.lower()})\b", text)}
    return used


def check(root: Path, example: Path) -> tuple[int, list[str]]:
    if not example.is_file():
        return 2, [f"BLOCKED: {example} not found (nothing to compare against)"]
    have = example_keys(example)
    need, optional = read_keys(root)
    lines = [f"FAIL missing from {example.name}: {k} (read in {src})" for k, src in sorted(need.items()) if k not in have]
    lines += [f"WARN optional key read but undocumented in {example.name}: {k} ({src})"
              for k, src in sorted(optional.items()) if k not in have]
    stale = have - set(need) - set(optional) - used_anywhere(root, have - set(need) - set(optional))
    lines += [f"WARN in {example.name} but never read: {k}" for k in sorted(stale)]
    lines.append(f"scanned: {len(have)} example key(s), {len(need)} required key(s), {len(optional)} optional read(s)")
    return (1 if any(l.startswith("FAIL") for l in lines) else 0), lines


def selftest() -> int:
    fails = 0

    def ok(cond: bool, label: str, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f" -> {detail}"))
        fails += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".env.example").write_text("DATABASE_URL=\nJWT_SECRET=\nLOG_LEVEL=info\n")
        (root / "docker-compose.yml").write_text("services:\n  api:\n    environment:\n      DATABASE_URL: ${DATABASE_URL}\n      LOG_LEVEL: ${LOG_LEVEL:-info}\n")
        (root / "app").mkdir()
        (root / "app" / "settings.py").write_text(
            "from pydantic_settings import BaseSettings\n\nclass Settings(BaseSettings):\n    jwt_secret: str\n    port: int = 8000\n")
        rc, out = check(root, root / ".env.example")
        ok(rc == 0 and not any(l.startswith(("FAIL", "WARN")) for l in out), "negative: matching keys are clean", out)
        (root / "app" / "worker.py").write_text("import os\nTOKEN = os.environ['STRIPE_API_KEY']\nX = os.getenv('DEBUG_SQL')\n")
        (root / "web.ts").write_text("const u = process.env.REDIS_URL; const e = process.env.NODE_ENV; const c = process.env.CI;\n")
        rc, out = check(root, root / ".env.example")
        text = "\n".join(out)
        ok(rc == 1 and "FAIL missing from .env.example: STRIPE_API_KEY" in text, "positive: os.environ[...] absent from .env.example FAILs", out)
        ok("WARN optional key read but undocumented in .env.example: REDIS_URL" in text, "positive: an undocumented optional read WARNs", out)
        ok(not any(l.startswith("FAIL") and ("REDIS_URL" in l or "DEBUG_SQL" in l) for l in out),
           "negative: getenv / process.env reads never FAIL", out)
        ok("NODE_ENV" not in text and " CI " not in text and ": CI" not in text, "negative: platform variables are ignored", out)
        (root / ".env.example").write_text("DATABASE_URL=\nJWT_SECRET=\nLOG_LEVEL=\nSTRIPE_API_KEY=\nREDIS_URL=\nDEBUG_SQL=\nOLD_FLAG=1\n")
        rc, out = check(root, root / ".env.example")
        ok(rc == 0 and any("WARN" in l and "OLD_FLAG" in l for l in out), "positive: an unread example key is a WARN, not a FAIL", out)
        (root / ".env").write_text("SECRET_ONLY_IN_DOTENV=x\n")
        rc, out = check(root, root / ".env.example")
        ok("SECRET_ONLY_IN_DOTENV" not in "\n".join(out), "the real .env is never read")
        (root / ".env.example").write_text("DATABASE_URL=\nLOG_LEVEL=\nSTRIPE_API_KEY=\nREDIS_URL=\nDEBUG_SQL=\n")
        rc, out = check(root, root / ".env.example")
        ok(rc == 1 and any("JWT_SECRET" in l and "settings.py" in l for l in out), "positive: a required BaseSettings field is detected", out)
        (root / "app" / "settings.py").write_text(
            "from pydantic import Field\nfrom pydantic_settings import BaseSettings, SettingsConfigDict\n\n"
            "class Settings(BaseSettings, frozen=True):\n    model_config = SettingsConfigDict(env_prefix='APP_')\n"
            "    jwt_secret: str = Field(min_length=32)\n    port: int = Field(default=8000)\n    region: str = 'eu'\n")
        rc, out = check(root, root / ".env.example")
        text = "\n".join(out)
        ok("FAIL missing from .env.example: APP_JWT_SECRET" in text and "APP_PORT" not in text and "APP_REGION" not in text,
           "positive: Field(min_length=...) is required; defaults are not; extra bases and env_prefix handled", out)
        rc, out = check(root, root / "missing.example")
        ok(rc == 2, "no .env.example -> BLOCKED (exit 2), never clean", out)
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--example", default=".env.example")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    root = Path(a.root).resolve()
    rc, lines = check(root, root / a.example)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
