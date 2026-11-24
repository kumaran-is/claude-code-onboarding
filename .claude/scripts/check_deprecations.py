#!/usr/bin/env python3
"""Fail on deprecations whose removal date has passed.

Convention: every deprecation carries a dated marker in the comment or decorator next to it:
`REMOVE-BY: 2027-03-31` (case-insensitive; `remove-by=`, `remove by` also accepted). The marker is the contract:
a deprecated route, flag, column or API with no date never gets removed, and one with a passed date is debt
that ships silently. FAIL: date < today. WARN: due within --warn-days (default 30). Malformed date: FAIL.

Usage: check_deprecations.py [ROOT] [--today YYYY-MM-DD] [--warn-days N]  |  --selftest
Exit: 0 clean, 1 overdue or malformed, 2 nothing scanned.
"""
import argparse
import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 10):  # `X | None` annotations below need 3.10; say so instead of a TypeError
    sys.exit(f"{Path(__file__).name} needs Python 3.10+, found {sys.version.split()[0]}")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".dart_tool", "__pycache__", "target", ".claude"}
EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".java", ".kt", ".dart", ".go", ".sql", ".yaml", ".yml", ".tf", ".html"}
MARK_RE = re.compile(r"(?i)\bremove[- ]by\s*[:=]?\s*(\S+)")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def today_utc() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def scan(root: Path, today: dt.date, warn_days: int) -> tuple[int, list[str]]:
    lines, files, marks = [], 0, 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in EXT or set(p.relative_to(root).parts[:-1]) & SKIP_DIRS:
            continue
        files += 1
        for n, text in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in MARK_RE.finditer(text):
                marks += 1
                where, raw = f"{p.relative_to(root)}:{n}", m.group(1).strip(".,;)'\"`")
                if not DATE_RE.fullmatch(raw):
                    lines.append(f"FAIL {where}: REMOVE-BY needs YYYY-MM-DD, got {raw!r}")
                    continue
                try:
                    due = dt.date.fromisoformat(raw)
                except ValueError:
                    lines.append(f"FAIL {where}: invalid date {raw}")
                    continue
                if due < today:
                    lines.append(f"FAIL {where}: removal was due {due} ({(today - due).days} day(s) overdue): remove it or re-date it with a reason")
                elif (due - today).days <= warn_days:
                    lines.append(f"WARN {where}: removal due {due} (in {(due - today).days} day(s))")
    if files == 0:
        return 2, [f"BLOCKED: no source files under {root}"]
    lines.append(f"scanned: {files} file(s), {marks} REMOVE-BY marker(s), today={today}")
    return (1 if any(l.startswith("FAIL") for l in lines) else 0), lines


def selftest() -> int:
    fails = 0

    def ok(cond: bool, label: str, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f" -> {detail}"))
        fails += 0 if cond else 1

    ok(isinstance(today_utc(), dt.date), "the default clock (no --today) works on this interpreter")
    today = dt.date(2026, 11, 24)  # injected clock: the result never depends on when the selftest runs
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "api.py").write_text("# deprecated: use /v2/orders. REMOVE-BY: 2027-06-30\n")
        rc, out = scan(root, today, 30)
        ok(rc == 0 and not any(l.startswith(("FAIL", "WARN")) for l in out), "negative: a future date is clean", out)
        (root / "flags.ts").write_text("// remove-by=2026-12-10 legacy toggle\n")
        rc, out = scan(root, today, 30)
        ok(rc == 0 and any(l.startswith("WARN") and "flags.ts:1" in l for l in out), "positive: due within 30 days WARNs", out)
        (root / "Old.java").write_text("@Deprecated(forRemoval = true) // REMOVE-BY: 2026-11-01\n")
        rc, out = scan(root, today, 30)
        ok(rc == 1 and any("Old.java:1" in l and "23 day(s) overdue" in l for l in out), "positive: a passed date FAILs with file:line", out)
        (root / "Old.java").write_text("// REMOVE-BY: next sprint\n")
        rc, out = scan(root, today, 30)
        ok(rc == 1 and any("YYYY-MM-DD" in l for l in out), "positive: an undated marker FAILs", out)
        ok(scan(root, dt.date(2026, 1, 1), 30)[0] == 1, "the same tree under another clock still fails only on the malformed marker")
        (root / "Old.java").unlink()
        rc, out = scan(root, dt.date(2027, 7, 1), 30)
        ok(rc == 1 and any("api.py:1" in l for l in out), "positive: time passing turns a clean marker into a FAIL", out)
    with tempfile.TemporaryDirectory() as d:
        ok(scan(Path(d), today, 30)[0] == 2, "an empty tree is BLOCKED, never clean")
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--today", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--warn-days", type=int, default=30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rc, lines = scan(Path(a.root).resolve(), a.today or today_utc(), a.warn_days)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
