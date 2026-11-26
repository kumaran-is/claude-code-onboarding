#!/usr/bin/env python3
"""Outer coordinator for opt-in `/next --auto` (not a second harness).

HITL `/next` never calls this. `--auto` is the only activation. Stdlib only.
Never talks to GitHub; callers pass fixtures or `gh` JSON. Destructive
workflow tests use isolated temp dirs — this script does not create or merge
real PRs.

Usage:
  check-next-auto.py --selftest
  check-next-auto.py --scan-skill
  check-next-auto.py --has-auto-flag -- ARGS...
  check-next-auto.py --graph ISSUES.json
  check-next-auto.py --order ISSUES.json
  check-next-auto.py --next-ready ISSUES.json --state STATE.json
  check-next-auto.py --merge-gate GATE.json
  check-next-auto.py --pr-idempotent PR.json
  check-next-auto.py --qualify-auto PAYLOAD.json
  check-next-auto.py --start --state-dir DIR --session SID --scope-file JSON
  check-next-auto.py --resume --state-dir DIR --session SID
  check-next-auto.py --advance --state-dir DIR --session SID --event EVENT.json
  check-next-auto.py --cancel --state-dir DIR --session SID
  check-next-auto.py --recover --state-dir DIR --session SID
  check-next-auto.py --hook-stop   # stdin: Stop payload JSON
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
PHASES = (
    "qualify",
    "plan",
    "implement",
    "verify",
    "fix",
    "review",
    "remediate",
    "frozen",
    "ship",
    "pr",
    "ci",
    "merge",
    "confirm",
)
TERMINAL = {"complete", "blocked", "cancelled"}
DEFAULT_MAX_STORIES = 20
DEFAULT_MAX_STORY_ATTEMPTS = 3
DEFAULT_MAX_DURATION_S = 8 * 3600
DEFAULT_MAX_REVIEW_ROUNDS = 3
DEFAULT_MAX_HOOK_ITERATIONS = 100
LOCK_STALE_S = 30 * 60
ADMIN_MERGE_FLAGS = ("--admin", "--disable-auto", "--bypass")


def _load_next_issue():
    path = Path(__file__).with_name("check-next-issue.py")
    spec = importlib.util.spec_from_file_location("check_next_issue", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check-next-issue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_auto_flag(argv: list[str]) -> bool:
    """True only for the exact token `--auto`. Never `--autoresearch` or `auto`."""
    return "--auto" in argv


def parse_issue_ref(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip().lstrip("#")
    if not text.isdigit():
        return None
    return int(text)


def issue_number(item: dict[str, Any]) -> int | None:
    return parse_issue_ref(item.get("number") if item.get("number") is not None else item.get("id"))


def dep_list(item: dict[str, Any]) -> tuple[list[int], bool]:
    """Return (deps, unknown). Unknown is fail-closed."""
    if item.get("deps_unknown") is True:
        return [], True
    raw = item.get("blocked_by")
    if raw is None:
        raw = item.get("blocked_by_open")
    if raw == "unknown":
        return [], True
    if raw is None:
        return [], False
    if isinstance(raw, str):
        if raw.strip().lower() == "unknown":
            return [], True
        raw = [raw]
    deps: list[int] = []
    unknown = False
    for entry in raw:
        if entry in (None, "", "unknown"):
            unknown = True
            continue
        parsed = parse_issue_ref(entry)
        if parsed is None:
            unknown = True
        else:
            deps.append(parsed)
    return deps, unknown


def build_graph(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    nodes: dict[int, dict[str, Any]] = {}
    for item in items:
        number = issue_number(item)
        if number is None:
            continue
        deps, unknown = dep_list(item)
        nodes[number] = {
            "number": number,
            "id": str(item.get("id") or number),
            "title": str(item.get("title") or ""),
            "status": str(item.get("status") or "todo").lower().replace(" ", "_"),
            "labels": [str(x) for x in item.get("labels") or []],
            "wave": item.get("wave"),
            "milestone": item.get("milestone"),
            "deps": deps,
            "unknown_deps": unknown,
            "verification": str(item.get("verification") or "unknown").lower(),
            "assignees": [str(x) for x in item.get("assignees") or []],
            "item": item,
        }
    return nodes


def detect_cycles(nodes: dict[int, dict[str, Any]]) -> list[list[int]]:
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []
    found: list[list[int]] = []

    def dfs(node: int) -> None:
        if node in visited or node not in nodes:
            return
        visiting.add(node)
        stack.append(node)
        for dep in nodes[node]["deps"]:
            if dep not in nodes:
                continue
            if dep in visiting:
                if dep in stack:
                    found.append(stack[stack.index(dep) :] + [dep])
                continue
            dfs(dep)
        stack.pop()
        visiting.discard(node)
        visited.add(node)

    for number in sorted(nodes):
        dfs(number)
    return found


def freeze_scope(kind: str, selector: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    kind = (kind or "").lower()
    if kind not in {"wave", "milestone", "issues"}:
        raise ValueError("scope kind must be wave, milestone, or issues")
    numbers: list[int] = []
    if kind == "wave":
        wave = int(selector)
        numbers = [n for n, node in build_graph(items).items() if node.get("wave") == wave]
        selector_out: Any = wave
    elif kind == "milestone":
        milestone = str(selector)
        numbers = [n for n, node in build_graph(items).items() if str(node.get("milestone") or "") == milestone]
        selector_out = milestone
    else:
        selector_out = [int(x) for x in selector]
        numbers = list(selector_out)
    unique = sorted(set(numbers))
    if not unique:
        raise ValueError("approved scope is empty")
    fingerprint = sha256_text(json.dumps({"kind": kind, "selector": selector_out, "issues": unique}, sort_keys=True))
    return {
        "kind": kind,
        "selector": selector_out,
        "issue_numbers": unique,
        "fingerprint": fingerprint,
    }


def check_scope(frozen: dict[str, Any], live_items: list[dict[str, Any]]) -> dict[str, Any]:
    live_graph = build_graph(live_items)
    if frozen["kind"] == "wave":
        live = sorted(n for n, node in live_graph.items() if node.get("wave") == frozen["selector"])
    elif frozen["kind"] == "milestone":
        live = sorted(n for n, node in live_graph.items() if str(node.get("milestone") or "") == str(frozen["selector"]))
    else:
        live = sorted(live_graph)
    approved = set(frozen["issue_numbers"])
    extra = sorted(n for n in live if n not in approved and frozen["kind"] != "issues")
    # Explicit issue lists: extra live board items are ignored; new numbers in the
    # live set that were not approved still count as expansion when kind is wave/milestone.
    missing = sorted(n for n in approved if n not in live_graph)
    if extra:
        return {"verdict": "EXPANDED", "extra": extra, "missing": missing, "live": live}
    return {"verdict": "OK", "extra": [], "missing": missing, "live": live}


def ready_issues(
    nodes: dict[int, dict[str, Any]],
    scope: set[int],
    merged: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Eligible next stories and blocked-in-scope records."""
    blocked: list[dict[str, Any]] = []
    ready: list[dict[str, Any]] = []
    for number in sorted(scope):
        if number in merged:
            continue
        node = nodes.get(number)
        if node is None:
            blocked.append({"number": number, "reason": "missing from live graph"})
            continue
        if node["unknown_deps"]:
            blocked.append({"number": number, "reason": "unknown dependencies (fail-closed)"})
            continue
        if node["status"] in {"done", "in_review"}:
            continue
        if node["status"] == "blocked":
            blocked.append({"number": number, "reason": "issue status blocked"})
            continue
        unmet: list[int] = []
        unknown_out = False
        for dep in node["deps"]:
            if dep in merged:
                continue
            if dep not in scope and dep not in nodes:
                unknown_out = True
                continue
            if dep not in merged:
                unmet.append(dep)
        if unknown_out:
            blocked.append({"number": number, "reason": "dependency outside known graph (fail-closed)"})
            continue
        if unmet:
            blocked.append({"number": number, "reason": f"waiting on {unmet}"})
            continue
        ready.append(node)
    return ready, blocked


def pick_ready(ready: list[dict[str, Any]], invoker: str) -> dict[str, Any] | None:
    if not ready:
        return None
    next_issue = _load_next_issue()
    items = []
    for node in ready:
        item = dict(node["item"])
        item.setdefault("number", node["number"])
        item.setdefault("status", "todo" if node["status"] not in {"in_progress"} else node["status"])
        items.append(item)
    pick = next_issue.pick_next(items, invoker or "auto")
    if pick is None:
        ready_sorted = sorted(ready, key=lambda n: (n["number"], n["id"]))
        winner = ready_sorted[0]
        return {**winner, "pick_reason": "todo-lowest-number"}
    return pick


def topo_order(items: list[dict[str, Any]], invoker: str = "auto") -> dict[str, Any]:
    nodes = build_graph(items)
    cycles = detect_cycles(nodes)
    if cycles:
        return {"verdict": "CYCLE", "cycles": cycles, "order": []}
    merged: set[int] = set()
    scope = set(nodes)
    order: list[int] = []
    remaining = set(scope)
    while remaining:
        ready, blocked = ready_issues(nodes, remaining, merged)
        # Nodes whose only blocker is a cycle already returned. Unknown deps stay blocked.
        if not ready:
            unknown = [b for b in blocked if "unknown" in b["reason"] or "fail-closed" in b["reason"]]
            if unknown:
                return {"verdict": "UNKNOWN_DEPS", "blocked": blocked, "order": order}
            return {"verdict": "STUCK", "blocked": blocked, "order": order}
        pick = pick_ready(ready, invoker)
        if pick is None:
            return {"verdict": "STUCK", "blocked": blocked, "order": order}
        number = int(pick["number"])
        order.append(number)
        merged.add(number)
        remaining.discard(number)
    return {"verdict": "OK", "cycles": [], "order": order}


def qualify_auto(payload: dict[str, Any]) -> dict[str, Any]:
    next_issue = _load_next_issue()
    result = dict(next_issue.qualify(payload))
    extra: list[str] = []
    risk = str(payload.get("risk") or payload.get("risk_level") or "").lower()
    if risk in {"high", "critical"}:
        extra.append("high-risk work is NO-GO for /next --auto")
    if payload.get("needs_human_review") is True:
        extra.append("implementation notes require human review")
    if payload.get("plan_verdict") in {"Revise", "Block", "revise", "block"}:
        extra.append("plan verdict is not Approve")
    reasons = list(result.get("reasons") or []) + extra
    go = not reasons
    result["verdict"] = "GO" if go else "NO-GO"
    result["reasons"] = reasons
    result["human_required"] = not go
    result["auto"] = True
    return result


def merge_args_forbidden(args: list[str]) -> list[str]:
    reasons: list[str] = []
    joined = " ".join(args)
    for flag in ADMIN_MERGE_FLAGS:
        if flag in args or flag in joined:
            reasons.append(f"merge flag {flag} is forbidden")
    if "--force" in args or "-f" in args:
        reasons.append("force-merge is forbidden")
    if any("bypass" in a.lower() for a in args):
        reasons.append("branch-protection bypass is forbidden")
    return reasons


def merge_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a GitHub-like fixture. Never calls gh. WAIT vs BLOCKED vs ALLOW."""
    reasons: list[str] = []
    wait: list[str] = []
    if payload.get("admin_bypass") or payload.get("bypass_protection"):
        reasons.append("must not override protected-branch restrictions or use administrative bypass")
    reasons.extend(merge_args_forbidden([str(a) for a in payload.get("merge_args") or []]))
    if payload.get("disable_checks") or payload.get("skip_required_checks"):
        reasons.append("disabling required checks is forbidden")
    if payload.get("self_approve") or payload.get("self_approved"):
        if not payload.get("external_approval"):
            reasons.append("self-approval is not an independent approval")
    if payload.get("blocking_findings"):
        reasons.append("unresolved blocking findings")
    if payload.get("stale_verify") or payload.get("verify_stamp") in {"CHANGED", "EXPIRED", "MISSING", "INSUFFICIENT"}:
        reasons.append("stale or missing verification evidence")
    pr = payload.get("pr") or {}
    expected_base = payload.get("expected_base")
    if expected_base and pr.get("baseRefName") and pr.get("baseRefName") != expected_base:
        reasons.append(f"base branch {pr.get('baseRefName')} != {expected_base}")
    local_head = payload.get("local_head")
    if local_head and pr.get("headRefOid") and pr.get("headRefOid") != local_head:
        reasons.append("PR head is not the current implementation SHA")
    if pr.get("isDraft") is True:
        reasons.append("draft PR cannot merge")
    if pr.get("state") == "MERGED":
        return {
            "verdict": "ALREADY_MERGED",
            "reasons": [],
            "merge_sha": pr.get("mergeCommitOid") or pr.get("mergeCommit", {}).get("oid"),
        }
    mergeable = pr.get("mergeable")
    if mergeable in {"CONFLICTING", False, "false"}:
        reasons.append("merge conflicts")
    merge_state = str(pr.get("mergeStateStatus") or "")
    if merge_state in {"DIRTY", "BLOCKED"}:
        reasons.append(f"merge state {merge_state}")
    if merge_state == "BEHIND":
        reasons.append("PR is behind the required merge-base (do not force)")
    checks = list(payload.get("checks") or pr.get("statusCheckRollup") or [])
    pending = [c for c in checks if str(c.get("state") or c.get("conclusion") or "").upper() in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED"}]
    failed = [
        c
        for c in checks
        if str(c.get("state") or c.get("conclusion") or "").upper() in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
    ]
    required = [str(x) for x in payload.get("required_checks") or []]
    names = {str(c.get("name") or c.get("context") or "") for c in checks}
    missing_required = [name for name in required if name not in names]
    if missing_required:
        reasons.append(f"required checks missing: {missing_required}")
    if failed:
        reasons.append("required checks failed: " + ", ".join(str(c.get("name") or c) for c in failed[:5]))
    elif pending:
        wait.append("required checks pending")
    reviews_required = int(payload.get("reviews_required") or 0)
    review_decision = str(payload.get("review_decision") or pr.get("reviewDecision") or "")
    if reviews_required > 0:
        if payload.get("author_is_only_reviewer") or payload.get("external_approval") is False:
            reasons.append("required external approval unavailable — automation cannot supply it")
        elif review_decision != "APPROVED":
            reasons.append("required independent approvals missing")
    if payload.get("protected") is True and payload.get("ruleset_bypass") is True:
        reasons.append("must not override protected-branch restrictions")
    if reasons:
        return {"verdict": "BLOCKED", "reasons": reasons, "wait": wait, "merge_sha": None}
    if wait:
        return {"verdict": "WAIT", "reasons": wait, "wait": wait, "merge_sha": None}
    return {
        "verdict": "ALLOW",
        "reasons": [],
        "wait": [],
        "merge_sha": pr.get("headRefOid"),
        "merge_args": ["--squash", "--delete-branch"],
    }


def pr_idempotent(payload: dict[str, Any]) -> dict[str, Any]:
    recorded = payload.get("recorded_pr")
    if recorded:
        return {"action": "reuse", "pr_number": int(recorded), "reason": "state already has PR"}
    head = payload.get("head_branch")
    existing = list(payload.get("open_prs") or [])
    matches = [p for p in existing if p.get("headRefName") == head or p.get("head") == head]
    if matches:
        number = int(matches[0]["number"])
        return {"action": "reuse", "pr_number": number, "reason": "open PR already exists for head branch"}
    merged = list(payload.get("merged_prs") or [])
    merged_matches = [p for p in merged if p.get("headRefName") == head]
    if merged_matches:
        return {
            "action": "already_merged",
            "pr_number": int(merged_matches[0]["number"]),
            "merge_sha": merged_matches[0].get("mergeCommitOid"),
            "reason": "PR already merged — do not create another",
        }
    return {"action": "create", "pr_number": None, "reason": "no existing PR"}


def confirm_merge(payload: dict[str, Any]) -> dict[str, Any]:
    expected = payload.get("expected_sha")
    got = payload.get("merge_sha") or payload.get("target_sha")
    base = payload.get("target_branch")
    actual_base = payload.get("merged_into")
    reasons: list[str] = []
    if not got:
        reasons.append("merge SHA missing")
    elif expected and got != expected:
        reasons.append(f"merge SHA {got} != expected {expected}")
    if base and actual_base and actual_base != base:
        reasons.append(f"merged into {actual_base} != {base}")
    if payload.get("target_contains_sha") is False:
        reasons.append("target branch does not contain merge SHA")
    if payload.get("pr_state") not in {None, "MERGED", "merged"}:
        reasons.append(f"PR state is {payload.get('pr_state')}, not MERGED")
    if reasons:
        return {"verdict": "BLOCKED", "reasons": reasons}
    return {"verdict": "CONFIRMED", "merge_sha": got}


def default_state_dir(root: Path) -> Path:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            common = Path(out.stdout.strip())
            if not common.is_absolute():
                common = root / common
            return common.resolve() / "claude-state" / "next-auto"
    except (OSError, subprocess.TimeoutExpired):
        pass
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "claude-state" / digest / "next-auto"


def state_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "state.json", state_dir / "coordinator.lock"


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class CoordinatorLock:
    def __init__(self, state_dir: Path, session: str, recover: bool = False):
        self.state_dir = state_dir
        self.session = session
        self.recover = recover
        self._fh = None

    def acquire(self) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / "coordinator.lock"
        self._fh = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.seek(0)
            raw = self._fh.read().strip()
            holder = json.loads(raw) if raw else {}
            return {
                "verdict": "CONCURRENT",
                "holder": holder,
                "reason": "another coordinator holds the lock",
            }
        self._fh.seek(0)
        raw = self._fh.read().strip()
        holder = json.loads(raw) if raw else {}
        holder_session = str(holder.get("session_id") or "")
        holder_pid = int(holder.get("pid") or 0)
        if holder_session and holder_session != self.session:
            alive = pid_alive(holder_pid)
            same_process = holder_pid == os.getpid()
            if (alive or same_process) and not self.recover:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                self._fh.close()
                self._fh = None
                return {"verdict": "CONCURRENT", "holder": holder, "reason": "live coordinator for another session"}
            acquired_at = float(holder.get("acquired_at") or 0)
            if not alive and not self.recover and acquired_at and (time.time() - acquired_at) < LOCK_STALE_S:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                self._fh.close()
                self._fh = None
                return {
                    "verdict": "STALE_LOCK",
                    "holder": holder,
                    "reason": "dead pid; pass --recover to steal after confirming no other session",
                }
        meta = {"session_id": self.session, "pid": os.getpid(), "acquired_at": time.time()}
        self._fh.seek(0)
        self._fh.truncate()
        json.dump(meta, self._fh)
        self._fh.flush()
        return {"verdict": "OK", "holder": meta}

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            self._fh.truncate()
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
        except OSError:
            pass
        self._fh = None


def empty_state(session: str, scope: dict[str, Any], budget: dict[str, Any] | None = None) -> dict[str, Any]:
    now = time.time()
    return {
        "version": 1,
        "mode": "auto",
        "status": "running",
        "session_id": session,
        "scope": scope,
        "current": None,
        "completed": [],
        "blocked": [],
        "skipped": [],
        "hook_iteration": 0,
        "started_at": now,
        "updated_at": now,
        "budget": {
            "max_stories": budget_int(budget or {}, "max_stories", DEFAULT_MAX_STORIES),
            "max_story_attempts": budget_int(budget or {}, "max_story_attempts", DEFAULT_MAX_STORY_ATTEMPTS),
            "max_duration_seconds": budget_int(budget or {}, "max_duration_seconds", DEFAULT_MAX_DURATION_S),
            "max_review_rounds": budget_int(budget or {}, "max_review_rounds", DEFAULT_MAX_REVIEW_ROUNDS),
            "max_hook_iterations": budget_int(budget or {}, "max_hook_iterations", DEFAULT_MAX_HOOK_ITERATIONS),
            "max_cost_usd": (budget or {}).get("max_cost_usd"),
            "cost_metered": False,
        },
        "report": None,
    }


def budget_int(budget: dict[str, Any], key: str, default: int) -> int:
    if key in budget and budget[key] is not None:
        return int(budget[key])
    return default


def budget_block(state: dict[str, Any], now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    budget = state.get("budget") or {}
    started = float(state.get("started_at") or now)
    if now - started >= budget_int(budget, "max_duration_seconds", DEFAULT_MAX_DURATION_S):
        return "execution duration budget exceeded"
    if int(state.get("hook_iteration") or 0) >= budget_int(budget, "max_hook_iterations", DEFAULT_MAX_HOOK_ITERATIONS):
        return "Stop-hook iteration budget exceeded"
    completed = list(state.get("completed") or [])
    current = 1 if state.get("current") else 0
    if len(completed) + current > budget_int(budget, "max_stories", DEFAULT_MAX_STORIES):
        return "max stories exceeded"
    current_obj = state.get("current") or {}
    if int(current_obj.get("attempts") or 0) >= budget_int(budget, "max_story_attempts", DEFAULT_MAX_STORY_ATTEMPTS):
        return "story retry limit exceeded"
    if int(current_obj.get("review_rounds") or 0) >= budget_int(budget, "max_review_rounds", DEFAULT_MAX_REVIEW_ROUNDS):
        return "independent review round cap exceeded"
    return None


def load_state(state_dir: Path) -> dict[str, Any] | None:
    path, _ = state_paths(state_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state_dir: Path, state: dict[str, Any]) -> None:
    path, _ = state_paths(state_dir)
    state["updated_at"] = time.time()
    atomic_write(path, state)


def final_report(state: dict[str, Any]) -> dict[str, Any]:
    completed = list(state.get("completed") or [])
    blocked = list(state.get("blocked") or [])
    scope = list((state.get("scope") or {}).get("issue_numbers") or [])
    remaining = [n for n in scope if n not in {c.get("issue") for c in completed} and n not in {b.get("issue") for b in blocked}]
    status = state.get("status")
    return {
        "status": status,
        "completed": completed,
        "blocked": blocked,
        "remaining": remaining,
        "scope": state.get("scope"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "limitations": [
            "GitHub create/merge is executed by the model after this coordinator ALLOWs it; this script never calls gh.",
            "Cost USD is not metered (budget.max_cost_usd is advisory).",
            "A killed Claude Code session does not resume until a human re-invokes /next --auto or the Stop hook of a live session continues.",
        ],
    }


def start(state_dir: Path, session: str, scope: dict[str, Any], items: list[dict[str, Any]], budget: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = load_state(state_dir)
    if existing and existing.get("status") == "running" and existing.get("session_id") not in {None, session}:
        return {"verdict": "CONCURRENT", "state": existing, "reason": "running coordinator for another session"}
    if existing and existing.get("status") == "running" and existing.get("session_id") == session:
        return {"verdict": "RESUME", "state": existing, "action": resume_action(existing, items)}
    graph = build_graph(items)
    cycles = detect_cycles(graph)
    if cycles:
        return {"verdict": "BLOCKED", "reason": "dependency cycle", "cycles": cycles}
    ordered = topo_order(items)
    if ordered["verdict"] != "OK":
        # Still start: process whatever is independently ready; record graph error for the rest.
        pass
    state = empty_state(session, scope, budget)
    save_state(state_dir, state)
    action = choose_next_story(state, items, session)
    save_state(state_dir, state)
    return {"verdict": "STARTED", "state": state, "action": action, "order": ordered}


def choose_next_story(state: dict[str, Any], items: list[dict[str, Any]], invoker: str) -> dict[str, Any]:
    drift = check_scope(state["scope"], items)
    if drift["verdict"] == "EXPANDED":
        state["status"] = "blocked"
        state["blocked"].append({"issue": None, "reason": "scope expansion", "extra": drift["extra"]})
        state["report"] = final_report(state)
        return {"status": "blocked", "action": "stop", "reason": "approved scope expanded", "drift": drift}
    nodes = build_graph(items)
    merged = {int(c["issue"]) for c in state.get("completed") or [] if c.get("issue") is not None}
    # Confirmed closed issues in live graph also count as merged deps.
    for number, node in nodes.items():
        if node["status"] == "done" and number in set(state["scope"]["issue_numbers"]):
            merged.add(number)
            if number not in {c.get("issue") for c in state.get("completed") or []}:
                state.setdefault("completed", []).append(
                    {"issue": number, "pr": None, "merge_sha": None, "note": "already done on board"}
                )
    scope = set(state["scope"]["issue_numbers"])
    ready, blocked_info = ready_issues(nodes, scope, merged)
    in_scope_left = [n for n in scope if n not in merged]
    if not in_scope_left:
        state["status"] = "complete"
        state["current"] = None
        state["report"] = final_report(state)
        return {"status": "complete", "action": "report", "report": state["report"]}
    if not ready:
        fail_closed = [b for b in blocked_info if b["number"] in in_scope_left]
        state["status"] = "blocked"
        state["blocked"].extend({"issue": b["number"], "reason": b["reason"]} for b in fail_closed)
        state["report"] = final_report(state)
        return {"status": "blocked", "action": "stop", "reason": "no dependency-ready story", "blocked": fail_closed}
    pick = pick_ready(ready, invoker)
    number = int(pick["number"])
    state["current"] = {
        "issue": number,
        "phase": "qualify",
        "pr_number": None,
        "head_branch": None,
        "merge_sha": None,
        "attempts": 0,
        "review_rounds": 0,
        "title": pick.get("title") or nodes[number]["title"],
    }
    return {
        "status": "running",
        "action": "execute_phase",
        "phase": "qualify",
        "issue": number,
        "prompt": phase_prompt(state),
    }


def phase_prompt(state: dict[str, Any]) -> str:
    current = state.get("current") or {}
    issue = current.get("issue")
    phase = current.get("phase")
    return (
        f"/next --auto continuing issue #{issue} phase `{phase}`. "
        f"Read `.claude/skills/next-issue/references/auto-loop.md`. "
        f"Run `python3 .claude/skills/next-issue/scripts/check-next-auto.py --resume` "
        f"and execute only that phase. Do not skip gates. Do not start another issue. "
        f"Do not use --admin, force-merge, or self-approve. "
        f"When the phase is done, call --advance with the event JSON."
    )


def resume_action(state: dict[str, Any], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if state.get("status") in TERMINAL:
        return {"status": state["status"], "action": "report", "report": state.get("report") or final_report(state)}
    blocked = budget_block(state)
    if blocked:
        state["status"] = "blocked"
        state["blocked"].append({"issue": (state.get("current") or {}).get("issue"), "reason": blocked})
        state["report"] = final_report(state)
        return {"status": "blocked", "action": "stop", "reason": blocked, "report": state["report"]}
    if not state.get("current"):
        if items is None:
            return {"status": "running", "action": "reload_issues", "prompt": "Re-fetch in-scope GitHub issues, then --advance with event refresh_issues."}
        return choose_next_story(state, items, state.get("session_id") or "auto")
    return {
        "status": "running",
        "action": "execute_phase",
        "phase": state["current"]["phase"],
        "issue": state["current"]["issue"],
        "prompt": phase_prompt(state),
        "current": state["current"],
    }


def next_phase(phase: str) -> str | None:
    try:
        idx = PHASES.index(phase)
    except ValueError:
        return None
    if idx + 1 >= len(PHASES):
        return None
    return PHASES[idx + 1]


def advance(state: dict[str, Any], event: dict[str, Any], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    name = str(event.get("event") or event.get("name") or "")
    current = state.get("current")
    if name == "cancel":
        state["status"] = "cancelled"
        state["report"] = final_report(state)
        return {"verdict": "CANCELLED", "state": state, "action": {"action": "stop", "status": "cancelled"}}
    if name == "refresh_issues":
        if items is None:
            return {"verdict": "ERROR", "reason": "refresh_issues requires live items"}
        action = choose_next_story(state, items, state.get("session_id") or "auto")
        return {"verdict": action.get("status", "running").upper(), "state": state, "action": action}
    if state.get("status") in TERMINAL:
        return {"verdict": state["status"].upper(), "state": state, "action": resume_action(state)}
    budget = budget_block(state)
    if budget:
        state["status"] = "blocked"
        state["blocked"].append({"issue": (current or {}).get("issue"), "reason": budget})
        state["report"] = final_report(state)
        return {"verdict": "BLOCKED", "state": state, "action": {"action": "stop", "reason": budget}}

    if current is None:
        if items is None:
            return {"verdict": "NEED_ISSUES", "state": state, "action": resume_action(state)}
        action = choose_next_story(state, items, state.get("session_id") or "auto")
        return {"verdict": "OK", "state": state, "action": action}

    phase = current.get("phase")

    def block(reason: str) -> dict[str, Any]:
        state["status"] = "blocked"
        state["blocked"].append({"issue": current["issue"], "phase": phase, "reason": reason})
        state["report"] = final_report(state)
        return {"verdict": "BLOCKED", "state": state, "action": {"action": "stop", "reason": reason, "status": "blocked"}}

    if name in {"nogo", "qualify_nogo", "NO-GO"}:
        return block("high-risk or qualification NO-GO")
    if name in {"escalated", "fix_escalated", "WEAKENED"}:
        return block(f"inner loop {name}")
    if name in {"review_fail"}:
        current["review_rounds"] = int(current.get("review_rounds") or 0) + 1
        if current["review_rounds"] >= budget_int(state.get("budget") or {}, "max_review_rounds", DEFAULT_MAX_REVIEW_ROUNDS):
            return block("independent reviewer failures exceeded round cap")
        current["phase"] = "remediate"
        return {"verdict": "OK", "state": state, "action": resume_action(state)}
    if name in {"verify_fail"}:
        current["attempts"] = int(current.get("attempts") or 0) + 1
        if current["attempts"] >= budget_int(state.get("budget") or {}, "max_story_attempts", DEFAULT_MAX_STORY_ATTEMPTS):
            return block("story retry limit exceeded")
        current["phase"] = "fix"
        return {"verdict": "OK", "state": state, "action": resume_action(state)}
    if name in {"ci_pending"}:
        current["phase"] = "ci"
        return {"verdict": "WAIT", "state": state, "action": resume_action(state)}
    if name in {"ci_fail"}:
        return block("required CI failed")
    if name in {"merge_blocked"}:
        return block("merge BLOCKED: " + str(event.get("reason") or "policy"))
    if name in {"approval_missing"}:
        return block("required human approval that automation cannot supply")
    if name in {"stale_verify"}:
        return block("stale verification evidence")
    if name in {"pr_created"}:
        current["pr_number"] = event.get("pr_number")
        current["head_branch"] = event.get("head_branch") or current.get("head_branch")
        current["phase"] = "ci"
        return {"verdict": "OK", "state": state, "action": resume_action(state)}
    if name in {"pr_reused"}:
        current["pr_number"] = event.get("pr_number")
        if event.get("already_merged"):
            current["merge_sha"] = event.get("merge_sha")
            current["phase"] = "confirm"
        else:
            current["phase"] = "ci"
        return {"verdict": "OK", "state": state, "action": resume_action(state)}
    if name in {"merged"}:
        current["merge_sha"] = event.get("merge_sha")
        current["phase"] = "confirm"
        return {"verdict": "OK", "state": state, "action": resume_action(state)}
    if name in {"confirmed"}:
        state["completed"].append(
            {
                "issue": current["issue"],
                "pr": current.get("pr_number"),
                "merge_sha": event.get("merge_sha") or current.get("merge_sha"),
            }
        )
        state["current"] = None
        if items is None:
            return {
                "verdict": "OK",
                "state": state,
                "action": {"action": "reload_issues", "prompt": "Re-fetch issues after merge, then --advance refresh_issues."},
            }
        action = choose_next_story(state, items, state.get("session_id") or "auto")
        return {"verdict": "OK", "state": state, "action": action}

    if name in {"phase_ok", "ok", "pass"}:
        nxt = next_phase(str(phase))
        if nxt is None:
            return block("confirm required before leaving last phase")
        current["phase"] = nxt
        return {"verdict": "OK", "state": state, "action": resume_action(state)}

    return {"verdict": "ERROR", "reason": f"unknown event {name}", "state": state}


def hook_stop(payload: dict[str, Any], root: Path, state_dir: Path | None = None) -> dict[str, Any]:
    """Return {kind: noop|block|done, stdout: optional JSON string}."""
    if payload.get("agent_id"):
        return {"kind": "noop"}
    ralph = Path(os.environ.get("NEXT_AUTO_RALPH_LOOP") or (root / ".claude" / "ralph-loop.local.md"))
    if ralph.is_file():
        return {"kind": "noop", "reason": "inner Ralph loop owns Stop"}
    state_dir = state_dir or default_state_dir(root)
    lock = CoordinatorLock(state_dir, str(payload.get("session_id") or ""), recover=False)
    locked = lock.acquire()
    if locked["verdict"] != "OK":
        return {"kind": "noop", "reason": locked.get("reason") or "coordinator lock busy"}
    try:
        return _hook_stop_locked(payload, state_dir)
    finally:
        lock.release()


def _hook_stop_locked(payload: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    state = load_state(state_dir)
    if not state or state.get("status") != "running":
        return {"kind": "noop"}
    stored = str(state.get("session_id") or "")
    incoming = str(payload.get("session_id") or "")
    if stored and incoming and stored != incoming:
        return {"kind": "noop", "reason": "foreign session"}
    if stored and not incoming:
        return {"kind": "noop", "reason": "unidentified session cannot drive auto loop"}
    cap = os.environ.get("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP")
    if cap and str(cap).isdigit():
        bound = max(1, int(cap) - 1)
        if int(state.get("hook_iteration") or 0) >= bound:
            state["status"] = "blocked"
            state["blocked"].append({"issue": (state.get("current") or {}).get("issue"), "reason": "Stop-hook platform cap"})
            state["report"] = final_report(state)
            save_state(state_dir, state)
            return {
                "kind": "done",
                "stdout": json.dumps({"systemMessage": "🛑 /next --auto interrupted at Stop-hook cap. State persisted; re-invoke /next --auto to resume."}),
            }
    blocked = budget_block(state)
    if blocked:
        state["status"] = "blocked"
        state["blocked"].append({"issue": (state.get("current") or {}).get("issue"), "reason": blocked})
        state["report"] = final_report(state)
        save_state(state_dir, state)
        return {"kind": "done", "stdout": json.dumps({"systemMessage": f"🛑 /next --auto BLOCKED: {blocked}"})}
    state["hook_iteration"] = int(state.get("hook_iteration") or 0) + 1
    save_state(state_dir, state)
    action = resume_action(state)
    if action.get("status") in TERMINAL:
        return {"kind": "done", "stdout": json.dumps({"systemMessage": f"/next --auto {action.get('status')}. See coordinator report."})}
    prompt = action.get("prompt") or phase_prompt(state)
    msg = f"/next --auto hook iteration {state['hook_iteration']} · issue #{(state.get('current') or {}).get('issue')} · {(state.get('current') or {}).get('phase')}"
    return {
        "kind": "block",
        "stdout": json.dumps({"decision": "block", "reason": prompt, "systemMessage": msg}),
    }


def scan_auto_isolation(skill_dir: Path = SKILL_DIR) -> list[str]:
    findings: list[str] = []
    auto = skill_dir / "references" / "auto-loop.md"
    if not auto.is_file():
        findings.append("missing references/auto-loop.md")
        return findings
    body = auto.read_text(encoding="utf-8")
    for needle in (
        "--auto",
        "never be activated implicitly",
        "gh pr merge",
        "BLOCKED",
        "topological",
        "coordinator",
        "--admin",
        "self-approve",
        "Do not silently expand",
    ):
        if needle not in body:
            findings.append(f"auto-loop.md missing {needle}")
    skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if "Do not run `gh pr merge`" not in skill:
        findings.append("SKILL.md lost HITL merge gate")
    if "only the `--auto` flag" not in skill and "only when `--auto`" not in skill:
        findings.append("SKILL.md must say --auto is opt-in only")
    loop = (skill_dir / "references" / "loop-and-qualify.md").read_text(encoding="utf-8")
    if "Do not start the next issue" not in loop:
        findings.append("loop-and-qualify.md lost no-chaining rule")
    handoff = (skill_dir / "references" / "plan-and-handoff.md").read_text(encoding="utf-8")
    if "Auto-merge is forbidden" not in handoff:
        findings.append("plan-and-handoff.md lost HITL auto-merge forbid")
    cmd = skill_dir.parent.parent / "commands" / "next.md"
    if cmd.is_file():
        cmd_body = cmd.read_text(encoding="utf-8")
        if "Never chain the next issue" not in cmd_body:
            findings.append("next.md lost never-chain")
        if "`/create-pr` prints `gh pr create` and does not run it" not in cmd_body:
            findings.append("next.md lost HITL create-pr print-only")
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

    def check_true(name: str, pred: bool) -> None:
        check(name, bool(pred), True)

    # 1. Backward compatibility of /next flag parsing + HITL docs
    check("hitl-no-auto-flag", has_auto_flag(["--plan", "--wave", "3"]), False)
    check("auto-flag-exact", has_auto_flag(["--auto", "--wave", "3"]), True)
    check("auto-not-autoresearch", has_auto_flag(["--autoresearch"]), False)
    check("auto-not-substring", has_auto_flag(["--auto-merge"]), False)
    iso = scan_auto_isolation()
    if iso:
        print("  FAIL isolation scan:")
        for f in iso:
            print(f"    - {f}")
        fail += 1
    else:
        print("  ok   hitl isolation scan")
    next_issue = _load_next_issue()
    pick = next_issue.pick_next(
        [
            {"id": "30", "number": 30, "title": "UI", "status": "todo", "labels": ["layer:flutter"]},
            {"id": "10", "number": 10, "title": "API", "status": "todo", "labels": ["area:backend"]},
        ],
        "me",
    )
    check("hitl-pick-unchanged", pick["id"] if pick else None, "10")

    # 2. Dependency graph ordering and cycle detection
    items = [
        {"number": 1, "title": "schema", "status": "todo", "labels": ["layer:schema"], "blocked_by": []},
        {"number": 2, "title": "api", "status": "todo", "labels": ["area:backend"], "blocked_by": [1]},
        {"number": 3, "title": "ui", "status": "todo", "labels": ["layer:flutter"], "blocked_by": [2]},
    ]
    ordered = topo_order(items)
    check("positive-topo-order", ordered.get("order"), [1, 2, 3])
    cyclic = [
        {"number": 1, "title": "a", "status": "todo", "blocked_by": [2]},
        {"number": 2, "title": "b", "status": "todo", "blocked_by": [1]},
    ]
    check("negative-cycle", topo_order(cyclic)["verdict"], "CYCLE")
    check_true("negative-cycle-members", bool(detect_cycles(build_graph(cyclic))))
    unknown = [{"number": 4, "title": "x", "status": "todo", "blocked_by": "unknown"}]
    check("negative-unknown-deps", topo_order(unknown)["verdict"], "UNKNOWN_DEPS")
    independent = [
        {"number": 20, "title": "ui", "status": "todo", "labels": ["layer:flutter"]},
        {"number": 10, "title": "api", "status": "todo", "labels": ["area:backend"]},
    ]
    check("positive-independent-priority", topo_order(independent)["order"], [10, 20])

    # 3–16 live in an isolated temp coordinator
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        state_dir = tdir / "next-auto"
        session = "sess-auto"
        wave_items = [
            {"number": 10, "title": "API", "status": "todo", "labels": ["area:backend"], "wave": 3, "blocked_by": []},
            {"number": 11, "title": "UI", "status": "todo", "labels": ["layer:flutter"], "wave": 3, "blocked_by": [10]},
            {"number": 12, "title": "docs", "status": "todo", "wave": 3, "blocked_by": [11]},
            {"number": 99, "title": "other wave", "status": "todo", "wave": 4, "blocked_by": []},
        ]
        try:
            freeze_scope("", None, wave_items)
            check("negative-scope-required", True, False)
        except ValueError:
            check("negative-scope-required", True, True)
        scope = freeze_scope("wave", 3, wave_items)
        check("positive-scope-excludes-other-wave", 99 in scope["issue_numbers"], False)
        started = start(state_dir, session, scope, wave_items, {"max_stories": 5, "max_story_attempts": 2, "max_duration_seconds": 3600})
        check("positive-start-first-ready", (started["state"]["current"] or {}).get("issue"), 10)
        check("positive-start-phase-qualify", started["state"]["current"]["phase"], "qualify")

        # High-risk NO-GO (15)
        q = qualify_auto(
            {
                "title": "Add widget test",
                "acceptance_criteria": ["empty state widget test exits 0"],
                "verify_cmd": "flutter analyze --no-pub",
                "risk": "high",
            }
        )
        check("negative-high-risk-nogo", q["verdict"], "NO-GO")
        q_go = qualify_auto(
            {
                "title": "Add widget test",
                "acceptance_criteria": ["empty state widget test exits 0"],
                "verify_cmd": "flutter analyze --no-pub",
                "risk": "low",
            }
        )
        check("positive-low-risk-go", q_go["verdict"], "GO")
        st = load_state(state_dir)
        assert st is not None
        advanced = advance(st, {"event": "nogo"})
        save_state(state_dir, advanced["state"])
        check("negative-nogo-blocks-run", advanced["state"]["status"], "blocked")

        # Fresh run for sequential completions (3)
        state_dir = tdir / "seq"
        st_start = start(state_dir, session, scope, wave_items)
        st = st_start["state"]
        # Walk #10 through confirm
        for ev in ["phase_ok"] * (PHASES.index("pr")):
            st = advance(st, {"event": ev}, wave_items)["state"]
        check("positive-reached-pr", st["current"]["phase"], "pr")
        # 6. PR idempotency
        first = pr_idempotent({"head_branch": "feat/10", "open_prs": []})
        check("positive-pr-create", first["action"], "create")
        reuse = pr_idempotent({"head_branch": "feat/10", "open_prs": [{"number": 7, "headRefName": "feat/10"}]})
        check("positive-pr-reuse", (reuse["action"], reuse["pr_number"]), ("reuse", 7))
        dup = pr_idempotent({"head_branch": "feat/10", "recorded_pr": 7, "open_prs": []})
        check("positive-pr-recorded", dup["pr_number"], 7)
        merged_pr = pr_idempotent(
            {"head_branch": "feat/10", "open_prs": [], "merged_prs": [{"number": 7, "headRefName": "feat/10", "mergeCommitOid": "abc"}]}
        )
        check("negative-pr-already-merged-no-recreate", merged_pr["action"], "already_merged")
        st = advance(st, {"event": "pr_created", "pr_number": 7, "head_branch": "feat/10"}, wave_items)["state"]
        check("positive-pr-number-recorded", st["current"]["pr_number"], 7)

        # 7. CI pending / fail
        pending_gate = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha10",
                "pr": {"baseRefName": "develop", "headRefOid": "sha10", "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
                "checks": [{"name": "ci", "state": "PENDING"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-ci-pending-wait", pending_gate["verdict"], "WAIT")
        fail_gate = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha10",
                "pr": {"baseRefName": "develop", "headRefOid": "sha10", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "FAILURE"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-ci-fail-blocked", fail_gate["verdict"], "BLOCKED")
        st = advance(st, {"event": "ci_pending"}, wave_items)["state"]
        check("positive-ci-pending-stays", st["current"]["phase"], "ci")
        st = advance(st, {"event": "phase_ok"}, wave_items)["state"]
        check("positive-ci-pass-to-merge", st["current"]["phase"], "merge")

        # 8. Required human approval automation cannot supply
        approval = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha10",
                "reviews_required": 1,
                "review_decision": "REVIEW_REQUIRED",
                "external_approval": False,
                "pr": {"baseRefName": "develop", "headRefOid": "sha10", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-missing-external-approval", approval["verdict"], "BLOCKED")
        check_true("negative-approval-reason", any("external approval" in r for r in approval["reasons"]))

        # 9. Protected branches / admin
        admin = merge_gate({"merge_args": ["--admin"], "pr": {"headRefOid": "x"}, "expected_base": "develop"})
        check("negative-admin-bypass", admin["verdict"], "BLOCKED")
        force = merge_gate({"merge_args": ["--squash", "--force"], "pr": {}, "bypass_protection": True})
        check("negative-force-and-bypass", force["verdict"], "BLOCKED")
        behind = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha",
                "pr": {"baseRefName": "develop", "headRefOid": "sha", "mergeStateStatus": "BEHIND", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-behind-no-force", behind["verdict"], "BLOCKED")

        allow = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha10",
                "reviews_required": 0,
                "pr": {"baseRefName": "develop", "headRefOid": "sha10", "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("positive-merge-allow", allow["verdict"], "ALLOW")
        check("positive-merge-args-no-admin", allow["merge_args"], ["--squash", "--delete-branch"])
        st = advance(st, {"event": "merged", "merge_sha": "sha10"}, wave_items)["state"]
        conf = confirm_merge({"expected_sha": "sha10", "merge_sha": "sha10", "target_branch": "develop", "merged_into": "develop", "pr_state": "MERGED", "target_contains_sha": True})
        check("positive-merge-confirmed", conf["verdict"], "CONFIRMED")
        # After confirm, #11 becomes ready (4. sequential)
        live_after = [
            {"number": 10, "title": "API", "status": "done", "labels": ["area:backend"], "wave": 3, "blocked_by": []},
            {"number": 11, "title": "UI", "status": "todo", "labels": ["layer:flutter"], "wave": 3, "blocked_by": [10]},
            {"number": 12, "title": "docs", "status": "todo", "wave": 3, "blocked_by": [11]},
        ]
        st = advance(st, {"event": "confirmed", "merge_sha": "sha10"}, live_after)["state"]
        check("positive-next-story-after-merge", (st.get("current") or {}).get("issue"), 11)
        check("positive-completed-records-sha", st["completed"][0]["merge_sha"], "sha10")

        # 13. Changed dependencies after a merge
        drifted = live_after + [{"number": 13, "title": "surprise", "status": "todo", "wave": 3, "blocked_by": []}]
        drift = check_scope(scope, drifted)
        check("negative-scope-expansion", drift["verdict"], "EXPANDED")
        st2 = json.loads(json.dumps(st))
        action = choose_next_story(st2, drifted, session)
        check("negative-expansion-stops", action["status"], "blocked")

        # 4. Failed verification and bounded correction
        st["current"]["attempts"] = 0
        st["current"]["phase"] = "verify"
        st = advance(st, {"event": "verify_fail"}, live_after)["state"]
        check("positive-verify-fail-enters-fix", st["current"]["phase"], "fix")
        st = advance(st, {"event": "verify_fail"}, live_after)["state"]
        st = advance(st, {"event": "verify_fail"}, live_after)["state"]
        check("negative-retry-limit", st["status"], "blocked")

        # 5. Independent reviewer failures
        state_dir_r = tdir / "review"
        st_r = start(state_dir_r, session, scope, wave_items)["state"]
        st_r["current"]["phase"] = "review"
        st_r["budget"]["max_review_rounds"] = 2
        for _ in range(3):
            st_r = advance(st_r, {"event": "review_fail"}, wave_items)["state"]
        check("negative-review-round-cap", st_r["status"], "blocked")

        # 10. Interrupted execution and safe resume
        state_dir_i = tdir / "resume"
        st_i = start(state_dir_i, session, scope, wave_items)["state"]
        st_i["current"]["phase"] = "implement"
        save_state(state_dir_i, st_i)
        resumed = resume_action(load_state(state_dir_i), wave_items)
        check("positive-resume-same-phase", resumed.get("phase"), "implement")
        check("positive-resume-same-issue", resumed.get("issue"), 10)

        # 11. Concurrent coordinator prevention
        lock_a = CoordinatorLock(state_dir_i, session)
        got_a = lock_a.acquire()
        check("positive-lock-acquire", got_a["verdict"], "OK")
        lock_b = CoordinatorLock(state_dir_i, "other-session")
        got_b = lock_b.acquire()
        check("negative-concurrent-lock", got_b["verdict"], "CONCURRENT")
        lock_a.release()

        # 12. Stale verification evidence
        stale = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha",
                "stale_verify": True,
                "pr": {"baseRefName": "develop", "headRefOid": "sha", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-stale-verify", stale["verdict"], "BLOCKED")
        stamp = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha",
                "verify_stamp": "CHANGED",
                "pr": {"baseRefName": "develop", "headRefOid": "sha", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-changed-stamp", stamp["verdict"], "BLOCKED")

        # 14. Retry, timeout, cancellation, cost limits
        state_dir_c = tdir / "cancel"
        st_c = start(state_dir_c, session, scope, wave_items)["state"]
        st_c = advance(st_c, {"event": "cancel"}, wave_items)["state"]
        check("positive-cancel", st_c["status"], "cancelled")
        state_dir_t = tdir / "timeout"
        st_t = start(state_dir_t, session, scope, wave_items, {"max_duration_seconds": 0})["state"]
        st_t["started_at"] = time.time() - 5
        reason = budget_block(st_t)
        check_true("negative-duration-budget", reason is not None and "duration" in reason)
        cost = (st_t.get("budget") or {}).get("cost_metered")
        check("limitation-cost-not-metered", cost, False)

        # Hook Stop: noop without state, noop with Ralph, continue when running, isolation
        hook_root = tdir / "hookroot"
        hook_root.mkdir()
        (hook_root / ".claude").mkdir()
        noop = hook_stop({"session_id": session}, hook_root, tdir / "no-such")
        check("hook-noop-no-state", noop["kind"], "noop")
        ralph = hook_root / ".claude" / "ralph-loop.local.md"
        ralph.write_text("active\n", encoding="utf-8")
        state_dir_h = tdir / "hook"
        st_h = start(state_dir_h, session, scope, wave_items)["state"]
        save_state(state_dir_h, st_h)
        skip_ralph = hook_stop({"session_id": session}, hook_root, state_dir_h)
        check("hook-noop-when-ralph-active", skip_ralph["kind"], "noop")
        ralph.unlink()
        foreign = hook_stop({"session_id": "other"}, hook_root, state_dir_h)
        check("hook-noop-foreign-session", foreign["kind"], "noop")
        unidentified = hook_stop({}, hook_root, state_dir_h)
        check("hook-noop-unidentified", unidentified["kind"], "noop")
        sub = hook_stop({"session_id": session, "agent_id": "sub-1"}, hook_root, state_dir_h)
        check("hook-noop-subagent", sub["kind"], "noop")
        cont = hook_stop({"session_id": session}, hook_root, state_dir_h)
        check("hook-continue-running", cont["kind"], "block")
        check_true("hook-continue-json", "decision" in (cont.get("stdout") or ""))
        # Platform cap
        st_h = load_state(state_dir_h)
        assert st_h is not None
        st_h["hook_iteration"] = 5
        save_state(state_dir_h, st_h)
        old = os.environ.get("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP")
        os.environ["CLAUDE_CODE_STOP_HOOK_BLOCK_CAP"] = "3"
        try:
            capped = hook_stop({"session_id": session}, hook_root, state_dir_h)
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP", None)
            else:
                os.environ["CLAUDE_CODE_STOP_HOOK_BLOCK_CAP"] = old
        check("hook-cap-stops-without-block-loop", capped["kind"], "done")
        check("hook-cap-persists-blocked", load_state(state_dir_h)["status"], "blocked")

        # 16. Entire-scope completion and final reporting
        state_dir_f = tdir / "finish"
        done_items = [
            {"number": 10, "title": "API", "status": "done", "wave": 3, "labels": ["area:backend"], "blocked_by": []},
            {"number": 11, "title": "UI", "status": "done", "wave": 3, "labels": ["layer:flutter"], "blocked_by": [10]},
            {"number": 12, "title": "docs", "status": "done", "wave": 3, "blocked_by": [11]},
        ]
        st_f = start(state_dir_f, session, freeze_scope("wave", 3, wave_items), done_items)["state"]
        check("positive-scope-complete", st_f["status"], "complete")
        check_true("positive-final-report", st_f.get("report") is not None)
        check("positive-report-remaining-empty", st_f["report"]["remaining"], [])

        # Self-approve / missing checks already covered. Blocking findings:
        findings_gate = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha",
                "blocking_findings": True,
                "pr": {"baseRefName": "develop", "headRefOid": "sha", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-blocking-findings", findings_gate["verdict"], "BLOCKED")

        # Wrong base
        base = merge_gate(
            {
                "expected_base": "develop",
                "local_head": "sha",
                "pr": {"baseRefName": "main", "headRefOid": "sha", "mergeable": "MERGEABLE"},
                "checks": [{"name": "ci", "state": "SUCCESS"}],
                "required_checks": ["ci"],
            }
        )
        check("negative-wrong-base", base["verdict"], "BLOCKED")

        # Empty --auto scope kind issues missing numbers still freeze if provided
        issue_scope = freeze_scope("issues", [10, 11], wave_items)
        check("positive-explicit-issue-scope", issue_scope["issue_numbers"], [10, 11])

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--scan-skill", action="store_true")
    parser.add_argument("--has-auto-flag", action="store_true")
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--order", type=Path)
    parser.add_argument("--next-ready", type=Path)
    parser.add_argument("--merge-gate", type=Path)
    parser.add_argument("--pr-idempotent", type=Path)
    parser.add_argument("--qualify-auto", type=Path)
    parser.add_argument("--confirm-merge", type=Path)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--advance", action="store_true")
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--hook-stop", action="store_true")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--session", default="")
    parser.add_argument("--scope-file", type=Path)
    parser.add_argument("--items", type=Path)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--invoker", default="auto")
    args, extra = parser.parse_known_args(argv)

    if args.selftest:
        return selftest()
    if args.scan_skill:
        findings = scan_auto_isolation()
        if findings:
            for f in findings:
                print(f)
            return 1
        print("SCAN PASS")
        return 0
    if args.has_auto_flag:
        tokens = extra[1:] if extra[:1] == ["--"] else extra
        ok = has_auto_flag(tokens)
        print("AUTO" if ok else "HITL")
        return 0 if ok else 1
    if args.graph:
        items = _read_json(args.graph)
        if isinstance(items, dict):
            items = items.get("items") or items.get("issues") or []
        nodes = build_graph(items)
        cycles = detect_cycles(nodes)
        print(json.dumps({"nodes": {str(k): {"deps": v["deps"], "unknown_deps": v["unknown_deps"]} for k, v in nodes.items()}, "cycles": cycles}, indent=2, sort_keys=True))
        return 1 if cycles else 0
    if args.order:
        items = _read_json(args.order)
        if isinstance(items, dict):
            items = items.get("items") or items.get("issues") or []
        result = topo_order(items, args.invoker)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("verdict") == "OK" else 1
    if args.next_ready:
        items = _read_json(args.next_ready)
        if isinstance(items, dict):
            items = items.get("items") or items.get("issues") or []
        state = _read_json(args.state) if args.state else empty_state(args.session or "auto", freeze_scope("issues", [issue_number(i) for i in items if issue_number(i) is not None], items))
        action = choose_next_story(state, items, args.invoker)
        print(json.dumps({"action": action, "state_current": state.get("current"), "status": state.get("status")}, indent=2, sort_keys=True, default=str))
        return 0 if action.get("status") != "blocked" else 1
    if args.merge_gate:
        result = merge_gate(_read_json(args.merge_gate))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] in {"ALLOW", "ALREADY_MERGED"} else 1
    if args.pr_idempotent:
        result = pr_idempotent(_read_json(args.pr_idempotent))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.qualify_auto:
        result = qualify_auto(_read_json(args.qualify_auto))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] == "GO" else 1
    if args.confirm_merge:
        result = confirm_merge(_read_json(args.confirm_merge))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] == "CONFIRMED" else 1
    if args.hook_stop:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        root = (args.root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())).resolve()
        result = hook_stop(payload, root, args.state_dir)
        if result.get("stdout"):
            sys.stdout.write(result["stdout"])
        return 0

    root = (args.root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())).resolve()
    state_dir = args.state_dir or default_state_dir(root)
    session = args.session or os.environ.get("CLAUDE_SESSION_ID") or ""
    items: list[dict[str, Any]] | None = None
    if args.items:
        loaded = _read_json(args.items)
        items = loaded.get("items") if isinstance(loaded, dict) and "items" in loaded else loaded

    if args.start:
        if not session:
            print("ERROR: --session is required", file=sys.stderr)
            return 2
        if not args.scope_file:
            print("ERROR: --scope-file is required (wave, milestone, or issues). Whole-board auto is forbidden.", file=sys.stderr)
            return 2
        if items is None:
            print("ERROR: --items is required for --start", file=sys.stderr)
            return 2
        scope_spec = _read_json(args.scope_file)
        try:
            scope = freeze_scope(str(scope_spec.get("kind") or ""), scope_spec.get("selector"), items)
        except (ValueError, TypeError) as exc:
            print(json.dumps({"verdict": "BLOCKED", "reason": str(exc)}))
            return 1
        lock = CoordinatorLock(state_dir, session, recover=args.recover)
        locked = lock.acquire()
        if locked["verdict"] != "OK":
            print(json.dumps(locked, indent=2, sort_keys=True, default=str))
            return 1
        try:
            result = start(state_dir, session, scope, items, scope_spec.get("budget"))
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if result.get("verdict") in {"STARTED", "RESUME"} else 1
        finally:
            # Keep the lock file metadata; process lock releases on exit.
            lock.release()
    if args.resume:
        state = load_state(state_dir)
        if not state:
            print(json.dumps({"verdict": "NONE", "reason": "no auto state"}))
            return 1
        if session and state.get("session_id") and state["session_id"] != session:
            print(json.dumps({"verdict": "CONCURRENT", "reason": "state belongs to another session"}))
            return 1
        action = resume_action(state, items)
        print(json.dumps({"verdict": "OK", "action": action, "state": {"status": state.get("status"), "current": state.get("current")}}, indent=2, sort_keys=True, default=str))
        return 0 if action.get("status") != "blocked" else 1
    if args.advance:
        if not args.event:
            print("ERROR: --event is required", file=sys.stderr)
            return 2
        lock = CoordinatorLock(state_dir, session or "auto", recover=args.recover)
        locked = lock.acquire()
        if locked["verdict"] != "OK":
            print(json.dumps(locked, indent=2, sort_keys=True, default=str))
            return 1
        try:
            state = load_state(state_dir)
            if not state:
                print(json.dumps({"verdict": "NONE"}))
                return 1
            if not session:
                session = str(state.get("session_id") or "auto")
            result = advance(state, _read_json(args.event), items)
            save_state(state_dir, result["state"])
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if result.get("verdict") in {"OK", "WAIT", "CANCELLED"} else 1
        finally:
            lock.release()
    if args.cancel:
        lock = CoordinatorLock(state_dir, session or "auto", recover=args.recover)
        locked = lock.acquire()
        if locked["verdict"] != "OK":
            print(json.dumps(locked, indent=2, sort_keys=True, default=str))
            return 1
        try:
            state = load_state(state_dir) or empty_state(session or "unknown", {"kind": "issues", "selector": [], "issue_numbers": [], "fingerprint": ""})
            state["status"] = "cancelled"
            state["report"] = final_report(state)
            save_state(state_dir, state)
            print(json.dumps({"verdict": "CANCELLED", "report": state["report"]}, indent=2, sort_keys=True, default=str))
            return 0
        finally:
            lock.release()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
