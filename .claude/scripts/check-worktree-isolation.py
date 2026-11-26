#!/usr/bin/env python3
"""Detect Git worktree isolation, collisions, and dirty-tree ownership.

Enhances /worktree-sync and /next. Worktrees are optional. This script never
creates, deletes, commits, merges, resets, discards, or edits .gitignore.

Inspired by Superpowers using-git-worktrees (obra/superpowers v7.0.2 MIT,
commit 22f0b463e7a5e579904dd6211a520321035526f7). Original implementation.

Usage:
  check-worktree-isolation.py --detect [--root DIR]
  check-worktree-isolation.py --propose-branch NAME [--propose-path PATH] [--files a,b] [--root DIR]
  check-worktree-isolation.py --scan-docs
  check-worktree-isolation.py --selftest

Exit: 0 ok, 1 collision / overlap, 2 usage or broken selftest.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

KIT = Path(__file__).resolve().parent.parent
DOC_MARKERS = {
    KIT / "commands" / "worktree-sync.md": (
        "already inside a worktree",
        "do not stash",
        "not mandatory",
        ".gitignore",
    ),
    KIT / "skills" / "next-issue" / "references" / "plan-and-handoff.md": (
        "optional worktree",
        "not mandatory",
    ),
}


def die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def repo_root(start: Path) -> Path:
    r = git(["rev-parse", "--show-toplevel"], start, check=False)
    if r.returncode != 0:
        die("not a git repository", 2)
    return Path(r.stdout.strip())


def parse_worktrees(cwd: Path) -> list[dict[str, str]]:
    r = git(["worktree", "list", "--porcelain"], cwd, check=False)
    if r.returncode != 0:
        die(r.stderr.strip() or "git worktree list failed", 2)
    items: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if line == "":
            if cur:
                items.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            cur["path"] = line.split(" ", 1)[1]
        elif line.startswith("HEAD "):
            cur["head"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1].removeprefix("refs/heads/")
        elif line == "bare":
            cur["bare"] = "1"
        elif line == "detached":
            cur["detached"] = "1"
        elif line.startswith("locked"):
            cur["locked"] = "1"
    if cur:
        items.append(cur)
    return items


def porcelain_files(cwd: Path) -> set[str]:
    r = git(["status", "--porcelain", "-uall"], cwd, check=False)
    out: set[str] = set()
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.add(path.strip())
    return out


def detect(root: Path) -> dict[str, Any]:
    git_dir = Path(git(["rev-parse", "--git-dir"], root).stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    common = Path(git(["rev-parse", "--git-common-dir"], root).stdout.strip())
    if not common.is_absolute():
        common = (root / common).resolve()
    else:
        common = common.resolve()
    branch_r = git(["rev-parse", "--abbrev-ref", "HEAD"], root, check=False)
    branch = (branch_r.stdout or "").strip()
    in_linked = git_dir != common
    worktrees = parse_worktrees(root)
    dirty = sorted(porcelain_files(root))
    return {
        "root": str(root),
        "git_dir": str(git_dir),
        "git_common_dir": str(common),
        "in_linked_worktree": in_linked,
        "branch": branch,
        "dirty_files": dirty,
        "worktrees": worktrees,
        "note": "Worktrees are optional. Do not stash, reset, or discard to enter one.",
    }


def propose(
    root: Path,
    branch: str,
    path: str | None,
    files: list[str],
) -> tuple[dict[str, Any], int]:
    info = detect(root)
    collisions: list[str] = []
    if info["in_linked_worktree"]:
        collisions.append("already inside a linked worktree; do not nest another")
    for wt in info["worktrees"]:
        if wt.get("branch") == branch:
            collisions.append(f"branch {branch} already checked out at {wt.get('path')}")
        if path and Path(wt.get("path", "")).resolve() == Path(path).resolve():
            collisions.append(f"worktree path already in use: {path}")
    if path and Path(path).exists() and not (Path(path) / ".git").exists():
        collisions.append(f"propose path exists and is not a worktree: {path}")
    # Overlap: another worktree has dirty files that intersect the proposed set.
    overlaps: list[str] = []
    if files:
        here = Path(info["root"]).resolve()
        for wt in info["worktrees"]:
            other = Path(wt.get("path", "")).resolve()
            if other == here:
                continue
            other_dirty = porcelain_files(other) if other.is_dir() else set()
            hit = sorted(set(files) & other_dirty)
            if hit:
                overlaps.append(f"{other}: {', '.join(hit)}")
    info["proposed_branch"] = branch
    info["proposed_path"] = path
    info["collisions"] = collisions
    info["overlapping_files"] = overlaps
    info["preserve_dirty"] = info["dirty_files"]
    code = 1 if collisions or overlaps else 0
    return info, code


def scan_docs() -> list[str]:
    findings: list[str] = []
    for path, markers in DOC_MARKERS.items():
        if not path.is_file():
            findings.append(f"missing {path}")
            continue
        body = path.read_text(encoding="utf-8").lower()
        for marker in markers:
            if marker.lower() not in body:
                findings.append(f"{path.name} missing {marker!r}")
        lower = body
        for banned in ("git stash", "git reset --hard", "git merge", "commit .gitignore"):
            if banned in lower and "never" not in lower[max(0, lower.find(banned) - 40) : lower.find(banned) + 20]:
                # Allow explicit "never git stash" / "do not stash".
                if "do not" in lower or "never" in lower or "not " in lower:
                    continue
                findings.append(f"{path.name} mutates git unsafely: {banned}")
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

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        git(["init"], tmp)
        git(["config", "user.email", "wt@example.test"], tmp)
        git(["config", "user.name", "wt"], tmp)
        (tmp / "README").write_text("a\n", encoding="utf-8")
        (tmp / "keep.txt").write_text("unrelated\n", encoding="utf-8")
        git(["add", "README", "keep.txt"], tmp)
        git(["commit", "-m", "init"], tmp)

        info = detect(tmp)
        check("primary checkout is not a linked worktree", info["in_linked_worktree"] is False)
        check("branch detected", bool(info["branch"]))

        (tmp / "keep.txt").write_text("unrelated dirty\n", encoding="utf-8")
        before = (tmp / "keep.txt").read_text(encoding="utf-8")
        info = detect(tmp)
        check("detect lists dirty file", "keep.txt" in info["dirty_files"], str(info["dirty_files"]))
        check("detect does not mutate dirty file", (tmp / "keep.txt").read_text(encoding="utf-8") == before)

        wt_path = tmp / "wt-feature"
        git(["worktree", "add", "-b", "feature/demo", str(wt_path)], tmp)
        linked = detect(wt_path)
        check("linked worktree detected", linked["in_linked_worktree"] is True, str(linked))
        check("linked branch is feature/demo", linked["branch"] == "feature/demo", linked["branch"])

        info, code = propose(tmp, "feature/demo", str(wt_path), [])
        check("same branch is a collision", code == 1 and any("already checked out" in c for c in info["collisions"]), str(info["collisions"]))

        info, code = propose(tmp, "feature/other", None, [])
        check("new branch from primary is free", code == 0, str(info["collisions"]))

        nested, ncode = propose(wt_path, "feature/nested", None, [])
        check("refuse nesting worktrees", ncode == 1 and any("already inside" in c for c in nested["collisions"]), str(nested["collisions"]))

        (wt_path / "keep.txt").write_text("other agent\n", encoding="utf-8")
        info, code = propose(tmp, "feature/overlap", None, ["keep.txt"])
        check(
            "overlapping dirty files flagged",
            code == 1 and info["overlapping_files"],
            str(info["overlapping_files"]),
        )
        check(
            "unrelated dirty file on primary still present",
            (tmp / "keep.txt").read_text(encoding="utf-8") == before,
        )

    docs = scan_docs()
    check("scan-docs clean", docs == [], str(docs))
    print("PASS" if fail == 0 else f"FAIL {fail}")
    return 0 if fail == 0 else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--detect", action="store_true")
    p.add_argument("--propose-branch", default=None)
    p.add_argument("--propose-path", default=None)
    p.add_argument("--files", default=None)
    p.add_argument("--scan-docs", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.scan_docs:
        findings = scan_docs()
        for f in findings:
            print(f)
        return 0 if not findings else 1

    root = repo_root(args.root or Path.cwd())
    if args.propose_branch:
        files = [x.strip() for x in args.files.split(",")] if args.files else []
        info, code = propose(root, args.propose_branch, args.propose_path, files)
        print(json.dumps(info, indent=2, sort_keys=True))
        return code
    info = detect(root)
    print(json.dumps(info, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
