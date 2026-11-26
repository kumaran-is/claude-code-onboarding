#!/usr/bin/env python3
"""Detect unauthorized weakening of quality-config files.

Not a ban on config edits: adding rules, raising thresholds, and unrelated
edits are allowed. Weakening (severity drop, skipLibCheck on, ignore-list
growth, coverage floor drop, CI quality-gate bypass) is a finding unless
the new text contains an auditable:

    quality-config-exception: <reason of 20+ characters>

Called from pre-edit-protect-sensitive.sh. Stdlib only.

Usage:
  python3 .claude/scripts/check-quality-config-weakening.py --selftest
  python3 .claude/scripts/check-quality-config-weakening.py --payload FILE --root DIR

Exit: 0 allow, 1 block (findings on stdout), 2 usage / broken selftest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

EXCEPTION_RE = re.compile(
    r"(?i)quality-config-exception:\s*(\S.{19,})",
)
QUALITY_NAME = re.compile(
    r"(?i)(^|/)("
    r"eslint\.config\.[cm]?[jt]s|"
    r"\.eslintrc(\.(json|js|cjs|ya?ml))?|"
    r"ruff\.toml|\.ruff\.toml|"
    r"pyproject\.toml|"
    r"analysis_options\.ya?ml|"
    r"tsconfig(\.[^/]+)?\.json|"
    r"(jest|vitest|karma)\.config\.[cm]?[jt]s|"
    r"\.nycrc(\.json)?|"
    r"codecov\.ya?ml|"
    r"\.coveragerc|"
    r"package\.json"
    r")$",
)
WORKFLOW_RE = re.compile(r"(?i)(^|/)\.github/workflows/[^/]+\.ya?ml$")
SKIP_DIR = re.compile(r"(^|/)(node_modules|\.venv|venv|dist|build|coverage)(/|$)")
QUALITY_CI = re.compile(
    r"(?i)(eslint|ruff|lint|coverage|cov-fail|pytest|vitest|jest|"
    r"dart analyze|flutter test|npm test|yarn test|pnpm test|"
    r"tsc |selftest|check-context-budget|"
    r"check-design-system|maven|gradle|analyze)",
)
SEV_RANK = {
    "error": 3,
    "2": 3,
    "warning": 2,
    "warn": 2,
    "1": 2,
    "info": 1,
    "off": 0,
    "ignore": 0,
    "0": 0,
    "false": 0,
}
RULE_SEV = re.compile(
    r"""(?x)
    (?P<q1>['"]?)
    (?P<rule>@?[\w./-]+)
    (?P=q1)
    \s*[:=]\s*
    (?P<q>['"]?)
    (?P<sev>error|warn(?:ing)?|off|ignore|info|false|0|1|2)
    (?P=q)
    """,
)
BOOL_TRUE_STRICT = {
    "strict",
    "noimplicitany",
    "strictnullchecks",
    "nounusedlocals",
    "nounusedparameters",
    "nofallthroughcasesinswitch",
    "noimplicitreturns",
    "nouncheckedindexedaccess",
    "exactoptionalpropertytypes",
    "alwaysstrict",
    "strictbindcallapply",
    "strictfunctiontypes",
    "strictpropertyinitialization",
    "noimplicitthis",
    "nopropertyaccessfromindexsignature",
    "noemitonerror",
    "fail-fast",
    "failfast",
}
BOOL_TRUE_WEAK = {
    "skiplibcheck",
    "skipdefaultlibcheck",
    "allowunreachablecode",
    "allowunusedlabels",
    "continue-on-error",
    "continueonerror",
}
LOWER_WEAKER = re.compile(
    r"(?i)(?:fail[_-]?under|cov-fail-under|--cov-fail-under|"
    r"branches|functions|lines|statements|coverageThreshold)\s*[:=]\s*(\d+)",
)
HIGHER_WEAKER = re.compile(
    r"(?i)(?:max-warnings|maxWarnings|max-errors|maxErrors)\s*[:=]\s*(\d+)",
)
IGNORE_BLOCK = re.compile(
    r"(?i)(?:ignore(?:s|Patterns)?|exclude|per-file-ignores|"
    r"coveragePathIgnorePatterns|testPathIgnorePatterns|"
    r"omit)\s*[:=]\s*[\[{]([^\]}]*)",
)
QUOTED = re.compile(r"""['"]([^'"]+)['"]""")
BOOL_KV = re.compile(
    r"""(?i)(['"]?)(?P<k>strict\w*|no[A-Z]\w+|skip\w+|allow\w+|fail-fast|failFast|"""
    r"""continue-on-error|continueOnError|noEmitOnError)\1\s*[:=]\s*"""
    r"""(['"]?)(?P<v>true|false)\3""",
)
PIPE_TRUE = re.compile(
    r"(?i)((?:eslint|ruff|pytest|vitest|jest|tsc|dart analyze|flutter test|"
    r"npm test|yarn test|pnpm test|npm run test|"
    r"check-context-budget|check-design-system|selftest)[^\n]{0,80})\|\|\s*true",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_path(path: str) -> str:
    return path.replace("\\", "/")


def is_quality_path(path: str) -> bool:
    p = norm_path(path)
    if SKIP_DIR.search(p):
        return False
    if QUALITY_NAME.search(p):
        return True
    if WORKFLOW_RE.search(p):
        return True
    return False


def has_exception(text: str) -> str | None:
    m = EXCEPTION_RE.search(text or "")
    if not m:
        return None
    reason = m.group(1).strip().strip("\"'")
    if len(reason) < 20:
        return None
    return reason[:240]


def _bool_map(text: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for m in BOOL_KV.finditer(text or ""):
        out[m.group("k").lower()] = m.group("v").lower() == "true"
    return out


def _sev_map(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in RULE_SEV.finditer(text or ""):
        sev = m.group("sev").lower()
        if sev in SEV_RANK:
            out[m.group("rule")] = SEV_RANK[sev]
    return out


def _nums(text: str, pattern: re.Pattern[str]) -> list[int]:
    return [int(x) for x in pattern.findall(text or "")]


def _ignore_items(text: str) -> set[str]:
    items: set[str] = set()
    for m in IGNORE_BLOCK.finditer(text or ""):
        items.update(QUOTED.findall(m.group(1)))
    # YAML block lists: exclude:\n  - build/**
    in_block = False
    indent = 0
    for line in (text or "").splitlines():
        key = re.match(
            r"^(\s*)(?:ignore(?:s|Patterns)?|exclude|per-file-ignores)\s*:\s*$",
            line,
            re.I,
        )
        if key:
            in_block = True
            indent = len(key.group(1))
            continue
        if in_block:
            item = re.match(r"^(\s*)-\s*[\'\"]?([^\'\"#\s][^\'\"#]*?)[\'\"]?\s*(?:#.*)?$", line)
            if item and len(item.group(1)) > indent:
                items.add(item.group(2).strip())
                continue
            if not line.strip() or line.strip().startswith("#"):
                continue
            in_block = False
    return items


def _quality_toml_slice(text: str) -> str:
    if not text:
        return ""
    chunks: list[str] = []
    current: list[str] = []
    keep = False
    for line in text.splitlines(True):
        if line.lstrip().startswith("["):
            keep = bool(
                re.match(
                    r"\[tool\.(ruff|coverage|pytest|mypy|pyright)",
                    line.strip(),
                )
            )
            if current and not keep:
                chunks.append("".join(current))
                current = []
        if keep:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return "".join(chunks)


def _package_slice(text: str) -> str:
    keys = ("eslintConfig", "coverageThreshold", "jest", "nyc", "c8")
    if not any(k in (text or "") for k in keys):
        return ""
    return text or ""


def compare_texts(path: str, old: str, new: str) -> list[str]:
    findings: list[str] = []
    p = norm_path(path)
    base = Path(p).name.lower()

    if base == "pyproject.toml":
        old, new = _quality_toml_slice(old), _quality_toml_slice(new)
        if old == new:
            return []
    if base == "package.json":
        old, new = _package_slice(old), _package_slice(new)
        if not old and not new:
            return []
        if old == new:
            return []
    if WORKFLOW_RE.search(p):
        if not QUALITY_CI.search(old or "") and not QUALITY_CI.search(new or ""):
            return []

    old_sev, new_sev = _sev_map(old), _sev_map(new)
    for rule, rank in old_sev.items():
        if rule in new_sev and new_sev[rule] < rank:
            findings.append(f"severity drop {rule}: {rank} -> {new_sev[rule]}")

    old_b, new_b = _bool_map(old), _bool_map(new)
    for key, val in old_b.items():
        if key not in new_b:
            continue
        nv = new_b[key]
        if key in BOOL_TRUE_STRICT and val and not nv:
            findings.append(f"strict flag off: {key}")
        if key in BOOL_TRUE_WEAK and (not val) and nv:
            findings.append(f"weak flag on: {key}")

    # Newly introduced skipLibCheck / continue-on-error (not in old)
    for key, nv in new_b.items():
        if key in BOOL_TRUE_WEAK and nv and key not in old_b:
            findings.append(f"weak flag on: {key}")
        if key in BOOL_TRUE_STRICT and (not nv) and key not in old_b:
            # introducing strict:false in a new tsconfig is weakening vs default-true
            if "tsconfig" in base:
                findings.append(f"strict flag off: {key}")

    old_low = _nums(old, LOWER_WEAKER)
    new_low = _nums(new, LOWER_WEAKER)
    if old_low and new_low and min(new_low) < min(old_low):
        findings.append(f"coverage/threshold lowered: {min(old_low)} -> {min(new_low)}")

    old_high = _nums(old, HIGHER_WEAKER)
    new_high = _nums(new, HIGHER_WEAKER)
    if old_high and new_high and max(new_high) > max(old_high):
        findings.append(f"max-warnings/errors raised: {max(old_high)} -> {max(new_high)}")

    added_ignores = _ignore_items(new) - _ignore_items(old)
    if added_ignores:
        sample = ", ".join(sorted(added_ignores)[:5])
        findings.append(f"ignore/exclude list grew: {sample}")

    if QUALITY_CI.search(old or "") or QUALITY_CI.search(new or ""):
        old_pipes = set(PIPE_TRUE.findall(old or ""))
        new_pipes = set(PIPE_TRUE.findall(new or ""))
        if new_pipes - old_pipes:
            findings.append("quality command now ends with || true")
        if "continue-on-error: true" in (new or "") and "continue-on-error: true" not in (old or ""):
            if QUALITY_CI.search(new or ""):
                findings.append("continue-on-error: true added on a quality workflow")
        for flag in ("--strict", "--cov-fail-under", "--fail-on", "--max-warnings=0"):
            if flag in (old or "") and flag not in (new or ""):
                findings.append(f"removed {flag} from a quality config/workflow")

    # Flutter lints include dropped
    if "analysis_options" in base:
        if "package:flutter_lints" in (old or "") and "package:flutter_lints" not in (new or ""):
            findings.append("removed package:flutter_lints include")
        if re.search(r"(?i)rules:\s*$", old or "", re.M) or "rules:" in (old or ""):
            old_on = set(re.findall(r"(?m)^\s{2,}(\w+):\s*true\s*$", old or ""))
            new_on = set(re.findall(r"(?m)^\s{2,}(\w+):\s*true\s*$", new or ""))
            old_off = set(re.findall(r"(?m)^\s{2,}(\w+):\s*false\s*$", new or ""))
            newly_off = (old_on - new_on) & old_off if old_off else (old_on - new_on)
            # rules that were true and became false
            became_false = set(re.findall(r"(?m)^\s{2,}(\w+):\s*false\s*$", new or "")) & old_on
            if became_false:
                findings.append("linter rules disabled: " + ", ".join(sorted(became_false)[:5]))

    # ruff select list shrunk (toml)
    if base in {"pyproject.toml", "ruff.toml", ".ruff.toml"}:
        findings.extend(_toml_ruff_weakening(old, new))

    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def _toml_ruff_weakening(old: str, new: str) -> list[str]:
    out: list[str] = []
    try:
        o = tomllib.loads(old) if old.strip() else {}
        n = tomllib.loads(new) if new.strip() else {}
    except tomllib.TOMLDecodeError:
        return out

    def walk(d: dict, prefix: str = "") -> dict:
        lint = d.get("tool", d).get("ruff", d.get("ruff", {})) if isinstance(d, dict) else {}
        if prefix == "" and "tool" in d:
            lint = ((d.get("tool") or {}).get("ruff") or {})
        elif prefix == "" and "lint" in d:
            lint = d
        return lint if isinstance(lint, dict) else {}

    ol, nl = walk(o), walk(n)
    o_lint = ol.get("lint", ol) if isinstance(ol, dict) else {}
    n_lint = nl.get("lint", nl) if isinstance(nl, dict) else {}
    if not isinstance(o_lint, dict):
        o_lint = {}
    if not isinstance(n_lint, dict):
        n_lint = {}
    o_ignore = set(o_lint.get("ignore") or ol.get("ignore") or [])
    n_ignore = set(n_lint.get("ignore") or nl.get("ignore") or [])
    added = n_ignore - o_ignore
    if added:
        out.append("ruff ignore grew: " + ", ".join(sorted(str(x) for x in added)[:5]))
    o_sel = o_lint.get("select") or ol.get("select")
    n_sel = n_lint.get("select") or nl.get("select")
    if isinstance(o_sel, list) and isinstance(n_sel, list) and len(n_sel) < len(o_sel):
        out.append(f"ruff select shrunk: {len(o_sel)} -> {len(n_sel)}")
    return out


def reconstruct(payload: dict, root: Path) -> tuple[str, str, str]:
    tool = payload.get("tool_input") or payload.get("toolInput") or {}
    path = str(tool.get("file_path") or tool.get("path") or "")
    disk = ""
    if path:
        fp = Path(path)
        if not fp.is_absolute():
            fp = root / path
        try:
            if fp.is_file():
                disk = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            disk = ""
    if "content" in tool:
        return path, disk, str(tool.get("content") or "")
    old_s = str(tool.get("old_string") or tool.get("oldString") or "")
    new_s = str(tool.get("new_string") or tool.get("newString") or "")
    if disk and old_s and old_s in disk:
        return path, disk, disk.replace(old_s, new_s, 1)
    return path, old_s, new_s


def write_audit(root: Path, path: str, reason: str) -> None:
    dest_dir = root / ".claude" / "temp"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        line = f"{utc_now()}|{path}|{reason}\n"
        with (dest_dir / "quality-config-exceptions.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        # Audit log is best-effort; the exception already allowed the edit.
        return


def evaluate(path: str, old: str, new: str, root: Path | None = None) -> tuple[int, str]:
    if not is_quality_path(path):
        return 0, ""
    if old == new:
        return 0, ""
    findings = compare_texts(path, old, new)
    if not findings:
        return 0, ""
    reason = has_exception(new)
    if reason:
        if root is not None:
            write_audit(root, path, reason)
        return 0, f"quality-config-exception accepted for {path}: {reason}\n"
    msg = (
        f"BLOCKED: quality-config weakening in {path}:\n"
        + "".join(f"  - {f}\n" for f in findings)
        + "Add a line `quality-config-exception: <reason, 20+ characters>` "
        "in the new file to proceed. The reason is appended to "
        ".claude/temp/quality-config-exceptions.log.\n"
    )
    return 1, msg


def from_payload(payload_path: Path, root: Path) -> int:
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"quality-config detector: cannot read payload ({exc}); allowing edit", file=sys.stderr)
        return 0
    path, old, new = reconstruct(payload, root)
    code, msg = evaluate(path, old, new, root)
    if msg:
        sys.stdout.write(msg)
    return code


def selftest() -> int:
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal fail
        if cond:
            print(f"  ok   {name}")
        else:
            fail += 1
            print(f"  FAIL {name} {detail}")

    check("path-positive-eslint", is_quality_path("/repo/eslint.config.mjs"))
    check("path-positive-ruff", is_quality_path("/repo/pyproject.toml"))
    check("path-positive-analysis", is_quality_path("analysis_options.yaml"))
    check("path-positive-tsconfig", is_quality_path("apps/web/tsconfig.app.json"))
    check("path-positive-workflow", is_quality_path(".github/workflows/ci.yml"))
    check("path-negative-source", not is_quality_path("src/app.ts"))
    check("path-negative-venv", not is_quality_path(".venv/pyproject.toml"))

    code, msg = evaluate(
        "eslint.config.js",
        "rules: { 'no-unused-vars': 'error' }",
        "rules: { 'no-unused-vars': 'off' }",
    )
    check("positive-eslint-severity", code == 1 and "severity drop" in msg, msg)

    code, msg = evaluate(
        "eslint.config.js",
        "rules: { 'no-unused-vars': 'error' }",
        "rules: { 'no-unused-vars': 'error', 'eqeqeq': 'error' }",
    )
    check("negative-eslint-strengthen", code == 0 and msg == "", msg)

    code, msg = evaluate(
        "tsconfig.json",
        '{ "compilerOptions": { "strict": true, "skipLibCheck": false } }',
        '{ "compilerOptions": { "strict": false, "skipLibCheck": true } }',
    )
    check(
        "positive-tsconfig-strict-and-skip",
        code == 1 and "strict flag off" in msg and "weak flag on" in msg,
        msg,
    )

    code, msg = evaluate(
        "tsconfig.json",
        '{ "compilerOptions": { "strict": true } }',
        '{ "compilerOptions": { "strict": true, "noImplicitOverride": true } }',
    )
    check("negative-tsconfig-unrelated", code == 0, msg)

    code, msg = evaluate(
        "analysis_options.yaml",
        "include: package:flutter_lints/flutter.yaml\nlinter:\n  rules:\n    avoid_print: true\n",
        "include: package:lints/recommended.yaml\nlinter:\n  rules:\n    avoid_print: false\n",
    )
    check(
        "positive-flutter-lints",
        code == 1 and ("flutter_lints" in msg or "linter rules disabled" in msg),
        msg,
    )

    code, msg = evaluate(
        "analysis_options.yaml",
        "linter:\n  rules:\n    avoid_print: true\n",
        "linter:\n  rules:\n    avoid_print: true\n    prefer_const_constructors: true\n",
    )
    check("negative-flutter-add-rule", code == 0, msg)

    old_ruff = "[tool.ruff.lint]\nselect = [\"E\", \"F\"]\nignore = [\"E501\"]\n"
    new_ruff = "[tool.ruff.lint]\nselect = [\"E\"]\nignore = [\"E501\", \"F401\"]\n"
    code, msg = evaluate("pyproject.toml", old_ruff, new_ruff)
    check(
        "positive-ruff-ignore-and-select",
        code == 1 and ("ignore" in msg or "select" in msg),
        msg,
    )

    code, msg = evaluate(
        "pyproject.toml",
        "[project]\nname = 'x'\nversion = '1'\n[tool.ruff.lint]\nignore = [\"E501\"]\n",
        "[project]\nname = 'x'\nversion = '2'\n[tool.ruff.lint]\nignore = [\"E501\"]\n",
    )
    check("negative-pyproject-version-only", code == 0, msg)

    code, msg = evaluate(
        "jest.config.js",
        "coverageThreshold: { global: { lines: 80 } }",
        "coverageThreshold: { global: { lines: 50 } }",
    )
    check("positive-coverage-floor", code == 1 and "lowered" in msg, msg)

    code, msg = evaluate(
        "jest.config.js",
        "coverageThreshold: { global: { lines: 80 } }",
        "coverageThreshold: { global: { lines: 90 } }",
    )
    check("negative-coverage-raised", code == 0, msg)

    code, msg = evaluate(
        "eslint.config.js",
        "ignores: ['dist']",
        "ignores: ['dist', 'src']",
    )
    check("positive-ignore-grew", code == 1 and "ignore" in msg, msg)

    code, msg = evaluate(
        "analysis_options.yaml",
        "analyzer:\n  exclude:\n    - build/**\n",
        "analyzer:\n  exclude:\n    - build/**\n    - lib/generated/**\n",
    )
    check("positive-yaml-exclude-grew", code == 1 and "ignore" in msg, msg)

    code, msg = evaluate(
        "analysis_options.yaml",
        "analyzer:\n  exclude:\n    - build/**\n",
        "analyzer:\n  exclude:\n    - build/**\nlinter:\n  rules:\n    avoid_print: true\n",
    )
    check("negative-yaml-exclude-unchanged", code == 0, msg)

    code, msg = evaluate(
        "eslint.config.js",
        "rules: { 'eqeqeq': 'error' }",
        "rules: { 'eqeqeq': 'error' }\nmodule.exports.maxWarnings = 50\n",
    )
    check("negative-max-warnings-introduced-is-a-gate", code == 0, msg)

    code, msg = evaluate(
        "eslint.config.js",
        "maxWarnings: 0",
        "maxWarnings: 50",
    )
    check("positive-max-warnings-raised", code == 1 and "raised" in msg, msg)

    code, msg = evaluate(
        ".github/workflows/ci.yml",
        "run: npm test\n",
        "run: npm test || true\n",
    )
    check("positive-ci-pipe-true", code == 1 and "|| true" in msg, msg)

    code, msg = evaluate(
        ".github/workflows/ci.yml",
        "jobs:\n  lint:\n    steps:\n      - run: ruff check\n",
        "jobs:\n  lint:\n    continue-on-error: true\n    steps:\n      - run: ruff check\n",
    )
    check("positive-ci-continue-on-error", code == 1 and "continue-on-error" in msg, msg)

    code, msg = evaluate(
        ".github/workflows/deploy.yml",
        "jobs:\n  notify:\n    steps:\n      - run: echo hi\n",
        "jobs:\n  notify:\n    continue-on-error: true\n    steps:\n      - run: echo hi\n",
    )
    check("negative-ci-non-quality-continue", code == 0, msg)

    code, msg = evaluate(
        ".github/workflows/ci.yml",
        "run: bash .claude/scripts/check-context-budget.sh --strict\n",
        "run: bash .claude/scripts/check-context-budget.sh\n",
    )
    check("positive-ci-removed-strict", code == 1 and "--strict" in msg, msg)

    weak = "rules: { 'no-unused-vars': 'off' }\n"
    code, msg = evaluate("eslint.config.js", "rules: { 'no-unused-vars': 'error' }", weak)
    check("positive-no-exception", code == 1, msg)
    excused = weak + "// quality-config-exception: temporary while migrating the parser to typescript-eslint\n"
    code, msg = evaluate("eslint.config.js", "rules: { 'no-unused-vars': 'error' }", excused)
    check("positive-exception-allows", code == 0 and "accepted" in msg, msg)
    short = weak + "// quality-config-exception: n/a\n"
    code, msg = evaluate("eslint.config.js", "rules: { 'no-unused-vars': 'error' }", short)
    check("negative-short-exception-rejected", code == 1, msg)

    code, msg = evaluate("src/main.ts", "x", "skipLibCheck: true")
    check("negative-non-quality-file", code == 0, msg)

    # payload reconstruction (Write + Edit)
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    (tmp / "eslint.config.js").write_text("rules: { 'eqeqeq': 'error' }\n", encoding="utf-8")
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp / "eslint.config.js"),
            "old_string": "'eqeqeq': 'error'",
            "new_string": "'eqeqeq': 'off'",
        },
    }
    pfile = tmp / "payload.json"
    pfile.write_text(json.dumps(payload), encoding="utf-8")
    rc = from_payload(pfile, tmp)
    check("positive-edit-payload", rc == 1)

    payload["tool_input"]["new_string"] = "'eqeqeq': 'off'"
    payload["tool_input"]["new_string"] = (
        "'eqeqeq': 'off'\n// quality-config-exception: documented waiver while the eqeqeq baseline is rebuilt"
    )
    # reconstruction applies replace on disk; exception must be in the resulting file text.
    # Put the exception in new_string as part of a larger unique old_string:
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp / "eslint.config.js"),
            "content": (
                "rules: { 'eqeqeq': 'off' }\n"
                "// quality-config-exception: documented waiver while the eqeqeq baseline is rebuilt\n"
            ),
        },
    }
    pfile.write_text(json.dumps(payload), encoding="utf-8")
    rc = from_payload(pfile, tmp)
    audit = tmp / ".claude" / "temp" / "quality-config-exceptions.log"
    check("positive-write-exception-audit", rc == 0 and audit.is_file() and "eqeqeq" in audit.read_text())

    # mutation: severity map must flag error->off; if SEV_RANK['off'] were 3 this would fail
    check("mutation-severity-off-is-zero", SEV_RANK["off"] == 0 and SEV_RANK["error"] > SEV_RANK["off"])

    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 0 if fail == 0 else 2


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--payload", type=Path)
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--path", default="")
    p.add_argument("--old-text", default=None)
    p.add_argument("--new-text", default=None)
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.payload is not None:
        root = (args.root or Path(".")).resolve()
        return from_payload(args.payload, root)
    if args.old_text is not None and args.new_text is not None and args.path:
        code, msg = evaluate(args.path, args.old_text, args.new_text, args.root)
        if msg:
            sys.stdout.write(msg)
        return code
    print("specify --selftest, --payload, or --path with --old-text/--new-text", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
