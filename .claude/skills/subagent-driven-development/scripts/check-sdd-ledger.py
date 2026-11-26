#!/usr/bin/env python3
"""SDD execution ledger, task briefs, plan-contract scan, review package.

Persists task progress outside the conversation so compaction or a new
session can resume without redispatching verified work. Inspired by the
Superpowers SDD ledger / review-package idea (obra/superpowers v7.0.2 MIT,
commit 22f0b463e7a5e579904dd6211a520321035526f7). This is an original
implementation for this toolkit — not a vendor copy, not AWS AI-DLC state,
and not a lifecycle engine.

State lives in <repo>/.claude/temp/sdd/<plan-stem>/ (already gitignored).
A ledger row is never verification proof.

Usage:
  check-sdd-ledger.py --init PLAN.md [--root DIR]
  check-sdd-ledger.py --status [--plan PLAN.md] [--root DIR]
  check-sdd-ledger.py --next [--plan PLAN.md] [--root DIR]
  check-sdd-ledger.py --mark ID --status STATUS [--verify-exit N]
      [--verify-cmd CMD] [--files a,b] [--findings TEXT] [--root DIR]
  check-sdd-ledger.py --reconcile [--plan PLAN.md] [--root DIR]
  check-sdd-ledger.py --scan-plan PLAN.md
  check-sdd-ledger.py --review-package [--base SHA] [--head SHA]
      [--uncommitted] [--task N] [--plan PLAN.md] [--root DIR]
  check-sdd-ledger.py --scan-skill
  check-sdd-ledger.py --selftest

Exit: 0 ok, 1 finding / cannot complete, 2 usage or broken selftest,
      3 empty or invalid review range.
Stdlib only. Never commits, pushes, merges, resets, or edits .gitignore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
VALID_STATUSES = ("pending", "in_progress", "blocked", "failed", "complete")
TASK_HEAD = re.compile(r"^### Task (\d+):\s*(.+)$", re.M)
FIELD_ROW = re.compile(
    r"^\|\s*\*?\*?([^*|]+?)\*?\*?\s*\|\s*(.*?)\s*\|",
    re.M,
)
REQUIRED_TASK_FIELDS = (
    "Affected files",
    "Verification command",
    "Acceptance Criteria",
    "Review focus",
    "Completion evidence",
    "Out of scope",
    "Interfaces consumed",
    "Interfaces produced",
)
SKILL_MARKERS = (
    "check-sdd-ledger.py",
    "execution ledger",
    "never treat a ledger",
    "review-package",
    "task brief",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def repo_root(start: Path) -> Path:
    r = git(["rev-parse", "--show-toplevel"], start, check=False)
    if r.returncode != 0:
        die("not a git repository", 2)
    return Path(r.stdout.strip())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_stem(plan: Path) -> str:
    stem = plan.stem
    if not stem or stem in {".", ".."} or "/" in stem or "\\" in stem:
        die(f"refusing plan stem {stem!r}", 2)
    return stem


def state_dir(root: Path, plan: Path) -> Path:
    return root / ".claude" / "temp" / "sdd" / plan_stem(plan)


def ledger_path(root: Path, plan: Path) -> Path:
    return state_dir(root, plan) / "ledger.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def split_tasks(plan_text: str) -> list[dict[str, str]]:
    matches = list(TASK_HEAD.finditer(plan_text))
    tasks: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(plan_text)
        body = plan_text[start:end].strip() + "\n"
        tasks.append({"id": m.group(1), "title": m.group(2).strip(), "body": body})
    return tasks


def field_map(body: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for m in FIELD_ROW.finditer(body):
        key = re.sub(r"\s+", " ", m.group(1)).strip()
        if not key or set(key) <= {"-", " "}:
            continue
        found[key] = m.group(2).strip()
    return found


def scan_plan(plan: Path) -> list[str]:
    if not plan.is_file():
        return [f"plan not found: {plan}"]
    text = plan.read_text(encoding="utf-8")
    findings: list[str] = []
    if "## Objective" not in text:
        findings.append("plan missing ## Objective")
    tasks = split_tasks(text)
    if not tasks:
        findings.append("plan has no ### Task N: headings")
        return findings
    for task in tasks:
        tid = task["id"]
        body = task["body"]
        fields = field_map(body)
        for req in REQUIRED_TASK_FIELDS:
            if req == "Acceptance Criteria":
                if "Acceptance Criteria" not in body and "#### Acceptance Criteria" not in body:
                    findings.append(f"task {tid}: missing Acceptance Criteria")
                continue
            hit = next((v for k, v in fields.items() if k.lower() == req.lower()), None)
            if hit is None or hit in {"", "[value]", "..."}:
                findings.append(f"task {tid}: missing {req}")
    return findings


def empty_task(parsed: dict[str, str], brief_rel: str) -> dict[str, Any]:
    fields = field_map(parsed["body"])
    verify_cmd = next(
        (v for k, v in fields.items() if k.lower() == "verification command"),
        "",
    )
    files_raw = next((v for k, v in fields.items() if k.lower() == "affected files"), "")
    files = [p.strip(" `") for p in files_raw.split(",") if p.strip(" `")]
    deps_raw = next((v for k, v in fields.items() if k.lower() == "preconditions"), "")
    depends = re.findall(r"Task\s+(\d+)", deps_raw, flags=re.I)
    return {
        "id": parsed["id"],
        "title": parsed["title"],
        "status": "pending",
        "depends_on": depends,
        "brief_path": brief_rel,
        "files_claimed": files,
        "review": {"spec": "pending", "quality": "pending", "findings": []},
        "verify": {
            "command": verify_cmd.strip("`"),
            "exit_code": None,
            "claimed_pass": False,
            "recorded_at": None,
        },
        "git": {"base": None, "head": None, "uncommitted": False},
        "stale": False,
        "inconsistent": False,
        "stale_reason": None,
    }


def init_ledger(root: Path, plan: Path) -> dict[str, Any]:
    text = plan.read_text(encoding="utf-8")
    parsed = split_tasks(text)
    if not parsed:
        die("plan has no ### Task N: headings", 1)
    sdir = state_dir(root, plan)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "briefs").mkdir(exist_ok=True)
    existing: dict[str, Any] | None = None
    lpath = ledger_path(root, plan)
    if lpath.is_file():
        existing = load_json(lpath)
    by_id = {t["id"]: t for t in (existing or {}).get("tasks", [])}
    tasks = []
    for item in parsed:
        rel = f".claude/temp/sdd/{plan_stem(plan)}/briefs/task-{item['id']}.md"
        (sdir / "briefs" / f"task-{item['id']}.md").write_text(item["body"], encoding="utf-8")
        if item["id"] in by_id:
            keep = by_id[item["id"]]
            keep["title"] = item["title"]
            keep["brief_path"] = rel
            tasks.append(keep)
        else:
            tasks.append(empty_task(item, rel))
    try:
        rel_plan = str(plan.resolve().relative_to(root.resolve()))
    except ValueError:
        rel_plan = str(plan)
    data = {
        "version": 1,
        "plan_path": rel_plan,
        "plan_sha256": sha256_text(text),
        "created_at": (existing or {}).get("created_at") or utc_now(),
        "updated_at": utc_now(),
        "tasks": tasks,
        "note": "A complete ledger row is not verification proof. Re-run the stack command.",
    }
    dump_json(lpath, data)
    return data


def resolve_plan(root: Path, plan: Path | None) -> Path:
    if plan is not None:
        p = plan if plan.is_absolute() else root / plan
        if not p.is_file():
            die(f"plan not found: {p}", 2)
        return p
    base = root / ".claude" / "temp" / "sdd"
    if not base.is_dir():
        die("no SDD ledger; pass --plan", 2)
    ledgers = sorted(base.glob("*/ledger.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not ledgers:
        die("no SDD ledger; pass --plan", 2)
    data = load_json(ledgers[0])
    p = root / data["plan_path"]
    if not p.is_file():
        die(f"ledger plan missing: {p}", 2)
    return p


def porcelain_files(root: Path) -> set[str]:
    r = git(["status", "--porcelain", "-uall"], root, check=False)
    if r.returncode != 0:
        return set()
    out: set[str] = set()
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.add(path.strip())
    return out


def diff_names(root: Path, base: str | None, head: str | None) -> set[str]:
    if not base or not head or base == head:
        return set()
    r = git(["diff", "--name-only", f"{base}..{head}"], root, check=False)
    if r.returncode != 0:
        return set()
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}


def reconcile_task(task: dict[str, Any], dirty: set[str], ranged: set[str]) -> dict[str, Any]:
    task = dict(task)
    task["stale"] = False
    task["inconsistent"] = False
    task["stale_reason"] = None
    status = task.get("status")
    verify = task.get("verify") or {}
    claimed = [f for f in (task.get("files_claimed") or []) if f]
    if status == "complete":
        if verify.get("exit_code") != 0 or not verify.get("claimed_pass"):
            task["stale"] = True
            task["stale_reason"] = "complete without passing verify evidence"
        elif claimed:
            present = set(claimed) & (dirty | ranged)
            missing_on_disk = [f for f in claimed if not Path(f).exists()]
            if not present and missing_on_disk:
                task["inconsistent"] = True
                task["stale_reason"] = "claimed files absent from git and working tree"
    if status == "in_progress" and not claimed and not dirty:
        task["stale"] = True
        task["stale_reason"] = "in_progress with no files and a clean tree"
    return task


def reconcile(data: dict[str, Any], root: Path) -> dict[str, Any]:
    dirty = porcelain_files(root)
    tasks = []
    for t in data.get("tasks", []):
        base = (t.get("git") or {}).get("base")
        head = (t.get("git") or {}).get("head")
        ranged = diff_names(root, base, head)
        tasks.append(reconcile_task(t, dirty, ranged))
    data = dict(data)
    data["tasks"] = tasks
    data["updated_at"] = utc_now()
    return data


def print_status(data: dict[str, Any]) -> None:
    print(f"plan: {data.get('plan_path')}")
    print(f"updated: {data.get('updated_at')}")
    for t in data.get("tasks", []):
        flags = []
        if t.get("stale"):
            flags.append("STALE")
        if t.get("inconsistent"):
            flags.append("INCONSISTENT")
        extra = f" [{' '.join(flags)}]" if flags else ""
        reason = f" — {t['stale_reason']}" if t.get("stale_reason") else ""
        v = t.get("verify") or {}
        evid = f" verify_exit={v.get('exit_code')}" if v.get("exit_code") is not None else " verify=none"
        print(f"  task {t['id']}: {t['status']}{extra}{evid}{reason}  {t.get('title')}")


def next_task(data: dict[str, Any]) -> dict[str, Any] | None:
    done = {
        t["id"]
        for t in data.get("tasks", [])
        if t.get("status") == "complete"
        and (t.get("verify") or {}).get("exit_code") == 0
        and (t.get("verify") or {}).get("claimed_pass")
        and not t.get("stale")
        and not t.get("inconsistent")
    }
    for t in data.get("tasks", []):
        if t["id"] in done:
            continue
        if t.get("status") == "complete" and not t.get("stale") and not t.get("inconsistent"):
            continue
        deps = t.get("depends_on") or []
        if any(d not in done for d in deps):
            continue
        return t
    return None


def mark(
    data: dict[str, Any],
    task_id: str,
    status: str,
    verify_exit: int | None,
    verify_cmd: str | None,
    files: list[str] | None,
    findings: str | None,
    root: Path,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        die(f"status must be one of {VALID_STATUSES}", 2)
    found = None
    for t in data["tasks"]:
        if t["id"] == task_id:
            found = t
            break
    if found is None:
        die(f"unknown task {task_id}", 1)
    if status == "complete":
        if verify_exit is None:
            die("refusing complete without --verify-exit (ledger is not proof)", 1)
        if verify_exit != 0:
            die("refusing complete: --verify-exit is not 0", 1)
        found["verify"]["exit_code"] = verify_exit
        found["verify"]["claimed_pass"] = True
        found["verify"]["recorded_at"] = utc_now()
        head = git(["rev-parse", "HEAD"], root, check=False)
        if head.returncode == 0:
            found["git"]["head"] = head.stdout.strip()
            if not found["git"].get("base"):
                found["git"]["base"] = head.stdout.strip()
        found["git"]["uncommitted"] = bool(porcelain_files(root))
    found["status"] = status
    if verify_cmd:
        found["verify"]["command"] = verify_cmd
    if verify_exit is not None and status != "complete":
        found["verify"]["exit_code"] = verify_exit
        found["verify"]["claimed_pass"] = verify_exit == 0
        found["verify"]["recorded_at"] = utc_now()
    if files:
        found["files_claimed"] = files
    if findings:
        found["review"]["findings"].append(findings)
    data["updated_at"] = utc_now()
    return data


def review_package(
    root: Path,
    base: str | None,
    head: str | None,
    uncommitted: bool,
    task: dict[str, Any] | None,
    plan: Path | None,
) -> dict[str, Any]:
    head_r = git(["rev-parse", "HEAD"], root, check=False)
    if head_r.returncode != 0:
        die("not a git repository", 2)
    head_sha = head or head_r.stdout.strip()
    if not base:
        mb = git(["merge-base", "origin/main", "HEAD"], root, check=False)
        if mb.returncode != 0:
            mb = git(["merge-base", "origin/master", "HEAD"], root, check=False)
        base_sha = mb.stdout.strip() if mb.returncode == 0 else head_sha
    else:
        base_sha = git(["rev-parse", base], root, check=False).stdout.strip() or base
    if base_sha != head_sha:
        anc = git(["merge-base", "--is-ancestor", base_sha, head_sha], root, check=False)
        if anc.returncode != 0:
            die("HEAD is not a descendant of BASE", 3)
        count = git(["rev-list", "--count", f"{base_sha}..{head_sha}"], root, check=False)
        ranged_n = int((count.stdout or "0").strip() or "0")
    else:
        ranged_n = 0
    dirty = porcelain_files(root)
    ranged = diff_names(root, base_sha, head_sha)
    files = sorted(ranged | (dirty if uncommitted or dirty else set()))
    if not files and ranged_n == 0 and not dirty:
        die("empty review range (no commits and no uncommitted files); will not invent a SHA", 3)
    focus = ""
    contract = ""
    if task:
        fields = field_map(Path(root / task["brief_path"]).read_text(encoding="utf-8")) if (root / task["brief_path"]).is_file() else {}
        focus = next((v for k, v in fields.items() if k.lower() == "review focus"), "")
        contract = task.get("brief_path") or ""
    pkg = {
        "base": base_sha,
        "head": head_sha,
        "uncommitted": bool(dirty),
        "files": files,
        "commit_count": ranged_n,
        "review_focus": focus,
        "task_id": None if task is None else task["id"],
        "task_contract": contract,
        "plan": None if plan is None else str(plan),
        "verify": None if task is None else task.get("verify"),
        "note": "Do not treat implementer self-assessment as proof. Do not commit merely to obtain a SHA.",
    }
    print(json.dumps(pkg, indent=2, sort_keys=True))
    return pkg


def scan_skill() -> list[str]:
    findings: list[str] = []
    skill = SKILL_DIR / "SKILL.md"
    if not skill.is_file():
        return ["missing SKILL.md"]
    text = skill.read_text(encoding="utf-8")
    for marker in SKILL_MARKERS:
        if marker.lower() not in text.lower():
            findings.append(f"SKILL.md missing marker: {marker}")
    ref = SKILL_DIR / "reference" / "execution-ledger.md"
    if not ref.is_file():
        findings.append("missing reference/execution-ledger.md")
    else:
        body = ref.read_text(encoding="utf-8")
        for needle in ("never verification proof", ".claude/temp/sdd", "NEXUS", "AI-DLC"):
            if needle.lower() not in body.lower():
                findings.append(f"execution-ledger.md missing {needle}")
    return findings


def selftest() -> int:
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal fail
        if cond:
            print(f"  PASS {name}")
        else:
            fail += 1
            print(f"  FAIL {name} {detail}")

    good = """# Plan: Demo

## Objective
Ship foo without touching UI.

### Task 1: Add foo

#### Context Brief

| Field | Value |
|-------|-------|
| **Affected files** | `src/foo.py` |
| **Preconditions** | none |
| **Invariants** | bar stays |
| **Verification command** | `pytest tests/test_foo.py` |
| **Interfaces consumed** | none |
| **Interfaces produced** | `foo()` |
| **Review focus** | error handling on foo |
| **Completion evidence** | pytest exit 0 on tests/test_foo.py |
| **Out of scope** | UI |

#### Acceptance Criteria

- [ ] foo returns 1

### Task 2: Add bar

#### Context Brief

| Field | Value |
|-------|-------|
| **Affected files** | `src/bar.py` |
| **Preconditions** | Task 1 complete |
| **Invariants** | foo stays |
| **Verification command** | `pytest tests/test_bar.py` |
| **Interfaces consumed** | `foo()` |
| **Interfaces produced** | `bar()` |
| **Review focus** | no silent catch |
| **Completion evidence** | pytest exit 0 on tests/test_bar.py |
| **Out of scope** | networking |

#### Acceptance Criteria

- [ ] bar calls foo
"""
    bad = """# Plan: Bad

### Task 1: Vague
Do stuff.
"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        git(["init"], tmp)
        git(["config", "user.email", "sdd@example.test"], tmp)
        git(["config", "user.name", "sdd"], tmp)
        (tmp / "README").write_text("root\n", encoding="utf-8")
        git(["add", "README"], tmp)
        git(["commit", "-m", "init"], tmp)
        (tmp / "orphan.txt").write_text("uncommitted\n", encoding="utf-8")
        orphan_rc = 0
        try:
            review_package(tmp, None, None, True, None, None)
        except SystemExit as e:
            orphan_rc = int(e.code)
        check("review-package works without a ledger", orphan_rc == 0)
        (tmp / "orphan.txt").unlink()
        plans = tmp / "docs" / "plans"
        plans.mkdir(parents=True)
        plan = plans / "2026-11-26-demo.md"
        plan.write_text(good, encoding="utf-8")
        bad_plan = plans / "bad.md"
        bad_plan.write_text(bad, encoding="utf-8")

        miss = scan_plan(bad_plan)
        check("scan-plan flags missing contracts", any("Review focus" in x for x in miss), str(miss))
        check("scan-plan good plan clean", scan_plan(plan) == [], str(scan_plan(plan)))

        data = init_ledger(tmp, plan)
        check("init writes ledger", ledger_path(tmp, plan).is_file())
        check("init writes briefs", (state_dir(tmp, plan) / "briefs" / "task-1.md").is_file())
        check("init two tasks", len(data["tasks"]) == 2)

        nxt = next_task(data)
        check("next is task 1", nxt is not None and nxt["id"] == "1", str(nxt))

        rc = 0
        try:
            mark(data, "1", "complete", None, None, None, None, tmp)
        except SystemExit as e:
            rc = int(e.code)
        check("complete without verify refused", rc == 1)

        data = mark(data, "1", "complete", 0, "pytest tests/test_foo.py", ["src/foo.py"], None, tmp)
        dump_json(ledger_path(tmp, plan), data)
        data = reconcile(data, tmp)
        t1 = data["tasks"][0]
        check(
            "complete without files on disk is inconsistent",
            t1.get("inconsistent") is True,
            str(t1.get("stale_reason")),
        )

        src = tmp / "src"
        src.mkdir()
        (src / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
        git(["add", "src/foo.py"], tmp)
        git(["commit", "-m", "foo"], tmp)
        head = git(["rev-parse", "HEAD"], tmp).stdout.strip()
        data["tasks"][0]["git"]["base"] = git(["rev-parse", "HEAD~1"], tmp).stdout.strip()
        data["tasks"][0]["git"]["head"] = head
        data = reconcile(data, tmp)
        t1 = data["tasks"][0]
        check("reconcile clears inconsistency after commit", not t1.get("inconsistent"))
        check(
            "verified complete is skipped",
            next_task(data) is not None and next_task(data)["id"] == "2",
            str(next_task(data)),
        )

        data["tasks"][0]["verify"]["exit_code"] = None
        data["tasks"][0]["verify"]["claimed_pass"] = False
        data = reconcile(data, tmp)
        check("complete without evidence is stale", data["tasks"][0]["stale"] is True)
        data["tasks"][0]["verify"]["exit_code"] = 0
        data["tasks"][0]["verify"]["claimed_pass"] = True
        data["tasks"][0]["stale"] = False
        dump_json(ledger_path(tmp, plan), data)

        (tmp / "src" / "bar.py").write_text("x = 1\n", encoding="utf-8")
        pkg_rc = 0
        try:
            review_package(tmp, None, None, True, data["tasks"][1], plan)
        except SystemExit as e:
            pkg_rc = int(e.code)
        check("review-package includes uncommitted without a new SHA", pkg_rc == 0)

        git(["add", "src/bar.py"], tmp)
        git(["commit", "-m", "bar"], tmp)
        # Fully commit remaining untracked state so BASE==HEAD is a clean empty range.
        git(["add", "-A"], tmp, check=False)
        git(["commit", "-m", "state", "--allow-empty"], tmp, check=False)
        empty_rc = 0
        try:
            h = git(["rev-parse", "HEAD"], tmp).stdout.strip()
            review_package(tmp, h, h, False, None, plan)
        except SystemExit as e:
            empty_rc = int(e.code)
        check("empty committed range without dirty files exits 3", empty_rc == 3)

        init_ledger(tmp, plan)
        again = load_json(ledger_path(tmp, plan))
        check("re-init preserves task 1 complete", again["tasks"][0]["status"] == "complete")

    skill_findings = scan_skill()
    check("scan-skill clean", skill_findings == [], str(skill_findings))
    print("PASS" if fail == 0 else f"FAIL {fail}")
    return 0 if fail == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--plan", type=Path, default=None)
    p.add_argument("--init", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--next", action="store_true", dest="next_task")
    p.add_argument("--mark", default=None, metavar="TASK_ID")
    p.add_argument("--status-value", dest="mark_status", default=None)
    p.add_argument("--verify-exit", type=int, default=None)
    p.add_argument("--verify-cmd", default=None)
    p.add_argument("--files", default=None)
    p.add_argument("--findings", default=None)
    p.add_argument("--reconcile", action="store_true")
    p.add_argument("--scan-plan", type=Path, default=None)
    p.add_argument("--review-package", action="store_true")
    p.add_argument("--base", default=None)
    p.add_argument("--head", default=None)
    p.add_argument("--uncommitted", action="store_true")
    p.add_argument("--task", default=None)
    p.add_argument("--scan-skill", action="store_true")
    p.add_argument("--selftest", action="store_true")
    # --status is used both as a verb and as mark's status; accept --state for mark.
    p.add_argument("--state", dest="mark_status_alt", default=None, help="alias of --status-value for --mark")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Allow `--mark 1 --status complete` by rewriting before parse.
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--mark" in raw and "--status" in raw:
        i = raw.index("--status")
        if i + 1 < len(raw) and not raw[i + 1].startswith("--"):
            raw[i] = "--status-value"
    args = parser.parse_args(raw)

    if args.selftest:
        return selftest()
    if args.scan_skill:
        findings = scan_skill()
        for f in findings:
            print(f)
        return 0 if not findings else 1
    if args.scan_plan is not None:
        findings = scan_plan(args.scan_plan)
        for f in findings:
            print(f)
        return 0 if not findings else 1

    root = (args.root or Path(".")).resolve()
    if args.root is None:
        root = repo_root(Path.cwd())

    if args.init:
        if args.plan is None:
            die("--init requires --plan", 2)
        plan = args.plan if args.plan.is_absolute() else root / args.plan
        findings = scan_plan(plan)
        if findings:
            print("PLAN CONTRACT GAPS (advisory on --init; --scan-plan is the authoring gate):")
            for f in findings:
                print(f"  {f}")
        data = init_ledger(root, plan)
        print(f"ledger: {ledger_path(root, plan)}")
        print_status(data)
        return 0

    if args.review_package and args.plan is None and args.task is None:
        # /review-code path: no SDD ledger required; uncommitted diffs are first-class.
        review_package(root, args.base, args.head, args.uncommitted, None, None)
        return 0

    if not any([args.status, args.next_task, args.mark, args.reconcile, args.review_package]):
        die("specify an action or --selftest", 2)

    plan = resolve_plan(root, args.plan)
    lpath = ledger_path(root, plan)
    if not lpath.is_file():
        die(f"no ledger at {lpath}; run --init", 1)
    data = load_json(lpath)

    if args.reconcile or args.status or args.next_task or args.review_package:
        data = reconcile(data, root)
        dump_json(lpath, data)

    if args.mark:
        status = args.mark_status or args.mark_status_alt
        if not status:
            die("--mark requires --status <pending|in_progress|blocked|failed|complete>", 2)
        files = [x.strip() for x in args.files.split(",")] if args.files else None
        data = mark(data, args.mark, status, args.verify_exit, args.verify_cmd, files, args.findings, root)
        data = reconcile(data, root)
        dump_json(lpath, data)
        print_status(data)
        return 0

    if args.review_package:
        task = None
        if args.task:
            task = next((t for t in data["tasks"] if t["id"] == str(args.task)), None)
            if task is None:
                die(f"unknown task {args.task}", 1)
        review_package(root, args.base, args.head, args.uncommitted, task, plan)
        return 0

    if args.next_task:
        nxt = next_task(data)
        if nxt is None:
            print("NO TASKS LEFT")
            return 0
        print(json.dumps({"id": nxt["id"], "title": nxt["title"], "status": nxt["status"], "brief_path": nxt.get("brief_path")}, indent=2))
        return 0

    print_status(data)
    if any(t.get("stale") or t.get("inconsistent") for t in data["tasks"]):
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        die(e.stderr or str(e), 2)
    except shutil.Error as e:
        die(str(e), 2)
