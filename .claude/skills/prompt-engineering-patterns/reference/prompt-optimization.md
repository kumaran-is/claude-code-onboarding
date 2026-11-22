# Prompt Optimization

> Referenced by `prompt-engineering-patterns` SKILL.md. Covers systematic refinement, A/B testing, token reduction, versioning, and production metrics.

## Optimization Process

```
1. Establish baseline (accuracy, tokens, latency, success rate)
2. Identify failure category (format, factual, logic, incomplete, hallucination)
3. Apply one change at a time
4. Test on the same golden cases for both variants; size the set for the effect you need to detect (`llm-evaluation` skill, `reference/ab-testing.md` — power and sample size)
5. Measure all metrics (not just accuracy)
6. Accept a change only if a paired comparison on the same cases shows an improvement whose confidence interval excludes zero (`llm-evaluation` skill, `reference/ab-testing.md`) and no guarded metric (safety, cost, latency) regresses
7. Version and document
```

---

## Failure Categories

Before optimizing, classify what's failing:

| Category | Description | Fix |
|----------|-------------|-----|
| Format failures | Wrong output structure | Add explicit format with example |
| Factual errors | Hallucinated facts | Add "only use provided context" constraint |
| Logic errors | Wrong reasoning | Add CoT / verification step |
| Incomplete | Cuts off mid-response | Reduce prompt size or increase max_tokens |
| Off-topic | Drifts from task | Strengthen role definition + hard constraints |
| Inconsistent | Different output each run | Add few-shot examples, use structured output; lower temperature only on models that document it helps (Gemini 3.x guidance: keep the default) |

---

## A/B Testing Framework

```python
import statistics
import time
from dataclasses import dataclass

@dataclass
class PromptTestResult:
    prompt_id: str
    accuracy: float
    avg_tokens: float
    avg_latency_ms: float
    success_rate: float
    sample_size: int


def evaluate_prompt(prompt: str, test_cases: list[dict], llm) -> PromptTestResult:
    """Evaluate a prompt against a test suite."""
    results = []

    for case in test_cases:
        start = time.time()
        response = llm.invoke(prompt.format(**case["inputs"]))
        latency = (time.time() - start) * 1000

        correct = case["expected"] in response.content
        results.append({
            "correct": correct,
            "tokens": response.usage_metadata.get("total_tokens", 0),
            "latency_ms": latency,
            "success": not response.content.startswith("I cannot")
        })

    return PromptTestResult(
        prompt_id=prompt[:40],
        accuracy=sum(r["correct"] for r in results) / len(results),
        avg_tokens=statistics.mean(r["tokens"] for r in results),
        avg_latency_ms=statistics.mean(r["latency_ms"] for r in results),
        success_rate=sum(r["success"] for r in results) / len(results),
        sample_size=len(results)
    )

```

`evaluate_prompt` gives descriptive numbers for one variant. To compare two variants, keep per-case outcomes for both on the same cases and use the paired procedure in `llm-evaluation/reference/ab-testing.md` (McNemar for pass/fail, paired bootstrap CI for scores, fail-closed regression check). Do not pick a winner from raw accuracy deltas or use independent-samples tests on paired data.

---

## Token Reduction Techniques

```python
# BEFORE: verbose, redundant
verbose_prompt = """
Please carefully analyze the following code that has been provided to you.
Your task is to review the code thoroughly and identify any issues, bugs,
problems, or potential improvements that you think would be helpful.
Please make sure to look at everything carefully.
Code: {code}
"""

# AFTER: concise, same quality
concise_prompt = """Review this code for bugs, security issues, and improvements.
Code: {code}
Output: Issues (severity, line, description), Fixes (code diff)"""

# Savings: ~60 tokens -> ~20 tokens per request = 66% reduction
```

**Reduction checklist:**
- [ ] Remove filler phrases ("Please", "carefully", "make sure to")
- [ ] Consolidate repeated instructions into one
- [ ] Move static content to system prompt (cached, not repeated)
- [ ] Use abbreviations consistently (after first definition)
- [ ] Replace paragraphs with bullet lists

---

## Prompt Versioning

Treat prompts as code: version, changelog, eval before promotion, rollback. The canonical registry pattern (versions, labels, promotion gate, rollback) is `eval-guide/reference/langfuse-prompts.md`; release and rollout rules are in `deployment-ci-cd/reference/llmops-release-and-rollout.md`. Do not build a second file-based registry. Log the prompt version id with every model call so traces and evals can be joined.

## Production Metrics to Track

```python
# Track these per prompt in production
PROMPT_METRICS = {
    "accuracy": "% outputs matching expected (requires labeling)",
    "success_rate": "% outputs that are non-error, non-refusal",
    "avg_tokens_input": "average input token count",
    "avg_tokens_output": "average output token count",
    "latency_p50": "median response time in ms",
    "latency_p95": "95th percentile latency in ms",
    "cost_per_1k_requests": "total LLM cost per 1000 calls"
}
```

---

## Common Optimization Patterns

| Pattern | When | Before | After |
|---------|------|--------|-------|
| Add structure | Format inconsistent | "Analyze the bug" | "Output: Bug (line, description), Root Cause, Fix (code)" |
| Add examples | Format wrong | Description of format | 1-2 concrete examples |
| Add constraints | Off-topic responses | No boundaries | "ONLY answer questions about [domain]" |
| Add verification | Logic errors | Single pass | "After answering, verify your answer against..." |
| Split prompt | Too many tasks | One long instruction | Separate prompts per node/agent |

---

## Prompt Problem Diagnosis

Before optimizing a prompt, identify the failure pattern:

| Symptom | Root Cause | Primary Fix |
|---------|-----------|-------------|
| Generic, unhelpful answers | Missing role + context | Add explicit role, domain, and situation |
| Inconsistent output format | No format specification | Add explicit output format with example |
| Confident wrong answers (hallucination) | No uncertainty instruction | Add "if unsure, say 'I don't know'" |
| Different answers each run (high variance) | No examples anchoring behavior | Add 2-3 few-shot examples covering edge cases |
| Verbose padded responses | No length constraint | Add explicit word/sentence/bullet count limit |
| Prompt works in playground, fails in prod | Token limit exceeded or system prompt missing | Check token count; verify system prompt delivery |
| Output ignores format instructions | Instructions at wrong position | Move format instructions to END of prompt, after examples |

---

## Pre-Production Prompt Audit Checklist

Before using a prompt in production, verify all items:

```
□ Role/persona explicitly defined (who the LLM IS in this interaction)
□ Output format explicitly specified (JSON schema / markdown structure / plain prose)
□ Length constraint present for responses that should be concise
□ Hallucination guard present for factual tasks ("say I don't know if unsure")
□ Edge cases tested: empty input, ambiguous data, out-of-domain question
□ Tested on 5+ varied real inputs (not just happy path)
□ Temperature set appropriately: 0.0-0.3 for factual/structured, 0.7 for creative
□ Negative instructions paired with positive alternatives ("don't be verbose" → "respond in 3 bullets")
□ User input uses delimiters (```, <tags>, ---) to separate from instructions
□ Prompt versioned in source control with change log entry
```

**LangGraph:** Put this checklist in a PR description whenever `SystemMessage` content changes.
**Google ADK:** Run this checklist whenever `LlmAgent(instruction=...)` is modified.
