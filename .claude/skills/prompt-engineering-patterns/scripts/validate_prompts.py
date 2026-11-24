# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["jsonschema==4.26.0", "referencing==0.37.0", "pyyaml==6.0.4"]
# [tool.uv]
# exclude-newer = "2026-11-21T00:00:00Z"
# ///
"""Deterministic validator for a Git prompt tree (default layout: prompts/<domain>/<feature>/<task>.<type>.yaml).

Checks each prompt card against ../assets/schemas/prompt_card.schema.json, then the rules a schema cannot
express (PRM section in brackets, mapped in reference/promptops-lifecycle.md section 13): name/path mirror and allowed domains [7], six-part
anatomy order [2], logic-less templates and declared/used variables [11], untrusted slots inside named
delimiters and named in CONSTRAINTS as data [3.2], uncertainty contract [2.2], secrets in template or examples
[6, 11], PII in examples and example coverage [5], examples valid against the exported output schema [4, 5],
examples overlapping eval cases [5], static-size and output budgets [14], changelog integrity [8].
It proves structure, not behaviour: the evals in section 15 prove behaviour.

Severities: BLOCK (exit 1) | REVIEW (exit 1 only with --strict) | ADVISORY (never fails).
Exit codes: 0 pass, 1 findings, 2 usage or unreadable input.

Run:  uv run --script validate_prompts.py prompts [--schemas-dir prompts/_schemas] [--golden-root tests/golden]
                                                  [--strict] [--json report.json]
      uv run --script validate_prompts.py classify --base-root OLD/prompts prompts [--json changes.json]
      uv run --script validate_prompts.py hash prompts/support/triage/classification.system.yaml
      uv run --script validate_prompts.py --selftest
"""

import argparse
import csv
import difflib
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TOOL, VERSION = "validate_prompts", "1.0.0"
HERE = Path(__file__).resolve().parent
CARD_SCHEMA = HERE.parent / "assets" / "schemas" / "prompt_card.schema.json"
SCAFFOLD = HERE.parent / "assets" / "prompts-scaffold" / "prompts"
SECTIONS = ["ROLE", "TASK", "CONSTRAINTS", "OUTPUT", "EXAMPLES", "CONTEXT"]
SECTION_RE = re.compile(r"^\[(ROLE|TASK|CONSTRAINTS|OUTPUT|EXAMPLES|CONTEXT)\]\s*$", re.MULTILINE)
SLOT_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
LOGIC_RE = re.compile(r"\{%|\{\{\s*[#/^>!&]|\{\{\{")
TAG_OPEN = re.compile(r"<([a-z_][a-z0-9_]*)(?:\s[^<>]*)?>")
DATA_RULE = re.compile(r"(?i)never follow|do not follow|not instructions|is data|as data|must not be followed")
UNCERTAINTY = re.compile(r"\b(UNKNOWN|CONFLICTED|STALE|ESCALATE|REFUSED)\b")
PLACEHOLDER = re.compile(r"<[a-z][a-z _-]*>")
SECRETS = [re.compile(p) for p in (
    r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"\bgh[pousr]_[A-Za-z0-9]{36,}",
    r"\bsk-[A-Za-z0-9_-]{20,}", r"\bxox[abprs]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_-]{35}",
    r"(?i)\b(api[_-]?key|secret|passw(or)?d|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{12,}",
    r"(?i)\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^:\s/]+:[^@\s]+@")]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
RESERVED_EMAIL = re.compile(r"@([a-z0-9-]+\.)*(example\.(com|org|net)|test|invalid|localhost)$", re.I)
SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
SAFETY_WORDS = re.compile(r"(?i)escalat|refus|safety|harm|emergency|legal|medical|fraud")
RAG_WORDS = re.compile(r"(?i)\bcit(e|ation)|source_id|retriev|<context")
CHARS_PER_TOKEN = 4          # ADAPT: approximation; swap in the pinned model's tokenizer for exact counts
CHANGE_EVALS = {  # PRM section 15 (reference/promptops-lifecycle.md section 3), cumulative rows ("Above +") expanded
    "metadata_only": [],
    "formatting": ["prompt file validation", "smoke golden cases"],
    "wording": ["full golden set for the feature", "critical sub-thresholds"],
    "output_schema": ["full golden set for the feature", "critical sub-thresholds", "schema conformance 100%",
                      "all consumers' contract tests"],
    "few_shot_examples": ["full golden set for the feature", "bias/fairness checks where applicable (G19)"],
    "safety_wording": ["full golden set for the feature", "critical sub-thresholds",
                       "safety-recall set at 100% critical sub-threshold", "red-team subset"],
    "rag_citation": ["full golden set for the feature", "critical sub-thresholds", "faithfulness",
                     "context precision", "citation correctness"],
    "tools": ["full golden set for the feature", "critical sub-thresholds", "trajectory eval",
              "tool-surface hash update", "tool red-team (eval strategy section 10)"],
    "model_change": ["full golden set", "safety", "red-team", "latency and cost comparison",
                     "fallback binding re-evaluated"],
    "new_language": ["full golden set in the new language", "safety recall in the new language"],
    "new_prompt": ["all applicable rows of section 15", "baseline established before first promotion"],
}


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    message: str


class Report:
    def __init__(self, root: Path) -> None:
        self.root, self.findings, self.scanned = root, [], 0

    def add(self, rule: str, sev: str, path: Path | str, msg: str) -> None:
        shown = str(path.relative_to(self.root)) if isinstance(path, Path) and path.is_relative_to(self.root) else str(path)
        self.findings.append(Finding(rule, sev, shown, msg))


class _StrDateLoader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so JSON Schema `format: date` sees what the author wrote."""


_StrDateLoader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def load(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    return yaml.load(text, Loader=_StrDateLoader) if path.suffix in (".yaml", ".yml") else json.loads(text)


def content_hash(card: dict) -> str:
    """Hash of everything that changes model behaviour; owner, description and changelog are excluded."""
    keys = ("template", "model", "output_schema", "variables", "tools", "examples", "languages")
    canon = json.dumps({k: card.get(k) for k in keys}, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def prompt_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.y*ml") if p.suffix in (".yaml", ".yml") and p.name != "domains.yaml"
                  and not any(part.startswith("_") for part in p.relative_to(root).parts))


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def sections(template: str) -> dict[str, str]:
    marks = list(SECTION_RE.finditer(template))
    return {m.group(1): template[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(template)]
            for i, m in enumerate(marks)}


def wrapper_tag(template: str, pos: int) -> str | None:
    """Name of the innermost tag that is open before `pos` and closed after it."""
    for match in reversed(list(TAG_OPEN.finditer(template, 0, pos))):
        tag = match.group(1)
        if f"</{tag}>" not in template[match.end():pos] and f"</{tag}>" in template[pos:]:
            return tag
    return None


def check_template(card: dict, path: Path, rep: Report) -> None:
    template = card["template"]
    order = [m.group(1) for m in SECTION_RE.finditer(template)]
    if len(order) != len(set(order)) or order != [s for s in SECTIONS if s in order]:
        rep.add("PC_ANATOMY_ORDER", "BLOCK", path, f"sections {order} are not in anatomy order {SECTIONS} (or repeat).")
    for required in ("ROLE", "TASK"):
        if required not in order:
            rep.add("PC_ANATOMY_MISSING", "BLOCK", path, f"[{required}] section missing (six-part anatomy, section 2).")
    parts = sections(template)
    if LOGIC_RE.search(template):
        rep.add("PC_TEMPLATE_LOGIC", "BLOCK", path, "template uses sections/partials/raw output; templates are logic-less (section 11).")
    declared = {v["name"]: v for v in card["variables"]}
    used = [(m.group(1), m.start()) for m in SLOT_RE.finditer(template)]
    for name, _ in used:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            rep.add("PC_TEMPLATE_LOGIC", "BLOCK", path, f"slot '{{{{{name}}}}}' is not a plain variable name (section 11).")
        elif name not in declared:
            rep.add("PC_VAR_UNDECLARED", "BLOCK", path, f"variable '{name}' used but not declared (section 11).")
    for name in sorted(set(declared) - {n for n, _ in used}):
        rep.add("PC_VAR_UNUSED", "BLOCK", path, f"variable '{name}' declared but never used (section 11).")
    constraints = parts.get("CONSTRAINTS", "")
    for name, pos in used:
        if declared.get(name, {}).get("trust") != "untrusted":
            continue
        tag = wrapper_tag(template, pos)
        if tag is None:
            rep.add("PC_UNTRUSTED_UNDELIMITED", "BLOCK", path, f"untrusted '{name}' is not inside a named <tag>...</tag> block (section 3.2).")
        elif not any(f"<{tag}>" in line and DATA_RULE.search(line) for line in constraints.splitlines()):
            rep.add("PC_UNTRUSTED_NOT_DATA", "REVIEW", path, f"[CONSTRAINTS] does not name <{tag}> as data that must not be followed (section 3.2).")
        if "CONTEXT" in parts and template.find("[CONTEXT]") > pos:
            rep.add("PC_UNTRUSTED_OUTSIDE_CONTEXT", "BLOCK", path, f"untrusted '{name}' appears before [CONTEXT]; slots carry data only (section 2).")
    if not UNCERTAINTY.search(constraints or template):
        rep.add("PC_UNCERTAINTY_CONTRACT", "REVIEW", path, "no uncertainty contract (UNKNOWN / CONFLICTED / STALE / ESCALATE) stated (section 2.2).")


def scan_text(card: dict, path: Path, rep: Report) -> None:
    blobs = [("template", card["template"])] + [(f"examples[{i}]", json.dumps(e, default=str))
                                                for i, e in enumerate(card.get("examples") or [])]
    for where, text in blobs:
        if any(p.search(text) for p in SECRETS):
            rep.add("PC_SECRET", "BLOCK", path, f"secret-like value in {where} (value not printed; sections 6, 11).")
    for where, text in blobs[1:]:
        pii = [e for e in EMAIL.findall(text) if not RESERVED_EMAIL.search(e)] + SSN.findall(text)
        pii += [c for c in CARD.findall(text) if luhn_ok(re.sub(r"\D", "", c))]
        if pii:
            rep.add("PC_EXAMPLE_PII", "BLOCK", path, f"{len(pii)} PII-like value(s) in {where}; examples are synthetic or sanitized (section 5).")
    for field in ("owner", "backup_owner"):
        if PLACEHOLDER.search(str(card.get(field, ""))):
            rep.add("PC_PLACEHOLDER", "REVIEW", path, f"{field} is a placeholder; name a person (section 20).")
    if any(PLACEHOLDER.search(str(card["model"].get(k, ""))) for k in ("provider", "model", "version")):
        rep.add("PC_PLACEHOLDER", "REVIEW", path, "model binding is a placeholder; pin provider, model and version (section 13).")


def check_examples(card: dict, path: Path, rep: Report, schemas_dir: Path | None, eval_inputs: set[str]) -> None:
    examples = card.get("examples") or []
    if not examples:
        return
    kinds = {e["kind"] for e in examples}
    if "edge" not in kinds or not kinds & {"escalate", "uncertain", "refuse"}:
        rep.add("PC_EXAMPLE_COVERAGE", "BLOCK", path, "examples MUST include an edge case and an uncertain/escalate case (section 5).")
    if any("provenance" not in e for e in examples):
        rep.add("PC_EXAMPLE_PROVENANCE", "REVIEW", path, "every example declares provenance synthetic|sanitized (section 5).")
    langs = set(card["languages"])
    if len(langs) > 1 and not langs <= {e.get("language", card["languages"][0]) for e in examples}:
        rep.add("PC_EXAMPLE_LANGUAGES", "ADVISORY", path, "examples do not cover every supported language; document why (section 12).")
    schema_file = schemas_dir / f"{card['output_schema']}.json" if schemas_dir else None
    if schema_file is None or not schema_file.is_file():
        rep.add("PC_EXAMPLE_SCHEMA_UNCHECKED", "REVIEW", path, f"no exported schema {card['output_schema']}.json to check examples against (sections 4, 5).")
    else:
        validator = Draft202012Validator(load(schema_file))
        for i, ex in enumerate(examples):
            out = json.loads(ex["output"]) if isinstance(ex["output"], str) and ex["output"].lstrip().startswith("{") else ex["output"]
            for err in validator.iter_errors(out):
                rep.add("PC_EXAMPLE_SCHEMA", "BLOCK", path, f"examples[{i}].output invalid for {card['output_schema']}: {err.message[:120]}")
    for i, ex in enumerate(examples):
        if normalise(ex["input"]) in eval_inputs:
            rep.add("PC_EXAMPLE_EVAL_OVERLAP", "BLOCK", path, f"examples[{i}] input also appears in an eval set (section 5 separation).")


def check_budget(card: dict, path: Path, rep: Report) -> None:
    budget, params = card["token_budget"], card["model"]["params"]
    static = SLOT_RE.sub("", card["template"]) + json.dumps(card.get("examples") or [], default=str)
    approx = len(static) // CHARS_PER_TOKEN
    if "static_max" not in budget:
        rep.add("PC_BUDGET_STATIC_UNSET", "REVIEW", path, "token_budget.static_max not set (section 14).")
    elif approx > budget["static_max"]:
        rep.add("PC_BUDGET_STATIC", "BLOCK", path,
                f"static prompt ~{approx} tokens (chars/{CHARS_PER_TOKEN}) > static_max {budget['static_max']} (section 14).")
    if params["max_output_tokens"] > budget["output_max"]:
        rep.add("PC_BUDGET_OUTPUT", "BLOCK", path, "model.params.max_output_tokens exceeds token_budget.output_max (section 14).")
    worst = sum(v.get("max_chars", 0) for v in card["variables"]) // CHARS_PER_TOKEN + approx
    if worst > budget["input_max"]:
        rep.add("PC_BUDGET_INPUT", "REVIEW", path, f"worst-case rendered input ~{worst} tokens > input_max "
                f"{budget['input_max']}; wrapper must truncate or reject (section 14).")


def normalise(text: str) -> str:
    return " ".join(str(text).casefold().split())


INPUT_KEYS = frozenset({"input", "question", "user_message", "planted_content"})   # golden-dataset.md case fields
LIST_INPUT_KEYS = frozenset({"turns"})


def collect_eval_inputs(golden_root: Path | None) -> set[str]:
    found: set[str] = set()
    if golden_root is None:
        return found

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in INPUT_KEYS and isinstance(value, str):
                    found.add(normalise(value))
                elif key in LIST_INPUT_KEYS and isinstance(value, list):
                    found.update(normalise(item) for item in value if isinstance(item, str))
                    visit([item for item in value if not isinstance(item, str)])
                else:
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    for path in golden_root.rglob("*"):
        if path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    visit({k: v for k, v in row.items() if k in INPUT_KEYS})
        elif path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    visit(json.loads(line))
        elif path.suffix in (".json", ".yaml", ".yml"):
            visit(load(path))
    return found


def load_card(path: Path, rep: Report, validator: Draft202012Validator) -> dict | None:
    try:
        card = load(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        rep.add("PC_UNREADABLE", "BLOCK", path, f"cannot parse: {type(exc).__name__}")
        return None
    errors = sorted(validator.iter_errors(card), key=lambda e: list(e.path))
    for err in errors:
        where = "/".join(map(str, err.path)) or "<root>"
        rep.add("PC_SCHEMA", "BLOCK", path, f"{where}: {err.message[:160]}")
    return None if errors else card


def validate(root: Path, schemas_dir: Path | None, golden_root: Path | None) -> Report:
    rep = Report(root)
    validator = Draft202012Validator(json.loads(CARD_SCHEMA.read_text()), format_checker=FormatChecker())
    domains_file = root / "domains.yaml"
    allowed = set((load(domains_file) or {}).get("allowed_domains", [])) if domains_file.is_file() else None
    if allowed is None:
        rep.add("PC_DOMAINS_UNPUBLISHED", "REVIEW", root / "domains.yaml", "no allowed-domain list published (section 7).")
    schemas_dir = schemas_dir or (root / "_schemas" if (root / "_schemas").is_dir() else None)
    eval_inputs = collect_eval_inputs(golden_root)
    seen: dict[str, Path] = {}
    for path in prompt_files(root):
        rep.scanned += 1
        card = load_card(path, rep, validator)
        if card is None:
            continue
        domain, feature, task, ptype = card["name"].split(".")
        expected = Path(domain, feature, f"{task}.{ptype}{path.suffix}")
        if path.relative_to(root) != expected:
            rep.add("PC_PATH", "BLOCK", path, f"path must mirror the name: {expected} (section 7).")
        if allowed is not None and domain not in allowed:
            rep.add("PC_DOMAIN", "BLOCK", path, f"domain '{domain}' is not in domains.yaml (section 7).")
        if card["name"] in seen:
            rep.add("PC_DUPLICATE_NAME", "BLOCK", path, f"name also used by {seen[card['name']].relative_to(root)}.")
        seen[card["name"]] = path
        versions = [c["version"] for c in card["changelog"]]
        if versions != sorted(set(versions)):
            rep.add("PC_CHANGELOG_ORDER", "BLOCK", path, "changelog versions must be unique and ascending (section 8).")
        if card["risk_tier"] in ("T2", "T3") and "feature_flag" not in card and versions == [1]:
            rep.add("PC_FEATURE_FLAG", "ADVISORY", path, "new T2/T3 prompt: ship behind a feature flag defaulting OFF (section 9.2).")
        check_template(card, path, rep)
        scan_text(card, path, rep)
        check_examples(card, path, rep, schemas_dir, eval_inputs)
        check_budget(card, path, rep)
    if rep.scanned == 0:
        rep.add("PC_NO_PROMPTS", "BLOCK", root, "no prompt files found; the check saw no input.")
    return rep


def classify_change(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["new_prompt"]
    if content_hash(old) == content_hash(new):
        return ["metadata_only"]
    classes: list[str] = []
    if old["model"] != new["model"]:
        classes.append("model_change")
    if old["output_schema"] != new["output_schema"]:
        classes.append("output_schema")
    if old.get("examples") != new.get("examples"):
        classes.append("few_shot_examples")
    if old.get("tools") != new.get("tools"):
        classes.append("tools")
    if set(new["languages"]) - set(old["languages"]):
        classes.append("new_language")
    if old["template"] != new["template"] or old["variables"] != new["variables"]:
        if normalise(old["template"]) == normalise(new["template"]) and old["variables"] == new["variables"]:
            classes.append("formatting")
        else:
            changed = [line[1:] for line in difflib.ndiff(old["template"].splitlines(), new["template"].splitlines())
                       if line[:1] in "+-" and line[1:].strip()]
            classes.append("wording")
            if any(SAFETY_WORDS.search(line) for line in changed):
                classes.append("safety_wording")
            if any(RAG_WORDS.search(line) for line in changed):
                classes.append("rag_citation")
            if any(t in line for t in (new.get("tools") or []) for line in changed) and "tools" not in classes:
                classes.append("tools")
    return classes or ["wording"]


def classify(base_root: Path, root: Path) -> tuple[dict, list[Finding]]:
    findings: list[Finding] = []
    old_cards = {}
    for path in prompt_files(base_root):
        card = load(path)
        old_cards[card["name"]] = card
    result: dict[str, dict] = {}
    for path in prompt_files(root):
        new = load(path)
        old = old_cards.get(new["name"])
        classes = classify_change(old, new)
        evals = list(dict.fromkeys(e for c in classes for e in CHANGE_EVALS[c]))
        if old is not None and classes != ["metadata_only"]:
            if max(c["version"] for c in new["changelog"]) <= max(c["version"] for c in old["changelog"]):
                findings.append(Finding("PC_CHANGELOG_NOT_BUMPED", "BLOCK", str(path.relative_to(root)),
                                        "behaviour changed without a new changelog entry (sections 8, 19)."))
        result[new["name"]] = {"classes": classes, "required_evals": evals, "content_hash": content_hash(new),
                               "full_golden": any(c not in ("metadata_only", "formatting") for c in classes)}
    for name in sorted(set(old_cards) - set(result)):
        result[name] = {"classes": ["removed"], "required_evals": [], "content_hash": None, "full_golden": False}
        findings.append(Finding("PC_PROMPT_REMOVED", "REVIEW", name, "prompt removed: confirm callers and labels are gone first (section 9.4)."))
    return result, findings


def out(line: str) -> None:
    sys.stdout.write(line + "\n")


def emit(findings: list[Finding], strict: bool, json_path: str | None, extra: dict, tool: str = TOOL) -> int:
    blocks = sum(f.severity == "BLOCK" for f in findings)
    reviews = sum(f.severity == "REVIEW" for f in findings)
    code = 1 if blocks or (strict and reviews) else 0
    for f in findings:
        out(f"{f.severity:<8} {f.rule:<30} {f.path}  {f.message}")
    out(f"{tool} {VERSION}: findings={len(findings)} block={blocks} review={reviews} verdict={'FAIL' if code else 'PASS'}")
    if json_path:
        Path(json_path).write_text(json.dumps({"tool": tool, "version": VERSION, "exit_code": code, **extra,
                                               "findings": [asdict(f) for f in findings]}, indent=2) + "\n", encoding="utf-8")
    return code


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        from selftest_prompts import run_validator_selftest   # sibling fixtures
        return run_validator_selftest()
    if argv[:1] == ["hash"] and len(argv) == 2:
        out(content_hash(load(Path(argv[1]))))
        return 0
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument("mode_or_root")
    parser.add_argument("root", nargs="?")
    parser.add_argument("--base-root", type=Path)
    parser.add_argument("--schemas-dir", type=Path)
    parser.add_argument("--golden-root", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    if args.mode_or_root == "classify":
        if args.base_root is None or args.root is None:
            parser.error("classify needs --base-root OLD and the new prompts root")
        changes, findings = classify(args.base_root, Path(args.root))
        for name, info in changes.items():
            out(f"CHANGE   {name}: {','.join(info['classes'])} -> {'; '.join(info['required_evals']) or 'no eval'}")
        return emit(findings, args.strict, args.json, {"changes": changes})
    root = Path(args.mode_or_root)
    if not root.is_dir():
        sys.stderr.write(f"{TOOL}: prompts root {root} not found\n")
        return 2
    rep = validate(root, args.schemas_dir, args.golden_root)
    return emit(rep.findings, args.strict, args.json, {"root": str(root), "prompt_files": rep.scanned})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
