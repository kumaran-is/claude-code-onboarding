# Parallel Agents Orchestration

> **When to use**: Coordinating 2+ specialized agents for comprehensive reviews, cross-domain feature implementation, or full pre-deploy audits
> **Time estimate**: 5 min setup + agent execution time; synthesis 10-15 min
> **Prerequisites**: Know which domains the task touches; files to review are identified

## Overview

Orchestration guide from the `parallel-agents` skill. Coordinates this workspace's 42 actual agents through Claude Code's native Agent tool. Provides 6 pre-built patterns (comprehensive review, pre-deploy audit, Flutter feature, agentic AI, DB schema, architecture validation) and a synthesis protocol.

---

## Iron Law (from `skills/parallel-agents/SKILL.md`)

> **USE THIS WORKSPACE'S ACTUAL AGENTS — never reference placeholder agents (security-auditor, backend-specialist) that don't exist here; always dispatch from the 42 agents in `.claude/agents/`**

---

## Phase 1 — Load Skill and Select Pattern

```
Load parallel-agents skill
Load references/workspace-agent-catalog.md
```

Select the orchestration pattern that matches the task:

| Pattern | When to Use |
|---------|-------------|
| Comprehensive Feature Review | Any PR touching security-sensitive code, DB, or multiple services |
| Pre-Deploy Audit | Before merging significant feature branches |
| Full Flutter Feature | Flutter screen/flow touching state, auth, or Firebase |
| Agentic AI System Review | LangGraph, LangChain, or ADK agent implementation |
| Database Schema Review | New migration, table, index, or vector column |
| Architecture Validation | Before committing to architectural decision |

---

## Phase 2 — Agent Selection

Load `references/workspace-agent-catalog.md` to select appropriate agents. Quick selection by stack:

### NestJS feature
```
nestjs-reviewer + security-reviewer + silent-failure-hunter + pr-test-analyzer
```

### Spring Boot feature
```
spring-reactive-reviewer + security-reviewer + silent-failure-hunter
+ postgresql-database-reviewer (if DB touched)
```

### Flutter feature
```
riverpod-reviewer + flutter-security-expert + accessibility-auditor + ui-standards-expert
```

### Python/FastAPI feature
```
code-reviewer + security-reviewer + silent-failure-hunter + pr-test-analyzer
```

### LangGraph agent
```
agentic-ai-reviewer + security-reviewer + silent-failure-hunter
+ rag-implementation-reviewer (if RAG components present)
```

### Any stack — pre-deploy gate
```
[stack-specific reviewer] + security-reviewer + pr-test-analyzer → output-evaluator
```

---

## Phase 3 — Dispatch Agents

Use this dispatch template for every agent:

```
Agent: [agent-name from .claude/agents/]
Task: [specific task — not "review this code"]
Files: [explicit file paths]
Tech stack: [Java 21 / NestJS 11 / Python 3.14 / Flutter 3.50 / Angular 22.3 / React 19.3]
Focus: [specific area of concern — e.g., "Riverpod provider lifecycle"]
Output format: severity-bucketed findings with file:line evidence

Non-negotiable rules passed to agent:
- No silent failures: every catch block must log + rethrow or return error state
- Show file:line for every finding
- ≥80% confidence before raising an issue
```

**Parallel vs sequential:**
- Independent reviews (security + code quality + test coverage) → dispatch in parallel
- Dependent reviews (code review → then security based on findings) → sequential
- Final synthesis gate (`output-evaluator`) → always last, after all others complete

---

## Phase 4 — Synthesize

Load `references/synthesis-protocol.md`

**Rules:**
1. Collect ALL agent findings before synthesizing
2. Deduplicate overlapping findings (two agents finding same bug = one entry)
3. Resolve contradictions (note which agent is authoritative)
4. Order findings: CRITICAL → HIGH → MEDIUM → LOW
5. Issue final verdict: APPROVE / NEEDS_REVIEW / BLOCK

**Synthesis output:**
```markdown
## Orchestration Synthesis

### Task Summary
[One sentence: what was reviewed and for what purpose]

### Agents Dispatched
| Agent | Scope | Finding Count |
|-------|-------|---------------|
| [agent] | [what it reviewed] | [N] |

### Consolidated Findings

#### CRITICAL (must fix before merge)
- **[Finding]** — [agent] — `file:line`: [impact]

#### HIGH (should fix before merge)
- **[Finding]** — [agent] — `file:line`: [description]

#### MEDIUM (fix in follow-up PR)
- **[Finding]** — [agent]: [description]

#### LOW (tech debt backlog)
- **[Finding]** — [agent]: [description]

### Verdict
**[APPROVE | NEEDS_REVIEW | BLOCK]**
```

---

## Quick Reference

| Pattern | Agents | Sequential or Parallel? |
|---------|--------|------------------------|
| NestJS comprehensive review | nestjs-reviewer, security-reviewer, silent-failure-hunter, pr-test-analyzer | Parallel |
| Flutter feature | riverpod-reviewer, flutter-security-expert, accessibility-auditor, ui-standards-expert | Parallel |
| Pre-deploy gate | [stack reviewer], security-reviewer, pr-test-analyzer → output-evaluator | Parallel then sequential |
| Architecture validation | architect → plan-challenger → threat-modeling-expert | Sequential |
| Agentic AI review | agentic-ai-reviewer, security-reviewer, rag-implementation-reviewer, silent-failure-hunter | Parallel |
| DB schema | postgresql-database-reviewer → pgvector-schema-reviewer (if vector) | Sequential |

---

## Common Pitfalls

- **Dispatching non-existent agents** — Only use agents from `.claude/agents/` (42 total); see catalog in `references/workspace-agent-catalog.md`
- **Vague dispatch prompts** — "Review this code" produces generic findings; always pass specific files, scope, and output format
- **Skipping synthesis** — Raw agent outputs are not deliverables; always synthesize to one report
- **Running output-evaluator too early** — It must be last, after all other agents complete
- **Not passing context to agents** — Agents never see the conversation; Explore/Plan agents also start without CLAUDE.md. Pass the task, stack, and file paths explicitly

---

## Related Workflows

- [`subagent-driven-development.md`](subagent-driven-development.md) — 3-role implementation pipeline (Implementer → Spec Reviewer → Quality Reviewer)
- [`code-review.md`](code-review.md) — single-reviewer code review (simpler than multi-agent orchestration)
- [`security-audit.md`](security-audit.md) — full security audit using security-reviewer + threat-modeling-expert
- [`multi-agent-patterns.md`](multi-agent-patterns.md) — architectural theory behind multi-agent orchestration
