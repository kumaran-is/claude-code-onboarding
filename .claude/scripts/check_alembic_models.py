#!/usr/bin/env python3
"""SQLAlchemy model <-> Alembic migration parity (static; advisory or CI).

`alembic check` / autogenerate compare the migrations with `target_metadata`, which only holds models whose
modules were imported when env.py built it. A model module nobody imports is invisible: autogenerate emits no
table and `alembic check` is green. This check does not import anything: it compares `__tablename__` values in
the source with tables created by migrations (`op.create_table("x"` / `op.rename_table(.., "x")`) minus dropped ones.

FAIL: a model table no migration creates (unregistered model or missing revision).
WARN: a table a migration creates that no model declares (raw table, or a deleted model without a drop).

Usage: check_alembic_models.py [ROOT] [--versions DIR]  |  --selftest
Exit: 0 clean, 1 findings, 2 cannot run (no versions directory or no models).
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 10):  # `X | None` annotations below need 3.10; say so instead of a TypeError
    sys.exit(f"{Path(__file__).name} needs Python 3.10+, found {sys.version.split()[0]}")

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", "tests", "test"}
TABLENAME_RE = re.compile(r"^\s+__tablename__\s*(?::\s*\w+\s*)?=\s*['\"]([\w.]+)['\"]", re.M)
CREATE_RE = re.compile(r"op\.create_table\(\s*['\"]([\w.]+)['\"]")
RENAME_RE = re.compile(r"op\.rename_table\(\s*['\"]([\w.]+)['\"]\s*,\s*['\"]([\w.]+)['\"]")
DROP_RE = re.compile(r"op\.drop_table\(\s*['\"]([\w.]+)['\"]")


OP_RE = re.compile(r"op\.(create_table|drop_table|rename_table)\(\s*['\"]([\w.]+)['\"](?:\s*,\s*['\"]([\w.]+)['\"])?")
REV_RE = re.compile(r"^(down_)?revision\s*(?::[^=]+)?=\s*['\"]?([\w-]+|None)['\"]?", re.M)


def ordered(files: list[Path]) -> list[Path]:
    """Linear revision order from `revision` / `down_revision`; unparseable or branched trees keep file order."""
    info = {}
    for f in files:
        ids = {bool(m.group(1)): m.group(2) for m in REV_RE.finditer(f.read_text(encoding="utf-8", errors="replace"))}
        if False in ids:
            info[ids[False]] = (ids.get(True, "None"), f)
    by_down = {down: rev for rev, (down, _) in info.items()}
    if len(info) != len(files) or len(by_down) != len(info) or "None" not in by_down:
        return files
    chain, cur = [], by_down["None"]
    while cur and cur in info and len(chain) <= len(info):
        chain.append(info[cur][1])
        cur = by_down.get(cur)
    return chain if len(chain) == len(files) else files


def upgrade_body(text: str) -> str:
    m = re.search(r"^def upgrade\(\)[^:]*:\n(.*?)(?=^def |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def find_versions(root: Path) -> Path | None:
    for cand in sorted(root.rglob("versions")):
        if cand.is_dir() and (cand.parent / "env.py").is_file() and not set(cand.relative_to(root).parts) & SKIP_DIRS:
            return cand
    return None


def check(root: Path, versions: Path | None) -> tuple[int, list[str]]:
    versions = versions or find_versions(root)
    if versions is None or not versions.is_dir():
        return 2, [f"BLOCKED: no Alembic versions directory (a 'versions/' next to env.py) under {root}"]
    models: dict[str, str] = {}
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if set(rel.parts[:-1]) & SKIP_DIRS or versions in p.parents:
            continue
        for m in TABLENAME_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            models.setdefault(m.group(1), f"{rel}")
    if not models:
        return 2, ["BLOCKED: no `__tablename__` found: nothing to compare"]
    created: set[str] = set()
    revisions = ordered(sorted(versions.glob("*.py")))
    for p in revisions:  # replayed in revision order, operations in source order within each upgrade()
        body = upgrade_body(p.read_text(encoding="utf-8", errors="replace"))
        for m in OP_RE.finditer(body):
            op, a, b = m.group(1), m.group(2), m.group(3)
            if op == "create_table":
                created.add(a)
            elif op == "drop_table":
                created.discard(a)
            elif b:
                created.discard(a)
                created.add(b)
    lines = [f"FAIL model table {t} ({src}) is created by no migration: import its module where target_metadata "
             f"is built (env.py / models/__init__.py), then `alembic revision --autogenerate`"
             for t, src in sorted(models.items()) if t not in created]
    lines += [f"WARN migrations create {t}, but no model declares it" for t in sorted(created - models.keys())]
    lines.append(f"scanned: {len(models)} model table(s), {len(revisions)} revision(s) in {versions.relative_to(root)}")
    return (1 if any(l.startswith("FAIL") for l in lines) else 0), lines


def selftest() -> int:
    fails = 0

    def ok(cond: bool, label: str, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f" -> {detail}"))
        fails += 0 if cond else 1

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app" / "models").mkdir(parents=True)
        (root / "alembic" / "versions").mkdir(parents=True)
        (root / "alembic" / "env.py").write_text("from app.models import Base\ntarget_metadata = Base.metadata\n")
        (root / "app" / "models" / "user.py").write_text("class User(Base):\n    __tablename__ = 'users'\n")
        (root / "alembic" / "versions" / "001_users.py").write_text(
            "def upgrade() -> None:\n    op.create_table('users', sa.Column('id'))\n\ndef downgrade() -> None:\n    op.drop_table('users')\n")
        rc, out = check(root, None)
        ok(rc == 0 and not any(l.startswith(("FAIL", "WARN")) for l in out), "negative: model and migration agree (downgrade drop ignored)", out)
        (root / "app" / "models" / "invoice.py").write_text("class Invoice(Base):\n    __tablename__: str = \"invoices\"\n")
        rc, out = check(root, None)
        ok(rc == 1 and any("invoices" in l and "invoice.py" in l for l in out), "positive: a model with no migration FAILs", out)
        (root / "alembic" / "versions" / "002_inv.py").write_text(
            "def upgrade():\n    op.create_table('invoice_old')\n    op.rename_table('invoice_old', 'invoices')\n    op.create_table('audit_raw')\n")
        rc, out = check(root, None)
        ok(rc == 0 and any(l.startswith("WARN") and "audit_raw" in l for l in out) and not any("invoice_old" in l for l in out),
           "rename is followed; a migration-only table WARNs", out)
        (root / "alembic" / "versions" / "003_drop.py").write_text("def upgrade():\n    op.drop_table('users')\n")
        rc, out = check(root, None)
        ok(rc == 1 and any("model table users" in l for l in out), "positive: a model whose table was dropped FAILs", out)
        (root / "tests").mkdir()
        (root / "tests" / "fixtures.py").write_text("class T(Base):\n    __tablename__ = 'only_in_tests'\n")
        ok("only_in_tests" not in "\n".join(check(root, None)[1]), "test-only models are ignored")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "models.py").write_text("class A(Base):\n    __tablename__ = 'events'\n")
        (root / "migrations" / "versions").mkdir(parents=True)
        (root / "migrations" / "env.py").write_text("")
        v = root / "migrations" / "versions"
        (v / "b_recreate.py").write_text("revision = 'r3'\ndown_revision = 'r2'\ndef upgrade():\n    op.create_table('events')\n")
        (v / "c_drop.py").write_text("revision = 'r2'\ndown_revision = 'r1'\ndef upgrade():\n    op.drop_table('events')\n")
        (v / "a_create.py").write_text("revision: str = 'r1'\ndown_revision: str | None = None\ndef upgrade():\n    op.create_table('events')\n")
        rc, out = check(root, None)
        ok(rc == 0, "dropped then re-created (file names out of revision order) is clean", out)
    with tempfile.TemporaryDirectory() as d:
        ok(check(Path(d), None)[0] == 2, "no Alembic setup -> BLOCKED, never clean")
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--versions")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    root = Path(a.root).resolve()
    rc, lines = check(root, (root / a.versions) if a.versions else None)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
