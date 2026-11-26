#!/usr/bin/env python3
"""Startup design-to-code workflow gate.

Validates `.startup-design/manifest.json`, secret-scans it, enforces G0–G10
dependencies, and checks the interactive prototype contract.

Usage:
  check-startup-design.py --selftest
  check-startup-design.py --root DIR
  check-startup-design.py --root DIR --status
  check-startup-design.py --root DIR --init --slug SLUG --idea TEXT
  check-startup-design.py --root DIR --set-stage G0 --status PASS [--reason TEXT] [--evidence PATH]
  check-startup-design.py --root DIR --approve-production --approved-by NAME
  check-startup-design.py --root DIR --record-mcp --evidence none|discovered|mocked [--tools t1,t2]
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

SECRET_KEYS = re.compile(
    r"(?i)(api[_-]?key|secret|password|access_token|id_token|refresh_token|"
    r"authorization|auth_header|x-goog-api-key|stitch[_-]?key|private_key)$"
)
SECRET_VALUES = re.compile(
    r"(?i)^(sk-|rk_|AIza|ya29\.|ghp_|github_pat_|xox[baprs]-|Bearer\s+\S{8,})"
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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


def default_manifest(slug: str, idea: str) -> dict:
    data = load_json(TEMPLATE_MANIFEST)
    data["product_slug"] = slug
    data["idea"] = idea
    return data


def validate_schema(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest is not an object"]
    required = [
        "version", "idea", "product_slug", "current_stage", "stages",
        "artifacts", "decisions", "stitch", "mcp_evidence",
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
    elif isinstance(artifacts, dict) and any(not isinstance(v, str) for v in artifacts.values()):
        errors.append("artifact paths must be strings")
    extra = set(data) - {
        "version", "idea", "product_slug", "current_stage", "stages",
        "artifacts", "decisions", "stitch", "mcp_evidence",
    }
    if extra:
        errors.append(f"unknown keys: {sorted(extra)}")
    return errors


def status_of(data: dict, stage: str) -> str:
    return data["stages"][stage]["status"]


def design_omits_tokens(root: Path, data: dict) -> bool:
    rel = (data.get("artifacts") or {}).get("design_md", "DESIGN.md")
    path = root / rel
    if not path.is_file():
        return True
    text = path.read_text(encoding="utf-8")
    fm = text.split("---", 2)
    block = fm[1] if text.startswith("---") and len(fm) >= 3 else ""
    if "status: unapproved" in block:
        return True
    if not OMITTED_RE.search(text):
        return False
    return any(
        re.search(rf"^omitted:[\s\S]*?- {fam}\b", block, re.M)
        or re.search(rf"^omitted:.*\b{fam}\b", block, re.M)
        for fam in TOKEN_FAMILIES
    )


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
    if st["G4"] == "PASS" and design_omits_tokens(root, data):
        errors.append("G4 PASS requires DESIGN.md token families (omitted/unapproved skeleton is not enough)")
    if st["G5"] in {"PASS", "IN_PROGRESS"} and st["G4"] != "PASS":
        errors.append("G5 requires G4 PASS")
    if st["G5"] == "PASS" and g5 not in {"PROCEED", "ITERATE", "STOP"}:
        errors.append("G5 PASS requires decisions.g5")
    if st["G6"] in {"PASS", "IN_PROGRESS"} and not (st["G5"] == "PASS" and g5 == "PROCEED"):
        errors.append("G6 requires G5 PASS and decisions.g5=PROCEED")
    for later in ["G7", "G8", "G9", "G10"]:
        if st[later] != "NOT_RUN":
            if not approved:
                errors.append(f"{later} requires decisions.production_approved")
            if st["G6"] != "PASS":
                errors.append(f"{later} requires G6 PASS")
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
    path = root / rel
    if not path.is_file():
        return [f"prototype missing: {rel}"]
    text = path.read_text(encoding="utf-8")
    missing = []
    for _key, rx, label in PROTOTYPE_MARKERS:
        if not rx.search(text):
            missing.append(f"prototype missing {label}")
    return missing


def print_status(data: dict) -> None:
    current = data["current_stage"]
    st = data["stages"][current]["status"]
    nxt = None
    for g in STAGES:
        if data["stages"][g]["status"] in {"NOT_RUN", "IN_PROGRESS", "FAIL", "BLOCKED"}:
            nxt = g
            break
    blocked = [
        f"{g}: {data['stages'][g].get('reason') or data['stages'][g]['status']}"
        for g in STAGES if data["stages"][g]["status"] == "BLOCKED"
    ]
    print("## Startup design")
    print(f"Stage: {current} {st}")
    print(f"Next: {nxt or 'complete'}")
    print(f"Blocked: {'; '.join(blocked) if blocked else 'none'}")
    arts = data.get("artifacts") or {}
    print("Artifacts: " + ", ".join(f"{k}={v}" for k, v in arts.items()))
    print(f"MCP: {data.get('mcp_evidence')}")
    print("Production approved: " + ("yes" if data["decisions"]["production_approved"] else "no"))


def copy_templates(root: Path) -> None:
    mapping = {
        TEMPLATE_BRIEF: root / "PRODUCT_BRIEF.md",
        TEMPLATE_INVENTORY: root / "docs" / "screen-inventory.md",
        TEMPLATE_DESIGN: root / "DESIGN.md",
    }
    for src, dest in mapping.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(src, dest)


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


def cmd_init(root: Path, slug: str, idea: str) -> int:
    path = manifest_path(root)
    if path.exists():
        print(f"manifest exists: {path}", file=sys.stderr, flush=True)
        return 1
    data = default_manifest(slug, idea)
    dump_json(path, data)
    copy_templates(root)
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
        expect("G4 with tokens", workflow_errors(root, g4, allow_mock=True), False)

        prod = json.loads(json.dumps(g4))
        prod["stages"]["G5"]["status"] = "PASS"
        prod["decisions"]["g5"] = "PROCEED"
        prod["stages"]["G6"]["status"] = "PASS"
        prod["stages"]["G7"]["status"] = "IN_PROGRESS"
        expect("G7 without approval", workflow_errors(root, prod, allow_mock=True), True)
        prod["decisions"]["production_approved"] = True
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

    if args.init:
        if not args.slug or not args.idea:
            print("ERROR: --init requires --slug and --idea", file=sys.stderr)
            return 2
        return cmd_init(root, args.slug, args.idea)

    try:
        data = load_or_die(root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    changed = False
    if args.set_stage:
        if args.set_stage not in STAGES or not args.stage_status:
            print("ERROR: --set-stage G0-G10 requires --stage-status", file=sys.stderr)
            return 2
        set_stage(data, args.set_stage, args.stage_status, args.reason, args.evidence)
        changed = True
    if args.record_mcp:
        kind = args.evidence_kind or "discovered"
        data["mcp_evidence"] = kind
        if args.tools:
            data["stitch"]["tools_discovered"] = [t for t in args.tools.split(",") if t]
        changed = True
    if args.approve_production:
        if data["stages"]["G5"]["status"] != "PASS" or data["decisions"].get("g5") != "PROCEED":
            print("ERROR: production approval requires G5 PASS and decisions.g5=PROCEED", file=sys.stderr)
            return 1
        data["decisions"]["production_approved"] = True
        data["decisions"]["production_approved_by"] = args.approved_by or "human"
        data["decisions"]["production_approved_at"] = utc_now()
        changed = True
    if changed:
        errors = judge(root, data, allow_mock=args.allow_mock, prototype=False)
        if errors:
            return report(errors)
        dump_json(manifest_path(root), data)

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
