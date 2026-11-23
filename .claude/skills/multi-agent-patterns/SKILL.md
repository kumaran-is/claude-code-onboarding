---
name: multi-agent-patterns
description: "Architectural reference for multi-agent system design — covers Supervisor/Orchestrator, Peer-to-Peer/Swarm, and Hierarchical patterns with token economics, context isolation strategies, consensus mechanisms, and failure mitigation. Primary use: building production LangGraph/LangChain/ADK agents and designing Claude Code agent orchestration."
allowed-tools: Read, Glob, Grep
metadata:
  triggers: multi-agent architecture, design multi-agent system, supervisor pattern, swarm architecture, coordinate agents, agent handoffs, parallel agent execution, context isolation, agent orchestration design
  related-skills: agentic-ai-dev, google-adk, subagent-driven-development, parallel-agents, architecture-design
  domain: workflow
  role: architect
  scope: design
  output-format: architecture
last-reviewed: "2026-11-22"
---

## Iron Law

**CHOOSE ARCHITECTURE PATTERN BEFORE DISPATCHING AGENTS — dispatching without a chosen pattern (Supervisor, Swarm, or Hierarchical) produces uncontrolled context bloat and coordination failures**

**Explanation:** Multi-agent systems consume ~15× the tokens of single-agent systems. Choosing the wrong pattern or dispatching without a plan creates bottlenecks that negate every parallelization benefit.

# Multi-Agent Architecture Patterns

Reference skill for designing multi-agent systems. Covers when to use multi-agent architectures, which pattern to choose, how to handle context isolation, and how to prevent the most common failure modes.

**Primary audience:** Developers building LangGraph/LangChain agents, Google ADK agents, or Claude Code agent orchestration layers.

---

## When to Activate

Load this skill when:
- Deciding whether a task warrants multi-agent architecture vs single agent
- Choosing between Supervisor, Swarm, or Hierarchical patterns
- Building production LangGraph/LangChain multi-agent systems
- Designing Claude Code sub-agent dispatch strategies
- Diagnosing performance problems in an existing multi-agent system
- Briefing a team on multi-agent architecture trade-offs

---

## Pattern Selection Quick Guide

```
Do parts of the task need different tools, permissions, models or data scopes,
or does one context window overflow?
    NO → Single agent (or a deterministic workflow). Multi-agent adds overhead, not capability.
    YES ↓

Do subtasks decompose cleanly into parallel work?
    NO → Sequential single agent with summarization between steps.
    YES ↓

Does the task need centralized control and human oversight?
    YES → Supervisor/Orchestrator pattern
    NO ↓

Does the task need flexible exploration with emergent structure?
    YES → Peer-to-Peer/Swarm pattern
    NO ↓

Does the task have clear hierarchical abstraction layers (strategy → planning → execution)?
    YES → Hierarchical pattern
    NO → Default to Supervisor
```

---

## Reference Files

| Topic | Reference | Load When |
|-------|-----------|-----------|
| All 3 architectural patterns (deep) | `references/architectural-patterns.md` | Choosing a pattern or implementing a new multi-agent system |
| Token economics and cost data | `references/token-economics.md` | Deciding whether multi-agent architecture is justified |
| Failure modes and mitigations | `references/failure-modes.md` | Debugging a multi-agent system or designing resilience |

---

## Core Concepts (Summary)

### Why Multi-Agent?

Single agents face context ceilings. As tasks grow, context windows fill with accumulated history, retrieved documents, and tool outputs. Performance degrades via:
- **Lost-in-middle effect**: Information in context center gets ~10–40% lower recall
- **Context poisoning**: A hallucination that enters context gets reinforced on every turn
- **Attention scarcity**: All information competes for the same attention budget

Multi-agent architectures address this by partitioning work across multiple context windows.

### The Three Patterns

| Pattern | Control | Use When | Risk |
|---------|---------|----------|------|
| Supervisor/Orchestrator | Centralized | Clear decomposition, human oversight needed | Supervisor bottleneck |
| Peer-to-Peer/Swarm | Distributed | Flexible exploration, rigid planning counterproductive | Divergence, coordination overhead |
| Hierarchical | Layered | Strategy → planning → execution separation | Misalignment between layers |

### Context Isolation Mechanisms

| Mechanism | When | Trade-off |
|-----------|------|-----------|
| Full context delegation | Complex tasks needing complete understanding | Defeats isolation purpose |
| Instruction passing | Simple, well-defined subtasks | Limits agent flexibility |
| File system memory | Shared state across agents | Adds latency, consistency risk |

### Consensus: The Sycophancy Problem

Simple majority voting among agents degrades to consensus on false premises — agents bias toward agreement. Mitigations:
- **Verifier over voting**: where a deterministic check exists (tests, schema, evidence gate), it decides; votes don't
- **Weighted voting**: weights from measured per-agent accuracy on evals, never from the agents' self-reported confidence (uncalibrated)
- **Debate protocols**: Agents critique each other's outputs (adversarial > collaborative for accuracy)
- **Trigger-based intervention**: Monitor for stall and sycophancy markers

---

## Delegation, Scope and Authority (all patterns)

| Rule | Why |
|---|---|
| Each agent gets its own explicit tool allowlist; a sub-agent never inherits the parent's full tool set | Least privilege; a compromised or confused sub-agent can only do its job |
| Identity and tenant scope travel in run `context`/config set by code, never in messages between agents | Messages are model text; a forged "org_id" in a handoff must have no effect |
| Handoff payloads are typed (schema-validated) and treated as untrusted data by the receiver | One agent's injection must not become another agent's instruction |
| A delegated agent receives the **remaining** budget (calls, tokens, deadline), not a fresh one | Budgets are cumulative per user request |
| Routes/handoffs are validated by code against a closed set plus transition rules; hop cap with a typed status | The model proposes, code authorizes (`agentic-ai-dev/reference/agentic-templates-advanced.md`) |
| No agent approves another agent's high-consequence action; approvals are human (or policy code) and durable | Agents request, workflows commit (`workflow-orchestration-patterns`) |
| Cross-service agents (A2A or similar protocols) authenticate as services, re-authorize per call, and pass no user credentials | See `references/architectural-patterns.md` §Cross-service agents |

Tool-level controls: `agentic-ai-dev/reference/tool-execution-safety.md`.

---

## Critical Production Finding: The Telephone Game Problem

**Evidence:** LangGraph benchmarks found supervisor architectures initially performed 50% worse than optimized versions.

**Cause:** Supervisors paraphrase sub-agent responses, losing fidelity at each hop.

**Fix:** Implement `forward_message` tool for direct pass-through when sub-agent output is complete:

```python
def forward_message(message: str, to_user: bool = True):
    """
    Forward sub-agent response directly to user without supervisor synthesis.

    Use when:
    - Sub-agent response is final and complete
    - Supervisor synthesis would lose important details
    - Response format must be preserved exactly
    """
    if to_user:
        return {"type": "direct_response", "content": message}
    return {"type": "supervisor_input", "content": message}
```

With this pattern, swarm architectures can slightly outperform supervisor architectures for tasks where sub-agent output needs no synthesis.

---

## Constraints

### MUST DO
- Choose architecture pattern before dispatching agents
- Calculate token budget impact before committing to multi-agent (see `references/token-economics.md`)
- Define explicit handoff protocols with state passing
- Implement convergence constraints for swarm patterns (time-to-live, iteration limits)
- Validate agent outputs before passing to downstream agents
- Give every agent its own allowlist and pass scope via context, not messages

### MUST NOT DO
- Use multi-agent for tasks a single agent can handle — overhead is ~15× tokens
- Use supervisor pattern without direct pass-through mechanism (telephone game problem)
- Run swarm patterns without convergence constraints (infinite loops)
- Assume model upgrade is always cheaper than parallelization (check `token-economics.md`)

---

## Knowledge Reference

LangGraph, AutoGen, CrewAI, context isolation, context window management, token economics, supervisor pattern, swarm architecture, hierarchical agents, consensus mechanisms, sycophancy detection, agent handoffs, forward_message, BrowseComp evaluation, multi-agent coordination
