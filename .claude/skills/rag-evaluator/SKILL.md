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
last-reviewed: "2026-11-23"
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
| ANN recall vs exact KNN | Overlap of the ANN top-K with an exact (brute-force) top-K for the same query embedding | Index quality (HNSW/IVF parameters); distinct from Recall@K, which is measured against labelled relevant chunks |

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
| Cited-claim ratio | Answer claims carrying a citation / all answer claims | |
| Correct outcome rate | Expected `NOT_FOUND` / `CONFLICTED` / `STALE` / `HUMAN_REVIEW` outcomes returned as that status (response contract: `rag-architect/references/rag-response-contract.md` §3) | yes, expected outcome |

**Routing (when a structured-vs-RAG router exists):** routing classification accuracy on labelled queries; a low score means the rules or classifier are wrong (`rag-architect/references/query-classification-taxonomy.md` §2).

**Priority:** faithfulness and Recall@K first; add Context Precision (and nDCG@K) as soon as a reranker exists. Evaluate each layer separately: a good end-to-end score can hide a broken layer.

**Isolation and operations (always on):** cross-scope leak count (retrieved or cited chunks outside the caller's scope; **must be 0**, a deterministic check on chunk ids, never a judge), latency p50/p95/p99 and cost per query. Report every retrieval, answer and ops metric **per tenant and per query-type slice** as well as in aggregate: an aggregate can look healthy while one tenant's document format collapses its recall.

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
  query_type: factual            # slice: factual | identifier | broad | multi-part | vague | temporal | comparison | high-stakes
  scope: org_a                   # scope context the query runs under
  expected_chunk_ids: [contractor-policy#c12]
  expected_outcome: ANSWERED     # ANSWERED | PARTIAL | NOT_FOUND | CONFLICTED | STALE | HUMAN_REVIEW (rag-architect/references/rag-response-contract.md §3)
  high_stakes: false             # must be true when query_type is high-stakes
```

**One golden set per query-type slice** (versioned): factual, identifier, broad, multi-part, vague, temporal, comparison, high-stakes. Each entry holds the query, scope context, expected chunk ids, expected answer essentials, expected outcome and a high-stakes flag. ADAPT start: 30–50 per slice, 50–200 in total; grow it from production failures. The YAML above is the authoring view. In CI the cases live in a CSV checked by the closed `eval-guide/assets/schemas/rag_case.schema.json`: the 8 required columns first, in fixed order, then any of the optional `query_type`, `scope`, `expected_outcome`, `high_stakes` columns, spelled as above. Lowercase outcomes, an unknown column or a high-stakes slice without `high_stakes: true` fail validation (GD007). Example: `eval-guide/assets/golden-scaffold/tests/golden/rag/support_kb_golden.csv`; validate with `uv run --script .claude/skills/eval-guide/scripts/validate_golden.py tests/golden`. These are the same values, spelled the same way, as the response contract `status` (`rag-architect/references/rag-response-contract.md` §3), so compare them exactly.

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

**Where the gates apply (every number is an ADAPT default to ratify):**

| Gate | Runs on | Blocks when |
|---|---|---|
| PR | chunking, embedding, retrieval config, reranker, prompt, generation model or routing changes | Recall@10 drops > 3 pts on any slice; faithfulness drops > 2 pts on the high-stakes slice; cited-claim ratio drops > 2 pts; any isolation leak |
| Re-index / embedding-model change | shadow vs active index | any slice regresses beyond the PR thresholds |
| Pre-launch | full suite + red team | below absolute floors, for example recall@20 ≥ 0.85 (factual), faithfulness ≥ 0.9 (≥ 0.95 high-stakes), cited-claim ratio ≥ 0.95 |
| Production | 1–2% sampled shadow judging | sustained drop alerts; failures become golden cases |

A slice drop counts as a regression only when the paired per-query test on that slice agrees (below); the isolation leak gate is absolute.

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

Suggested libraries: `ragas==0.4.4` (`ragas.metrics.collections`, with calibration), `deepeval==4.3.4`, or custom; retrieval rank metrics always come from `llm-evaluation/reference/evaluation-metrics.md` §2 (Ragas 0.4.4 deprecates its id-based context precision/recall with no collections equivalent). Pins verified in `eval-guide` "Verified pins". The framework matters less than having the golden set and running it on every change.

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
