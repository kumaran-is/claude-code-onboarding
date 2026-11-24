# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0", "pyyaml==6.0.4"]
# [tool.uv]
# exclude-newer = "2026-11-21T00:00:00Z"
# ///
"""Deterministic eval gate: per-feature thresholds, hard blockers, critical sub-thresholds, triple baseline,
release gates, and R1 path routing. Inputs are validated against ../assets/schemas first (fail closed).

check: every results file is one feature's run (eval_result.schema.json); baselines are stored results of
       the same shape. Only `status: ratified` thresholds gate; `proposed` ones are advisories. A judge or
       aggregate score never clears a hard blocker or a critical-class case.
route: maps changed paths to R1 suites (union of matching rules + `always`); refuses a routing file that
       sends a never-on-PR suite into R1.

Exit codes: 0 pass, 1 gate failed, 2 usage or invalid input.
Run:  uv run --script eval_gate.py check --thresholds tests/eval/thresholds.yaml --results r1.json [...]
          [--baseline-current b.json ...] [--baseline-release b.json ...] [--baseline-anchor b.json ...]
          [--release --approved-dataset NAME@VERSION ...] [--json report.json]
      uv run --script eval_gate.py route --routing tests/eval/r1-routing.yaml --changed-files changed.txt|-
      uv run --script eval_gate.py --selftest
"""

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TOOL = "eval_gate"
VERSION = "1.0.0"
SCHEMAS = Path(__file__).resolve().parent.parent / "assets" / "schemas"
PROTECTED = {"critical", "isolation", "compliance", "tool_auth", "security"}
RELEASE_DIMENSIONS = ["correctness", "groundedness", "hallucination", "sensitive_data_leakage", "tool_authorization",
                      "agent_task_success", "idempotency", "recovery", "safety", "latency", "cost"]


class InputError(Exception):
    """Unreadable or schema-invalid gate input (exit 2)."""


@dataclass
class Finding:
    rule: str
    severity: str
    feature: str
    message: str


def load(path: Path, schema: str) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise InputError(f"{path}: {exc}") from exc
    validator = Draft202012Validator(json.loads((SCHEMAS / schema).read_text()), format_checker=FormatChecker())
    errors = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator.iter_errors(data)]
    if errors:
        raise InputError(f"{path} fails {schema}: " + "; ".join(errors[:5]))
    return data


def by_feature(runs: list[dict], label: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for run in runs:
        if run["feature"] in out:
            raise InputError(f"two {label} files for feature '{run['feature']}'")
        out[run["feature"]] = run
    return out


def run_key(run: dict) -> tuple:
    judge = run.get("judge") or {}
    return run["dataset_name"], run["dataset_version"], run["tier"], judge.get("model"), judge.get("rubric_version")


def worse_by(metric: str, bound: dict, current: float, base: float) -> float:
    """How much `current` is worse than `base`; direction comes from the threshold bound."""
    return base - current if "min" in bound else current - base


def check(thresholds: dict, results: list[dict], baselines: dict[str, list[dict]], release: bool,
          approved: set[str]) -> list[Finding]:
    out: list[Finding] = []
    policy = thresholds["baseline_policy"]
    runs = by_feature(results, "results")
    bases = {kind: by_feature(files, kind) for kind, files in baselines.items()}
    for feat, run in sorted(runs.items()):
        def add(rule: str, sev: str, msg: str, f: str = feat) -> None:
            out.append(Finding(rule, sev, f, msg))
        for case in run["cases"]:
            if "blocker" in case and case["bucket"] != "PASS":
                add("EG002", "BLOCK", f"hard blocker {case['blocker']}: case {case['case_id']} is {case['bucket']}")
            elif case["case_class"] in PROTECTED and case["bucket"] != "PASS":
                add("EG003", "BLOCK", f"{case['case_class']} case {case['case_id']} is {case['bucket']} (100% sub-threshold)")
        unscored = [c["case_id"] for c in run["cases"] if c["bucket"] in ("UNSCORED", "DEPENDENCY_FAILURE", "SKIPPED")]
        if unscored:
            add("EG004", "BLOCK", f"{len(unscored)} case(s) not scored, the run is incomplete: {unscored[:5]}")
        spec = thresholds["features"].get(feat)
        if spec is None:
            add("EG005", "BLOCK", "no thresholds entry for this feature (fail closed)")
            continue
        ratified = spec["status"] == "ratified"
        for metric, bound in spec["metrics"].items():
            value = run["metrics"].get(metric)
            if value is None:
                add("EG007", "BLOCK" if ratified else "REVIEW", f"metric '{metric}' missing from results")
                continue
            low, high = bound.get("min"), bound.get("max")
            if (low is not None and value < low) or (high is not None and value > high):
                add("EG006", "BLOCK" if ratified else "ADVISORY",
                    f"{metric}={value} outside {bound}{'' if ratified else ' (proposed threshold: not a merge gate until ratified)'}")
        for kind in ("current", "release", "anchor"):
            base = bases.get(kind, {}).get(feat)
            if base is None:
                if release and kind in ("current", "release"):
                    add("EG013", "BLOCK", f"release gate needs a {kind} baseline for this feature")
                continue
            if run_key(base) != run_key(run):
                add("EG008", "BLOCK", f"{kind} baseline key {run_key(base)} != run {run_key(run)}: record a matching baseline")
                continue
            for metric, bound in spec["metrics"].items():
                if metric not in run["metrics"] or metric not in base["metrics"]:
                    continue
                worse = worse_by(metric, bound, run["metrics"][metric], base["metrics"][metric])
                if kind == "anchor":
                    ref = abs(base["metrics"][metric]) or 1.0
                    if worse / ref * 100 > policy["anchor_alert_drop_pct"]:
                        add("EG012", "REVIEW", f"{metric} drifted {worse / ref * 100:.1f}% from the anchor baseline (alert)")
                elif worse > policy["max_drop"] + 1e-12:
                    add("EG009", "BLOCK", f"{metric} is {worse:.3f} worse than the {kind} baseline (tolerance {policy['max_drop']})")
            if kind == "anchor":
                continue
            flips = [c["case_id"] for c in run["cases"]
                     if c["bucket"] != "PASS" and any(b["case_id"] == c["case_id"] and b["bucket"] == "PASS" for b in base["cases"])]
            if flips:
                add("EG010", "ADVISORY", f"{len(flips)} case(s) passed in the {kind} baseline and do not now: {flips[:5]}")
            for field, limit in (("latency_p95_ms", policy["latency_ratio_block"]), ("cost_per_request", policy["cost_ratio_block"])):
                if field in run and field in base and base[field] > 0:
                    ratio = run[field] / base[field]
                    if ratio > limit:
                        add("EG011", "BLOCK", f"{field} is {ratio:.2f}x the {kind} baseline (block above {limit}x)")
                    elif ratio > 1.0:
                        add("EG011", "ADVISORY", f"{field} is {ratio:.2f}x the {kind} baseline (tracked, not blocking)")
                elif release and field not in run:
                    add("EG013", "BLOCK", f"release run does not record {field}")
        if release:
            if run["tier"] != "R3":
                add("EG014", "BLOCK", f"release decisions use R3 results, got {run['tier']}")
            if f"{run['dataset_name']}@{run['dataset_version']}" not in approved:
                add("EG013", "BLOCK", f"dataset {run['dataset_name']}@{run['dataset_version']} is not the approved release dataset")
            gates = thresholds.get("release_gates", {})
            for dim in RELEASE_DIMENSIONS:
                target = gates.get(dim)
                if target is None:
                    add("EG013", "BLOCK", f"release dimension '{dim}' is neither mapped to a metric nor marked not_applicable")
                elif isinstance(target, str) and target not in run["metrics"] and target not in ("latency_p95_ms", "cost_per_request"):
                    add("EG013", "BLOCK", f"release dimension '{dim}' maps to '{target}', which this run did not measure")
                elif isinstance(target, str) and target in run["metrics"] and target not in spec["metrics"]:
                    add("EG013", "BLOCK", f"release dimension '{dim}' metric '{target}' has no threshold for this feature")
    return out


def route(routing: dict, changed: list[str]) -> tuple[dict, list[Finding]]:
    findings = []
    forbidden = set(routing["never_on_pr"])
    for rule in routing["rules"]:
        bad = forbidden & set(rule["suites"])
        if bad:
            findings.append(Finding("EG020", "BLOCK", rule["name"], f"routes never-on-PR suite(s) into R1: {sorted(bad)}"))
    bad = forbidden & set(routing["always"])
    if bad:
        findings.append(Finding("EG020", "BLOCK", "always", f"never-on-PR suite(s) in always: {sorted(bad)}"))
    suites, matched, never_sampled = set(routing["always"]), [], False
    for rule in routing["rules"]:
        if any(PurePosixPath(p).full_match(g) for p in changed for g in rule["paths"]):
            matched.append(rule["name"])
            suites |= set(rule["suites"])
            never_sampled |= rule.get("never_sampled", False)
    return {"suites": sorted(suites), "matched_rules": matched, "never_sampled": never_sampled}, findings


def emit(findings: list[Finding], extra: dict, json_out: Path | None) -> int:
    failed = any(f.severity == "BLOCK" for f in findings)
    verdict = "FAIL" if failed else ("PASS_WITH_REVIEW" if any(f.severity == "REVIEW" for f in findings) else "PASS")
    for f in findings:
        sys.stdout.write(f"{f.severity:8} {f.rule} [{f.feature}] {f.message}\n")
    sys.stdout.write(f"{TOOL} {verdict}: {len(findings)} finding(s)\n")
    report = {"tool": TOOL, "version": VERSION, "verdict": verdict, "findings": [asdict(f) for f in findings]} | extra
    if json_out:
        json_out.write_text(json.dumps(report, indent=2))
    return 1 if failed else 0


def selftest() -> int:
    sys.dont_write_bytecode = True                              # keep the skill directory clean
    from selftest_gate import BASE_RESULT, GATE_MUTATIONS, ROUTING, THRESHOLDS   # sibling fixtures
    failures: list[str] = []

    def run(thr: dict, res: dict, bases: dict, release: bool) -> set[str]:
        for doc, schema in ((thr, "thresholds.schema.json"), (res, "eval_result.schema.json")):
            errors = list(Draft202012Validator(json.loads((SCHEMAS / schema).read_text())).iter_errors(doc))
            if errors:
                raise InputError(f"selftest fixture invalid for {schema}: {errors[0].message}")
        approved = {f"{res['dataset_name']}@{res['dataset_version']}"}
        return {f.rule for f in check(thr, [res], bases, release, approved) if f.severity == "BLOCK"}

    clean = run(THRESHOLDS, BASE_RESULT, {"current": [BASE_RESULT]}, False)
    if clean:
        failures.append(f"clean fixture blocked: {sorted(clean)}")
    else:
        sys.stdout.write("ok   clean run vs identical baseline: no BLOCK\n")
    for name, (mutate, expected) in GATE_MUTATIONS.items():
        thr, res, base = copy.deepcopy(THRESHOLDS), copy.deepcopy(BASE_RESULT), copy.deepcopy(BASE_RESULT)
        bases, release = mutate(thr, res, base)
        got = run(thr, res, bases, release)
        ok = (not got) if expected == "" else (expected[1:] not in got) if expected.startswith("!") else (expected in got)
        if ok:
            sys.stdout.write(f"ok   {name} -> {expected or 'no BLOCK'} (blocks: {sorted(got)})\n")
        else:
            failures.append(f"{name}: expected {expected}, got {sorted(got)}")
    result, findings = route(ROUTING, ["src/ai/support-answer/agent.py", "prompts/support.md"])
    if findings or "support-answer-critical" not in result["suites"] or "prompt-redteam" not in result["suites"]:
        failures.append(f"route union wrong: {result} {findings}")
    else:
        sys.stdout.write(f"ok   route union -> {result['suites']}\n")
    bad = copy.deepcopy(ROUTING)
    bad["rules"][0]["suites"].append(bad["never_on_pr"][0])
    if any(f.rule == "EG020" for f in route(bad, [])[1]):
        sys.stdout.write("ok   never-on-PR suite routed into R1 -> EG020\n")
    else:
        failures.append("routing a never-on-PR suite was not rejected")
    for msg in failures:
        sys.stdout.write(f"FAIL {msg}\n")
    sys.stdout.write("selftest PASS\n" if not failures else "selftest FAIL\n")
    return 0 if not failures else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(prog=TOOL)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--thresholds", type=Path, required=True)
    c.add_argument("--results", type=Path, nargs="+", required=True)
    for kind in ("current", "release", "anchor"):
        c.add_argument(f"--baseline-{kind}", type=Path, nargs="+", default=[])
    c.add_argument("--release", action="store_true")
    c.add_argument("--approved-dataset", nargs="+", default=[])
    c.add_argument("--json", type=Path, dest="json_out")
    r = sub.add_parser("route")
    r.add_argument("--routing", type=Path, required=True)
    r.add_argument("--changed-files", required=True, help="file with one path per line, or - for stdin")
    r.add_argument("--json", type=Path, dest="json_out")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "route":
            routing = load(args.routing, "r1_routing.schema.json")
            text = sys.stdin.read() if args.changed_files == "-" else Path(args.changed_files).read_text(encoding="utf-8")
            result, findings = route(routing, [line.strip() for line in text.splitlines() if line.strip()])
            sys.stdout.write(json.dumps(result) + "\n")
            return emit(findings, result, args.json_out)
        if args.release and not args.approved_dataset:
            raise InputError("--release requires --approved-dataset NAME@VERSION")
        thresholds = load(args.thresholds, "thresholds.schema.json")
        results = [load(p, "eval_result.schema.json") for p in args.results]
        baselines = {kind: [load(p, "eval_result.schema.json") for p in getattr(args, f"baseline_{kind}")]
                     for kind in ("current", "release", "anchor")}
        findings = check(thresholds, results, baselines, args.release, set(args.approved_dataset))
    except (InputError, OSError) as exc:
        sys.stderr.write(f"{TOOL}: invalid input: {exc}\n")
        return 2
    return emit(findings, {}, args.json_out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
