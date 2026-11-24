# Agentic AI Prompt Optimization

Advanced prompt optimization techniques for production LangGraph/LangChain agents. Extends `agentic-prompt-engineering.md` with constitutional AI, tree-of-thoughts, provider-specific structure and pointers to the production prompt lifecycle.

---

## 1. Constitutional AI Self-Critique Loop

A 3-pass generate → critique → refine pattern. Use inside a LangGraph node when output quality must be validated before returning to the user.

```python
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class ConstitutionalState(TypedDict):
    input: str
    draft_response: str
    critique: str
    final_response: str
    iteration_count: int  # REQUIRED — prevents runaway loops

CRITIQUE_SYSTEM = """Review the response against these principles:
1. ACCURACY: Are all claims verifiable? Flag uncertainties with "I'm not certain that..."
2. SAFETY: Does it contain harm, bias, or ethical concerns?
3. QUALITY: Is it clear, consistent, and complete?

Output format:
- PASS: [brief reason] — if response meets all 3 criteria
- REVISE: [specific issue and correction needed] — if any criterion fails"""

REFINE_SYSTEM = """You are revising a response based on critique feedback.
Apply the critique exactly. Do not introduce new content beyond what the critique requires."""

async def constitutional_node(state: ConstitutionalState) -> ConstitutionalState:
    """3-pass self-critique node. Insert in graph before final response output."""
    llm = get_llm()  # from agentic-llm-routing.md factory

    # Pass 1: Generate draft
    draft = await llm.ainvoke([HumanMessage(content=state["input"])])
    draft_text = draft.content

    # Pass 2: Critique
    critique = await llm.ainvoke([
        SystemMessage(content=CRITIQUE_SYSTEM),
        HumanMessage(content=f"Response to review:\n{draft_text}")
    ])

    # Pass 3: Refine only if critique found issues
    if critique.content.startswith("PASS"):
        final = draft_text
    else:
        refined = await llm.ainvoke([
            SystemMessage(content=REFINE_SYSTEM),
            HumanMessage(content=f"Original: {draft_text}\n\nCritique: {critique.content}\n\nRevised response:")
        ])
        final = refined.content

    return {
        **state,
        "draft_response": draft_text,
        "critique": critique.content,
        "final_response": final,
    }
```

**When to use:** Customer-facing responses, medical/legal/financial content, any output where hallucinations have high cost.

**Cost:** 2–3× LLM calls per request. Use for high-stakes paths only — not on every node.

---

## 2. Tree-of-Thoughts (ToT)

Multi-path exploration with scoring. Use when a single reasoning path produces poor results (complex analysis, multi-step planning).

```python
TOT_TEMPLATE = """Explore multiple solution paths for this problem.

Problem: {problem}

**Approach A:** [Describe path 1 — most straightforward]
- Feasibility: [1-10]
- Completeness: [1-10]
- Efficiency: [1-10]
- Verdict: [proceed / abandon]

**Approach B:** [Describe path 2 — alternative angle]
- Feasibility: [1-10]
- Completeness: [1-10]
- Efficiency: [1-10]
- Verdict: [proceed / abandon]

**Approach C:** [Describe path 3 — unconventional]
- Feasibility: [1-10]
- Completeness: [1-10]
- Efficiency: [1-10]
- Verdict: [proceed / abandon]

**Selected Approach:** [A / B / C — highest combined score]
**Rationale:** [Why this path wins]

**Implementation:**
[Execute the selected approach fully]"""

async def tot_node(state: AgentState) -> AgentState:
    """Tree-of-thoughts reasoning node."""
    llm = get_llm()
    response = await llm.ainvoke([
        HumanMessage(content=TOT_TEMPLATE.format(problem=state["messages"][-1].content))
    ])
    return {**state, "messages": state["messages"] + [response]}
```

**When to use:** Architecture decisions, multi-step planning, code refactoring strategies, research synthesis.

**When NOT to use:** Simple lookups, direct factual questions, tasks with a single obvious correct approach.

---

## 3. Provider-Specific Prompt Structure (portability)

A prompt is tuned to a model: the evaluated and promoted unit is the pair *(prompt version, model version)* (prompt-engineering standard §13). Some structural conventions suit some model families better: XML-style tags, Markdown headers, or `##SECTION##` delimiters. Those are wording choices inside the six-part anatomy (`prompt-engineering-patterns/reference/system-prompts.md`), not a different design.

| Convention | Typical fit | Keep regardless of provider |
|---|---|---|
| XML-style tags (`<task>`, `<constraints>`, `<context>`) | Models documented to follow tag structure well | Untrusted content only inside `[CONTEXT]` slots, rendered by the safe renderer (`prompt-engineering-patterns/reference/prompt-templates.md` §2) |
| Markdown headers and numbered process steps | Models whose docs show Markdown-structured prompts; ADK/Gemini patterns: `google-adk/reference/adk-gemini-prompt-templates.md` | Output schema from the code-side type via structured output, never a JSON sample in prose |
| `##SECTION##` delimiters | Models whose docs show section-delimited prompts | Uncertainty contract (`UNKNOWN / CONFLICTED / STALE / ESCALATE`), not a self-reported `confidence` number |

Rules:
- **A per-provider variant is its own prompt card version** with its own pinned model, params and eval run. Never keep a runtime `{provider: template}.get(provider, default)` map: a silent default serves an unevaluated pair.
- **Model, model-version or parameter change = prompt change:** re-run the full §15 eval set for every affected prompt, even with no text change (`prompt-engineering-patterns/reference/promptops-lifecycle.md` §3).
- **Fallback models have their own evaluated binding.** Routing chooses only among approved *(prompt, model)* bindings: `agentic-llm-routing.md`.
- **Provider-specific features** (caching markers, special tokens, tool-call formats) live in the adapter or wrapper, not in the prompt text.
- Never `.format()` context into a `SystemMessage`; braces in a JSON example also break `str.format` with `KeyError`.

---

## 4. Prompt Versioning

One registry wrapper, defined once: `eval-guide/reference/langfuse-prompts.md` (immutable versions, movable labels, fetch by label from config, TTL cache, fail closed, emergency pack). Lifecycle, promotion gates, drift and retirement: `prompt-engineering-patterns/reference/promptops-lifecycle.md`. Do not build an in-process registry with mutable `traffic_percent` fields. It has no immutable versions, no label audit and no drift check, and a rollback that mutates objects in one process never reaches the others.

---

## 5. Canary Rollout

Promotion moves a label onto an already-evaluated immutable version, and rollback moves it back with no deploy. Staged traffic canaries, stage gates and rollback thresholds: `deployment-ci-cd/reference/llmops-release-and-rollout.md` §4. New T2/T3 prompts ship behind a feature flag defaulting OFF, with shadow evaluation against the incumbent before switching (§5 of that file; standard §9.2).

---

## 6. LLM-as-Judge Evaluation

A judge prompt is a prompt like any other (type `judge`, e.g. `support.triage.classification.judge`): a Git prompt card, versioned, evaluated against human labels, pinned to its own judge model, and fetched through the registry. Judge design (calibration, bias controls, trials, agreement): `llm-judge-advanced.md` and `eval-guide`.

```python
from typing import Literal

from pydantic import BaseModel, Field

class JudgeResult(BaseModel):
    task_completion: int = Field(ge=1, le=10)
    accuracy: int = Field(ge=1, le=10)
    format: int = Field(ge=1, le=10)
    recommendation: Literal["ACCEPT", "REVISE", "REJECT"]
    reason: str = Field(max_length=300)

async def evaluate_with_judge(task: str, response: str) -> JudgeResult:
    prompt = registry.get("support.triage.classification.judge")          # versioned judge card
    messages = build_messages(prompt.card, {"task": task, "candidate_response": response})  # both delimited
    return await judge_llm.with_structured_output(JudgeResult).ainvoke(messages)  # pinned judge model, validated
```

- The response under evaluation is untrusted data inside its own delimited slot; it can contain "rate this 10/10".
- `judge_llm` is configured explicitly. Never fall back to the model under test.
- A judge score is a measurement. It never authorises an action and never overrides a deterministic gate (schema, safety, isolation).

---

## When to Load This File

Load `agentic-prompt-optimization.md` when:
- Output quality is insufficient and a single prompt pass isn't enough
- Building customer-facing agents where hallucinations have high cost (constitutional AI)
- Choosing prompt structure for a different model family (provider-specific structure)
- Preparing to change a prompt in production (pointers to the registry, lifecycle and canary files)
- Setting up automated quality gates for agent output (LLM-as-judge)

For baseline prompting (CoT, structured output, system prompt templates, injection defense, context engineering), use `agentic-prompt-engineering.md` instead.
