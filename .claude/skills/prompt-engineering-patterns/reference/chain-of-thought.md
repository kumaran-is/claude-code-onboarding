# Chain-of-Thought, Tree-of-Thought, and Self-Consistency

> Referenced by `prompt-engineering-patterns` SKILL.md. Contains CoT, ToT, and Self-Consistency patterns adapted for LangGraph and Google ADK.

## When to Use

| Task Type | Use CoT | Use ToT | Use Self-Consistency |
|-----------|---------|---------|---------------------|
| Math / logic problems | Yes | No | Yes (high accuracy needed) |
| Code debugging | Yes | No | No |
| Multi-step planning | Yes | Yes | No |
| Complex design decisions | No | Yes | No |
| Critical single answers | No | No | Yes |
| Simple facts / lookups | No | No | No — just ask directly |

---

## Chain-of-Thought (CoT)

### Zero-Shot CoT

Add a "think step by step" trigger — for **non-thinking** models. Models with built-in reasoning (Gemini thinking models, other providers' reasoning models) already reason internally; an explicit scaffold mostly adds output tokens and latency. For them, set the thinking level/budget, ask for the answer's structure, and judge the change with evals.

**LangGraph:**
```python
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model=settings.llm_model)  # model id from config

def reasoning_node(state: AgentState) -> AgentState:
    messages = [
        SystemMessage(content="""You are an expert analyst.
Think through problems step by step before answering.
Show your reasoning explicitly. End with a clear conclusion."""),
        HumanMessage(content=f"Problem: {state['problem']}\n\nLet's think step by step:")
    ]
    response = llm.invoke(messages)
    return {"reasoning": response.content}
```

**Google ADK:**
```python
from google.adk.agents import LlmAgent

reasoning_agent = LlmAgent(
    name="reasoning_agent",
    model=settings.agent_model,
    instruction="""You are an expert analyst.
Think through problems step by step before answering.

Always structure your response:
Step 1: [Understand the problem]
Step 2: [Identify relevant information]
Step 3: [Apply reasoning]
Step 4: [Verify your answer]
Conclusion: [Final answer]"""
)
```

---

### Few-Shot CoT

Provide examples with explicit reasoning chains.

**LangGraph:**
```python
FEW_SHOT_COT_SYSTEM = """You are a SQL expert. Convert natural language to SQL.

Example 1:
Input: "Find users registered in the last 30 days"
Reasoning:
- We need the users table
- Filter by registration date within 30 days of today
- Use NOW() - INTERVAL for date math
Output: SELECT * FROM users WHERE created_at > NOW() - INTERVAL 30 DAY;

Example 2:
Input: "Count orders grouped by status"
Reasoning:
- We need the orders table
- COUNT(*) for each group
- GROUP BY the status column
Output: SELECT status, COUNT(*) as count FROM orders GROUP BY status;

Now convert the following query using the same step-by-step reasoning."""
```

**Google ADK:**
```python
sql_agent = LlmAgent(
    name="sql_agent",
    model=settings.agent_model,
    instruction="""You are a SQL expert. Convert natural language to SQL.

Example 1:
Input: Find users registered in the last 30 days
Reasoning: Need users table, filter created_at > NOW() - 30 days
SQL: SELECT * FROM users WHERE created_at > NOW() - INTERVAL 30 DAY;

Example 2:
Input: Count orders by status
Reasoning: Need orders table, COUNT(*) per GROUP BY status
SQL: SELECT status, COUNT(*) FROM orders GROUP BY status;

Follow the same Reasoning -> SQL pattern for each request.
Output format: Reasoning on first line, SQL in a code block."""
)
```

---

## Self-Consistency {#self-consistency}

Generate N reasoning paths independently, take majority vote. Use when accuracy is critical and cost is secondary.

**LangGraph:**
```python
from collections import Counter
from langchain_core.messages import SystemMessage, HumanMessage

def self_consistency_node(state: AgentState) -> AgentState:
    """Sample 5 reasoning paths, return majority answer."""
    prompt = [
        SystemMessage(content="You are an expert. Solve the problem step by step."),
        HumanMessage(content=state["problem"])
    ]

    # Generate N independent samples
    N = 5
    answers = []
    for _ in range(N):
        response = llm.invoke(prompt)  # sampling diversity comes from the default temperature;
        # Gemini 3.x: keep the default (lowering it can cause loops); check your provider's guidance
        # Extract final answer (last line or after "Answer:")
        answer = response.content.split("Answer:")[-1].strip()
        answers.append(answer)

    # Majority vote
    majority_answer = Counter(answers).most_common(1)[0][0]
    return {"answer": majority_answer, "all_answers": answers}
```

**Google ADK (via multiple sequential runs):**
```python
import asyncio
from collections import Counter
from google.adk.agents import RunConfig
from google.adk.runners import Runner
from google.genai import types

async def self_consistent_answer(question: str, n_samples: int = 5) -> str:
    """Run agent N times, return majority answer."""
    runner = Runner(
        agent=analysis_agent,
        app_name="consistency_check",
        session_service=session_service
    )

    answers = []
    for i in range(n_samples):
        session = await session_service.create_session(
            app_name="consistency_check",
            user_id=f"run_{i}"
        )
        final_text = ""
        async for event in runner.run_async(          # an async generator: iterate, never await
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=question)]),
            run_config=RunConfig(max_llm_calls=5),
        ):
            if event.is_final_response() and event.content:
                final_text = "".join(p.text for p in event.content.parts or [] if p.text)
        answers.append(final_text.strip())

    return Counter(answers).most_common(1)[0][0]
```

**Cost warning:** Self-consistency multiplies your LLM cost by N. Use only for high-stakes single answers.

---

## Tree-of-Thought (ToT) {#tot}

Explore multiple reasoning branches in parallel, synthesize the best path. Use for complex planning and design decisions.

**LangGraph — Parallel Branch + Synthesis:**
```python
from langgraph.graph import StateGraph
from langchain_core.messages import SystemMessage, HumanMessage
from typing import TypedDict

class ToTState(TypedDict):
    problem: str
    branch_a: str
    branch_b: str
    branch_c: str
    synthesis: str

def branch_a_node(state: ToTState) -> ToTState:
    """Explore approach A."""
    response = llm.invoke([
        SystemMessage(content="You are exploring Approach A: microservices architecture. Think through pros, cons, and implementation."),
        HumanMessage(content=state["problem"])
    ])
    return {"branch_a": response.content}

def branch_b_node(state: ToTState) -> ToTState:
    """Explore approach B."""
    response = llm.invoke([
        SystemMessage(content="You are exploring Approach B: modular monolith. Think through pros, cons, and implementation."),
        HumanMessage(content=state["problem"])
    ])
    return {"branch_b": response.content}

def branch_c_node(state: ToTState) -> ToTState:
    """Explore approach C."""
    response = llm.invoke([
        SystemMessage(content="You are exploring Approach C: serverless functions. Think through pros, cons, and implementation."),
        HumanMessage(content=state["problem"])
    ])
    return {"branch_c": response.content}

def synthesizer_node(state: ToTState) -> ToTState:
    """Select best branch."""
    synthesis_prompt = f"""Three architectural approaches have been explored:

Approach A (Microservices):
{state['branch_a']}

Approach B (Modular Monolith):
{state['branch_b']}

Approach C (Serverless):
{state['branch_c']}

Evaluate each approach against the original problem. Select the best approach and explain why.
Original problem: {state['problem']}"""

    response = llm.invoke([HumanMessage(content=synthesis_prompt)])
    return {"synthesis": response.content}

# Build ToT graph with parallel branches
tot_graph = StateGraph(ToTState)
tot_graph.add_node("branch_a", branch_a_node)
tot_graph.add_node("branch_b", branch_b_node)
tot_graph.add_node("branch_c", branch_c_node)
tot_graph.add_node("synthesizer", synthesizer_node)

tot_graph.set_entry_point("branch_a")
tot_graph.add_edge("branch_a", "synthesizer")
tot_graph.add_edge("branch_b", "synthesizer")
tot_graph.add_edge("branch_c", "synthesizer")
```

**Google ADK — Workflow + JoinNode (2.x).** `ParallelAgent`/`SequentialAgent` are deprecated (`google-adk/reference/adk-agent-types.md` §1). **NOT TESTED on 2.15.1.**
```python
from google.adk.agents import LlmAgent
from google.adk.workflow import JoinNode, Workflow

branch_a = LlmAgent(
    name="microservices_explorer",
    model=settings.agent_model,
    instruction="Explore the microservices approach for the given problem. Analyze pros, cons, complexity, and fit.",
)
branch_b = LlmAgent(
    name="monolith_explorer",
    model=settings.agent_model,
    instruction="Explore the modular monolith approach. Analyze pros, cons, complexity, and fit.",
)
branch_c = LlmAgent(
    name="serverless_explorer",
    model=settings.agent_model,
    instruction="Explore the serverless approach. Analyze pros, cons, complexity, and fit.",
)
gather = JoinNode(name="gather")
synthesizer = LlmAgent(
    name="synthesizer",
    model=settings.reasoning_model,  # a stronger configured model for synthesis
    instruction="""Review the three architectural explorations from the joined nodes.
Select the best approach based on the original problem requirements.
Output: Decision (which approach), Rationale (3 bullet points), Risk Mitigation (top 2 risks).""",
)
tot_pipeline = Workflow(
    name="tot_pipeline",
    edges=[
        ("START", branch_a, gather),
        ("START", branch_b, gather),
        ("START", branch_c, gather),
        (gather, synthesizer),
    ],
)
```

---

## Verification Step

Add explicit verification to catch reasoning errors.

```python
VERIFIED_COT_SYSTEM = """Solve the problem step by step.

After your solution, add a verification section:
**Verification:**
- Does my answer satisfy all constraints?
- Have I considered edge cases?
- Is there a simpler solution?
- Final answer (after verification): [answer]"""
```

---

## Best Practices

| Rule | Why |
|------|-----|
| Use clear step markers (Step 1, Step 2) | Forces explicit reasoning, easier to debug |
| Show all intermediate work | Helps catch where reasoning goes wrong |
| Add verification step for critical tasks | Catches errors before returning answer |
| State assumptions explicitly | Makes reasoning auditable |
| Use ToT only for genuinely complex decisions | Expensive — 3x cost minimum |
| Self-Consistency only for high-stakes answers | 5x cost — not for routine tasks |
