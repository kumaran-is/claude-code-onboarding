#!/usr/bin/env python3
"""Discover language-native workspaces and recommend orchestration.

Read-only. Never creates nx.json, lockfiles, or MCP config.

  python3 discover_monorepo.py --root DIR
  python3 discover_monorepo.py --find-host DIR
  python3 discover_monorepo.py --selftest

Exit 0 on a successful report / passing selftest, 2 on usage or selftest failure.
Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

JS_HEAVY = 8  # expanded npm members; with nx.json => justified; without => candidate-needs-approval


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def has_dart_workspace(root: Path) -> bool:
    text = read(root / "pubspec.yaml")
    return bool(re.search(r"(?m)^workspace:\s*$", text) or re.search(r"(?m)^workspace:\s*\[", text))


def has_melos_pubspec(root: Path) -> bool:
    """True only for a YAML key `melos:`, not comments."""
    for raw in read(root / "pubspec.yaml").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if re.match(r"^melos:\s*$", line) or re.match(r"^melos:\s+\S", line):
            return True
        if re.match(r"^[ \t]+melos:\s", line):
            return True
    return False


def has_uv_workspace(root: Path) -> bool:
    return "[tool.uv.workspace]" in read(root / "pyproject.toml")


def _workspace_patterns(root: Path) -> list[str]:
    text = read(root / "package.json")
    patterns: list[str] = []
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        ws = data.get("workspaces") if isinstance(data, dict) else None
        if isinstance(ws, dict):
            ws = ws.get("packages") or []
        if isinstance(ws, list):
            patterns.extend(str(x) for x in ws)
    pnpm = read(root / "pnpm-workspace.yaml")
    if pnpm:
        for line in pnpm.splitlines():
            m = re.match(r'^[ \t]*-[ \t]+["\']?([^"\'#]+)["\']?', line)
            if m:
                patterns.append(m.group(1).strip())
    return patterns


def expand_workspace_members(root: Path, patterns: list[str]) -> list[str]:
    """Expand npm/pnpm workspace globs (`packages/*`) into directories that have package.json."""
    seen: list[str] = []
    for pat in patterns:
        if any(ch in pat for ch in "*?["):
            for hit in sorted(root.glob(pat)):
                if hit.is_dir() and (hit / "package.json").is_file():
                    rel = str(hit.relative_to(root))
                    if rel not in seen:
                        seen.append(rel)
        elif pat and pat not in seen:
            seen.append(pat)
    return seen


def npm_members(root: Path) -> list[str]:
    return expand_workspace_members(root, _workspace_patterns(root))


UNSAFE_CACHE_NAMES = (
    "codegen",
    "build_runner",
    "openapi",
    "openapi:gen",
    "generate",
    "gen",
    "migrate",
    "db:migrate",
    "docker",
    "image",
)


def nx_cache_unsafe_targets(root: Path) -> list[str]:
    """Advisory: target names whose configs mention cache:true. Plugins may still cache by default.

    This is not a full Nx project-graph parse. A clean list does not prove cache safety.
    """
    blobs: list[str] = []
    candidates = [root / "nx.json", *root.glob("**/project.json")]
    for path in candidates:
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        if path.is_file() and path.stat().st_size < 2_000_000:
            blobs.append(read(path))
    joined = "\n".join(blobs)
    unsafe: list[str] = []
    for name in UNSAFE_CACHE_NAMES:
        if re.search(rf'"{re.escape(name)}"[\s\S]{{0,400}}"cache"\s*:\s*true', joined, re.I):
            unsafe.append(name)
    return unsafe


def is_workspace_host(path: Path) -> bool:
    return (
        has_dart_workspace(path)
        or has_uv_workspace(path)
        or bool(_workspace_patterns(path))
        or (path / "nx.json").is_file()
        or (path / "turbo.json").is_file()
        or (path / "pnpm-workspace.yaml").is_file()
    )


def find_host(start: Path) -> Path | None:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        if is_workspace_host(cur):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def recommend(detected: dict[str, object]) -> dict[str, object]:
    dart = bool(detected["dart_workspace"])
    melos = bool(detected["melos"])
    legacy = bool(detected["melos_legacy_yaml"])
    uv = bool(detected["uv_workspace"])
    npm = bool(detected["npm_workspaces"])
    nx = bool(detected["nx"])
    make = bool(detected["makefile"])
    task = bool(detected["taskfile"])
    n_npm = int(detected["npm_member_count"])
    turbo = bool(detected["turbo"])
    pnpm = bool(detected["pnpm_workspace"])
    pms: list[str] = []
    reasons: list[str] = []

    if dart:
        pms.append("dart-workspaces")
        reasons.append("Dart pub workspace is the package manager for Flutter/Dart")
        if melos:
            pms.append("melos")
            reasons.append("Melos already owns Flutter scoped scripts / dependents")
        else:
            reasons.append("Two or more Dart packages: add Melos 7+ on the root pubspec (default)")
    if legacy:
        reasons.append("melos.yaml is legacy Melos 6; migrate config into root pubspec.yaml (Melos 7+)")
    if uv:
        pms.append("uv")
        reasons.append("uv workspace is the package manager for Python")
    if npm:
        pms.append("pnpm" if pnpm and "package-lock.json" not in detected["lockfiles"] else "npm")
        reasons.append("npm/pnpm workspaces are the package manager for Angular/TypeScript/MCP")

    js_heavy = n_npm >= JS_HEAVY and not dart
    if nx:
        nx_verdict = "justified" if js_heavy else "keep"
        reasons.append(
            "nx.json exists — keep Nx; do not rip it out. Flutter stays on Melos if present."
            if nx_verdict == "keep"
            else "nx.json exists and JS/TS workspace is large — Nx is justified around npm only"
        )
    elif js_heavy and not uv:
        nx_verdict = "candidate-needs-approval"
        reasons.append(
            "JS/TS workspace is large and has no nx.json — Nx is a candidate only; ask the human "
            "(measured CI cost) before CC_NX_INIT=1. Do not add it unsolicited."
        )
    else:
        nx_verdict = "do-not-add"
        reasons.append("No nx.json — do not introduce Nx; language-native workspaces + Makefile/Taskfile")

    orchestrator = "none"
    if nx:
        orchestrator = "nx"
        if dart or uv:
            reasons.append("Nx must not become the Dart or uv package manager; Makefile may still own compose/release")
    elif turbo:
        orchestrator = "turbo"
        reasons.append("turbo.json is present — keep Turbo for JS tasks; do not add Nx or a second JS orchestrator")
    elif make:
        orchestrator = "makefile"
        reasons.append("Makefile is the polyglot task orchestrator")
    elif task:
        orchestrator = "taskfile"
        reasons.append("Taskfile is the polyglot task orchestrator")
    elif dart or uv or npm:
        orchestrator = "makefile-or-taskfile"
        reasons.append("Add a lightweight Makefile/Taskfile only if cross-language tasks appear")

    dart_owner = "melos" if melos else ("dart-workspaces" if dart else "none")
    js_owner = "nx" if nx else ("npm-workspaces" if npm else "none")
    py_owner = "uv-or-make" if uv else "none"

    return {
        "package_managers": pms,
        "orchestrator": orchestrator,
        "nx": nx_verdict,
        "affected_owners": {"dart": dart_owner, "javascript": js_owner, "python": py_owner},
        "mcp": {"nx_mcp": "product-repo-only" if nx else "skip", "melos_mcp": "skip"},
        "reasons": reasons,
        "join": {
            "dart": dart,
            "uv": uv,
            "npm": npm,
        },
        "nx_cache_advisory": True,
    }


def discover(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        die(f"not a directory: {root}")
    npm = npm_members(root)
    detected: dict[str, object] = {
        "dart_workspace": has_dart_workspace(root),
        "melos": has_melos_pubspec(root),
        "melos_legacy_yaml": (root / "melos.yaml").is_file(),
        "uv_workspace": has_uv_workspace(root),
        "npm_workspaces": bool(npm),
        "npm_member_count": len(npm),
        "nx": (root / "nx.json").is_file(),
        "turbo": (root / "turbo.json").is_file(),
        "pnpm_workspace": (root / "pnpm-workspace.yaml").is_file(),
        "makefile": (root / "Makefile").is_file(),
        "taskfile": any(
            (root / name).is_file() for name in ("Taskfile.yml", "Taskfile.yaml", "Taskfile.dist.yml")
        ),
        "lockfiles": [
            p.name
            for p in (
                root / "pubspec.lock",
                root / "uv.lock",
                root / "package-lock.json",
                root / "pnpm-lock.yaml",
            )
            if p.is_file()
        ],
        "nx_cache_unsafe": nx_cache_unsafe_targets(root),
        "nx_cache_note": "advisory: not a full Nx graph; inferred plugin cache is invisible here",
    }
    rec = recommend(detected)
    return {"root": str(root), "detected": detected, "recommendation": rec}


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def fixture_flutter(root: Path) -> None:
    write(
        root / "pubspec.yaml",
        "name: ws\nworkspace:\n  - apps/tenant\ndev_dependencies:\n  melos: 8.10.1\nmelos:\n  scripts:\n    analyze:\n      exec: dart analyze .\n",
    )
    write(root / "apps/tenant/pubspec.yaml", "name: tenant\nresolution: workspace\nversion: 0.1.0+1\n")
    write(root / "pubspec.lock", "# lock\n")


def fixture_npm(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps({"name": "web-ws", "private": True, "workspaces": ["web/admin", "web/shared"]}, indent=2),
    )
    write(root / "web/admin/package.json", json.dumps({"name": "admin", "version": "0.1.0"}))
    write(root / "package-lock.json", '{"lockfileVersion": 3}\n')


def fixture_uv(root: Path) -> None:
    write(
        root / "pyproject.toml",
        '[project]\nname = "py-ws"\nrequires-python = ">=3.14"\n[tool.uv.workspace]\nmembers = ["services/api"]\n',
    )
    write(root / "services/api/pyproject.toml", '[project]\nname = "api"\nrequires-python = ">=3.14"\n')
    write(root / "uv.lock", "# lock\n")


def fixture_mixed(root: Path) -> None:
    fixture_flutter(root)
    fixture_npm(root)
    fixture_uv(root)
    write(root / "Makefile", "python-deps:\n\tuv sync --locked\n")
    write(root / "mcp/server/package.json", json.dumps({"name": "@ws/mcp", "version": "0.1.0"}))
    pkg = json.loads(read(root / "package.json"))
    pkg["workspaces"] = ["web/admin", "web/shared", "mcp/server"]
    write(root / "package.json", json.dumps(pkg, indent=2))


def fixture_mixed_no_nx(root: Path) -> None:
    fixture_mixed(root)


def fixture_js_nx(root: Path) -> None:
    members = [f"packages/p{i}" for i in range(JS_HEAVY)]
    write(
        root / "package.json",
        json.dumps({"name": "js-ws", "private": True, "workspaces": members}, indent=2),
    )
    write(root / "nx.json", json.dumps({"$schema": "./node_modules/nx/schemas/nx-schema.json", "targetDefaults": {}}))
    write(root / "package-lock.json", '{"lockfileVersion": 3}\n')


def fixture_js_glob(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps({"name": "js-glob", "private": True, "workspaces": ["packages/*"]}, indent=2),
    )
    for i in range(JS_HEAVY):
        write(root / f"packages/p{i}/package.json", json.dumps({"name": f"p{i}", "version": "0.1.0"}))
    write(root / "package-lock.json", '{"lockfileVersion": 3}\n')


def expect(cond: bool, label: str, fails: list[str]) -> None:
    if not cond:
        fails.append(label)


def selftest() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        flutter = base / "flutter"
        fixture_flutter(flutter)
        r = discover(flutter)
        rec = r["recommendation"]
        expect(r["detected"]["dart_workspace"] is True, "flutter: dart workspace", fails)
        expect(r["detected"]["melos"] is True, "flutter: melos", fails)
        expect("melos" in rec["package_managers"], "flutter: recommend melos", fails)
        expect(rec["nx"] == "do-not-add", "flutter: no nx", fails)
        expect(rec["affected_owners"]["dart"] == "melos", "flutter: dart owner melos", fails)
        expect(rec["mcp"]["nx_mcp"] == "skip", "flutter: skip nx mcp", fails)
        expect(rec["mcp"]["melos_mcp"] == "skip", "flutter: skip melos mcp", fails)

        npm = base / "npm"
        fixture_npm(npm)
        r = discover(npm)
        rec = r["recommendation"]
        expect(r["detected"]["npm_workspaces"] is True, "npm: workspaces", fails)
        expect(rec["nx"] == "do-not-add", "npm: two members is not Nx", fails)
        expect(rec["affected_owners"]["javascript"] == "npm-workspaces", "npm: js owner", fails)
        expect("pubspec.lock" not in r["detected"]["lockfiles"], "npm: no dart lock", fails)

        uv = base / "uv"
        fixture_uv(uv)
        r = discover(uv)
        rec = r["recommendation"]
        expect(r["detected"]["uv_workspace"] is True, "uv: workspace", fails)
        expect("uv" in rec["package_managers"], "uv: recommend uv", fails)
        expect(rec["nx"] == "do-not-add", "uv: no nx", fails)
        expect(rec["join"]["uv"] is True, "uv: join hint", fails)

        mixed = base / "mixed"
        fixture_mixed(mixed)
        r = discover(mixed)
        rec = r["recommendation"]
        expect(r["detected"]["dart_workspace"] and r["detected"]["uv_workspace"] and r["detected"]["npm_workspaces"], "mixed: all three PMs", fails)
        expect(rec["orchestrator"] == "makefile", "mixed: makefile orchestrator", fails)
        expect(rec["nx"] == "do-not-add", "mixed: do not add Nx", fails)
        expect(sorted(rec["package_managers"]) == sorted(["dart-workspaces", "melos", "uv", "npm"]), "mixed: PMs", fails)
        expect(r["detected"]["npm_member_count"] == 3, "mixed: mcp joined npm workspaces", fails)

        no_nx = base / "no-nx"
        fixture_mixed_no_nx(no_nx)
        rec = discover(no_nx)["recommendation"]
        expect(rec["nx"] == "do-not-add", "existing mixed: never introduce Nx", fails)
        expect((no_nx / "nx.json").is_file() is False, "existing mixed: no nx.json written", fails)

        js_nx = base / "js-nx"
        fixture_js_nx(js_nx)
        r = discover(js_nx)
        rec = r["recommendation"]
        expect(r["detected"]["nx"] is True, "js-nx: nx present", fails)
        expect(int(r["detected"]["npm_member_count"]) >= JS_HEAVY, "js-nx: heavy", fails)
        expect(rec["nx"] == "justified", "js-nx: Nx justified", fails)
        expect(rec["orchestrator"] == "nx", "js-nx: nx orchestrator", fails)
        expect(rec["mcp"]["nx_mcp"] == "product-repo-only", "js-nx: nx mcp only in product repo", fails)
        expect(r["detected"]["dart_workspace"] is False, "js-nx: isolation no dart", fails)

        unsafe = base / "unsafe-cache"
        fixture_js_nx(unsafe)
        write(
            unsafe / "nx.json",
            json.dumps({"targetDefaults": {}, "codegen": {"cache": True}, "openapi": {"cache": True}}),
        )
        r = discover(unsafe)
        expect("codegen" in r["detected"]["nx_cache_unsafe"], "cache: codegen flagged", fails)
        expect("openapi" in r["detected"]["nx_cache_unsafe"], "cache: openapi flagged", fails)

        versions = base / "versions"
        fixture_flutter(versions)
        write(versions / "apps/tenant/pubspec.yaml", "name: tenant\nresolution: workspace\nversion: 0.93.2+147\n")
        write(versions / "apps/landlord/pubspec.yaml", "name: landlord\nresolution: workspace\nversion: 0.80.2+108\n")
        pub = read(versions / "pubspec.yaml")
        write(versions / "pubspec.yaml", pub.replace("- apps/tenant", "- apps/tenant\n  - apps/landlord"))
        r = discover(versions)
        expect(r["recommendation"]["nx"] == "do-not-add", "independent versions: still no Nx", fails)
        t = read(versions / "apps/tenant/pubspec.yaml")
        l = read(versions / "apps/landlord/pubspec.yaml")
        expect("0.93.2+147" in t and "0.80.2+108" in l, "independent versions preserved in fixtures", fails)

        globbed = base / "js-glob"
        fixture_js_glob(globbed)
        r = discover(globbed)
        rec = r["recommendation"]
        expect(int(r["detected"]["npm_member_count"]) == JS_HEAVY, "glob: packages/* expands to 8", fails)
        expect(rec["nx"] == "candidate-needs-approval", "glob: no nx.json → candidate, not do-not-add", fails)
        expect(rec["orchestrator"] != "nx", "glob: candidate is not already on Nx", fails)

        comment = base / "melos-comment"
        write(comment / "pubspec.yaml", "name: ws\nworkspace:\n  - apps/a\n# melos: do not treat comments as config\n")
        write(comment / "apps/a/pubspec.yaml", "name: a\nresolution: workspace\n")
        r = discover(comment)
        expect(r["detected"]["melos"] is False, "comment: # melos: is not a key", fails)

        turbo = base / "turbo"
        fixture_npm(turbo)
        write(turbo / "turbo.json", '{"$schema":"https://turbo.build/schema.json","tasks":{}}\n')
        rec = discover(turbo)["recommendation"]
        expect(rec["orchestrator"] == "turbo", "turbo: keep turbo", fails)
        expect(rec["nx"] == "do-not-add", "turbo: do not add Nx", fails)

        nested = mixed / "web" / "admin"
        host = find_host(nested)
        expect(host == mixed.resolve(), "find-host: nested npm member → mixed root", fails)
        host_file = find_host(nested / "package.json")
        expect(host_file == mixed.resolve(), "find-host: file path walks to host", fails)
        stray = base / "stray" / "empty"
        stray.mkdir(parents=True)
        expect(find_host(stray) is None, "find-host: no host returns None", fails)

        dist = base / "task-dist"
        fixture_uv(dist)
        write(dist / "Taskfile.dist.yml", "version: '3'\n")
        expect(discover(dist)["detected"]["taskfile"] is True, "taskfile: Taskfile.dist.yml counts", fails)

    if fails:
        print("selftest FAIL")
        for item in fails:
            print(f"  FAIL {item}")
        return 2
    print("selftest PASS")
    print("  ok   1 Flutter+Melos → dart-workspaces+melos, nx=do-not-add")
    print("  ok   2 npm workspaces → npm, nx=do-not-add")
    print("  ok   3 uv workspace → uv, nx=do-not-add")
    print("  ok   4 mixed Flutter+Angular+Python+MCP → makefile, nx=do-not-add")
    print("  ok   5 existing mixed without nx.json → do-not-add (no file written)")
    print("  ok   6 JS-heavy nx.json → justified, nx orchestrator, nx_mcp=product-repo-only")
    print("  ok   cache safety flags codegen/openapi cache:true")
    print("  ok   independent Flutter versions remain per-app")
    print("  ok   glob packages/* expands; no nx.json → candidate-needs-approval")
    print("  ok   # melos: comment is not Melos")
    print("  ok   turbo.json → keep turbo, do not add Nx")
    print("  ok   --find-host walks to the workspace host")
    print("  ok   Taskfile.dist.yml is a taskfile")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    root: Path | None = None
    find: Path | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = Path(argv[i + 1])
            i += 2
            continue
        if a == "--find-host" and i + 1 < len(argv):
            find = Path(argv[i + 1])
            i += 2
            continue
        die(f"unknown argument: {a}")
    if find is not None:
        if not find.exists():
            die(f"not found: {find}")
        host = find_host(find)
        if host is None:
            return 1
        print(str(host))
        return 0
    if root is None:
        die("usage: discover_monorepo.py --root DIR | --find-host DIR | --selftest")
    print(json.dumps(discover(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
