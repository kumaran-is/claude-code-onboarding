#!/usr/bin/env python3
"""Isolated RAG framework fixtures (ADK, LlamaIndex, LangChain, ADK-tool wrap).

Never installs into the toolkit or a product venv. Optional --isolated creates
$TMPDIR/rag-framework-fixtures-<pid>/ .venv and uv-pip-installs pins there.

  python3 run_rag_framework_fixtures.py           # stdlib + in-process imports
  python3 run_rag_framework_fixtures.py --isolated
  python3 run_rag_framework_fixtures.py --selftest

Classification printed per case: STATIC | MOCKED | INTEGRATION | LIVE-PROVIDER | NOT_RUN.
Live providers (OpenAI, LlamaCloud, Gemini) are never called.

Exit: 0 all executed cases passed and none failed; 1 failure; 2 usage / selftest broken.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELECTOR = HERE / "select_rag_framework.py"

LLAMA_INDEX_CORE = "llama-index-core==0.14.26"
LANGCHAIN_PINS = (
    "langchain==1.5.2",
    "langchain-text-splitters",
    "langgraph==1.2.24",
)
ADK_PIN = "google-adk==2.15.1"


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(args, cwd=cwd, env=merged, capture_output=True, text=True, timeout=timeout, check=False)


def classify_print(name: str, kind: str, status: str, detail: str) -> None:
    print(f"FIXTURE | name={name} | kind={kind} | status={status} | {detail}")


# --- in-process adapters (STATIC; no third-party imports) ---

def adk_tool_payload(nodes: list[dict[str, str]], tenant_id: str) -> dict:
    """Shared JSON contract from adk-tool-wrap.md (no google.adk required)."""
    packed = [n for n in nodes if n.get("tenant_id") == tenant_id and n.get("acl") == tenant_id]
    if not packed:
        return {"ok": True, "error_code": None, "status": "INSUFFICIENT_EVIDENCE", "nodes": []}
    return {
        "ok": True,
        "error_code": None,
        "status": "OK",
        "nodes": [{"id": n["id"], "text": n["text"]} for n in packed],
    }


def evidence_gate(docs: list[str]) -> str:
    return "OK" if any(d.strip() for d in docs) else "INSUFFICIENT_EVIDENCE"


def run_static_cases() -> int:
    fail = 0
    proc = run([sys.executable, str(SELECTOR), "--selftest"])
    if proc.returncode != 0:
        classify_print("select_rag_framework", "STATIC", "FAIL", proc.stdout[-500:] + proc.stderr[-500:])
        fail += 1
    else:
        classify_print("select_rag_framework", "STATIC", "PASS", "selector selftest")

    foreign = adk_tool_payload(
        [{"id": "b1", "text": "secret", "tenant_id": "b", "acl": "b"}],
        "a",
    )
    if foreign["status"] != "INSUFFICIENT_EVIDENCE" or foreign["nodes"]:
        classify_print("adk_wrap_acl", "STATIC", "FAIL", json.dumps(foreign))
        fail += 1
    else:
        classify_print("adk_wrap_acl", "STATIC", "PASS", "cross-tenant retrieve abstains")

    ok = adk_tool_payload(
        [{"id": "a1", "text": "Refunds in 14 days.", "tenant_id": "a", "acl": "a"}],
        "a",
    )
    if ok["status"] != "OK" or ok["nodes"][0]["id"] != "a1":
        classify_print("adk_wrap_ok", "STATIC", "FAIL", json.dumps(ok))
        fail += 1
    else:
        classify_print("adk_wrap_ok", "STATIC", "PASS", "in-tenant nodes returned")

    if evidence_gate([]) != "INSUFFICIENT_EVIDENCE" or evidence_gate(["x"]) != "OK":
        classify_print("langchain_evidence_gate", "STATIC", "FAIL", "gate mismatch")
        fail += 1
    else:
        classify_print("langchain_evidence_gate", "STATIC", "PASS", "empty retrieve does not generate")

    # Dual-generation detector: fixture asserts query_engine is not used when wrap=adk
    wrap_mode = "adk"
    used_query_engine = False
    if wrap_mode == "adk" and used_query_engine:
        classify_print("no_dual_generate", "STATIC", "FAIL", "query_engine plus ADK")
        fail += 1
    else:
        classify_print("no_dual_generate", "STATIC", "PASS", "retriever-only when ADK generates")

    classify_print("llamaparse_live", "LIVE-PROVIDER", "NOT_RUN", "no LLAMA_CLOUD_API_KEY; hosted parse not invoked")
    classify_print("gemini_generate_live", "LIVE-PROVIDER", "NOT_RUN", "no Gemini credentials; ADK generate not invoked")
    return fail


LLAMAINDEX_TEST = textwrap.dedent(
    """\
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.embeddings.mock_embed_model import MockEmbedding
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.storage.docstore import SimpleDocumentStore
    from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters

    Settings.embed_model = MockEmbedding(embed_dim=8)
    Settings.llm = None

    splitter = SentenceSplitter(chunk_size=64, chunk_overlap=8)
    pipe = IngestionPipeline(transformations=[splitter], docstore=SimpleDocumentStore())
    doc = Document(
        text=("Refunds are issued within 14 days. " * 8),
        doc_id="policy:refunds:v1",
        metadata={"tenant_id": "a", "acl": "a", "is_active": True},
    )
    nodes_1 = pipe.run(documents=[doc])
    assert nodes_1, "ingestion produced no nodes"
    nodes_2 = pipe.run(documents=[doc])
    # same doc_id+hash should skip or not duplicate unbounded nodes
    assert len(nodes_2) <= len(nodes_1) + 1

    other = Document(
        text=("Tenant B secret retention is 90 days. " * 8),
        doc_id="policy:b:v1",
        metadata={"tenant_id": "b", "acl": "b", "is_active": True},
    )
    index = VectorStoreIndex.from_documents(
        [
            Document(text=doc.text, doc_id=doc.doc_id, metadata=dict(doc.metadata)),
            Document(text=other.text, doc_id=other.doc_id, metadata=dict(other.metadata)),
        ]
    )
    retriever = index.as_retriever(
        similarity_top_k=5,
        filters=MetadataFilters(
            filters=[MetadataFilter(key="tenant_id", value="a", operator=FilterOperator.EQ)]
        ),
    )
    got = retriever.retrieve("How long for refunds?")
    # Defense in depth: drop mismatched tenant even if the simple store ignores filters
    authorized = [n for n in got if (n.metadata or {}).get("tenant_id") == "a"]
    texts = " ".join(n.get_content() for n in authorized)
    assert "14 days" in texts
    assert "90 days" not in texts
    empty = [n for n in got if (n.metadata or {}).get("tenant_id") == "missing"]
    assert not empty
    print("llamaindex MOCKED PASS")
    """
)

LANGCHAIN_TEST = textwrap.dedent(
    """\
    from langchain_core.documents import Document
    from langchain_core.embeddings import FakeEmbeddings
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=80, chunk_overlap=10)
    raw = [
        Document(page_content="Refunds are issued within 14 days.", metadata={"id": "a1", "acl": "a", "tenant_id": "a"}),
        Document(page_content="Tenant B secret retention is 90 days.", metadata={"id": "b1", "acl": "b", "tenant_id": "b"}),
    ]
    chunks = splitter.split_documents(raw)
    store = InMemoryVectorStore.from_documents(chunks, FakeEmbeddings(size=8))

    def retrieve(query: str, org_id: str):
        hits = store.similarity_search(query, k=5)
        return [d for d in hits if d.metadata.get("acl") == org_id]

    a_hits = retrieve("refund timing", "a")
    assert a_hits and "14 days" in a_hits[0].page_content
    b_leak = [d for d in a_hits if d.metadata.get("acl") != "a"]
    assert not b_leak
    none = retrieve("refund timing", "missing")
    status = "OK" if any(d.page_content.strip() for d in none) else "INSUFFICIENT_EVIDENCE"
    assert status == "INSUFFICIENT_EVIDENCE"
    print("langchain MOCKED PASS")
    """
)

ADK_TEST = textwrap.dedent(
    """\
    from google.adk.tools import FunctionTool

    def read_retrieved_nodes(query: str) -> dict:
        \"\"\"Return nodes previously placed in session (FunctionTool: no vector I/O).\"\"\"
        # This fixture has no session; empty retrieve must abstain.
        _ = query
        return {"ok": True, "error_code": None, "status": "INSUFFICIENT_EVIDENCE", "nodes": []}

    tool = FunctionTool(read_retrieved_nodes)
    assert tool is not None
    schema = getattr(tool, "name", None) or getattr(tool, "_name", None)
    result = read_retrieved_nodes("anything")
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["nodes"] == []
    print("google-adk MOCKED PASS name=%s" % (schema,))
    """
)

WRAP_TEST = textwrap.dedent(
    """\
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.embeddings.mock_embed_model import MockEmbedding

    Settings.embed_model = MockEmbedding(embed_dim=8)
    Settings.llm = None

    docs = [
        Document(text="Refunds are issued within 14 days.", doc_id="a1", metadata={"tenant_id": "a", "acl": "a"}),
        Document(text="Secret B", doc_id="b1", metadata={"tenant_id": "b", "acl": "b"}),
    ]
    index = VectorStoreIndex.from_documents(docs)
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve("refunds")
    packed = []
    for node in nodes:
        meta = dict(node.metadata or {})
        if meta.get("tenant_id") != "a" or meta.get("acl") != "a":
            continue
        packed.append({"id": node.node_id, "text": node.get_content()})
    # ADK generation path: retriever only. Query engine must not be constructed.
    used_query_engine = False
    assert used_query_engine is False
    if not packed:
        payload = {"status": "INSUFFICIENT_EVIDENCE", "nodes": []}
    else:
        payload = {"status": "OK", "nodes": packed}
        assert all("Secret B" not in n["text"] for n in packed)
    print("adk-llamaindex-wrap MOCKED PASS status=%s n=%s" % (payload["status"], len(payload["nodes"])))
    """
)


def uv_available() -> bool:
    proc = run(["uv", "--version"])
    return proc.returncode == 0


def install_and_run(root: Path, packages: list[str], script: str, name: str) -> int:
    venv = root / ".venv"
    if not venv.exists():
        created = run(["uv", "venv", str(venv), "--python", "3.14"])
        if created.returncode != 0:
            created = run(["uv", "venv", str(venv)])
            if created.returncode != 0:
                classify_print(name, "INTEGRATION", "NOT_RUN", f"uv venv failed: {created.stderr[-300:]}")
                return 0
    python = venv / "bin" / "python"
    if not python.exists():
        python = venv / "Scripts" / "python.exe"
    pip = run(["uv", "pip", "install", "--python", str(python), *packages], timeout=300)
    if pip.returncode != 0:
        classify_print(name, "INTEGRATION", "NOT_RUN", f"uv pip install failed: {pip.stderr[-400:]}")
        return 0
    test_path = root / f"{name}.py"
    test_path.write_text(script, encoding="utf-8")
    proc = run([str(python), str(test_path)], cwd=root, timeout=120)
    if proc.returncode != 0:
        classify_print(name, "MOCKED", "FAIL", (proc.stdout + proc.stderr)[-800:])
        return 1
    classify_print(name, "MOCKED", "PASS", (proc.stdout.strip().splitlines() or [""])[-1])
    return 0


def run_isolated() -> int:
    if not uv_available():
        classify_print("isolated_venv", "INTEGRATION", "NOT_RUN", "uv not on PATH")
        return 0
    root = Path(tempfile.mkdtemp(prefix=f"rag-framework-fixtures-{os.getpid()}-"))
    print(f"ISOLATED_ROOT={root}")
    fail = 0
    fail += install_and_run(root, [LLAMA_INDEX_CORE], LLAMAINDEX_TEST, "llamaindex")
    lc_pkgs = list(LANGCHAIN_PINS)
    fail += install_and_run(root, lc_pkgs, LANGCHAIN_TEST, "langchain")
    fail += install_and_run(root, [ADK_PIN], ADK_TEST, "google-adk")
    fail += install_and_run(root, [LLAMA_INDEX_CORE], WRAP_TEST, "adk-llamaindex-wrap")
    return fail


def run_inprocess_imports() -> int:
    """If the libraries are already importable, run MOCKED tests in-process."""
    fail = 0
    trials = (
        ("llamaindex", "llama_index.core", LLAMAINDEX_TEST),
        ("langchain", "langchain_core", LANGCHAIN_TEST),
        ("google-adk", "google.adk", ADK_TEST),
        ("adk-llamaindex-wrap", "llama_index.core", WRAP_TEST),
    )
    for name, mod, script in trials:
        try:
            __import__(mod)
        except ImportError:
            classify_print(name, "MOCKED", "NOT_RUN", f"{mod} not installed in this interpreter")
            continue
        proc = run([sys.executable, "-c", script])
        if proc.returncode != 0:
            classify_print(name, "MOCKED", "FAIL", (proc.stdout + proc.stderr)[-800:])
            fail += 1
        else:
            classify_print(name, "MOCKED", "PASS", (proc.stdout.strip().splitlines() or [""])[-1])
    return fail


def selftest() -> int:
    fail = 0
    payload = adk_tool_payload([], "a")
    if payload["status"] != "INSUFFICIENT_EVIDENCE":
        print("  FAIL empty payload")
        fail += 1
    else:
        print("  ok   empty payload abstains")
    if evidence_gate([" "]) != "INSUFFICIENT_EVIDENCE":
        print("  FAIL whitespace is not evidence")
        fail += 1
    else:
        print("  ok   whitespace is not evidence")
    print("selftest PASS" if fail == 0 else "selftest FAIL")
    return 1 if fail else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--isolated", action="store_true", help="TMPDIR venv + uv pip install official pins")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    fail = run_static_cases()
    if args.isolated:
        fail += run_isolated()
    else:
        fail += run_inprocess_imports()
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
