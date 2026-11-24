---
name: llm-evaluation
description: "Canonical eval metric formulas and statistics: Recall@K, Precision@K, MRR, nDCG, BLEU/ROUGE/BERTScore, paired A/B and McNemar tests, power and sample size, fail-closed regression detection, trajectory scoring. Use when writing or reviewing metric code or comparing models/prompts. Tooling and CI → eval-guide."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: BLEU, ROUGE, BERTScore, MRR, NDCG, Recall@K, Precision@K, metric formula, paired t-test, Wilcoxon, McNemar, bootstrap CI, sample size, statistical significance, A/B test prompts, compare models, regression detector, trajectory score
  related-skills: agentic-ai-dev, google-adk, adk-eval-guide, python-testing-patterns, vector-database
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO EVALUATION CONCLUSION WITHOUT A BASELINE AND THE RIGHT TEST — two variants on the same golden cases are paired data (paired t / Wilcoxon / McNemar, never an independent-samples test). Every eval claim states: metric name and definition, n, test used, effect size with CI, dataset and judge version.**

# LLM Evaluation Skill — Python 3.14 + LangGraph + Google ADK

## When to Use This Skill

- Measuring quality of a RAG agent's retrieval or generation output
- Comparing two prompt variants or model versions before promoting to production
- Detecting metric regressions in CI after code or model changes
- Building an automated eval harness for a LangGraph or Google ADK agent
- Selecting the right metric family for a given eval task (retrieval vs generation vs classification)
- Establishing baseline scores before any optimization work
- Setting up inter-rater agreement to validate human evaluation labels

## Metric Selection Quick Reference

| Eval Task | Primary Metric | Secondary Metric | When NOT to Use |
|-----------|---------------|-----------------|-----------------|
| RAG Retrieval | MRR, NDCG@K | Precision@K, Recall@K | When you have no relevance judgments |
| Text Generation (summarization) | ROUGE-L, BERTScore-F1 | BLEU | When output style matters more than content |
| Classification | F1 (macro) | Precision/Recall | When class imbalance makes accuracy misleading |
| A/B prompt/model comparison (same cases) | paired delta + bootstrap CI, McNemar for pass/fail | Cohen's d | Independent-samples tests on paired data |
| RAG Generation Quality | BERTScore + Groundedness | Perplexity | For factual domain QA |

## Framework Decision Tree

```
What are you evaluating?
├── Retrieval quality (RAG) → reference/evaluation-metrics.md#rag-metrics
├── Text generation quality → reference/evaluation-metrics.md#text-generation
├── Comparing two prompts/models → reference/ab-testing.md
├── Detecting regression vs baseline → reference/ab-testing.md#regression
├── Building full eval harness → reference/evaluation-harness.md
└── Evaluating agent trajectory (tool calls, reasoning steps) → reference/trajectory-evaluation.md
```

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `reference/evaluation-metrics.md` | BLEU, ROUGE, BERTScore; §2 = **canonical** rank metrics (Recall@K, Precision@K, Hit@K, MRR, nDCG) with executed worked examples; groundedness | Implementing or reviewing metric code anywhere in the toolkit |
| `reference/ab-testing.md` | Paired comparison, McNemar, online A/B (Welch + power), model/prompt comparison protocol, fail-closed RegressionDetector | Comparing prompts/models, detecting regressions |
| `reference/evaluation-harness.md` | Full eval harness for LangGraph agents and ADK agents, benchmark runner, inter-rater agreement | Building end-to-end eval pipeline |
| `reference/trajectory-evaluation.md` | 4-pillar evaluation (Effectiveness 40%, Efficiency 20%, Robustness 20%, Safety 20%), safety zero-tolerance, EvaluationResult structure, batch eval, pass/fail gates | Evaluating LangGraph agent trajectories end-to-end |

## Post-Code Review

After implementing any eval pipeline, dispatch the `eval-reviewer` agent to verify:
- The test matches the design (paired for same-case comparisons) and n is sufficient for the claimed delta
- Rank metrics use per-query relevance, dedupe ids, divide Precision@K by K and exclude zero-relevant queries
- Baselines are versioned and the comparator fails closed
- No silent metric failures: an error or an unmeasured metric raises or is reported NOT RUN, never 0.0

Eval process, judge trials, CI tiers and golden-set discipline: `eval-guide`. RAG metric concepts and judge calibration: `rag-evaluator`.
