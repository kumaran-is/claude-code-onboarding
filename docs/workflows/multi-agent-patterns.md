# Multi-Agent Patterns

> **When to use**: Before designing a new multi-agent system or choosing an agent architecture — covers LangGraph/LangChain agents, Google ADK agents, and Claude Code orchestration layers
> **Time estimate**: 15 min orientation; reference skill loaded on-demand during design
> **Prerequisites**: Single-agent approach has been considered and found insufficient

## Overview

Architectural reference from the `multi-agent-patterns` skill. Covers when multi-agent adds value, which of 3 patterns to use (Supervisor, Swarm, Hierarchical), token cost implications (~15× multiplier), context isolation strategies, and the 6 most common failure modes with mitigations.

Primary use cases in this workspace:
- Building LangGraph/LangChain agents in the Agentic AI (Python) tier
- Designing Google ADK agents with `Workflow` graphs (ADK 2.x; SequentialAgent/ParallelAgent are deprecated)
- Designing Claude Code sub-agent dispatch strategies using `parallel-agents` skill

---

## Iron Law (from `skills/multi-agent-patterns/SKILL.md`)

> **CHOOSE ARCHITECTURE PATTERN BEFORE DISPATCHING AGENTS — dispatching without a chosen pattern produces uncontrolled context bloat and coordination failures**

---

## Phase 1 — Load Skill

```
Load multi-agent-patterns skill
```

Then load reference files based on the decision to be made:

| Decision | Load |
|----------|------|
| Choosing a pattern | `references/architectural-patterns.md` |
| Justifying the token cost | `references/token-economics.md` |
| Designing for resilience | `references/failure-modes.md` |

---

## Phase 2 — Pattern Selection

Work through this decision tree before writing any agent code:

```
Is the task too large for one context window?
    NO → Single agent. Stop here.
    YES ↓

Do subtasks decompose cleanly into parallel work?
    NO → Sequential single agent with summarization between steps.
    YES ↓

Does the task need centralized control and human oversight?
    YES → Supervisor/Orchestrator
    NO ↓

Does the task need flexible exploration with emergent structure?
    YES → Peer-to-Peer/Swarm
    NO ↓

Does the task have clear strategy → planning → execution layers?
    YES → Hierarchical
    NO → Default to Supervisor
```

---

## Phase 3 — Token Budget Check

Before committing to multi-agent, verify cost is justified:

```
Load references/token-economics.md

Cost check:
- Single-agent baseline cost: [N tokens]
- Multi-agent estimate: [N × 15 tokens]
- Would model upgrade (Sonnet → Opus) solve the problem cheaper?

If upgrading model solves the problem: do NOT use multi-agent.
If task has genuinely parallel subtasks: multi-agent justified.
```

---

## Phase 4 — Pattern Implementation

### Supervisor/Orchestrator

```python
# Core principle: supervisor coordinates, workers execute in clean context
# Critical: implement forward_message for direct pass-through (prevents 50% perf loss)

def forward_message(message: str, to_user: bool = True):
    """Use when sub-agent output is complete and synthesis would lose fidelity."""
    if to_user:
        return {"type": "direct_response", "content": message}
    return {"type": "supervisor_input", "content": message}

# Workers return structured output (not raw text) to prevent supervisor context bloat
class WorkerOutput(BaseModel):
    finding: str           # distilled summary — not full context
    evidence: list[str]    # file:line or URL references
    confidence: float      # 0.0–1.0
    requires_followup: bool
```

See `references/architectural-patterns.md` for full LangGraph implementation template.

### Peer-to-Peer/Swarm

```python
# Core principle: explicit handoff protocols + convergence constraints

class SwarmConfig:
    max_iterations: int = 10         # Hard loop limit — mandatory
    max_agent_hops: int = 5          # Prevent infinite handoff chains
    time_to_live_seconds: int = 300  # Wall-clock termination
```

### Hierarchical

```python
# Core principle: strategy goal → planning tasks → execution output must stay aligned
# Run alignment_check() periodically to detect drift between layers
```

---

## Phase 5 — Resilience Design

Load `references/failure-modes.md` and review these 6 failure modes before finalizing:

| Failure | Affects | Mitigation |
|---------|---------|-----------|
| Supervisor bottleneck | Supervisor | Structured output schemas + checkpointing |
| Coordination overhead | All | Batch results, async comms |
| Divergence | Swarm | Convergence checks + TTL limits |
| Error propagation | All | Output validation before passing downstream |
| Sycophancy / false consensus | All | Debate protocol + independent sampling |
| Team shutdown neglect | Claude Code | Always `shutdown_request` + `TeamDelete` |

---

## Pattern Reference by Workspace Use Case

| Use Case | Pattern | Agents / Components |
|----------|---------|---------------------|
| LangGraph research agent | Swarm | Independent source agents → synthesis |
| Google ADK workflow | Hierarchical | `Workflow` graph (strategy) → LLM agents (execution) |
| Claude Code feature review | Supervisor | `parallel-agents` skill orchestrates reviewers |
| ADK with tool specialization | Supervisor | Tool-specialized sub-agents, ADK supervisor node |
| Autonomous PR iteration | Swarm | Retry loop until convergence (ralph-loop pattern) |

---

## Quick Reference

| Decision | Reference |
|----------|-----------|
| Which pattern? | `references/architectural-patterns.md` |
| Is multi-agent worth the cost? | `references/token-economics.md` |
| What failure modes to design for? | `references/failure-modes.md` |
| How to dispatch agents in Claude Code? | `parallel-agents` skill |
| LangGraph implementation? | `agentic-ai-dev` skill |
| Google ADK implementation? | `google-adk` skill |

---

## Common Pitfalls

- **Multi-agent before verifying single-agent fails** — Always try single agent + model upgrade first
- **Supervisor without `forward_message`** — 50% performance loss from telephone game problem
- **Swarm without convergence constraints** — infinite loops in production
- **Workers returning raw text** — supervisor context bloat; use structured output schemas
- **Agent teams never shut down** — run `TeamDelete` after every Claude Code team session

---

## Related Workflows

- [`parallel-agents.md`](parallel-agents.md) — Claude Code native orchestration using this workspace's 42 agents
- [`subagent-driven-development.md`](subagent-driven-development.md) — supervisor pattern applied to implementation pipeline
- [`feature-agentic-ai.md`](feature-agentic-ai.md) — building LangGraph/LangChain agents end-to-end
- [`feature-google-adk.md`](feature-google-adk.md) — building Google ADK agents end-to-end
