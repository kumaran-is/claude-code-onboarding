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
├── Comparing two prompts or models → paired_compare + mcnemar_exact  (ab-testing.md)
├── Detecting regression vs baseline → RegressionDetector  (ab-testing.md#regression)
├── Subjective quality (tone, style) → Pairwise judge  (llm-judge-advanced.md)
└── Objective quality (accuracy, groundedness) → Direct scoring  (llm-judge-advanced.md)
```

---

## Phase 3 — Implement Metrics

The metric functions live in the skill reference as copy-in code, not as an importable package: copy `llm-evaluation/reference/evaluation-metrics.md` §2 into your eval module (for example `tests/eval/metrics.py`) with its tests.

```python
from tests.eval.metrics import mean_defined, ndcg_at_k, recall_at_k   # your copy of §2

# per query: ranked ids from the run, relevant ids / grades from the golden case
recall_10, n_defined = mean_defined(recall_at_k(r.ranked_ids, r.relevant_ids, 10) for r in runs)
ndcg_10, _ = mean_defined(ndcg_at_k(r.ranked_ids, r.grades, 10) for r in runs)
```

`None` (a query with no relevant ids) is excluded from the mean and counted, never scored 0.0. For a Google ADK agent, collect trajectories and responses with `adk eval` / `AgentEvaluator` (`adk-eval-guide`); the rank metrics are framework-agnostic.

---

## Phase 4 — Statistical Validation (A/B Test or Regression)

### Comparing two prompt or model variants on the same golden cases (paired)

```python
from tests.eval.stats import mcnemar_exact, paired_compare   # your copy of ab-testing.md Section 1

result = paired_compare(baseline_scores, candidate_scores)    # dicts keyed by case id; refuses different case sets
p_flip = mcnemar_exact(baseline_pass, candidate_pass)         # pass/fail flips
# Promote only on a non-inferior lower bound: result.ci95[0] >= -margin, deterministic gates green,
# and no newly broken critical case. Never on a raw-mean win or a tuning-set improvement.
```

### Regression gate against a versioned baseline (fails closed)

```python
from tests.eval.stats import Baseline, RegressionDetector    # ab-testing.md Section 3

detector = RegressionDetector(baseline=load_baseline(run_key), max_drop={"faithfulness": 0.02})
failures = detector.check(run_key, current_metrics)           # missing baseline / key mismatch = failure
assert not failures, failures
```

In CI prefer the shared gate: write the run as `eval_result.schema.json` and run `eval-guide/scripts/eval_gate.py check --thresholds tests/eval/thresholds.yaml --results <run>.json --json <report>.json` (exit 0 pass, 1 gate failed, 2 invalid input; critical classes gate at 100%).

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
    uv run --locked pytest -m r1 tests/eval -v
    uv run --script .claude/skills/eval-guide/scripts/eval_gate.py check \
      --thresholds tests/eval/thresholds.yaml --results results/r1.json --json results/r1-gate.json
  env:
    DEEPEVAL_TELEMETRY_OPT_OUT: "1"
    RAGAS_DO_NOT_TRACK: "true"
    GISKARD_TELEMETRY_DISABLED: "1"
    PROMPTFOO_DISABLE_TELEMETRY: "1"
```

R1 (every PR) runs only deterministic checks and scripted/fake models; live judges run in R2/R3 with an explicit judge model and are reported BLOCKED when credentials are absent, never skipped into a PASS. Library pins and current APIs (DeepEval 4.3.4, Ragas 0.4.4 `ragas.metrics.collections`, `giskard-checks` 1.0.7, Langfuse 5.2.0, Presidio 2.2.366): `eval-guide` "Verified pins".

Rule: baselines are committed files keyed by dataset version, judge model + rubric version and tier, written only by an explicit reviewed step (current, previous-release and anchor baselines: `eval-guide/reference/golden-dataset.md`).

---

## Phase 7 — Adopting an eval program in a product

The skills hold both the measurement policy and the tooling. Measurement only: runtime guardrails are `ai-playbook` / `ai-launch-check`, organisational controls are `ai-governance`.

1. Fill the inventory (features, corpora with embedding model + dimension, tools with read/write and audit need) and choose one tool per job: `.claude/skills/eval-guide/reference/eval-program-adoption.md` "Inventory" and "Tool selection".
2. Mark all 13 dimensions and map them to tiers: `.claude/skills/eval-guide/SKILL.md` "The 13 dimensions" and "Five layers vs CI tiers".
3. Prove each Day-1 gate (observability boots, prompts seeded, framework eval, judge metrics, RAG metrics, red team, tool suite, one trace, one scraped service, one dashboard) with the "Toolkit proof" column of `eval-program-adoption.md` "Day-1 definition of done". A gate you have not run is NOT RUN, never PASS.
4. Work through the organisation-owned "Adoption checklist" in the same file (rollout order, cost levers, named owners, checklist). Anti-patterns there are review findings for `eval-reviewer`.

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
| Paired delta + bootstrap CI | Effect size between variants on the same cases | Independent-samples comparisons |

---

## Common Pitfalls

- **Evaluating on training data**: Test cases must be held-out; never evaluate on prompts used during development
- **Ignoring variance**: High std/mean > 0.3 means results are unreliable — increase sample size
- **p-value without effect size**: report the paired mean delta with its bootstrap CI; a significant p-value with a negligible delta is not a reason to ship
- **Single metric obsession**: Always use ≥2 metrics; a model can win on BLEU while losing on BERTScore
- **Skipping baseline**: "Score improved" is meaningless without a defined starting point

---

## Related Workflows

- `docs/workflows/multi-agent-patterns.md` — architecture selection for the agents being evaluated
- `docs/workflows/parallel-agents.md` — dispatching eval agents in parallel for large test sets
- `adk-eval-guide` skill — ADK-specific `adk eval` CLI workflow with evalsets and criteria config
