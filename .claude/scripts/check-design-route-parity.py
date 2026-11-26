#!/usr/bin/env python3
"""Same-PR screen/route ↔ DESIGN.md / inventory parity.

SSOT order (first source that yields routes wins; do not invent a second map):
  1. DESIGN.md ## Screens (canonical path)
  2. docs/screen-inventory.md (Route/Path column)
  3. app-screen-map.json only if already present (legacy fallback)

No design-side routes → exit 2 NOT APPLICABLE. --require-map makes absence a FAIL.

Usage:
  check-design-route-parity.py [--root DIR] [--require-map] [--selftest]

Exit: 0 ok, 1 FAIL, 2 NOT APPLICABLE / broken selftest.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

DESIGN_MD_CANDIDATES = ("DESIGN.md", "docs/DESIGN.md", "design/DESIGN.md")
INVENTORY_CANDIDATES = (
    "docs/screen-inventory.md",
    "docs/design/screen-inventory.md",
    "screen-inventory.md",
)
MAP_CANDIDATES = (
    "app-screen-map.json",
    "docs/design/app-screen-map.json",
    "docs/wireframes/app-screen-map.json",
    "docs/screens/app-screen-map.json",
)
SCREENS_H2 = re.compile(r"^##\s+Screens\b.*$", re.M | re.I)
NEXT_H2 = re.compile(r"^##\s+", re.M)
ROUTE_TICK = re.compile(r"`(/[A-Za-z0-9_\-/{}.]+)`")
ROUTE_KV = re.compile(r"\broute:\s*`?(/[A-Za-z0-9_\-/{}.]+)`?", re.I)
SKIP = {
    "node_modules", ".git", ".dart_tool", "build", "dist", ".angular", "coverage",
    ".next", "out", ".claude", "Pods", ".gradle", "test", "tests", "__tests__", "e2e",
}
GO_ROUTE = re.compile(r"""GoRoute\s*\(\s*path:\s*['\"]([^'\"]+)['\"]""")
NG_PATH = re.compile(r"""path:\s*['\"]([^'\"]+)['\"]""")
REACT_PATH = re.compile(r"""\bpath:\s*['\"]([^'\"]+)['\"]""")


def walk(root: Path):
    root = root.resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).parts
        if set(rel[:-1]) & SKIP:
            continue
        yield p


def find_map(root: Path) -> Path | None:
    for rel in MAP_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    return None


def screens_section(text: str) -> str:
    m = SCREENS_H2.search(text)
    if not m:
        return ""
    rest = text[m.end() :]
    n = NEXT_H2.search(rest)
    return rest[: n.start()] if n else rest


def routes_from_table(text: str) -> set[str]:
    routes: set[str] = set()
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if not lines:
        return routes
    headers = [c.strip().lower() for c in lines[0].strip().strip("|").split("|")]
    idx = next((i for i, h in enumerate(headers) if h in {"route", "path", "url"}), None)
    if idx is None:
        return routes
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not cells or idx >= len(cells) or set(cells[0]) <= set("-: "):
            continue
        val = cells[idx].strip().strip("`").split()[0] if cells[idx].strip() else ""
        if val.startswith("/"):
            routes.add(normalize(val))
    return routes


def routes_from_prose(text: str) -> set[str]:
    out = {normalize(m.group(1)) for m in ROUTE_TICK.finditer(text)}
    out |= {normalize(m.group(1)) for m in ROUTE_KV.finditer(text)}
    return out


def design_routes(root: Path) -> tuple[set[str], str]:
    """First source that yields routes wins. Empty → no SSOT yet."""
    for rel in DESIGN_MD_CANDIDATES:
        p = root / rel
        if not p.is_file():
            continue
        section = screens_section(p.read_text(encoding="utf-8", errors="replace"))
        found = routes_from_table(section) | routes_from_prose(section)
        if found:
            return found, rel
        break
    for rel in INVENTORY_CANDIDATES:
        p = root / rel
        if not p.is_file():
            continue
        found = routes_from_table(p.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found, rel
        break
    mapping = find_map(root)
    if mapping is not None:
        return map_routes(mapping), str(mapping.relative_to(root))
    return set(), ""


def map_routes(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("screens") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            route = row.get("route") or row.get("path")
            if route:
                out.add(normalize(str(route)))
        elif isinstance(row, str):
            out.add(normalize(row))
    return out


def normalize(route: str) -> str:
    r = route.strip()
    if not r.startswith("/"):
        r = "/" + r
    if r != "/" and r.endswith("/"):
        r = r[:-1]
    return r


def code_routes(root: Path) -> set[str]:
    found: set[str] = set()
    for p in walk(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".dart":
            found |= {normalize(m.group(1)) for m in GO_ROUTE.finditer(text)}
        elif p.suffix in {".ts", ".js"} and "route" in p.name.lower():
            found |= {normalize(m.group(1)) for m in NG_PATH.finditer(text)}
        elif p.suffix in {".tsx", ".jsx", ".ts", ".js"} and (
            "route" in p.name.lower() or "router" in p.name.lower()
        ):
            found |= {normalize(m.group(1)) for m in REACT_PATH.finditer(text)}
    # Angular/React often use relative segments; keep as normalized paths.
    return {r for r in found if r and r != "/"} | ({"/"} if "/" in found else set())


def check(root: Path, require_map: bool = False) -> tuple[int, list[str]]:
    try:
        mapped, source = design_routes(root)
    except (json.JSONDecodeError, OSError) as e:
        return 1, [f"FAIL design source: {e}"]
    if not mapped:
        msg = "NOT APPLICABLE: no DESIGN.md ## Screens routes, screen-inventory Route column, or app-screen-map.json"
        return (1 if require_map else 2), [msg if not require_map else "FAIL " + msg[18:]]
    coded = code_routes(root)
    lines = [f"design: {source} ({len(mapped)} route(s))", f"code: {len(coded)} route(s)"]
    missing_in_map = sorted(coded - mapped)
    missing_in_code = sorted(mapped - coded)
    for r in missing_in_map:
        lines.append(f"FAIL route in code missing from design: {r}")
    for r in missing_in_code:
        lines.append(f"FAIL route in design missing from code: {r}")
    if missing_in_map or missing_in_code:
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
        ok(rc == 2, "negative: no map is NOT APPLICABLE", out)
        rc, out = check(root, require_map=True)
        ok(rc == 1, "positive: --require-map with no map FAILs", out)

        (root / "lib").mkdir()
        (root / "lib" / "router.dart").write_text(
            "GoRoute(\n  path: '/home',\n)\nGoRoute(path: '/settings');\n",
            encoding="utf-8",
        )
        (root / "docs").mkdir()
        (root / "docs" / "design").mkdir()
        (root / "docs" / "design" / "app-screen-map.json").write_text(
            json.dumps({"screens": [{"id": "home", "route": "/home"}, {"id": "settings", "route": "/settings"}]}),
            encoding="utf-8",
        )
        rc, out = check(root)
        ok(rc == 0, "negative: matching GoRoutes pass", out)

        (root / "lib" / "router.dart").write_text(
            "GoRoute(path: '/home');\nGoRoute(path: '/new');\n",
            encoding="utf-8",
        )
        rc, out = check(root)
        ok(rc == 1 and any("/new" in l for l in out), "positive: code route missing from map FAILs", out)
        ok(any("/settings" in l for l in out), "positive: map route missing from code FAILs", out)

        (root / "docs" / "design" / "app-screen-map.json").unlink()
        (root / "DESIGN.md").write_text(
            "# Design\n## Screens\n| id | route |\n|----|-------|\n| home | /home |\n| settings | /settings |\n## Motion\nNative.\n",
            encoding="utf-8",
        )
        (root / "lib" / "router.dart").write_text(
            "GoRoute(path: '/home');\nGoRoute(path: '/settings');\n",
            encoding="utf-8",
        )
        rc, out = check(root)
        ok(rc == 0 and any("DESIGN.md" in l for l in out), "negative: DESIGN.md Screens table matching routes passes", out)

        (root / "lib" / "router.dart").write_text("GoRoute(path: '/home');\nGoRoute(path: '/extra');\n", encoding="utf-8")
        rc, out = check(root)
        ok(rc == 1 and any("/extra" in l for l in out), "positive: code route missing from DESIGN.md FAILs", out)

        (root / "DESIGN.md").unlink()
        (root / "docs" / "screen-inventory.md").write_text(
            "| ID | Title | Route |\n|----|-------|-------|\n| S1 | Home | /home |\n| S2 | Settings | /settings |\n",
            encoding="utf-8",
        )
        (root / "lib" / "router.dart").write_text(
            "GoRoute(path: '/home');\nGoRoute(path: '/settings');\n",
            encoding="utf-8",
        )
        rc, out = check(root)
        ok(rc == 0 and any("screen-inventory" in l for l in out), "negative: inventory Route column matching routes passes", out)

        (root / "DESIGN.md").write_text(
            "# Design\n## Screens\n| id | route |\n|----|-------|\n| home | /home |\n",
            encoding="utf-8",
        )
        (root / "docs" / "design" / "app-screen-map.json").write_text(
            json.dumps({"screens": [{"id": "settings", "route": "/settings"}]}),
            encoding="utf-8",
        )
        (root / "lib" / "router.dart").write_text("GoRoute(path: '/home');\n", encoding="utf-8")
        rc, out = check(root)
        ok(rc == 0 and any("DESIGN.md" in l for l in out) and not any("/settings" in l and "FAIL" in l for l in out),
           "negative: DESIGN.md wins over stale json map", out)

        (root / "lib" / "router.dart").unlink()
        (root / "src").mkdir()
        (root / "src" / "app.routes.ts").write_text("export const routes = [{ path: 'home' }];\n", encoding="utf-8")
        rc, out = check(root)
        ok(rc == 0, "negative: Angular path in DESIGN.md matching code passes", out)

    with contextlib.redirect_stderr(io.StringIO()):
        ok(main(["--root"]) == 2, "positive: --root without value exits 2")

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    root = Path(".")
    require = False
    args = list(argv)
    if args and args[0] == "--selftest":
        return selftest()
    if "--require-map" in args:
        require = True
        args.remove("--require-map")
    if "--root" in args:
        i = args.index("--root")
        if i + 1 >= len(args):
            print("ERROR: --root requires a value", file=sys.stderr)
            return 2
        root = Path(args[i + 1])
    rc, lines = check(root, require_map=require)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
