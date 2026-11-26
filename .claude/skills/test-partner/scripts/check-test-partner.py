#!/usr/bin/env python3
"""Partner-testing target and tool selection (framework-agnostic).

Usage:
  check-test-partner.py --selftest
  check-test-partner.py --detect-target --root DIR
  check-test-partner.py --select-tools --target TARGET
  check-test-partner.py --check-ledger LEDGER.md
  check-test-partner.py --scan-skill

Exit: 0 ok, 1 check failure, 2 usage or broken selftest.
Stdlib only. Never hardcodes a product, owner, or absolute project path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent

TARGETS = (
    "flutter-android",
    "flutter-ios",
    "flutter-web",
    "angular",
    "react",
    "web",
    "unknown",
)

UI_E2E = {
    "flutter-android": ("maestro",),
    "flutter-ios": ("maestro",),
    "flutter-web": ("playwright-cli", "playwright-test"),
    "angular": ("playwright-cli", "playwright-test"),
    "react": ("playwright-cli", "playwright-test"),
    "web": ("playwright-cli", "playwright-test"),
}

DIAGNOSTICS = {
    "flutter-android": ("adb-logcat", "flutter-logs", "backend-logs"),
    "flutter-ios": ("simctl-logs", "flutter-logs", "backend-logs"),
    "flutter-web": ("chrome-devtools-mcp", "backend-logs"),
    "angular": ("chrome-devtools-mcp", "backend-logs"),
    "react": ("chrome-devtools-mcp", "backend-logs"),
    "web": ("chrome-devtools-mcp", "backend-logs"),
}

FORBIDDEN_FOR_TARGET = {
    "flutter-android": {"playwright-cli", "playwright-test", "chrome-devtools-mcp", "playwright-mcp", "browser-use-mcp"},
    "flutter-ios": {"playwright-cli", "playwright-test", "chrome-devtools-mcp", "playwright-mcp", "browser-use-mcp"},
    "angular": {"maestro"},
    "react": {"maestro"},
    "web": {"maestro"},
    "flutter-web": {"maestro"},
}

FORBIDDEN_SKILL_MARKERS = (
    "property-harbor",
    "propertyharbor",
    "ph-tenants",
    "ph-postgres",
    "rentflow",
    "harbor-ai",
    "/Users/",
    "/home/",
    "mcp__playwright",
    "npx playwright-mcp",
)

REQUIRED_SKILL_MARKERS = (
    "NO FINDING WITHOUT EVIDENCE",
    "NO UNASKED FIX",
    "pass / fail / shot",
    "Maestro",
    "Playwright",
    "Chrome DevTools MCP",
    "offline",
    ".claude/state/test-sessions/",
    "No Playwright MCP",
)

LEDGER_HEADING = re.compile(r"^# test-partner\b", re.M)
FINDING_HEADING = re.compile(r"^### F\d+\s+\[(BLOCKER|MAJOR|MINOR|NOTE|UNVERIFIED)\]", re.M)
STEP_HEADING = re.compile(r"^## S\d+\b", re.M)
REQUIRED_FINDING_FIELDS = ("observed:", "expected:", "repro:", "evidence:", "retest:", "status:")


def detect_target(root: Path, hint: str = "") -> str:
    hint_l = hint.lower().strip()
    aliases = {
        "ios": "flutter-ios",
        "android": "flutter-android",
        "flutter": "flutter-android",
        "angular": "angular",
        "react": "react",
        "web": "web",
        "flutter-web": "flutter-web",
    }
    if hint_l in TARGETS:
        return hint_l
    if hint_l in aliases:
        return aliases[hint_l]

    pubspec = root / "pubspec.yaml"
    angular = root / "angular.json"
    package = root / "package.json"
    has_android = (root / "android").is_dir()
    has_ios = (root / "ios").is_dir()
    has_web_flutter = (root / "web").is_dir() and pubspec.is_file()

    if pubspec.is_file() and (has_android or has_ios):
        if hint_l == "web" or (has_web_flutter and not has_android and not has_ios):
            return "flutter-web"
        return "flutter-ios" if hint_l == "ios" or (has_ios and not has_android) else "flutter-android"
    if pubspec.is_file() and has_web_flutter:
        return "flutter-web"
    if angular.is_file():
        return "angular"
    if package.is_file():
        text = package.read_text(encoding="utf-8")
        if '"react"' in text or '"react-dom"' in text:
            return "react"
        return "web"
    return "unknown"


def select_tools(target: str) -> dict[str, Any]:
    if target not in TARGETS or target == "unknown":
        return {
            "target": target,
            "ui_e2e": (),
            "diagnostics": (),
            "forbidden": ("playwright-mcp", "browser-use-mcp"),
            "status": "BLOCKED",
            "reason": "unknown target — set --target or add an adapter",
        }
    return {
        "target": target,
        "ui_e2e": UI_E2E[target],
        "diagnostics": DIAGNOSTICS[target],
        "forbidden": tuple(sorted(FORBIDDEN_FOR_TARGET.get(target, set()) | {"playwright-mcp", "browser-use-mcp"})),
        "status": "ok",
        "reason": "",
    }


def check_ledger(path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing ledger {path}"]
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    if not LEDGER_HEADING.search(text):
        findings.append("missing '# test-partner' heading")
    if not STEP_HEADING.search(text):
        findings.append("no ## S<n> step blocks")
    if FINDING_HEADING.search(text):
        for field in REQUIRED_FINDING_FIELDS:
            if field not in text:
                findings.append(f"finding missing field {field}")
    if re.search(r"(?i)(sk-|ghp_|github_pat_|-----BEGIN )", text):
        findings.append("possible secret in ledger")
    return findings


def scan_skill(skill_dir: Path) -> list[str]:
    findings: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"missing {skill_md}"]
    text = skill_md.read_text(encoding="utf-8")
    for marker in REQUIRED_SKILL_MARKERS:
        if marker not in text:
            findings.append(f"SKILL.md missing required marker: {marker}")
    for path in [skill_md, *sorted((skill_dir / "references").glob("*.md"))]:
        body = path.read_text(encoding="utf-8")
        lower = body.lower()
        for bad in FORBIDDEN_SKILL_MARKERS:
            if bad.lower() in lower:
                findings.append(f"{path.name} contains product/path marker: {bad}")
    return findings


def selftest() -> int:
    fail = 0

    def check(name: str, got: Any, expect: Any) -> None:
        nonlocal fail
        if got != expect:
            print(f"  FAIL {name}: got {got!r} expected {expect!r}")
            fail += 1
        else:
            print(f"  ok   {name}")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
        (root / "android").mkdir()
        check("detect-flutter-android", detect_target(root), "flutter-android")
        (root / "ios").mkdir()
        check("detect-flutter-ios-hint", detect_target(root, "ios"), "flutter-ios")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "angular.json").write_text("{}", encoding="utf-8")
        check("detect-angular", detect_target(root), "angular")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text('{"dependencies":{"react":"19.0.0"}}', encoding="utf-8")
        check("detect-react", detect_target(root), "react")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        check("detect-unknown", detect_target(root), "unknown")

    flutter_tools = select_tools("flutter-android")
    check("flutter-uses-maestro", "maestro" in flutter_tools["ui_e2e"], True)
    check(
        "negative-flutter-forbids-playwright",
        "playwright-cli" in flutter_tools["forbidden"] and "playwright-test" in flutter_tools["forbidden"],
        True,
    )
    check(
        "negative-flutter-forbids-cdp",
        "chrome-devtools-mcp" in flutter_tools["forbidden"],
        True,
    )

    web_tools = select_tools("angular")
    check("angular-uses-playwright", "playwright-cli" in web_tools["ui_e2e"], True)
    check("negative-angular-forbids-maestro", "maestro" in web_tools["forbidden"], True)
    check("angular-allows-cdp", "chrome-devtools-mcp" in web_tools["diagnostics"], True)

    unknown = select_tools("unknown")
    check("unknown-is-blocked", unknown["status"], "BLOCKED")

    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.md"
        good.write_text(
            "# test-partner — demo / local / chrome\n\n"
            "## S1 — open home\n"
            "verdict: expected\n\n"
            "## Findings\n\n"
            "### F1 [MAJOR] home\n"
            "observed: blank\n"
            "expected: list\n"
            "repro: open home offline\n"
            "evidence: shot.png\n"
            "retest: PENDING\n"
            "status: OPEN\n",
            encoding="utf-8",
        )
        check("positive-ledger", check_ledger(good), [])

        bad = Path(tmp) / "bad.md"
        bad.write_text("no heading\nsk-live-secret\n", encoding="utf-8")
        bad_findings = check_ledger(bad)
        check("negative-ledger-heading", any("heading" in f for f in bad_findings), True)
        check("negative-ledger-secret", any("secret" in f for f in bad_findings), True)

    findings = scan_skill(SKILL_DIR)
    if findings:
        print("  FAIL skill scan:")
        for f in findings:
            print(f"    - {f}")
        fail += 1
    else:
        print("  ok   skill scan clean")

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--detect-target", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--hint", default="")
    parser.add_argument("--select-tools", action="store_true")
    parser.add_argument("--target", default="")
    parser.add_argument("--check-ledger", type=Path)
    parser.add_argument("--scan-skill", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.scan_skill:
        findings = scan_skill(SKILL_DIR)
        if findings:
            for f in findings:
                print(f)
            return 1
        print("SCAN PASS")
        return 0
    if args.detect_target:
        print(detect_target(args.root, args.hint))
        return 0
    if args.select_tools:
        target = args.target or detect_target(args.root, args.hint)
        payload = select_tools(target)
        print(json.dumps(payload, indent=2))
        return 0 if payload["status"] == "ok" else 1
    if args.check_ledger:
        findings = check_ledger(args.check_ledger)
        if findings:
            for f in findings:
                print(f)
            return 1
        print("LEDGER PASS")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
