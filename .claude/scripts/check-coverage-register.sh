#!/usr/bin/env bash
# check-coverage-register.sh — verify the AI engineering standards coverage register (.tsv) against the repository.
# Register: docs/audits/ai-engineering-standards-coverage.tsv (requirements extracted from the AI engineering standards; section homes: docs/audits/standards-section-map.tsv).
#
# Register columns (tab-separated, header row required, lines starting with '#' are comments):
#   ID  source  section  severity  requirement  status  boundary  toolkit_refs  gap  evidence
#
# Checks
#   C1  Header carries the required columns and at least one requirement row (an empty register fails).
#   C2  Every ID is well formed (<EVAL|GOV|SEC|MSR|PRM|RAG|MEM|IR|DGP|PRIN>-<sec>-<nn> | GR-G<n>-<nn> | GR-§<n>-<nn>) and unique.
#   C3  status is one of the coverage statuses; boundary is A-D (or a combination such as B/C) on every GOV row
#       except NOT_APPLICABLE (informative) rows.
#   C4  IMPLEMENTED_* and PARTIALLY_COVERED rows cite at least one toolkit_ref.
#   C5  Every toolkit_ref (`path` or `path:line` or `path:start-end`, ';'-separated) is repo-relative, exists, and
#       its line numbers are within the file. Absolute paths and temp paths are rejected.
#
# Usage: check-coverage-register.sh [--root <repo>] <register.tsv> | --selftest     Exit 0 = clean, 1 = violations, 2 = usage.
set -uo pipefail
exec python3 - "$@" <<'PY'
import os
import re
import sys
import tempfile

REQUIRED = ["ID", "status", "boundary", "toolkit_refs"]
STATUSES = {"IMPLEMENTED_AND_TESTED", "IMPLEMENTED_NOT_TESTED", "PARTIALLY_COVERED", "DOCUMENTED_ONLY", "MISSING",
            "NOT_APPLICABLE", "REQUIRES_ENTERPRISE_ADOPTION", "BLOCKED"}
NEEDS_REF = {"IMPLEMENTED_AND_TESTED", "IMPLEMENTED_NOT_TESTED", "PARTIALLY_COVERED"}
ID_RE = re.compile(r"^((EVAL|SEC|MSR|PRM|RAG|MEM|GOV|IR|DGP|PRIN)-[0-9A-Z.]+|GR-(G\d+|§\d+|PRE))-\d{2,3}$")
BOUNDARY_RE = re.compile(r"^[ABCD](/[ABCD])*$")
REF_RE = re.compile(r"^(?P<path>[^:\s]+)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?$")


def check(root, register):
    errors = []
    lines = [l.rstrip("\n") for l in open(register, encoding="utf-8")]
    rows = [l.split("\t") for l in lines if l and not l.startswith("#")]
    if not rows:
        return ["C1 register is empty"]
    header, body = rows[0], rows[1:]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        return [f"C1 header lacks columns: {', '.join(missing)}"]
    if not body:
        return ["C1 register has no requirement rows"]
    col = {name: i for i, name in enumerate(header)}
    seen = set()
    line_cache = {}
    for n, row in enumerate(body, start=2):
        cell = lambda name: row[col[name]].strip() if col[name] < len(row) else ""
        rid, status, boundary, refs = cell("ID"), cell("status"), cell("boundary"), cell("toolkit_refs")
        where = f"row {n} ({rid or '?'})"
        if not ID_RE.match(rid):
            errors.append(f"C2 {where}: malformed ID")
        if rid in seen:
            errors.append(f"C2 {where}: duplicate ID")
        seen.add(rid)
        if status not in STATUSES:
            errors.append(f"C3 {where}: unknown status '{status}'")
        if rid.startswith("GOV-") and status != "NOT_APPLICABLE" and not BOUNDARY_RE.match(boundary):
            errors.append(f"C3 {where}: governance row needs boundary A-D, got '{boundary}'")
        ref_list = [r.strip() for r in refs.split(";") if r.strip() and r.strip() != "-"]
        if status in NEEDS_REF and not ref_list:
            errors.append(f"C4 {where}: {status} without a toolkit_ref")
        for ref in ref_list:
            m = REF_RE.match(ref)
            if not m:
                errors.append(f"C5 {where}: unparseable ref '{ref}'")
                continue
            path = m.group("path")
            if os.path.isabs(path) or path.startswith("~") or ".." in path.split("/") or re.search(r"(^|/)(tmp|private)/", path):
                errors.append(f"C5 {where}: ref must be repo-relative: '{ref}'")
                continue
            full = os.path.join(root, path)
            if not os.path.isfile(full):
                errors.append(f"C5 {where}: missing file '{path}'")
                continue
            if full not in line_cache:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    line_cache[full] = sum(1 for _ in fh)
            for key in ("a", "b"):
                if m.group(key) and not (1 <= int(m.group(key)) <= line_cache[full]):
                    errors.append(f"C5 {where}: line {m.group(key)} outside '{path}' ({line_cache[full]} lines)")
    return errors


def selftest():
    fail = 0
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "docs"))
        with open(os.path.join(root, "docs", "a.md"), "w") as fh:
            fh.write("one\ntwo\nthree\n")
        header = "ID\tstatus\tboundary\ttoolkit_refs\n"
        cases = {
            "header only (vacuous)": ("", "C1"),
            "clean": ("EVAL-7.4-01\tIMPLEMENTED_NOT_TESTED\t\tdocs/a.md:2\nGOV-1.2-01\tREQUIRES_ENTERPRISE_ADOPTION\tC\t-\nGR-G4-01\tMISSING\t\t\n", None),
            "missing file": ("EVAL-7.4-01\tIMPLEMENTED_NOT_TESTED\t\tdocs/b.md:1\n", "C5"),
            "line out of range": ("EVAL-7.4-01\tIMPLEMENTED_NOT_TESTED\t\tdocs/a.md:9\n", "C5"),
            "range end out of range": ("EVAL-7.4-01\tPARTIALLY_COVERED\t\tdocs/a.md:2-7\n", "C5"),
            "unknown status": ("EVAL-7.4-01\tDONE\t\tdocs/a.md:1\n", "C3"),
            "implemented without ref": ("EVAL-7.4-01\tIMPLEMENTED_AND_TESTED\t\t\n", "C4"),
            "absolute path": ("EVAL-7.4-01\tIMPLEMENTED_NOT_TESTED\t\t/etc/hosts\n", "C5"),
            "temp path": ("EVAL-7.4-01\tIMPLEMENTED_NOT_TESTED\t\tprivate/tmp/x.md\n", "C5"),
            "duplicate ID": ("EVAL-7.4-01\tMISSING\t\t\nEVAL-7.4-01\tMISSING\t\t\n", "C2"),
            "malformed ID": ("EVAL7401\tMISSING\t\t\n", "C2"),
            "new prefixes clean": ("SEC-4-03\tMISSING\t\t\nMSR-11.1-01\tMISSING\t\t\nPRM-PRE-01\tMISSING\t\t\nRAG-14.3-02\tMISSING\t\t\nMEM-5.4-01\tMISSING\t\t\nIR-4.2-01\tMISSING\t\t\nDGP-6-03\tMISSING\t\t\nPRIN-L3-02\tMISSING\t\t\n", None),
            "unknown prefix": ("XYZ-1-01\tMISSING\t\t\n", "C2"),
            "governance without boundary": ("GOV-1.2-01\tMISSING\t\t\n", "C3"),
            "informative governance row needs no boundary": ("GOV-PRE-01\tNOT_APPLICABLE\t-\t-\n", None),
        }
        for name, (body, expected_code) in cases.items():
            reg = os.path.join(root, "reg.tsv")
            with open(reg, "w") as fh:
                fh.write("# comment\n" + header + body)
            got = check(root, reg)
            # A violation case passes only if every finding carries the expected check code.
            ok = (not got) if expected_code is None else (bool(got) and all(g.startswith(expected_code + " ") for g in got))
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(got)} finding(s)")
            fail |= not ok
    print("selftest PASS" if not fail else "selftest FAIL")
    return 1 if fail else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    root = os.getcwd()
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("usage: check-coverage-register.sh [--root <repo>] <register.tsv> | --selftest", file=sys.stderr)
            return 2
        root = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1 or not os.path.isfile(argv[0]):
        print("usage: check-coverage-register.sh [--root <repo>] <register.tsv> | --selftest", file=sys.stderr)
        return 2
    errors = check(root, argv[0])
    for e in errors:
        print(e)
    print(f"{len(errors)} violation(s)")
    return 1 if errors else 0


sys.exit(main(sys.argv[1:]))
PY
