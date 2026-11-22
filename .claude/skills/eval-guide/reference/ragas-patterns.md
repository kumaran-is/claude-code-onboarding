# Ragas Patterns

> Checked against **ragas 0.4.4** (signatures introspected; metric construction executed offline with a dummy client, no judge calls). Query Context7 (`ragas`) before upgrading: the 0.4 metric API differs from 0.2/0.3 and the old one is scheduled for removal in 1.0.

## Install

```toml
# pyproject.toml (eval dependency group)
ragas = "==0.4.4"   # pin exactly; re-verify signatures on every bump
```

Ragas is **not** LangChain-free: 0.4.4 requires `langchain`, `langchain-community` and `langchain-openai` and imports them at `import ragas`. Scope any "no LangChain" rule to direct imports in your own eval code.

## Metrics API (0.4): `ragas.metrics.collections`

```python
# WRONG: deprecated in 0.4, "will be removed in v1.0" (DeprecationWarning at import)
from ragas.metrics import faithfulness
from datasets import Dataset   # old question/answer/contexts/ground_truth schema

# RIGHT
import os
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, FactualCorrectness, Faithfulness

judge = llm_factory(os.environ["EVAL_JUDGE_MODEL"], provider=os.environ["EVAL_JUDGE_PROVIDER"],
                    client=judge_client)            # async client for your provider; never a literal model id
coverage = FactualCorrectness(llm=judge, mode="recall", atomicity="high")  # defaults are f1 / low
faith = Faithfulness(llm=judge)

cov = await coverage.ascore(response=answer, reference=authored_reference)
fth = await faith.ascore(user_input=question, response=answer, retrieved_contexts=chunks)
# case passes only if cov.value >= gate AND fth.value >= gate
```

Verified `ascore` signatures (0.4.4): `Faithfulness(user_input, response, retrieved_contexts)`, `FactualCorrectness(response, reference)`, `AnswerRelevancy(user_input, response)` (constructor needs `llm` and `embeddings`), `ContextPrecision(user_input, reference, retrieved_contexts)`. Samples for `evaluate()` use `SingleTurnSample(user_input, response, retrieved_contexts, reference, ...)` in an `EvaluationDataset`.

## Metric choice

| Metric | Measures | Needs reference? |
|---|---|---|
| `Faithfulness` | supported claims / claims in the answer, against retrieved context (precision / hallucination axis) | no |
| `FactualCorrectness(mode="recall", atomicity="high")` | required facts from the reference that the answer covers | yes (authored) |
| `AnswerRelevancy` | does the answer address the question (regenerated-question similarity; penalises noncommittal answers; not correctness) | no |
| `ContextPrecision` / `ContextRecall` | relevant chunks ranked high / reference claims attributable to retrieved context | yes |
| `ContextUtilization` | reference-free context precision judged against the response; **not** a substitute for `AnswerRelevancy` | no |
| `ToolCallAccuracy(strict_order=True)` / `ToolCallF1` | tool name + args vs reference calls, ordered / order-free; deterministic, no judge | reference calls |
| `TopicAdherence` | conversation stays within reference topics; **not** a tenant/data-scope isolation check | reference topics |

Isolation is a deterministic assertion (zero foreign ids in tool args, results and persisted rows), never a topic metric. Formulas for retrieval metrics: `llm-evaluation/reference/evaluation-metrics.md` §2.

## FactualCorrectness reference contract

- Defaults `mode="f1", atomicity="low"` are wrong for required-fact coverage: f1 penalises a correct superset for extra true claims; low atomicity makes compound claims all-or-nothing, so a correct answer can score 0.0. Precision belongs to `Faithfulness`; gate a case only when both clear.
- The reference is **authored and provenance-backed**: every required fact traces to a canonical source id. Never LLM-generated, never derived from the candidate answer. Split `required_facts` (scored) from `optional_grounded_facts` (allowed, not required).
- Persist the compared reference and response on every scored row.
- Feed metrics the authoritative chunk text stored at ingest, not a truncated preview.

## Classify a 0.0 before acting

Run three probes on the same reference: **CEILING** (response := reference → must score high), **FLOOR** (a contradiction → ~0), **PERTURBATION** (strip citations or raise atomicity; a score change with no fact change is an EVALUATOR artifact). Only a red that survives the probes is a PRODUCT failure. For judge variance use median-of-3 (`../SKILL.md` "Judge variance").

## Tool-call metrics (deterministic, executed)

```python
from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from ragas.metrics.collections import ToolCallAccuracy

conversation = [HumanMessage(content="status of order o-1?"),
                AIMessage(content="", tool_calls=[ToolCall(name="lookup_order", args={"order_id": "o-1"})]),
                ToolMessage(content="shipped"), AIMessage(content="It shipped.")]
score = await ToolCallAccuracy().ascore(
    user_input=conversation, reference_tool_calls=[ToolCall(name="lookup_order", args={"order_id": "o-1"})])
# score.value == 1.0; with args {"order_id": "o-2"} the value is 0.0
```

Use `strict_order=True` only where the domain requires order; assert key arguments (scope ids, amounts) deterministically before any judge.

## Known Gotchas

| Gotcha | Fix |
|--------|-----|
| `from ragas.metrics import X` | `from ragas.metrics.collections import X` (0.4+) |
| `datasets.Dataset` with `question/answer/contexts/ground_truth` | `SingleTurnSample` / `EvaluationDataset` field names |
| "use ContextUtilization instead of answer_relevancy" | Wrong: `AnswerRelevancy` exists; the two measure different things |
| `evaluate()` without `llm=` | Falls back to OpenAI; always pass the judge |
| Ragas async in pytest | `asyncio_mode = "auto"`; see `pytest-harness.md` |

## Example gates (adapt; from `per-agent-thresholds.md`)

| Flow | Metric | Threshold |
|-------|--------|-----------|
| Sequential tool workflow | `ToolCallAccuracy(strict_order=True)` | ≥ 0.9 |
| Document Q&A | `Faithfulness` | ≥ 0.9 |
| Document Q&A | `FactualCorrectness(mode="recall", atomicity="high")` | ≥ 0.85 |
| Retrieval | `ContextPrecision` | ≥ 0.8 |
