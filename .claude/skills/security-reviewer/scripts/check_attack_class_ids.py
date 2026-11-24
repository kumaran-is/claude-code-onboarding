# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["pyyaml==6.0.4"]
# ///
"""Check that every OWASP LLM / OWASP Agentic / MITRE ATLAS identifier cited in a document exists in the
official sources you downloaded (the script never touches the network).

Inputs (download them first; commands in ai-threat-model-attack-classes.md §3.1):
  ATLAS release YAML   https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/v6/ATLAS-<release>.yaml
  OWASP LLM page HTML  https://genai.owasp.org/llm-top-10/
  OWASP Agentic HTML   https://genai.owasp.org/top-10-for-agentic-applications-2026/
Exit codes: 0 every cited id exists, 1 unknown id(s) listed, 2 usage or unreadable input.
Run:  uv run --script check_attack_class_ids.py DOC ATLAS.yaml LLM.html AGENTIC.html [--llm-edition 2025]
      uv run --script check_attack_class_ids.py --selftest
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
import tempfile
from pathlib import Path

import yaml

log = logging.getLogger("check_attack_class_ids")

ATLAS_ID = re.compile(r"AML\.TA?\d{4}(?:\.\d{3})?")
ASI_ID = re.compile(r"ASI(?:0[1-9]|10)\b")


def page_text(raw: str) -> str:
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def unknown_ids(doc: str, atlas: dict, llm_page: str, asi_page: str, edition: str) -> list[str]:
    llm_id = re.compile(rf"LLM(?:0[1-9]|10):{edition}")
    known = set(atlas.get("techniques", {})) | set(atlas.get("tactics", {}))
    known |= set(llm_id.findall(page_text(llm_page))) | set(ASI_ID.findall(page_text(asi_page)))
    cited = set(ATLAS_ID.findall(doc)) | set(re.findall(r"LLM\d{2}:\d{4}", doc)) | set(re.findall(r"ASI\d{2}", doc))
    return sorted(cited - known)


def run(doc_path: str, atlas_path: str, llm_path: str, asi_path: str, edition: str) -> int:
    try:
        doc = Path(doc_path).read_text(encoding="utf-8")
        atlas = yaml.safe_load(Path(atlas_path).read_text(encoding="utf-8"))
        llm_page = Path(llm_path).read_text(encoding="utf-8", errors="replace")
        asi_page = Path(asi_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, yaml.YAMLError) as exc:
        log.error("unreadable input: %s", type(exc).__name__)
        return 2
    if not isinstance(atlas, dict) or "techniques" not in atlas:
        log.error("ATLAS file has no 'techniques' map (use a dist/v6 release file)")
        return 2
    bad = unknown_ids(doc, atlas, llm_page, asi_page, edition)
    cited = len(set(ATLAS_ID.findall(doc)))
    sys.stdout.write(f"cited ATLAS ids={cited}; unknown={len(bad)}\n")
    for item in bad:
        sys.stdout.write(f"UNKNOWN {item}\n")
    return 1 if bad else 0


def selftest() -> int:
    atlas = "techniques:\n  AML.T0051.000: {name: Direct}\n  AML.T0110: {name: AI Agent Tool Poisoning}\ntactics:\n  AML.TA0005: {name: Execution}\n"
    llm = "<html><h2>LLM01:2025 Prompt Injection</h2><h2>LLM07:2025 System Prompt Leakage</h2></html>"
    asi = "<p>ASI01: Agent Goal Hijack</p><p>ASI02: Tool Misuse</p>"
    cases = [("valid ids pass", "AC-01 LLM01:2025 ASI01 AML.T0051.000 (AML.TA0005); AML.T0110", 0),
             ("unknown ATLAS technique fails", "AC-08 AML.T0199", 1),
             ("wrong OWASP edition fails", "AC-06 LLM07:2023", 1),
             ("unknown agentic id fails", "ASI11 or ASI09", 1)]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "a.yaml").write_text(atlas, encoding="utf-8")
        (t / "l.html").write_text(llm, encoding="utf-8")
        (t / "s.html").write_text(asi, encoding="utf-8")
        for name, doc, want in cases:
            (t / "d.md").write_text(doc, encoding="utf-8")
            got = run(str(t / "d.md"), str(t / "a.yaml"), str(t / "l.html"), str(t / "s.html"), "2025")
            ok = got == want
            failures += not ok
            sys.stdout.write(f"{'PASS' if ok else 'FAIL'} selftest: {name} (exit {got}, want {want})\n")
        got = run(str(t / "missing.md"), str(t / "a.yaml"), str(t / "l.html"), str(t / "s.html"), "2025")
        failures += got != 2
        sys.stdout.write(f"{'PASS' if got == 2 else 'FAIL'} selftest: missing input is a usage error (exit {got}, want 2)\n")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if argv[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("doc"), ap.add_argument("atlas"), ap.add_argument("llm_html"), ap.add_argument("agentic_html")
    ap.add_argument("--llm-edition", default="2025")
    a = ap.parse_args(argv)
    return run(a.doc, a.atlas, a.llm_html, a.agentic_html, a.llm_edition)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
