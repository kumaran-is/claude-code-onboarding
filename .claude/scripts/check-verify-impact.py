#!/usr/bin/env python3
"""Select the smallest safe /verify gate set from a git diff.

Principles (Property Harbor optimized-verification-loop, not its Makefile):
  never skip a gate the diff can reach; unknown impact → FULL (broader);
  docs/comments-only with zero code files → app suites NOT APPLICABLE;
  shared path-deps fan out to consumers; OpenAPI fans out to generated clients.
  Iteration stage: cheap + tests of reached stacks. Frozen/pre-pr: those plus
  expensive E2E/security of reached stacks. Playwright never substitutes for
  Flutter Android/iOS Maestro.

Usage:
  check-verify-impact.py --stage iteration|frozen [--root DIR] [--base REF]
  check-verify-impact.py --files a,b --stage iteration [--root DIR]
  check-verify-impact.py --scan-docs
  check-verify-impact.py --benchmark
  check-verify-impact.py --selftest

Exit: 0 ok, 2 usage / broken selftest. Stdlib only. Never weakens a reached gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

KIT = Path(__file__).resolve().parent.parent
DOC_MARKERS = {
    KIT / "commands" / "verify.md": (
        "check-verify-impact.py",
        "--stage iteration",
        "--stage frozen",
        "never skip a gate the diff can reach",
        "maestro test",
        "BLOCKED",
        "NOT RUN",
        "Playwright",
    ),
    KIT / "commands" / "next.md": (
        "/create-pr",
        "does not merge",
        "check-verify-impact.py",
    ),
    KIT / "commands" / "review-code.md": (
        "check-verify-impact.py",
        "rereview",
        "newly appearing",
        "security-reviewer",
    ),
    KIT / "commands" / "ship.md": (
        "readiness",
        "/create-pr",
        "does not merge",
        "--stage frozen",
    ),
    KIT / "commands" / "create-pr.md": (
        "/verify pre-pr",
        "does not run `gh pr create`",
    ),
    KIT / "skills" / "next-issue" / "references" / "plan-and-handoff.md": (
        "check-verify-impact.py",
        "/create-pr",
        "does not merge",
        "--stage iteration",
        "--stage frozen",
    ),
    KIT / "skills" / "receiving-code-review" / "SKILL.md": (
        "check-verify-impact.py",
        "touched",
    ),
    KIT / "skills" / "verification-before-completion" / "reference" / "verification-loop.md": (
        "check-verify-impact.py",
        "--stage iteration",
        "--stage frozen",
    ),
}

CODE_SUFFIX = {
    ".dart": "flutter",
    ".java": "java",
    ".kt": "java",
    ".py": "python",
    ".sql": "sql",
}
DOC_SUFFIX = {".md", ".txt", ".rst"}
OPENAPI_NAMES = {"openapi.yaml", "openapi.yml", "openapi.json"}
MAESTRO_DIR_NAMES = {".maestro", "maestro"}
AUTH_RE = re.compile(
    r"(?i)(auth|oauth|jwt|password|secret|encrypt|payment|stripe|pci|billing)",
)
PATH_DEP_RE = re.compile(r"""path:\s*['\"]?([^'\"\s]+)['\"]?""")


def die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def changed_files(root: Path, base: str | None) -> list[str]:
    names: set[str] = set()
    if git(["rev-parse", "--is-inside-work-tree"], root).returncode != 0:
        return []
    ranges = ["HEAD"]
    if base:
        ranges.insert(0, f"{base}...HEAD")
    for spec in ranges:
        r = git(["diff", "--name-only", spec], root)
        if r.returncode == 0:
            names.update(n.strip() for n in r.stdout.splitlines() if n.strip())
    extra = git(["ls-files", "--others", "--exclude-standard"], root)
    if extra.returncode == 0:
        names.update(n.strip() for n in extra.stdout.splitlines() if n.strip())
    return sorted(names)


def nearest_pubspec(root: Path, rel: str) -> Path | None:
    p = (root / rel).resolve()
    if p.is_file():
        p = p.parent
    root_r = root.resolve()
    while True:
        cand = p / "pubspec.yaml"
        if cand.is_file():
            return cand
        if p == root_r or p.parent == p:
            return None
        p = p.parent


def parse_path_deps(pubspec: Path, root: Path) -> list[Path] | None:
    """Return path-deps, or None when the file cannot be read (treat as unknown)."""
    try:
        text = pubspec.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out: list[Path] = []
    root_r = root.resolve()
    for m in PATH_DEP_RE.finditer(text):
        dep = (pubspec.parent / m.group(1)).resolve()
        if not (dep.is_dir() and (dep / "pubspec.yaml").is_file()):
            continue
        try:
            dep.relative_to(root_r)
        except ValueError:
            continue  # outside the repo; cannot verify here
        out.append(dep)
    return out


def flutter_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".dart_tool", "build", ".venv"}]
        if "pubspec.yaml" in filenames:
            pub = Path(dirpath, "pubspec.yaml")
            try:
                text = pub.read_text(encoding="utf-8", errors="replace")
            except OSError:
                found.append(Path(dirpath))  # unreadable → still a package; fan-out broadens
                continue
            if re.search(r"(?m)^flutter:\s*$", text) or "sdk: flutter" in text:
                found.append(Path(dirpath))
    return found


def maestro_roots(root: Path, packages: list[Path]) -> list[Path]:
    hits: list[Path] = []
    search = packages or [root]
    for pkg in search:
        for name in MAESTRO_DIR_NAMES:
            d = pkg / name
            if d.is_dir() and (any(d.glob("*.yaml")) or any(d.glob("*.yml"))):
                hits.append(d)
        for pat in ("*.yaml", "*.yml"):
            for f in pkg.glob(pat):
                if "maestro" in f.name.lower():
                    hits.append(f.parent)
    return hits


def classify_file(rel: str) -> str:
    name = Path(rel).name.lower()
    low = rel.replace("\\", "/").lower()
    suf = Path(rel).suffix.lower()
    if name in OPENAPI_NAMES or "openapi" in name:
        return "openapi"
    if any(h in name or h in low for h in (".g.dart", ".freezed.dart", ".mocks.dart", "schema.d.ts")):
        return "generated"
    if suf in DOC_SUFFIX or "/docs/" in f"/{low}" or low.startswith("docs/"):
        if suf in {".md", ".txt", ".rst"}:
            return "docs"
    if suf in CODE_SUFFIX:
        return CODE_SUFFIX[suf]
    if name == "pubspec.yaml" or suf == ".arb":
        return "flutter"
    if name in {"pyproject.toml", "requirements.txt"} or "alembic" in low:
        return "python"
    if name == "pom.xml":
        return "java"
    if name == "angular.json" or low.endswith(".component.ts") or low.endswith(".component.html"):
        return "angular"
    if suf in {".tsx", ".jsx"} or "vite.config" in name:
        return "react"
    if name in {"package.json", "package-lock.json"} and "nestjs" in low:
        return "nestjs"
    if name in {"package.json", "tsconfig.json"} or suf in {".ts", ".js"}:
        if "angular" in low:
            return "angular"
        if "react" in low or "/web/" in f"/{low}":
            return "react"
        return "node"
    if suf == ".tf" or "terraform" in low:
        return "terraform"
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
        return "infra"
    if ".github/workflows" in low:
        return "ci"
    if AUTH_RE.search(low):
        return "security"
    return "unknown"


def fan_out_flutter(root: Path, touched_pkgs: set[Path]) -> tuple[set[Path], list[str]]:
    notes: list[str] = []
    all_pkgs = flutter_packages(root)
    consumers = set(touched_pkgs)
    unreadable = False
    for pkg in all_pkgs:
        deps = parse_path_deps(pkg / "pubspec.yaml", root)
        if deps is None:
            unreadable = True
            notes.append(f"unreadable pubspec: {pkg.relative_to(root)} (fan-out unknown → all packages)")
            continue
        for dep in deps:
            if dep in touched_pkgs:
                consumers.add(pkg)
                notes.append(f"{dep.relative_to(root)} -> {pkg.relative_to(root)}")
    if unreadable:
        consumers.update(all_pkgs)
    return consumers, notes


def fan_out_openapi(root: Path, files: list[str]) -> list[str]:
    extra: list[str] = []
    if not any(classify_file(f) == "openapi" or "openapi" in f.lower() for f in files):
        return extra
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".dart_tool", "build"}]
        for fn in filenames:
            if fn in {"schema.d.ts", "api.ts", "openapi.ts"} or fn.endswith(".client.ts"):
                extra.append(str(Path(dirpath, fn).relative_to(root)))
    return extra


def is_flutter_ui(rel: str) -> bool:
    low = rel.replace("\\", "/")
    return low.endswith(".dart") and "/lib/" in f"/{low}" and not low.endswith("_test.dart")


def select(root: Path, files: list[str], stage: str) -> dict[str, Any]:
    root = root.resolve()
    kinds = {f: classify_file(f) for f in files}
    unknown = sorted(f for f, k in kinds.items() if k == "unknown")
    docs_only = bool(files) and all(k == "docs" for k in kinds.values())
    empty = not files

    stacks: set[str] = set()
    for k in kinds.values():
        if k in {"docs", "unknown", "generated", "security", "ci", "infra"}:
            continue
        stacks.add("flutter" if k == "flutter" else k)
        if k == "openapi":
            stacks.add("openapi")
        if k == "sql":
            stacks.add("python")  # alembic often lives with python
            stacks.add("sql")

    flutter_touched: set[Path] = set()
    for f, k in kinds.items():
        if k in {"flutter", "generated"} or f.endswith(".dart"):
            ps = nearest_pubspec(root, f)
            if ps:
                flutter_touched.add(ps.parent)

    fan_notes: list[str] = []
    flutter_all = set()
    if flutter_touched:
        flutter_all, fan_notes = fan_out_flutter(root, flutter_touched)
        if flutter_all:
            stacks.add("flutter")

    openapi_extra = fan_out_openapi(root, files)
    if openapi_extra:
        stacks.add("openapi")
        for rel in openapi_extra:
            stacks.add(classify_file(rel) if classify_file(rel) not in {"docs", "unknown"} else "node")

    selection = "SCOPED"
    skip: list[dict[str, str]] = []
    if empty:
        selection = "EMPTY"
    elif docs_only:
        selection = "DOCS"
        skip.append({"stack": "app-suites", "reason": "docs/comments only; zero code files"})
        stacks.clear()
    elif unknown:
        selection = "FULL"
        skip.append({"stack": "*", "reason": f"unknown impact ({len(unknown)} unclassified file(s)); broaden to FULL"})

    present = detect_present_stacks(root)
    if selection == "FULL":
        for s in present:
            if s not in stacks:
                stacks.add(s)
                skip.append({"stack": s, "reason": "included because unknown impact broadens to present stacks"})
        if "flutter" in stacks and not (flutter_all or flutter_touched):
            flutter_all = set(flutter_packages(root))
            skip.append({"stack": "flutter", "reason": "FULL: all nested Flutter packages (unknown impact)"})

    maestro_required = False
    maestro_flows: list[str] = []
    maestro_blocked = False
    flutter_ui = any(is_flutter_ui(f) for f in files) or (
        selection == "FULL" and "flutter" in stacks and stage == "frozen"
    )
    if "flutter" in stacks and flutter_ui:
        roots = maestro_roots(root, sorted(flutter_all or flutter_touched) or [root])
        if roots:
            maestro_required = True
            for rdir in roots:
                maestro_flows.extend(str(p.resolve().relative_to(root)) for p in rdir.glob("*.y*ml"))
        elif stage == "frozen":
            maestro_required = True
        else:
            skip.append({"stack": "maestro", "reason": "no Maestro flows configured; iteration skips E2E"})

    if maestro_required:
        maestro_blocked = shutil.which("maestro") is None

    cheap_gates: list[str] = []
    test_gates: list[str] = []
    if "flutter" in stacks:
        cheap_gates.extend(["dart format", "flutter analyze"])
        pkgs = sorted(flutter_all or flutter_touched)
        if pkgs:
            for pkg in pkgs:
                rel = str(pkg.relative_to(root)) if pkg != root else "."
                test_gates.append(f"flutter test ({rel})")
        else:
            test_gates.append("flutter test")
        if maestro_required and (stage == "frozen" or maestro_flows):
            test_gates.append("maestro test")
    if "python" in stacks:
        cheap_gates.extend(["ruff", "mypy"])
        test_gates.append("pytest (touched)" if stage == "iteration" else "pytest")
    if "java" in stacks:
        cheap_gates.append("mvnw compile")
        if stage == "frozen":
            test_gates.append("mvnw test")
        else:
            test_gates.append("mvnw test (touched)")
    if "angular" in stacks or "react" in stacks:
        cheap_gates.extend(["tsc", "lint"])
        test_gates.append("unit tests")
        if stage == "frozen":
            test_gates.append("playwright test (web only)")
    if "nestjs" in stacks or "node" in stacks:
        cheap_gates.extend(["tsc", "lint"])
        test_gates.append("node unit tests")
    if "sql" in stacks and stage == "frozen":
        test_gates.append("alembic check")
    if "openapi" in stacks:
        cheap_gates.append("openapi consumer check")
    if "terraform" in stacks:
        cheap_gates.append("terraform validate")
    if (any(kinds.get(f) == "security" or AUTH_RE.search(f) for f in files) or selection == "FULL") and stage == "frozen":
        test_gates.append("security audit (pre-pr)")

    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for g in items:
            if g not in seen:
                seen.add(g)
                out.append(g)
        return out

    cheap_gates = _uniq(cheap_gates)
    test_gates = _uniq(test_gates)
    uniq_gates = _uniq(cheap_gates + (test_gates if stage in {"iteration", "frozen"} else []))

    return {
        "stage": stage,
        "selection": selection,
        "files": files,
        "kinds": kinds,
        "unknown_files": unknown,
        "stacks": sorted(stacks),
        "present_stacks": present,
        "flutter_packages": sorted(str(p.relative_to(root)) for p in (flutter_all or flutter_touched)),
        "fan_out": fan_notes,
        "openapi_consumers": openapi_extra,
        "cheap_gates": cheap_gates,
        "gates": uniq_gates,
        "skip": skip,
        "docs_only": docs_only,
        "maestro": {
            "required": maestro_required,
            "flows": maestro_flows,
            "blocked": maestro_blocked,
            "never_playwright_for_flutter_mobile": True,
        },
        "stamp_mode": "pre-pr" if stage == "frozen" else "iteration",
        "note": "never skip a gate the diff can reach; unknown impact → FULL",
    }


def detect_present_stacks(root: Path) -> list[str]:
    found: set[str] = set()
    skip_dirs = {".git", "node_modules", ".dart_tool", "build", ".venv", "target", "dist"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        names = set(filenames)
        if "pom.xml" in names:
            found.add("java")
        if "pyproject.toml" in names or "requirements.txt" in names:
            found.add("python")
        if "pubspec.yaml" in names:
            found.add("flutter")
        if "angular.json" in names:
            found.add("angular")
        if any(n.startswith("vite.config") for n in names) or any(n.endswith(".tsx") for n in names):
            found.add("react")
        if "package.json" in names:
            found.add("node")
    return sorted(found)


def scan_docs() -> list[str]:
    findings: list[str] = []
    for path, markers in DOC_MARKERS.items():
        if not path.is_file():
            findings.append(f"missing {path}")
            continue
        body = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in body:
                findings.append(f"{path.name} missing {marker!r}")
    return findings


def build_fixture(tmp: Path) -> None:
    git(["init"], tmp)
    git(["config", "user.email", "t@t"], tmp)
    git(["config", "user.name", "t"], tmp)
    (tmp / "apps" / "tenant" / "lib").mkdir(parents=True)
    (tmp / "packages" / "shared_core").mkdir(parents=True)
    (tmp / "web" / "admin").mkdir(parents=True)
    (tmp / "services" / "api").mkdir(parents=True)
    (tmp / "docs").mkdir()
    (tmp / "packages" / "shared_core" / "pubspec.yaml").write_text(
        "name: shared_core\nflutter:\n  sdk: flutter\n", encoding="utf-8"
    )
    (tmp / "packages" / "shared_core" / "lib.dart").write_text("class A {}\n", encoding="utf-8")
    (tmp / "apps" / "tenant" / "pubspec.yaml").write_text(
        "name: tenant\nflutter:\n  sdk: flutter\ndependencies:\n  shared_core:\n    path: ../../packages/shared_core\n",
        encoding="utf-8",
    )
    (tmp / "apps" / "tenant" / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
    (tmp / "apps" / "tenant" / ".maestro").mkdir()
    (tmp / "apps" / "tenant" / ".maestro" / "home.yaml").write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    (tmp / "web" / "admin" / "angular.json").write_text("{}\n", encoding="utf-8")
    (tmp / "web" / "admin" / "app.component.ts").write_text("export class App {}\n", encoding="utf-8")
    (tmp / "services" / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
    (tmp / "services" / "api" / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
    (tmp / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    (tmp / "web" / "admin" / "schema.d.ts").write_text("export type T = string;\n", encoding="utf-8")
    git(["add", "."], tmp)
    git(["commit", "-m", "init"], tmp)


def selftest() -> int:
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal fail
        if cond:
            print(f"  ok   {name}")
        else:
            fail += 1
            print(f"  FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        build_fixture(tmp)

        def run(files: list[str], stage: str) -> dict[str, Any]:
            return select(tmp, files, stage)

        r = run(["docs/guide.md"], "iteration")
        check("positive-docs-only skips app suites", r["selection"] == "DOCS" and "flutter" not in r["stacks"], str(r["stacks"]))
        check("negative-docs-only has no flutter test gate", not any("flutter test" == g for g in r["gates"]), str(r["gates"]))

        r = run(["apps/tenant/lib/main.dart"], "iteration")
        check("positive-isolated-flutter-ui selects flutter", "flutter" in r["stacks"], str(r["stacks"]))
        check("negative-isolated-flutter does not select angular", "angular" not in r["stacks"], str(r["stacks"]))
        check("negative-isolated-flutter does not select python", "python" not in r["stacks"], str(r["stacks"]))
        check("maestro never playwright", r["maestro"]["never_playwright_for_flutter_mobile"] is True)
        check("negative-no-generic-flutter-test-when-packages", "flutter test" not in r["gates"], str(r["gates"]))
        check("negative-flutter-iteration-has-no-playwright-gate", "playwright test (web only)" not in r["gates"], str(r["gates"]))
        check("empty-files-EMPTY", run([], "iteration")["selection"] == "EMPTY")

        r = run(["packages/shared_core/lib.dart"], "iteration")
        check("positive-shared-package fans out to tenant", any("tenant" in p for p in r["flutter_packages"]), str(r["flutter_packages"]))
        check("positive-shared-package fan_out note", bool(r["fan_out"]), str(r["fan_out"]))
        check("mutation-shared-package-lists-consumer-test", any("tenant" in g for g in r["gates"]), str(r["gates"]))
        # Mutation: unreadable consumer pubspec must broaden to every Flutter package.
        tenant_pub = tmp / "apps" / "tenant" / "pubspec.yaml"
        saved = tenant_pub.read_text(encoding="utf-8")
        r_bad: dict[str, Any] = {"fan_out": []}
        try:
            tenant_pub.unlink()
            tenant_pub.symlink_to("/no/such/pubspec.yaml")
            r_bad = run(["packages/shared_core/lib.dart"], "iteration")
        finally:
            tenant_pub.unlink(missing_ok=True)
            tenant_pub.write_text(saved, encoding="utf-8")
        check(
            "mutation-unreadable-pubspec-fans-out-all",
            any("unreadable pubspec" in n for n in r_bad["fan_out"]),
            str(r_bad["fan_out"]),
        )

        r = run(["openapi.yaml"], "frozen")
        check("positive-openapi fans out to schema.d.ts", any("schema.d.ts" in x for x in r["openapi_consumers"]), str(r["openapi_consumers"]))
        check("positive-openapi gate listed", "openapi consumer check" in r["gates"], str(r["gates"]))

        r = run(["weird.unknownext"], "iteration")
        check("positive-unknown-impact is FULL", r["selection"] == "FULL", r["selection"])
        check("mutation-unknown includes present stacks", "flutter" in r["present_stacks"] or "python" in r.get("stacks", []), str(r))
        check("mutation-unknown-FULL-emits-gates", bool(r["gates"]), str(r["gates"]))
        check("negative-cheap-gates-omit-tests", "flutter test" not in r.get("cheap_gates", []) and not any("flutter test" in g for g in r.get("cheap_gates", [])), str(r.get("cheap_gates")))

        r_iter = run(["apps/tenant/lib/main.dart"], "iteration")
        r_frz = run(["apps/tenant/lib/main.dart"], "frozen")
        check(
            "positive-frozen-adds-maestro-when-ui",
            "maestro test" in r_frz["gates"] or r_frz["maestro"]["required"],
            str(r_frz["gates"]),
        )
        check("negative-quick-is-not-a-stage", r_iter["stamp_mode"] != "pre-pr", r_iter["stamp_mode"])
        check("positive-frozen-stamp-is-pre-pr", r_frz["stamp_mode"] == "pre-pr")

        # Stale evidence: docs-only vs previous flutter selection must not keep flutter gates.
        prev = run(["apps/tenant/lib/main.dart"], "frozen")
        now = run(["docs/guide.md"], "frozen")
        check(
            "positive-stale-flutter-gates-dropped-on-docs-only",
            "flutter" in prev["stacks"] and "flutter" not in now["stacks"],
            str(now),
        )

        # Baseline vs optimized gate counts on identical fixture.
        all_files = [
            "apps/tenant/lib/main.dart",
            "packages/shared_core/lib.dart",
            "web/admin/app.component.ts",
            "services/api/main.py",
            "docs/guide.md",
            "openapi.yaml",
        ]
        t0 = time.perf_counter()
        naive_gates = 0
        for _ in range(50):
            naive = select(tmp, all_files, "frozen")  # worst-case mixed diff
            naive_gates = len(naive["gates"])
        naive_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        scoped_gates = 0
        for _ in range(50):
            scoped = select(tmp, ["apps/tenant/lib/main.dart"], "iteration")
            scoped_gates = len(scoped["gates"])
        scoped_ms = (time.perf_counter() - t1) * 1000
        check("benchmark-scoped-fewer-gates-than-mixed-frozen", scoped_gates < naive_gates, f"{scoped_gates} vs {naive_gates}")
        print(f"  TIME naive-mixed-frozen x50: {naive_ms:.1f}ms gates={naive_gates}")
        print(f"  TIME scoped-flutter-iteration x50: {scoped_ms:.1f}ms gates={scoped_gates}")
        print(f"  TIME gate-count-delta: {naive_gates - scoped_gates} fewer gates on isolated Flutter UI iteration")

        r = run(["web/admin/app.component.ts"], "iteration")
        check("negative-angular-does-not-list-maestro", "maestro test" not in r["gates"], str(r["gates"]))
        r = run(["services/api/main.py"], "iteration")
        check("negative-python-does-not-select-flutter", "flutter" not in r["stacks"], str(r["stacks"]))

    docs = scan_docs()
    check("scan-docs clean", docs == [], str(docs))
    print("selftest PASS" if fail == 0 else f"selftest FAIL {fail}")
    return 0 if fail == 0 else 2


def benchmark() -> int:
    """Public --benchmark: same fixture, print executed selector timings."""
    rc = selftest()
    return rc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--base", default=None, help="git merge-base ref (e.g. origin/develop)")
    p.add_argument("--files", default=None, help="comma-separated relative paths (skip git)")
    p.add_argument("--stage", choices=("iteration", "frozen"), default="iteration")
    p.add_argument("--scan-docs", action="store_true")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--benchmark", action="store_true")
    args = p.parse_args(argv)

    if args.selftest or args.benchmark:
        return selftest()
    if args.scan_docs:
        findings = scan_docs()
        for f in findings:
            print(f)
        return 0 if not findings else 1

    root = (args.root or Path.cwd()).resolve()
    if args.files:
        files = [x.strip() for x in args.files.split(",") if x.strip()]
    else:
        files = changed_files(root, args.base)
    result = select(root, files, args.stage)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
