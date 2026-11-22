# Evaluation Metrics Reference

Python 3.14 implementations for BLEU, ROUGE, BERTScore, RAG metrics, and custom quality metrics.

## Dependencies

```bash
uv add nltk rouge-score bert-score transformers detoxify torch
```

---

## Section 1: Text Generation Metrics

```python
from __future__ import annotations

import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
from bert_score import score as bert_score_fn

# Download required NLTK data on first use
nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)


def calculate_bleu(reference: str, hypothesis: str) -> float:
    """Calculate sentence-level BLEU score with smoothing.

    Uses SmoothingFunction method4 (geometric mean of modified n-gram precisions
    with epsilon smoothing) to handle zero-count n-grams in short outputs.

    Args:
        reference: Ground-truth reference string.
        hypothesis: Model-generated output string.

    Returns:
        BLEU score in [0.0, 1.0].
    """
    reference_tokens = nltk.word_tokenize(reference.lower())
    hypothesis_tokens = nltk.word_tokenize(hypothesis.lower())
    smoothing = SmoothingFunction().method4
    return sentence_bleu(
        [reference_tokens],
        hypothesis_tokens,
        smoothing_function=smoothing,
    )


def calculate_rouge(reference: str, hypothesis: str) -> dict[str, float]:
    """Calculate ROUGE-1, ROUGE-2, and ROUGE-L F-measures.

    Args:
        reference: Ground-truth reference string.
        hypothesis: Model-generated output string.

    Returns:
        Dict with keys "rouge1", "rouge2", "rougeL", each containing the F-measure.
    """
    scorer = rouge_scorer.RougeScorer(
        ["rouge1", "rouge2", "rougeL"],
        use_stemmer=True,
    )
    scores = scorer.score(reference, hypothesis)
    return {
        "rouge1": scores["rouge1"].fmeasure,
        "rouge2": scores["rouge2"].fmeasure,
        "rougeL": scores["rougeL"].fmeasure,
    }


def calculate_bertscore(
    references: list[str],
    hypotheses: list[str],
    model: str = "microsoft/deberta-xlarge-mnli",
) -> dict[str, float]:
    """Calculate BERTScore precision, recall, and F1 over a batch.

    DeBERTa-xlarge-mnli is recommended for its strong NLI-tuned representations.
    For faster inference at slight quality cost, use "microsoft/deberta-base-mnli".

    Args:
        references: List of ground-truth reference strings.
        hypotheses: List of model-generated output strings (same length).
        model: HuggingFace model ID for BERTScore computation.

    Returns:
        Dict with keys "precision", "recall", "f1" — each is the mean over the batch.

    Raises:
        ValueError: If references and hypotheses have different lengths.
    """
    if len(references) != len(hypotheses):
        raise ValueError(
            f"references and hypotheses must have equal length; "
            f"got {len(references)} vs {len(hypotheses)}"
        )

    precision_tensor, recall_tensor, f1_tensor = bert_score_fn(
        hypotheses,
        references,
        model_type=model,
        verbose=False,
    )

    return {
        "precision": precision_tensor.mean().item(),
        "recall": recall_tensor.mean().item(),
        "f1": f1_tensor.mean().item(),
    }
```

---

## Section 2: Retrieval Rank Metrics (canonical)

This section is the **single canonical home** for Recall@K, Precision@K, Hit@K, MRR and nDCG in this toolkit. `rag-evaluator`, `/rag-eval-init`, `eval-guide` and `vector-database` link here; copy this module verbatim rather than re-deriving it. Executed: the worked examples below run as pytest (6 tests pass, `mypy --strict` clean); the previous versions of these functions failed 4 of them (shared-pool MRR 1.0 instead of 0.75, nDCG 2.13 on duplicates, P@10 = 1.0 for a single hit, Recall = 1.0 or 0.0 for zero-relevant queries).

```python
"""Rank metrics for retrieval evaluation (one query at a time).

Conventions (state them in every report):
- ``ranked`` is the retrieved id list in rank order; duplicates are removed first
  (a chunk earns gain once). Report the duplicate rate separately.
- ``relevant`` / ``grades`` are THIS query's judgments, never a pool shared across queries.
- A query with no relevant documents returns ``None`` (undefined): exclude it from the
  mean and score it as an abstention case instead.
- Precision@K divides by K, even when fewer than K results came back.
- nDCG uses linear gain (grade / log2(rank + 1)); the ideal ranking is built from ALL
  judged grades for the query, including documents that were not retrieved.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def dedupe(ranked: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for doc_id in ranked:
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc_id)
    return out


def duplicate_rate(ranked: Sequence[str]) -> float:
    return 0.0 if not ranked else 1 - len(set(ranked)) / len(ranked)


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return None
    return sum(d in relevant for d in dedupe(ranked)[:k]) / k


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    return len(set(dedupe(ranked)[:k]) & relevant) / len(relevant)


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    return 1.0 if set(dedupe(ranked)[:k]) & relevant else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for rank, doc_id in enumerate(dedupe(ranked), start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[str], grades: dict[str, int], k: int) -> float | None:
    dcg = sum(grades.get(d, 0) / math.log2(i + 1) for i, d in enumerate(dedupe(ranked)[:k], start=1))
    ideal = sorted((g for g in grades.values() if g > 0), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    return None if idcg == 0 else dcg / idcg


def mean_defined(values: Iterable[float | None]) -> tuple[float | None, int]:
    """Mean over defined values plus the count of undefined (excluded) queries."""
    vals = list(values)
    defined = [v for v in vals if v is not None]
    return (sum(defined) / len(defined) if defined else None), len(vals) - len(defined)
```

**Definitions.** Recall@K = unique relevant ids in the top K / all relevant ids for the query. Hit@K = 1 if any relevant id is in the top K (do not call it recall). Precision@K = relevant ids in the top K / K. Reciprocal rank = 1 / rank of the first relevant id; MRR = mean over queries that have relevant ids. nDCG@K = DCG@K / IDCG@K with DCG@K = Σ_{i=1..K} grade_i / log2(i + 1); IDCG uses the top-K grades of all judged documents, retrieved or not. Exponential gain (2^grade - 1) is an alternative: say which one a threshold uses.

**Worked examples (asserted in tests):**

| Case | Input | Correct value | Common wrong value |
|---|---|---|---|
| Per-query MRR | q1 relevant={a} ranked [a]; q2 relevant={b} ranked [a, b] | (1 + 0.5) / 2 = **0.75** | 1.0 with a relevant pool shared across queries |
| K > results | ranked [r1], relevant={r1, r2}, K=10 | P@10 = **0.1** | 1.0 when dividing by results returned |
| Duplicates | ranked [a, a, a], relevant={a: 1}, K=3 | nDCG@3 = **1.0**, P@3 = **0.333**, duplicate rate 0.667 | nDCG 2.13, P@3 1.0 |
| Zero relevant | relevant = {} | **None** (excluded, scored as abstention) | 1.0 (inflates) or 0.0 (deflates) |
| Graded nDCG@5 | ranked [d1..d5]; grades d1=3, d2=2, d3=0, d4=1, d6=2 (d6 not retrieved) | DCG = 3 + 2/log2(3) + 1/log2(5) = 4.6926; IDCG (3,2,2,1) = 5.6926; **0.8243** (exponential gain: 0.8614) | 0.9854 when IDCG is built from the retrieved list only (ignores unretrieved d6) |

```python
# test_rank_metrics.py (excerpt)
def test_mrr_uses_per_query_relevance() -> None:
    mrr, excluded = mean_defined([reciprocal_rank(["a"], {"a"}), reciprocal_rank(["a", "b"], {"b"})])
    assert mrr == pytest.approx(0.75) and excluded == 0

def test_worked_ndcg_at_5() -> None:
    grades = {"d1": 3, "d2": 2, "d3": 0, "d4": 1, "d6": 2}
    assert ndcg_at_k(["d1", "d2", "d3", "d4", "d5"], grades, 5) == pytest.approx(0.8243, abs=1e-4)
```

Report alongside every mean: the number of queries excluded as undefined, the duplicate rate, and raw-retrieval vs post-rerank values separately. Score retrieval on canonical chunk ids, not keyword-substring proxies.

---

## Section 3: Custom Quality Metrics

```python
from transformers import pipeline


def calculate_groundedness(
    response: str,
    context: str,
    nli_model_name: str = "microsoft/deberta-large-mnli",
) -> float:
    """Estimate response groundedness using Natural Language Inference (NLI).

    Treats the context as the NLI premise and the response as the hypothesis.
    The entailment probability indicates how well the response is supported by context.
    Low groundedness suggests hallucination or out-of-context generation.

    Args:
        response: Model-generated response to evaluate.
        context: Retrieved context that the response should be grounded in.
        nli_model_name: HuggingFace NLI model. deberta-large-mnli balances
            quality and inference speed for production use.

    Returns:
        Entailment probability in [0.0, 1.0]. Higher = better grounded.
    """
    nli_pipeline = pipeline(
        "text-classification",
        model=nli_model_name,
        top_k=None,
    )
    # NLI format: premise [SEP] hypothesis
    input_text = f"{context} [SEP] {response}"
    results: list[dict] = nli_pipeline(input_text)[0]  # type: ignore[index]

    label_map = {r["label"].upper(): r["score"] for r in results}
    # DeBERTa-MNLI labels: ENTAILMENT, NEUTRAL, CONTRADICTION
    return label_map.get("ENTAILMENT", 0.0)


def calculate_toxicity(text: str) -> float:
    """Calculate the maximum toxicity score across all toxicity dimensions.

    Uses Detoxify's 'original' Unitary model trained on the Jigsaw Toxic Comment dataset.
    Returns the worst-case score across: toxicity, severe_toxicity, obscene,
    threat, insult, identity_attack.

    Args:
        text: Text to evaluate for toxicity.

    Returns:
        Maximum toxicity score across all categories, in [0.0, 1.0].
        Higher = more toxic. Threshold for flagging: typically >= 0.5.
    """
    from detoxify import Detoxify

    results: dict[str, float] = Detoxify("original").predict(text)
    return max(results.values())
```

---

## Section 4: Metric Selection Rules

| Use Case | Primary | Why |
|----------|---------|-----|
| RAG retrieval ranking | MRR + NDCG@10 | Accounts for rank position, not just presence |
| Summarization quality | ROUGE-L + BERTScore | Content coverage + semantic similarity |
| Factual Q&A | Groundedness + BERTScore | Grounding is critical to prevent hallucination |
| Classification agent | F1-macro | Handles class imbalance; accuracy is misleading |
| Avoid BLEU for... | Long text, style-dependent outputs | N-gram overlap is too simplistic for fluency |

**Important:** Never report a single metric in isolation. Pair complementary metrics:
- ROUGE-L (lexical overlap) + BERTScore (semantic similarity) together surface cases where paraphrasing fools one but not the other.
- MRR + NDCG together surface both "did we find anything?" and "did we rank it well?".
