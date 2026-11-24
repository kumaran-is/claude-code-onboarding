# LLM Evaluation

> **When to use**: When measuring agent quality, comparing prompts or models, detecting regressions, or building a production eval pipeline for LangGraph or Google ADK agents
> **Time estimate**: 10 min for a single metric; 30 min for a full eval harness with regression gate
> **Prerequisites**: The agent or prompt under evaluation is implemented and callable

## Overview

Evaluation workflow for LangGraph and Google ADK agents. Covers automated metrics (BLEU, ROUGE, BERTScore, RAG metrics), A/B testing with statistical significance, regression detection for CI/CD, and LLM-as-judge with bias mitigation.

Primary use cases in this workspace:
- Measuring quality of LangGraph RAG agents and ADK retrieval tools
- Comparing two prompt versions before promoting to production
- Gating deployments on regression tests (CI/CD integration)
- Evaluating generation quality with LLM-as-judge (both pointwise and pairwise)

---

## Iron Law (from `skills/llm-evaluation/SKILL.md`)

> **NO EVALUATION CONCLUSION WITHOUT A BASELINE AND THE RIGHT TEST — two variants on the same golden cases are paired data (paired t / Wilcoxon / McNemar, never an independent-samples test). Every eval claim states: metric name and definition, n, test used, effect size with CI, dataset and judge version.**
>
> Tooling Iron Law (`eval-guide`): deterministic checks decide; an LLM judge only scores semantic quality and never upgrades a case. Security and privacy gates (forbidden tool calls, cross-tenant ids, PII via Presidio) are deterministic code and never depend on a judge.

---

## Phase 1 — Load Skill

```
Load llm-evaluation skill
```

Then choose the right reference file based on the task:

| Task | Reference File |
|------|---------------|
| Implementing BLEU, ROUGE, BERTScore, RAG metrics | `reference/evaluation-metrics.md` |
| Comparing two prompts/models with statistics | `reference/ab-testing.md` |
| Building a full eval harness or regression gate | `reference/evaluation-harness.md` |
| LLM-as-judge with position bias mitigation | `agentic-ai-dev/reference/llm-judge-advanced.md` |
| ADK-specific eval (`adk eval` CLI, evalsets) | `adk-eval-guide` skill |

---

## Phase 2 — Choose Evaluation Type

```
What are you evaluating?
├── Retrieval quality (RAG) → MRR + NDCG@K  (evaluation-metrics.md#rag-metrics)
├── Text generation (summarization, Q&A) → ROUGE-L + BERTScore  (evaluation-metrics.md#text-generation)
├── Comparing two prompts or models → ABTest class  (ab-testing.md)
├── Detecting regression vs baseline → RegressionDetector  (ab-testing.md#regression)
├── Subjective quality (tone, style) → Pairwise judge  (llm-judge-advanced.md)
└── Objective quality (accuracy, groundedness) → Direct scoring  (llm-judge-advanced.md)
```

---

## Phase 3 — Implement Metrics

### LangGraph RAG Agent (example)
```python
from skills.llm_evaluation.evaluation_metrics import (
    calculate_bertscore, calculate_mrr, calculate_ndcg
)

# After running your RAG agent on test cases:
results = {
    "mrr": calculate_mrr(ranked_results, relevant_docs),
    "ndcg_10": calculate_ndcg(ranked_results, relevance_scores, k=10),
    "bertscore_f1": calculate_bertscore(references, hypotheses)["f1"],
}
```

### Google ADK Agent (example)
```python
from google.adk.runners import InMemoryRunner

runner = InMemoryRunner(agent=my_adk_agent)
# Collect outputs, compute same metrics — metrics are framework-agnostic
```

---

## Phase 4 — Statistical Validation (A/B Test or Regression)

### A/B Test: Comparing prompt variants
```python
from skills.llm_evaluation.ab_testing import ABTest

ab = ABTest(variant_a_name="current_prompt", variant_b_name="new_prompt")
# ... populate results from eval runs
report = ab.analyze()

# Decision rule:
# - p < 0.05 AND Cohen's d > 0.5 (medium effect) → promote new prompt
# - p < 0.05 AND Cohen's d < 0.2 (negligible) → difference not meaningful
# - p >= 0.05 → not statistically significant, need more data
```

### Regression Gate: CI/CD integration
```python
from skills.llm_evaluation.ab_testing import RegressionDetector

detector = RegressionDetector(baseline_results=PRODUCTION_BASELINE, threshold=0.05)
report = detector.check_for_regression(new_results)

assert not report["has_regression"], (
    f"Regression detected: {report['regressions']}"
)
```

---

## Phase 5 — LLM Judge (optional, for subjective quality)

For pairwise or direct scoring with bias mitigation:

```
Load: agentic-ai-dev/reference/llm-judge-advanced.md
```

Key decisions:
- **Direct scoring**: Use for objective criteria (factual accuracy, groundedness, instruction following)
- **Pairwise comparison**: Use for subjective preferences (tone, clarity, helpfulness) — always use `pairwise_with_swap` to eliminate position bias
- **Panel of LLMs (PoLL)**: Use for high-stakes decisions (3 models, majority vote)
- **Hierarchical eval**: Use for high-volume (fast screener + deep eval for low-confidence cases)

---

## Phase 6 — Regression Gate in CI/CD

```yaml
# .github/workflows/eval.yml (example)
- name: Run eval regression gate
  run: |
    uv run --locked pytest -m r1 tests/eval/test_regression.py -v
    # test_regression.py uses RegressionDetector with PRODUCTION_BASELINE
  env:
    DEEPEVAL_TELEMETRY_OPT_OUT: "1"
    RAGAS_DO_NOT_TRACK: "true"
    GISKARD_TELEMETRY_DISABLED: "1"
```

R1 (every PR) runs only deterministic checks and scripted/fake models; live judges run in R2/R3 with an explicit judge model and are reported BLOCKED when credentials are absent, never skipped into a PASS. Library pins and current APIs (DeepEval 4.3.4, Ragas 0.4.4 `ragas.metrics.collections`, `giskard-checks` 1.0.7, Langfuse 5.2.0, Presidio 2.2.366): `eval-guide` "Verified pins".

Rule: Store `PRODUCTION_BASELINE` as a committed JSON file updated only on deliberate promotion.

---

## Quick Reference

| Metric | Best For | NOT for |
|--------|---------|---------|
| BERTScore-F1 | Semantic similarity, summarization | Exact match tasks |
| ROUGE-L | Long-form summarization coverage | Style-dependent output |
| BLEU | Translation, short text generation | Long text, style |
| MRR | Retrieval ranking (first relevant doc) | When rank doesn't matter |
| NDCG@K | Retrieval with graded relevance | Binary relevant/not-relevant |
| Groundedness | RAG factual accuracy | Creative generation |
| Cohen's d | Effect size between variants | Single-run comparisons |

---

## Common Pitfalls

- **Evaluating on training data**: Test cases must be held-out; never evaluate on prompts used during development
- **Ignoring variance**: High std/mean > 0.3 means results are unreliable — increase sample size
- **p-value without effect size**: p < 0.05 with Cohen's d = 0.1 is statistically significant but practically meaningless
- **Single metric obsession**: Always use ≥2 metrics; a model can win on BLEU while losing on BERTScore
- **Skipping baseline**: "Score improved" is meaningless without a defined starting point

---

## Related Workflows

- `docs/workflows/multi-agent-patterns.md` — architecture selection for the agents being evaluated
- `docs/workflows/parallel-agents.md` — dispatching eval agents in parallel for large test sets
- `adk-eval-guide` skill — ADK-specific `adk eval` CLI workflow with evalsets and criteria config
