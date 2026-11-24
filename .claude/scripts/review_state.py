#!/usr/bin/env python3
"""Review state for the opt-in enforcement kit: findings ledger + content-fingerprinted evidence stamps.

State lives under .claude/state/review/<branch>/ (gitignored): ledger.json, stamps/<name>.json and the
opt-in marker `enabled`. Hooks import this file; humans and Claude use the CLI.

  review_state.py init | enabled | disable
  review_state.py findings add --reviewer R --severity S --summary T [--location L]
  review_state.py findings list [--state OPEN]
  review_state.py findings close ID --class CONTROL|MECHANISM|STATIC|NOCONTROL --evidence TEXT
  review_state.py findings dismiss ID --reason TEXT
  review_state.py findings fail ID --note TEXT       (a close did not survive re-verification)
  review_state.py findings blocking                  (exit 1 when any finding blocks)
  review_state.py findings rereview                  (reviewers whose findings were closed since their last report)
  review_state.py stamp write NAME [--note TEXT]     (after the check PASSED on the current tree)
  review_state.py stamp check NAME                   (VALID | CHANGED | EXPIRED | MISSING | UNKNOWN; exit 0 only on VALID)
  review_state.py --selftest

Rules (verification-before-completion/reference/verification-loop.md §4):
  - closing needs an evidence class; STATIC evidence must cite path:line; evidence/reasons >= 20 chars.
  - 2 failed closes -> INVESTIGATION_REQUIRED, which closes only with CONTROL or MECHANISM evidence.
  - review round = most reports by any one reviewer; rounds 1-2 block on every open finding, round 3+
    only on CRITICAL/HIGH (MEDIUM/LOW stay open and go into the PR body).
  - a stamp is VALID only when the working-tree content fingerprint matches and it is younger than
    REVIEW_STAMP_MAX_AGE_HOURS (default 72). Anything else is not valid evidence.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
CLASSES = ("CONTROL", "MECHANISM", "STATIC", "NOCONTROL")
OPEN_STATES = ("OPEN", "INVESTIGATION_REQUIRED")
FINDING_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?FINDING:\s*(CRITICAL|HIGH|MEDIUM|LOW)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*`?\s*$", re.M)
NONE_RE = re.compile(r"^\s*(?:[-*]\s*)?`?FINDINGS:\s*none\b", re.M | re.I)
CONTRACT = (
    "FINDINGS LEDGER CONTRACT (enforcement kit is on for this branch): end your report with one line per "
    "finding, exactly `FINDING: <CRITICAL|HIGH|MEDIUM|LOW> | <path:line or area> | <one-line summary>`, "
    "or the single line `FINDINGS: none`. Lines in any other shape are not recorded.")


def git(*args: str, cwd: Path, env: dict | None = None, timeout: int = 20) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        return Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()))
    except (RuntimeError, OSError):
        return Path.cwd()


def state_dir(root: Path) -> Path:
    try:
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    except (RuntimeError, OSError):
        branch = "no-git"
    return root / ".claude" / "state" / "review" / re.sub(r"[^A-Za-z0-9._-]", "__", branch)


def is_enabled(root: Path) -> bool:
    return os.environ.get("CLAUDE_ENFORCEMENT_KIT") == "1" or (state_dir(root) / "enabled").is_file()


@contextlib.contextmanager
def ledger(root: Path, write: bool = False):
    """Yield the ledger dict under an exclusive lock; persist atomically when write=True."""
    import fcntl
    d = state_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "ledger.json"
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.is_file() else {"next_id": 1, "findings": [], "reports": {}}
        yield data
        if write:
            fd, tmp = tempfile.mkstemp(dir=d)
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, path)


def review_round(data: dict) -> int:
    counts: dict[str, int] = {}
    for rep in data["reports"].values():
        counts[rep["reviewer"]] = counts.get(rep["reviewer"], 0) + 1
    return max(counts.values(), default=0)


def blocking(data: dict) -> list[dict]:
    late = review_round(data) >= 3
    return [f for f in data["findings"] if f["state"] in OPEN_STATES
            and (not late or f["severity"] in ("CRITICAL", "HIGH") or f["state"] == "INVESTIGATION_REQUIRED")]


def add_finding(data: dict, reviewer: str, severity: str, summary: str, location: str = "-", agent_id: str = "") -> dict:
    severity = severity.upper()
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    for f in data["findings"]:  # the same reviewer re-reporting an open finding does not duplicate it
        if f["state"] in OPEN_STATES and f["reviewer"] == reviewer and f["summary"] == summary and f["location"] == location:
            return f
    f = {"id": f"F{data['next_id']}", "reviewer": reviewer, "severity": severity, "location": location,
         "summary": summary, "state": "OPEN", "attempts": 0, "agent_id": agent_id, "opened": time.time(),
         "resolution": None}
    data["next_id"] += 1
    data["findings"].append(f)
    return f


def record_report(data: dict, reviewer: str, agent_id: str, text: str) -> tuple[str, int]:
    """Parse a reviewer report. Returns (status, count): status is recorded | duplicate | none | missing."""
    if agent_id and agent_id in data["reports"]:
        return "duplicate", 0
    rows = FINDING_RE.findall(text or "")
    if not rows and not NONE_RE.search(text or ""):
        return "missing", 0
    for sev, loc, summary in rows:
        add_finding(data, reviewer, sev, summary, loc, agent_id)
    data["reports"][agent_id or f"anon-{len(data['reports']) + 1}"] = {"reviewer": reviewer, "at": time.time(), "count": len(rows)}
    return ("recorded" if rows else "none"), len(rows)


def find(data: dict, fid: str) -> dict:
    for f in data["findings"]:
        if f["id"] == fid:
            return f
    raise ValueError(f"no finding {fid}")


def close(data: dict, fid: str, klass: str, evidence: str) -> dict:
    f = find(data, fid)
    klass = klass.upper()
    if f["state"] not in OPEN_STATES:
        raise ValueError(f"{fid} is {f['state']}, not open")
    if klass not in CLASSES:
        raise ValueError(f"class must be one of {CLASSES}")
    if len(evidence.strip()) < 20:
        raise ValueError("evidence must say what proves it (>= 20 chars)")
    if klass == "STATIC" and not re.search(r"\S+:\d+", evidence):
        raise ValueError("STATIC evidence must cite path:line")
    if f["state"] == "INVESTIGATION_REQUIRED" and klass not in ("CONTROL", "MECHANISM"):
        raise ValueError(f"{fid} failed twice: close it only with CONTROL or MECHANISM evidence")
    f.update(state="CLOSED", resolution={"class": klass, "evidence": evidence.strip(), "at": time.time()})
    return f


def dismiss(data: dict, fid: str, reason: str) -> dict:
    f = find(data, fid)
    if len(reason.strip()) < 20:
        raise ValueError("a dismissal needs a reason (>= 20 chars)")
    f.update(state="DISMISSED", resolution={"class": "DISMISSED", "evidence": reason.strip(), "at": time.time()})
    return f


def fail(data: dict, fid: str, note: str) -> dict:
    f = find(data, fid)
    f["attempts"] += 1
    f["state"] = "INVESTIGATION_REQUIRED" if f["attempts"] >= 2 else "OPEN"
    f.setdefault("notes", []).append(note)
    return f


def rereview(data: dict) -> list[str]:
    last: dict[str, float] = {}
    for rep in data["reports"].values():
        last[rep["reviewer"]] = max(last.get(rep["reviewer"], 0), rep["at"])
    owners = {f["reviewer"] for f in data["findings"]
              if f["state"] == "CLOSED" and f["resolution"]["at"] > last.get(f["reviewer"], 0)}
    owners |= {f["reviewer"] for f in data["findings"] if f["state"] in OPEN_STATES}
    return sorted(owners)


# ── content-fingerprinted evidence stamps ─────────────────────────────────────────────────────────
SCOPES = {  # stamps whose evidence covers only part of the tree; every other stamp covers all of it
    "ui-web": [":(glob)**/*.tsx", ":(glob)**/*.jsx", ":(glob)**/*.component.*", ":(glob)**/src/app/**"],
    "ui-mobile": [":(glob)**/lib/**/*.dart", ":(glob)**/pubspec.yaml"],
}


GIT_BUDGET_S = 10  # each git call stays well under the hook timeouts (10-30 s), so a timeout reaches our handler


def fingerprint(root: Path, scope: list[str] | None = None) -> str:
    """sha256 over (path, executable bit, content | symlink target | submodule commit) for tracked + untracked
    files in scope (.gitignore respected). Hashed in Python from the -z list, so odd file names are exact.
    The index is never written."""
    import hashlib
    spec = (scope or ["."]) + [":(exclude).claude/state"]
    out = subprocess.run(["git", "ls-files", "-z", "-c", "-o", "--exclude-standard", "--", *spec], cwd=root,
                         capture_output=True, timeout=GIT_BUDGET_S)
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files: {out.stderr.decode(errors='replace').strip()[:200]}")
    digest = hashlib.sha256()
    for raw in sorted(set(out.stdout.split(b"\0"))):
        if not raw:
            continue
        path = root / os.fsdecode(raw)
        digest.update(raw + b"\0")
        if path.is_symlink():
            digest.update(b"L" + os.fsencode(os.readlink(path)))
        elif path.is_dir():  # a submodule (gitlink): its checked-out commit
            sub = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, timeout=GIT_BUDGET_S)
            digest.update(b"S" + sub.stdout.strip())
        elif path.is_file():
            digest.update(b"X" if os.access(path, os.X_OK) else b"F")
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
        else:
            digest.update(b"D")  # tracked but deleted
        digest.update(b"\0")
    return digest.hexdigest()


def stamp_write(root: Path, name: str, note: str = "") -> dict:
    d = state_dir(root) / "stamps"
    d.mkdir(parents=True, exist_ok=True)
    scope = SCOPES.get(name)
    rec = {"name": name, "tree": fingerprint(root, scope), "scope": scope, "at": time.time(), "note": note}
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w") as fh:
        json.dump(rec, fh, indent=2)
    os.replace(tmp, d / f"{name}.json")
    return rec


def stamp_check(root: Path, name: str) -> tuple[str, str]:
    path = state_dir(root) / "stamps" / f"{name}.json"
    if not path.is_file():
        return "MISSING", f"no '{name}' stamp for this branch"
    try:
        rec = json.loads(path.read_text())
        tree, at = rec["tree"], float(rec["at"])
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return "UNKNOWN", f"unreadable '{name}' stamp ({type(exc).__name__}): write it again"
    try:
        current = fingerprint(root, rec.get("scope"))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return "UNKNOWN", f"cannot fingerprint the tree: {exc}"
    if current != tree:
        return "CHANGED", f"files changed since '{name}' passed"
    age_h = (time.time() - at) / 3600
    if age_h > float(os.environ.get("REVIEW_STAMP_MAX_AGE_HOURS", "72")):
        return "EXPIRED", f"'{name}' passed {age_h:.0f}h ago"
    return "VALID", f"'{name}' matches the current tree ({rec.get('note') or 'no note'})"


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def cli(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="review_state.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init"); sub.add_parser("enabled"); sub.add_parser("disable")
    fp = sub.add_parser("findings").add_subparsers(dest="op", required=True)
    a = fp.add_parser("add"); a.add_argument("--reviewer", required=True); a.add_argument("--severity", required=True)
    a.add_argument("--summary", required=True); a.add_argument("--location", default="-")
    ls = fp.add_parser("list"); ls.add_argument("--state")
    c = fp.add_parser("close"); c.add_argument("id"); c.add_argument("--class", dest="klass", required=True); c.add_argument("--evidence", required=True)
    dm = fp.add_parser("dismiss"); dm.add_argument("id"); dm.add_argument("--reason", required=True)
    fl = fp.add_parser("fail"); fl.add_argument("id"); fl.add_argument("--note", required=True)
    fp.add_parser("blocking"); fp.add_parser("rereview")
    sp = sub.add_parser("stamp").add_subparsers(dest="op", required=True)
    sw = sp.add_parser("write"); sw.add_argument("name"); sw.add_argument("--note", default="")
    sc = sp.add_parser("check"); sc.add_argument("name")
    args = p.parse_args(argv)
    root = project_root()
    if args.cmd == "init":
        d = state_dir(root); d.mkdir(parents=True, exist_ok=True); (d / "enabled").write_text("opt-in\n")
        print(f"enforcement kit ON for this branch ({d.relative_to(root)})"); return 0
    if args.cmd == "disable":
        (state_dir(root) / "enabled").unlink(missing_ok=True); print("enforcement kit OFF for this branch"); return 0
    if args.cmd == "enabled":
        on = is_enabled(root); print("on" if on else "off"); return 0 if on else 1
    if args.cmd == "stamp":
        if args.op == "write":
            rec = stamp_write(root, args.name, args.note); print(f"stamp {args.name} = {rec['tree'][:12]}"); return 0
        status, why = stamp_check(root, args.name); print(f"{status}: {why}"); return 0 if status == "VALID" else 1
    try:
        with ledger(root, write=args.op in ("add", "close", "dismiss", "fail")) as data:
            if args.op == "add":
                f = add_finding(data, args.reviewer, args.severity, args.summary, args.location); print(f["id"])
            elif args.op == "list":
                for f in data["findings"]:
                    if not args.state or f["state"] == args.state:
                        print(f"{f['id']}\t{f['state']}\t{f['severity']}\t{f['reviewer']}\t{f['location']}\t{f['summary']}")
                print(f"round {review_round(data)}; {len(blocking(data))} blocking")
            elif args.op == "close":
                close(data, args.id, args.klass, args.evidence); print(f"{args.id} CLOSED ({args.klass.upper()})")
            elif args.op == "dismiss":
                dismiss(data, args.id, args.reason); print(f"{args.id} DISMISSED")
            elif args.op == "fail":
                print(f"{args.id} {fail(data, args.id, args.note)['state']}")
            elif args.op == "blocking":
                rows = blocking(data)
                for f in rows:
                    print(f"{f['id']}\t{f['state']}\t{f['severity']}\t{f['reviewer']}\t{f['summary']}")
                print(f"round {review_round(data)}: {len(rows)} blocking finding(s)"); return 1 if rows else 0
            elif args.op == "rereview":
                print(" ".join(rereview(data)) or "none")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    return 0


def selftest() -> int:
    fails = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")
        fails += 0 if cond else 1

    def raises(fn, label: str) -> None:
        try:
            fn(); ok(False, label)
        except ValueError:
            ok(True, label)

    data = {"next_id": 1, "findings": [], "reports": {}}
    rep = "Review done.\nFINDING: HIGH | src/a.py:10 | token not verified\n- `FINDING: LOW | docs | typo`\nHIGH risk overall\n"
    ok(record_report(data, "code-reviewer", "a1", rep) == ("recorded", 2), "positive: two contract lines recorded; prose 'HIGH risk' ignored")
    ok(record_report(data, "code-reviewer", "a1", rep) == ("duplicate", 0), "negative: the same agent_id twice records nothing (no double SubagentStop)")
    ok(record_report(data, "x-reviewer", "a2", "Looks fine to me.") == ("missing", 0), "positive: a report with no contract line is 'missing'")
    ok(record_report(data, "x-reviewer", "a3", "FINDINGS: none") == ("none", 0), "negative: 'FINDINGS: none' is a valid empty report")
    ok(len(blocking(data)) == 2, "round 1: every open finding blocks")
    raises(lambda: close(data, "F1", "STATIC", "looked at it and it is fine now"), "positive: STATIC evidence without path:line is refused")
    raises(lambda: close(data, "F1", "CONTROL", "fixed"), "positive: evidence under 20 chars is refused")
    raises(lambda: close(data, "F1", "GUESS", "x" * 30), "positive: unknown evidence class is refused")
    fail(data, "F1", "test still red"); fail(data, "F1", "still red")
    ok(find(data, "F1")["state"] == "INVESTIGATION_REQUIRED", "2 failed closes escalate to INVESTIGATION_REQUIRED")
    raises(lambda: close(data, "F1", "STATIC", "src/a.py:12 now verifies the token"), "escalated finding refuses STATIC evidence")
    close(data, "F1", "CONTROL", "tests/test_auth.py::test_rejects_unsigned failed before, passes now")
    ok(find(data, "F1")["state"] == "CLOSED", "negative: CONTROL evidence closes an escalated finding")
    ok(rereview(data) == ["code-reviewer"], "rereview names only the owner of open or newly closed findings")
    for i in range(2, 4):  # rounds 2 and 3 for code-reviewer
        record_report(data, "code-reviewer", f"b{i}", "FINDING: MEDIUM | src/b.py:3 | naming\nFINDING: LOW | docs | typo")
    ok(review_round(data) == 3, "round = most reports by one reviewer")
    ok(all(f["severity"] in ("CRITICAL", "HIGH") or f["state"] == "INVESTIGATION_REQUIRED" for f in blocking(data)),
       "round 3+: MEDIUM/LOW stop blocking")
    ok(sum(1 for f in data["findings"] if f["summary"] == "typo") == 1, "an open finding re-reported by its reviewer is not duplicated")

    # stamps on a throwaway repo
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            git("init", "-q", cwd=root); (root / "a.txt").write_text("1\n")
            (root / ".gitignore").write_text(".claude/state/\nignored.log\n")
            os.environ.pop("REVIEW_STAMP_MAX_AGE_HOURS", None)
            ok(stamp_check(root, "verify")[0] == "MISSING", "stamp: MISSING before any write")
            stamp_write(root, "verify", "pytest 12 passed")
            ok(stamp_check(root, "verify")[0] == "VALID", "negative: unchanged tree -> VALID")
            (root / "ignored.log").write_text("noise")
            ok(stamp_check(root, "verify")[0] == "VALID", "negative: a gitignored file does not invalidate")
            (root / "b.txt").write_text("new untracked\n")
            ok(stamp_check(root, "verify")[0] == "CHANGED", "positive: an untracked file -> CHANGED")
            (root / "b.txt").unlink(); (root / "a.txt").write_text("2\n")
            ok(stamp_check(root, "verify")[0] == "CHANGED", "positive: an edited file -> CHANGED (content, not mtime)")
            (root / "a.txt").write_text("1\n")
            ok(stamp_check(root, "verify")[0] == "VALID", "negative: content restored -> VALID again")
            os.environ["REVIEW_STAMP_MAX_AGE_HOURS"] = "0"
            ok(stamp_check(root, "verify")[0] == "EXPIRED", "positive: older than the max age -> EXPIRED")
            os.environ.pop("REVIEW_STAMP_MAX_AGE_HOURS", None)
            ok(not (root / ".git" / "index").exists() or "a.txt" not in git("ls-files", cwd=root), "the real index is never touched")
            (root / "lib").mkdir(); (root / "lib" / "main.dart").write_text("void main() {}\n")
            stamp_write(root, "ui-mobile", "maestro 3 flows passed")
            (root / "a.txt").write_text("outside the UI scope\n")
            ok(stamp_check(root, "ui-mobile")[0] == "VALID", "negative: a scoped stamp ignores files outside its scope")
            (root / "lib" / "main.dart").write_text("void main() { run(); }\n")
            ok(stamp_check(root, "ui-mobile")[0] == "CHANGED", "positive: a scoped stamp sees edits inside its scope")
            stamp_write(root, "verify", "again")
            os.chmod(root / "a.txt", 0o755)
            ok(stamp_check(root, "verify")[0] == "CHANGED", "positive: a mode-only change (chmod +x) -> CHANGED")
            stamp_write(root, "verify", "again")
            (root / " sp ace").write_text("x")
            ok(stamp_check(root, "verify")[0] == "CHANGED", "positive: a file whose name starts with a space -> CHANGED")
            (root / 'q"uote\nnl').write_text("x")
            ok(stamp_check(root, "verify")[0] == "CHANGED", "positive: quote and newline in a file name are hashed, not an error")
            (state_dir(root) / "stamps" / "verify.json").write_text("{not json")
            ok(stamp_check(root, "verify")[0] == "UNKNOWN", "a corrupt stamp is UNKNOWN (never VALID)")
        except (RuntimeError, OSError) as exc:
            ok(False, f"stamp fixture: {exc}")
    print("selftest PASS" if fails == 0 else "selftest FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(cli(sys.argv[1:]))
