"""Fixtures and planted violations for `eval_gate.py --selftest`.

The clean inputs are the shipped scaffold files (thresholds, R1 routing, current baseline), so the selftest
also proves the scaffold stays valid. Each mutation returns (baselines-by-kind, release flag) and names the
BLOCK rule expected; "!RULE" means RULE must NOT block, and "" means nothing may block.
"""

import json
from collections.abc import Callable
from pathlib import Path

import yaml

SCAFFOLD = Path(__file__).resolve().parent.parent / "assets" / "golden-scaffold" / "tests"
THRESHOLDS: dict = yaml.safe_load((SCAFFOLD / "eval" / "thresholds.yaml").read_text(encoding="utf-8"))
ROUTING: dict = yaml.safe_load((SCAFFOLD / "eval" / "r1-routing.yaml").read_text(encoding="utf-8"))
BASE_RESULT: dict = json.loads((SCAFFOLD / "golden" / "baselines" / "current.json").read_text(encoding="utf-8"))

Bases = dict[str, list[dict]]
Mutation = Callable[[dict, dict, dict], tuple[Bases, bool]]


def _case(res: dict, case_id: str) -> dict:
    return next(c for c in res["cases"] if c["case_id"] == case_id)


def _as_release(res: dict, base: dict) -> Bases:
    res["tier"] = base["tier"] = "R3"
    return {"current": [base], "release": [dict(base)]}


def blocker_failed(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    _case(res, "support-answer-cross-scope-003")["bucket"] = "FAIL"
    return {"current": [base]}, False


def critical_skipped(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    case = _case(res, "support-answer-order-status-001")
    case["case_class"], case["bucket"] = "critical", "SKIPPED"
    return {}, False


def regular_unscored(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    _case(res, "support-answer-escalation-005")["bucket"] = "DEPENDENCY_FAILURE"
    return {}, False


def no_thresholds(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["feature"] = "other-feature"
    return {}, False


def ratified_violation(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["metrics"]["faithfulness"] = 0.85
    return {}, False


def proposed_violation(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    spec = thr["features"]["support-answer"]
    for key in ("ratified_by", "ratified_on", "decision_ref"):
        del spec[key]
    spec["status"] = "proposed"
    res["metrics"]["faithfulness"] = 0.85
    return {}, False


def metric_missing(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    del res["metrics"]["faithfulness"]
    return {}, False


def baseline_dataset_mismatch(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    base["dataset_version"] = "0.9.0"
    return {"current": [base]}, False


def judge_mismatch(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["judge"] = {"model": "judge-model-b", "rubric_version": "3", "trials": 3}
    base["judge"] = {"model": "judge-model-a", "rubric_version": "3", "trials": 3}
    return {"current": [base]}, False


def drop_beyond_tolerance(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["metrics"]["answer_accuracy"] = 0.90          # still >= the 0.9 floor, but 3 pp below baseline
    return {"current": [base]}, False


def hallucination_increase(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    thr["features"]["support-answer"]["metrics"]["hallucination_rate"] = {"max": 0.05}
    res["metrics"]["hallucination_rate"] = 0.03       # within the max, but 3 pp worse (lower is better)
    return {"current": [base]}, False


def latency_over_ratio(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["latency_p95_ms"] = 3000                      # 1.25x
    return {"current": [base]}, False


def latency_tracked_only(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["latency_p95_ms"] = 2600                      # 1.08x: tracked, not blocking
    return {"current": [base]}, False


def anchor_drift_alerts_only(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    base["metrics"]["answer_accuracy"] = 1.0          # 7% relative drift from the anchor
    return {"anchor": [base]}, False


def release_missing_release_baseline(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    res["tier"] = base["tier"] = "R3"
    return {"current": [base]}, True


def release_on_r1(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    return {"current": [base], "release": [dict(base)]}, True


def release_dimension_unmapped(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    del thr["release_gates"]["idempotency"]
    return _as_release(res, base), True


def release_unmeasured_dimension(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    del res["metrics"]["recovery_success_rate"]
    return _as_release(res, base), True


def release_clean(thr: dict, res: dict, base: dict) -> tuple[Bases, bool]:
    return _as_release(res, base), True


GATE_MUTATIONS: dict[str, tuple[Mutation, str]] = {
    "hard-blocker-case-failed": (blocker_failed, "EG002"),
    "critical-case-skipped": (critical_skipped, "EG003"),
    "regular-case-unscored": (regular_unscored, "EG004"),
    "feature-without-thresholds": (no_thresholds, "EG005"),
    "ratified-threshold-violated": (ratified_violation, "EG006"),
    "proposed-threshold-is-advisory": (proposed_violation, "!EG006"),
    "ratified-metric-missing": (metric_missing, "EG007"),
    "baseline-dataset-version-mismatch": (baseline_dataset_mismatch, "EG008"),
    "baseline-judge-mismatch": (judge_mismatch, "EG008"),
    "drop-beyond-2pp": (drop_beyond_tolerance, "EG009"),
    "lower-is-better-metric-regressed": (hallucination_increase, "EG009"),
    "p95-latency-over-1.2x": (latency_over_ratio, "EG011"),
    "p95-latency-under-1.2x-tracked": (latency_tracked_only, "!EG011"),
    "anchor-drift-alerts-not-blocks": (anchor_drift_alerts_only, "!EG012"),
    "release-without-release-baseline": (release_missing_release_baseline, "EG013"),
    "release-on-r1-results": (release_on_r1, "EG014"),
    "release-dimension-unmapped": (release_dimension_unmapped, "EG013"),
    "release-dimension-unmeasured": (release_unmeasured_dimension, "EG007"),
    "release-clean": (release_clean, ""),
}
