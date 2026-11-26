#!/usr/bin/env python3
"""Compact, accurate test-log summaries for /verify.

Reads a saved runner log (and optional JUnit XML / JSON report). Prints counts,
actionable failure names, and the log path. Never deletes or rewrites the log.
Never replaces the runner's exit code: callers echo `TEST EXIT:$rc` first.

Unknown, truncated, or malformed output is status=UNKNOWN, never PASS.
Stdlib only. Used by `/verify`; do not pipe the runner into this script.

Usage:
  summarize-test-log.py --log PATH --exit-code N [--framework auto|pytest|surefire|flutter|vitest|jest|playwright|junit]
                        [--junit PATH] [--json PATH] [--max-failures N] [--max-tail N]
  summarize-test-log.py --selftest

Exit: 0 report written (PASS, FAIL, or UNKNOWN), 2 usage or broken selftest.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import ParseError, parse as xml_parse

if sys.version_info < (3, 10):
    sys.exit(f"{Path(__file__).name} needs Python 3.10+, found {sys.version.split()[0]}")

KIT = Path(__file__).resolve().parent.parent
VERIFY_MD = KIT / "commands" / "verify.md"
MAX_READ = 8_000_000
TAIL_READ = 2_000_000
DETAIL_LEN = 180
FRAMEWORKS = (
    "auto",
    "pytest",
    "surefire",
    "flutter",
    "vitest",
    "jest",
    "playwright",
    "junit",
)

PYTEST_FINAL = re.compile(
    r"^=+ .*\b(passed|failed|error|skipped|no tests ran)\b.* =+$",
    re.I,
)
PYTEST_FAIL_LINE = re.compile(r"^(FAILED|ERROR)\s+(\S+)(?:\s+-\s+(.*))?")
SUREFIRE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
    re.I,
)
FLUTTER_PASS = re.compile(r"\+(\d+):\s*All tests passed!")
FLUTTER_FAIL = re.compile(r"\+(\d+)\s+(?:~(\d+)\s+)?-(\d+):\s*Some tests failed")
FLUTTER_NONE = re.compile(r"No tests ran\.?", re.I)
FLUTTER_SKIP_ONLY = re.compile(r"~(\d+):\s*All tests skipped", re.I)
FLUTTER_E = re.compile(r"^\d+:\d+\s+\+\d+(?:\s+~\d+)?\s+-\d+:\s+(.+?)\s+\[E\]\s*$", re.M)
VITEST_TESTS = re.compile(r"^\s*Tests\s+(.+?)\s*$", re.M)
JEST_TESTS = re.compile(r"^\s*Tests:\s+(.+?)\s*$", re.M)
COUNT_PIPE = re.compile(r"(\d+)\s+(failed|passed|skipped|todo|errors?)", re.I)
COUNT_COMMA = re.compile(r"(\d+)\s+(failed|passed|skipped|pending|todo|total)", re.I)


@dataclass
class Failure:
    name: str
    detail: str = ""


@dataclass
class Parse:
    framework: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    failures: list[Failure] = field(default_factory=list)
    complete: bool = True


def _clip(text: str) -> str:
    one = " ".join(text.split())
    if len(one) <= DETAIL_LEN:
        return one
    return one[: DETAIL_LEN - 3] + "..."


def _count(parse: Parse) -> None:
    if parse.passed < 0 or parse.failed < 0 or parse.errors < 0 or parse.skipped < 0:
        parse.complete = False


def executed(parse: Parse) -> int:
    return parse.passed + parse.failed + parse.errors


def read_log(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    sliced = False
    if len(data) > MAX_READ:
        data = data[-TAIL_READ:]
        sliced = True
    return data.decode("utf-8", errors="replace"), sliced


def parse_pytest(text: str) -> Parse | None:
    summary = None
    for line in reversed(text.splitlines()):
        if PYTEST_FINAL.match(line.strip()):
            summary = line.strip().strip("=").strip()
            break
    started = bool(
        re.search(r"test session starts|collected \d+ item", text, re.I)
        or re.search(r"^=+\s*short test summary", text, re.M)
    )
    if summary is None:
        if started:
            failures = _pytest_failures(text)
            return Parse(
                framework="pytest",
                failures=failures,
                complete=False,
                failed=len(failures) if failures else 0,
            )
        return None
    if re.search(r"no tests ran", summary, re.I):
        return Parse(framework="pytest", complete=True)
    def grab(word: str) -> int:
        m = re.search(rf"(?<![a-z])(\d+)\s+{word}", summary, re.I)
        return int(m.group(1)) if m else 0

    parse = Parse(
        framework="pytest",
        passed=grab("passed"),
        failed=grab("failed"),
        errors=grab("errors?"),
        skipped=grab("skipped"),
        failures=_pytest_failures(text),
        complete=True,
    )
    _count(parse)
    return parse


def _pytest_failures(text: str) -> list[Failure]:
    out: list[Failure] = []
    for line in text.splitlines():
        m = PYTEST_FAIL_LINE.match(line.strip())
        if m:
            out.append(Failure(name=m.group(2), detail=_clip(m.group(3) or m.group(1))))
    return out


def parse_surefire(text: str) -> Parse | None:
    last = None
    for m in SUREFIRE.finditer(text):
        last = m
    if last is None:
        return None
    total, failures, errors, skipped = (int(last.group(i)) for i in range(1, 5))
    passed = total - failures - errors - skipped
    parse = Parse(
        framework="surefire",
        passed=max(passed, 0),
        failed=failures,
        errors=errors,
        skipped=skipped,
        failures=_surefire_failures(text),
        complete=passed >= 0,
    )
    if passed < 0:
        parse.complete = False
    return parse


def _surefire_failures(text: str) -> list[Failure]:
    out: list[Failure] = []
    section = None
    for line in text.splitlines():
        stripped = re.sub(r"^\[(?:ERROR|INFO|WARN)\]\s*", "", line).strip()
        if re.match(r"Failures:\s*$", stripped, re.I):
            section = "fail"
            continue
        if re.match(r"Errors:\s*$", stripped, re.I):
            section = "error"
            continue
        if re.match(r"Tests run:", stripped, re.I):
            section = None
            continue
        if section and stripped:
            name = stripped.split(":", 1)[0].strip()
            if name and not name.lower().startswith("there are"):
                detail = stripped[len(name) :].lstrip(" :")
                out.append(Failure(name=name, detail=_clip(detail or section)))
    return out


def parse_flutter(text: str) -> Parse | None:
    if FLUTTER_NONE.search(text):
        return Parse(framework="flutter", complete=True)
    skip_only = FLUTTER_SKIP_ONLY.search(text)
    if skip_only:
        return Parse(framework="flutter", skipped=int(skip_only.group(1)), complete=True)
    last_pass = None
    last_fail = None
    for line in text.splitlines():
        p = FLUTTER_PASS.search(line)
        if p:
            last_pass = p
        f = FLUTTER_FAIL.search(line)
        if f:
            last_fail = f
    failures = [Failure(name=_clip(m.group(1))) for m in FLUTTER_E.finditer(text)]
    if last_fail:
        skipped = int(last_fail.group(2) or 0)
        return Parse(
            framework="flutter",
            passed=int(last_fail.group(1)),
            failed=int(last_fail.group(3)),
            skipped=skipped,
            failures=failures,
            complete=True,
        )
    if last_pass:
        return Parse(framework="flutter", passed=int(last_pass.group(1)), complete=True)
    if re.search(r"^\d+:\d+\s+\+\d+", text, re.M) and not last_pass and not last_fail:
        return Parse(framework="flutter", failures=failures, complete=False)
    return None


def _vitest_counts(blob: str) -> tuple[int, int, int, int] | None:
    found = {k: 0 for k in ("passed", "failed", "skipped", "todo")}
    hits = 0
    for m in COUNT_PIPE.finditer(blob):
        key = m.group(2).lower().rstrip("s")
        if key == "error":
            return None
        if key == "todo":
            found["skipped"] += int(m.group(1))
        elif key in found:
            found[key] = int(m.group(1))
            hits += 1
    if hits == 0:
        return None
    return found["passed"], found["failed"], 0, found["skipped"]


def parse_vitest(text: str) -> Parse | None:
    if "Test Files" not in text:
        return None
    m = None
    for match in VITEST_TESTS.finditer(text):
        m = match
    if m is None:
        return None
    counts = _vitest_counts(m.group(1))
    if counts is None:
        return None
    passed, failed, errors, skipped = counts
    failures = _vitest_failures(text)
    return Parse(
        framework="vitest",
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        failures=failures,
        complete=True,
    )


def _vitest_failures(text: str) -> list[Failure]:
    out: list[Failure] = []
    for line in text.splitlines():
        m = re.match(r"^\s*[×x✘]\s+(.+?)(?:\s+\d+ms)?\s*$", line)
        if m and "Test Files" not in m.group(1) and "Tests " not in m.group(1):
            out.append(Failure(name=_clip(m.group(1))))
        m2 = re.match(r"^\s*FAIL\s+(\S+)", line)
        if m2:
            out.append(Failure(name=m2.group(1)))
    return out


def parse_jest(text: str) -> Parse | None:
    if not re.search(r"Test Suites:", text):
        return None
    m = None
    for match in JEST_TESTS.finditer(text):
        m = match
    if m is None:
        return None
    found = {"passed": 0, "failed": 0, "skipped": 0, "pending": 0, "todo": 0, "total": 0}
    for cm in COUNT_COMMA.finditer(m.group(1)):
        found[cm.group(2).lower()] = int(cm.group(1))
    skipped = found["skipped"] + found["pending"] + found["todo"]
    passed, failed = found["passed"], found["failed"]
    if found["total"] and passed + failed + skipped == 0:
        return None
    failures = [Failure(name=_clip(m3.group(1))) for m3 in re.finditer(r"^\s*●\s+(.+)$", text, re.M)]
    return Parse(
        framework="jest",
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures,
        complete=True,
    )


def parse_playwright_log(text: str) -> Parse | None:
    if not re.search(r"\[(chromium|firefox|webkit)\]|Playwright Test", text, re.I):
        return None
    passed = failed = skipped = 0
    saw = False
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+(passed|failed|skipped|flaky)\b", line, re.I)
        if m:
            saw = True
            n, kind = int(m.group(1)), m.group(2).lower()
            if kind == "passed":
                passed = n
            elif kind in ("failed", "flaky"):
                failed += n
            else:
                skipped = n
    if not saw:
        return None
    failures = [
        Failure(name=_clip(m.group(1)))
        for m in re.finditer(r"\[(?:chromium|firefox|webkit)\][^\n]*", text, re.I)
        if "›" in m.group(0) or ":" in m.group(0)
    ]
    return Parse(
        framework="playwright",
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures[:20],
        complete=True,
    )


def load_junit(path: Path) -> Parse | None:
    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("TEST-*.xml")) or sorted(p for p in path.glob("*.xml") if p.is_file())
    elif path.is_file():
        files = [path]
    else:
        return None
    if not files:
        return None
    cases: list[tuple] = []
    try:
        for f in files:
            root = xml_parse(f).getroot()
            for case in root.iter("testcase"):
                name = case.get("name") or ""
                cls = case.get("classname") or ""
                label = f"{cls}::{name}".strip(":")
                fail = case.find("failure")
                err = case.find("error")
                skipped = case.find("skipped") is not None or case.find("skip") is not None
                cases.append((label, fail, err, skipped))
    except (ParseError, OSError):
        return None  # malformed XML → UNKNOWN, never PASS
    if not cases and files:
        # File parsed but had no testcase nodes — incomplete / empty suite document.
        try:
            root = xml_parse(files[0]).getroot()
        except (ParseError, OSError):
            return None  # malformed XML → UNKNOWN, never PASS
        if root.tag not in ("testsuite", "testsuites"):
            return None
        # Honour suite-level counters when present (Surefire sometimes omits bodies in summaries).
        suites = list(root.iter("testsuite"))
        if root.tag == "testsuite":
            suites = [root] + [s for s in suites if s is not root]
        if not suites and root.tag == "testsuites":
            return Parse(framework="junit", complete=True)
        passed = failed = errors = skipped = 0
        try:
            for s in suites:
                t = int(s.get("tests") or 0)
                f = int(s.get("failures") or 0)
                e = int(s.get("errors") or 0)
                k = int(s.get("skipped") or 0)
                failed += f
                errors += e
                skipped += k
                passed += max(t - f - e - k, 0)
        except (TypeError, ValueError):
            return None  # non-numeric suite counters → UNKNOWN, never PASS
        return Parse(framework="junit", passed=passed, failed=failed, errors=errors, skipped=skipped, complete=True)
    failed_n = errors_n = skipped_n = passed_n = 0
    failures: list[Failure] = []
    for label, fail, err, skipped in cases:
        if fail is not None:
            failed_n += 1
            msg = fail.get("message") or (fail.text or "failure")
            failures.append(Failure(name=label, detail=_clip(msg)))
        elif err is not None:
            errors_n += 1
            msg = err.get("message") or (err.text or "error")
            failures.append(Failure(name=label, detail=_clip(msg)))
        elif skipped:
            skipped_n += 1
        else:
            passed_n += 1
    return Parse(
        framework="junit",
        passed=passed_n,
        failed=failed_n,
        errors=errors_n,
        skipped=skipped_n,
        failures=failures,
        complete=True,
    )


def load_json_report(path: Path, prefer: str) -> Parse | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # malformed JSON → UNKNOWN, never PASS
    if not isinstance(data, dict):
        return None
    if prefer in ("auto", "playwright") and isinstance(data.get("stats"), dict) and "expected" in data["stats"]:
        if prefer not in ("auto", "playwright"):
            return None
        return _parse_playwright_json(data)
    if prefer in ("auto", "vitest", "jest") and "numPassedTests" in data:
        if prefer == "playwright":
            return None
        return _parse_jestlike_json(data, prefer if prefer in ("vitest", "jest") else "vitest")
    return None


def _parse_jestlike_json(data: dict, framework: str) -> Parse:
    passed = int(data.get("numPassedTests") or 0)
    failed = int(data.get("numFailedTests") or 0)
    skipped = int(data.get("numPendingTests") or 0) + int(data.get("numTodoTests") or 0)
    failures: list[Failure] = []
    for suite in data.get("testResults") or []:
        for asst in suite.get("assertionResults") or []:
            if asst.get("status") == "failed":
                msgs = asst.get("failureMessages") or ["failed"]
                name = asst.get("fullName") or asst.get("title") or "test"
                failures.append(Failure(name=_clip(str(name)), detail=_clip(str(msgs[0]))))
    return Parse(
        framework=framework,
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures,
        complete=True,
    )


def _parse_playwright_json(data: dict) -> Parse:
    stats = data["stats"]
    passed = int(stats.get("expected") or 0)
    failed = int(stats.get("unexpected") or 0) + int(stats.get("flaky") or 0)
    skipped = int(stats.get("skipped") or 0)
    failures: list[Failure] = []

    def walk(node: dict) -> None:
        for spec in node.get("specs") or []:
            title = spec.get("title") or ""
            for test in spec.get("tests") or []:
                for result in test.get("results") or []:
                    if result.get("status") in ("failed", "timedOut", "interrupted"):
                        err = result.get("error") or {}
                        failures.append(
                            Failure(name=_clip(title), detail=_clip(str(err.get("message") or result.get("status"))))
                        )
        for child in node.get("suites") or []:
            walk(child)

    walk(data)
    return Parse(
        framework="playwright",
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures,
        complete=True,
    )


def parse_log(text: str, framework: str) -> Parse | None:
    order: list[tuple[str, callable]]
    if framework == "pytest":
        order = [("pytest", parse_pytest)]
    elif framework == "surefire":
        order = [("surefire", parse_surefire)]
    elif framework == "flutter":
        order = [("flutter", parse_flutter)]
    elif framework == "vitest":
        order = [("vitest", parse_vitest)]
    elif framework == "jest":
        order = [("jest", parse_jest)]
    elif framework == "playwright":
        order = [("playwright", parse_playwright_log)]
    elif framework == "junit":
        return None
    else:
        order = [
            ("pytest", parse_pytest),
            ("surefire", parse_surefire),
            ("flutter", parse_flutter),
            ("vitest", parse_vitest),
            ("jest", parse_jest),
            ("playwright", parse_playwright_log),
        ]
    for name, fn in order:
        got = fn(text)
        if got is not None:
            got.framework = name
            return got
    return None


def decide_status(parse: Parse | None, exit_code: int) -> tuple[str, str]:
    if parse is None:
        return "UNKNOWN", "unparseable"
    if not parse.complete:
        return "UNKNOWN", "truncated"
    if parse.failed > 0 or parse.errors > 0:
        return "FAIL", "failures"
    if executed(parse) == 0:
        return "FAIL", "zero_executed"
    if exit_code != 0:
        return "FAIL", "nonzero_exit"
    return "PASS", "ok"


def format_report(
    parse: Parse | None,
    status: str,
    reason: str,
    exit_code: int,
    log: Path,
    raw: str,
    max_failures: int,
    max_tail: int,
) -> str:
    fw = parse.framework if parse else "unknown"
    if parse is None or not parse.complete:
        p = f = e = s = x = "?"
    else:
        p, f, e, s = parse.passed, parse.failed, parse.errors, parse.skipped
        x = executed(parse)
    lines = [
        "TEST SUMMARY"
        f" | framework={fw}"
        f" | status={status}"
        f" | passed={p} failed={f} errors={e} skipped={s} executed={x}"
        f" | exit={exit_code}"
        f" | log={log}"
        f" | reason={reason}"
    ]
    shown: list[Failure] = []
    extra = 0
    if parse and parse.failures:
        shown = parse.failures[:max_failures]
        extra = max(0, len(parse.failures) - max_failures)
        lines.append(f"FAILURES ({len(parse.failures)}):")
        for item in shown:
            detail = f": {item.detail}" if item.detail else ""
            lines.append(f"- {item.name}{detail}")
        if extra:
            lines.append(f"- ... and {extra} more (see log)")
    if status == "UNKNOWN":
        lines.append(f"UNPARSED TAIL (raw log preserved at {log}):")
        tail = raw.splitlines()[-max_tail:] if raw.strip() else ["(empty log)"]
        lines.extend(tail)
    return "\n".join(lines) + "\n"


def summarize(
    log: Path,
    exit_code: int,
    framework: str = "auto",
    junit: Path | None = None,
    json_path: Path | None = None,
    max_failures: int = 10,
    max_tail: int = 15,
) -> str:
    raw, _sliced = read_log(log)
    parse: Parse | None = None
    if junit is not None:
        parse = load_junit(junit)
        if parse is not None and framework not in ("auto", "junit", "pytest", "surefire"):
            parse = None
    if parse is None and json_path is not None:
        parse = load_json_report(json_path, framework)
    if parse is None:
        parse = parse_log(raw, framework)
    # _sliced-but-complete (summary in the last 2MB) is intentional: trust the tail.
    status, reason = decide_status(parse, exit_code)
    return format_report(parse, status, reason, exit_code, log, raw, max_failures, max_tail)


def selftest() -> int:
    fail = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal fail
        if cond:
            print(f"  PASS {name}")
        else:
            fail += 1
            print(f"  FAIL {name} -> {detail}")

    def run(text: str, exit_code: int, **kwargs) -> str:
        tmp = Path(kwargs.pop("tmp"))
        log = tmp / "test.log"
        log.write_text(text, encoding="utf-8")
        before = log.read_bytes()
        report = summarize(log, exit_code, **kwargs)
        check(f"preserves log ({name_hint(text)})", log.read_bytes() == before, "log mutated")
        return report

    def name_hint(text: str) -> str:
        return text.strip().splitlines()[0][:40] if text.strip() else "empty"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        pytest_pass = (
            "============================= test session starts ==============================\n"
            "collected 5 items\n"
            "tests/test_ok.py .....                                                  [100%]\n"
            "============================== 5 passed in 0.04s ===============================\n"
        )
        r = run(pytest_pass, 0, tmp=tmp, framework="pytest")
        check("pytest pass → PASS executed=5", "status=PASS" in r and "executed=5" in r and "passed=5" in r, r)

        pytest_fail = (
            "============================= test session starts ==============================\n"
            "collected 8 items\n"
            "FAILED tests/test_user.py::test_create_user_duplicate - AssertionError: expected 409\n"
            "FAILED tests/test_payment.py::test_payment_timeout - TimeoutError: 30s\n"
            "ERROR tests/test_db.py::test_connect - RuntimeError: boom\n"
            "=========================== short test summary info ============================\n"
            "================= 2 failed, 1 error, 4 passed, 1 skipped in 0.20s =================\n"
        )
        r = run(pytest_fail, 1, tmp=tmp, framework="pytest")
        check(
            "pytest fail counts + names",
            "status=FAIL" in r
            and "failed=2" in r
            and "errors=1" in r
            and "passed=4" in r
            and "skipped=1" in r
            and "test_create_user_duplicate" in r
            and "test_payment_timeout" in r
            and "test_connect" in r,
            r,
        )
        check("pytest fail omits traceback dump", "Traceback" not in r, r)

        junit = tmp / "junit.xml"
        junit.write_text(
            """<?xml version="1.0"?>
<testsuites tests="3" failures="1" errors="0" skipped="1">
  <testsuite name="pytest" tests="3" failures="1" errors="0" skipped="1">
    <testcase classname="tests.test_user" name="test_ok"/>
    <testcase classname="tests.test_user" name="test_dup">
      <failure message="AssertionError: 409">AssertionError: 409</failure>
    </testcase>
    <testcase classname="tests.test_user" name="test_skip"><skipped/></testcase>
  </testsuite>
</testsuites>
""",
            encoding="utf-8",
        )
        (tmp / "test.log").write_text("noise\n", encoding="utf-8")
        r = summarize(tmp / "test.log", 1, framework="pytest", junit=junit)
        check(
            "pytest junit artifact wins over noise log",
            "status=FAIL" in r and "failed=1" in r and "passed=1" in r and "skipped=1" in r and "test_dup" in r,
            r,
        )

        surefire_pass = "[INFO] Tests run: 47, Failures: 0, Errors: 0, Skipped: 0\n"
        r = run(surefire_pass, 0, tmp=tmp, framework="surefire")
        check("surefire pass → PASS executed=47", "status=PASS" in r and "executed=47" in r, r)

        surefire_mid = (
            "[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0\n"
            "[ERROR] Failures: \n"
            "[ERROR]   UserServiceTest.testCreateUser_withDuplicateEmail:45 expected 409\n"
            "[ERROR] Errors: \n"
            "[ERROR]   OrderRepoTest.save_whenDbDown:12 NullPointerException\n"
            "[INFO] Tests run: 47, Failures: 2, Errors: 1, Skipped: 0\n"
        )
        r = run(surefire_mid, 1, tmp=tmp, framework="surefire")
        check(
            "surefire last Tests run: wins + failure names",
            "status=FAIL" in r
            and "failed=2" in r
            and "errors=1" in r
            and "executed=47" in r
            and "UserServiceTest.testCreateUser_withDuplicateEmail" in r
            and "OrderRepoTest.save_whenDbDown" in r,
            r,
        )

        sure_dir = tmp / "surefire-reports"
        sure_dir.mkdir()
        (sure_dir / "TEST-UserServiceTest.xml").write_text(
            """<?xml version="1.0"?>
<testsuite name="UserServiceTest" tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="com.company.UserServiceTest" name="ok"/>
  <testcase classname="com.company.UserServiceTest" name="dup">
    <failure message="expected 409">expected 409</failure>
  </testcase>
</testsuite>
""",
            encoding="utf-8",
        )
        (tmp / "test.log").write_text("", encoding="utf-8")
        r = summarize(tmp / "test.log", 1, framework="surefire", junit=sure_dir)
        check("maven surefire XML dir (quiet log)", "status=FAIL" in r and "failed=1" in r and "dup" in r, r)

        flutter_pass = "00:02 +31: All tests passed!\n"
        r = run(flutter_pass, 0, tmp=tmp, framework="flutter")
        check("flutter pass → PASS executed=31", "status=PASS" in r and "executed=31" in r, r)

        flutter_fail = (
            "00:01 +5 -1: /tmp/app/test/user_test.dart: createUser throws ConflictException when email is duplicate [E]\n"
            "  Expected: true\n"
            "    Actual: <false>\n"
            "00:02 +5 -1: Some tests failed.\n"
        )
        r = run(flutter_fail, 1, tmp=tmp, framework="flutter")
        check(
            "flutter fail counts + [E] name, no Expected/Actual dump",
            "status=FAIL" in r
            and "passed=5" in r
            and "failed=1" in r
            and "createUser throws ConflictException" in r
            and "Actual:" not in r,
            r,
        )

        vitest_pass = (
            "   ✓ src/app.spec.ts (12 tests) 45ms\n"
            " Test Files  1 passed (1)\n"
            "      Tests  12 passed (12)\n"
        )
        r = run(vitest_pass, 0, tmp=tmp, framework="vitest")
        check("vitest/angular-like pass", "status=PASS" in r and "passed=12" in r, r)

        angular_ng = (
            "\n > @angular-devkit/build-angular:unit-test\n\n"
            " ✓ src/app.component.spec.ts (1 test) 23ms\n"
            " Test Files  1 passed (1)\n"
            "      Tests  1 passed (1)\n"
            "   Duration  1.23s\n"
        )
        r = run(angular_ng, 0, tmp=tmp, framework="vitest")
        check("angular ng test Vitest wrapper → PASS", "status=PASS" in r and "passed=1" in r, r)

        vitest_fail = (
            "   × src/app.spec.ts (12 tests | 1 failed) 45ms\n"
            "     × should throw ConflictException when email already exists\n"
            " Test Files  1 failed (1)\n"
            "      Tests  1 failed | 11 passed | 3 skipped (15)\n"
        )
        r = run(vitest_fail, 1, tmp=tmp, framework="vitest")
        check(
            "vitest fail + skipped (NestJS/React/Angular)",
            "status=FAIL" in r and "failed=1" in r and "passed=11" in r and "skipped=3" in r
            and "should throw ConflictException" in r,
            r,
        )

        vjson = tmp / "vitest.json"
        vjson.write_text(
            json.dumps(
                {
                    "numPassedTests": 11,
                    "numFailedTests": 1,
                    "numPendingTests": 3,
                    "numTodoTests": 0,
                    "numTotalTests": 15,
                    "testResults": [
                        {
                            "assertionResults": [
                                {
                                    "status": "failed",
                                    "fullName": "AuthService duplicate email",
                                    "failureMessages": ["AssertionError: expected 409"],
                                }
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (tmp / "test.log").write_text("ignored\n", encoding="utf-8")
        r = summarize(tmp / "test.log", 1, framework="vitest", json_path=vjson)
        check("vitest JSON report", "status=FAIL" in r and "AuthService duplicate email" in r and "executed=12" in r, r)

        jest_fail = (
            "Test Suites: 1 failed, 1 total\n"
            "Tests:       1 failed, 3 skipped, 12 passed, 16 total\n"
            "  ● UserService › rejects duplicate email\n"
        )
        r = run(jest_fail, 1, tmp=tmp, framework="jest")
        check(
            "jest fail counts + bullet name",
            "status=FAIL" in r and "failed=1" in r and "passed=12" in r and "skipped=3" in r
            and "rejects duplicate email" in r,
            r,
        )

        pjson = tmp / "playwright.json"
        pjson.write_text(
            json.dumps(
                {
                    "stats": {"expected": 8, "unexpected": 1, "flaky": 1, "skipped": 2},
                    "suites": [
                        {
                            "specs": [
                                {
                                    "title": "login fails on bad password",
                                    "tests": [{"results": [{"status": "failed", "error": {"message": "Timeout"}}]}],
                                }
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (tmp / "test.log").write_text(
            "Running 12 tests using 1 worker\n  1 failed\n    [chromium] › tests/login.spec.ts:12:5 › login fails\n  8 passed (2.1s)\n",
            encoding="utf-8",
        )
        r = summarize(tmp / "test.log", 1, framework="playwright", json_path=pjson)
        check(
            "playwright JSON: flaky counts as failed",
            "status=FAIL" in r and "failed=2" in r and "passed=8" in r and "skipped=2" in r
            and "login fails on bad password" in r,
            r,
        )

        # --- negatives / edges ---
        unknown = "Build finished. 5 passed the lint heuristic. Have a nice day.\n"
        r = run(unknown, 0, tmp=tmp, framework="auto")
        check("unknown format + exit 0 → UNKNOWN never PASS", "status=UNKNOWN" in r and "status=PASS" not in r, r)
        check("unknown still prints log path and tail", "log=" in r and "UNPARSED TAIL" in r and "Have a nice day" in r, r)

        r = run(unknown, 1, tmp=tmp, framework="auto")
        check("unknown format + nonzero exit → UNKNOWN not FAIL-from-guess", "status=UNKNOWN" in r and "exit=1" in r, r)

        empty = ""
        r = run(empty, 0, tmp=tmp, framework="auto")
        check("empty log + exit 0 → UNKNOWN", "status=UNKNOWN" in r and "(empty log)" in r, r)

        truncated = (
            "============================= test session starts ==============================\n"
            "collected 40 items\n"
            "tests/test_a.py ..........\n"
            "FAILED tests/test_user.py::test_create_user_duplicate - AssertionError\n"
            # no final ===== summary
        )
        r = run(truncated, 1, tmp=tmp, framework="pytest")
        check(
            "truncated pytest → UNKNOWN, never PASS, names still listed",
            "status=UNKNOWN" in r and "status=PASS" not in r and "reason=truncated" in r
            and "test_create_user_duplicate" in r,
            r,
        )

        (tmp / "bad.xml").write_text("<testsuite><testcase name='x'><failure", encoding="utf-8")
        (tmp / "test.log").write_text("not a test log\n", encoding="utf-8")
        r = summarize(tmp / "test.log", 0, framework="pytest", junit=tmp / "bad.xml")
        check("malformed junit → UNKNOWN never PASS", "status=UNKNOWN" in r and "status=PASS" not in r, r)

        (tmp / "nan.xml").write_text(
            '<testsuite name="empty" tests="N/A" failures="0" errors="0" skipped="0"/>',
            encoding="utf-8",
        )
        r = summarize(tmp / "test.log", 0, framework="surefire", junit=tmp / "nan.xml")
        check("non-numeric junit counters → UNKNOWN never PASS (no traceback)", "status=UNKNOWN" in r and "status=PASS" not in r, r)

        (tmp / "bad.json").write_text("{not json", encoding="utf-8")
        r = summarize(tmp / "test.log", 0, framework="vitest", json_path=tmp / "bad.json")
        check("malformed json → UNKNOWN never PASS", "status=UNKNOWN" in r and "status=PASS" not in r, r)

        r = run(pytest_pass, 1, tmp=tmp, framework="pytest")
        check(
            "nonzero exit + all-passed summary → FAIL not PASS",
            "status=FAIL" in r and "reason=nonzero_exit" in r and "status=PASS" not in r,
            r,
        )

        skipped_only = (
            "============================= test session starts ==============================\n"
            "collected 4 items\n"
            "============================== 4 skipped in 0.01s ==============================\n"
        )
        r = run(skipped_only, 0, tmp=tmp, framework="pytest")
        check(
            "all skipped + exit 0 → FAIL zero_executed",
            "status=FAIL" in r and "reason=zero_executed" in r and "executed=0" in r,
            r,
        )

        no_tests = "============================ no tests ran in 0.12s =============================\n"
        r = run(no_tests, 5, tmp=tmp, framework="pytest")
        check("pytest no tests ran (exit 5) → FAIL zero_executed", "status=FAIL" in r and "reason=zero_executed" in r, r)

        r = run(surefire_pass, 0, tmp=tmp, framework="pytest")
        check(
            "honour --framework: surefire log as pytest → UNKNOWN",
            "status=UNKNOWN" in r,
            r,
        )

        bulky = (
            "============================= test session starts ==============================\n"
            + ("tests/test_bulk.py " + ("." * 80) + "\n") * 200
            + "[warning] " + ("x" * 200 + "\n") * 50
            + "============================= 200 passed in 4.12s ==============================\n"
        )
        r = run(bulky, 0, tmp=tmp, framework="pytest")
        raw_tokens = max(1, len(bulky) // 4)
        sum_tokens = max(1, len(r) // 4)
        check("bulky pass → PASS", "status=PASS" in r and "passed=200" in r, r)
        check(
            f"token reduction vs full log ({sum_tokens} << {raw_tokens})",
            sum_tokens * 20 < raw_tokens and "status=PASS" in r,
            f"summary_tokens={sum_tokens} raw_tokens={raw_tokens} report={r!r}",
        )
        tail10 = "\n".join(bulky.splitlines()[-10:])
        tail_tokens = max(1, len(tail10) // 4)
        check(
            f"summary not larger than tail -10 ({sum_tokens} vs tail {tail_tokens})",
            sum_tokens <= tail_tokens + 20,
            f"summary={sum_tokens} tail={tail_tokens}",
        )

        # failure details survive compaction
        check(
            "failed-test names survive compaction",
            "test_create_user_duplicate" in run(pytest_fail, 1, tmp=tmp, framework="pytest"),
            "",
        )

        # missing junit path falls back to log
        (tmp / "test.log").write_text(pytest_pass, encoding="utf-8")
        r = summarize(tmp / "test.log", 0, framework="pytest", junit=tmp / "missing.xml")
        check("missing --junit falls back to pytest log", "status=PASS" in r and "passed=5" in r, r)

    # usage: missing log
    err = io.StringIO()
    with redirect_stderr(err):
        rc = main_argv(["--log", str(KIT / "no-such-log-file.log"), "--exit-code", "0"])
    check("missing log → exit 2", rc == 2 and "log not found" in err.getvalue(), rc)

    body = VERIFY_MD.read_text(encoding="utf-8") if VERIFY_MD.is_file() else ""
    check("verify.md exists", VERIFY_MD.is_file(), str(VERIFY_MD))
    for needle, label in (
        ("summarize-test-log.py", "script cited"),
        ("--exit-code", "original rc passed in"),
        ("--framework surefire", "Spring/Maven"),
        ("--framework pytest", "Python"),
        ("--framework flutter", "Flutter"),
        ("--junit /tmp/junit.xml", "pytest junit"),
        ("target/surefire-reports", "maven XML dir"),
        ("UNKNOWN, never PASS", "unknown policy"),
        ("rc=$?", "rc captured before summarize"),
    ):
        check(f"verify.md wires {label}", needle in body, needle)

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main_argv(argv: list[str]) -> int:
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("--log")
    p.add_argument("--exit-code", type=int)
    p.add_argument("--framework", choices=FRAMEWORKS, default="auto")
    p.add_argument("--junit", type=Path)
    p.add_argument("--json", dest="json_path", type=Path)
    p.add_argument("--max-failures", type=int, default=10)
    p.add_argument("--max-tail", type=int, default=15)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.log is None or args.exit_code is None:
        print("specify --log PATH and --exit-code N (or --selftest)", file=sys.stderr)
        return 2
    log = Path(args.log)
    if not log.is_file():
        print(f"log not found: {log}", file=sys.stderr)
        return 2
    sys.stdout.write(
        summarize(
            log,
            args.exit_code,
            framework=args.framework,
            junit=args.junit,
            json_path=args.json_path,
            max_failures=args.max_failures,
            max_tail=args.max_tail,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_argv(sys.argv[1:]))
