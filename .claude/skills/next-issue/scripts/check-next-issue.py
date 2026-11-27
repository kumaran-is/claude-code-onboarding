#!/usr/bin/env python3
"""Rank the next actionable work item (framework-agnostic).

Usage:
  check-next-issue.py --selftest
  check-next-issue.py --pick CANDIDATES.json --invoker LOGIN
      [--wave N] [--include-assigned-to-others]
  check-next-issue.py --scan-skill
  check-next-issue.py --check-notes docs/plans/<file>.md
  check-next-issue.py --qualify PAYLOAD.json
  check-next-issue.py --validate-verify-cmd CMD
  check-next-issue.py --verify-cmd-for STACK
  check-next-issue.py --snapshot-contract PAYLOAD.json [--root DIR]
  check-next-issue.py --check-contract SNAPSHOT.json [--root DIR]
  check-next-issue.py --scan-skip-delta FILE [FILE ...] [--root DIR]

Exit: 0 ok, 1 no pick / scan finding, 2 usage or broken selftest.
Stdlib only. Never hardcodes a product, owner, repo, or absolute path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
    "--fix-loop",
    "NO-GO",
)

FIX_LOOP_MAX_ITERATIONS = 5

# Templates from verify.md — not slash commands. Used as --verify-cmd examples.
STACK_VERIFY_CMDS = {
    "flutter": "flutter analyze --no-pub",
    "angular": "npm exec --no -- ng test --watch=false",
    "react": "npm exec --no -- vitest run",
    "python": "uv run --no-sync pytest -q",
    "java": "./mvnw test -q",
    "spring": "./mvnw test -q",
    "nestjs": "npx vitest run",
}

NOOP_VERIFY_FIRST = {
    "true",
    ":",
    "echo",
    "/bin/true",
    "/usr/bin/true",
}

SENSITIVE_RE = re.compile(
    r"\b(auth|oauth|jwt|password|secret|encrypt|payment|stripe|pci|pii|"
    r"billing|invoice|bank account|firestore rules|row.level|drop table|"
    r"force.?push|production migrate)\b",
    re.I,
)
SKIP_TEST_RE = re.compile(
    r"xit\(|xdescribe\(|xtest\(|it\.skip|test\.skip|test\.fixme|it\.fixme|"
    r"describe\.fixme|test\.fail|it\.fail|describe\.fail|pytest\.mark\.skip|"
    r"@unittest\.skip|\.skip\(|describe\.skip|skip:\s*true|"
    r"optional\s*:\s*['\"]?true['\"]?",
    re.I,
)
ASSERT_TEST_RE = re.compile(
    r"\bassert\b|assertVisible|assertNotVisible|expect\(|XCTAssert|fail\(|verifyThat",
    re.I,
)
COV_FLOOR_RE = re.compile(
    r"(?i)(?:fail[_-]?under|cov-fail-under|--cov-fail-under|"
    r"branches|functions|lines|statements|coverageThreshold)"
    r"[\"']?\s*[:=]\s*[\"']?(\d+)"
)
AMBIGUOUS_RE = re.compile(r"\b(TBD|TODO|FIXME|maybe|somehow|tbd)\b", re.I)
DESTRUCTIVE_RE = re.compile(
    r"\b(git\s+(reset\s+--hard|push\s+--force|push\s+-f|commit|merge|checkout\s+--|clean\s+-)|"
    r"gh\s+pr\s+merge|rm\s+-rf)\b",
    re.I,
)
SLASH_CMD_RE = re.compile(r"^/[A-Za-z][A-Za-z0-9_-]*$")
WRAPPED_NOOP_RE = re.compile(
    r"(?:^|[\s;|&])(?:bash|zsh|sh)\s+-c\s+['\"]?(?:true|:|exit\s+0)\b",
    re.I,
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


def first_token(cmd: str) -> str:
    parts = cmd.strip().split()
    return parts[0] if parts else ""


def validate_verify_cmd(cmd: str) -> list[str]:
    """Return reasons the command cannot be a Ralph --verify-cmd. Empty = usable."""
    reasons: list[str] = []
    text = (cmd or "").strip()
    if not text or text == "null":
        return ["verify_cmd is empty — /verify is a Claude command, not a shell binary"]
    first = first_token(text)
    if SLASH_CMD_RE.match(first):
        reasons.append(
            f"{first} is a slash command, not a shell binary; pass the stack command from verify.md"
        )
    if first in NOOP_VERIFY_FIRST or text == "exit 0" or WRAPPED_NOOP_RE.search(text):
        reasons.append(f"{text!r} is a no-op, not a deterministic gate")
    if DESTRUCTIVE_RE.search(text):
        reasons.append("verify_cmd must not commit, push, merge, reset, or force-push")
    return reasons


def stack_verify_cmd(stack: str) -> str | None:
    key = (stack or "").strip().lower()
    return STACK_VERIFY_CMDS.get(key)


def _ac_text(payload: dict[str, Any]) -> str:
    ac = payload.get("acceptance_criteria")
    if isinstance(ac, list):
        return "\n".join(str(x) for x in ac)
    if ac:
        return str(ac)
    return str(payload.get("body") or "")


def qualify(payload: dict[str, Any]) -> dict[str, Any]:
    """GO/NO-GO before unattended /next --fix-loop. Never starts the next issue."""
    reasons: list[str] = []
    title = str(payload.get("title") or "")
    body = str(payload.get("body") or "")
    ac = _ac_text(payload)
    verify_cmd = str(payload.get("verify_cmd") or "")
    unattended = bool(payload.get("unattended", True))
    max_iter = payload.get("max_iterations", FIX_LOOP_MAX_ITERATIONS)
    try:
        max_n = int(max_iter)
    except (TypeError, ValueError):
        max_n = -1
        reasons.append("max_iterations must be a whole number")

    if not ac.strip() and "acceptance" not in body.lower() and "ac:" not in body.lower():
        reasons.append("no immutable acceptance criteria")
    if AMBIGUOUS_RE.search(ac) or AMBIGUOUS_RE.search(title):
        reasons.append("acceptance criteria are ambiguous (TBD/TODO/maybe)")
    reasons.extend(validate_verify_cmd(verify_cmd))
    blob = " ".join([title, body, ac])
    if SENSITIVE_RE.search(blob):
        reasons.append("sensitive scope (auth, payments, secrets, production data) needs a human")
    if payload.get("destructive") is True or DESTRUCTIVE_RE.search(blob):
        reasons.append("destructive git/merge/reset operations are never unattended")
    if payload.get("permissions") in {"bypass", "skip", "dangerously-skip-permissions"}:
        reasons.append("permission bypass is forbidden")
    if unattended and max_n > FIX_LOOP_MAX_ITERATIONS:
        reasons.append(f"unattended max_iterations cap is {FIX_LOOP_MAX_ITERATIONS}")
    if unattended and max_n < 1:
        reasons.append("unattended max_iterations must be 1–5")
    if not payload.get("testable", True):
        reasons.append("task is not machine-testable")
    if unattended and not (payload.get("test_files") or payload.get("acceptance_criteria") or ac.strip()):
        reasons.append("unattended loop needs acceptance criteria or listed test files")

    go = not reasons
    return {
        "verdict": "GO" if go else "NO-GO",
        "reasons": reasons,
        "max_iterations": FIX_LOOP_MAX_ITERATIONS if unattended else max_n,
        "verify_cmd": verify_cmd,
        "human_required": not go,
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count_in_files(root: Path, rels: list[str], pattern: re.Pattern[str]) -> int:
    n = 0
    for rel in rels:
        path = root / rel
        if not path.is_file():
            continue
        try:
            n += len(pattern.findall(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return n


def _min_cov_floor(root: Path, rels: list[str]) -> int | None:
    floors: list[int] = []
    for rel in rels:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        floors.extend(int(m.group(1)) for m in COV_FLOOR_RE.finditer(text))
    return min(floors) if floors else None


def snapshot_contract(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    """Hash approved AC + verifier + test files. Stored in existing Ralph state, not a new store."""
    ac = _ac_text(payload)
    cmd = str(payload.get("verify_cmd") or "")
    files = [str(x) for x in (payload.get("test_files") or []) if str(x).strip()]
    quality = [str(x) for x in (payload.get("quality_files") or []) if str(x).strip()]
    file_sha: dict[str, str] = {}
    for rel in files:
        path = root / rel
        if path.is_file():
            file_sha[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            file_sha[rel] = "missing"
    quality_sha: dict[str, str] = {}
    for rel in quality:
        path = root / rel
        if path.is_file():
            quality_sha[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            quality_sha[rel] = "missing"
    return {
        "ac_sha256": _sha256_text(ac.strip()),
        "verify_cmd": cmd,
        "verify_cmd_sha256": _sha256_text(cmd.strip()),
        "test_files": files,
        "test_sha256": file_sha,
        "quality_files": quality,
        "quality_sha256": quality_sha,
        "assert_count": _count_in_files(root, files, ASSERT_TEST_RE),
        "skip_count": _count_in_files(root, files, SKIP_TEST_RE),
        "cov_floor": _min_cov_floor(root, quality or files),
        "root": str(root),
    }


def check_contract(snapshot: dict[str, Any], root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare live AC/tests to the snapshot. Weakening is not a PASS. TDD additions are OK."""
    findings: list[str] = []
    if payload is None:
        live_ac_sha = snapshot.get("ac_sha256")
        live_cmd_sha = _sha256_text(str(snapshot.get("verify_cmd") or "").strip())
    else:
        live_ac_sha = _sha256_text(_ac_text(payload).strip())
        live_cmd_sha = _sha256_text(str(payload.get("verify_cmd") or "").strip())
    if live_ac_sha != snapshot.get("ac_sha256"):
        findings.append("acceptance criteria hash changed — completion criteria were altered")
    if live_cmd_sha != snapshot.get("verify_cmd_sha256"):
        findings.append("verify_cmd hash changed — verifier was swapped")
    files = [str(x) for x in (snapshot.get("test_files") or [])]
    skip_now = _count_in_files(root, files, SKIP_TEST_RE)
    assert_now = _count_in_files(root, files, ASSERT_TEST_RE)
    skip_was = int(snapshot.get("skip_count") or 0)
    assert_was = int(snapshot.get("assert_count") or 0)
    if skip_now > skip_was:
        findings.append(f"skip/xit count rose {skip_was} → {skip_now} (test weakening)")
    if assert_now < assert_was:
        findings.append(f"assertion count fell {assert_was} → {assert_now} (deleted assertions)")
    missing = [rel for rel in files if not (root / rel).is_file() and (snapshot.get("test_sha256") or {}).get(rel) not in {None, "missing"}]
    if missing:
        findings.append(f"test files disappeared: {', '.join(missing)}")
    quality = [str(x) for x in (snapshot.get("quality_files") or [])]
    floor_now = _min_cov_floor(root, quality or files)
    floor_was = snapshot.get("cov_floor")
    if floor_was is not None and floor_now is not None and int(floor_now) < int(floor_was):
        findings.append(f"coverage floor dropped {floor_was} → {floor_now}")
    quality_changed = False
    for rel in quality:
        path = root / rel
        was = (snapshot.get("quality_sha256") or {}).get(rel)
        if not was or was == "missing":
            continue
        if not path.is_file():
            findings.append(f"quality config disappeared: {rel}")
            continue
        now = hashlib.sha256(path.read_bytes()).hexdigest()
        if now != was:
            quality_changed = True
    verdict = "WEAKENED" if findings else "OK"
    tdd_added = assert_now > assert_was and skip_now <= skip_was and not findings
    return {
        "verdict": verdict,
        "findings": findings,
        "assert_count": assert_now,
        "skip_count": skip_now,
        "tdd_added": tdd_added,
        "quality_changed": quality_changed,
        "human_required": bool(findings) or tdd_added or quality_changed,
    }


def _git_show(root: Path, rel: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _repo_rel(root: Path, spec: str) -> tuple[Path, str] | str:
    """Resolve spec to (path, git-relative). Return an error string if it is outside root."""
    raw = Path(spec)
    path = raw if raw.is_absolute() else (root / spec)
    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return f"{spec}: path is outside --root"
    return path, rel


def scan_skip_delta(root: Path, rels: list[str]) -> list[str]:
    """Fail closed when skip/fixme/optional count rose vs HEAD (healer path; no Ralph snapshot)."""
    findings: list[str] = []
    root = root.resolve()
    for spec in rels:
        resolved = _repo_rel(root, spec)
        if isinstance(resolved, str):
            findings.append(resolved)
            continue
        path, rel = resolved
        if not path.is_file():
            findings.append(f"{rel}: missing (not a file)")
            continue
        after = path.read_text(encoding="utf-8", errors="replace")
        before = _git_show(root, rel) or ""
        n_after = len(SKIP_TEST_RE.findall(after))
        n_before = len(SKIP_TEST_RE.findall(before))
        if n_after > n_before:
            findings.append(f"{rel}: skip/fixme/optional count rose {n_before} → {n_after}")
    return findings


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
    loop_ref = skill_dir / "references" / "loop-and-qualify.md"
    if not loop_ref.is_file():
        findings.append("missing references/loop-and-qualify.md")
    else:
        loop_body = loop_ref.read_text(encoding="utf-8")
        for needle in (
            "--fix-loop",
            "NO-GO",
            "--verify-cmd",
            "require_verify",
            "Do not start the next issue",
            "--snapshot-contract",
            "WEAKENED",
            "ESCALATED",
        ):
            if needle not in loop_body:
                findings.append(f"loop-and-qualify.md missing {needle}")
    handoff = skill_dir / "references" / "plan-and-handoff.md"
    handoff_body = handoff.read_text(encoding="utf-8")
    if "optional worktree" not in handoff_body.lower():
        findings.append("plan-and-handoff.md missing optional worktree")
    if "--fix-loop" not in handoff_body:
        findings.append("plan-and-handoff.md missing --fix-loop")
    if "Auto-merge is forbidden" not in handoff_body:
        findings.append("plan-and-handoff.md lost HITL auto-merge forbid")
    for needle in ("check-verify-impact.py", "/create-pr", "does not merge", "--stage iteration", "--stage frozen", "playwright-test-agents.md", "E2E quality contract", "--scan-skip-delta"):
        if needle not in handoff_body:
            findings.append(f"plan-and-handoff.md missing {needle}")
    auto_ref = skill_dir / "references" / "auto-loop.md"
    if not auto_ref.is_file():
        findings.append("missing references/auto-loop.md")
    else:
        auto_body = auto_ref.read_text(encoding="utf-8")
        for needle in ("never be activated implicitly", "Do not silently expand", "--admin"):
            if needle not in auto_body:
                findings.append(f"auto-loop.md missing {needle}")
    if "only the `--auto` flag" not in text and "only when `--auto`" not in text:
        findings.append("SKILL.md must say --auto is opt-in only")
    if "Do not run `gh pr merge`" not in text:
        findings.append("SKILL.md lost HITL merge gate")
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

    q_go = qualify(
        {
            "title": "Add widget test",
            "body": "Acceptance criteria: the widget renders empty and error states.",
            "acceptance_criteria": ["empty state widget test exits 0"],
            "verify_cmd": STACK_VERIFY_CMDS["flutter"],
            "unattended": True,
            "max_iterations": 5,
        }
    )
    check("positive-qualify-flutter-go", q_go["verdict"], "GO")
    q_angular = qualify(
        {
            "title": "Fix login form validation",
            "acceptance_criteria": ["invalid email shows the error id"],
            "verify_cmd": STACK_VERIFY_CMDS["angular"],
            "unattended": True,
        }
    )
    check("positive-qualify-angular-go", q_angular["verdict"], "GO")
    q_react = qualify(
        {
            "title": "Query cache invalidation",
            "acceptance_criteria": ["vitest covers stale-while-revalidate"],
            "verify_cmd": STACK_VERIFY_CMDS["react"],
            "unattended": True,
        }
    )
    check("positive-qualify-react-go", q_react["verdict"], "GO")
    q_py = qualify(
        {
            "title": "Health endpoint",
            "acceptance_criteria": ["pytest covers 200 and 503"],
            "verify_cmd": STACK_VERIFY_CMDS["python"],
            "unattended": True,
        }
    )
    check("positive-qualify-python-go", q_py["verdict"], "GO")
    q_java = qualify(
        {
            "title": "Add ProblemDetail handler",
            "acceptance_criteria": ["mvn test covers 404 mapping"],
            "verify_cmd": STACK_VERIFY_CMDS["java"],
            "unattended": True,
        }
    )
    check("positive-qualify-java-go", q_java["verdict"], "GO")

    q_slash = qualify(
        {
            "title": "Fix tests",
            "acceptance_criteria": ["all tests pass"],
            "verify_cmd": "/verify full",
            "unattended": True,
        }
    )
    check("negative-qualify-slash-verify", q_slash["verdict"], "NO-GO")
    q_auth = qualify(
        {
            "title": "Rotate JWT secret",
            "acceptance_criteria": ["auth still works"],
            "verify_cmd": STACK_VERIFY_CMDS["python"],
            "unattended": True,
        }
    )
    check("negative-qualify-auth-nogo", q_auth["verdict"], "NO-GO")
    q_ac = qualify({"title": "Do stuff", "verify_cmd": "flutter test", "unattended": True})
    check("negative-qualify-no-ac", q_ac["verdict"], "NO-GO")
    q_iter = qualify(
        {
            "title": "Tiny fix",
            "acceptance_criteria": ["unit test exits 0"],
            "verify_cmd": "flutter test",
            "unattended": True,
            "max_iterations": 12,
        }
    )
    check("negative-qualify-over-max-iter", q_iter["verdict"], "NO-GO")
    q_destr = qualify(
        {
            "title": "Clean tree",
            "acceptance_criteria": ["tests pass"],
            "verify_cmd": "flutter test",
            "destructive": True,
            "unattended": True,
        }
    )
    check("negative-qualify-destructive", q_destr["verdict"], "NO-GO")
    q_bill = qualify(
        {
            "title": "Change billing invoice totals",
            "acceptance_criteria": ["invoice PDF matches"],
            "verify_cmd": STACK_VERIFY_CMDS["python"],
            "unattended": True,
        }
    )
    check("negative-qualify-billing-nogo", q_bill["verdict"], "NO-GO")

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        testf = tdir / "t_widget_test.dart"
        testf.write_text("void main() { test('empty', () { expect(1, 1); }); }\n", encoding="utf-8")
        snap_payload = {
            "title": "Widget empty state",
            "acceptance_criteria": ["empty state widget test exits 0"],
            "verify_cmd": STACK_VERIFY_CMDS["flutter"],
            "test_files": ["t_widget_test.dart"],
        }
        snap = snapshot_contract(snap_payload, tdir)
        chk = check_contract(snap, tdir, snap_payload)
        check("positive-contract-unchanged", chk["verdict"], "OK")
        testf.write_text(
            "void main() { test('empty', () { expect(1, 1); expect(2, 2); }); }\n",
            encoding="utf-8",
        )
        chk = check_contract(snap, tdir, snap_payload)
        check("positive-tdd-added-assertions", chk["tdd_added"] and chk["verdict"] == "OK", True)
        testf.write_text("void main() { test('empty', () {}, skip: true); }\n", encoding="utf-8")
        chk = check_contract(snap, tdir, snap_payload)
        check("negative-skip-is-weakening", chk["verdict"], "WEAKENED")
        pw = tdir / "signin.spec.ts"
        pw.write_text(
            "test('shows heading', async ({ page }) => { await expect(page.getByRole('heading')).toBeVisible(); });\n",
            encoding="utf-8",
        )
        pw_payload = {
            "title": "Sign in heading",
            "acceptance_criteria": ["heading is visible"],
            "verify_cmd": STACK_VERIFY_CMDS["angular"],
            "test_files": ["signin.spec.ts"],
        }
        pw_snap = snapshot_contract(pw_payload, tdir)
        pw.write_text(
            "test.fixme('shows heading', async ({ page }) => { await expect(page.getByRole('heading')).toBeVisible(); });\n",
            encoding="utf-8",
        )
        chk = check_contract(pw_snap, tdir, pw_payload)
        check("negative-fixme-is-weakening", chk["verdict"], "WEAKENED")
        repo = tdir / "repo"
        repo.mkdir()
        spec = repo / "e2e.spec.ts"
        spec.write_text("test('ok', async ({ page }) => { await expect(page).toHaveURL('/'); });\n", encoding="utf-8")
        git_id = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo, check=True)
        subprocess.run([*git_id, "add", "e2e.spec.ts"], cwd=repo, check=True)
        subprocess.run([*git_id, "commit", "-qm", "base"], cwd=repo, check=True)
        spec.write_text("test.fixme('ok', async ({ page }) => { await expect(page).toHaveURL('/'); });\n", encoding="utf-8")
        delta = scan_skip_delta(repo, ["e2e.spec.ts"])
        check("negative-scan-skip-delta-fixme", bool(delta), True)
        spec.write_text("test('ok', async ({ page }) => { await expect(page).toHaveURL('/'); });\n", encoding="utf-8")
        check("positive-scan-skip-delta-clean", scan_skip_delta(repo, ["e2e.spec.ts"]), [])
        flow = repo / "increment.yaml"
        flow.write_text('appId: x\n---\n- assertVisible: "1"\n', encoding="utf-8")
        subprocess.run([*git_id, "add", "increment.yaml"], cwd=repo, check=True)
        subprocess.run([*git_id, "commit", "-qm", "flow"], cwd=repo, check=True)
        flow.write_text(
            'appId: x\n---\n- assertVisible:\n    text: "1"\n    optional: true\n',
            encoding="utf-8",
        )
        check(
            "negative-scan-skip-delta-optional",
            bool(scan_skip_delta(repo, ["increment.yaml"])),
            True,
        )
        subprocess.run(["git", "checkout", "-q", "--", "increment.yaml"], cwd=repo, check=True)
        flow.write_text(
            'appId: x\n---\n- assertVisible:\n    text: "1"\n    optional : true\n',
            encoding="utf-8",
        )
        check(
            "negative-scan-skip-delta-optional-space",
            bool(scan_skip_delta(repo, ["increment.yaml"])),
            True,
        )
        check(
            "negative-scan-skip-delta-missing",
            bool(scan_skip_delta(repo, ["nope.spec.ts"])),
            True,
        )
        yml = tdir / "flow.yaml"
        yml.write_text('appId: x\n---\n- assertVisible: "1"\n', encoding="utf-8")
        yml_payload = {
            "title": "Increment",
            "acceptance_criteria": ["counter is 1"],
            "verify_cmd": STACK_VERIFY_CMDS["flutter"],
            "test_files": ["flow.yaml"],
        }
        yml_snap = snapshot_contract(yml_payload, tdir)
        yml.write_text('appId: x\n---\n- tapOn: "Increment"\n', encoding="utf-8")
        chk = check_contract(yml_snap, tdir, yml_payload)
        check("negative-maestro-deleted-assertVisible", chk["verdict"], "WEAKENED")
        testf.write_text("void main() {}\n", encoding="utf-8")
        chk = check_contract(snap, tdir, snap_payload)
        check("negative-deleted-assertions", chk["verdict"], "WEAKENED")
        testf.write_text("void main() { test('empty', () { expect(1, 1); }); }\n", encoding="utf-8")
        tampered = dict(snap_payload)
        tampered["acceptance_criteria"] = ["ship it without tests"]
        chk = check_contract(snap, tdir, tampered)
        check("negative-ac-hash-changed", chk["verdict"], "WEAKENED")
        swapped = dict(snap_payload)
        swapped["verify_cmd"] = "true"
        chk = check_contract(snap, tdir, swapped)
        check("negative-verify-cmd-swapped", chk["verdict"], "WEAKENED")
        cov = tdir / "coverage.config.json"
        cov.write_text('{"coverageThreshold": 80}\n', encoding="utf-8")
        cov_payload = dict(snap_payload)
        cov_payload["quality_files"] = ["coverage.config.json"]
        cov_snap = snapshot_contract(cov_payload, tdir)
        chk = check_contract(cov_snap, tdir, cov_payload)
        check("positive-coverage-unchanged", chk["verdict"], "OK")
        cov.write_text('{"coverageThreshold": 90}\n', encoding="utf-8")
        chk = check_contract(cov_snap, tdir, cov_payload)
        check("positive-coverage-raised", chk["verdict"] == "OK" and chk["quality_changed"] and chk["human_required"], True)
        cov.write_text('{"coverageThreshold": 10}\n', encoding="utf-8")
        chk = check_contract(cov_snap, tdir, cov_payload)
        check("negative-coverage-floor-dropped", chk["verdict"], "WEAKENED")

    check("negative-validate-slash", bool(validate_verify_cmd("/verify")), True)
    check("negative-validate-true", bool(validate_verify_cmd("true")), True)
    check("negative-validate-wrapped-noop", bool(validate_verify_cmd("bash -c true")), True)
    check("negative-validate-merge", bool(validate_verify_cmd("gh pr merge 1")), True)
    check("positive-validate-flutter", validate_verify_cmd(STACK_VERIFY_CMDS["flutter"]), [])
    check("positive-validate-angular", validate_verify_cmd(STACK_VERIFY_CMDS["angular"]), [])
    check("positive-validate-react", validate_verify_cmd(STACK_VERIFY_CMDS["react"]), [])
    check("positive-validate-python", validate_verify_cmd(STACK_VERIFY_CMDS["python"]), [])
    check("positive-verify-cmd-for-nestjs", stack_verify_cmd("nestjs"), STACK_VERIFY_CMDS["nestjs"])
    check("negative-verify-cmd-for-unknown", stack_verify_cmd("cobol"), None)

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
    parser.add_argument("--qualify", type=Path)
    parser.add_argument("--validate-verify-cmd", dest="validate_cmd", default=None)
    parser.add_argument("--verify-cmd-for", dest="verify_for", default=None)
    parser.add_argument("--snapshot-contract", type=Path)
    parser.add_argument("--check-contract", type=Path)
    parser.add_argument("--scan-skip-delta", nargs="+", metavar="FILE")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--payload", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.validate_cmd is not None:
        reasons = validate_verify_cmd(args.validate_cmd)
        if reasons:
            for r in reasons:
                print(r)
            return 1
        print("VERIFY_CMD OK")
        return 0
    if args.verify_for is not None:
        cmd = stack_verify_cmd(args.verify_for)
        if not cmd:
            print(f"unknown stack {args.verify_for!r}; known: {', '.join(sorted(STACK_VERIFY_CMDS))}", file=sys.stderr)
            return 2
        print(cmd)
        return 0
    if args.qualify:
        payload = json.loads(args.qualify.read_text(encoding="utf-8"))
        result = qualify(payload)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] == "GO" else 1
    if args.snapshot_contract:
        payload = json.loads(args.snapshot_contract.read_text(encoding="utf-8"))
        root = (args.root or Path.cwd()).resolve()
        print(json.dumps(snapshot_contract(payload, root), indent=2, sort_keys=True))
        return 0
    if args.check_contract:
        snapshot = json.loads(args.check_contract.read_text(encoding="utf-8"))
        root = (args.root or Path.cwd()).resolve()
        payload = json.loads(args.payload.read_text(encoding="utf-8")) if args.payload else None
        result = check_contract(snapshot, root, payload)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] == "OK" else 1
    if args.scan_skip_delta:
        root = (args.root or Path.cwd()).resolve()
        findings = scan_skip_delta(root, args.scan_skip_delta)
        if findings:
            for f in findings:
                print(f)
            return 1
        print("SKIP DELTA OK")
        return 0
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
