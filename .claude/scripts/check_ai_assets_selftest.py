"""Controls for check-ai-assets.py; loaded by `check-ai-assets.py` in selftest mode, never run on its own.

Stub delegates prove the exit-code mapping (PASS, BLOCK, BLOCKED) without uv or network; live controls run the
real golden and prompt validators when uv is installed and print NOT RUN otherwise (CI fails on NOT RUN).
Every control asserts on finding codes or paths, not only on exit status.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType


def run(m: ModuleType) -> int:  # noqa: PLR0915 - one linear list of controls reads better than many helpers
    failures = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal failures
        print(f"  {'ok  ' if ok else 'FAIL'} {label}{'' if ok else f' -> {detail}'}")
        failures += 0 if ok else 1

    def codes(rep: m.Report) -> list[str]:
        return [f["code"] for f in rep.findings]

    real = (m.UV_RUNNER, m.GOVERNANCE_RUNNER, m.GOLDEN_VALIDATOR, m.GOVERNANCE_VALIDATOR, m.PROMPT_VALIDATOR)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Stub delegates: behaviour chosen by a marker file next to the input, so exit-code mapping is provable
        # without uv or network. GOLDEN: writes the JSON report the real validator writes.
        stub_golden = base / "stub_golden.py"
        stub_golden.write_text(
            "import json, sys, pathlib\nroot = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[sys.argv.index('--json') + 1])\n"
            "mode = (root / 'MODE').read_text().strip() if (root / 'MODE').exists() else 'pass'\n"
            "if mode == 'crash':\n    sys.exit(2)\n"
            "f = [] if mode == 'pass' else [{'rule': 'unmanifested_file', 'severity': 'BLOCK', "
            "'path': 'features/x/golden.jsonl', 'message': 'no manifest lists this file', 'case_id': ''}]\n"
            "out.write_text(json.dumps({'verdict': 'BLOCK' if f else 'PASS', 'findings': f}))\n"
            "sys.exit(1 if f else 0)\n")
        m.UV_RUNNER, m.GOLDEN_VALIDATOR, m.PROMPT_VALIDATOR = [sys.executable], stub_golden, stub_golden

        empty = base / "empty"
        (empty / "src").mkdir(parents=True)
        (empty / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")
        (empty / "package.json").write_text('{"name": "x"}\n')
        (empty / ".claude" / "golden").mkdir(parents=True)  # toolkit assets are not project assets
        (empty / ".claude" / "golden" / "x.jsonl").write_text('{"case_id": "c1"}\n')
        rep = m.scan_tree(empty)
        check("negative: non-AI project is NOT_APPLICABLE", rep.verdict(False) == ("NOT_APPLICABLE", 0),
              rep.verdict(False))

        proj = base / "proj"
        golden = proj / "tests" / "golden"
        (golden / "features" / "triage").mkdir(parents=True)
        (golden / "features" / "triage" / "golden.jsonl").write_text('{"case_id": "c1"}\n')
        (golden / "MODE").write_text("block\n")
        prompts_dir = proj / "prompts" / "support"
        prompts_dir.mkdir(parents=True)
        aws = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
        (prompts_dir / "triage.system.yaml").write_text(
            f"name: support.triage.classification.system\ntext: use key {aws}\n")
        src = proj / "src" / "agent"
        src.mkdir(parents=True)
        (src / "retrieval.py").write_text("docs = store.similarity_search(query, k=5)\n")
        (src / "tools.py").write_text("@tool\ndef create_refund(amount: int) -> str:\n    return 'ok'\n")
        (proj / "prompts" / "MODE").write_text("block\n")
        (src / "notes.py").write_text('"""Compare Git <-> registry hashes."""\n@tool\ndef read_doc() -> str:\n    return ""\n')
        (src / "sql_search.py").write_text('Q = "SELECT id FROM docs ORDER BY embedding <-> :q LIMIT 5"\n')
        (src / "service.py").write_text('MODEL = "gemini-3-flash-preview"\n')
        (src / "router_setup.py").write_text("from litellm import Router\nr = Router(model_list=ml, "
                                             "default_fallbacks=['b'])\n")
        (src / "router_fb.py").write_text("from litellm import Router\nr = Router(model_list=ml, fallbacks=[{'a': ['b']}],"
                                          " content_policy_fallbacks=[{'a': []}], fallback_on_unsupported_params=False)\n")
        (prompts_dir / "tone.system.md").write_text(f"Few-shot reply.\nkey {aws}\n")   # non-YAML prompt text
        (proj / "config").mkdir()
        (proj / "config" / "models.yaml").write_text("chat_model: x-latest\njudge_model: models/x-2026-10-01\n")
        (proj / "prompts" / "support" / "refund").mkdir()
        (proj / "prompts" / "support" / "refund" / "draft_reply.system.yaml").write_text("template: x\n")
        (src / "prompts_use.py").write_text(
            "p = prompts.get('support.triage.classification.system', label='production')\n"
            "r = prompts.get('support.refund.draft_reply.system', label='production')\n"
            "q = registry.get('support.triage.missing.system', label=\"latest\")\n")
        (proj / "notebooks").mkdir()
        gh_token = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        (proj / "notebooks" / "explore.ipynb").write_text('{"cells": [{"source": ["t = \'' + gh_token + '\'"]}]}\n')
        gov = proj / "governance"
        gov.mkdir()
        example = m.GOVERNANCE_VALIDATOR.parent.parent / "assets" / "examples" / "approval_record.example.json"
        if example.is_file():
            (gov / "approval.json").write_text(example.read_text())  # record_status=example -> invalid
        rep = m.scan_tree(proj)
        found = codes(rep)
        for expected in ("PROMPT_UNMANIFESTED_FILE", "MODEL_LITERAL_IN_BUSINESS_LOGIC", "LITELLM_ROUTER_FALLBACK",
                         "GOLDEN_UNMANIFESTED_FILE", "SECRET_IN_AI_ASSET", "RETRIEVAL_WITHOUT_SCOPE_FILTER",
                         "STATE_CHANGING_TOOL_UNGUARDED", "PROMPT_LABEL_LATEST", "PROMPT_REFERENCE_UNRESOLVED",
                         "GOVERNANCE_RECORD_INVALID"):
            check(f"positive: {expected} flagged", expected in found, found)
        where = {(f["code"], f["path"]) for f in rep.findings}
        check("positive: unpinned model alias in config flagged, pinned id on the next line not flagged",
              ("MODEL_UNPINNED", "config/models.yaml:1") in where
              and ("MODEL_UNPINNED", "config/models.yaml:2") not in where, sorted(where))
        check("positive: preview model literal in code flagged", ("MODEL_UNPINNED", "src/agent/service.py:1") in where,
              sorted(where))
        check("positive: pgvector operator in a SQL query flagged without a scope filter",
              ("RETRIEVAL_WITHOUT_SCOPE_FILTER", "src/agent/sql_search.py") in where, sorted(where))
        check("negative: '<->' in prose is not a retrieval call",
              ("RETRIEVAL_WITHOUT_SCOPE_FILTER", "src/agent/notes.py") not in where, sorted(where))
        check("positive: golden validator BLOCK severity kept as BLOCK",
              {"level": "BLOCK", "code": "GOLDEN_UNMANIFESTED_FILE"}.items()
              <= next((f for f in rep.findings if f["code"] == "GOLDEN_UNMANIFESTED_FILE"), {}).items(), rep.findings)
        check("negative: resolvable prompt reference not flagged",
              not any(n in f["message"] for f in rep.findings
                      for n in ("classification.system", "draft_reply.system")), rep.findings)
        check("positive: secret in a notebook flagged (security playbook §13)",
              any(f["code"] == "SECRET_IN_AI_ASSET" and f["path"].endswith("explore.ipynb") for f in rep.findings),
              rep.findings)
        check("positive: secret in a non-YAML prompt file (prompts/**/*.md) flagged (security playbook §13)",
              ("SECRET_IN_AI_ASSET", "prompts/support/tone.system.md") in where, sorted(where))
        fb = next((f["message"] for f in rep.findings if f["path"] == "src/agent/router_fb.py"), "")
        check("positive: LiteLLM fallbacks= without explicit context_window_fallbacks= flagged",
              "context_window_fallbacks" in fb and "fallback_on_unsupported_params" not in fb, fb)
        check("positive: secret value never printed", all(aws not in f["message"] for f in rep.findings))
        check("positive: BLOCK verdict exits 1", rep.verdict(False) == ("BLOCK", 1), rep.verdict(False))

        (golden / "MODE").write_text("crash\n")
        rep = m.scan_tree(proj)
        check("positive: golden validator exit 2 makes the run BLOCKED (exit 3)", rep.verdict(False)[1] == 3,
              rep.blocked)
        m.GOLDEN_VALIDATOR = base / "absent.py"
        rep = m.scan_tree(proj)
        check("positive: missing golden validator makes the run BLOCKED, never PASS",
              rep.verdict(False)[1] == 3 and any("cannot run" in b for b in rep.blocked), rep.blocked)
        m.GOLDEN_VALIDATOR = stub_golden

        clean = base / "clean"
        cgold = clean / "tests" / "golden" / "features" / "triage"
        cgold.mkdir(parents=True)
        (cgold / "golden.jsonl").write_text('{"case_id": "c1", "input": "mail user_a@example.com"}\n')
        csrc = clean / "src" / "agent"
        csrc.mkdir(parents=True)
        (csrc / "retrieval.py").write_text("docs = store.similarity_search(q, k=5, filter={'tenant_id': tid})\n")
        (csrc / "tools.py").write_text("@tool\ndef create_refund(amount: int, idempotency_key: str) -> str:\n"
                                       "    authorize(principal, 'refund')\n    return 'ok'\n")
        (csrc / "model_client.py").write_text('CHAT = "gemini-3.1-flash-001"\n')
        (csrc / "llm_router.py").write_text("from litellm import Router\nr = Router(model_list=ml, fallbacks=[{'a': ['b']}],"
                                            " content_policy_fallbacks=[{'a': []}], context_window_fallbacks=[{'a': []}],"
                                            " fallback_on_unsupported_params=False)\n")
        (clean / ".env").write_text("CHAT_MODEL=x-latest\n")               # real env file: never read
        (clean / ".env.example").write_text("CHAT_MODEL=models/x-2026-10-01\n")
        if example.is_file():
            (clean / "governance").mkdir()
            (clean / "governance" / "approval.json").write_text(
                example.read_text().replace('"record_status": "example"', '"record_status": "draft"'))
        (clean / "tests" / "unit").mkdir(parents=True)
        (clean / "tests" / "unit" / "test_r.py").write_text("store.similarity_search(q)\n")
        rep = m.scan_tree(clean)
        check("negative: clean project has no findings and PASSes", rep.findings == [] and
              rep.verdict(False) == ("PASS", 0), (rep.findings, rep.blocked))
        check("positive: clean project scanned golden, governance and code",
              rep.scanned["golden_trees"] == 1 and rep.scanned["ai_code_files"] == 5
              and rep.scanned["model_config_files"] == 1
              and rep.scanned["governance_files"] == (1 if example.is_file() else 0), rep.scanned)

        md_only = base / "md_only"
        (md_only / "prompts").mkdir(parents=True)
        (md_only / "prompts" / "support.system.md").write_text(f"System prompt.\nkey {aws}\n")
        rep = m.scan_tree(md_only)
        check("positive: a tree whose only prompt is .md is scanned (not NOT_APPLICABLE) and BLOCKs on a secret",
              rep.verdict(False) == ("BLOCK", 1) and rep.scanned["prompt_text_files"] == 1, (rep.verdict(False), rep.scanned))

        # JSON-record delegates (model registry, memory items): exit-code mapping with a stub validator
        stub_json = base / "stub_json.py"
        stub_json.write_text(
            "import json, sys, pathlib\nfiles = [a for a in sys.argv[1:] if a != '--json']\n"
            "if any('crash' in pathlib.Path(f).name for f in files):\n    sys.exit(2)\n"
            "print(json.dumps({'scope': 'structure-only', 'results': [{'file': f, 'valid': True, 'errors': []}"
            " for f in files]}))\n")
        reg_tree = base / "reg"
        (reg_tree / "config").mkdir(parents=True)
        (reg_tree / "config" / "model-registry.json").write_text('{"registry_version": "1"}\n')
        (reg_tree / "memory_items").mkdir()
        (reg_tree / "memory_items" / "a.json").write_text('{"memory_items": []}\n')
        saved = (m.REGISTRY_VALIDATOR, m.MEMORY_VALIDATOR)
        m.REGISTRY_VALIDATOR = m.MEMORY_VALIDATOR = stub_json
        rep = m.scan_tree(reg_tree)
        check("negative: valid registry and memory files pass, scanned, with the validator's scope note shown",
              rep.verdict(False) == ("PASS", 0) and rep.scanned["model_registry_files"] == 1
              and rep.scanned["memory_files"] == 1 and any("structure-only" in n for n in rep.notes),
              (rep.findings, rep.blocked, rep.scanned, rep.notes))
        (reg_tree / "memory_items" / "crash.json").write_text('{"memory_items": []}\n')
        rep = m.scan_tree(reg_tree)
        check("positive: memory validator exit 2 makes the run BLOCKED (exit 3)", rep.verdict(False)[1] == 3, rep.blocked)
        m.MEMORY_VALIDATOR = base / "absent.py"
        rep = m.scan_tree(reg_tree)
        check("positive: missing memory validator is BLOCKED, never PASS", rep.verdict(False)[1] == 3, rep.blocked)
        m.REGISTRY_VALIDATOR, m.MEMORY_VALIDATOR = saved
        if sys.version_info >= (3, 11) and m.REGISTRY_VALIDATOR.is_file() and m.MEMORY_VALIDATOR.is_file():
            livej = base / "livej"
            (livej / "memory_items").mkdir(parents=True)
            examples = m.MEMORY_VALIDATOR.parent.parent / "assets" / "examples"
            shutil.copy(examples / "memory_item.example.json", livej / "memory_items" / "x.json")
            reg = (examples / "model-registry.example.json").read_text()
            (livej / "model-registry.json").write_text(reg.replace('"pinned_version": "2026-10-01"',
                                                                    '"pinned_version": "latest"', 1))
            rep = m.scan_tree(livej)
            msgs = {f["code"]: f["message"] for f in rep.findings}
            check("live: copied memory example is a BLOCK (EXAMPLE_RECORD) from the real validator",
                  "EXAMPLE_RECORD" in msgs.get("MEMORY_RECORD_INVALID", ""), (rep.findings, rep.blocked))
            check("live: registry entry pinned to an alias is a BLOCK from the real validator",
                  "MODEL_REGISTRY_RECORD_INVALID" in msgs and not rep.blocked, (rep.findings, rep.blocked))
        else:
            print("  NOT RUN live registry/memory-validator controls: needs python3 >= 3.11 and both validators")

        per_file = m.Report()
        m.code_signals((src / "retrieval.py").read_text(), "retrieval.py", per_file)
        check("positive: --file mode flags the retrieval signal",
              codes(per_file) == ["RETRIEVAL_WITHOUT_SCOPE_FILTER"], per_file.findings)

        hook_probe = base / "probe.py"
        hook_probe.write_text("p = prompts.get('a.b.c.system', label='latest')\n")
        out = m.run([sys.executable, str(Path(m.__file__).resolve()), "--file", str(hook_probe)])
        check("positive: --file mode (edit hook) reports even a deterministic finding as ADVISORY",
              out is not None and out.returncode == 0 and out.stdout.startswith("ADVISORY PROMPT_LABEL_LATEST"),
              out.stdout if out else None)

        # Live integration with the real golden and prompt validators when uv is present (CI installs it).
        m.UV_RUNNER, m.GOLDEN_VALIDATOR, m.PROMPT_VALIDATOR = real[0], real[2], real[4]
        prompt_scaffold = m.PROMPT_VALIDATOR.parent.parent / "assets" / "prompts-scaffold"
        if shutil.which(m.UV_RUNNER[0]) and prompt_scaffold.is_dir():
            livep = base / "livep"
            shutil.copytree(prompt_scaffold, livep)
            rep = m.scan_tree(livep)
            check("live: shipped prompt scaffold has no BLOCK", "BLOCK" not in {f["level"] for f in rep.findings}
                  and not rep.blocked and rep.scanned["prompt_files"] == 1, (rep.findings, rep.blocked, rep.scanned))
            card = next((livep / "prompts").rglob("classification.system.yaml"))
            card.rename(card.with_name("classify.system.yaml"))     # breaks the §7 name/path mirror
            rep = m.scan_tree(livep)
            check("live: a prompt card whose path no longer mirrors its name is a BLOCK from the real validator",
                  rep.verdict(False) == ("BLOCK", 1), (rep.findings, rep.blocked))
        else:
            print("  NOT RUN live prompt-validator controls: uv or the prompt scaffold is missing")
        scaffold = m.GOLDEN_VALIDATOR.parent.parent / "assets" / "golden-scaffold"
        if shutil.which(m.UV_RUNNER[0]) and scaffold.is_dir():
            live = base / "live"
            shutil.copytree(scaffold, live)
            rep = m.scan_tree(live)
            check("live: shipped golden scaffold has no BLOCK", "BLOCK" not in {f["level"] for f in rep.findings}
                  and not rep.blocked, (rep.findings, rep.blocked))
            manifest = live / "tests" / "golden" / "features" / "support-answer" / "dataset_manifest.yaml"
            manifest.unlink()
            rep = m.scan_tree(live)
            check("live: removing a feature manifest is a BLOCK from the real validator",
                  rep.verdict(False) == ("BLOCK", 1), (rep.findings, rep.blocked))
        else:
            print("  NOT RUN live golden-validator controls: uv or the golden scaffold is missing")
    m.UV_RUNNER, m.GOVERNANCE_RUNNER, m.GOLDEN_VALIDATOR, m.GOVERNANCE_VALIDATOR, m.PROMPT_VALIDATOR = real
    print("selftest PASS" if failures == 0 else f"selftest FAIL ({failures})")
    return 0 if failures == 0 else 1
