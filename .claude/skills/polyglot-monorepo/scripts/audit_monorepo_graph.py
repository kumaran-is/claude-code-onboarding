#!/usr/bin/env python3
"""Fail-closed Nx/Melos project-graph audit (MONO-ARCH-001).

  python3 audit_monorepo_graph.py --root DIR --expect expect.json
  python3 audit_monorepo_graph.py --graph-file graph.json --nx-json nx.json --expect expect.json
  python3 audit_monorepo_graph.py --selftest

Exit 0 PASS, 2 FAIL/usage. Stdlib only. Never writes nx.json into a product repo.
Does not assume JS import inference covers Python, Java, or Flutter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

NEVER_CACHE_DEFAULT = ("deploy", "migrate", "release", "docker-push")
GENERATED_DEFAULT = ("codegen", "generate", "openapi", "build_runner", "protobuf", "gen")
FLUTTER_BRIDGE_NAMES = ("flutter-workspace", "flutter_workspace")


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def load_json(path: Path) -> Any:
    text = read(path)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_graph(data: Any) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    if not isinstance(data, dict):
        return {}, {}
    g = data.get("graph") if isinstance(data.get("graph"), dict) else data
    nodes = g.get("nodes") or g.get("projects") or {}
    deps = g.get("dependencies") or {}
    if not isinstance(nodes, dict):
        nodes = {}
    if not isinstance(deps, dict):
        deps = {}
    return nodes, deps


def project_names(nodes: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key, val in nodes.items():
        if isinstance(val, dict):
            names.add(str(val.get("name") or key))
        else:
            names.add(str(key))
    return names


def node_data(nodes: dict[str, Any], name: str) -> dict[str, Any]:
    raw = nodes.get(name)
    if isinstance(raw, dict):
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        return data if isinstance(data, dict) else {}
    return {}


def edge_pairs(deps: dict[str, list[dict[str, Any]]]) -> set[tuple[str, str]]:
    """Return (consumer, dependency) pairs."""
    out: set[tuple[str, str]] = set()
    for consumer, items in deps.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            src = str(item.get("source") or consumer)
            tgt = item.get("target") or item.get("targetName")
            if tgt:
                out.add((src, str(tgt)))
    return out


def collect_targets(nodes: dict[str, Any], nx_json: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map 'project:target' -> target config (merged with targetDefaults by name)."""
    defaults = {}
    if isinstance(nx_json, dict):
        td = nx_json.get("targetDefaults") or {}
        if isinstance(td, dict):
            defaults = td
    found: dict[str, dict[str, Any]] = {}
    for name in project_names(nodes):
        data = node_data(nodes, name)
        targets = data.get("targets") or {}
        if not isinstance(targets, dict):
            continue
        for tname, tcfg in targets.items():
            merged: dict[str, Any] = {}
            if isinstance(defaults.get(tname), dict):
                merged.update(defaults[tname])
            if isinstance(tcfg, dict):
                merged.update(tcfg)
            found[f"{name}:{tname}"] = merged
    if isinstance(nx_json, dict):
        for tname, tcfg in defaults.items():
            if isinstance(tcfg, dict):
                found.setdefault(f"*:{tname}", tcfg)
    return found


def cache_flag(cfg: dict[str, Any]) -> bool | None:
    if "cache" in cfg:
        return bool(cfg["cache"])
    opts = cfg.get("options")
    if isinstance(opts, dict) and "cache" in opts:
        return bool(opts["cache"])
    return None


def inputs_blob(cfg: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("inputs", "outputs"):
        val = cfg.get(key)
        if val is not None:
            parts.append(json.dumps(val))
    opts = cfg.get("options")
    if isinstance(opts, dict):
        for key in ("inputs", "outputs"):
            if key in opts:
                parts.append(json.dumps(opts[key]))
    return "\n".join(parts)


def is_side_effect_target(tname: str, names: list[str]) -> bool:
    t = tname.lower().replace("_", "-")
    for n in names:
        n = n.lower()
        if t == n or t.startswith(n + ":") or t.startswith(n + "-") or t.endswith("-" + n):
            return True
        if n == "docker-push" and "docker" in t and "push" in t:
            return True
        if n in {"deploy", "migrate"} and n in t:
            return True
        if n == "release" and (t == "release" or t.startswith("release-") or t.startswith("release:")):
            return True
    return False


def is_generated_target(tname: str, names: list[str]) -> bool:
    t = tname.lower().replace("_", "-")
    for n in names:
        n = n.lower()
        if t == n or t.startswith(n + ":") or t.startswith(n + "-") or n in t:
            return True
    return False


def flutter_bridge_keys(nodes: dict[str, Any], declared: str | None) -> list[str]:
    """Node keys whose project name is the Flutter bridge (duplicate names still count)."""
    keys: list[str] = []
    for key, val in nodes.items():
        name = str(val.get("name") or key) if isinstance(val, dict) else str(key)
        if name in FLUTTER_BRIDGE_NAMES or (declared and name == declared):
            keys.append(str(key))
    return keys


def audit(
    nodes: dict[str, Any],
    deps: dict[str, list[dict[str, Any]]],
    expect: dict[str, Any],
    nx_json: dict[str, Any] | None,
) -> dict[str, Any]:
    failures: list[str] = []
    names = project_names(nodes)
    edges = edge_pairs(deps)
    targets = collect_targets(nodes, nx_json)

    expected_projects = [str(p) for p in expect.get("projects") or []]
    if not expected_projects:
        failures.append("expect.projects is empty; refuse fail-open")
    for proj in expected_projects:
        if proj not in names:
            failures.append(f"missing project: {proj}")

    expected_edges = expect.get("edges") or []
    for item in expected_edges:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            failures.append(f"malformed edge: {item!r}")
            continue
        pair = (str(item[0]), str(item[1]))
        if pair not in edges:
            failures.append(f"missing edge: {pair[0]} -> {pair[1]}")

    declared = expect.get("flutter_bridge")
    declared_s = str(declared) if declared else None
    bridge_keys = flutter_bridge_keys(nodes, declared_s)
    if declared_s:
        if declared_s not in names and not bridge_keys:
            failures.append(f"flutter bridge missing from graph: {declared_s}")
        if len(bridge_keys) > 1:
            failures.append(f"duplicate Flutter bridge projects: {bridge_keys}")
        contract_deps = [
            str(e[1])
            for e in expected_edges
            if isinstance(e, (list, tuple)) and len(e) == 2 and str(e[0]) == declared_s
        ]
        for dep in contract_deps:
            if (declared_s, dep) not in edges:
                failures.append(f"flutter bridge not connected to {dep}")
        for key, cfg in targets.items():
            if key.startswith(declared_s + ":") and cache_flag(cfg) is not False:
                failures.append(f"flutter bridge task must set cache false: {key}")
    bridges = bridge_keys

    py_projects = [str(p) for p in expect.get("python_projects") or []]
    if py_projects:
        py_edges = [e for e in expected_edges if isinstance(e, (list, tuple)) and e[0] in py_projects and e[1] in py_projects]
        present = [(str(a), str(b)) in edges for a, b in py_edges] if py_edges else []
        if not py_edges:
            failures.append("python projects listed but no explicit edges (plugin name is not proof)")
        elif not all(present):
            failures.append("python workspace dependencies missing from graph")

    extra_never = [str(x) for x in expect.get("never_cache") or []]
    never_cache = list(dict.fromkeys([*NEVER_CACHE_DEFAULT, *extra_never]))
    extra_gen = [str(x) for x in expect.get("generated_targets") or []]
    generated = list(dict.fromkeys([*GENERATED_DEFAULT, *extra_gen]))
    for key, cfg in targets.items():
        tname = key.split(":", 1)[-1]
        flag = cache_flag(cfg)
        if is_side_effect_target(tname, never_cache) and flag is not False:
            failures.append(f"side-effect task must set cache false: {key}")
        if is_generated_target(tname, generated) and flag is not False:
            failures.append(f"generated-code task must default cache false: {key}")

    for tname in never_cache:
        wildcard = targets.get(f"*:{tname}")
        if isinstance(wildcard, dict) and cache_flag(wildcard) is not False:
            # flag project-less default
            if not any(k.endswith(f":{tname}") and k != f"*:{tname}" for k in targets):
                failures.append(f"side-effect targetDefault must set cache false: {tname}")

    req_in = expect.get("required_inputs") or {}
    if isinstance(req_in, dict):
        for target, needles in req_in.items():
            cfg = targets.get(str(target))
            if not isinstance(cfg, dict):
                failures.append(f"required inputs target missing: {target}")
                continue
            blob = inputs_blob(cfg)
            for needle in needles or []:
                if str(needle) not in blob:
                    failures.append(f"missing input on {target}: {needle}")

    req_out = expect.get("required_outputs") or {}
    if isinstance(req_out, dict):
        for target, needles in req_out.items():
            cfg = targets.get(str(target))
            if not isinstance(cfg, dict):
                failures.append(f"required outputs target missing: {target}")
                continue
            blob = inputs_blob(cfg)
            for needle in needles or []:
                if str(needle) not in blob:
                    failures.append(f"missing output on {target}: {needle}")

    return {
        "verdict": "FAIL" if failures else "PASS",
        "failures": failures,
        "projects": sorted(names),
        "edges": sorted(edges),
        "flutter_bridges": bridges,
        "targets": sorted(targets),
    }


def run_nx_graph(root: Path, out: Path) -> tuple[bool, str]:
    env = os.environ.copy()
    env["NX_DAEMON"] = "false"
    env["NX_ISOLATE_PLUGINS"] = "false"
    cmd = ["npx", "--no-install", "nx", "graph", f"--file={out}"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"nx graph invocation failed: {exc}"
    if proc.returncode != 0 or not out.is_file():
        local = root / "node_modules" / ".bin" / "nx"
        if local.is_file():
            try:
                proc = subprocess.run(
                    [str(local), "graph", f"--file={out}"],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return False, f"nx graph invocation failed: {exc}"
        else:
            err = (proc.stderr or proc.stdout or "").strip()[:800]
            return False, f"local nx not installed (pin it in devDependencies): {err}"
    if proc.returncode != 0 or not out.is_file():
        err = (proc.stderr or proc.stdout or "").strip()[:800]
        return False, f"nx graph --file failed (exit {proc.returncode}): {err}"
    return True, str(out)


def run_melos_list(root: Path) -> tuple[bool, str, list[str]]:
    pubspec = read(root / "pubspec.yaml")
    flutter_dir = root
    def _has_melos_key(text: str) -> bool:
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if line.startswith("melos:") or line.endswith(" melos:"):
                return True
        return False

    if not _has_melos_key(pubspec):
        if (root / "flutter" / "pubspec.yaml").is_file():
            flutter_dir = root / "flutter"
            pubspec = read(flutter_dir / "pubspec.yaml")
    if not _has_melos_key(pubspec):
        return True, "melos not configured", []
    try:
        proc = subprocess.run(
            ["dart", "run", "melos", "list", "--json"],
            cwd=flutter_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"melos list failed: {exc}", []
    if proc.returncode != 0:
        try:
            proc = subprocess.run(
                ["dart", "run", "melos", "list"],
                cwd=flutter_dir,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"melos list failed: {exc}", []
        if proc.returncode != 0:
            return False, f"melos list failed (exit {proc.returncode})", []
        names = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip() and not ln.startswith("$")]
        return True, "melos list", names
    try:
        data = json.loads(proc.stdout)
        if isinstance(data, list):
            names = [str(x.get("name") or x) if isinstance(x, dict) else str(x) for x in data]
            return True, "melos list --json", names
    except json.JSONDecodeError:
        pass
    names = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return True, "melos list", names


def sample_graph() -> dict[str, Any]:
    return {
        "graph": {
            "nodes": {
                "web": {
                    "name": "web",
                    "data": {
                        "root": "apps/web",
                        "targets": {
                            "verify": {
                                "command": "echo web",
                                "cache": True,
                                "inputs": ["default", "^default"],
                            }
                        },
                    },
                },
                "ui": {
                    "name": "ui",
                    "data": {
                        "root": "libs/ui",
                        "targets": {"verify": {"command": "echo ui", "cache": True, "inputs": ["default"]}},
                    },
                },
                "api-contracts": {
                    "name": "api-contracts",
                    "data": {
                        "root": "contracts",
                        "targets": {
                            "openapi": {"command": "echo gen", "cache": False, "outputs": ["{projectRoot}/openapi.json"]}
                        },
                    },
                },
                "flutter-workspace": {
                    "name": "flutter-workspace",
                    "data": {
                        "root": "flutter",
                        "targets": {
                            "verify": {
                                "command": "dart run melos run test:all",
                                "cache": False,
                                "inputs": ["default", "^default", "{workspaceRoot}/contracts/**/*"],
                            }
                        },
                    },
                },
                "py-api": {
                    "name": "py-api",
                    "data": {
                        "root": "services/api",
                        "targets": {"verify": {"command": "uv run pytest", "cache": True, "inputs": ["default", "^default"]}},
                    },
                },
                "py-lib": {
                    "name": "py-lib",
                    "data": {"root": "packages/py-lib", "targets": {"verify": {"command": "uv run pytest", "cache": True}}},
                },
            },
            "dependencies": {
                "web": [{"source": "web", "target": "ui", "type": "static"}],
                "flutter-workspace": [{"source": "flutter-workspace", "target": "api-contracts", "type": "implicit"}],
                "py-api": [{"source": "py-api", "target": "py-lib", "type": "implicit"}],
            },
        }
    }


def sample_expect() -> dict[str, Any]:
    return {
        "projects": ["web", "ui", "api-contracts", "flutter-workspace", "py-api", "py-lib"],
        "edges": [
            ["web", "ui"],
            ["flutter-workspace", "api-contracts"],
            ["py-api", "py-lib"],
        ],
        "flutter_bridge": "flutter-workspace",
        "python_projects": ["py-api", "py-lib"],
        "required_inputs": {"flutter-workspace:verify": ["^default", "{workspaceRoot}/contracts/**/*"]},
        "never_cache": ["deploy", "migrate", "release", "docker-push"],
        "generated_targets": ["openapi"],
    }


def selftest() -> int:
    fails: list[str] = []

    def expect(cond: bool, label: str) -> None:
        if not cond:
            fails.append(label)

    nodes, deps = parse_graph(sample_graph())
    ok = audit(nodes, deps, sample_expect(), {"targetDefaults": {"deploy": {"cache": False}}})
    expect(ok["verdict"] == "PASS", f"healthy graph PASS got {ok['failures']}")

    missing = sample_expect()
    missing["projects"] = ["web", "ghost"]
    bad = audit(nodes, deps, missing, None)
    expect(bad["verdict"] == "FAIL" and any("ghost" in f for f in bad["failures"]), "missing project fails")

    no_edge = sample_expect()
    no_edge["edges"] = [["web", "ui"], ["flutter-workspace", "api-contracts"], ["py-api", "missing-lib"]]
    bad = audit(nodes, deps, no_edge, None)
    expect(any("missing edge" in f for f in bad["failures"]), "missing python/js edge fails")

    dup_nodes, dup_deps = parse_graph(sample_graph())
    dup_nodes["flutter-app"] = {"name": "flutter-workspace", "data": {"root": "apps/mobile", "targets": {}}}
    bad = audit(dup_nodes, dup_deps, sample_expect(), None)
    expect(any("duplicate Flutter" in f for f in bad["failures"]), "duplicate flutter bridge fails")

    cache_nodes, cache_deps = parse_graph(sample_graph())
    cache_nodes["web"]["data"]["targets"]["deploy"] = {"command": "echo deploy", "cache": True}
    bad = audit(cache_nodes, cache_deps, sample_expect(), None)
    expect(any("cache false" in f for f in bad["failures"]), "cached deploy fails")

    gen_nodes, gen_deps = parse_graph(sample_graph())
    gen_nodes["api-contracts"]["data"]["targets"]["openapi"]["cache"] = True
    bad = audit(gen_nodes, gen_deps, sample_expect(), None)
    expect(any("generated-code" in f for f in bad["failures"]), "cached openapi fails")

    inp = sample_expect()
    inp["required_inputs"] = {"flutter-workspace:verify": ["DOES_NOT_EXIST"]}
    bad = audit(nodes, deps, inp, None)
    expect(any("missing input" in f for f in bad["failures"]), "missing required input fails")

    py = sample_expect()
    py["edges"] = [["web", "ui"], ["flutter-workspace", "api-contracts"]]
    bad = audit(nodes, deps, py, {"plugins": []})
    expect(any("python" in f.lower() for f in bad["failures"]), "python without edges fails closed")

    empty = audit({}, {}, sample_expect(), None)
    expect(empty["verdict"] == "FAIL", "empty graph fail closed")
    empty_expect = audit(nodes, deps, {}, None)
    expect(empty_expect["verdict"] == "FAIL" and any("expect.projects is empty" in f for f in empty_expect["failures"]), "empty expect fail closed")
    prod = sample_graph()
    prod["graph"]["nodes"]["web"]["data"]["targets"]["deploy-prod"] = {"command": "echo", "cache": True}
    prod_nodes, prod_deps = parse_graph(prod)
    bad = audit(prod_nodes, prod_deps, sample_expect(), None)
    expect(any("deploy-prod" in f for f in bad["failures"]), "deploy-prod cached fails")
    plugin_only = sample_expect()
    plugin_only["edges"] = [["web", "ui"], ["flutter-workspace", "api-contracts"]]
    bad = audit(nodes, deps, plugin_only, {"plugins": [{"plugin": "@nxlv/python"}]})
    expect(any("plugin name is not proof" in f for f in bad["failures"]), "python plugin name is not proof")

    if fails:
        print("selftest FAIL")
        for item in fails:
            print(f"  FAIL {item}")
        return 2
    print("selftest PASS")
    print("  ok   healthy graph PASS")
    print("  ok   missing project FAIL")
    print("  ok   missing edge FAIL")
    print("  ok   duplicate Flutter bridge FAIL")
    print("  ok   cached deploy FAIL")
    print("  ok   cached generated openapi FAIL")
    print("  ok   missing required input FAIL")
    print("  ok   python without edges FAIL")
    print("  ok   empty graph FAIL")
    print("  ok   empty expect FAIL")
    print("  ok   deploy-prod cached FAIL")
    print("  ok   python plugin name is not proof FAIL")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    root: Path | None = None
    expect_path: Path | None = None
    graph_file: Path | None = None
    nx_json_path: Path | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = Path(argv[i + 1])
            i += 2
            continue
        if a == "--expect" and i + 1 < len(argv):
            expect_path = Path(argv[i + 1])
            i += 2
            continue
        if a == "--graph-file" and i + 1 < len(argv):
            graph_file = Path(argv[i + 1])
            i += 2
            continue
        if a == "--nx-json" and i + 1 < len(argv):
            nx_json_path = Path(argv[i + 1])
            i += 2
            continue
        die(f"unknown argument: {a}")
    if expect_path is None:
        die("usage: audit_monorepo_graph.py --expect FILE [--root DIR | --graph-file FILE] [--nx-json FILE] | --selftest")
    expect = load_json(expect_path)
    if not isinstance(expect, dict):
        die(f"expect JSON unreadable: {expect_path}")

    nx_json: dict[str, Any] | None = None
    if nx_json_path:
        loaded = load_json(nx_json_path)
        if not isinstance(loaded, dict):
            die(f"nx.json unreadable: {nx_json_path}")
        nx_json = loaded
    elif root and (root / "nx.json").is_file():
        loaded = load_json(root / "nx.json")
        nx_json = loaded if isinstance(loaded, dict) else None

    if graph_file is not None:
        data = load_json(graph_file)
        if not isinstance(data, dict):
            report = {"verdict": "FAIL", "failures": [f"graph file unreadable: {graph_file}"], "projects": [], "edges": []}
            print(json.dumps(report, indent=2))
            return 2
        nodes, deps = parse_graph(data)
        report = audit(nodes, deps, expect, nx_json)
        print(json.dumps(report, indent=2))
        return 0 if report["verdict"] == "PASS" else 2

    if root is None:
        die("provide --root or --graph-file")
    root = root.resolve()
    if not (root / "nx.json").is_file():
        report = {
            "verdict": "FAIL",
            "failures": ["no nx.json; cannot prove Nx affected-task correctness"],
            "projects": [],
            "edges": [],
        }
        print(json.dumps(report, indent=2))
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "nx-graph.json"
        ok, msg = run_nx_graph(root, out)
        if not ok:
            report = {"verdict": "FAIL", "failures": [msg], "projects": [], "edges": []}
            print(json.dumps(report, indent=2))
            return 2
        data = load_json(out)
        if not isinstance(data, dict):
            report = {"verdict": "FAIL", "failures": ["nx graph JSON unparseable"], "projects": [], "edges": []}
            print(json.dumps(report, indent=2))
            return 2
        nodes, deps = parse_graph(data)
        report = audit(nodes, deps, expect, nx_json)
        melos_ok, melos_msg, melos_names = run_melos_list(root)
        report["melos"] = {"ok": melos_ok, "detail": melos_msg, "packages": melos_names}
        if not melos_ok:
            report["verdict"] = "FAIL"
            report["failures"] = list(report["failures"]) + [melos_msg]
        print(json.dumps(report, indent=2))
        return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
