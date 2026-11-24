"""Planted violations for `validate_golden.py --selftest` and `eval_gate.py --selftest`.

Each golden mutation edits a fresh copy of assets/golden-scaffold/tests/golden and names the BLOCK rule the
validator must raise. `rehash` = recompute manifest sha256/counts after the edit, so only the planted rule fires.
"""

import json
from collections.abc import Callable
from pathlib import Path

FEATURE = "features/support-answer/golden.jsonl"
TOOLS = "tools/contract_cases.jsonl"
REDTEAM = "security/prompt_injection.yaml"


def _edit(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"selftest fixture drift: {old!r} not in {rel}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _append_case(root: Path, rel: str, case: dict) -> None:
    with (root / rel).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(case) + "\n")


def _first_case(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8").splitlines()[0])


def tamper_without_manifest(root: Path) -> None:
    _edit(root, FEATURE, "Where is my order", "Where is my parcel")


def unknown_key(root: Path) -> None:
    _edit(root, FEATURE, '"forbidden_tools": ["create_ticket"]', '"forbiden_tools": ["create_ticket"]')


def duplicate_id(root: Path) -> None:
    case = _first_case(root, FEATURE)
    case["tags"] = ["ci"]
    _append_case(root, FEATURE, case)


def real_email(root: Path) -> None:
    _edit(root, FEATURE, "Where is my order A-1001?", "Where is my order A-1001? I am jane.doe@gmail.com")


def card_number(root: Path) -> None:
    _edit(root, FEATURE, "Where is my order A-1001?", "Charge 4111 1111 1111 1111 for order A-1001")


def unmapped_tool(root: Path) -> None:
    path = root / REDTEAM
    text = path.read_text(encoding="utf-8")
    if "target_tools: [create_ticket]" not in text:
        raise AssertionError("selftest fixture drift: no create_ticket mapping")
    path.write_text(text.replace("target_tools: [create_ticket]", "target_tools: [get_order]"), encoding="utf-8")


def write_tool_without_audit(root: Path) -> None:
    lines = (root / TOOLS).read_text(encoding="utf-8").splitlines()
    kept = []
    for line in lines:
        case = json.loads(line)
        if case["case_kind"] == "happy":
            continue
        case["expected"]["audit_log_required"] = False
        kept.append(json.dumps(case))
    (root / TOOLS).write_text("\n".join(kept) + "\n", encoding="utf-8")
    _edit(root, "tools/dataset_manifest.yaml", "minimum_required_cases: 5", "minimum_required_cases: 4")


def unmanifested_file(root: Path) -> None:
    (root / "features/support-answer/edge_cases.jsonl").write_text(
        json.dumps(_first_case(root, FEATURE) | {"id": "support-answer-edge-901"}) + "\n", encoding="utf-8")


def missing_manifest(root: Path) -> None:
    (root / "features/new-feature").mkdir(parents=True)
    (root / "features/new-feature/golden.jsonl").write_text("{}\n", encoding="utf-8")


def critical_outside_ci(root: Path) -> None:
    _edit(root, "features/support-answer/dataset_manifest.yaml", "[smoke, ci, nightly, release]", "[smoke, nightly, release]")


def no_nightly(root: Path) -> None:
    _edit(root, "rag/dataset_manifest.yaml", "[smoke, ci, nightly, release]", "[smoke, ci, release]")


def rag_overlap(root: Path) -> None:
    _edit(root, "rag/support_kb_golden.csv", "kb-returns-v3,kb-org-b-pricing", "kb-org-b-pricing,kb-org-b-pricing")


def behaviour_change_patch_bump(root: Path) -> None:
    _edit(root, FEATURE, '"output": {"status": "shipped"}', '"output": {"status": "delivered"}')
    _edit(root, "features/support-answer/dataset_manifest.yaml", "version: 1.0.0", "version: 1.0.1")


def protected_canary_open(root: Path) -> None:
    _edit(root, "security/dataset_manifest.yaml", "class: heldout", "class: protected_canary")


def regression_name_mismatch(root: Path) -> None:
    src = root / "production_regressions/INC-2026-001.yaml"
    src.rename(root / "production_regressions/INC-2026-002.yaml")
    _edit(root, "production_regressions/dataset_manifest.yaml", "INC-2026-001.yaml", "INC-2026-002.yaml")


def unsanitized_regression(root: Path) -> None:
    _edit(root, "production_regressions/INC-2026-001.yaml", "payment_data_removed: true", "payment_data_removed: false")


def below_declared_minimum(root: Path) -> None:
    _edit(root, "rag/dataset_manifest.yaml", "minimum_required_cases: 3", "minimum_required_cases: 4")


def critical_asr_tolerance(root: Path) -> None:
    _edit(root, REDTEAM, "asr_budget: {runs: 5, max_successes: 0}", "asr_budget: {runs: 5, max_successes: 1}")


def unknown_attack_class_id(root: Path) -> None:
    _edit(root, REDTEAM, "ac_id: AC-01", "ac_id: AC-19")


def regression_case_deleted(root: Path) -> None:
    _edit(root, "production_regressions/INC-2026-001.yaml", "id: inc-2026-001-refund-promise-001",
          "id: inc-2026-001-refund-promise-002")
    _edit(root, "production_regressions/dataset_manifest.yaml", "version: 1.0.0", "version: 2.0.0")


def rag_outcome_not_in_enum(root: Path) -> None:
    _edit(root, "rag/support_kb_golden.csv", "org_a,NOT_FOUND,false", "org_a,not_found,false")


def rag_high_stakes_unflagged(root: Path) -> None:
    _edit(root, "rag/support_kb_golden.csv", "high-stakes,org_a,ANSWERED,true", "high-stakes,org_a,ANSWERED,false")


def rag_unknown_column(root: Path) -> None:
    _edit(root, "rag/support_kb_golden.csv", "expected_outcome,high_stakes", "expected_outcome,high_stake")


MANIFEST = "features/support-answer/dataset_manifest.yaml"


def synthetic_without_provenance(root: Path) -> None:
    _edit(root, MANIFEST, "source: expert_authored", "source: synthetic")


def synthetic_seeded_without_privacy_review(root: Path) -> None:
    _edit(root, MANIFEST, "source: expert_authored", "source: synthetic\nsynthetic_provenance:\n  generator: case-gen\n"
          "  generator_version: 1.2.0\n  seeded_from_real_data: true\n  reviewed_by: support-ai-team")

# name -> (mutate, expected BLOCK rule, rehash manifests after mutation, compare against the clean base tree)
MUTATIONS: dict[str, tuple[Callable[[Path], None], str, bool, bool]] = {
    "edit-without-manifest-update": (tamper_without_manifest, "GD004", False, False),
    "closed-schema-unknown-key": (unknown_key, "GD007", True, False),
    "duplicate-case-id": (duplicate_id, "GD008", True, False),
    "real-email-committed": (real_email, "GD013", True, False),
    "luhn-valid-card-committed": (card_number, "GD013", True, False),
    "tool-without-red-team-case": (unmapped_tool, "GD014", True, False),
    "write-tool-without-audit-case": (write_tool_without_audit, "GD015", True, False),
    "case-file-not-in-manifest": (unmanifested_file, "GD006", False, False),
    "directory-without-manifest": (missing_manifest, "GD001", False, False),
    "critical-cases-outside-ci": (critical_outside_ci, "GD012", False, False),
    "dataset-not-nightly": (no_nightly, "GD011", False, False),
    "rag-required-and-forbidden": (rag_overlap, "GD016", True, False),
    "expected-change-with-patch-bump": (behaviour_change_patch_bump, "GD019", True, True),
    "protected-canary-missing-controls": (protected_canary_open, "GD002", False, False),
    "regression-file-name-mismatch": (regression_name_mismatch, "GD017", True, False),
    "regression-not-sanitized": (unsanitized_regression, "GD007", True, False),
    "below-declared-minimum": (below_declared_minimum, "GD010", False, False),
    "critical-case-with-asr-tolerance": (critical_asr_tolerance, "GD007", True, False),
    "unknown-attack-class-id": (unknown_attack_class_id, "GD007", True, False),
    "incident-case-deleted": (regression_case_deleted, "GD021", True, True),
    "rag-outcome-not-in-enum": (rag_outcome_not_in_enum, "GD007", True, False),
    "rag-high-stakes-slice-unflagged": (rag_high_stakes_unflagged, "GD007", True, False),
    "rag-unknown-column": (rag_unknown_column, "GD007", False, False),
    "synthetic-without-provenance": (synthetic_without_provenance, "GD002", False, False),
    "synthetic-seeded-without-privacy-review": (synthetic_seeded_without_privacy_review, "GD002", False, False),
}
