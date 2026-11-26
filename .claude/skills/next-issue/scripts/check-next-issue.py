#!/usr/bin/env python3
"""Rank the next actionable work item (framework-agnostic).

Usage:
  check-next-issue.py --selftest
  check-next-issue.py --pick CANDIDATES.json --invoker LOGIN
      [--wave N] [--include-assigned-to-others]
  check-next-issue.py --scan-skill
  check-next-issue.py --check-notes docs/plans/<file>.md

Exit: 0 ok, 1 no pick / scan finding, 2 usage or broken selftest.
Stdlib only. Never hardcodes a product, owner, repo, or absolute path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ENTRY_SPLIT = re.compile(r"\*\*Category:\*\*\s*(\w+)", re.I)
FLAG_RE = re.compile(r"\*\*Needs human review:\*\*\s*(yes|no)", re.I)
REV_RE = re.compile(r"\*\*Reversibility:\*\*\s*(GREEN|YELLOW|RED)", re.I)
CONF_RE = re.compile(r"\*\*Confidence:\*\*\s*(high|medium|low)", re.I)

SKILL_DIR = Path(__file__).resolve().parent.parent

STATUSES_TODO = {"todo"}
STATUSES_RESUME = {"in_progress"}
STATUSES_DROP = {"done", "in_review"}
LAYER_ORDER = ("foundation", "api", "agent", "frontend", "other")

FOUNDATION_LABELS = {
    "layer:migration",
    "layer:schema",
    "layer:infra",
    "area:infra",
    "area:database",
    "layer:database",
}
API_LABELS = {
    "area:backend",
    "layer:backend",
    "layer:api",
    "layer:mcp",
    "layer:fastapi",
    "area:api",
}
AGENT_LABELS = {
    "layer:ai-agent",
    "area:ai-agent",
    "layer:agent",
    "area:agent",
}
FRONTEND_LABELS = {
    "layer:flutter",
    "layer:angular",
    "layer:react",
    "layer:frontend",
    "layer:ui",
    "area:flutter",
    "area:frontend",
    "area:web",
}

BLOCKING_BRAINSTORM = (
    "must brainstorm",
    "brainstorm before",
    "required brainstorm",
    "brainstorm hard gate",
)

FORBIDDEN_SKILL_MARKERS = (
    "property-harbor",
    "propertyharbor",
    "ph-tenants",
    "ph-postgres",
    "rentflow",
    "harbor-ai",
    "/Users/",
    "/home/",
)

REQUIRED_SKILL_MARKERS = (
    "NEVER start implementing",
    "blocked_by_open",
    "/verify",
    "/ship",
    "--plan",
    "implementation-notes",
)

NOTES_REQUIRED_FIELDS = (
    "**Category:**",
    "**Needs human review:**",
    "**Reversibility:**",
    "**Files:**",
)

FILES_RE = re.compile(r"\*\*Files?:\*\*")
END_SESSION_MARKERS = (
    "/checkpoint",
    "/promote-lessons",
    "Do not commit",
    "Do not push",
    "Blockers",
    "Resume prompt",
    "What Did Not Work",
    "not a lesson",
)
PROMOTE_MARKERS = (
    "escaped",
    "Which existing test",
    "positive control",
    "unverified",
    "Never weaken",
)


def layer_of(labels: list[str], title: str) -> str:
    lowered = {str(x).lower() for x in labels}
    title_l = title.lower()
    if title_l.startswith("[schema]") or lowered & FOUNDATION_LABELS:
        return "foundation"
    if title_l.startswith("[mcp-tool]") or lowered & API_LABELS:
        if lowered & AGENT_LABELS and "layer:mcp" not in lowered and not title_l.startswith("[mcp-tool]"):
            return "agent"
        return "api"
    if lowered & AGENT_LABELS:
        return "agent"
    if lowered & FRONTEND_LABELS:
        return "frontend"
    return "other"


def assigned_to_other(item: dict[str, Any], invoker: str) -> bool:
    assignees = [str(a).lower() for a in item.get("assignees") or [] if a]
    if not assignees:
        return False
    return invoker.lower() not in assignees


def is_epic(item: dict[str, Any]) -> bool:
    if item.get("is_epic") is True:
        return True
    title = str(item.get("title") or "")
    return title.startswith("[EPIC]")


def normalize(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out["status"] = str(item.get("status") or "todo").lower().replace(" ", "_")
    out["labels"] = [str(x) for x in item.get("labels") or []]
    out["assignees"] = [str(x) for x in item.get("assignees") or []]
    out["blocked_by_open"] = [str(x) for x in item.get("blocked_by_open") or []]
    out["verification"] = str(item.get("verification") or "unknown").lower()
    out["title"] = str(item.get("title") or "")
    out["source"] = str(item.get("source") or "unknown")
    number = item.get("number")
    out["number"] = int(number) if number is not None else None
    wave = item.get("wave")
    out["wave"] = int(wave) if wave not in (None, "") else None
    out["id"] = str(item.get("id") or out["number"] or out["title"])
    out["layer"] = layer_of(out["labels"], out["title"])
    return out


def active_wave(items: list[dict[str, Any]], explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    waves = sorted(
        {
            i["wave"]
            for i in items
            if i["wave"] is not None and i["status"] in STATUSES_TODO and not is_epic(i)
        }
    )
    return waves[0] if waves else None


def pick_next(
    items: list[dict[str, Any]],
    invoker: str,
    wave: int | None = None,
    include_assigned_to_others: bool = False,
) -> dict[str, Any] | None:
    """Return the next work item or None. Resume in-flight work before new Todo."""
    if not invoker:
        raise ValueError("invoker is required")
    normalized = [normalize(i) for i in items]

    mine_in_progress = [
        i
        for i in normalized
        if i["status"] in STATUSES_RESUME and not assigned_to_other(i, invoker)
    ]
    failed = [i for i in mine_in_progress if i["verification"] == "fail"]
    if failed:
        failed.sort(key=lambda i: (i["number"] is None, i["number"] or 0, i["id"]))
        return {**failed[0], "pick_reason": "resume-failed-verification"}
    if mine_in_progress:
        mine_in_progress.sort(key=lambda i: (i["number"] is None, i["number"] or 0, i["id"]))
        return {**mine_in_progress[0], "pick_reason": "resume-in-progress"}

    resolved_wave = active_wave(normalized, wave)
    pool: list[dict[str, Any]] = []
    for i in normalized:
        if i["status"] in STATUSES_DROP:
            continue
        if i["status"] not in STATUSES_TODO:
            continue
        if is_epic(i):
            continue
        if i["blocked_by_open"]:
            continue
        if not include_assigned_to_others and assigned_to_other(i, invoker):
            continue
        if resolved_wave is not None and i["wave"] is not None and i["wave"] != resolved_wave:
            continue
        pool.append(i)

    if not pool:
        return None

    pool.sort(
        key=lambda i: (
            LAYER_ORDER.index(i["layer"]) if i["layer"] in LAYER_ORDER else 99,
            i["number"] is None,
            i["number"] or 0,
            i["id"],
        )
    )
    winner = pool[0]
    return {**winner, "pick_reason": f"todo-layer-{winner['layer']}", "active_wave": resolved_wave}


def load_candidates(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("candidates JSON must be a list or {items: [...]}")


def check_notes(path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing notes file {path}"]
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    if "Needs human review" not in text and "**Needs human review:**" not in text:
        findings.append("notes file has no 'Needs human review' field")
    starts = list(ENTRY_SPLIT.finditer(text))
    if not starts:
        return findings
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[m.start() : end]
        cat = m.group(1).lower()
        flag_m = FLAG_RE.search(body)
        flag = flag_m.group(1).lower() if flag_m else ""
        rev_m = REV_RE.search(body)
        conf_m = CONF_RE.search(body)
        rev = rev_m.group(1).upper() if rev_m else ""
        conf = conf_m.group(1).lower() if conf_m else ""
        must_flag = cat == "deviation" or (rev == "RED" and conf in {"medium", "low"})
        if must_flag and flag != "yes":
            findings.append(
                f"entry {i + 1} ({cat or 'unknown'}): needs human review: yes required"
            )
        if not FILES_RE.search(body):
            findings.append(f"entry {i + 1}: missing Files scope")
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
    notes_ref = skill_dir / "references" / "implementation-notes.md"
    if not notes_ref.is_file():
        findings.append("missing references/implementation-notes.md")
    else:
        body = notes_ref.read_text(encoding="utf-8")
        for field in NOTES_REQUIRED_FIELDS:
            if field not in body:
                findings.append(f"implementation-notes.md missing {field}")
    for path in [skill_md, *sorted((skill_dir / "references").glob("*.md"))]:
        body = path.read_text(encoding="utf-8")
        lower = body.lower()
        for bad in FORBIDDEN_SKILL_MARKERS:
            if bad.lower() in lower:
                findings.append(f"{path.name} contains product/path marker: {bad}")
        for bad in BLOCKING_BRAINSTORM:
            if bad in lower:
                findings.append(f"{path.name} makes brainstorm a gate: {bad}")
    if "optional worktree" not in (skill_dir / "references" / "plan-and-handoff.md").read_text(encoding="utf-8").lower():
        findings.append("plan-and-handoff.md missing optional worktree")
    if "/brainstorm" not in skill_md.read_text(encoding="utf-8") and "brainstorm is never required" not in skill_md.read_text(encoding="utf-8").lower():
        findings.append("SKILL.md must state brainstorm is never required")
    claude_dir = skill_dir.parent.parent
    related = {
        claude_dir / "commands" / "end-session.md": END_SESSION_MARKERS,
        claude_dir / "commands" / "promote-lessons.md": PROMOTE_MARKERS,
        claude_dir / "commands" / "brainstorm.md": (
            "Playback",
            "Assumptions and constraints",
            "never blocks",
            "startup-design",
        ),
    }
    for path, markers in related.items():
        if not path.is_file():
            findings.append(f"missing related command {path.name}")
            continue
        body = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in body:
                findings.append(f"{path.name} missing required marker: {marker}")
    return findings


def selftest() -> int:
    invoker = "me"
    fail = 0

    def check(name: str, got: Any, expect: Any) -> None:
        nonlocal fail
        if got != expect:
            print(f"  FAIL {name}: got {got!r} expected {expect!r}")
            fail += 1
        else:
            print(f"  ok   {name}")

    # Positive: lowest unblocked in earliest layer
    items = [
        {"id": "30", "number": 30, "title": "UI", "status": "todo", "labels": ["layer:flutter"]},
        {"id": "10", "number": 10, "title": "API", "status": "todo", "labels": ["area:backend"]},
        {"id": "5", "number": 5, "title": "Agent", "status": "todo", "labels": ["layer:ai-agent"]},
    ]
    pick = pick_next(items, invoker)
    check("positive-layer-before-number", pick["id"] if pick else None, "10")

    # Positive: resume in-progress over newer todo
    items = [
        {"id": "1", "number": 1, "title": "old", "status": "todo", "assignees": [invoker]},
        {"id": "9", "number": 9, "title": "wip", "status": "in_progress", "assignees": [invoker]},
    ]
    pick = pick_next(items, invoker)
    check("positive-resume-in-progress", pick["id"] if pick else None, "9")

    # Positive: failed verification wins even vs other in-progress
    items = [
        {"id": "2", "number": 2, "title": "ok", "status": "in_progress", "assignees": [invoker], "verification": "pass"},
        {"id": "8", "number": 8, "title": "red", "status": "in_progress", "assignees": [invoker], "verification": "fail"},
    ]
    pick = pick_next(items, invoker)
    check("positive-resume-failed-verification", pick["id"] if pick else None, "8")

    # Positive: lowest wave with todos
    items = [
        {"id": "1", "number": 1, "title": "w1", "status": "todo", "wave": 1, "labels": ["layer:flutter"]},
        {"id": "2", "number": 2, "title": "w2", "status": "todo", "wave": 2, "labels": ["area:backend"]},
    ]
    pick = pick_next(items, invoker)
    check("positive-lowest-wave", pick["id"] if pick else None, "1")

    # Negative: open blocker skipped
    items = [
        {"id": "1", "number": 1, "title": "blocked", "status": "todo", "blocked_by_open": ["99"]},
        {"id": "2", "number": 2, "title": "free", "status": "todo"},
    ]
    pick = pick_next(items, invoker)
    check("negative-open-blocker-skipped", pick["id"] if pick else None, "2")

    # Negative: assigned to someone else skipped
    items = [
        {"id": "1", "number": 1, "title": "theirs", "status": "todo", "assignees": ["other"]},
        {"id": "2", "number": 2, "title": "open", "status": "todo", "assignees": []},
    ]
    pick = pick_next(items, invoker)
    check("negative-assignee-other-skipped", pick["id"] if pick else None, "2")

    # Negative: epic skipped
    items = [
        {"id": "1", "number": 1, "title": "[EPIC] Wave 3", "status": "todo"},
        {"id": "2", "number": 2, "title": "real", "status": "todo"},
    ]
    pick = pick_next(items, invoker)
    check("negative-epic-skipped", pick["id"] if pick else None, "2")

    # Negative: empty pool
    pick = pick_next(
        [{"id": "1", "number": 1, "title": "done", "status": "done"}],
        invoker,
    )
    check("negative-none-when-done-only", pick, None)

    # Override: include assigned to others
    items = [
        {"id": "1", "number": 1, "title": "theirs", "status": "todo", "assignees": ["other"]},
    ]
    pick = pick_next(items, invoker, include_assigned_to_others=True)
    check("positive-include-assigned-to-others", pick["id"] if pick else None, "1")

    with tempfile.TemporaryDirectory() as tmp:
        notes = Path(tmp) / "notes.md"
        notes.write_text(
            "### 2026-11-26T00:00:00Z — pick json column\n"
            "**Category:** deviation\n"
            "**Files:** src/db.py\n"
            "**Needs human review:** no\n",
            encoding="utf-8",
        )
        check(
            "negative-deviation-requires-human-review",
            any("needs human review" in f for f in check_notes(notes)),
            True,
        )
        notes.write_text(
            "### 2026-11-26T00:00:00Z — pick json column\n"
            "**Category:** tradeoff\n"
            "**Files:** src/db.py\n"
            "**Needs human review:** yes\n",
            encoding="utf-8",
        )
        check("positive-flagged-notes", check_notes(notes), [])
        notes.write_text(
            "### 2026-11-26T00:00:00Z — tradeoff no files\n"
            "**Category:** tradeoff\n"
            "**Needs human review:** yes\n",
            encoding="utf-8",
        )
        check(
            "negative-missing-files-scope",
            any("Files scope" in f for f in check_notes(notes)),
            True,
        )
        notes.write_text(
            "### 2026-11-26T00:00:00Z — tradeoff ok\n"
            "**Category:** tradeoff\n"
            "**Files:** src/a.py\n"
            "**Needs human review:** yes\n"
            "---\n"
            "### 2026-11-26T00:01:00Z — silent deviation\n"
            "**Category:** deviation\n"
            "**Files:** src/b.py\n"
            "**Needs human review:** no\n",
            encoding="utf-8",
        )
        check(
            "negative-multi-entry-deviation-not-masked",
            any("entry 2" in f and "needs human review" in f for f in check_notes(notes)),
            True,
        )
        notes.write_text(
            "### 2026-11-26T00:00:00Z — red low\n"
            "**Category:** tradeoff\n"
            "**Files:** src/schema.py\n"
            "**Reversibility:** RED\n"
            "**Confidence:** low\n"
            "**Needs human review:** no\n",
            encoding="utf-8",
        )
        check(
            "negative-red-low-requires-human-review",
            any("needs human review" in f for f in check_notes(notes)),
            True,
        )

    end_session = (SKILL_DIR.parent.parent / "commands" / "end-session.md").read_text(encoding="utf-8")
    missing = [m for m in END_SESSION_MARKERS if m not in end_session]
    check("positive-end-session-markers", missing, [])
    stripped = end_session.replace("What Did Not Work", "Omitted Section")
    check(
        "negative-end-session-without-failed-approaches",
        "What Did Not Work" in [m for m in END_SESSION_MARKERS if m not in stripped],
        True,
    )
    check(
        "regression-end-session-still-reuses-checkpoint",
        "/checkpoint" in end_session and "second snapshot" in end_session.lower(),
        True,
    )

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
    parser.add_argument("--pick", type=Path)
    parser.add_argument("--invoker", default="")
    parser.add_argument("--wave", type=int)
    parser.add_argument("--include-assigned-to-others", action="store_true")
    parser.add_argument("--scan-skill", action="store_true")
    parser.add_argument("--check-notes", type=Path)
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.check_notes:
        findings = check_notes(args.check_notes)
        if findings:
            for f in findings:
                print(f)
            return 1
        print("NOTES PASS")
        return 0
    if args.scan_skill:
        findings = scan_skill(SKILL_DIR)
        if findings:
            for f in findings:
                print(f)
            return 1
        print("SCAN PASS")
        return 0
    if args.pick:
        if not args.invoker:
            print("ERROR: --invoker is required with --pick", file=sys.stderr)
            return 2
        items = load_candidates(args.pick)
        pick = pick_next(
            items,
            args.invoker,
            wave=args.wave,
            include_assigned_to_others=args.include_assigned_to_others,
        )
        if pick is None:
            print("NONE")
            return 1
        print(json.dumps(pick, indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
