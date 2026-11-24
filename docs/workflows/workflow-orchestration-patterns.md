# Workflow: Temporal Workflow Orchestration

**When to use:** Building long-running, failure-resilient distributed business processes that span multiple services, require automatic retry/compensation, or must survive infrastructure restarts.

**Skill:** `workflow-orchestration-patterns`
**Stacks:** Java 21 / Spring Boot 3.5.x · Python 3.14 / FastAPI · NestJS 11.x
**Not applicable to:** Angular, Flutter (client-side only — trigger workflows via REST)

---

## Decision: Do You Need Temporal?

```
Is the process multi-step AND touches external systems?
  YES → Does it need to survive crashes / resume from last step?
          YES → Use Temporal
          NO  → Use a simple async queue (BullMQ, Celery, Spring @Async)
  NO  → Direct API call is sufficient
```

**Use Temporal when:**
- Process runs for seconds to hours (or longer) across services
- Failure at any step requires rollback (saga) or resume
- Business rules define compensation (refund if payment fails after inventory reserved)
- Human approval step with timeout is required
- 1M+ parallel tasks need orchestration (fan-out/fan-in)

**Do not use Temporal when:**
- Single-step CRUD operations
- Pure data pipelines (use Airflow, Prefect, or batch jobs)
- Stateless request/response (use standard REST)
- Real-time streaming (use Kafka, Pub/Sub)

---

## Phase 1 — Local Temporal Setup

```bash
# Start Temporal server + Web UI (port 8080)
docker run -d --name temporal \
  -p 7233:7233 -p 8080:8080 \
  temporalio/auto-setup:1.24

# Verify
open http://localhost:8080  # Temporal Web UI — shows running workflows
```

---

## Phase 2 — Load Skill

```
Load skill: workflow-orchestration-patterns
Read reference: .claude/skills/workflow-orchestration-patterns/reference/implementation-playbook.md
```

Then decide your pattern:

| Pattern | When | Section in Playbook |
|---------|------|---------------------|
| Saga + Compensation | Distributed transaction with rollback | `#saga` |
| Entity Workflow | One workflow per entity lifecycle | `#entity` |
| Fan-Out / Fan-In | Parallel N-task execution | `#fanout` |
| Async Signal | External event or human approval | `#signals` |
| Long-Running Activity | Activity > 30 seconds | `#heartbeat` |

---

## Phase 3 — Define Activities First

Activities = all external interactions. Define and test these before the workflow.

**Rules:**
1. Every activity MUST be idempotent — safe to call N times with same result
2. Every activity MUST have `start_to_close_timeout` configured
3. Classify every exception: `non_retryable` for business rule violations, retryable for transient failures
4. Activities longer than 30s MUST call `heartbeat()` periodically

```python
# Python example — activity with idempotency + error classification
@activity.defn
async def charge_payment(order_id: str, amount_cents: int) -> None:
    # Idempotency: the gateway key is derived from order_id, so a retried attempt is not a second charge
    # (a check-then-charge on your own table races between attempts)
    result = await gateway.charge(order_id, amount_cents, idempotency_key=f"charge-{order_id}")
    if result.code == "INSUFFICIENT_FUNDS":
        # type= is keyword-only: a positional 2nd argument becomes a detail and never matches the retry policy
        raise ApplicationError("Declined", type="InsufficientFundsError", non_retryable=True)
```

---

## Phase 4 — Define Workflow

Workflow = orchestration and decision logic ONLY. No I/O allowed.

**Determinism checklist (verify before committing):**
- [ ] No `datetime.now()` / `new Date()` / `LocalDateTime.now()` — use SDK equivalents
- [ ] No `random()` — use SDK random
- [ ] No HTTP calls / DB queries — delegate to activities
- [ ] No threading or sleep — use `Workflow.sleep()` / `asyncio` Temporal API
- [ ] No global mutable state

```python
# Python — minimal deterministic workflow
@workflow.defn
class OrderWorkflow:
    @workflow.run
    async def run(self, input: OrderInput) -> str:
        await workflow.execute_activity(
            reserve_inventory,
            args=[input.order_id, input.product_id],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            charge_payment,
            args=[input.order_id, input.amount_cents],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(non_retryable_error_types=["InsufficientFundsError"]),
        )
        return f"Order {input.order_id} complete"
```

For Saga pattern with compensation, see `implementation-playbook.md#saga`.

---

## Phase 5 — Register Worker

Worker binds workflow + activity implementations to a task queue. Run as a separate process from your API server.

```bash
# Python — separate worker process (SIGTERM drains via graceful_shutdown_timeout: implementation-playbook.md)
uv run python -m src.worker

# Java — Spring Boot auto-registers via application.yml
mvn spring-boot:run

# NestJS — separate worker process
npm run start:worker
```

Worker must be running BEFORE any workflow is started. Workers pull tasks from Temporal server.

---

## Phase 6 — Start Workflows via REST API

Expose workflow start as a POST endpoint. Workflow ID must be deterministic (use entity ID).

```python
# Python / FastAPI (client on app.state from the lifespan)
@app.post("/orders", status_code=202)
async def create_order(order: OrderInput, request: Request) -> dict[str, str]:
    handle = await request.app.state.temporal.start_workflow(
        OrderSagaWorkflow.run,
        order,
        id=f"order-{order.order_id}",      # business key
        task_queue="order-processing",
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,  # client retry -> same execution
    )
    return {"workflow_id": handle.id}      # never await handle.result() in the request
```

**Workflow ID rule:** Use the entity's natural key (`order-{order_id}`, `cart-{user_id}`). By default a second start with the ID of a running workflow raises `WorkflowAlreadyStartedError`; pass `id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING` to get the existing execution instead (both executed on temporalio 1.36.1).

---

## Phase 7 — Test

Temporal provides a test environment with time-skipping. Use it for all workflow tests.

```python
# Python — workflow test with time-skipping (temporalio 1.36.1; pytest-asyncio module loop scope)
import uuid
from collections.abc import AsyncIterator

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as e:
        yield e


async def test_declined_payment_compensates(env: WorkflowEnvironment) -> None:
    ledger = Ledger(decline_payment=True)  # activity object with recorded calls
    queue = f"q-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=queue, workflows=[OrderSagaWorkflow],
                      activities=[ledger.reserve_inventory, ledger.release_inventory, ledger.charge_payment,
                                  ledger.refund_payment, ledger.fulfil_order]):
        with pytest.raises(WorkflowFailureError):
            await env.client.execute_workflow(OrderSagaWorkflow.run, ORDER, id=f"order-{uuid.uuid4()}",
                                              task_queue=queue)
    assert ledger.calls.count("charge") == 1          # non-retryable: one attempt
    assert ledger.calls[-2:] == ["refund", "release"]  # LIFO compensation
```

---

## Phase 8 — Observe in Temporal Web UI

```
http://localhost:8080
```

| View | What to Check |
|------|--------------|
| Workflows → Running | Active executions, task queue assignment |
| Workflow Detail → History | Event replay log — every activity start/complete/fail |
| Workflow Detail → Pending | Stuck activities, missing worker, heartbeat failures |
| Task Queues | Worker registration, pollers alive |

**Common issues:**
- **Workflow stuck in Running** — worker is down or not registered to correct task queue
- **Activity failing with non-retryable** — check error type classification in activity code
- **Workflow history growing unbounded** — too many activities in one workflow; use child workflows

---

## Phase 9 — Code Review Gate

Before merging any Temporal workflow code:

- [ ] Dispatch `architect-review` — verify workflow/activity boundaries, saga completeness
- [ ] Dispatch `security-reviewer` — no secrets in workflow state, activity input validation, 2MB payload limit not exceeded
- [ ] Determinism checklist passed (Phase 4)
- [ ] All activities are idempotent (verified, not assumed)
- [ ] Retry policy configured with explicit non-retryable error types
- [ ] Tests cover happy path + at least one failure + saga compensation

---

## Related Workflows

| Workflow | When |
|----------|------|
| [feature-agentic-ai.md](feature-agentic-ai.md) | AI agents that trigger durable workflows |
| [feature-java-spring.md](feature-java-spring.md) | Java backend hosting Temporal workers |
| [feature-python-fastapi.md](feature-python-fastapi.md) | Python backend hosting Temporal workers |
| [feature-nestjs.md](feature-nestjs.md) | NestJS backend hosting Temporal workers |
| [architecture-design.md](architecture-design.md) | Deciding whether Temporal fits the architecture |
