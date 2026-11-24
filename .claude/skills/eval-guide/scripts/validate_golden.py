# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0", "pyyaml==6.0.4"]
# [tool.uv]
# exclude-newer = "2026-11-21T00:00:00Z"
# ///
"""Deterministic validator for a golden-dataset tree (default layout: tests/golden/).

Checks every dataset_manifest.yaml and the case files it lists against the closed JSON Schemas in
../assets/schemas, then the cross-file rules a schema cannot express: sha256 + case-count integrity,
unmanifested case files, unique case ids, declared minimum sizes, run-stage splits, deterministic PII
patterns, red-team class coverage per feature and tool, audit-required write tools, RAG isolation ids,
regression-file SLAs, protected-canary review dates, default minimum sizes and SemVer bumps vs a base tree.

Severities: BLOCK (exit 1) | REVIEW (exit 1 only with --strict) | ADVISORY (never fails).
Exit codes: 0 pass, 1 findings, 2 usage or unreadable input.

Run:  uv run --script validate_golden.py tests/golden [--base-root OLD/tests/golden] [--stage day1|prelaunch]
                                                    [--strict] [--json report.json] [--today YYYY-MM-DD]
      uv run --script validate_golden.py hash <dataset_dir>     # print sha256 + case counts for the manifest
      uv run --script validate_golden.py --selftest
"""

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TOOL = "validate_golden"
VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
SCHEMAS = HERE.parent / "assets" / "schemas"
SCAFFOLD = HERE.parent / "assets" / "golden-scaffold" / "tests" / "golden"
CASE_SUFFIXES = {".jsonl", ".csv", ".yaml", ".yml", ".json"}
SKIP_DIRS = {"baselines"}
RAG_HEADER = ["case_id", "feature", "question", "expected_answer", "required_context_ids",
              "forbidden_context_ids", "risk_level", "tags"]
RAG_OPTIONAL = ["query_type", "scope", "expected_outcome", "high_stakes"]    # optional trailing columns
BEHAVIOUR_KEYS = {"input", "question", "expected", "assertions", "expected_answer",
                  "required_context_ids", "forbidden_context_ids", "case_kind", "expected_outcome"}
SLA_HOURS = {"P0": 24, "P1": 72, "P2": 168}           # P3 = "1 sprint": checked only with --sprint-days
# Section 7.10 defaults (ADAPT): (day1, prelaunch)
MIN_SIZES = {"feature": (8, 50), "rag": (10, 100), "isolation": (10, 50), "prompt_injection": (10, 100),
             "compliance": (25, 100), "multi_turn": (3, 15)}
TOOL_KINDS = {"happy", "auth_fail", "schema_invalid", "scope_mismatch", "downstream_timeout"}
RESERVED_EMAIL = re.compile(r"@([a-z0-9-]+\.)*(example\.(com|org|net)|example|test|invalid|localhost)$", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w-])\+?\d[\d ().-]{8,}\d(?![\w-])")
SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    message: str
    case_id: str = ""


@dataclass
class Dataset:
    manifest_path: Path
    manifest: dict
    cases: dict[str, list[dict]] = field(default_factory=dict)   # case_schema -> cases


class Report:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(self, rule: str, sev: str, path: Path | str, msg: str, case_id: str = "") -> None:
        rel = str(path.relative_to(self.root)) if isinstance(path, Path) and path.is_relative_to(self.root) else str(path)
        self.findings.append(Finding(rule, sev, rel, msg, case_id))


def load_schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text()), format_checker=FormatChecker())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def iban_ok(value: str) -> bool:
    moved = value[4:] + value[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def pii_hits(text: str) -> list[str]:
    hits = [f"email {m}" for m in EMAIL.findall(text) if not RESERVED_EMAIL.search(m)]
    hits += [f"US SSN {m}" for m in SSN.findall(text)]
    for m in CARD.findall(text):
        digits = re.sub(r"\D", "", m)
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            hits.append(f"payment card ending {digits[-4:]}")
    hits += [f"IBAN {m[:4]}..." for m in IBAN.findall(text) if iban_ok(m)]
    for m in PHONE.findall(text):
        digits = re.sub(r"\D", "", m)
        reserved = "55501" in digits[-7:-2] or digits.startswith(("447700900", "07700900"))
        if 10 <= len(digits) <= 15 and not reserved and not SSN.search(m):
            hits.append(f"phone number {m.strip()}")
    return hits


def read_cases(path: Path, case_schema: str) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if case_schema == "rag":
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        extra = header[len(RAG_HEADER):]
        if header[:len(RAG_HEADER)] != RAG_HEADER or len(set(extra)) != len(extra) or not set(extra) <= set(RAG_OPTIONAL):
            raise ValueError(f"RAG CSV header must be {','.join(RAG_HEADER)} then optionally any of {','.join(RAG_OPTIONAL)}")
        rows = []
        for raw in reader:
            row: dict[str, object] = {k: v for k, v in zip(header, raw, strict=True) if k in RAG_HEADER or v != ""}
            for col in ("required_context_ids", "forbidden_context_ids", "tags"):
                row[col] = [v for v in str(row[col]).split("|") if v]
            if row.get("high_stakes") in ("true", "false"):
                row["high_stakes"] = row["high_stakes"] == "true"
            rows.append(row)
        return rows
    if case_schema in ("trajectory", "tool"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = yaml.safe_load(text)
    if case_schema == "regression":
        return [data]
    return [data]                                       # redteam: whole {cases: [...]} document


def case_list(case_schema: str, docs: list[dict]) -> list[dict]:
    if case_schema == "redteam":
        return [c for d in docs for c in d.get("cases", [])]
    if case_schema == "regression":
        return [c for d in docs for c in d.get("cases", [])]
    return docs


def case_id(case: dict) -> str:
    return str(case.get("id") or case.get("case_id") or "")


def parse_ts(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value}")
    return ts


def load_tree(root: Path, rep: Report) -> list[Dataset]:
    validators = {n: load_schema(f"{n}_case.schema.json") for n in ("trajectory", "rag", "tool", "redteam", "regression")}
    manifest_v = load_schema("dataset_manifest.schema.json")
    datasets: list[Dataset] = []
    listed: set[Path] = set()
    for mpath in sorted(root.rglob("dataset_manifest.yaml")):
        try:
            manifest = yaml.safe_load(mpath.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            rep.add("GD002", "BLOCK", mpath, f"manifest is not valid YAML: {exc}")
            continue
        errors = sorted(manifest_v.iter_errors(manifest), key=lambda e: list(e.path))
        for err in errors:
            rep.add("GD002", "BLOCK", mpath, f"manifest schema: {'/'.join(map(str, err.path)) or '<root>'}: {err.message}")
        if errors:
            continue
        ds = Dataset(mpath, manifest)
        for entry in manifest["files"]:
            fpath = (mpath.parent / entry["path"]).resolve()
            listed.add(fpath)
            if not fpath.is_file():
                rep.add("GD003", "BLOCK", mpath, f"listed file missing: {entry['path']}")
                continue
            if sha256(fpath) != entry["sha256"]:
                rep.add("GD004", "BLOCK", fpath, "sha256 differs from the manifest (edit without manifest update)")
            kind = entry["case_schema"]
            try:
                docs = read_cases(fpath, kind)
            except (ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
                rep.add("GD007", "BLOCK", fpath, f"unparseable case file: {exc}")
                continue
            for doc in docs:
                for err in validators[kind].iter_errors(doc):
                    rep.add("GD007", "BLOCK", fpath, f"{kind} schema: {'/'.join(map(str, err.path)) or '<root>'}: {err.message}",
                            case_id(doc) if isinstance(doc, dict) else "")
            cases = case_list(kind, docs)
            if len(cases) != entry["cases"]:
                rep.add("GD005", "BLOCK", fpath, f"manifest says {entry['cases']} cases, file has {len(cases)}")
            if kind == "regression":
                for doc in docs:
                    doc["_path"] = fpath
                ds.cases.setdefault("regression_files", []).extend(docs)
            ds.cases.setdefault(kind, []).extend(cases)
        datasets.append(ds)
    for fpath in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in CASE_SUFFIXES):
        if fpath.name == "dataset_manifest.yaml" or SKIP_DIRS & set(fpath.relative_to(root).parts):
            continue
        if fpath.resolve() not in listed:
            has_manifest = (fpath.parent / "dataset_manifest.yaml").exists()
            rule, msg = ("GD006", "case file not listed in its dataset_manifest.yaml") if has_manifest else \
                ("GD001", "case file in a directory without dataset_manifest.yaml")
            rep.add(rule, "BLOCK", fpath, msg)
    return datasets


def check_rules(datasets: list[Dataset], rep: Report, stage: str, today: dt.date, sprint_days: int | None) -> None:
    seen: dict[str, Path] = {}
    features: set[str] = set()
    tool_cases: dict[str, list[dict]] = {}
    where: dict[str, Path] = {}
    redteam: list[dict] = []
    counts: dict[str, dict[str, int]] = {k: {} for k in MIN_SIZES}
    idx = 0 if stage == "day1" else 1
    for ds in datasets:
        m, mp = ds.manifest, ds.manifest_path
        all_cases = [c for kind, cs in ds.cases.items() if kind != "regression_files" for c in cs]
        for c in all_cases:
            cid = case_id(c)
            if cid in seen:
                rep.add("GD008", "BLOCK", mp, f"duplicate case id (also in {seen[cid].parent.name})", cid)
            seen[cid] = mp
            feat = c.get("feature")
            if feat and m["feature"] != "cross-cutting" and feat != m["feature"]:
                rep.add("GD009", "BLOCK", mp, f"case feature '{feat}' differs from manifest feature '{m['feature']}'", cid)
        if len(all_cases) < m["minimum_required_cases"]:
            rep.add("GD010", "BLOCK", mp, f"{len(all_cases)} cases < minimum_required_cases {m['minimum_required_cases']}")
        missing = {"nightly", "release"} - set(m["splits"])
        if missing:
            rep.add("GD011", "BLOCK", mp, f"full datasets must run nightly and before release; splits lack {sorted(missing)}")
        if any(c.get("risk_level") == "critical" for c in all_cases) and "ci" not in m["splits"]:
            rep.add("GD012", "BLOCK", mp, "dataset holds critical cases but is not in the 'ci' split (critical cases never sampled out)")
        for entry in m["files"]:
            fpath = mp.parent / entry["path"]
            if fpath.is_file():
                for hit in pii_hits(fpath.read_text(encoding="utf-8")):
                    rep.add("GD013", "BLOCK", fpath, f"possible real PII: {hit} (use aliases, example.com, reserved phone ranges)")
        if m["dataset_type"] not in ("adversarial_security", "production_regressions", "tool_contract") and m["feature"] != "cross-cutting":
            features.add(m["feature"])
            where[f"feature:{m['feature']}"] = mp
        for c in ds.cases.get("tool", []):
            tool_cases.setdefault(c["tool"], []).append(c)
            where.setdefault(f"tool:{c['tool']}", mp)
        redteam += ds.cases.get("redteam", [])
        for c in ds.cases.get("trajectory", []):
            counts["feature"][c["feature"]] = counts["feature"].get(c["feature"], 0) + 1
            if "turns" in c.get("input", {}):
                counts["multi_turn"][c["feature"]] = counts["multi_turn"].get(c["feature"], 0) + 1
            if c.get("case_class") in ("isolation", "compliance"):
                key = c["case_class"]
                counts[key]["all"] = counts[key].get("all", 0) + 1
        for c in ds.cases.get("rag", []):
            counts["rag"][c["feature"]] = counts["rag"].get(c["feature"], 0) + 1
            if c["forbidden_context_ids"]:
                counts["isolation"]["all"] = counts["isolation"].get("all", 0) + 1
            overlap = set(c["required_context_ids"]) & set(c["forbidden_context_ids"])
            if overlap:
                rep.add("GD016", "BLOCK", mp, f"context ids both required and forbidden: {sorted(overlap)}", c["case_id"])
        for doc in ds.cases.get("regression_files", []):
            check_regression(doc, rep, sprint_days)
        check_protection(m, mp, rep, today)
    for c in redteam:
        if c["attack_class"] in ("direct_prompt_injection", "indirect_injection_retrieved", "indirect_injection_stored"):
            counts["prompt_injection"]["all"] = counts["prompt_injection"].get("all", 0) + 1
        if c["attack_class"] == "cross_scope_exfiltration":
            counts["isolation"]["all"] = counts["isolation"].get("all", 0) + 1
        if c["attack_class"] == "compliance_bypass_paraphrase":
            counts["compliance"]["all"] = counts["compliance"].get("all", 0) + 1
    families: dict[str, int] = {}
    for c in redteam:
        if "paraphrase_of" in c:
            families[c["paraphrase_of"]] = families.get(c["paraphrase_of"], 0) + 1
    for c in redteam:
        if c["risk_level"] == "critical" and "paraphrase_of" not in c and families.get(c["id"], 0) < 2:
            rep.add("GD022", "REVIEW", ".", "critical red-team case needs >= 3 phrasings (2+ cases with paraphrase_of) "
                    "plus an encoding or language variant (security playbook 10.1)", c["id"])
    mapped_features = {c["feature"] for c in redteam}
    mapped_tools = {t for c in redteam for t in c.get("target_tools", [])}
    for feat in sorted(features - mapped_features):
        rep.add("GD014", "BLOCK", where[f"feature:{feat}"], f"feature '{feat}' has zero mapped red-team cases")
    for tool in sorted(set(tool_cases) - mapped_tools):
        rep.add("GD014", "BLOCK", where[f"tool:{tool}"], f"tool '{tool}' has zero mapped red-team cases (target_tools)")
    for tool, cases in sorted(tool_cases.items()):
        if any(c["tool_side_effect"] == "write" for c in cases) and not any(c["expected"]["audit_log_required"] for c in cases):
            rep.add("GD015", "BLOCK", where[f"tool:{tool}"], f"write tool '{tool}' has no case asserting an audit-log record")
        kinds = TOOL_KINDS - {c["case_kind"] for c in cases}
        if kinds:
            rep.add("GD018", "REVIEW", where[f"tool:{tool}"], f"tool '{tool}' lacks default case kinds {sorted(kinds)} (golden-dataset.md Minimum sizes, ADAPT)")
    for key, per in counts.items():
        need = MIN_SIZES[key][idx]
        scope = per.items() if per else [("all", 0)] if key in ("isolation", "prompt_injection") else []
        for name, n in scope:
            if n < need:
                rep.add("GD018", "REVIEW", ".", f"{key} '{name}': {n} cases < {stage} default {need} (ADAPT; record the decision if lower)")


def check_regression(doc: dict, rep: Report, sprint_days: int | None) -> None:
    path = doc["_path"]
    if path.stem != doc.get("incident_id"):
        rep.add("GD017", "BLOCK", path, f"file name must equal incident_id ({doc.get('incident_id')})")
    try:
        detected, committed = parse_ts(doc["detected_at"]), parse_ts(doc["dataset_committed_at"])
    except (KeyError, ValueError) as exc:
        rep.add("GD017", "BLOCK", path, f"incident timestamps: {exc}")
        return
    limit = SLA_HOURS.get(doc["severity"])
    if limit is None and sprint_days:
        limit = sprint_days * 24
    if limit is not None and (committed - detected).total_seconds() > limit * 3600:
        rep.add("GD017", "REVIEW", path, f"{doc['severity']} detection -> dataset took longer than {limit} h (golden-dataset.md flywheel SLA)")
    if committed < detected:
        rep.add("GD017", "BLOCK", path, "dataset_committed_at is before detected_at")


def check_protection(m: dict, mp: Path, rep: Report, today: dt.date) -> None:
    prot = m.get("protection") or {}
    if prot.get("class") != "protected_canary":
        return
    if dt.date.fromisoformat(prot["refresh_review_due"]) < today:
        rep.add("GD020", "REVIEW", mp, "protected canary relevance review is overdue (refresh_review_due passed)")
    for key, label in (("contamination_check", "last_run"), ("access_review", "last_review")):
        if (today - dt.date.fromisoformat(prot[key][label])).days > 92:
            rep.add("GD020", "REVIEW", mp, f"protected canary {key} older than a quarter")


def check_versions(datasets: list[Dataset], base_root: Path, rep: Report) -> None:
    base = Report(base_root)
    old = {d.manifest["dataset_name"]: d for d in load_tree(base_root, base)}
    kept = {case_id(c) for ds in datasets for k, cs in ds.cases.items() if k != "regression_files" for c in cs}
    for old_ds in old.values():                                  # regression forever (security playbook 10.1)
        derived = old_ds.cases.get("regression", []) + [
            c for c in old_ds.cases.get("redteam", []) if str(c.get("source", "")).startswith(("finding:", "incident:"))]
        for c in derived:
            if case_id(c) not in kept:
                rep.add("GD021", "BLOCK", old_ds.manifest_path.relative_to(base_root), "a finding- or incident-derived "
                        "case was deleted (supersede it with a stronger case instead)", case_id(c))
    for ds in datasets:
        prev = old.get(ds.manifest["dataset_name"])
        if prev is None:
            continue
        def index(d: Dataset) -> dict[str, dict]:
            return {case_id(c): c for k, cs in d.cases.items() if k != "regression_files" for c in cs}
        new_cases, old_cases = index(ds), index(prev)
        need = 0                                                     # 0 none, 1 patch, 2 minor, 3 major
        if ds.manifest["schema_version"] != prev.manifest["schema_version"] or set(old_cases) - set(new_cases):
            need = 3
        for cid, case in new_cases.items():
            if cid not in old_cases:
                need = max(need, 2)
            elif case != old_cases[cid]:
                changed = {k for k in case.keys() | old_cases[cid].keys() if case.get(k) != old_cases[cid].get(k)}
                need = max(need, 3 if changed & BEHAVIOUR_KEYS else 1)
        cur = tuple(int(x) for x in ds.manifest["version"].split("."))
        was = tuple(int(x) for x in prev.manifest["version"].split("."))
        if need == 0 and ds.manifest != prev.manifest and cur <= was:
            need = 1
        bumped = 3 if cur[0] > was[0] else 2 if cur[:2] > was[:2] else 1 if cur > was else 0
        if cur < was:
            rep.add("GD019", "BLOCK", ds.manifest_path, f"version went backwards {prev.manifest['version']} -> {ds.manifest['version']}")
        elif bumped < need:
            label = {1: "PATCH", 2: "MINOR", 3: "MAJOR"}[need]
            rep.add("GD019", "BLOCK", ds.manifest_path, f"changes require a {label} bump; version {prev.manifest['version']} -> {ds.manifest['version']}")


def validate(root: Path, base_root: Path | None, stage: str, today: dt.date, sprint_days: int | None) -> Report:
    rep = Report(root)
    datasets = load_tree(root, rep)
    if not datasets and not rep.findings:
        rep.add("GD001", "BLOCK", root, "no dataset_manifest.yaml found under the golden root")
    check_rules(datasets, rep, stage, today, sprint_days)
    if base_root is not None:
        check_versions(datasets, base_root, rep)
    return rep


def verdict(rep: Report, strict: bool) -> tuple[str, int]:
    sev = {f.severity for f in rep.findings}
    if "BLOCK" in sev or (strict and "REVIEW" in sev):
        return "FAIL", 1
    return ("PASS_WITH_REVIEW" if "REVIEW" in sev else "PASS"), 0


def emit(rep: Report, strict: bool, json_out: Path | None) -> int:
    result, code = verdict(rep, strict)
    for f in rep.findings:
        sys.stdout.write(f"{f.severity:8} {f.rule} {f.path}{' [' + f.case_id + ']' if f.case_id else ''}: {f.message}\n")
    sys.stdout.write(f"{TOOL} {result}: {len(rep.findings)} finding(s)\n")
    if json_out:
        json_out.write_text(json.dumps({"tool": TOOL, "version": VERSION, "verdict": result,
                                        "findings": [asdict(f) for f in rep.findings]}, indent=2))
    return code


def hash_cmd(dataset_dir: Path) -> int:
    manifest = yaml.safe_load((dataset_dir / "dataset_manifest.yaml").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        fpath = dataset_dir / entry["path"]
        try:
            n = len(case_list(entry["case_schema"], read_cases(fpath, entry["case_schema"])))
        except (ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
            sys.stderr.write(f"{fpath}: unparseable case file: {exc}\n")
            return 2
        sys.stdout.write(f"- path: {entry['path']}\n  sha256: {sha256(fpath)}\n  cases: {n}\n  case_schema: {entry['case_schema']}\n")
    return 0


def rehash(root: Path) -> None:
    for mpath in root.rglob("dataset_manifest.yaml"):
        manifest = yaml.safe_load(mpath.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            fpath = mpath.parent / entry["path"]
            entry["sha256"] = sha256(fpath)
            entry["cases"] = len(case_list(entry["case_schema"], read_cases(fpath, entry["case_schema"])))
        mpath.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def selftest() -> int:
    sys.dont_write_bytecode = True                              # keep the skill directory clean
    from selftest_golden import MUTATIONS                       # sibling module: planted violations
    today = dt.date(2026, 11, 23)
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean"
        shutil.copytree(SCAFFOLD, clean)
        rep = validate(clean, None, "day1", today, None)
        blocks = [f for f in rep.findings if f.severity == "BLOCK"]
        if blocks:
            failures.append(f"clean scaffold has BLOCK findings: {[asdict(f) for f in blocks]}")
        else:
            sys.stdout.write(f"ok   clean scaffold: no BLOCK ({len(rep.findings)} REVIEW/ADVISORY)\n")
        for name, (mutate, expected_rule, needs_rehash, use_base) in MUTATIONS.items():
            work = Path(tmp) / name
            shutil.copytree(SCAFFOLD, work)
            mutate(work)
            if needs_rehash:
                rehash(work)
            rep = validate(work, clean if use_base else None, "day1", today, None)
            got = {f.rule for f in rep.findings if f.severity == "BLOCK"}
            if expected_rule in got and verdict(rep, False)[1] == 1:
                sys.stdout.write(f"ok   {name} -> {expected_rule}\n")
            else:
                failures.append(f"{name}: expected {expected_rule}, got {sorted(got)}")
    for msg in failures:
        sys.stdout.write(f"FAIL {msg}\n")
    sys.stdout.write("selftest PASS\n" if not failures else "selftest FAIL\n")
    return 0 if not failures else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] == ["hash"] and len(argv) == 2:
        return hash_cmd(Path(argv[1]))
    ap = argparse.ArgumentParser(prog=TOOL, description=__doc__.split("\n")[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--base-root", type=Path)
    ap.add_argument("--stage", choices=["day1", "prelaunch"], default="day1")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", type=Path, dest="json_out")
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.datetime.now(dt.UTC).date())
    ap.add_argument("--sprint-days", type=int)
    args = ap.parse_args(argv)
    if not args.root.is_dir() or (args.base_root is not None and not args.base_root.is_dir()):
        sys.stderr.write(f"{TOOL}: golden root not found: {args.root}\n")
        return 2
    try:
        rep = validate(args.root.resolve(), args.base_root.resolve() if args.base_root else None,
                       args.stage, args.today, args.sprint_days)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"{TOOL}: cannot read input: {exc}\n")
        return 2
    return emit(rep, args.strict, args.json_out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
