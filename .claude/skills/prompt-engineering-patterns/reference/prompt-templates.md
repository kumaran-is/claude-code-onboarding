# Prompt Templates

> Referenced by `prompt-engineering-patterns` SKILL.md. Reusable templates for LangGraph and ADK.

## LangGraph — Message Template Pattern

```python
from langchain_core.messages import SystemMessage, HumanMessage
from string import Template


class AgentPromptTemplate:
    """Type-safe prompt template for LangGraph agents."""

    def __init__(self, system: str, user: str):
        self._system = system
        self._user_template = Template(user)

    def build(self, **kwargs) -> list:
        """Build message list for llm.invoke()."""
        return [
            SystemMessage(content=self._system),
            HumanMessage(content=self._user_template.substitute(**kwargs))
        ]


# Define templates as constants — NOT inline in node functions
SQL_TEMPLATE = AgentPromptTemplate(
    system="""You are a SQL expert. Convert natural language to efficient SQL.
Always include a comment explaining the query logic.
Output: SQL code block only.""",
    user="Convert to SQL: $query"
)

REVIEW_TEMPLATE = AgentPromptTemplate(
    system="""You are a code reviewer. Review for: bugs, security issues, performance.
Output format: Issues (list), Severity (HIGH/MED/LOW), Fix (code diff)""",
    user="Review this $language code:\n```$language\n$code\n```"
)


# Usage in LangGraph node
def sql_node(state: AgentState) -> AgentState:
    messages = SQL_TEMPLATE.build(query=state["nl_query"])
    response = llm.invoke(messages)
    return {"sql": response.content}
```

---

## Google ADK — Instruction Template Pattern

```python
from google.adk.agents import LlmAgent


def make_specialist_agent(
    name: str,
    role: str,
    domain: str,
    output_format: str,
    constraints: list[str] | None = None
) -> LlmAgent:
    """Factory for domain-specialist ADK agents."""
    constraint_lines = ""
    if constraints:
        constraint_lines = "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)

    instruction = f"""You are a {role} specializing in {domain}.

{output_format}{constraint_lines}"""

    return LlmAgent(
        name=name,
        model=settings.agent_model,
        instruction=instruction
    )


# Create specialized agents from template
sql_agent = make_specialist_agent(
    name="sql_agent",
    role="SQL expert",
    domain="PostgreSQL query optimization",
    output_format="Output: SQL in code block with inline comments explaining logic.",
    constraints=["Never use SELECT *", "Always add LIMIT unless explicitly told not to"]
)

code_reviewer = make_specialist_agent(
    name="code_reviewer",
    role="senior code reviewer",
    domain="Python and TypeScript",
    output_format='Output JSON: {"issues": [{"line": int, "severity": str, "description": str, "fix": str}]}',
    constraints=["Never skip security issues", "Always suggest a concrete fix"]
)
```

---

## Multi-Turn Template

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


class ConversationTemplate:
    """Manage multi-turn conversation with sliding context window."""

    def __init__(self, system: str, max_history: int = 10):
        self._system = SystemMessage(content=system)
        self._history: list = []
        self._max_history = max_history

    def add_turn(self, user_input: str, assistant_response: str) -> None:
        self._history.append(HumanMessage(content=user_input))
        self._history.append(AIMessage(content=assistant_response))
        # Trim to window
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-(self._max_history * 2):]

    def build(self, user_input: str) -> list:
        return [self._system, *self._history, HumanMessage(content=user_input)]


# Usage
support_chat = ConversationTemplate(
    system="You are a helpful customer support agent for Acme Corp. Be concise and solution-focused.",
    max_history=5
)

def chat_node(state: AgentState) -> AgentState:
    messages = support_chat.build(state["user_message"])
    response = llm.invoke(messages)
    support_chat.add_turn(state["user_message"], response.content)
    return {"messages": [response]}
```

---

## Instruction Hierarchy Template

Universal structure — apply to every prompt:

```
System: [Role + Expertise]
System: [Behavioral rules]
System: [Output format]
Human:  [Few-shot examples if needed]
Human:  [Actual task input]
```

```python
def build_structured_prompt(
    role: str,
    task: str,
    output_format: str,
    examples: list[tuple[str, str]] | None = None,
    constraints: list[str] | None = None
) -> list:
    """Build a fully structured prompt following the instruction hierarchy."""
    system_parts = [f"You are {role}."]

    if constraints:
        system_parts.append("Rules:\n" + "\n".join(f"- {c}" for c in constraints))

    system_parts.append(f"Output format: {output_format}")

    messages = [SystemMessage(content="\n\n".join(system_parts))]

    if examples:
        example_text = "\n\n".join(
            f"Input: {inp}\nOutput: {out}" for inp, out in examples
        )
        messages.append(HumanMessage(content=f"Examples:\n{example_text}"))

    messages.append(HumanMessage(content=f"Task: {task}"))
    return messages
```

---

## Template Registry Pattern

Centralize all prompts in one place — prevents ad-hoc strings scattered across node files.

```python
from dataclasses import dataclass
from langchain_core.messages import SystemMessage, HumanMessage


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    system: str
    user_template: str  # uses {variable} f-string style

    def build(self, **kwargs) -> list:
        return [
            SystemMessage(content=self.system),
            HumanMessage(content=self.user_template.format(**kwargs))
        ]


class PromptRegistry:
    """Single source of truth for all agent prompts."""
    _registry: dict[str, PromptTemplate] = {}

    @classmethod
    def register(cls, template: PromptTemplate) -> PromptTemplate:
        cls._registry[template.name] = template
        return template

    @classmethod
    def get(cls, name: str) -> PromptTemplate:
        if name not in cls._registry:
            raise KeyError(f"Prompt '{name}' not found. Registered: {list(cls._registry)}")
        return cls._registry[name]


# Register at module load time
PromptRegistry.register(PromptTemplate(
    name="sql_generation",
    system="You are a PostgreSQL expert. Generate optimized SQL with index-aware queries.",
    user_template="Convert to SQL: {query}\nSchema context: {schema}"
))

PromptRegistry.register(PromptTemplate(
    name="code_review",
    system="You are a senior engineer. Review for bugs, security, and performance. Output JSON.",
    user_template="Review {language} code:\n```\n{code}\n```"
))


# Usage
def sql_node(state: AgentState) -> AgentState:
    template = PromptRegistry.get("sql_generation")
    response = llm.invoke(template.build(
        query=state["nl_query"],
        schema=state["schema"]
    ))
    return {"sql": response.content}
```
