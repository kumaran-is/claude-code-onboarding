#!/usr/bin/env python3
"""Classify RED-phase test output: behavioral vs compile/config/environment.

Does not replace stack runners. Used by the test-driven-development skill and
/tdd so GREEN is not claimed on a compile failure, and RED is not claimed on
a missing binary.

Usage:
  check-tdd-evidence.py --classify LOG.txt
  check-tdd-evidence.py --classify-text TEXT
  check-tdd-evidence.py --scan-skill
  check-tdd-evidence.py --selftest

Exit: 0 ok, 1 scan finding, 2 usage or broken selftest.
Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

COMPILE = (
    "cannot find symbol",
    "compilation failed",
    "error ts",
    "syntaxerror",
    "build failed",
    "failed to compile",
    "error: expected identifier",
    "error: expected ';'",
    "undeclared identifier",
    "not a statement",
    "javac:",
)
CONFIG = (
    "no tests found",
    "plugin not found",
    "could not resolve",
    "pubspec.yaml has no",
    "invalid testdescriptor",
    "unknown option",
    "unrecognized option",
)
ENVIRONMENT = (
    "command not found",
    "no such file or directory",
    "connection refused",
    "could not find a version that satisfies",
    "error: unable to start",
    "sdk not found",
)
BEHAVIORAL = (
    "assertionerror",
    "assert equals",
    "expected:",
    "was:",
    "but was",
    "testfailure",
    "failed expectation",
    "expected:",
    "matcher",
    "expect(",
    "❌",
    "failed tests:",
    "failures:",
)

SKILL_MARKERS = (
    "expected behavioral reason",
    "compile",
    "configuration",
    "environment",
    "check-tdd-evidence.py",
    "do not delete",
)
COMMAND_MARKERS = (
    "expected behavioral reason",
    "configuration",
    "Maestro",
    "Playwright",
)


def classify(text: str) -> str:
    low = text.lower()
    for needle in ENVIRONMENT:
        if needle in low:
            return "environment"
    for needle in CONFIG:
        if needle in low:
            return "configuration"
    for needle in COMPILE:
        if needle in low:
            return "compile"
    # A failing test that names expect/assert after a runner started.
    runner_started = bool(
        re.search(r"(test session starts|running tests|surefire|flutter test|vitest|pytest)", low)
    )
    for needle in BEHAVIORAL:
        if needle in low:
            return "behavioral"
    if runner_started and re.search(r"\bfail(ed|ures?)?\b", low):
        return "behavioral"
    if re.search(r"\b(error|failed|failure)\b", low):
        return "unknown"
    return "unknown"


def scan_skill() -> list[str]:
    findings: list[str] = []
    skill = SKILL_DIR / "SKILL.md"
    if not skill.is_file():
        return ["missing SKILL.md"]
    text = skill.read_text(encoding="utf-8")
    for marker in SKILL_MARKERS:
        if marker.lower() not in text.lower():
            findings.append(f"SKILL.md missing {marker!r}")
    ref = SKILL_DIR / "reference" / "red-green-evidence.md"
    if not ref.is_file():
        findings.append("missing reference/red-green-evidence.md")
    cmd = SKILL_DIR.parent.parent / "commands" / "tdd.md"
    if cmd.is_file():
        body = cmd.read_text(encoding="utf-8")
        for marker in COMMAND_MARKERS:
            if marker.lower() not in body.lower() and marker not in body:
                findings.append(f"tdd.md missing {marker!r}")
    else:
        findings.append("missing commands/tdd.md")
    agent = SKILL_DIR.parent.parent / "agents" / "tdd-guide.md"
    if agent.is_file():
        body = agent.read_text(encoding="utf-8")
        if "expected behavioral reason" not in body.lower() and "behavioral reason" not in body.lower():
            findings.append("tdd-guide.md missing behavioral-reason classification")
        if "playwright" in body.lower() and "maestro" not in body.lower():
            findings.append("tdd-guide.md mentions Playwright without Maestro")
    return findings


def selftest() -> int:
    fail = 0

    def check(name: str, got: str, expect: str) -> None:
        nonlocal fail
        if got == expect:
            print(f"  PASS {name}")
        else:
            fail += 1
            print(f"  FAIL {name} got={got} expect={expect}")

    check(
        "pytest assertion is behavioral",
        classify("============================= test session starts ==============================\nE   AssertionError: expected 1 == 2\nFAILED tests/test_foo.py::test_foo"),
        "behavioral",
    )
    check(
        "javac is compile",
        classify("Compilation failure\n[ERROR] cannot find symbol\n  symbol:   method foo()"),
        "compile",
    )
    check(
        "missing binary is environment",
        classify("zsh: command not found: pytest"),
        "environment",
    )
    check(
        "no tests found is configuration",
        classify("No tests found matching UserServiceTest"),
        "configuration",
    )
    check(
        "flutter expect is behavioral",
        classify("00:01 +0 -1: createUser throws\n  Expected: <true>\n    Actual: <false>\nflutter test test/foo_test.dart"),
        "behavioral",
    )
    findings = scan_skill()
    if findings:
        fail += 1
        print(f"  FAIL scan-skill {findings}")
    else:
        print("  PASS scan-skill")
    print("PASS" if fail == 0 else f"FAIL {fail}")
    return 0 if fail == 0 else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--classify", type=Path, default=None)
    p.add_argument("--classify-text", default=None)
    p.add_argument("--scan-skill", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.scan_skill:
        findings = scan_skill()
        for f in findings:
            print(f)
        return 0 if not findings else 1
    text = ""
    if args.classify is not None:
        text = args.classify.read_text(encoding="utf-8", errors="replace")
    elif args.classify_text is not None:
        text = args.classify_text
    else:
        print("specify --classify, --classify-text, --scan-skill, or --selftest", file=sys.stderr)
        return 2
    kind = classify(text)
    print(kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
