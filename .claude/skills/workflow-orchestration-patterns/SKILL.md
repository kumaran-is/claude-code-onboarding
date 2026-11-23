---
name: workflow-orchestration-patterns
description: "Durable workflows with Temporal (Java 21, Python 3.14, NestJS): workflow vs activity, saga, entity workflows, fan-out/fan-in, determinism, retries, idempotency. Use for long-running, failure-resilient business processes. Not for LLM agent graphs (agentic-ai-dev)."
allowed-tools: Bash, Read, Write, Edit
metadata:
  triggers: Temporal, workflow orchestration, durable execution, saga pattern, distributed transaction, long-running workflow, activity, worker, task queue, compensation, entity workflow, fan-out, fan-in, async callback
  related-skills: agentic-ai-dev, java-spring-api, nestjs-api, python-dev, architecture-design
  domain: backend
  role: specialist
  scope: implementation
  output-format: code
last-reviewed: "2026-11-22"
---

## Iron Law

**NO WORKFLOW WITHOUT DETERMINISM ENFORCEMENT AND IDEMPOTENT ACTIVITIES — non-deterministic workflow code causes replay failures; non-idempotent activities cause duplicate charges, double-sends, and data corruption**

# Workflow Orchestration Patterns — Temporal + Java 21 / Python 3.14 / NestJS 11.x

## Quick Scaffold

```bash
# Start Temporal server locally (Docker)
docker run -d --name temporal \
  -p 7233:7233 -p 8080:8080 \
  temporalio/auto-setup:1.24

# Java 21 / Spring Boot — add to pom.xml
# io.temporal:temporal-sdk:1.25.0
# io.temporal:temporal-spring-boot-autoconfigure-alpha:0.6.0

# Python 3.14 — uv add
uv add temporalio==1.7.0 fastapi uvicorn

# NestJS 11.x — npm
npm install @temporalio/client @temporalio/worker @temporalio/workflow @temporalio/activity
```

## Process

1. **Deploy Temporal** — local Docker or Temporal Cloud (cloud.temporal.io)
2. **Define Activities** — external interactions (API calls, DB writes, emails) — must be idempotent
3. **Define Workflow** — orchestration logic only — must be deterministic (no I/O, no `Date.now()`, no random)
4. **Configure Retry Policies** — initial interval, backoff coefficient, max attempts, non-retryable errors
5. **Register Worker** — binds workflow + activity implementations to task queues
6. **Start Execution** — client sends `startWorkflow()` with typed input
7. **Add Signals/Queries** — external state mutations (signals) and reads (queries) on running workflows
8. **Implement Saga** — register compensations BEFORE each step; run in reverse (LIFO) on failure
9. **Add Heartbeats** — long-running activities must call `heartbeat()` periodically
10. **Write Tests** — use Temporal test environment with time-skipping for deterministic test execution

## Key Patterns

| Pattern | When to Use | Reference |
|---------|-------------|-----------|
| Saga + Compensation | Distributed transactions needing rollback | `reference/implementation-playbook.md#saga` |
| Entity Workflow (Actor) | One workflow per entity lifecycle (cart, account, order) | `reference/implementation-playbook.md#entity` |
| Fan-Out / Fan-In | Parallel execution of N tasks with result aggregation | `reference/implementation-playbook.md#fanout` |
| Async Callback / Signal | Waiting for external event or human approval | `reference/implementation-playbook.md#signals` |
| Activity Heartbeat | Long-running activities (>30s) with progress tracking | `reference/implementation-playbook.md#heartbeat` |
| Workflow Versioning | Safe code changes while old executions still running | `reference/implementation-playbook.md#versioning` |
| Child Workflows | Decompose large workflows for scalability (1M tasks = 1K x 1K) | `reference/implementation-playbook.md#child` |

## Workflow vs Activity Decision Rule

```
Does the code touch an external system? (API, DB, file, email, network)
  YES -> Activity
  NO  -> Workflow (orchestration/decision logic only)
```

**Prohibited in Workflow code:**
- `new Date()` / `datetime.now()` / `LocalDateTime.now()` — use `Workflow.currentTimeMillis()` / `workflow.now()`
- `Math.random()` / `random.random()` — use `Workflow.newRandom()` / `workflow.random()`
- HTTP calls, DB queries, file I/O — move to Activity
- Threading, locks, `Thread.sleep()` — use `Workflow.sleep()`
- Non-deterministic libraries

## AI Agents and Workflows: Agents Request, Workflows Commit

When an LLM agent is part of a business process, the agent decides *what to ask for*; the workflow owns *what happens*:

- The agent emits a typed proposal (action, args, evidence, required authority). It never holds a multi-step transaction open.
- The workflow validates the proposal in code, waits for human approval as a **Signal** when the action is high-consequence, then runs each side effect as an idempotent Activity with a compensation (saga).
- LLM calls themselves run as Activities (they are non-deterministic and touch the network), with their own timeouts and retry policy limited to transient errors.
- A crashed agent run or an exhausted agent budget leaves no half-applied change: nothing was committed outside the workflow.

Agent-side patterns: `agentic-ai-dev/reference/tool-execution-safety.md` (§2 authority tiers, §6 idempotency, §9 compensation) and `agentic-ai-dev/reference/agentic-streaming-hitl.md` (durable approvals).

## Conventions & Rules

> For per-SDK implementation templates (Java, Python, NestJS), read `reference/implementation-playbook.md`

## Documentation Sources

Before generating code, consult these sources for current SDK APIs:

| Source | URL / Tool | Purpose |
|--------|-----------|---------|
| Temporal Docs | `https://docs.temporal.io/dev-guide` | Core concepts, SDK APIs, best practices |
| Java SDK | `https://www.javadoc.io/doc/io.temporal/temporal-sdk/latest/` | Java workflow/activity annotations |
| Python SDK | `https://python.temporal.io/` | Python asyncio API reference |
| TypeScript SDK | `https://typescript.temporal.io/` | NestJS/TypeScript worker and client APIs |
| Context7 MCP | `resolve-library-id: temporalio` | Latest Temporal Python patterns |

## Reference Files

| File | Content | When to Use |
|------|---------|-------------|
| `reference/implementation-playbook.md` | Full workflow + activity code for Java, Python, NestJS; Saga, Entity, Fan-out, Signal, Heartbeat, Versioning, Child Workflow patterns | Any Temporal implementation |

## Common Commands

```bash
# View Temporal Web UI (workflows, history, task queues)
open http://localhost:8080

# Java — run worker
mvn spring-boot:run

# Python — run worker
uvicorn src.main:app --reload &
python -m src.worker   # separate process

# NestJS — run worker
npm run start:worker   # defined in package.json scripts

# Run Temporal test suite (time-skipping enabled)
# Java: mvn test
# Python: pytest -q
# NestJS: npm test
```

## Error Handling

> For retry policy templates and non-retryable error classification per SDK, read `reference/implementation-playbook.md#retry`

**Activity retry rule:** classify every exception before throwing. Validation errors and business rule violations -> `ApplicationFailure.newNonRetryableFailure()`. Transient network/timeout errors -> retryable (default).

**Workflow failure rule:** workflows do not catch activity exceptions unless implementing compensation. Let Temporal's retry engine handle transient failures. Only catch `ActivityFailure` when running saga compensations.

**Idempotency rule:** every activity MUST be safe to call N times. Use idempotency keys, upsert patterns, and check-then-act with unique constraints. Verify with: "If this activity runs twice with the same input, is the final state identical?"

## Post-Code Review

After writing Temporal workflow code, dispatch these reviewer agents:
- `architect-review` — workflow boundaries, saga completeness, entity lifecycle correctness
- `security-reviewer` — activity input validation, no secrets in workflow state, payload size limits (2MB)
