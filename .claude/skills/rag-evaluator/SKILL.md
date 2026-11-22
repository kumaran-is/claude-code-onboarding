---
name: rag-evaluator
description: Use when designing, building, or operating RAG evaluation — golden sets, retrieval metrics (Recall@K, NDCG, MRR), answer metrics (faithfulness, citation accuracy), LLM-as-judge setup and calibration, CI gates for RAG, eval at scale, production sampling, drift detection. Triggers on phrases like "evaluate RAG", "golden set", "RAG metrics", "RAGAS", "faithfulness evaluation", "regression test RAG", "RAG CI".
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  triggers: evaluate RAG, golden set, RAG metrics, RAGAS, faithfulness evaluation, regression test RAG, RAG CI, context precision, judge calibration, abstention eval, citation quality
  related-skills: llm-evaluation, eval-guide, rag-architect, rag-debugger, vector-database
  domain: agentic-ai
  role: specialist
  scope: evaluation
  output-format: guidance
last-reviewed: "2026-11-22"
---

# RAG Evaluation

## Iron Law

**Retrieval is scored on per-query relevance judgments with one canonical metric implementation (`llm-evaluation/reference/evaluation-metrics.md` §2); answers are scored by a calibrated judge whose errors are never counted as passes.** Build evaluation **before** tuning the system, not after.

## Three levels of evaluation

| Level | What it measures |
|---|---|
| Retrieval | Did we fetch the right evidence? |
| Answer | Did the model generate a correct, grounded response? |
| Operational | Latency, cost, abstention rate, drift |

You need all three. Skipping retrieval evaluation is the most common mistake — teams measure answers and miss that retrieval was the actual problem.

## v1 vs v2 evaluation maturity

| Phase | Approach |
|---|---|
| **v1 (launch)** | 50–200 hand-labeled golden queries; retrieval metrics (Recall@K, NDCG); human spot checks; simple faithfulness rubric |
| **v2 (scale)** | LLM-as-judge calibrated against human labels; production-trace eval; synthetic eval generation; drift detection |

**Critical:** do not start with LLM-as-judge. Build the hand-labeled foundation first; an uncalibrated judge gives confident garbage.

## Retrieval metrics

| Metric | Measures | Use when |
|---|---|---|
| Recall@K | Unique relevant docs in top-K / all relevant docs for the query | High-stakes / compliance |
| Precision@K | Relevant docs in top-K / **K** (even when fewer than K came back) | Reducing noise |
| Context Precision | Are relevant chunks ranked near the **top** of retrieved set? | As soon as you add a reranker |
| MRR | 1 / rank of first relevant | Q&A where first hit matters |
| NDCG@K | Ranking quality with graded relevance | Search-style ordering |
| Hit@K | Any relevant doc in top-K? (not "recall") | Coarse baseline |

**Context Precision vs Precision@K:** Precision@K asks "how many of the top-K are relevant?" — binary. Context Precision asks "are the relevant chunks ranked near position 1 or buried at position K?" A reranker can leave Precision@K unchanged while dramatically improving Context Precision. Add this metric as soon as you introduce a reranker — it's the clearest signal of whether the reranker is earning its keep.

**Formula (RAGAS definition):** `Context Precision@K = Σ_{i=1..K} (Precision@i × v_i) / (number of relevant items in the top K)`, where `v_i` is 1 if the chunk at position i is relevant. Dividing by all relevant items in the corpus is a different metric: for flags `[0,1,0,1]` with 3 relevant items in the corpus it gives 0.33 instead of 0.50.

**Canonical code and edge cases** (executed worked examples): `llm-evaluation/reference/evaluation-metrics.md` §2. De-duplicate retrieved ids before scoring; a query with **zero relevant documents is undefined** for Recall/MRR/nDCG: exclude it from those means and score it as an abstention case. nDCG states its gain (linear by default) and builds the ideal ranking from all judged grades, including unretrieved documents. Score on canonical chunk ids and the authoritative chunk text stored at ingest; report raw-retrieval and post-rerank values separately.

## Eval Breakdown by Dimension

When Recall@K or another metric regresses — especially after a corpus growth event — **never treat the aggregate metric as the diagnosis**. Break it down first. The aggregate may hide a regression in one segment while other segments stay healthy.

Dimensions to slice by before touching the pipeline:

| Dimension | How to slice | What a drop isolates |
|---|---|---|
| **Document type** | policy vs. support article vs. manual vs. table | Chunking or parsing problem specific to one format |
| **Recency** | fresh docs (< 30 days) vs. stale docs (> 90 days) | Freshness/version filtering issue; stale docs flooding top-K |
| **Query style** | keyword-heavy vs. semantic / conceptual | Embedding model weakness on one query style; BM25 not covering the other |
| **Query length** | short (≤ 5 tokens) vs. long (≥ 15 tokens) | Short queries may need expansion; long queries may need decomposition |
| **Corpus segment** | department, product line, access tier | Index crowding in one segment; wrong routing; missing sub-index |
| **Near-duplicate rate** | queries where top-3 results are near-identical | Corpus has duplicate/stale documents polluting top-K |

**Rule:** if one dimension shows a sharp drop while others are flat, the root cause is in that segment — fix that segment before changing the global pipeline. See `rag-operations-guide.md §9` for corpus hygiene fixes when duplicates or stale docs are the culprit.

## Answer metrics

| Metric | Measures | Needs reference? |
|---|---|---|
| Faithfulness | Supported claims / all claims in the answer, judged against the retrieved context | no |
| Answer relevance | Similarity of questions regenerated from the answer to the original question; penalises noncommittal answers; **not** correctness | no |
| Context recall | Reference claims attributable to the retrieved context / reference claims | yes |
| Context relevance | Was retrieved context actually useful? | no |
| Factual coverage | Required reference facts present in the answer (Ragas `FactualCorrectness(mode="recall", atomicity="high")`) | yes, authored |
| Citation accuracy | Do citations support the claims? Cited ids must be a subset of ids retrieved for this request | |
| Citation quality (≠ presence) | Does the cited chunk contain the *specific* assertion? | |
| Hallucination rate | Frequency of unsupported assertions | |
| Abstention quality | Refusals when refusal was correct | |
| False Abstention Rate | How often the system refused when retrieved context actually supported an answer | |
| False Answer Rate | How often the system answered when it should have abstained (the dangerous failure) | |

## Citation quality is not citation presence

A common failure: 100% of answers have citations, but 30% of citations don't actually support the specific claim. Build evaluation that checks per-claim support:

```yaml
- query: "What approval is required for external contractors?"
  claim: "External contractors need written approval and a valid certificate"
  citation_must_support:
    - contractor_type: external
    - requirement_type: written_approval
    - requirement_type: certificate
  failing_citations:
    - Generic contractor discussion without approval specificity
    - Discussion of approval without certificate requirement
```

## Golden set design

Build the golden set BEFORE building the system. Minimum viable golden set:

```yaml
- question: What approval is required for external contractors?
  expected_documents:
    - contractor-policy.pdf#page=12
  expected_sections:
    - Approval Requirements
  expected_answer_contains:
    - written approval
    - certificate of compliance
  must_not_claim:                 # the violating claim, not a topic word (a topic ban also matches a correct refusal)
    - "the cost will be"
  expected_classification: policy_question
  expected_abstention: false
```

**Coverage targets:**
- ~60% happy path (typical queries with clear answers)
- ~20% edge cases (rare terms, multi-hop, comparisons)
- ~20% known unanswerable (verify abstention works)

Even 50 labeled queries is dramatically better than zero. Don't wait for perfection; release-gate floors by risk tier are set in the `ai-eval-designer` agent, and at N=50 a pass rate carries a ±0.10 95% CI, so small sets detect only large regressions.

## LLM-as-judge: dangers and mitigations

When you move to LLM-as-judge at scale (RAGAS, TruLens, custom), know the biases:

| Bias | Mitigation |
|---|---|
| Position bias | Randomize position |
| Verbosity bias | Cap or normalize answer length |
| Self-preference bias | Use different model family for judge vs generator |
| Style bias | Score against rubric, not impression |

This skill is the canonical judge-provider rule: prefer a judge from a different model family than the generator; if policy forces the same provider, calibrate against humans and record it.

**Calibration is mandatory before a judge gates anything:**
- 100+ human-labelled cases, stratified by class/slice, including known-bad answers.
- Report a chance-corrected agreement statistic (Cohen's kappa for binary/categorical labels, Spearman/Kendall for scores) and the judge's **false-PASS rate on known-bad answers** (target ~0 for safety rubrics), not raw % agreement. Kappa ≥ 0.6 ("substantial") is a common convention, not a law.
- Pin judge model + rubric version; any change re-runs calibration. Re-check on a schedule against fresh human labels.
- Before classifying a judge 0.0 as a product failure, run CEILING / FLOOR / PERTURBATION probes (`eval-guide/reference/ragas-patterns.md`). For a gate that showed variance, score median-of-3 (`eval-guide/SKILL.md`).

## Eval at scale

| Approach | When |
|---|---|
| Hand-labeled golden set | Always, from day one |
| Synthetic eval generation | Expand coverage; verify 10% by hand |
| Production-trace eval | After 1+ month live; sample real queries, label, feed back (rules below) |
| Drift detection | Monitor distribution shifts in queries, scores, abstention rate |
| Counterfactual eval | Test abstention works — remove answer doc, verify refusal |

**Production sampling:** rate from config (default 0 = off); PII-redacted before data leaves the service; counters for submitted / redacted / skipped; best-effort (never blocks the request); stratify by flow and outcome and oversample low-confidence, thumbs-down and abstentions. Sampled cases enter the dev set first, the held-out set only after labelling and review.

## CI gate pattern

```python
# Eval CI gate (pseudocode). Gate implementation: eval-guide/reference/ci-tiers.md
def rag_ci_gate(change):
    run = run_eval(heldout_set, change)                 # every planned query accounted for
    if run.key != baseline.key:                         # dataset hash, judge + rubric, tier
        fail("baseline mismatch: re-baseline deliberately")
    for metric, floor in ABSOLUTE_FLOORS.items():       # absolute floors always apply
        if run[metric] < floor: fail(metric)
    flips = paired_flips(run, baseline_run)             # per-query fixed vs newly broken
    if mcnemar_or_paired_test(flips).significant_regression: fail("paired regression")
    return PASS if run.complete else NOT_RUN            # missing judge scores are not passes
```

On 50-200 queries an absolute delta of 0.02 is inside sampling noise (±0.05-0.10): use per-query flips with a paired test (`llm-evaluation/reference/ab-testing.md`) plus absolute floors. Deterministic retrieval metrics run on every PR touching the pipeline; judge metrics run in the nightly/pre-release tiers.

## Python + FastAPI eval scaffolding

When the user wants to set up evaluation in a Python/FastAPI project:

```
evals/
  golden_set.yaml          # Hand-labeled queries
  run_eval.py              # Eval runner
  metrics.py               # Retrieval + answer metrics
  judges.py                # LLM-as-judge (v2)
  baselines.json           # Baseline scores for CI comparison
  reports/                 # Per-run reports
```

Suggested libraries: `ragas` (with calibration), `deepeval`, or custom — depends on stack. The framework matters less than having the golden set and running it on every change.

## Diagnostic Matrix

When a metric regresses, use this table to locate the root cause before touching any code. Fix the upstream layer first — don't patch generation when retrieval is broken.

| Bad Metric | Likely Root Cause | Where to Look First |
|---|---|---|
| Low **Recall@K** | Bad chunking (chunks too large/small), weak embedding model, indexing gap, metadata filter too strict | Check chunking strategy, embedding model selection, pre-filter logic |
| Low **Precision@K** | Too many irrelevant chunks retrieved, reranker missing or weak, k too high | Reduce k, add/tune reranker, tighten hybrid retrieval |
| Low **Context Precision** | Reranker missing or underperforming — relevant chunks exist but are buried | Reranker not deployed, or `ef_search`/`nprobe` index params too loose; tune or add cross-encoder |
| Low **Context Relevance** | Semantic drift between query and document vocabulary, poor chunking, wrong retrieval strategy | Check query expansion, embedding model mismatch, chunking granularity |
| Low **Answer Relevance** | Prompt issue, generation model too weak, instructions unclear or conflicting | Audit system prompt, check for prompt injection, try stronger model |
| Low **Faithfulness** | Hallucination, citation enforcement absent in prompt, grounding prompt too weak | Add atomic-claim citation check, tighten grounding instructions, check context packing for noise |

**Key principle:** trace backward from the bad metric to the pipeline layer that owns it. Low Faithfulness is almost always a generation-layer or context-packing problem, not a retrieval problem. Low Recall@K is almost always a retrieval or chunking problem — fixing the prompt won't help.

## How to apply

When asked about RAG evaluation:

1. **Find out their phase.** v1 (no eval yet) needs golden set first. v2 (has eval) needs scale and calibration.
2. **Push back on "we'll evaluate later."** No golden set = flying blind. Even 50 queries beats nothing.
3. **Start with retrieval metrics, not just answer metrics.** Recall@K catches retrieval failures that look like generation failures.
4. **Warn against uncalibrated LLM-as-judge.** It's the most common eval mistake.
5. **Recommend per-claim citation checking** — citation presence is a weak signal.

Reference: full playbook §33–37 (evaluation), §35.2 (citation quality), §37.1 (eval at scale).
