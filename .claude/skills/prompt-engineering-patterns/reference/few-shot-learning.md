# Few-Shot Learning Patterns

> Referenced by `prompt-engineering-patterns` SKILL.md.

## When to Use Few-Shot

- Output format is non-obvious (JSON schema, specific structure)
- Classification task with specific categories
- Style or tone needs demonstration, not description
- Model keeps getting format wrong despite instructions

## When NOT to Use Few-Shot

- Simple factual tasks (adds tokens, no benefit)
- When you're near token limit (use zero-shot instead)
- When examples are hard to generalize (misleads the model)

---

## Static Few-Shot — LangGraph

```python
from langchain_core.messages import SystemMessage, HumanMessage

CLASSIFICATION_SYSTEM = SystemMessage(content="""You are a customer support classifier.
Classify each message into exactly one category.

Categories: BILLING, TECHNICAL, ACCOUNT, GENERAL

Examples:
---
Message: "My invoice shows wrong amount"
Category: BILLING

Message: "App crashes when I open settings"
Category: TECHNICAL

Message: "I need to reset my password"
Category: ACCOUNT

Message: "What are your business hours?"
Category: GENERAL
---

Respond with ONLY the category name. No explanation.""")

def classify_node(state: AgentState) -> AgentState:
    response = llm.invoke([
        CLASSIFICATION_SYSTEM,
        HumanMessage(content=f"Message: {state['message']}")
    ])
    return {"category": response.content.strip()}
```

## Static Few-Shot — Google ADK

```python
from google.adk.agents import LlmAgent

classifier_agent = LlmAgent(
    name="classifier",
    model=settings.agent_model,
    instruction="""You are a customer support classifier.
Classify each message into exactly one category: BILLING, TECHNICAL, ACCOUNT, or GENERAL.

Examples:
Message: "My invoice shows wrong amount" -> BILLING
Message: "App crashes when I open settings" -> TECHNICAL
Message: "I need to reset my password" -> ACCOUNT
Message: "What are your business hours?" -> GENERAL

Respond with ONLY the category name."""
)
```

---

## Dynamic Few-Shot (Semantic Retrieval)

Select examples at runtime based on similarity to the input. More expensive but more accurate for diverse inputs.

```python
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings

class DynamicFewShotSelector:
    """Selects the most relevant few-shot examples using semantic similarity."""

    def __init__(self, examples: list[dict], embeddings: Embeddings, k: int = 3):
        self.k = k
        texts = [ex["input"] for ex in examples]
        self.store = FAISS.from_texts(texts, embeddings, metadatas=examples)

    def select(self, query: str) -> list[dict]:
        results = self.store.similarity_search(query, k=self.k)
        return [doc.metadata for doc in results]

    def build_prompt(self, query: str, task_instruction: str) -> str:
        examples = self.select(query)
        example_block = "\n\n".join(
            f"Input: {ex['input']}\nOutput: {ex['output']}"
            for ex in examples
        )
        return f"{task_instruction}\n\nExamples:\n{example_block}\n\nInput: {query}\nOutput:"


# Usage in LangGraph node
selector = DynamicFewShotSelector(
    examples=EXAMPLE_BANK,
    embeddings=embeddings_model,
    k=3
)

def dynamic_few_shot_node(state: AgentState) -> AgentState:
    prompt = selector.build_prompt(
        query=state["input"],
        task_instruction="Convert natural language to SQL. Think through the table and filter logic."
    )
    response = llm.invoke(prompt)
    return {"sql": response.content}
```

---

## Token Budget for Few-Shot

```python
# Allocation rule: few-shot should not exceed 40% of total context
MAX_TOKENS = 100_000  # model context window
BUDGET = {
    "system_prompt": int(MAX_TOKENS * 0.12),   # 12%
    "few_shot":      int(MAX_TOKENS * 0.38),   # 38% — generous for examples
    "user_input":    int(MAX_TOKENS * 0.12),   # 12%
    "response":      int(MAX_TOKENS * 0.38),   # 38%
}

def fits_budget(examples: list[dict], budget: int) -> list[dict]:
    """Trim examples to fit token budget."""
    selected = []
    used = 0
    for ex in examples:
        size = len(ex["input"].split()) + len(ex["output"].split())  # rough token estimate
        if used + size <= budget:
            selected.append(ex)
            used += size
    return selected
```

---

## Edge Case Examples

Always include at least one edge case example:

```python
EDGE_CASE_EXAMPLES = [
    # Normal case
    {
        "input": "Users registered last 30 days",
        "output": "SELECT * FROM users WHERE created_at > NOW() - INTERVAL '30 days'"
    },
    # Empty result case
    {
        "input": "Users with no orders",
        "output": "SELECT u.* FROM users u LEFT JOIN orders o ON u.id = o.user_id WHERE o.id IS NULL"
    },
    # Ambiguous case — model should ask for clarification
    {
        "input": "Recent users",
        "output": "CLARIFICATION_NEEDED: 'Recent' is ambiguous. Specify a time range (e.g., last 7 days, 30 days)."
    },
]
```

---

## Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Too many examples (>5 for simple tasks) | Token waste, dilutes attention | Use 2-3 high-quality examples |
| Inconsistent example format | Model copies inconsistency | Enforce identical structure |
| Examples don't cover the actual input distribution | Poor generalization | Sample examples from real data |
| Examples too similar to each other | Poor coverage | Ensure diversity (use clustering) |
| Forgetting edge cases | Failures on boundary inputs | Always include 1 edge case |
