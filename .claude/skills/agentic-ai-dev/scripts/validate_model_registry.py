#!/usr/bin/env python3
"""Validate approved-model registry files (MSR requirement sections §5, §6.1, §10-§12; home: reference/agentic-llm-routing.md).

Usage:
  validate_model_registry.py [--json] [--today YYYY-MM-DD] FILE...
  validate_model_registry.py --selftest

Exit codes: 0 every file valid, 1 at least one file invalid, 2 usage, IO, JSON or schema error.

Checks: the JSON Schema in ../assets/model-registry.schema.json, then deterministic cross-field rules
(no aliases or floating versions, lifecycle entry criteria, tier vs model class, provider training terms,
successors, same-tier equivalent or non-AI fallback for STANDARD/STRONG, no future-dated evidence).
Scope: structure and internal consistency only. A valid registry does not prove that an eval passed, that a
vendor review happened or that any owner approved anything.
Stdlib only. The schema engine is the ai-governance validator's fail-closed engine (imported, not copied).
"""

import argparse
import copy
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "assets" / "model-registry.schema.json"
EXAMPLE_PATH = SKILL_DIR / "assets" / "examples" / "model-registry.example.json"
ENGINE_PATH = SKILL_DIR.parent / "ai-governance" / "scripts" / "validate_governance_record.py"
ALIAS = re.compile(r"(^|[-_.@:/])(latest|default|preview|exp|experimental|auto)($|[-_.@:/])", re.IGNORECASE)
FLOATING = re.compile(r"^(\*|x)$|[\^~<>*]|\.x$|\|\|")
EVIDENCED_STATES = {"approved", "deployed", "deprecated"}
UNTIERED_CLASSES = {"embedding", "reranker", "judge"}
SCOPE_NOTE = "structure-and-consistency-only; does not attest eval results, vendor review or approval"


class UsageError(Exception):
    """Unusable input, schema or engine. Always exit 2."""


def load_engine():
    if not ENGINE_PATH.is_file():
        raise UsageError(f"schema engine not found: {ENGINE_PATH}")
    spec = importlib.util.spec_from_file_location("governance_schema_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cross_field_rules(reg: dict, today: date, errors: list) -> None:
    entries = reg["entries"]
    ids = [e["config_id"] for e in entries]
    by_id = {e["config_id"]: e for e in entries}
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(("$.entries", f"duplicate config_id {dup!r}"))
    for n, e in enumerate(entries):
        p = f"$.entries[{n}]({e['config_id']})"
        for field in ("model_id", "pinned_version"):
            if ALIAS.search(e[field]) or FLOATING.search(e[field]):
                errors.append((f"{p}.{field}", f"alias or floating version {e[field]!r}: pin an exact version or dated snapshot (§11.1)"))
        if e["model_class"] in UNTIERED_CLASSES and e["tier"] != "n.a.":
            errors.append((f"{p}.tier", f"{e['model_class']} configs are pinned, never tier-routed: tier must be 'n.a.' (§4.2)"))
        if e["model_class"] == "generation" and e["tier"] == "n.a.":
            errors.append((f"{p}.tier", "generation configs need a tier FAST/STANDARD/STRONG (§4.1)"))
        if e["state"] in EVIDENCED_STATES:
            if not e["capabilities_approved"]:
                errors.append((f"{p}.capabilities_approved", f"state {e['state']} needs at least one capability with a passing eval run (§5.2)"))
            if e["safety_eval"] is None:
                errors.append((f"{p}.safety_eval", f"state {e['state']} needs a safety/red-team run id (§5.2, §7.2)"))
        if e["data_terms"]["training_use"] == "allowed" and e["allowed_data_classes"] != "public":
            errors.append((f"{p}.data_terms.training_use", "provider may train on non-public data without contractual opt-out (§6.1)"))
        if e["state"] == "deprecated" and (e["deprecation_date"] is None or (e["successor"] is None and e["retirement_date"] is None)):
            errors.append((f"{p}.state", "deprecated needs deprecation_date and a successor or dated retirement (§5.2 migration plan)"))
        if e["state"] == "retired" and e["retirement_date"] is None:
            errors.append((f"{p}.retirement_date", "retired needs retirement_date"))
        if e["successor"] is not None:
            succ = by_id.get(e["successor"])
            if succ is None or succ["config_id"] == e["config_id"]:
                errors.append((f"{p}.successor", f"successor {e['successor']!r} is not another entry in this registry"))
            elif succ["state"] in {"retired", "rejected", "suspended"}:
                errors.append((f"{p}.successor", f"successor {e['successor']!r} is {succ['state']}"))
        dated = [(f"{p}.capabilities_approved[{k}].date", a["date"]) for k, a in enumerate(e["capabilities_approved"])]
        if e["safety_eval"] is not None:
            dated.append((f"{p}.safety_eval.date", e["safety_eval"]["date"]))
        for path, value in dated:
            if date.fromisoformat(value) > today:
                errors.append((path, f"evidence dated in the future ({value})"))
    # §12: each deployed STANDARD/STRONG capability has a same-tier equivalent or a documented non-AI fallback.
    live = defaultdict(set)
    for e in entries:
        if e["state"] == "deployed" and e["model_class"] == "generation" and e["tier"] in {"STANDARD", "STRONG"}:
            for a in e["capabilities_approved"]:
                live[(a["capability"], e["tier"])].add(e["config_id"])
    fallbacks = set(reg.get("non_ai_fallbacks", []))
    for (capability, tier), configs in sorted(live.items()):
        if len(configs) < 2 and capability not in fallbacks:
            errors.append(("$.entries", f"{capability}/{tier} has one deployed config ({sorted(configs)[0]}) and no "
                                        "approved same-tier equivalent or non_ai_fallbacks entry (§12)"))


def validate(reg, schema: dict, engine, today: date) -> list:
    errors: list = []
    engine.check(reg, schema, schema, "$", errors)
    if not errors:
        cross_field_rules(reg, today, errors)
    return errors


# ---------------------------------------------------------------- selftest
NEGATIVE_CASES = [
    ("alias model id", lambda r: r["entries"][0].update(model_id="example-generation-latest"), "alias or floating"),
    ("floating version", lambda r: r["entries"][0].update(pinned_version="2026.*"), "alias or floating"),
    ("preview version", lambda r: r["entries"][1].update(pinned_version="2026-10-01-preview"), "alias or floating"),
    ("deployed without safety eval", lambda r: r["entries"][0].update(safety_eval=None), "safety/red-team"),
    ("deployed without capability approval", lambda r: r["entries"][0].update(capabilities_approved=[]), "passing eval run"),
    ("duplicate config_id", lambda r: r["entries"][2].update(config_id=r["entries"][1]["config_id"]), "duplicate config_id"),
    ("embedding with a tier", lambda r: r["entries"][6].update(tier="FAST"), "never tier-routed"),
    ("generation without tier", lambda r: r["entries"][0].update(tier="n.a."), "need a tier"),
    ("training on confidential data", lambda r: r["entries"][0]["data_terms"].update(training_use="allowed"), "may train"),
    ("deprecated without plan", lambda r: r["entries"][4].update(successor=None), "deprecated needs"),
    ("unknown successor", lambda r: r["entries"][4].update(successor="no-such-config"), "is not another entry"),
    ("successor retired", lambda r: (r["entries"][0].update(state="retired", retirement_date="2026-11-20")), "is retired"),
    ("future-dated eval", lambda r: r["entries"][0]["capabilities_approved"][0].update(date="2099-01-01"), "future"),
    ("STANDARD without equivalent or fallback",
     lambda r: (r["entries"][2].update(state="suspended"), r.update(non_ai_fallbacks=[])), "invoice_extraction/STANDARD has one"),
    ("STRONG without equivalent or fallback", lambda r: r.update(non_ai_fallbacks=[]), "invoice_extraction/STRONG has one"),
    ("placeholder owner", lambda r: r["entries"][0].update(owner="<named person>"), "placeholder"),
    ("unknown state", lambda r: r["entries"][0].update(state="live"), "is not one of"),
    ("unknown property", lambda r: r["entries"][0].update(temperature=0), "not an allowed property"),
    ("missing required field", lambda r: r["entries"][0].pop("allowed_data_classes"), "is required"),
    ("unknown data class", lambda r: r["entries"][0].update(allowed_data_classes="secret"), "is not one of"),
]


def selftest(engine) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    today = date(2026, 11, 23)
    failures = 0

    def report(ok: bool, label: str) -> None:
        nonlocal failures
        failures += not ok
        sys.stdout.write(f"  {'ok  ' if ok else 'FAIL'} {label}\n")

    errs = validate(example, schema, engine, today)
    report(not errs, f"positive: example registry is valid {errs[:2] if errs else ''}")
    regulated = copy.deepcopy(example)
    regulated["entries"][0]["allowed_data_classes"] = "regulated"
    errs = validate(regulated, schema, engine, today)
    report(not errs, f"positive: a config declared for regulated data is valid {errs[:2] if errs else ''}")
    for label, mutate, expect in NEGATIVE_CASES:
        reg = copy.deepcopy(example)
        mutate(reg)
        errs = validate(reg, schema, engine, today)
        hit = any(expect in msg for _, msg in errs)
        report(hit, f"negative: {label} -> {'rejected' if hit else 'NOT rejected: ' + str(errs[:2])}")
    try:
        engine.check({}, {"type": "object", "if": {}}, {}, "$", [])
        report(False, "negative: unsupported schema keyword fails closed")
    except engine.SchemaError:
        report(True, "negative: unsupported schema keyword fails closed")
    sys.stdout.write(f"selftest {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))\n")
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------- CLI
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="reference date for future-dated evidence")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    try:
        engine = load_engine()
    except UsageError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    try:
        if args.selftest:
            return selftest(engine)
        if not args.files:
            raise UsageError("no registry files given")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        results = []
        for path in args.files:
            try:
                reg = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise UsageError(f"{path}: {type(exc).__name__}: {exc}") from exc
            errs = validate(reg, schema, engine, args.today)
            results.append({"file": str(path), "valid": not errs,
                            "errors": [{"path": p, "message": m} for p, m in errs]})
    except (UsageError, engine.SchemaError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if args.json:
        sys.stdout.write(json.dumps({"tool": "validate_model_registry", "scope": SCOPE_NOTE, "results": results}, indent=2) + "\n")
    else:
        for r in results:
            sys.stdout.write(f"{'VALID  ' if r['valid'] else 'INVALID'} {r['file']}\n")
            for e in r["errors"]:
                sys.stdout.write(f"  {e['path']}: {e['message']}\n")
    return 0 if all(r["valid"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
