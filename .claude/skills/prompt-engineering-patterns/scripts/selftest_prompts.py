"""Selftest fixtures for validate_prompts.py and prompt_drift.py (positive and negative controls).

Every control mutates a copy of ../assets/prompts-scaffold in a temp dir. A control passes only when the
expected rule fires (negative) or no BLOCK fires (positive); the scaffold itself is the positive control.
"""

import contextlib
import copy
import datetime as dt
import io
import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import yaml

import prompt_drift
import validate_prompts as vp

CARD_REL = Path("support/triage/classification.system.yaml")
TODAY = dt.date(2026, 11, 20)


def _tree(tmp: Path, mutate: Callable[[dict], None] | None = None, name: str = "prompts") -> Path:
    root = tmp / name
    shutil.copytree(vp.SCAFFOLD, root)
    if mutate is not None:
        card = vp.load(root / CARD_REL)
        mutate(card)
        (root / CARD_REL).write_text(yaml.safe_dump(card, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return root


def _set(path: str, value: object) -> Callable[[dict], None]:
    def mutate(card: dict) -> None:
        node, *keys = [card, *path.split(".")]
        for key in keys[:-1]:
            node = node[int(key)] if isinstance(node, list) else node[key]
        last = keys[-1]
        if value is _DELETE:
            del node[last]
        elif isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    return mutate


def _tpl(old: str, new: str) -> Callable[[dict], None]:
    def mutate(card: dict) -> None:
        assert old in card["template"], old
        card["template"] = card["template"].replace(old, new)
    return mutate


_DELETE = object()
FAKE_KEY = "api" + "_key = " + "Zq8" * 8                     # assembled so this file holds no secret literal
FAKE_EMAIL = "jane.doe" + "@" + "corp-mail.io"


def _example_email(card: dict) -> None:
    card["examples"][0]["input"] = f"Contact me at {FAKE_EMAIL} about the refund."


def _swap(a: str, b: str) -> Callable[[dict], None]:
    def mutate(card: dict) -> None:
        card["template"] = card["template"].replace(a, "[X]").replace(b, a).replace("[X]", b)
    return mutate


def _lowercase_statuses(card: dict) -> None:
    for status in ("UNKNOWN", "CONFLICTED", "ESCALATE"):
        card["template"] = card["template"].replace(f'"{status}"', status.lower())


def _move(tmp_root: Path) -> None:
    (tmp_root / CARD_REL).rename(tmp_root / "support/triage/wrong.system.yaml")


VALIDATOR_CASES: list[tuple[str, Callable[[dict], None] | None, str]] = [
    ("three-segment name", _set("name", "support.triage.system"), "PC_SCHEMA"),
    ("model version alias", _set("model.version", "latest"), "PC_SCHEMA"),
    ("model id alias suffix", _set("model.model", "provider-flash-latest"), "PC_SCHEMA"),
    ("owner missing", _set("owner", _DELETE), "PC_SCHEMA"),
    ("untrusted var without max_chars", _set("variables.0.max_chars", _DELETE), "PC_SCHEMA"),
    ("changelog without eval_run", _set("changelog.0.eval_run", _DELETE), "PC_SCHEMA"),
    ("duplicate changelog version", lambda c: c["changelog"].append(dict(c["changelog"][0])), "PC_CHANGELOG_ORDER"),
    ("domain not published", _set("name", "legal.triage.classification.system"), "PC_DOMAIN"),
    ("undeclared variable", _tpl("{{user_message}}", "{{user_message}} {{account_id}}"), "PC_VAR_UNDECLARED"),
    ("unused variable", lambda c: c["variables"].append({"name": "locale", "trust": "trusted", "pii": "none"}), "PC_VAR_UNUSED"),
    ("untrusted slot undelimited", _tpl("<user_input>\n{{user_message}}\n</user_input>", "{{user_message}}"), "PC_UNTRUSTED_UNDELIMITED"),
    ("untrusted slot before CONTEXT", _tpl("[TASK]\n", "[TASK]\n<user_input>{{user_message}}</user_input>\n"), "PC_UNTRUSTED_OUTSIDE_CONTEXT"),
    ("template logic", _tpl("{{canonical_state}}", "{{#canonical_state}}x{{/canonical_state}}"), "PC_TEMPLATE_LOGIC"),
    ("attribute access slot", _tpl("{{canonical_state}}", "{{canonical_state.__class__}}"), "PC_TEMPLATE_LOGIC"),
    ("ROLE section missing", _tpl("[ROLE]", "[TASK_TMP]"), "PC_ANATOMY_MISSING"),
    ("sections reordered", _swap("[OUTPUT]", "[CONSTRAINTS]"), "PC_ANATOMY_ORDER"),
    ("secret in template", _tpl("[OUTPUT]", f"{FAKE_KEY}\n[OUTPUT]"), "PC_SECRET"),
    ("PII in example", _example_email, "PC_EXAMPLE_PII"),
    ("example breaks output schema", _set("examples.0.output.priority", "URGENT"), "PC_EXAMPLE_SCHEMA"),
    ("static budget exceeded", _set("token_budget.static_max", 50), "PC_BUDGET_STATIC"),
    ("output budget exceeded", _set("model.params.max_output_tokens", 900), "PC_BUDGET_OUTPUT"),
    ("examples lack escalate case", lambda c: c.update(examples=c["examples"][:2]), "PC_EXAMPLE_COVERAGE"),
]
REVIEW_CASES: list[tuple[str, Callable[[dict], None], str]] = [
    ("constraints do not name the delimiter", _tpl("inside <user_input>; it", "inside the user block; it"), "PC_UNTRUSTED_NOT_DATA"),
    ("no uncertainty contract", _lowercase_statuses, "PC_UNCERTAINTY_CONTRACT"),
]


class Runner:
    def __init__(self) -> None:
        self.failures = 0
        self.count = 0

    def check(self, label: str, ok: bool, detail: object = "") -> None:
        self.count += 1
        self.failures += not ok
        vp.out(f"{'PASS' if ok else 'FAIL'}  {label}{'' if ok else f'  -> {detail}'}")

    def done(self, what: str) -> int:
        vp.out(f"{what} selftest: {self.count - self.failures}/{self.count} controls passed")
        return 1 if self.failures else 0


def _rules(rep: vp.Report, severity: str | None = None) -> set[str]:
    return {f.rule for f in rep.findings if severity is None or f.severity == severity}


def _main_exit(fn: Callable[[list[str]], int], argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(argv)


def run_validator_selftest() -> int:
    r = Runner()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        base = vp.validate(_tree(tmp), None, None)
        r.check("positive: scaffold has no BLOCK", not _rules(base, "BLOCK"), [f.message for f in base.findings])
        r.check("positive: scaffold placeholders flagged REVIEW", "PC_PLACEHOLDER" in _rules(base, "REVIEW"))
        r.check("positive: scaffold exit 0 (non-strict)", _main_exit(vp.main, [str(tmp / "prompts")]) == 0)
        r.check("negative: scaffold exit 1 with --strict (placeholders)", _main_exit(vp.main, [str(tmp / "prompts"), "--strict"]) == 1)
        for i, (label, mutate, rule) in enumerate(VALIDATOR_CASES):
            rep = vp.validate(_tree(tmp, mutate, f"v{i}"), None, None)
            r.check(f"negative: {label} -> {rule}", rule in _rules(rep, "BLOCK"), sorted(_rules(rep)))
        for i, (label, mutate, rule) in enumerate(REVIEW_CASES):
            rep = vp.validate(_tree(tmp, mutate, f"r{i}"), None, None)
            r.check(f"negative: {label} -> {rule} (REVIEW)", rule in _rules(rep, "REVIEW") and not _rules(rep, "BLOCK"), sorted(_rules(rep)))
        moved = _tree(tmp, None, "moved")
        _move(moved)
        r.check("negative: path does not mirror name -> PC_PATH", "PC_PATH" in _rules(vp.validate(moved, None, None), "BLOCK"))
        golden = tmp / "golden"
        golden.mkdir()
        (golden / "cases.jsonl").write_text(json.dumps({"input": "  I was charged TWICE for my subscription this month. "}) + "\n")
        r.check("negative: example reused as eval case -> PC_EXAMPLE_EVAL_OVERLAP",
                "PC_EXAMPLE_EVAL_OVERLAP" in _rules(vp.validate(_tree(tmp, None, "ov"), None, golden), "BLOCK"))
        dup = "  I was charged TWICE for my subscription this month. "
        layouts = {
            "user_message (yaml)": ("cases.yaml", yaml.safe_dump({"cases": [{"input": {"user_message": dup}}]})),
            "planted_content (yaml)": ("cases.yaml", yaml.safe_dump({"cases": [{"input": {"planted_content": dup}}]})),
            "turns list (jsonl)": ("cases.jsonl", json.dumps({"input": {"turns": ["hello", dup]}}) + "\n"),
            "question column (csv)": ("rag.csv", "case_id,question,expected_answer\nc-1,\"" + dup + "\",x\n"),
        }
        for label, (fname, body) in layouts.items():
            alt = tmp / f"golden_{len(fname)}_{abs(hash(label)) % 10_000}"
            alt.mkdir()
            (alt / fname).write_text(body, encoding="utf-8")
            r.check(f"negative: planted duplicate in {label} -> PC_EXAMPLE_EVAL_OVERLAP",
                    "PC_EXAMPLE_EVAL_OVERLAP" in _rules(vp.validate(_tree(tmp, None, "ov_" + label[:4].strip()), None, alt), "BLOCK"))
        (tmp / "empty").mkdir()
        r.check("negative: empty tree -> PC_NO_PROMPTS (no vacuous pass)", "PC_NO_PROMPTS" in _rules(vp.validate(tmp / "empty", None, None)))
        r.check("negative: missing root -> exit 2", _main_exit(vp.main, [str(tmp / "absent")]) == 2)
        r.check("negative: BLOCK -> exit 1", _main_exit(vp.main, [str(tmp / "v0")]) == 1)
        _classify_controls(r, tmp)   # records through r.check; `r.failures += f()` would discard them
    return r.done("validate_prompts")


def _classify_controls(r: Runner, tmp: Path) -> None:
    old = vp.load(vp.SCAFFOLD / CARD_REL)

    def variant(fn: Callable[[dict], None], bump: bool = True) -> dict:
        new = copy.deepcopy(old)
        fn(new)
        if bump:
            new["changelog"].append({**new["changelog"][-1], "version": new["changelog"][-1]["version"] + 1})
        return new

    cases = [
        ("owner change only", variant(_set("owner", "Someone Else"), bump=False), ["metadata_only"]),
        ("whitespace only", variant(_tpl("[TASK]\n", "[TASK]  \n")), ["formatting"]),
        ("task wording", variant(_tpl("Classify one inbound", "Classify exactly one inbound")), ["wording"]),
        ("escalation wording", variant(_tpl("takeover or a safety issue", "takeover, threats or a safety issue")),
         ["wording", "safety_wording"]),
        ("model version", variant(_set("model.version", "2026-10-01")), ["model_change"]),
        ("new language", variant(_set("languages", ["en", "es"])), ["new_language"]),
        ("examples", variant(lambda c: c["examples"].pop()), ["few_shot_examples"]),
        ("output schema", variant(_set("output_schema", "support_triage@3")), ["output_schema"]),
        ("generation params", variant(_set("model.params.temperature", 0.2)), ["model_change"]),
        ("citation wording", variant(_tpl("Use only the information", "Cite the source_id of the information")),
         ["wording", "rag_citation"]),
        ("tool list", variant(_set("tools", ["lookup_order"])), ["tools"]),
    ]
    for label, new, expected in cases:
        got = vp.classify_change(old, new)
        r.check(f"classify: {label} -> {expected}", got == expected, got)
    with_tool = variant(_set("tools", ["lookup_order"]), bump=False)
    named = copy.deepcopy(with_tool)
    _tpl("Respond in English.", "Call lookup_order first. Respond in English.")(named)
    got = vp.classify_change(with_tool, named)
    r.check("classify: tool named in changed wording -> ['wording', 'tools']", got == ["wording", "tools"], got)
    r.check("classify: every class in the change matrix has an eval list",
            set(vp.CHANGE_EVALS) == {"metadata_only", "formatting", "wording", "output_schema", "few_shot_examples",
                                     "safety_wording", "rag_citation", "tools", "model_change", "new_language",
                                     "new_prompt"}, sorted(vp.CHANGE_EVALS))
    r.check("classify: new prompt", vp.classify_change(None, old) == ["new_prompt"])
    r.check("classify: model change requires red-team",
            "red-team" in vp.CHANGE_EVALS[vp.classify_change(old, cases[4][1])[0]])
    base = _tree(tmp, None, "cls_base")
    head = _tree(tmp, _tpl("Classify one inbound", "Classify exactly one inbound"), "cls_head")
    _, findings = vp.classify(base, head)
    r.check("negative: behaviour change without changelog bump -> PC_CHANGELOG_NOT_BUMPED",
            any(f.rule == "PC_CHANGELOG_NOT_BUMPED" for f in findings))
    gone = tmp / "cls_gone"
    gone.mkdir()
    (gone / "domains.yaml").write_text("allowed_domains: [support]\n", encoding="utf-8")
    other = gone / "support" / "faq" / "answer.system.yaml"
    other.parent.mkdir(parents=True)
    other.write_text(yaml.safe_dump({**old, "name": "support.faq.answer.system"}, sort_keys=False), encoding="utf-8")
    changes, findings = vp.classify(base, gone)
    r.check("classify: removed prompt -> removed + PC_PROMPT_REMOVED (REVIEW)",
            changes["support.triage.classification.system"]["classes"] == ["removed"]
            and any(f.rule == "PC_PROMPT_REMOVED" and f.severity == "REVIEW" for f in findings), changes)


def _snapshot(card_hash: str, **over: object) -> dict:
    entry = {"name": "support.triage.classification.system", "labels": {"production": 1, "staging": 1},
             "versions": [{"version": 1, "content_hash": card_hash, "created_at": "2026-11-01T10:00:00+00:00"}]}
    entry.update(over)
    return {"prompts": [entry]}


def run_drift_selftest() -> int:
    r = Runner()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        git = prompt_drift.git_state(_tree(tmp))
        h = git["support.triage.classification.system"]["hash"]
        other = "sha256:" + "0" * 64

        def rules(snap: dict, mode: str = "scheduled", traces: list | None = None, days: int = 7) -> set[str]:
            return {f.rule for f in prompt_drift.detect(git, snap, traces or [], mode, days, TODAY)}

        ok_traces = [{"prompt_name": "support.triage.classification.system", "prompt_version": 1}]
        r.check("positive: in-sync snapshot + labelled traces -> no findings",
                rules(_snapshot(h), "prerelease", ok_traces) == set(), rules(_snapshot(h), "prerelease", ok_traces))
        stale = _snapshot(h, labels={"production": 1, "staging": 1},
                          versions=[{"version": 1, "content_hash": other, "created_at": "2026-10-01T00:00:00+00:00"},
                                    {"version": 2, "content_hash": h, "created_at": "2026-11-01T00:00:00+00:00"}])
        r.check("negative: staging != Git before release -> DRIFT_STAGING_MISMATCH",
                "DRIFT_STAGING_MISMATCH" in rules(stale, "prerelease"))
        r.check("control: same snapshot on schedule -> no BLOCK rule", "DRIFT_STAGING_MISMATCH" not in rules(stale))
        r.check("negative: labelled version unknown to Git -> DRIFT_REGISTRY_EDIT", "DRIFT_REGISTRY_EDIT" in rules(stale))
        r.check("negative: production behind Git > 7 days -> DRIFT_PRODUCTION_BEHIND", "DRIFT_PRODUCTION_BEHIND" in rules(stale))
        r.check("control: within 30-day window -> no DRIFT_PRODUCTION_BEHIND", "DRIFT_PRODUCTION_BEHIND" not in rules(stale, days=30))
        known = _tree(tmp, lambda c: c["changelog"][0].update(content_hash=other), "known")
        git_known = prompt_drift.git_state(known)
        r.check("control: older hash recorded in changelog -> not a registry edit",
                "DRIFT_REGISTRY_EDIT" not in {f.rule for f in prompt_drift.detect(git_known, stale, [], "scheduled", 30, TODAY)})
        no_stamp = json.loads(json.dumps(stale))
        for v in no_stamp["prompts"][0]["versions"]:
            v["created_at"] = None
        r.check("negative: behind with no timestamps -> DRIFT_AGE_UNKNOWN (no crash)", "DRIFT_AGE_UNKNOWN" in rules(no_stamp))
        r.check("negative: Git content never synced -> DRIFT_NOT_SYNCED",
                "DRIFT_NOT_SYNCED" in rules(_snapshot(other)))
        orphan = _snapshot(h)
        orphan["prompts"].append({"name": "support.ui_only.draft.system", "labels": {}, "versions": []})
        r.check("negative: registry-only prompt -> DRIFT_REGISTRY_ORPHAN", "DRIFT_REGISTRY_ORPHAN" in rules(orphan))
        bad_trace = [{"prompt_name": "support.triage.classification.system", "prompt_version": 9}]
        r.check("negative: trace version at no label -> DRIFT_TRACE_UNLABELED",
                "DRIFT_TRACE_UNLABELED" in rules(_snapshot(h), traces=bad_trace))
        snap_file = tmp / "snap.json"
        snap_file.write_text(json.dumps(stale))
        argv = ["--prompts-root", str(tmp / "prompts"), "--registry", str(snap_file), "--today", TODAY.isoformat()]
        r.check("exit: prerelease mismatch -> 1", _main_exit(prompt_drift.main, [*argv, "--mode", "prerelease"]) == 1)
        r.check("exit: scheduled REVIEW-only -> 0", _main_exit(prompt_drift.main, argv) == 0)
        r.check("exit: scheduled --strict -> 1", _main_exit(prompt_drift.main, [*argv, "--strict"]) == 1)
        (tmp / "empty").mkdir()
        r.check("exit: no prompt files -> 2 (no vacuous pass)",
                _main_exit(prompt_drift.main, ["--prompts-root", str(tmp / "empty"), "--registry", str(snap_file)]) == 2)
    return r.done("prompt_drift")
