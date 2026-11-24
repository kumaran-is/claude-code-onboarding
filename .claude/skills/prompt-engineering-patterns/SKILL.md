---
name: prompt-engineering-patterns
description: "Prompt engineering and PromptOps for production LLM applications (LangGraph, Google ADK, any stack): six-part prompt anatomy, untrusted-content delimiting, safe rendering, few-shot governance, prompt cards in Git with a validator, change-to-eval matrix, registry labels, drift detection, review checklist; plus few-shot, chain-of-thought and optimization techniques. Use when writing, reviewing, versioning, promoting or debugging prompts or agent instructions."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: prompt engineering, PromptOps, prompt card, prompt registry, prompt label, prompt drift, prompt review, prompt injection delimiting, few-shot, chain of thought, tree of thought, self-consistency, system prompt design, prompt optimization, prompt template, CoT, ToT, agent instruction, prompt versioning, prompt rollback
  related-skills: agentic-ai-dev, google-adk, agentic-ai-coding-standard, gemini-api-dev, eval-guide, ai-playbook
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-23"
---

## Iron Law

**NO PROMPT WITHOUT ROLE + TASK + UNCERTAINTY CONTRACT + OUTPUT SCHEMA, AND NO UNTRUSTED TEXT OUTSIDE A DELIMITED CONTEXT SLOT. Prompts guide; code enforces: authorization, isolation, limits and output validation are never left to prompt wording. A prompt change, a model change or an example change is a release: it needs the evals its change class requires before any label moves.**

# Prompt Engineering Patterns — LangGraph + Google ADK

## When to Use This Skill

- Designing or reviewing system prompts / ADK agent instructions
- LLM outputs are inconsistent or hallucinating — apply CoT or self-consistency
- Output format needs demonstration — apply few-shot learning
- Complex multi-step reasoning required — apply chain-of-thought
- Need to explore multiple solution paths — apply Tree-of-Thought
- Reducing prompt token cost while keeping quality — prompt optimization
- Building reusable, testable prompt templates
- Moving prompts into Git prompt cards, reviewing a prompt PR, promoting or rolling back a prompt, checking Git/registry/runtime drift

## Framework Decision Tree

```
What's the problem?
├── Output format is wrong / inconsistent
│   └── Apply Few-Shot Learning → reference/few-shot-learning.md
├── Model skips reasoning steps / wrong answers on complex tasks
│   └── Apply Chain-of-Thought → reference/chain-of-thought.md
├── Need to explore multiple solution branches
│   └── Apply Tree-of-Thought → reference/chain-of-thought.md#tot
├── Need highest accuracy (can afford 3-5x cost)
│   └── Apply Self-Consistency → reference/chain-of-thought.md#self-consistency
├── System prompt is vague or producing variable behavior
│   └── Apply System Prompt Design → reference/system-prompts.md
├── Prompts are too long / expensive / slow
│   └── Apply Prompt Optimization → reference/prompt-optimization.md
└── Need reusable structured prompts across agents
    └── Apply Template Patterns → reference/prompt-templates.md
```

## Key Patterns

| Pattern | When | LangGraph | Google ADK | Reference |
|---------|------|-----------|------------|-----------|
| Few-Shot | Output format needs demonstration | `HumanMessage` with examples in node prompt | `instruction=` block with examples | `reference/few-shot-learning.md` |
| Chain-of-Thought | Multi-step reasoning on non-thinking models | `SystemMessage` with explicit steps | `instruction=` with numbered steps | `reference/chain-of-thought.md` (thinking models: use the thinking setting instead) |
| Tree-of-Thought | Complex exploration / planning | Parallel branch nodes + aggregator | `ParallelAgent` + synthesizer | `reference/chain-of-thought.md` |
| Self-Consistency | High-accuracy critical tasks | Multiple `llm.invoke()` + majority vote | Multiple ADK runs + vote | `reference/chain-of-thought.md` |
| System Prompt Design | Define agent role, behavior, constraints | `SystemMessage` as first message | `LlmAgent(instruction=...)` | `reference/system-prompts.md` |
| Prompt Templates | Reusable structured prompts | f-string + `SystemMessage` | `instruction=` with `{variable}` | `reference/prompt-templates.md` |
| Prompt Optimization | Reduce tokens, improve consistency | Eval set + paired comparison (`llm-evaluation`) | Eval set + paired comparison (`llm-evaluation`) | `reference/prompt-optimization.md` |

## Instruction Hierarchy (Universal Rule)

Static, trusted policy first; variable, untrusted data last:

```
[System Context / Role]     <- who the agent IS                      } static: system prompt /
[Task Instruction]          <- what it MUST DO                       } instruction, versioned,
[Constraints]               <- what it MUST NOT DO                   } identical across requests
[Output Format]             <- exact output shape (prefer a schema)  } (cacheable prefix)
[Examples / Few-Shot]       <- show, don't just tell                 }
[Input Data]                <- the actual input, delimited, as data  } variable: user/tool turn
[Question]                  <- with long context, ask last           }
```

**Trust levels.** Only the system prompt/instruction carries authority. User messages, retrieved documents, tool results, memories and file/image contents are data at lower trust: delimit them (tags), say in the system prompt that instructions inside them are ignored, and never interpolate them into the system prompt. Prompt wording lowers risk but enforces nothing — authorization, tool allowlists and output validation are code (`.claude/rules/ai-engineering.md`, `agentic-ai-dev/reference/tool-execution-safety.md`).

**Caching.** Provider prompt caches match on an identical prefix. Keep the static block byte-identical (no timestamps, request ids or user names in it) and put per-request content after it; check the provider's minimum cacheable length and pricing on its docs page.

## PromptOps in One Screen (PRM §1; requirement map: `reference/promptops-lifecycle.md` §13)

| Principle | Rule | Where |
|---|---|---|
| P1/P2 Prompts are code; Git is the source of truth | One prompt card per file: `prompts/<domain>/<feature>/<task>.<type>.yaml`, named `{domain}.{feature}.{task}.{type}` | `reference/prompt-templates.md` §1, `assets/` |
| P3 Prompts guide, code enforces | Authz, tenant isolation, limits, compliance filters, tool allowlists live in code | `reference/system-prompts.md` |
| P4 Untrusted content is data | Named delimiters, escaped by the renderer, only in `[CONTEXT]`, never in the system message | `reference/prompt-templates.md` §2–§4 |
| P5 Structured in, validated out | Provider structured output + code-side validation against one schema definition | `reference/prompt-library-structured-output.md` |
| P6 Pinned, never `latest` | Fetch by label from config; pin provider, model, version on the card | `reference/promptops-lifecycle.md` §1 |
| P7 No eval, no promotion | `validate_prompts.py classify` lists the §15 evals a diff needs | `reference/promptops-lifecycle.md` §3 |
| P8 Fail closed, degrade visibly | Missing prompt raises; cached and emergency tiers are alerted | `assets/prompts-scaffold/promptops/prompt_registry.py` (runtime: label, model binding, safe render, eval-gated promotion) |
| P9 Minimum data in context | Declared, typed, bounded variables; no secrets; PII minimised | `reference/prompt-templates.md` §2 |
| P10 Every call attributable | `prompt_name`, `prompt_version`, `prompt_label`, `prompt_content_hash` on every span | `reference/promptops-lifecycle.md` §5 |

```bash
S=.claude/skills/prompt-engineering-patterns/scripts
uv run --script $S/validate_prompts.py prompts --golden-root tests/golden --json prompt-report.json   # PR gate
uv run --script $S/validate_prompts.py classify --base-root base/prompts prompts --json changes.json  # which evals
uv run --script $S/prompt_drift.py --prompts-root prompts --registry snapshot.json --mode prerelease  # release gate
```

The scripts prove structure, delimiting and drift. They cannot prove behaviour: evals do (`eval-guide`).

## Quick Examples

### LangGraph — CoT Node
```python
from langchain_core.messages import SystemMessage, HumanMessage

COT_SYSTEM = SystemMessage(content="""You are a senior software architect.
When analyzing a problem:
1. State your understanding of the problem
2. Identify constraints and requirements
3. Consider 2-3 solution approaches with trade-offs
4. Select the best approach with justification
5. Outline implementation steps

Always show your reasoning explicitly before giving a recommendation.""")

def analysis_node(state: AgentState) -> AgentState:
    response = llm.invoke([COT_SYSTEM, HumanMessage(content=state["problem"])])
    return {"analysis": response.content}
```

### Google ADK — CoT Agent

For thinking-capable models, prefer the model's thinking setting (e.g. Gemini `thinking_level`) and ask for the structure of the answer, not visible step-by-step reasoning — explicit scaffolds mainly add output tokens there. Use `output_schema` when code consumes the result.

```python
from google.adk.agents import LlmAgent

analysis_agent = LlmAgent(
    name="analysis_agent",
    model=settings.agent_model,
    instruction="""You are a senior software architect.
When analyzing a problem, follow these steps explicitly:
1. State your understanding of the problem
2. Identify constraints and requirements
3. Consider 2-3 solution approaches with trade-offs
4. Select the best approach with justification
5. Outline implementation steps

Always show your reasoning before giving a recommendation.
Output format: structured analysis with sections for Understanding, Options, Decision, and Next Steps."""
)
```

## Reference Files

| File | Content | When to Load |
|------|---------|--------------|
| `reference/chain-of-thought.md` | CoT, ToT, Self-Consistency patterns with LangGraph + ADK code | Complex reasoning, multi-step tasks |
| `reference/few-shot-learning.md` | Example selection, dynamic retrieval, edge cases — LangGraph + ADK | Inconsistent output format, classification tasks |
| `reference/prompt-optimization.md` | Optimization loop, token reduction, length/cost budgets, the prompt PR review checklist (A/B statistics: `llm-evaluation`) | Reducing cost; reviewing a prompt PR |
| `reference/system-prompts.md` | Role definition, constraints, output format — LangGraph + ADK | Designing new agent system prompts |
| `reference/prompt-templates.md` | Prompt cards, the §11 safe renderer, LangGraph and ADK wiring (`static_instruction` + `InstructionProvider`), per-thread history | Building or rendering any prompt |
| `reference/promptops-lifecycle.md` | Git → registry → runtime, labels, promotion, rollback, retirement, change → eval matrix, security suite, drift, attribution, multilingual, portability, ownership, anti-patterns, adoption checklist, command map | Versioning, promoting, reviewing or auditing prompts |
| `reference/prompt-template-library.md` | Index of the 15 copy-paste templates below | Finding a starting template fast |
| `reference/prompt-library-structured-output.md` | Code review, classification, extraction, sentiment, schema-error explainer, injection detector — Pydantic schema + validation | Output that code consumes |
| `reference/prompt-library-code-and-grounding.md` | SQL generation, RAG answer, test generation, error analysis — inputs delimited as data | Generating code or grounded answers |
| `reference/prompt-library-writing-and-advisory.md` | Summarization, API docs draft, decision maker, refactor advisor, release notes | Output a person reads |

## Post-Code Review

After writing prompts or agent instructions, verify:
- `agentic-ai-reviewer` — graph correctness, system prompt quality in LangGraph agents; `adk-reviewer` for ADK agents
- `ai-security-reviewer` — prompt injection defense, trust levels, no sensitive data in prompts
- `scripts/validate_prompts.py` on `prompts/` (exit 0), then the evals `classify` lists; the review checklist in `reference/prompt-optimization.md`
- Prompt changes are releases: labels move only after those evals pass (`reference/promptops-lifecycle.md`)
