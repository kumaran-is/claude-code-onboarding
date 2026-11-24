#!/usr/bin/env python3
"""Validate durable agent-memory records (MEM requirement sections §4, §5, §9-§11; home: reference/agent-memory-lifecycle.md).

Usage:
  validate_memory_item.py [--json] [--allow-examples] FILE...
  validate_memory_item.py --selftest
  validate_memory_item.py --print-schema

A FILE holds one MemoryItem object or {"memory_items": [...]}.
Exit codes: 0 every record valid, 1 at least one record invalid, 2 usage, IO, JSON or schema error.

Checks: the JSON Schema in ../assets/schemas/memory_item.schema.json, then deterministic cross-field rules
(untrusted writers, user writes only about self, agent proposals held for review, inferred or unknown
provenance never CURRENT on consequential items, untraceable claims, prohibited data classes, lineage
shape, compiler versioning, expiry, status/freshness consistency, deleted items carry no content).
Scope: structure and internal consistency only. A valid record does not prove isolation, erasure, freshness
or any runtime behaviour; those need the tests in reference/agent-memory-lifecycle.md.
Stdlib only. The schema engine is the ai-governance validator's fail-closed engine (imported, not copied).
"""

import argparse
import copy
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "assets" / "schemas" / "memory_item.schema.json"
EXAMPLE_PATH = SKILL_DIR / "assets" / "examples" / "memory_item.example.json"
ENGINE_PATH = SKILL_DIR.parent / "ai-governance" / "scripts" / "validate_governance_record.py"
UNTRUSTED = {"tool_output", "retrieved_document", "inbound_message", "upload", "web"}
NON_CONSEQUENTIAL = {"MODEL_INFERRED", "UNKNOWN_PROVENANCE"}
HELD = {"REVIEW_REQUIRED", "DELETED", "SUPERSEDED"}
# Pattern-based detector for §5.2 classes: a signal, not proof of absence (measured detectors run upstream, §5.3).
PROHIBITED = re.compile(
    r"(?i)\b(password|passwd|passcode|pin code|access code|api[_ -]?key|secret|token|bearer)\b\s*[:=]\s*\S+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\b(?:\d[ -]?){13,19}\b"
    r"|\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b"
)
CODE_FOR_PATH = {"$.org_id": "MISSING_ORG_ID", "$.source_refs": "NO_LINEAGE", "$.expires_at": "NO_EXPIRY"}
SCOPE_NOTE = "structure-and-consistency-only; does not prove isolation, erasure or runtime behaviour"


class UsageError(Exception):
    """Unusable input, schema or engine. Always exit 2."""


def load_engine():
    if not ENGINE_PATH.is_file():
        raise UsageError(f"schema engine not found: {ENGINE_PATH}")
    spec = importlib.util.spec_from_file_location("governance_schema_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _texts(item: dict):
    yield "$.content", item.get("content", "")
    for key, val in (item.get("structured_facts") or {}).items():
        yield f"$.structured_facts.{key}", json.dumps(val)
    for n, claim in enumerate(item.get("claims") or []):
        yield f"$.claims[{n}].claim_text", claim.get("claim_text", "")


def cross_field_rules(item: dict, errors: list) -> None:
    def err(path: str, code: str, msg: str) -> None:
        errors.append((path, code, msg))

    writer, status, prov = item["written_by"], item["status"], item["provenance_quality"]
    if writer["kind"] in UNTRUSTED:
        err("$.written_by.kind", "UNTRUSTED_WRITER", "untrusted content may only feed a reviewed pipeline, never write durable memory (§5.1, §10)")
    if writer["kind"] == "user_self" and (item["subject_type"] != "user" or item["subject_id"] != writer["id"]):
        err("$.written_by", "USER_WRITES_ABOUT_OTHERS", "users write memory only about themselves (§5.1, §10)")
    if writer["kind"] == "agent_runtime" and (prov != "MODEL_INFERRED" or status not in HELD):
        err("$.written_by", "AGENT_WRITE_NOT_HELD", "agent-written durable items are MODEL_INFERRED proposals held for review (§5.1)")
    if writer["kind"] == "compiler":
        if "compiler_version" not in item:
            err("$.compiler_version", "COMPILER_UNVERSIONED", "compiled items record the compiler version (§6.2)")
        if "model_name" in item and "prompt_version" not in item:
            err("$.prompt_version", "COMPILER_UNVERSIONED", "an LLM compile step records the prompt version (§6.2)")
    if item["consequential"] and prov in NON_CONSEQUENTIAL and status not in HELD:
        err("$.provenance_quality", "INFERRED_PROVENANCE_CONSEQUENTIAL",
            f"{prov} is never consequential: hold the item as REVIEW_REQUIRED (§4)")
    for n, claim in enumerate(item.get("claims") or []):
        if not claim["source_refs"] and claim.get("status") != "REVIEW_REQUIRED":
            err(f"$.claims[{n}]", "UNTRACEABLE_CLAIM", "a claim without sources is omitted or marked REVIEW_REQUIRED (§4)")
        if claim.get("source_versions") and len(claim["source_versions"]) != len(claim["source_refs"]):
            err(f"$.claims[{n}].source_versions", "LINEAGE_SHAPE", "one source version per source ref")
    if len(item["source_versions"]) != len(item["source_refs"]):
        err("$.source_versions", "LINEAGE_SHAPE", "one source version per source ref, same order (§4, §6.2)")
    for path, text in _texts(item):
        if PROHIBITED.search(text):
            err(path, "PROHIBITED_DATA_CLASS", "credentials, secrets, access codes and payment/bank data are never stored (§5.2)")
    created, generated, expires = _ts(item["created_at"]), _ts(item["generated_at"]), _ts(item["expires_at"])
    if generated < created:
        err("$.generated_at", "TIME_ORDER", "generated_at precedes created_at")
    if expires <= generated:
        err("$.expires_at", "NO_EXPIRY", "expires_at must be after generated_at (§9)")
    if "valid_until" in item and _ts(item["valid_until"]) > expires:
        err("$.valid_until", "TIME_ORDER", "valid_until is after expires_at")
    if status == "CURRENT" and item["freshness_state"] == "STALE":
        err("$.status", "STATUS_FRESHNESS_INCONSISTENT", "a STALE item is not CURRENT; label it STALE and use the canonical fallback (§8, §11)")
    if status == "DELETED":
        if item["content"] or item.get("structured_facts") or item.get("claims"):
            err("$.content", "DELETED_RETAINS_CONTENT", "erasure removes content; a tombstone keeps lineage only (§9)")
    elif not item["content"].strip():
        err("$.content", "EMPTY_CONTENT", "only a DELETED tombstone may have empty content")


def validate_item(item, schema: dict, engine) -> list:
    raw: list = []
    engine.check(item, schema, schema, "$", raw)
    errors = [(p, CODE_FOR_PATH.get(p, "SCHEMA"), m) for p, m in raw]
    if not errors:
        cross_field_rules(item, errors)
    return errors


def items_of(doc, schema: dict, engine, allow_examples: bool) -> tuple[list, list]:
    """Returns (items, file-level errors)."""
    if isinstance(doc, dict) and "memory_items" in doc:
        raw: list = []
        engine.check(doc, schema["$defs"]["file"], schema, "$", raw)
        errs = [(p, "SCHEMA", m) for p, m in raw]
        if not errs and doc.get("example") and not allow_examples:
            errs.append(("$.example", "EXAMPLE_RECORD", "example data is fictional; copy, replace every value and drop 'example'"))
        return (doc["memory_items"] if not raw else []), errs
    if isinstance(doc, dict):
        return [doc], []
    return [], [("$", "SCHEMA", "file must hold a MemoryItem object or {\"memory_items\": [...]}")]


def validate_doc(doc, schema: dict, engine, allow_examples: bool = False) -> list:
    items, errors = items_of(doc, schema, engine, allow_examples)
    out = [{"index": None, "pointer": p, "code": c, "message": m} for p, c, m in errors]
    for n, item in enumerate(items):
        if not isinstance(item, dict):
            out.append({"index": n, "pointer": "$", "code": "SCHEMA", "message": "item must be an object"})
            continue
        out += [{"index": n, "pointer": p, "code": c, "message": m} for p, c, m in validate_item(item, schema, engine)]
    return out


# ---------------------------------------------------------------- selftest
def _set(path: list, value):
    def mutate(item: dict) -> None:
        target = item
        for key in path[:-1]:
            target = target[key]
        if value is _DEL:
            target.pop(path[-1])
        else:
            target[path[-1]] = value
    return mutate


_DEL = object()
NEGATIVE_CASES = [  # (label, item index in example, mutation, expected code)
    ("missing org_id", 0, _set(["org_id"], _DEL), "MISSING_ORG_ID"),
    ("empty lineage", 0, _set(["source_refs"], []), "NO_LINEAGE"),
    ("working memory is not durable", 0, _set(["memory_type"], "working_session"), "SCHEMA"),
    ("no expiry", 0, _set(["expires_at"], _DEL), "NO_EXPIRY"),
    ("unknown property", 0, _set(["embedding"], [0.1]), "SCHEMA"),
    ("tool output writes memory", 0, _set(["written_by", "kind"], "tool_output"), "UNTRUSTED_WRITER"),
    ("retrieved document writes memory", 1, _set(["written_by", "kind"], "retrieved_document"), "UNTRUSTED_WRITER"),
    ("user writes about another user", 0, _set(["subject_id"], "user-2000"), "USER_WRITES_ABOUT_OTHERS"),
    ("agent writes CURRENT durable item", 0, _set(["written_by"], {"kind": "agent_runtime", "id": "planner"}), "AGENT_WRITE_NOT_HELD"),
    ("model-inferred consequential CURRENT", 1, _set(["provenance_quality"], "MODEL_INFERRED"), "INFERRED_PROVENANCE_CONSEQUENTIAL"),
    ("unknown provenance consequential CURRENT", 1, _set(["provenance_quality"], "UNKNOWN_PROVENANCE"), "INFERRED_PROVENANCE_CONSEQUENTIAL"),
    ("untraceable claim kept CURRENT", 1, _set(["claims", 0, "source_refs"], []), "UNTRACEABLE_CLAIM"),
    ("compiler without version", 1, _set(["compiler_version"], _DEL), "COMPILER_UNVERSIONED"),
    ("LLM compile without prompt version", 1, _set(["prompt_version"], _DEL), "COMPILER_UNVERSIONED"),
    ("source versions misaligned", 1, _set(["source_versions"], ["4"]), "LINEAGE_SHAPE"),
    ("password in content", 0, _set(["content"], "Login password: hunter22"), "PROHIBITED_DATA_CLASS"),
    ("api key in facts", 0, _set(["structured_facts"], {"note": "api_key=sk-live-abc123"}), "PROHIBITED_DATA_CLASS"),
    ("card number in claim", 1, _set(["claims", 1, "claim_text"], "Card 4111 1111 1111 1111 on file"), "PROHIBITED_DATA_CLASS"),
    ("expiry before generation", 0, _set(["expires_at"], "2026-11-19T00:00:00Z"), "NO_EXPIRY"),
    ("CURRENT but STALE", 0, _set(["freshness_state"], "STALE"), "STATUS_FRESHNESS_INCONSISTENT"),
    ("deleted tombstone keeps content", 0, _set(["status"], "DELETED"), "DELETED_RETAINS_CONTENT"),
    ("blank content on live item", 0, _set(["content"], "  "), "EMPTY_CONTENT"),
    ("naive timestamp", 0, _set(["created_at"], "2026-11-20T09:15:00"), "SCHEMA"),
]
POSITIVE_CASES = [  # mutations that must stay valid
    ("model-inferred held for review", 1, lambda i: i.update(provenance_quality="MODEL_INFERRED", status="REVIEW_REQUIRED")),
    ("untraceable claim held for review", 1, lambda i: i["claims"][0].update(source_refs=[], source_versions=[], status="REVIEW_REQUIRED")),
    ("agent proposal held for review", 0, lambda i: i.update(written_by={"kind": "agent_runtime", "id": "planner"},
                                                             provenance_quality="MODEL_INFERRED", status="REVIEW_REQUIRED")),
    ("deleted tombstone keeps lineage only", 0, lambda i: (i.update(status="DELETED", content=""), i.pop("structured_facts"))),
]


def selftest(engine) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    failures = 0

    def report(ok: bool, label: str) -> None:
        nonlocal failures
        failures += not ok
        sys.stdout.write(f"  {'ok  ' if ok else 'FAIL'} {label}\n")

    errs = validate_doc(example, schema, engine, allow_examples=True)
    report(not errs, f"positive: example file is valid {errs[:2] if errs else ''}")
    errs = validate_doc(example, schema, engine)
    report(any(e["code"] == "EXAMPLE_RECORD" for e in errs), "negative: example file rejected without --allow-examples")
    for label, idx, mutate in POSITIVE_CASES:
        item = copy.deepcopy(example["memory_items"][idx])
        mutate(item)
        errs = validate_item(item, schema, engine)
        report(not errs, f"positive: {label} {errs[:2] if errs else ''}")
    for label, idx, mutate, code in NEGATIVE_CASES:
        item = copy.deepcopy(example["memory_items"][idx])
        mutate(item)
        errs = validate_item(item, schema, engine)
        hit = any(c == code for _, c, _ in errs)
        report(hit, f"negative: {label} -> {code if hit else 'NOT rejected: ' + str(errs[:2])}")
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
    parser.add_argument("--allow-examples", action="store_true", help="accept files marked \"example\": true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--print-schema", action="store_true")
    args = parser.parse_args(argv)
    try:
        engine = load_engine()
    except UsageError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    try:
        if args.print_schema:
            sys.stdout.write(SCHEMA_PATH.read_text(encoding="utf-8"))
            return 0
        if args.selftest:
            return selftest(engine)
        if not args.files:
            raise UsageError("no memory record files given")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        results = []
        for path in args.files:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise UsageError(f"{path}: {type(exc).__name__}: {exc}") from exc
            errs = validate_doc(doc, schema, engine, args.allow_examples)
            count = len(doc["memory_items"]) if isinstance(doc, dict) and isinstance(doc.get("memory_items"), list) else 1
            results.append({"path": str(path), "records": count, "valid": not errs, "errors": errs})
    except (UsageError, engine.SchemaError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if args.json:
        invalid = sum(len({e["index"] for e in r["errors"]}) for r in results)
        sys.stdout.write(json.dumps({"tool": "validate_memory_item", "version": 1, "scope_note": SCOPE_NOTE, "files": results,
                                     "summary": {"files": len(results), "records": sum(r["records"] for r in results),
                                                 "invalid": invalid}}, indent=2) + "\n")
    else:
        for r in results:
            sys.stdout.write(f"{'VALID  ' if r['valid'] else 'INVALID'} {r['path']}\n")
            for e in r["errors"]:
                where = "" if e["index"] is None else f"[{e['index']}]"
                sys.stdout.write(f"  {where}{e['pointer']}: {e['code']}: {e['message']}\n")
    return 0 if all(r["valid"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
