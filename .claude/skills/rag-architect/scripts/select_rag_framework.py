#!/usr/bin/env python3
"""Deterministic RAG framework selector (auto | google-adk | llamaindex | langchain).

Stdlib only. No network. Custom Python is never auto-selected.

  python3 select_rag_framework.py --selftest
  python3 select_rag_framework.py --requirements req.json
  python3 select_rag_framework.py --framework langchain --requirements req.json

Exit: 0 ok, 1 failed selftest or invalid input, 2 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SELECTABLE = ("google-adk", "llamaindex", "langchain")
ALLOWED_EXPLICIT = SELECTABLE + ("auto",)
COMPAT_ONLY = "custom-python"
COMPLEXITY = ("ordinary", "tables", "scans", "multimodal")
SIZES = ("small", "medium", "large")
UPDATES = ("static", "daily", "hourly", "realtime")
EXISTING = ("none", "google-adk", "llamaindex", "langchain", "custom-python")

DEFAULTS: dict[str, Any] = {
    "framework": "auto",
    "document_complexity": "ordinary",
    "corpus_size": "medium",
    "update_frequency": "daily",
    "ocr_needed": False,
    "multimodal": False,
    "agentic_workflows": False,
    "multi_source_tools": False,
    "existing_stack": "none",
    "hybrid_rerank": True,
    "citations_required": True,
    "tenancy": True,
    "data_must_stay_local": False,
    "llamaparse_approved": False,
}


def die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def as_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    die(f"invalid boolean for {key}: {value!r}", 1)
    raise AssertionError("unreachable")


def load_requirements(raw: dict[str, Any]) -> dict[str, Any]:
    req = dict(DEFAULTS)
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        die(f"unknown requirement keys: {', '.join(unknown)}", 1)
    req.update(raw)
    fw = str(req["framework"])
    if fw not in ALLOWED_EXPLICIT and fw != COMPAT_ONLY:
        die(f"framework must be auto|google-adk|llamaindex|langchain (got {fw!r})", 1)
    if req["document_complexity"] not in COMPLEXITY:
        die("document_complexity must be ordinary|tables|scans|multimodal", 1)
    if req["corpus_size"] not in SIZES:
        die("corpus_size must be small|medium|large", 1)
    if req["update_frequency"] not in UPDATES:
        die("update_frequency must be static|daily|hourly|realtime", 1)
    if req["existing_stack"] not in EXISTING:
        die("existing_stack must be none|google-adk|llamaindex|langchain|custom-python", 1)
    for key in (
        "ocr_needed",
        "multimodal",
        "agentic_workflows",
        "multi_source_tools",
        "hybrid_rerank",
        "citations_required",
        "tenancy",
        "data_must_stay_local",
        "llamaparse_approved",
    ):
        req[key] = as_bool(req[key], key)
    return req


def _scores(req: dict[str, Any]) -> dict[str, int]:
    scores = {name: 0 for name in SELECTABLE}
    existing = req["existing_stack"]
    if existing in SELECTABLE:
        scores[existing] += 4
    if req["agentic_workflows"] or req["multi_source_tools"]:
        scores["google-adk"] += 3
    complexity = req["document_complexity"]
    if complexity in {"tables", "scans"} or req["ocr_needed"]:
        scores["llamaindex"] += 3
    if complexity == "multimodal" or req["multimodal"]:
        scores["llamaindex"] += 2
    if req["corpus_size"] == "large" and complexity != "ordinary":
        scores["llamaindex"] += 1
    if existing == "none" and not req["agentic_workflows"] and complexity == "ordinary":
        scores["llamaindex"] += 1
    if existing == "langchain":
        scores["langchain"] += 1
    if existing == "custom-python":
        scores["langchain"] += 1  # nearest selectable; custom stays compatibility-only
    return scores


def _tie_break(req: dict[str, Any], scores: dict[str, int]) -> str:
    top = max(scores.values())
    tied = [name for name, score in scores.items() if score == top]
    if len(tied) == 1:
        return tied[0]
    if req["agentic_workflows"] and "google-adk" in tied:
        return "google-adk"
    if (
        req["document_complexity"] in {"tables", "scans", "multimodal"} or req["ocr_needed"]
    ) and "llamaindex" in tied:
        return "llamaindex"
    if req["existing_stack"] in tied:
        return str(req["existing_stack"])
    if "llamaindex" in tied:
        return "llamaindex"
    return tied[0]


def choose_parser(req: dict[str, Any], framework: str) -> dict[str, Any]:
    if framework != "llamaindex":
        return {
            "parser": "framework-default",
            "approval_required": False,
            "reason": "Parser choice applies to LlamaIndex document loading.",
        }
    if req["document_complexity"] == "ordinary" and not req["ocr_needed"] and not req["multimodal"]:
        return {
            "parser": "builtin-readers",
            "approval_required": False,
            "reason": "Ordinary digital text: SimpleDirectoryReader / built-in LlamaIndex readers.",
        }
    if req["llamaparse_approved"] and (
        req["document_complexity"] in {"tables", "scans", "multimodal"} or req["ocr_needed"]
    ):
        return {
            "parser": "llamaparse",
            "approval_required": False,
            "reason": "Hosted LlamaParse approved for complex/OCR documents.",
        }
    needs_hosted = req["document_complexity"] in {"tables", "scans", "multimodal"} or req["ocr_needed"]
    if needs_hosted and not req["llamaparse_approved"]:
        if req["data_must_stay_local"]:
            return {
                "parser": "liteparse",
                "approval_required": False,
                "reason": "Data must stay local: LiteParse. LlamaParse blocked without approval.",
            }
        return {
            "parser": "liteparse",
            "approval_required": True,
            "reason": "Start with LiteParse (local). LlamaParse needs explicit approval for data, credentials, and cost.",
        }
    return {
        "parser": "liteparse",
        "approval_required": False,
        "reason": "Local PDF/Office: LiteParse (no API key).",
    }


def select(req: dict[str, Any]) -> dict[str, Any]:
    explicit = str(req["framework"])
    reasons: list[str] = []
    compatibility_custom = req["existing_stack"] == "custom-python"

    if explicit == COMPAT_ONLY:
        return {
            "selected": COMPAT_ONLY,
            "selectable": False,
            "reasons": [
                "custom-python is a compatibility path for existing pipelines, not a selectable framework.",
                "New work must pick google-adk, llamaindex, or langchain.",
            ],
            "scores": {name: 0 for name in SELECTABLE},
            "parser": {
                "parser": "unchanged",
                "approval_required": False,
                "reason": "Preserve the existing custom parser.",
            },
            "compatibility_custom": True,
        }

    if explicit in SELECTABLE:
        selected = explicit
        reasons.append(f"Explicit framework={explicit} (user choice wins).")
        scores = _scores(req)
    else:
        scores = _scores(req)
        selected = _tie_break(req, scores)
        ranked = ", ".join(f"{name}={scores[name]}" for name in SELECTABLE)
        reasons.append(f"auto scores: {ranked}; selected {selected}.")
        if req["agentic_workflows"] or req["multi_source_tools"]:
            reasons.append("Agentic / multi-source tools favour google-adk.")
        if req["document_complexity"] != "ordinary" or req["ocr_needed"]:
            reasons.append("Document complexity / OCR favour llamaindex.")
        if req["existing_stack"] in SELECTABLE:
            reasons.append(f"Existing stack {req['existing_stack']} is weighted.")

    if not req["citations_required"] or not req["tenancy"]:
        reasons.append("citations_required and tenancy are mandatory in the shared RAG contract; do not disable them.")
    if compatibility_custom:
        reasons.append("Existing custom-python implementation is preserved; do not scaffold a second pipeline.")

    return {
        "selected": selected,
        "selectable": True,
        "reasons": reasons,
        "scores": scores,
        "parser": choose_parser(req, selected),
        "compatibility_custom": compatibility_custom,
    }


def format_report(result: dict[str, Any]) -> str:
    parser = result["parser"]
    lines = [
        f"SELECTED={result['selected']}",
        f"SELECTABLE={str(result['selectable']).lower()}",
        f"COMPAT_CUSTOM={str(result['compatibility_custom']).lower()}",
        f"PARSE={parser['parser']}",
        f"PARSE_APPROVAL_REQUIRED={str(parser['approval_required']).lower()}",
        f"SCORES={json.dumps(result['scores'], sort_keys=True)}",
    ]
    for reason in result["reasons"]:
        lines.append(f"REASON={reason}")
    lines.append(f"PARSE_REASON={parser['reason']}")
    return "\n".join(lines)


def selftest() -> int:
    fail = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal fail
        if cond:
            print(f"  ok   {label}")
        else:
            fail += 1
            print(f"  FAIL {label} {detail}")

    explicit = select(load_requirements({"framework": "langchain", "agentic_workflows": True}))
    check("explicit langchain wins over agentic ADK signals", explicit["selected"] == "langchain")

    adk = select(load_requirements({"framework": "auto", "agentic_workflows": True, "multi_source_tools": True}))
    check("auto + agentic → google-adk", adk["selected"] == "google-adk", str(adk["selected"]))

    li = select(
        load_requirements(
            {
                "framework": "auto",
                "document_complexity": "tables",
                "ocr_needed": True,
                "existing_stack": "none",
            }
        )
    )
    check("auto + tables/OCR → llamaindex", li["selected"] == "llamaindex", str(li["selected"]))
    check("tables without approval → LiteParse + approval flag", li["parser"]["parser"] == "liteparse" and li["parser"]["approval_required"] is True)

    hosted = select(
        load_requirements(
            {
                "framework": "llamaindex",
                "document_complexity": "scans",
                "ocr_needed": True,
                "llamaparse_approved": True,
            }
        )
    )
    check("approved LlamaParse for scans", hosted["parser"]["parser"] == "llamaparse")

    local = select(
        load_requirements(
            {
                "framework": "llamaindex",
                "document_complexity": "scans",
                "data_must_stay_local": True,
            }
        )
    )
    check("local data blocks hosted parse", local["parser"]["parser"] == "liteparse" and local["parser"]["approval_required"] is False)

    lc = select(load_requirements({"framework": "auto", "existing_stack": "langchain"}))
    check("existing langchain stack → langchain", lc["selected"] == "langchain")

    green = select(load_requirements({"framework": "auto"}))
    check("greenfield ordinary docs → llamaindex", green["selected"] == "llamaindex", str(green["selected"]))

    compat = select(load_requirements({"framework": "custom-python"}))
    check("custom-python is not selectable", compat["selectable"] is False and compat["selected"] == COMPAT_ONLY)

    ordinary = select(load_requirements({"framework": "llamaindex", "document_complexity": "ordinary"}))
    check("ordinary LlamaIndex uses builtin readers", ordinary["parser"]["parser"] == "builtin-readers")

    try:
        load_requirements({"framework": "haystack"})
        check("unknown framework rejected", False)
    except SystemExit as exc:
        check("unknown framework rejected", exc.code == 1)

    try:
        load_requirements({"surprise": True})
        check("unknown keys rejected", False)
    except SystemExit as exc:
        check("unknown keys rejected", exc.code == 1)

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 1 if fail else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--requirements", metavar="FILE", help="JSON object of requirement fields")
    parser.add_argument("--framework", choices=ALLOWED_EXPLICIT + (COMPAT_ONLY,))
    parser.add_argument("--json", action="store_true", help="print the result object as JSON")
    args = parser.parse_args(argv)

    if args.selftest:
        if args.requirements or args.framework:
            die("usage: --selftest cannot be combined with --requirements/--framework", 2)
        return selftest()

    raw: dict[str, Any] = {}
    if args.requirements:
        path = args.requirements
        if path == "-":
            raw = json.load(sys.stdin)
        else:
            try:
                raw = json.loads(__import__("pathlib").Path(path).read_text(encoding="utf-8"))
            except OSError as exc:
                die(f"cannot read {path}: {exc}", 1)
            except json.JSONDecodeError as exc:
                die(f"invalid JSON in {path}: {exc}", 1)
        if not isinstance(raw, dict):
            die("requirements JSON must be an object", 1)
    if args.framework:
        raw["framework"] = args.framework
    if not raw:
        die("usage: select_rag_framework.py --selftest | --requirements FILE [--framework NAME]", 2)

    result = select(load_requirements(raw))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
