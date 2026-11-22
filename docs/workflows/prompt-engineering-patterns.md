# Workflow: Prompt Engineering Patterns

**When to use:** Designing or improving system prompts / agent instructions, implementing structured reasoning (CoT, ToT), fixing inconsistent LLM outputs, or building reusable prompt template systems.

**Skill:** `prompt-engineering-patterns`
**Stacks:** Python 3.14 / LangChain + LangGraph · Python 3.14 / Google ADK
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
└── Documents queried repeatedly → CAG (Cache Augmented Generation)
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
    model="gemini-3.1-flash",
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

Use `ParallelAgent` (ADK) or parallel LangGraph nodes when you need to explore multiple approaches:

```python
# Google ADK
from google.adk.agents import ParallelAgent, SequentialAgent, LlmAgent

branch_1 = LlmAgent(name="approach_1", model="gemini-3.1-flash", instruction="Explore approach A...")
branch_2 = LlmAgent(name="approach_2", model="gemini-3.1-flash", instruction="Explore approach B...")
synthesizer = LlmAgent(name="synthesizer", model="gemini-3.1-pro", instruction="Evaluate both approaches and select the best...")

tot_pipeline = SequentialAgent(
    name="tot",
    sub_agents=[ParallelAgent(name="branches", sub_agents=[branch_1, branch_2]), synthesizer]
)
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

**Version your prompts:**
```python
pvc = PromptVersionControl()
pvc.save(name="agent_system", prompt=PROMPT, version="1.1.0",
         metrics={"accuracy": 0.94, "avg_tokens": 320})
```

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

```python
# Minimum test coverage for any prompt change
def test_agent_prompt():
    # 1. Happy path — standard input
    assert agent.invoke(standard_input) produces expected_format

    # 2. Edge case — empty/ambiguous input
    assert agent.invoke(ambiguous_input) asks for clarification or handles gracefully

    # 3. Constraint adherence — off-topic input
    assert agent.invoke(off_topic) does NOT hallucinate outside domain

    # 4. Format compliance — output matches schema
    assert json.loads(agent.invoke(sample_input)) has all required_keys
```

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
