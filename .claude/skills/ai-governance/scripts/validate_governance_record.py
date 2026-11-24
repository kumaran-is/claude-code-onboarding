#!/usr/bin/env python3
"""Validate AI governance records (JSON) against the ai-governance schemas plus deterministic cross-field rules.

Usage:
  validate_governance_record.py [--json] [--allow-examples] [--regressions-root DIR] FILE...
  validate_governance_record.py --selftest
  validate_governance_record.py --list-types

Exit codes: 0 every record valid, 1 at least one record invalid, 2 usage, IO, JSON or schema error.

Scope: structure and internal consistency only. A valid record does not prove that a control works,
that an owner accepted the role, or that any organisation adopted or approved anything.
Stdlib only. The schema engine implements the JSON Schema 2020-12 keywords listed in SUPPORTED and
fails closed (exit 2) on any other keyword, so a schema can never rely on an unchecked rule.
Reused API (keep stable): `check(value, schema, root, path, errors)` and `SchemaError` are imported by
agentic-ai-dev/scripts/validate_memory_item.py and validate_model_registry.py; run their --selftest after changing either.
"""

import argparse
import copy
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = SKILL_DIR / "assets" / "schemas"
EXAMPLE_DIR = SKILL_DIR / "assets" / "examples"
SUPPORTED = {
    "$schema", "$defs", "$ref", "title", "description", "type", "properties", "required", "additionalProperties",
    "enum", "const", "pattern", "minLength", "minimum", "maximum", "items", "minItems", "uniqueItems", "format", "oneOf",
}
PLACEHOLDER = re.compile(r"^\s*(tbd|tba|unassigned|unknown|n/?a|none|xxx+|\?+)\s*$|<[^<>]+>", re.IGNORECASE)
FLOATING_VERSION = re.compile(r"^(latest|\*|x)$|[\^~<>*]|\.x$|\|\|", re.IGNORECASE)
LEVELS = ["A0", "A1", "A2", "A3", "A4"]
SCOPE_NOTE = "structure-and-consistency-only; does not attest adoption, approval or control effectiveness"


class SchemaError(Exception):
    """The schema itself is unusable (unsupported keyword, bad $ref). Always exit 2."""


def load_schemas() -> dict[str, dict]:
    schemas = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schemas[path.name.removesuffix(".schema.json")] = json.loads(path.read_text(encoding="utf-8"))
    if not schemas:
        raise SchemaError(f"no schemas found in {SCHEMA_DIR}")
    return schemas


# ---------------------------------------------------------------- schema engine
TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _type_ok(value, expected: str) -> bool:
    if expected not in TYPE_CHECKS:
        raise SchemaError(f"unsupported type {expected!r}")
    return TYPE_CHECKS[expected](value)


def _format_ok(value: str, fmt: str) -> bool:
    try:
        if fmt == "date":
            date.fromisoformat(value)
        elif fmt == "date-time":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return False
        else:
            raise SchemaError(f"unsupported format {fmt!r}")
    except ValueError:
        return False
    return True


def check(value, schema: dict, root: dict, path: str, errors: list) -> None:
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported schema keyword(s) {sorted(unknown)} at {path}")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/") or ref.split("/")[-1] not in root.get("$defs", {}):
            raise SchemaError(f"unresolvable $ref {ref!r}")
        check(value, root["$defs"][ref.split("/")[-1]], root, path, errors)
    if "oneOf" in schema:
        passing = 0
        for option in schema["oneOf"]:
            trial: list = []
            check(value, option, root, path, trial)
            passing += not trial
        if passing != 1:
            errors.append((path, f"must match exactly one allowed shape (matched {passing})"))
            return
    if "const" in schema and value != schema["const"]:
        errors.append((path, f"must be {schema['const']!r}"))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, f"{value!r} is not one of {schema['enum']}"))
        return
    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append((path, f"must be of type {schema['type']}"))
        return
    if isinstance(value, str):
        if "minLength" in schema:
            if len(value.strip()) < schema["minLength"]:
                errors.append((path, f"must have at least {schema['minLength']} non-blank characters"))
            elif PLACEHOLDER.search(value):
                errors.append((path, f"placeholder value {value!r} must be replaced with a real value"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append((path, f"{value!r} does not match {schema['pattern']}"))
        if "format" in schema and not _format_ok(value, schema["format"]):
            errors.append((path, f"{value!r} is not a valid {schema['format']} (date-time needs a UTC offset)"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((path, f"must be >= {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append((path, f"must be <= {schema['maximum']}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append((path, f"must contain at least {schema['minItems']} item(s)"))
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append((path, "items must be unique"))
        if "items" in schema:
            for i, item in enumerate(value):
                check(item, schema["items"], root, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append((f"{path}.{key}", "is required"))
        props = schema.get("properties", {})
        for key, sub in value.items():
            if key in props:
                check(sub, props[key], root, f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append((f"{path}.{key}", "is not an allowed property"))


# ---------------------------------------------------------------- cross-field rules
def _d(value):
    return date.fromisoformat(value) if isinstance(value, str) else None


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None


def _need(rec: dict, keys: list[str], why: str, errors: list, prefix: str = "$") -> None:
    for key in keys:
        if rec.get(key) in (None, "", []):
            errors.append((f"{prefix}.{key}", f"is required because {why}"))


def rules_risk_assessment(r, e):
    if _d(r["next_reassessment"]) <= _d(r["assessed_on"]):
        e.append(("$.next_reassessment", "must be after assessed_on (periodic reassessment, s2.4)"))
    review = r["independent_review"]
    if r["risk_tier"] == "Critical" and not review.get("required"):
        e.append(("$.independent_review.required", "must be true for Critical risk (specialized independent review, s6.1)"))
    if r["approval_status"] == "approved":
        _need(r, ["approved_by"], "approval_status is approved", e)
        if review.get("required"):
            for key in ("reviewer", "completed_on", "report_ref"):
                if key not in review:
                    e.append((f"$.independent_review.{key}", "is required before approval when independent review is required"))
    factors = r["factors"]
    if r["risk_tier"] in ("High", "Critical") and factors["tenancy"] != "single_tenant":
        _need(r, ["tenant_isolation_validation_ref"], "systems above Medium risk must validate isolation (s8.1)", e)
    if factors["durable_memory"] or factors["fine_tuning"]:
        _need(r, ["lineage_manifest_ref"], "durable memory, embeddings or fine-tuning need a lineage manifest (s2.5)", e)
    acceptance = r.get("risk_acceptance")
    if acceptance and _d(acceptance["expires"]) <= _d(r["assessed_on"]):
        e.append(("$.risk_acceptance.expires", "must be after assessed_on (time-bound acceptance)"))


METRIC_FOR = {"A1": "recommendation_correctness", "A2": "correct_proposals", "A3": "task_success", "A4": "task_success"}
ROLES_FOR = {"A1": {"owner"}, "A2": {"owner"}, "A3": {"independent_risk"}, "A4": {"independent_assurance", "executive_risk"}}


def rules_autonomy_declaration(r, e):
    level, prev = LEVELS.index(r["declared_level"]), r.get("previous_level")
    promotion = prev is not None and level > LEVELS.index(prev)
    if promotion and level - LEVELS.index(prev) != 1:
        e.append(("$.declared_level", f"promotion must be one step at a time ({prev} -> {LEVELS[LEVELS.index(prev) + 1]}), s6.3"))
    if level >= 2 or promotion:
        _need(r, ["quantitative_evidence", "additional_criteria"], "quantitative gates are mandatory for A2+ and every promotion (s6.3)", e)
    q = r.get("quantitative_evidence")
    if q:
        ci = q["confidence_interval"]
        if not ci["lower"] <= q["success_rate"] <= ci["upper"] or ci["lower"] >= ci["upper"]:
            e.append(("$.quantitative_evidence.confidence_interval", "must satisfy lower <= success_rate <= upper and lower < upper"))
        if q["unauthorized_actions_observed"] != 0:
            e.append(("$.quantitative_evidence.unauthorized_actions_observed", "must be 0 to declare this level (s6.3)"))
        if q["unresolved_critical_incidents"] != 0:
            e.append(("$.quantitative_evidence.unresolved_critical_incidents", "must be 0 to declare this level (s6.3)"))
        if level >= 1 and q["success_metric"] != METRIC_FOR[r["declared_level"]]:
            e.append(("$.quantitative_evidence.success_metric", f"must be {METRIC_FOR[r['declared_level']]} for {r['declared_level']} (s6.3)"))
        if r["record_status"] == "final" and (q["thresholds_source"] != "risk-owner-approved" or "threshold_approved_by" not in q):
            e.append(("$.quantitative_evidence.thresholds_source", "final records need risk-owner-approved thresholds with threshold_approved_by; the s6.3 numbers are illustrative ADAPT defaults (reference/risk-autonomy-oversight.md s3)"))
    for name, crit in (r.get("additional_criteria") or {}).items():
        if crit["status"] != "met":
            e.append((f"$.additional_criteria.{name}.status", "must be met; reaching the task count alone never permits promotion (s6.3)"))
    have = {a["approval_role"] for a in r["approvals"]}
    if level >= 1 and not ROLES_FOR[r["declared_level"]] <= have:
        e.append(("$.approvals", f"{r['declared_level']} needs approval roles {sorted(ROLES_FOR[r['declared_level']])} (s6.3)"))


def rules_approval_record(r, e):
    requested, expires = _dt(r["requested_at"]), _dt(r["expires_at"])
    if expires <= requested:
        e.append(("$.expires_at", "must be after requested_at"))
    decision = r["decision"]
    if decision == "timed_out":
        if "decided_by" in r:
            e.append(("$.decided_by", "must be absent when the approval timed out"))
        if r.get("timeout_outcome") != r["timeout_policy"]:
            e.append(("$.timeout_outcome", "must equal timeout_policy; a timeout never auto-approves (s7.3)"))
    else:
        _need(r, ["decided_by", "decided_at"], f"decision is {decision}", e)
    decided = _dt(r.get("decided_at"))
    if decision in ("approve", "modify") and decided:
        if decided > expires:
            e.append(("$.decided_at", "approval after expires_at is a stale approval and is invalid (s7.1, s10.5)"))
        if _dt(r["authoritative_state"]["read_at"]) > decided:
            e.append(("$.authoritative_state.read_at", "state must be read before the decision"))
        if (r["proposed_action"]["reversibility"] == "irreversible" or r["policy_warnings"]) and r.get("risk_acknowledged") is not True:
            e.append(("$.risk_acknowledged", "must be true when approving an irreversible action or one with policy warnings (s7.2)"))
    if decision == "modify":
        if r.get("modified_action_digest") in (None, r["action_digest"]):
            e.append(("$.modified_action_digest", "is required and must differ from action_digest when the decision is modify"))
    if r["bulk"]:
        if len(r.get("bulk_items", [])) < 2:
            e.append(("$.bulk_items", "bulk approvals must list every bound action (no silent bulk approval, s7.2)"))
    elif "bulk_items" in r:
        e.append(("$.bulk_items", "must be absent when bulk is false"))


def rules_control_register_entry(r, e):
    tested = r["result"] != "Not tested"
    if tested:
        _need(r, ["last_tested", "latest_evidence_ref"], f"result is {r['result']}", e)
    elif r["effectiveness_status"] != "not_assessed":
        e.append(("$.effectiveness_status", "an untested control cannot be presumed effective (s10.5); use not_assessed"))
    if r["effectiveness_status"] == "effective" and r["result"] != "Pass":
        e.append(("$.effectiveness_status", "effective requires result Pass"))
    if r["result"] in ("Fail", "Partial") and not r["remediation"]:
        e.append(("$.remediation", "is required when result is Fail or Partial"))
    last = _d(r.get("last_tested"))
    if last and _d(r["next_review"]) < last:
        e.append(("$.next_review", "must not be before last_tested"))


SEEDED_BLOCK = {"blocked", "quarantined", "contained"}


def rules_control_evidence(r, e):
    if r["method"] == "seeded_unsafe_scenario":
        _need(r, ["scenario"], "method is seeded_unsafe_scenario (s10.5)", e)
        if r["expected_outcome"] not in SEEDED_BLOCK:
            e.append(("$.expected_outcome", "a seeded unsafe scenario must expect blocked, quarantined or contained (s10.5)"))
    if r["result"] in ("pass", "fail"):
        _need(r, ["command", "exit_code"], "an executed test records its command and own exit code", e)
        matched = r["observed_outcome"] == r["expected_outcome"]
        if r["result"] == "pass" and not matched:
            e.append(("$.result", "pass requires observed_outcome == expected_outcome"))
        if r["result"] == "fail" and matched:
            e.append(("$.result", "fail contradicts observed_outcome == expected_outcome"))
    else:
        if "exit_code" in r:
            e.append(("$.exit_code", f"must be absent when result is {r['result']} (nothing executed)"))
        if r["observed_outcome"] != "not_observed":
            e.append(("$.observed_outcome", f"must be not_observed when result is {r['result']}"))
    nc = r["negative_control"]
    if nc["performed"] and ("description" not in nc or "observed_failure" not in nc):
        e.append(("$.negative_control", "a performed negative control needs description and observed_failure"))


DIGEST_REQUIRED = {"model_weights", "adapter", "container_image", "training_dataset", "evaluation_dataset", "prompt_template", "mcp_server", "tool_package"}
MANAGED_OK = {"foundation_model", "judge_model", "embedding_model", "tokenizer"}
DIGEST_LEN = {"sha256": 64, "sha384": 96, "sha512": 128}


def rules_ai_bom(r, e):
    types = set()
    for i, c in enumerate(r["components"]):
        p, ctype = f"$.components[{i}]", c["component_type"]
        types.add(ctype)
        if FLOATING_VERSION.search(c["version"]):
            e.append((f"{p}.version", f"{c['version']!r} is not pinned (s9.2 version pinning)"))
        digest = c.get("digest")
        if digest and len(digest["value"]) != DIGEST_LEN[digest["algorithm"]]:
            e.append((f"{p}.digest.value", f"length does not match {digest['algorithm']}"))
        if ctype in DIGEST_REQUIRED and not digest:
            e.append((f"{p}.digest", f"{ctype} needs a cryptographic hash (s9.2)"))
        if ctype in MANAGED_OK and not digest and not ("vendor_model_id" in c and "visibility_limitations" in c):
            e.append((p, "managed model without weights needs vendor_model_id and visibility_limitations (s9.2)"))
    for needed in ("foundation_model", "prompt_template"):
        if needed not in types:
            e.append(("$.components", f"must include a {needed} component (s9.1)"))
    profile, lineage = r["system_profile"], r.get("lineage", {})
    if profile["fine_tunes"]:
        if not types & {"adapter", "model_weights"} or "training_dataset" not in types:
            e.append(("$.components", "fine-tuning systems must list adapter or weights and training datasets (s9.1)"))
        if "dataset_lineage_ref" not in lineage:
            e.append(("$.lineage.dataset_lineage_ref", "is required for fine-tuning systems (s9.3)"))
    if profile["durable_memory"]:
        for key in ("memory_lineage_ref", "source_to_derived_map_ref"):
            if key not in lineage:
                e.append((f"$.lineage.{key}", "is required for durable-memory systems (s8.4, s9.3)"))
    if (profile["fine_tunes"] or profile["durable_memory"]) and not r.get("deletion_propagation_tests"):
        e.append(("$.deletion_propagation_tests", "release gate: applicable deletion-propagation tests are required (s9.3)"))


NEVER_NA = {"business_owner_assigned", "technical_owner_assigned", "risk_classification_approved", "approved_model_provider",
            "model_prompt_versions_recorded", "next_review_scheduled"}


def rules_production_readiness(r, e):
    open_items = 0
    for section, items in r["sections"].items():
        for name, item in items.items():
            p = f"$.sections.{section}.{name}"
            if item["status"] == "done" and "evidence_ref" not in item:
                e.append((f"{p}.evidence_ref", "done needs evidence; a checked box is not evidence"))
            if item["status"] == "not_applicable":
                if name in NEVER_NA:
                    e.append((f"{p}.status", "cannot be not_applicable for any production AI system"))
                if "justification" not in item:
                    e.append((f"{p}.justification", "not_applicable needs a justification"))
            open_items += item["status"] == "not_done"
    if r["verdict"] == "READY" and open_items:
        e.append(("$.verdict", f"READY contradicts {open_items} not_done item(s)"))
    if _d(r["next_review"]) <= _d(r["assessed_on"]):
        e.append(("$.next_review", "must be after assessed_on"))


def rules_regulatory_register_row(r, e):
    if r["date_legal_status"] != "enacted" and r["treated_as_binding"]:
        e.append(("$.treated_as_binding", "a proposed, guidance-only or unverified date must not be treated as binding (s15.2)"))
    if r["compliance_status"] == "compliant":
        if not r["evidence_links"]:
            e.append(("$.evidence_links", "compliant needs evidence links"))
        if r["role"] == "undetermined":
            e.append(("$.role", "compliance cannot be claimed while the provider/deployer role is undetermined"))
    if _d(r["next_review"]) <= _d(r["last_verification"]):
        e.append(("$.next_review", "must be after last_verification"))


def rules_incident_record(r, e):
    contained = _dt(r.get("contained_at"))
    if contained and contained < _dt(r["detected_at"]):
        e.append(("$.contained_at", "must not be before detected_at"))
    if r["status"] != "open":
        _need(r, ["contained_at"], f"status is {r['status']}", e)
    if r["status"] in ("resolved", "closed"):
        _need(r, ["recovery_outcome", "root_cause", "corrective_actions", "preventive_test_cases"],
              "a resolved incident records root cause, corrective actions and preventive test cases (s13.3)", e)
    if r["category"] == "AI-TENANT" and not r["tenant_scope"]:
        e.append(("$.tenant_scope", "AI-TENANT incidents must name the affected tenant scope"))
    # Severity crosswalk (reference/supply-chain-eval-and-release.md s7.1): one bijection, stricter obligation wins.
    sev = r.get("security_severity")
    if sev is not None and sev != SEV_FOR[r["severity"]]:
        e.append(("$.security_severity", f"{sev} contradicts severity {r['severity']} (crosswalk: {r['severity']} = {SEV_FOR[r['severity']]})"))
    if r["category"] == "AI-TENANT" and not r["severity_factors"]["blocked_by_deterministic_control"] and r["severity"] != "S0":
        e.append(("$.severity", "an unblocked cross-tenant exposure is always S0 / SEV-1 (playbook s8.2: isolation breach never downgraded)"))
    if "I3" in r.get("incident_types", []) and not r["severity_factors"]["blocked_by_deterministic_control"] and r["severity"] != "S0":
        e.append(("$.severity", "an unblocked I3 data leakage starts at S0 / SEV-1 until scope is proven smaller (runbook s3, s8.3)"))
    rules_incident_runbook(r, e)


def rules_incident_runbook(r, e):
    """Runbook (IR requirements, ai-incident-response skill) s7 ladder logging, s11 recovery verification, s12 closure."""
    detected, finished = _dt(r["detected_at"]), r["status"] in ("resolved", "closed")
    verification = r.get("recovery_verification")
    for i, lever in enumerate(r.get("containment_levers", [])):
        p = f"$.containment_levers[{i}]"
        pulled, restored = _dt(lever["pulled_at"]), _dt(lever.get("restored_at"))
        if pulled < detected:
            e.append((p + ".pulled_at", "must not be before detected_at"))
        if lever["lever"] in ("tool_disable", "platform_kill_switch") and "authorized_by" not in lever:
            e.append((p + ".authorized_by", f"{lever['lever']} (rung 4-5) needs incident-commander authorization (runbook s5)"))
        if restored and "left_in_place" in lever:
            e.append((p, "a lever is either restored or left in place, not both"))
        if restored and restored < pulled:
            e.append((p + ".restored_at", "must not be before pulled_at"))
        if restored and (verification is None or any(c["result"] == "fail" for c in verification.values())):
            e.append((p + ".restored_at", "a rung is lowered only after recovery verification with no failed check (runbook s7, s11)"))
        if r["status"] == "closed" and not restored and "left_in_place" not in lever:
            e.append((p, "at closure every lever is restored or left in place with an owner and review date (runbook s12)"))
    if finished:
        _need(r, ["incident_types", "containment_levers", "recovery_verification"],
              "a resolved incident names its I1-I11 playbooks, the levers pulled and the s11 recovery verification (runbook s2, s7, s11)", e)
        if "containment_levers" in r and not r["containment_levers"]:
            e.append(("$.containment_levers", "a resolved incident records at least one lever pull (runbook s6 contain exit: lever recorded)"))
    case = r.get("regression_case")
    if verification is not None:
        for name, c in verification.items():
            p = f"$.recovery_verification.{name}"
            if c["result"] == "pass" and "evidence" not in c:
                e.append((p, "pass needs an evidence reference"))
            if c["result"] == "not_applicable" and "reason" not in c:
                e.append((p, "not_applicable needs a reason"))
            if finished and c["result"] == "fail":
                e.append((p, f"{r['status']} contradicts a failed recovery check (runbook s11)"))
        detector = case is not None and case["kind"] == "monitored_detector"
        if finished and verification["regression_fail_before_pass_after"]["result"] != "pass" and not detector:
            e.append(("$.recovery_verification.regression_fail_before_pass_after",
                      "must pass: the regression case fails on pre-fix and passes on post-fix code (runbook s11, s12)"))
    if r["status"] == "closed":
        _need(r, ["regression_case"], "an AI incident never closes without a regression case (runbook s12; eval-guide GD021)", e)
    if case is None:
        return
    if case["kind"] == "regression_file":
        _need(case, ["regression_incident_id", "pre_fix_run_id", "post_fix_run_id"], "regression_file", e, "$.regression_case")
        rid = case.get("regression_incident_id")
        name = case["ref"].replace("\\", "/").rsplit("/", 1)[-1]
        if "production_regressions/" not in case["ref"].replace("\\", "/") or name not in (f"{rid}.yaml", f"{rid}.yml"):
            e.append(("$.regression_case.ref", f"must be production_regressions/{rid}.yaml (eval-guide GD017 file naming)"))
        if case.get("pre_fix_run_id") is not None and case.get("pre_fix_run_id") == case.get("post_fix_run_id"):
            e.append(("$.regression_case.post_fix_run_id", "fail-before and pass-after need two different runs"))
        if case["ref"] not in r.get("preventive_test_cases", []):
            e.append(("$.regression_case.ref", "must also be listed in preventive_test_cases"))
    else:
        _need(case, ["reason", "signed_off_by"],
              "a monitored detector replaces a regression file only with a documented reason and owner sign-off (runbook s12)", e, "$.regression_case")


def check_regression_file(r, root: Path, e) -> None:
    """--regressions-root: a closed incident's regression file must exist and carry the same incident_id (GD017 naming)."""
    case = r.get("regression_case")
    if r["status"] != "closed" or not case or case["kind"] != "regression_file" or "regression_incident_id" not in case:
        return
    rid = case["regression_incident_id"]
    found = [p for p in (root / f"{rid}.yaml", root / f"{rid}.yml") if p.is_file()]
    if not found:
        e.append(("$.regression_case.ref", f"{rid}.yaml not found under {root}; the regression case must exist before closure"))
    elif not re.search(rf"^incident_id:\s*[\"']?{re.escape(rid)}[\"']?\s*$", found[0].read_text(encoding="utf-8"), re.MULTILINE):
        e.append(("$.regression_case.ref", f"{found[0].name} does not declare incident_id: {rid}"))


SEV_FOR = {"S0": "SEV-1", "S1": "SEV-2", "S2": "SEV-3", "S3": "SEV-4"}
EXERCISE_SCENARIOS = (
    "known_bad_model_output", "unauthorized_tool_access", "cross_tenant_retrieval", "stale_human_approval",
    "prohibited_sensitive_data_transfer", "duplicate_financial_mutation", "prompt_injection_in_retrieved_content",
    "invalid_artifact_manifest",
)


def rules_unsafe_release_exercise(r, e):
    listed = [s["scenario"] for s in r["scenarios"]]
    for scenario in EXERCISE_SCENARIOS:
        if listed.count(scenario) != 1:
            e.append(("$.scenarios", f"scenario {scenario} must appear exactly once (found {listed.count(scenario)}); all 8 s10.5 scenarios are required"))
    ids = [s["evidence_id"] for s in r["scenarios"]]
    if len(set(ids)) != len(ids):
        e.append(("$.scenarios", "each scenario needs its own control_evidence record (duplicate evidence_id)"))


def check_exercise_evidence(r, evidence: dict, e) -> None:
    """Aggregate s10.5 check: resolve every scenario of an exercise against control_evidence records supplied in the same run."""
    clean = 0
    for i, entry in enumerate(r["scenarios"]):
        p, ev = f"$.scenarios[{i}]", evidence.get(entry["evidence_id"])
        if ev is None:
            e.append((p, f"control_evidence {entry['evidence_id']!r} was not supplied (or is itself invalid) in this run; an exercise never validates without its evidence"))
            continue
        if ev.get("method") != "seeded_unsafe_scenario" or ev.get("scenario") != entry["scenario"]:
            e.append((p, f"evidence {entry['evidence_id']!r} is not a seeded_unsafe_scenario record for {entry['scenario']}"))
            continue
        executed_ok = ev["result"] == "pass" and ev["observed_outcome"] in SEEDED_BLOCK
        clean += executed_ok and not ev["mocked"]
        if r["verdict"] == "passed":
            if not executed_ok:
                e.append((p, f"{entry['scenario']} is untested or failed (result {ev['result']}, observed {ev['observed_outcome']}); verdict passed needs every scenario blocked, quarantined or contained (s10.5)"))
            elif ev["mocked"]:
                e.append((p, f"{entry['scenario']} evidence is mocked; mocked runs prove test logic, not the intended independent control"))
    if r["verdict"] == "failed" and clean == len(r["scenarios"]):
        e.append(("$.verdict", "failed contradicts evidence in which every scenario passed unmocked"))


def rules_kpi_definition(r, e):
    if "last_value" in r and r["last_measurement_date"] is None:
        e.append(("$.last_measurement_date", "is required when last_value is present"))
    if r.get("last_value") == 0 and r.get("counts_violations_or_blocks"):
        _need(r, ["independent_control_test_ref", "detection_coverage_ref"],
              "a zero count is not proof of effectiveness without independent testing and detection coverage (s17)", e)


RULES = {name.removeprefix("rules_"): fn for name, fn in globals().items() if name.startswith("rules_")}


def validate_record(record, schemas: dict, allow_examples: bool = False) -> "tuple[str | None, list]":
    if not isinstance(record, dict):
        return None, [("$", "record must be a JSON object")]
    rtype = record.get("record_type")
    if rtype not in schemas:
        return rtype, [("$.record_type", f"must be one of {sorted(schemas)}")]
    errors: list = []
    check(record, schemas[rtype], schemas[rtype], "$", errors)
    if record.get("record_status") == "example" and not allow_examples:
        errors.append(("$.record_status", "example records are fictional; copy, replace every value and set draft or final"))
    if not errors:
        RULES[rtype](record, errors)
    return rtype, errors


def validate_batch(records: list, schemas: dict, allow_examples: bool = False, regressions_root: "Path | None" = None) -> list:
    """Validate each record, then run cross-record checks (s10.5 exercise completeness; regression files) over the batch."""
    results = [validate_record(rec, schemas, allow_examples) for rec in records]
    if regressions_root is not None:
        for rec, (rtype, errs) in zip(records, results):
            if rtype == "incident_record" and not errs:
                check_regression_file(rec, regressions_root, errs)
    evidence: dict = {}
    for rec, (rtype, errs) in zip(records, results):
        if rtype == "control_evidence" and not errs:
            evidence.setdefault(rec["evidence_id"], []).append(rec)
    unique = {eid: recs[0] for eid, recs in evidence.items() if len(recs) == 1}
    for rec, (rtype, errs) in zip(records, results):
        if rtype == "unsafe_release_exercise" and not errs:
            for eid in sorted(set(evidence) - set(unique)):
                if any(s["evidence_id"] == eid for s in rec["scenarios"]):
                    errs.append(("$.scenarios", f"evidence_id {eid!r} is ambiguous: supplied by more than one control_evidence record"))
            check_exercise_evidence(rec, unique, errs)
    return results


# ---------------------------------------------------------------- selftest
FIXTURES = SKILL_DIR / "assets" / "fixtures" / "negative-cases.json"
DELETE = "__DELETE__"


def apply_changes(record: dict, changes: list) -> None:
    for path, value in changes:
        *parents, last = path.split(".")
        node = record
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        key = int(last) if isinstance(node, list) else last
        if value == DELETE:
            del node[key]
        else:
            node[key] = value


def selftest_exercise_batch(schemas: dict, examples: dict, report) -> None:
    """s10.5 aggregate: one positive control and negative controls that must fail."""
    if "unsafe_release_exercise" not in examples or "control_evidence" not in examples:
        report(False, "exercise batch: examples missing")
        return
    enum_ce = schemas["control_evidence"]["properties"]["scenario"]["enum"]
    enum_ex = schemas["unsafe_release_exercise"]["properties"]["scenarios"]["items"]["properties"]["scenario"]["enum"]
    report(list(EXERCISE_SCENARIOS) == enum_ce == enum_ex, "exercise batch: scenario list matches both schemas (no drift)")
    exercise = examples["unsafe_release_exercise"]
    evidence = []
    for entry in exercise["scenarios"]:
        ev = copy.deepcopy(examples["control_evidence"])
        ev.update(evidence_id=entry["evidence_id"], scenario=entry["scenario"], mocked=False, environment="staging")
        evidence.append(ev)

    def run(label: str, mutate, expect: "str | None") -> None:
        ex, evs = copy.deepcopy(exercise), copy.deepcopy(evidence)
        batch = mutate(ex, evs) or [ex] + evs
        errs = [m for _, errs in validate_batch(batch, schemas, allow_examples=True) for _, m in errs]
        if expect is None:
            report(not errs, f"positive: exercise batch / {label} {errs[:2] if errs else ''}")
        else:
            hit = any(expect in m for m in errs)
            report(hit, f"negative: exercise batch / {label} -> {'rejected' if hit else 'NOT rejected: ' + str(errs[:2])}")

    def not_run(ex, evs):
        evs[3].update(result="not_run", observed_outcome="not_observed")
        del evs[3]["exit_code"]

    def failed(ex, evs):
        evs[5].update(result="fail", observed_outcome="allowed", exit_code=1)

    def drop_scenario(ex, evs):
        del ex["scenarios"][6]
        del evs[6]

    run("8 scenarios, all executed and blocked", lambda ex, evs: None, None)
    def honest_failure(ex, evs):
        failed(ex, evs)
        ex["verdict"] = "failed"

    run("verdict failed with an honest failing scenario", honest_failure, None)
    run("one scenario missing from the exercise", drop_scenario, "at least 8 item(s)")
    run("one scenario not executed", not_run, "untested or failed")
    run("one scenario failed", failed, "untested or failed")
    run("exercise validated without its evidence", lambda ex, evs: [ex], "was not supplied")
    run("evidence for a different scenario", lambda ex, evs: evs[0].update(scenario="stale_human_approval"), "is not a seeded")
    run("mocked evidence behind verdict passed", lambda ex, evs: evs[2].update(mocked=True), "is mocked")
    run("verdict failed while every scenario passed", lambda ex, evs: ex.update(verdict="failed"), "failed contradicts")
    run("same evidence_id supplied twice", lambda ex, evs: [ex] + evs + [copy.deepcopy(evs[1])], "is ambiguous")


def selftest_regression_root(schemas: dict, examples: dict, report) -> None:
    """--regressions-root: positive control with the file present, negative controls missing / wrong incident_id."""
    import tempfile
    record = examples.get("incident_record")
    if record is None:
        report(False, "regression root: incident_record example missing")
        return
    rid = record["regression_case"]["regression_incident_id"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def run(label: str, content: "str | None", expect: "str | None") -> None:
            target = root / f"{rid}.yaml"
            if target.exists():
                target.unlink()
            if content is not None:
                target.write_text(content, encoding="utf-8")
            errs = [m for _, errs in validate_batch([copy.deepcopy(record)], schemas, True, root) for _, m in errs]
            if expect is None:
                report(not errs, f"positive: regression root / {label} {errs[:2] if errs else ''}")
            else:
                hit = any(expect in m for m in errs)
                report(hit, f"negative: regression root / {label} -> {'rejected' if hit else 'NOT rejected: ' + str(errs[:2])}")

        run("regression file present with matching incident_id", f"incident_id: {rid}\nseverity: P0\n", None)
        run("regression file missing", None, "not found under")
        run("regression file declares another incident_id", "incident_id: INC-1999-001\n", "does not declare incident_id")


def selftest() -> int:
    schemas = load_schemas()
    failures = 0

    def report(ok: bool, label: str) -> None:
        nonlocal failures
        failures += not ok
        sys.stdout.write(f"  {'ok  ' if ok else 'FAIL'} {label}\n")

    examples = {}
    for rtype in sorted(schemas):
        path = EXAMPLE_DIR / f"{rtype}.example.json"
        if not path.exists():
            report(False, f"example missing for {rtype}")
            continue
        examples[rtype] = json.loads(path.read_text(encoding="utf-8"))
        _, errs = validate_record(examples[rtype], schemas, allow_examples=True)
        report(not errs, f"positive: {rtype} example is valid {errs[:2] if errs else ''}")
        _, errs = validate_record(examples[rtype], schemas)
        report(any("example records" in m for _, m in errs), f"negative: {rtype} example rejected without --allow-examples")
    covered = set()
    for case in json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]:
        rtype = case["record_type"]
        if rtype not in examples:
            continue
        record = copy.deepcopy(examples[rtype])
        apply_changes(record, case["changes"])
        _, errs = validate_record(record, schemas, allow_examples=True)
        if case["expect"] is None:                                   # positive variant: must validate clean
            report(not errs, f"{case['label']} ({rtype}) {errs[:2] if errs else ''}")
            continue
        hit = any(case["expect"] in m for _, m in errs)
        covered.add(rtype)
        report(hit, f"negative: {rtype} / {case['label']} -> {'rejected' if hit else 'NOT rejected: ' + str(errs[:2])}")
    report(covered == set(schemas), f"every record type has negative fixtures ({len(covered)}/{len(schemas)})")
    selftest_exercise_batch(schemas, examples, report)
    selftest_regression_root(schemas, examples, report)
    try:
        check({}, {"type": "object", "if": {}}, {}, "$", [])
        report(False, "negative: unsupported schema keyword fails closed")
    except SchemaError:
        report(True, "negative: unsupported schema keyword fails closed")
    sys.stdout.write(f"selftest {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))\n")
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------- CLI
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--allow-examples", action="store_true", help="accept record_status example (fixtures only)")
    parser.add_argument("--regressions-root", type=Path, help="production_regressions/ directory: a closed incident's "
                        "regression file must exist there and declare the same incident_id")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--list-types", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        schemas = load_schemas()
        if args.list_types:
            sys.stdout.write("\n".join(sorted(schemas)) + "\n")
            return 0
        if not args.files:
            parser.error("give at least one FILE, --selftest or --list-types")
        records = []
        for path in args.files:
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                sys.stderr.write(f"ERROR {path}: {exc}\n")
                return 2
        results = [{"file": str(path), "record_type": rtype, "valid": not errs,
                    "errors": [{"path": p, "message": m} for p, m in errs]}
                   for path, (rtype, errs) in zip(args.files, validate_batch(records, schemas, args.allow_examples, args.regressions_root))]
    except SchemaError as exc:
        sys.stderr.write(f"SCHEMA ERROR: {exc}\n")
        return 2
    invalid = sum(not r["valid"] for r in results)
    if args.json:
        summary = {"files": len(results), "valid": len(results) - invalid, "invalid": invalid, "scope": SCOPE_NOTE}
        sys.stdout.write(json.dumps({"tool": "validate_governance_record", "results": results, "summary": summary}, indent=2) + "\n")
    else:
        for r in results:
            sys.stdout.write(f"{'VALID  ' if r['valid'] else 'INVALID'} {r['file']} ({r['record_type']})\n")
            for err in r["errors"]:
                sys.stdout.write(f"    {err['path']}: {err['message']}\n")
        sys.stdout.write(f"{len(results) - invalid} valid, {invalid} invalid ({SCOPE_NOTE})\n")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
