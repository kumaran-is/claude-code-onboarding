# ADK Agent Types

Executed with `google-adk==1.29.0` and a scripted fake model (`adk-testing.md` §2). `MODEL` stands for `settings.agent_model` — never a literal id. Run every example with `run_once` from `adk-core-patterns.md` §2 (awaited `create_session`, `RunConfig(max_llm_calls=...)`).

Multi-agent only when it beats a single agent or deterministic workflow on evals (separate tool/authority scopes, isolation of untrusted input, parallel latency) — `multi-agent-patterns` skill. Agents never own multi-step transactions: side effects go through a domain service or durable workflow (`workflow-orchestration-patterns`).

## 1. SequentialAgent — pipeline

Sub-agents run in order. Each writes its final text to `output_key`; later agents read it with `{key}` in their `instruction`.

```python
from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent

researcher = Agent(
    name="researcher",
    model=MODEL,
    description="Researches a topic and produces raw findings.",
    instruction="Research the topic provided by the user. Write key facts and context as plain text.",
    output_key="research_findings",
)

writer = Agent(
    name="writer",
    model=MODEL,
    description="Turns findings into a draft.",
    instruction="Write a clear draft article from these findings:\n\n{research_findings}",
    output_key="draft_article",
)

pipeline = SequentialAgent(name="research_pipeline", sub_agents=[researcher, writer])
```

An identifier-like `{name}` in an instruction must exist in session state when the agent runs — a missing key raises `KeyError: Context variable not found` (executed). Use `{name?}` for optional keys; use an instruction provider callable (`instruction=lambda ctx: TEXT`) when the text contains placeholder-like braces such as `{source_name}` in a citation template — callables bypass templating (executed).

## 2. ParallelAgent — fan-out, then synthesize

Branches run concurrently and must not depend on each other; each writes its own key. Wrap in a `SequentialAgent` to synthesize.

```python
technical = Agent(name="technical_analyst", model=MODEL,
                  instruction="Analyze technical feasibility of: {topic}", output_key="technical_analysis")
market = Agent(name="market_analyst", model=MODEL,
               instruction="Analyze the market for: {topic}", output_key="market_analysis")
synthesizer = Agent(
    name="synthesizer",
    model=MODEL,
    instruction="Synthesize a recommendation.\n\nTechnical:\n{technical_analysis}\n\nMarket:\n{market_analysis}",
    output_key="executive_summary",
)

full_analysis = SequentialAgent(
    name="full_analysis_pipeline",
    sub_agents=[ParallelAgent(name="analysis_team", sub_agents=[technical, market]), synthesizer],
)
# create the session with state={"topic": ...} so {topic} resolves
```

Parallel branches multiply model calls and cost; the per-request `max_llm_calls` cap covers the whole tree.

## 3. LoopAgent — iterative refinement

`LoopAgent.max_iterations` defaults to `None` = **unbounded** (verified on 1.29): always set it, and also pass `RunConfig(max_llm_calls=N)` (default 500; exceeding it raises `LlmCallsLimitExceededError`, executed). The loop stops early when a sub-agent calls `exit_loop`.

Do not put `output_key` on the agent that calls `exit_loop`: its final response is the tool turn, so the key is overwritten with empty text (executed: the improved code was lost). Split review from rewrite:

```python
from google.adk.tools import exit_loop

reviewer = Agent(
    name="reviewer",
    model=MODEL,
    instruction="Review this code:\n{current_code}\nIf it has no issues, call exit_loop. Otherwise list the issues.",
    tools=[exit_loop],
    output_key="review_notes",
)
refiner = Agent(
    name="refiner",
    model=MODEL,
    instruction="Fix these issues:\n{review_notes}\n\nCode:\n{current_code}\nReturn only the code.",
    output_key="current_code",
)
refinement_loop = LoopAgent(name="code_refinement_loop", sub_agents=[reviewer, refiner], max_iterations=3)
# session state={"current_code": ...}; executed: issues -> rewrite -> exit_loop, current_code kept
```

When the cap is hit without `exit_loop`, return a typed status (e.g. `ITERATION_LIMIT`) to the caller, not the last draft as if it passed review. A same-model reviewer is not independent verification — gate on deterministic checks (tests, validators) where they exist.

## 4. Composition patterns

| Pattern | Use case | Structure |
|---|---|---|
| Sequential | A feeds B feeds C | `SequentialAgent(sub_agents=[a, b, c])` |
| Parallel + synthesize | Independent perspectives | `SequentialAgent([ParallelAgent([a, b]), synthesizer])` |
| Loop | Refine until a check passes | `LoopAgent(sub_agents=[reviewer, refiner], max_iterations=N)` |
| Handoff | Intent routing; the specialist talks to the user | root `sub_agents=[s1, s2]` (`transfer_to_agent` is injected) |
| Agent as tool | Parent keeps control, typed I/O | `tools=[AgentTool(agent=specialist)]` |

Orchestrators accept no model callbacks (`extra_forbidden`); screen input in the route. Handoff rules: `adk-agent-handoff.md`.
