#!/usr/bin/env python3
"""Startup design-to-code workflow gate.

Validates `.startup-design/manifest.json`, secret-scans it, enforces G0–G10
dependencies, and checks the interactive prototype contract.

Usage:
  check-startup-design.py --selftest
  check-startup-design.py --root DIR
  check-startup-design.py --root DIR --status
  check-startup-design.py --root DIR --init --slug SLUG --idea TEXT [--mode standalone|aidlc]
  check-startup-design.py --root DIR --bind-aidlc [--intent PATH] [--rebind-aidlc]
  check-startup-design.py --root DIR --handoff-aidlc
  check-startup-design.py --root DIR --g5 PROCEED|ITERATE|STOP
  check-startup-design.py --root DIR --set-stage G0 --stage-status PASS [--reason TEXT] [--evidence PATH]
  check-startup-design.py --root DIR --approve-production --approved-by NAME
  check-startup-design.py --root DIR --record-mcp --evidence-kind none|discovered|mocked [--tools t1,t2]
  check-startup-design.py --root DIR --check-prototype
  check-startup-design.py --root DIR --require-production

Exit: 0 ok, 1 workflow/secret/prototype failure, 2 usage or broken selftest.
Stdlib only. A mocked MCP PASS is illegal unless --allow-mock.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(os.environ.get("STARTUP_DESIGN_SKILL_DIR", Path(__file__).resolve().parent.parent))
TEMPLATE_MANIFEST = SKILL_DIR / "assets" / "templates" / "manifest.json"
TEMPLATE_BRIEF = SKILL_DIR / "assets" / "templates" / "PRODUCT_BRIEF.md"
TEMPLATE_INVENTORY = SKILL_DIR / "assets" / "templates" / "screen-inventory.md"
TEMPLATE_DESIGN = SKILL_DIR / "assets" / "templates" / "DESIGN.md"
SCHEMA_PATH = SKILL_DIR / "assets" / "manifest.schema.json"

STAGES = [f"G{i}" for i in range(11)]
STAGE_STATUSES = {"NOT_RUN", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED"}
G5_DECISIONS = {"PROCEED", "ITERATE", "STOP", None}
PLATFORMS = {"flutter", "angular", "react", None}
UI_MODES = {"daisyui", "spartan", "hybrid", None}
MCP_EVIDENCE = {"none", "discovered", "mocked"}
SCREEN_STATUSES = {"draft", "variant", "approved", "discarded"}
MODES = {"standalone", "aidlc"}
AIDLC_BRIEF_PREFERRED = (
    "inception/requirements-analysis/requirements.md",
    "ideation/approval-handoff/initiative-brief.md",
    "ideation/intent-capture/intent-statement.md",
)
AIDLC_JOURNEY_CANDIDATES = (
    "inception/user-stories/stories.md",
    "inception/user-stories/personas.md",
    "ideation/rough-mockups/user-flow.md",
    "ideation/scope-definition/scope-document.md",
)
AIDLC_PHASE_IDEATION = "verification/phase-check-ideation.md"
AIDLC_PHASE_INCEPTION = "verification/phase-check-inception.md"
AIDLC_PHASE_CHECKS = (AIDLC_PHASE_IDEATION, AIDLC_PHASE_INCEPTION)
DESIGN_HEADINGS = (
    "## Overview",
    "## Colors",
    "## Typography",
    "## Layout",
    "## Elevation",
    "## Shapes",
    "## Motion",
    "## Voice",
    "## Components",
    "## Do",
    "## Icons",
    "## States",
    "## Refresh",
    "## Accessibility",
    "## Gap policy",
    "## Approved screens",
)

SECRET_KEYS = re.compile(
    r"(?i)(api[_-]?key|secret|password|access_token|id_token|refresh_token|"
    r"authorization|auth_header|x-goog-api-key|stitch[_-]?key|private_key)$"
)
SECRET_VALUES = re.compile(
    r"(?i)(sk-|rk_|AIza|ya29\.|ghp_|github_pat_|xox[baprs]-|Bearer\s+\S{8,})"
)
PLACEHOLDER_VALUE = re.compile(
    r"(?i)^\s*(your[_-]?api[_-]?key|<[^>]+>|\$\{[A-Z0-9_]+\}|redacted|n/?a|none)?\s*$"
)

OMITTED_RE = re.compile(r"^omitted\s*:", re.M)
TOKEN_FAMILIES = ("colors", "typography", "spacing", "rounded", "motion", "components")
PROTOTYPE_MARKERS = (
    ("banner", re.compile(r"PROTOTYPE", re.I), "prototype banner 'PROTOTYPE'"),
    ("simulated", re.compile(r"simulat", re.I), "simulated-data disclosure"),
    ("nav", re.compile(r"<nav\b|role=['\"]navigation['\"]", re.I), "navigation"),
    ("form", re.compile(r"<form\b", re.I), "form"),
    ("status", re.compile(r"role=['\"]status['\"]|class=['\"][^'\"]*skeleton", re.I),
     "cold-load status/skeleton"),
    ("empty", re.compile(r"\bempty\b", re.I), "empty state"),
    ("error", re.compile(r"\berror\b", re.I), "error state"),
    ("theme", re.compile(r"color-scheme|\.dark\b|prefers-color-scheme", re.I),
     "light/dark hook"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def manifest_path(root: Path) -> Path:
    return root / ".startup-design" / "manifest.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict) -> None:
    if aidlc_in_path(path):
        raise ValueError(f"refusing write under aidlc/: {path}")
    secrets = secret_findings(data)
    if secrets:
        raise ValueError("secret-like values in manifest: " + "; ".join(secrets))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def save_manifest(path: Path, data: dict) -> list[str]:
    try:
        dump_json(path, data)
        return []
    except ValueError as exc:
        return [str(exc)]


def walk_strings(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{path}.{k}")
            if SECRET_KEYS.search(str(k)):
                yield ("key", f"{path}.{k}", k, v if isinstance(v, str) else json.dumps(v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield ("value", path, None, obj)


def secret_findings(obj) -> list[str]:
    found = []
    for kind, path, key, value in walk_strings(obj):
        if not isinstance(value, str) or PLACEHOLDER_VALUE.match(value or ""):
            continue
        if kind == "key" and value.strip():
            found.append(f"{path}: secret-like key {key!r} has a non-placeholder value")
        if SECRET_VALUES.search(value.strip()):
            found.append(f"{path}: value looks like a credential")
    return found


def empty_stage() -> dict:
    return {"status": "NOT_RUN", "updated": None, "evidence": [], "reason": None}


def default_manifest(slug: str, idea: str, mode: str = "standalone") -> dict:
    data = load_json(TEMPLATE_MANIFEST)
    data["product_slug"] = slug
    data["idea"] = idea
    data["mode"] = mode if mode in MODES else "standalone"
    if data["mode"] == "aidlc":
        data["aidlc"] = {
            "intent_dir": None,
            "phase_checks": [],
            "consumed": [],
            "handoff": None,
        }
    else:
        data["aidlc"] = None
    return data


def aidlc_bound(data: dict) -> bool:
    aidlc = data.get("aidlc") if isinstance(data.get("aidlc"), dict) else {}
    return bool(aidlc.get("intent_dir") or aidlc.get("consumed"))


def manifest_mode(data: dict) -> str:
    if aidlc_bound(data):
        return "aidlc"
    mode = data.get("mode") or "standalone"
    return mode if mode in MODES else "standalone"


def validate_schema(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest is not an object"]
    required = [
        "version", "idea", "product_slug", "current_stage", "stages",
        "artifacts", "decisions", "stitch", "mcp_evidence", "mode",
    ]
    for key in required:
        if key not in data:
            errors.append(f"missing {key}")
    if data.get("version") != 1:
        errors.append("version must be 1")
    if not isinstance(data.get("idea"), str) or len(data.get("idea") or "") < 8:
        errors.append("idea must be a string of at least 8 characters")
    slug = data.get("product_slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug or ""):
        errors.append("product_slug must be lowercase kebab-case")
    if data.get("current_stage") not in STAGES:
        errors.append(f"current_stage {data.get('current_stage')!r} is not a gate")
    if data.get("mcp_evidence") not in MCP_EVIDENCE:
        errors.append("mcp_evidence must be none|discovered|mocked")
    mode = data.get("mode", "standalone")
    if mode not in MODES:
        errors.append("mode must be standalone|aidlc")
    aidlc = data.get("aidlc")
    if aidlc is not None and not isinstance(aidlc, dict):
        errors.append("aidlc must be an object or null")
    elif isinstance(aidlc, dict):
        for key in ("intent_dir", "handoff"):
            if key in aidlc and aidlc[key] is not None and not isinstance(aidlc[key], str):
                errors.append(f"aidlc.{key} must be a string or null")
        for key in ("phase_checks", "consumed"):
            if key in aidlc and not isinstance(aidlc[key], list):
                errors.append(f"aidlc.{key} must be an array")
        extra_aidlc = set(aidlc) - {"intent_dir", "phase_checks", "consumed", "handoff"}
        if extra_aidlc:
            errors.append(f"unknown aidlc keys: {sorted(extra_aidlc)}")
    stages = data.get("stages")
    if not isinstance(stages, dict):
        errors.append("stages must be an object")
        return errors
    for name in STAGES:
        st = stages.get(name)
        if not isinstance(st, dict):
            errors.append(f"stages.{name} missing")
            continue
        if st.get("status") not in STAGE_STATUSES:
            errors.append(f"stages.{name}.status invalid")
        if "evidence" in st and not isinstance(st["evidence"], list):
            errors.append(f"stages.{name}.evidence must be an array")
    decisions = data.get("decisions") or {}
    if not isinstance(decisions, dict):
        errors.append("decisions must be an object")
    else:
        if decisions.get("g5") not in G5_DECISIONS:
            errors.append("decisions.g5 invalid")
        if decisions.get("platform") not in PLATFORMS:
            errors.append("decisions.platform invalid")
        if decisions.get("angular_ui_mode") not in UI_MODES:
            errors.append("decisions.angular_ui_mode invalid")
        if not isinstance(decisions.get("production_approved"), bool):
            errors.append("decisions.production_approved must be boolean")
    stitch = data.get("stitch") or {}
    if not isinstance(stitch, dict):
        errors.append("stitch must be an object")
    else:
        tools = stitch.get("tools_discovered")
        if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
            errors.append("stitch.tools_discovered must be an array of strings")
        screens = stitch.get("screens")
        if not isinstance(screens, list):
            errors.append("stitch.screens must be an array")
        else:
            for i, s in enumerate(screens):
                if not isinstance(s, dict) or not s.get("id") or not s.get("title"):
                    errors.append(f"stitch.screens[{i}] needs id and title")
                elif s.get("status") not in SCREEN_STATUSES:
                    errors.append(f"stitch.screens[{i}].status invalid")
    artifacts = data.get("artifacts")
    if artifacts is not None and not isinstance(artifacts, dict):
        errors.append("artifacts must be an object")
    elif isinstance(artifacts, dict):
        for key, value in artifacts.items():
            if not isinstance(value, str):
                errors.append("artifact paths must be strings")
                break
            if not is_safe_rel(value):
                errors.append(f"artifacts.{key} must be a relative path without ..")
    if isinstance(aidlc, dict):
        for key in ("intent_dir", "handoff"):
            value = aidlc.get(key)
            if isinstance(value, str) and value and not is_safe_rel(value):
                errors.append(f"aidlc.{key} must be a relative path without ..")
        for key in ("phase_checks", "consumed"):
            for i, value in enumerate(aidlc.get(key) or []):
                if isinstance(value, str) and not is_safe_rel(value):
                    errors.append(f"aidlc.{key}[{i}] must be a relative path without ..")
    extra = set(data) - {
        "version", "mode", "idea", "product_slug", "current_stage", "stages",
        "artifacts", "decisions", "stitch", "mcp_evidence", "aidlc",
    }
    if extra:
        errors.append(f"unknown keys: {sorted(extra)}")
    return errors


def status_of(data: dict, stage: str) -> str:
    return data["stages"][stage]["status"]


def design_contract_errors(root: Path, data: dict) -> list[str]:
    rel = (data.get("artifacts") or {}).get("design_md", "DESIGN.md")
    if not is_safe_rel(rel):
        return [f"DESIGN.md path is not a safe relative path: {rel}"]
    path = root / rel
    if not path.is_file():
        return ["DESIGN.md missing"]
    if aidlc_in_path(path):
        return ["DESIGN.md is under aidlc/; refuse"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    fm = text.split("---", 2)
    block = fm[1] if text.startswith("---") and len(fm) >= 3 else ""
    if "status: unapproved" in block:
        errors.append("DESIGN.md status: unapproved is not a G4 contract")
    if OMITTED_RE.search(text) and any(
        re.search(rf"^omitted:[\s\S]*?- {fam}\b", block, re.M)
        or re.search(rf"^omitted:.*\b{fam}\b", block, re.M)
        for fam in TOKEN_FAMILIES
    ):
        errors.append("DESIGN.md still lists token families in omitted:")
    missing_heads = [h for h in DESIGN_HEADINGS if h.lower() not in text.lower()]
    if missing_heads:
        errors.append("DESIGN.md missing required headings: " + ", ".join(missing_heads))
    missing_fams = [fam for fam in TOKEN_FAMILIES if fam not in block and f"{{{fam}." not in text]
    if missing_fams:
        errors.append("DESIGN.md missing token family data: " + ", ".join(missing_fams))
    return errors


def design_omits_tokens(root: Path, data: dict) -> bool:
    return bool(design_contract_errors(root, data))


def workflow_errors(root: Path, data: dict, *, allow_mock: bool) -> list[str]:
    errors: list[str] = []
    st = {g: status_of(data, g) for g in STAGES}
    evidence = data.get("mcp_evidence")
    g5 = (data.get("decisions") or {}).get("g5")
    approved = bool((data.get("decisions") or {}).get("production_approved"))

    if st["G1"] in {"PASS", "IN_PROGRESS"} and st["G0"] != "PASS":
        errors.append("G1 requires G0 PASS")
    if st["G2"] in {"PASS", "IN_PROGRESS"} and st["G0"] != "PASS":
        errors.append("G2 requires G0 PASS")
    if st["G3"] in {"PASS", "IN_PROGRESS"} and not (st["G1"] == "PASS" and st["G2"] == "PASS"):
        errors.append("G3 requires G1 PASS and G2 PASS")
    if st["G3"] == "PASS":
        if evidence == "none":
            errors.append("G3 PASS requires mcp_evidence discovered (got none)")
        if evidence == "mocked" and not allow_mock:
            errors.append("G3 PASS with mcp_evidence=mocked is not real MCP evidence")
        if not (data.get("stitch") or {}).get("tools_discovered"):
            errors.append("G3 PASS requires stitch.tools_discovered")
        screens = (data.get("stitch") or {}).get("screens") or []
        if not any(s.get("status") == "approved" for s in screens):
            errors.append("G3 PASS requires at least one approved screen")
    if st["G4"] in {"PASS", "IN_PROGRESS"} and st["G3"] != "PASS":
        errors.append("G4 requires G3 PASS")
    if st["G4"] == "PASS":
        errors.extend(design_contract_errors(root, data))
    if st["G5"] in {"PASS", "IN_PROGRESS"} and st["G4"] != "PASS":
        errors.append("G5 requires G4 PASS")
    if st["G5"] == "PASS" and g5 not in {"PROCEED", "ITERATE", "STOP"}:
        errors.append("G5 PASS requires decisions.g5")
    if st["G6"] in {"PASS", "IN_PROGRESS"} and not (st["G5"] == "PASS" and g5 == "PROCEED"):
        errors.append("G6 requires G5 PASS and decisions.g5=PROCEED")
    if st["G6"] == "PASS":
        platform = (data.get("decisions") or {}).get("platform")
        if platform not in {"flutter", "angular", "react"}:
            errors.append("G6 PASS requires decisions.platform")
        if platform == "angular" and (data.get("decisions") or {}).get("angular_ui_mode") not in {"daisyui", "spartan", "hybrid"}:
            errors.append("G6 PASS on angular requires decisions.angular_ui_mode")
    mode = manifest_mode(data)
    for later in ["G7", "G8", "G9", "G10"]:
        if st[later] != "NOT_RUN":
            if mode == "aidlc":
                errors.append(
                    f"{later} is Construction; in aidlc mode it stays with /aidlc "
                    "(use --handoff-aidlc, do not run G7–G10 here)"
                )
            else:
                if not approved:
                    errors.append(f"{later} requires decisions.production_approved")
                if st["G6"] != "PASS":
                    errors.append(f"{later} requires G6 PASS")
    if mode == "aidlc":
        if approved:
            errors.append("aidlc mode refuses production_approved; Construction stays with /aidlc")
        intent = ((data.get("aidlc") or {}) if isinstance(data.get("aidlc"), dict) else {}).get("intent_dir")
        consumed = ((data.get("aidlc") or {}) if isinstance(data.get("aidlc"), dict) else {}).get("consumed") or []
        if st["G0"] == "PASS" and not consumed:
            errors.append("G0 PASS in aidlc mode requires --bind-aidlc consumed files")
        if st["G0"] == "PASS" and not any(str(p).endswith(AIDLC_PHASE_IDEATION) for p in consumed):
            errors.append("G0 PASS in aidlc mode requires verification/phase-check-ideation.md")
        if intent and not is_safe_rel(intent):
            errors.append(f"aidlc.intent_dir is not a safe relative path: {intent}")
        elif intent and not (root / intent).is_dir():
            errors.append(f"aidlc.intent_dir missing on disk: {intent}")
        intent_resolved = (root / intent).resolve() if intent and is_safe_rel(intent) else None
        for rel in consumed:
            if not is_safe_rel(rel):
                errors.append(f"bound AI-DLC artifact is not a safe relative path: {rel}")
                continue
            path = root / rel
            if not path.is_file():
                errors.append(f"bound AI-DLC artifact missing: {rel}")
            elif intent_resolved is not None:
                try:
                    path.resolve().relative_to(intent_resolved)
                except ValueError:
                    errors.append(f"bound AI-DLC artifact is outside intent_dir: {rel}")
    if st["G1"] == "PASS" and evidence == "none":
        errors.append("G1 PASS requires mcp_evidence discovered or mocked")
    if st["G1"] == "PASS" and evidence == "mocked" and not allow_mock:
        errors.append("G1 PASS with mcp_evidence=mocked is not real MCP evidence")
    if approved and g5 != "PROCEED":
        errors.append("production_approved requires decisions.g5=PROCEED")
    current = data.get("current_stage")
    if current not in STAGES:
        errors.append("current_stage invalid")
    return errors


def check_prototype(root: Path, data: dict) -> list[str]:
    rel = (data.get("artifacts") or {}).get("prototype", "design/prototype/index.html")
    if not is_safe_rel(rel):
        return [f"prototype path is not a safe relative path: {rel}"]
    path = root / rel
    if aidlc_in_path(path):
        return ["prototype is under aidlc/; refuse"]
    if not path.is_file():
        return [f"prototype missing: {rel}"]
    text = path.read_text(encoding="utf-8")
    missing = []
    for _key, rx, label in PROTOTYPE_MARKERS:
        if not rx.search(text):
            missing.append(f"prototype missing {label}")
    return missing


def next_action(data: dict) -> str:
    mode = manifest_mode(data)
    g5 = (data.get("decisions") or {}).get("g5")
    st = {g: status_of(data, g) for g in STAGES}
    if g5 == "STOP":
        return "stop"
    if g5 == "ITERATE":
        return "G2"
    if mode == "aidlc" and st["G5"] == "PASS" and g5 == "PROCEED":
        aidlc = data.get("aidlc") if isinstance(data.get("aidlc"), dict) else {}
        if aidlc.get("handoff"):
            return "complete (tell the human to open /aidlc)"
        return "--handoff-aidlc"
    for g in STAGES:
        if st[g] in {"NOT_RUN", "IN_PROGRESS", "FAIL", "BLOCKED"}:
            return g
    return "complete"


def print_status(data: dict) -> None:
    current = data["current_stage"]
    st = data["stages"][current]["status"]
    nxt = next_action(data)
    blocked = [
        f"{g}: {data['stages'][g].get('reason') or data['stages'][g]['status']}"
        for g in STAGES if data["stages"][g]["status"] == "BLOCKED"
    ]
    print("## Startup design")
    print(f"Mode: {manifest_mode(data)}")
    print(f"Stage: {current} {st}")
    print(f"Next: {nxt or 'complete'}")
    print(f"Blocked: {'; '.join(blocked) if blocked else 'none'}")
    arts = data.get("artifacts") or {}
    print("Artifacts: " + ", ".join(f"{k}={v}" for k, v in arts.items()))
    print(f"MCP: {data.get('mcp_evidence')}")
    if manifest_mode(data) == "aidlc":
        print("Production approved: no (Construction stays with /aidlc)")
    else:
        print("Production approved: " + ("yes" if data["decisions"]["production_approved"] else "no"))


def copy_templates(root: Path, *, skip_brief: bool = False) -> None:
    mapping = {
        TEMPLATE_INVENTORY: root / "docs" / "screen-inventory.md",
        TEMPLATE_DESIGN: root / "DESIGN.md",
    }
    if not skip_brief:
        mapping[TEMPLATE_BRIEF] = root / "PRODUCT_BRIEF.md"
    for src, dest in mapping.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(src, dest)


def find_intent_dirs(root: Path) -> list[Path]:
    spaces = root / "aidlc" / "spaces"
    if not spaces.is_dir():
        return []
    found: list[Path] = []
    for space in sorted(spaces.iterdir()):
        intents = space / "intents"
        if not intents.is_dir():
            continue
        for intent in sorted(intents.iterdir(), reverse=True):
            if intent.is_dir() and (intent / "aidlc-state.md").is_file():
                found.append(intent)
    return found


def rel_to_root(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def existing_files(intent: Path, rels: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for rel in rels:
        candidate = intent / rel
        if candidate.is_file() and candidate.stat().st_size > 0:
            found.append(candidate)
    return found


def resolve_intent(root: Path, intent_arg: str | None) -> tuple[Path | None, str | None]:
    root_r = root.resolve()
    jail = (root_r / "aidlc" / "spaces").resolve()
    if intent_arg:
        path = Path(intent_arg)
        if not path.is_absolute():
            path = root / intent_arg
        path = path.resolve()
        try:
            path.relative_to(jail)
        except ValueError:
            return None, f"intent path is outside aidlc/spaces: {intent_arg}"
        if not path.is_dir() or not (path / "aidlc-state.md").is_file():
            return None, f"not an AI-DLC intent dir (missing aidlc-state.md): {intent_arg}"
        return path, None
    found = find_intent_dirs(root)
    if not found:
        return None, "no aidlc/spaces/*/intents/*/aidlc-state.md found"
    if len(found) > 1:
        listed = ", ".join(rel_to_root(root, p) for p in found)
        return None, f"multiple intents; pass --intent. found: {listed}"
    return found[0], None


def bind_aidlc(root: Path, data: dict, intent_arg: str | None, *, rebind: bool = False) -> list[str]:
    blocked = refuse_product_writes(root)
    if blocked:
        return [blocked]
    if not (root / "aidlc").is_dir():
        return ["aidlc/ workspace missing; use --mode standalone or tell the human to run /setup-aidlc"]
    intent, err = resolve_intent(root, intent_arg)
    if err or intent is None:
        return [err or "intent not found"]
    new_rel = rel_to_root(root, intent)
    previous = (data.get("aidlc") or {}).get("intent_dir") if isinstance(data.get("aidlc"), dict) else None
    late_pass = any(status_of(data, g) == "PASS" for g in ("G2", "G3", "G4", "G5"))
    if previous and previous != new_rel and late_pass:
        if not rebind:
            return ["re-bind after G2+ PASS requires --rebind-aidlc (resets G2–G5)"]
        for g in ("G2", "G3", "G4", "G5"):
            data["stages"][g] = empty_stage()
        data["current_stage"] = "G2"
    briefs = existing_files(intent, AIDLC_BRIEF_PREFERRED)
    if not briefs:
        return [
            "no Ideation/Inception brief found "
            f"(looked for {', '.join(AIDLC_BRIEF_PREFERRED)} under {new_rel})"
        ]
    ideation_check = intent / AIDLC_PHASE_IDEATION
    if not (ideation_check.is_file() and ideation_check.stat().st_size > 0):
        return [f"missing non-empty {AIDLC_PHASE_IDEATION}"]
    journeys = existing_files(intent, AIDLC_JOURNEY_CANDIDATES)
    inception_check = intent / AIDLC_PHASE_INCEPTION
    artifacts = data.setdefault("artifacts", {})
    artifacts["product_brief"] = rel_to_root(root, briefs[0])
    consumed = [rel_to_root(root, path) for path in briefs]
    if journeys:
        artifacts["journeys"] = rel_to_root(root, journeys[0])
        consumed.extend(rel_to_root(root, path) for path in journeys)
    else:
        artifacts["journeys"] = ""
    checks = [rel_to_root(root, ideation_check)]
    artifacts["validation_plan"] = checks[0]
    consumed.append(checks[0])
    if inception_check.is_file() and inception_check.stat().st_size > 0:
        rel = rel_to_root(root, inception_check)
        checks.append(rel)
        consumed.append(rel)
    data["mode"] = "aidlc"
    data["aidlc"] = {
        "intent_dir": new_rel,
        "phase_checks": checks,
        "consumed": list(dict.fromkeys(consumed)),
        "handoff": (data.get("aidlc") or {}).get("handoff") if isinstance(data.get("aidlc"), dict) else None,
    }
    return []


def handoff_destination(root: Path) -> Path:
    return root / "design" / "AIDLC_HANDOFF.md"


def aidlc_in_path(path: Path) -> bool:
    try:
        return "aidlc" in path.resolve().parts
    except OSError as exc:
        print(f"ERROR: cannot resolve {path}: {exc}", file=sys.stderr)
        return True


def refuse_product_writes(root: Path) -> str | None:
    if "aidlc" in root.resolve().parts:
        return f"--root is under aidlc/; refuse writes: {root}"
    return None


def is_safe_rel(rel: str) -> bool:
    if not isinstance(rel, str) or not rel.strip():
        return True
    path = Path(rel)
    if path.is_absolute() or rel.startswith("/") or rel.startswith("~"):
        return False
    return ".." not in path.parts


def write_aidlc_handoff(root: Path, data: dict) -> tuple[str | None, str | None]:
    dest = handoff_destination(root)
    if aidlc_in_path(dest):
        return None, "handoff destination is under aidlc/; refuse to write"
    dest.parent.mkdir(parents=True, exist_ok=True)
    aidlc = data.get("aidlc") if isinstance(data.get("aidlc"), dict) else {}
    arts = data.get("artifacts") or {}
    approved = [
        s for s in ((data.get("stitch") or {}).get("screens") or [])
        if isinstance(s, dict) and s.get("status") == "approved"
    ]
    screen_line = ", ".join(
        f"{s.get('id')}@{s.get('version') or 'unversioned'}" for s in approved
    ) or "none"
    lines = [
        "# AI-DLC design handoff",
        "",
        "This file is **not** an AI-DLC phase approval and is not written under `aidlc/`.",
        "Construction and lifecycle stay with `/aidlc`. `/startup-design` will not run G7–G10.",
        "",
        f"- Mode: {manifest_mode(data)}",
        f"- Intent: {aidlc.get('intent_dir') or 'none'}",
        f"- Product brief (consumed): {arts.get('product_brief', '')}",
        f"- Journeys (consumed): {arts.get('journeys', '')}",
        f"- DESIGN.md: {arts.get('design_md', 'DESIGN.md')}",
        f"- Screen inventory: {arts.get('screen_inventory', '')}",
        f"- Prototype: {arts.get('prototype', '')}",
        f"- G5: {(data.get('decisions') or {}).get('g5')}",
        f"- Platform recommendation: {(data.get('decisions') or {}).get('platform') or 'unset'}",
        f"- MCP evidence: {data.get('mcp_evidence')}",
        f"- Approved screens: {screen_line}",
        "- Required states: loading, empty, error, offline (prototype contract)",
        "- Construction reviewers: accessibility-auditor, ui-standards-expert, design-system-reviewer",
        "",
        "Tell the human to open `/aidlc` for Construction. Do not invoke `/aidlc` from this skill.",
        "Do not treat this prototype as production.",
        "",
    ]
    dest.write_text("\n".join(lines), encoding="utf-8")
    return rel_to_root(root, dest), None


def set_stage(data: dict, stage: str, status: str, reason: str | None, evidence: list[str]) -> None:
    row = data["stages"][stage]
    row["status"] = status
    row["updated"] = utc_now()
    if reason is not None:
        row["reason"] = reason
    if evidence:
        row["evidence"] = list(dict.fromkeys([*(row.get("evidence") or []), *evidence]))
    data["current_stage"] = stage


def judge(root: Path, data: dict, *, allow_mock: bool, prototype: bool) -> list[str]:
    errors = validate_schema(data)
    errors.extend(secret_findings(data))
    if errors:
        return errors
    errors.extend(workflow_errors(root, data, allow_mock=allow_mock))
    if prototype and data["stages"]["G5"]["status"] in {"PASS", "IN_PROGRESS"}:
        errors.extend(check_prototype(root, data))
    return errors


def cmd_init(root: Path, slug: str, idea: str, mode: str = "standalone") -> int:
    blocked = refuse_product_writes(root)
    if blocked:
        print(f"ERROR: {blocked}", file=sys.stderr)
        return 1
    path = manifest_path(root)
    if path.exists():
        print(f"manifest exists: {path}", file=sys.stderr, flush=True)
        return 1
    if mode not in MODES:
        print("ERROR: --mode must be standalone|aidlc", file=sys.stderr)
        return 2
    if mode == "aidlc":
        if not (root / "aidlc").is_dir() or not find_intent_dirs(root):
            print(
                "ERROR: --mode aidlc requires aidlc/spaces/*/intents/*/aidlc-state.md "
                "(or use --mode standalone)",
                file=sys.stderr,
            )
            return 1
    data = default_manifest(slug, idea, mode=mode)
    save_errs = save_manifest(path, data)
    if save_errs:
        return report(save_errs)
    copy_templates(root, skip_brief=(mode == "aidlc"))
    print(f"wrote {path}", flush=True)
    return 0


def load_or_die(root: Path) -> dict:
    path = manifest_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"no manifest at {path}")
    return load_json(path)


def report(errors: list[str]) -> int:
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("startup-design: PASS")
    return 0


# -------------------------------------------------------------------------------- selftest
def _write(root: Path, data: dict) -> None:
    dump_json(manifest_path(root), data)


def selftest() -> int:
    failures: list[str] = []

    def expect(label: str, errors: list[str], should_fail: bool) -> None:
        failed = bool(errors)
        if should_fail != failed:
            failures.append(f"{label}: expected {'fail' if should_fail else 'pass'}, got {errors}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        idea = "LeafLog reminds apartment dwellers to water plants."
        if cmd_init(root, "leaflog", idea) != 0:
            return 2
        data = load_or_die(root)
        expect("init schema", validate_schema(data) + secret_findings(data), False)

        dirty = json.loads(json.dumps(data))
        dirty["stitch"]["server_name"] = "stitch"
        dirty["decisions"]["api_key"] = "sk-live-not-a-real-key-but-looks-like-one"
        expect("secret key", secret_findings(dirty), True)

        token = json.loads(json.dumps(data))
        token["idea"] = "Bearer ya29.secret-value-should-fail-scan"
        expect("secret value", secret_findings(token), True)

        data["stages"]["G0"]["status"] = "PASS"
        data["stages"]["G1"]["status"] = "BLOCKED"
        data["stages"]["G1"]["reason"] = "Stitch MCP not connected"
        data["current_stage"] = "G1"
        expect("G0 pass G1 blocked", workflow_errors(root, data, allow_mock=False), False)

        g3 = json.loads(json.dumps(data))
        g3["stages"]["G1"]["status"] = "PASS"
        g3["stages"]["G2"]["status"] = "PASS"
        g3["stages"]["G3"]["status"] = "PASS"
        g3["mcp_evidence"] = "none"
        expect("G3 without MCP", workflow_errors(root, g3, allow_mock=False), True)

        mocked = json.loads(json.dumps(g3))
        mocked["mcp_evidence"] = "mocked"
        mocked["stitch"]["tools_discovered"] = ["fake_generate"]
        mocked["stitch"]["screens"] = [{"id": "s1", "title": "Home", "status": "approved"}]
        expect("mocked G3 no allow", workflow_errors(root, mocked, allow_mock=False), True)
        expect("mocked G3 allow", workflow_errors(root, mocked, allow_mock=True), False)

        g4 = json.loads(json.dumps(mocked))
        g4["mcp_evidence"] = "discovered"
        g4["stages"]["G4"]["status"] = "PASS"
        shutil.copyfile(TEMPLATE_DESIGN, root / "DESIGN.md")
        expect("G4 skeleton omitted", workflow_errors(root, g4, allow_mock=True), True)

        (root / "DESIGN.md").write_text(
            "---\nversion: alpha\nname: LeafLog\ncolors:\n  primary: \"#2F6F4E\"\n---\n# DESIGN.md\n",
            encoding="utf-8",
        )
        expect("G4 tokens without headings", workflow_errors(root, g4, allow_mock=True), True)
        (root / "DESIGN.md").write_text(
            "---\nversion: alpha\nname: LeafLog\n"
            "colors:\n  primary: \"#2F6F4E\"\n"
            "typography:\n  body: Inter\n"
            "spacing:\n  md: 8\n"
            "rounded:\n  md: 8\n"
            "motion:\n  duration: 200ms\n"
            "components:\n  button: molecule\n"
            "---\n# DESIGN.md\n"
            "## Overview\n## Colors\n## Typography\n## Layout\n## Elevation & Depth\n"
            "## Shapes\n## Motion & Micro-interaction\n## Voice & Content Strategy\n"
            "## Components\n## Do's and Don'ts\n## Icons\n## States\n## Refresh\n"
            "## Accessibility\n## Gap policy\n## Approved screens\n",
            encoding="utf-8",
        )
        expect("G4 with tokens", workflow_errors(root, g4, allow_mock=True), False)

        prod = json.loads(json.dumps(g4))
        prod["stages"]["G5"]["status"] = "PASS"
        prod["decisions"]["g5"] = "PROCEED"
        prod["stages"]["G6"]["status"] = "PASS"
        prod["stages"]["G7"]["status"] = "IN_PROGRESS"
        expect("G7 without approval", workflow_errors(root, prod, allow_mock=True), True)
        prod["decisions"]["production_approved"] = True
        expect("G7 with approval still needs platform", workflow_errors(root, prod, allow_mock=True), True)
        prod["decisions"]["platform"] = "flutter"
        expect("G7 with approval", workflow_errors(root, prod, allow_mock=True), False)

        early = json.loads(json.dumps(data))
        early["stages"]["G6"]["status"] = "PASS"
        expect("G6 without G5 proceed", workflow_errors(root, early, allow_mock=False), True)

        proto = root / "design" / "prototype" / "index.html"
        proto.parent.mkdir(parents=True, exist_ok=True)
        proto.write_text("<html><body>hello</body></html>", encoding="utf-8")
        pdata = json.loads(json.dumps(data))
        pdata["artifacts"]["prototype"] = "design/prototype/index.html"
        expect("thin prototype", check_prototype(root, pdata), True)
        proto.write_text(
            "<html><head><style>:root{color-scheme:light dark} .dark{}"
            "@media (prefers-color-scheme:dark){}</style></head>"
            "<body><p>PROTOTYPE — simulated data</p><nav>Home</nav>"
            "<form><label>Email<input></label></form>"
            "<div role='status' class='skeleton'>Loading</div>"
            "<p>empty garden</p><p>error retry</p></body></html>",
            encoding="utf-8",
        )
        expect("full prototype", check_prototype(root, pdata), False)

        # resume: init twice fails
        if cmd_init(root, "leaflog", idea) == 0:
            failures.append("second init should fail")

        aidlc_root = root / "aidlc-product"
        if cmd_init(aidlc_root, "bound", idea, mode="aidlc") == 0:
            failures.append("aidlc init without workspace should fail")
        empty_ws = root / "aidlc-empty"
        (empty_ws / "aidlc").mkdir(parents=True)
        if cmd_init(empty_ws, "emptyws", idea, mode="aidlc") == 0:
            failures.append("aidlc init without aidlc-state.md should fail")
        if (empty_ws / ".startup-design" / "manifest.json").exists():
            failures.append("aidlc init without intent must not write a manifest")
        intent = (
            aidlc_root / "aidlc" / "spaces" / "default" / "intents" / "261127-leaflog"
        )
        (intent / "ideation" / "intent-capture").mkdir(parents=True)
        (intent / "inception" / "user-stories").mkdir(parents=True)
        (intent / "verification").mkdir(parents=True)
        (intent / "aidlc-state.md").write_text("# state\n", encoding="utf-8")
        statement = intent / "ideation" / "intent-capture" / "intent-statement.md"
        statement.write_text("# Intent\nWater plants on time.\n", encoding="utf-8")
        stories = intent / "inception" / "user-stories" / "stories.md"
        stories.write_text("# Stories\nAs a dweller I water plants.\n", encoding="utf-8")
        (intent / "verification" / "phase-check-ideation.md").write_text(
            "# phase-check-ideation\napproved\n", encoding="utf-8"
        )
        if cmd_init(aidlc_root, "bound", idea, mode="aidlc") != 0:
            failures.append("aidlc init with workspace should succeed")
        bound = load_or_die(aidlc_root)
        bind_errs = bind_aidlc(aidlc_root, bound, None)
        if bind_errs:
            failures.append(f"bind should succeed: {bind_errs}")
        else:
            dump_json(manifest_path(aidlc_root), bound)
            bound["stages"]["G0"]["status"] = "PASS"
            bound["stages"]["G0"]["evidence"] = list(bound["aidlc"]["consumed"])
            expect("aidlc G0 after bind", workflow_errors(aidlc_root, bound, allow_mock=False), False)
            if (aidlc_root / "PRODUCT_BRIEF.md").exists():
                failures.append("aidlc init must not write a competing PRODUCT_BRIEF.md")
            g7 = json.loads(json.dumps(bound))
            g7["stages"]["G5"]["status"] = "PASS"
            g7["decisions"]["g5"] = "PROCEED"
            g7["stages"]["G6"]["status"] = "PASS"
            g7["stages"]["G7"]["status"] = "IN_PROGRESS"
            expect("aidlc G7 forbidden", workflow_errors(aidlc_root, g7, allow_mock=False), True)
            g7["decisions"]["production_approved"] = True
            g7["stages"]["G7"]["status"] = "NOT_RUN"
            expect("aidlc production_approved forbidden", workflow_errors(aidlc_root, g7, allow_mock=False), True)
            g5ok = json.loads(json.dumps(bound))
            g5ok["stages"]["G5"]["status"] = "PASS"
            g5ok["decisions"]["g5"] = "PROCEED"
            rel, herr = write_aidlc_handoff(aidlc_root, g5ok)
            if herr or rel is None:
                failures.append(f"handoff should succeed: {herr}")
            else:
                handoff_path = aidlc_root / rel
                if not handoff_path.is_file() or "Construction" not in handoff_path.read_text(encoding="utf-8"):
                    failures.append("handoff file missing Construction notice")
                handoff_path.unlink()
            if any(p.parts[-1] == "AIDLC_HANDOFF.md" for p in intent.rglob("AIDLC_HANDOFF.md")):
                failures.append("handoff must not be written under aidlc/")
            nested_rel, nested_err = write_aidlc_handoff(intent, g5ok)
            if nested_err is None or nested_rel is not None:
                failures.append("handoff under an aidlc/ path must refuse")

            stolen = json.loads(json.dumps(bound))
            stolen["mode"] = "standalone"
            stolen["stages"]["G5"]["status"] = "PASS"
            stolen["decisions"]["g5"] = "PROCEED"
            stolen["decisions"]["production_approved"] = True
            expect(
                "bound aidlc object locks production even if mode says standalone",
                workflow_errors(aidlc_root, stolen, allow_mock=False),
                True,
            )
            missing_mode = json.loads(json.dumps(bound))
            missing_mode.pop("mode", None)
            expect("mode is required", validate_schema(missing_mode), True)

            empty = aidlc_root / "empty-bind"
            empty_intent = empty / "aidlc" / "spaces" / "default" / "intents" / "261127-x"
            empty_intent.mkdir(parents=True)
            (empty_intent / "aidlc-state.md").write_text("# state\n", encoding="utf-8")
            bind_rc = main(
                [
                    "--root", str(empty), "--init", "--slug", "nobrief",
                    "--idea", idea, "--mode", "aidlc", "--bind-aidlc",
                ]
            )
            if bind_rc == 0:
                failures.append("init --bind-aidlc without a brief should fail")
            if (empty / ".startup-design" / "manifest.json").exists():
                failures.append("failed bind must not leave a manifest")

            rec_root = root / "recmcp"
            if cmd_init(rec_root, "recmcp", idea) != 0:
                failures.append("record-mcp fixture init failed")
            else:
                rec_rc = main(["--root", str(rec_root), "--record-mcp"])
                if rec_rc == 0:
                    failures.append("record-mcp without kind should fail")
                rec = load_or_die(rec_root)
                if rec.get("mcp_evidence") != "none":
                    failures.append("record-mcp without kind must not default to discovered")
                rec_ok = main(
                    ["--root", str(rec_root), "--record-mcp", "--evidence", "mocked"]
                )
                if rec_ok != 0:
                    failures.append("record-mcp --evidence mocked should succeed")
                rec = load_or_die(rec_root)
                if rec.get("mcp_evidence") != "mocked":
                    failures.append("record-mcp --evidence mocked should set mocked")

            nested_rc = main(
                ["--root", str(intent), "--init", "--slug", "nested", "--idea", idea]
            )
            if nested_rc == 0:
                failures.append("--root inside aidlc/ should fail")
            if (intent / ".startup-design").exists() or (intent / "DESIGN.md").exists():
                failures.append("--root inside aidlc/ must not write files")

            outside_rc = main(
                [
                    "--root", str(aidlc_root), "--bind-aidlc",
                    "--intent", "/tmp/not-an-intent",
                ]
            )
            if outside_rc == 0:
                failures.append("--intent outside aidlc/spaces should fail")

            intent_b = (
                aidlc_root / "aidlc" / "spaces" / "default" / "intents" / "261127-other"
            )
            (intent_b / "ideation" / "intent-capture").mkdir(parents=True)
            (intent_b / "verification").mkdir(parents=True)
            (intent_b / "aidlc-state.md").write_text("# state\n", encoding="utf-8")
            (intent_b / "ideation" / "intent-capture" / "intent-statement.md").write_text(
                "# Other\nOther idea.\n", encoding="utf-8"
            )
            (intent_b / "verification" / "phase-check-ideation.md").write_text(
                "# phase-check-ideation\npresent\n", encoding="utf-8"
            )
            multi_rc = main(["--root", str(aidlc_root), "--bind-aidlc"])
            if multi_rc == 0:
                failures.append("multiple intents without --intent should fail")

            late = json.loads(json.dumps(bound))
            late["stages"]["G2"]["status"] = "PASS"
            late["stages"]["G3"]["status"] = "PASS"
            late["stages"]["G4"]["status"] = "PASS"
            late["stages"]["G5"]["status"] = "PASS"
            late["decisions"]["g5"] = "PROCEED"
            dump_json(manifest_path(aidlc_root), late)
            rebind_rc = main(
                [
                    "--root", str(aidlc_root), "--bind-aidlc",
                    "--intent", rel_to_root(aidlc_root, intent_b),
                ]
            )
            if rebind_rc == 0:
                failures.append("re-bind after G5 PASS without --rebind-aidlc should fail")
            still = load_or_die(aidlc_root)
            if still["aidlc"]["intent_dir"].endswith("261127-other"):
                failures.append("rejected re-bind must keep the previous intent")

            (intent / "inception" / "requirements-analysis").mkdir(parents=True)
            (intent / "inception" / "requirements-analysis" / "requirements.md").write_text(
                "# Requirements\nMust water plants.\n", encoding="utf-8"
            )
            (intent / "inception" / "user-stories" / "personas.md").write_text(
                "# Personas\nDweller.\n", encoding="utf-8"
            )
            prefer_errs = bind_aidlc(aidlc_root, bound, rel_to_root(aidlc_root, intent))
            if prefer_errs:
                failures.append(f"same-intent bind should succeed: {prefer_errs}")
            elif not bound["artifacts"]["product_brief"].endswith("requirements.md"):
                failures.append("product_brief must prefer requirements.md")
            elif "personas.md" not in " ".join(bound["aidlc"]["consumed"]):
                failures.append("consumed must include personas.md when present")

            approve_rc = main(
                ["--root", str(aidlc_root), "--approve-production", "--approved-by", "test"]
            )
            if approve_rc == 0:
                failures.append("CLI --approve-production in aidlc mode should fail")
            if load_or_die(aidlc_root)["decisions"]["production_approved"]:
                failures.append("refused approve-production must not set the flag")

            early_hand = main(["--root", str(aidlc_root), "--handoff-aidlc"])
            if early_hand == 0:
                failures.append("--handoff-aidlc before a legal G5 prototype should fail")
            if (aidlc_root / "design" / "AIDLC_HANDOFF.md").exists():
                failures.append("failed handoff must not leave AIDLC_HANDOFF.md")
            if load_or_die(aidlc_root).get("aidlc", {}).get("handoff"):
                failures.append("failed handoff must not record aidlc.handoff")

        if not SCHEMA_PATH.is_file() or not TEMPLATE_MANIFEST.is_file():
            failures.append("schema or template missing")

    if failures:
        print("check-startup-design selftest FAIL", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 2
    print("check-startup-design selftest PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--init", action="store_true")
    p.add_argument("--slug", default=None)
    p.add_argument("--idea", default=None)
    p.add_argument("--mode", choices=sorted(MODES), default="standalone")
    p.add_argument("--bind-aidlc", action="store_true")
    p.add_argument("--rebind-aidlc", action="store_true")
    p.add_argument("--intent", default=None, help="aidlc/spaces/<space>/intents/<id> when several exist")
    p.add_argument("--handoff-aidlc", action="store_true")
    p.add_argument("--g5", dest="g5", choices=["PROCEED", "ITERATE", "STOP"], default=None)
    p.add_argument("--set-stage", dest="set_stage", default=None)
    p.add_argument("--stage-status", dest="stage_status", default=None, choices=sorted(STAGE_STATUSES))
    p.add_argument("--reason", default=None)
    p.add_argument("--evidence", action="append", default=[])
    p.add_argument("--approve-production", action="store_true")
    p.add_argument("--approved-by", default=None)
    p.add_argument("--record-mcp", action="store_true")
    p.add_argument("--evidence-kind", dest="evidence_kind", choices=sorted(MCP_EVIDENCE), default=None)
    p.add_argument("--tools", default=None, help="comma-separated discovered tool names")
    p.add_argument("--check-prototype", action="store_true")
    p.add_argument("--require-production", action="store_true")
    p.add_argument("--allow-mock", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.root is None:
        print("ERROR: --root is required (or --selftest)", file=sys.stderr)
        return 2
    root = args.root.resolve()
    blocked = refuse_product_writes(root)
    if blocked:
        print(f"ERROR: {blocked}", file=sys.stderr)
        return 1

    if args.init:
        if not args.slug or not args.idea:
            print("ERROR: --init requires --slug and --idea", file=sys.stderr)
            return 2
        if args.mode == "aidlc" and args.bind_aidlc:
            path = manifest_path(root)
            if path.exists():
                print(f"manifest exists: {path}", file=sys.stderr, flush=True)
                return 1
            data = default_manifest(args.slug, args.idea, mode="aidlc")
            bind_errs = bind_aidlc(root, data, args.intent, rebind=args.rebind_aidlc)
            if bind_errs:
                return report(bind_errs)
            save_errs = save_manifest(path, data)
            if save_errs:
                return report(save_errs)
            copy_templates(root, skip_brief=True)
            print(f"wrote {path}", flush=True)
            print(f"bound {data['aidlc']['intent_dir']}", flush=True)
            return 0
        rc = cmd_init(root, args.slug, args.idea, mode=args.mode)
        if rc != 0 or not args.bind_aidlc:
            return rc
        data = load_or_die(root)
        bind_errs = bind_aidlc(root, data, args.intent, rebind=args.rebind_aidlc)
        if bind_errs:
            return report(bind_errs)
        save_errs = save_manifest(manifest_path(root), data)
        if save_errs:
            return report(save_errs)
        print(f"bound {data['aidlc']['intent_dir']}", flush=True)
        return 0

    try:
        data = load_or_die(root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    changed = False
    pending_handoff = False
    if args.g5:
        data.setdefault("decisions", {})["g5"] = args.g5
        changed = True
    if args.set_stage:
        if args.set_stage not in STAGES or not args.stage_status:
            print("ERROR: --set-stage G0-G10 requires --stage-status", file=sys.stderr)
            return 2
        set_stage(data, args.set_stage, args.stage_status, args.reason, args.evidence)
        changed = True
    if args.record_mcp:
        kind = args.evidence_kind
        if kind is None:
            kinds = [e for e in args.evidence if e in MCP_EVIDENCE]
            if len(kinds) == 1:
                kind = kinds[0]
        if kind is None:
            print(
                "ERROR: --record-mcp requires --evidence-kind none|discovered|mocked "
                "(do not default to discovered)",
                file=sys.stderr,
            )
            return 2
        data["mcp_evidence"] = kind
        if args.tools:
            data["stitch"]["tools_discovered"] = [t for t in args.tools.split(",") if t]
        changed = True
    if args.bind_aidlc:
        bind_errs = bind_aidlc(root, data, args.intent, rebind=args.rebind_aidlc)
        if bind_errs:
            return report(bind_errs)
        changed = True
    if args.handoff_aidlc:
        if manifest_mode(data) != "aidlc":
            print("ERROR: --handoff-aidlc requires mode=aidlc", file=sys.stderr)
            return 1
        if data["stages"]["G5"]["status"] != "PASS" or data["decisions"].get("g5") != "PROCEED":
            print("ERROR: handoff requires G5 PASS and decisions.g5=PROCEED", file=sys.stderr)
            return 1
        if aidlc_in_path(handoff_destination(root)):
            print("ERROR: handoff destination is under aidlc/; refuse to write", file=sys.stderr)
            return 1
        pending_handoff = True
        changed = True
    if args.approve_production:
        if manifest_mode(data) == "aidlc":
            print(
                "ERROR: aidlc mode refuses --approve-production; Construction stays with /aidlc "
                "(use --handoff-aidlc)",
                file=sys.stderr,
            )
            return 1
        if data["stages"]["G5"]["status"] != "PASS" or data["decisions"].get("g5") != "PROCEED":
            print("ERROR: production approval requires G5 PASS and decisions.g5=PROCEED", file=sys.stderr)
            return 1
        data["decisions"]["production_approved"] = True
        data["decisions"]["production_approved_by"] = args.approved_by or "human"
        data["decisions"]["production_approved_at"] = utc_now()
        changed = True
    if changed:
        proto_needed = (
            pending_handoff
            or args.check_prototype
            or data["stages"]["G5"]["status"] in {"PASS", "IN_PROGRESS"}
        )
        errors = judge(root, data, allow_mock=args.allow_mock, prototype=proto_needed)
        if errors:
            return report(errors)
        if pending_handoff:
            rel, herr = write_aidlc_handoff(root, data)
            if herr:
                return report([herr])
            data.setdefault("aidlc", {})
            if not isinstance(data["aidlc"], dict):
                data["aidlc"] = {}
            data["aidlc"]["handoff"] = rel
            data.setdefault("artifacts", {})["aidlc_handoff"] = rel
        save_errs = save_manifest(manifest_path(root), data)
        if save_errs:
            if pending_handoff:
                dest = handoff_destination(root)
                if dest.is_file():
                    dest.unlink()
            return report(save_errs)

    if args.status:
        print_status(data)

    proto = args.check_prototype or data["stages"]["G5"]["status"] in {"PASS", "IN_PROGRESS"}
    errors = judge(root, data, allow_mock=args.allow_mock, prototype=proto or args.check_prototype)
    if args.require_production and not data["decisions"]["production_approved"]:
        errors.append("production translation refused: production_approved is false")
    if args.check_prototype and data["stages"]["G5"]["status"] == "NOT_RUN":
        errors.extend(check_prototype(root, data))
    if args.status and not errors:
        return 0
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
