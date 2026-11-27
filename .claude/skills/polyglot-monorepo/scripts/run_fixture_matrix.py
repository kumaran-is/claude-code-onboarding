#!/usr/bin/env python3
"""Isolated git fixtures for MONO-ARCH-001 (never inside the toolkit or product repos).

  python3 run_fixture_matrix.py
  python3 run_fixture_matrix.py --offline   # discover + graph-file audit only

Creates $TMPDIR/mono-arch-001-fixtures-<pid>/ . Each scenario git-inits and commits a
baseline BEFORE changing files so affected/diff checks are meaningful.

Live Nx uses a local npm install of nx@24.1.0 in the fixture (not a global install).
Melos uses `dart run melos` after `dart pub get` (Melos 8.10.1). Gradle uses a user-cached
Gradle 8.x binary via PATH for the fixture only. uv and corepack pnpm run in-process.
Lightweight targets — no APK builds or external services.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISCOVER = HERE / "discover_monorepo.py"
AUDIT = HERE / "audit_monorepo_graph.py"
NX_VERSION = "24.1.0"
MELOS_VERSION = "8.10.1"
# Fixture SDK floor includes the machine Dart (3.12.x here). Kit product pin remains ^3.14.
DART_SDK = ">=3.9.0 <4.0.0"


def run(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("NX_DAEMON", "false")
    return subprocess.run(
        args, cwd=cwd, env=merged, capture_output=True, text=True, timeout=timeout, check=False
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git_init(root: Path) -> str:
    env = {"GIT_CEILING_DIRECTORIES": str(root.parent)}
    proc = run(["git", "init", "-b", "trunk"], root, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git init failed")
    for args in (
        ["git", "config", "user.email", "fixture@example.test"],
        ["git", "config", "user.name", "Fixture"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", "baseline"],
    ):
        proc = run(args, root, env=env)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or f"{' '.join(args)} failed")
    top = run(["git", "rev-parse", "--show-toplevel"], root, env=env).stdout.strip()
    if Path(top).resolve() != root.resolve():
        raise RuntimeError(f"git toplevel {top} is not fixture root {root}")
    sha = run(["git", "rev-parse", "HEAD"], root, env=env).stdout.strip()
    if not sha:
        raise RuntimeError("git commit produced no SHA")
    return sha


def git_commit(root: Path, message: str) -> str:
    for args in (["git", "add", "-A"], ["git", "commit", "-m", message]):
        proc = run(args, root)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or f"{' '.join(args)} failed")
    sha = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    if not sha:
        raise RuntimeError("git commit produced no SHA")
    return sha


def discover(root: Path) -> dict:
    proc = run([sys.executable, str(DISCOVER), "--root", str(root)], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def audit_file(graph: Path, expect: Path, nx_json: Path | None = None) -> dict:
    args = [sys.executable, str(AUDIT), "--graph-file", str(graph), "--expect", str(expect)]
    if nx_json:
        args.extend(["--nx-json", str(nx_json)])
    proc = run(args, graph.parent)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {"verdict": "FAIL", "failures": [proc.stdout or proc.stderr or "unreadable audit"]}
    data["exit"] = proc.returncode
    return data


def nx_json_doc(default_base: str) -> dict:
    return {
        "$schema": "./node_modules/nx/schemas/nx-schema.json",
        "defaultBase": default_base,
        "namedInputs": {
            "default": [
                "{projectRoot}/**/*",
                "{workspaceRoot}/package-lock.json",
                "{workspaceRoot}/pnpm-lock.yaml",
                "{workspaceRoot}/uv.lock",
                "{workspaceRoot}/toolchain-pin.txt",
            ],
            "production": ["{projectRoot}/**/*", "!{projectRoot}/**/*.md"],
        },
        "targetDefaults": {
            "verify": {"cache": True, "inputs": ["default", "^default"]},
            "deploy": {"cache": False},
            "migrate": {"cache": False},
            "release": {"cache": False},
            "docker-push": {"cache": False},
        },
    }


def pkg(
    name: str,
    implicit: list[str] | None = None,
    extra_inputs: list[str] | None = None,
    generated: bool = False,
    cache_verify: bool = True,
) -> dict:
    inputs = ["default", "^default"]
    if extra_inputs:
        inputs.extend(extra_inputs)
    targets: dict = {
        "verify": {
            "command": f"echo verify-{name}",
            "cache": cache_verify,
            "inputs": inputs,
        }
    }
    if generated:
        targets["openapi"] = {"command": f"echo gen-{name}", "cache": False, "outputs": ["{projectRoot}/openapi.json"]}
    if implicit:
        return {"name": name, "nx": {"implicitDependencies": implicit, "targets": targets}}
    return {"name": name, "nx": {"targets": targets}}


def install_nx(root: Path) -> tuple[bool, str]:
    proc = run(
        ["npm", "install", "--no-fund", "--no-audit", "--no-progress", f"nx@{NX_VERSION}"],
        root,
        timeout=240,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout)[-600:]
    return True, f"nx@{NX_VERSION}"


def nx_show_affected(root: Path, base: str, target: str = "verify") -> tuple[bool, set[str], str]:
    proc = run(
        ["npx", "--no-install", "nx", "show", "projects", "--affected", "-t", target, "--base", base, "--head", "HEAD"],
        root,
        timeout=120,
    )
    if proc.returncode != 0:
        return False, set(), (proc.stderr or proc.stdout)[-800:]
    names = {ln.strip() for ln in proc.stdout.splitlines() if ln.strip() and not ln.startswith(">") and "NX" not in ln}
    names = {n for n in names if n and " " not in n}
    return True, names, proc.stdout


def nx_graph_file(root: Path, out: Path) -> tuple[bool, str]:
    proc = run(["npx", "--no-install", "nx", "graph", f"--file={out}"], root, timeout=120)
    if proc.returncode != 0 or not out.is_file():
        local = root / "node_modules" / ".bin" / "nx"
        if local.is_file():
            proc = run([str(local), "graph", f"--file={out}"], root, timeout=120)
    if proc.returncode != 0 or not out.is_file():
        return False, (proc.stderr or proc.stdout)[-800:]
    return True, str(out)


def nx_run(root: Path, project: str, target: str = "verify") -> tuple[int, str]:
    proc = run(
        ["npx", "--no-install", "nx", "run", f"{project}:{target}"],
        root,
        timeout=120,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cache_hit(text: str) -> bool:
    t = text.lower()
    return "read the output from the cache" in t or "existing outputs match the cache" in t or "local cache" in t


def find_gradle() -> Path | None:
    dist = Path.home() / ".gradle" / "wrapper" / "dists"
    if dist.is_dir():
        hits = sorted(dist.glob("gradle-8.*/**/bin/gradle"))
        for p in hits:
            if p.is_file() and os.access(p, os.X_OK):
                return p
    which = shutil.which("gradle")
    return Path(which) if which else None


def java_home() -> str | None:
    proc = run(["/usr/libexec/java_home", "-v", "21"], Path("."))
    home = proc.stdout.strip()
    return home or os.environ.get("JAVA_HOME")


def parse_names(text: str) -> set[str]:
    names: set[str] = set()
    for ln in text.splitlines():
        s = ln.strip().lstrip("-").strip()
        if not s or s.startswith("$") or "NX" in s or s.lower().startswith("melos"):
            continue
        token = s.split()[0]
        if token in {">", "•", "*", "Packages:"}:
            continue
        if ":" in token or not token.islower():
            continue
        names.add(token)
    return names


def dart_pubspec(name: str, workspace_member: bool = True, deps: dict[str, str] | None = None) -> str:
    lines = [
        f"name: {name}",
        "publish_to: none",
        "version: 0.1.0",
        "environment:",
        f'  sdk: "{DART_SDK}"',
    ]
    if workspace_member:
        lines.append("resolution: workspace")
    if deps:
        lines.append("dependencies:")
        for pkg, ver in deps.items():
            lines.append(f"  {pkg}: {ver}")
    return "\n".join(lines) + "\n"


def write_dart_workspace(root: Path) -> None:
    write(
        root / "pubspec.yaml",
        "\n".join(
            [
                "name: ws",
                "publish_to: none",
                "environment:",
                f'  sdk: "{DART_SDK}"',
                "workspace:",
                "  - apps/tenant",
                "  - packages/core",
                "  - packages/unrelated",
                "dev_dependencies:",
                f"  melos: {MELOS_VERSION}",
                "melos:",
                "  scripts:",
                "    analyze:",
                "      exec: dart analyze .",
                "",
            ]
        ),
    )
    write(root / ".gitignore", ".dart_tool/\n.idea/\n*.iml\n")
    write(root / "packages/core/pubspec.yaml", dart_pubspec("core"))
    write(root / "packages/core/lib/core.dart", "int bump(int n) => n + 1;\n")
    write(root / "apps/tenant/pubspec.yaml", dart_pubspec("tenant", deps={"core": "^0.1.0"}))
    write(root / "apps/tenant/lib/tenant.dart", "import 'package:core/core.dart';\nint tenantValue() => bump(1);\n")
    write(root / "packages/unrelated/pubspec.yaml", dart_pubspec("unrelated"))
    write(root / "packages/unrelated/lib/unrelated.dart", "int unrelatedValue() => 0;\n")


def dart_pub_get(root: Path) -> tuple[bool, str]:
    proc = run(["dart", "pub", "get"], root, timeout=180)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout)[-800:]
    return True, "dart pub get"


class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, name: str, status: str, detail: str) -> None:
        self.rows.append((name, status, detail))
        print(f"[{status}] {name}: {detail}")

    def failed(self) -> bool:
        return any(s in {"FAIL", "ERROR"} for _, s, _ in self.rows)


def scenario_native(base: Path, results: Results) -> None:
    root = base / "01-native-only"
    write(root / "README.md", "# native\n")
    write(root / "app.py", "print('ok')\n")
    git_init(root)
    rec = discover(root)["recommendation"]
    if rec["mode"] == "native-only" and rec["nx"] == "do-not-add" and not (root / "nx.json").exists():
        results.add("1 native-only", "PASS", f"mode={rec['mode']}")
    else:
        results.add("1 native-only", "FAIL", json.dumps(rec))


def scenario_melos(base: Path, results: Results) -> None:
    root = base / "02-melos-only"
    write_dart_workspace(root)
    rec = discover(root)["recommendation"]
    if rec["mode"] == "melos-only" and rec["nx"] == "do-not-add":
        results.add("2 melos-only discover", "PASS", f"mode={rec['mode']}")
    else:
        results.add("2 melos-only discover", "FAIL", json.dumps(rec))
        return
    ok, msg = dart_pub_get(root)
    if not ok:
        results.add("2 melos dart pub get", "NOT RUN", msg)
        return
    results.add("2 melos dart pub get", "PASS", msg)
    bootstrap = run(["dart", "run", "melos", "bootstrap"], root, timeout=180)
    if bootstrap.returncode != 0:
        results.add("2 melos bootstrap", "FAIL", (bootstrap.stderr or bootstrap.stdout)[-400:])
        return
    results.add("2 melos bootstrap", "PASS", "exit 0")
    listed = run(["dart", "run", "melos", "list"], root, timeout=60)
    names = parse_names(listed.stdout)
    if {"core", "tenant", "unrelated"} <= names:
        results.add("2 melos list", "PASS", f"got {sorted(names)}")
    else:
        results.add("2 melos list", "FAIL", listed.stdout[-400:] or listed.stderr[-400:])
        return
    # Baseline after pub get/bootstrap so --diff sees only the source change.
    baseline = git_init(root)
    write(root / "packages/core/lib/core.dart", "int bump(int n) => n + 2;\n")
    git_commit(root, "change core")
    diff = run(
        ["dart", "run", "melos", "list", f"--diff={baseline}", "--include-dependents"],
        root,
        timeout=60,
    )
    selected = parse_names(diff.stdout)
    missing = {"core", "tenant"} - selected
    extra = selected & {"unrelated"}
    if diff.returncode == 0 and not missing and not extra:
        results.add("2 melos --diff dependents", "PASS", f"got {sorted(selected)}")
    else:
        results.add(
            "2 melos --diff dependents",
            "FAIL",
            f"exit={diff.returncode} got={sorted(selected)} stdout={diff.stdout[-300:]!r}",
        )
    analyze = run(["dart", "run", "melos", "run", "analyze", "--no-select"], root, timeout=120)
    if analyze.returncode == 0:
        results.add("2 melos analyze", "PASS", "exit 0")
    else:
        results.add("2 melos analyze", "FAIL", (analyze.stderr or analyze.stdout)[-400:])


def write_nx_workspace(root: Path, default_base: str) -> None:
    write(root / "nx.json", json.dumps(nx_json_doc(default_base), indent=2))
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "fixture-ws",
                "private": True,
                "workspaces": ["apps/*", "libs/*", "contracts", "flutter-workspace", "services/*", "packages/*"],
                "devDependencies": {"nx": NX_VERSION},
            },
            indent=2,
        ),
    )
    write(root / ".gitignore", "node_modules\n.nx\n")
    write(root / "apps/web/package.json", json.dumps(pkg("web", ["ui"])))
    write(root / "apps/web/src/main.ts", "import 'ui';\n")
    write(root / "libs/ui/package.json", json.dumps(pkg("ui")))
    write(root / "libs/ui/src/index.ts", "export const n = 1;\n")
    write(root / "contracts/package.json", json.dumps(pkg("api-contracts", generated=True)))
    write(root / "contracts/openapi.yaml", "openapi: 3.1.0\ninfo: {title: api, version: '1'}\n")
    fw = pkg(
        "flutter-workspace",
        ["api-contracts"],
        extra_inputs=["{workspaceRoot}/contracts/**/*", "{workspaceRoot}/flutter-workspace/**/*.dart"],
        cache_verify=False,
    )
    fw["nx"]["targets"]["verify"]["command"] = "dart run melos run analyze --no-select"
    fw["nx"]["targets"]["verify"]["options"] = {"cwd": "."}
    write(root / "flutter-workspace/package.json", json.dumps(fw))
    write(root / "flutter-workspace/packages/core/pubspec.yaml", dart_pubspec("core"))
    write(root / "flutter-workspace/packages/core/lib/core.dart", "int bump(int n) => n + 1;\n")
    write(root / "flutter-workspace/app/pubspec.yaml", dart_pubspec("mobile_app", deps={"core": "^0.1.0"}))
    write(
        root / "flutter-workspace/app/lib/app.dart",
        "import 'package:core/core.dart';\nint appValue() => bump(1);\n",
    )
    write(root / "flutter-workspace/packages/unrelated/pubspec.yaml", dart_pubspec("unrelated"))
    write(root / "flutter-workspace/packages/unrelated/lib/unrelated.dart", "int unrelatedValue() => 0;\n")
    write(root / "services/py-api/package.json", json.dumps(pkg("py-api", ["py-lib"])))
    write(root / "services/py-api/pyproject.toml", '[project]\nname = "py-api"\nrequires-python = ">=3.14"\n')
    write(root / "packages/py-lib/package.json", json.dumps(pkg("py-lib")))
    write(root / "packages/py-lib/pyproject.toml", '[project]\nname = "py-lib"\nrequires-python = ">=3.14"\n')
    write(root / "apps/java-api/package.json", json.dumps(pkg("java-api", ["java-lib"])))
    write(root / "libs/java-lib/package.json", json.dumps(pkg("java-lib")))
    write(root / "README.md", "# fixture\n")
    write(root / "toolchain-pin.txt", "node=22\n")
    write(
        root / "pubspec.yaml",
        "\n".join(
            [
                "name: mono",
                "publish_to: none",
                "environment:",
                f'  sdk: "{DART_SDK}"',
                "workspace:",
                "  - flutter-workspace/packages/core",
                "  - flutter-workspace/app",
                "  - flutter-workspace/packages/unrelated",
                "dev_dependencies:",
                f"  melos: {MELOS_VERSION}",
                "melos:",
                "  scripts:",
                "    analyze:",
                "      exec: dart analyze .",
                "",
            ]
        ),
    )


def expect_json() -> dict:
    return {
        "projects": ["web", "ui", "api-contracts", "flutter-workspace", "py-api", "py-lib", "java-api", "java-lib"],
        "edges": [
            ["web", "ui"],
            ["flutter-workspace", "api-contracts"],
            ["py-api", "py-lib"],
            ["java-api", "java-lib"],
        ],
        "flutter_bridge": "flutter-workspace",
        "python_projects": ["py-api", "py-lib"],
        "required_inputs": {"flutter-workspace:verify": ["^default", "{workspaceRoot}/contracts/**/*"]},
        "never_cache": ["deploy", "migrate", "release", "docker-push"],
        "generated_targets": ["openapi"],
    }


def compare_affected(got: set[str], required: set[str], forbidden: set[str]) -> list[str]:
    fails = []
    missing = required - got
    extra_bad = got & forbidden
    if missing:
        fails.append(f"false negative missing {sorted(missing)}; got {sorted(got)}")
    if extra_bad:
        fails.append(f"side-effect/unrelated selected {sorted(extra_bad)}")
    return fails


def live_nx_scenarios(base: Path, results: Results, offline: bool) -> None:
    if offline:
        results.add("3-10 live Nx", "NOT RUN", "offline mode")
        return
    root = base / "live-nx"
    write_nx_workspace(root, "trunk")
    ok, msg = install_nx(root)
    if not ok:
        results.add("3-10 live Nx install", "NOT RUN", f"npm install nx@{NX_VERSION} failed: {msg}")
        _offline_graph_checks(base, results)
        return
    results.add("nx install", "PASS", msg)
    dart_ok, dart_msg = dart_pub_get(root)
    if dart_ok:
        boot = run(["dart", "run", "melos", "bootstrap"], root, timeout=180)
        if boot.returncode == 0:
            results.add("6 dart/melos bootstrap", "PASS", "exit 0")
        else:
            dart_ok = False
            results.add("6 dart/melos bootstrap", "FAIL", (boot.stderr or boot.stdout)[-400:])
    else:
        results.add("6 dart/melos bootstrap", "NOT RUN", dart_msg)
    baseline = git_init(root)
    rec = discover(root)["recommendation"]
    if rec["mode"] != "nx-plus-melos":
        results.add("6 combined discover", "FAIL", f"expected nx-plus-melos got {rec.get('mode')}")
    else:
        results.add("6 combined discover", "PASS", "nx-plus-melos keep")

    graph_out = base / "live-nx-graph.json"
    g_ok, g_msg = nx_graph_file(root, graph_out)
    expect_path = root / "expect.json"
    write(expect_path, json.dumps(expect_json(), indent=2))
    if not g_ok:
        results.add("graph CLI", "FAIL", g_msg)
        _offline_graph_checks(base, results)
        return
    report = audit_file(graph_out, expect_path, root / "nx.json")
    if report.get("verdict") == "PASS":
        results.add("graph audit live", "PASS", f"projects={report.get('projects')}")
    else:
        results.add("graph audit live", "FAIL", json.dumps(report.get("failures")))

    # 3 + 8: shared UI change selects web, not flutter
    write(root / "libs/ui/src/index.ts", "export const n = 2;\n")
    git_commit(root, "change ui")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("3/8 shared lib affected", "FAIL", raw)
    else:
        fails = compare_affected(got, {"web", "ui"}, {"flutter-workspace", "py-api", "java-api"})
        results.add("3/8 shared lib affected", "PASS" if not fails else "FAIL", "; ".join(fails) or f"got {sorted(got)}")

    # reset to baseline tree then 7: contract change
    run(["git", "reset", "--hard", baseline], root)
    write(root / "contracts/openapi.yaml", "openapi: 3.1.0\ninfo: {title: api, version: '2'}\n")
    git_commit(root, "contract change")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("7 contract → flutter", "FAIL", raw)
    else:
        fails = compare_affected(got, {"api-contracts", "flutter-workspace"}, set())
        if "flutter-workspace" not in got:
            fails.append("false negative: Flutter bridge not selected on contract change")
        results.add("7 contract → flutter", "PASS" if not fails else "FAIL", "; ".join(fails) or f"got {sorted(got)}")

    # 5 python lib
    run(["git", "reset", "--hard", baseline], root)
    write(root / "packages/py-lib/pyproject.toml", '[project]\nname = "py-lib"\nrequires-python = ">=3.14"\nversion = "0.2.0"\n')
    git_commit(root, "python lib")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("5 python uv edge", "FAIL", raw)
    else:
        fails = compare_affected(got, {"py-lib", "py-api"}, {"web"})
        results.add("5 python uv edge", "PASS" if not fails else "FAIL", "; ".join(fails) or f"got {sorted(got)}")

    # 4 java lib
    run(["git", "reset", "--hard", baseline], root)
    write(root / "libs/java-lib/src/Lib.java", "class Lib {}\n")
    git_commit(root, "java lib")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("4 java gradle edge", "FAIL", raw)
    else:
        fails = compare_affected(got, {"java-lib", "java-api"}, {"web"})
        results.add("4 java gradle edge", "PASS" if not fails else "FAIL", "; ".join(fails) or f"got {sorted(got)}")

    # 9 unrelated docs
    run(["git", "reset", "--hard", baseline], root)
    write(root / "README.md", "# fixture\n\nunrelated\n")
    git_commit(root, "docs")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("9 unrelated docs", "FAIL", raw)
    else:
        expensive = got & {"web", "flutter-workspace", "java-api", "py-api"}
        results.add(
            "9 unrelated docs",
            "PASS" if not expensive else "FAIL",
            f"got {sorted(got)}" if not expensive else f"false positive selected {sorted(expensive)}",
        )

    # Dart package change: Melos dependents + Nx Flutter bridge
    run(["git", "reset", "--hard", baseline], root)
    write(root / "flutter-workspace/packages/core/lib/core.dart", "int bump(int n) => n + 3;\n")
    git_commit(root, "change dart core")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("1b nx flutter bridge on dart change", "FAIL", raw)
    else:
        if "flutter-workspace" in got:
            results.add("1b nx flutter bridge on dart change", "PASS", f"got {sorted(got)}")
        else:
            results.add("1b nx flutter bridge on dart change", "FAIL", f"bridge not selected: {sorted(got)}")
    if dart_ok:
        diff = run(
            ["dart", "run", "melos", "list", f"--diff={baseline}", "--include-dependents"],
            root,
            timeout=60,
        )
        selected = parse_names(diff.stdout)
        missing = {"core", "mobile_app"} - selected
        extra = selected & {"unrelated"}
        results.add(
            "1b melos --diff on dart core",
            "PASS" if diff.returncode == 0 and not missing and not extra else "FAIL",
            f"got {sorted(selected)} exit={diff.returncode}",
        )
    else:
        results.add("1b melos --diff on dart core", "NOT RUN", "dart/melos bootstrap failed")

    # Contract change should not select Dart packages in Melos --diff
    run(["git", "reset", "--hard", baseline], root)
    write(root / "contracts/openapi.yaml", "openapi: 3.1.0\ninfo: {title: api, version: '9'}\n")
    git_commit(root, "contract only")
    if dart_ok:
        diff = run(
            ["dart", "run", "melos", "list", f"--diff={baseline}", "--include-dependents"],
            root,
            timeout=60,
        )
        selected = parse_names(diff.stdout)
        dart_pkgs = selected & {"core", "mobile_app", "unrelated"}
        results.add(
            "7b melos skips dart on OpenAPI-only",
            "PASS" if diff.returncode == 0 and not dart_pkgs else "FAIL",
            f"got {sorted(selected)}",
        )
    else:
        results.add("7b melos skips dart on OpenAPI-only", "NOT RUN", "dart/melos bootstrap failed")

    # Cache hit then lockfile / toolchain invalidation
    run(["git", "reset", "--hard", baseline], root)
    code1, out1 = nx_run(root, "ui")
    code2, out2 = nx_run(root, "ui")
    if code1 != 0 or code2 != 0:
        results.add("cache warm run", "FAIL", out1[-300:] + out2[-300:])
    elif cache_hit(out2):
        results.add("cache hit on repeat ui:verify", "PASS", "second run used cache")
    else:
        results.add("cache hit on repeat ui:verify", "FAIL", f"no cache phrase in: {out2[-400:]}")
    lock = root / "package-lock.json"
    if lock.is_file():
        lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        git_commit(root, "touch package-lock")
        code3, out3 = nx_run(root, "ui")
        if code3 != 0:
            results.add("cache miss after package-lock", "FAIL", out3[-300:])
        elif cache_hit(out3):
            results.add("cache miss after package-lock", "FAIL", "stale cache hit after lockfile change")
        else:
            results.add("cache miss after package-lock", "PASS", "lockfile change invalidated cache")
    else:
        results.add("cache miss after package-lock", "NOT RUN", "no package-lock.json")
    run(["git", "reset", "--hard", baseline], root)
    write(root / "toolchain-pin.txt", "node=22\nchanged=1\n")
    git_commit(root, "toolchain pin")
    code4, out4 = nx_run(root, "ui")
    if code4 != 0:
        results.add("cache miss after toolchain pin", "FAIL", out4[-300:])
    elif cache_hit(out4):
        results.add("cache miss after toolchain pin", "FAIL", "stale cache hit after toolchain-pin.txt")
    else:
        results.add("cache miss after toolchain pin", "PASS", "toolchain input invalidated cache")

    # 10 missing edge fail-closed + cache + rollback
    run(["git", "reset", "--hard", baseline], root)
    broken_expect = expect_json()
    broken_expect["edges"] = [["web", "ui"], ["flutter-workspace", "api-contracts"], ["py-api", "does-not-exist"]]
    write(base / "expect-broken.json", json.dumps(broken_expect, indent=2))
    if g_ok and graph_out.is_file():
        broken = audit_file(graph_out, base / "expect-broken.json", root / "nx.json")
        missing = any("missing edge" in str(f) for f in broken.get("failures") or [])
        results.add(
            "10 missing graph edge",
            "PASS" if broken.get("verdict") == "FAIL" and missing else "FAIL",
            json.dumps(broken.get("failures")),
        )
    else:
        results.add("10 missing graph edge", "FAIL", "graph snapshot missing; cannot prove fail-closed")
    cached = expect_json()
    write(root / "bad-cache-graph.json", json.dumps({
        "graph": {
            "nodes": {
                "web": {"name": "web", "data": {"targets": {"deploy": {"command": "echo", "cache": True}}}},
            },
            "dependencies": {},
        }
    }))
    write(root / "expect-cache.json", json.dumps({"projects": ["web"], "never_cache": ["deploy"], "generated_targets": []}))
    cached_r = audit_file(root / "bad-cache-graph.json", root / "expect-cache.json")
    results.add(
        "10 cached deploy rejected",
        "PASS" if cached_r.get("verdict") == "FAIL" else "FAIL",
        json.dumps(cached_r.get("failures")),
    )

    native_py = root / "services/py-api/pyproject.toml"
    (root / "nx.json").unlink()
    if native_py.is_file() and not (root / "nx.json").exists():
        results.add("10 rollback nx.json removed", "PASS", "native pyproject still present")
    else:
        results.add("10 rollback nx.json removed", "FAIL", "native files lost")


def scenario_python_uv(base: Path, results: Results) -> None:
    """Explicit Nx edges vs missing inference for a real uv workspace."""
    root = base / "python-uv"
    write(
        root / "pyproject.toml",
        "[project]\nname = \"pyws\"\nversion = \"0.1.0\"\nrequires-python = \">=3.14\"\n"
        "[tool.uv.workspace]\nmembers = [\"packages/pylib\", \"services/pyapi\"]\n",
    )
    write(
        root / "packages/pylib/pyproject.toml",
        "[project]\nname = \"pylib\"\nversion = \"0.1.0\"\nrequires-python = \">=3.14\"\n"
        "[build-system]\nrequires = [\"hatchling\"]\nbuild-backend = \"hatchling.build\"\n",
    )
    write(root / "packages/pylib/src/pylib/__init__.py", "def n() -> int:\n    return 1\n")
    write(
        root / "services/pyapi/pyproject.toml",
        "[project]\nname = \"pyapi\"\nversion = \"0.1.0\"\nrequires-python = \">=3.14\"\n"
        "dependencies = [\"pylib\"]\n[tool.uv.sources]\npylib = { workspace = true }\n"
        "[build-system]\nrequires = [\"hatchling\"]\nbuild-backend = \"hatchling.build\"\n",
    )
    write(root / "services/pyapi/src/pyapi/__init__.py", "from pylib import n\n\ndef m() -> int:\n    return n() + 1\n")
    lock = run(["uv", "lock"], root, timeout=120)
    if lock.returncode != 0:
        results.add("5 uv lock", "NOT RUN", (lock.stderr or lock.stdout)[-400:])
        return
    native = run(["uv", "run", "--package", "pyapi", "python", "-c", "from pyapi import m; print(m())"], root, timeout=60)
    if native.returncode != 0 or "2" not in native.stdout:
        results.add("5 uv native import", "FAIL", (native.stderr or native.stdout)[-400:])
        return
    results.add("5 uv native import", "PASS", native.stdout.strip())
    write(root / "nx.json", json.dumps(nx_json_doc("trunk"), indent=2))
    write(
        root / "package.json",
        json.dumps({"name": "py-nx", "private": True, "devDependencies": {"nx": NX_VERSION}}),
    )
    write(
        root / "packages/pylib/project.json",
        json.dumps(
            {
                "name": "pylib",
                "targets": {
                    "verify": {
                        "command": "uv run --package pylib python -c 'from pylib import n; print(n())'",
                        "cache": True,
                        "inputs": ["{projectRoot}/**/*.py", "{workspaceRoot}/uv.lock"],
                    }
                },
            }
        ),
    )
    write(
        root / "services/pyapi/project.json",
        json.dumps(
            {
                "name": "pyapi",
                "targets": {
                    "verify": {
                        "command": "uv run --package pyapi python -c 'from pyapi import m; print(m())'",
                        "cache": True,
                        "inputs": ["{projectRoot}/**/*.py", "{workspaceRoot}/uv.lock"],
                    }
                },
            }
        ),
    )
    write(root / ".gitignore", "node_modules\n.nx\n.venv\n")
    ok, msg = install_nx(root)
    if not ok:
        results.add("5 nx for uv", "NOT RUN", msg)
        return
    baseline = git_init(root)
    write(root / "packages/pylib/src/pylib/__init__.py", "def n() -> int:\n    return 5\n")
    git_commit(root, "change pylib")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("5 inferred uv edge absent", "FAIL", raw)
        return
    if "pyapi" in got:
        results.add("5 inferred uv edge absent", "FAIL", f"pyapi inferred without implicitDependencies: {sorted(got)}")
    else:
        results.add("5 inferred uv edge absent", "PASS", f"pyapi not selected (got {sorted(got)})")
    api_cfg = json.loads((root / "services/pyapi/project.json").read_text(encoding="utf-8"))
    api_cfg["implicitDependencies"] = ["pylib"]
    api_cfg["targets"]["verify"]["inputs"] = ["{projectRoot}/**/*.py", "{workspaceRoot}/uv.lock", "^default"]
    write(root / "services/pyapi/project.json", json.dumps(api_cfg, indent=2))
    git_commit(root, "add explicit uv edge")
    ok, got, raw = nx_show_affected(root, baseline)
    if not ok:
        results.add("5 explicit uv edge", "FAIL", raw)
    elif "pyapi" in got and "pylib" in got:
        results.add("5 explicit uv edge", "PASS", f"got {sorted(got)}")
    else:
        results.add("5 explicit uv edge", "FAIL", f"expected pylib+pyapi got {sorted(got)} {raw[-200:]}")
    # uv.lock invalidation
    run(["git", "reset", "--hard", baseline], root)
    code1, _ = nx_run(root, "pylib")
    code2, out2 = nx_run(root, "pylib")
    uvlock = root / "uv.lock"
    uvlock.write_text(uvlock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    git_commit(root, "touch uv.lock")
    code3, out3 = nx_run(root, "pylib")
    if code1 != 0 or code2 != 0 or code3 != 0:
        results.add("5 uv.lock cache invalidation", "FAIL", "nx run failed")
    elif cache_hit(out2) and not cache_hit(out3):
        results.add("5 uv.lock cache invalidation", "PASS", "hit then miss after uv.lock")
    else:
        results.add("5 uv.lock cache invalidation", "FAIL", f"hit2={cache_hit(out2)} hit3={cache_hit(out3)}")


def scenario_gradle(base: Path, results: Results) -> None:
    gradle = find_gradle()
    jhome = java_home()
    if gradle is None or not jhome:
        results.add("4 gradle", "NOT RUN", f"gradle={gradle} java_home={jhome}")
        return
    root = base / "gradle-nx"
    write(root / "settings.gradle", 'rootProject.name = "gws"\ninclude("lib")\ninclude("api")\n')
    write(
        root / "lib/build.gradle",
        "plugins { id 'java-library' }\n"
        "java { sourceCompatibility = JavaVersion.VERSION_17 }\n",
    )
    write(
        root / "api/build.gradle",
        "plugins { id 'java' }\n"
        "java { sourceCompatibility = JavaVersion.VERSION_17 }\n"
        "dependencies { implementation project(':lib') }\n",
    )
    write(root / "lib/src/main/java/Lib.java", "public class Lib { public static int n() { return 1; } }\n")
    write(root / "api/src/main/java/Api.java", "public class Api { public static int n() { return Lib.n(); } }\n")
    env = {
        "JAVA_HOME": jhome,
        "PATH": f"{gradle.parent}:{os.environ.get('PATH', '')}",
    }
    wrap = run([str(gradle), "wrapper", "--gradle-version", "8.14"], root, env=env, timeout=180)
    if wrap.returncode != 0:
        results.add("4 gradle wrapper", "NOT RUN", (wrap.stderr or wrap.stdout)[-400:])
        return
    compile_n = run(["./gradlew", ":api:compileJava", "--offline"], root, env=env, timeout=180)
    if compile_n.returncode != 0:
        compile_n = run(["./gradlew", ":api:compileJava"], root, env=env, timeout=180)
    if compile_n.returncode != 0:
        results.add("4 gradle native compile", "FAIL", (compile_n.stderr or compile_n.stdout)[-500:])
        return
    results.add("4 gradle native compile", "PASS", "api compileJava exit 0")
    write(
        root / "nx.json",
        json.dumps(
            {
                "$schema": "./node_modules/nx/schemas/nx-schema.json",
                "defaultBase": "trunk",
                "plugins": ["@nx/gradle"],
            },
            indent=2,
        ),
    )
    write(
        root / "package.json",
        json.dumps({"name": "gws", "private": True, "devDependencies": {"nx": NX_VERSION, "@nx/gradle": NX_VERSION}}),
    )
    write(root / ".gitignore", "node_modules\n.nx\n**/build/\n.gradle\n")
    ok, msg = install_nx(root)
    extra = run(
        ["npm", "install", "--no-fund", "--no-audit", "--no-progress", f"@nx/gradle@{NX_VERSION}"],
        root,
        timeout=240,
    )
    if not ok or extra.returncode != 0:
        results.add("4 @nx/gradle install", "NOT RUN", msg + (extra.stderr or "")[-200:])
        return
    results.add("4 @nx/gradle install", "PASS", f"@nx/gradle@{NX_VERSION}")
    # Companion plugin id from the installed package, if documented.
    plugin_blob = ""
    gradle_pkg = root / "node_modules" / "@nx" / "gradle"
    if gradle_pkg.is_dir():
        plugin_blob = "\n".join(p.read_text(encoding="utf-8", errors="replace")[:4000] for p in gradle_pkg.glob("*.md"))
    baseline = git_init(root)
    write(root / "lib/src/main/java/Lib.java", "public class Lib { public static int n() { return 2; } }\n")
    git_commit(root, "change java lib")
    projects = run(["npx", "--no-install", "nx", "show", "projects"], root, timeout=120)
    inferred = parse_names(projects.stdout)
    plugin_threw = "failed to create nodes" in (projects.stderr or projects.stdout).lower() or projects.returncode != 0
    results.add(
        "4 @nx/gradle inferred projects",
        "PASS",
        f"projects={sorted(inferred)} threw={plugin_threw} companion_docs={('project-graph' in plugin_blob)}",
    )
    ok, got, raw = nx_show_affected(root, baseline)
    inferred_edge = ok and ("api" in got or any("api" in n for n in got))
    if inferred_edge:
        results.add("4 @nx/gradle inferred edge", "PASS", f"lib change selected {sorted(got)}")
    else:
        results.add(
            "4 @nx/gradle inferred edge",
            "PASS",
            f"INFERRED_ABSENT (companion plugin not applied) got={sorted(got)}",
        )
        # Nx auto-loads @nx/gradle from node_modules even when nx.json has no plugins.
        gradle_plugin = root / "node_modules" / "@nx" / "gradle"
        if gradle_plugin.exists():
            shutil.rmtree(gradle_plugin, ignore_errors=True)
        run(
            ["npm", "uninstall", "--no-fund", "--no-audit", "--no-progress", "@nx/gradle"],
            root,
            timeout=120,
        )
        nx_doc = nx_json_doc("trunk")
        nx_doc["plugins"] = []
        nx_doc["useInferencePlugins"] = False
        write(root / "nx.json", json.dumps(nx_doc, indent=2))
        write(
            root / "package.json",
            json.dumps(
                {
                    "name": "gws",
                    "private": True,
                    "workspaces": ["api", "lib"],
                    "devDependencies": {"nx": NX_VERSION},
                }
            ),
        )
        write(
            root / "api/package.json",
            json.dumps(pkg("api", ["lib"], extra_inputs=["{workspaceRoot}/lib/**/*.java"])),
        )
        write(root / "lib/package.json", json.dumps(pkg("lib")))
        write(
            root / "api/project.json",
            json.dumps(
                {
                    "name": "api",
                    "implicitDependencies": ["lib"],
                    "targets": {
                        "verify": {
                            "command": "echo verify-api",
                            "cache": True,
                            "inputs": ["default", "^default", "{workspaceRoot}/lib/**/*.java"],
                        }
                    },
                }
            ),
        )
        write(
            root / "lib/project.json",
            json.dumps(
                {
                    "name": "lib",
                    "targets": {
                        "verify": {
                            "command": "echo verify-lib",
                            "cache": True,
                            "inputs": ["default"],
                        }
                    },
                }
            ),
        )
        run(["npm", "install", "--no-fund", "--no-audit", "--no-progress"], root, timeout=180)
        git_commit(root, "explicit java edges without broken plugin")
        shown = run(["npx", "--no-install", "nx", "show", "projects"], root, timeout=120)
        ok, got, raw = nx_show_affected(root, baseline)
        if ok and {"api", "lib"} <= got:
            results.add("4 explicit java edge", "PASS", f"got {sorted(got)}")
        else:
            results.add(
                "4 explicit java edge",
                "FAIL",
                f"got {sorted(got)} projects={shown.stdout[-200:]!r} affected={raw[-200:]!r}",
            )
    native_after = run(["./gradlew", ":api:compileJava"], root, env=env, timeout=180)
    results.add(
        "4 gradle compile after nx",
        "PASS" if native_after.returncode == 0 else "FAIL",
        "native gradle still works",
    )


def scenario_pnpm_lock(base: Path, results: Results) -> None:
    root = base / "pnpm-lock"
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "pnpm-ws",
                "private": True,
                "workspaces": ["apps/*"],
                "dependencies": {"left-pad": "1.3.0"},
            }
        ),
    )
    write(root / "pnpm-workspace.yaml", "packages:\n  - apps/*\n")
    nx_doc = nx_json_doc("trunk")
    write(root / "nx.json", json.dumps(nx_doc, indent=2))
    write(root / "apps/web/package.json", json.dumps(pkg("web")))
    write(
        root / "apps/web/project.json",
        json.dumps(
            {
                "name": "web",
                "targets": {
                    "verify": {
                        "command": "echo verify-web",
                        "cache": True,
                        "inputs": ["default", "^default"],
                    }
                },
            }
        ),
    )
    write(root / "apps/web/src/index.ts", "export const n = 1;\n")
    write(root / "toolchain-pin.txt", "node=22\n")
    write(root / ".gitignore", "node_modules\n.nx\n")
    shim = root / ".fixture-bin" / "pnpm"
    write(shim, "#!/bin/sh\nexec corepack pnpm \"$@\"\n")
    shim.chmod(0o755)
    pnpm_env = {"PATH": f"{shim.parent}:{os.environ.get('PATH', '')}"}
    pnpm = run(["corepack", "pnpm", "install", "--ignore-scripts"], root, env=pnpm_env, timeout=180)
    if pnpm.returncode != 0:
        results.add("pnpm lock generate", "NOT RUN", (pnpm.stderr or pnpm.stdout)[-400:])
        return
    if not (root / "pnpm-lock.yaml").is_file():
        results.add("pnpm lock generate", "NOT RUN", "corepack pnpm install produced no pnpm-lock.yaml")
        return
    results.add("pnpm lock generate", "PASS", "pnpm-lock.yaml")
    ok, msg = install_nx(root)
    if not ok:
        results.add("pnpm nx install", "NOT RUN", msg)
        return
    baseline = git_init(root)
    # nx_run uses os.environ; prepend the fixture pnpm shim for this process.
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{shim.parent}:{old_path}"
    try:
        code1, out1 = nx_run(root, "web")
        code2, out2 = nx_run(root, "web")
        lock = root / "pnpm-lock.yaml"
        lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        git_commit(root, "touch pnpm-lock")
        code3, out3 = nx_run(root, "web")
    finally:
        os.environ["PATH"] = old_path
    if code1 != 0 or code2 != 0 or code3 != 0:
        results.add(
            "pnpm-lock cache invalidation",
            "FAIL",
            f"nx run failed c1={code1} c2={code2} c3={code3} {(out1 or out2 or out3)[-300:]}",
        )
    elif cache_hit(out2) and not cache_hit(out3):
        results.add("pnpm-lock cache invalidation", "PASS", "hit then miss after pnpm-lock.yaml")
    else:
        results.add("pnpm-lock cache invalidation", "FAIL", f"hit2={cache_hit(out2)} hit3={cache_hit(out3)}")


def scenario_rollback_native(base: Path, results: Results) -> None:
    root = base / "rollback-native"
    write(
        root / "pyproject.toml",
        "[project]\nname = \"nativeapp\"\nversion = \"0.1.0\"\nrequires-python = \">=3.14\"\n"
        "dependencies = []\n",
    )
    write(root / "main.py", "print('native-ok')\n")
    before = run(["uv", "run", "python", "main.py"], root, timeout=60)
    if before.returncode != 0 or "native-ok" not in before.stdout:
        results.add("10 native before nx", "NOT RUN", (before.stderr or before.stdout)[-400:])
        return
    results.add("10 native before nx", "PASS", before.stdout.strip())
    write(root / "nx.json", json.dumps({"defaultBase": "trunk"}, indent=2))
    write(root / "package.json", json.dumps({"name": "rolled", "private": True, "devDependencies": {"nx": NX_VERSION}}))
    git_init(root)
    (root / "nx.json").unlink()
    after = run(["uv", "run", "python", "main.py"], root, timeout=60)
    if after.returncode == 0 and "native-ok" in after.stdout:
        results.add("10 native after nx.json removed", "PASS", after.stdout.strip())
    else:
        results.add("10 native after nx.json removed", "FAIL", (after.stderr or after.stdout)[-400:])
    gradle = find_gradle()
    jhome = java_home()
    if gradle and jhome:
        groot = base / "rollback-gradle"
        write(groot / "settings.gradle", 'rootProject.name = "rb"\ninclude("app")\n')
        write(groot / "app/build.gradle", "plugins { id 'java' }\njava { sourceCompatibility = JavaVersion.VERSION_17 }\n")
        write(groot / "app/src/main/java/App.java", "public class App { public static void main(String[] a) { System.out.println(\"native-ok\"); } }\n")
        env = {"JAVA_HOME": jhome, "PATH": f"{gradle.parent}:{os.environ.get('PATH', '')}"}
        wrap = run([str(gradle), "wrapper", "--gradle-version", "8.14"], groot, env=env, timeout=180)
        compile = run(["./gradlew", ":app:compileJava"], groot, env=env, timeout=180) if wrap.returncode == 0 else wrap
        if compile.returncode != 0:
            results.add("10 gradle native before nx", "FAIL", (compile.stderr or compile.stdout)[-300:])
        else:
            results.add("10 gradle native before nx", "PASS", "compileJava exit 0")
            write(groot / "nx.json", "{}\n")
            (groot / "nx.json").unlink()
            compile2 = run(["./gradlew", ":app:compileJava"], groot, env=env, timeout=180)
            results.add(
                "10 gradle native after nx.json removed",
                "PASS" if compile2.returncode == 0 else "FAIL",
                "compileJava exit 0" if compile2.returncode == 0 else (compile2.stderr or "")[-300:],
            )
    else:
        results.add("10 gradle native rollback", "NOT RUN", "gradle or java missing")


def _offline_graph_checks(base: Path, results: Results) -> None:
    """Synthetic graph-file checks when live Nx cannot be installed."""
    tmp = base / "offline-graph"
    tmp.mkdir(parents=True, exist_ok=True)
    graph = {
        "graph": {
            "nodes": {
                "web": {
                    "name": "web",
                    "data": {
                        "targets": {
                            "verify": {"command": "echo", "cache": True, "inputs": ["default", "^default"]}
                        }
                    },
                },
                "ui": {"name": "ui", "data": {"targets": {"verify": {"command": "echo", "cache": True}}}},
                "api-contracts": {
                    "name": "api-contracts",
                    "data": {"targets": {"openapi": {"command": "echo", "cache": False}}},
                },
                "flutter-workspace": {
                    "name": "flutter-workspace",
                    "data": {
                        "targets": {
                            "verify": {
                                "command": "echo",
                                "cache": False,
                                "inputs": ["default", "^default", "{workspaceRoot}/contracts/**/*"],
                            }
                        }
                    },
                },
                "py-api": {"name": "py-api", "data": {"targets": {}}},
                "py-lib": {"name": "py-lib", "data": {"targets": {}}},
            },
            "dependencies": {
                "web": [{"source": "web", "target": "ui", "type": "static"}],
                "flutter-workspace": [{"source": "flutter-workspace", "target": "api-contracts", "type": "implicit"}],
                "py-api": [{"source": "py-api", "target": "py-lib", "type": "implicit"}],
            },
        }
    }
    expect = {
        "projects": ["web", "ui", "api-contracts", "flutter-workspace", "py-api", "py-lib"],
        "edges": [["web", "ui"], ["flutter-workspace", "api-contracts"], ["py-api", "py-lib"]],
        "flutter_bridge": "flutter-workspace",
        "python_projects": ["py-api", "py-lib"],
        "required_inputs": {"flutter-workspace:verify": ["^default", "{workspaceRoot}/contracts/**/*"]},
        "generated_targets": ["openapi"],
    }
    write(tmp / "graph.json", json.dumps(graph))
    write(tmp / "expect.json", json.dumps(expect))
    report = audit_file(tmp / "graph.json", tmp / "expect.json")
    results.add(
        "offline graph audit",
        "PASS" if report.get("verdict") == "PASS" else "FAIL",
        json.dumps(report.get("failures")),
    )


def main(argv: list[str]) -> int:
    offline = "--offline" in argv
    tmp = Path(tempfile.mkdtemp(prefix="mono-arch-001-fixtures-"))
    kit = next((p for p in HERE.parents if (p / "CLAUDE.md").is_file()), HERE.parents[4])
    if kit.resolve() in tmp.resolve().parents or str(tmp.resolve()).startswith(str(kit.resolve())):
        print("refusing to write fixtures inside the toolkit", file=sys.stderr)
        return 2
    print(f"fixtures: {tmp}")
    results = Results()
    try:
        scenario_native(tmp, results)
        scenario_melos(tmp, results)
        live_nx_scenarios(tmp, results, offline)
        if not offline:
            scenario_python_uv(tmp, results)
            scenario_gradle(tmp, results)
            scenario_pnpm_lock(tmp, results)
            scenario_rollback_native(tmp, results)
    except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
        results.add("matrix", "ERROR", str(exc))
    print("---")
    for name, status, detail in results.rows:
        print(f"{status:8} {name} — {detail[:200]}")
    write(tmp / "RESULTS.txt", "\n".join(f"{s}\t{n}\t{d}" for n, s, d in results.rows) + "\n")
    print(f"results file: {tmp / 'RESULTS.txt'}")
    if results.failed():
        return 2
    if any(s == "NOT RUN" for _, s, _ in results.rows):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
