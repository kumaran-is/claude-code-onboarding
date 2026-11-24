#!/usr/bin/env python3
"""check-ai-assets.py: deterministic gate over AI evaluation, prompt and governance assets.

Activation is by what exists: a project with no golden data, prompt files, governance records or
AI code is NOT_APPLICABLE and exits 0. Every finding carries one level:

  BLOCK          deterministic violation; exit 1 (CI fails, merge blocked)
  REVIEW         a human decides and records the decision; exit 0 (exit 1 with --strict)
  ADVISORY       pattern-based signal that cannot prove semantics; never fails
  NOT_APPLICABLE nothing in scope was found

Delegates (one owner per rule, never re-implemented here):
  golden trees      -> .claude/skills/eval-guide/scripts/validate_golden.py (manifests, case schemas,
                       unmanifested files, PII patterns, sizes, red-team coverage); run with `uv run --script`
  prompt cards      -> .claude/skills/prompt-engineering-patterns/scripts/validate_prompts.py (prompts/<domain>/
                       <feature>/<task>.<type>.yaml: schema, name/path mirror, slots, secrets, budgets); `uv run --script`
  governance records -> .claude/skills/ai-governance/scripts/validate_governance_record.py (JSON files whose
                       top-level `record_type` is a governance type)
  model registries   -> .claude/skills/agentic-ai-dev/scripts/validate_model_registry.py (*model-registry*.json or
                       top-level registry_version + routing_policy_version + entries)
  memory items       -> .claude/skills/agentic-ai-dev/scripts/validate_memory_item.py (*.memory.json, memory_items/,
                       top-level memory_items, or memory_type + org_id); stdlib validators run on this python3
  secrets also cover every prompt-text file under prompts/ (.md, .txt, .j2, few-shot JSON), not only prompt cards
  secrets            -> .claude/hooks/post-edit-secrets-scan.sh --scan-files (single token table)
A delegate that is missing, cannot run or exits 2 makes the run BLOCKED (exit 3), never PASS.
Own rules: prompt label `latest` (BLOCK), prompt reference with no Git prompt file (REVIEW), unpinned model id
(alias/preview, REVIEW), LiteLLM Router fallback defaults (REVIEW), and the pattern-only code signals shared with
the post-edit-ai-patterns.sh hook (ADVISORY). In --file mode (the edit hook) every finding prints as ADVISORY.

Usage:
  check-ai-assets.py [--root DIR] [--json FILE] [--strict]   scan a project tree
  check-ai-assets.py --file PATH                             per-file code signals (edit hook), exit 0
  check-ai-assets.py --selftest                              positive + negative controls
Exit codes: 0 PASS / REVIEW / NOT_APPLICABLE, 1 BLOCK (or REVIEW with --strict), 2 usage, 3 BLOCKED.
Rules: eval-guide ci-tiers.md (L2 PR gates), golden-dataset.md, prompt-engineering-patterns promptops-lifecycle.md; guardrails G2, G4, G9, G11; governance §5.1, §14.2; prompt standard §7-§8;
model-selection-routing standard (pinned versions, explicit fallbacks).
"""

# Runs under whatever python3 the developer has (macOS ships 3.9): lazy annotations keep `X | None` legal there.
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parents[2]
SECRETS_SCANNER = TOOLKIT_ROOT / ".claude/hooks/post-edit-secrets-scan.sh"
GOLDEN_VALIDATOR = TOOLKIT_ROOT / ".claude/skills/eval-guide/scripts/validate_golden.py"
GOVERNANCE_VALIDATOR = TOOLKIT_ROOT / ".claude/skills/ai-governance/scripts/validate_governance_record.py"
PROMPT_VALIDATOR = TOOLKIT_ROOT / ".claude/skills/prompt-engineering-patterns/scripts/validate_prompts.py"
REGISTRY_VALIDATOR = TOOLKIT_ROOT / ".claude/skills/agentic-ai-dev/scripts/validate_model_registry.py"
MEMORY_VALIDATOR = TOOLKIT_ROOT / ".claude/skills/agentic-ai-dev/scripts/validate_memory_item.py"
# Command prefixes for the delegates; the selftest swaps in stubs to prove the exit-code mapping.
UV_RUNNER = ["uv", "run", "--quiet", "--script"]   # PEP 723 validators (golden, prompts) pin their own Python
GOVERNANCE_RUNNER = [sys.executable]   # stdlib JSON-record validators (governance, model registry, memory items)

# `.claude/` holds toolkit skills, examples and fixtures, not the project's own assets.
SKIP_DIRS = {".claude", ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".dart_tool",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage", ".next", "target"}
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".java", ".dart"}
MAX_RECORD_BYTES = 1_000_000
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|e2e|fixtures)/|(^|/)test_[^/]*$|[._](test|spec)\.[a-z]+$")

# --- code signals (ADVISORY: co-occurrence in a file cannot prove what the code does) ---
RETRIEVAL_FN = re.compile(
    r"\b(a?similarity_search\w*|as_retriever|max_marginal_relevance_search|near_text|near_vector|"
    r"query\.hybrid|query\.bm25)\s*\(")
# pgvector distance operators count only on a line that also reads like a vector query (not prose such as "a <-> b")
VECTOR_SQL_LINE = re.compile(r"(?im)^(?=.*(?:<=>|<->|<#>))(?=.*\b(?:order\s+by|embedding|vector)\b).*$")
SCOPE_TOKEN = re.compile(r"tenant|org_id|orgId|organization_id|owner_id|ownerId|principal|acl\b|"
                         r"user_id|userId|account_id|accountId|filters?\s*=", re.IGNORECASE)
TOOL_DECL = re.compile(r"@tool\b|@\w+\.tool\b|FunctionTool\s*\(|StructuredTool|registerTool\s*\(|"
                       r"\.tool\s*\(\s*['\"]|@Tool\b")
MUTATING_NAME = re.compile(r"\b(def|async def|function|const|registerTool\s*\(\s*['\"]|name\s*[:=]\s*['\"])"
                           r"\s*_?(create|update|delete|remove|send|pay|transfer|refund|cancel|approve|"
                           r"submit|write|post|publish|charge|book|grant|revoke)\w*", re.IGNORECASE)
IDEMPOTENCY_TOKEN = re.compile(r"idempoten", re.IGNORECASE)
AUTHZ_TOKEN = re.compile(r"authori[sz]|principal|permission|require_scope|check_access|can_\w+\(|policy",
                         re.IGNORECASE)
# --- prompt references (eval §9: registry.get(name, label); never `latest`) ---
LATEST_LABEL = re.compile(r"""label\s*[=:]\s*['"]latest['"]""")
PROMPT_REF = re.compile(r"""\b\w*(prompts?|registry)\.get\(\s*['"]([a-z0-9_-]+(?:\.[a-z0-9_-]+){2,})['"]""",
                        re.IGNORECASE)
PROMPT_NAME_LINE = re.compile(r"""^name:\s*['"]?([A-Za-z0-9_.-]+)['"]?\s*$""", re.MULTILINE)
# --- model ids (model-selection-routing standard: pinned versions, resolver-owned literals, explicit fallbacks) ---
UNPINNED_MODEL = re.compile(r"(^|[-_.@:/])(latest|default|preview|exp)($|[-_.@:/])", re.IGNORECASE)
MODEL_ASSIGN = re.compile(r"""(?im)\b[a-z_]*model(?:_?id|_?name)?["']?[ \t]*[:=][ \t]*["']?([A-Za-z0-9][A-Za-z0-9._/@:-]*)""")
MODEL_LITERAL = re.compile(r"""["']((?:models/)?(?:(?:gemini|gpt|claude|llama|mistral|gemma|command-r|text-embedding)"""
                           r"""-[A-Za-z0-9._/@:-]+|o[1-9](?:-[A-Za-z0-9._-]+)?))["']""", re.IGNORECASE)
MODEL_HOME = re.compile(r"(client|resolver|rout|gateway|registry|config|settings|constants|catalog)[^/]*$",
                        re.IGNORECASE)
LITELLM_ROUTER = re.compile(r"\bRouter\s*\(")
LITELLM_DEFAULT_FB = re.compile(r"\bdefault_fallbacks\s*=")
LITELLM_GENERIC_FB = re.compile(r"\bfallbacks\s*=")   # \b: not default_/content_policy_/context_window_fallbacks
LITELLM_ERROR_FB = [re.compile(r"\bcontent_policy_fallbacks\s*="), re.compile(r"\bcontext_window_fallbacks\s*=")]
LITELLM_SAFE = re.compile(r"\bfallback_on_unsupported_params\s*=\s*False\b")
PROMPT_TEXT_EXT = {".yaml", ".yml", ".md", ".txt", ".j2", ".jinja", ".jinja2", ".prompt", ".json", ".jsonl"}
CONFIG_EXT = {".yaml", ".yml", ".toml", ".json", ".properties"}
ENV_TEMPLATE = re.compile(r"^\.env\.(example|sample|template)$")   # real .env files are never read


class Report:
    def __init__(self) -> None:
        self.findings: list[dict[str, str]] = []
        self.blocked: list[str] = []
        self.notes: list[str] = []
        self.scanned: dict[str, int] = {"golden_trees": 0, "prompt_files": 0, "prompt_text_files": 0,
                                        "governance_files": 0, "model_registry_files": 0, "memory_files": 0,
                                        "notebooks_and_eval_reports": 0, "model_config_files": 0,
                                        "ai_code_files": 0}

    def add(self, level: str, code: str, path: str, message: str) -> None:
        self.findings.append({"level": level, "code": code, "path": path, "message": message})

    def verdict(self, strict: bool) -> tuple[str, int]:
        levels = {f["level"] for f in self.findings}
        if self.blocked:
            return "BLOCKED", 3
        if "BLOCK" in levels:
            return "BLOCK", 1
        if "REVIEW" in levels:
            return "REVIEW", 1 if strict else 0
        if not any(self.scanned.values()):
            return "NOT_APPLICABLE", 0
        return "PASS", 0


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def walk(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        out.extend(Path(dirpath) / f for f in sorted(filenames))
    return out


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def has_retrieval(text: str) -> bool:
    return bool(RETRIEVAL_FN.search(text) or VECTOR_SQL_LINE.search(text))


def unpinned_models(text: str, literal_only: bool) -> list[tuple[int, str]]:
    hits = list(MODEL_LITERAL.finditer(text)) + ([] if literal_only else list(MODEL_ASSIGN.finditer(text)))
    seen: dict[int, str] = {}
    for m in hits:
        if UNPINNED_MODEL.search(m.group(1)):
            seen.setdefault(text.count("\n", 0, m.start()) + 1, m.group(1))
    return sorted(seen.items())


def model_signals(text: str, shown: str, report: Report, is_code: bool) -> bool:
    """Model-id and routing signals; returns True when the file references models at all."""
    if TEST_PATH.search(shown.replace(os.sep, "/")):
        return False
    literals = list(MODEL_LITERAL.finditer(text))
    for line, model in unpinned_models(text, literal_only=is_code):
        report.add("REVIEW", "MODEL_UNPINNED", f"{shown}:{line}",
                   f"model id '{model}' is an alias or preview, not a pinned version (routing standard; guardrail G11). "
                   "Allowed only inside an approved, recorded experiment.")
    if is_code and literals and not MODEL_HOME.search(shown):
        line = text.count("\n", 0, literals[0].start()) + 1
        report.add("ADVISORY", "MODEL_LITERAL_IN_BUSINESS_LOGIC", f"{shown}:{line}",
                   f"{len(literals)} model id literal(s) outside a client/resolver/config module; resolve models "
                   "through the routing resolver. Pattern-only.")
    if is_code and "litellm" in text and LITELLM_ROUTER.search(text):
        reasons = [why for why, hit in (
            ("default_fallbacks is set", LITELLM_DEFAULT_FB.search(text)),
            ("fallback_on_unsupported_params=False is missing (default True serves a 400 from the fallback model)",
             not LITELLM_SAFE.search(text)),
            ("fallbacks= without explicit content_policy_fallbacks= and context_window_fallbacks= (unset, those "
             "errors fall through to the generic fallbacks)",
             LITELLM_GENERIC_FB.search(text) and not all(rx.search(text) for rx in LITELLM_ERROR_FB)))
            if hit]
        if reasons:
            report.add("REVIEW", "LITELLM_ROUTER_FALLBACK", shown,
                       "LiteLLM Router (litellm 1.110.2): " + "; ".join(reasons) + ". Pattern-only: it cannot prove "
                       "the values; the safe form is an explicit empty list per group for those error classes.")
    return bool(literals) or "litellm" in text


def code_signals(text: str, shown: str, report: Report) -> None:
    """Signals for one source file. ADVISORY except a `latest` prompt label, a deterministic token (BLOCK)."""
    if TEST_PATH.search(shown.replace(os.sep, "/")):
        return
    if has_retrieval(text) and not SCOPE_TOKEN.search(text):
        report.add("ADVISORY", "RETRIEVAL_WITHOUT_SCOPE_FILTER", shown,
                   "vector/hybrid retrieval call with no tenant/principal/ACL filter token in the file; "
                   "authorize before retrieval (guardrail G9). Pattern-only: verify the filter is in the query.")
    if TOOL_DECL.search(text) and MUTATING_NAME.search(text):
        missing = [name for name, rx in (("idempotency key", IDEMPOTENCY_TOKEN), ("authorization", AUTHZ_TOKEN))
                   if not rx.search(text)]
        if missing:
            report.add("ADVISORY", "STATE_CHANGING_TOOL_UNGUARDED", shown,
                       "state-changing tool declared with no " + " or ".join(missing) + " marker in the file "
                       "(guardrails G2, G4; governance §5.1). Pattern-only: verify server-side enforcement.")
    for match in LATEST_LABEL.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        report.add("BLOCK", "PROMPT_LABEL_LATEST", f"{shown}:{line}",
                   "prompt fetched with label 'latest'; fetch by deployment label (eval §9, guardrail G11).")


def run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str] | None:
    try:
        # delegates import each other by file path; keep their __pycache__ out of the toolkit tree
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=False, env=env)
    except OSError:
        return None


def tail(proc: subprocess.CompletedProcess[str]) -> str:
    return " | ".join((proc.stderr.strip() or proc.stdout.strip()).splitlines()[-3:])


def check_uv_tree(kind: str, validator: Path, tree: Path, root: Path, report: Report,
                  extra: tuple[str, ...] = ()) -> None:
    """Run a PEP 723 tree validator (golden data, prompt cards) and map its JSON findings 1:1."""
    shown = rel(tree, root)
    if not validator.is_file() or shutil.which(UV_RUNNER[0]) is None:
        report.blocked.append(f"{kind} validator cannot run for {shown} (needs {UV_RUNNER[0]} and "
                              f"{rel(validator, TOOLKIT_ROOT)})")
        return
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{kind}.json"
        proc = run([*UV_RUNNER, str(validator), str(tree), *extra, "--json", str(out)])
        if proc is None or proc.returncode not in (0, 1):
            report.blocked.append(f"{kind} validator exited {proc.returncode if proc else 'OSError'} on {shown}"
                                  + (f": {tail(proc)}" if proc else ""))
            return
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report.blocked.append(f"{kind} validator wrote no readable JSON report for {shown}")
            return
    findings = data.get("findings")
    if not isinstance(findings, list) or (proc.returncode == 1 and not findings):
        report.blocked.append(f"{kind} validator report for {shown} is inconsistent with its exit code")
        return
    for f in findings:
        level = f.get("severity") if f.get("severity") in ("BLOCK", "REVIEW", "ADVISORY") else "BLOCK"
        where = f"{shown}/{f.get('path', '')}".rstrip("/")
        case = f" [{f['case_id']}]" if f.get("case_id") else ""
        report.add(level, f"{kind}_{f.get('rule', 'FINDING')}".upper(), where, f"{f.get('message', '')}{case}")


def governance_types(report: Report) -> set[str]:
    if not GOVERNANCE_VALIDATOR.is_file():
        report.blocked.append(f"governance validator not found at {rel(GOVERNANCE_VALIDATOR, TOOLKIT_ROOT)}")
        return set()
    proc = run([*GOVERNANCE_RUNNER, str(GOVERNANCE_VALIDATOR), "--list-types"])
    if proc is None or proc.returncode != 0:
        report.blocked.append("governance validator --list-types failed" + (f": {tail(proc)}" if proc else ""))
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def check_records(kind: str, validator: Path, records: list[Path], root: Path, report: Report) -> None:
    """Run a stdlib JSON-record validator (`--json FILE...`, exit 0/1/2) and map invalid files to BLOCK."""
    report.scanned[f"{kind}_files"] = len(records)
    if not records:
        return
    if not validator.is_file():
        report.blocked.append(f"{kind} validator not found at {rel(validator, TOOLKIT_ROOT)}")
        return
    proc = run([*GOVERNANCE_RUNNER, str(validator), "--json", *map(str, records)])
    if proc is None or proc.returncode not in (0, 1):
        report.blocked.append(f"{kind} validator exited {proc.returncode if proc else 'OSError'}"
                              + (f": {tail(proc)}" if proc else ""))
        return
    try:
        data = json.loads(proc.stdout)
        results = data["results"] if "results" in data else data["files"]
    except (json.JSONDecodeError, KeyError, TypeError):
        report.blocked.append(f"{kind} validator printed no readable JSON report"
                              + ("" if proc.returncode == 0 else f": {tail(proc)}"))
        return
    invalid = [r for r in results if not r.get("valid")]
    if (proc.returncode == 1) != bool(invalid) or len(results) != len(records):
        report.blocked.append(f"{kind} validator report is inconsistent with its exit code or inputs")
        return
    scope = data.get("scope") or data.get("scope_note") or (data.get("summary") or {}).get("scope")
    if scope:
        report.notes.append(f"{kind}: {scope}")   # a valid record is not proof of adoption or effectiveness
    for r in invalid:
        errors = "; ".join(f"{e.get('code', '')} {e.get('path') or e.get('pointer')}: {e.get('message')}".strip()
                           for e in r.get("errors", [])[:3])
        report.add("BLOCK", f"{kind.upper()}_RECORD_INVALID", rel(Path(r.get("file") or r.get("path") or ""), root),
                   f"{r.get('record_type', kind)}: {errors}")


def record_kinds(path: Path, doc: object, gov_types: set[str]) -> str | None:
    """Which JSON-record validator owns this file (detection rules from each validator's owner)."""
    keys = set(doc) if isinstance(doc, dict) else set()
    if isinstance(doc, dict) and doc.get("record_type") in gov_types:
        return "governance"
    if "model-registry" in path.name or {"registry_version", "routing_policy_version", "entries"} <= keys:
        return "model_registry"
    if (path.name.endswith(".memory.json") or path.parent.name == "memory_items" or "memory_items" in keys
            or {"memory_type", "org_id"} <= keys):
        return "memory"
    return None


def scan_secrets(paths: list[Path], root: Path, report: Report) -> None:
    if not paths:
        return
    if not SECRETS_SCANNER.is_file() or shutil.which("bash") is None:
        report.blocked.append("secrets scanner (post-edit-secrets-scan.sh --scan-files) unavailable")
        return
    # one path per line, newline-terminated: bash `read` drops an unterminated last line
    proc = run(["bash", str(SECRETS_SCANNER), "--scan-files"], stdin="".join(f"{p}\n" for p in paths))
    if proc is None or proc.returncode != 0:
        report.blocked.append(f"secrets scanner exited {proc.returncode if proc else 'OSError'}")
        return
    for line in proc.stdout.splitlines():
        path, _, label = line.partition("\t")
        report.add("BLOCK", "SECRET_IN_AI_ASSET", rel(Path(path), root),
                   f"{label} in a prompt, golden-data, notebook or eval-report file (value not printed).")


def scan_tree(root: Path) -> Report:
    report = Report()
    files = walk(root)
    parts = {p: p.relative_to(root).parts for p in files}
    golden_files = [p for p in files if "golden" in parts[p][:-1]]
    golden_roots = sorted({root.joinpath(*parts[p][:parts[p].index("golden") + 1]) for p in golden_files})
    prompts = [p for p in files if "prompts" in parts[p][:-1] and p.suffix in {".yaml", ".yml"}
               and p.name != "domains.yaml" and not any(d.startswith("_") for d in parts[p][:-1])]
    json_files = [p for p in files if p.suffix == ".json" and p.stat().st_size <= MAX_RECORD_BYTES]
    report.scanned["golden_trees"] = len(golden_roots)
    report.scanned["prompt_files"] = len(prompts)

    for golden_root in golden_roots:
        check_uv_tree("golden", GOLDEN_VALIDATOR, golden_root, root, report)
    # prompt standard §7-§8: prompt cards validated by their owner's validator; `_`-prefixed dirs hold schemas
    prompt_roots = sorted({root.joinpath(*parts[p][:parts[p].index("prompts") + 1]) for p in prompts})
    golden_arg = ("--golden-root", str(golden_roots[0])) if len(golden_roots) == 1 else ()
    for prompt_root in prompt_roots:
        check_uv_tree("prompt", PROMPT_VALIDATOR, prompt_root, root, report, golden_arg)
    markers = (b'"record_type"', b'"registry_version"', b'"memory_items"', b'"memory_type"')
    docs: dict[Path, object] = {}
    for p in json_files:
        if (any(mk in p.read_bytes() for mk in markers) or "model-registry" in p.name
                or p.name.endswith(".memory.json") or p.parent.name == "memory_items"):
            try:
                docs[p] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                docs[p] = None   # the owning validator reports it (exit 2 -> BLOCKED) when the name claims a kind
    gov_types = governance_types(report) if any(isinstance(d, dict) and "record_type" in d
                                                for d in docs.values()) else set()
    by_kind: dict[str, list[Path]] = {"governance": [], "model_registry": [], "memory": []}
    for p, doc in docs.items():
        kind = record_kinds(p, doc, gov_types)
        if kind:
            by_kind[kind].append(p)
    for kind, validator in (("governance", GOVERNANCE_VALIDATOR), ("model_registry", REGISTRY_VALIDATOR),
                            ("memory", MEMORY_VALIDATOR)):
        check_records(kind, validator, by_kind[kind], root, report)
    # security playbook §13: secret scanning covers prompt files, golden datasets, notebooks and eval reports
    eval_dirs = {"evals", "eval", "eval_reports", "eval-results"}
    report_ext = {".json", ".jsonl", ".csv", ".yaml", ".yml", ".md"}
    eval_outputs = [p for p in files if p.suffix == ".ipynb"
                    or (eval_dirs & set(parts[p][:-1]) and p.suffix in report_ext)]
    report.scanned["notebooks_and_eval_reports"] = len(eval_outputs)
    # every prompt-text file (templates, few-shot, .md/.txt/.j2), not only the YAML prompt cards
    prompt_text = [p for p in files if "prompts" in parts[p][:-1] and p.suffix in PROMPT_TEXT_EXT]
    report.scanned["prompt_text_files"] = len(prompt_text)
    scan_secrets(sorted(set(golden_files + prompts + prompt_text + eval_outputs)), root, report)

    declared: set[str] = set()
    for path in prompts:
        declared.update(PROMPT_NAME_LINE.findall(read_text(path) or ""))
        # prompt standard §7: prompts/<domain>/<feature>/<task>.<type>.yaml mirrors <domain>.<feature>.<task>.<type>
        under = parts[path][parts[path].index("prompts") + 1:]
        declared.add(".".join([*under[:-1], path.name.rsplit(".", 1)[0]]))
    skip_config = {"golden", "prompts", "tests", "test", "fixtures", "node_modules"}
    for path in files:
        if (path.suffix in CONFIG_EXT or ENV_TEMPLATE.match(path.name)) and not (skip_config & set(parts[path])):
            text = read_text(path) or ""
            if len(text) <= MAX_RECORD_BYTES and (MODEL_LITERAL.search(text) or MODEL_ASSIGN.search(text)):
                report.scanned["model_config_files"] += 1
                model_signals(text, rel(path, root), report, is_code=False)
    for path in (p for p in files if p.suffix in CODE_EXT):
        text = read_text(path)
        if text is None:
            continue
        shown = rel(path, root)
        uses_models = model_signals(text, shown, report, is_code=True)
        if not (uses_models or has_retrieval(text) or TOOL_DECL.search(text)
                or LATEST_LABEL.search(text) or PROMPT_REF.search(text)):
            continue
        report.scanned["ai_code_files"] += 1
        code_signals(text, shown, report)
        if prompts and not TEST_PATH.search(shown):
            for match in PROMPT_REF.finditer(text):
                if match.group(2) not in declared:
                    line = text.count("\n", 0, match.start()) + 1
                    report.add("REVIEW", "PROMPT_REFERENCE_UNRESOLVED", f"{shown}:{line}",
                               f"prompt '{match.group(2)}' has no Git prompt file under prompts/ (eval §9).")
    return report


def emit(report: Report, root: Path, strict: bool, json_path: str | None) -> int:
    verdict, code = report.verdict(strict)
    for f in report.findings:
        print(f"{f['level']:<8} {f['code']:<32} {f['path']}  {f['message']}")
    for reason in report.blocked:
        print(f"BLOCKED  {reason}")
    for note in report.notes:
        print(f"SCOPE    {note}")
    counts = ", ".join(f"{k}={v}" for k, v in report.scanned.items())
    print(f"check-ai-assets: root={root} scanned: {counts} findings={len(report.findings)} verdict={verdict}")
    if json_path:
        Path(json_path).write_text(json.dumps({
            "tool": "check-ai-assets", "root": str(root), "verdict": verdict, "exit_code": code,
            "scanned": report.scanned, "blocked": report.blocked, "findings": report.findings,
            "scope_notes": report.notes,
        }, indent=2) + "\n", encoding="utf-8")
    return code


def selftest() -> int:
    """Controls live in a sibling module to keep this gate short; it receives this module to patch delegates."""
    module_path = Path(__file__).resolve().with_name("check_ai_assets_selftest.py")
    spec = importlib.util.spec_from_file_location("check_ai_assets_selftest", module_path)
    if not module_path.is_file() or spec is None or spec.loader is None:
        print("selftest FAIL: check_ai_assets_selftest.py not found next to this script")
        return 1
    sys.dont_write_bytecode = True   # no __pycache__ next to the toolkit scripts
    controls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controls)
    return controls.run(sys.modules[__name__])


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--strict", action="store_true", help="REVIEW findings also exit 1")
    parser.add_argument("--file", help="per-file code signals (prints findings, always exit 0)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.file:
        text = read_text(Path(args.file))
        report = Report()
        if text is not None:
            model_signals(text, args.file, report, is_code=True)
            code_signals(text, args.file, report)
        for f in report.findings:   # the edit hook is advisory: pattern checks never block an edit
            print(f"ADVISORY {f['code']}: {f['path']} {f['message']}")
        return 0
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"check-ai-assets: root {root} is not a directory", file=sys.stderr)
        return 2
    return emit(scan_tree(root), root, args.strict, args.json_path)


if __name__ == "__main__":
    sys.exit(main())
