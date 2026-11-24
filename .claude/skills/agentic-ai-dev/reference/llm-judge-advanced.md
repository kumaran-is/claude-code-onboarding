# LLM-as-Judge Advanced — Production Reliability & Bias Mitigation

> This file covers production-grade LLM-as-Judge techniques beyond the basic `evaluate_with_judge()` in `agentic-prompt-optimization.md`. Do NOT duplicate the basic judge — this file is exclusively about reliability and bias mitigation.

---

## Section 1: The Bias Landscape

| Bias Type | Description | Symptom | Mitigation |
|-----------|-------------|---------|-----------|
| Position Bias | First-position response preferred | Response A always "wins" in pairwise | Position swap protocol — always evaluate twice |
| Length Bias | Longer responses rated higher | Verbose answers outscore concise ones | Explicit prompt: "Do NOT prefer based on length"; length-normalized scoring |
| Self-Enhancement Bias | Model rates own outputs higher | Claude judge rates Claude outputs better | Use different model for generation vs evaluation |
| Verbosity Bias | Detailed explanations score higher regardless of accuracy | Padded responses outperform terse correct ones | Criteria-specific rubrics that penalize irrelevant detail |
| Authority Bias | Confident/authoritative tone scores higher | Wrong confident answer beats correct hedged one | Require evidence citation; fact-checking layer |

---

## Section 2: Position Swap Protocol

```python
import asyncio
from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from langchain_anthropic import ChatAnthropic


class PairwiseResult(BaseModel):
    winner: str  # "A" or "B" or "tie"
    confidence: float  # 0.0-1.0
    reasoning: str
    per_criterion: dict[str, str]  # criterion_name -> "A"/"B"/"tie"


async def pairwise_with_swap(
    llm,
    prompt: str,
    response_a: str,
    response_b: str,
    criteria: list[str],
) -> PairwiseResult:
    """Pairwise comparison with mandatory position swap for bias mitigation.

    Pass 1: A first, B second
    Pass 2: B first, A second (mapped back to A/B)
    If passes disagree -> TIE with confidence 0.5
    """
    judge_llm = llm.with_structured_output(PairwiseResult)

    PAIRWISE_SYSTEM = """You are an expert evaluator comparing two AI responses.

## Critical Instructions (READ BEFORE SCORING)
- Do NOT prefer responses because they are longer
- Do NOT prefer responses based on position (first vs second listed)
- Do NOT favor more confident-sounding responses over accurate ones
- Ties are acceptable when responses are genuinely equivalent
- Focus ONLY on quality according to the specified criteria

## Evaluation Criteria
{criteria}

## Original Prompt
{prompt}

## Response A
{response_a}

## Response B
{response_b}

## Instructions
1. Analyze each response independently against each criterion
2. Compare them criterion by criterion
3. Determine overall winner: "A", "B", or "tie"
4. Set confidence: 0.9=very confident, 0.7=fairly confident, 0.5=close call"""

    # Pass 1: A first
    pass1 = await judge_llm.ainvoke([
        SystemMessage(content=PAIRWISE_SYSTEM.format(
            criteria="\n".join(f"- {c}" for c in criteria),
            prompt=prompt,
            response_a=response_a,
            response_b=response_b,
        ))
    ])

    # Pass 2: B first (swap positions — note winner must be remapped)
    pass2_raw = await judge_llm.ainvoke([
        SystemMessage(content=PAIRWISE_SYSTEM.format(
            criteria="\n".join(f"- {c}" for c in criteria),
            prompt=prompt,
            response_a=response_b,  # swapped
            response_b=response_a,  # swapped
        ))
    ])

    # Remap pass2 winner back to A/B (since positions were swapped)
    remap = {"A": "B", "B": "A", "tie": "tie"}
    pass2_winner = remap[pass2_raw.winner]

    # Consistency check
    if pass1.winner == pass2_winner:
        return PairwiseResult(
            winner=pass1.winner,
            confidence=(pass1.confidence + pass2_raw.confidence) / 2,
            reasoning=f"Consistent across both passes. {pass1.reasoning}",
            per_criterion=pass1.per_criterion,
        )
    else:
        # Inconsistent — return tie with low confidence
        return PairwiseResult(
            winner="tie",
            confidence=0.5,
            reasoning=f"Position inconsistency detected. Pass1={pass1.winner}, Pass2={pass2_winner}. Calling tie.",
            per_criterion={c: "tie" for c in criteria},
        )
```

---

## Section 3: Rubric Generation

```python
import asyncio
from typing import Literal
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic


class RubricLevel(BaseModel):
    score: int
    label: str  # "Poor", "Below Average", "Average", "Good", "Excellent"
    description: str
    characteristics: list[str]


class EvaluationRubric(BaseModel):
    criterion_name: str
    criterion_description: str
    scale: str  # "1-5"
    levels: list[RubricLevel]
    edge_cases: list[dict[str, str]]  # {"situation": ..., "guidance": ...}
    scoring_guidelines: list[str]


async def generate_rubric(
    llm,
    criterion_name: str,
    criterion_description: str,
    domain: str,
    scale: Literal["1-3", "1-5", "1-10"] = "1-5",
    strictness: Literal["lenient", "balanced", "strict"] = "balanced",
) -> EvaluationRubric:
    """Generate a domain-specific evaluation rubric for a criterion.

    Chain-of-thought rubric generation: define anchor points first,
    then fill intermediate levels, then add edge cases.
    """
    rubric_llm = llm.with_structured_output(EvaluationRubric)

    RUBRIC_PROMPT = f"""Generate an evaluation rubric for the following criterion.

Criterion: {criterion_name}
Description: {criterion_description}
Domain: {domain}
Scale: {scale}
Strictness: {strictness} (lenient=lower bar, balanced=fair, strict=high standards)

Requirements:
1. Use domain-specific terminology from {domain}
2. Each level must have 3-5 observable characteristics (things an evaluator can see)
3. Include 2-3 edge cases with explicit guidance
4. Strictness={strictness}: adjust score thresholds accordingly
5. One criterion = one measurable aspect (do not mix concerns)"""

    return await rubric_llm.ainvoke([{"role": "user", "content": RUBRIC_PROMPT}])
```

---

## Section 4: Direct Scoring with Rubric

```python
import asyncio
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic


class DirectScoringResult(BaseModel):
    criterion: str
    score: int
    evidence: list[str]  # specific quotes/observations from response
    justification: str  # reasoning BEFORE score (chain-of-thought required)
    improvement: str  # one specific suggestion


async def score_with_rubric(
    llm,
    response: str,
    prompt: str,
    rubric: EvaluationRubric,
) -> DirectScoringResult:
    """Direct scoring using a defined rubric.

    Chain-of-thought is MANDATORY: justification appears before score in prompt
    to improve reliability by 15-25% (Zheng et al., 2023).
    """
    scorer = llm.with_structured_output(DirectScoringResult)

    SCORING_PROMPT = f"""Evaluate this response against the rubric criterion.

## Original Prompt
{prompt}

## Response to Evaluate
{response}

## Criterion: {rubric.criterion_name}
{rubric.criterion_description}

## Rubric
{_format_rubric_levels(rubric.levels)}

## Instructions (follow in order)
1. Find specific evidence in the response (quote actual text)
2. Write your justification comparing evidence to rubric levels
3. THEN assign your score (do not decide score before justifying)
4. Suggest one concrete improvement"""

    return await scorer.ainvoke([{"role": "user", "content": SCORING_PROMPT}])


def _format_rubric_levels(levels: list[RubricLevel]) -> str:
    return "\n".join(
        f"Score {l.score} ({l.label}): {l.description}\n  Characteristics: {', '.join(l.characteristics)}"
        for l in levels
    )
```

---

## Section 5: Scaling Patterns

```python
import asyncio
from collections import Counter
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic


# Panel of LLMs (PoLL) — use multiple models for high-stakes evaluation
async def panel_evaluation(
    llms: list,  # e.g., [claude_llm, gemini_llm, gpt4_llm]
    response: str,
    prompt: str,
    rubric: EvaluationRubric,
) -> dict:
    """Evaluate with multiple LLM judges and aggregate by majority vote.

    Reduces individual model bias. Use for high-stakes decisions.
    Cost: 3x single judge. Worth it for: production model selection,
    critical quality gates, bias-sensitive domains.
    """
    results = await asyncio.gather(*[
        score_with_rubric(llm, response, prompt, rubric)
        for llm in llms
    ])

    scores = [r.score for r in results]
    majority_score = Counter(scores).most_common(1)[0][0]
    agreement = scores.count(majority_score) / len(scores)

    return {
        "majority_score": majority_score,
        "agreement_rate": agreement,
        "individual_scores": scores,
        "high_confidence": agreement >= 2/3,  # 2 of 3 agree
        "reasoning": [r.justification for r in results],
    }


# Hierarchical evaluation — cheap screener + expensive deep eval
async def hierarchical_eval(
    fast_llm,      # e.g., gemini-flash or haiku
    deep_llm,      # e.g., claude-opus or gemini-pro
    response: str,
    prompt: str,
    rubric: EvaluationRubric,
    confidence_threshold: float = 0.8,
) -> DirectScoringResult:
    """Screen with fast model, use deep model only for low-confidence cases.

    Typical cost reduction: 60-70% vs always using deep model.
    """
    screen_result = await score_with_rubric(fast_llm, response, prompt, rubric)

    # Use deep model if fast model is uncertain (near rubric boundaries)
    # Boundaries are at score transitions: 1-2, 2-3, 3-4, 4-5
    is_boundary = (screen_result.score != round(screen_result.score))  # adjust for your scale
    needs_deep_eval = len(screen_result.evidence) < 2  # weak evidence = uncertain

    if needs_deep_eval:
        return await score_with_rubric(deep_llm, response, prompt, rubric)
    return screen_result
```

---

## Section 6: Decision Framework — Direct vs Pairwise

```
Is there an objective ground truth or clear criteria?
+-- Yes -> Direct Scoring
|   Use: factual accuracy, instruction following, format compliance, groundedness
|   Scale: 1-5 with rubric for consistency; 1-10 only with 10 explicit level descriptions
|
+-- No -> Is it a preference or subjective quality judgment?
    +-- Yes -> Pairwise Comparison (use pairwise_with_swap above)
    |   Use: tone, style, persuasiveness, creativity, "which is better"
    |
    +-- No (reference available) -> Reference-Based Direct Scoring
        Use: summarization (vs source), translation (vs reference)
```

---

## Section 7: Common Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Score without justification | Unreliable, can't debug | Chain-of-thought: justification BEFORE score |
| Single-pass pairwise | Position bias corrupts | Always use pairwise_with_swap |
| Overloaded criteria | One criterion measuring 2+ things | Split: one criterion = one aspect |
| Missing edge case guidance | Inconsistent handling of ambiguous cases | Add edge_cases to rubric |
| High confidence + low evidence | Judge is overconfident | Flag when evidence list < 2 items |
| Using judge model = generation model | Self-enhancement bias | Different models for gen vs eval |

---

## Section 8: ADK Integration

Run the two judge passes as ADK agents if your stack is ADK-first, but keep the **swap remap and the agreement check in Python** (`pairwise_with_swap` above): the consistency decision is deterministic and never delegated to a third LLM agent.

```python
import os

from google.adk.agents import LlmAgent
from pydantic import BaseModel


class PairwiseVerdict(BaseModel):
    winner: str          # "A" | "B" | "tie"
    confidence: float
    reasoning: str


def make_pairwise_judge(name: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=os.environ["EVAL_JUDGE_MODEL"],   # config-driven, recorded per result row; never a literal id
        instruction="You are a pairwise evaluator. ...(criteria as in Section 2)...",
        output_schema=PairwiseVerdict,
    )
```

Call the judge once with (A, B) and once with (B, A) as two separate runs, remap the second winner (A↔B, tie stays tie) and compute agreement in code; disagreement is a tie with confidence 0.5, as in `pairwise_with_swap`. Do not chain the passes with `SequentialAgent`: it is deprecated in google-adk 2.x in favour of `Workflow` (`google-adk/SKILL.md`), and an LLM "consistency checker" would turn a deterministic rule into a sampled one. Treat each pass as a judge trial (`eval-guide` "Judge variance and trials"): a failed or unparseable pass is UNSCORED, never a tie.
