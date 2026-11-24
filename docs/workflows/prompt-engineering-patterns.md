# Workflow: Prompt Engineering Patterns

**When to use:** Designing or improving system prompts / agent instructions, implementing structured reasoning (CoT, ToT), fixing inconsistent LLM outputs, building reusable prompt templates, or running PromptOps (prompt cards in Git, review, eval-gated promotion, rollback, drift checks).

**Skill:** `prompt-engineering-patterns`
**Stacks:** Python 3.14 / LangChain + LangGraph · Python 3.14 / Google ADK · any stack for the PromptOps phases (prompt cards and validator are stack-neutral)
**Requirements:** `.claude/skills/prompt-engineering-patterns/reference/promptops-lifecycle.md` (§13 maps every PRM requirement to its home)
**Not applicable to:** Angular, Flutter (frontend — prompting happens in backend agents)

---

## Quick Decision: Which Pattern Do You Need?

```
What's the problem?
├── Output format is wrong / inconsistent → Few-Shot Learning
├── Model skips reasoning steps → Chain-of-Thought (CoT)
├── Need to explore multiple solution paths → Tree-of-Thought (ToT)
├── Need highest accuracy possible → Self-Consistency
├── System prompt is vague → System Prompt Design
├── Prompts are too expensive / slow → Prompt Optimization
├── Need reusable prompts across agents → Prompt Templates
├── Documents queried repeatedly → CAG (Cache Augmented Generation)
└── Prompt is going to production / changing in production → Phases 7–8 (PromptOps)
```

---

## Phase 1 — Load Skill

```
Load skill: prompt-engineering-patterns
```

Then identify which reference to load:

| Problem | Reference File |
|---------|---------------|
| CoT / ToT / Self-Consistency | `reference/chain-of-thought.md` |
| Few-shot, example selection | `reference/few-shot-learning.md` |
| System prompt design | `reference/system-prompts.md` |
| Token reduction, A/B testing | `reference/prompt-optimization.md` |
| Reusable templates | `reference/prompt-templates.md` |
| Copy-paste starting point | `reference/prompt-template-library.md` (index) → `prompt-library-structured-output.md`, `prompt-library-code-and-grounding.md`, `prompt-library-writing-and-advisory.md` |

---

## Phase 2 — System Prompt Design (Start Here for New Agents)

Every agent system prompt must follow the **Instruction Hierarchy**:

```
[Role Definition]       — who the agent IS
[Task Instruction]      — what it MUST DO
[Constraints]           — what it MUST NOT DO
[Output Format]         — exact expected structure
[Examples]              — show, don't just tell (add if format is non-obvious)
```

### LangGraph
```python
from langchain_core.messages import SystemMessage

AGENT_SYSTEM = SystemMessage(content="""You are a [ROLE] specializing in [DOMAIN].

When [TASK DESCRIPTION]:
1. [Step 1]
2. [Step 2]
3. [Step 3]

Output format:
[FIELD 1]: [description]
[FIELD 2]: [description]

Never [CONSTRAINT 1].
Never [CONSTRAINT 2].""")
```

### Google ADK
```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="agent_name",
    model=settings.agent_model,  # model id from config, never a literal
    instruction="""You are a [ROLE] specializing in [DOMAIN].

When [TASK DESCRIPTION]:
1. [Step 1]
2. [Step 2]

Output: [exact format description]
Never [constraint]."""
)
```

**Check:** Does your system prompt have all 5 elements? If not, add what's missing before moving on.

---

## Phase 3 — Add Reasoning Pattern If Needed

### Chain-of-Thought (CoT)

Add to any system prompt when the task requires multi-step reasoning:

```python
# LangGraph — add to SystemMessage
"Think through this step by step:\n1. [step]\n2. [step]\n\nShow your reasoning before giving the final answer."

# ADK — add to instruction=
"Think step by step. Show your reasoning explicitly before giving the final answer."
```

### Tree-of-Thought (ToT) — for complex planning

Use a `Workflow` fan-out (ADK 2.x) or parallel LangGraph nodes when you need to explore multiple approaches:

```python
# Google ADK 2.x (executed on google-adk 2.15.0 with a fixture model, not live)
import asyncio
from typing import Any

from google.adk import Context, Event, Workflow
from google.adk.agents import Agent
from google.adk.workflow import node

branches = [
    Agent(name="approach_1", model=settings.agent_model, instruction="Explore approach A..."),
    Agent(name="approach_2", model=settings.agent_model, instruction="Explore approach B..."),
]
synthesizer = Agent(name="synthesizer", model=settings.synth_model,
                    instruction="Evaluate both approaches and select the best...")


@node(rerun_on_resume=True)
async def explore(ctx: Context, node_input: Any) -> Any:
    drafts = await asyncio.gather(*(ctx.run_node(b, node_input, use_sub_branch=True) for b in branches))
    yield Event(output="\n\n".join(str(d) for d in drafts))


tot_pipeline = Workflow(name="tot", edges=[("START", explore, synthesizer)])  # Runner(node=tot_pipeline, ...)
```

### Self-Consistency — for high-accuracy single answers

Sample 3-5 independent answers, take majority vote. Only for critical decisions:

```python
# LangGraph
answers = [llm.invoke(messages, config={"temperature": 0.7}).content for _ in range(5)]
final = Counter(answers).most_common(1)[0][0]
```

---

## Phase 4 — Add Few-Shot Examples If Output Format Is Non-Obvious

Add 2-3 examples when:
- Output is structured (JSON, SQL, specific format)
- Model keeps getting format wrong despite instructions
- Classification with specific category names

```python
# Add to SystemMessage or instruction= — BEFORE the actual input
"""Examples:
Input: [example 1 input]
Output: [example 1 output]

Input: [example 2 input]
Output: [example 2 output]"""
```

Keep examples <= 3 for simple tasks, <= 5 for complex classification.

---

## Phase 5 — Optimize (After Baseline Is Working)

Only optimize after the prompt produces correct output on the happy path.

**Token reduction checklist:**
- [ ] Remove filler phrases ("Please carefully", "make sure to")
- [ ] Move static content to system prompt (cached, not repeated in every user message)
- [ ] Consolidate duplicate instructions
- [ ] Replace verbose descriptions with concrete examples

**A/B testing:**
```python
# Run both variants on 20+ test cases
result_a = evaluate_prompt(prompt_a, test_cases, llm)
result_b = evaluate_prompt(prompt_b, test_cases, llm)
# Accept only if accuracy delta >= +2% OR token delta >= -15%
```

**Version your prompts:** the prompt lives in a Git prompt card (`prompts/<domain>/<feature>/<task>.<type>.yaml`), and every behaviour change adds a `changelog` entry with its `eval_run`. The registry serves immutable versions by label through one wrapper (`eval-guide/reference/langfuse-prompts.md`). Never use an in-process version store.

---

## Phase 6 — CAG for Repeated Document Queries

If agents repeatedly query the same fixed document set (< 200K tokens), use CAG instead of RAG:

```python
# Load documents into cached context — pay once, reuse many times
DOCS_CONTEXT = load_documents_as_cached_context(["docs/api.md", "docs/runbook.md"])

# First query: full cost (cache miss)
# Subsequent queries: ~90% cheaper (Anthropic prompt cache hit)
messages = build_cag_messages(DOCS_CONTEXT, question=state["question"])
```

See `agentic-ai-dev/reference/agentic-cost-optimization.md#cag` for full implementation.

---

## Phase 7 — Test Before Shipping

Three layers, each with its own evidence:

```bash
S=.claude/skills/prompt-engineering-patterns/scripts
# 1. Structure (deterministic, every PR touching prompts/**): exit 0 pass, 1 BLOCK, 2 unreadable
uv run --script $S/validate_prompts.py prompts --golden-root tests/golden --json prompt-report.json
# 2. Which evals this diff needs (PRM §15, promptops-lifecycle.md §3): typo -> smoke; wording -> full golden; model -> full + red-team ...
uv run --script $S/validate_prompts.py classify --base-root base/prompts prompts --json changes.json
```

3. **Code around the prompt (unit, fake model):** the renderer rejects undeclared, over-length and secret-bearing variables and neutralises delimiter breakout. Untrusted input lands only in the user turn. Schema-invalid output becomes a typed error (`prompt-engineering-patterns/reference/prompt-templates.md` §2, `system-prompts.md` §Testing).
4. **Behaviour (evals):** run the sets `classify` listed on the held-out golden data, compare with the baseline (no regression on critical, safety or isolation cases), and add the §16 prompt security suite for every T1+ prompt (`eval-guide`, `promptops-lifecycle.md` §3–§4). A single assert against a live model is not evidence.

---

## Phase 8 — Promote, Roll Back, Watch for Drift

1. Sync job pushes the card to the registry only on content change and records `content_hash` → label `development`.
2. CI evals pass on that exact version → `staging`. `prompt_drift.py --mode prerelease` must exit 0 (staging serves the Git release content).
3. Staging evals + human approval (independent sign-off for T2/T3) → the release owner moves `production`. New T2/T3 prompts start behind a flag defaulting OFF.
4. Rollback = move `production` back to the previous version; rehearse it before the first promotion.
5. Scheduled drift (`prompt_drift.py --mode scheduled --traces spans.jsonl`): registry edits outside Git, production behind Git, traces on unlabelled versions.

Detail and the command map (create / review / regression / promote / drift / rollback): `prompt-engineering-patterns/reference/promptops-lifecycle.md`.

---

## Framework Selection Cheat Sheet

| Task Type | Framework | Key Trigger Words |
|-----------|-----------|-------------------|
| Expert role + output | RTF | "act as", "you are a" |
| Step-by-step reasoning | CoT | "debug", "analyze", "solve" |
| Multi-phase project | RISEN | "phases", "deliverables", "roadmap" |
| Complex design | RODES | "architecture", "design", "system" |
| Summarize | Chain of Density | "summarize", "compress", "condense" |
| Stakeholder report | RACE | "executive", "presentation", "report" |
| Investigation | RISE | "investigate", "research", "diagnose" |
| Incident | SOAP | "incident", "postmortem", "report" |

---

## Related Workflows

| Workflow | When |
|----------|------|
| [feature-agentic-ai.md](feature-agentic-ai.md) | Full LangGraph agent feature development |
| [feature-google-adk.md](feature-google-adk.md) | Full ADK agent feature development |
| [pgvector-rag-pipeline.md](pgvector-rag-pipeline.md) | RAG pipeline when documents are too large for CAG |
| [llm-evaluation.md](llm-evaluation.md) | Running the eval sets a prompt change requires |
