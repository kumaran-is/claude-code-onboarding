---
description: Scaffold a RAG evaluation setup — golden set template, eval runner, canonical metrics, fail-closed CI gate
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# /rag-eval-init — Bootstrap RAG Evaluation

Scaffold a complete RAG evaluation setup. The goal is for the user to have something runnable within 30 minutes that catches regressions.

## Phase 1: Confirm context

Ask:
1. Where should `evals/` live? (default: repo root)
2. Python or another language? (default: Python — matches FastAPI / ADK stack)
3. Does a golden set already exist anywhere? (CSV, spreadsheet, Notion?)
4. Vector DB / retrieval entry point? (so the runner can hit it)

## Phase 2: Create the directory structure

```
evals/
  golden_set.yaml          # Hand-labeled queries
  run_eval.py              # Eval runner (exit 0 PASS / 1 FAIL / 2 NOT RUN / 3 usage or refused)
  rank_metrics.py          # Copied verbatim from llm-evaluation/reference/evaluation-metrics.md §2
  metrics.py               # Aggregation, context precision, answer checks
  baselines/               # One baseline file per golden-set version (sha256), never overwritten
  reports/                 # Per-run reports (gitignored except .gitkeep)
  README.md                # How to add queries, run evals, interpret results
```

## Phase 3: Write the files

### `evals/golden_set.yaml`

Start with 10 placeholder queries spanning happy path / edge case / unanswerable. Show the schema clearly:

```yaml
# RAG Golden Set
# Target: 50+ queries before tuning the system
# Coverage: ~60% happy path, ~20% edge cases, ~20% known unanswerable

version: 1
queries:
  - id: q-001
    question: "REPLACE WITH A TYPICAL USER QUERY"
    category: happy_path
    classification: factual_lookup
    expected_documents:
      - "REPLACE: document_id or path"
    expected_sections:
      - "REPLACE: section name"
    expected_answer_contains:
      - "REPLACE: phrase that must appear"
    must_not_claim:
      - "REPLACE: a violating claim, e.g. a wrong figure (not a topic word)"
    expected_abstention: false

  - id: q-002
    question: "REPLACE WITH AN EDGE CASE — multi-hop or comparison"
    category: edge_case
    classification: comparison
    expected_documents:
      - doc-a
      - doc-b
    expected_answer_contains:
      - "REPLACE"
    expected_abstention: false

  - id: q-003
    question: "REPLACE WITH AN UNANSWERABLE QUERY"
    category: unanswerable
    expected_abstention: true
    abstention_reason_should_mention: "insufficient evidence"

  # ... add 7 more placeholders following the same pattern
```

### `evals/rank_metrics.py`

Copy the module in `.claude/skills/llm-evaluation/reference/evaluation-metrics.md` §2 verbatim (Recall@K, Precision@K, MRR, nDCG, de-duplication, `mean_defined`). It is the single canonical implementation with executed worked examples; do not re-derive the formulas here. Copy its tests too.

### `evals/metrics.py`

```python
"""RAG eval metrics. Rank metrics: rank_metrics.py is evaluation-metrics.md §2 copied verbatim."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from evals.rank_metrics import dedupe, mean_defined, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank


@dataclass(frozen=True)
class RetrievalResult:
    query_id: str
    retrieved_doc_ids: list[str]   # rank order, as returned
    expected_doc_ids: set[str]     # this query's relevant ids (empty for unanswerable queries)


def context_precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float | None:
    """RAGAS definition: sum(Precision@i * v_i) / relevant items in the top K. None if none in top K."""
    hits, total = 0, 0.0
    for i, doc in enumerate(dedupe(ranked)[:k], start=1):
        if doc in relevant:
            hits += 1
            total += hits / i
    return total / hits if hits else None


def aggregate(results: Iterable[RetrievalResult], k: int = 10) -> dict[str, float]:
    """Means over queries where each metric is defined; '<metric>.excluded' counts the rest."""
    rows = list(results)
    per_metric: dict[str, list[float | None]] = {
        f"recall@{k}": [recall_at_k(r.retrieved_doc_ids, r.expected_doc_ids, k) for r in rows],
        f"precision@{k}": [precision_at_k(r.retrieved_doc_ids, r.expected_doc_ids, k) for r in rows],
        f"context_precision@{k}": [context_precision_at_k(r.retrieved_doc_ids, r.expected_doc_ids, k) for r in rows],
        "mrr": [reciprocal_rank(r.retrieved_doc_ids, r.expected_doc_ids) for r in rows],
        f"ndcg@{k}": [ndcg_at_k(r.retrieved_doc_ids, dict.fromkeys(r.expected_doc_ids, 1), k) for r in rows],
    }
    out: dict[str, float] = {}
    for name, values in per_metric.items():
        mean, excluded = mean_defined(values)
        if mean is not None:
            out[name] = mean
        out[f"{name}.excluded"] = float(excluded)
    if "mrr" not in out:
        raise RuntimeError("no query has expected documents: retrieval metrics were not measured")
    return out


def answer_contains_check(answer: str, must_contain: list[str]) -> bool:
    return all(s.lower() in answer.lower() for s in must_contain)


def answer_does_not_claim_check(answer: str, must_not_claim: list[str]) -> bool:
    """must_not_claim lists violating claims ("the cost will be"), not topic words."""
    return not any(s.lower() in answer.lower() for s in must_not_claim)
```

Zero-relevant (unanswerable) queries are **excluded** from retrieval means and scored by `abstention_ok_rate`; the report records how many were excluded.

### `evals/run_eval.py`

A runner with a pluggable RAG callable:

```python
"""
RAG eval runner. Exit codes: 0 PASS, 1 FAIL (regression or floor), 2 NOT RUN (no baseline for this golden set),
3 usage error or refused action (e.g. a baseline for this golden set already exists).

Usage:
    python -m evals.run_eval --rag-callable myapp.rag:answer
    python -m evals.run_eval --rag-callable myapp.rag:answer --record-baseline   # deliberate, reviewed step
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import yaml

from evals.metrics import RetrievalResult, aggregate, answer_contains_check, answer_does_not_claim_check

EVAL_DIR = Path(__file__).parent
GOLDEN = EVAL_DIR / "golden_set.yaml"
BASELINES = EVAL_DIR / "baselines"   # one file per golden-set version; never overwritten
REPORTS = EVAL_DIR / "reports"

MAX_DROP = {"recall@10": 0.02, "ndcg@10": 0.02, "mrr": 0.02, "answer_ok_rate": 0.03, "abstention_ok_rate": 0.05}
FLOORS: dict[str, float] = {}         # absolute floors, e.g. {"abstention_ok_rate": 0.9}, once you have data

RagFn = Callable[[str], dict[str, Any]]


def load_callable(spec: str) -> RagFn:
    mod_path, func_name = spec.split(":")
    fn: RagFn = getattr(importlib.import_module(mod_path), func_name)
    return fn


def run(rag: RagFn, golden: dict[str, Any]) -> dict[str, Any]:
    retrieval: list[RetrievalResult] = []
    per_query: list[dict[str, Any]] = []
    for q in golden["queries"]:
        # Contract: {"answer": str, "retrieved_doc_ids": [str], "abstained": bool}
        response = rag(q["question"])
        expected = set(q.get("expected_documents", []))
        retrieval.append(RetrievalResult(q["id"], response["retrieved_doc_ids"], expected))
        answer_ok = answer_contains_check(
            response["answer"], q.get("expected_answer_contains", [])
        ) and answer_does_not_claim_check(response["answer"], q.get("must_not_claim", []))
        abstention_ok = bool(response["abstained"]) == bool(q.get("expected_abstention", False))
        per_query.append({"id": q["id"], "answer_ok": answer_ok, "abstention_ok": abstention_ok,
                          "passed": answer_ok and abstention_ok})
    planned = len(golden["queries"])
    if planned == 0 or len(per_query) != planned:
        raise RuntimeError(f"accounting: planned {planned}, recorded {len(per_query)}")
    metrics = aggregate(retrieval, k=10)
    metrics["answer_ok_rate"] = sum(r["answer_ok"] for r in per_query) / planned
    metrics["abstention_ok_rate"] = sum(r["abstention_ok"] for r in per_query) / planned
    return {"metrics": metrics, "per_query": per_query, "planned": planned}


def verdict(run_key: str, metrics: dict[str, float]) -> tuple[int, list[str]]:
    path = BASELINES / f"{run_key}.json"
    if not path.exists():
        return 2, [f"no baseline for golden set {run_key}: record one deliberately (--record-baseline)"]
    baseline = json.loads(path.read_text())["metrics"]
    failures = [f"{m}: {metrics.get(m)} below floor {f}" for m, f in FLOORS.items() if metrics.get(m, -1.0) < f]
    for m, drop in MAX_DROP.items():
        if m not in metrics or m not in baseline:
            failures.append(f"{m}: missing from {'run' if m not in metrics else 'baseline'}")
        elif metrics[m] < baseline[m] - drop:
            failures.append(f"{m}: {metrics[m]:.3f} < baseline {baseline[m]:.3f} - {drop}")
    return (1 if failures else 0), failures


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:   # argparse exits 2 by default, which means NOT RUN here
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: error: {message}\n")


def main() -> None:
    parser = _Parser()
    parser.add_argument("--rag-callable", required=True, help="'module.path:function'")
    parser.add_argument("--record-baseline", action="store_true",
                        help="Write the baseline for this golden-set version (refuses to overwrite)")
    args = parser.parse_args()
    raw = GOLDEN.read_bytes()
    run_key = "golden-" + hashlib.sha256(raw).hexdigest()[:12]
    result = run(load_callable(args.rag_callable), yaml.safe_load(raw))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"run-{stamp}.json").write_text(json.dumps({**result, "run_key": run_key}, indent=2))
    if args.record_baseline:
        BASELINES.mkdir(exist_ok=True)
        path = BASELINES / f"{run_key}.json"
        if path.exists():
            refusal = f"{path} exists: a new baseline needs a new golden-set version or a reviewed manual edit"
            print(refusal, file=sys.stderr)  # noqa: T201 - CLI output
            sys.exit(3)                      # refused: distinct from 1 (FAIL)
        path.write_text(json.dumps({"metrics": result["metrics"], "recorded_at": stamp}, indent=2))
        print(f"Baseline recorded: {path}")  # noqa: T201 - CLI output
        return
    code, failures = verdict(run_key, result["metrics"])
    print(json.dumps(result["metrics"], indent=2))  # noqa: T201 - CLI output
    print({0: "PASS", 1: "FAIL", 2: "NOT RUN"}[code], *failures, sep="\n  ")  # noqa: T201 - CLI output
    sys.exit(code)


if __name__ == "__main__":
    main()
```

Verified with a scripted fake RAG callable: no baseline → exit 2 (NOT RUN), `--record-baseline` writes `baselines/golden-<sha>.json` and refuses a second write with exit 3, unchanged run → exit 0, broken answer and retrieval → exit 1 with per-metric reasons. `mypy --strict` and ruff clean (including `T201`: CLI `print()` calls carry `# noqa: T201`; this is a CLI, not service code).

**Gate notes.** On 50-200 queries an absolute drop of 0.02 is inside sampling noise: also compare per-query flips with an exact McNemar test (`llm-evaluation/reference/ab-testing.md`) and set absolute `FLOORS` once you have data. Editing the golden set changes its hash, so the next run is NOT RUN until a baseline is deliberately recorded for the new version.

### LLM-as-judge (v2: not scaffolded)

Do not scaffold judge code in v1. When retrieval and deterministic answer checks are stable, add faithfulness and citation-quality judges following `rag-evaluator` (calibration with Cohen's kappa and false-PASS rate on 100+ human-labelled cases) and `eval-guide` (explicit judge model, median-of-3 trials, judge errors recorded as UNSCORED, never PASS).

### `evals/README.md`

```markdown
# RAG Evaluation

## Quickstart

1. Edit `golden_set.yaml` — replace the 10 placeholder queries with real ones from your domain. Target 50+ before tuning the system.

2. Implement a RAG callable that takes a question and returns:
   ```python
   {
     "answer": "...",
     "retrieved_doc_ids": ["doc-1", "doc-2"],
     "abstained": False,
   }
   ```

3. Run the eval:
   ```bash
   python -m evals.run_eval --rag-callable yourapp.rag:answer
   ```

4. Record the baseline for this golden-set version (a reviewed step; commit the file):
   ```bash
   python -m evals.run_eval --rag-callable yourapp.rag:answer --record-baseline
   ```

5. Wire into CI: exit 1 (regression or floor), exit 2 (no baseline for this golden set) and exit 3 (usage/refused) all fail the job.

## What to evaluate (v1 vs v2)

- v1: retrieval metrics (Recall@K, NDCG, MRR) + content checks (`expected_answer_contains`) + abstention correctness
- v2: LLM-as-judge for faithfulness and citation quality, calibrated against human labels (`rag-evaluator`)

Do not start with LLM-as-judge.

## Coverage target

- 60% happy path
- 20% edge cases (multi-hop, comparison, rare terms)
- 20% known unanswerable (verify abstention)

## CI integration

GitHub Actions:
```yaml
- name: RAG eval gate
  run: uv run --locked python -m evals.run_eval --rag-callable yourapp.rag:answer
  env:
    DEEPEVAL_TELEMETRY_OPT_OUT: "1"     # only if the project also runs DeepEval / Ragas judges
    RAGAS_DO_NOT_TRACK: "true"
```
The runner exits 1 on regression or a floor breach and 2 when no baseline exists for the golden-set version; never mark the step `continue-on-error`.
```

## Phase 4: Confirm and finish

After creating the files:

1. Tell the user what's in each file.
2. Point them at `golden_set.yaml` as the first thing to edit.
3. Suggest implementing the RAG callable signature in their existing pipeline.
4. Remind them: 50 labeled queries is the minimum before tuning.

## Style notes

- Create real, runnable code — not pseudocode placeholders.
- Stack-agnostic where possible; Python because the user said FastAPI + ADK.
- Do not scaffold v2 judges as stubs; point to `rag-evaluator` and `eval-guide` instead.
- Metric formulas come from `llm-evaluation/reference/evaluation-metrics.md` §2, never re-derived.
